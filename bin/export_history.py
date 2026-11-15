#!/usr/bin/env python3
"""Export every act's official consolidations since 2020 for dated answers (D-029): what an agent gets for
"article N as of date D".

Usage: uv run bin/export_history.py [scope/v1.yaml] [--out out/history] [--since 2020-01-01] [--acts DK,CK]

Versions come from two places, both the Chancellery's own consolidations, never ours (D-002):
  - the frozen Suvestine table (versions prepared up to 2025-05; texts cached under data/suvestine/),
  - our nightly archive of Dokumentas (data/dokumentas/<doc>/<day>.json, from 2026-10-17).
For a version valid on D, its text is the official text in force on D as the Chancellery consolidated it. Only
versions whose range is known answer a date: a closed one ("from 2024-07-01 to 2024-10-24"), or the last, open
one of the frozen table up to the table's last preparation (about 2025-05-20: whether it changed later, the table
can't say). Our own archive's open version is today's text (the pages and get_article without a date handle it:
its labels need the rules, not a date range). Other dates are gaps, said so.

Layout (uploaded as is to the R2 bucket; the Worker reads three objects per dated question):
  v1/<act>/versions.json        [{from, to, source, id, prepared, manifest}] in date order, plus the gaps
  v1/<act>/m/<from>_<id>.json    that version: {label: [article object, title]} and the order of articles
  v1/a/<hash>.json               one article's text (with its dated variants), stored once however many
                                 versions share it
  v1/<act>/h/<label>.json        one article's timeline: the periods its text stayed the same ({from, to, hash,
                                 title}), for the dated pages (/kaip-buvo/)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import source  # noqa: E402
from ltlaw.parse import parse  # noqa: E402
from ltlaw.render import _word_diff, text_changes  # noqa: E402
from ltlaw.today import _with_header  # noqa: E402
from ltlaw.validate import dropped_lines  # noqa: E402


def _article(a) -> dict:
    return {"title": a.title or None, "text": [b.text for b in a.blocks],
            "variants": [{"from": v.valid_from, "to": v.valid_to, "text": [b.text for b in v.blocks]} for v in a.variants],
            "amended_by": sorted({r.nr for r in a.all_refs()})}


def _put(out: pathlib.Path, rel: str, obj) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


BULK_END = "2025-05-20"  # the table's bulk load: daily preparations up to 2025-05-20, sporadic rows after (05-30, 06-23, …)


def freeze_day() -> str:
    """The last day of the table's bulk load: up to it the table is complete, so an open version prepared by then is
    known to apply up to this day. Later rows (a few acts, prepared in 2025-12 … 2026-07) don't extend that: they
    are sporadic, not a complete table (2026-10-23: taking the newest of them, 2026-07-20, as the freeze day would
    have stretched DK's 2025-01-01 version over a year of changes)."""
    return max((d for l in (source.STATE / "suvestine_scope.jsonl").open()
                if (d := (json.loads(l).get("suv_duom_atnaujinimas") or "")[:10]) and d <= BULK_END), default="")


def versions_of(sa: dict, since: str, frozen: str) -> list[dict]:
    """[{from, to, source, id, prepared, text}] for one act, the newer source winning a shared start date; each with
    the range it answers ("to"): its own end, or for the frozen table's open version the freeze day."""
    doc, out = sa["dokumento_id"], {}
    rows = source.dedupe_versions([r for l in (source.STATE / "suvestine_scope.jsonl").open()
                                   if (r := json.loads(l))["dokumento_id"] == doc], "latest")  # B51
    for r in sorted(rows, key=lambda r: r.get("suv_duom_atnaujinimas") or ""):  # same start: the newer wins below
        if (r.get("galioja_iki") or "9999") < since:
            continue
        p = source.DATA / "suvestine" / doc / f"{r['suvestines_id']}.json"
        row = json.loads(p.read_text()) if p.exists() else None
        if not row or not row.get("tekstas_lt"):
            continue
        frm = (r["galioja_nuo"] or "")[:10]
        to = (r.get("galioja_iki") or "")[:10] or None
        prep = (r.get("suv_duom_atnaujinimas") or "")[:10]
        if not to and frm > frozen:  # prepared ahead, starting after the freeze: when it ended is unknown
            continue
        if not to and prep > frozen:  # an open version prepared after the bulk load: no complete table says how long
            continue                 # it lasted (its range is answered only if a later row closes it)
        out[frm] = {"from": frm, "to": to or frozen, "open_end": not to, "source": "Suvestine",
                    "id": r["suvestines_id"], "prepared": (r.get("suv_duom_atnaujinimas") or "")[:10] or None,
                    "text": _with_header(row)}
    for p in source.snapshots(doc):  # our archive: a snapshot is kept only when the text changed
        row = json.loads(p.read_text())["row"]
        text = row.get("tekstas_lt") or ""
        if not source.has_consolidation(text):
            continue
        act = parse(text, sa.get("document"))
        if not act.version_from or not act.version_to:
            continue  # an open version: today's text, not a dated one (see the module's note)
        out[act.version_from] = {"from": act.version_from, "to": act.version_to, "source": "Dokumentas", "id": p.stem,
                                 "prepared": None, "fetched": p.stem, "text": text}
    return [out[k] for k in sorted(out)]


def export_act(out: pathlib.Path, sa: dict, key: str, since: str, written: set, frozen: str) -> dict:
    vs = versions_of(sa, since, frozen)
    listed, gaps = [], []
    timeline: dict[str, list[dict]] = {}  # label -> the periods its text stayed the same, for the dated pages
    for k, v in enumerate(vs):
        text = v.pop("text")
        act = parse(text, sa.get("document"))
        v["lines_not_shown"] = len(dropped_lines(text, act, []))  # the coverage check of the pages, per old version
        arts = {}
        for a in act.main.articles:
            obj = _article(a)
            h = hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
            if h not in written:
                _put(out, f"v1/a/{h}.json", obj)
                written.add(h)
            arts[a.label] = [h, a.title or None]
            ps = timeline.setdefault(a.label, [])
            words = hashlib.sha256(json.dumps([obj["title"], obj["text"], obj["variants"]], ensure_ascii=False).encode()).hexdigest()
            if ps and ps[-1]["words"] == words and _next(ps[-1]["to"]) >= v["from"]:  # same text in the next version
                ps[-1].update(to=v["to"], open_end=v.get("open_end", False), hash=h)  # (its list of amending acts may grow)
            else:  # changed, or back after a version without it: a new period
                ps.append({"from": v["from"], "to": v["to"], "open_end": v.get("open_end", False), "hash": h,
                           "title": a.title or None, "words": words, "_text": obj["text"]})
        name = f"{v['from']}_{v['id']}.json"
        _put(out, f"v1/{key}/m/{name}", {"act": key, "from": v["from"], "to": v["to"], "source": v["source"],
                                          "order": [a.label for a in act.main.articles], "articles": arts})
        listed.append(dict(v, manifest=name, articles=len(arts)))
        nxt = vs[k + 1]["from"] if k + 1 < len(vs) else None
        if v["to"] and nxt and v["to"] < nxt:  # days no consolidation in the open data covers
            gaps.append({"from": _next(v["to"]), "to": _prev(nxt)})
    gaps = [g for g in gaps if g["from"] <= g["to"]]
    covered_to = max((v["to"] for v in listed), default=None)
    _put(out, f"v1/{key}/versions.json", {"act": key, "versions": listed, "gaps": gaps, "covered_from": listed[0]["from"] if listed else None,
                                           "covered_to": covered_to, "frozen_table_day": frozen})
    for label, ps in timeline.items():  # one small object per article: the dated page reads it and one article text
        assert "/" not in label, label
        for k in range(1, len(ps)):  # what changed against the period before (D-030: "Kas pakeista")
            ch = text_changes(ps[k - 1]["_text"], ps[k]["_text"])
            if (ps[k - 1]["title"] or "") != (ps[k]["title"] or ""):
                ch.insert(0, {"html": _word_diff(ps[k - 1]["title"] or "", ps[k]["title"] or ""), "kind": "pavadinimas"})
            ps[k]["changes"] = ch
        _put(out, f"v1/{key}/h/{label}.json", {"act": key, "label": label, "gaps": gaps,
                                                "periods": [{k: x[k] for k in x if k not in ("words", "_text")} for x in ps],
                                                "frozen_table_day": frozen})
    return {"versions": len(listed), "gaps": len(gaps), "covered_to": covered_to}


def _next(d: str) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()


def _prev(d: str) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/v1.yaml")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("out/history"))
    ap.add_argument("--since", default="2020-01-01")
    ap.add_argument("--acts", default="")
    a = ap.parse_args()
    only = {x for x in a.acts.split(",") if x}
    scope = [s for s in yaml.safe_load(open(a.scope))["acts"] if not only or s["abbr"] in only]
    # the act's key is its site alias (as /api/v1/acts.json)
    acts_json = source.DATA.parent / "out" / "site" / "api" / "v1" / "acts.json"
    keys = {x["abbr"]: x["key"] for x in json.loads(acts_json.read_text())["acts"]} if acts_json.exists() else {}
    written: set = {p.stem for p in (a.out / "v1" / "a").glob("*.json")} if (a.out / "v1" / "a").exists() else set()
    tot = {"acts": 0, "versions": 0, "gaps": 0}
    frozen = freeze_day()
    for sa in scope:
        key = keys.get(sa["abbr"])
        if not key:
            print(f"skip {sa['abbr']}: not in the built site's acts.json (build the site first)")
            continue
        r = export_act(a.out, sa, key, a.since, written, frozen)
        tot["acts"] += 1
        tot["versions"] += r["versions"]
        tot["gaps"] += r["gaps"]
        print(f"{sa['abbr']:10s} {r['versions']:3d} versions, {r['gaps']} gaps, up to {r['covered_to']}")
    files = sum(1 for _ in a.out.rglob("*.json"))
    size = sum(p.stat().st_size for p in a.out.rglob("*.json"))
    print(f"TOTAL {tot}, {len(written)} distinct article texts, {files} objects, {size / 1e6:.0f} MB in {a.out}")


if __name__ == "__main__":
    main()
