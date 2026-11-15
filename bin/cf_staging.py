#!/usr/bin/env python3
"""Private staging on Cloudflare (docs/OPERATIONS.md "Private staging"): every step idempotent.

Usage:
  uv run bin/cf_staging.py status
  uv run bin/cf_staging.py access --email you@example.com   # Pages project + login gate (one-time PIN, that email only)
  uv run bin/cf_staging.py domain                           # parking A records out, the domain on the Pages project
  uv run bin/cf_staging.py check                            # from outside: a stranger must see the login, not the site
  uv run bin/cf_staging.py release                          # at release: remove the login gate

Token: CLOUDFLARE_API_TOKEN from the environment or ~/.config/lt-law/.env (never printed). Needs Pages Write,
Access Apps/Policies and Organizations/Identity Providers Write, and Zone DNS Write on the domain (`domain` only).
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

DOMAIN = "atviri-teises-aktai.lt"
PROJECT = "atviri-teises-aktai"
APP = "atviri-teises-aktai staging"
ACME = "atviri-teises-aktai certificate validation"  # Pages renews certificates over HTTP: never behind the login
# (the same bypass app also opens /status.json for the nightly job's skip check)
HOSTS = [DOMAIN, f"www.{DOMAIN}", f"{PROJECT}.pages.dev", f"*.{PROJECT}.pages.dev"]


def token() -> str:
    t = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    env = pathlib.Path.home() / ".config/lt-law/.env"
    if not t and env.exists():
        t = next((l.split("=", 1)[1] for l in env.read_text().splitlines() if l.startswith("CLOUDFLARE_API_TOKEN=")), "")
    if not t.strip():
        sys.exit("no CLOUDFLARE_API_TOKEN (environment or ~/.config/lt-law/.env)")
    return t.strip()


def cf(method: str, path: str, body=None) -> dict:
    """One API call; a 5xx from Cloudflare (their incidents) is retried a few times with back-off."""
    import time
    for wait in (5, 15, 45, 0):
        r = _cf(method, path, body)
        if r.get("http", 200) < 500 or not wait or method == "POST":  # a timed-out create may have happened
            return r
        time.sleep(wait)
    return r


def _cf(method: str, path: str, body=None) -> dict:
    req = urllib.request.Request("https://api.cloudflare.com/client/v4" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw) | {"http": e.code}
        except ValueError:
            return {"success": False, "errors": [{"message": raw[:200].decode(errors="replace")}], "http": e.code}


def ok(r: dict, what: str):
    if not r.get("success"):
        sys.exit(f"{what}: {r.get('errors')}")
    return r.get("result")


def ids() -> tuple[str, str]:
    z = ok(cf("GET", f"/zones?name={DOMAIN}"), "zone")
    if not z:
        sys.exit(f"{DOMAIN} is not in this account")
    return z[0]["account"]["id"], z[0]["id"]


def status() -> None:
    acc, zid = ids()
    p = cf("GET", f"/accounts/{acc}/pages/projects/{PROJECT}")
    doms = [d["name"] for d in (cf("GET", f"/accounts/{acc}/pages/projects/{PROJECT}/domains").get("result") or [])] \
        if p.get("success") else []
    print("pages project:", "yes" if p.get("success") else "no", doms)
    org = cf("GET", f"/accounts/{acc}/access/organizations")
    print("zero trust:", (org.get("result") or {}).get("auth_domain") if org.get("success") else org.get("errors"))
    apps = [a for a in (cf("GET", f"/accounts/{acc}/access/apps").get("result") or []) if a.get("name") == APP]
    print("access app:", [(a["name"], a.get("self_hosted_domains")) for a in apps] or "none")
    d = cf("GET", f"/zones/{zid}/dns_records")
    print("dns:", [(r["type"], r["name"], r["content"]) for r in d["result"]] if d.get("success") else d.get("errors"))


def access(email: str) -> None:
    acc, _ = ids()
    if not cf("GET", f"/accounts/{acc}/pages/projects/{PROJECT}").get("success"):
        ok(cf("POST", f"/accounts/{acc}/pages/projects", {"name": PROJECT, "production_branch": "main"}), "create project")
        print("created Pages project", PROJECT, "(empty: nothing deployed)")
    all_apps0 = ok(cf("GET", f"/accounts/{acc}/access/apps"), "apps")
    existing = next((a for a in all_apps0 if a.get("name") == APP), None)
    r = cf("GET", f"/accounts/{acc}/access/identity_providers")
    if r.get("success"):
        otp = next((i for i in r["result"] if i["type"] == "onetimepin"), None)
    elif existing and existing.get("allowed_idps"):  # the token may lack that permission once set up: reuse
        otp = {"id": existing["allowed_idps"][0]}
    else:
        sys.exit(f"login methods: {r.get('errors')}")
    if not otp and existing and existing.get("allowed_idps"):
        otp = {"id": existing["allowed_idps"][0]}  # not listed to this token: the gate's own login method
    if not otp:
        otp = ok(cf("POST", f"/accounts/{acc}/access/identity_providers",
                    {"type": "onetimepin", "name": "One-time PIN", "config": {}}), "one-time PIN")
        print("added login method: one-time PIN")
    body = {"name": APP, "type": "self_hosted", "domain": HOSTS[0], "self_hosted_domains": HOSTS,
            "allowed_idps": [otp["id"]], "auto_redirect_to_identity": True, "session_duration": "720h",
            "app_launcher_visible": False,
            "policies": [{"name": "maintainer only", "decision": "allow", "include": [{"email": {"email": email}}],
                          "precedence": 1}]}
    all_apps = ok(cf("GET", f"/accounts/{acc}/access/apps"), "apps")
    acme = next((a for a in all_apps if a.get("name") == ACME), None)
    if acme and f"{DOMAIN}/status.json" not in (acme.get("self_hosted_domains") or []):
        ok(cf("DELETE", f"/accounts/{acc}/access/apps/{acme['id']}"), "replace bypass")  # recreated below with the new path
        all_apps = [a for a in all_apps if a is not acme]
        print("replacing the bypass app to add /status.json")
    if not any(a.get("name") == ACME for a in all_apps):
        # also /status.json: the nightly job's "already deployed today?" check reads it (no secrets in it)
        paths = [f"{h}/.well-known/acme-challenge/*" for h in (DOMAIN, f"www.{DOMAIN}")] + [f"{DOMAIN}/status.json"]
        ok(cf("POST", f"/accounts/{acc}/access/apps",
              {"name": ACME, "type": "self_hosted", "domain": paths[0], "self_hosted_domains": paths, "app_launcher_visible": False,
               "policies": [{"name": "certificate validation", "decision": "bypass", "include": [{"everyone": {}}],
                             "precedence": 1}]}), "create bypass")
        print("created bypass for", ", ".join(paths))
    apps = [a for a in all_apps if a.get("name") == APP]
    if apps:
        ok(cf("PUT", f"/accounts/{acc}/access/apps/{apps[0]['id']}", body), "update app")
        print("updated access app:", ", ".join(HOSTS))
    else:
        ok(cf("POST", f"/accounts/{acc}/access/apps", body), "create app")
        print("created access app:", ", ".join(HOSTS))


def domain() -> None:
    acc, zid = ids()
    recs = ok(cf("GET", f"/zones/{zid}/dns_records"), "dns (needs Zone DNS Write on the domain)")
    for r in recs:  # the registrar's parking page (imported when the domain was added): blocks the Pages domain
        if r["type"] in ("A", "AAAA") and r["name"] in (DOMAIN, f"www.{DOMAIN}", f"*.{DOMAIN}"):
            ok(cf("DELETE", f"/zones/{zid}/dns_records/{r['id']}"), f"delete {r['name']}")
            print("deleted", r["type"], r["name"], r["content"])
    have = {d["name"] for d in ok(cf("GET", f"/accounts/{acc}/pages/projects/{PROJECT}/domains"), "domains")}
    for host in (DOMAIN, f"www.{DOMAIN}"):
        if host not in have:
            ok(cf("POST", f"/accounts/{acc}/pages/projects/{PROJECT}/domains", {"name": host}), f"add {host}")
            print("added custom domain", host)
    names = {r["name"] for r in ok(cf("GET", f"/zones/{zid}/dns_records"), "dns") if r["type"] in ("A", "AAAA", "CNAME")}
    for host in (DOMAIN, f"www.{DOMAIN}"):
        if host not in names:
            ok(cf("POST", f"/zones/{zid}/dns_records", {"type": "CNAME", "name": host, "content": f"{PROJECT}.pages.dev",
                                                        "proxied": True}), f"CNAME {host}")
            print("added CNAME", host, "->", f"{PROJECT}.pages.dev")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def check() -> None:
    bad = 0
    for host in (DOMAIN, f"www.{DOMAIN}", f"{PROJECT}.pages.dev"):
        req = urllib.request.Request(f"https://{host}/", headers={"User-Agent": "lt-law staging check"})
        try:
            r = urllib.request.build_opener(_NoRedirect).open(req, timeout=30)
            code, loc = r.status, ""
        except urllib.error.HTTPError as e:
            code, loc = e.code, e.headers.get("Location", "")
        except Exception as e:  # noqa: BLE001
            code, loc = None, str(e)[:80]
        gated = code in (302, 303) and "cloudflareaccess.com" in loc
        bad += not gated
        print(f"{'OK  ' if gated else 'OPEN'} {host}: {code} {loc[:70]}")
    sys.exit(1 if bad else 0)


def release() -> None:
    acc, _ = ids()
    for a in ok(cf("GET", f"/accounts/{acc}/access/apps"), "apps"):
        if a.get("name") in (APP, ACME):
            ok(cf("DELETE", f"/accounts/{acc}/access/apps/{a['id']}"), "delete app")
            print("removed the login gate; now set INDEXABLE=true and run nightly")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["status", "access", "domain", "check", "release"])
    ap.add_argument("--email", help="the one address allowed in (access)")
    a = ap.parse_args()
    if a.step == "access" and not a.email:
        sys.exit("access needs --email")
    {"status": status, "access": lambda: access(a.email), "domain": domain, "check": check, "release": release}[a.step]()


if __name__ == "__main__":
    main()
