#!/usr/bin/env python3
"""Seimas votes (D-054, proof of concept): one term's votes and individual votes from data.gov.lt.

Usage: uv run bin/fetch_votes.py [--term N] [--out data/seimas]

Reads the Seimas Chancellery's open data (datasets/gov/lrsk/balsavimai, CC BY 4.0) into data/seimas/<term>/:
  votes.json       every vote of the term: sitting, agenda item, what was voted on, for/against/abstain, result, record;
                   with `bare: true` the votes the open data hold without term, agenda item and totals (taken by date)
  individual.json  {vote id: [[MP id, 1 for | 2 against | 3 abstained], …]}: MPs who didn't vote have no entry
  mps.json         {MP id: name as printed}: an MP id is the term's own
  persons.json     {MP id: asmens_id}: the same person in every term (Bilotaitė, Šimonytė: checked 2026-11-11)
  fetched.json     when, how many, the newest vote and the newest individual vote (they lag the totals by days)
Without --term: the newest term. A full fetch of a term is ~25 requests (368,000 individual votes in term 10); pages of
20,000 rows, a pause between requests (2026-11-15: 162 s from Lithuania). The nightly runs it for the newest term when
data/seimas is in the state asset (bin/nightly.py); earlier terms are closed and kept there.
"""
import argparse
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.parse
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ltlaw import source  # noqa: E402

BASE = (source.RELAY or "https://get.data.gov.lt") + "/datasets/gov/lrsk/balsavimai"
PAGE = 20000


def rows(model: str, q: str, keep: tuple[str, ...]) -> list[dict]:
    """Every row of a query, page by page (data.gov.lt's `_page.next`)."""
    out, token = [], None
    fresh = f'_id!="{uuid.uuid4()}"'  # data.gov.lt serves a cached answer to a repeated URL (memory: stale cache)
    while True:
        qq = f"{fresh}&{q}&limit({PAGE})" + (f'&page("{token}")' if token else "")
        d = source._get(f"{BASE}/{model}?" + urllib.parse.quote(qq, safe='()&=,"_-<>!/'), timeout=300)
        got = d.get("_data", [])
        out += [{k: r.get(k) for k in keep} for r in got]
        token = (d.get("_page") or {}).get("next")
        print(f"  {model}: {len(out)}", flush=True)
        if not got or not token or len(got) < PAGE:
            return out
        time.sleep(2)


VOTE_KEYS = ("balsavimo_id", "kadencijos_id", "sesijos_id", "sesija", "posedzio_tipas", "posedzio_nr", "balsavimo_pradzia",
             "balsavimo_pabaiga", "klausimo_nr", "darb_klausimas", "balsavimo_tipas", "balsavimo_klausimas",
             "balsavimo_klausimas_alt", "suvestine", "uz", "pries", "susilaike", "verdiktas")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--term", type=int, help="kadencijos_id (10: 2024–2028); default the newest")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("data/seimas"))
    a = ap.parse_args()
    # the newest term: the newest vote's; that sort over all 76,000 votes is the slowest request (it timed out on a slow
    # day, 2026-11-12), so then the newest term already fetched
    have = [int(p.name) for p in a.out.glob("*") if p.name.isdigit()]
    try:
        last = source._get(f"{BASE}/Balsavimas?" + urllib.parse.quote(
            f'_id!="{uuid.uuid4()}"&kadencijos_id!=null&sort(-balsavimo_pradzia)&limit(1)', safe='()&=,"_-<>!/'),
            tries=2 if have else 4)["_data"]
        newest = int(last[0]["kadencijos_id"])
    except (OSError, TimeoutError):
        if not have:
            raise
        newest = max(have)
        print(f"the newest vote not read: term {newest}, the newest fetched", file=sys.stderr)
    term = a.term or newest
    votes = rows("Balsavimas", f'kadencijos_id="{term}"', VOTE_KEYS)
    # votes the open data hold without their term, agenda item and totals (12% of term 10: 657, 2026-11-11), some with
    # individual votes: taken in by date, inside the term's first and last vote (the newest term: from its first)
    span = sorted(v["balsavimo_pradzia"] for v in votes if v.get("balsavimo_pradzia"))
    if span:
        q = f'kadencijos_id=null&balsavimo_pradzia>="{span[0]}"' + (f'&balsavimo_pradzia<="{span[-1]}"' if term != newest else "")
        bare = rows("Balsavimas", q, VOTE_KEYS)
        for v in bare:
            v["kadencijos_id"], v["bare"] = str(term), True
        votes += bare
    # (no select(): with it data.gov.lt returns one page and no `_page.next`, 2026-11-11)
    ind = rows("IndividualusBalsavimai", f'kadencijos_id="{term}"',
               ("balsavimo_id", "seimo_nario_id", "asmens_id", "seimo_narys", "rezultatas"))
    by_vote: dict[str, list] = {}
    mps: dict[str, str] = {}
    persons: dict[str, str] = {}  # MP id (the term's own) -> asmens_id (the same person in every term)
    for r in ind:
        by_vote.setdefault(r["balsavimo_id"], []).append([r["seimo_nario_id"], int(r["rezultatas"])])
        mps[r["seimo_nario_id"]] = r["seimo_narys"]
        if r.get("asmens_id"):
            persons[r["seimo_nario_id"]] = r["asmens_id"]
    d = a.out / str(term)
    # a short answer must not replace a full one (data.gov.lt has ended paged answers early): the nightly keeps
    # yesterday's files and warns; votes and individual votes only grow during a term
    # (a correction may drop a few rows: 0.5% allowed)
    old = json.loads((d / "fetched.json").read_text()) if (d / "fetched.json").exists() else {}
    if len(votes) < 0.995 * old.get("votes", 0) or len(ind) < 0.995 * old.get("individual_rows", 0):
        raise SystemExit(f"term {term}: {len(votes)} votes and {len(ind)} individual votes, fewer than the "
                         f"{old.get('votes')} and {old.get('individual_rows')} fetched {old.get('fetched')}: kept those")
    d.mkdir(parents=True, exist_ok=True)
    votes.sort(key=lambda v: v["balsavimo_pradzia"] or "")
    (d / "votes.json").write_text(json.dumps(votes, ensure_ascii=False))
    (d / "individual.json").write_text(json.dumps(by_vote, ensure_ascii=False))
    (d / "mps.json").write_text(json.dumps(mps, ensure_ascii=False, indent=0))
    (d / "persons.json").write_text(json.dumps(persons, indent=0))
    newest_ind = max((v["balsavimo_pradzia"] for v in votes if v["balsavimo_id"] in by_vote), default=None)
    meta = {"term": term, "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "votes": len(votes),
            "individual_rows": len(ind), "votes_with_individual": len(by_vote), "mps": len(mps),
            "votes_without_item": sum(1 for v in votes if v.get("bare")),
            "newest_vote": votes[-1]["balsavimo_pradzia"] if votes else None, "newest_individual": newest_ind,
            "source": "data.gov.lt datasets/gov/lrsk/balsavimai (Lietuvos Respublikos Seimo kanceliarija, CC BY 4.0)"}
    (d / "fetched.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
