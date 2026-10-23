#!/usr/bin/env python3
"""Build the site in _site/: the front end (web/) and the data its pages read (scripts/site_data.py).

  python3 scripts/build_site.py --dataset DIR --source CHECKOUT [--store evidence] [--imports DIR]
                                [--out _site] [--budget-mb 800]

`--imports` is where `evidence-store fetch-imports` fetched the stores this one imports. The build
fails when the site is larger than its budget: GitHub Pages serves at most 1 GB.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_settings  # noqa: E402
import site_data  # noqa: E402


class SiteTooLarge(RuntimeError):
    pass


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build(dataset: Path, store: Path, out: Path, settings: dict, source: Path | None = None,
          imports: Path | None = None, web: Path = ROOT / "web", budget_mb: int = 800,
          cap: int = site_data.CAP) -> dict:
    started = time.time()
    site = site_data.Site(site_data.load(dataset, store, imports, source, settings), cap=cap)
    if out.exists():
        shutil.rmtree(out)
    if web.exists():
        shutil.copytree(web, out)
    data = out / "data"
    for k, rows in site.node_shards():
        write(data / "nodes" / f"{k}.json", rows)
    for k, rows in site.name_shards().items():
        write(data / "names" / f"{k}.json", rows)
    for mi in range(site.project_modules):
        write(data / "m" / f"{mi}.json", site.module_file(mi))
    write(data / "modules.json", site.modules)
    names, titles = site.search()
    write(data / "search.json", names)
    write(data / "titles.json", titles)
    write(data / "named.json", site.named_rows())
    write(data / "upstream.json", site.upstream())
    write(data / "activity.json", site.activity())
    counts = site.counts()
    write(data / "meta.json", site.meta(counts))
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    if size > budget_mb * 2 ** 20:
        raise SiteTooLarge(f"the site is {size / 2 ** 20:.0f} MB, over its budget of {budget_mb} MB")
    return {**counts, "megabytes": round(size / 2 ** 20, 1), "seconds": round(time.time() - started)}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="build_site.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--source", type=Path)
    p.add_argument("--store", type=Path, default=ROOT / "evidence")
    p.add_argument("--imports", type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--budget-mb", type=int, default=800)
    a = p.parse_args(argv)
    try:
        result = build(a.dataset, a.store, a.out, load_settings(), a.source, a.imports, budget_mb=a.budget_mb)
    except SiteTooLarge as e:
        print(f"::error::{e}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
