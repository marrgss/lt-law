#!/usr/bin/env python3
"""Split the built site between the Workers that serve it (D-051).

A Worker version holds at most 100,000 static files (Workers Paid) and a `_redirects` file at most 2,000 static rules.
The site is past what one Worker can grow into, so more Workers serve parts of it: each extra Worker is a
`worker-mcp/wrangler.site<N>.toml` with routes like `atviri-teises-aktai.lt/ta/1*` and no script (assets only: their
requests are free, D-051). A route is more specific than the main Worker's `/*`, so it takes those addresses; this
script puts the files of those addresses into that Worker's `[assets] directory`. Everything else, and every file the
MCP Worker reads (api/v1/), stays with the main Worker.

Each part gets its own copy of 404.html and _headers (the security headers apply per Worker), and the `_redirects`
rules whose source is in its paths.

Usage:
  python3 bin/split_site.py out/site --count                 # files and redirect rules per Worker (JSON), moves nothing
  python3 bin/split_site.py out/site --apply                 # move the files into each extra Worker's directory
  python3 bin/split_site.py out/site --smoke https://atviri-teises-aktai.lt   # after the deploys: one page of each part

Standard library only: the deploy job runs it with the runner's python3, without the project's environment.
"""
import argparse
import json
import pathlib
import shutil
import sys
import time
import tomllib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILE_LIMIT = 100_000      # static files per Worker version (Workers Paid)
REDIRECT_LIMIT = 2_000    # static rules in one `_redirects`
SHARED = ("404.html", "_headers")  # each part needs its own


def mcp_reads(rel: str) -> bool:
    """A file the MCP Worker reads through its own assets outside api/v1/: an act's article list (get_act_contents).
    It goes to the part that serves its address and a copy stays with the main Worker (2026-11-25: since the split,
    get_act_contents answered "0 articles" for every act under /ta/1*: its articles.json was only on the second Worker)."""
    return rel.endswith("/articles.json")


def configs(root: pathlib.Path = ROOT) -> list[pathlib.Path]:
    """The extra Workers' configurations, in a stable order (wrangler.site2.toml, wrangler.site3.toml, ...)."""
    return sorted((root / "worker-mcp").glob("wrangler.site[0-9]*.toml"), key=lambda p: int(p.stem.removeprefix("wrangler.site")))


def part_of(cfg: pathlib.Path) -> dict:
    """An extra Worker: its name, the path prefixes its routes take (without the leading slash), its assets directory."""
    d = tomllib.loads(cfg.read_text())
    prefixes = []
    for r in d.get("routes", []):
        pattern = r["pattern"] if isinstance(r, dict) else r
        host, _, path = pattern.partition("/")
        if not path.endswith("*") or "*" in path[:-1] or not path[:-1]:
            raise SystemExit(f"{cfg.name}: route {pattern!r}: only a path prefix ending in * is supported")
        prefixes.append(path[:-1])
    if not prefixes:
        raise SystemExit(f"{cfg.name}: no routes")
    if d.get("main"):
        raise SystemExit(f"{cfg.name}: an extra Worker serves files only (no `main`: its requests stay free, D-051)")
    return {"name": d["name"], "prefixes": prefixes, "dir": (cfg.parent / d["assets"]["directory"]).resolve()}


def owner(rel: str, parts: list[dict]) -> int:
    """Which part serves this site path ("ta/1041.../index.html" or "/ta/1041.../"): 0 the main Worker, else 1, 2, ...
    The most specific route wins, as on Cloudflare: the longest matching prefix."""
    rel = rel.lstrip("/")
    best, n = 0, -1
    for i, p in enumerate(parts, 1):
        for pre in p["prefixes"]:
            if rel.startswith(pre) and len(pre) > n:
                best, n = i, len(pre)
    return best


def plan(site: pathlib.Path, parts: list[dict]) -> dict:
    """Files and redirect rules per part (0 = main)."""
    files = {i: [] for i in range(len(parts) + 1)}
    for f in site.rglob("*"):
        if f.is_file():
            rel = f.relative_to(site).as_posix()
            i = 0 if rel in SHARED or rel == "_redirects" else owner(rel, parts)
            files[i].append(rel)
            if i and mcp_reads(rel):
                files[0].append(rel)  # the MCP Worker's copy
    rules = {i: [] for i in files}
    red = site / "_redirects"
    for line in (red.read_text(encoding="utf-8").splitlines() if red.exists() else []):
        src = line.split()[0] if line.strip() and not line.lstrip().startswith("#") else ""
        rules[owner(src, parts) if src.startswith("/") else 0].append(line)
    return {"files": files, "rules": rules}


def counts(site: pathlib.Path, parts: list[dict] | None = None) -> list[dict]:
    """Per Worker: name, files (as deployed: with its copies of the shared files and its own _redirects), rules."""
    parts = [part_of(c) for c in configs()] if parts is None else parts
    p = plan(site, parts)
    out = []
    for i in p["files"]:
        extra = 0 if i == 0 else sum((site / s).exists() for s in SHARED) + (1 if p["rules"][i] else 0)
        out.append({"worker": "main" if i == 0 else parts[i - 1]["name"], "files": len(p["files"][i]) + extra,
                    "redirect_rules": len(p["rules"][i])})
    return out


