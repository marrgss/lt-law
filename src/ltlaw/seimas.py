"""Seimas votes (D-054, proof of concept): the site's JSON for the Worker's vote tools, from bin/fetch_votes.py's data.

out/api/v1/seimas/
  meta.json              terms, counts, freshness, what the data lack, the result codes
  <term>/index.json      {record: the lrs.lt record URL to which a vote's `r` is added, items: [{t: the agenda item,
                         draft, law, act}], votes: [{i, id, at, s (sitting), it (item), q, qa (the alternative), ty
                         (type), f, a, ab (for, against, abstain), v (verdict), r, ind (the individual votes' file block,
                         or why there are none), bare (no agenda item or record link in the open data; 1: nor totals,
                         2: the totals counted from the individual votes, 3: the totals in the data)}]}
                         oldest first
  <term>/v/<block>.json  {vote id: {"for": [MP index], "against": [...], "abstain": [...]}}, BLOCK votes a file
  <term>/mps.json        [{i, id (the term's own), person (asmens_id: the same in every term), name, votes, first, last}]
  <term>/mp/<i>.json     [[vote index position, 1|2|3], ...]: the MP's votes, oldest first

Nothing is interpreted: the agenda item and the question are the data's own words; the draft ("XVP-1885") and the law
number ("XIV-1381") are read from the agenda item, the act on the site by that number, or by its name in the genitive
at the item's start when no number matches ("Darbo kodekso 138 straipsnio pakeitimo …": codes are named without one).
"""
from __future__ import annotations

import json
import pathlib
import re

BLOCK = 200
CHOICE = {1: "for", 2: "against", 3: "abstain"}
RECORD = "https://www.lrs.lt/sip/portal.show?p_r=37067&p_k=1&p_a=sale_klaus_detaliau&p_kl_stad_id="  # + a vote's `r`
RE_DRAFT = re.compile(r"\(Nr\.\s*([IVXL]*P-\d+(?:\([^)]*\))?)\)")
RE_LAW = re.compile(r"\bNr\.\s*([IVXL]+-\d+)\b")
LACKS = ("Factions are not in the open data. An MP's id is the term's own; `person` (asmens_id) is the same in every term. Decisions by consensus (\"Pritarta bendru sutarimu\") and secret ballots have "
         "no individual votes. MPs who did not vote are not listed, so absent and present-but-not-voting look the same. "
         "Whether a decision passed depends on the MPs present (registered) at the vote, which the data lack: a law needs the "
         "votes of a majority of the MPs present (Konstitucijos 69 str., Seimo statuto 113 str.), so a majority of the votes "
         "cast can be \"nepritarta\". Individual votes are published a few days after the totals. Some votes (`without_item` a term: 12% of terms 9 and 10) are in the open data without "
         "their agenda item and record link, some without totals too (`bare`): they cannot be found by words, draft or act, only by date (the sitting's transcript on lrs.lt says what was voted on). \"verdict\" is the data's own value (\"P\" is not "
         "explained by the source).")


