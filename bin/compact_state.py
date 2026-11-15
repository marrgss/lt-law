#!/usr/bin/env python3
"""Build the compact state the nightly job needs from the full local downloads.

Usage: uv run bin/compact_state.py [scope/v1.yaml]

Writes data/state/laws.jsonl (laws/codes only, from data/raw/dokumentas.jsonl) and
data/state/suvestine_scope.jsonl (Suvestine version list for the scope's acts only). Run once,
or after a full metadata refresh (bin/fetch_meta.py); the nightly job then updates laws.jsonl
incrementally (source.update_recent_laws).
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import source  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/v1.yaml")
    scope = ap.parse_args().scope
    acts = yaml.safe_load(open(scope))["acts"]
    docs = {a["dokumento_id"] for a in acts}
    source.use_scope(acts)  # resolutions amending a points act in scope (KET) are kept too
    source.STATE.mkdir(parents=True, exist_ok=True)
    keep = source.META_FIELDS.split(",")
    n = 0
    with (source.STATE / "laws.jsonl").open("w") as out:
        for line in (source.DATA / "raw" / "dokumentas.jsonl").open():
            d = json.loads(line)
            if source.keep_meta(d):
                out.write(json.dumps({k: d.get(k) for k in keep}, ensure_ascii=False) + "\n")
                n += 1
    m = 0
    raw = source.DATA / "raw" / "suvestine.jsonl"  # optional: without it today.py queries the API directly
    if raw.exists():
        with (source.STATE / "suvestine_scope.jsonl").open("w") as out:
            for line in raw.open():
                d = json.loads(line)
                if d["dokumento_id"] in docs:
                    out.write(json.dumps(d, ensure_ascii=False) + "\n")
                    m += 1
    print(f"laws.jsonl: {n} laws | suvestine_scope.jsonl: {m} versions for {len(docs)} acts")


if __name__ == "__main__":
    main()
