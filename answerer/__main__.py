"""The review answerer, on the server.

  python -m answerer run [--dry-run] [--only RECORD …] [--max N]
  python -m answerer seed FILE
  python -m answerer show

`run` answers the open items (the systemd timer runs it every hour). `--dry-run` posts nothing and opens
no pull request: it prints each verdict and what would have been posted, and keeps its own state, apart
from the real one. `--only` answers just those records, whether or not they were answered before (a dry
run only). `seed` records docstring fixes proposed by hand before the answerer existed, from a JSON
list of {id, pr, reply, by: {tool, model}, issue, decl, kind}, so that it closes them when they merge.
`show` prints what it remembers.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

from evidence_core.coverage import Evidence
from evidence_core.dataset import Dataset
from evidence_core.store import Store

from .items import open_items
from .leancheck import Sandbox
from .library import Library
from .post import Poster
from .prepare import Paths, build, cache, prepare, roadmaps
from .pulls import PullRequests
from .run import Config, answer
from .state import State
from .tools import LibraryTools


def log(s: str) -> None:
    print(f"{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {s}", flush=True)


def run(a: argparse.Namespace) -> int:
    import anthropic

    p = Paths.default()
    real = State(p.state)
    with State.locked(p.state):
        ready = prepare(p, real, log)
        state = real
        if a.dry_run:  # its own state: a copy of what was answered, or nothing at all for --only
            state = State(Path(tempfile.mkdtemp()) / "state.json")
            if not a.only:
                state.items = json.loads(json.dumps(real.items))
        settings = ready.settings
        store = Store.load(p.review / "evidence")
        maintainers = tuple(store.config.get("maintainers") or ())
        if ready.login not in maintainers:  # its closes would be refused: only a maintainer's count
            log(f"gh acts as {ready.login}, not one of the store's maintainers ({', '.join(maintainers)}): stopping")
            return 1
        ds = Dataset.load(ready.dataset)
        ev = Evidence.resolve(store.records, ds)
        items = open_items(ev, settings["repo"])
        if a.only:
            if not a.dry_run:
                print("--only is for a dry run", file=sys.stderr)
                return 2
            known = {i.id: i for i in items}
            items = [known[r] for r in a.only if r in known]
        lib = Library(p.work, ready.commit, root=settings["library"]["root"])
        sandbox = Sandbox(toolchain=ready.toolchain, roots=[p.work], lean_path=ready.lean_path, home=Path.home(),
                          scratch=p.scratch)
        tools = LibraryTools(lib, ds, sandbox, ready=lambda modules: build(p.work, modules))
        client = anthropic.Anthropic(api_key=p.key.read_text(encoding="utf-8").strip(), timeout=1800, max_retries=3)
        poster = Poster(settings["repo"], dry=a.dry_run)

        def build_pr(module: str) -> tuple[bool, str]:
            cache(p.prwork)  # the library's main, from the Lake caches, before the edited module is rebuilt
            return sandbox.build(p.prwork, module)

        prs = PullRequests(p.prwork, settings["library"]["repo"], build=build_pr, roadmaps=roadmaps,
                           site=settings["site"]["url"], dry=a.dry_run)
        cfg = Config(repo=settings["repo"], library_repo=settings["library"]["repo"], site=settings["site"]["url"],
                     commit=ready.commit, maintainers=maintainers, log=log)
        if a.max is not None:
            cfg.max_items = a.max
        system = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        done = answer(items, ev, ds, lib, tools, client, poster, prs, state, cfg, today, system)
        if a.dry_run:
            for e in done:
                print(json.dumps(e, ensure_ascii=False, indent=1))
            for argv, stdin in poster.would:
                print("WOULD:", " ".join(argv[:6]), "\n" + (stdin or ""))
        if state is not real:  # a dry run's spending is real spending
            real.spend(today, sum(e.get("cost", 0.0) for e in done))
            real.save()
    return 0


def seed(a: argparse.Namespace) -> int:
    p = Paths.default()
    with State.locked(p.state):
        state = State(p.state)
        for e in json.loads(Path(a.file).read_text(encoding="utf-8")):
            state.handled(e["id"], {k: v for k, v in e.items() if k != "id"} |
                          {"verdict": "docstring_fix", "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        state.save()
    print(f"{len(state.items)} items remembered")
    return 0


def show(a: argparse.Namespace) -> int:
    state = State(Paths.default().state)
    print(json.dumps({"spend": state.days, "flag_issue": state.flag_issue, "prepared": {
        k: v for k, v in state.prepared.items() if k != "lean_path"}, "items": state.items}, indent=1, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m answerer", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--only", nargs="*")
    r.add_argument("--max", type=int)
    sub.add_parser("seed").add_argument("file")
    sub.add_parser("show")
    a = ap.parse_args(argv)
    return {"run": run, "seed": seed, "show": show}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
