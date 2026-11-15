#!/usr/bin/env python3
"""Short act aliases (/dk/52/ → /ta/<TAR>/str/52/) as Cloudflare Bulk Redirects, not Pages `_redirects`.

Pages allows only 100 dynamic `_redirects` rules (one per act); Bulk Redirects on the Free plan allow 10,000
entries account-wide, and one entry per act covers every article (subpath matching + preserve path suffix).
Nothing runs per request: no Worker, no cost, static traffic stays free.

Usage:
  uv run bin/nightly.py --no-fetch          # first: a local build writes out/site/index.json (the aliases)
  uv run bin/cf_redirects.py                # show what the list would contain and what changes
  uv run bin/cf_redirects.py --apply        # write the list and the account redirect rule
  uv run bin/cf_redirects.py --check        # from outside: does /dk/52/ land on the article?

Run it whenever an act is added or an alias changes (docs/ROADMAP.md, "The procedure for every new act").
Token: as bin/cf_staging.py, plus Account Filter Lists Edit and Account Rulesets Edit (Mass URL Redirects).
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cf_staging import DOMAIN, cf, ids, ok  # noqa: E402

LIST = "lt_law_aliases"
RULE = "lt-law: act aliases (/dk/52/ → article)"


def wanted(index: pathlib.Path) -> list[dict]:
    """One redirect per act: https://DOMAIN/<alias>/… → https://DOMAIN/ta/<TAR>/<str|p>/…"""
    acts = json.loads(index.read_text())["acts"]
    out = []
    for a in acts:
        alias = urlparse(a["alias"]).path          # "/dk/"
        base = urlparse(a["url"]).path             # "/ta/2016-23709/"
        seg = "p" if a.get("unit") == "punktas" else "str"
        for src in [alias] + [f"/{x}/" for x in a.get("short", [])]:  # "/dk/"; a name people use, "/gdpr/" (scope/names.yaml)
            out.append({"redirect": {"source_url": f"{DOMAIN}{src}", "target_url": f"https://{DOMAIN}{base}{seg}/",
                                     "status_code": 301, "include_subdomains": True, "subpath_matching": True,
                                     "preserve_path_suffix": True, "preserve_query_string": False}})
    # www served the whole site again under a second name (2026-10-25): every page to the same path on the domain
    out.append({"redirect": {"source_url": f"www.{DOMAIN}/", "target_url": f"https://{DOMAIN}/", "status_code": 301,
                             "subpath_matching": True, "preserve_path_suffix": True, "preserve_query_string": True}})
    return sorted(out, key=lambda x: x["redirect"]["source_url"])


def current(acc: str) -> tuple[dict | None, list[dict]]:
    lists = ok(cf("GET", f"/accounts/{acc}/rules/lists"), "lists (needs Account Filter Lists)")
    lst = next((l for l in lists if l["name"] == LIST), None)
    if not lst:
        return None, []
    items, cursor = [], None
    while True:
        r = cf("GET", f"/accounts/{acc}/rules/lists/{lst['id']}/items" + (f"?cursor={cursor}" if cursor else ""))
        items += ok(r, "list items")
        cursor = ((r.get("result_info") or {}).get("cursors") or {}).get("after")
        if not cursor:
            return lst, items


def key(item: dict) -> tuple:
    r = item["redirect"]
    return (r["source_url"], r["target_url"], r.get("status_code", 301), bool(r.get("subpath_matching")),
            bool(r.get("preserve_path_suffix", True)), bool(r.get("include_subdomains")))


def apply(acc: str, want: list[dict]) -> None:
    lst, _ = current(acc)
    if not lst:
        lst = ok(cf("POST", f"/accounts/{acc}/rules/lists",
                    {"name": LIST, "kind": "redirect", "description": "lt-law short act aliases (bin/cf_redirects.py)"}),
                 "create list")
        print("created list", LIST)
    op = ok(cf("PUT", f"/accounts/{acc}/rules/lists/{lst['id']}/items", want), "replace items")
    for _ in range(30):  # the list update is asynchronous
        st = ok(cf("GET", f"/accounts/{acc}/rules/lists/bulk_operations/{op['operation_id']}"), "operation")
        if st["status"] in ("completed", "failed"):
            break
        time.sleep(2)
    if st["status"] != "completed":
        sys.exit(f"list update: {st}")
    print(f"list {LIST}: {len(want)} redirects")
    # the account's redirect phase: keep anyone else's rules, add or update ours
    r = cf("GET", f"/accounts/{acc}/rulesets/phases/http_request_redirect/entrypoint")
    rules = [x for x in ((r.get("result") or {}).get("rules") or []) if x.get("description") != RULE] if r.get("success") else []
    rules.append({"description": RULE, "enabled": True, "action": "redirect",
                  "expression": f"http.request.full_uri in ${LIST}",
                  "action_parameters": {"from_list": {"name": LIST, "key": "http.request.full_uri"}}})
    keep = [{k: x[k] for k in ("description", "enabled", "action", "expression", "action_parameters") if k in x} for x in rules]
    ok(cf("PUT", f"/accounts/{acc}/rulesets/phases/http_request_redirect/entrypoint", {"rules": keep}),
       "redirect rule (needs Account Rulesets / Mass URL Redirects)")
    print("rule on:", RULE)


def check(want: list[dict]) -> None:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    bad = 0
    for item in want[:3] + want[-2:]:
        src = "https://" + quote(item["redirect"]["source_url"]) + "1/"   # a few aliases keep „“ and – from the name
        exp = item["redirect"]["target_url"] + "1/"
        try:
            urllib.request.build_opener(NoRedirect).open(urllib.request.Request(src, headers={"User-Agent": "lt-law check"}), timeout=30)
            loc, code = "", 200
        except urllib.error.HTTPError as e:
            loc, code = e.headers.get("Location", ""), e.code
        good = code in (301, 308) and loc == exp
        bad += not good
        print(f"{'OK ' if good else 'BAD'} {src} -> {code} {loc}")
    sys.exit(1 if bad else 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=pathlib.Path, default=pathlib.Path("out/site/index.json"))
    ap.add_argument("--apply", action="store_true", help="write the list and the rule")
    ap.add_argument("--check", action="store_true", help="test a few aliases from outside")
    a = ap.parse_args()
    want = wanted(a.index)
    if a.check:
        return check(want)
    acc, _ = ids()
    lst, have = current(acc)
    add = {key(x) for x in want} - {key(x) for x in have}
    drop = {key(x) for x in have} - {key(x) for x in want}
    print(f"aliases in the site: {len(want)}; in Cloudflare: {len(have)}; to add/change {len(add)}, to remove {len(drop)}")
    for k in sorted(add)[:5]:
        print("  +", k[0], "->", k[1])
    for k in sorted(drop)[:5]:
        print("  -", k[0], "->", k[1])
    if a.apply:
        apply(acc, want)
    elif add or drop:
        print("dry run: add --apply to write")


if __name__ == "__main__":
    main()
