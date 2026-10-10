"""Acceptance tests for the conversation engine (T3): full conversations, NO messaging provider."""
from src.channel import flow, store


def say(user, text=None, audio=None):
    return flow.handle_message(user, text=text, audio_bytes=audio)


def test_full_english_journey_to_saved_case():
    u = "u1"
    r = say(u, "hi");            assert "1. हिन्दी" in r.render() and "2. English" in r.render()
    r = say(u, "2");             assert "job card" in r.text.lower()
    r = say(u, "1001");          assert "1001" in r.text and len(r.options) == 2
    r = say(u, "1");             assert "₹36" in r.text and "estimate" in r.text.lower()
    assert [o.id for o in r.options] == ["act:calc", "act:draft", "act:cancel"]
    r = say(u, "1");             assert "Formula" in r.text and "6000 x 0.0005 x 12 = 36" in r.text
    assert [o.id for o in r.options] == ["act:draft", "act:cancel"]     # calc button disappears after use
    r = say(u, "1");             assert "complaint draft" in r.text.lower() and "36" in r.text
    r = say(u, "YES");           assert "KH-101" in r.text and "NOT yet filed" in r.text
    r = say(u, "status");        assert "KH-101" in r.text and "1001" in r.text
    assert len(store.list_cases(u)) == 1


def test_hindi_journey():
    u = "u2"
    say(u, "नमस्ते"); r = say(u, "1")
    assert "जॉब कार्ड" in r.text
    r = say(u, "१००१");  assert "1001" in r.text
    r = say(u, "हाँ");   assert "₹36" in r.text and "अनुमान" in r.text


def test_needs_review_has_no_amount_and_no_complaint_option():
    u = "u3"
    say(u, "hi"); say(u, "2"); say(u, "1005"); r = say(u, "1")
    assert "₹" not in r.text and "act:draft" not in [o.id for o in r.options]


def test_unknown_job_card_asks_again():
    u = "u4"
    say(u, "hi"); say(u, "2"); say(u, "9999"); r = say(u, "1")
    assert "No record found" in r.text and "job card" in r.text.lower()


def test_no_means_retry_job_card():
    u = "u5"
    say(u, "hi"); say(u, "2"); say(u, "1001"); r = say(u, "2")
    assert "job card number" in r.text.lower()


def test_garbage_input_does_not_crash():
    u = "u6"
    say(u, "hi"); say(u, "2")
    assert "could not understand" in say(u, "blah blah").text
    say(u, "1001")
    assert say(u, "???").options          # re-asks with the same options


def test_edit_complaint_then_approve():
    u = "u7"
    for m in ("hi", "2", "1001", "1", "2"):
        r = say(u, m)
    assert [o.id for o in r.options] == ["act:approve", "act:edit", "act:cancel"]
    say(u, "2"); r = say(u, "My own words about the delay.")
    assert "My own words" in r.text
    say(u, "YES")
    assert "My own words" in store.list_cases(u)[0].complaint_text


def test_cancel_resets_and_nothing_saved_without_approval():
    u = "u8"
    for m in ("hi", "2", "1001", "1", "2"):
        say(u, m)
    r = say(u, "cancel")
    assert "cancel" in r.text.lower()
    assert store.list_cases(u) == []


def test_voice_note_path(monkeypatch):
    monkeypatch.setattr("src.ai.transcribe", lambda audio, lang=None: "1001")
    u = "u9"
    say(u, "hi"); say(u, "2")
    r = say(u, audio=b"ogg-bytes")
    assert "1001" in r.text


def test_failed_transcription_asks_to_type(monkeypatch):
    monkeypatch.setattr("src.ai.transcribe", lambda audio, lang=None: None)
    u = "u10"
    say(u, "hi"); say(u, "2")
    r = say(u, audio=b"noise")
    assert "type" in r.text.lower()


def test_users_are_isolated():
    say("a", "hi"); say("a", "2"); say("a", "1001")
    r = say("b", "hi")
    assert "1. हिन्दी" in r.render()
