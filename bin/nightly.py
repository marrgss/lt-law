#!/usr/bin/env python3
"""Nightly update: fetch what changed, rebuild, check, and (later) deploy. Runs in GitHub Actions.

Usage: uv run bin/nightly.py [scope/v1.yaml] [--base-url URL] [--indexable] [--out out/site] [--no-fetch]
                             [--accept ABBR,ABBR]

Steps:
  1. merge the newest acts into data/state/laws.jsonl (new amending laws and their dates); the update
     must reach back to the newest act we already had, otherwise it pages back until it does;
  2. snapshot every scope act; a text is archived only when it changed (data/dokumentas/);
  3. build the whole site for today, Europe/Vilnius (labels change with the date even without new data);
  4. per-act checks against the last good build: articles parsed, no more than 2 % of them lost
     (unless the act was rewritten as a whole, or --accept names it), version not moving backwards.
     An act whose new text fails is rebuilt from its previous snapshot and reported; only if that
     fails too does the run fail (exit 1, nothing deployed);
  5. site checks: every article page has text; the laws list did not shrink;
  6. write out/site/status.json (data dates, warnings, health) and data/state/manifest.json.
No e-tar requests (D-004). data.gov.lt outages are warnings, not failures: the site is rebuilt
from the cached data (labels change with the date), and pages say when the data were last checked.
"""
import argparse
import datetime as dt
import importlib.util
import json
import os
import subprocess
import pathlib
import re
import shutil
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import currency, source  # noqa: E402
from ltlaw.currency import Laws  # noqa: E402
from ltlaw import feeds  # noqa: E402
from ltlaw.ledger import Ledger  # noqa: E402
from ltlaw.parse import parse  # noqa: E402
from ltlaw.render import STATIC_REDIRECTS, Site  # noqa: E402

MAX_DROP = 0.02
MIN_LAWS = 10_000  # the full law metadata has ~15k laws; far fewer means it's missing (fresh clone, lost state)
TEXT_ORIGIN_OK = {"Dokumentas"}
FETCH_BUDGET_S = 40 * 60  # all fetching together: building, checks and saving must fit the job's 90 minutes
SEARCH_FLOOR = 65  # bin/search_questions.json: questions whose right act must come first (of 80)


# the site as the Workers' static assets (D-032, D-051, vars.SITE_ON_WORKER): 100,000 files a Worker on Workers Paid
SITE_ON_WORKER = os.environ.get("SITE_ON_WORKER") == "true"
PAGES_FILE_LIMIT = 20000  # Cloudflare Pages (free), files a deployment: the way back while the site fit it
_spec = importlib.util.spec_from_file_location("split_site", pathlib.Path(__file__).with_name("split_site.py"))
split_site = importlib.util.module_from_spec(_spec)  # per-Worker limits (D-051); a stdlib script the deploy job runs too
_spec.loader.exec_module(split_site)


def count_laws() -> int:
    p = source.STATE / "laws.jsonl"
    return sum(1 for _ in p.open()) if p.exists() else 0


def check_act(b: dict, prev: dict | None, accept: set[str]) -> str | None:
    """Why the new build of one act must not be published, or None."""
    if b["n"] == 0:
        return "no articles parsed"
    # a rule set's points start at 1: one that starts further on lost its start (2026-11-09: MPT from 14, GDSVSET from 44,
    # SŽVVA from 36, 11 acts live so; the parser waited for a title in capitals). An independent check: validate_scope
    # parses e-tar's copy with the same parser, so both sides missed the same points.
    if b.get("unit") == "punktas" and b.get("labels") and b["labels"][0].split("-")[0] != "1":
        return f"points start at {b['labels'][0]}: the start of the document was not read"
    if not prev or b["abbr"] in accept:
        return None
    old_n, old_from = prev.get("articles"), prev.get("version_from")
    to = b.get("consolidation_valid_to")
    # an earlier version is a step back, unless it is a closed period that ends before the old one starts: a slice newly
    # prepared in front of it (CK 2026-10-27: "nuo 2027-01-01 iki 2027-10-31" before "nuo 2027-11-01", B62)
    if old_from and b["consolidation_valid_from"] and b["consolidation_valid_from"] < old_from and not (to and to < old_from):
        return f"version moved backwards ({old_from} -> {b['consolidation_valid_from']})"
    # one article lost from the same version is a broken text, however small the share (A8)
    lost = sorted(set(prev.get("labels") or []) - set(b["labels"]))
    if lost and b["consolidation_valid_from"] == old_from:
        return f"articles disappeared from the same version: {lost[:8]}"
    if old_n and b["n"] < old_n * (1 - MAX_DROP):
        rewritten = any(old_from and old_from < w <= (b["consolidation_valid_from"] or "") for w in b["rewrites"])
        if not rewritten:
            return f"articles {old_n} -> {b['n']} (more than {MAX_DROP:.0%} lost)"
    return None


