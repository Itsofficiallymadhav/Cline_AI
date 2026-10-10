"""Unit tests for the AI layer (T2) that do NOT depend on T1's adapter/calculator.

CalcResult objects are constructed directly with synthetic, clearly fictional values that mirror what the engine is
specified to produce for the sample job cards (SPEC.md section 4). The LLM and HTTP are always mocked: no network.
"""
import importlib
from datetime import date

import httpx
import pytest

from src import ai, config
from src.ai import llm
from src.ai.explain import explain, is_grounded, template_explain
from src.engine.models import CalcResult, ExtractedFields, Flag, Status

explain_mod = importlib.import_module("src.ai.explain")         # src.ai.explain is shadowed by the function in __init__
transcribe_mod = importlib.import_module("src.ai.transcribe")


def delayed():          # mirrors sample 1001: 20 x 300 = 6000, paid 12 days late -> 6000 x 0.0005 x 12 = 36
    return CalcResult(status=Status.DELAYED, job_card_no="1001", worker_name="Ramesh (fictional)", village="Demo Gram",
                      wage_amount=6000.0, payment_amount=6000.0, closure_date=date(2026, 8, 1),
                      due_date=date(2026, 8, 16), payment_date=date(2026, 8, 28), delay_days=12, compensation=36.0,
                      rate_per_day=0.0005, due_days=15, formula="6000 x 0.0005 x 12 = 36")


def unpaid():           # mirrors sample 1003: 3000 wage, due 2026-09-16, as of 2026-10-10 -> 24 days -> 36
    return CalcResult(status=Status.UNPAID_OVERDUE, job_card_no="1003", worker_name="Mohan (fictional)",
                      village="Demo Gram", wage_amount=3000.0, closure_date=date(2026, 9, 1),
                      due_date=date(2026, 9, 16), as_of_date=date(2026, 10, 10), delay_days=24, compensation=36.0)


def review():           # mirrors sample 1005: days worked 20 != days paid 18
    return CalcResult(status=Status.NEEDS_REVIEW, job_card_no="1005", worker_name="Geeta (fictional)",
                      village="Demo Gram", wage_amount=6000.0, payment_amount=5400.0, flags=[Flag.DAYS_MISMATCH])


def on_time():
    return CalcResult(status=Status.ON_TIME, job_card_no="1002", worker_name="Sunita (fictional)",
                      wage_amount=4500.0, payment_amount=4500.0)


def not_found():
    return CalcResult(status=Status.NOT_FOUND, job_card_no="9999")


def fail_if_called(*a, **k):
    raise AssertionError("LLM/HTTP must not be called here")


# ---------------------------------------------------------------- extract
@pytest.mark.parametrize("text,jc", [
    ("my job card is 1001", "1001"), ("मेरा जॉब कार्ड १००१ है", "1001"), ("1 0 0 1", "1001"), ("1-0-0-1", "1001"),
    ("1001 for 20 days", "1001"), ("job card 1001 and 2002", "1001"), ("hello", None), ("", None),
])
def test_extract_job_card_regex(text, jc):
    assert ai.extract_fields(text).job_card == jc


@pytest.mark.parametrize("text,issue", [
    ("पैसे नहीं मिले 1001", "unpaid"), ("मज़दूरी नहीं मिली", "unpaid"), ("wages not paid yet", "unpaid"),
    ("payment late 1001", "delay"), ("payment delayed", "delay"), ("पैसे देरी से आए", "delay"),
    ("payment late and still not received", "unpaid"), ("1001", "unknown"),
])
def test_extract_issue_type_words(text, issue):
    assert ai.extract_fields(text).issue_type == issue


