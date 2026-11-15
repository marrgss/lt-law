#!/usr/bin/env python3
"""The open-data side of adding acts: amending orders, Suvestine version lists and today's texts, waiting out failures.

Usage: uv run bin/fetch_new_acts.py <subset.yaml> [--amenders] [--lists] [--texts]   (none given: all three)

<subset.yaml> holds only the new acts (scope/v1.yaml's format). --amenders before bin/snapshot_scope.py <subset> --amending
(the amending orders it finds are what the snapshot and the validators read), --lists --texts after it.
  --amenders  rules made of points: the resolutions/orders amending them (source.update_point_amenders, title search)
  --lists     Suvestine version lists, repeated until every act was read today (one failed query ends a library call)
  --texts     the Suvestine version valid today for every act (today._suvestine_valid_on), retrying acts that met an
              HTTP 500 (SUVESTINE_DOWN) rather than counting them as having none
data.gov.lt answers HTTP 500/429 in spells (2026-11-03: most of the morning): each pass waits and goes on with the rest.
"""
import argparse
import datetime as dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import source, today  # noqa: E402


def amenders(acts: list[dict]) -> None:
    """The title search for each act's amending orders, repeated until every act was searched today: a query that times
    out is skipped silently for the next night (2026-11-03: 29 of 205 new rule sets never searched, and their texts
    read as current against amendments e-tar shows)."""
    day = dt.date.today().isoformat()
    source.use_scope(acts)

    def left() -> list[dict]:
        p = source.STATE / "point_amenders_checked.json"
        seen = json.loads(p.read_text()) if p.exists() else {}
        return [x for x in acts if seen.get(f"{x['number']}/{x['adopted']}") != day]
    t0, added, todo = time.time(), 0, left()
    for attempt in range(6):
        if not todo:
            break
        source.POINT_ACTS[:] = [(x["number"], x["adopted"]) for x in todo]  # only those not searched yet (use_scope set the kinds)
        added += source.update_point_amenders(refresh_days=0, budget_s=7200)
        todo = left()
        print(f"  amending orders: {added} rows added, {len(todo)} acts not searched yet ({time.time() - t0:.0f} s)", flush=True)
        if todo:
            time.sleep(60)
    source.use_scope(acts)
    print(f"amending orders: {added} rows added; not searched: {[x['abbr'] for x in todo]}")


def lists(acts: list[dict]) -> None:
    day = dt.date.today().isoformat()

    def done() -> int:
        p = source.STATE / "suvestine_checked.json"
        ch = json.loads(p.read_text()) if p.exists() else {}
        return sum(ch.get(a["dokumento_id"]) == day for a in acts)
    t0, prev, stuck = time.time(), -1, 0
    while (n := done()) < len(acts) and stuck < 6:
        stuck, prev = (stuck + 1 if n == prev else 0), n
        source.SUVESTINE_DOWN = False
        source.update_suvestine_lists(acts, refresh_days=0, per_run=len(acts), budget_s=3600)
        print(f"  version lists: {done()}/{len(acts)} read today ({time.time() - t0:.0f} s)", flush=True)
        if done() < len(acts):
            time.sleep(30)
    print(f"version lists: {done()}/{len(acts)} read today")


def texts(acts: list[dict]) -> None:
    today.FETCH_BUDGET_S = 7200
    day, todo, got, t0 = dt.date.today().isoformat(), list(acts), {}, time.time()
    for attempt in range(8):
        left = []
        for a in todo:
            source.SUVESTINE_DOWN = False
            try:
                r = today._suvestine_valid_on(a["dokumento_id"], day)
            except Exception:
                r = None
            if source.SUVESTINE_DOWN:  # the table failed, not "no version": ask again
                left.append(a)
            else:
                got[a["abbr"]] = bool(r)
        print(f"  pass {attempt}: {len(todo) - len(left)} answered, {len(left)} left ({time.time() - t0:.0f} s)", flush=True)
        if not left:
            break
        todo = left
        time.sleep(90)
    print(f"today's texts: {sum(got.values())}/{len(acts)} found, {sum(not v for v in got.values())} without a version "
          f"valid today, {len(acts) - len(got)} unanswered")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subset")
    ap.add_argument("--amenders", action="store_true")
    ap.add_argument("--lists", action="store_true")
    ap.add_argument("--texts", action="store_true")
    a = ap.parse_args()
    every = not (a.amenders or a.lists or a.texts)
    acts = [x for x in yaml.safe_load(open(a.subset))["acts"] if not x["dokumento_id"].startswith("EU.")]
    if (a.amenders or every) and any(x.get("adopted") for x in acts):  # approved by a resolution or an order
        amenders([x for x in acts if x.get("adopted")])
    if a.lists or every:
        lists(acts)
    if a.texts or every:
        texts(acts)


if __name__ == "__main__":
    main()
