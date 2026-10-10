"""Acceptance tests for the deterministic engine (T1). Do not weaken these to make code pass."""
from datetime import date
from pathlib import Path

from src.engine import calculator
from src.engine.calculator import calculate
from src.engine.models import Flag, Status, WorkerRecord
from src.engine.rules import Rules, load_rules

RULES = Rules(due_days=15, rate_per_day=0.0005, last_verified="2026-10-10")   # fixed test rules
TODAY = date(2026, 10, 10)


def rec(**kw) -> WorkerRecord:
    base = dict(job_card_no="T1", worker_name="Test", village="V", muster_roll_closed_on=date(2026, 8, 1),
                days_worked=10, daily_wage_rate=300, days_paid=10, payment_amount=3000,
                payment_date=date(2026, 8, 16), payment_status="success")      # due date = 2026-08-16
    base.update(kw)
    return WorkerRecord(**base)


def test_rules_file_loads():
    r = load_rules()
    assert r.due_days > 0 and 0 < r.rate_per_day < 1


def test_on_time():
    r = calculate(rec(payment_date=date(2026, 8, 16)), RULES, TODAY)
    assert r.status == Status.ON_TIME and r.delay_days == 0 and r.compensation is None


def test_one_day_late():
    r = calculate(rec(payment_date=date(2026, 8, 17)), RULES, TODAY)
    assert r.status == Status.DELAYED and r.delay_days == 1 and r.compensation == 1.5   # 3000*0.0005*1


def test_eight_days_late():
    r = calculate(rec(payment_date=date(2026, 8, 24)), RULES, TODAY)
    assert r.delay_days == 8 and r.compensation == 12.0
    assert "3000" in r.formula and "8" in r.formula


def test_forty_days_late():
    r = calculate(rec(payment_date=date(2026, 9, 25)), RULES, TODAY)
    assert r.delay_days == 40 and r.compensation == 60.0


def test_unpaid_uses_today():
    r = calculate(rec(payment_date=None, payment_status="pending", days_paid=None, payment_amount=None), RULES, TODAY)
    assert r.status == Status.UNPAID_OVERDUE
    assert r.delay_days == (TODAY - date(2026, 8, 16)).days and r.compensation is not None


def test_unpaid_not_yet_due_is_on_time():
    r = calculate(rec(muster_roll_closed_on=date(2026, 10, 1), payment_date=None, payment_status="pending",
                      days_paid=None, payment_amount=None), RULES, TODAY)
    assert r.status == Status.ON_TIME and r.delay_days == 0


def test_missing_closure_date_needs_review():
    r = calculate(rec(muster_roll_closed_on=None), RULES, TODAY)
    assert r.status == Status.NEEDS_REVIEW and r.compensation is None and Flag.MISSING_CLOSURE_DATE in r.flags


def test_days_mismatch_needs_review():
    r = calculate(rec(days_paid=8, payment_amount=2400, payment_date=date(2026, 9, 1)), RULES, TODAY)
    assert r.status == Status.NEEDS_REVIEW and r.compensation is None and Flag.DAYS_MISMATCH in r.flags


def test_wage_rate_mismatch_needs_review():
    r = calculate(rec(payment_amount=2500, payment_date=date(2026, 9, 1)), RULES, TODAY)
    assert r.status == Status.NEEDS_REVIEW and r.compensation is None and Flag.WAGE_RATE_MISMATCH in r.flags


def test_failed_transaction_needs_review():
    r = calculate(rec(payment_status="failed", payment_date=None), RULES, TODAY)
    assert r.status == Status.NEEDS_REVIEW and r.compensation is None and Flag.FAILED_TRANSACTION in r.flags


def test_demo_example_6000_12_days_is_36():
    r = calculate(rec(days_worked=20, daily_wage_rate=300, days_paid=20, payment_amount=6000,
                      payment_date=date(2026, 8, 28)), RULES, TODAY)
    assert r.delay_days == 12 and r.compensation == 36.0


def test_unverified_rules_are_disclosed():
    r = calculate(rec(payment_date=date(2026, 8, 24)), Rules(due_days=15, rate_per_day=0.0005), TODAY)
    assert r.rule_verified is False and "not yet verified" in r.disclaimer.lower()


def test_engine_has_no_llm_or_network():
    src = Path(calculator.__file__).read_text()
    assert "src.ai" not in src and "httpx" not in src and "requests" not in src
