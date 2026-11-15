#!/usr/bin/env python3
"""Tell search engines (Bing, Yandex, Seznam, Naver, … via api.indexnow.org) which pages changed, after a deploy.

Usage: python3 bin/indexnow.py [out/site] [--all] [--dry-run]

Reads the deployed site's sitemap.xml and submits the URLs whose lastmod is the build's day (status.json "day"), or
every URL with --all (the first submission). The key is public by design: the site serves it as /<key>.txt (written
by the build, ltlaw.render.INDEXNOW_KEY) and IndexNow checks it there. Standard library only; a failure is printed,
never fatal (the deploy has already happened). At most 10,000 URLs a request.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://api.indexnow.org/indexnow"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", nargs="?", type=pathlib.Path, default=pathlib.Path("out/site"))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live", metavar="URL", help="read sitemap.xml and status.json from the public site; --key KEY")
    ap.add_argument("--key", help="with --live: the key (the site serves /<key>.txt)")
    a = ap.parse_args()
    if a.live:  # e.g. a first full submission once the key is verified: no local build needed
        import tempfile
        d = pathlib.Path(tempfile.mkdtemp())
        for f in ("sitemap.xml", "status.json", f"{a.key}.txt"):
            req = urllib.request.Request(a.live.rstrip("/") + "/" + f, headers={"User-Agent": "atviri-teises-aktai-indexnow/1.0"})
            (d / f).write_bytes(urllib.request.urlopen(req, timeout=60).read())
        a.site = d
    keys = [p for p in a.site.glob("*.txt") if re.fullmatch(r"[0-9a-f]{32}", p.stem) and p.read_text().strip() == p.stem]
    if not keys:
        print("indexnow: no key file in the site; nothing sent")
        return
    key = keys[0].stem
    xml = (a.site / "sitemap.xml").read_text()
    for part in re.findall(r"<sitemap><loc>[^<]*/(sitemap-\d+\.xml)</loc>", xml):  # an index (over 45,000 URLs): its parts
        if a.live:
            req = urllib.request.Request(a.live.rstrip("/") + "/" + part, headers={"User-Agent": "atviri-teises-aktai-indexnow/1.0"})
            (a.site / part).write_bytes(urllib.request.urlopen(req, timeout=60).read())
        xml += (a.site / part).read_text()
    xml = re.sub(r"<sitemap>.*?</sitemap>", "", xml)
    entries = re.findall(r"<loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?", xml)
    st = a.site / "status.json"  # the nightly's; a local build has none: the sitemap's newest day
    day = json.loads(st.read_text()).get("day", "") if st.exists() else max((lm for _, lm in entries), default="")
    urls = [u for u, lm in entries if a.all or lm == day]
    if not urls:
        print(f"indexnow: no page changed on {day}")
        return
    host = re.match(r"https?://([^/]+)", urls[0]).group(1)
    print(f"indexnow: {len(urls)} URLs ({'all' if a.all else 'changed on ' + day}) for {host}")
    if a.dry_run:
        return
    for k in range(0, len(urls), 10000):
        body = json.dumps({"host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt",
                           "urlList": urls[k:k + 10000]}).encode()
        req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json; charset=utf-8",
                                                                   "User-Agent": "atviri-teises-aktai-indexnow/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(f"  {k}–{k + len(urls[k:k + 10000])}: HTTP {r.status}")
        except urllib.error.HTTPError as e:  # 202 accepted, 200 ok; 403 key not valid yet, 422 URLs not of this host
            print(f"  {k}: HTTP {e.code} {e.read()[:200]!r}", file=sys.stderr)
        except Exception as e:
            print(f"  {k}: {type(e).__name__}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