def test_llm_not_called_when_regex_finds_job_card(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", fail_if_called)
    assert ai.extract_fields("job card 1001").job_card == "1001"


@pytest.mark.parametrize("bad", [None, "not a dict", ["2002"], {"job_card": "abc"}, {"job_card": "12"},
                                 {"job_card": "10a1"}, {"job_card": True}, {"job_card": -2002}, {"job_card": None}])
def test_invalid_llm_output_is_ignored(monkeypatch, bad):
    monkeypatch.setattr(llm, "complete_json", lambda p: bad)
    assert ai.extract_fields("one zero zero one").job_card is None


def test_llm_exception_is_swallowed(monkeypatch):
    def boom(p):
        raise RuntimeError("provider down")
    monkeypatch.setattr(llm, "complete_json", boom)
    assert ai.extract_fields("one zero zero one").job_card is None


def test_valid_llm_output_is_normalised(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": "२००२", "issue_type": "unpaid"})
    f = ai.extract_fields("do zero zero do")
    assert f.job_card == "2002" and f.issue_type == "unpaid"
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": 3003, "issue_type": "bogus"})
    f = ai.extract_fields("teen zero zero teen")
    assert f.job_card == "3003" and f.issue_type == "unknown"


def test_llm_issue_type_does_not_override_regex(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": "2002", "issue_type": "delay"})
    assert ai.extract_fields("one zero zero one, not paid").issue_type == "unpaid"


# ---------------------------------------------------------------- template_explain
@pytest.mark.parametrize("lang,qualifier", [("en", "estimate"), ("hi", "अनुमान")])
def test_template_delayed_and_unpaid(lang, qualifier):
    d = template_explain(delayed(), lang)
    assert "₹6000" in d and "₹36" in d and "12" in d and qualifier in d and "Ramesh" in d
    u = template_explain(unpaid(), lang)
    assert "₹3000" in u and "₹36" in u and "24" in u and qualifier in u


@pytest.mark.parametrize("lang,flag_text", [("en", "days worked and days paid are different"),
                                            ("hi", "काम के दिन और भुगतान के दिन अलग हैं")])
def test_template_review_lists_flags_and_no_amount(lang, flag_text):
    r = review()
    r.flags = [Flag.DAYS_MISMATCH, Flag.FAILED_TRANSACTION]
    text = template_explain(r, lang)
    assert flag_text in text and ", " in text and "₹" not in text


def test_template_on_time_and_not_found():
    assert "on time" in template_explain(on_time(), "en") and "₹" not in template_explain(on_time(), "en")
    assert "9999" in template_explain(not_found(), "en") and "9999" in template_explain(not_found(), "hi")


def test_template_never_guesses_missing_engine_numbers():
    r = delayed()
    r.compensation = None
    text = template_explain(r, "en")
    assert "₹" not in text and "No compensation could be calculated" in text


def test_template_without_worker_name_does_not_invent_one():
    r = delayed()
    r.worker_name = ""
    text = template_explain(r, "en")
    assert text.startswith("Your wages of ₹6000") and is_grounded(text, r)


# ---------------------------------------------------------------- is_grounded (contract from the docstring)
def test_grounded_accepts_engine_amounts_in_any_format():
    r = delayed()
    assert is_grounded("Wage ₹6000, about ₹36 (estimate).", r)
    assert is_grounded("Wage Rs. 6,000 and ₹36.00", r)
    assert is_grounded("मज़दूरी ₹६००० और ₹३६", r)                    # Devanagari digits
    assert is_grounded("36 रुपये", r)


def test_grounded_rejects_invented_or_missing_compensation():
    r = delayed()
    assert not is_grounded("You will get ₹999 extra.", r)
    assert not is_grounded("Your wage was ₹6000.", r)              # delayed must mention compensation
    assert not is_grounded("₹36 and ₹37", r)


def test_grounded_rejects_any_amount_for_review_and_not_found():
    assert not is_grounded("You may get ₹50", review())
    assert not is_grounded("Your wage was ₹6000", review())        # even a real engine amount
    assert is_grounded("Please contact your Gram Panchayat.", review())
    assert not is_grounded("₹10", not_found())


def test_grounded_on_time_allows_engine_amounts_only():
    assert is_grounded("Your ₹4500 was paid on time.", on_time())
    assert not is_grounded("Your ₹4600 was paid on time.", on_time())



# ---------------------------------------------------------------- explain (guarded LLM rewrite)
def test_no_key_path_returns_template():
    assert config.GEMINI_API_KEY == ""                             # conftest blanks keys
    assert explain(delayed(), "en") == template_explain(delayed(), "en")


def test_grounded_rewrite_is_accepted_and_prompt_has_template(monkeypatch):
    seen = {}
    def fake(p, json_mode=False):
        seen["prompt"] = p
        return "  Your ₹6000 came 12 days late. About ₹36 may be owed (estimate).  "
    monkeypatch.setattr(llm, "complete_text", fake)
    assert explain(delayed(), "en") == "Your ₹6000 came 12 days late. About ₹36 may be owed (estimate)."
    assert template_explain(delayed(), "en") in seen["prompt"]


@pytest.mark.parametrize("rewrite", [
    "You will get ₹999 extra.",                                     # invented amount (is_grounded)
    "Your ₹6000 came 15 days late. About ₹36 (estimate).",          # wrong plain number (stricter check)
    "Your ₹6000 came 12 days late. You will get ₹36.",             # dropped the estimate qualifier
    "Your wage was ₹6000 (estimate).",                             # dropped compensation
    "", "   ", None, 42,
])
def test_unsafe_rewrites_fall_back_to_template(monkeypatch, rewrite):
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: rewrite)
    assert explain(delayed(), "en") == template_explain(delayed(), "en")


def test_hindi_rewrite_must_be_devanagari(monkeypatch):
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: "Your ₹6000 came 12 days late, ₹36 estimate.")
    assert explain(delayed(), "hi") == template_explain(delayed(), "hi")
    good = "आपकी मज़दूरी ₹6000 का भुगतान 12 दिन देर से हुआ। लगभग ₹36 मिल सकते हैं। यह अनुमान है।"
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: good)
    assert explain(delayed(), "hi") == good


