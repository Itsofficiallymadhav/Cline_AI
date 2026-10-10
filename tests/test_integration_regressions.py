"""Integration regressions (added during the main-branch integration pass). Additions only; offline; synthetic data."""
import re

from fastapi.testclient import TestClient

from src.channel import flow
from src.main import app
from src.messages import M

client = TestClient(app)
_LATIN_WORD = re.compile(r"[A-Za-z]{4,}")
NEW_KEYS = ("service_error", "approve_by_typing", "unsupported_media", "voice_unavailable", "rule_unverified",
            "demo_rule", "st_HANDED_OVER", "st_WITHDRAWN", "st_CLOSED", "rs_on_time", "rs_delayed",
            "rs_unpaid_overdue", "rs_needs_review", "rs_not_found")


def test_new_message_keys_exist_in_every_language():
    for lang, texts in M.items():
        for key in NEW_KEYS:
            assert texts.get(key, "").strip(), f"{lang} is missing {key}"


def test_voice_note_without_keys_gets_immediate_please_type_reply():
    f = {"From": "whatsapp:+910000000077", "NumMedia": "1", "MediaContentType0": "audio/ogg",
         "MediaUrl0": "https://example.invalid/media/1", "Body": ""}
    r = client.post("/twilio/whatsapp", data=f)
    assert r.status_code == 200 and "<Message>" in r.text and "type" in r.text.lower()


def test_hindi_calculation_view_has_no_english_engine_text():
    u = "regress-hi-calc"
    for msg in ("hi", "1", "1001", "1"):        # Hindi -> job card -> confirm
        flow.handle_message(u, text=msg)
    r = flow.handle_message(u, text="1")        # "हिसाब देखें"
    assert M["hi"]["calc"].split(":")[0] in r.text   # really the calculation view
    body = r.text.split("\n\n")
    words = {w for part in body for w in _LATIN_WORD.findall(part)}
    assert not ({"Illustrative", "verified", "Synthetic", "Rule"} & words), words
    assert M["hi"]["rule_unverified"] in r.text
