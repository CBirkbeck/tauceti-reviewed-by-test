"""The model's tools: Tau Ceti's files in the fixer's checkout, to read, search and edit, the Mathlib it builds on, to
read and search, and Lean, to build modules and check short files, sealed off (`answerer.leancheck`: no network, an
empty environment, a fresh home directory). A path the model gives can only name a file below `TauCeti/` in the
checkout (to read or edit, `.lean` only) or below `Mathlib/` in Mathlib's (to read): it is matched, and its real path
checked to lie inside, before anything is opened. There is no shell. Each tool returns its text and whether it
failed."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from answerer.leancheck import Sandbox, bad_imports, refuse

PART = r"[A-Za-z0-9_'+-][A-Za-z0-9_'.+-]*"
PATH = re.compile(rf"^(TauCeti|Mathlib)(?:/{PART})*$")
MODULE = re.compile(r"^(TauCeti|Mathlib)(\.[A-Za-z_][A-Za-z0-9_']*)+$")
MAX_LINES, MAX_MATCHES, MAX_OUT = 400, 60, 8000
MAX_FILE = 200_000
MAX_BUILD = 8


def tool(name: str, description: str, properties: dict) -> dict:
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": properties, "required": list(properties),
                             "additionalProperties": False}}


TOOLS = [
    tool("read_file", "Read lines of a file, numbered: Tau Ceti's as your checkout has it now (TauCeti/…), or "
         "Mathlib's (Mathlib/…). At most 400 lines at a time.",
         {"path": {"type": "string"}, "start_line": {"type": "integer", "description": "1 for the start."},
          "end_line": {"type": "integer", "description": "0 for as far as allowed."}}),
    tool("list_dir", "The files and directories in a directory of Tau Ceti (TauCeti/…) or Mathlib (Mathlib/…).",
         {"path": {"type": "string"}}),
    tool("search", "Search Tau Ceti (your checkout, edits included) or Mathlib with git grep: an extended regular "
         "expression, or fixed text. Returns path:line:text for up to 60 matches.",
         {"pattern": {"type": "string"}, "scope": {"type": "string", "enum": ["TauCeti", "Mathlib"]},
          "within": {"type": "string", "description": "A directory or file below the scope, or empty for all of it."},
          "fixed": {"type": "boolean", "description": "Whether the pattern is fixed text rather than a regular expression."}}),
    tool("edit_file", "Replace text in a file of Tau Ceti (TauCeti/…, .lean): `old` must occur exactly once in it, "
         "and is replaced by `new` (empty to delete it). Returns the lines around the change.",
         {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}),
    tool("write_file", "Create a new Lean file of Tau Ceti (TauCeti/…, .lean) with this content, or rewrite one you "
         "created in this session. Existing files are changed with edit_file.",
         {"path": {"type": "string"}, "content": {"type": "string"}}),
    tool("importers", "The files of Tau Ceti that import a module directly (`import` or `public import`).",
         {"module": {"type": "string", "description": "Such as TauCeti.Probability.Martingale.MaximalInequality."}}),
    tool("lean_build", "Build modules of Tau Ceti as your checkout has them, with `lake build`, sealed off, and "
         "return Lean's errors and warnings. Up to 8 modules at a time; a build may take minutes.",
         {"modules": {"type": "array", "items": {"type": "string"}}}),
    tool("lean_check", "Check a short Lean file against your checkout's build: #check, #print, #print axioms, "
         "example, theorem. Imports apart, modules of Tau Ceti or Mathlib (build a module you edited first). Anything "
         "that runs code, strings and set_option are refused. Returns Lean's messages.",
         {"imports": {"type": "array", "items": {"type": "string"}}, "code": {"type": "string"}}),
    tool("show_diff", "Your changes so far: git's diff of the checkout, new files included.", {}),
]


#: What a build may write: the library's sources (which the model edits anyway) and the build's outputs. Nothing
#: else of the checkout: not `.git` (its hooks and config run with the run's git), not `.lake/packages` (Mathlib's
#: `cache` program runs when the checkout is next prepared), not the lakefile, the pins or `scripts/`.
WRITABLE = ("TauCeti", ".lake/build")


def build_command(sandbox: Sandbox, workdir: Path, modules: list[str], timeout: int) -> list[str]:
    """`lake build` of `modules` in `workdir`, sealed off: no network, an empty environment, a fresh home directory,
    the toolchain and the checkout read only but for `WRITABLE`. `.lake/packages` must be the checkout's own
    directory, not a link to another checkout's: the sandbox shows nothing outside the checkout."""
    argv = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv"]
    for d in ("/usr", "/bin", "/lib", "/lib64", "/etc/ld.so.cache"):
        if Path(d).exists():
            argv += ["--ro-bind", d, d]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", str(sandbox.home),
             "--ro-bind", str(sandbox.toolchain), str(sandbox.toolchain), "--ro-bind", str(workdir), str(workdir)]
    for d in WRITABLE:
        (workdir / d).mkdir(parents=True, exist_ok=True)
        argv += ["--bind", str(workdir / d), str(workdir / d)]
    return argv + ["--chdir", str(workdir), "--setenv", "HOME", "/tmp",
                   "--setenv", "PATH", f"{sandbox.toolchain / 'bin'}:/usr/bin:/bin",
                   "timeout", "-k", "5", str(timeout), str(sandbox.toolchain / "bin" / "lake"), "build", *modules]


