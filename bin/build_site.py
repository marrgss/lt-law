#!/usr/bin/env python3
"""Build the static site for a scope into out/site (local only in P2).

Usage: uv run bin/build_site.py [scope/p2.yaml] [--out out/site] [--base-url http://127.0.0.1:8765]
                                [--day YYYY-MM-DD] [--indexable]

Uses the newest snapshots in data/ (bin/snapshot_scope.py). Without --indexable every page
carries noindex and robots.txt disallows everything, so a test deploy can't get indexed.
"""
import argparse
import datetime as dt
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw.currency import Laws  # noqa: E402
from ltlaw.render import Site  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/p2.yaml")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("out/site"))
    ap.add_argument("--base-url", default="http://127.0.0.1:8765")
    ap.add_argument("--day", default=dt.date.today().isoformat())
    ap.add_argument("--indexable", action="store_true", help="P3 launch only: allow search engines")
    a = ap.parse_args()
    if a.out.exists():
        shutil.rmtree(a.out)  # build output only; it is regenerated every time
    site = Site(a.out, a.base_url, a.day, a.indexable, Laws())
    acts = []
    scope = yaml.safe_load(open(a.scope))["acts"]
    site.prepare(scope)
    for act in scope:
        acts.append(site.act(act))
        print(f"{act['abbr']:5s} {acts[-1]['n']} articles -> {acts[-1]['url']}", flush=True)
    site.finish(acts)
    files = list(a.out.rglob("*"))
    print(f"{sum(f.is_file() for f in files)} files, {sum(f.stat().st_size for f in files if f.is_file()) / 1e6:.1f} MB in {a.out}")


if __name__ == "__main__":
    main()
