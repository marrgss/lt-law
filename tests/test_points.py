"""Acts made of points (Government resolutions approving rules: KET)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ltlaw.parse import parse  # noqa: E402

KET = """Suvestinė redakcija nuo 2024-12-01 iki 2025-12-31
Nutarimas paskelbtas: Žin. 2003, Nr. 7-263, i. k. 1021100NUTA00001950
Nauja nutarimo redakcija nuo 2008-09-01:
Nr. 768, 2008-07-16, Žin., 2008, Nr. 88-3530 (2008-08-02)
Lietuvos Respublikos Vyriausybė
nutarimas
2002 m. gruodžio 11 d. Nr. 1950
Vilnius
DĖL KELIŲ EISMO TAISYKLIŲ PATVIRTINIMO
1. Patvirtinti Kelių eismo taisykles (pridedama).
2. Pavesti Susisiekimo ministerijai organizuoti supažindinimą.
Ministras Pirmininkas Algirdas Brazauskas
PATVIRTINTA Lietuvos Respublikos Vyriausybės 2002 m. gruodžio 11 d. nutarimu Nr. 1950
KELIŲ EISMO TAISYKLĖS
I SKYRIUS
BENDROSIOS NUOSTATOS
1. Taisyklės nustato eismo tvarką.
2. Kiti teisės aktai negali prieštarauti Taisyklėms.
Punkto pakeitimai:
Nr. 1135, 2015-11-04, paskelbta TAR 2015-11-05, i. k. 2015-17682
3. Taisyklėse vartojamos sąvokos:
3.1. Aptarnaujantysis transportas – transporto priemonės.
3.2. Duoti kelią – reikalavimas.
3.21. Dviračių gatvė – kelias.
Papildyta papunkčiu:
Nr. 744, 2021-09-15, paskelbta TAR 2021-09-20, i. k. 2021-19691
4. Neteko galios nuo 2019-11-01
Punkto naikinimas:
Nr. 989, 2018-10-03, paskelbta TAR 2018-10-08, i. k. 2018-15920
4. Jeigu sankryžoje pritvirtinta lentelė, leidžiama sukti.
Papildyta punktu:
Nr. 2, 2020-01-08, paskelbta TAR 2020-01-09, i. k. 2020-00271
5. Penktas.
6. Šeštas.
61. Pirmas papildomas.
62. Antras papildomas.
7. Septintas.
8. Aštuntas.
9. Devintas.
10. Dešimtas.
––––––––––––––––––––
Priedo pakeitimai:
Nr. 1086, 2014-10-03, paskelbta TAR 2014-10-10, i. k. 2014-13954
Kelių eismo taisyklių 1 priedas
KELIO ŽENKLAI
1. Įspėjamieji kelio ženklai yra šie:
"""


def test_points_act_structure_and_keys():
    act = parse(KET)
    approval, main = act.segments
    assert approval.kind == "approval" and [a.label for a in approval.articles] == ["1", "2"]
    assert approval.signature == ["Ministras Pirmininkas Algirdas Brazauskas"]
    assert main.title == "KELIŲ EISMO TAISYKLĖS" and (main.headings[0].kind, main.headings[0].num) == ("skyrius", "I")
    labels = [a.label for a in main.articles]
    assert labels == ["1", "2", "3", "4", "5", "6", "6-1", "6-2", "7", "8", "9", "10"]   # 61, 62 after 6: 6¹, 6²
    a = {x.label: x for x in main.articles}
    assert [b.num for b in a["3"].blocks if b.kind == "point"] == ["3.1", "3.2", "3.2-1"]   # 3.21 after 3.2: 3.2¹
    assert a["3"].blocks[-1].notes[0].refs[0].nr == "744/2021-09-15"   # resolution numbers repeat: number/date
    assert a["2"].notes[0].refs[0].nr == "1135/2015-11-04"
    # a repealed entry left in the text, then the point added anew (KET 76): the new point, not a duplicate
    assert not a["4"].repealed and not a["4"].duplicates and a["4"].blocks[0].text.startswith("4. Jeigu")
    assert {r.nr for r in a["4"].all_refs()} == {"989/2018-10-03", "2/2020-01-08"}
    assert act.rewrites == [("2008-09-01", "768/2008-07-16")]
    assert [x.num for x in main.annexes] == ["1"] and main.annexes[0].notes[0].refs[0].nr == "1086/2014-10-03"


def test_plain_new_wording_header_is_a_rewrite():
    # NPVAT: "Nauja redakcija nuo …" without "nutarimo" is the resolution's new wording too
    act = parse(KET.replace("Nauja nutarimo redakcija nuo 2008-09-01:", "Nauja redakcija nuo 2008-09-01:"))
    assert act.rewrites == [("2008-09-01", "768/2008-07-16")]


def test_amending_resolution_items_annexes_and_staged_items():
    from ltlaw.currency import parse_amending_resolution
    t = ("Lietuvos Respublikos Vyriausybė n u t a r i a:\n"
         "1. Pakeisti Kelių eismo taisykles, patvirtintas … nutarimu Nr. 1950 „Dėl Kelių eismo taisyklių patvirtinimo“:\n"
         "1.1. Pakeisti 3.3 papunktį ir jį išdėstyti taip:\n„3.3. Naujas tekstas, žr. 99 punktą.“\n"
         "1.2. Pripažinti netekusiu galios 3.11 papunktį.\n"
         "1.3. Pakeisti 16 punktą ir jį išdėstyti taip:\n„16. Tekstas.“\n"
         "1.4. Pakeisti 1782 punktą ir jį išdėstyti taip:\n„1782. Tekstas.“\n"
         "1.5. Papildyti VIII1 skyriumi:\n„VIII1 SKYRIUS …“\n"
         "1.6. Pakeisti XXIII skyriaus pavadinimą ir jį išdėstyti taip:\n„X“\n"
         "1.7. Pakeisti 1 priedą:\n1.7.1. Pakeisti 4 punktą ir kelio ženklą Nr. 129 išdėstyti taip:\n„…“\n"
         "1.8. Pakeisti 4 priedo 9 punktą ir jį išdėstyti taip:\n„…“\n"
         "2. Nustatyti, kad:\n2.1. šis nutarimas, išskyrus šio nutarimo 1.3 papunktį, įsigalioja 2024 m. sausio 1 d.;\n"
         "2.2. šio nutarimo 1.3 papunktis įsigalioja 2024 m. vasario 1 d.\n")
    law = parse_amending_resolution("982/2023-12-20", t, "2024-01-01", "2023-12-21")
    toks = sorted({x for v in law.targets.values() for x in v}, key=lambda x: (len(x), x))
    assert toks == ["3", "16", "1782"]          # not 99 (quoted), not 4 or 9 (annex points)
    assert list(law.chapters.values()) == [["VIII-1"]]   # a chapter added; XXIII's title only is not a change
    assert law.default == "2024-01-01" and not law.unresolved
    assert law.dates_for("16") == {"2024-02-01"} and law.dates_for("3") == {"2024-01-01"}
    # flattened "1782" is 178² exactly: a resolution gets no sibling margin
    assert law.targets_article("178-2") and not law.targets_article("178-1")


def test_resolutions_are_kept_and_keyed_by_number_and_date():
    from ltlaw import source
    source.use_scope([{"unit": "punktas", "number": "1950", "adopted": "2002-12-11"}, {"abbr": "DK"}])
    r = {"rusis": "Nutarimas", "atv_dok_nr": "875", "priimtas": "2025-12-03",
         "pavadinimas": "Dėl Lietuvos Respublikos Vyriausybės 2002 m. gruodžio 11 d. nutarimo Nr. 1950 „Dėl Kelių eismo taisyklių patvirtinimo“ pakeitimo"}
    assert source.keep_meta(r) and source.meta_key(r) == "875/2025-12-03"
    other_year = dict(r, pavadinimas=r["pavadinimas"].replace("2002 m. gruodžio 11 d.", "2003 m. sausio 8 d."))
    assert not source.keep_meta(other_year)     # another year's resolution No. 1950
    source.use_scope([])


def test_the_resolution_set_out_anew_without_its_document_is_no_rewrite():
    """No. 813/2026 restates resolution No. 916 itself ("… aprašas nauja redakcija nedėstomas") and changes four points
    of the approved procedure: those are its targets; the procedure is not set out anew (the 2026-11-01 nightly)."""
    from ltlaw.currency import parse_amending_resolution
    t = ("Lietuvos Respublikos Vyriausybė n u t a r i a:\n"
         "Pakeisti Lietuvos Respublikos Vyriausybės 2012 m. liepos 18 d. nutarimą Nr. 916 „Dėl … aprašo patvirtinimo“:\n"
         "1. Pakeisti nurodytą nutarimą ir jį išdėstyti nauja redakcija (… tvarkos aprašas nauja redakcija nedėstomas):\n"
         "„LIETUVOS RESPUBLIKOS VYRIAUSYBĖ NUTARIMAS … Patvirtinti … tvarkos aprašą (pridedama).“\n"
         "2. Pakeisti nurodytu nutarimu patvirtintą … tvarkos aprašą:\n"
         "2.1. Pakeisti pavadinimą ir jį išdėstyti taip:\n„… APRAŠAS“.\n"
         "2.2. Papildyti 7.10 papunkčiu:\n„7.10. tekstas.“\n"
         "2.3. Pakeisti 8.5 papunktį ir jį išdėstyti taip:\n„8.5. asmenys, teikiantys Aprašo 7.7 arba 7.10 papunkčiuose …“.\n"
         "2.4. Pakeisti 18 punktą ir jį išdėstyti taip:\n„18. Tekstas.“\n"
         "2.5. Papildyti 191 punktu:\n„191. Tekstas.“\n")
    law = parse_amending_resolution("813/2026-10-28", t, "2026-10-30", "2026-10-29")
    assert law.rewrite_own is None
    assert sorted({x for ts in law.targets.values() for x in ts}, key=int) == ["7", "8", "18", "191"]


def test_numbers_inside_the_new_wording_are_not_targets():
    """No. 52/2026: "Pakeisti 59 punktą ir jį išdėstyti taip: „59. … Nuostatų 54 ir 56 punktuose …“" changes point 59
    only; 54 and 56 are the new wording's own references (B43)."""
    from ltlaw.currency import parse_amending_resolution
    t = ("Lietuvos Respublikos Vyriausybė nutaria:\n"
         "1. Pakeisti Juridinių asmenų registro nuostatus, patvirtintus Lietuvos Respublikos Vyriausybės 2003 m. "
         "lapkričio 12 d. nutarimu Nr. 1407 (toliau – Nuostatai):\n"
         "1.1. Pakeisti 59 punktą ir jį išdėstyti taip:\n„59. Duomenys, nurodyti Nuostatų 54 ir 56 punktuose, teikiami.“\n"
         "1.2. Pakeisti 60 punktą ir jį išdėstyti taip:\n„60. Kaip nustatyta 38 punkte.“\n")
    law = parse_amending_resolution("52/2026-01-28", t, "2026-02-04", "2026-02-03")
    assert sorted({x for ts in law.targets.values() for x in ts}) == ["59", "60"]


