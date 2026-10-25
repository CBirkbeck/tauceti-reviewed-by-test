"""A short Lean file, checked against the library's build, sealed off.

The model may ask Lean whether something holds: a declaration's actual signature (`#check`), a small
`example`, `#print axioms`. Its file is written from a report anyone can file, and Lean runs code
while it elaborates (`#eval`, `run_cmd`, elaborators, macros, initializers, `implemented_by`, …), so:

- `refuse` turns away any file with a construct that could run code, or that names `IO`, `System`
  or `Lean`, or has a string, an attribute, a quotation or an antiquotation; imports are given apart,
  modules of the library or of Mathlib that exist (`bad_imports`);
- whatever gets through runs under `bubblewrap` (`Sandbox`): no network, a fresh empty home
  directory, an empty environment, the toolchain and the builds read-only, a time limit and Lean's
  own memory limit. The process that holds the API key and the GitHub token is outside it.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

#: Commands that define syntax or run code, at the start of a line (after modifiers).
COMMANDS = ("elab", "elab_rules", "macro", "macro_rules", "syntax", "declare_syntax_cat", "notation", "infix",
            "infixl", "infixr", "prefix", "postfix", "initialize", "builtin_initialize", "export", "attribute",
            "import", "add_decl_doc")
MODIFIERS = r"(?:(?:local|scoped|private|protected|noncomputable|partial|nonrec)\s+)*"
#: Anywhere: what runs code, reaches the system, or builds syntax.
ANYWHERE = (r"#eval\b", r"#exit\b", r"#guard\b", r"#run\b", r"\brun_cmd\b", r"\brun_elab\b", r"\brun_meta\b",
            r"\brun_tac\b", r"\bby_elab\b", r"\bset_option\b", r"\bunsafe\b", r"\bimplemented_by\b", r"\bextern\b",
            r"\bnative_decide\b", r"\bnative\b", r"\bofReduceBool\b", r"\binclude_str\b", r"\bevalExpr\b",
            r"\bdbg_trace\b", r"\bdbgTrace\b", r"\bunsafeCast\b", r"\bIO\b", r"\bSystem\b", r"\bLean\b",
            r"\b(?:Core|Meta|TermElab|CommandElab|Tactic|Elab|Macro)M\b", r"\b(?:EIO|BaseIO|EStateM)\b",
            r"@\[", "«", r"\$", r"`\(", r"`\[", r"``", '"')
FORBIDDEN = re.compile("|".join([rf"^\s*{MODIFIERS}(?:{'|'.join(COMMANDS)})\b", *ANYWHERE]), re.M)
COMMENT = re.compile(r"--[^\n]*|/-.*?-/", re.S)
MODULE = re.compile(r"^(TauCeti|Mathlib)(\.[A-Za-z_][A-Za-z0-9_']*)+$")
MAX_CODE, MAX_IMPORTS = 6000, 6


def refuse(code: str) -> str | None:
    """Why `code` may not run, or None."""
    if len(code) > MAX_CODE:
        return f"longer than {MAX_CODE} characters"
    m = FORBIDDEN.search(COMMENT.sub(" ", code))
    return f"it has {m.group(0).strip()!r}, which can run code or reach the system" if m else None


def bad_imports(imports: list[str], exists: Callable[[str], bool]) -> str | None:
    """Why these imports may not be used, or None: at most a few, modules of the library or Mathlib."""
    if len(imports) > MAX_IMPORTS:
        return f"at most {MAX_IMPORTS} imports"
    for m in imports:
        if not MODULE.match(m):
            return f"{m!r} is not a module of TauCeti or Mathlib"
        if not exists(m):
            return f"no module {m}"
    return None


def run(argv: list[str], timeout: int) -> tuple[int, str]:
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout + 30)
    return p.returncode, (p.stdout + p.stderr)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@dataclass
class Sandbox:
    """Where a check runs: `toolchain` (its `bin/lean`), the builds it reads (`roots`, whose oleans
    `lean_path` lists), the home directory it hides, and the directory its file is written to."""

    toolchain: Path
    roots: list[Path]
    lean_path: str
    home: Path
    scratch: Path
    timeout: int = 180
    memory_mb: int = 6144
    runner: Callable[[list[str], int], tuple[int, str]] = field(default=run, repr=False)
    write: Callable[[Path, str], None] = field(default=write, repr=False)

    def command(self, file: Path) -> list[str]:
        argv = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv"]
        for d in ("/usr", "/bin", "/lib", "/lib64", "/etc/ld.so.cache"):
            if Path(d).exists():
                argv += ["--ro-bind", d, d]
        argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", str(self.home)]
        for d in [self.toolchain, *self.roots]:
            argv += ["--ro-bind", str(d), str(d)]
        argv += ["--ro-bind", str(file), "/tmp/Check.lean", "--chdir", "/tmp",
                 "--setenv", "LEAN_PATH", self.lean_path, "--setenv", "HOME", "/tmp", "--setenv", "PATH", "/usr/bin:/bin",
                 "timeout", "-k", "5", str(self.timeout), str(self.toolchain / "bin" / "lean"), f"-M{self.memory_mb}",
                 "/tmp/Check.lean"]
        return argv

    def build_command(self, workdir: Path, module: str, timeout: int = 1800) -> list[str]:
        """`lake build module` in `workdir`, the one place it may write: for a docstring fix's branch."""
        argv = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv"]
        for d in ("/usr", "/bin", "/lib", "/lib64", "/etc/ld.so.cache"):
            if Path(d).exists():
                argv += ["--ro-bind", d, d]
        argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", str(self.home),
                 "--ro-bind", str(self.toolchain), str(self.toolchain), "--bind", str(workdir), str(workdir),
                 "--chdir", str(workdir), "--setenv", "HOME", "/tmp",
                 "--setenv", "PATH", f"{self.toolchain / 'bin'}:/usr/bin:/bin",
                 "timeout", "-k", "5", str(timeout), str(self.toolchain / "bin" / "lake"), "build", module]
        return argv

    def build(self, workdir: Path, module: str) -> tuple[bool, str]:
        try:
            code, out = self.runner(self.build_command(workdir, module), 1800)
        except subprocess.TimeoutExpired:
            return False, "the build did not finish within 30 minutes"
        return code == 0, out

    def check(self, imports: list[str], code: str, exists: Callable[[str], bool]) -> str:
        """Lean's messages on `code` under `imports`, or why it was refused."""
        why = bad_imports(imports, exists) or refuse(code)
        if why:
            return f"Not run: refused, because {why}."
        file = self.scratch / "Check.lean"
        self.write(file, "".join(f"import {m}\n" for m in imports) + "\n" + code.rstrip() + "\n")
        try:
            code_, out = self.runner(self.command(file), self.timeout)
        except subprocess.TimeoutExpired:
            return f"Lean did not finish within {self.timeout} seconds."
        out = out.strip()
        if len(out) > 8000:
            out = out[:8000] + "\n… (cut)"
        if code_ == 124:
            return f"Lean did not finish within {self.timeout} seconds.\n{out}"
        return out if out else ("No errors, and no messages." if code_ == 0 else f"Lean exited with {code_}.")
