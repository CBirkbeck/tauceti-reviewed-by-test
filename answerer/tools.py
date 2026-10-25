"""The model's tools, as the run provides them: reading and searching the library (`Library`), finding
a declaration in the dataset, and checking a short Lean file in the sandbox (`Sandbox`), after the
modules it imports are built from the Lake cache at the site's commit (`ready`). Each returns its text
and whether it failed."""
from __future__ import annotations

import json
from typing import Callable

from evidence_core.dataset import Dataset

from .items import declaration
from .leancheck import Sandbox, bad_imports, refuse
from .library import Library


class LibraryTools:
    def __init__(self, lib: Library, ds: Dataset, sandbox: Sandbox, ready: Callable[[list[str]], str | None]):
        self.lib, self.ds, self.sandbox, self.ready = lib, ds, sandbox, ready

    def run(self, name: str, inp: dict) -> tuple[str, bool]:
        if name == "read_source":
            out = self.lib.read(str(inp.get("path", "")), int(inp.get("start_line") or 1), int(inp.get("end_line") or 0) or None)
            return out, out.startswith("No such file")
        if name == "search_source":
            out = self.lib.search(str(inp.get("pattern", "")), str(inp.get("scope", self.lib.root)),
                                  str(inp.get("within", "")), bool(inp.get("fixed")))
            return out, out.startswith("Not searched")
        if name == "find_declaration":
            d = declaration(self.ds, self.lib, str(inp.get("name", "")))
            if not d["module"]:
                return f"No declaration {d['name']!r} in the dataset of Tau Ceti and what it imports.", True
            return json.dumps(d, ensure_ascii=False, indent=1), False
        if name == "lean_check":
            imports, code = [str(m) for m in inp.get("imports") or []], str(inp.get("code", ""))
            why = bad_imports(imports, self.lib.module_exists) or refuse(code)
            if why:
                return f"Not run: refused, because {why}.", True
            failed = self.ready(imports)
            if failed:
                return f"Not run: the imports did not build: {failed}", True
            out = self.sandbox.check(imports, code, exists=self.lib.module_exists)
            return out, out.startswith("Not run")
        return f"There is no tool {name!r}.", True
