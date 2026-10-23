#!/usr/bin/env python3
"""The extractor releases this repository uses: those of one series (`extractor.series` in
data/settings.json, `0.13`, which writes `ltb-dataset/2`), the newest for each Lean toolchain. A new
series is taken on deliberately, by changing the setting, never because one was published.

  python3 scripts/extractor.py toolchains                 the toolchains the series has a release for
  python3 scripts/extractor.py tag <toolchain>            the release for a toolchain (or a lean-toolchain file)
  python3 scripts/extractor.py install <toolchain> <dir>  unpack that release into <dir>; print its tag
"""
from __future__ import annotations

import re
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings  # noqa: E402

TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)-lean-v(.+)$")
ASSET = "trust-extract-linux-x86_64.tar.gz"


def toolchain_of(value: str) -> str:
    """`leanprover/lean4:v4.36.0-rc1`, `v4.36.0-rc1` or a lean-toolchain file: `4.36.0-rc1`."""
    p = Path(value)
    if p.is_file():
        value = p.read_text(encoding="utf-8")
    return value.strip().split(":", 1)[-1].removeprefix("v")


def supported(tags: list[str], series: str) -> dict[str, str]:
    """For each toolchain, the newest release of ``series`` for it."""
    major, minor = (int(x) for x in series.split("."))
    best: dict[str, tuple[int, str]] = {}
    for tag in tags:
        m = TAG.match(tag)
        if not m or (int(m[1]), int(m[2])) != (major, minor):
            continue
        patch, toolchain = int(m[3]), m[4]
        if toolchain not in best or patch > best[toolchain][0]:
            best[toolchain] = (patch, tag)
    return {t: tag for t, (_, tag) in sorted(best.items())}


def release_tags(repo: str) -> list[str]:
    out = subprocess.run(["gh", "release", "list", "-R", repo, "--limit", "200", "--json", "tagName",
                          "--jq", ".[].tagName"], check=True, capture_output=True, text=True).stdout
    return out.split()


def install(repo: str, tag: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gh", "release", "download", tag, "-R", repo, "-p", ASSET, "-D", str(dest), "--clobber"],
                   check=True)
    with tarfile.open(dest / ASSET) as tar:
        tar.extractall(dest, filter="tar")
    (dest / ASSET).unlink()


def main(argv: list[str]) -> int:
    settings = load_settings()
    repo, series = settings["extractor"]["repo"], settings["extractor"]["series"]
    if not argv or argv[0] not in ("toolchains", "tag", "install") or (argv[0] != "toolchains" and len(argv) < 2):
        print(__doc__, file=sys.stderr)
        return 2
    table = supported(release_tags(repo), series)
    if argv[0] == "toolchains":
        print("\n".join(table))
        return 0
    toolchain = toolchain_of(argv[1])
    tag = table.get(toolchain)
    if tag is None:
        print(f"::error::the extractor has no release of series {series} for Lean {toolchain}", file=sys.stderr)
        return 1
    if argv[0] == "install":
        if len(argv) < 3:
            print(__doc__, file=sys.stderr)
            return 2
        install(repo, tag, Path(argv[2]))
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
