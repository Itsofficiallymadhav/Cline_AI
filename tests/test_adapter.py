from src.adapters import get_adapter
from src.engine.calculator import calculate
from src.engine.models import Status


def test_known_and_unknown_job_card():
    a = get_adapter()
    assert len(a.get_records("1001")) == 1
    assert a.get_records("9999") == []


def test_sample_data_covers_every_case():
    a = get_adapter()
    got = {jc: calculate(a.get_records(jc)[0]).status for jc in ["1001", "1002", "1003", "1004", "1005", "1006"]}
    assert got == {"1001": Status.DELAYED, "1002": Status.ON_TIME, "1003": Status.UNPAID_OVERDUE,
                   "1004": Status.NEEDS_REVIEW, "1005": Status.NEEDS_REVIEW, "1006": Status.NEEDS_REVIEW}


def test_demo_worker_gets_36():
    r = calculate(get_adapter().get_records("1001")[0])
    assert r.delay_days == 12 and r.compensation == 36.0
