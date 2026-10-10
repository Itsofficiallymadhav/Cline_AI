"""Free text -> validated fields.   OWNER: T2

TODO(T2): implement extract_fields(text, language=None) -> ExtractedFields
  1. Regex fallback (MUST work with no API key): job card = first run of 3+ digits after normalising Unicode digits
     (src.ai.utils.normalize_digits) and joining spaced/dashed digits ("1 0 0 1" -> "1001").
     issue_type: "unpaid" if text says not paid / नहीं मिला|मिले|मिली; "delay" if late/delay/देर/देरी; else "unknown".
  2. Optional LLM pass via src.ai.llm.complete_json for spoken number words ("one zero zero one").
     VALIDATE the output (ExtractedFields + digits-only job card); on anything odd keep the regex result.
"""
from __future__ import annotations
from typing import Optional

from src.engine.models import ExtractedFields


def extract_fields(text: str, language: Optional[str] = None) -> ExtractedFields:
    raise NotImplementedError("T2: implement extraction")
