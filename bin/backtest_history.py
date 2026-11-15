#!/usr/bin/env python3
"""Historical back-test of the labelling rules against the Chancellery's own past consolidations (D-024).

Usage: uv run bin/backtest_history.py [scope/v1.yaml] [--since 2023-01-01] [--until 2025-05-31] [--acts DK,CK] [--no-fetch]

For each act and each pair of consecutive official consolidations A → B (B starting in the period):
  lag     we hold A on B's first day (B not yet in the open data):  truth = B
  future  we hold B the day before it starts (prepared in advance):  truth = A
Our rules label every article as they would have on that day, knowing only laws published by then
(amending-law texts are today's copies: a small leak, noted in the output). A "current" article whose
text differs from the truth is a silent error, and so is a "repealed" one in force in the truth; a flagged
article whose text equals it is a false alarm.
Texts come from the frozen Suvestine table, cached under data/suvestine/<doc>/<id>.json (fetched once,
politely). Writes validation/backtest_history.json. Read-only towards e-tar (not used at all).
"""
import argparse
import datetime as dt
import json
import pathlib
import sys
import time
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import source  # noqa: E402
from ltlaw.currency import Laws, _article_repealed, _expired_articles, article_expiry, assess  # noqa: E402
from ltlaw.parse import parse  # noqa: E402
from ltlaw.today import _with_header  # noqa: E402
from ltlaw.validate import article_text, norm as _norm  # noqa: E402
import re  # noqa: E402


def norm(t: str) -> str:
    """As the validators compare, without the internal part markers some old versions carry
    ("part_d1af…_end", different in every version) and editorial "N. Neteko galios nuo D" lines."""
    t = re.sub(r"part_?[0-9a-f]{32}_?end", "", t)
    t = re.sub(r"(^|\n)\s*\d+(-\d+)?\.\s*Neteko galios nuo \d{4}-\d{2}-\d{2}\.?", "\\1", t)
    return _norm(t)


class LawsAsOf(Laws):
    """The law register as it was known on `day`: laws published later don't exist yet."""
    _texts: dict = {}

    def __init__(self, base: Laws, day: str):
        self.meta = {k: v for k, v in base.meta.items() if (v.get("paskelbta_tar") or v.get("priimtas") or "9999") <= day}
        self.fetch = False
        self._cache = LawsAsOf._texts  # parsed amending laws are shared (their texts don't depend on the day)


def version_text(doc: str, row: dict, fetch: bool) -> str | None:
    path = source.DATA / "suvestine" / doc / f"{row['suvestines_id']}.json"
    if not path.exists():
        if not fetch:
            return None
        got = source.query("Suvestine", f'select(suvestines_id,galioja_nuo,galioja_iki,suv_duom_atnaujinimas,tekstas_lt)'
                                        f'&dokumento_id="{doc}"&suvestines_id="{row["suvestines_id"]}"&limit(1)')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(got[0] if got else None, ensure_ascii=False))
        time.sleep(0.5)
    r = json.loads(path.read_text())
    return _with_header(r) if r and r.get("tekstas_lt") else None


def day_before(d: str) -> str:
    return (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/v1.yaml")
    ap.add_argument("--since", default="2023-01-01")
    ap.add_argument("--until", default="2025-05-31")
    ap.add_argument("--acts", default="", help="comma-separated abbreviations (default: all)")
    ap.add_argument("--no-fetch", action="store_true", help="use cached version texts only")
    a = ap.parse_args()
    only = {x for x in a.acts.split(",") if x}
    scope = [s for s in yaml.safe_load(open(a.scope))["acts"] if not only or s["abbr"] in only]
    versions: dict = {}
    for line in (source.STATE / "suvestine_scope.jsonl").open():
        r = json.loads(line)
        versions.setdefault(r["dokumento_id"], []).append(r)
    base = Laws(fetch=False)
    tot = Counter()
    per_act, silent = {}, []
    for sa in scope:
        vs = sorted(source.dedupe_versions(versions.get(sa["dokumento_id"], []), "earliest"), key=lambda r: r["galioja_nuo"])
        c = Counter()
        for A, B in zip(vs, vs[1:]):
            b0 = (B["galioja_nuo"] or "")[:10]
            if not (a.since <= b0 <= a.until) or (A["galioja_nuo"] or "")[:10] >= b0:
                continue
            ta, tb = version_text(sa["dokumento_id"], A, not a.no_fetch), version_text(sa["dokumento_id"], B, not a.no_fetch)
            if not ta or not tb:
                c["pairs_missing_text"] += 1
                continue
            act_a, act_b = parse(ta, sa.get("document")), parse(tb, sa.get("document"))
            act_a.prepared, act_b.prepared = A.get("suv_duom_atnaujinimas"), B.get("suv_duom_atnaujinimas")
            prepared_b = (B.get("suv_duom_atnaujinimas") or "")[:10]
            cases = [("lag", act_a, b0, act_b)]
            if prepared_b and prepared_b < b0:
                cases.append(("future", act_b, day_before(b0), act_a))
            for kind, held, day, truth in cases:
                st = assess(held, sa, LawsAsOf(base, day), day)
                T = {x.label: x for x in truth.main.articles}
                c["pairs"] += 1
                for art in held.main.articles:
                    s = st.articles[art.label]
                    t = T.get(art.label)
                    same = t is not None and norm(article_text(art.variant_on(day))) == norm(article_text(t.variant_on(day)))
                    c["articles"] += 1
                    if s.state == "repealed":  # right if the official text has no article in force either
                        tv = t.variant_on(day) if t is not None else None
                        # the official text may keep printing an article that its own note says has lapsed
                        exp = article_expiry(tv, art.label) if tv is not None else None
                        gone = tv is None or _article_repealed(tv)[0] or bool(exp and exp <= day) or \
                            art.label in _expired_articles(truth, day)
                        c["repealed_ok" if gone else "SILENT"] += 1
                        if not gone:
                            silent.append({"act": sa["abbr"], "article": art.label, "case": kind, "day": day,
                                           "held": held.version_from, "truth": truth.version_from, "said": "repealed"})
                    elif s.state == "current":
                        c["current_ok" if same else "SILENT"] += 1
                        if not same:
                            silent.append({"act": sa["abbr"], "article": art.label, "case": kind, "day": day,
                                           "held": held.version_from, "truth": truth.version_from})
                    elif same:
                        c["false_alarm"] += 1
                    else:
                        c["flag_correct"] += 1
        per_act[sa["abbr"]] = dict(c)
        tot.update(c)
        if c:
            print(f"{sa['abbr']:12s} {dict(c)}", flush=True)
    out = {"run": dt.date.today().isoformat(), "period": f"{a.since}..{a.until}", "totals": dict(tot), "acts": per_act,
           "silent": silent[:500],
           "note": "rules as of this commit, laws known by each simulated day; amending-law texts are today's copies"}
    source.VALIDATION.mkdir(exist_ok=True)
    (source.VALIDATION / "backtest_history.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("TOTAL", dict(tot))


if __name__ == "__main__":
    main()
