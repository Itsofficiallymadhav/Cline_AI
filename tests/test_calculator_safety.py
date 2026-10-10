"""Extra safety tests for the deterministic engine (T1). Synthetic data only. Complements test_calculator.py.
Calculator-only: adapter tests were handed off in docs/handoff_adapter_tests_for_T1_adapter_owner.md."""
from datetime import date
from decimal import Decimal

from src.engine.calculator import _fmt, calculate
from src.engine.models import Flag, Status, WorkerRecord
from src.engine.rules import Rules, load_rules

VERIFIED = Rules(due_days=15, rate_per_day=0.0005, last_verified="2026-10-10", scheme="TEST", source="test fixture")
DEMO = Rules(due_days=15, rate_per_day=0.0005, synthetic_demo=True, scheme="DEMO_ILLUSTRATIVE")
UNVERIFIED = Rules(due_days=15, rate_per_day=0.0005)
TODAY = date(2026, 10, 10)


def rec(**kw) -> WorkerRecord:
    base = dict(job_card_no="S1", worker_name="Synthetic", village="V", muster_roll_closed_on=date(2026, 8, 1),
                days_worked=10, daily_wage_rate=300, days_paid=10, payment_amount=3000,
                payment_date=date(2026, 8, 16), payment_status="success")      # due date = 2026-08-16
    base.update(kw)
    return WorkerRecord(**base)


def assert_review(r, *flags):
    assert r.status == Status.NEEDS_REVIEW
    assert r.compensation is None and r.wage_amount is None and r.payment_amount is None and r.formula == ""
    for f in flags:
        assert f in r.flags
    assert any(e.label == "Review reason" for e in r.evidence)


# ---- rule safety ----------------------------------------------------------------------------------
def test_unverified_non_demo_rule_needs_review():
    r = calculate(rec(payment_date=date(2026, 8, 24)), UNVERIFIED, TODAY)
    assert_review(r)
    assert r.rule_verified is False and "not yet verified" in r.disclaimer.lower()


def test_demo_rule_gives_labelled_estimate_not_verified():
    r = calculate(rec(payment_date=date(2026, 8, 24)), DEMO, TODAY)
    assert r.status == Status.DELAYED and r.compensation == 12.0 and r.rule_verified is False
    assert "not yet verified" in r.disclaimer.lower() and "synthetic" in r.disclaimer.lower()


def test_verified_rule_has_no_unverified_note():
    r = calculate(rec(payment_date=date(2026, 8, 24)), VERIFIED, TODAY)
    assert r.rule_verified is True and "not yet verified" not in r.disclaimer.lower()


def test_shipped_rule_stays_unverified_and_demo():
    r = load_rules()
    assert r.last_verified is None and r.synthetic_demo is True and r.scheme == "DEMO_ILLUSTRATIVE"


def test_rule_effective_window_is_enforced():
    early = Rules(due_days=15, rate_per_day=0.0005, last_verified="2026-10-10", effective_from=date(2026, 9, 1))
    assert_review(calculate(rec(payment_date=date(2026, 8, 24)), early, TODAY))
    late = Rules(due_days=15, rate_per_day=0.0005, last_verified="2026-10-10", effective_to=date(2026, 7, 31))
    assert_review(calculate(rec(payment_date=date(2026, 8, 24)), late, TODAY))


def test_unusable_rule_values_need_review():
    for bad in (Rules(due_days=0, rate_per_day=0.0005, last_verified="x"),
                Rules(due_days=15, rate_per_day=0, last_verified="x"),
                Rules(due_days=15, rate_per_day=1.5, last_verified="x")):
        assert_review(calculate(rec(payment_date=date(2026, 8, 24)), bad, TODAY))


def test_delay_start_offset_is_configurable():
    rules = Rules(due_days=15, rate_per_day=0.0005, last_verified="x", delay_start_offset_days=1)
    assert calculate(rec(payment_date=date(2026, 8, 17)), rules, TODAY).status == Status.ON_TIME
    r = calculate(rec(payment_date=date(2026, 8, 24)), rules, TODAY)
    assert r.delay_days == 7 and r.compensation == 10.5


# ---- record problems => NEEDS_REVIEW ---------------------------------------------------------------
def test_success_without_payment_date_needs_review():
    assert_review(calculate(rec(payment_date=None), VERIFIED, TODAY), Flag.MISSING_WAGE_DATA)


