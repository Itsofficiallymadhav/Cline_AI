"""Voice note -> text.   OWNER: T2

transcribe(audio_bytes, language_hint=None) -> Optional[str]
  - Groq-hosted Whisper (OpenAI-compatible endpoint). WhatsApp & Twilio voice notes are OGG/Opus.
  - returns None on ANY failure (no key, empty audio, network/HTTP error, bad JSON, empty text) so the flow asks the
    user to type. Never raises.
  - Groq docs (speech-to-text): endpoint below, ogg is a supported upload type, 25 MB max file size on the free tier.
    config.py has no STT model/URL setting, so they are module constants here (shared config left unchanged).
  - Nothing is logged (no audio, key or transcript).
  - NOT verified against the live API yet (no key in this checkout): test once with a real WhatsApp voice note.
"""
from __future__ import annotations
from typing import Optional

import httpx

from src import config

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_STT_MODEL = "whisper-large-v3"        # lower word error rate than -turbo per Groq docs; numbers matter here
_WHISPER_LANGS = {"hi", "en"}
MAX_AUDIO_BYTES = 25 * 1024 * 1024         # Groq free-tier upload limit
TIMEOUT_S = 30


def transcribe(audio_bytes: bytes, language_hint: Optional[str] = None) -> Optional[str]:
    try:
        key = config.GROQ_API_KEY
        if not key or not isinstance(audio_bytes, (bytes, bytearray)) or not audio_bytes:
            return None
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            return None
        data = {"model": GROQ_STT_MODEL, "temperature": "0", "response_format": "json"}
        if language_hint in _WHISPER_LANGS:
            data["language"] = language_hint
        r = httpx.post(
            GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {key}"},
            data=data,
            files={"file": ("voice.ogg", bytes(audio_bytes), "audio/ogg")},
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        text = r.json().get("text")
        if not isinstance(text, str):
            return None
        return text.strip() or None
    except Exception:
        return None
