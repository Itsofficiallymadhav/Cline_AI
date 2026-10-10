"""Complaint draft.   OWNER: T2

TODO(T2): draft_complaint(result, language) -> str  from the "complaint" template in src.messages
(name, job card, village, wage, due date, payment date or 'not paid yet', delay days, compensation).
Optional: LLM polish, but it must pass the same grounding check as explain().
"""
from __future__ import annotations
from src.engine.models import CalcResult


def draft_complaint(result: CalcResult, language: str) -> str:
    raise NotImplementedError("T2")
