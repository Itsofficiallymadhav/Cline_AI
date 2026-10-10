"""SQLite: per-user conversation state + saved (SIMULATED) cases.   OWNER: T3

Standard-library sqlite3 only (no new dependency). config.DB_PATH is read at CALL time (tests override it) and a
connection is opened/closed per call, so state survives app restarts and every test gets a fresh database.

Contract used by flow.py / tests:
  get_session(user_id) -> {"state": "NEW", "lang": None, "data": {}} for unknown users, else the stored values
  save_session(user_id, state, lang, data)           data is a JSON-serialisable dict
  create_case(user_id, job_card_no, complaint_text, compensation) -> Case   ids KH-101, KH-102, ... "READY_FOR_HANDOFF"
  list_cases(user_id) -> list[Case]   oldest first
Extra helpers: get_case, update_case_status, get_case_history (status history with timestamps),
claim_message / save_message_reply (idempotent webhook deliveries).

Safety:
  - Cases are SIMULATED hand-off records (column is_simulated = 1). Nothing is filed with any government system.
  - This module never decides consent: flow.py calls create_case ONLY after the worker's explicit approval.
  - create_case is idempotent: the same confirmed submission (same user, job card, text, amount) returns the existing
    case instead of creating a duplicate.
  - Data minimisation: the raw user id (a WhatsApp phone number) is NOT stored; rows are keyed by its SHA-256 hash.
    This is pseudonymisation, not anonymisation (phone numbers are guessable). No names/villages are stored outside
    the complaint text the worker approved.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Optional

from src import config
from src.engine.models import Case

STATUS_READY = "READY_FOR_HANDOFF"
# Allowed case status transitions (simulated lifecycle). Anything else raises InvalidTransitionError.
TRANSITIONS: dict[str, set[str]] = {
    STATUS_READY: {"HANDED_OVER", "WITHDRAWN"},
    "HANDED_OVER": {"CLOSED"},
    "WITHDRAWN": set(),
    "CLOSED": set(),
}
CASE_ID_OFFSET = 100                     # first case is KH-101
MAX_COMPLAINT_CHARS = 5000
PROCESSED_TTL = timedelta(days=1)        # webhook de-duplication window

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    user_key   TEXT PRIMARY KEY,
    state      TEXT NOT NULL,
    lang       TEXT,
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id        TEXT UNIQUE,
    user_key       TEXT NOT NULL,
    job_card_no    TEXT NOT NULL,
    status         TEXT NOT NULL,
    complaint_text TEXT NOT NULL,
    compensation   REAL NOT NULL,
    is_simulated   INTEGER NOT NULL DEFAULT 1,
    submission_key TEXT NOT NULL UNIQUE,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_user ON cases(user_key);
CREATE TABLE IF NOT EXISTS case_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    status  TEXT NOT NULL,
    note    TEXT NOT NULL DEFAULT '',
    at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processed_messages (
    message_sid TEXT PRIMARY KEY,
    reply       TEXT,
    at          TEXT NOT NULL
);
"""


class StoreError(Exception):
    """Storage failed (database unavailable, corrupt row...). Message never contains user data."""


class CaseNotFoundError(StoreError):
    pass


