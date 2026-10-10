"""SQLite: per-user conversation state + saved cases.   OWNER: T3

Read config.DB_PATH at CALL time (tests override it). Open/close a connection per call.
TODO(T3):
  get_session(user_id) -> {"state": "NEW", "lang": None, "data": {}} for unknown users, else the stored values
  save_session(user_id, state, lang, data)           data is a JSON-serialisable dict
  create_case(user_id, job_card_no, complaint_text, compensation) -> Case   ids KH-101, KH-102, ... status "READY_FOR_HANDOFF"
  list_cases(user_id) -> list[Case]   oldest first
"""
from __future__ import annotations
from typing import Optional

from src.engine.models import Case


def get_session(user_id: str) -> dict:
    raise NotImplementedError("T3")


def save_session(user_id: str, state: str, lang: Optional[str], data: dict) -> None:
    raise NotImplementedError("T3")


def create_case(user_id: str, job_card_no: str, complaint_text: str, compensation: float) -> Case:
    raise NotImplementedError("T3")


def list_cases(user_id: str) -> list[Case]:
    raise NotImplementedError("T3")
