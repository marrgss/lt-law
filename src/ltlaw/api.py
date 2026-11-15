"""A read-only API for agents, as static files (D-028): what the MCP/REST Worker (worker-mcp/) reads.

Everything is small enough for a Worker on the free plan (10 ms CPU per request): no file has to be parsed whole
to answer one question.

  /api/v1/meta.json                status day, data dates, counts, the bar (what the site promises)
  /api/v1/acts.json                every act: key (its alias), cite, name, unit, URL, status counts, text chunks
  /api/v1/text/<alias>/<k>.json    the articles of one act, about 40 per file; article label L is in file
                                   fnv1a(L) % chunks (the Worker computes it, no index needed)
  /api/v1/items/<k>.json           the search items (one per article page) in blocks of 500, in the order of
                                   search-index.json, so the full-text shards' item numbers find them
  /api/v1/upcoming.json            label changes in the next 30 days
  /api/v1/refs/<alias>.json        per article: what it cites and what cites it (articles of other acts, points,
                                   regulator decisions), from the page's links (D-036)

The texts are exactly those of the pages (data.json's "blocks"), never edited (D-002).
"""
from __future__ import annotations

import json
import pathlib

import yaml

PER_CHUNK = 40
ITEMS_PER_FILE = 500


def fnv1a(s: str) -> int:
    """32-bit FNV-1a over UTF-8 (the Worker has the same function)."""
    h = 0x811C9DC5
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def chunks_for(n: int) -> int:
    return max(1, -(-n // PER_CHUNK))


def _article(x: dict) -> dict:
    st = x["status"]
    return {"label": x["label"], "number": x["pretty"], "title": x["title"] or None, "url": x["url"],
            "place": [" ".join(p for p in (h.get("num"), h.get("kind")) if p) + (f" – {h['title']}" if h.get("title") else "")
                      for h in x.get("path") or []],
            "status": {k: st.get(k) for k in ("state", "label", "day", "label_valid_until", "reasons", "note",
                                               "future_change", "repealed_from", "applies_from") if st.get(k)},
            "source": x.get("text"),
            "text": [{"anchor": b.get("anchor"), "text": b["text"]} for b in x.get("blocks") or []],
            "amended_by": sorted({r.get("nr") for n in x.get("notes") or [] for r in n.get("refs") or [] if r.get("nr")}),
            "future": {"applies_from": x["future"]["applies_from"], "text": [b["text"] for b in x["future"]["blocks"]],
                       "changed_parts": x["future"].get("changed_parts") or []}
            if x.get("future") else None,
            "defined_terms": x.get("defined_terms") or [],
            "cite": x.get("cite")}


def write_act(write, alias: str, art_json: list[dict]) -> int:
    """The act's article texts in chunk files; returns the number of chunks."""
    n = chunks_for(len(art_json))
    files: list[dict] = [{} for _ in range(n)]
    for x in art_json:
        files[fnv1a(x["label"]) % n][x["label"]] = _article(x)
    for k, f in enumerate(files):
        write(f"/api/v1/text/{alias}/{k}.json", json.dumps(f, ensure_ascii=False, separators=(",", ":")))
    return n


def write_topics(write, acts: list[dict], path: pathlib.Path) -> list[str]:
    """scope/topics.yaml as /api/v1/topics.json: everyday words → articles. Problems: an act or article that isn't there."""
    by_abbr = {a["abbr"]: a for a in acts}
    out, problems = [], []
    for t in yaml.safe_load(path.read_text())["topics"]:
        refs = []
        for r in t["refs"]:
            abbr, _, label = r.rpartition(" ")
            if abbr not in by_abbr or label not in by_abbr[abbr]["labels"]:
                problems.append(f"topics.yaml: no {r} (for “{t['when'][0]}”)")
            else:
                refs.append([by_abbr[abbr]["alias"].rstrip("/").rsplit("/", 1)[-1], label])
        out.append({"when": [w.split() for w in t["when"]], "refs": refs})
    write("/api/v1/topics.json", json.dumps({"topics": out}, ensure_ascii=False, separators=(",", ":")))
    return problems


def write_site(write, acts: list[dict], search_items: list[list], upcoming: list[dict], meta: dict,
               search_acts: list[list] | None = None) -> None:
    """`search_acts`: search-index.json's act list; an item's first field is an index into it."""
    write("/api/v1/acts.json", json.dumps({"unofficial": True, "acts": [{
        "key": a["alias"].rstrip("/").rsplit("/", 1)[-1], "abbr": a["abbr"], "abbreviation": a.get("tag") or None, "cite": a["cite"],
        "name": a["name"], "unit": a["unit"], "url": a["url"], "official_url": a["official_url"], "n": a["n"],
        "counts": a["counts"], "chunks": a["api_chunks"], "consolidation_valid_from": a.get("consolidation_valid_from"),
        "consolidation_valid_to": a.get("consolidation_valid_to"), "expires": a.get("expires"),
        **({"names": a["names"]} if a.get("names") else {}), **({"genitive": a["genitive"]} if a.get("genitive") else {})} for a in acts]},
        ensure_ascii=False, separators=(",", ":")))
    for k in range(0, len(search_items), ITEMS_PER_FILE):
        write(f"/api/v1/items/{k // ITEMS_PER_FILE}.json",
              json.dumps(search_items[k:k + ITEMS_PER_FILE], ensure_ascii=False, separators=(",", ":")))
    write("/api/v1/upcoming.json", json.dumps({"label_changes_next_30_days": upcoming}, ensure_ascii=False, separators=(",", ":")))
    by_abbr = {a["abbr"]: a["alias"].rstrip("/").rsplit("/", 1)[-1] for a in acts}
    item_acts = []
    for sa in search_acts or []:  # [abbreviation or "", name, unit, cited as]: matched back to the act by name
        key = next((by_abbr[a["abbr"]] for a in acts if a["name"] == sa[1]), None)
        item_acts.append(key)
    ranges: dict[str, list[int]] = {}  # an act's items are consecutive: [first, last]
    for i, it in enumerate(search_items):
        key = item_acts[it[0]] if it[0] < len(item_acts) else None
        if key:
            ranges.setdefault(key, [i, i])[1] = i
    write("/api/v1/meta.json", json.dumps(dict(meta, items_per_file=ITEMS_PER_FILE, items=len(search_items), item_acts=item_acts,
                                               item_ranges=ranges),
                                          ensure_ascii=False, separators=(",", ":")))


def write_refs(write, base: str, acts: list[dict], search_items: list[list], search_acts: list[list] | None,
               refs: list[tuple[str, str]], decisions: dict[str, dict]) -> None:
    """References both ways, per act (D-036): {label: {"cites": [...], "cited_by": [...]}}; "" is the whole act (a decision
    citing the order that approved the rules). Only links the pages make: an article named with its act ("Lietuvos
    Respublikos … įstatymo 9 straipsnio", "šio kodekso 52 straipsnio", "Taisyklių 66 punkto"), so the lists are what the
    text says, never guessed; a reference in other words is missing, not wrong."""
    def key_of(a: dict) -> str:
        return a["alias"].rstrip("/").rsplit("/", 1)[-1]
    by_name = {a["name"]: a for a in acts}
    acts_of_items = [by_name.get(sa[1]) for sa in search_acts or []]
    pages: dict[str, dict] = {}  # page URL -> what an agent needs to know about it
    for it in search_items:
        a = acts_of_items[it[0]] if it[0] < len(acts_of_items) else None
        if a:
            pages[it[3]] = {"act": key_of(a), "cite": a["cite"], "label": it[1], "number": it[4], "title": it[2] or None,
                            "status": it[5], "url": it[3]}
    roots = {a["url"]: a for a in acts}

    def info(url: str) -> dict | None:
        page, _, anchor = url.partition("#")
        if page in pages:
            return dict(pages[page], part=anchor or None)
        if page in decisions:
            return {"kind": "decision", "url": page, **decisions[page]}
        if page in roots:
            a = roots[page]
            return {"act": key_of(a), "cite": a["cite"], "label": "", "title": a["name"], "url": page}
        return None

    out: dict[str, dict[str, dict[str, list]]] = {}
    seen = set()
    for src, dst in refs:
        s, d = info(src), info(dst)
        if not s or not d or (s.get("url"), d.get("url")) in seen or s.get("url") == d.get("url"):
            continue
        seen.add((s.get("url"), d.get("url")))
        if s.get("act"):  # an article's own references (a decision's are listed only where they point)
            out.setdefault(s["act"], {}).setdefault(s["label"], {"cites": [], "cited_by": []})["cites"].append(
                {k: v for k, v in dict(d, from_part=s.get("part")).items() if v is not None})
        if d.get("act"):
            out.setdefault(d["act"], {}).setdefault(d["label"], {"cites": [], "cited_by": []})["cited_by"].append(
                {k: v for k, v in dict(s, to_part=d.get("part")).items() if v is not None and k != "part"} | (
                    {"from_part": s["part"]} if s.get("part") else {}))
    for a in acts:  # every act has a file, so "nothing" is an answer and not a missing file
        write(f"/api/v1/refs/{key_of(a)}.json", json.dumps(out.get(key_of(a), {}), ensure_ascii=False, separators=(",", ":")))
    # how often other acts cite each act (references to its articles or to it as a whole): search ranks the law a
    # question is most likely about first among equals (DK before the extra-leave rules, 2026-11-03)
    write("/api/v1/cited.json", json.dumps({k: n for k in out if (n := sum(1 for v in out[k].values() for x in v["cited_by"]
                                                                         if x.get("act") and x["act"] != k))},
                                           separators=(",", ":")))