class WorkTools:
    """`work` is the fixer's checkout of Tau Ceti, built from the Lake caches; `sandbox` runs Lean in it."""

    def __init__(self, work: Path, sandbox: Sandbox, root: str = "TauCeti", build_timeout: int = 2400,
                 runner: Callable[[list[str], int], tuple[int, str]] | None = None):
        self.work, self.root, self.sandbox = Path(work).resolve(), root, sandbox
        self.mathlib = (self.work / ".lake" / "packages" / "mathlib").resolve()
        self.build_timeout = build_timeout
        self.runner = runner or sandbox.runner
        self.created: set[str] = set()
        self.built: set[str] = set()

    # --- where a path may lead ----------------------------------------------------------------------

    def base(self, top: str) -> Path:
        return self.work if top == self.root else self.mathlib

    def resolve(self, path: str, write: bool = False) -> tuple[Path | None, str]:
        """The file or directory `path` names, or None and why. Writing: a `.lean` file below `TauCeti/` only."""
        path = (path or "").strip().strip("/")
        m = PATH.match(path)
        if not m or ".." in path.split("/") or m.group(1) not in (self.root, "Mathlib"):
            return None, f"{path!r} is not a path below {self.root}/ or Mathlib/"
        if write and (m.group(1) != self.root or not path.endswith(".lean")):
            return None, f"only Lean files below {self.root}/ can be changed"
        base = self.base(m.group(1))
        top, full = (base / m.group(1)).resolve(), (base / path).resolve()
        if full != top and top not in full.parents:  # a link out of the directory
            return None, f"{path!r} leads outside {m.group(1)}/"
        return full, ""

    # --- the tools ----------------------------------------------------------------------------------------

    def run(self, name: str, inp: dict) -> tuple[str, bool]:
        method = getattr(self, f"t_{name}", None)
        if method is None:
            return f"There is no tool {name!r}.", True
        return method(**inp)

    def t_read_file(self, path: str, start_line: int = 1, end_line: int = 0) -> tuple[str, bool]:
        full, why = self.resolve(path)
        if full is None or not full.is_file():
            return why or f"No such file: {path!r}.", True
        lines = full.read_text(encoding="utf-8", errors="replace").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        start = max(1, int(start_line or 1))
        end = min(len(lines), int(end_line) if end_line else len(lines), start + MAX_LINES - 1)
        note = "" if end - start + 1 < MAX_LINES or end == len(lines) else f" (at most {MAX_LINES} lines at a time)"
        body = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))
        return f"{path}, lines {start}–{end} of {len(lines)}{note}:\n{body}", False

    def t_list_dir(self, path: str) -> tuple[str, bool]:
        full, why = self.resolve(path)
        if full is None or not full.is_dir():
            return why or f"No such directory: {path!r}.", True
        rows = sorted((p.name + "/" if p.is_dir() else p.name) for p in full.iterdir() if not p.name.startswith("."))
        return "\n".join(rows[:300]) + (f"\n… {len(rows) - 300} more" if len(rows) > 300 else ""), False

    def git(self, repo: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)

    def t_search(self, pattern: str, scope: str, within: str = "", fixed: bool = False) -> tuple[str, bool]:
        where = f"{scope}/{within.strip('/')}" if within else scope
        full, why = self.resolve(where)
        if full is None:
            return f"Not searched: {why}.", True
        if not pattern or len(pattern) > 300 or "\n" in pattern:
            return "Not searched: give a pattern of one line, at most 300 characters.", True
        repo = self.base(scope)
        extra = ["--untracked"] if scope == self.root else []
        out = self.git(repo, "grep", "-n", "-I", *extra, "-F" if fixed else "-E", "-e", pattern, "--", where)
        if out.returncode == 1:
            return "No matches.", False
        if out.returncode != 0:
            return f"Not searched: {out.stderr.strip()[:300]}", True
        rows = out.stdout.splitlines()
        shown = [r if len(r) <= 240 else r[:240] + " …" for r in rows[:MAX_MATCHES]]
        more = f"\n… the first {len(shown)} matches of {len(rows)}; narrow the pattern or the directory." \
            if len(rows) > len(shown) else ""
        return "\n".join(shown) + more, False

    def t_edit_file(self, path: str, old: str, new: str) -> tuple[str, bool]:
        full, why = self.resolve(path, write=True)
        if full is None or not full.is_file():
            return why or f"No such file: {path!r}; create one with write_file.", True
        text = full.read_text(encoding="utf-8")
        n = text.count(old) if old else 0
        if n != 1:
            return (f"Not edited: `old` occurs {n} times in {path}; give text that occurs exactly once, with enough "
                    f"around it."), True
        before = text.split(old, 1)[0]
        full.write_text(text.replace(old, new, 1), encoding="utf-8")
        self.built.clear()
        first = before.count("\n") + 1
        lines = full.read_text(encoding="utf-8").split("\n")
        last = first + new.count("\n")
        lo, hi = max(1, first - 3), min(len(lines), last + 3)
        return f"Edited {path}; lines {lo}–{hi} now read:\n" + "\n".join(f"{i}: {lines[i - 1]}" for i in range(lo, hi + 1)), False

    def t_write_file(self, path: str, content: str) -> tuple[str, bool]:
        full, why = self.resolve(path, write=True)
        if full is None:
            return why, True
        if full.exists() and path not in self.created:
            return f"Not written: {path} exists; change it with edit_file.", True
        if len(content) > MAX_FILE:
            return f"Not written: more than {MAX_FILE} characters.", True
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        self.created.add(path)
        self.built.clear()
        return f"Wrote {path}, {content.count(chr(10)) + 1} lines.", False

    def t_importers(self, module: str) -> tuple[str, bool]:
        if not MODULE.match(module or "") or not module.startswith(self.root + "."):
            return f"{module!r} is not a module of {self.root}.", True
        # POSIX classes: git grep's extended expressions have no \s
        sp = "[[:space:]]"
        pat = (rf"^{sp}*((public|private|meta){sp}+)*import{sp}+(all{sp}+)?([^[:space:]]+{sp}+)*"
               rf"{re.escape(module)}({sp}|$)")
        out = self.git(self.work, "grep", "-l", "--untracked", "-E", "-e", pat, "--", self.root)
        rows = out.stdout.split()
        return ("\n".join(rows) if rows else "No file imports it directly."), out.returncode not in (0, 1)

    def module_file(self, module: str) -> Path | None:
        if not MODULE.match(module or ""):
            return None
        top = module.split(".")[0]
        full, _ = self.resolve(module.replace(".", "/") + ".lean")
        return full if full is not None and full.is_file() and top in (self.root, "Mathlib") else None

    def t_lean_build(self, modules: list[str]) -> tuple[str, bool]:
        modules = [m.strip() for m in modules or [] if m.strip()]
        if not modules or len(modules) > MAX_BUILD:
            return f"Give from 1 to {MAX_BUILD} modules.", True
        for m in modules:
            if not m.startswith(self.root + ".") or self.module_file(m) is None:
                return f"Not built: {m!r} is not a module of {self.root} in your checkout.", True
        return self.build(modules)

    def build(self, modules: list[str]) -> tuple[str, bool]:
        """Builds `modules`, sealed off; also the run's own check before anything is published."""
        try:
            code, out = self.runner(build_command(self.sandbox, self.work, modules, self.build_timeout),
                                    self.build_timeout)
        except subprocess.TimeoutExpired:
            return f"The build did not finish within {self.build_timeout // 60} minutes.", True
        if code == 0:
            self.built.update(modules)
        return (("Built: " + ", ".join(modules) + ".\n") if code == 0 else f"The build failed ({code}).\n") + \
            trim(out), code != 0

    def t_lean_check(self, imports: list[str], code: str) -> tuple[str, bool]:
        imports = [str(m) for m in imports or []]
        exists = lambda m: self.module_file(m) is not None  # noqa: E731
        why = bad_imports(imports, exists) or refuse(code)
        if why:
            return f"Not run: refused, because {why}.", True
        out = self.sandbox.check(imports, code, exists=exists)
        return out, out.startswith("Not run")

    def t_show_diff(self) -> tuple[str, bool]:
        return trim(diff(self.work, self.root), keep="head"), False


def diff(work: Path, root: str = "TauCeti") -> str:
    """The checkout's changes: git's diff of tracked files, then each new file whole."""
    run = lambda *a: subprocess.run(["git", "-C", str(work), *a], capture_output=True, text=True, timeout=120).stdout  # noqa: E731
    out = run("diff", "--", root)
    for f in run("ls-files", "--others", "--exclude-standard", "--", root).split():
        out += f"\n--- new file {f}\n" + (Path(work) / f).read_text(encoding="utf-8", errors="replace")
    return out or "No changes."


def trim(text: str, keep: str = "errors") -> str:
    """At most MAX_OUT characters: the errors and the end of a build's output first, or the start of a diff."""
    text = (text or "").strip()
    if len(text) <= MAX_OUT:
        return text
    if keep == "head":
        return text[:MAX_OUT] + "\n… (cut)"
    errors = [l for l in text.splitlines() if re.search(r"\berror\b", l)]
    head = "\n".join(errors)[: MAX_OUT // 2]
    return (head + "\n…\n" if head else "") + text[-(MAX_OUT - len(head) - 4):]
