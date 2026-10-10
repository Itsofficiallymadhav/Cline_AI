"""Deterministic wage-delay + compensation engine.   OWNER: T1

No LLM, no network, no imports from the AI layer (a test enforces this). All money maths uses Decimal;
values are converted to float only when filling the CalcResult contract (src/engine/models.py).

Formulas (SPEC.md section 4, with the safety decisions agreed for the first implementation):
  gross wages   = days_worked x daily_wage_rate                           (muster roll values as given)
  due_date      = muster_roll_closed_on + rules.due_days
  delay_days    = max(0, (end_date - due_date).days - rules.delay_start_offset_days)
                  end_date = payment_date when a full payment is confirmed, else the reference date
  compensation  = gross wages x rules.rate_per_day x delay_days           (2 dp, round half up)
                  only for status delayed / unpaid_overdue, otherwise None
  outstanding   = max(0, gross - confirmed payment); shown as an Evidence entry (no model field yet)

Safety rules:
  * ANY uncertain, conflicting, missing or non-applicable input => NEEDS_REVIEW, no amounts, no compensation.
  * A rule set is applied only if it is verified (last_verified set) OR explicitly flagged synthetic_demo.
    Otherwise the result is NEEDS_REVIEW. Demo results are labelled as synthetic estimates, never as legal findings.
  * Partial payments, failed payments, unknown payment status, missing payment date and conflicting dates
    are NEEDS_REVIEW. Existing flags are reused; reasons that have no flag are recorded as Evidence.
  * The calculator never picks a scheme and never changes last_verified.
"""
from __future__ import annotations
import math
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from src import config
from src.engine.models import CalcResult, Evidence, Flag, Status, WorkerRecord
from src.engine.rules import Rules, load_rules


def _today() -> date:
    return date.fromisoformat(config.AS_OF_DATE) if config.AS_OF_DATE else date.today()


def not_found(job_card_no: str) -> CalcResult:
    return CalcResult(status=Status.NOT_FOUND, job_card_no=job_card_no)


_CENT = Decimal("0.01")
_KNOWN_PAYMENT_STATUSES = {"success", "failed", "pending"}
_BASE_DISCLAIMER = "Illustrative estimate, not a legal determination."
_UNVERIFIED_NOTE = "Rule values not yet verified."
_DEMO_NOTE = "Synthetic demo data and demo rule; not a real claim."


def _dec(value) -> Decimal:
    """float/int -> Decimal via str(), so binary float noise never enters the arithmetic."""
    return Decimal(str(value))