def test_dated_item_dates_its_subitems_and_setting_subitems_change_nothing():
    # No. 744/2025: "2.1. šio nutarimo 1.2 papunktis įsigalioja 2026 m. sausio 1 d." dates 1.2.1 and 1.2.2 (PAILGA 6, 8);
    # "2.2. … vadovaujantis … 6 ir 8 punktų nuostatomis" names points it doesn't change
    from ltlaw.currency import parse_amending_resolution
    t = ("Lietuvos Respublikos Vyriausybė n u t a r i a:\n"
         "1. Pakeisti … nutarimą Nr. 496:\n1.1. Pakeisti … aprašą:\n1.1.1. Pakeisti 3 punktą ir jį išdėstyti taip:\n„3. Tekstas.“\n"
         "1.2. Pakeisti … sąrašą:\n1.2.1. Pakeisti 6 punktą ir jį išdėstyti taip:\n„6. Tekstas.“\n"
         "1.2.2. Pakeisti 8 punktą ir jį išdėstyti taip:\n„8. Tekstas.“\n"
         "2. Nustatyti, kad:\n2.1. šio nutarimo 1.2 papunktis įsigalioja 2026 m. sausio 1 d.;\n"
         "2.2. darbuotojų iki 2025 m. gruodžio 31 d. nepanaudotų atostogų trukmė nustatoma vadovaujantis 6 ir 8 punktų nuostatomis.\n")
    law = parse_amending_resolution("744/2025-10-29", t, "2025-10-31")
    assert law.dates_for("6") == {"2026-01-01"} and law.dates_for("8") == {"2026-01-01"}
    assert law.dates_for("3") == {"2025-10-31"} and not law.unresolved


