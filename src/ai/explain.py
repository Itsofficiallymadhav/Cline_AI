"""Plain-language explanation of an engine result.   OWNER: T2

GOLDEN RULE: restate the engine's numbers; never invent or calculate any.

TODO(T2):
  template_explain(result, language) -> str   build from src.messages (keys result_delayed / result_unpaid /
        result_on_time / result_review / not_found). For needs_review join the flag texts "flag_<flag>".
  is_grounded(text, result) -> bool   True only if every amount in `text` (src.ai.utils.amounts_in) is one of
        {wage_amount, payment_amount, compensation}; if the status is delayed/unpaid_overdue the compensation MUST appear;
        a needs_review result must contain NO amounts.
  explain(result, language) -> str   template first; optionally ask src.ai.llm.complete_text to rewrite it in
        simpler words; use the rewrite ONLY if is_grounded(), otherwise return the template. not_found -> template.
"""
from __future__ import annotations
from src.engine.models import CalcResult


def template_explain(result: CalcResult, language: str) -> str:
    raise NotImplementedError("T2")


def is_grounded(text: str, result: CalcResult) -> bool:
    raise NotImplementedError("T2")


def explain(result: CalcResult, language: str) -> str:
    raise NotImplementedError("T2")
