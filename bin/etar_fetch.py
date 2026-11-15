#!/usr/bin/env python3
"""Save e-tar's current consolidated text for a few hand-picked acts (D-004: no fetching at scale).

Usage: bin/etar_fetch.py DOKUMENTO_ID [DOKUMENTO_ID ...] [--out data/etar]

For each act: fetch the act page (/portal/lt/legalAct/<doc>/asr), read the current
consolidation id and validity period, then fetch /rs/actualedition/<doc>/<id>/ and save it as
<out>/<doc>/<id>.html plus <out>/<doc>/meta.json. Skips acts already saved with the same id.
Two requests per act, 3 s apart, identified User-Agent.
"""
import argparse
import json
import pathlib
import re
import time
import urllib.request

ETAR = "https://www.e-tar.lt"
UA = "Mozilla/5.0 (lt-law research; hand-picked acts only)"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read().decode("utf-8", "replace")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc_ids", nargs="+")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("data/etar"))
    a = ap.parse_args()
    for doc in a.doc_ids:
        page = fetch(f"{ETAR}/portal/lt/legalAct/{doc}/asr")
        cur = re.search(rf"actualedition/{re.escape(doc)}/([A-Za-z0-9]+)", page).group(1)
        period = re.search(r"(20\d\d-\d\d-\d\d) - (20\d\d-\d\d-\d\d)?", page)
        title = re.search(r"<title>(.*?)</title>", page, re.S)
        d = a.out / doc
        d.mkdir(parents=True, exist_ok=True)
        target = d / f"{cur}.html"
        if not target.exists():
            time.sleep(3)
            target.write_text(fetch(f"{ETAR}/rs/actualedition/{doc}/{cur}/"))
        meta = {"dokumento_id": doc, "suvestines_id": cur,
                "valid_from": period.group(1) if period else None,
                "valid_to": period.group(2) if period else None,
                "title": title.group(1).strip() if title else None,
                "fetched": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        print(f"{doc}  {cur}  {meta['valid_from']}..{meta['valid_to']}  {target.stat().st_size} B  {meta['title'][:60] if meta['title'] else ''}")
        time.sleep(3)


if __name__ == "__main__":
    main()
