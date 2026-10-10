"""SHARED CONTRACT - every module imports names from here. Change only by team agreement (update SPEC.md too)."""
from __future__ import annotations
from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Status(str, Enum):
    ON_TIME = "on_time"                  # paid by the due date (or not yet due)
    DELAYED = "delayed"                  # paid late -> compensation computed
    UNPAID_OVERDUE = "unpaid_overdue"    # not paid and past due -> delay counted up to today
    NEEDS_REVIEW = "needs_review"        # uncertain/conflicting data -> NO amount
    NOT_FOUND = "not_found"              # no record for this job card


class Flag(str, Enum):
    MISSING_CLOSURE_DATE = "missing_closure_date"
    MISSING_WAGE_DATA = "missing_wage_data"
    DAYS_MISMATCH = "days_mismatch"              # days worked != days paid
    WAGE_RATE_MISMATCH = "wage_rate_mismatch"    # amount paid != days_paid x daily rate
    FAILED_TRANSACTION = "failed_transaction"    # payment_status == "failed"


class WorkerRecord(BaseModel):
    """One wage period for one worker, as returned by a record adapter."""
    job_card_no: str
    worker_name: str
    village: str = ""
    muster_roll_closed_on: Optional[date] = None
    days_worked: Optional[int] = None
    daily_wage_rate: Optional[float] = None
    days_paid: Optional[int] = None
    payment_amount: Optional[float] = None
    payment_date: Optional[date] = None
    payment_status: str = "success"      # "success" | "failed" | "pending"


class Evidence(BaseModel):
    label: str
    value: str
    source: str          # "muster_roll" | "payment_record" | "rule"


class CalcResult(BaseModel):
    """Output of the engine. The ONLY source of numbers the bot may state."""
    status: Status
    job_card_no: str
    worker_name: str = ""
    village: str = ""
    wage_amount: Optional[float] = None            # per muster roll (days_worked x daily rate)
    payment_amount: Optional[float] = None
    closure_date: Optional[date] = None
    due_date: Optional[date] = None
    payment_date: Optional[date] = None
    as_of_date: Optional[date] = None
    delay_days: int = 0
    compensation: Optional[float] = None           # None unless status is delayed / unpaid_overdue
    rate_per_day: float = 0.0
    due_days: int = 0
    formula: str = ""
    flags: list[Flag] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    rule_source: str = ""
    rule_verified: bool = False
    disclaimer: str = "Illustrative estimate, not a legal determination."


class ExtractedFields(BaseModel):
    job_card: Optional[str] = None
    work_period: Optional[str] = None
    issue_type: str = "unknown"          # "delay" | "unpaid" | "other" | "unknown"


class Option(BaseModel):
    id: str              # e.g. "lang:hi", "act:draft"
    label: str


class Reply(BaseModel):
    """What handle_message returns. Channels send render(); the simulator may also draw options as buttons."""
    text: str
    options: list[Option] = Field(default_factory=list)
    hint: str = ""

    def render(self) -> str:
        if not self.options:
            return self.text
        lines = [f"{i}. {o.label}" for i, o in enumerate(self.options, 1)]
        tail = f"\n{self.hint}" if self.hint else ""
        return f"{self.text}\n\n" + "\n".join(lines) + tail


class Case(BaseModel):
    case_id: str
    user_id: str
    job_card_no: str
    status: str                  # "READY_FOR_HANDOFF"
    complaint_text: str
    compensation: float
    created_at: str
