"""Free text -> validated fields.   OWNER: T2

extract_fields(text, language=None) -> ExtractedFields
  1. Regex pass (works with NO API key): normalise Unicode digits (src.ai.utils.normalize_digits), join runs of 3+
     single digits separated by spaces or (unicode) dashes ("1 0 0 1", "1-0-0-1" -> "1001"), then pick the job card.
     Only WHOLE numbers count: never part of "6,000" or "300.50" (but "paid,1001" is fine).
       a. a number right after a job-card label ("job card 1001", "job card no. is 1001", "job card – 1001",
          "जॉब कार्ड १००१") wins - unless that number is itself an amount / per-day rate / day count;
       b. otherwise the first number of 3+ digits that is NOT an amount (₹300, Rs 300, 300 rupees/रुपये),
          NOT a per-day rate (300 per day / 300 रोज़) and NOT a day count (100 days / 100 दिन / 100 दिनों).
     issue_type: "unpaid" (not paid / unpaid / not received / no payment / नहीं मिला|मिले|मिली) wins over
     "delay" (late / delay / देर / देरी), else "unknown".
  2. LLM fallback ONLY when the regex finds no job card (e.g. spoken number words "one zero zero one"), via
     src.ai.llm.complete_json. The output is VALIDATED: job_card must be 3-30 digits (Unicode digits normalised; no
     separators, so a date like "2026-08-16" is rejected) and must not be any number already written in the message
     (the regex rejected those for a reason); issue_type must be an allowed value and only fills an "unknown" regex
     result. Anything odd (or any exception) is ignored and the regex result is kept.
"""
from __future__ import annotations
import json
import re
from typing import Any, Optional

from src.ai import llm
from src.ai.utils import normalize_digits
from src.engine.models import ExtractedFields

ISSUE_TYPES = ("delay", "unpaid", "other", "unknown")

_DASHES = r"\-\u2010-\u2015"                                           # hyphen + unicode dashes (‐ ‑ ‒ – — ―)
_SEP = rf"[ \t{_DASHES}]"
_SPACED_DIGITS_RE = re.compile(rf"(?<!\d)\d(?:{_SEP}+\d(?!\d)){{2,}}")  # "1 0 0 1", "1-0-0-1" (single digits only)
# A WHOLE number of 3+ digits: not glued to other digits and not part of "6,000" / "300.50" ("paid,1001" is fine).
# Both sides need two checks; a single "(?![\d.,]\d)" would let "1001.5" match as "100".
_WHOLE_NUMBER = r"(?<!\d)(?<!\d[.,])\d{3,}(?!\d)(?![.,]\d)"
_JOB_CARD_RE = re.compile(_WHOLE_NUMBER)
_NUMBER_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")                    # any number as written: 1001, 6,000, 300.50
_VALID_JOB_CARD_RE = re.compile(r"[0-9]{3,30}")
_LABELLED_RE = re.compile(
    r"(?:job\s*card|jobcard|जॉब\s*कार्ड|जाब\s*कार्ड|कार्ड)"
    r"(?:\s*(?:no\.?|number|num|#|नंबर|नम्बर|संख्या))?"
    rf"(?:\s*(?:is|:|=|है|[{_DASHES}]))?\s*({_WHOLE_NUMBER})",
    re.IGNORECASE,
)
# Devanagari LETTERS and vowel signs only - excludes "।" "॥" (U+0964/5) and digits, which may follow a word.
_DEVA_LETTER = r"[\u0900-\u0963\u0971-\u097F]"
_NOT_JOB_CARD_RES = (                                                  # numbers that are clearly NOT a job card
    # \b / lookahead guards: "workers 1001" is not "rs 1001"; "1001 रोजगार"/"1001 दिनेश" are not "रोज"/"दिन"
    re.compile(r"(?:₹|\b(?:rs\.?|inr))\s*\d[\d,]*(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:रुपये|रुपए|रुपया|\brupees?\b|/-)", re.IGNORECASE),
    re.compile(rf"\d[\d,]*(?:\.\d+)?\s*(?:/\s*day\b|per\s+day\b|a\s+day\b|प्रति\s*दिन(?!{_DEVA_LETTER})"
               rf"|रोज़?(?!{_DEVA_LETTER}))", re.IGNORECASE),
    re.compile(rf"\d+\s*(?:days?\b|दिन(?:ों)?(?!{_DEVA_LETTER}))", re.IGNORECASE),
)
_UNPAID_RE = re.compile(
    r"\b(?:not\s+(?:yet\s+)?(?:been\s+)?(?:paid|received)|unpaid|no\s+payments?|never\s+(?:paid|received))\b"
    r"|नहीं\s*मिल[ाेी]",
    re.IGNORECASE,
)
_DELAY_RE = re.compile(r"\b(?:late|delay\w*)\b|देर", re.IGNORECASE)   # देर also covers देरी