def test_numbers_going_back_inside_a_point_are_its_text_and_a_doubled_stop_is_still_the_next_point():
    head = KET.split("I SKYRIUS")[0]
    pts = "\n".join(f"{n}. Punktas {n}." for n in range(1, 54))
    text = head + "I SKYRIUS\nBENDROSIOS NUOSTATOS\n" + pts + "\n54. Liftų skaičius pateiktas lentelėje.\n2 lentelė\n" \
        "1. Skaičiuojama pagal paskutinį aukštą.\n2. Sekcijinio tipo namų plotas.\n55. Garažai.\n56.. Pandusai.\n" \
        "57. Vartai.\n561.. Ne punktas, o 57 punkto tekstas.\n"
    act = parse(text)
    labels = [a.label for a in act.main.articles]
    assert labels[-4:] == ["54", "55", "56", "57"]                             # 55 is 55, not 5⁵ (STR 2.02.12)
    p54 = act.main.articles[53]
    assert [b.text for b in p54.blocks][-2:] == ["1. Skaičiuojama pagal paskutinį aukštą.", "2. Sekcijinio tipo namų plotas."]
    assert not act.main.articles[0].duplicates                                 # the notes are not point 1 printed again
    assert act.main.articles[-1].blocks[-1].text.startswith("561..")         # "N.." only as the very next point