def _positive_finite(value) -> bool:
    """True only for a real, finite number > 0 (rejects None, NaN and +/-inf before any Decimal maths)."""
    return value is not None and math.isfinite(value) and value > 0


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _fmt(value: Decimal) -> str:
    """Plain decimal text, no exponent or trailing zeros: 6000.00 -> '6000', 1.50 -> '1.5', 0.0005 -> '0.0005'."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _disclaimer(rules: Optional[Rules], verified: bool) -> str:
    parts = [_BASE_DISCLAIMER]
    if not verified:
        parts.append(_UNVERIFIED_NOTE)
    if rules is not None and rules.synthetic_demo:
        parts.append(_DEMO_NOTE)
    return " ".join(parts)


def _rule_problems(rules: Rules, closure: Optional[date]) -> list[str]:
    """Reasons why this rule set cannot be applied to this record. Empty list => rule may be applied."""
    problems: list[str] = []
    if rules.due_days <= 0:
        problems.append("rule due_days is not a positive number")
    if not (0 < rules.rate_per_day < 1):
        problems.append("rule rate_per_day is outside the range 0 to 1")
    if rules.delay_start_offset_days < 0:
        problems.append("rule delay_start_offset_days is negative")
    if not rules.verified and not rules.synthetic_demo:
        problems.append("rule is not verified and not marked as a synthetic demo rule")
    if closure is not None:
        if rules.effective_from is not None and closure < rules.effective_from:
            problems.append("muster roll closed before the rule's effective_from date")
        if rules.effective_to is not None and closure > rules.effective_to:
            problems.append("muster roll closed after the rule's effective_to date")
    return problems


def _record_problems(rec: WorkerRecord, ref_date: date, status_text: str) -> tuple[list[Flag], list[tuple[str, str]]]:
    """Run ALL record checks (no short-circuit). Returns (existing flags, [(reason, evidence source)])."""
    flags: list[Flag] = []
    reasons: list[tuple[str, str]] = []
    closure = rec.muster_roll_closed_on

    def flag(f: Flag, reason: str, source: str = "payment_record") -> None:
        if f not in flags:
            flags.append(f)
        reasons.append((reason, source))

    if closure is None:
        flag(Flag.MISSING_CLOSURE_DATE, "muster roll closure date is missing", "muster_roll")
    elif closure > ref_date:
        reasons.append(("muster roll closure date is after the reference date", "muster_roll"))

    rate_ok = _positive_finite(rec.daily_wage_rate)
    if not (rec.days_worked is not None and rec.days_worked > 0) or not rate_ok:
        flag(Flag.MISSING_WAGE_DATA, "days worked or daily wage rate is missing, not a number or not positive", "muster_roll")
    if rec.payment_amount is not None and not math.isfinite(rec.payment_amount):
        flag(Flag.MISSING_WAGE_DATA, "payment amount is not a finite number")

    if status_text not in _KNOWN_PAYMENT_STATUSES:
        flag(Flag.MISSING_WAGE_DATA, f"unknown payment status '{rec.payment_status}'")
    elif status_text == "failed":
        flag(Flag.FAILED_TRANSACTION, "the payment transaction failed")
    elif status_text == "pending":
        if rec.payment_date is not None or rec.payment_amount is not None or rec.days_paid is not None:
            reasons.append(("payment is marked pending but payment details are present", "payment_record"))
    else:  # "success": the single recorded payment must be complete and consistent
        if rec.payment_date is None:
            flag(Flag.MISSING_WAGE_DATA, "payment is marked successful but the payment date is missing")
        if rec.payment_amount is None or rec.days_paid is None:
            flag(Flag.MISSING_WAGE_DATA, "payment is marked successful but paid days or amount is missing")
        if rec.days_paid is not None and rec.days_worked is not None and rec.days_paid != rec.days_worked:
            flag(Flag.DAYS_MISMATCH, "days paid differ from days worked (partial or inconsistent payment)")
        if rec.payment_amount is not None and math.isfinite(rec.payment_amount) and rec.days_paid is not None and rate_ok:
            expected = _money(_dec(rec.days_paid) * _dec(rec.daily_wage_rate))
            if _money(_dec(rec.payment_amount)) != expected:
                flag(Flag.WAGE_RATE_MISMATCH, "amount paid does not equal days paid x daily wage rate")

    if rec.payment_date is not None:
        if rec.payment_date > ref_date:
            reasons.append(("payment date is after the reference date", "payment_record"))
        if closure is not None and rec.payment_date < closure:
            reasons.append(("payment date is before the muster roll closure date", "payment_record"))
    return flags, reasons


def _review_result(rec: WorkerRecord, rules: Optional[Rules], ref_date: date, flags: list[Flag],
                   reasons: list[tuple[str, str]], rule_ok: bool) -> CalcResult:
    """NEEDS_REVIEW: no amounts, no compensation. Reasons are listed as Evidence."""
    closure = rec.muster_roll_closed_on
    verified = bool(rules.verified) if rules is not None else False
    evidence = [Evidence(label="Review reason", value=text, source=src) for text, src in reasons]
    evidence += [
        Evidence(label="Muster roll closed (unreconciled)", value=str(closure) if closure else "missing", source="muster_roll"),
        Evidence(label="Days worked (unreconciled)", value=str(rec.days_worked) if rec.days_worked is not None else "missing", source="muster_roll"),
        Evidence(label="Payment status (unreconciled)", value=rec.payment_status or "missing", source="payment_record"),
    ]
    use_rule = rules is not None and rule_ok
    return CalcResult(
        status=Status.NEEDS_REVIEW,
        job_card_no=rec.job_card_no, worker_name=rec.worker_name, village=rec.village,
        closure_date=closure, as_of_date=ref_date,
        due_days=rules.due_days if use_rule else 0,
        rate_per_day=rules.rate_per_day if use_rule else 0.0,
        flags=flags, evidence=evidence,
        rule_source=rules.source if rules is not None else "",
        rule_verified=verified,
        disclaimer=_disclaimer(rules, verified),
    )


def calculate(rec: WorkerRecord, rules: Optional[Rules] = None, today: Optional[date] = None) -> CalcResult:
    ref_date = today or _today()
    closure = rec.muster_roll_closed_on
    status_text = (rec.payment_status or "").strip().lower()

    # Rule set: never picked silently. It must be verified OR an explicit synthetic demo rule.
    if rules is None:
        try:
            rules = load_rules()
        except Exception:
            rules = None
    reasons: list[tuple[str, str]] = []
    if rules is None:
        reasons.append(("rule file is missing or unreadable", "rule"))
        rule_ok = False
    else:
        problems = _rule_problems(rules, closure)
        reasons.extend((p, "rule") for p in problems)
        rule_ok = not problems

    flags, record_reasons = _record_problems(rec, ref_date, status_text)
    reasons.extend(record_reasons)
    if reasons:
        return _review_result(rec, rules, ref_date, flags, reasons, rule_ok)

    # Inputs are complete, consistent and the rule applies. All checks above guarantee these are set.
    assert rules is not None and closure is not None
    assert rec.days_worked is not None and rec.daily_wage_rate is not None
    daily_rate = _dec(rec.daily_wage_rate)
    gross = _money(_dec(rec.days_worked) * daily_rate)
    rate = _dec(rules.rate_per_day)
    due_date = closure + timedelta(days=rules.due_days)

    fully_paid = status_text == "success"      # days, amount and date were verified as consistent above
    end_date = rec.payment_date if fully_paid else ref_date
    assert end_date is not None
    delay_days = max(0, (end_date - due_date).days - rules.delay_start_offset_days)
    confirmed = _money(_dec(rec.payment_amount)) if fully_paid else Decimal("0")
    outstanding = max(Decimal("0"), gross - confirmed)

    if delay_days == 0:
        status = Status.ON_TIME
    else:
        status = Status.DELAYED if fully_paid else Status.UNPAID_OVERDUE

    compensation: Optional[Decimal] = None
    formula = ""
    if status in (Status.DELAYED, Status.UNPAID_OVERDUE):
        compensation = _money(gross * rate * delay_days)
        formula = f"{_fmt(gross)} x {_fmt(rate)} x {delay_days} = {_fmt(compensation)}"

    evidence = [
        Evidence(label="Days worked", value=str(rec.days_worked), source="muster_roll"),
        Evidence(label="Daily wage rate", value=_fmt(daily_rate), source="muster_roll"),
        Evidence(label="Gross wages", value=_fmt(gross), source="muster_roll"),
        Evidence(label="Muster roll closed", value=str(closure), source="muster_roll"),
        Evidence(label="Payment due date", value=f"{due_date} (closure + {rules.due_days} days)", source="rule"),
        Evidence(label="Delay start offset (days)", value=str(rules.delay_start_offset_days), source="rule"),
        Evidence(label="Daily compensation rate", value=_fmt(rate), source="rule"),
        Evidence(label="Rule set", value=f"{rules.scheme or 'unnamed'} {rules.version}".strip(), source="rule"),
        Evidence(label="Payment status", value=status_text, source="payment_record"),
        Evidence(label="Payment date", value=str(rec.payment_date) if rec.payment_date else "not paid yet", source="payment_record"),
        Evidence(label="Confirmed payment", value=_fmt(confirmed), source="payment_record"),
        Evidence(label="Outstanding wages", value=_fmt(outstanding), source="payment_record"),
        Evidence(label="Reference date", value=str(ref_date), source="rule"),
    ]
    verified = bool(rules.verified)
    return CalcResult(
        status=status,
        job_card_no=rec.job_card_no, worker_name=rec.worker_name, village=rec.village,
        wage_amount=float(gross),
        payment_amount=float(confirmed) if fully_paid else None,
        closure_date=closure, due_date=due_date,
        payment_date=rec.payment_date if fully_paid else None,
        as_of_date=ref_date, delay_days=delay_days,
        compensation=float(compensation) if compensation is not None else None,
        rate_per_day=float(rate), due_days=rules.due_days,
        formula=formula, evidence=evidence,
        rule_source=rules.source, rule_verified=verified,
        disclaimer=_disclaimer(rules, verified),
    )
