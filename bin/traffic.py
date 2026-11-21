#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["cryptography>=44"]
# ///
"""Who reads and who gathers the site: one page from Cloudflare, Google Search Console and Bing, aggregate numbers only.

Usage: uv run bin/traffic.py [--days 30] [--no-google] [--open]

Writes private/usage/traffic.html (open it in a browser) and keeps every finished day in private/usage/traffic.json, so
the history outlives Cloudflare's month. Running it again fills in the missing days and refreshes the last two.

Sources (all read only, nothing about single visitors is kept):
  * Cloudflare GraphQL (the local token in ~/.config/lt-law/.env): requests per user agent and day, sorted into who
    makes them (assistants fetching for a person, search engines, AI crawlers, SEO crawlers, other bots, browser-like,
    scripts), the /mcp endpoint's callers, browser visits (requests for /app.js, which only a browser running the page
    asks for), and our own traffic: our checks' user agents and this machine's public address (looked up at each run
    and used only as a filter; other visitors' addresses are never read).
  * Google Search Console (bin/search_console.py's read-only service account): clicks and impressions per day,
    the sitemaps' submitted and indexed counts, the top queries and pages of the last 28 days, and Google's verdict
    on the key pages (URL Inspection).
  * Bing Webmaster Tools, if BING_WEBMASTER_API_KEY is in the .env (Bing Webmaster > Settings > API access): clicks
    and impressions per day and crawl statistics. Bing's index also feeds ChatGPT search.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
OUT = ROOT / "private" / "usage"
STORE, PAGE = OUT / "traffic.json", OUT / "traffic.html"
ENV = pathlib.Path.home() / ".config" / "lt-law" / ".env"
ZONE_NAME = "atviri-teises-aktai.lt"
BASE = "https://" + ZONE_NAME
KEY_PAGES = {"Konstitucija": "/ta/0921010KONSRG922324/", "Darbo kodeksas": "/ta/2016-23709/",
             "Civilinis kodeksas": "/ta/1001010ISTAIII-1864/", "ANK": "/ta/2015-11216/",
             "CPK": "/ta/1021010KODE00IX-743/", "Baudžiamasis kodeksas": "/ta/1001010ISTAIII-1968/",
             "Elektros energetikos įstatymas": "/ta/1001010ISTAIII-1881/", "Pradžia": "/"}

# --- who is asking: user agent -> (group, family) -------------------------------------------------------------------
GROUPS = {  # key: (label, what it means); the order is the page's order and the colour order
    "assistants": ("AI assistants for a person", "ChatGPT, Claude, Perplexity… fetching a page because someone asked a question"),
    "search": ("Search engines", "crawlers that build search indexes: Google, Bing (feeds ChatGPT search), Yandex, OpenAI/Claude/Perplexity search"),
    "ai": ("AI crawlers", "collect pages to train models or build AI datasets; nobody is reading at that moment"),
    "mcp": ("MCP endpoint", "calls to /mcp: AI apps using the site as a tool, and registries/monitors checking that it works"),
    "seo": ("SEO crawlers", "backlink and ranking services (Semrush, Ahrefs, Majestic…); no value to readers"),
    "other_bots": ("Other bots", "self-declared bots not in the lists above"),
    "browserlike": ("Browser-like", "browser user agents: real people's page and file loads, plus bots pretending to be browsers"),
    "scripts": ("Scripts and unknown", "curl, Python, Node, empty user agent"),
    "ours": ("Ours", "this project's own checks and this machine"),
}
FAMILIES = [  # (group, family, regex); first match wins
    ("ours", "our checks", r"^lt-law|^atviri-teises-aktai[-/]|atviri-teises-aktai-checkup"),
    ("internal", "Cloudflare early hints", r"early hints$"),
    ("assistants", "ChatGPT", r"ChatGPT-User"), ("assistants", "Claude", r"Claude-User"),
    ("assistants", "Perplexity", r"Perplexity-User"), ("assistants", "Mistral", r"MistralAI-User"),
    ("assistants", "DuckDuckGo assist", r"DuckAssistBot"), ("assistants", "Meta AI", r"meta-externalfetcher"),
    ("assistants", "Exa (on request)", r"ExaUser"), ("assistants", "Google (on request)", r"Google-Read-Aloud|GoogleAgent|Google-NotebookLM"),
    ("search", "Google", r"Googlebot|Google-InspectionTool|GoogleOther|Storebot-Google|AdsBot-Google"),
    ("search", "Bing", r"bingbot|BingPreview|msnbot"), ("search", "OpenAI search", r"OAI-SearchBot"),
    ("search", "Claude search", r"Claude-SearchBot"), ("search", "Perplexity", r"PerplexityBot"),
    ("search", "Yandex", r"YandexBot|YandexMobileBot|YandexRenderResourcesBot"), ("search", "Apple", r"Applebot"),
    ("search", "DuckDuckGo", r"DuckDuckBot"), ("search", "Brave", r"Bravebot"), ("search", "Exa", r"ExaSearchBot|Exabot"),
    ("search", "Seznam", r"SeznamBot"), ("search", "Baidu", r"Baiduspider"), ("search", "Qwant", r"Qwantbot"),
    ("search", "Petal (Huawei)", r"PetalBot"), ("search", "Epochal", r"Epochal-Search"),
    ("search", "Meta AI search", r"Meta-WebIndexer"), ("search", "Kimi search", r"Kimi-SearchBot"), ("search", "Mojeek", r"MojeekBot"),
    ("ai", "GPTBot (OpenAI training)", r"GPTBot"), ("ai", "ClaudeBot (Anthropic training)", r"ClaudeBot|anthropic-ai"),
    ("ai", "Common Crawl", r"CCBot"), ("ai", "ByteDance", r"Bytespider|TikTokSpider"), ("ai", "Meta", r"meta-externalagent|FacebookBot"),
    ("ai", "Amazon", r"Amazonbot"), ("ai", "Reflection AI", r"Reflectionbot"), ("ai", "River AI", r"RiverBot"),
    ("ai", "ElevenLabs", r"ElevenlabsCrawler"), ("ai", "Shap", r"ShapBot"), ("ai", "Diffbot", r"Diffbot"),
    ("ai", "AI2", r"AI2Bot"), ("ai", "Cohere", r"cohere-"), ("ai", "Timpi", r"Timpibot"), ("ai", "ImageSift", r"ImagesiftBot"),
    ("ai", "Huawei Pangu", r"PanguBot"), ("ai", "You.com", r"YouBot"), ("ai", "Google-CloudVertexBot", r"CloudVertexBot"),
    ("ai", "Mistral", r"MistralAI(?!-User)"), ("ai", "Kangaroo", r"Kangaroo Bot"), ("ai", "Omgili", r"omgili"),
    ("ai", "Chinese AI labs", r"ChatGLM-Spider|Hunyuan|Qwenbot|DeepSeekBot|KimiBot|MoonshotBot|Baichuan|Doubao"),
    ("ai", "xAI (Grok)", r"GrokBot|xAI-"),
    ("seo", "Semrush", r"SemrushBot|SiteAuditBot"), ("seo", "Ahrefs", r"AhrefsBot|AhrefsSiteAudit"), ("seo", "Majestic", r"MJ12bot"),
    ("seo", "Moz", r"DotBot|rogerbot"), ("seo", "SE Ranking", r"SERanking"), ("seo", "DataForSEO", r"DataForSeoBot"),
    ("seo", "BLEXBot", r"BLEXBot"), ("seo", "Barkrowler", r"Barkrowler"), ("seo", "Serpstat", r"serpstatbot"),
    ("seo", "Sistrix", r"SISTRIX"), ("seo", "Screaming Frog", r"Screaming Frog"),
    ("scripts", "curl", r"^curl/"), ("scripts", "Python", r"python|aiohttp|httpx|Python-urllib"), ("scripts", "Node", r"^node$|axios|undici|node-fetch"),
    ("scripts", "Go", r"Go-http-client"), ("scripts", "Java", r"^Java/|okhttp|Apache-HttpClient"), ("scripts", "wget", r"^Wget"),
    ("scripts", "empty", r"^$|^Mozilla/5\.0$|^-$"),
    ("other_bots", None, r"bot\b|bot/|crawl|spider|probe|scan|check|monitor|fetch|index|research|survey|harvest|https?://|@"),
    ("browserlike", "browser", r"^Mozilla/|^Opera/|WhatsApp|Viber|Telegram|Slack|Discord"),
]
_FAM = [(g, f, re.compile(rx, re.I)) for g, f, rx in FAMILIES]
# who calls /mcp
MCP_CLIENT = re.compile(r"Claude-User|claude-code|Claude-Desktop|openai-mcp|ChatGPT|Cursor|cline|Windsurf|copilot|vscode|"
                        r"Zed|LibreChat|n8n|coda-agent|Talaria|mcp-remote|MCP Inspector|langchain|llama", re.I)
MCP_MONITOR = re.compile(r"bot|probe|check|monitor|index|crawl|scan|research|survey|harvest|liveness|registry|watch|"
                         r"prober|scout|https?://|@", re.I)


def family(ua: str) -> tuple[str, str]:
    for g, f, rx in _FAM:
        if rx.search(ua):
            if f is None:  # another self-declared bot: name it by the word that says so
                m = (re.match(r"(?!Mozilla)([\w.-]+)", ua) or re.search(r"compatible; ([\w.-]+)", ua) or re.search(r"([\w.-]*(?:bot|crawl|spider|probe|index|scan)[\w.-]*)", ua, re.I)
                     or re.match(r"([\w.-]+)", ua))
                f = m.group(1)[:40] if m else "?"
            return g, f
    return "scripts", "other"


def mcp_kind(ua: str) -> str:
    if re.search(r"^lt-law|^atviri-teises-aktai[-/]", ua):
        return "ours"
    if MCP_CLIENT.search(ua):
        return "AI apps"
    if MCP_MONITOR.search(ua):
        return "registries and monitors"
    return "libraries and unknown"


# --- Cloudflare -----------------------------------------------------------------------------------------------------
def env(name: str) -> str:
    if not ENV.exists():
        return ""
    return next((l.split("=", 1)[1].strip().strip('"') for l in ENV.read_text().splitlines() if l.startswith(name + "=")), "")


def cf_client():
    tok = env("CLOUDFLARE_API_TOKEN")
    if not tok:
        sys.exit(f"no CLOUDFLARE_API_TOKEN in {ENV}")

    def cf(path: str | None = None, q: str | None = None) -> dict:
        req = urllib.request.Request("https://api.cloudflare.com/client/v4/" + (path or "graphql"),
                                     data=json.dumps({"query": q}).encode() if q else None,
                                     headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            return json.loads(e.read() or b"{}")
    return cf


def own_ips() -> list[str]:
    """This machine's public addresses now (IPv4 and, if any, IPv6), plus the ones seen at earlier runs."""
    ips = set()
    for url in ("https://1.1.1.1/cdn-cgi/trace", "https://[2606:4700:4700::1111]/cdn-cgi/trace"):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                m = re.search(r"^ip=(\S+)", r.read().decode(), re.M)
                if m:
                    ips.add(m.group(1))
        except Exception:
            pass
    return sorted(ips)