def test_the_points_number_then_its_subpoints_numbers_is_its_text_not_a_copy():
    head = KET.split("I SKYRIUS")[0]
    text = head + "I SKYRIUS\nBENDROSIOS NUOSTATOS\n" + "\n".join(f"{n}. Punktas {n}." for n in range(1, 10)) + \
        "\n10. Išlaidos dalijamos taip:\n10.13. Elektrifikavimo projektas.\n10.14. Rekonstrukcijos atveju:\n" \
        "10.  10.13.  10.14.1. 1 Vartotojas apmoka perkėlimo sąnaudas.\n10.14.2. Kai linijos senesnės nei 20 metų.\n11. Kitas.\n"
    act = parse(text)
    p10 = act.main.articles[9]
    assert p10.label == "10" and not p10.duplicates                              # the connection fee methodology's table
    assert any(b.text.startswith("10. 10.13. 10.14.1.") for b in p10.blocks)  # spaces normalised
    assert p10.blocks[-1].text.startswith("10.14.2.") and act.main.articles[-1].label == "11"


ORDER_HEAD = """Suvestinė redakcija nuo 2024-01-11
LIETUVOS RESPUBLIKOS VYRIAUSYBĖ
NUTARIMAS
DĖL MAŽMENINĖS PREKYBOS TAISYKLIŲ PATVIRTINIMO
2001 m. birželio 11 d. Nr. 697
Vilnius
1. Patvirtinti Mažmeninės prekybos taisykles (pridedama).
2. Įgalioti tarnybą.
Ministras Pirmininkas                                    Rolandas Paksas
"""


def test_a_document_whose_title_is_not_in_capitals_is_read_from_its_start():  # MPT lost points 1-13 until 2026-11-09
    text = ORDER_HEAD + """PATVIRTINTA Lietuvos Respublikos Vyriausybės 2001 m. birželio 11 d. nutarimu Nr. 697 (… redakcija)
Mažmeninės prekybos taisyklės
I SKYRIUS
Bendrosios Nuostatos
""" + "".join(f"{i}. Pirmojo skyriaus punktas {i}.\n" for i in range(1, 14)) + """II SKYRIUS
Prekių KEITIMas IR GRĄŽINIMas
""" + "".join(f"{i}. Antrojo skyriaus punktas {i}.\n" for i in range(14, 20))
    main = parse(text).main
    assert [a.label for a in main.articles] == [str(i) for i in range(1, 20)]
    assert main.title == "Mažmeninės prekybos taisyklės"
    assert [h.num for h in main.articles[0].path] == ["I"]


def test_a_document_in_lower_case_starting_with_its_first_point():  # KĮPNIPVT read the resolution's 3 points
    text = ORDER_HEAD + "PATVIRTINTA\nLietuvos Respublikos Vyriausybės\n2004 m. balandžio 16 d. nutarimu Nr. 439\n" \
        "keleivių įvežamų prekių neapmokestinimo taisyklės\n" + "".join(f"{i}. Punktas {i}.\n" for i in range(1, 12))
    assert [a.label for a in parse(text).main.articles] == [str(i) for i in range(1, 12)]


