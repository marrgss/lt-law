#!/usr/bin/env python3
"""Save today's Dokumentas rows (full text + metadata) for every act in a scope file.

Usage: uv run bin/snapshot_scope.py [scope/p2.yaml] [--amending]

Writes data/dokumentas/<dokumento_id>/<YYYY-MM-DD>.json (once per day per act).
--amending also snapshots the amending laws cited in each act's notes (needed to resolve
staged entry-into-force dates); they are fetched once and reused.
data.gov.lt answers HTTP 429 for minutes after a few big texts: the script waits it out and paces its requests.
"""
import argparse
import json
import pathlib
import re
import sys
import time
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import source
from ltlaw.currency import Laws  # noqa: E402

GAP_S, WAIT_S, WAITS = 5, 60, 10


def patient(dokumento_id: str, **kw) -> pathlib.Path:
    """source.snapshot, waiting out data.gov.lt's 429s (a minute each, ten at most)."""
    for n in range(WAITS + 1):
        try:
            return source.snapshot(dokumento_id, **kw)
        except urllib.error.HTTPError as e:
            if e.code != 429 or n == WAITS:
                raise
            print(f"      HTTP 429: waiting {WAIT_S} s", flush=True)
            time.sleep(WAIT_S)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/p2.yaml")
    ap.add_argument("--amending", action="store_true")
    a = ap.parse_args()
    acts = yaml.safe_load(open(a.scope))["acts"]
    meta = source.act_metadata() if a.amending else {}
    for act in acts:
        p = patient(act["dokumento_id"])
        print(f"{act['abbr']:5s} {p}  {p.stat().st_size} B", flush=True)
        if not a.amending:
            continue
        text = json.loads(p.read_text())["row"]["tekstas_lt"] or ""
        nrs = sorted(set(re.findall(r"Nr\.\s*([IVXL]+-\d+)", text)))
        # only laws whose text the rules read: adopted since Laws.TEXT_SINCE (older ones use metadata, D-011)
        todo = [meta[n]["dokumento_id"] for n in nrs if n in meta
                and (meta[n].get("priimtas") or meta[n].get("paskelbta_tar") or "") >= Laws.TEXT_SINCE]
        have = {q.name for q in (source.DATA / "amending").glob("*")} if (source.DATA / "amending").exists() else set()
        new = [d for d in todo if d not in have]
        print(f"      amending laws cited: {len(nrs)}, known: {len(todo)}, to fetch: {len(new)}", flush=True)
        for d in new:
            patient(d, root=source.DATA / "amending", day="fixed")
            time.sleep(GAP_S)


if __name__ == "__main__":
    main()
