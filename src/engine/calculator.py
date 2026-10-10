"""Deterministic wage-delay + compensation engine.   OWNER: T1

NO LLM, NO network, no imports from the AI layer (a test enforces this).

TODO(T1) implement `calculate` so tests/test_calculator.py passes. Spec (see SPEC.md section 4):
  wage_amount   = days_worked x daily_wage_rate                    (muster roll)
  due_date      = muster_roll_closed_on + rules.due_days
  delay_days    = max(0, (payment_date or today) - due_date)       (unpaid -> today)
  compensation  = wage_amount x rules.rate_per_day x delay_days    (Decimal, round half up to 2 dp)
  status        = on_time | delayed (paid late) | unpaid_overdue (unpaid & past due)
  UNCERTAINTY -> status needs_review, compensation None, flags set:
     missing_closure_date, missing_wage_data, days_mismatch (days_worked != days_paid),
     wage_rate_mismatch (payment_amount != days_paid x daily_wage_rate), failed_transaction (payment_status == "failed")
  Always fill `evidence` (label/value/source) and `formula` (e.g. "6000 x 0.0005 x 12 = 36") when an amount exists.
  Set rule_verified from Rules.verified and add 'Rule values not yet verified.' to disclaimer when false.
"""
from __future__ import annotations
from datetime import date
from typing import Optional

from src import config
from src.engine.models import CalcResult, Status, WorkerRecord
from src.engine.rules import Rules, load_rules


def _today() -> date:
    return date.fromisoformat(config.AS_OF_DATE) if config.AS_OF_DATE else date.today()


def not_found(job_card_no: str) -> CalcResult:
    return CalcResult(status=Status.NOT_FOUND, job_card_no=job_card_no)


def calculate(rec: WorkerRecord, rules: Optional[Rules] = None, today: Optional[date] = None) -> CalcResult:
    raise NotImplementedError("T1: implement the calculator - see module docstring and SPEC.md")