def cf_day(cf, zone: str, day: str, ips: list[str]) -> dict | None:
    """One UTC day: requests per user agent (sorted into groups), /mcp callers, browser visits, ours."""
    ip_q = " ".join(f'own{i}: httpRequestsAdaptiveGroups(limit:500, filter:{{date:"{day}", clientIP:"{ip}"}}) '
                    f'{{ count dimensions {{ userAgent }} }}' for i, ip in enumerate(ips))
    not_own = "".join(f', clientIP_neq:"{ip}"' for ip in ips[:1]) + (  # browser visits leave this machine out
        ', AND:[' + ",".join(f'{{clientIP_neq:"{ip}"}}' for ip in ips[1:]) + ']' if len(ips) > 1 else "")
    q = ('{ viewer { zones(filter:{zoneTag:"%s"}) { '
         'ua: httpRequestsAdaptiveGroups(limit:9000, filter:{date:"%s"}) { count dimensions { userAgent } } '
         'mcp: httpRequestsAdaptiveGroups(limit:2000, filter:{date:"%s", clientRequestPath:"/mcp"}) { count dimensions { userAgent } } '
         'js: httpRequestsAdaptiveGroups(limit:3000, filter:{date:"%s", clientRequestPath:"/app.js"%s}) { count dimensions { userAgent clientCountryName } } '
         'api: httpRequestsAdaptiveGroups(limit:1, filter:{date:"%s", clientRequestPath_like:"/api/%%"}) { count } '
         'tot: httpRequests1dGroups(limit:1, filter:{date:"%s"}) { sum { requests pageViews threats bytes cachedRequests '
         'responseStatusMap { edgeResponseStatus requests } } uniq { uniques } } %s } } }'
         % (zone, day, day, day, not_own, day, day, ip_q))
    r = cf(q=q)
    if r.get("errors") or not r.get("data"):
        return None
    z = r["data"]["viewer"]["zones"][0]
    mcp_by_ua = {g["dimensions"]["userAgent"]: g["count"] for g in z["mcp"]}
    groups, fams = {k: 0 for k in GROUPS}, {}
    for g in z["ua"]:
        ua, n = g["dimensions"]["userAgent"], g["count"]
        n -= mcp_by_ua.get(ua, 0)  # a user agent's /mcp calls count under the MCP endpoint
        grp, fam = family(ua)
        if grp == "internal" or n <= 0:
            continue
        groups[grp] += n
        if grp != "browserlike":
            fams[f"{grp}|{fam}"] = fams.get(f"{grp}|{fam}", 0) + n
    mcp, callers = {}, {}
    for ua, n in mcp_by_ua.items():
        k = mcp_kind(ua)
        if k == "ours":
            groups["ours"] += n
            continue
        mcp[k] = mcp.get(k, 0) + n
        name = family(ua)[1] if k != "AI apps" else re.split(r"[/ ;(]", ua.replace("Mozilla/5.0 ", ""))[0]
        name = name if name not in ("other", "browser", "empty") else (ua[:40] or "(no user agent)")
        callers[f"{k}|{name}"] = callers.get(f"{k}|{name}", 0) + n
    groups["mcp"] = sum(mcp.values())
    visits, countries = 0, {}
    for g in z["js"]:
        ua = g["dimensions"]["userAgent"]
        if family(ua)[0] != "browserlike":
            continue
        visits += g["count"]
        c = g["dimensions"]["clientCountryName"] or "?"
        countries[c] = countries.get(c, 0) + g["count"]
    own_ip = 0  # this machine: whatever user agent it sent, it counts as ours
    for i in range(len(ips)):
        for g in z.get(f"own{i}") or []:
            grp, fam = family(g["dimensions"]["userAgent"])
            if grp == "internal":
                continue
            own_ip += g["count"]
            if grp in ("ours", "mcp"):
                continue
            groups[grp] -= g["count"]
            groups["ours"] += g["count"]
            if f"{grp}|{fam}" in fams:
                fams[f"{grp}|{fam}"] -= g["count"]
    t = z["tot"][0] if z["tot"] else None
    st = {}
    if t:
        for x in t["sum"]["responseStatusMap"]:
            st[x["edgeResponseStatus"]] = st.get(x["edgeResponseStatus"], 0) + x["requests"]
    return {"groups": groups, "families": fams, "mcp": mcp, "mcp_callers": callers, "browser_visits": visits,
            "visit_countries": countries, "own_ip": own_ip, "api": z["api"][0]["count"] if z["api"] else 0,
            "requests": t["sum"]["requests"] if t else sum(groups.values()), "page_views": t["sum"]["pageViews"] if t else 0,
            "uniques": t["uniq"]["uniques"] if t else 0, "threats": t["sum"]["threats"] if t else 0,
            "bytes": t["sum"]["bytes"] if t else 0, "cached": t["sum"]["cachedRequests"] if t else 0,
            "s4xx": sum(v for k, v in st.items() if 400 <= k < 500), "s5xx": sum(v for k, v in st.items() if k >= 500)}


