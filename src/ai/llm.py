"""Thin LLM wrapper (Gemini free tier). Returns None when no key / any failure, so callers ALWAYS have a fallback.
Tests monkeypatch complete_text / complete_json. STARTER: not verified against the live API."""
from __future__ import annotations
import json
from typing import Optional

import httpx
from src import config


def complete_text(prompt: str, json_mode: bool = False) -> Optional[str]:
    if not config.GEMINI_API_KEY:
        return None
    try:
        gen = {"temperature": 0.2}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": config.GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None


def complete_json(prompt: str) -> Optional[dict]:
    raw = complete_text(prompt, json_mode=True)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None
