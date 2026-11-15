"""Change feeds (Atom): what changed on the site, per act and site-wide, from the nightly ledger.

An event is written when an article's label or text differs from its last night on record: a new text (a new official
consolidation, or another version taking over), a label that changed (e.g. "Įsigalios 2026-11-01" → "Galioja
šiandien"), or, one entry per act, texts our own fixes changed while the source stayed the same.
Events are kept in data/state/changes.jsonl so the feeds have history. Wording is built from data only.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import urllib.parse
from xml.sax.saxutils import escape

from . import source

LABEL = {"current": "Galioja šiandien", "pending": "Įsigalios", "outdated": "Gali būti pasenęs", "unknown": "Neaišku, ar galioja",
         "repealed": "Neteko galios"}


SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
NEW_TEXT = {"lt": "tekstas pasikeitė (nauja Seimo kanceliarijos suvestinė redakcija)",
            "eu": "tekstas pasikeitė (nauja EUR-Lex suvestinė redakcija)"}


def _cause(label: str, now: dict | None, prev: dict | None) -> str | None:
    """Why an article's shown text changed, from where tonight's and last night's texts came from (render.sources_today):
    another version shown, a new text of the act, or None: shown from the act's stored text both nights and that text
    the same, so our reading of it changed (a fix on the site, not a change in the law). Anything else (no record of
    last night; the same other version, whose source we don't track): the plain words, no cause claimed."""
    if not now or not prev:
        return "tekstas pasikeitė"
    v_now, v_prev = now["today"].get(label), prev["today"].get(label)
    if v_now != v_prev:
        v = v_now or now.get("from")
        return f"tekstas pasikeitė (rodoma redakcija, galiojanti nuo {v})" if v else "tekstas pasikeitė (rodoma kita redakcija)"
    if v_now:
        return "tekstas pasikeitė"
    if now["text"] != prev["text"]:
        if not now.get("eu_version"):
            return NEW_TEXT["lt"]
        if now["eu_version"] != prev.get("eu_version"):
            return NEW_TEXT["eu"]
    return None


def detect(led, today: dict, day: str, urls: dict, names: dict, short: dict | None = None, cites: dict | None = None,
           sources: dict | None = None, sources_prev: dict | None = None) -> list[dict]:
    """Compare tonight's (state, fingerprint) per article with the ledger's last entry before `day`.
    `short`: the unit's abbreviation per act ("str.", or "p." for points acts such as KET). `sources`, `sources_prev`:
    where tonight's and last night's texts came from; texts our fixes changed (the source the same) make one entry
    per act, not one per article (a parser fix once made 500)."""
    out, sources = [], sources or {}
    for abbr, labels in today.items():
        known = led.acts.get(abbr)
        if not known:
            if led.acts:  # the ledger exists, this act doesn't: a newly added act
                out.append({"day": day, "act": abbr, "article": None, "kind": "act_added", "url": urls.get((abbr, None)),
                            "text": f"Pridėtas teisės aktas: {names.get(abbr, abbr)}"})
            continue
        cite, unit = (cites or {}).get(abbr, abbr), (short or {}).get(abbr, "str.")
        fixed = []
        for label, (state, fp) in labels.items():
            rows = [r for r in known.get(label, []) if r[0] < day]
            if not rows:
                continue
            prev = rows[-1]
            head, _, sup = label.partition("-")  # "41-1" -> "41¹", as the pages print it
            pretty = head + sup.translate(SUP) if sup.isdigit() else label
            changes = []
            if prev[3] != fp:
                cause = "tekstas pasikeitė" if sources_prev is None else _cause(label, sources.get(abbr), sources_prev.get(abbr))
                if cause:
                    changes.append(cause)
                else:
                    fixed.append(pretty)
            if prev[2] != state:
                changes.append(f"žyma: {LABEL.get(prev[2], prev[2])} → {LABEL.get(state, state)}")
            if changes:
                out.append({"day": day, "act": abbr, "article": label, "kind": "change", "url": urls.get((abbr, label)),
                            "text": f"{cite} {pretty} {unit}: " + "; ".join(changes)})
        if fixed:
            how = "perkėlimas iš EUR-Lex" if (sources.get(abbr) or {}).get("eu_version") else "nuskaitymas"
            shown = ", ".join(fixed[:12]) + (f" ir dar {len(fixed) - 12}" if len(fixed) > 12 else "")
            out.append({"day": day, "act": abbr, "article": None, "kind": "fix", "url": urls.get((abbr, None)),
                        "text": f"{cite}: svetainėje pataisytas teksto {how} ({len(fixed)} {unit}: {shown}); "
                                f"teisės akto tekstas nepasikeitė"})
    return out


def store(events: list[dict]) -> list[dict]:
    path = source.STATE / "changes.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    # a night run twice (a re-run, the backup run) records the same events again: keep each once
    have = {l.strip() for l in path.open()} if path.exists() else set()
    with path.open("a") as f:
        for e in events:
            line = json.dumps(e, ensure_ascii=False)
            if line not in have:
                f.write(line + "\n")
                have.add(line)
    return [json.loads(l) for l in path.open()] if path.exists() else events


def _eid(e: dict) -> str:
    # stable across nights (a position would change as entries are added: readers would see old ones as new)
    return f"tag:atviri-teises-aktai.lt,{e['day']}:{e['act']}:{e.get('article') or e.get('kind', 'act')}"


def _atom(title: str, self_url: str, site_url: str, entries: list[dict], updated: str) -> str:
    items = []
    for e in entries:
        e = dict(e, text=re.sub(r"(\d)\^(\d+)", lambda m: m[1] + m[2].translate(SUP), e["text"]))  # older entries: "48^1"
        eid = _eid(e)
        items.append(f"<entry><id>{escape(eid)}</id><title>{escape(e['text'])}</title><updated>{e['day']}T00:00:00Z</updated>"
                     f"<link href=\"{escape(e.get('url') or site_url)}\"/><summary>{escape(e['text'])}</summary></entry>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
            f"<title>{escape(title)}</title><id>{escape(self_url)}</id><updated>{updated}T00:00:00Z</updated>"
            f"<link rel=\"self\" href=\"{escape(self_url)}\"/><link href=\"{escape(site_url)}\"/>"
            f"<author><name>Atviri teisės aktai</name></author>{''.join(items)}</feed>\n")


def _newest(all_events: list[dict], base: str) -> list[dict]:
    """Newest first, one per id: older logs hold a day's events twice or thrice (re-runs); the last wins."""
    once: dict[str, dict] = {}
    for e in all_events:
        if e.get("url"):  # on this site's address: a local build stores its own (2026-11-02: 136 http://127.0.0.1 links)
            u = urllib.parse.urlsplit(e["url"])
            e = dict(e, url=base + u.path + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else ""))
        once[_eid(e)] = e
    return sorted(once.values(), key=lambda e: e["day"], reverse=True)


