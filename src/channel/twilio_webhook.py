"""Twilio WhatsApp sandbox webhook (thin adapter around flow.handle_message).   OWNER: T3 (T4 helps)

Twilio console: Messaging > Try it out > WhatsApp sandbox > "When a message comes in" = https://<tunnel>/twilio/whatsapp (POST).
Each tester first sends the sandbox "join <code>" message. Twilio times out webhooks after ~15 s.

REQUIRES SETUP for live use (none of this is in the repo): TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
TWILIO_WHATSAPP_FROM and PUBLIC_BASE_URL (the exact public https base URL Twilio calls, e.g. the ngrok URL) in .env.
The `twilio` SDK is NOT a project dependency, so signature checking and the REST reply use the documented
algorithm/API directly with the existing httpx dependency. Live delivery has NOT been tested from this repo.

  compute_signature(url, params, auth_token) -> str   base64(HMAC-SHA1(token, url + "".join(k+v for sorted keys)))
  split_text(text, n=1500) -> list[str]               split on line breaks, each part <= n chars
  twiml(text) -> str                                  <Response><Message>..</Message>..</Response>, XML-escaped, split
  POST /twilio/whatsapp (form: From, Body, NumMedia, MediaUrl0, MediaContentType0, MessageSid)
     - X-Twilio-Signature is verified when TWILIO_AUTH_TOKEN and PUBLIC_BASE_URL are set (403 if wrong/missing)
     - duplicate deliveries (same MessageSid) are answered with the stored reply and NOT processed twice
     - text -> handle_message(From, text=Body) -> TwiML reply with reply.render()
     - audio -> empty TwiML at once; a BackgroundTask downloads MediaUrl0 (basic auth sid/token, follows redirects),
       calls handle_message(audio_bytes=...) and sends the reply with the Twilio REST Messages API
     - other media (images, documents...) -> polite "please type" reply; nothing is downloaded
Logging never includes tokens, phone numbers or message text.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import logging
from typing import Optional
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import Response

from src import config
from src.channel import flow, store
from src.messages import t

log = logging.getLogger(__name__)
router = APIRouter()
MAX_LEN = 1500
MAX_AUDIO_BYTES = 16 * 1024 * 1024               # WhatsApp audio limit
TWILIO_API = "https://api.twilio.com/2010-04-01"
_UNSUPPORTED_MEDIA = {
    "en": "Sorry, I can only read text and voice notes. Please type your message.",
    "hi": "माफ़ कीजिए, मैं सिर्फ़ लिखा हुआ संदेश और वॉइस नोट समझ सकता हूँ। कृपया अपना संदेश लिखें।",
}


def compute_signature(url: str, params: dict, auth_token: str) -> str:
    """Twilio's documented scheme: base64(HMAC-SHA1(auth_token, url + concatenated sorted key+value pairs))."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def split_text(text: str, n: int = MAX_LEN) -> list[str]:
    """Split on line breaks into parts of at most n characters (a single over-long line is hard-cut)."""
    parts, cur = [], ""
    for line in (text or "").split("\n"):
        while len(line) > n:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:n])
            line = line[n:]
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) <= n:
            cur = candidate
        else:
            parts.append(cur)
            cur = line
    if cur:
        parts.append(cur)
    return [p for p in parts if p.strip()] or [""]


def twiml(text: str) -> str:
    if not text:
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    msgs = "".join(f"<Message>{escape(p)}</Message>" for p in split_text(text))
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{msgs}</Response>'


def _xml(text: str, status: int = 200) -> Response:
    return Response(content=twiml(text), media_type="application/xml", status_code=status)


def _signature_ok(request: Request, params: dict) -> bool:
    token, base = config.TWILIO_AUTH_TOKEN, config.PUBLIC_BASE_URL
    if not (token and base):
        return True                                # local/dev mode: verification needs both settings
    url = base.rstrip("/") + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    expected = compute_signature(url, params, token)
    return hmac.compare_digest(expected, request.headers.get("X-Twilio-Signature", ""))


def _lang_of(user_id: str) -> Optional[str]:
    try:
        return store.get_session(user_id).get("lang")
    except store.StoreError:
        return None


def _send_whatsapp(to: str, text: str) -> None:
    """Twilio REST Messages API (used only for the asynchronous voice-note reply). No-op without credentials."""
    sid, token, sender = config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN, config.TWILIO_WHATSAPP_FROM
    if not (sid and token and sender):
        log.warning("Twilio REST credentials not configured; voice-note reply not sent")
        return
    for part in split_text(text):
        try:
            r = httpx.post(f"{TWILIO_API}/Accounts/{sid}/Messages.json", auth=(sid, token),
                           data={"From": sender, "To": to, "Body": part}, timeout=15)
            r.raise_for_status()
        except Exception as e:
            log.error("Twilio send failed: %s", type(e).__name__)      # no number, token or text in logs
            return


def _process_voice_note(user_id: str, media_url: str) -> None:
    """Background task: download the voice note, run the SAME flow, reply via REST. Never raises."""
    sid, token = config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN
    reply_text = None
    try:
        auth = (sid, token) if sid and token else None
        r = httpx.get(media_url, auth=auth, follow_redirects=True, timeout=20)
        r.raise_for_status()
        audio = r.content
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise ValueError("empty or oversized audio")
        reply_text = flow.handle_message(user_id, audio_bytes=audio).render()
    except Exception as e:
        log.error("voice note processing failed: %s", type(e).__name__)
        reply_text = t(_lang_of(user_id), "retry_audio")
    _send_whatsapp(user_id, reply_text)


@router.post("/twilio/whatsapp")
async def whatsapp_webhook(request: Request, background: BackgroundTasks) -> Response:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    if not _signature_ok(request, params):
        return Response(content="invalid signature", status_code=403, media_type="text/plain")

    user_id = params.get("From", "").strip()
    if not user_id:
        return _xml("")                                         # nothing to answer
    body = params.get("Body", "")
    try:
        num_media = int(params.get("NumMedia", "0") or 0)
    except ValueError:
        num_media = 0
    media_type = params.get("MediaContentType0", "")
    message_sid = params.get("MessageSid", "")

    if message_sid:                                             # idempotency: Twilio may redeliver
        try:
            is_new, stored = store.claim_message(message_sid)
        except store.StoreError:
            is_new, stored = True, None
        if not is_new:
            return _xml(stored or "")

    try:
        if num_media > 0 and media_type.startswith("audio/") and not body.strip():
            background.add_task(_process_voice_note, user_id, params.get("MediaUrl0", ""))
            text = ""                                           # reply arrives later via the REST API
        elif num_media > 0 and not body.strip():
            lang = _lang_of(user_id)
            text = _UNSUPPORTED_MEDIA.get(lang or config.DEFAULT_LANG, _UNSUPPORTED_MEDIA["en"])
        else:
            text = flow.handle_message(user_id, text=body).render()
    except Exception as e:                                      # flow already guards itself; belt and braces
        log.error("webhook processing failed: %s", type(e).__name__)
        if message_sid:
            try:
                store.release_message(message_sid)             # let Twilio's retry be processed normally
            except store.StoreError:
                pass
        return _xml(t(None, "fallback"))

    if message_sid:
        try:
            store.save_message_reply(message_sid, text)
        except store.StoreError:
            pass
    return _xml(text)

