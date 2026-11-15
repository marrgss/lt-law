"""Full-text search for a static site: an inverted index of word stems, split into small files.

A word is folded (lowercase, no diacritics) and cut to a rough Lithuanian stem: its first 6 letters, or for a
short word all but its ending ("atostogų", "atostogos" → "atosto"; "šalmas", "šalmą" → "salm"). Words shorter than
4 letters are not indexed; stems found in over a fifth of all articles are listed as common (the page ignores them). The index is split by the stem's first two letters (/paieska/t/<xx>.json), so a query downloads a few
small files. Postings are positions in search-index.json's items. The search page (app.js) uses it.
"""
from __future__ import annotations

import json
import re

FOLD = str.maketrans("ąčęėįšųūž", "aceeisuuz")
STEM = 6


def stem(word: str) -> str:
    """'atostogų' → 'atosto'; a short word loses its ending: 'šalmas', 'šalmą' → 'salm' (at least 4 letters)."""
    w = word.lower().translate(FOLD)
    return w[:min(STEM, max(4, len(w) - 2))]


def stems(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-ząčęėįšųūž]{4,}", (text or "").lower())}


def write(out, items_stems: list[set[str]], max_share: float = 0.2, subdir: str = "paieska/t") -> dict:
    """Write the shards; returns size facts for the build log."""
    post: dict[str, list[int]] = {}
    for i, ss in enumerate(items_stems):
        for s in ss:
            post.setdefault(s, []).append(i)
    limit = max(50, int(max_share * len(items_stems)))
    shards: dict[str, dict[str, list[int]]] = {}
    dropped = 0
    common = []
    for s, ids in post.items():
        if len(ids) > limit:
            dropped += 1
            common.append(s)
            continue
        shards.setdefault(s[:2], {})[s] = ids
    d = out / subdir
    d.mkdir(parents=True, exist_ok=True)
    size = 0
    for k, v in shards.items():
        txt = json.dumps(v, separators=(",", ":"))
        (d / f"{k}.json").write_text(txt)
        size += len(txt)
    return {"stems": len(post) - dropped, "common_dropped": dropped, "shards": len(shards), "bytes": size,
            "common": sorted(common)}
