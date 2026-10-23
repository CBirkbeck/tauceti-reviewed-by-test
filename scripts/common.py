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
