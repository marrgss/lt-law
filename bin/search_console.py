#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["cryptography>=44"]
# ///
"""What Google search brings to the site: Search Console's own aggregate numbers (no visitor tracking), read only.

Usage: uv run bin/search_console.py [--days 28] [--end YYYY-MM-DD] [--site sc-domain:atviri-teises-aktai.lt] [--brief]

Prints totals against the previous period, the three kinds of queries (an article by citation such as "ck 3.88", an
act by name, a topic), the acts that get impressions, queries just below the first page (position 8-20: titles and
descriptions can lift them), and topic queries the site has no act for (candidates for the scope, ROADMAP).
Saves the rows to private/search_console/<end>_<days>d.json (gitignored). --brief prints one line (for checkup.py).

Access (OPERATIONS "Search Console, read only"): a Google Cloud service account whose JSON key is
~/.config/lt-law/search-console.json (chmod 600, never printed), added in Search Console as a *Restricted* user. The
token asks only for the webmasters.readonly scope, so the key can read the numbers and nothing else.
Exit code 1 without a key or access. Includes Google's fresh data (dataState "all"): --end defaults to yesterday,
whose numbers still grow for a day or two.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "private" / "search_console"
KEY = pathlib.Path(os.environ.get("GSC_KEY_FILE") or pathlib.Path.home() / ".config" / "lt-law" / "search-console.json")
SITE = "sc-domain:atviri-teises-aktai.lt"
BASE = "https://atviri-teises-aktai.lt"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"

# an article asked by its citation: "ck 3.88", "dk 64 str", "bpk 97", "64 straipsnis", "ket 20 punktas"
CITATION = re.compile(r"\d+\s*(?:[.,]\d+)*\s*(?:str\b|straipsn|p\b|punkt|dalis|d\.)|\b(?:str|straipsn\w*)\.?\s*\d"
                      r"|^\s*[a-ząčęėįšųūž]{2,8}[\s-]*\d|^\s*\d+\s+[a-ząčęėįšųūž]{2,8}\s*$|^\s*\d+\.\d+\s*$", re.I)
ACT_NAME = re.compile(r"įstatym|istatym|kodeks|taisykl|nutarim|įsakym|isakym|aprašas|aprasas|reglament|konstitucij|tvarkos apra", re.I)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def token() -> str:
    """An access token for the read-only scope, from the service account's key (JWT bearer grant)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    if not KEY.exists():
        sys.exit(f"no key at {KEY} (OPERATIONS: Search Console, read only)")
    if KEY.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        sys.exit(f"{KEY} is readable by others: chmod 600 it")
    k = json.loads(KEY.read_text())
    now = int(time.time())
    claims = {"iss": k["client_email"], "scope": SCOPE, "aud": k["token_uri"], "iat": now, "exp": now + 600}
    signing = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()) + "." + _b64(json.dumps(claims).encode())
    pk = serialization.load_pem_private_key(k["private_key"].encode(), password=None)
    sig = pk.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                   "assertion": signing + "." + _b64(sig)}).encode()
    with urllib.request.urlopen(urllib.request.Request(k["token_uri"], data=body), timeout=30) as r:
        return json.load(r)["access_token"]


def api(tok: str, path: str, payload: dict | None = None) -> dict:
    url = "https://www.googleapis.com/webmasters/v3/" + path
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:300]
        sys.exit(f"Search Console API {e.code}: {msg}" + ("\n(is the service account added to the property as a user?)"
                                                          if e.code == 403 else ""))


def rows(tok: str, site: str, start: dt.date, end: dt.date, dims: list[str]) -> list[dict]:
    out, first = [], 0
    while True:
        r = api(tok, f"sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query",
                {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dims, "rowLimit": 25000,
                 "startRow": first, "dataState": "all"})
        got = r.get("rows") or []
        out += [{**dict(zip(dims, x["keys"])), **{m: x[m] for m in ("clicks", "impressions", "ctr", "position")}} for x in got]
        if len(got) < 25000:
            return out
        first += len(got)


FOLD = str.maketrans("ąčęėįšųūž", "aceeisuuz")


def kind(q: str, abbrs: set[str] = frozenset()) -> str:
    """abbrs: the acts' short names folded ("kasoktį" and "kasokti" are both KASOKTĮ's)."""
    if CITATION.search(q):
        return "citation"
    if ACT_NAME.search(q) or set(q.lower().translate(FOLD).split()) & abbrs:
        return "act name"
    return "topic"


def agg(rs: list[dict]) -> dict:
    imp = sum(r["impressions"] for r in rs)
    clicks = sum(r["clicks"] for r in rs)
    pos = sum(r["position"] * r["impressions"] for r in rs) / imp if imp else 0
    return {"clicks": clicks, "impressions": imp, "position": round(pos, 1), "n": len(rs)}


