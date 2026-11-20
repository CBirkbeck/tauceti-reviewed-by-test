"""What the scripts share: where things are, the settings, how records' origins compare, and the hash that shards
names."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "data" / "settings.json"


def load_settings(path: Path = SETTINGS) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_settings(settings: dict, path: Path = SETTINGS) -> None:
    Path(path).write_text(json.dumps(settings, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def origin_key(repo: str, settings: dict | None = None) -> Callable[[str], str]:
    """How a run for the store's repository, which GitHub now names `repo` (intake's `--repo`), compares the origins
    of records (`origin.ref`): the key of a ref names the repository `repo` where the ref names it by any name it has
    had, the settings' `repo` and the names it had before (`formerly`), in either form intake writes, a link
    `https://github.com/<name>/…` or `<name>#<n>…`, and ignoring case, as GitHub's names do. Any other ref is its own
    key. A repository moved or renamed keeps its issues, their numbers and their comments' ids, and GitHub names them
    under the new name from then on, while the records made before name them under the old one: compared by key, an
    issue, comment or line recorded under either name is found recorded, and none is recorded twice. `settings` is
    data/settings.json unless given."""
    settings = load_settings() if settings is None else settings
    names = dict.fromkeys(n.lower() for n in [repo, settings["repo"], *settings.get("formerly", [])] if n)
    heads = [(head, to) for n in names for head, to in ((f"https://github.com/{n}/", f"https://github.com/{repo}/"),
                                                        (f"{n}#", f"{repo}#"))]
    longest = max((len(head) for head, _ in heads), default=0)

    def key(ref: str) -> str:
        start = ref[:longest].lower()
        for head, to in heads:
            if start.startswith(head):
                return to + ref[len(head):]
        return ref
    return key


def from_origin(records: Iterable[dict], ref: str, key: Callable[[str], str]) -> list[dict]:
    """The records made from one issue, comment, line or event, as evidence-core's `Store.from_origin` finds them, by
    the key of their origin (`origin_key`)."""
    want = key(ref)
    return [r for r in records if key((r.get("origin") or {}).get("ref") or "") == want]


def fnv_shard(name: str, shards: int) -> int:
    """FNV-1a over the name's UTF-16 code units, modulo ``shards``. The page computes the same
    (web/data.js, `fnv`), so it finds the shard of any name without an index."""
    h = 0x811C9DC5
    data = name.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h % shards


OPEN, CLOSE = "([{⟨⦃", ")]}⟩⦄"


def header(sig: dict) -> tuple[str, list]:
    """A signature (a row of the dataset's signature facet) as the docs head the declaration: for a
    structure that extends others, ` extends P₁, P₂` before the colon of its type, as doc-gen4 writes
    it. Returns the text and its refs, [start, stop, constant], moved to match."""
    text, refs = sig.get("text", ""), [list(r) for r in sig.get("refs") or []]
    parents = sig.get("extends") or []
    if not parents:
        return text, refs
    depth, at = 0, None
    for i, c in enumerate(text):
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        elif depth == 0 and text.startswith(" :", i) and text[i + 2:i + 3] in ("", " ", "\n"):
            at = i
            break
    if at is None:
        return text, refs
    piece, moved = " extends ", []
    for k, parent in enumerate(parents):
        if k:
            piece += ", "
        base = at + len(piece)
        moved += [[base + s, base + e, c] for s, e, c in parent.get("refs") or []]
        piece += parent.get("text", "")
    shift = len(piece)
    out = [r for r in refs if r[0] < at] + moved + [[s + shift, e + shift, c] for s, e, c in refs if s >= at]
    return text[:at] + piece + text[at:], out