def backtest_changed(scope: list[dict], changed: list[str], led: Ledger, day: str, warnings: list[str]) -> dict:
    """T3: compare what we said about each act whose text changed tonight with that text. A report, never a reason to
    stop: an act whose text can't be read tonight is the build's to judge, with its fallback to the last good text
    (2026-11-07: Suvestine down, an act with no cached consolidation stopped two runs here, before anything was built)."""
    out = {}
    for act in scope:
        if act["abbr"] not in changed:
            continue
        try:
            text, origin = source.act_text(act["dokumento_id"])
            if origin["origin"] == "Dokumentas":
                r = led.backtest(act["abbr"], parse(text, act.get("document")), day)
                if r["article_days"]:
                    out[act["abbr"]] = r
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{act['abbr']}: back-test skipped tonight ({type(e).__name__}: {e})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/v1.yaml")
    ap.add_argument("--base-url", default="http://127.0.0.1:8765")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("out/site"))
    ap.add_argument("--indexable", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="build from what is already in data/ (offline test)")
    ap.add_argument("--accept", default="", help="comma-separated act abbreviations whose big change is expected")
    ap.add_argument("--day", help="build as of this date (tests only; needs --no-fetch)")
    ap.add_argument("--skip-if-done", action="store_true", help="exit if today's build already succeeded (scheduled runs)")
    a = ap.parse_args()
    accept = {x.strip() for x in a.accept.split(",") if x.strip()}
    if a.day and not a.no_fetch:
        ap.error("--day needs --no-fetch")
    day = a.day or dt.date.today().isoformat()  # the workflow sets TZ=Europe/Vilnius
    t0 = time.time()
    scope = yaml.safe_load(open(a.scope))["acts"]
    source.use_scope(scope)  # keep resolutions amending points acts (KET) in the law metadata
    log = {"day": day, "started": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "steps": {},
           "fetch_via": "cloudflare relay (D-019)" if source.RELAY else "direct"}
    manifest_path = source.STATE / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    prev = manifest.get("acts", {})
    pathlib.Path(".skip").unlink(missing_ok=True)
    if a.skip_if_done and manifest.get("day") == day:
        print(f"already built {day}: nothing to do")
        (pathlib.Path(".skip")).write_text(day)  # tells the workflow not to save or deploy again
        return

    warnings, problems = [], []
    t_start = time.time()
    tick = lambda what: print(f"[{time.time() - t_start:6.0f} s] {what}", flush=True)  # noqa: E731  (where a slow night goes)
    source.REFRESH_SUVESTINE = not a.no_fetch
    if not a.no_fetch:
        source.limit_run(FETCH_BUDGET_S)  # an outage is a warning and a build from the last copies, never a cancelled job
        try:
            log["steps"]["new_laws"] = source.update_recent_laws(3000)
            log["steps"]["new_laws_query"] = source.UPDATE_LOG[-1:]
            log["steps"]["laws_coverage"] = dict(source.COVERAGE)
        except Exception as e:
            warnings.append(f"new laws not fetched: {e}")
        tick("new laws")
        try:
            log["steps"]["law_types_backfilled"] = source.update_missing_types()
        except Exception as e:  # tried again next night
            warnings.append(f"law types not backfilled: {e}")
        tick("law types")
        try:
            lt = [x for x in scope if not x["dokumento_id"].startswith("EU.")]
            log["steps"]["suvestine_versions_added"] = source.update_suvestine_lists(  # each act about every 4 nights: next weeks' versions known early
                lt, refresh_days=4, per_run=max(80, len(lt) // 4 + 1))  # a quarter of the scope a night (its time budget still caps it)
        except Exception as e:  # without them fewer of today's texts are recovered; tried again next night
            warnings.append(f"Suvestine version lists not fetched: {e}")
        tick("Suvestine version lists")
        try:
            log["steps"]["rulings_backfilled"] = source.update_rulings()
        except Exception as e:  # tried again next night
            warnings.append(f"Constitutional Court rulings not backfilled: {e}")
        if source.POINT_ACTS:
            try:
                log["steps"]["point_amenders_added"] = source.update_point_amenders()
            except Exception as e:  # the newest-n window still brings new ones; older ones come next night
                warnings.append(f"amending resolutions not fetched: {e}")
        tick("rulings, amending resolutions")
        try:  # the energy regulator's decisions (D-034): new ones each night, texts fetched once (5-minute budget)
            log["steps"]["regulator_decisions_added"] = source.update_decisions()
            from ltlaw import decisions as regdec
            t_dec, got, left = time.time(), 0, 0
            for d in regdec.build(source.decision_rows(), day):
                for x in ([d] + d["changed_by"]) if regdec.wants_text(d) else []:
                    if source.decision_text(x["dokumento_id"]) is not None:
                        continue
                    if time.time() - t_dec > 300:
                        left += 1
                        continue
                    try:
                        source.decision_text(x["dokumento_id"], fetch=True)
                        got += 1
                    except Exception:  # next night
                        left += 1
            log["steps"]["regulator_decision_texts"] = {"fetched": got, "left": left}
            if left:
                warnings.append(f"regulator decisions: {left} texts not fetched tonight; next night continues")
        except Exception as e:
            warnings.append(f"regulator decisions not updated: {e}")
        tick("regulator decisions")
        # Seimas votes (D-054): the newest term each night (~25 requests); earlier terms are closed and kept in the
        # state asset. A failure keeps yesterday's files: the acts' build never waits on the votes
        # its own process, outside the fetch budget: 10 minutes at most (162 s on 2026-11-15), none on a night already
        # slow, so a hung data.gov.lt costs the job's 90 minutes nothing it needs
        if pathlib.Path("data/seimas").exists() and time.time() - t_start > 30 * 60:
            warnings.append("Seimas votes not fetched (yesterday's kept): the night's fetches already took 30 minutes")
        elif pathlib.Path("data/seimas").exists():
            try:
                r = subprocess.run([sys.executable, "bin/fetch_votes.py", "--out", "data/seimas"], capture_output=True,
                                   text=True, timeout=600)
                last = (r.stdout.strip().splitlines() or [""])[-1]
                log["steps"]["seimas_votes"] = json.loads(last) if r.returncode == 0 and last.startswith("{") else None
                if r.returncode:
                    warnings.append(f"Seimas votes not fetched (yesterday's kept): {(r.stderr or r.stdout).strip()[-200:]}")
            except Exception as e:
                warnings.append(f"Seimas votes not fetched (yesterday's kept): {type(e).__name__}: {e}")
            tick("Seimas votes")
        changed, failed, t_texts, late = [], [], time.time(), []
        # longest unchecked first: a slow night's budget leaves different acts for tomorrow, not always the same ones
        due = source.awaiting_consolidation(scope, day)  # acts just amended: their new consolidation first
        log["steps"]["texts_due"] = len(due)
        # which texts changed at all: their rows' revisions, seconds for every act (D-039); an unchanged one is fetched
        # only about once a week. Failing, every act's text is fetched as before.
        lt_ids = [a["dokumento_id"] for a in scope if not a["dokumento_id"].startswith("EU.")]
        try:
            revs = source.revisions(lt_ids)
            n_revs = len(revs)
        except Exception as e:
            revs, n_revs = {}, 0
            warnings.append(f"revisions not read ({type(e).__name__}): every act's text fetched")
        # still, a seventh of the texts in full every night (the longest unfetched): each about weekly, spread evenly
        for i in sorted(lt_ids, key=source.full_fetched)[:-(-len(lt_ids) // 7)]:
            revs.pop(i, None)
        for act in sorted(scope, key=lambda x: (x["dokumento_id"] not in due, source.last_checked(x["dokumento_id"]))):
            if time.time() - t_texts > 20 * 60:  # a slow source (2026-10-24: hours): the rest from yesterday's copies
                late.append(act["abbr"])
                continue
            if source.DOWN and not act["dokumento_id"].startswith("EU."):  # EU acts come from EUR-Lex
                late.append(act["abbr"])
                continue
            before = source.snapshots(act["dokumento_id"])
            try:
                p = source.snapshot(act["dokumento_id"], revision=revs.get(act["dokumento_id"]))
            except Exception as e:  # the reason, so a one-off (data.gov.lt's 500s) and a lasting failure can be told apart
                failed.append(f"{act['abbr']} ({type(e).__name__}: {str(e)[:80]})")
                continue
            if not before or p != before[-1]:
                changed.append(act["abbr"])
        log["steps"]["texts_changed"] = changed
        log["steps"]["texts_by_revision"] = {"revisions": n_revs, "not_fetched": source.REVISION_SKIPS}
        if late:
            warnings.append(f"data.gov.lt {'not answering' if source.DOWN else 'slow'}: {len(late)} acts' texts not refreshed tonight, built from the last copies")
        tick("act texts")
        # a new act whose first text didn't come (slow or failing source) waits for the next night (STSRĮ, 2026-10-26)
        nosnap = [x["abbr"] for x in scope if not source.snapshots(x["dokumento_id"]) and x["dokumento_id"] not in source.PINNED]
        if nosnap:
            warnings.append(f"new acts not added tonight, no text fetched yet: {nosnap}")
            scope = [x for x in scope if x["abbr"] not in nosnap]
        if failed:
            warnings.append(f"texts not refreshed (kept the previous copy): {failed}")
    n_laws = count_laws()
    if manifest.get("laws") and n_laws < manifest["laws"]:
        problems.append(f"laws list shrank: {manifest['laws']} -> {n_laws} (lost state?)")
    if n_laws < MIN_LAWS:  # labels would miss older amending laws: never build on a partial list
        problems.append(f"only {n_laws} laws in data/state/laws.jsonl: restore the state archive, or run "
                        "bin/fetch_meta.py (Dokumentas) and bin/compact_state.py first")

    # T3: today's new consolidations are the answer for past days: compare what we said then (ledger.py)
    led = Ledger()
    backtests = backtest_changed(scope, log["steps"].get("texts_changed") or [], led, day, warnings)
    if not a.day:
        led.save()
    if backtests and any(r["silent"] for r in backtests.values()):
        warnings.append(f"back-test found labels that were wrong: {[f for f in led.findings[-10:]]}")

    if a.out.exists():
        shutil.rmtree(a.out)
    site = Site(a.out, a.base_url, day, a.indexable, Laws(fetch=not a.no_fetch))
    site.ledger_totals = dict(led.totals)
    site.prepare(scope)
    built, fallbacks = [], []
    tick("build starts")
    for k, act in enumerate(scope):
        t_act, net0 = time.time(), list(source.NET)
        if k and k % 25 == 0:
            tick(f"built {k} acts")
        doc = act["dokumento_id"]
        act_dir = a.out / source.act_path(act, source.latest_snapshot(doc)["row"]["tar_kodas"])
        cp = site.checkpoint()
        try:
            b = site.act(act)
            why = check_act(b, prev.get(act["abbr"]), accept)
        except Exception as e:
            b, why = None, f"build failed: {e!r}"
        if why:
            # keep the last good text: rebuild this act from its previous snapshot
            site.rollback(cp, act_dir)
            snaps = source.snapshots(doc)
            older = snaps[-2] if len(snaps) >= 2 else None
            b2, why2 = None, "no previous snapshot"
            if older:
                source.PINNED[doc] = older
                cp = site.checkpoint()
                try:
                    b2 = site.act(act)
                    why2 = check_act(b2, prev.get(act["abbr"]), accept)
                except Exception as e:
                    why2 = f"build failed: {e!r}"
            if why2 and act["abbr"] not in prev:  # not on the site yet: left out tonight, the rest goes ahead
                site.rollback(cp, act_dir)
                warnings.append(f"{act['abbr']}: new act not added tonight ({why})")
                continue
            if why2:
                problems.append(f"{act['abbr']}: {why}; previous snapshot: {why2}")
                continue
            fallbacks.append(f"{act['abbr']}: new text not used ({why}); showing the snapshot of {older.stem}")
            b = b2
        built.append(b)
        if time.time() - t_act > 30:
            n = [x - y for x, y in zip(source.NET, net0)]  # 11-09: ANK 536 s, cause unknown
            tick(f"{act['abbr']} took {time.time() - t_act:.0f} s (data.gov.lt: {n[1]} requests, {n[0]:.0f} s, {n[2] / 1e6:.1f} MB)")
    tick("all acts built")
    if not a.no_fetch:  # next weeks' versions, a few a night, so their first day needs no burst of downloads
        from ltlaw import today as _today
        try:
            log["steps"]["upcoming_texts"] = _today.prefetch_upcoming(
                [x["dokumento_id"] for x in scope if not x["dokumento_id"].startswith("EU.")], day)
        except Exception as e:  # tonight's site doesn't depend on it
            warnings.append(f"upcoming versions' texts not fetched: {type(e).__name__}: {e}")
        tick("upcoming versions' texts")
    xref_unlinked: list[str] = []
    if not problems:
        site.finish(built)
        warnings += site.soft_warnings
        if pathlib.Path("data/seimas").exists():  # the votes' JSON for the MCP tools (D-054); needs api/v1/acts.json
            r = subprocess.run([sys.executable, "bin/build_votes.py", "--out", str(a.out), "--data", "data/seimas"],
                               capture_output=True, text=True, timeout=600)
            if r.returncode:
                warnings.append(f"Seimas votes not built (the vote tools say so): {(r.stderr or r.stdout).strip()[-200:]}")
            else:
                log["steps"]["seimas_build"] = r.stdout.strip().splitlines()[-3:]
            tick("Seimas votes built")
        bad, mismatch, contradict, leftovers = [], [], [], []
        pages = {}
        broken = []
        for p in [*a.out.glob("ta/*/str/*/index.html"), *a.out.glob("ta/*/p/*/index.html")]:  # articles, points
            h = pages.setdefault(p, p.read_text())
            # cross-reference links (xref.py): the target page must exist and carry the anchor. A link without one
            # (e.g. another act fell back to an older text tonight) is unwrapped: the words stay, the link goes
            def target_ok(m):
                href = m.group(1)
                path, _, frag = re.sub(r"^https?://[^/]+", "", href).partition("#")
                tp = a.out / path.strip("/") / "index.html" if path else p
                th = pages.get(tp) if tp in pages else (pages.setdefault(tp, tp.read_text()) if tp.exists() else None)
                if th is None or (frag and f'id="{frag}"' not in th):
                    broken.append(f"{p.parent.relative_to(a.out)} → {href}")
                    return m.group(2)
                return m.group(0)
            h2 = re.sub(r'<a class="xref" href="([^"]+)">([^<]*)</a>', target_ok, h)
            if h2 != h:
                p.write_text(h2)
                pages[p] = h = h2
            # a point can be one table row; a repealed article has no text, labelled "repealed", or under its own
            # heading "Neteko galios" when the stored version is a past one (CVVTV2Į 5 in a text to 2026-05-31: "may be
            # outdated", as every article of that version; the gate stopped on it 2026-11-11)
            if not re.search(r'class="law[^"]*">\s*(?:<p|<div class="tbl")|data-state="repealed"|<h1>[^<]*\bNeteko galios nuo \d{4}-\d\d-\d\d\s*<', h):
                bad.append(str(p))
            if re.search(r'(?:nuo|redakcija) None\b|data-rel-n=""', h):
                leftovers.append(str(p))  # a value missing from a sentence ("redakcija nuo None" on 8,000 pages until 2026-11-05)
            # the label's end: data-changes-on (page) = JSON-LD temporalCoverage end + 1 day (E4, G4)
            on = re.search(r'data-changes-on="([\d-]+)"', h)
            tc = re.search(r'"temporalCoverage": "\.\./([\d-]+)"', h)
            st = re.search(r'data-state="(\w+)"', h)
            if st and st.group(1) == "current" and re.search(r'class="box box-outdated"|Nepavyko patvirtinti, kad šis tekstas', h):
                contradict.append(str(p))  # a "Galioja šiandien" page must not also warn that its text may be outdated
            if st and st.group(1) == "current" and bool(on) != bool(tc):
                mismatch.append(str(p))
            elif on and tc and (dt.date.fromisoformat(tc.group(1)) + dt.timedelta(days=1)).isoformat() != on.group(1):
                mismatch.append(str(p))
        if bad:
            problems.append(f"{len(bad)} article pages without text, e.g. {bad[:2]}")
        if leftovers:
            problems.append(f"{len(leftovers)} pages with a missing value in a sentence, e.g. {leftovers[:2]}")
        if mismatch:
            problems.append(f"{len(mismatch)} pages whose end date differs between HTML and JSON-LD, e.g. {mismatch[:2]}")
        if contradict:
            problems.append(f"{len(contradict)} pages labelled current that also warn the text may be outdated, e.g. {contradict[:2]}")
        # the agents' API files must answer through the MCP Worker's own code (D-028): run its checks on this build
        if shutil.which("node"):
            r = subprocess.run(["node", "bin/check_mcp.mjs", str(a.out)], capture_output=True, text=True, timeout=300)
            log["steps"]["mcp_check"] = (r.stdout.strip().splitlines() or ["?"])[-1]
            if r.returncode:
                problems.append("agents' API check failed: " + "; ".join(l for l in r.stdout.splitlines() if l.startswith("FAIL"))[:300])
            # the search benchmark (D-044): recorded each night, a warning below the floor (69 of 80 top-1 on 2026-11-03)
            r = subprocess.run(["node", "bin/check_search_ranking.mjs", str(a.out), "--quiet"], capture_output=True, text=True, timeout=300)
            if m := re.search(r"top-1 (\d+)/(\d+), top-3 (\d+)/\d+", r.stdout):
                log["steps"]["search_ranking"] = m.group(0)
                if int(m.group(1)) < SEARCH_FLOOR:
                    warnings.append(f"search benchmark {m.group(0)}: below {SEARCH_FLOOR} top-1 (bin/check_search_ranking.mjs)")
            else:
                warnings.append(f"search benchmark not run: {(r.stderr or r.stdout).strip()[-150:]}")
        else:
            warnings.append("node not found: the agents' API check (bin/check_mcp.mjs) was skipped")
        xref_unlinked = broken[:20] + ([f"… {len(broken)} in all"] if len(broken) > 20 else [])

    now = {b["abbr"]: {"articles": b["n"], "counts": b["counts"], "version_from": b["consolidation_valid_from"],
                       "version_to": b["consolidation_valid_to"], "fetched": b["fetched"], "labels": b["labels"]} for b in built}
    # a new version may legitimately drop articles; say which (the old URLs then show "not in this text")
    dropped = {k: sorted(set(prev.get(k, {}).get("labels") or []) - set(v["labels"]))[:20] for k, v in now.items()
               if prev.get(k, {}).get("labels") and set(prev[k]["labels"]) - set(v["labels"])}
    log["acts"] = now
    # the name we show is the text's heading, our document the first the order approves (ltlaw.scopecheck): a rename
    # by amendment shows up here the night it is consolidated (2026-11-03: 25 acts under their adopted names)
    from ltlaw import scopecheck
    names = {}
    for act in scope:
        try:
            if why := scopecheck.check(source.act_text(act["dokumento_id"])[0], act, day):
                names[act["abbr"]] = why[0]
        except Exception as e:  # noqa: BLE001  a report, never a reason to stop
            names[act["abbr"]] = f"not checked: {type(e).__name__}"
    if names:
        warnings.append(f"names or documents to check (scope/v1_seed.yaml): {names}")
    log["data_checked"] = min((b["fetched"] for b in built), default=None)
    log["register_newest_publication"] = source.register_watermark()  # acts published later are not visible yet (A19)
    if source.DOWN:
        warnings.append(f"data.gov.lt not answering ({source.DOWN}): nothing fetched after that, built from the last copies")
    if source.SUVESTINE_DOWN:
        warnings.append(f"data.gov.lt's Suvestine table failed ({source.SUVESTINE_DOWN}): version lists and today's texts from it skipped tonight")
    if source.RATE_LIMITED[0]:
        warnings.append(f"data.gov.lt answered HTTP 429 (Too Many Requests) to {source.RATE_LIMITED[0]} Suvestine queries")
    from ltlaw import today as _today
    if _today._FETCH["skipped"]:
        warnings.append(f"today's-text versions not fetched tonight (time budget or errors): {_today._FETCH['skipped']}; next night continues")
    log["warnings"] = warnings + fallbacks
    log["health"] = {"laws": n_laws, "fallbacks": fallbacks, "xref_unlinked": xref_unlinked,
                     "unexplained_version_dates": {b["abbr"]: b["unexplained"] for b in built if b["unexplained"]},
                     "repealed_or_expiring": {b["abbr"]: b["expires"] for b in built if b["expires"]},
                     "corrupt_characters": {b["abbr"]: b["corrupt_chars"][:20] for b in built if b["corrupt_chars"]},
                     "articles_dropped_by_new_version": dropped,
                     # source lines shown nowhere on the site (parser losses; A10)
                     "source_lines_not_shown": {b["abbr"]: b["dropped_lines"] for b in built if b["dropped_lines"]},
                     "signature_and_history_lines_excluded": sum(b["excluded_lines"] for b in built),
                     "amending_fetch_failed": currency.FETCH_FAILED[:20], "amending_refreshed": currency.REFRESHED[:50],
                     "suvestine_refresh_failed": source.SUVESTINE_FAILED[:20],
                     "articles_not_in_stored_text": {b["abbr"]: b["today_only"] for b in built if b["today_only"]},
                     "notices": {b["abbr"]: b["notices"] for b in built if b["notices"]},
                     "unrendered_tail_lines": {b["abbr"]: b["tail_lines"] for b in built if b["tail_lines"]},
                     # D-009 fallback: Dokumentas has no consolidation for these, the frozen Suvestine is used
                     "text_from_suvestine": [b["abbr"] for b in built if b["origin"] not in TEXT_ORIGIN_OK]}
    log["problems"] = problems
    log["seconds"] = round(time.time() - t0)
    for w in log["warnings"]:
        print("WARNING", w)
    if problems:
        print("GATES FAILED:\n  " + "\n  ".join(problems))
        source.STATE.mkdir(parents=True, exist_ok=True)
        (source.STATE / "last_failed.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
        sys.exit(1)
    # change feeds: tonight vs the last night on record (before tonight is recorded)
    urls = {(b["abbr"], None): b["url"] for b in built}
    urls.update({(b["abbr"], l): f"{b['url']}{b.get('seg', 'str')}/{l}/" for b in built for l in site.ledger_today.get(b["abbr"], {})})
    # where the texts came from, tonight and on the last earlier day (as the ledger compares): the feeds say why a text
    # changed. A second run on the same day compares with the same earlier day.
    src_path = source.STATE / "act_sources.json"
    src_file = json.loads(src_path.read_text()) if src_path.exists() else {}
    src_last = src_file.get("prev") if src_file.get("day") == day else (src_file if src_file.get("day") else None)
    src_prev = src_last["acts"] if src_last else None
    events = feeds.detect(led, site.ledger_today, day, urls, {b["abbr"]: b["name"] for b in built},
                          {b["abbr"]: "p." if b.get("unit") == "punktas" else "str." for b in built},
                          {b["abbr"]: b.get("cite") or b["abbr"] for b in built}, site.sources_today, src_prev)
    all_events = feeds.store(events) if not a.day else events
    if not a.day:
        src_path.write_text(json.dumps({"day": day, "acts": site.sources_today,
                                        "prev": {"day": src_last["day"], "acts": src_last["acts"]} if src_last else None},
                                       ensure_ascii=False, sort_keys=True))
    areas = yaml.safe_load(pathlib.Path("scope/areas.yaml").read_text())["areas"] if pathlib.Path("scope/areas.yaml").exists() else []
    feeds.write(a.out, a.base_url.rstrip("/"), all_events, {b["abbr"]: (b["path"], f"{b['tag']} – {b['name']}" if b.get("tag") else b["name"]) for b in built},
                day, areas)
    site.changes_pages(all_events, built, areas)
    log["changes_today"] = len(events)
    if not a.day:  # simulated days (tests) never go on record
        for abbr, labels in site.ledger_today.items():  # only a build that passed is on record
            for label, (state, fp) in labels.items():
                led.record(day, abbr, label, state, fp)
        led.save()
    log["ledger"] = {"totals": led.totals, "today": backtests}
    # the host's limits, checked before a deploy that would be refused (2026-11-04: _redirects): on the Workers
    # (D-032, D-051) per Worker, the site split as bin/split_site.py will split it; on Pages (free) 20,000 files in all
    n_files = sum(1 for f in a.out.rglob("*") if f.is_file()) + (0 if (a.out / "status.json").exists() else 1)
    log["files"] = n_files
    big = [f"{f.relative_to(a.out)} ({f.stat().st_size // 2**20} MiB)" for f in a.out.rglob("*") if f.is_file() and f.stat().st_size > 25 * 2**20]
    if SITE_ON_WORKER:
        parts = split_site.counts(a.out)
        parts[0]["files"] += 0 if (a.out / "status.json").exists() else 1
        log["workers"] = parts
        over = split_site.over_limits(parts)
        near = [f"{p['worker']}: {p['files']} files" for p in parts if p["files"] > split_site.FILE_LIMIT - 5000] + \
               [f"{p['worker']}: {p['redirect_rules']} _redirects rules" for p in parts if p["redirect_rules"] > split_site.REDIRECT_LIMIT - 100]
    else:
        n_redirects = sum(1 for _ in (a.out / "_redirects").open()) if (a.out / "_redirects").exists() else 0
        over = ([f"{n_files} files, more than Pages' {PAGES_FILE_LIMIT}"] if n_files > PAGES_FILE_LIMIT else []) + \
               ([f"_redirects has {n_redirects} lines (limit {STATIC_REDIRECTS})"] if n_redirects > STATIC_REDIRECTS else [])
        near = [f"{n_files} files"] if n_files > PAGES_FILE_LIMIT - 300 else []
    if over or big:
        print(f"GATES FAILED:\n  the host would refuse this: {over}; files over 25 MiB: {big} (OPERATIONS: another Worker, D-051)")
        sys.exit(1)
    if near:
        log["warnings"].append(f"near the host's limits: {near} (a new Worker: bin/split_site.py, D-051)")
        print("WARNING", log["warnings"][-1])
    (a.out / "status.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    manifest_path.write_text(json.dumps({"day": day, "laws": n_laws, "acts": now}, ensure_ascii=False, indent=1))
    files = [f for f in a.out.rglob("*") if f.is_file()]
    print(f"OK {day}: {len(built)} acts, {len(files)} files, {log['seconds']} s; "
          f"new laws {log['steps'].get('new_laws', '-')}, texts changed {log['steps'].get('texts_changed', '-')}, "
          f"fallbacks {len(fallbacks)}")


if __name__ == "__main__":
    main()
