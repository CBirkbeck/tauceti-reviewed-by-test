"""What the answerer says on the review repository, and how.

Everything it posts starts with its agent mark, `<!-- agent: tool=…; model=… -->`, so that intake
records it as an AI agent's (through the server's GitHub account), naming the model that answered.

- `close`: a status on the item, with the reply as its note. On the item's own issue it is a comment
  whose first line (after the mark) is the command, `/intended`, `/invalid`, `/answered` or
  `/fixed <commit>`, and whose rest intake keeps as the note. An item from a pull request's file (an
  AI agent's batch) has no issue: the store's status form is used instead (`evidence-store status`).
- `reply`: a comment on the item's own issue, kept as a reply; an item without one gets none.
- `flags`: the one issue listing what needs a person, created once and rewritten each run.

A dry run posts nothing and keeps what it would have posted (`would`).
"""
from __future__ import annotations

import re
import subprocess
from typing import Any, Callable

FLAG_TITLE = "Answerer: needs a person"


def mark(by: dict) -> str:
    return f"<!-- agent: tool={by['tool']}; model={by['model']} -->"


def gh(argv: list[str], stdin: str | None = None) -> str:
    return subprocess.run(argv, input=stdin, capture_output=True, text=True, check=True, timeout=120).stdout


class Poster:
    def __init__(self, repo: str, run: Callable[[list[str], str | None], str] = gh, dry: bool = False):
        self.repo, self.run, self.dry = repo, run, dry
        self.would: list[tuple[list[str], str | None]] = []

    def call(self, argv: list[str], stdin: str | None = None) -> str:
        if self.dry:
            self.would.append((argv, stdin))
            return ""
        return self.run(argv, stdin)

    def comment(self, issue: int, body: str) -> str:
        return self.call(["gh", "issue", "comment", str(issue), "-R", self.repo, "--body-file", "-"], body).strip()

    def close(self, item: Any, command: str, note: str, by: dict, commit: str | None = None) -> str:
        if item.issue:
            head = f"/{command}" + (f" {commit}" if commit else "")
            return self.comment(item.issue, f"{mark(by)}\n{head}\n\n{note}")
        argv = ["evidence-store", "status", "--repo", self.repo, "--record", item.id, "--action", command,
                "--note", note, "--agent", f"{by['tool']}, {by['model']}"]
        if commit:
            argv += ["--commit", commit]
        return self.call(argv).strip()

    def reply(self, item: Any, text: str, by: dict) -> str | None:
        if not item.issue:
            return None
        return self.comment(item.issue, f"{mark(by)}\n{text}")

    def flags(self, entries: list[str], number: int | None) -> int | None:
        body = ("Items the review answerer could not settle, or where it found the Lean itself wrong: each needs "
                "a person. It rewrites this list every hour.\n\n" + ("\n".join(entries) if entries else "Nothing now."))
        if number:
            self.call(["gh", "issue", "edit", str(number), "-R", self.repo, "--body-file", "-"], body)
            return number
        if not entries:
            return None
        out = self.call(["gh", "issue", "create", "-R", self.repo, "--title", FLAG_TITLE, "--body-file", "-"], body)
        m = re.search(r"/issues/(\d+)", out)
        return int(m.group(1)) if m else None