def test_llm_exception_falls_back(monkeypatch):
    def boom(p, json_mode=False):
        raise RuntimeError("provider down")
    monkeypatch.setattr(llm, "complete_text", boom)
    assert explain(unpaid(), "en") == template_explain(unpaid(), "en")


@pytest.mark.parametrize("make", [review, not_found])
def test_review_and_not_found_never_call_llm(monkeypatch, make):
    monkeypatch.setattr(llm, "complete_text", fail_if_called)
    text = explain(make(), "en")
    assert text == template_explain(make(), "en") and "₹" not in text


# ---------------------------------------------------------------- draft_complaint
@pytest.mark.parametrize("lang", ["en", "hi"])
def test_complaint_uses_only_result_facts(monkeypatch, lang):
    monkeypatch.setattr(llm, "complete_text", fail_if_called)      # template-only by design
    d = ai.draft_complaint(delayed(), lang)
    for fact in ("1001", "Ramesh (fictional)", "Demo Gram", "₹6000", "₹36", "2026-08-16", "2026-08-28", "12"):
        assert fact in d
    assert is_grounded(d, delayed())


@pytest.mark.parametrize("lang,not_paid", [("en", "not paid yet"), ("hi", "अभी तक नहीं")])
def test_complaint_unpaid_says_not_paid(lang, not_paid):
    d = ai.draft_complaint(unpaid(), lang)
    assert not_paid in d and "1003" in d and "₹36" in d and "24" in d


@pytest.mark.parametrize("make", [review, on_time, not_found])
def test_no_draft_without_compensation(make):
    d = ai.draft_complaint(make(), "en")
    assert "complaint cannot be made" in d and "₹" not in d



# ---------------------------------------------------------------- transcribe (HTTP mocked)
class FakeResp:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status_code, self.payload, self.bad_json = status, payload, bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=httpx.Request("POST", "http://x"),
                                        response=httpx.Response(self.status_code))

    def json(self):
        if self.bad_json:
            raise ValueError("not json")
        return self.payload


def test_transcribe_no_key_or_empty_audio_never_calls_network(monkeypatch):
    monkeypatch.setattr(transcribe_mod.httpx, "post", fail_if_called)
    assert ai.transcribe(b"ogg", "hi") is None                     # no key (conftest)
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    assert ai.transcribe(b"", "hi") is None
    assert ai.transcribe(None, "hi") is None


