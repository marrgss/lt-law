#!/usr/bin/env python3
"""Validate the parser: open-data text vs e-tar HTML of the same consolidated version.

Usage: uv run bin/validate_scope.py [scope/p2.yaml] [--show N]

Needs today's snapshots (bin/snapshot_scope.py). Fetches from e-tar only what isn't cached
under data/etar/ (the version list and the one matching version per act; D-004).
Exit code 1 if any act fails.
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import etar, source  # noqa: E402
from ltlaw.parse import html_to_text, parse  # noqa: E402
from ltlaw.validate import article_text, compare  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/p2.yaml")
    ap.add_argument("--show", type=int, default=3, help="print the first N differing articles per act")
    a = ap.parse_args()
    failed = 0
    summary = {"day": dt.date.today().isoformat(), "answer_key": "e-tar.lt, same consolidated version", "acts": {}}
    for act in yaml.safe_load(open(a.scope))["acts"]:
        if act["dokumento_id"].startswith("EU."):  # EU acts are checked against EUR-Lex when fetched (D-037)
            continue
        doc = act["dokumento_id"]
        ours = parse(source.act_text(doc)[0], act.get("document"))
        v = etar.version_from(doc, ours.version_from)
        if v is None:
            row = source.latest_snapshot(doc)["row"]
            if ours.version_from is None and row.get("galioj_busena") == "neįsigaliojęs":
                # adopted, never amended, not in force yet (NTRgĮ): e-tar has no consolidation to compare with
                print(f"SKIP {act['abbr']}: not in force yet, original text only (no consolidated version on e-tar)")
                summary["acts"][act["abbr"]] = {"ok": None, "not_in_force": True, "articles": len(ours.main.articles)}
                continue
            if ours.version_from is None or etar.original_in_force(doc, ours.version_from, row):
                # in force and never amended (TMĮ, KPTAĮ, …; EOSPPSAA, whose original Suvestine dates: B83): the original is the text
                print(f"SKIP {act['abbr']}: original text only, never consolidated (no consolidated version on e-tar)")
                summary["acts"][act["abbr"]] = {"ok": None, "original_only": True, "articles": len(ours.main.articles)}
                continue
            print(f"SKIP {act['abbr']}: e-tar has no version from {ours.version_from}")
            failed += 1
            continue
        html = etar.version_html_or_none(doc, v["id"])
        if html is None:
            print(f"SKIP {act['abbr']}: e-tar gives version {v['valid_from']} only as files (no HTML): unverified")
            summary["acts"][act["abbr"]] = {"ok": None, "unverified": True, "articles": len(ours.main.articles)}
            failed += 1
            continue
        theirs = parse(html_to_text(html), act.get("document"))
        r = compare(act["abbr"], ours, theirs)
        print(r.summary())
        summary["acts"][act["abbr"]] = {"ok": r.ok, "version": r.version, "articles": r.articles_ours,
                                        "text_diff": len(r.text_diff), "missing": len(r.missing), "extra": len(r.extra)}
        for kind in ("missing", "extra", "text_diff", "heading_diff", "warnings"):
            items = getattr(r, kind)
            if items:
                print(f"      {kind}: {items[:12]}{' …' if len(items) > 12 else ''}")
        O = {x.label: x for x in ours.main.articles}
        E = {x.label: x for x in theirs.main.articles}
        for k in r.text_diff[: a.show]:
            print(f"      --- {k} ours : {article_text(O[k])[:300]}")
            print(f"      --- {k} etar : {article_text(E[k])[:300]}")
        failed += not r.ok
    out = source.VALIDATION / "scope.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