def workers(cf, account: str, start: str) -> dict:
    r = cf(q='{ viewer { accounts(filter:{accountTag:"%s"}) { workersInvocationsAdaptive(limit:500, filter:{date_geq:"%s"}) '
             '{ sum { requests errors } dimensions { date scriptName } } } } }' % (account, start))
    out = {}
    if r.get("data"):
        for g in r["data"]["viewer"]["accounts"][0]["workersInvocationsAdaptive"]:
            d = out.setdefault(g["dimensions"]["date"], {"requests": 0, "errors": 0})
            d["requests"] += g["sum"]["requests"]
            d["errors"] += g["sum"]["errors"]
    return out


# --- Google ---------------------------------------------------------------------------------------------------------
def google(days: int) -> dict:
    import search_console as sc
    if not sc.KEY.exists():
        return {"error": "no Search Console key"}
    tok = sc.token()
    site = urllib.parse.quote(sc.SITE, safe="")
    end = dt.date.today()
    out = {"daily": {r["date"]: {"clicks": r["clicks"], "impressions": r["impressions"], "position": r["position"]}
                     for r in sc.rows(tok, sc.SITE, end - dt.timedelta(days=max(days, 120)), end, ["date"])}}
    start28 = end - dt.timedelta(days=28)
    out["queries"] = sorted(sc.rows(tok, sc.SITE, start28, end, ["query"]), key=lambda r: -r["impressions"])[:15]
    out["pages"] = sorted(sc.rows(tok, sc.SITE, start28, end, ["page"]), key=lambda r: -r["impressions"])[:10]
    out["sitemaps"] = []
    for s in sc.api(tok, f"sites/{site}/sitemaps").get("sitemap", []):
        c = (s.get("contents") or [{}])[0]
        out["sitemaps"].append({"path": s["path"].replace(BASE, ""), "read": s.get("lastDownloaded", "")[:16].replace("T", " "),
                                "submitted": int(c.get("submitted", 0)), "indexed": int(c.get("indexed", 0)),
                                "errors": int(s.get("errors", 0)), "warnings": int(s.get("warnings", 0))})
    out["pages_checked"] = []
    for name, path in KEY_PAGES.items():
        req = urllib.request.Request("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                                     data=json.dumps({"inspectionUrl": BASE + path, "siteUrl": sc.SITE}).encode(),
                                     headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                ir = json.load(r)["inspectionResult"]["indexStatusResult"]
            out["pages_checked"].append({"name": name, "path": path, "verdict": ir.get("verdict", ""),
                                         "state": ir.get("coverageState", ""), "crawled": ir.get("lastCrawlTime", "")[:10]})
        except Exception as e:
            out["pages_checked"].append({"name": name, "path": path, "verdict": "?", "state": type(e).__name__, "crawled": ""})
    return out


# --- Bing -----------------------------------------------------------------------------------------------------------
def bing() -> dict:
    key = env("BING_WEBMASTER_API_KEY")
    if not key:
        return {"error": "not connected"}

    def call(method: str) -> list:
        url = (f"https://ssl.bing.com/webmaster/api.svc/json/{method}?"
               + urllib.parse.urlencode({"siteUrl": BASE + "/", "apikey": key}))
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "lt-law-traffic"}), timeout=60) as r:
            return json.load(r).get("d") or []

    def day(v: str) -> str:  # "/Date(1731715200000-0800)/"
        ms = int(re.search(r"\d+", v).group())
        return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat()
    try:
        traffic = {day(x["Date"]): {"clicks": x.get("Clicks", 0), "impressions": x.get("Impressions", 0)}
                   for x in call("GetRankAndTrafficStats")}
        crawl = [{"date": day(x["Date"]), "crawled": x.get("CrawledPages", 0), "in_index": x.get("InIndex", 0),
                  "errors": x.get("CrawlErrors", 0) + x.get("Code4xx", 0) + x.get("Code5xx", 0)} for x in call("GetCrawlStats")]
        return {"daily": traffic, "crawl": sorted(crawl, key=lambda x: x["date"])}
    except Exception as e:  # the key is in the URL: never print the exception's text
        return {"error": f"not readable ({type(e).__name__})"}


