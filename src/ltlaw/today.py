"""Find the text that applies TODAY for articles whose stored text doesn't (D-009, NEXT item 1).

The stored consolidation (Dokumentas) is one version per act and is often a future one. For an
article flagged pending/outdated/unknown we look for today's text in other official
consolidations, in order:
  1. our own archive of earlier Dokumentas snapshots (grows nightly);
  2. the Chancellery's frozen Suvestine consolidations (prepared up to 2025-05), version valid today;
  3. first of all, a whole-act new wording in force that no consolidation has yet: the amending act's own
     attached text ("PATVIRTINTA … (… nutarimo Nr. 260 redakcija)", VGON 2026-05-01; B47).
A candidate text is used only if the same currency rules (ltlaw.currency.assess) say that article
is current in it. We never edit or assemble text: every text is a whole official text, as published.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import urllib.error
from dataclasses import dataclass

from . import source
from .currency import ActStatus, Laws, _candidate_laws, assess
from .parse import Act, Article, parse


def _prepared_before_changes(cand: Article, label: str, prepared: str | None, laws: Laws, day: str) -> bool:
    """False if a law amending one of the candidate's amending laws was published after the candidate
    was prepared and already applies (the candidate can't contain it, e.g. MATĮ 9 / XV-359)."""
    if not prepared:
        return True
    for r in cand.all_refs():
        for d in laws.amended_by(r.nr):
            if (d.get("paskelbta_tar") or "") > prepared[:10]:
                law = laws.get(d["atv_dok_nr"])
                dates = law.dates_for(label) if law else {d.get("isigalioja")} - {None}
                if not dates or min(dates) <= day:
                    return False
    return True


def _stale_for_today(act: Act, other: Act, prepared: str | None, laws: Laws, day: str) -> bool:
    """The candidate was prepared before a whole-act rewrite that applies by `day` (NTMĮ: a Suvestine
    version prepared in 2024 for 2026-05-01, while XV-344, adopted 2025-06-26, rewrote the act from
    2026-01-01): nothing in it can be today's text."""
    for when, nr in act.rewrites + other.rewrites:
        adopted = (laws.meta.get(nr) or {}).get("priimtas") or when
        later = adopted > prepared[:10] if prepared else when > (other.version_from or "0000")
        if when <= day and later:
            return True
    return False


def _later_law_targets(label: str, scope_act: dict, act: Act, prepared: str | None, laws: Laws, day: str, path=()) -> bool:
    """A law naming the act, adopted after the candidate was prepared and in force by `day`, changes `label`
    (by name, or by replacing or repealing its chapter or section: GTK XV-390, fifth section)."""
    from .currency import _candidate_laws, _in_part, _matches
    if not prepared:
        return False
    key = (scope_act.get("dokumento_id"), act.version_from, day, tuple(sorted(source.PINNED.items())))
    if key not in _LATER:
        _LATER[key] = _candidate_laws(act, scope_act, laws, day)
    for law, d in _LATER[key]:
        if (d.get("priimtas") or "") > prepared[:10] and any(x <= day for x in law.dates_for(label)) and \
                (any(_matches(t, label) for ts in law.targets.values() for t in ts)
                 or any(_in_part(path, c) for chs in law.chapters.values() for c in chs)):
            return True
    return False


_LATER: dict = {}


@dataclass
class TodayText:
    article: Article
    origin: str          # "Suvestine" | "archive" | "new wording"
    version_from: str | None
    version_to: str | None
    ref: str             # suvestines_id or snapshot date
    status: object = None  # find_today_only: the article's status in the candidate
    issuer: str | None = None    # a new wording's issuer and type in the genitive: "Lietuvos Respublikos energetikos
    kind_gen: str | None = None  # ministro", "įsakymo" (D-033); None: "Vyriausybės", "nutarimo"


def _issuer(scope_act: dict) -> tuple[str | None, str | None]:
    if not scope_act.get("issuer"):
        return None, None  # the Government
    return scope_act["issuer"], ("įsakymo" if scope_act.get("kind") == "Įsakymas" else "nutarimo")


def _suvestine_valid_on(doc: str, day: str) -> dict | None:
    """The frozen Suvestine version valid on `day`. Chosen from the compact version list
    (data/state/suvestine_scope.jsonl, from bin/compact_state.py); its text is fetched once and
    cached by version id (the table is frozen). Falls back to a direct API query without the list."""
    meta = source.STATE / "suvestine_scope.jsonl"
    if meta.exists():
        rows = [json.loads(l) for l in meta.open()]
        rows = [r for r in rows if r["dokumento_id"] == doc and (r["galioja_nuo"] or "")[:10] <= day
                and (not r.get("galioja_iki") or day <= r["galioja_iki"][:10])]
        if not rows:
            return None
        rows = source.dedupe_versions(rows, "latest")  # a re-prepared range: the newer preparation (B51)
        r = max(rows, key=lambda r: (r["galioja_nuo"], r.get("suv_duom_atnaujinimas") or ""))
        path = source.DATA / "suvestine" / doc / f"{r['suvestines_id']}.json"
        if not path.exists():
            # texts are fetched once and kept (the state); a night with many new versions spends at most
            # FETCH_BUDGET_S on them, the rest stays flagged until the next night (the refreshed lists, B50)
            if _FETCH["spent"] > FETCH_BUDGET_S:
                _FETCH["skipped"] += 1
                return None
            t = time.time()
            try:
                while True:
                    try:
                        got = source.query("Suvestine", f'select(suvestines_id,galioja_nuo,galioja_iki,suv_duom_atnaujinimas,tekstas_lt)'
                                                        f'&dokumento_id="{doc}"&suvestines_id="{r["suvestines_id"]}"&limit(1)')
                        break
                    except urllib.error.HTTPError as e:
                        # 429 after a few big texts, for minutes: wait within the budget (2026-11-02: all 51 skipped)
                        if e.code != 429 or _FETCH["spent"] + time.time() - t + RATE_WAIT_S > FETCH_BUDGET_S:
                            raise
                        time.sleep(RATE_WAIT_S)
            except Exception:
                _FETCH["skipped"] += 1
                return None  # not fetched tonight: no text from it, the article stays flagged
            finally:
                _FETCH["spent"] += time.time() - t
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(got[0] if got else None, ensure_ascii=False))
        r = json.loads(path.read_text())
        return r if r and r.get("tekstas_lt") else None
    path = source.DATA / "suvestine" / doc / f"valid-{day}.json"
    if not path.exists():
        r = source.fetch_suvestine_newest(doc, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(r, ensure_ascii=False))
    r = json.loads(path.read_text())
    if not r:
        return None
    if not ((r["galioja_nuo"] or "")[:10] <= day and (not r.get("galioja_iki") or day <= r["galioja_iki"][:10])):
        return None  # newest Suvestine version isn't valid today: nothing to offer
    return r


