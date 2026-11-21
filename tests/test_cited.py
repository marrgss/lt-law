"""D-057: amending acts a text names that the metadata lacks are looked up by number and date the next night."""
import json

from ltlaw import currency, source


def _row(nr, adopted, kind="Įsakymas", eff="2020-09-01", doc="D1"):
    return {"dokumento_id": doc, "tar_kodas": "t", "atv_dok_nr": nr, "rusis": kind, "galioj_busena": "galioja",
            "priimtas": adopted, "paskelbta_tar": adopted, "isigalioja": eff, "negalioja": None, "pavadinimas": "Dėl …"}


def _state(tmp_path, monkeypatch, wanted, checked=None):
    st = tmp_path / "state"
    st.mkdir()
    (st / "laws.jsonl").write_text(json.dumps(_row("XV-1", "2025-01-01", "Įstatymas", doc="L1")) + "\n")
    for name in ("STATE", "CITED", "CITED_WANTED", "CITED_CHECKED"):
        monkeypatch.setattr(source, name, st / {"STATE": "", "CITED": "cited.jsonl", "CITED_WANTED": "cited_wanted.json",
                                                 "CITED_CHECKED": "cited_checked.json"}[name] if name != "STATE" else st)
    (st / "cited_wanted.json").write_text(json.dumps(wanted))
    if checked:
        (st / "cited_checked.json").write_text(json.dumps(checked))
    return st


def test_a_cited_order_is_found_by_number_and_date_and_dated(tmp_path, monkeypatch):
    st = _state(tmp_path, monkeypatch, ["V-1862/2020-08-18", "XV-1"])
    asked = []
    monkeypatch.setattr(source, "query", lambda m, q, **kw: asked.append(q) or [_row("V-1862", "2020-08-18")])
    assert source.update_cited() == {"wanted": 2, "asked": 1, "found": 1}  # a Seimas number is never asked this way
    assert 'atv_dok_nr="V-1862"&priimtas="2020-08-18"' in asked[0]
    meta = source.act_metadata(st / "laws.jsonl")
    assert meta["V-1862/2020-08-18"]["isigalioja"] == "2020-09-01" and "XV-1" in meta
    assert source.update_cited() == {"wanted": 2, "asked": 0, "found": 0}  # known now: not asked again


def test_two_answers_or_a_new_court_decision_are_not_kept(tmp_path, monkeypatch):
    st = _state(tmp_path, monkeypatch, ["176/2021-05-11", "I-1-14/2022-10-31", "176/1999-05-11/x"])
    answers = {"176": [_row("176", "2021-05-11", "Nutarimas", doc="A"), _row("176", "2021-05-11", "Nutarimas", doc="B")],
               "I-1-14": [_row("I-1-14", "2022-10-31", "Sprendimas")]}
    monkeypatch.setattr(source, "query", lambda m, q, **kw: answers.get(q.split('atv_dok_nr="')[1].split('"')[0], []))
    got = source.update_cited()
    assert got["found"] == 0 and not (st / "cited.jsonl").exists()
    # not found: asked again only after 30 days
    assert set(json.loads((st / "cited_checked.json").read_text())) == {"176/2021-05-11", "I-1-14/2022-10-31", "176/1999-05-11/x"}
    assert source.update_cited()["asked"] == 0


def test_an_older_court_decision_is_kept_and_dated_from_its_metadata(tmp_path, monkeypatch):
    st = _state(tmp_path, monkeypatch, ["I-858-13-14/2014-10-31"])
    monkeypatch.setattr(source, "query", lambda m, q, **kw: [_row("I-858-13-14", "2014-10-31", "Sprendimas", eff="2014-11-03")])
    assert source.update_cited()["found"] == 1
    monkeypatch.setattr(source, "DATA", tmp_path)
    laws = currency.Laws(fetch=False)
    laws.meta = source.act_metadata(st / "laws.jsonl")
    law = laws.get("I-858-13-14/2014-10-31")
    assert law is not None and law.default == "2014-11-03"