def test_transcribe_success_sends_expected_request(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    seen = {}
    def fake_post(url, **kw):
        seen.update(url=url, **kw)
        return FakeResp(payload={"text": "  मेरा जॉब कार्ड 1001 है  "})
    monkeypatch.setattr(transcribe_mod.httpx, "post", fake_post)
    assert ai.transcribe(b"ogg-bytes", "hi") == "मेरा जॉब कार्ड 1001 है"
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert seen["data"]["model"] == "whisper-large-v3" and seen["data"]["language"] == "hi"
    assert seen["files"]["file"][0] == "voice.ogg" and seen["files"]["file"][1] == b"ogg-bytes"


def test_transcribe_omits_unknown_language_hint(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    seen = {}
    monkeypatch.setattr(transcribe_mod.httpx, "post",
                        lambda url, **kw: seen.update(kw) or FakeResp(payload={"text": "1001"}))
    assert ai.transcribe(b"ogg", "xx") == "1001" and "language" not in seen["data"]


@pytest.mark.parametrize("resp", [FakeResp(status=429), FakeResp(payload={"text": "   "}), FakeResp(payload={}),
                                  FakeResp(payload={"text": None}), FakeResp(bad_json=True)])
def test_transcribe_bad_responses_return_none(monkeypatch, resp):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(transcribe_mod.httpx, "post", lambda url, **kw: resp)
    assert ai.transcribe(b"ogg", "hi") is None


def test_transcribe_network_error_returns_none(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    def boom(url, **kw):
        raise httpx.ConnectTimeout("timeout")
    monkeypatch.setattr(transcribe_mod.httpx, "post", boom)
    assert ai.transcribe(b"ogg", "hi") is None



# ================================================================ added in the full-package pass
# ---------------------------------------------------------------- extract: labels beat unrelated numbers
@pytest.mark.parametrize("text,jc", [
    ("I worked 100 days at 300 per day, job card 1001", "1001"),
    ("wage ₹300 and 120 days, job card no. is 1001", "1001"),
    ("job card number: 1001, got Rs 6,000", "1001"),
    ("मैंने 100 दिन काम किया, जॉब कार्ड १००१ है", "1001"),
    ("I got 600 rupees, my card 2002", "2002"),
    ("₹6000 not paid, 1001", "1001"),                               # unlabelled, but amount is skipped
    ("I worked 120 days", None),                                    # only a day count -> no job card
    ("paid ₹300 for 15 days", None),                                # only amounts/days -> no job card
])
def test_extract_prefers_label_and_skips_amounts_and_days(text, jc):
    assert ai.extract_fields(text).job_card == jc


@pytest.mark.parametrize("text", ["workers 1001", "my papers 1001", "hours 1001", "letters 1001", "1001 रोजगार",
                                  "1001 dayshift", "Rs. 300 paid, 1001"])
def test_amount_and_day_markers_need_word_boundaries(text):
    # regression: "rs"/"inr"/"रोज"/"day" inside ordinary words must not hide the job card
    assert ai.extract_fields(text).job_card == "1001"


@pytest.mark.parametrize("text", ["Rs 300 per day", "INR 300", "300 रोज़", "300 रोज", "100 दिनों तक"])
def test_real_amount_and_day_markers_still_excluded(text):
    assert ai.extract_fields(text).job_card is None


@pytest.mark.parametrize("text", ["   ", "\n\t", None])
def test_extract_blank_or_none_is_safe_and_skips_llm(monkeypatch, text):
    monkeypatch.setattr(llm, "complete_json", fail_if_called)
    f = ai.extract_fields(text)
    assert isinstance(f, ExtractedFields) and f.job_card is None and f.issue_type == "unknown"


def test_llm_cannot_turn_an_amount_or_day_count_into_a_job_card(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": "300", "issue_type": "unpaid"})
    assert ai.extract_fields("₹300 per day, not paid").job_card is None
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": "120"})
    assert ai.extract_fields("worked 120 days").job_card is None


def test_llm_job_card_too_long_is_rejected(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": "9" * 31})
    assert ai.extract_fields("one zero zero one").job_card is None


@pytest.mark.parametrize("text", ["no payment yet", "unpaid wages", "not received my money", "पैसे नहीं मिला"])
def test_extract_more_unpaid_phrases(text):
    assert ai.extract_fields(text).issue_type == "unpaid"


def test_extracted_fields_contract_unchanged():
    f = ai.extract_fields("job card 1001 late")
    assert set(ExtractedFields.model_fields) == {"job_card", "work_period", "issue_type"}
    assert f.work_period is None and f.issue_type in ("delay", "unpaid", "other", "unknown")


# ---------------------------------------------------------------- explain: every status, both languages
@pytest.mark.parametrize("make", [delayed, unpaid, on_time, review, not_found])
@pytest.mark.parametrize("lang", ["en", "hi"])
def test_every_status_template_is_grounded_and_nonempty(make, lang):
    r = make()
    text = template_explain(r, lang)
    assert text.strip() and is_grounded(text, r)


def test_hindi_templates_are_devanagari():
    for make in (delayed, unpaid, on_time, review, not_found):
        assert explain_mod._is_meaningful_hindi(template_explain(make(), "hi"))


def test_missing_wage_for_unpaid_uses_safe_fallback_in_both_languages():
    r = unpaid()
    r.wage_amount = None
    assert "No compensation could be calculated" in template_explain(r, "en")
    assert "मुआवज़ा नहीं निकाला जा सका" in template_explain(r, "hi")


def test_missing_compensation_never_calls_llm(monkeypatch):
    monkeypatch.setattr(llm, "complete_text", fail_if_called)
    r = delayed()
    r.compensation = None
    assert "₹" not in explain(r, "en")



def test_rewrite_prompt_sends_only_the_rendered_template(monkeypatch):
    seen = {}
    def fake(p, json_mode=False):
        seen["p"] = p
        return None
    monkeypatch.setattr(llm, "complete_text", fake)
    r = delayed()
    explain(r, "en")
    assert template_explain(r, "en") in seen["p"]
    for raw in ("0.0005", "formula", "2026-08-01", "rate_per_day", "6000 x"):   # no raw record / calculation data
        assert raw not in seen["p"]


@pytest.mark.parametrize("rewrite", [
    "Job card 2002: your ₹6000 came 12 days late. About ₹36 (estimate).",     # invented job card
    "Your ₹6000 came 13 days late. About ₹36 (estimate).",                    # invented delay days
    "Your ₹6000 came 12 days late on 2026-08-28. About ₹36 (estimate).",      # date not in the template
    "Your 6000 came 12 days late. About ₹36 and 50 more (estimate).",         # invented plain number
])
def test_rewrite_with_invented_facts_is_rejected(monkeypatch, rewrite):
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: rewrite)
    assert explain(delayed(), "en") == template_explain(delayed(), "en")


def test_rewrite_may_reuse_job_card_number(monkeypatch):
    good = "Job card 1001: your ₹6000 came 12 days late. About ₹36 may be owed (estimate)."
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: good)
    assert explain(delayed(), "en") == good


def test_hindi_rewrite_with_token_devanagari_is_rejected(monkeypatch):
    mostly_english = "Your ₹6000 came 12 days late. About ₹36 may be owed. अनुमान"
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: mostly_english)
    assert explain(delayed(), "hi") == template_explain(delayed(), "hi")


def test_on_time_rewrite_accepted_only_if_grounded(monkeypatch):
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: "Sunita, your wages came on time.")
    assert explain(on_time(), "en") == "Sunita, your wages came on time."
    monkeypatch.setattr(llm, "complete_text", lambda p, json_mode=False: "Sunita, you are owed ₹10.")
    assert explain(on_time(), "en") == template_explain(on_time(), "en")


# ---------------------------------------------------------------- complaint: available vs missing information
def test_complaint_missing_optional_personal_details_uses_dash_not_invented():
    r = delayed()
    r.worker_name, r.village = "", ""
    d = ai.draft_complaint(r, "en")
    assert "I am -, job card no. 1001, village -." in d and "Ramesh" not in d


@pytest.mark.parametrize("field,value", [("due_date", None), ("wage_amount", None), ("compensation", None),
                                         ("delay_days", 0), ("payment_date", None), ("job_card_no", "  ")])
def test_complaint_missing_required_fact_returns_no_draft(field, value):
    r = delayed()
    setattr(r, field, value)
    d = ai.draft_complaint(r, "hi")
    assert d == "आपके रिकॉर्ड में मुआवज़े की कोई राशि नहीं निकली, इसलिए यहाँ शिकायत नहीं बन सकती।"


def test_complaint_unpaid_without_payment_date_is_still_eligible():
    assert "Payment status: not paid yet (24 days late)" in ai.draft_complaint(unpaid(), "en")


# ---------------------------------------------------------------- transcribe: more failure modes
def test_transcribe_oversized_audio_never_calls_network(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(transcribe_mod.httpx, "post", fail_if_called)
    assert ai.transcribe(b"x" * (transcribe_mod.MAX_AUDIO_BYTES + 1), "hi") is None


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("t"), httpx.ConnectError("c"), RuntimeError("x"), KeyError("k")])
def test_transcribe_any_exception_returns_none(monkeypatch, exc):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    def boom(url, **kw):
        raise exc
    monkeypatch.setattr(transcribe_mod.httpx, "post", boom)
    assert ai.transcribe(b"ogg", "en") is None


