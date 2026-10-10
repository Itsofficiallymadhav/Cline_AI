from __future__ import annotations
from typing import Protocol
from src.engine.models import WorkerRecord


class RecordAdapter(Protocol):
    def get_records(self, job_card: str) -> list[WorkerRecord]:
        """Read-only. Return [] if the job card is unknown. Never raise for 'not found'."""
        ...