def prefetch_upcoming(doc_ids: list[str], day: str, horizon_days: int = 45, budget_s: int = 300, gap_s: float = 10) -> dict:
    """Texts of the versions that take effect within `horizon_days`, soonest first, a few a night: the Chancellery
    prepares them weeks ahead (110 of 117 versions from 2026-10 over 30 days ahead), so the day they take effect needs
    no burst of downloads. data.gov.lt answers 429 for minutes after a few big texts (2026-11-02: all 51 of 11-01's
    texts skipped): paced, a 429 waited out within the budget."""
    meta = source.STATE / "suvestine_scope.jsonl"
    if not meta.exists():
        return {"fetched": 0, "left": 0}
    end = (dt.date.fromisoformat(day) + dt.timedelta(days=horizon_days)).isoformat()
    ids = set(doc_ids)
    by_doc: dict[str, list[dict]] = {}
    for l in meta.open():
        r = json.loads(l)
        if r["dokumento_id"] in ids and day < (r["galioja_nuo"] or "")[:10] <= end:
            by_doc.setdefault(r["dokumento_id"], []).append(r)
    todo = sorted((r for rows in by_doc.values() for r in source.dedupe_versions(rows, "latest")
                   if not (source.DATA / "suvestine" / r["dokumento_id"] / f"{r['suvestines_id']}.json").exists()),
                  key=lambda r: r["galioja_nuo"])
    fetched, t0 = 0, time.time()
    for r in todo:
        if source.SUVESTINE_DOWN or time.time() - t0 > budget_s:
            break
        try:
            got = source.query("Suvestine", f'select(suvestines_id,galioja_nuo,galioja_iki,suv_duom_atnaujinimas,tekstas_lt)'
                                            f'&dokumento_id="{r["dokumento_id"]}"&suvestines_id="{r["suvestines_id"]}"&limit(1)')
        except urllib.error.HTTPError as e:
            if e.code != 429 or time.time() - t0 + RATE_WAIT_S > budget_s:
                break
            time.sleep(RATE_WAIT_S)
            continue  # this one again next night (or later in the list)
        except Exception:
            break
        path = source.DATA / "suvestine" / r["dokumento_id"] / f"{r['suvestines_id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(got[0] if got else None, ensure_ascii=False))
        fetched += 1
        time.sleep(gap_s)
    return {"fetched": fetched, "left": len(todo) - fetched}