@pytest.mark.parametrize("payload", [["text"], "text", 42, {"text": 1001}])
def test_transcribe_malformed_json_shapes_return_none(monkeypatch, payload):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(transcribe_mod.httpx, "post", lambda url, **kw: FakeResp(payload=payload))
    assert ai.transcribe(b"ogg", "en") is None


def test_transcribe_uses_timeout_and_reads_key_at_call_time(monkeypatch):
    seen = {}
    monkeypatch.setattr(transcribe_mod.httpx, "post",
                        lambda url, **kw: seen.update(kw) or FakeResp(payload={"text": "ok"}))
    monkeypatch.setattr(config, "GROQ_API_KEY", "key-A")
    ai.transcribe(b"ogg")
    assert seen["headers"]["Authorization"] == "Bearer key-A" and seen["timeout"] == transcribe_mod.TIMEOUT_S
    monkeypatch.setattr(config, "GROQ_API_KEY", "key-B")
    ai.transcribe(b"ogg")
    assert seen["headers"]["Authorization"] == "Bearer key-B" and "language" not in seen["data"]


def test_transcribe_logs_nothing(monkeypatch, caplog, capsys):
    monkeypatch.setattr(config, "GROQ_API_KEY", "secret-key")
    monkeypatch.setattr(transcribe_mod.httpx, "post", lambda url, **kw: FakeResp(status=500))
    with caplog.at_level("DEBUG"):
        assert ai.transcribe(b"private-audio", "hi") is None
    out = capsys.readouterr()
    assert not caplog.records and "secret-key" not in out.out + out.err



