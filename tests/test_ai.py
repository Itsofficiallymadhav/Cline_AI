"""Acceptance tests for the AI layer (T2). The LLM is always mocked."""
from datetime import date

from src import ai
from src.ai import llm
from src.ai.explain import explain, is_grounded
from src.engine.calculator import calculate
from src.engine.models import Status
from src.adapters import get_adapter


def result(jc):
    return calculate(get_adapter().get_records(jc)[0])


def test_extract_job_card_ascii_and_devanagari_and_spaced():
    assert ai.extract_fields("my job card is 1001").job_card == "1001"
    assert ai.extract_fields("मेरा जॉब कार्ड १००१ है").job_card == "1001"
    assert ai.extract_fields("1 0 0 1").job_card == "1001"
    assert ai.extract_fields("hello").job_card is None


def test_extract_issue_type():
    assert ai.extract_fields("पैसे नहीं मिले 1001").issue_type == "unpaid"
    assert ai.extract_fields("payment late 1001").issue_type == "delay"


def test_llm_extraction_is_validated(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": "abc", "issue_type": "delay"})   # invalid -> ignored
    assert ai.extract_fields("job card 1001").job_card == "1001"
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": "२००२", "issue_type": "delay"})
    assert ai.extract_fields("do zero zero do").job_card == "2002"


def test_explain_contains_engine_amount_and_no_other_amount():
    for lang in ("en", "hi"):
        r = result("1001")
        text = explain(r, lang)
        assert is_grounded(text, r)
        assert "36" in text and "6000" in text


def test_llm_rewrite_with_invented_amount_is_rejected(monkeypatch):
    r = result("1001")
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: "You will get ₹999 extra.")
    text = explain(r, "en")
    assert "999" not in text and "36" in text      # fell back to template


def test_llm_rewrite_that_keeps_numbers_is_accepted(monkeypatch):
    r = result("1001")
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: "Your ₹6000 came 12 days late. About ₹36 may be owed (estimate).")
    assert explain(r, "en").startswith("Your ₹6000 came 12 days late")


def test_needs_review_never_quotes_an_amount():
    r = result("1005")
    assert r.status == Status.NEEDS_REVIEW
    text = explain(r, "en")
    assert "₹" not in text
    assert not is_grounded("You may get ₹50", r)


def test_complaint_draft_mentions_amount_and_job_card():
    r = result("1001")
    for lang in ("en", "hi"):
        d = ai.draft_complaint(r, lang)
        assert "1001" in d and "36" in d and "6000" in d


def test_transcribe_returns_none_without_key():
    assert ai.transcribe(b"fake-audio", "hi") is None
