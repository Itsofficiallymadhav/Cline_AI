"""Sample-data record adapter.   OWNER: T1

TODO(T1): implement SampleAdapter.get_records(job_card) -> list[WorkerRecord]
  - load data/sample_records.json (config.SAMPLE_DATA_PATH) into WorkerRecord objects once, in __init__
  - return every record whose job_card_no equals the (stripped) job card; return [] if unknown (never raise)
Keep the read-only interface in base.py so a live adapter can replace this later.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from src.engine.models import WorkerRecord


class SampleAdapter:
    def __init__(self, path: Optional[Path] = None):
        raise NotImplementedError("T1: load sample_records.json")

    def get_records(self, job_card: str) -> list[WorkerRecord]:
        raise NotImplementedError("T1: return matching records or []")
