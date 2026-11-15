"""update_point_amenders: never-searched acts first, then weekly, within a time budget (2026-10-28: 45 minutes)."""
import datetime as dt
import json

from ltlaw import source


def test_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "STATE", tmp_path)
    acts = [("86", "2001-01-25"), ("1-22", "2012-02-03"), ("O3-75", "2009-05-28")]
    monkeypatch.setattr(source, "POINT_ACTS", acts)
    today = dt.date.today()
    (tmp_path / "point_amenders_checked.json").write_text(json.dumps({
        "86/2001-01-25": today.isoformat(),                                   # checked today: not due
        "1-22/2012-02-03": (today - dt.timedelta(days=8)).isoformat()}))      # a week ago: due, after the new one
    asked = []
    monkeypatch.setattr(source, "query", lambda model, q, **kw: asked.append(q) or [])
    assert source.update_point_amenders() == 0
    # VERT's "O3-75" by its digits: amenders cite it as O3E-75 or O3-75 (B84)
    assert len(asked) == 2 and 'contains("-75")' in asked[0] and 'contains("1-22")' in asked[1]
    assert 'contains("gegužės")' in asked[0] and 'contains("2009")' in asked[0]  # no spaces: titles have \xa0
    seen = json.loads((tmp_path / "point_amenders_checked.json").read_text())
    assert seen["O3-75/2009-05-28"] == seen["1-22/2012-02-03"] == today.isoformat()
    asked.clear()
    source.update_point_amenders(budget_s=-1)  # over budget at once: nothing asked
    assert asked == []


def test_a_title_with_non_breaking_spaces_is_kept(monkeypatch):
    # NPKR's amenders cite "2010 m. gruodžio 22\xa0d. įsakymo Nr. 1-348/D1-1014/3-742": missed by the exact-phrase search
    monkeypatch.setattr(source, "POINT_ACTS", [("1-348/D1-1014/3-742", "2010-12-22")])
    monkeypatch.setattr(source, "POINT_KIND", {("1-348/D1-1014/3-742", "2010-12-22"): "Įsakymas"})
    r = {"rusis": "Įsakymas", "atv_dok_nr": "1-251/D1-275/3-412",
         "pavadinimas": "Dėl … ministro 2010 m. gruodžio 22\xa0d. įsakymo Nr. 1-348/D1-1014/3-742 „Dėl …“ pakeitimo"}
    assert source.keep_meta(r)
    assert not source.keep_meta(dict(r, pavadinimas=r["pavadinimas"].replace("22\xa0d.", "23 d.")))


def test_awaiting_consolidation(tmp_path, monkeypatch):
    """A law in force for a few days whose act's stored text starts before it: fetched first. Not when the text
    already starts on or after it, nor for a law naming another act."""
    monkeypatch.setattr(source, "STATE", tmp_path / "state")
    monkeypatch.setattr(source, "POINT_ACTS", [])
    (tmp_path / "state").mkdir()
    rows = [{"atv_dok_nr": "XV-1", "isigalioja": "2026-10-20", "pavadinimas": "… įstatymo Nr. XI-242 2 straipsnio pakeitimo įstatymas"},
            {"atv_dok_nr": "XV-2", "isigalioja": "2026-10-20", "pavadinimas": "… įstatymo Nr. XI-2420 pakeitimo įstatymas"}]
    (tmp_path / "state" / "laws.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    root = tmp_path / "dok"
    monkeypatch.setattr(source, "snapshots", lambda d: sorted((root / d).glob("*.json")))
    for d, start in (("OLD", "2026-05-01"), ("NEW", "2026-10-20")):
        (root / d).mkdir(parents=True)
        (root / d / "2026-10-25.json").write_text(json.dumps({"row": {"tekstas_lt": f"Suvestinė redakcija nuo {start}\n…"}}))
    monkeypatch.setattr(source, "latest_snapshot", lambda d: json.loads(sorted((root / d).glob("*.json"))[-1].read_text()))
    scope = [{"dokumento_id": "OLD", "number": "XI-242"}, {"dokumento_id": "NEW", "number": "XI-242"},
             {"dokumento_id": "OLD", "number": "XI-24"}]
    assert source.awaiting_consolidation(scope[:1], "2026-10-28") == {"OLD"}
    assert source.awaiting_consolidation(scope[1:2], "2026-10-28") == set()
    assert source.awaiting_consolidation(scope[2:], "2026-10-28") == set()  # "Nr. XI-242" is not "Nr. XI-24"


def test_chapters_named_by_their_new_numbers_after_a_renumbering():  # D1-188/2026 for RŽNTKŽŠA
    from ltlaw.currency import parse_amending_resolution
    law = parse_amending_resolution("D1-188/2026-10-19", """1. P a k e i č i u aprašą:
1.1. Pakeičiu VI skyrių ir jį išdėstau taip: „tekstas“.
1.2. Buvusius III‒X skyrius laikau atitinkamai IV‒XI skyriais.
1.3. Pakeičiu IV skyriaus antrąjį skirsnį ir jį išdėstau taip: „tekstas“.
1.4. Pakeičiu XI skyrių ir jį išdėstau taip: „tekstas“.
1.5. Pakeičiu II skyrių ir jį išdėstau taip: „tekstas“.
""", "2026-10-20")
    assert sorted(x for v in law.chapters.values() for x in v) == sorted(["VI", "III/2", "X", "II"])

