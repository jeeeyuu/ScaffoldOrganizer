from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Task:
    id: str
    priority: str
    category: str
    task: str
    next_action: str
    tool: Optional[str]
    estimate_min: Optional[int | str]
    status: str
    notes: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)
