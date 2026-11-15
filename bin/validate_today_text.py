#!/usr/bin/env python3
"""Validate today's-text recovery (ltlaw.today) against e-tar's version in force today.

Usage: uv run bin/validate_today_text.py [scope/v1.yaml] [--day YYYY-MM-DD] [--abbr X ...] [--show N]

For every flagged article for which ltlaw.today finds a text in another official consolidation,
compare it with e-tar's text in force on --day. Every mismatch is a WRONG answer (must be 0
before the two-version pages ship). Uses cached e-tar pages (D-004). Exit 1 if any wrong.
"""
import argparse
import collections
import datetime as dt
import difflib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import etar, source  # noqa: E402
from ltlaw.currency import Laws, assess  # noqa: E402
from ltlaw.parse import html_to_text, parse  # noqa: E402
from ltlaw.today import find_today  # noqa: E402
from ltlaw.validate import article_text, norm  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/v1.yaml")
    ap.add_argument("--day", default=dt.date.today().isoformat())
    ap.add_argument("--abbr", nargs="*")
    ap.add_argument("--show", type=int, default=3)
    a = ap.parse_args()
    laws = Laws()
    total = collections.Counter()
    summary = {"day": a.day, "acts": {}}
    for act in yaml.safe_load(open(a.scope))["acts"]:
        if act["dokumento_id"].startswith("EU."):  # EU acts are checked against EUR-Lex when fetched (D-037)
            continue
        if a.abbr and act["abbr"] not in a.abbr:
            continue
        doc = act["dokumento_id"]
        ours = parse(source.act_text(doc)[0], act.get("document"))
        st = assess(ours, act, laws, a.day)
        flagged = sum(1 for s in st.articles.values() if s.state != "current")
        if not flagged:
            continue
        found = find_today(ours, st, doc, act, laws, a.day)
        v = etar.version_valid_on(doc, a.day)
        if v is None:  # e-tar has no consolidated version (never amended, or none prepared): nothing to compare
            print(f"{act['abbr']:6} flagged {flagged:3} | today's text found {len(found):3} | SKIP: no e-tar version in force")
            continue
        html = etar.version_html_or_none(doc, v["id"])
        if html is None:
            print(f"{act['abbr']:6} flagged {flagged:3} | today's text found {len(found):3} | SKIP: e-tar has today's version only as files")
            continue
        T = {x.label: x for x in parse(html_to_text(html), act.get("document")).main.articles}
        ok, wrong = 0, []
        for label, tt in found.items():
            t = T.get(label)
            if t is not None and norm(article_text(tt.article)) == norm(article_text(t.variant_on(a.day))):
                ok += 1
            else:
                wrong.append(label)
        total.update(flagged=flagged, found=len(found), ok=ok, wrong=len(wrong))
        summary["acts"][act["abbr"]] = {"flagged": flagged, "found": len(found), "ok": ok, "wrong": len(wrong)}
        print(f"{act['abbr']:6s} flagged {flagged:3d} | today's text found {len(found):3d} | correct {ok:3d} | WRONG {len(wrong)} {wrong[:8]}")
        for label in wrong[: a.show]:
            t, tt = T.get(label), found[label]
            if t is None:
                print(f"       {label}: not in e-tar today")
                continue
            d = [x for x in difflib.ndiff(article_text(tt.article).split(), article_text(t.variant_on(a.day)).split()) if x[:1] in "+-"]
            refs_e = {r.nr for r in t.variant_on(a.day).all_refs()} - {r.nr for r in tt.article.all_refs()}
            print(f"       {label} ({tt.origin} {tt.version_from}): e-tar extra refs {sorted(refs_e)} | diff {' '.join(d)[:220]}")
    summary["total"] = dict(total)
    out = source.VALIDATION / "today_text.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print("TOTAL", dict(total))
    sys.exit(1 if total["wrong"] else 0)


if __name__ == "__main__":
    main()
