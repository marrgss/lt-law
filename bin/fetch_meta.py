#!/usr/bin/env python3
"""Page through a TAR open-data model on data.gov.lt and save the selected fields as JSONL.

Usage:
  bin/fetch_meta.py Dokumentas data/raw/dokumentas.jsonl \
      --fields dokumento_id,tar_kodas,atv_dok_nr,rusis,galioj_busena,priemusi_inst,priimtas,paskelbta_tar,isigalioja,negalioja,pavadinimas
  bin/fetch_meta.py Suvestine data/raw/suvestine.jsonl \
      --fields dokumento_id,suvestines_id,galioja_nuo,galioja_iki,suv_duom_atnaujinimas

Read-only. Keyset pagination: sort(_id)&_id>"<last>". Spinta omits its `_page.next` token
when select() is used, and the full export (:format/csv) returns 504, hence this approach.
Resumes from the last _id already in <out>, so an interrupted run continues where it stopped.
"""
import argparse
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://get.data.gov.lt/datasets/gov/lrsk/teises_aktai"
UA = "lt-law-research/0.1 (personal civic project; contact via github)"


def get(url: str, tries: int = 6) -> dict:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            wait = 30 * (i + 1)
            print(f"  retry {i + 1}/{tries} in {wait}s: {e}", flush=True)
            time.sleep(wait)
    raise SystemExit(f"giving up on {url}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--fields", required=True, help="comma-separated field list for select(); _id is always added")
    ap.add_argument("--page-size", type=int, default=2000)
    ap.add_argument("--sleep", type=float, default=1.0)
    a = ap.parse_args()

    a.out.parent.mkdir(parents=True, exist_ok=True)
    last = None
    if a.out.exists():
        with a.out.open() as f:
            for line in f:
                last = json.loads(line)["_id"]
    fields = ",".join(dict.fromkeys(["_id", *a.fields.split(",")]))
    n = 0
    with a.out.open("a") as f:
        while True:
            q = f"select({fields})&sort(_id)&limit({a.page_size})"
            if last:
                q += f'&_id>"{last}"'
            url = f"{BASE}/{a.model}?" + urllib.parse.quote(q, safe='()&=,"_-<>')
            rows = get(url).get("_data", [])
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            n += len(rows)
            if n % 50000 < a.page_size:
                print(f"{a.model}: {n} rows this run", flush=True)
            if len(rows) < a.page_size:
                break
            last = rows[-1]["_id"]
            time.sleep(a.sleep)
    print(f"done: {n} rows this run")


if __name__ == "__main__":
    main()