class InvalidTransitionError(StoreError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _user_key(user_id: str) -> str:
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn
    except sqlite3.Error as e:
        raise StoreError(f"database unavailable: {type(e).__name__}") from e


def _run(fn):
    """Run fn(conn) in one transaction (commit on success, rollback on error); sqlite errors -> StoreError."""
    try:
        with closing(_connect()) as conn:
            with conn:
                return fn(conn)
    except StoreError:
        raise
    except sqlite3.Error as e:
        raise StoreError(f"database error: {type(e).__name__}") from e


# ---------------------------------------------------------------- sessions (conversation state)
def get_session(user_id: str) -> dict:
    row = _run(lambda c: c.execute("SELECT state, lang, data FROM sessions WHERE user_key = ?",
                                   (_user_key(user_id),)).fetchone())
    if row is None:
        return {"state": "NEW", "lang": None, "data": {}}
    try:
        data = json.loads(row["data"])
    except (TypeError, ValueError):
        data = {}                                   # corrupt row -> safe empty data, never crash the chat
    return {"state": row["state"], "lang": row["lang"], "data": data if isinstance(data, dict) else {}}


def save_session(user_id: str, state: str, lang: Optional[str], data: dict) -> None:
    payload = json.dumps(data or {}, ensure_ascii=False)
    _run(lambda c: c.execute(
        "INSERT INTO sessions (user_key, state, lang, data, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_key) DO UPDATE SET state = excluded.state, lang = excluded.lang, "
        "data = excluded.data, updated_at = excluded.updated_at",
        (_user_key(user_id), state, lang, payload, _now())))


def reset_session(user_id: str) -> None:
    _run(lambda c: c.execute("DELETE FROM sessions WHERE user_key = ?", (_user_key(user_id),)))


# ---------------------------------------------------------------- cases (simulated, created only after approval)
def _submission_key(user_key: str, job_card_no: str, complaint_text: str, compensation: float) -> str:
    raw = json.dumps([user_key, job_card_no, complaint_text, round(float(compensation), 2)], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _row_to_case(row: sqlite3.Row, user_id: str) -> Case:
    return Case(case_id=row["case_id"], user_id=user_id, job_card_no=row["job_card_no"], status=row["status"],
                complaint_text=row["complaint_text"], compensation=row["compensation"], created_at=row["created_at"])


def create_case(user_id: str, job_card_no: str, complaint_text: str, compensation: float) -> Case:
    """Persist an APPROVED complaint as a simulated case. Returns the existing case for a duplicate submission."""
    job_card_no = (job_card_no or "").strip()
    complaint_text = (complaint_text or "").strip()[:MAX_COMPLAINT_CHARS]
    if not job_card_no or not complaint_text:
        raise ValueError("job card number and complaint text are required")
    if compensation is None or float(compensation) < 0:
        raise ValueError("compensation must be a non-negative engine amount")
    ukey = _user_key(user_id)
    skey = _submission_key(ukey, job_card_no, complaint_text, compensation)

    def tx(c: sqlite3.Connection) -> sqlite3.Row:
        existing = c.execute("SELECT * FROM cases WHERE submission_key = ?", (skey,)).fetchone()
        if existing is not None:
            return existing                                  # duplicate confirmation -> same case
        now = _now()
        cur = c.execute(
            "INSERT INTO cases (user_key, job_card_no, status, complaint_text, compensation, is_simulated, "
            "submission_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (ukey, job_card_no, STATUS_READY, complaint_text, float(compensation), skey, now, now))
        case_id = f"KH-{CASE_ID_OFFSET + cur.lastrowid}"    # AUTOINCREMENT ids are never reused -> unique
        c.execute("UPDATE cases SET case_id = ? WHERE id = ?", (case_id, cur.lastrowid))
        c.execute("INSERT INTO case_events (case_id, status, note, at) VALUES (?, ?, ?, ?)",
                  (case_id, STATUS_READY, "Simulated case saved after explicit approval. Not filed.", now))
        return c.execute("SELECT * FROM cases WHERE id = ?", (cur.lastrowid,)).fetchone()

    return _row_to_case(_run(tx), user_id)


def list_cases(user_id: str) -> list[Case]:
    rows = _run(lambda c: c.execute("SELECT * FROM cases WHERE user_key = ? ORDER BY id",
                                    (_user_key(user_id),)).fetchall())
    return [_row_to_case(r, user_id) for r in rows]



def get_case(user_id: str, case_id: str) -> Case:
    """Only the owner can read a case. Raises CaseNotFoundError otherwise."""
    row = _run(lambda c: c.execute("SELECT * FROM cases WHERE case_id = ? AND user_key = ?",
                                   (case_id, _user_key(user_id))).fetchone())
    if row is None:
        raise CaseNotFoundError(f"case {case_id} not found")
    return _row_to_case(row, user_id)


def update_case_status(user_id: str, case_id: str, new_status: str, note: str = "") -> Case:
    """Move a case along TRANSITIONS (simulated lifecycle). Raises CaseNotFoundError / InvalidTransitionError."""
    def tx(c: sqlite3.Connection) -> sqlite3.Row:
        row = c.execute("SELECT * FROM cases WHERE case_id = ? AND user_key = ?",
                        (case_id, _user_key(user_id))).fetchone()
        if row is None:
            raise CaseNotFoundError(f"case {case_id} not found")
        if new_status not in TRANSITIONS.get(row["status"], set()):
            raise InvalidTransitionError(f"cannot move {case_id} from {row['status']} to {new_status}")
        now = _now()
        c.execute("UPDATE cases SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, row["id"]))
        c.execute("INSERT INTO case_events (case_id, status, note, at) VALUES (?, ?, ?, ?)",
                  (case_id, new_status, (note or "")[:500], now))
        return c.execute("SELECT * FROM cases WHERE id = ?", (row["id"],)).fetchone()

    return _row_to_case(_run(tx), user_id)


def get_case_history(user_id: str, case_id: str) -> list[dict]:
    """Status history (oldest first) with UTC timestamps. Raises CaseNotFoundError for unknown / other users' cases."""
    get_case(user_id, case_id)
    rows = _run(lambda c: c.execute("SELECT status, note, at FROM case_events WHERE case_id = ? ORDER BY id",
                                    (case_id,)).fetchall())
    return [{"status": r["status"], "note": r["note"], "at": r["at"]} for r in rows]


# ---------------------------------------------------------------- webhook idempotency (duplicate deliveries)
def claim_message(message_sid: str) -> tuple[bool, Optional[str]]:
    """Record a provider message id. Returns (True, None) the first time, (False, earlier reply or None) on redelivery."""
    def tx(c: sqlite3.Connection):
        cutoff = (datetime.now(timezone.utc) - PROCESSED_TTL).isoformat(timespec="seconds")
        c.execute("DELETE FROM processed_messages WHERE at < ?", (cutoff,))
        row = c.execute("SELECT reply FROM processed_messages WHERE message_sid = ?", (message_sid,)).fetchone()
        if row is not None:
            return False, row["reply"]
        c.execute("INSERT INTO processed_messages (message_sid, reply, at) VALUES (?, NULL, ?)",
                  (message_sid, _now()))
        return True, None

    return _run(tx)


def save_message_reply(message_sid: str, reply: str) -> None:
    _run(lambda c: c.execute("UPDATE processed_messages SET reply = ? WHERE message_sid = ?", (reply, message_sid)))


def release_message(message_sid: str) -> None:
    """Forget a claimed id after a processing failure, so the provider's retry is handled normally."""
    _run(lambda c: c.execute("DELETE FROM processed_messages WHERE message_sid = ?", (message_sid,)))