# ================================================================ extract.py review: regression tests
extract_mod = importlib.import_module("src.ai.extract")


# ---------------------------------------------------------------- span overlap helper
@pytest.mark.parametrize("a,b,expected", [
    ((0, 6), (2, 4), True),     # b strictly inside a  (missed by the old start/end-inside-span check)
    ((2, 4), (0, 6), True),     # a strictly inside b
    ((0, 4), (2, 6), True),     # partial overlap, both directions
    ((2, 6), (0, 4), True),
    ((0, 4), (0, 4), True),     # identical
    ((0, 4), (4, 8), False),    # touching only: half-open spans share no character
    ((4, 8), (0, 4), False),
    ((0, 2), (5, 9), False),    # disjoint
])
def test_overlaps_is_symmetric_half_open_intersection(a, b, expected):
    assert extract_mod._overlaps(a, b) is expected
    assert extract_mod._overlaps(b, a) is expected


# ---------------------------------------------------------------- labelled priority (documented contract)
@pytest.mark.parametrize("text,jc", [
    ("worked 1200 hours, job card 1001", "1001"),              # label beats an earlier unlabelled number
    ("worked 1200 hours, job card – 1001", "1001"),            # en dash connector
    ("worked 1200 hours, job card — 1001", "1001"),            # em dash connector
    ("worked 1200 hours, job card - 1001", "1001"),            # ASCII hyphen connector
    ("जॉब कार्ड 300 रुपये, 1001", "1001"),                       # labelled number is an amount -> next candidate
    ("job card 120 days, 1001", "1001"),                       # labelled number is a day count -> next candidate
    ("job card ₹300", None),                                   # labelled amount and nothing else
    ("job card 100,000", None),                                # never the "100" prefix of a comma number
    ("job card 1001.5", None),                                 # never the "1001" prefix of a decimal
])
def test_labelled_priority_and_whole_numbers(text, jc):
    assert ai.extract_fields(text).job_card == jc


