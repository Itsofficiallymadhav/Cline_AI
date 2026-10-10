"""Rule file loader. Legal parameters are DATA (rules/delay_rules.json), never hard-coded."""
from __future__ import annotations
import json
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

    @property
    def verified(self) -> bool:
        return bool(self.last_verified)


def load_rules(path: Optional[Path] = None) -> Rules:
    return Rules(**json.loads(Path(path or config.RULES_PATH).read_text(encoding="utf-8")))