# --- the page -------------------------------------------------------------------------------------------------------
def fmt(n: float) -> str:
    n = round(n)
    return f"{n:,}".replace(",", " ")


def bars(days: list[str], values: list[float], slot: int, height: int = 70, unit: str = "") -> str:
    """A small daily bar chart (SVG, one series), hover shows the day and the value."""
    w, gap = 12, 2
    top = max(values + [1])
    out = [f'<svg class="bars" viewBox="0 0 {len(days) * (w + gap)} {height + 14}" preserveAspectRatio="none" role="img">']
    for i, (d, v) in enumerate(zip(days, values)):
        h = max(0 if not v else 2, v / top * height)
        x = i * (w + gap)
        out.append(f'<rect class="hit" x="{x}" y="0" width="{w + gap}" height="{height}" data-tip="{d}: {fmt(v)}{unit}"/>'
                   f'<path class="s{slot}" d="M{x},{height} v{-h + 3:.1f} q0,-3 3,-3 h{w - 6} q3,0 3,3 v{h - 3:.1f} z" '
                   f'pointer-events="none"/>')
    out.append(f'<line class="base" x1="0" x2="{len(days) * (w + gap)}" y1="{height}" y2="{height}"/>'
               f'<text x="0" y="{height + 12}">{days[0][5:]}</text>'
               f'<text x="{len(days) * (w + gap)}" y="{height + 12}" text-anchor="end">{days[-1][5:]}</text></svg>')
    return "".join(out)


