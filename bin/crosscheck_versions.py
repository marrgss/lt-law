#!/usr/bin/env python3
"""Compare the newest consolidated text in the open-data dump with e-tar's current one.

Usage: bin/crosscheck_versions.py DOKUMENTO_ID [DOKUMENTO_ID ...]

For each act it fetches:
  - the dump's newest Suvestine row (by galioja_nuo) from data.gov.lt, with its full text;
  - the current consolidation id from the e-tar act page, then that text from
    e-tar /rs/actualedition/<doc>/<id>/.
Both texts end with a "Pakeitimai:" list of every amending act (Nr., adoption date).
Comparing those lists checks the content, independently of any date or label field.
Read-only; two e-tar requests per act.
"""
import argparse
import html
import json
import re
import time
import urllib.parse
import urllib.request

API = "https://get.data.gov.lt/datasets/gov/lrsk/teises_aktai/Suvestine"
ETAR = "https://www.e-tar.lt"
UA = "Mozilla/5.0 (lt-law research; manual cross-check)"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read().decode("utf-8", "replace")


def amendments(text: str) -> list[tuple[str, str]]:
    """(Nr., date) pairs from the trailing 'Pakeitimai:' list."""
    i = text.rfind("Pakeitimai:")
    tail = text[i:] if i >= 0 else ""
    return re.findall(r"Nr\.\s*([^,\s]+)\s*,\s*(\d{4}-\d{2}-\d{2})", tail)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc_ids", nargs="+")
    a = ap.parse_args()
    for doc in a.doc_ids:
        q = (f'select(suvestines_id,galioja_nuo,galioja_iki,suv_duom_atnaujinimas,tekstas_lt)'
             f'&dokumento_id="{doc}"&sort(-galioja_nuo)&limit(1)')
        row = json.loads(fetch(f"{API}?" + urllib.parse.quote(q, safe='()&=,"_-')))["_data"][0]
        dump_am = amendments(row["tekstas_lt"] or "")

        page = fetch(f"{ETAR}/portal/lt/legalAct/{doc}/asr")
        cur = re.search(rf"actualedition/{re.escape(doc)}/([A-Za-z0-9]+)", page).group(1)
        period = re.search(r"(20\d\d-\d\d-\d\d) - (20\d\d-\d\d-\d\d)?", page)
        etar_txt = html.unescape(re.sub(r"<[^>]+>", "\n", fetch(f"{ETAR}/rs/actualedition/{doc}/{cur}/")))
        etar_am = amendments(etar_txt)

        missing = [x for x in etar_am if x not in dump_am]
        print(f"\n== {doc}")
        print(f"  dump : version {row['suvestines_id']} valid {row['galioja_nuo'][:10]}..{(row['galioja_iki'] or '')[:10] or 'open'}"
              f", prepared {row['suv_duom_atnaujinimas']}; amending acts listed: {len(dump_am)}, latest {max((d for _, d in dump_am), default='-')}")
        print(f"  e-tar: version {cur} valid {period.group(0) if period else '?'}"
              f"; amending acts listed: {len(etar_am)}, latest {max((d for _, d in etar_am), default='-')}")
        print(f"  in e-tar list but NOT in dump text: {len(missing)}"
              + (f" e.g. {', '.join(f'{n} ({d})' for n, d in missing[-5:])}" if missing else ""))
        time.sleep(2)


if __name__ == "__main__":
    main()
