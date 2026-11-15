#!/usr/bin/env python3
"""Add a batch of acts in one command: seed → resolve → fetch → check → validate → hold failures → areas → gate.

Usage: uv run bin/add_acts.py <batch.yaml> [--area SLUG] [--from STEP] [--no-gate]

<batch.yaml> holds seed lines (scope/v1_seed.yaml's format, e.g. from bin/rank_candidates.py --seeds) under `acts:`,
each optionally with `area: <slug>` (scope/areas.yaml); --area is the default for those without. The run is resumable:
each step is recorded in out/add/<batch>/progress.json and a rerun starts after the last finished one (--from STEP to
redo from there). Steps:
  seed      append the batch to scope/v1_seed.yaml under a dated comment (abbreviations must be new)
  resolve   bin/resolve_scope.py; seeds that don't resolve are held
  fetch     amending orders (rules made of points), today's snapshots with the amending laws, Suvestine version lists
            and today's texts (bin/fetch_new_acts.py, bin/snapshot_scope.py), each repeated through data.gov.lt's
            500/429 spells
  check     per act: articles parsed, the name is the text's heading and the document is the first one the order
            approves (ltlaw.scopecheck), the act is in an area
  validate  validate_scope, validate_currency, validate_today_text on the batch only, one after the other (two at once
            meet 429s); validation/*.json, the full scope's record, is put back afterwards
  hold      every act that failed a step goes to scope/queued_seed.yaml with its reason; resolve again
  areas     the kept acts into scope/areas.yaml
  gate      bin/nightly.py --no-fetch on the whole scope into out/gate (data/state is copied before and put back:
            the gate writes the ledger and the manifest)
The state asset is not uploaded: bin/state_asset.py does that, after a look at the report.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import yaml  # noqa: E402

STEPS = ["seed", "resolve", "fetch", "check", "validate", "hold", "areas", "gate"]
SEED, QUEUE, SCOPE, AREAS = (ROOT / "scope" / f for f in ("v1_seed.yaml", "queued_seed.yaml", "v1.yaml", "areas.yaml"))


def run(cmd: list[str], log: pathlib.Path, tries: int = 1, wait: int = 120, env: dict | None = None) -> tuple[int, str]:
    """A tool's run, its output kept in `log`; a crash (a traceback: data.gov.lt failing) is tried again after `wait` s.
    An exit code of 1 with no traceback is a result (a validator's failures), not a crash."""
    for k in range(tries):
        r = subprocess.run(["uv", "run", *cmd], cwd=ROOT, capture_output=True, text=True, env={**os.environ, **(env or {})})
        out = r.stdout + r.stderr
        log.write_text(out)
        if "Traceback (most recent call last)" not in out or k == tries - 1:
            return r.returncode, out
        print(f"    {cmd[1]} crashed ({out.strip().splitlines()[-1][:100]}); again in {wait} s", flush=True)
        time.sleep(wait)
    return r.returncode, out


def seed_lines(batch: pathlib.Path) -> list[tuple[str, str, str | None]]:
    """(abbr, the seed line without `area`, area) for each act of the batch file, its text kept as written."""
    out = []
    for line in batch.read_text().splitlines():
        m = re.match(r"\s*- \{abbr: ([^,}]+),", line)
        if not m:
            continue
        area = re.search(r",\s*area: ([\w-]+)", line)
        out.append((m.group(1).strip(), "  " + re.sub(r",\s*area: [\w-]+", "", line.strip()), area.group(1) if area else None))
    return out


def subset(abbrs: set[str]) -> list[dict]:
    return [a for a in yaml.safe_load(SCOPE.read_text())["acts"] if a["abbr"] in abbrs]


def add_to_area(slug: str, abbrs: list[str]) -> None:
    """Append to one area's `acts: [...]` list, keeping the file's comments (no YAML round trip). The list ends at its
    first "]": never a re.S ".*" across lines (2026-11-03: energy acts landed in Transport that way)."""
    s = AREAS.read_text()
    pat = re.compile(r"(    slug: " + re.escape(slug) + r"\n(?:    #[^\n]*\n)*    acts: \[)([^\]]*)(\])")
    m = pat.search(s)
    if not m:
        raise SystemExit(f"area {slug!r} not in scope/areas.yaml")
    have = {x.strip() for x in m.group(2).split(",")}
    new = [x for x in abbrs if x not in have]
    if new:
        body = m.group(2).rstrip() + (", " if m.group(2).strip() else "") + ", ".join(new)
        s = s[:m.start()] + m.group(1) + body + m.group(3) + s[m.end():]
        AREAS.write_text(s)


def remove_from_areas(abbrs: set[str]) -> None:
    """Take held acts out of every area list (a rerun after the areas step held one more), lines kept as they are."""
    s = AREAS.read_text()

    def drop(m: re.Match) -> str:
        body = m.group(2)
        for x in abbrs:
            x = re.escape(x)
            body = re.sub(rf",\s*{x}(?=\s*(?:,|$))", "", body)   # after another
            body = re.sub(rf"^(\s*){x}\s*(?:,\s*|$)", r"\1", body)  # the first
        return m.group(1) + body + m.group(3)
    AREAS.write_text(re.sub(r"(    acts: \[)([^\]]*)(\])", drop, s))


def in_areas() -> set[str]:
    return {x for g in yaml.safe_load(AREAS.read_text())["areas"] for x in g["acts"]}


def hold(abbrs: dict[str, str], day: str) -> None:
    """Move these seeds from v1_seed.yaml to queued_seed.yaml, one dated comment per reason."""
    lines = SEED.read_text().split("\n")
    moved: dict[str, list[str]] = {}
    keep = []
    for line in lines:
        m = re.match(r"  - \{abbr: ([^,}]+),", line)
        if m and m.group(1) in abbrs:
            moved.setdefault(abbrs[m.group(1)], []).append(line)
        else:
            keep.append(line)
    SEED.write_text("\n".join(keep))
    q = QUEUE.read_text().rstrip("\n")
    for reason, ls in moved.items():
        q += f"\n  # {day}: held back by bin/add_acts.py: {reason}\n" + "\n".join(ls)
    QUEUE.write_text(q + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch", type=pathlib.Path)
    ap.add_argument("--area", help="area slug for acts whose seed line has no `area:`")
    ap.add_argument("--from", dest="start", choices=STEPS, help="redo from this step")
    ap.add_argument("--no-gate", action="store_true", help="stop before the gate (another batch follows)")
    ap.add_argument("--accept", default="", help="gate: comma-separated live acts whose lost articles are expected (a parser "
                    "fix: IASESASA's annex read as points 9–51 until 2026-11-11); the state then needs their new labels")
    a = ap.parse_args()
    from ltlaw import scopecheck, source
    from ltlaw.parse import parse

    work = ROOT / "out" / "add" / a.batch.stem
    work.mkdir(parents=True, exist_ok=True)
    prog_path = work / "progress.json"
    prog = json.loads(prog_path.read_text()) if prog_path.exists() else {"done": [], "held": {}}
    if a.start:
        prog["done"] = prog["done"][:STEPS.index(a.start)]
    save = lambda: prog_path.write_text(json.dumps(prog, ensure_ascii=False, indent=1))  # noqa: E731
    day = dt.date.today().isoformat()
    batch = seed_lines(a.batch)
    abbrs = {x[0] for x in batch}
    area_of = {ab: ar or a.area for ab, _, ar in batch}
    held: dict[str, str] = prog["held"]
    live = lambda: abbrs - set(held)  # noqa: E731
    sub = work / "subset.yaml"

    def write_subset() -> list[dict]:
        acts = subset(live())
        sub.write_text(yaml.safe_dump({"acts": acts}, allow_unicode=True, sort_keys=False))
        return acts

    for step in STEPS:
        if step in prog["done"] or (step == "gate" and a.no_gate):
            continue
        t0 = time.time()
        print(f"== {step}", flush=True)
        if step == "seed":
            text = SEED.read_text()
            known = set(re.findall(r"abbr: ([^,}]+)", text + QUEUE.read_text()))
            clash = sorted(abbrs & known)
            if clash:
                raise SystemExit(f"abbreviations already in the seed or the queue: {clash}")
            SEED.write_text(text.rstrip("\n") + f"\n  # {day}: {a.batch.stem} (bin/add_acts.py)\n" + "\n".join(x[1] for x in batch) + "\n")
        elif step == "resolve":
            code, out = run(["bin/resolve_scope.py"], work / "resolve.log")
            if "resolved ->" not in out:  # it stopped before writing the scope: nothing else is safe to do
                raise SystemExit(f"bin/resolve_scope.py failed: {out.strip().splitlines()[-1][:200]}")
            for m in re.finditer(r"UNRESOLVED (\S+): (.*)", out):
                if m.group(1) in abbrs:
                    held[m.group(1)] = f"not resolved ({m.group(2)[:120]})"
            write_subset()
        elif step == "fetch":
            acts = write_subset()
            if any(x.get("adopted") for x in acts):  # approved by a resolution or an order: amended by those
                run(["bin/fetch_new_acts.py", str(sub), "--amenders"], work / "amenders.log", tries=3)
            code, out = run(["bin/snapshot_scope.py", str(sub), "--amending"], work / "snapshot.log", tries=5, wait=180)
            if code:
                raise SystemExit(f"snapshots failed after 5 tries (data.gov.lt down?): see {work / 'snapshot.log'}; rerun later")
            run(["bin/fetch_new_acts.py", str(sub), "--lists", "--texts"], work / "lists_texts.log", tries=3)
        elif step == "check":
            areas = in_areas()
            for act in write_subset():
                why = None
                try:
                    for attempt in range(4):  # Suvestine's 500s come in spells, and one ends the table for the whole process
                        source.SUVESTINE_DOWN = False
                        try:
                            text = source.act_text(act["dokumento_id"])[0]
                            break
                        except (OSError, TimeoutError):
                            if attempt == 3:
                                raise
                            time.sleep(30)
                    arts = parse(text, act.get("document")).main.articles
                    n = len(arts)
                    first = arts[0].label.split("-")[0] if arts else ""
                    why = "0 articles or points parsed (a layout the parser doesn't read)" if n == 0 else \
                        f"points start at {arts[0].label} (the start of the document not read)" if act.get("unit") == "punktas" and first != "1" else \
                        "; ".join(scopecheck.check(text, act, day)) or None
                except (OSError, TimeoutError) as e:  # data.gov.lt down (its 500s): the act is fine, the source isn't
                    why = f"source unavailable ({type(e).__name__}: {str(e)[:80]}): add again when data.gov.lt answers"
                except Exception as e:  # noqa: BLE001
                    why = f"parse failed: {type(e).__name__}: {str(e)[:100]}"
                if not why and not area_of.get(act["abbr"]) and act["abbr"] not in areas:
                    why = "no area (give `area:` in the batch or --area)"
                if why:
                    held[act["abbr"]] = why
                    print(f"  {act['abbr']}: {why}")
        elif step == "validate":
            write_subset()
            vdir = ROOT / "validation"
            keep = {p.name: p.read_bytes() for p in vdir.glob("*.json")}
            try:
                for tool in ("validate_scope", "validate_currency", "validate_today_text"):
                    code, out = run([f"bin/{tool}.py", str(sub)], work / f"{tool}.log", tries=4, wait=180)
                    res = json.loads((vdir / {"validate_scope": "scope.json", "validate_currency": "currency.json",
                                              "validate_today_text": "today_text.json"}[tool]).read_text())
                    for ab in sorted(live()):
                        r = res.get("acts", {}).get(ab)
                        if tool == "validate_scope":
                            if r is None and re.search(rf"^SKIP {re.escape(ab)}: e-tar has no version", out, re.M):
                                held[ab] = "validate_scope: e-tar has no version matching our text"
                            elif r is not None and (r.get("ok") is False or r.get("unverified")):
                                held[ab] = (f"validate_scope: parser vs e-tar differ (missing {r.get('missing')}, extra "
                                            f"{r.get('extra')}, text {r.get('text_diff')})" if not r.get("unverified")
                                            else "validate_scope: e-tar has the version only as files")
                        elif tool == "validate_currency" and r is not None:
                            if r.get("silent_errors"):
                                held[ab] = f"validate_currency: {r['silent_errors']} articles labelled current with another wording than e-tar's today"
                            elif r.get("unverified"):
                                held[ab] = "validate_currency: e-tar gives today's version only as files: labels unverifiable"
                        elif tool == "validate_today_text" and r is not None and r.get("wrong"):
                            held[ab] = f"validate_today_text: {r['wrong']} recovered texts differ from e-tar's"
                    if "Traceback" in out:
                        raise SystemExit(f"{tool} kept crashing: see {work / (tool + '.log')}; rerun with --from validate")
                    print(f"  {tool}: exit {code}; held so far {len(held)}", flush=True)
            finally:
                for name, b in keep.items():
                    (vdir / name).write_bytes(b)
        elif step == "hold":
            mine = {ab: why for ab, why in held.items() if ab in abbrs}
            if mine:
                hold(mine, day)
                remove_from_areas(set(mine))
                run(["bin/resolve_scope.py"], work / "resolve2.log")
            write_subset()
        elif step == "areas":
            by: dict[str, list[str]] = {}
            for ab in sorted(live()):
                if area_of.get(ab):
                    by.setdefault(area_of[ab], []).append(ab)
            for slug, xs in by.items():
                add_to_area(slug, xs)
            missing = sorted(live() - in_areas())
            if missing:
                raise SystemExit(f"acts in no area: {missing}")
        elif step == "gate":
            state, keep = source.STATE, work / "state.before-gate"
            shutil.rmtree(keep, ignore_errors=True)
            shutil.copytree(state, keep)
            try:
                code, out = run(["bin/nightly.py", "scope/v1.yaml", "--no-fetch", "--indexable", "--out", "out/gate"]
                                + (["--accept", a.accept] if a.accept else []),
                                work / "gate.log", env={"SITE_ON_WORKER": "true"})
            finally:
                shutil.rmtree(state)
                shutil.copytree(keep, state)
            ok = re.search(r"^OK .*", out, re.M)
            not_added = re.findall(r"WARNING (\S+): new act not added tonight \((.*)\)", out)
            for ab, why in not_added:
                if ab in abbrs:
                    held[ab] = f"gate: {why[:150]}"
            if not ok or any(ab in abbrs for ab, _ in not_added):
                save()
                raise SystemExit(f"gate: {'not OK' if not ok else 'acts left out'}; see {work / 'gate.log'} "
                                 f"(held ones are in progress.json: rerun with --from hold)")
            print("  " + ok.group(0))
        prog["done"].append(step)
        save()
        print(f"   {step} done in {time.time() - t0:.0f} s", flush=True)

    kept = sorted(live())
    print(f"\n{len(kept)} of {len(abbrs)} acts added: {kept}")
    for ab, why in sorted(held.items()):
        if ab in abbrs:
            print(f"  held {ab}: {why}")
    print("next: review, commit, then bin/state_asset.py pack && bin/state_asset.py upload (not while a nightly runs)")


if __name__ == "__main__":
    main()
