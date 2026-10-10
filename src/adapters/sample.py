"""Sample-data record adapter.   OWNER: T1

Loads the synthetic records from data/sample_records.json into WorkerRecord
objects once, in __init__, and serves read-only lookups by job card number.
A live read-only adapter can replace this later via src.adapters.get_adapter().
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src import config
from src.engine.models import WorkerRecord


class SampleAdapter:
    """Read-only adapter over the bundled sample data (all names fictional)."""

    def __init__(self, path: Optional[Path] = None):
        self._path = Path(path) if path is not None else Path(config.SAMPLE_DATA_PATH)
        with open(self._path, encoding="utf-8") as f:
            rows = json.load(f)
        self._records: list[WorkerRecord] = [WorkerRecord(**row) for row in rows]

    def get_records(self, job_card: str) -> list[WorkerRecord]:
        """Return every record whose job_card_no matches the stripped job card.

        Returns [] for unknown or blank job cards. Never raises for 'not found'.
        """
        jc = str(job_card or "").strip()
        if not jc:
            return []
        return [rec for rec in self._records if rec.job_card_no == jc]