def week_sum(store: dict, days: list[str], fn) -> tuple[float, float]:
    last, prev = days[-7:], days[-14:-7]
    return sum(fn(store[d]) for d in last), sum(fn(store[d]) for d in prev)


def change(a: float, b: float) -> str:
    if not b:
        return "new" if a else "–"
    p = (a - b) / b * 100
    text = f"×{a / b:.0f}" if p >= 400 else f"{'+' if p > 0 else ''}{p:.0f}%"
    return f'<span class="{"up" if p > 0 else "down"}">{text}</span>'


def render(store: dict, g: dict, b: dict, ws: dict, ips_note: str) -> str:
    days = sorted(store)
    n = len(days)
    e = html.escape
    tot7 = sum(store[d]["requests"] for d in days[-7:])
    gs7 = {k: sum(store[d]["groups"][k] for d in days[-7:]) for k in GROUPS}
    lt_v = lambda r: r["visit_countries"].get("LT", 0)
    people = gs7["assistants"] + sum(lt_v(store[d]) for d in days[-7:])
    gather = gs7["search"] + gs7["ai"] + gs7["seo"]

    # what the numbers say (computed, so the page reads the same way every time)
    notes = []
    a7, a_prev = week_sum(store, days, lambda r: r["groups"]["assistants"])
    v7, v_prev = week_sum(store, days, lt_v)
    o7v = sum(store[d]["browser_visits"] - lt_v(store[d]) for d in days[-7:])
    notes.append(f"<b>People</b> reached the site about <b>{fmt(people / 7)} times a day</b> this week: "
                 f"{fmt(a7 / 7)} page fetches by AI assistants answering someone ({change(a7, a_prev)} on the week before) and "
                 f"{fmt(v7 / 7)} browser visits from Lithuania ({change(v7, v_prev)}). That is {people / max(tot7, 1) * 100:.1f}% of all requests.")
    notes.append(f"Browser visits from other countries ({fmt(o7v / 7)}/day) jump on single days (mostly US data centres): "
                 f"that is crawlers running a real browser, so they are left out of the people count. Browser-like requests "
                 f"({fmt(gs7['browserlike'] / 7)}/day) are far more than any visits: mostly bots dressed as browsers.")
    top_gather = sorted(((f.split("|")[1], sum(store[d]["families"].get(f, 0) for d in days[-7:]))
                         for f in {f for d in days[-7:] for f in store[d]["families"]} if f.split("|")[0] in ("search", "ai", "seo")),
                        key=lambda x: -x[1])[:4]
    notes.append(f"<b>Gathering</b>: crawlers made {gather / max(tot7, 1) * 100:.0f}% of the requests ({fmt(gather / 7)}/day). "
                 f"Search engines {fmt(gs7['search'] / 7)}/day, AI crawlers {fmt(gs7['ai'] / 7)}/day, SEO crawlers {fmt(gs7['seo'] / 7)}/day. "
                 f"Biggest this week: " + ", ".join(f"{e(f)} {fmt(v / 7)}/day" for f, v in top_gather) + ".")
    m7 = {k: sum(store[d]["mcp"].get(k, 0) for d in days[-7:]) for k in ("AI apps", "registries and monitors", "libraries and unknown")}
    mt = sum(m7.values())
    if mt:
        notes.append(f"<b>MCP</b>: {fmt(mt / 7)} calls a day. <b>{m7['registries and monitors'] / mt * 100:.0f}%</b> are registries and "
                     f"uptime monitors checking the endpoint (not use), {m7['AI apps'] / mt * 100:.0f}% come from AI apps (Claude, ChatGPT and others; "
                     f"these can include our own tests from claude.ai or ChatGPT, which the numbers cannot tell apart), "
                     f"{m7['libraries and unknown'] / mt * 100:.0f}% from bare libraries (node, python) that do not say who they are. "
                     f"Our own scripts and this machine are counted separately, not here.")
    o7 = sum(store[d]["groups"]["ours"] for d in days[-7:])
    notes.append(f"<b>Ours</b>: about {fmt(o7 / 7)} requests a day ({o7 / max(tot7, 1) * 100:.1f}% of all) from our checks and "
                 f"this machine, so they hardly move the totals. {ips_note}")
    if g.get("daily"):
        gd = sorted(g["daily"])
        i7 = sum(g["daily"][d]["impressions"] for d in gd[-7:])
        c7 = sum(g["daily"][d]["clicks"] for d in gd[-7:])
        idx = sum(s["indexed"] for s in g.get("sitemaps", []))
        sub = sum(s["submitted"] for s in g.get("sitemaps", []))
        ok = sum(1 for p in g.get("pages_checked", []) if p["verdict"] == "PASS")
        notes.append(f"<b>Google</b>: {fmt(i7)} impressions and {fmt(c7)} clicks in the last 7 days of data; "
                     f"{ok} of {len(g.get('pages_checked', []))} key pages are indexed; sitemaps: {fmt(sub)} pages submitted, "
                     f"{fmt(idx)} reported indexed. Google still sends almost no one; people come through AI assistants.")

    css = """
:root{color-scheme:light;--bg:#fcfcfb;--card:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--ink3:#8a8984;--line:#e6e5e0;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948;--s9:#8a8984;--up:#006300;--down:#b42318}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--bg:#1a1a19;--card:#232321;--ink:#f0efec;--ink2:#c3c2b7;
--ink3:#8f8e86;--line:#383835;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;--s9:#8f8e86;--up:#5fc35f;--down:#f08a7e}}
:root[data-theme=dark]{color-scheme:dark;--bg:#1a1a19;--card:#232321;--ink:#f0efec;--ink2:#c3c2b7;--ink3:#8f8e86;--line:#383835;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;--s9:#8f8e86;--up:#5fc35f;--down:#f08a7e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 10px}
.sub{color:var(--ink2);margin:0 0 20px}.notes{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px}
.notes p{margin:6px 0}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card h3{font-size:14px;margin:0;display:flex;gap:8px;align-items:center}.dot{width:10px;height:10px;border-radius:3px;flex:none}
.card .what{color:var(--ink3);font-size:12px;margin:2px 0 6px;min-height:34px}.big{font-size:22px;font-weight:600}
.big small{font-size:13px;color:var(--ink2);font-weight:400}.bars{width:100%;height:84px;display:block;margin-top:6px}
.bars text{font-size:9px;fill:var(--ink3)}.bars .base{stroke:var(--line)}.bars .hit{fill:transparent}.bars .hit:hover{fill:var(--line)}
.s1{fill:var(--s1)}.s2{fill:var(--s2)}.s3{fill:var(--s3)}.s4{fill:var(--s4)}.s5{fill:var(--s5)}.s6{fill:var(--s6)}.s7{fill:var(--s7)}.s8{fill:var(--s8)}.s9{fill:var(--s9)}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:4px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--ink2);font-weight:500}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.up{color:var(--up)}.down{color:var(--down)}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:760px){.two{grid-template-columns:1fr}}.tbl{overflow-x:auto}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);font-size:12px;padding:3px 7px;border-radius:5px;display:none;z-index:9}
footer{color:var(--ink3);font-size:12px;margin-top:40px}code{font-size:12px}"""
    p = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>Site traffic</title><style>{css}</style></head><body><main>",
         f"<h1>Who reads and who gathers {ZONE_NAME}</h1>",
         f"<p class=sub>Daily, UTC, {days[0]} – {days[-1]} ({n} days; today is not finished and is not shown). "
         f"Updated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC by <code>uv run bin/traffic.py</code>.</p>",
         "<div class=notes>" + "".join(f"<p>{x}</p>" for x in notes) + "</div>"]

    # people
    p.append("<h2>People</h2><div class=grid>")
    for title, what, fn, slot in [
            ("AI assistants for a person", GROUPS["assistants"][1], lambda r: r["groups"]["assistants"], 1),
            ("Browser visits from Lithuania", "requests for the site's script (/app.js), which only a browser asks for, about once "
             "per visit; this machine left out", lt_v, 2),
            ("Browser visits, other countries", "the same elsewhere: some people, plus crawlers that run a real browser (the spikes)",
             lambda r: r["browser_visits"] - lt_v(r), 9),
            ("Google search: clicks", "people who clicked the site in Google results", None, 3)]:
        if fn is None:
            if not g.get("daily"):
                continue
            gd = [d for d in days if d in g["daily"]] or sorted(g["daily"])[-n:]
            vals = [g["daily"].get(d, {}).get("clicks", 0) for d in days]
            v7, vp = sum(vals[-7:]), sum(vals[-14:-7])
        else:
            vals = [fn(store[d]) for d in days]
            v7, vp = sum(vals[-7:]), sum(vals[-14:-7])
        p.append(f"<div class=card><h3><span class='dot s{slot}' style='background:var(--s{slot})'></span>{e(title)}</h3>"
                 f"<div class=what>{e(what)}</div><div class=big>{fmt(v7 / 7)} <small>a day, last 7 days ({change(v7, vp)})</small></div>"
                 f"{bars(days, vals, slot)}</div>")
    p.append("</div>")

    # everyone, by group
    p.append("<h2>All requests by who makes them</h2><div class=grid>")
    for i, (k, (label, what)) in enumerate(GROUPS.items()):
        slot = i + 1 if i < 8 else 9
        vals = [store[d]["groups"][k] for d in days]
        v7, vp = sum(vals[-7:]), sum(vals[-14:-7])
        p.append(f"<div class=card><h3><span class=dot style='background:var(--s{slot})'></span>{e(label)}</h3><div class=what>{e(what)}</div>"
                 f"<div class=big>{fmt(v7 / 7)} <small>a day ({v7 / max(tot7, 1) * 100:.1f}%) {change(v7, vp)}</small></div>"
                 f"{bars(days, vals, slot)}</div>")
    p.append("</div><p class=sub style='margin-top:8px'>Each chart has its own scale. All requests together: "
             f"{fmt(tot7 / 7)} a day this week (Cloudflare counts every file: pages, the script, icons, data). "
             "Counts per user agent are Cloudflare's sampled estimates.</p>")

    # families table
    fams = {f for d in days for f in store[d]["families"]}
    rows = []
    for f in fams:
        grp, name = f.split("|", 1)
        if grp == "ours":
            continue
        a, bprev = (sum(store[d]["families"].get(f, 0) for d in ds) for ds in (days[-7:], days[-14:-7]))
        allv = sum(store[d]["families"].get(f, 0) for d in days)
        rows.append((grp, name, a, bprev, allv))
    rows.sort(key=lambda r: -r[2])
    p.append("<h2>Who exactly (named agents)</h2><div class=tbl><table><tr><th>Agent</th><th>Kind</th><th class=n>Last 7 days</th>"
             f"<th class=n>Change</th><th class=n>All {n} days</th></tr>")
    for grp, name, a, bp, allv in rows[:40]:
        if a or allv > 50:
            p.append(f"<tr><td>{e(name)}</td><td>{e(GROUPS[grp][0])}</td><td class=n>{fmt(a)}</td><td class=n>{change(a, bp)}</td>"
                     f"<td class=n>{fmt(allv)}</td></tr>")
    p.append("</table></div>")

    # MCP
    callers = {}
    for d in days[-7:]:
        for k, v in store[d]["mcp_callers"].items():
            callers[k] = callers.get(k, 0) + v
    p.append("<h2>MCP endpoint: who calls it</h2><div class=two><div class=card>")
    for j, k in enumerate(("AI apps", "registries and monitors", "libraries and unknown")):
        vals = [store[d]["mcp"].get(k, 0) for d in days]
        p.append(f"<h3><span class=dot style='background:var(--s{j + 1})'></span>{k}: {fmt(sum(vals[-7:]) / 7)} a day</h3>{bars(days, vals, j + 1, 40)}")
    p.append("</div><div class='card tbl'><table><tr><th>Caller, last 7 days</th><th>Kind</th><th class=n>Calls</th></tr>")
    for k, v in sorted(callers.items(), key=lambda kv: -kv[1])[:25]:
        kind, name = k.split("|", 1)
        p.append(f"<tr><td>{e(name)}</td><td>{e(kind)}</td><td class=n>{fmt(v)}</td></tr>")
    p.append("</table></div></div>")

    # Google
    p.append("<h2>Google Search</h2>")
    if g.get("error"):
        p.append(f"<p class=sub>{e(g['error'])}</p>")
    elif g.get("daily"):
        gd = sorted(g["daily"])
        p.append("<div class=two><div class=card>")
        for label, k, slot in (("Impressions", "impressions", 1), ("Clicks", "clicks", 3)):
            vals = [g["daily"][d][k] for d in gd]
            p.append(f"<h3>{label}: {fmt(sum(vals[-7:]))} in the last 7 days of data</h3>{bars(gd, vals, slot, 50)}")
        p.append("<p class=sub>Google's newest 2–3 days are still growing.</p></div><div class='card tbl'><table>"
                 "<tr><th>Key page</th><th>Google says</th><th>Crawled</th></tr>")
        for x in g.get("pages_checked", []):
            p.append(f"<tr><td><a href='{BASE}{e(x['path'])}'>{e(x['name'])}</a></td><td>{'✓ ' if x['verdict'] == 'PASS' else ''}"
                     f"{e(x['state'])}</td><td>{e(x['crawled'])}</td></tr>")
        p.append("</table><table style='margin-top:10px'><tr><th>Sitemap</th><th>Read</th><th class=n>Submitted</th><th class=n>Indexed</th></tr>")
        for s in g.get("sitemaps", []):
            p.append(f"<tr><td>{e(s['path'])}</td><td>{e(s['read'])}</td><td class=n>{fmt(s['submitted'])}</td><td class=n>{fmt(s['indexed'])}</td></tr>")
        p.append("</table></div></div><div class=two style='margin-top:12px'>")
        for title, rows_, key in (("Queries, last 28 days", g.get("queries", []), "query"), ("Pages, last 28 days", g.get("pages", []), "page")):
            p.append(f"<div class='card tbl'><table><tr><th>{title}</th><th class=n>Impr.</th><th class=n>Clicks</th><th class=n>Pos.</th></tr>")
            for r in rows_:
                p.append(f"<tr><td>{e(r[key].replace(BASE, ''))}</td><td class=n>{fmt(r['impressions'])}</td><td class=n>{fmt(r['clicks'])}</td>"
                         f"<td class=n>{r['position']:.1f}</td></tr>")
            p.append("</table></div>")
        p.append("</div>")

    # Bing
    p.append("<h2>Bing</h2>")
    if b.get("error"):
        p.append(f"<p class=sub>Bing Webmaster Tools: {e(b['error'])}. To connect: Bing Webmaster Tools → Settings → API access → "
                 f"generate an API key, then add <code>BING_WEBMASTER_API_KEY=…</code> to <code>~/.config/lt-law/.env</code>. "
                 f"Bing's crawler is counted above under Search engines either way.</p>")
    else:
        bd = sorted(b.get("daily", {}))
        p.append("<div class=two><div class=card>")
        for label, k, slot in (("Impressions", "impressions", 1), ("Clicks", "clicks", 3)):
            vals = [b["daily"][d][k] for d in bd]
            if vals:
                p.append(f"<h3>{label}: {fmt(sum(vals[-7:]))} in the last 7 days of data</h3>{bars(bd, vals, slot, 50)}")
        p.append("</div><div class='card tbl'><table><tr><th>Day</th><th class=n>Crawled</th><th class=n>In index</th><th class=n>Errors</th></tr>")
        for c in b.get("crawl", [])[-10:]:
            p.append(f"<tr><td>{c['date']}</td><td class=n>{fmt(c['crawled'])}</td><td class=n>{fmt(c['in_index'])}</td><td class=n>{fmt(c['errors'])}</td></tr>")
        p.append("</table></div></div>")

    # site health
    p.append("<h2>Site and Workers</h2><div class=grid>")
    for label, what, vals, slot, unit in [
            ("Page views (Cloudflare)", "HTML responses, any visitor including bots", [store[d]["page_views"] for d in days], 1, ""),
            ("Unique addresses", "distinct visitor addresses a day (Cloudflare)", [store[d]["uniques"] for d in days], 3, ""),
            ("REST API /api/", "requests to the JSON API", [store[d]["api"] for d in days], 5, ""),
            ("Errors 5xx", "server errors", [store[d]["s5xx"] for d in days], 8, ""),
            ("Workers requests", "all Workers, against the free 100 000 a day", [ws.get(d, {}).get("requests", 0) for d in days], 7, ""),
            ("Data served", "megabytes a day", [store[d]["bytes"] / 1e6 for d in days], 4, " MB")]:
        v7 = sum(vals[-7:])
        p.append(f"<div class=card><h3><span class=dot style='background:var(--s{slot})'></span>{e(label)}</h3><div class=what>{e(what)}</div>"
                 f"<div class=big>{fmt(v7 / 7)}{unit} <small>a day</small></div>{bars(days, vals, slot, 70, unit)}</div>")
    p.append("</div>")

    # table view of the daily numbers
    p.append("<h2>Daily numbers</h2><div class=tbl><table><tr><th>Day</th><th class=n>All</th>"
             + "".join(f"<th class=n>{e(v[0])}</th>" for v in GROUPS.values()) + "<th class=n>Visits LT</th><th class=n>Visits other</th></tr>")
    for d in reversed(days):
        r = store[d]
        p.append(f"<tr><td>{d}</td><td class=n>{fmt(r['requests'])}</td>"
                 + "".join(f"<td class=n>{fmt(r['groups'][k])}</td>" for k in GROUPS)
                 + f"<td class=n>{fmt(lt_v(r))}</td><td class=n>{fmt(r['browser_visits'] - lt_v(r))}</td></tr>")
    p.append("</table></div>")
    p.append("<footer>Aggregate counts only: no cookies, no tracking script, no single visitors. Cloudflare's per-agent counts are "
             "sampled estimates; its daily totals are exact. \"Ours\" also counts everything from this machine's public "
             "address (the address itself is not stored here).</footer>"
             "<div id=tip></div><script>const t=document.getElementById('tip');document.addEventListener('mousemove',e=>{"
             "const h=e.target.closest('[data-tip]');if(!h){t.style.display='none';return}t.textContent=h.dataset.tip;"
             "t.style.display='block';t.style.left=Math.min(e.clientX+12,innerWidth-t.offsetWidth-8)+'px';t.style.top=(e.clientY-30)+'px'})"
             "</script></main></body></html>")
    return "".join(p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30, help="how many days back to show and to fill in (Cloudflare keeps ~30)")
    ap.add_argument("--no-google", action="store_true", help="skip Search Console (it takes ~20 s)")
    ap.add_argument("--open", action="store_true", help="open the page in the default browser afterwards")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    store = json.loads(STORE.read_text()) if STORE.exists() else {}
    cf = cf_client()
    zone = cf(f"zones?name={ZONE_NAME}")["result"][0]
    ips = own_ips()
    today = dt.datetime.now(dt.timezone.utc).date()
    want = [(today - dt.timedelta(days=k)).isoformat() for k in range(a.days, 0, -1)]
    fresh = set(want[-2:])  # yesterday's sampled counts settle within a day: read it again next time
    got = 0
    for d in want:
        if d in store and d not in fresh:
            continue
        r = cf_day(cf, zone["id"], d, ips)
        if r is None:
            print(f"{d}: not readable (older than Cloudflare keeps?)", file=sys.stderr)
            continue
        store[d] = r
        got += 1
    STORE.write_text(json.dumps(store, ensure_ascii=False, indent=0, sort_keys=True))
    shown = {d: store[d] for d in sorted(store) if d >= want[0]}
    ws = workers(cf, zone["account"]["id"], want[0])
    g = {"error": "skipped (--no-google)"} if a.no_google else google(a.days)
    b = bing()
    note = (f"This machine's address was looked up at this run ({'IPv4 and IPv6' if len(ips) > 1 else 'IPv4 only' if ips else 'not found'}); "
            "on days when it was different, its traffic shows under Browser-like or Scripts.")
    PAGE.write_text(render(shown, g, b, ws, note))
    print(f"{got} days read from Cloudflare, {len(shown)} shown; Google: {g.get('error') or 'ok'}; Bing: {b.get('error') or 'ok'}")
    print(f"page: {PAGE}")
    if a.open:
        subprocess.run(["xdg-open", str(PAGE)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