def over_limits(cs: list[dict]) -> list[str]:
    return [f"{c['worker']}: {c['files']} files (limit {FILE_LIMIT})" for c in cs if c["files"] > FILE_LIMIT] + \
           [f"{c['worker']}: {c['redirect_rules']} _redirects rules (limit {REDIRECT_LIMIT})" for c in cs if c["redirect_rules"] > REDIRECT_LIMIT]


def apply(site: pathlib.Path, parts: list[dict]) -> list[dict]:
    p = plan(site, parts)
    for i, part in enumerate(parts, 1):
        dest = part["dir"]
        if dest == site.resolve() or site.resolve() in dest.parents:
            raise SystemExit(f"{part['name']}: its directory {dest} is inside the site")
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for rel in p["files"][i]:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (shutil.copy2 if mcp_reads(rel) else shutil.move)(site / rel, dest / rel)
        for s in SHARED:
            if (site / s).exists():
                shutil.copy2(site / s, dest / s)
        if p["rules"][i]:
            (dest / "_redirects").write_text("\n".join(p["rules"][i]) + "\n", encoding="utf-8")
    if (site / "_redirects").exists():
        (site / "_redirects").write_text("".join(f"{l}\n" for l in p["rules"][0]), encoding="utf-8")
    for d in sorted((x for x in site.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):  # emptied directories
        if not any(d.iterdir()):
            d.rmdir()
    return counts_after(site, parts)


def counts_after(site: pathlib.Path, parts: list[dict]) -> list[dict]:
    def n(d: pathlib.Path) -> int:
        return sum(1 for f in d.rglob("*") if f.is_file())

    def r(d: pathlib.Path) -> int:
        return len((d / "_redirects").read_text(encoding="utf-8").splitlines()) if (d / "_redirects").exists() else 0
    return [{"worker": "main", "files": n(site), "redirect_rules": r(site)}] + \
           [{"worker": p["name"], "files": n(p["dir"]), "redirect_rules": r(p["dir"])} for p in parts]


def smoke(base: str, site: pathlib.Path, parts: list[dict], wait: int = 90) -> list[str]:
    """One page of each part answers 200 from the public site (a new route can take some seconds to apply), and the MCP
    Worker lists the articles of an act in each part (its own copy of the act's articles.json)."""
    pages = [("main", "/")]
    for p in parts:
        html = next((f for f in sorted(p["dir"].rglob("index.html"))), None)
        if html:
            pages.append((p["name"], "/" + html.parent.relative_to(p["dir"]).as_posix() + "/"))
    bad = []
    for name, path in pages:
        deadline, status = time.time() + wait, None
        while True:
            try:
                req = urllib.request.Request(base.rstrip("/") + path, headers={"User-Agent": "atviri-teises-aktai-deploy-check"})
                status = urllib.request.urlopen(req, timeout=30).status
            except urllib.error.HTTPError as e:
                status = e.code
            except Exception as e:  # noqa: BLE001
                status = type(e).__name__
            if status == 200 or time.time() > deadline:
                break
            time.sleep(10)
        print(f"{name}: {path} -> {status}")
        if status != 200:
            bad.append(f"{name}: {path} -> {status}")
    for p in parts:
        lst = next((f for f in sorted(p["dir"].rglob("articles.json")) if f.parent.parent.name == "ta"), None)
        if not lst:
            continue
        tar = lst.parent.name
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "get_act_contents", "arguments": {"act": tar, "limit": 1}}}).encode()
        try:
            req = urllib.request.Request(base.rstrip("/") + "/mcp", body, {"Content-Type": "application/json",
                                         "Accept": "application/json", "User-Agent": "atviri-teises-aktai-deploy-check"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            total = json.loads(r["result"]["content"][0]["text"]).get("total")
        except Exception as e:  # noqa: BLE001
            total = type(e).__name__
        print(f"mcp get_act_contents {tar} ({p['name']}): {total} articles")
        if not isinstance(total, int) or total < 1:
            bad.append(f"mcp get_act_contents {tar} ({p['name']}): {total}")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("site", type=pathlib.Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--count", action="store_true", help="print files and redirect rules per Worker; move nothing")
    g.add_argument("--apply", action="store_true", help="move each extra Worker's files into its assets directory")
    g.add_argument("--smoke", metavar="URL", help="after the deploys: one page of each part must answer 200")
    a = ap.parse_args()
    parts = [part_of(c) for c in configs()]
    if a.smoke:
        bad = smoke(a.smoke, a.site, parts)
        sys.exit(f"pages not served: {bad}" if bad else 0)
    cs = apply(a.site, parts) if a.apply else counts(a.site, parts)
    print(json.dumps(cs, ensure_ascii=False))
    if over := over_limits(cs):
        sys.exit(f"over the host's limits: {over}")


if __name__ == "__main__":
    main()