def test_success_without_amount_or_days_needs_review():
    assert_review(calculate(rec(payment_amount=None), VERIFIED, TODAY), Flag.MISSING_WAGE_DATA)
    assert_review(calculate(rec(days_paid=None), VERIFIED, TODAY), Flag.MISSING_WAGE_DATA)


def test_partial_payment_needs_review():
    r = calculate(rec(days_paid=5, payment_amount=1500, payment_date=date(2026, 9, 1)), VERIFIED, TODAY)
    assert_review(r, Flag.DAYS_MISMATCH)


def test_unknown_payment_status_needs_review():
    assert_review(calculate(rec(payment_status="processing"), VERIFIED, TODAY), Flag.MISSING_WAGE_DATA)


def test_pending_with_payment_details_is_conflict():
    assert_review(calculate(rec(payment_status="pending"), VERIFIED, TODAY))


def test_payment_before_closure_needs_review():
    assert_review(calculate(rec(payment_date=date(2026, 7, 1)), VERIFIED, TODAY))


def test_future_dates_need_review():
    assert_review(calculate(rec(payment_date=date(2026, 11, 1)), VERIFIED, TODAY))
    future_closure = rec(muster_roll_closed_on=date(2026, 11, 1), payment_date=None, payment_status="pending",
                         days_paid=None, payment_amount=None)
    assert_review(calculate(future_closure, VERIFIED, TODAY))


def test_missing_or_nonpositive_wage_inputs_need_review():
    for kw in (dict(days_worked=None), dict(days_worked=0), dict(daily_wage_rate=None), dict(daily_wage_rate=-5)):
        assert_review(calculate(rec(**kw), VERIFIED, TODAY), Flag.MISSING_WAGE_DATA)


def test_all_problems_are_reported_together():
    r = calculate(rec(muster_roll_closed_on=None, days_paid=8, payment_amount=2500), VERIFIED, TODAY)
    assert_review(r, Flag.MISSING_CLOSURE_DATE, Flag.DAYS_MISMATCH, Flag.WAGE_RATE_MISMATCH)


def test_non_finite_numbers_need_review_not_crash():
    for kw in (dict(daily_wage_rate=float("nan")), dict(daily_wage_rate=float("inf")),
               dict(payment_amount=float("nan")), dict(payment_amount=float("inf"))):
        assert_review(calculate(rec(**kw), VERIFIED, TODAY), Flag.MISSING_WAGE_DATA)


def test_review_reason_sources_are_correct():
    r = calculate(rec(muster_roll_closed_on=None, days_worked=None), VERIFIED, TODAY)
    sources = {e.value: e.source for e in r.evidence if e.label == "Review reason"}
    assert sources["muster roll closure date is missing"] == "muster_roll"
    assert all(s == "muster_roll" for v, s in sources.items() if "days worked" in v)


# ---- arithmetic and output --------------------------------------------------------------------------
def test_rounding_is_half_up_decimal():
    # 90 x 0.0005 x 1 = 0.045 exactly in Decimal -> half-up 0.05 (float arithmetic or banker's rounding could give 0.04)
    r = calculate(rec(days_worked=1, days_paid=1, daily_wage_rate=90, payment_amount=90,
                      payment_date=date(2026, 8, 17)), VERIFIED, TODAY)
    assert r.compensation == 0.05


def test_formula_text_has_no_exponent_or_trailing_zeros():
    assert _fmt(Decimal("6000.00")) == "6000" and _fmt(Decimal("1.50")) == "1.5" and _fmt(Decimal("0.0005")) == "0.0005"
    r = calculate(rec(days_worked=20, days_paid=20, payment_amount=6000, payment_date=date(2026, 8, 28)), VERIFIED, TODAY)
    assert r.formula == "6000 x 0.0005 x 12 = 36"


def test_outstanding_wages_in_evidence():
    unpaid = rec(payment_status="pending", payment_date=None, days_paid=None, payment_amount=None)
    r = calculate(unpaid, VERIFIED, TODAY)
    values = {e.label: e.value for e in r.evidence}
    assert r.status == Status.UNPAID_OVERDUE and values["Outstanding wages"] == "3000" and r.payment_amount is None
    paid = {e.label: e.value for e in calculate(rec(), VERIFIED, TODAY).evidence}
    assert paid["Outstanding wages"] == "0"
