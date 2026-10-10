"""Plain-language explanation of an engine result.   OWNER: T2

GOLDEN RULE: restate the engine's numbers; never invent or calculate any.

  template_explain(result, language) -> str   built from src.messages (keys result_delayed / result_unpaid /
        result_on_time / result_review / not_found). For needs_review the flag texts "flag_<flag>" are joined.
  is_grounded(text, result) -> bool   True only if every amount in `text` (src.ai.utils.amounts_in) is one of
        {wage_amount, payment_amount, compensation}; if the status is delayed/unpaid_overdue the compensation MUST
        appear; a needs_review (or not_found) result must contain NO amounts.
  explain(result, language) -> str   template first; the LLM (src.ai.llm.complete_text) may only REPHRASE the finished
        template. The rewrite is used ONLY if it passes is_grounded() AND the stricter rewrite checks below;
        otherwise the template is returned. not_found / needs_review -> template only (no LLM call).

Stricter rewrite-only checks (is_grounded's contract is unchanged):
  - every plain number in the rewrite (amounts, days, job card, dates...) must be a trusted value: wage, payment,
    compensation, delay days, job card no., or a number already present in the safe template
  - delayed / unpaid rewrites must keep an "estimate" / "अनुमान" qualifier
  - Hindi rewrites must be meaningfully Devanagari (not just one Hindi character in English text)
"""
from __future__ import annotations
import re
from typing import Optional

from src.ai import llm
from src.ai.utils import amounts_in, fmt_money, normalize_digits
from src.engine.models import CalcResult, Status
from src.messages import t

_AMOUNT_STATUSES = (Status.DELAYED, Status.UNPAID_OVERDUE)
_NO_AMOUNT_STATUSES = (Status.NEEDS_REVIEW, Status.NOT_FOUND)
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ESTIMATE_RE = re.compile(r"estimate|अनुमान", re.IGNORECASE)
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LANG_NAMES = {"hi": "Hindi (Devanagari script)", "en": "English"}


def _money(x) -> str:
    """fmt_money, guarded against exponent notation for very large values (e.g. 1e+06)."""
    s = fmt_money(x)
    if "e" in s.lower():
        s = f"{float(x):.0f}" if float(x).is_integer() else f"{float(x):.2f}"
    return s


def _r2(x) -> float:
    return round(float(x), 2)


def _with_name(lang: Optional[str], key: str, name: str, **kw) -> str:
    """Fill a result_* template; with no worker name, drop the leading "{name}, " instead of inventing one."""
    if name:
        return t(lang, key, name=name, **kw)
    text = t(lang, key, name="", **kw).lstrip(" ,").strip()
    return text[:1].upper() + text[1:]


def _flag_text(lang: Optional[str], flags) -> str:
    return ", ".join(t(lang, f"flag_{getattr(f, 'value', f)}") for f in flags)


def template_explain(result: CalcResult, language: str) -> str:
    name = (result.worker_name or "").strip()
    status = result.status
    if status == Status.NOT_FOUND:
        return t(language, "not_found", jc=result.job_card_no)
    if status == Status.NEEDS_REVIEW:
        return _with_name(language, "result_review", name, flags=_flag_text(language, result.flags))
    if status == Status.ON_TIME:
        return _with_name(language, "result_on_time", name)
    if status in _AMOUNT_STATUSES:
        if result.compensation is None or result.wage_amount is None:
            return t(language, "no_calc")          # never guess a missing engine number
        key = "result_delayed" if status == Status.DELAYED else "result_unpaid"
        return _with_name(language, key, name, wage=_money(result.wage_amount), days=result.delay_days,
                          comp=_money(result.compensation))
    return t(language, "no_calc")


def _trusted_amounts(result: CalcResult) -> set[float]:
    return {_r2(v) for v in (result.wage_amount, result.payment_amount, result.compensation) if v is not None}


def is_grounded(text: str, result: CalcResult) -> bool:
    found = amounts_in(text or "")
    if result.status in _NO_AMOUNT_STATUSES:
        return not found
    if not found <= _trusted_amounts(result):
        return False
    if result.status in _AMOUNT_STATUSES:
        return result.compensation is not None and _r2(result.compensation) in found
    return True


def _plain_numbers(text: str) -> set[float]:
    out = set()
    for m in _NUMBER_RE.finditer(normalize_digits(text)):
        out.add(_r2(m.group(0).replace(",", "")))
    return out


def _trusted_numbers(result: CalcResult, template: str) -> set[float]:
    trusted = set(_trusted_amounts(result)) | _plain_numbers(template)
    trusted.add(_r2(result.delay_days))
    jc = normalize_digits(result.job_card_no or "")
    if jc.isdigit():
        trusted.add(_r2(jc))
    return trusted


def _is_meaningful_hindi(text: str) -> bool:
    """Mostly Devanagari letters: at least 10 of them and at least as many as Latin letters (names may be Latin)."""
    deva = len(_DEVANAGARI_RE.findall(text))
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return deva >= 10 and deva >= latin


def _rewrite_is_safe(rewrite: str, result: CalcResult, language: str, template: str) -> bool:
    if not is_grounded(rewrite, result):
        return False
    if not _plain_numbers(rewrite) <= _trusted_numbers(result, template):
        return False
    if result.status in _AMOUNT_STATUSES and not _ESTIMATE_RE.search(rewrite):
        return False
    if language == "hi" and not _is_meaningful_hindi(rewrite):
        return False
    return True


def _rewrite_prompt(template: str, language: str) -> str:
    lang_name = _LANG_NAMES.get(language, _LANG_NAMES["en"])
    return (
        "Rewrite the message below in simpler, shorter words for a rural worker with low literacy.\n"
        f"Write in {lang_name}. Keep every number and the ₹ symbol exactly as written. "
        "Do not add, remove, change or calculate any number, amount, date or rule. "
        "Keep the word that says this is only an estimate. Reply with the rewritten message only.\n\n"
        f"Message:\n{template}"
    )


def explain(result: CalcResult, language: str) -> str:
    template = template_explain(result, language)
    if result.status in _NO_AMOUNT_STATUSES:
        return template                             # honest fixed text; never rephrased
    if result.status in _AMOUNT_STATUSES and (result.compensation is None or result.wage_amount is None):
        return template                             # "no_calc" text: nothing to rephrase
    try:
        rewrite = llm.complete_text(_rewrite_prompt(template, language))
    except Exception:
        return template
    if not isinstance(rewrite, str) or not rewrite.strip():
        return template
    rewrite = rewrite.strip()
    return rewrite if _rewrite_is_safe(rewrite, result, language, template) else template

