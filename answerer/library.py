"""The library as the model reads it: Tau Ceti at the commit the site shows, and the Mathlib that
commit pins, both read through git (`git show`, `git grep`) rather than the file system, so that a path
the model gives can only name one of their files: `TauCeti/…` or `Mathlib/…`, ending in `.lean`."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

PART = r"[A-Za-z0-9_'+-][A-Za-z0-9_'.+-]*"
DIR = re.compile(rf"^(?:{PART}/)*(?:{PART})?$")
NAME = r"[A-Za-z_][A-Za-z0-9_']*"
MAX_LINES = 400


class Library:
    """`root` is the library's top directory, `TauCeti`; Mathlib is read from the package checkout."""

    def __init__(self, work: Path, commit: str, root: str = "TauCeti", max_matches: int = 60):
        self.work, self.commit, self.root, self.max_matches = Path(work), commit, root, max_matches
        self.mathlib = self.work / ".lake" / "packages" / "mathlib"
        roots = f"(?:{re.escape(root)}|Mathlib)"
        self.file = re.compile(rf"^{roots}/(?:{PART}/)*{PART}\.lean$")
        self.module = re.compile(rf"^{roots}(\.{NAME})+$")

    def place(self, top: str) -> tuple[Path, str]:
        """The repository and revision a top directory is read from."""
        return (self.work, self.commit) if top == self.root else (self.mathlib, "HEAD")

    def git(self, repo: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)

    def text(self, path: str) -> str | None:
        """A file's text at the commit, or None."""
        if not self.file.match(path or "") or ".." in path.split("/"):
            return None
        repo, rev = self.place(path.split("/", 1)[0])
        out = self.git(repo, "show", f"{rev}:{path}")
        return out.stdout if out.returncode == 0 else None

    def read(self, path: str, start: int = 1, end: int | None = None) -> str:
        text = self.text(path)
        if text is None:
            return f"No such file: {path!r}. Paths are {self.root}/… or Mathlib/…, ending in .lean."
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        start = max(1, int(start or 1))
        end = min(len(lines), int(end) if end else len(lines), start + MAX_LINES - 1)
        note = "" if end - start + 1 < MAX_LINES or end == len(lines) else f" (at most {MAX_LINES} lines at a time)"
        body = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))
        return f"{path}, lines {start}–{end} of {len(lines)}{note}:\n{body}"

    def search(self, pattern: str, scope: str = "TauCeti", within: str = "", fixed: bool = False) -> str:
        """`git grep` for `pattern` (extended regular expression, or fixed text) under `scope/within`."""
        if scope not in (self.root, "Mathlib") or not DIR.match(within or "") or ".." in (within or "").split("/"):
            return f"Not searched: the scope is {self.root} or Mathlib, and `within` a directory or file below it."
        if not pattern or len(pattern) > 300 or "\n" in pattern:
            return "Not searched: give a pattern of one line, at most 300 characters."
        repo, rev = self.place(scope)
        out = self.git(repo, "grep", "-n", "-I", "-F" if fixed else "-E", "-e", pattern, rev, "--",
                       f"{scope}/{within}" if within else scope)
        if out.returncode == 1:
            return "No matches."
        if out.returncode != 0:
            return f"Not searched: {out.stderr.strip()[:300]}"
        rows = [line[len(rev) + 1:] if line.startswith(rev + ":") else line for line in out.stdout.splitlines()]
        shown = [r if len(r) <= 240 else r[:240] + " …" for r in rows[:self.max_matches]]
        more = f"\n… the first {len(shown)} matches of {len(rows)}; narrow the pattern or the directory." \
            if len(rows) > len(shown) else ""
        return "\n".join(shown) + more

    def module_exists(self, module: str) -> bool:
        return bool(self.module.match(module or "")) and self.text(module.replace(".", "/") + ".lean") is not None
