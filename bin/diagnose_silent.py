#!/usr/bin/env python3
"""Explain each silent currency error: why an article we call current differs from e-tar today.

Usage: uv run bin/diagnose_silent.py [scope/v1.yaml] [--abbr CPK ...]

For every article validate_currency would count as SILENT, prints:
  - amending acts in e-tar's notes but not in ours (law missing from the stored text), and
    whether our title-based missing-law detection saw them;
  - otherwise a short word diff of the two texts.
Read-only; uses cached data only (data/etar, data/amending, snapshots).
"""
import argparse
import difflib
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import etar, source  # noqa: E402
from ltlaw.currency import Laws, assess  # noqa: E402
from ltlaw.parse import html_to_text, parse  # noqa: E402
from ltlaw.validate import article_text, norm  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/v1.yaml")
    ap.add_argument("--abbr", nargs="*")
    ap.add_argument("--day", default="2026-10-18")
    a = ap.parse_args()
    laws = Laws(fetch=False)
    for act in yaml.safe_load(open(a.scope))["acts"]:
        if a.abbr and act["abbr"] not in a.abbr:
            continue
        doc = act["dokumento_id"]
        ours = parse(source.act_text(doc)[0], act.get("document"))
        st = assess(ours, act, laws, a.day)
        v = etar.version_valid_on(doc, a.day)
        if v is None:  # no e-tar version for the day (never consolidated): nothing to compare (validate_currency: SKIP)
            continue
        html = etar.version_html_or_none(doc, v["id"])
        if html is None:
            print(f"== {act['abbr']}: e-tar has today's version only as files: nothing to compare")
            continue
        T = {x.label: x for x in parse(html_to_text(html), act.get("document")).main.articles}
        for art in ours.main.articles:
            if st.articles[art.label].state != "current":
                continue
            t = T.get(art.label)
            mine = art.variant_on(a.day)
            if t is not None and norm(article_text(mine)) == norm(article_text(t.variant_on(a.day))):
                continue
            print(f"== {act['abbr']} {art.label}")
            if t is None:
                print("   not in e-tar's version in force today")
                continue
            r_ours = {r.nr for r in mine.all_refs()}
            r_etar = {r.nr for r in t.variant_on(a.day).all_refs()}
            extra = sorted(r_etar - r_ours)
            if extra:
                for nr in extra:
                    m = laws.meta.get(nr)
                    print(f"   e-tar has {nr} (in force {m.get('isigalioja') if m else '?'}), ours not | title: "
                          f"{(m or {}).get('pavadinimas', '?')[:140]}")
                    print(f"      detected as missing law? {any(x['nr'] == nr for x in st.missing)}")
            else:
                w1, w2 = article_text(mine).split(), article_text(t.variant_on(a.day)).split()
                d = [x for x in difflib.ndiff(w1, w2) if x[:1] in "+-"][:16]
                print(f"   same refs; text diff: {' '.join(d)[:400]}")
                only = sorted(r_ours - r_etar)
                if only:
                    print(f"   refs only in ours: {only}")


if __name__ == "__main__":
    main()
