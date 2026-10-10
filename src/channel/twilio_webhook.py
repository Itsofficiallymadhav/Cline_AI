"""Twilio WhatsApp sandbox webhook (thin adapter around flow.handle_message).   OWNER: T3 (T4 helps)

Twilio console: Messaging > Try it out > WhatsApp sandbox > "When a message comes in" = https://<tunnel>/twilio/whatsapp (POST).
Each tester first sends the sandbox "join <code>" message. Twilio times out webhooks after ~15 s.
TODO implement so tests/test_webhook.py passes:
  compute_signature(url, params, auth_token) -> str   base64(HMAC-SHA1(token, url + "".join(k+v for sorted keys)))
  split_text(text, n=1500) -> list[str]               split on line breaks, each part <= n chars where possible
  twiml(text) -> str                                  <Response><Message>..</Message>..</Response>, XML-escaped, split
  POST /twilio/whatsapp (form: From, Body, NumMedia, MediaUrl0, MediaContentType0)
     - verify X-Twilio-Signature when TWILIO_AUTH_TOKEN and PUBLIC_BASE_URL are set (403 if wrong)
     - text -> handle_message(From, text=Body) -> TwiML reply with reply.render()
     - audio -> return empty TwiML at once; in a BackgroundTask download MediaUrl0 (basic auth sid/token, follow redirects),
       call handle_message(audio_bytes=...) and send the reply with the Twilio REST Messages API
"""
from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()
MAX_LEN = 1500


def compute_signature(url: str, params: dict, auth_token: str) -> str:
    raise NotImplementedError("T3/T4")


def split_text(text: str, n: int = MAX_LEN) -> list[str]:
    raise NotImplementedError("T3/T4")


def twiml(text: str) -> str:
    raise NotImplementedError("T3/T4")

# TODO: @router.post("/twilio/whatsapp") ...
