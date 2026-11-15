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