def _num(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def build(data: pathlib.Path, out: pathlib.Path, scope: list[dict], acts: list[dict]) -> dict:
    """Write out/api/v1/seimas/ for every term in data/seimas/; returns the counts."""
    by_abbr = {a.get("abbr"): a for a in acts}
    by_number = {}
    for s in scope:
        a = by_abbr.get(s.get("abbr"))
        if s.get("number") and a and not s["dokumento_id"].startswith("EU."):
            by_number.setdefault(s["number"], a)
    # the acts named without a number ("Darbo kodekso 138 straipsnio pakeitimo …"): by the genitive the item starts with
    gens = sorted(((a["genitive"].lower(), a) for a in acts if a.get("genitive") and len(a["genitive"]) >= 10),
                  key=lambda x: -len(x[0]))

    def by_name(item: str):
        t = re.sub(r"^(lietuvos respublikos\s+)", "", item.lower().strip("„“\" "))
        return next((a for g, a in gens if t.startswith(g) and re.match(r"[\s,]|$", t[len(g):len(g) + 1] or "")), None)

    root = out / "api" / "v1" / "seimas"
    terms, report = [], {}
    for td in sorted((p for p in data.glob("*") if p.is_dir() and p.name.isdigit()), key=lambda p: int(p.name)):
        term = int(td.name)
        votes = sorted(json.loads((td / "votes.json").read_text()), key=lambda v: v.get("balsavimo_pradzia") or "")
        ind = json.loads((td / "individual.json").read_text())
        names = json.loads((td / "mps.json").read_text())
        fetched = json.loads((td / "fetched.json").read_text())
        persons = json.loads((td / "persons.json").read_text()) if (td / "persons.json").exists() else {}
        mp_ids = sorted(names, key=lambda k: names[k])
        mpi = {k: n for n, k in enumerate(mp_ids)}
        newest_ind = fetched.get("newest_individual") or ""
        index, blocks, per_mp, mismatch, items, item_no = [], {}, {k: [] for k in mp_ids}, [], [], {}
        for pos, v in enumerate(votes):
            item = v.get("darb_klausimas") if v.get("darb_klausimas") not in (None, "None") else ""
            draft = (m.group(1) for m in [RE_DRAFT.search(item)] if m)
            law = next((x for x in RE_LAW.findall(item)), None)
            act = (by_number.get(law) if law else None) or (by_name(item) if item else None)
            rows = ind.get(v["balsavimo_id"])
            if rows:
                b = pos // BLOCK
                choices = {"for": [], "against": [], "abstain": []}
                for mp, r in rows:
                    if r in CHOICE:
                        choices[CHOICE[r]].append(mpi[mp])
                        per_mp[mp].append([pos, r])
                blocks.setdefault(b, {})[v["balsavimo_id"]] = choices
                counted = [len(choices["for"]), len(choices["against"]), len(choices["abstain"])]
                if not v.get("bare") and counted != [_num(v.get("uz")) or 0, _num(v.get("pries")) or 0, _num(v.get("susilaike")) or 0]:
                    mismatch.append(v["balsavimo_id"])
                why = b
            elif v.get("balsavimo_tipas") == "Pritarta bendru sutarimu":
                why = "consensus"
            elif v.get("balsavimo_tipas") == "Slaptas":
                why = "secret"
            elif (v.get("balsavimo_pradzia") or "") > newest_ind:
                why = "not published yet"
            else:
                why = "none in the data"
            tot = [_num(v.get("uz")), _num(v.get("pries")), _num(v.get("susilaike"))]
            bare = None
            if v.get("bare"):  # no agenda item or record link; the totals too in some (term 10), counted then if it can be
                bare = 3 if tot[0] is not None else 2 if rows else 1
                if bare == 2:
                    tot = [len(choices["for"]), len(choices["against"]), len(choices["abstain"])]
            if item not in item_no:
                item_no[item] = len(items)
                items.append({k: x for k, x in {"t": item, "draft": next(draft, None), "law": law,
                                                "act": act["key"] if act else None}.items() if x})
            rec = re.sub(r".*[?&]p_kl_stad_id=", "", v.get("suvestine") or "") or None
            e = {"i": pos, "id": v["balsavimo_id"], "at": (v.get("balsavimo_pradzia") or "")[:16],
                 "s": f"{v.get('posedzio_tipas') or ''} Nr. {v.get('posedzio_nr') or ''}".strip() if v.get("posedzio_nr") not in (None, "None") else None,
                 "it": item_no[item], "q": v.get("balsavimo_klausimas"), "qa": v.get("balsavimo_klausimas_alt"),
                 "ty": v.get("balsavimo_tipas"), "f": tot[0], "a": tot[1], "ab": tot[2], "v": v.get("verdiktas"),
                 "r": rec, "ind": why, "bare": bare}
            index.append({k: x for k, x in e.items() if x is not None and x != "None"})
        d = root / str(term)
        (d / "v").mkdir(parents=True, exist_ok=True)
        (d / "mp").mkdir(parents=True, exist_ok=True)
        (d / "index.json").write_text(json.dumps({"record": RECORD, "items": items, "votes": index}, ensure_ascii=False,
                                                 separators=(",", ":")))
        for b, x in blocks.items():
            (d / "v" / f"{b}.json").write_text(json.dumps(x, separators=(",", ":")))
        # the first and last vote each MP cast: MPs leave and join during a term (Mažylis to 2024-12, Masiulis from
        # 2026-10); a vote outside them is no absence
        span = lambda k: ([index[per_mp[k][0][0]]["at"], index[per_mp[k][-1][0]]["at"]] if per_mp[k] else [None, None])  # noqa: E731
        (d / "mps.json").write_text(json.dumps([{"i": n, "id": k, "person": persons.get(k), "name": names[k], "votes": len(per_mp[k]),
                                                 "first": span(k)[0], "last": span(k)[1]}
                                                for n, k in enumerate(mp_ids)], ensure_ascii=False))
        for n, k in enumerate(mp_ids):
            (d / "mp" / f"{n}.json").write_text(json.dumps(per_mp[k], separators=(",", ":")))
        terms.append({"term": term, "votes": len(index), "first": index[0]["at"] if index else None,
                      "last": index[-1]["at"] if index else None, "individual_until": newest_ind[:16],
                      "mps": len(mp_ids), "block": BLOCK, "fetched": fetched.get("fetched"),
                      "without_item": sum(1 for x in index if x.get("bare"))})
        report[term] = {"votes": len(index), "with_individual": sum(1 for x in index if isinstance(x["ind"], int)),
                        "linked_to_acts": sum(1 for x in index if items[x["it"]].get("act")), "items": len(items), "counts_differ": mismatch[:20],
                        "counts_differ_n": len(mismatch), "files": 3 + len(blocks) + len(mp_ids)}
    (root).mkdir(parents=True, exist_ok=True)
    (root / "meta.json").write_text(json.dumps({
        "terms": terms, "choices": {"1": "for (už)", "2": "against (prieš)", "3": "abstain (susilaikė)"},
        "lacks": LACKS, "source": "Lietuvos Respublikos Seimo kanceliarija, data.gov.lt datasets/gov/lrsk/balsavimai, CC BY 4.0",
        "status": "proof of concept (D-054): not on the site"}, ensure_ascii=False, indent=1))
    return report
