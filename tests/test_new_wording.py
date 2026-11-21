from ltlaw.today import _quoted_new_wording

LAW = """1 straipsnis. Įstatymo papildymas 12¹ straipsniu
Papildyti Įstatymą 12¹ straipsniu:
„12¹ straipsnis. Kita
1. Tekstas.“

3 straipsnis. Lietuvos Respublikos pavyzdžio įstatymo Nr. XII-1 nauja redakcija
Pakeisti Lietuvos Respublikos pavyzdžio įstatymą Nr. XII-1 ir jį išdėstyti taip:
„LIETUVOS RESPUBLIKOS
PAVYZDŽIO ĮSTATYMAS

1 straipsnis. Paskirtis
1. Šis įstatymas nustato „kabutėse“ dalykus.

2 straipsnis. Įsigaliojimas
Taikoma.

Lietuvos Respublikos pavyzdžio
įstatymo priedas
ĮGYVENDINAMI ES TEISĖS AKTAI
1. Direktyva.
––––––––––––“.

4 straipsnis. Įstatymo įsigaliojimas
Šis įstatymas įsigalioja 2025 m. spalio 1 d.
"""


def test_quoted_new_wording_is_the_whole_act_without_its_annex():
    q = _quoted_new_wording(LAW, 3)
    assert q.startswith("LIETUVOS RESPUBLIKOS")
    assert "2 straipsnis. Įsigaliojimas\nTaikoma." in q
    assert "priedas" not in q and "4 straipsnis. Įstatymo įsigaliojimas" not in q


def test_no_quoted_act_without_a_rewrite_article():
    assert _quoted_new_wording(LAW, None) is None
    assert _quoted_new_wording(LAW, 1) is None  # article 1 adds one article: not a whole act


def test_flagged_orders_are_named_with_their_date_as_the_notes_name_them():
    """Since B88 an order is keyed "V-434/2016-04-01": matched bare, no candidate note could ever match it (HN71)."""
    from ltlaw.today import _needed
    got = _needed(["V-434/2016-04-01 (galioja nuo 2016-04-05) dar neįtrauktas į tekstą",
                   "V-959/A1-650/2024-10-03 (galioja nuo 2024-10-10) dar neįtrauktas į tekstą", "XIV-123: nežinoma įsigaliojimo data"])
    assert got == {"V-434/2016-04-01", "V-959/A1-650/2024-10-03", "XIV-123"}


def test_an_official_consolidation_holds_the_act_level_laws_in_force_when_it_starts():
    """HN71 1 p.: the 2017 consolidation's note names V-434 only (V-257 changed other points); valid from V-257's
    entry into force and prepared after its publication, it holds V-257 all the same. A law it can't hold (in force
    later, or published after it was prepared) is still needed; a new wording or an unknown preparation proves nothing."""
    from types import SimpleNamespace as N
    from ltlaw.today import _consolidated
    laws = N(meta={"V-434/2016-04-01": {"paskelbta_tar": "2016-04-04"}, "V-257/2017-03-07": {"paskelbta_tar": "2017-03-09"},
                   "V-9/2018-01-02": {"paskelbta_tar": "2018-01-03"}})
    flags = [("V-434/2016-04-01", "2016-04-05"), ("V-257/2017-03-07", "2017-03-10"), ("V-9/2018-01-02", "2018-01-05")]
    other = N(version_from="2017-03-10")
    assert _consolidated(flags, "Suvestine", other, "2017-03-10T11:03:11", laws) == {"V-434/2016-04-01", "V-257/2017-03-07"}
    assert _consolidated(flags, "Suvestine", other, "2017-03-08T09:00:00", laws) == {"V-434/2016-04-01"}  # V-257 published after
    assert _consolidated(flags, "new wording", other, "2017-03-10T11:03:11", laws) == set()
    assert _consolidated(flags, "Suvestine", other, None, laws) == set()