def test_a_numbered_table_before_the_documents_points_is_not_its_start():  # SPĮDAAPT
    text = ORDER_HEAD + "PATVIRTINTA\nLietuvos Respublikos sveikatos apsaugos\nministro 2002 m. balandžio 23 d.\nįsakymu Nr. 186\n" \
        "Sveikatos priežiūros įstaigų darbuotojų priemonės\nLigos pavadinimas\nCholera\n1. Chirurginė pižama\n+\n2. Pirštinės\n+\n" \
        "I. BENDROSIOS NUOSTATOS\n" + "".join(f"{i}. Punktas {i}.\n" for i in range(1, 10))
    assert [a.label for a in parse(text).main.articles] == [str(i) for i in range(1, 10)]


def test_annex_headers_long_or_split_over_lines():  # AEKRSNBM, EIEEVSIA, IASESASA, e-tar's copies; 2026-11-11
    body = KET.split("––––––––––––––––––––")[0]
    one = "Atskirų energijos ir kuro rūšių sąnaudų normatyvų būstui šildyti ir karštam vandeniui ruošti nustatymo bei taikymo metodikos"
    for tail, headers in (
        # the whole header on one line, over 80 characters (the annex's points were read as the rules' points again)
        (f"{one} 1 priedas\nNORMATYVAI\n1. Pirmas.\n2. Antras.\n{one} 2 priedas\nSĄNAUDOS\n1. Pirmas.",
         [f"{one} 1 priedas", f"{one} 2 priedas"]),
        # e-tar: the header's last words on a line of their own, after the previous annex's text
        (f"{one}\n1 priedas\nNORMATYVAI\n1. Pirmas.\n{one}\n2 priedas\nSĄNAUDOS\n1. Pirmas.",
         [f"{one} 1 priedas", f"{one} 2 priedas"]),
        # split over short lines, the last in lower case
        ("Energijos išteklių ir energijos efektyvaus\nvartojimo stebėsenos (informacijos)\nparengimo tvarkos aprašo 1 priedas\n"
         "TVARKA\n1. Pirmas.\n2. Antras.",
         ["Energijos išteklių ir energijos efektyvaus vartojimo stebėsenos (informacijos) parengimo tvarkos aprašo 1 priedas"]),
        # a header starting with a year stops there; a long sentence before it is the previous annex's text
        ("Kelių eismo taisyklių 1 priedas\nFORMA\nbūti nepriklausomu nuo tikrinamos įmonės paslaugos teikėjo vadovo ar jo įgalioto asmens ir"
         " už sutarties vykdymą atsakingo auditoriaus pasirašytas deklaracijas pagal formas (Taisyklių 2 ir 3 priedai)\n"
         "2014–2020 metų programų įgyvendinimo Lietuvoje taisyklių\n2 priedas\nDEKLARACIJA",
         ["Kelių eismo taisyklių 1 priedas", "2014–2020 metų programų įgyvendinimo Lietuvoje taisyklių 2 priedas"]),
    ):
        main = parse(body + "––––––––––––––––––––\n" + tail).main
        assert [x.header for x in main.annexes] == headers
        assert [a.label for a in main.articles][-1] == "10" and not any("again" in w for w in main.warnings) and not main.tail
    # a standard's annex in a table cell, split over two lines on e-tar: not an annex of the rules (DSPĮT)
    main = parse(body + "––––––––––––––––––––\nKelių eismo taisyklių 1 priedas\nSTANDARTAI\nLST EN 12732\nLST EN 1775 C\n1 priedas\n"
                 "LST EN 10255\nKelių eismo taisyklių 2 priedas\nFORMA").main
    assert [x.num for x in main.annexes] == ["1", "2"] and "1 priedas" in [b.text for b in main.annexes[0].blocks]
    assert parse(body + "––––––––––––––––––––\nKelių eismo taisyklių 1 priedas\nFORMA\n"
                 "būti nepriklausomu nuo tikrinamos įmonės paslaugos teikėjo vadovo ar jo įgalioto asmens ir"
                 " už sutarties vykdymą atsakingo auditoriaus pasirašytas deklaracijas pagal formas (Taisyklių 2 ir 3 priedai)\n"
                 "2014–2020 metų programų įgyvendinimo Lietuvoje taisyklių\n2 priedas\nDEKLARACIJA").main.annexes[0].blocks[-1].text.startswith("būti")