def _with_header(r: dict) -> str:
    t = r["tekstas_lt"] or ""
    if source.has_consolidation(t):
        return t
    head = f"Suvestinė redakcija nuo {r['galioja_nuo'][:10]}" + (f" iki {r['galioja_iki'][:10]}" if r.get("galioja_iki") else "")
    return head + "\n" + t


_CANDS: dict = {}
FETCH_BUDGET_S = 600
RATE_WAIT_S = 60
_FETCH = {"spent": 0.0, "skipped": 0}  # per process (one nightly run): seconds spent fetching, versions left out


def candidates_for(doc: str, scope_act: dict, laws: Laws, day: str) -> list[tuple[str, str, Act, ActStatus, str | None]]:
    """Other official consolidations to try, with their statuses for `day` (memoised per run)."""
    key = (doc, scope_act.get("document"), day, tuple(sorted(source.PINNED.items())))
    if key not in _CANDS:
        _CANDS[key] = _candidates_for(doc, scope_act, laws, day)
    return _CANDS[key]


def _new_wordings(doc: str, scope_act: dict, laws: Laws, day: str) -> list[tuple[str, str, Act, ActStatus, str | None]]:
    """Whole-act new wordings in force by `day` and newer than the stored text: the amending act's text read as the
    act (its attached "PATVIRTINTA … redakcija" document), dated from the rewrite's entry into force."""
    stored = parse(source.act_text(doc)[0], scope_act.get("document"))
    out = []
    for law, d in _candidate_laws(stored, scope_act, laws, day):
        w = law.rewrite_date()
        if not w or w > day or w <= (stored.version_from or "0000"):
            continue
        p = source.DATA / "amending" / (d.get("dokumento_id") or "?") / "fixed.json"
        if not p.exists():
            continue
        row = dict(json.loads(p.read_text())["row"], galioja_nuo=w, galioja_iki=None)
        if not scope_act.get("adopted"):  # a law: the new act is quoted inside the amending law's own article (B53)
            q = _quoted_new_wording(row.get("tekstas_lt") or "", law.rewrite_own)
            if not q:
                continue
            row["tekstas_lt"] = q
        elif not re.search(r"\(\s*[^()]{0,200}?(?:nutarimo|įsakymo)\s+Nr\.\s*" + re.escape(law.nr.rsplit("/", 1)[0]) + r"\s+redakcija\s*\)",
                         re.sub(r"<[^>]+>", " ", row.get("tekstas_lt") or "")):
            continue  # not the whole text attached as the act's new wording
        try:
            a = parse(_with_header(row), scope_act.get("document"))
        except Exception:
            continue
        if a.version_from != w or len(a.main.articles) < len(stored.main.articles) / 2:
            continue
        a.prepared = d.get("paskelbta_tar")
        out.append(("new wording", law.nr, a, assess(a, scope_act, laws, day), d.get("paskelbta_tar")))
    return out


