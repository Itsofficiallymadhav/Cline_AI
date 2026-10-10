"""Rule file loader. Legal parameters are DATA (rules/delay_rules.json), never hard-coded."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from src import config


class Rules(BaseModel):
    due_days: int
    rate_per_day: float
    source: str = ""
    last_verified: Optional[str] = None
    note: str = ""
    # Optional rule-identity metadata (all additive; absent => no restriction / defaults).
    scheme: str = ""                          # e.g. "DEMO_ILLUSTRATIVE"; never auto-selected by the engine
    version: str = ""
    effective_from: Optional[date] = None     # muster-roll closure dates before this are NOT covered
    effective_to: Optional[date] = None       # muster-roll closure dates after this are NOT covered
    delay_start_offset_days: int = 0          # day-counting convention: extra days after due date before delay counts
    synthetic_demo: bool = False              # True ONLY for clearly labelled synthetic demo rules

    @property
    def verified(self) -> bool:
        return bool(self.last_verified)


def load_rules(path: Optional[Path] = None) -> Rules:
    return Rules(**json.loads(Path(path or config.RULES_PATH).read_text(encoding="utf-8")))
