"""Seimas votes (D-054, proof of concept): the JSON the Worker's vote tools read."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ltlaw import seimas  # noqa: E402


def vote(i, at, item, q, typ="Atviras", uz=None, pries=None, sus=None, **kw):
    return {"balsavimo_id": str(i), "kadencijos_id": "10", "balsavimo_pradzia": at, "darb_klausimas": item, "balsavimo_klausimas": q,
            "balsavimo_klausimas_alt": None, "balsavimo_tipas": typ, "posedzio_tipas": "Rytinis posėdis", "posedzio_nr": "7",
            "suvestine": f"https://www.lrs.lt/sip/portal.show?p_r=37067&p_k=1&p_a=sale_klaus_detaliau&p_kl_stad_id={i}",
            "uz": uz, "pries": pries, "susilaike": sus, "verdiktas": "pritarta", **kw}


def test_votes_linked_to_acts_with_every_mps_choice(tmp_path):
    d = tmp_path / "data" / "10"
    d.mkdir(parents=True)
    gpm = "Gyventojų pajamų mokesčio įstatymo Nr. IX-1007 17 straipsnio pakeitimo įstatymo projektas (Nr. XVP-1835(2))"
    dk = "Darbo kodekso 138 straipsnio pakeitimo įstatymo projektas (Nr. XVP-184)"
    votes = [vote(-3, "2026-11-10T16:41:00", dk, "dėl šio įstatymo priėmimo", uz="1", pries="1", sus="0"),
             vote(-1, "2026-11-05T10:00:00", gpm, "dėl pritarimo po pateikimo", uz="2", pries="0", sus="1"),
             vote(-2, "2026-11-05T10:01:00", gpm, "po pateikimo", typ="Pritarta bendru sutarimu"),
             {**vote(-4, "2026-11-06T09:00:00", "None", "po pateikimo", uz="None"), "bare": True, "darb_klausimas": "None",
              "suvestine": "https://www.lrs.lt/sip/portal.show?p_r=37067&p_k=1&p_a=sale_klaus_detaliau&p_kl_stad_id="},
             # (term 9's votes without an agenda item have their totals)
             {**vote(-5, "2026-11-06T09:01:00", "None", "dėl pritarimo po pateikimo", uz="63", pries="58", sus="7"), "bare": True,
              "darb_klausimas": "None"}]
    (d / "votes.json").write_text(json.dumps(votes))
    (d / "individual.json").write_text(json.dumps({"-1": [["a", 1], ["b", 1], ["c", 3]], "-4": [["a", 2]]}))
    (d / "mps.json").write_text(json.dumps({"a": "ONA ANAITĖ", "b": "BENAS BENAITIS", "c": "CEZARIS CEZARAITIS"}))
    (d / "persons.json").write_text(json.dumps({"a": "p1", "b": "p2"}))
    (d / "fetched.json").write_text(json.dumps({"newest_individual": "2026-11-06T09:00:00", "fetched": "2026-11-11"}))
    acts = [{"key": "gpmi", "abbr": "GPMĮ", "genitive": "gyventojų pajamų mokesčio įstatymo"},
            {"key": "dk", "abbr": "DK", "genitive": "darbo kodekso"}]
    scope = [{"abbr": "GPMĮ", "number": "IX-1007", "dokumento_id": "TAR.1"}, {"abbr": "DK", "number": "XII-2603", "dokumento_id": "TAR.2"}]
    rep = seimas.build(tmp_path / "data", tmp_path / "out", scope, acts)
    assert rep[10]["votes"] == 5 and rep[10]["with_individual"] == 2 and rep[10]["counts_differ_n"] == 0
    root = tmp_path / "out" / "api" / "v1" / "seimas" / "10"
    ix = json.loads((root / "index.json").read_text())
    v = {x["id"]: x for x in ix["votes"]}
    assert [x["id"] for x in ix["votes"]] == ["-1", "-2", "-4", "-5", "-3"]  # oldest first
    it = ix["items"][v["-1"]["it"]]
    assert (it["draft"], it["law"], it["act"]) == ("XVP-1835(2)", "IX-1007", "gpmi")  # by the number
    assert ix["items"][v["-3"]["it"]]["act"] == "dk"  # a code: by its name, no number in the item
    assert (v["-1"]["f"], v["-1"]["a"], v["-1"]["ab"], v["-1"]["ind"]) == (2, 0, 1, 0)
    assert v["-2"]["ind"] == "consensus" and "f" not in v["-2"]
    assert v["-3"]["ind"] == "not published yet"  # after the newest individual vote
    assert v["-4"]["bare"] == 2 and (v["-4"]["f"], v["-4"]["a"]) == (0, 1) and "r" not in v["-4"]  # counted, no record
    assert v["-5"]["bare"] == 3 and (v["-5"]["f"], v["-5"]["a"], v["-5"]["ab"]) == (63, 58, 7)  # the data's totals
    assert ix["record"] + v["-1"]["r"] == votes[1]["suvestine"]
    block = json.loads((root / "v" / "0.json").read_text())
    mps = json.loads((root / "mps.json").read_text())
    assert sorted(mps[i]["name"] for i in block["-1"]["for"]) == ["BENAS BENAITIS", "ONA ANAITĖ"]
    a = next(m for m in mps if m["name"] == "ONA ANAITĖ")
    assert json.loads((root / "mp" / f"{a['i']}.json").read_text()) == [[0, 1], [2, 2]]
    assert a["person"] == "p1"  # the same person in every term
    assert (a["first"], a["last"]) == ("2026-11-05T10:00", "2026-11-06T09:00")  # MPs come and go within a term
    c = next(m for m in mps if m["name"] == "CEZARIS CEZARAITIS")
    assert (c["first"], c["last"], c["votes"]) == ("2026-11-05T10:00", "2026-11-05T10:00", 1)
    meta = json.loads((tmp_path / "out" / "api" / "v1" / "seimas" / "meta.json").read_text())
    assert "Factions are not in the open data" in meta["lacks"] and "present (registered)" in meta["lacks"] and meta["terms"][0]["votes"] == 5 and meta["terms"][0]["without_item"] == 2


def test_the_vote_that_adopted_a_law_is_found_by_title_and_day_and_only_when_unique(tmp_path):
    from ltlaw.seimas import _title_core, adopted_votes
    assert _title_core("Lietuvos Respublikos išmokų vaikams įstatymo Nr. I-621 1 straipsnio pakeitimo įstatymas") == \
        _title_core("Išmokų vaikams įstatymo Nr. I-621 1 straipsnio pakeitimo įstatymo projektas (Nr. XVP-1023(2))")
    item = "Išmokų vaikams įstatymo Nr. I-621 1 straipsnio pakeitimo įstatymo projektas (Nr. XVP-1023(2))"
    vote = {"balsavimo_id": "-58955", "balsavimo_pradzia": "2026-05-14T12:01:00", "darb_klausimas": item,
            "balsavimo_klausimas": "dėl šio įstatymo priėmimo", "uz": "90", "pries": "0", "susilaike": "1",
            "verdiktas": "pritarta", "suvestine": "https://www.lrs.lt/sip/portal.show?p_r=37067&p_kl_stad_id=-101504"}
    other = dict(vote, balsavimo_id="-58950", balsavimo_klausimas="dėl pritarimo po svarstymo")  # not the adoption
    (tmp_path / "10").mkdir()
    (tmp_path / "10" / "votes.json").write_text(json.dumps([other, vote]))
    meta = {"XV-946": {"rusis": "Įstatymas", "priimtas": "2026-05-14",
                       "pavadinimas": "Lietuvos Respublikos išmokų vaikams įstatymo Nr. I-621 1 straipsnio pakeitimo įstatymas"},
            "XV-947": {"rusis": "Įstatymas", "priimtas": "2026-05-15",  # another day: not this vote
                       "pavadinimas": "Lietuvos Respublikos išmokų vaikams įstatymo Nr. I-621 1 straipsnio pakeitimo įstatymas"}}
    got = adopted_votes(tmp_path, meta)
    assert list(got) == ["XV-946"]
    assert {k: got["XV-946"][k] for k in ("at", "for", "against", "abstain", "term")} == \
        {"at": "2026-05-14", "for": 90, "against": 0, "abstain": 1, "term": 10}
    assert got["XV-946"]["record"].endswith("p_kl_stad_id=-101504")
    # two adoption votes for the same title that day (a re-vote): which one adopted it is not ours to guess
    (tmp_path / "10" / "votes.json").write_text(json.dumps([vote, dict(vote, balsavimo_id="-58956")]))
    assert adopted_votes(tmp_path, meta) == {}
    (tmp_path / "10" / "votes.json").write_text(json.dumps([dict(vote, verdiktas="nepritarta")]))
    assert adopted_votes(tmp_path, meta) == {}


def test_the_adoption_vote_reads_in_the_notes():
    from ltlaw.render import vote_text
    v = {"at": "2026-05-14", "for": 90, "against": 0, "abstain": 1, "record": "https://www.lrs.lt/x?a=1&b=2"}
    assert str(vote_text(v)) == ('; Seime <a href="https://www.lrs.lt/x?a=1&amp;b=2" title="Seimo balsavimas dėl įstatymo '
                                 'priėmimo 2026-05-14">už 90, prieš 0, susilaikė 1</a>')
    assert str(vote_text(dict(v, record=None))) == "; Seime už 90, prieš 0, susilaikė 1"
    assert vote_text(None) == ""


def test_order_keys_read_whole_in_reasons():
    from ltlaw.render import nr_text
    assert nr_text("(D1-188/2026-10-19): skyrių keitęs įsakymas") == "(Nr. D1-188 (2026-10-19)): skyrių keitęs įsakymas"
    assert nr_text("875/2025-12-03 ir 1-348/D1-1014/3-742/2024-11-29") == \
        "Nr. 875 (2025-12-03) ir Nr. 1-348/D1-1014/3-742 (2024-11-29)"
    assert nr_text("XV-659 ir V-434/2016-04-01") == "XV-659 ir Nr. V-434 (2016-04-01)"


def test_the_api_lists_part_level_amenders_with_their_adoption_votes():
    from ltlaw.api import _article
    v = {"at": "2023-12-19", "for": 85, "against": 2, "abstain": 4, "term": 9, "id": "-51480", "record": "https://www.lrs.lt/x"}
    x = {"label": "8", "pretty": "8", "title": "T", "url": "u", "status": {"state": "current"}, "notes": [],
         "blocks": [{"anchor": "d1", "text": "1. …", "notes": []},
                    {"anchor": "d2", "text": "2. …", "notes": [{"label": "Straipsnio dalies pakeitimai",
                                                               "refs": [{"nr": "XI-738"}, {"nr": "XIV-2398", "vote": v}]}]}]}
    out = _article(x)
    assert out["amended_by"] == ["XI-738", "XIV-2398"]
    assert out["adoption_votes"] == {"XIV-2398": {"at": "2023-12-19", "for": 85, "against": 2, "abstain": 4, "record": "https://www.lrs.lt/x"}}
    assert _article({**x, "blocks": []})["adoption_votes"] is None