def _quoted_new_wording(text: str, own: int | None) -> str | None:
    """The act set out anew inside an amending law: its article `own` ("3 straipsnis. … įstatymo Nr. XII-2702 nauja
    redakcija. Pakeisti … ir jį išdėstyti taip: „LIETUVOS RESPUBLIKOS … ĮSTATYMAS … “.") up to the closing quote
    that is followed by the law's next own article or its signature (EVEDĮ XV-237, B53)."""
    if own is None:
        return None
    h = re.search(rf"(?m)^\s*{own} straipsnis\.[^\n]*nauja redakcija", text)
    if not h:
        return None
    o = text.find("„", h.end())
    if o < 0 or not re.match(r"\s*[A-ZĄČĘĖĮŠŲŪŽ]{4}", text[o + 1:o + 40]):
        return None  # not a whole quoted act
    for m in re.finditer(r"“\s*\.", text[o:]):
        rest = text[o + m.end():].lstrip()
        if re.match(rf"{own + 1} straipsnis\.", rest) or rest.startswith("Skelbiu") or not rest:
            q = text[o + 1:o + m.start()]
            # its annexes follow the last article with no signature between: cut them, or the heading
            # ("Lietuvos Respublikos … įstatymo priedas") is read as the last article's text (EVEDĮ 27)
            an = re.search(r"(?m)^[^\n]*(?:įstatymo|kodekso) priedas\s*$", q)
            if an:
                cut = q.rfind("\n\n", 0, an.start())
                q = q[:cut if cut > 0 else an.start()]
            return q
    return None


def _candidates_for(doc: str, scope_act: dict, laws: Laws, day: str) -> list[tuple[str, str, Act, ActStatus, str | None]]:
    out = _new_wordings(doc, scope_act, laws, day)
    snaps = sorted((source.DATA / "dokumentas" / doc).glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))
    seen_versions = set()
    for p in reversed(snaps[:-1]):  # older snapshots of our own archive, newest first
        t = json.loads(p.read_text())["row"].get("tekstas_lt") or ""
        if not source.has_consolidation(t):
            continue
        a = parse(t, scope_act.get("document"))
        if a.version_from in seen_versions:
            continue
        seen_versions.add(a.version_from)
        a.prepared = p.stem  # fetched that day: prepared then or earlier
        out.append(("archive", p.stem, a, assess(a, scope_act, laws, day), p.stem))
    r = _suvestine_valid_on(doc, day)
    if r:
        a = parse(_with_header(r), scope_act.get("document"))
        a.prepared = r.get("suv_duom_atnaujinimas")  # a ruling published after it was prepared is not in it (B3)
        out.append(("Suvestine", r["suvestines_id"], a, assess(a, scope_act, laws, day), r.get("suv_duom_atnaujinimas")))
    return out


def _needed(reasons: list[str]) -> set[str]:
    """The laws an article's reasons name, as the references name them: a minister's order with its date since B88
    ("V-434/2016-04-01"), a joint order with all its numbers. Matched bare ("V-434"), no candidate's note could match
    them, and today's text was never found for the orders' points (HN71, 2026-11-21)."""
    return set(re.findall(r"\b([IVXL]+-\d+(?:/[A-Z][A-Z0-9]*-\d+)*(?:/\d{4}-\d{2}-\d{2})?|KT[\w()-]+/\d{4})", " ".join(reasons)))


def _consolidated(act_level: list[tuple[str, str]], origin: str, other: Act, prepared: str | None, laws: Laws) -> set[str]:
    """The act-level laws (no article targets we can read) that an official consolidation holds by what it is: a
    version valid from on or after the law's entry into force, prepared after the law was published, includes every
    amendment then in force. Its article notes name only the laws that changed that article, so a point the law left
    alone never lists it (HN71 1 p. in the 2017 consolidation names V-434, not V-257, which changed other points)."""
    if origin not in ("Suvestine", "archive") or not other.version_from or not prepared:
        return set()
    out = set()
    for nr, ent in act_level:
        pub = (laws.meta.get(nr) or {}).get("paskelbta_tar") or ""
        if pub and ent <= other.version_from[:10] and pub[:10] <= prepared[:10]:
            out.add(nr)
    return out


