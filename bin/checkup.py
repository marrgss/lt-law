#!/usr/bin/env python3
"""A checkup of the public site from outside: availability, integrity, security probes, freshness, label sanity.

Usage: uv run bin/checkup.py [--base https://atviri-teises-aktai.lt] [--quiet]

Writes one line per check and a summary to private/checkups/<day>.log (gitignored) and keeps the previous totals in
private/checkups/state.json. Exit code 2 if a CRITICAL finding: the site is altered (a foreign script or frame, the
unofficial-text notice gone), a probe's script comes back unescaped in our HTML, a secret is visible in a public file,
or the labels collapse (far fewer "current" than at the last checkup). Downtime or slowness is WARN: taking the site
down would not help. What to do on CRITICAL: OPERATIONS.md "Taking the site down" (the login gate back on).
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "private" / "checkups"
UA = "Mozilla/5.0 (compatible; atviri-teises-aktai-checkup/1.0)"
PROBE = "<script>alert(7731)</script>"
SECRETS = re.compile(r"cfat_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY"
                     r"|CLOUDFLARE_[A-Z_]*TOKEN\s*[=:]|R2_SECRET|ACCESS_CLIENT_SECRET\s*[=:]|CF-Access-Client-Secret")
ALLOWED_SCRIPT = re.compile(r'<script(?: src="(?:https://atviri-teises-aktai\.lt)?/app\.js" defer| type="application/ld\+json"'
                            r'| data-cfasync="false" src="/cdn-cgi/scripts/[0-9a-f]+/cloudflare-static/email-decode\.min\.js")>')
# (the last: Cloudflare's own e-mail obfuscation of the contact address, served from the zone's /cdn-cgi/ path)


def _h(headers) -> dict:
    """Header names in their usual capitalisation, whatever case the server sent ("content-security-policy")."""
    return {"-".join(w.capitalize() for w in k.split("-")): v for k, v in dict(headers).items()}


def get(url: str, ua: str = UA, data: bytes | None = None, ctype: str | None = None, timeout: int = 20):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": ua, **({"Content-Type": ctype} if ctype else {}),
                                                          "Accept": "application/json, text/html, */*"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), _h(r.headers), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), _h(e.headers or {}), time.time() - t
    except Exception as e:  # network
        return 0, f"{type(e).__name__}: {e}", {}, time.time() - t


def usage() -> list[tuple[str, str, str]]:
    """The last 24 hours from Cloudflare's own aggregate statistics (no visitor tracking): site requests, page views,
    threats, 5xx, countries; Worker requests against the free plan's 100,000 a day. Token: the local one in
    ~/.config/lt-law/.env (Zone Analytics Read + Account Analytics Read), never printed."""
    env = pathlib.Path.home() / ".config" / "lt-law" / ".env"
    tok = next((l.split("=", 1)[1].strip().strip('"') for l in env.read_text().splitlines() if l.startswith("CLOUDFLARE_API_TOKEN=")), "") \
        if env.exists() else ""
    if not tok:
        return [("INFO", "usage", "no local Cloudflare token")]

    def cf(path=None, q=None):
        req = urllib.request.Request("https://api.cloudflare.com/client/v4/" + (path or "graphql"),
                                     data=json.dumps({"query": q}).encode() if q else None,
                                     headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            return json.loads(e.read() or b"{}")
    try:
        z = cf("zones?name=atviri-teises-aktai.lt")["result"][0]
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:00:00Z")
        r = cf(q='{ viewer { zones(filter:{zoneTag:"%s"}) { httpRequests1hGroups(limit:25, filter:{datetime_geq:"%s"}) { sum { requests '
                 'pageViews threats responseStatusMap { edgeResponseStatus requests } countryMap { clientCountryName requests } } '
                 'uniq { uniques } } } } }' % (z["id"], since))
        out = []
        if r.get("errors"):
            out.append(("INFO", "usage", "site statistics not readable: " + r["errors"][0]["message"][:80]))
        else:
            gs = r["data"]["viewer"]["zones"][0]["httpRequests1hGroups"]
            req, pv, thr = (sum(g["sum"][k] for g in gs) for k in ("requests", "pageViews", "threats"))
            st, cc = {}, {}
            for g in gs:
                for x in g["sum"]["responseStatusMap"]:
                    st[x["edgeResponseStatus"]] = st.get(x["edgeResponseStatus"], 0) + x["requests"]
                for x in g["sum"]["countryMap"]:
                    cc[x["clientCountryName"]] = cc.get(x["clientCountryName"], 0) + x["requests"]
            e5 = sum(v for k, v in st.items() if k >= 500)
            top = ", ".join(f"{k} {v}" for k, v in sorted(cc.items(), key=lambda kv: -kv[1])[:5])
            out.append(("WARN" if e5 > 100 else "INFO", "usage 24 h",
                        f"{req} requests, {pv} page views, {max((g['uniq']['uniques'] for g in gs), default=0)} max visitors/h, "
                        f"{thr} threats, 5xx {e5}, 404 {st.get(404, 0)}, 403 {st.get(403, 0)}; {top} (incl. ~45/h of these checkups)"))
        out += readers(cf, z["id"])
        day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        r = cf(q='{ viewer { accounts(filter:{accountTag:"%s"}) { workersInvocationsAdaptive(limit:20, filter:{datetime_geq:"%s"}) '
                 '{ sum { requests errors } dimensions { scriptName } } } } }' % (z["account"]["id"], day))
        if r.get("errors"):
            out.append(("INFO", "workers", "not readable: " + r["errors"][0]["message"][:80]))
        else:
            ws = {g["dimensions"]["scriptName"]: g["sum"] for g in r["data"]["viewer"]["accounts"][0]["workersInvocationsAdaptive"]}
            total = sum(v["requests"] for v in ws.values())
            out.append(("WARN" if total > 70000 else "INFO", "workers today (UTC)",
                        f"{total} of 100,000 free; " + ", ".join(f"{k} {v['requests']} ({v['errors']} errors)" for k, v in ws.items())))
        return out
    except Exception as e:
        return [("INFO", "usage", f"not read: {type(e).__name__}")]


# who reads the site, by user agent (ROADMAP go/no-go: assistants fetching pages for people, and the search engines'
# crawlers that feed them: ChatGPT reads Bing's and OAI-SearchBot's index, Gemini Google's, Claude its own)
READERS = ["ChatGPT-User", "Claude-User", "Perplexity-User", "OAI-SearchBot", "Claude-SearchBot", "PerplexityBot",
           "bingbot", "Googlebot", "GPTBot", "ClaudeBot"]
READERS_LOG = ROOT / "private" / "usage" / "readers.csv"


def readers(cf, zone: str) -> list[tuple[str, str, str]]:
    """Yesterday's requests (UTC, a whole day) per assistant and crawler, and POSTs to /mcp, from Cloudflare's sampled
    counts. Each day is kept in private/usage/readers.csv (Cloudflare keeps about a month; days missing from the file
    are filled in, so the trend outlives that)."""
    cols = READERS + ["mcp_post"]
    have = {}
    if READERS_LOG.exists():
        have = {l.split(",")[0]: l.strip().split(",")[1:] for l in READERS_LOG.read_text().splitlines()[1:] if l.strip()}
    today = dt.datetime.now(dt.timezone.utc).date()
    for back in range(30, 0, -1):
        d = (today - dt.timedelta(days=back)).isoformat()
        if d in have:
            continue
        parts = [f'a{i}: httpRequestsAdaptiveGroups(limit:1, filter:{{date:"{d}", userAgent_like:"%{b}%"}}) {{ count }}'
                 for i, b in enumerate(READERS)]
        parts.append(f'a{len(READERS)}: httpRequestsAdaptiveGroups(limit:1, filter:{{date:"{d}", clientRequestPath:"/mcp", '
                     'clientRequestHTTPMethodName:"POST"}) { count }')
        r = cf(q='{ viewer { zones(filter:{zoneTag:"%s"}) { %s } } }' % (zone, " ".join(parts)))
        if r.get("errors"):
            if back == 1:
                return [("INFO", "readers", "not readable: " + r["errors"][0]["message"][:80])]
            continue  # older than Cloudflare keeps
        g = r["data"]["viewer"]["zones"][0]
        have[d] = [str(g[f"a{i}"][0]["count"] if g[f"a{i}"] else 0) for i in range(len(cols))]
    READERS_LOG.parent.mkdir(parents=True, exist_ok=True)
    READERS_LOG.write_text("date," + ",".join(cols) + "\n" + "".join(f"{d},{','.join(v)}\n" for d, v in sorted(have.items())))
    y = (today - dt.timedelta(days=1)).isoformat()
    if y not in have:
        return [("INFO", "readers", "yesterday not read")]
    row = dict(zip(cols, map(int, have[y])))
    week = [dict(zip(cols, map(int, v))) for d, v in sorted(have.items())[-8:-1]]
    people = ("ChatGPT-User", "Claude-User", "Perplexity-User")
    mean = round(sum(sum(w.get(k, 0) for k in people) for w in week) / len(week)) if week else 0
    return [("INFO", f"readers {y} (UTC)",
             "for people: " + ", ".join(f"{k} {row[k]}" for k in people) + f" (the 7 days before: {mean} a day); crawlers: "
             + ", ".join(f"{k} {row[k]}" for k in READERS if k not in people) + f"; MCP calls {row['mcp_post']} (monitors included)")]


FREE_MINUTES = 2000  # GitHub Free, private repositories, Linux runners (billed per job, rounded up to the minute)


def github_billing() -> tuple[str, str, str] | None:
    """GitHub's own billing summary for the month (token GITHUB_READ_TOKEN in ~/.config/lt-law/.env: fine-grained, read
    only, account Plan + this repository's Actions/Contents/Variables/Administration; never printed). None without it.
    WARN when anything is charged or the free minutes are three-quarters used (budget: Actions $5, stop at the limit)."""
    tok = _read_token()
    if not tok:
        return None
    req = urllib.request.Request("https://api.github.com/users/marrgss/settings/billing/usage/summary",
                                 headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "lt-law-checkup"})
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.load(r).get("usageItems") or []
    minutes = sum(i.get("grossQuantity", 0) for i in items if i.get("sku") == "actions_linux")
    gross = sum(i.get("grossAmount", 0) for i in items)
    net = sum(i.get("netAmount", 0) for i in items)
    today = dt.date.today()
    day = today.day
    pace = int(minutes * calendar.monthrange(today.year, today.month)[1] / max(day, 1))
    lvl = "WARN" if net > 0 or minutes > FREE_MINUTES * 3 // 4 or pace > FREE_MINUTES else "INFO"
    return (lvl, "github billing", f"{minutes:.0f} of {FREE_MINUTES} free minutes (pace ~{pace}); usage ${gross:.2f}, charged ${net:.2f}")


def _read_token() -> str:
    env = pathlib.Path.home() / ".config" / "lt-law" / ".env"
    return next((l.split("=", 1)[1].strip().strip('"') for l in env.read_text().splitlines() if l.startswith("GITHUB_READ_TOKEN=")), "") \
        if env.exists() else ""


def dependabot() -> tuple[str, str, str] | None:
    """Open Dependabot alerts (enabled 2026-10-27): WARN for any, CRITICAL for a critical one."""
    tok = _read_token()
    if not tok:
        return None
    req = urllib.request.Request("https://api.github.com/repos/marrgss/atviri-teises-aktai/dependabot/alerts?state=open&per_page=100",
                                 headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "lt-law-checkup"})
    with urllib.request.urlopen(req, timeout=30) as r:
        alerts = json.load(r)
    sev = [a["security_advisory"]["severity"] for a in alerts]
    lvl = "CRITICAL" if "critical" in sev else "WARN" if sev else "OK"
    return (lvl, "dependabot", f"{len(sev)} open alerts" + (f": {', '.join(f'{a['dependency']['package']['name']} ({a['security_advisory']['severity']})' for a in alerts[:5])}" if sev else ""))


def actions_minutes() -> tuple[str, str, str]:
    """This month's billable minutes, summed from the runs' jobs (the run history needs only Actions read; GitHub's
    own billing report needs a token with the account's Plan permission). WARN from 75% of the free minutes."""
    month = dt.date.today().replace(day=1).isoformat()
    gh = lambda path, q: [json.loads(l) for l in subprocess.run(["gh", "api", "--paginate", path, "-q", q], cwd=ROOT, capture_output=True,
                                                                  text=True, timeout=300, check=True).stdout.splitlines() if l]
    repo = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=ROOT,
                          capture_output=True, text=True, timeout=60, check=True).stdout.strip()
    runs = gh(f"/repos/{repo}/actions/runs?created=>={month}&per_page=100", ".workflow_runs[] | {id} | @json")
    total = 0
    for r in runs:
        for j in gh(f"/repos/{repo}/actions/runs/{r['id']}/jobs?per_page=100", ".jobs[] | {started_at, completed_at} | @json"):
                if j.get("started_at") and j.get("completed_at"):
                    secs = (dt.datetime.fromisoformat(j["completed_at"].replace("Z", "+00:00"))
                            - dt.datetime.fromisoformat(j["started_at"].replace("Z", "+00:00"))).total_seconds()
                    total += max(1, -(-int(secs) // 60))
    day, days = dt.date.today().day, 31
    pace = total * days // max(day, 1)
    return ("WARN" if total > FREE_MINUTES * 3 // 4 or pace > FREE_MINUTES else "INFO", "actions minutes",
            f"{total} of {FREE_MINUTES} free this month ({len(runs)} runs; at this pace ~{pace})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="https://atviri-teises-aktai.lt")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    B = a.base.rstrip("/")
    res: list[tuple[str, str, str]] = []  # (level, check, detail)
    add = lambda lvl, chk, det="": res.append((lvl, chk, det))  # noqa: E731

    # 1. availability and latency
    for path in ["/", "/ta/2016-23709/str/52/", "/ta/1001010ISTAIII-1864/str/1.1/", "/dk/52/", "/llms.txt", "/sitemap.xml", "/status.json", "/api/v1/acts.json",
                 "/api/search?q=nuotolinis+darbas", "/api/article?act=DK&n=52",
                 "/kaip-buvo/?u=%2Fta%2F2016-23709%2Fstr%2F52%2F&data=2021-05-01"]:
        st, body, h, s = get(B + path)
        lvl = "OK" if st == 200 and s < 5 else "WARN"
        add(lvl, f"GET {path}", f"{st} {s:.2f}s {len(body)}B")
    mcp = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
    st, body, _, s = get(B + "/mcp", data=mcp, ctype="application/json")
    ntools = len(json.loads(body)["result"]["tools"]) if st == 200 else 0
    add("OK" if st == 200 and ntools == 8 else "WARN", "MCP tools/list", f"{st} {ntools} tools {s:.2f}s")
    st, _, _, _ = get(B + "/llms.txt", ua="Python-urllib/3.12")  # Cloudflare Pages' own rule refuses it (OPERATIONS)
    add("OK" if st == 200 else "INFO", "Python-urllib on a static file", f"{st} (known: Pages refuses this User-Agent)")
    st, _, _, _ = get(B + "/mcp", ua="Python-urllib/3.12", data=mcp, ctype="application/json")
    add("OK" if st == 200 else "WARN", "Python-urllib on /mcp", str(st))

    # 2. integrity: our own pages, only our scripts, the notice in place
    for path in ["/", "/ta/2016-23709/str/52/", "/apie/"]:
        st, body, _, _ = get(B + path)
        if st != 200:
            continue
        scripts = re.findall(r"<script[^>]*>", body)
        foreign = [x for x in scripts if not ALLOWED_SCRIPT.fullmatch(x)]
        frames = re.findall(r"<(?:iframe|object|embed)\b[^>]*>", body, re.I)
        notice = "Neoficialus tekstas" in body
        if foreign or frames or not notice:
            add("CRITICAL", f"integrity {path}", f"foreign scripts {foreign[:3]}, frames {frames[:2]}, notice {notice}")
        else:
            add("OK", f"integrity {path}", f"{len(scripts)} scripts, notice present")
        if 'content="noindex"' in body:
            add("WARN", f"noindex on {path}", "the site is meant to be indexable (D-031)")

    # 3. security probes: what we echo back must be escaped
    q = urllib.parse.quote(PROBE)
    for path in [f"/kaip-buvo/?u={q}", f"/kaip-buvo/?u=%2Fta%2F2016-23709%2Fstr%2F52%2F&data={q}", f"/api/search?q={q}",
                 f"/api/article?act={q}&n=1", f"/paieska/?q={q}"]:
        st, body, h, _ = get(B + path)
        raw = PROBE in body and "json" not in (h.get("Content-Type") or "")
        add("CRITICAL" if raw else "OK", f"probe {path[:40]}", f"{st}, {'REFLECTED UNESCAPED' if raw else 'not reflected raw'}")
    big = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": "search_law", "arguments": {"query": "a " * 20000}}}).encode()
    st, _, _, s = get(B + "/mcp", data=big, ctype="application/json")
    add("OK" if st in (200, 400, 413) else "WARN", "MCP oversized query", f"{st} {s:.2f}s")
    st, body, _, _ = get(B + "/api/article?act=..%2F..%2Fapi%2Fv1%2Fmeta&n=1")
    # an unknown act is a 404 with an error (REST answers carry their status), never another file's content
    add("OK" if st in (200, 400, 404) and '"error"' in body and '"status_day"' not in body else "WARN", "act path traversal", f"{st} {body[:80]}")

    # scanners' favourite paths must be a real 404, not the home page with 200 (Pages without a 404.html)
    for path in ["/.env", "/.git/config", "/wp-login.php"]:
        st, body, _, _ = get(B + path)
        hit = SECRETS.search(body)
        add("CRITICAL" if hit else "OK" if st == 404 else "WARN", f"scanner path {path}", f"{st}{' SECRET' if hit else ''}")
    st, _, h, _ = get(B + "/")
    add("OK" if "frame-ancestors" in (h.get("Content-Security-Policy") or "") and "max-age=0" not in (h.get("Strict-Transport-Security") or "max-age=0")
        else "WARN", "security headers", f"CSP {h.get('Content-Security-Policy')!r}, HSTS {h.get('Strict-Transport-Security')!r}")

    # 4. secrets in public files
    for path in ["/status.json", "/index.json", "/llms.txt", "/api/v1/meta.json", "/api/v1/acts.json", "/app.js",
                 "/api/v1/dated.html", "/ta/2016-23709/data.json"]:
        st, body, _, _ = get(B + path, timeout=40)
        hit = SECRETS.search(body) if st == 200 else None
        add("CRITICAL" if hit else "OK", f"secrets {path}", f"{st} {'FOUND ' + hit.group(0)[:12] + '…' if hit else 'none'}")

    # 5. freshness and the nightly
    st, body, _, _ = get(B + "/status.json")
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).date()  # Vilnius (summer); a day either way is fine
    try:
        s_ = json.loads(body)
        age = (today - dt.date.fromisoformat(s_["day"])).days
        add("OK" if age <= 2 else "WARN", "status day", f"{s_['day']} ({age} d), data checked {s_.get('data_checked')}, "
            f"newest publication {s_.get('register_newest_publication')}, warnings {len(s_.get('warnings') or [])}, problems {len(s_.get('problems') or [])}")
    except Exception as e:
        add("WARN", "status.json", f"unreadable: {e}")
    try:
        r = subprocess.run(["gh", "run", "list", "--workflow", "nightly.yml", "--limit", "1", "--json", "conclusion,status,createdAt,event"],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        last = json.loads(r.stdout)[0]
        add("OK" if last.get("conclusion") in ("success", None, "") or last.get("status") != "completed" else "WARN", "last nightly run",
            f"{last['createdAt'][:16]} {last['event']} {last['status']} {last.get('conclusion')}")
    except Exception as e:
        add("WARN", "last nightly run", f"not read: {e}")
    try:  # GitHub this month: billing (read-only token), else minutes counted from the runs; the free plan has 2,000
        add(*(github_billing() or actions_minutes()))
    except Exception as e:
        add("INFO", "github usage", f"not read: {e}")
    try:  # known vulnerabilities in the dependencies (wrangler and its npm tree, the uv lockfile)
        if (r := dependabot()) is not None:
            add(*r)
    except Exception as e:
        add("INFO", "dependabot", f"not read: {e}")

    # 6. label sanity against the last checkup
    st, body, _, _ = get(B + "/api/v1/acts.json", timeout=40)
    OUT.mkdir(parents=True, exist_ok=True)
    state_p = OUT / "state.json"
    prev = json.loads(state_p.read_text()) if state_p.exists() else {}
    try:
        acts = json.loads(body)["acts"]
        tot = {"acts": len(acts), "articles": sum(x["n"] for x in acts),
               "current": sum((x.get("counts") or {}).get("current", 0) for x in acts)}
        if prev.get("current"):
            drop = 1 - tot["current"] / prev["current"]
            lvl = "CRITICAL" if drop > 0.30 else "WARN" if drop > 0.10 or tot["acts"] < prev["acts"] else "OK"
            add(lvl, "labels vs last checkup", f"{tot} (was {prev.get('acts')} acts, {prev.get('current')} current)")
        else:
            add("OK", "labels", f"{tot} (first checkup)")
        state_p.write_text(json.dumps(dict(tot, at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))))
    except Exception as e:
        add("WARN", "labels", f"acts.json unreadable: {e}")

    for lvl, chk, det in usage():
        add(lvl, chk, det)
    if (pathlib.Path.home() / ".config" / "lt-law" / "search-console.json").exists():  # Google search, last 7 days (read only)
        r = subprocess.run(["uv", "run", "-q", "bin/search_console.py", "--brief", "--days", "7"], cwd=ROOT,
                           capture_output=True, text=True, timeout=180)
        add("INFO" if r.returncode == 0 else "WARN", "google search", (r.stdout or r.stderr).strip()[-200:])
    crit = [r for r in res if r[0] == "CRITICAL"]
    warn = [r for r in res if r[0] == "WARN"]
    stamp = dt.datetime.now().astimezone().isoformat(timespec="minutes")
    lines = [f"{stamp} {lvl:8s} {chk}: {det}" for lvl, chk, det in res]
    summary = f"{stamp} SUMMARY {len(crit)} critical, {len(warn)} warn, {len(res)} checks"
    with (OUT / f"{dt.date.today().isoformat()}.log").open("a") as f:
        f.write("\n".join(lines + [summary, ""]) + "\n")
    for l in lines:
        if not a.quiet or not l.split()[1].startswith("OK"):
            print(l)
    print(summary)
    raise SystemExit(2 if crit else 0)


if __name__ == "__main__":
    main()
