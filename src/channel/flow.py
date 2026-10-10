"""Conversation state machine - THE single entry point for every channel.   OWNER: T3

    handle_message(user_id, text=None, audio_bytes=None) -> Reply        (src.engine.models.Reply)

No provider code in here: the simulator and the Twilio webhook both call this and send reply.render().
TODO(T3) implement so tests/test_flow.py passes. Design (SPEC.md section 5):
  States: NEW -> LANG -> ASK_JC -> CONFIRM_JC -> RESULT -> DRAFT_REVIEW <-> EDIT_DRAFT -> DONE
  - Replies are NUMBERED: return Reply(text, options=[Option(id,label)...], hint=t(lang,"reply_number")).
    Store the offered option ids in the session (data["opts"]) so "1","2",... map back to ids next turn.
    Also accept YES/NO/CANCEL words, language names, STATUS (works in any state), and restart words (hi, नमस्ते...).
  - Voice: if audio_bytes and no text -> text = src.ai.transcribe(...); if None -> Reply asking the user to type
    (key "retry_audio") WITHOUT changing state.
  - Language options come from src.messages.LANG_OPTIONS. All text via src.messages.t(lang, key, **kw).
  - Job card: src.ai.extract_fields(text, lang).job_card; confirm it back to the user ("jc:yes"/"jc:no").
  - Lookup: src.adapters.get_adapter().get_records(jc); none -> "not_found" and ask again. Else calculate() each record,
    explain() each (src.ai.explain), options: calc, draft (ONLY if some result is delayed/unpaid_overdue), cancel.
  - Calculation view: dates + formula from the result (never recomputed). Draft: src.ai.draft_complaint -> approve/edit/cancel.
  - Approval is EXPLICIT (option 1 or YES). Only then store.create_case(...). Never save/submit anything otherwise.
  - Edit: next message text replaces the draft; show it again with approve/edit/cancel.
  - Garbage input never crashes: re-ask with the same options.
"""
from __future__ import annotations
from typing import Optional

from src.engine.models import Reply


def handle_message(user_id: str, text: Optional[str] = None, audio_bytes: Optional[bytes] = None) -> Reply:
    raise NotImplementedError("T3: implement the conversation state machine")