def digest(all_events: list[dict], base: str, day: str, acts: dict[str, dict], days: int, only: set[str] | None = None, per_act: int = 40) -> list[dict]:
    """The events of the last `days` days for a page: per day, per act (those with a new text first), what changed. `acts`:
    abbr -> {name, url}. An act no longer on the site is left out."""
    since = (dt.date.fromisoformat(day) - dt.timedelta(days=days - 1)).isoformat()
    by_day: dict[str, dict[str, list[dict]]] = {}
    for e in _newest(all_events, base):
        if e["day"] >= since and e["act"] in acts and (only is None or e["act"] in only):
            by_day.setdefault(e["day"], {}).setdefault(e["act"], []).append(e)
    out = []
    for d in sorted(by_day, reverse=True):
        rows, added = [], []
        for abbr, evs in by_day[d].items():
            info = acts[abbr]
            added += [{"name": info["name"], "url": info["url"]} for e in evs if e["kind"] == "act_added"]
            items = []
            for e in evs:
                if e["kind"] == "act_added":
                    continue
                head, _, what = e["text"].partition(": ")
                m = re.search(r"\S+ (?:str\.|p\.)$", head)  # "4 p." of "… tvarkos aprašo 4 p.": the act is named above
                items.append({"url": e.get("url"), "label": m.group(0) if m else head, "what": what or head, "text": "tekstas" in what})
            if items:
                items.sort(key=lambda i: not i["text"])  # (stable: in the act's order)
                n_text = sum(i["text"] for i in items)
                rows.append({"name": info["name"], "url": info["url"], "atom": info["url"] + "atom.xml", "n": len(items), "n_text": n_text,
                             "n_mark": len(items) - n_text, "entries": items[:per_act], "more": max(0, len(items) - per_act)})
        rows.sort(key=lambda r: (-r["n_text"], r["name"]))
        out.append({"day": d, "acts": rows, "added": sorted(added, key=lambda x: x["name"])})
    return out


def write(out: pathlib.Path, base: str, all_events: list[dict], act_dirs: dict, day: str, areas: list[dict] | None = None) -> int:
    """/atom.xml (site-wide, newest 200), /ta/<tar>/atom.xml per act (newest 100) and /sritis/<area>/atom.xml per area
    (scope/areas.yaml: its acts' changes, newest 200; one feed for a field instead of an act's each)."""
    newest = _newest(all_events, base)
    for g in areas or []:
        p = out / "sritis" / (g.get("slug") or "-") / "atom.xml"
        if g.get("slug") and p.parent.exists():
            acts = set(g["acts"])
            p.write_text(_atom(f"{g['name']}: pakeitimai", f"{base}/sritis/{g['slug']}/atom.xml", f"{base}/sritis/{g['slug']}/",
                               [e for e in newest if e["act"] in acts][:200], day))
    (out / "atom.xml").write_text(_atom("Atviri teisės aktai: pakeitimai", f"{base}/atom.xml", f"{base}/", newest[:200], day))
    n = 1
    for abbr, (path, name) in act_dirs.items():  # path: "ta/<TAR>/" (source.act_path)
        mine = [e for e in newest if e["act"] == abbr][:100]
        p = out / path / "atom.xml"
        if p.parent.exists():
            p.write_text(_atom(f"{name}: pakeitimai", f"{base}/{path}atom.xml", f"{base}/{path}", mine, day))
            n += 1
    return n
