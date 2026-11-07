"""What the fixer remembers between runs, in one JSON file: since when it takes reviews, those it has taken (what it
found and did), a dry run's drafts waiting to be published, the dollars spent each day, its issue listing what needs
a person, and the commit its checkout was last prepared at. One run at a time (`answerer.state.State.locked`)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from answerer.state import State as AnswererState


class State:
    locked = staticmethod(AnswererState.locked)

    def __init__(self, path: Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.since: str = data.get("since", "")
        self.items: dict[str, dict] = data.get("items", {})
        self.drafts: dict[str, dict] = data.get("drafts", {})
        self.days: dict[str, float] = data.get("spend", {})
        self.flag_issue: int | None = data.get("flag_issue")
        self.prepared: dict = data.get("prepared", {})

    def taken(self, item_id: str, entry: dict) -> None:
        self.items[item_id] = {**self.items.get(item_id, {}), **entry}

    def spend(self, day: str, usd: float) -> None:
        self.days[day] = round(self.days.get(day, 0.0) + usd, 4)

    def spent(self, day: str) -> float:
        return self.days.get(day, 0.0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"since": self.since, "items": self.items, "drafts": self.drafts, "spend": self.days,
                                   "flag_issue": self.flag_issue, "prepared": self.prepared},
                                  indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
