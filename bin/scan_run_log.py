#!/usr/bin/env python3
"""Look for personal or private details in a GitHub Actions run's log, before (or while) the build runs in public.

Usage: uv run bin/scan_run_log.py <run id> [--repo owner/name]
       uv run bin/scan_run_log.py --file saved.log

Reads the run's whole log (`gh run view --log`) and applies bin/publish_code.py's patterns (local paths, credentials,
mail addresses, wording about who asked, and private/public_scan.txt's names and identifiers), plus any
`<name>.workers.dev` address (the account's subdomain, which secrets and the mask keep out of logs). Prints each hit
with its job, step and kind (never the matched text); exit code 1 if anything was found. A hit in a public run: delete the
run (Actions → the run → Delete workflow run), then fix its cause.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import publish_code  # noqa: E402

WORKERS_DEV = re.compile(r"[\w-]+\.[\w-]+\.workers\.dev", re.I)


def scan(text: str) -> list[str]:
    pats, hits = publish_code.patterns(), []
    for n, line in enumerate(text.splitlines(), 1):
        where = "\t".join(line.split("\t")[:2]) if line.count("\t") >= 2 else f"line {n}"
        body = line.split("\t", 2)[-1].replace("/home/runner/", "<runner>/")  # GitHub's own machine, not ours
        found = [why for rx, why in pats if rx.search(body)]
        found += [f"a mail address" for m in publish_code.MAIL.findall(body) if not publish_code.MAIL_OK.search(m)]
        found += ["a workers.dev address"] if WORKERS_DEV.search(body) else []
        for why in found:
            hits.append(f"{where}: {why}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", help="the run's id")
    ap.add_argument("--repo", default="marrgss/lt-law", help="owner/name (default: the public repository)")
    ap.add_argument("--file", help="a saved log instead of a run id")
    a = ap.parse_args()
    if a.file:
        text = pathlib.Path(a.file).read_text(errors="replace")
    elif a.run:
        text = subprocess.run(["gh", "run", "view", a.run, "--repo", a.repo, "--log"], check=True, capture_output=True,
                              text=True).stdout
    else:
        ap.error("a run id or --file")
    hits = scan(text)
    for h in hits:
        print(h)  # job and step only: the matched text itself stays out of this output
    print(f"{len(text.splitlines())} lines, {len(hits)} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
