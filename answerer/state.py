"""What the answerer remembers between runs, in one JSON file: the items it has handled (its verdict,
what it did, a pull request it is waiting on), the dollars spent each day, the issue listing what
needs a person, and the library commit its checkout was last prepared at. One run at a time: a run
holds a lock on the file while it works."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.items: dict[str, dict] = data.get("items", {})
        self.days: dict[str, float] = data.get("spend", {})
        self.flag_issue: int | None = data.get("flag_issue")
        self.prepared: dict = data.get("prepared", {})

    def handled(self, item_id: str, entry: dict) -> None:
        self.items[item_id] = {**self.items.get(item_id, {}), **entry}

    def spend(self, day: str, usd: float) -> None:
        self.days[day] = round(self.days.get(day, 0.0) + usd, 4)

    def spent(self, day: str) -> float:
        return self.days.get(day, 0.0)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": self.items, "spend": self.days, "flag_issue": self.flag_issue,
                                   "prepared": self.prepared}, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    @contextlib.contextmanager
    def locked(path: Path):
        """Held for a whole run; a second run started meanwhile stops at once (BlockingIOError)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_suffix(".lock"), "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