def _join_spaced_digits(text: str) -> str:
    return _SPACED_DIGITS_RE.sub(lambda m: re.sub(r"\D", "", m.group(0)), text)


def _canon(digits: str) -> str:
    """Compare numbers by value: "0300" and "300" are the same number."""
    return digits.lstrip("0") or "0"


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Half-open spans [start, end) share at least one character (covers partial overlap AND containment)."""
    return a[0] < b[1] and b[0] < a[1]


def _excluded_spans(joined: str) -> list[tuple[int, int]]:
    """Spans the message uses as amounts / per-day rates / day counts."""
    return [m.span() for rx in _NOT_JOB_CARD_RES for m in rx.finditer(joined)]


def _is_excluded(span: tuple[int, int], excluded: list[tuple[int, int]]) -> bool:
    return any(_overlaps(span, x) for x in excluded)


def _numbers_in(joined: str) -> set[str]:
    """Every number written in the message, by value: "6,000" -> "6000"; "300.50" -> "300" and "30050"."""
    out = set()
    for m in _NUMBER_TOKEN_RE.finditer(joined):
        token = m.group(0).replace(",", "")
        out.update(_canon(d) for d in (token.split(".")[0], token.replace(".", "")))
    return out


def _regex_job_card(joined: str) -> Optional[str]:
    excluded = _excluded_spans(joined)
    for m in _LABELLED_RE.finditer(joined):      # a. labelled number wins, unless it is an amount / day count
        if not _is_excluded(m.span(1), excluded):
            return m.group(1)
    for m in _JOB_CARD_RE.finditer(joined):      # b. first unlabelled whole number that is not an amount / day count
        if not _is_excluded(m.span(), excluded):
            return m.group(0)
    return None


def _issue_type(normalised: str) -> str:
    if _UNPAID_RE.search(normalised):
        return "unpaid"
    if _DELAY_RE.search(normalised):
        return "delay"
    return "unknown"


def _valid_job_card(value: Any) -> Optional[str]:
    """LLM output -> digits-only job card, or None if it is not clearly a job card number.

    Separators are NOT stripped: "2026-08-16" (a date) must not become job card "20260816".
    Negative ints fail the digits-only check ("-2002").
    """
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    digits = normalize_digits(str(value)).strip()
    return digits if _VALID_JOB_CARD_RE.fullmatch(digits) else None


def _llm_fields(text: str, language: Optional[str]) -> Optional[dict]:
    prompt = (
        "Extract fields from a message sent by an MNREGA worker. Reply with JSON only, exactly: "
        '{"job_card": <string of digits or null>, "issue_type": "delay" | "unpaid" | "other" | "unknown"}. '
        'Convert spoken number words in any language (for example "one zero zero one" or "एक शून्य शून्य एक") '
        "to digits. If no job card number is clearly stated, use null. Do not guess.\n"
        f"Language hint: {language or 'unknown'}\n"
        f"Message: {json.dumps(text, ensure_ascii=False)}"
    )
    try:
        data = llm.complete_json(prompt)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def extract_fields(text: str, language: Optional[str] = None) -> ExtractedFields:
    raw = text if isinstance(text, str) else ""
    joined = _join_spaced_digits(normalize_digits(raw))
    job_card = _regex_job_card(joined)
    issue_type = _issue_type(joined)

    if job_card is None and raw.strip():
        data = _llm_fields(raw, language)
        if data:
            candidate = _valid_job_card(data.get("job_card"))
            if candidate is not None and _canon(candidate) not in _numbers_in(joined):
                job_card = candidate                    # never promote a number the regex already rejected
            llm_issue = data.get("issue_type")
            if issue_type == "unknown" and isinstance(llm_issue, str) and llm_issue.strip().lower() in ISSUE_TYPES:
                issue_type = llm_issue.strip().lower()

    return ExtractedFields(job_card=job_card, issue_type=issue_type)