# ---------------------------------------------------------------- amounts, rates, day counts, commas, dashes, digits
@pytest.mark.parametrize("text,jc", [
    ("I earned 6,000 and my card is 1001", "1001"),            # comma amount skipped, labelled card found
    ("I earned 6,000", None),                                  # comma number is never split into "6" / "000"
    ("rate 300.50 only", None),                                # decimal is never a job card
    ("not paid,1001", "1001"),                                 # punctuation directly before the card is fine
    ("Hello.1001", "1001"),
    ("300/day, 1001", "1001"),                                 # per-day rate skipped
    ("300 प्रति दिन, 1001", "1001"),
    ("100 दिनों तक काम, १००१", "1001"),                           # plural day count + Devanagari card
    ("1001 दिनेश", "1001"),                                     # name starting with "दिन" is not a day count
    ("1–0–0–1", "1001"),                                       # spaced/dashed digits with en dash
    ("1 — 0 — 0 — 1", "1001"),                                 # em dash with spaces
    ("१ ० ० १", "1001"),                                        # spaced Devanagari digits
    ("Rs 6,000 for 20 days at ₹300 per day", None),            # everything is an amount / day count
])
def test_amounts_rates_days_commas_dashes_and_digits(text, jc):
    assert ai.extract_fields(text).job_card == jc



# ---------------------------------------------------------------- LLM output can never create a false job card
@pytest.mark.parametrize("text,reply", [
    ("I earned 6,000", {"job_card": "6000"}),                  # comma quantity from the message
    ("rate 300.50 only", {"job_card": "300"}),                 # integer part of a decimal from the message
    ("rate 300.50 only", {"job_card": "30050"}),               # decimal with the point dropped
    ("job card 100,000", {"job_card": "100000"}),              # labelled comma number the regex rejected
    ("worked 120 days", {"job_card": "0120"}),                 # same number with a leading zero
    ("work was on 16 August", {"job_card": "2026-08-16"}),     # a date must not become "20260816"
    ("one zero zero one", {"job_card": "1 0 0 1"}),            # separators are not stripped from LLM output
    ("one zero zero one", {"job_card": "1001x"}),              # trailing junk
    ("one zero zero one", {"job_card": 10.01}),                # float is not a job card
])
def test_llm_cannot_create_false_job_card(monkeypatch, text, reply):
    monkeypatch.setattr(llm, "complete_json", lambda p: reply)
    assert ai.extract_fields(text).job_card is None


def test_llm_valid_new_job_card_still_accepted(monkeypatch):
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": "१००१"})
    assert ai.extract_fields("I earned 6,000, card one zero zero one").job_card == "1001"


def test_extract_calls_llm_through_module_attribute(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "complete_json", lambda p: calls.append(p) or {"job_card": "2002"})
    assert ai.extract_fields("do zero zero do", "hi").job_card == "2002"
    assert len(calls) == 1 and "do zero zero do" in calls[0] and "Language hint: hi" in calls[0]


# ---------------------------------------------------------------- issue_type: allowed values + unpaid precedence
ALLOWED_ISSUES = ("delay", "unpaid", "other", "unknown")       # ExtractedFields.issue_type comment


def test_issue_types_match_model_contract():
    assert extract_mod.ISSUE_TYPES == ALLOWED_ISSUES
    assert ExtractedFields.model_fields["issue_type"].default == "unknown"


@pytest.mark.parametrize("text,issue", [
    ("late and not paid", "unpaid"),                           # unpaid wins regardless of order
    ("not paid, very late", "unpaid"),
    ("देरी हुई और पैसे नहीं मिले", "unpaid"),
    ("no payments yet", "unpaid"),
    ("delayed by a month", "delay"),
    ("plate 1001", "unknown"),                                 # "late" inside "plate" is not a delay
    ("translate 1001", "unknown"),
])
def test_issue_type_precedence_and_word_boundaries(text, issue):
    assert ai.extract_fields(text).issue_type == issue


@pytest.mark.parametrize("llm_issue,expected", [("OTHER", "other"), (" unpaid ", "unpaid"), ("refund", "unknown"),
                                                 (None, "unknown"), (7, "unknown")])
def test_llm_issue_type_is_validated_and_normalised(monkeypatch, llm_issue, expected):
    monkeypatch.setattr(llm, "complete_json", lambda p: {"job_card": None, "issue_type": llm_issue})
    f = ai.extract_fields("one zero zero one")
    assert f.issue_type == expected and f.issue_type in ALLOWED_ISSUES

