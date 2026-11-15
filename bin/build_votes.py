#!/usr/bin/env python3
"""Seimas votes (D-054, proof of concept): write the vote JSON into a built site for the Worker's vote tools.

Usage: uv run bin/build_votes.py --out out/gate [--data data/seimas]

Needs a built site (its api/v1/acts.json links votes to acts) and bin/fetch_votes.py's data. Prints, per term, how many
votes there are, how many have individual votes, how many name an act on the site, and votes whose individual count
differs from the totals.
"""
import argparse
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ltlaw import seimas  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--data", type=pathlib.Path, default=pathlib.Path("data/seimas"))
    ap.add_argument("--scope", type=pathlib.Path, default=pathlib.Path("scope/v1.yaml"))
    a = ap.parse_args()
    acts = json.loads((a.out / "api" / "v1" / "acts.json").read_text())["acts"]
    scope = yaml.safe_load(a.scope.open())["acts"]
    print(json.dumps(seimas.build(a.data, a.out, scope, acts), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