def test_a_point_printed_out_of_place_does_not_swallow_the_points_after_it():  # ŠTTŠPĮT 191, 2026-11-11
    # the amended 191 printed after 118 (open data and e-tar alike), 119 missing, the old 191 in its place further on;
    # until 2026-11-11 points 120–190 were read as the stray 191's text
    head = KET.split("5. Penktas.")[0]
    act = parse(head + "\n".join(f"{n}. Punktas {n}." for n in range(5, 119))
                + "\n191. Naujas šimtas devyniasdešimt pirmas.\nPunkto pakeitimai:\n"
                + "Nr. 1-29, 2019-01-29, paskelbta TAR 2019-01-30, i. k. 2019-01381\n"
                + "\n".join(f"{n}. Punktas {n}." for n in range(120, 193)))
    main = act.main
    labels = [a.label for a in main.articles]
    assert labels == [str(n) for n in range(1, 119)] + ["191"] + [str(n) for n in range(120, 191)] + ["192"]
    a = next(a for a in main.articles if a.label == "191")
    assert a.blocks[0].text.startswith("191. Naujas") and a.duplicates[0].blocks[0].text == "191. Punktas 191."
    assert "point 191 printed out of place, after point 118" in main.warnings


def test_older_rule_sets_chapters_and_sections_in_roman_figures():  # EETEKT, ELIĮT, DSPĮT, ŠTTŠPĮT: 197 rule sets, 2026-11-11
    # "II. SĄVOKOS" was read as the last line of the point before it, the act without chapters
    head = KET.split("I SKYRIUS")[0]
    pts = lambda a, b: "\n".join(f"{n}. Punktas {n}." for n in range(a, b))  # noqa: E731
    text = (head + "I. BENDROSIOS NUOSTATOS\n" + pts(1, 3) + "\nII. BENDRIEJI EKSPLOATAVIMO REIKALAVIMAI\nI. STATYBOS UŽBAIGIMAS\n"
            + pts(3, 5) + "\nII. TECHNINIAI DOKUMENTAI\n" + pts(5, 7) + "\nIII. EKSPLOATAVIMAS\n" + pts(7, 9)
            + "\nIII. TERITORIJA IR\nSTATINIAI\n" + pts(9, 11) + "\nV. Dujinių prietaisų įrengimas\nI. BENDRIEJI NURODYMAI\n"
            + pts(11, 13) + "\n13. Punktas su sąrašu:\nIV. PAREIŠKĖJAS\n" + pts(14, 15))
    main = parse(text).main
    assert [(h.kind, h.num, h.title) for h in main.headings] == [
        ("skyrius", "I", "BENDROSIOS NUOSTATOS"), ("skyrius", "II", "BENDRIEJI EKSPLOATAVIMO REIKALAVIMAI"),
        ("skirsnis", "I", "STATYBOS UŽBAIGIMAS"), ("skirsnis", "II", "TECHNINIAI DOKUMENTAI"), ("skirsnis", "III", "EKSPLOATAVIMAS"),
        ("skyrius", "III", "TERITORIJA IR STATINIAI"), ("skyrius", "V", "Dujinių prietaisų įrengimas"),
        ("skirsnis", "I", "BENDRIEJI NURODYMAI")]
    a = {x.label: x for x in main.articles}
    assert [b.text for b in a["2"].blocks] == ["2. Punktas 2."]  # the heading no longer the point's last line
    assert [(h.kind, h.num) for h in a["7"].path] == [("skyrius", "II"), ("skirsnis", "III")]
    assert [b.text for b in a["13"].blocks][-1] == "IV. PAREIŠKĖJAS"  # out of turn (after chapter V): the point's text
    # chapters each numbering their points from 1 (GAAPT, a standard per chapter): left as text, as before
    gaapt = parse(head + "I. BENDROSIOS NUOSTATOS\n" + pts(1, 4) + "\nII. KVIEČIAI\n" + pts(1, 3)).main
    assert not gaapt.headings
    # a table's rows in a point before any chapter: no chapter I after the first point
    table = parse(head + pts(1, 3) + "\n3. Gyvavimo trukmė, metais\nI. GYVENAMOSIOS PASKIRTIES PASTATAI\n120\n" + pts(4, 12)).main
    assert not table.headings and "I. GYVENAMOSIOS PASKIRTIES PASTATAI" in [b.text for b in table.articles[2].blocks]
    assert parse(head + "I. SKYRIUS TAIKYMO SRITIS\n" + pts(1, 12)).main.headings[0].title == "TAIKYMO SRITIS"