def site_acts() -> list[dict]:
    with urllib.request.urlopen(urllib.request.Request(BASE + "/api/v1/acts.json", headers={"User-Agent": "lt-law-gsc"}),
                                timeout=30) as r:
        return json.load(r)["acts"]


def act_of(page: str, paths: dict[str, str]) -> str:
    p = urllib.parse.urlparse(page).path
    m = re.match(r"/ta/[^/]+/", p)
    if m and m.group(0) in paths:
        return paths[m.group(0)]
    return "/" + p.strip("/").split("/")[0] + "/" if p.strip("/") else "home"


def words(s: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-ząčęėįšųūž]{4,}", s.lower())}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--end", help="last day (default: yesterday; its numbers are still partial)")
    ap.add_argument("--site", default=SITE)
    ap.add_argument("--brief", action="store_true", help="one line: the period against the previous one")
    a = ap.parse_args()
    end = dt.date.fromisoformat(a.end) if a.end else dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=a.days - 1)
    pstart, pend = start - dt.timedelta(days=a.days), start - dt.timedelta(days=1)
    tok = token()

    now, prev = agg(rows(tok, a.site, start, end, ["date"])), agg(rows(tok, a.site, pstart, pend, ["date"]))
    line = (f"{start}..{end}: {now['clicks']:.0f} clicks, {now['impressions']:.0f} impressions "
            f"(previous {a.days} days: {prev['clicks']:.0f}, {prev['impressions']:.0f})")
    if a.brief:
        print(line)
        return

    acts = site_acts()
    abbrs = {x["abbr"].lower().translate(FOLD) for x in acts}
    qp = rows(tok, a.site, start, end, ["query", "page"])
    qs = rows(tok, a.site, start, end, ["query"])
    pages = rows(tok, a.site, start, end, ["page"])
    sitemaps = api(tok, f"sites/{urllib.parse.quote(a.site, safe='')}/sitemaps").get("sitemap") or []
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{end}_{a.days}d.json").write_text(json.dumps({"site": a.site, "start": str(start), "end": str(end), "totals": now,
                                                           "previous": prev, "queries": qs, "pages": pages, "query_page": qp,
                                                           "sitemaps": sitemaps}, ensure_ascii=False, indent=1))
    print(line)
    print(f"(per-query rows cover {sum(r['clicks'] for r in qs):.0f} clicks: Google hides rare queries)")

    print("\nQueries by kind (impressions, clicks, mean position):")
    for k in ("citation", "act name", "topic"):
        s = agg([r for r in qs if kind(r["query"], abbrs) == k])
        print(f"  {k:9} {s['impressions']:6.0f} {s['clicks']:4.0f}  pos {s['position']:5.1f}  ({s['n']} queries)")

    paths = {urllib.parse.urlparse(x["url"]).path: x["abbr"] for x in acts}  # '/ta/<tar>/' -> short name
    by_act: dict[str, list[dict]] = {}
    for r in pages:
        by_act.setdefault(act_of(r["page"], paths), []).append(r)
    print(f"\nActs and sections ({len(pages)} pages with impressions):")
    for act, rs in sorted(by_act.items(), key=lambda x: -agg(x[1])["impressions"])[:20]:
        s = agg(rs)
        print(f"  {act:14} {s['impressions']:6.0f} impr {s['clicks']:4.0f} clicks  pos {s['position']:5.1f}  {s['n']} pages")

    near = sorted((r for r in qs if 8 <= r["position"] <= 20), key=lambda r: -r["impressions"])[:15]
    print("\nJust below the first page (position 8-20), most impressions:")
    for r in near:
        print(f"  {r['impressions']:5.0f}  pos {r['position']:4.1f}  {kind(r['query'], abbrs):9} {r['query']}")

    names = [words(x["name"]) for x in acts]
    gaps = [r for r in qs if kind(r["query"], abbrs) == "topic"
            and not any(len(words(r["query"]) & n) >= max(1, min(2, len(words(r["query"])))) for n in names)]
    print("\nQueries matching no act's name (scope candidates; read them, the match is by word stems):")
    for r in sorted(gaps, key=lambda r: -r["impressions"])[:20]:
        print(f"  {r['impressions']:5.0f}  pos {r['position']:5.1f}  {r['query']}")

    bad = [s for s in sitemaps if int(s.get("errors", 0)) or int(s.get("warnings", 0))]
    print(f"\nSitemaps: {len(sitemaps)}" + "".join(f"\n  {s['path']}: {s.get('errors')} errors, {s.get('warnings')} warnings"
                                                    for s in bad))


if __name__ == "__main__":
    main()