def find_today(act: Act, st: ActStatus, doc: str, scope_act: dict, laws: Laws, day: str) -> dict[str, TodayText]:
    """For each flagged article of `act`, today's text from another official consolidation, if any."""
    # an article uncertain because a part enters into force on a condition is left flagged: an older text can't
    # say whether the condition has been met since (SSĮ 59³: met on 2026-05-28, after the 2025 consolidation)
    # and an article the stored (newer) text says is repealed by today has no today's text: an older consolidation
    # that still shows it was made before the repeal was known or dated (GTK 33², repealed from 2024-12-02)
    flagged = [a.label for a in act.main.articles if st.articles[a.label].state != "current"
               and not any("sąlyg" in r for r in st.articles[a.label].reasons)
               and not (st.articles[a.label].state == "repealed" and (st.articles[a.label].applies_from or "0000") <= day)]
    if not flagged:
        return {}
    stored = {a.label: a for a in act.main.articles}
    act_level = [(m[1], m[2]) for f in st.act_level_flags if (m := re.match(r"(\S+) \(galioja nuo (\d{4}-\d{2}-\d{2})\)", f))]
    found: dict[str, TodayText] = {}
    for origin, ref, other, ost, prepared in candidates_for(doc, scope_act, laws, day):
        if _stale_for_today(act, other, prepared, laws, day):
            continue
        by = {a.label: a for a in other.main.articles}
        for label in flagged:
            if label in found or label not in by:
                continue
            s = ost.articles.get(label)
            if s is None or s.state != "current":
                continue
            cand = by[label].variant_on(day)
            if origin != "new wording" and not _no_newer_law_in_force(stored[label], cand, label, laws, day):
                continue  # (a new wording replaces every earlier change; later ones are assess()'s, above)
            # laws our stored text is flagged for (missing, in force) must already be in the candidate
            needed = _needed(st.articles[label].reasons) | {nr for nr, _ in act_level}
            if origin == "new wording":
                needed.discard(ref)  # the new wording is that law's own text: it doesn't list itself
            if needed - {r.nr for r in cand.all_refs()} - _consolidated(act_level, origin, other, prepared, laws):
                continue
            if not _prepared_before_changes(cand, label, prepared, laws, day):
                continue
            found[label] = TodayText(cand, origin, other.version_from, other.version_to, ref, None, *_issuer(scope_act))
            found[label].status = s  # its label in the candidate (carries a later adopted change, if any)
    return found


def _no_newer_law_in_force(newer: Article, older: Article, label: str, laws: Laws, day: str) -> bool:
    """The newer (stored) text lists every law that touched the article. Any law it lists that the
    older text lacks must take effect for this article only after `day`; otherwise the older text
    is missing a change already in force (e.g. an omnibus law whose title doesn't name the act)."""
    old_refs = {r.nr for r in older.all_refs()}
    for r in newer.all_refs():
        if r.nr in old_refs:
            continue
        law = laws.get(r.nr)
        dates = law.dates_for(label) if law else ({r.published or r.adopted} - {None})
        if not dates or min(dates) <= day:
            return False
    return True


def find_today_only(act: Act, doc: str, scope_act: dict, laws: Laws, day: str) -> list[TodayText]:
    """Articles in force today that the stored text doesn't have: a future version that repeals or
    renumbers them (VKĮ 21¹ before the new act of 2026-11-20), or a lagging version that lacks articles
    added since (PMĮ 30³). Taken from the first official consolidation valid today, and only if the
    currency rules call them current in it."""
    stored = {a.label for a in act.main.articles}
    for origin, ref, other, ost, prepared in candidates_for(doc, scope_act, laws, day):
        if not (other.version_from and other.version_from <= day and (not other.version_to or day <= other.version_to)):
            continue
        # useful when the stored text is a future version, or an older one than this candidate
        # (PMĮ 30³, SEAKĮ 11⁴: added by laws in force, missing from a stored text that lags)
        if not (act.version_from and act.version_from > day) and (other.version_from or "") <= (act.version_from or ""):
            continue
        if _stale_for_today(act, other, prepared, laws, day):
            continue
        out = []
        for a in other.main.articles:
            s = ost.articles.get(a.label)
            if a.label in stored or s is None or s.state == "repealed":
                continue  # repealed long ago (VKĮ 22²): not an article "in force today"
            cand = a.variant_on(day)
            if s.state == "current" and (not _prepared_before_changes(cand, a.label, prepared, laws, day)
                                         or _later_law_targets(a.label, scope_act, act, prepared, laws, day, cand.path)):
                s = type(s)("unknown", ["šio straipsnio tekste gali trūkti vėliau priimto pakeitimo"])
            x = TodayText(cand, origin, other.version_from, other.version_to, ref, None, *_issuer(scope_act))
            x.status = s  # the candidate's own label for today (flagged ones are shown flagged)
            out.append(x)
        return out
    return []

