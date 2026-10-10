"""Voice note -> text.   OWNER: T2

TODO(T2): transcribe(audio_bytes, language_hint=None) -> Optional[str]
  - use your STT provider (Groq-hosted Whisper free tier / Sarvam / faster-whisper). WhatsApp & Twilio voice notes are OGG/Opus.
  - return None on ANY failure (no key, network error, empty audio, empty text) - the flow then asks the user to type.
  - never raise.   Test with tests/test_ai.py::test_transcribe_returns_none_without_key (no key -> None).
"""
from __future__ import annotations
from typing import Optional


def transcribe(audio_bytes: bytes, language_hint: Optional[str] = None) -> Optional[str]:
    raise NotImplementedError("T2")
