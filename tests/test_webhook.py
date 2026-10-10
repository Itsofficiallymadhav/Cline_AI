from fastapi.testclient import TestClient

from src.channel.twilio_webhook import compute_signature, split_text, twiml
from src.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_text_message_gets_twiml_reply():
    r = client.post("/twilio/whatsapp", data={"From": "whatsapp:+910000000001", "Body": "hi", "NumMedia": "0"})
    assert r.status_code == 200 and "<Message>" in r.text and "English" in r.text


def test_conversation_over_webhook():
    f = {"From": "whatsapp:+910000000002", "NumMedia": "0"}
    client.post("/twilio/whatsapp", data={**f, "Body": "hi"})
    client.post("/twilio/whatsapp", data={**f, "Body": "2"})
    client.post("/twilio/whatsapp", data={**f, "Body": "1001"})
    r = client.post("/twilio/whatsapp", data={**f, "Body": "1"})
    assert "36" in r.text


def test_xml_is_escaped_and_long_text_split():
    assert "&amp;" in twiml("a & b")
    parts = split_text("x" * 100 + "\n" + "y" * 100, 150)
    assert len(parts) == 2


def test_twilio_signature_algorithm_known_vector():
    # Vector from Twilio's documentation algorithm: HMAC-SHA1(token, url + sorted key+value), base64.
    sig = compute_signature("https://mycompany.com/myapp.php?foo=1&bar=2",
                            {"Digits": "1234", "To": "+18005551212", "From": "+14158675310", "Caller": "+14158675310", "CallSid": "CA1234567890ABCDE"},
                            "12345")
    assert sig == "GvWf1cFY/Q7PnoempGyD5oXAezc="
