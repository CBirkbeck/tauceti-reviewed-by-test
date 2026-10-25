"""What the scripts share: where things are, the settings, and the hash that shards names."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "data" / "settings.json"


def load_settings(path: Path = SETTINGS) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_settings(settings: dict, path: Path = SETTINGS) -> None:
    Path(path).write_text(json.dumps(settings, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


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

