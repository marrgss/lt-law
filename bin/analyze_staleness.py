#!/usr/bin/env python3
"""Estimate how much of the in-force law is stale in the open-data consolidations.

Usage: bin/analyze_staleness.py [--docs data/raw/dokumentas.jsonl] [--suv data/raw/suvestine.jsonl]

Inputs come from bin/fetch_meta.py. For each in-force act, find amending acts whose title
cites it, published after the act's newest consolidation in the dump (or after the
one-time load of 2025-06-13). Matching is title-based and approximate:
  laws/codes:  "... Nr. VIII-1881 ..."                 -> atv_dok_nr (Seimas numbers are unique)
  others:      "... 2015 m. vasario 25 d. nutarimo Nr. 210 ..." -> (adoption year, number)
The numbers are an estimate for planning, not a data product. Known bias (2026-10-17):
  - misses code amendments: "Lietuvos Respublikos darbo kodekso 132 straipsnio pakeitimo
    įstatymas" carries no "Nr. XII-2603", so codes need name-based matching;
  - counts Government opinions on draft laws ("Dėl … pakeitimo įstatymo projekto …").
"""
import argparse
import collections
import json
import re

SNAPSHOT = "2025-06-13"
AMEND = re.compile(r"pakeitimo|papildymo|pripažinimo netekusi|pripažinimo netekusiu", re.I)
SEIMAS_NR = re.compile(r"Nr\.\s*([IVXL]{1,5}-\d+)")
DATED_NR = re.compile(r"(\d{4}) m\. [a-zė]+ \d{1,2} d\. [a-zėįąčšųūž]+ Nr\.\s*([0-9A-ZĄČĘĖĮŠŲŪŽa-z/().\-]+)")
LAW_TYPES = {"Įstatymas", "Kodeksas", "Konstitucinis įstatymas", "Konstitucija"}


def load(path):
    with open(path) as f:
        for line in f:
            yield json.loads(line)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", default="data/raw/dokumentas.jsonl")
    ap.add_argument("--suv", default="data/raw/suvestine.jsonl")
    a = ap.parse_args()

    docs = list(load(a.docs))
    newest_cons = {}
    for s in load(a.suv):
        k, d = s["dokumento_id"], (s.get("suv_duom_atnaujinimas") or s.get("galioja_nuo") or "")[:10]
        newest_cons[k] = max(newest_cons.get(k, ""), d)

    in_force = [d for d in docs if d.get("galioj_busena") == "galioja"]
    by_type = collections.Counter(d.get("rusis") for d in in_force)
    by_seimas_nr = {d["atv_dok_nr"]: d for d in in_force if d.get("rusis") in LAW_TYPES and d.get("atv_dok_nr")}
    by_year_nr = collections.defaultdict(list)
    for d in in_force:
        if d.get("rusis") in LAW_TYPES or not d.get("atv_dok_nr"):
            continue
        # adoption year ~ publication year (priimtas isn't fetched; late-December acts may miss)
        y = (d.get("priimtas") or d.get("paskelbta_tar") or d.get("isigalioja") or "")[:4]
        by_year_nr[(y, d["atv_dok_nr"])].append(d)

    stale = {}  # dokumento_id -> list of amending tar_kodas
    for am in docs:
        t, pub = am.get("pavadinimas") or "", am.get("paskelbta_tar") or ""
        if pub < SNAPSHOT or not AMEND.search(t):
            continue
        targets = [by_seimas_nr[n] for n in SEIMAS_NR.findall(t) if n in by_seimas_nr]
        for y, n in DATED_NR.findall(t):
            hits = by_year_nr.get((y, n), [])
            if len(hits) == 1:  # ambiguous (same year+number in two institutions) -> skip
                targets.append(hits[0])
        for tg in targets:
            if tg["dokumento_id"] == am["dokumento_id"]:
                continue
            if pub > newest_cons.get(tg["dokumento_id"], SNAPSHOT):
                stale.setdefault(tg["dokumento_id"], []).append(am.get("tar_kodas"))

    idx = {d["dokumento_id"]: d for d in in_force}
    stale_types = collections.Counter(idx[k].get("rusis") for k in stale if k in idx)
    print(f"acts total {len(docs)}, in force {len(in_force)}, with any consolidation in dump {sum(1 for d in in_force if d['dokumento_id'] in newest_cons)}")
    print(f"amending acts published since {SNAPSHOT}: "
          f"{sum(1 for d in docs if (d.get('paskelbta_tar') or '') >= SNAPSHOT and AMEND.search(d.get('pavadinimas') or ''))}")
    print(f"\n{'type':32s} {'in force':>9s} {'stale (est.)':>13s}")
    for t, n in by_type.most_common(12):
        print(f"{str(t):32s} {n:9d} {stale_types.get(t, 0):13d}")
    print(f"{'ALL':32s} {len(in_force):9d} {len(stale):13d}")
    top = sorted(stale.items(), key=lambda kv: -len(kv[1]))[:15]
    print("\nmost-amended since the snapshot:")
    for k, ams in top:
        d = idx.get(k, {})
        print(f"  {len(ams):3d}  {d.get('atv_dok_nr','?'):12s} {(d.get('pavadinimas') or '')[:90]}")


if __name__ == "__main__":
    main()