def test_a_point_with_no_space_after_its_number_and_a_repealed_chapter_stub():
    head = KET.split("I SKYRIUS")[0]
    pts = "\n".join(f"{n}. Punktas {n}." for n in range(1, 51))
    # "52.Tarybos …" right after 51 is point 52 (SSTT); "60.5 mln." is no point; a repealed chapter's stub is a heading,
    # not the last point's words (ITIVKDĮN on e-tar)
    text = head + "I SKYRIUS\nBENDROSIOS NUOSTATOS\n" + pts + "\n51. Taryba sprendimą priima.\n52.Tarybos nutarimai įforminami.\n" \
        "53. Ataskaita pateikiama.\n8 skyrius. Neteko galios nuo 2026-06-02\nSkyriaus naikinimas:\n" \
        "Nr. D1-96, 2026-06-01, paskelbta TAR 2026-06-01, i. k. 2026-09552\n"
    act = parse(text)
    labels = [a.label for a in act.main.articles]
    assert labels[-3:] == ["51", "52", "53"]
    assert act.main.articles[51].blocks[0].text.endswith("Tarybos nutarimai įforminami.")
    assert all("Neteko galios" not in b.text for b in act.main.articles[52].blocks)
    # (in figures on e-tar whatever the act's own: here its chapters are "I SKYRIUS", so chapter VIII)
    assert any(h.kind == "skyrius" and h.num == "VIII" and h.title.startswith("Neteko galios") for h in act.main.headings)


def test_short_rules_after_the_stamp_are_points():
    """3–7 points right after the stamp are rules (KPSPEAT, MKPVKNSA, ITĮPTEBA); a short numbered list deep inside a
    document of paragraphs is not (PLNN2MLN)."""
    from ltlaw.points import is_points
    order = ["APLINKOS MINISTRAS", "Į S A K Y M A S", "1. Tvirtinu Tvarkos aprašą (pridedama).", "MINISTRAS"]
    stamp = ["PATVIRTINTA", "Lietuvos Respublikos aplinkos ministro", "2004 m. lapkričio 8 d. įsakymu Nr. D1-569",
             "MIŠKO KIRTIMO TVARKOS APRAŠAS", "I. BENDROSIOS NUOSTATOS"]
    pts = ["1. Šis aprašas nustato tvarką.", "2. Leidžiami šie kirtimai:", "2.1. šviesinimo;", "3. Atsako pagal įstatymus."]
    assert is_points(order + stamp + pts)
    assert not is_points(order + stamp + pts[:2])                                  # 2 points: too few to tell
    assert not is_points(order + stamp + ["Įvadas"] + ["Paragrafas be numerio."] * 12 + pts)  # a list deep inside
    assert not is_points(order + pts)                                              # no stamp


def test_document_selector_tells_apart_titles_sharing_their_start():
    from ltlaw.points import doc_matches
    sel = "papildomosios ir alternatyviosios sveikatos priežiūros sričių paslaugų grupėms ir (ar) pogrupiams priskiriamų " \
          "konkrečių paslaugų sąrašo sudarymo tvarkos aprašas"
    assert not doc_matches("PAPILDOMOSIOS IR ALTERNATYVIOSIOS SVEIKATOS PRIEŽIŪROS SRIČIŲ PASLAUGŲ GRUPĖMS IR (AR) "
                           "POGRUPIAMS PRISKIRIAMŲ KONKREČIŲ PASLAUGŲ SĄRAŠAS", sel)  # the list, not its procedure
    assert doc_matches("Papildomosios ir alternatyviosios sveikatos priežiūros SRIČIŲ paslaugų grupėms ir (ar) pogrupiams "
                       "priskiriamų konkrečių paslaugų sąrašo sudarymo tvarkOS APRAŠAS", sel)
    assert doc_matches("PAPILDOMOSIOS IR ALTERNATYVIOSIOS SVEIKATOS PRIEŽIŪROS SRIČIŲ PASLAUGŲ GRUPĖMS IR", sel)  # cut at a line
    assert doc_matches("Vidutinio darbo užmokesčio skaičiavimo tvarkos aprašas", "vidutinio darbo užmokesčio skaičiavimo tvarkos aprašas")
