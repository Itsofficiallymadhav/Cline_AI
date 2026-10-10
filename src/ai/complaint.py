"""Complaint draft.   OWNER: T2

draft_complaint(result, language) -> str   filled from the "complaint" template in src.messages using ONLY the engine
result (name, job card, village, wage, due date, payment date or 'not paid yet', delay days, compensation).
Template-only by design: the worker signs this text, so no LLM polish. Nothing is calculated here, and the draft is
only RETURNED - never saved, sent or filed (the flow saves it only after explicit approval).

Eligibility (mirrors the engine contract): status delayed / unpaid_overdue AND the facts the complaint asserts are
present - job card no., wage_amount, compensation, due_date and delay_days > 0. Otherwise "no_draft_needed".
A delayed result must also carry its payment_date (otherwise "paid late" cannot be stated).
Optional personal details (worker name, village) are shown as "-" when absent - never invented.
"""
from __future__ import annotations

from src.ai.utils import fmt_money as _money
from src.engine.models import CalcResult, Status
from src.messages import t

_MISSING = "-"


def _eligible(result: CalcResult) -> bool:
    if result.status not in (Status.DELAYED, Status.UNPAID_OVERDUE):
        return False
    if not (result.job_card_no or "").strip():
        return False
    if result.compensation is None or result.wage_amount is None or result.due_date is None:
        return False
    if result.delay_days <= 0:
        return False
    if result.status == Status.DELAYED and result.payment_date is None:
        return False
    return True


def draft_complaint(result: CalcResult, language: str) -> str:
    if not _eligible(result):
        return t(language, "no_draft_needed")
    return t(
        language, "complaint",
        name=(result.worker_name or "").strip() or _MISSING,
        jc=result.job_card_no.strip(),
        village=(result.village or "").strip() or _MISSING,
        wage=_money(result.wage_amount),
        due=result.due_date.isoformat(),
        paid=result.payment_date.isoformat() if result.payment_date else t(language, "not_paid"),
        days=result.delay_days,
        comp=_money(result.compensation),
    )
