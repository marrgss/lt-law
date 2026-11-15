from ltlaw.currency import parse_amending

XV969 = """1 straipsnis. 23 straipsnio pakeitimas
Pakeisti 23 straipsnio 3 dalį.
2 straipsnis. 23 straipsnio pakeitimas
Pakeisti 23 straipsnio 5 dalį.
3 straipsnis. 26 straipsnio pakeitimas
Pakeisti 26 straipsnį.
17 straipsnis. 148 straipsnio pakeitimas
Pakeisti 148 straipsnį.
23 straipsnis. Įstatymo įsigaliojimas, įgyvendinimas ir taikymas
1. Šis įstatymas, išskyrus šio įstatymo 2 ir 17 straipsnius, šio straipsnio 2 ir 3 dalis, įsigalioja 2026 m. birželio 7 d.
2. Šio įstatymo 2 ir 17 straipsniai įsigalioja 2027 m. sausio 1 d.
3. Socialinės apsaugos ir darbo ministras iki 2026 m. liepos 31 d. priima šio įstatymo įgyvendinamuosius teisės aktus.
"""


def test_staged_entry_into_force_dk23():
    law = parse_amending("XV-969", XV969, "2026-06-07")
    assert law.default == "2026-06-07"
    assert law.own_dates == {2: {"2027-01-01"}, 17: {"2027-01-01"}} and law.exceptions == {2, 17}
    # art. 23 is changed by own arts 1 (June) and 2 (January)
    assert law.dates_for("23") == {"2026-06-07", "2027-01-01"}
    assert law.dates_for("148") == {"2027-01-01"}
    assert law.dates_for("26") == {"2026-06-07"}


def test_simple_law_and_superscript_target():
    text = """1 straipsnis. 252 straipsnio pakeitimas
x
2 straipsnis. Kodekso papildymas 2521 straipsniu
x
3 straipsnis. 252, 2551 ir 589 straipsnių pakeitimas
x
6 straipsnis. Įstatymo įsigaliojimas
Šis įstatymas įsigalioja 2026 m. spalio 1 d.
"""
    law = parse_amending("XV-1142", text, "2026-10-01")
    assert law.default == "2026-10-01" and not law.unresolved
    assert law.dates_for("252-1") == {"2026-10-01"}   # flattened 2521 matches 252¹
    assert law.dates_for("255-1") == {"2026-10-01"}


def test_unmapped_exception_falls_back_to_latest_date():
    text = """1 straipsnis. 10 straipsnio pakeitimas
x
2 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas įsigalioja 2026 m. sausio 1 d.
2. Kodekso 10 straipsnio 3 dalies nuostatos taikomos nuo 2027 m. liepos 1 d. ir įsigalioja 2027 m. liepos 1 d.
"""
    law = parse_amending("XV-1", text, "2026-01-01")
    assert law.unresolved
    assert "2027-07-01" in law.dates_for("10")


XIV2769 = """2 straipsnis. 24 straipsnio pakeitimas
x
3 straipsnis. 24 straipsnio pakeitimas
x
4 straipsnis. 24 straipsnio pakeitimas
x
8 straipsnis. 26 straipsnio pakeitimas
x
20 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas, išskyrus 1 straipsnio 2 ir 3 dalis, 3, 4, 6 ir 7 straipsnius, 8 straipsnio 2 ir 3 dalis, įsigalioja 2025 m. sausio 1 d.
2. Šio įstatymo 1 straipsnio 2 dalis, 3 ir 6 straipsniai, 8 straipsnio 2 dalis įsigalioja 2026 m. sausio 1 d.
3. Šio įstatymo 1 straipsnio 3 dalis, 4 ir 7 straipsniai, 8 straipsnio 3 dalis įsigalioja 2027 m. sausio 1 d.
"""


def test_multi_year_schedule_akcizai():
    law = parse_amending("XIV-2769", XIV2769, "2025-01-01")
    assert law.exceptions == {3, 4, 6, 7} and law.partial == {1, 8} and not law.unresolved
    assert law.dates_for("24") == {"2025-01-01", "2026-01-01", "2027-01-01"}  # own arts 2, 3, 4
    assert law.dates_for("26") == {"2025-01-01", "2026-01-01", "2027-01-01"}  # own art 8, parts staged


def test_ranges_and_no_default_sentence():
    text = """1 straipsnis. 41 straipsnio pakeitimas
x
16 straipsnis. 50 straipsnio pakeitimas
x
40 straipsnis. Įstatymo įsigaliojimas, įgyvendinimas ir taikymas
1. Šio įstatymo 1 straipsnio 3, 5, 6 dalys ir 10 straipsnis įsigalioja 2026 m. rugpjūčio 1 d.
2. Šio įstatymo 16–20, 28, 30 ir 31 straipsniai įsigalioja 2027 m. sausio 1 d.
3. Šio įstatymo 1 straipsnio 1, 2, 4, 7 dalys, 2–9, 11–15, 21–27 ir 29 straipsniai įsigalioja 2027 m. sausio 2 d.
"""
    law = parse_amending("XV-1067", text, "2026-07-04")
    assert law.dates_for("50") == {"2027-01-01"}            # 16 is inside the range 16–20; no metadata default
    assert {"2026-08-01", "2027-01-02"} <= law.dates_for("41")


def test_conditional_entry():
    text = """1 straipsnis. 3 straipsnio pakeitimas
x
2 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas įsigalioja 2026 m. sausio 1 d.
2. Šio įstatymo 1 straipsnio 2 dalis įsigalioja tą dieną, kai įsigalios Europos Komisijos sprendimas.
"""
    law = parse_amending("XV-2", text, "2026-01-01")
    assert law.conditional_for("3") and not law.unresolved


def test_entry_dates_changed_by_later_law_and_first_date_after_isigalioja():
    text = """1 straipsnis. 82 straipsnio pakeitimas
x
43 straipsnis. Įstatymo įsigaliojimas, įgyvendinimas ir taikymas
1. Šis įstatymas, išskyrus 1 straipsnį, įsigalioja 2024 m. balandžio 1 d.
4. Šio įstatymo 1 straipsnis įsigalioja 2027 m. rugsėjo 1 d.
Straipsnio dalies pakeitimai:
Nr. XV-1028, 2026-06-11, paskelbta TAR 2026-06-26, i. k. 2026-11104
5. Lietuvos Respublikos Vyriausybė iki 2024 m. kovo 31 d. priima įgyvendinamuosius teisės aktus.
"""
    law = parse_amending("XIV-2317", text, "2024-04-01")
    assert law.dates_for("82") == {"2027-09-01"}       # not the 2024-03-31 deadline of part 5
    assert law.entry_amended == ["XV-1028"]


def test_excepted_without_date_takes_effect_day_after_publication():
    text = """6 straipsnis. 14 straipsnio pakeitimas
x
7 straipsnis. 15 straipsnio pakeitimas
x
69 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas, išskyrus 6 straipsnį, įsigalioja 2027 m. sausio 1 d.
"""
    law = parse_amending("XV-986", text, "2027-01-01", published="2026-06-12")
    assert law.dates_for("14") == {"2026-06-13"} and law.dates_for("15") == {"2027-01-01"} and not law.unresolved
