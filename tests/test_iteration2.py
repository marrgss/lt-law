"""Regression tests for the fixes of review iteration 2 (code review of iteration 1, 2026-10-18)."""
import json

import pytest

from ltlaw import currency, source, today
from ltlaw.currency import Laws, _candidate_laws, decode_new_label, parse_amending
from ltlaw.parse import Block, parse
from ltlaw.render import Site, _blocks, sentence_case


# --- parser ----------------------------------------------------------------------------------
CHAPTERS = """Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
2016 m. rugsėjo 14 d. Nr. XII-1
Vilnius
V SKYRIUS
TVARKA
PIRMASIS SKIRSNIS
BENDROSIOS NUOSTATOS
37 straipsnis. Pirmas
Tekstas.
ANTRASIS SKIRSNIS
KITOS NUOSTATOS
38 straipsnis. Neteko galios nuo 2020-01-01
Skyriaus pakeitimai:
Nr. XV-1, 2025-06-01, paskelbta TAR 2025-06-05, i. k. 2025-00001
VI SKIRSNIS
RESPUBLIKOS PREZIDENTAS
39 straipsnis. Prezidento įgaliojimai
Prezidentas skelbia įstatymus.
"""


def test_chapter_note_attaches_to_the_chapter_not_the_last_article():
    act = parse(CHAPTERS)
    a37 = next(a for a in act.main.articles if a.label == "37")
    assert "XV-1" in {r.nr for r in a37.all_refs()}          # via its chapter V


def test_chapter_title_is_not_a_signature():
    act = parse(CHAPTERS)
    a39 = next(a for a in act.main.articles if a.label == "39")
    assert a39.blocks and "skelbia" in a39.blocks[0].text and not act.main.signature


ANNEXES = """Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
1 straipsnis. Pirmas
Tekstas.
Skelbiu šį Lietuvos Respublikos Seimo priimtą įstatymą.
Respublikos Prezidentas Vardas Pavardė
Lietuvos Respublikos
bandomojo įstatymo
1 priedėlis
NUSIDĖVĖJIMO NORMATYVAI
Turtas – 5 metai.
"""


def test_priedelis_is_an_annex():
    act = parse(ANNEXES)
    assert act.main.annexes and act.main.annexes[0].title == "NUSIDĖVĖJIMO NORMATYVAI"


QUOTED = """1 straipsnis. Įstatymo nauja redakcija
Pakeisti įstatymą ir jį išdėstyti taip:
71 straipsnis. Teisės aktų paskelbimas ir įsigaliojimas
Aktai įsigalioja kitą dieną po paskelbimo, jeigu pačiame akte nenustatyta vėlesnė data.
2 straipsnis. Įstatymo įsigaliojimas
Šis įstatymas įsigalioja 2026 m. sausio 1 d.
"""


def test_quoted_entry_heading_of_the_amended_act_is_not_the_laws_own():
    law = parse_amending("XIV-1", QUOTED, "2026-01-01")
    assert law.default == "2026-01-01" and not law.conditional and not law.unresolved


EXCEPT = """1 straipsnis. 5 straipsnio pakeitimas
Pakeisti 5 straipsnį.
2 straipsnis. Įstatymo įsigaliojimas
Šis įstatymas, išskyrus Kodekso 2-3 straipsnių nuostatas, įsigalioja 2026 m. sausio 1 d.
"""


def test_another_acts_numbers_are_not_own_exceptions():
    law = parse_amending("XV-9", EXCEPT, "2026-01-01")
    assert not law.exceptions and not law.partial


def test_ambiguous_new_article_number_is_not_guessed():
    assert decode_new_label("215", ["20", "21", "21-1", "22", "300"]) is None  # 215 or 21⁵?


# --- rendering ---------------------------------------------------------------------------------
def test_duplicate_anchors_become_unique_and_text_is_displayed():
    out = _blocks([Block("part", None, "161. Pirma", anchor="d16-1"), Block("part", None, "161. Antra", anchor="d16-1")], {})
    assert [b["anchor"] for b in out] == ["d16-1", "d16-1-r2"] and out[0]["text"].startswith("16¹.")


def test_heading_case_details():
    assert sentence_case("LIETUVOS RESPUBLIKOS PREZIDENTAS", set()) == "Lietuvos Respublikos Prezidentas"
    assert sentence_case("2020 M. SAUSIO 1 D. NUOSTATOS", set()) == "2020 m. sausio 1 d. nuostatos"


def test_rollback_restores_every_list(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "STATE", tmp_path / "state")
    site = Site(tmp_path / "out", "http://x", "2026-10-19", False, None)
    cp = site.checkpoint()
    site.sitemap.append("u"); site.redirects.append("r"); site.search_items.append([0]); site.search_acts.append(["A"])
    site.upcoming.append({"on": "2026-11-01"}); site.aliases["a"] = "A"; site.lastmod["/x/"] = ["h", "d"]
    (tmp_path / "out" / "ta" / "X").mkdir(parents=True)
    site.rollback(cp, tmp_path / "out" / "ta" / "X")
    assert not (site.sitemap or site.redirects or site.search_items or site.search_acts or site.upcoming or site.aliases)
    assert "/x/" not in site.lastmod and not (tmp_path / "out" / "ta" / "X").exists()


# --- sources -----------------------------------------------------------------------------------
class MetaLaws(Laws):
    def __init__(self, meta):
        self.meta, self.fetch, self._cache = meta, False, {}


def test_approval_law_number_does_not_target_the_codes_articles():
    act = parse("Suvestinė redakcija nuo 2026-01-01\nDARBO KODEKSAS\n6 straipsnis. Šeštas\nTekstas.\n")
    meta = {"XIII-2889": {"atv_dok_nr": "XIII-2889", "dokumento_id": "D1", "priimtas": "2019-01-01",
                          "paskelbta_tar": "2026-06-01", "isigalioja": "2026-07-01",
                          "pavadinimas": "Lietuvos Respublikos darbo kodekso patvirtinimo, įsigaliojimo ir įgyvendinimo "
                                         "įstatymo Nr. XII-2603 6 straipsnio pakeitimo įstatymas"}}
    cands = _candidate_laws(act, {"genitive": "darbo kodekso", "number": "XII-2603"}, MetaLaws(meta), "2026-10-19")
    assert not cands


def test_failed_amending_fetch_is_recorded_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "DATA", tmp_path)
    monkeypatch.setattr(currency, "FETCH_FAILED", [])
    def boom(*a, **k):
        raise TimeoutError("relay down")
    monkeypatch.setattr(source, "snapshot", boom)
    laws = MetaLaws({"XV-5": {"atv_dok_nr": "XV-5", "dokumento_id": "D5", "priimtas": "2026-01-01",
                              "paskelbta_tar": "2026-01-05", "isigalioja": "2026-02-01", "pavadinimas": "x"}})
    laws.fetch = True
    assert laws.get("XV-5") is None and currency.FETCH_FAILED and "relay down" in currency.FETCH_FAILED[0]


def test_suvestine_refresh_never_replaces_a_text_with_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "DATA", tmp_path)
    monkeypatch.setattr(source, "REFRESH_SUVESTINE", True)
    monkeypatch.setattr(source, "SUVESTINE_FAILED", [])
    d = tmp_path / "dokumentas" / "DOC"
    d.mkdir(parents=True)
    (d / "2026-01-01.json").write_text(json.dumps({"fetched": "2026-01-01T00:00:00", "row": {"tekstas_lt": "Originalus tekstas"}}))
    good = {"suvestines_id": "S1", "galioja_nuo": "2025-01-01", "galioja_iki": None, "tekstas_lt": "1 straipsnis. Pirmas\nTekstas."}
    (d / "suvestine.json").write_text(json.dumps({"fetched": "2026-01-01T00:00:00", "row": good}))  # stale: > 7 days
    monkeypatch.setattr(source, "fetch_suvestine_newest", lambda *a: None)
    monkeypatch.setattr(source, "latest_snapshot", lambda doc, root=None: json.loads((d / "2026-01-01.json").read_text()))
    text, origin = source.act_text("DOC")
    assert "Tekstas." in text and json.loads((d / "suvestine.json").read_text())["row"] == good
    assert source.SUVESTINE_FAILED


def test_today_only_skips_repealed_articles(monkeypatch):
    stored = parse("Suvestinė redakcija nuo 2027-01-01\nĮSTATYMAS\n1 straipsnis. Pirmas\nTekstas.\n")
    other = parse("Suvestinė redakcija nuo 2026-01-01\nĮSTATYMAS\n1 straipsnis. Pirmas\nTekstas.\n"
                  "2 straipsnis. Antras\nGalioja.\n3 straipsnis. Neteko galios nuo 2018-06-15\n")
    ost = currency.assess(other, {"genitive": "x įstatymo", "number": ""}, MetaLaws({}), "2026-10-19")
    monkeypatch.setattr(today, "candidates_for", lambda *a: [("archive", "2026-01-01", other, ost, None)])
    got = {x.article.label: x.status.state for x in today.find_today_only(stored, "DOC", {}, MetaLaws({}), "2026-10-19")}
    assert got == {"2": "current"}  # 3 was repealed in 2018: not "in force today"


# --- data hunt of iteration 2 ------------------------------------------------------------------
from ltlaw.currency import article_expiry, tar_note_effects  # noqa: E402


class _A:
    def __init__(self, *texts):
        self.blocks = [Block("para", None, t) for t in texts]


def test_temporary_article_lapses():
    assert article_expiry(_A("1254 straipsnis netenka galios 2024-05-01."), "125-4") == "2024-05-01"
    assert article_expiry(_A("TAR pastaba. 1253 straipsnis netenka galios 2023-05-01."), "125-3") == "2023-05-01"
    assert article_expiry(_A("Kitas straipsnis netenka galios 2024-05-01."), "7") is None


def test_transitional_applicability_notes_are_not_entry_dates():
    n = _A("TAR pastaba. Nuostatos taikomi nuo 2027-01-01 sudaromiems sandoriams.")
    n.blocks[0].text = "TAR pastaba. Nuostatos taikomos nuo 2027-01-01 sudaromiems sandoriams."
    assert tar_note_effects(n, "2026-10-19") == ([], [])
    paren = _A("TAR pastaba. 3 dalies nuostatos taikomos nuo Vyriausybės nutarimo Nr. 152 įsigaliojimo dienos (2020-02-26).")
    assert tar_note_effects(paren, "2026-10-19") == ([], [])  # the date in brackets is read: in the past


def test_recovered_text_older_than_a_rewrite_is_not_today(monkeypatch):
    stored = parse("Suvestinė redakcija nuo 2026-05-01\nĮSTATYMAS\nNauja įstatymo redakcija nuo 2026-01-01:\n"
                   "Nr. XV-344, 2025-06-26, paskelbta TAR 2025-06-30, i. k. 2025-00001\n1 straipsnis. Pirmas\nTekstas.\n")
    other = parse("Suvestinė redakcija nuo 2026-05-01\nĮSTATYMAS\n1 straipsnis. Pirmas\nSenas.\n15 straipsnis. Penkioliktas\nSenas.\n")
    laws = MetaLaws({"XV-344": {"atv_dok_nr": "XV-344", "priimtas": "2025-06-26"}})
    assert stored.rewrites, "the fixture must carry a whole-act rewrite"
    ost = currency.assess(other, {"genitive": "x įstatymo", "number": ""}, laws, "2026-10-19")
    monkeypatch.setattr(today, "candidates_for", lambda *a: [("Suvestine", "S1", other, ost, "2024-05-03")])
    assert today.find_today_only(stored, "DOC", {"genitive": "x įstatymo", "number": ""}, laws, "2026-10-19") == []


# --- iteration 3 -------------------------------------------------------------------------------
from ltlaw.validate import dropped_lines  # noqa: E402
from ltlaw.eu import find as eu_find  # noqa: E402

LOSS = """Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
1 straipsnis. Pirmas
1. Fondo valdyba:
1) tvarko apskaitą;
2. Tekstas.
2 straipsnis. Antras
Tekstas.
"""


def test_coverage_check_catches_lost_lines():
    act = parse(LOSS)
    assert dropped_lines(LOSS, act) == []
    a1 = act.main.articles[0]
    a1.blocks = [b for b in a1.blocks if not b.text.endswith(":")]   # a part ending with ":" lost
    act.main.articles[1].blocks = []                                 # "Tekstas." shown once, twice in source
    lost = dropped_lines(LOSS, act)
    assert "1. Fondo valdyba:" in lost and "Tekstas." in lost


def test_headings_with_a_full_stop():
    act = parse("Suvestinė redakcija nuo 2026-01-01\nLIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS\n"
                "1992 m. sausio 21 d. Nr. I-1\nVilnius\nI SKYRIUS. BENDRIEJI NUOSTATAI\n1 straipsnis. Pirmas\nTekstas.\n")
    assert act.main.articles[0].path and act.main.articles[0].path[0].title == "BENDRIEJI NUOSTATAI"


def test_annex_header_keeps_the_previous_annexs_values():
    t = ("Suvestinė redakcija nuo 2026-01-01\nLIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS\n1 straipsnis. Pirmas\nTekstas.\n"
         "Skelbiu šį Lietuvos Respublikos Seimo priimtą įstatymą.\nRespublikos Prezidentas Vardas Pavardė\n"
         "Lietuvos Respublikos\nbandomojo įstatymo\n1 priedas\nTARIFAI\nSO2\n423\n"
         "Lietuvos Respublikos\nbandomojo įstatymo\n2 priedas\nKITA\nTekstas.\n")
    act = parse(t)
    assert act.main.annexes[0].blocks[-1].text == "423"
    assert act.main.annexes[1].header == "Lietuvos Respublikos bandomojo įstatymo 2 priedas"
    assert "Skelbiu" not in act.main.annexes[0].header


def test_celex_year_first_regulations_and_decisions():
    assert [r.celex for r in eu_find("reglamentas (ES) Nr. 2024/3234")] == ["32024R3234"]
    assert [r.celex for r in eu_find("sprendimas Nr. 676/2002/EB")] == ["32002D0676"]
    assert [r.celex for r in eu_find("reglamentas (EB) Nr. 338/97")] == ["31997R0338"]
    assert [r.celex for r in eu_find("reglamentas (EB) Nr. 2023/2006")] == ["32006R2023"]   # number/year before 2015
    assert [r.celex for r in eu_find("reglamentas (EEB) Nr. 2092/91")] == ["31991R2092"]


# --- iteration 4 -------------------------------------------------------------------------------
from ltlaw.parse import _header_line, _titleish  # noqa: E402

STAGED = """1 straipsnis. 5 straipsnio pakeitimas
Pakeisti 5 straipsnį.
2 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas įsigalioja 2026 m. sausio 1 d. Vyriausybė iki 2026 m. birželio 30 d. priima įgyvendinamuosius teisės aktus.
2. 2031 m. sausio 1 d. įsigalioja tokia šio įstatymo 1 straipsnyje išdėstyto įstatymo 5 straipsnio redakcija.
"""


def test_entry_dates_before_the_verb_kept_deadlines_dropped():
    law = parse_amending("XV-7", STAGED, "2026-01-01")
    assert "2031-01-01" in law.all_dates and "2026-06-30" not in law.all_dates


def test_staged_later_part_of_a_law_already_in_the_text_is_announced():
    from ltlaw.currency import _future_change
    from ltlaw.parse import Ref
    law = parse_amending("XV-7", STAGED, "2026-01-01")
    law.targets = {1: ["5"]}
    refs = [Ref("XV-7", "2025-06-01", None, None)]
    got = _future_change("5", refs, [(law, {})], "2026-10-19", ["5"], "2026-01-01")
    assert got and got[0] == "2031-01-01"            # the 2031 wording isn't in a 2026 text
    assert _future_change("5", refs, [(law, {})], "2026-10-19", ["5"], "2031-01-01") is None  # a 2031 text has it


def test_annex_heading_forms_and_header_lines():
    from ltlaw.parse import RE_ANNEX
    assert RE_ANNEX.match("įstatymo priedas") and RE_ANNEX.match("2 priedėlis") and not RE_ANNEX.match("Šio įstatymo priedas taikomas")
    assert _header_line("asmens duomenų teisinės apsaugos") and _header_line("įstatymo") and _header_line("2002 m. kovo 5 d.")
    assert not _header_line("Lietuvos Respublikos bandomojo įstatymo pakeitimo įstatymas")
    assert not _header_line("Gitanas Nausėda") and not _header_line("423")


def test_titleish_lines():
    assert _titleish("k o d e k s a s") and _titleish("TEISĖS GAUTI INFORMACIJĄ IR duomenų PAKARTOTINIO NAUDOJIMO")
    assert not _titleish("Nr. VIII-940, 1998.11.24, Žin., 1998") and not _titleish("1 2 3 4")


def test_a_date_ending_the_sentence_is_kept():
    t = STAGED.replace("2. 2031 m. sausio 1 d. įsigalioja tokia šio įstatymo 1 straipsnyje išdėstyto įstatymo 5 straipsnio redakcija.",
                       "2. Šio įstatymo 1 straipsnis įsigalioja 2027 m. sausio 11 d.\n3. Licencijos, išduotos iki 2027 m. sausio 10 d., galioja.")
    law = parse_amending("XV-8", t, "2026-01-01")
    assert "2027-01-11" in law.all_dates and "2027-01-10" not in law.all_dates


# --- iteration 5 -------------------------------------------------------------------------------
def test_the_participle_is_not_the_entry_verb():
    t = STAGED + "3. Iki 2026 m. gruodžio 31 d. pradėtoms procedūroms taikomas iki šio įstatymo įsigaliojantį tvarka.\n"
    law, base = parse_amending("XV-9", t, "2026-01-01"), parse_amending("XV-9", STAGED, "2026-01-01")
    assert law.unresolved == base.unresolved and "2026-12-31" not in law.all_dates


# --- back-test findings ------------------------------------------------------------------------
def test_a_chapter_replaced_as_a_whole():
    t = ("1 straipsnis. 12 straipsnio pakeitimas\nPakeisti 12 straipsnį.\n"
         "2 straipsnis. VII skyriaus pakeitimas\nPakeisti VII skyrių ir jį išdėstyti taip:\n"
         "3 straipsnis. IV skyriaus pavadinimo pakeitimas\nPakeisti pavadinimą.\n"
         "4 straipsnis. Įstatymo įsigaliojimas\nŠis įstatymas įsigalioja 2023 m. sausio 1 d.\n")
    law = parse_amending("XIV-1570", t, "2023-01-01")
    assert law.chapters == {2: ["VII"]}   # a chapter title alone (IV) is not a change of its articles


def test_the_title_decides_flattened_superscripts():
    # headings flatten 3³ to "33" and 34²⁴ to "3424"; the title spells them out (XIV-595, XIV-2784)
    t = ("1 straipsnis. 33 straipsnio pakeitimas\nPakeisti.\n2 straipsnis. 3424 straipsnio pakeitimas\nPakeisti.\n"
         "3 straipsnis. 35 straipsnio pakeitimas\nPakeisti.\n"
         "4 straipsnis. Įstatymo įsigaliojimas\nŠis įstatymas įsigalioja 2023 m. sausio 1 d.\n")
    law = parse_amending("XIV-595", t, "2023-01-01", "… įstatymo Nr. VIII-787 3-3, 34-24, 35 straipsnių pakeitimo įstatymas")
    assert law.targets == {1: ["3-3"], 2: ["34-24"], 3: ["35"]}
    hit = [l for l in ["3-1", "3-3", "33", "34-2", "34-24", "35", "3-5"] if law.targets_article(l)]
    assert hit == ["3-3", "34-24", "35"]   # "35" in such a title is article 35, not 3⁵
    # without superscripts in the title a flattened token stays ambiguous between its readings (fail safe):
    # "33" is 33 or 3³; it is not 3¹ or 34² (the old sibling margin flagged those too: noise, ACCURACY B31)
    law = parse_amending("XIV-1", t, "2023-01-01", "… įstatymo Nr. VIII-787 pakeitimo įstatymas")
    assert {l for l in ["3-1", "3-3", "33", "34-2", "34-24"] if law.targets_article(l)} == {"3-3", "33", "34-24"}


def test_redating_flag_also_while_our_copy_lacks_the_amender():
    from ltlaw.currency import _recent_redating

    class L:  # register: XV-1028 amends XIV-2317's entry article; XV-1027 only a wording (article 1)
        meta = {"XV-1028": {"priimtas": "2026-06-11"}}
        def amended_by(self, nr):
            return [{"atv_dok_nr": "XV-1028", "priimtas": "2026-06-11",
                     "pavadinimas": "… pakeitimo įstatymo Nr. XIV-2317 2 straipsnio pakeitimo įstatymas"},
                    {"atv_dok_nr": "XV-1027", "priimtas": "2026-06-11",
                     "pavadinimas": "… pakeitimo įstatymo Nr. XIV-2317 1 straipsnio pakeitimo įstatymas"}] if nr == "XIV-2317" else []
    old = parse_amending("XIV-2317", "1 straipsnis. 82 straipsnio pakeitimas\nx\n2 straipsnis. Įstatymo įsigaliojimas\n"
                         "Šis įstatymas įsigalioja 2027 m. rugsėjo 1 d.\n", "2027-09-01")
    assert _recent_redating(old, L(), "2025-07-01") == ["XV-1028"]   # our copy predates it: dates uncertain
    new = parse_amending("XIV-2317", "1 straipsnis. 82 straipsnio pakeitimas\nx\n2 straipsnis. Įstatymo įsigaliojimas\n"
                         "Šis įstatymas įsigalioja 2028 m. rugsėjo 1 d.\nStraipsnio pakeitimai:\nNr. XV-1028, 2026-06-11\n",
                         "2027-09-01")
    assert _recent_redating(new, L(), "2025-07-01") == ["XV-1028"]   # consolidated: still flagged for a while (B8)
    assert _recent_redating(old, L(), "2026-07-01") == []             # adopted before the look-back window
    assert old.entry_articles == {2}


def test_a_section_replaced_and_a_whole_new_wording():
    # AlkKĮ XIV-2621: "III skyriaus ketvirtojo skirsnio pakeitimas"; SPĮ XIV-2357 art. 4: the whole law anew,
    # its quoted headings („1 straipsnis. …“ … "2 straipsnis. …") are the new law's, not XIV-2357's own
    t = ("1 straipsnis. 19 straipsnio pakeitimas\nPakeisti.\n"
         "2 straipsnis. III skyriaus ketvirtojo skirsnio pakeitimas\nPakeisti ir išdėstyti taip:\n„KETVIRTASIS SKIRSNIS\n"
         "181 straipsnis. Reikalavimai\nx\n182 straipsnis. Leidimų rūšys\ny“\n"
         "3 straipsnis. Lietuvos Respublikos socialinių paslaugų įstatymo Nr. X-493 nauja redakcija\n"
         "Pakeisti ir išdėstyti nauja redakcija:\n„1 straipsnis. Įstatymo paskirtis\nz\n"
         "2 straipsnis. Pagrindinės sąvokos\nw\n4 straipsnis. Įstatymo įsigaliojimas\nkita“\n"
         "4 straipsnis. Įstatymo įsigaliojimas\n1. Šis įstatymas, išskyrus 3 straipsnį, įsigalioja 2023 m. gruodžio 31 d.\n"
         "2. Šio įstatymo 3 straipsnis įsigalioja 2024 m. liepos 1 d.\n")
    law = parse_amending("XIV-2357", t, "2024-07-01")
    assert law.chapters == {2: ["III/4"]}
    assert law.rewrite_own == 3 and law.rewrite_date() == "2024-07-01"
    assert law.entry_articles == {4} and law.targets == {1: ["19"]}
    from ltlaw.currency import _in_part
    from ltlaw.parse import Heading
    p = [Heading("skyrius", "III", ""), Heading("skirsnis", "4", "")]
    assert _in_part(p, "III/4") and _in_part(p, "*/4") and not _in_part(p, "II/4") and not _in_part(p, "III/3")


def test_statute_forms_parentheses_and_compound_ordinals():
    from ltlaw.currency import _sup_parens, _ordinal
    from ltlaw.parse import _heading
    assert _sup_parens("Dėl … statuto Nr. I-399 15(5) ir 3(1) straipsnių") == "Dėl … statuto Nr. I-399 15-5 ir 3-1 straipsnių"
    assert _heading("DVIDEŠIMT KETVIRTASIS SKIRSNIS") == ("skirsnis", "24")
    assert _heading("DVIDEŠIMT AŠTUNTASIS(1) SKIRSNIS") == ("skirsnis", "28-1")
    assert _heading("TRISDEŠIMTASIS SKIRSNIS") == ("skirsnis", "30")
    assert _ordinal("dvidešimt ketvirt") == 24 and _ordinal("ketvirt") == 4
    law = parse_amending("XIV-1945", "11 straipsnis. Dvidešimt ketvirtojo skirsnio pakeitimas\nPakeisti.\n"
                         "12 straipsnis. Statuto įsigaliojimas\nŠis statutas įsigalioja 2023 m. birželio 1 d.\n", "2023-06-01")
    assert law.chapters == {11: ["*/24"]} and law.default == "2023-06-01"


def test_whole_act_rewrite_staged_by_article():
    # VAĮ XIII-2987: the whole act anew in its article 1; some articles of the new wording take effect later
    t = ("1 straipsnis. Lietuvos Respublikos viešojo administravimo įstatymo Nr. VIII-1234 nauja redakcija\n"
         "Pakeisti ir išdėstyti nauja redakcija:\n„1 straipsnis. Paskirtis\nx\n33 straipsnis. Skundai\ny“\n"
         "2 straipsnis. Įstatymo įsigaliojimas\n"
         "1. Šis įstatymas, išskyrus šio straipsnio 2 ir 3 dalis, įsigalioja 2020 m. lapkričio 1 d.\n"
         "2. Šio įstatymo 1 straipsnyje išdėstyto Lietuvos Respublikos viešojo administravimo įstatymo 9 straipsnis "
         "įsigalioja 2021 m. liepos 1 d.\n"
         "3. Nuo 2023 m. sausio 1 d. įsigalioja tokia šio įstatymo 1 straipsnyje išdėstyto Lietuvos Respublikos "
         "viešojo administravimo įstatymo 33 straipsnio redakcija:\n„33 straipsnis. Skundai\nz“\n")
    law = parse_amending("XIII-2987", t, "2020-11-01")
    assert law.rewrite_own == 1 and law.rewrite_date() == "2020-11-01" and law.own_dates == {}
    assert law.staged == {"9": {"2021-07-01"}, "33": {"2023-01-01"}}


def test_quoted_article_in_an_article_is_text():
    # SŽNSĮ 143: "Pakeisti šio įstatymo 10 straipsnį ir jį išdėstyti taip: „10 straipsnis. …“" is 143's text, not article 10
    act = parse("""Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
2016 m. rugsėjo 14 d. Nr. XII-1
Vilnius
10 straipsnis. Taikymas
Tekstas.
11 straipsnis. Šio įstatymo 10 straipsnio nauja redakcija
Pakeisti šio įstatymo 10 straipsnį ir jį išdėstyti taip:
„10 straipsnis. Taikymas
1. Naujas tekstas.“
""")
    assert [a.label for a in act.main.articles] == ["10", "11"]
    assert "„10 straipsnis. Taikymas" in [b.text for b in act.main.articles[1].blocks]
    # several articles quoted in a row: all of them are text of the quoting article
    act = parse("""Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
2016 m. rugsėjo 14 d. Nr. XII-1
Vilnius
6 straipsnis. Šeštas
Tekstas.
7 straipsnis. Septintas
Tekstas.
8 straipsnis. Pakeitimai
Pakeisti šio įstatymo 6 ir 7 straipsnius ir juos išdėstyti taip:
„6 straipsnis. Šeštas
1. Naujas.
7 straipsnis. Septintas
Naujas tekstas.“
9 straipsnis. Devintas
Tekstas.
""")
    assert [a.label for a in act.main.articles] == ["6", "7", "8", "9"]


def test_heading_says_repealed():
    from ltlaw.currency import _article_repealed
    act = parse("""Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
2016 m. rugsėjo 14 d. Nr. XII-1
Vilnius
15 straipsnis. Gynybos štabas (neteko galios)
Straipsnio pakeitimai:
Nr. XI-1303, 2011-03-31, Žin., 2011, Nr. 46-2155 (2011-04-16)
16 straipsnis. Kitas
Tekstas.
""")
    assert _article_repealed(act.main.articles[0]) == (True, None)
    assert _article_repealed(act.main.articles[1]) == (False, None)


def test_renumbering_targets_the_new_numbers():
    """XV-1217: "Buvusius Statuto 18610–18614 straipsnius laikyti atitinkamai 18611–18615 straipsniais" (flattened
    superscripts): 186¹⁵ is a target, so the act lacking it gets the "not yet in this text" notice and page (B41)."""
    text = ("1 straipsnis. 18610–18614 straipsnių pernumeravimas\n"
            "Buvusius Statuto 18610–18614 straipsnius laikyti atitinkamai 18611–18615 straipsniais.\n"
            "2 straipsnis. Statuto įsigaliojimas\nŠis Statutas įsigalioja 2026 m. spalio 20 d.\n")
    law = parse_amending("XV-1", text, "2026-10-20")
    labels = ["186"] + [f"186-{k}" for k in range(1, 15)]
    new = {decode_new_label(t, labels) for t in law.targets[1]} - set(labels)
    assert new == {"186-15"}


def test_an_act_named_only_in_another_acts_quoted_title_is_not_amended():
    """No. 744/2025 amends resolution No. 496 „Dėl Lietuvos Respublikos darbo kodekso įgyvendinimo“, not DK (B42);
    a law amending DK itself still counts."""
    act = parse("Suvestinė redakcija nuo 2026-01-01\nDARBO KODEKSAS\n6 straipsnis. Šeštas\nTekstas.\n")
    meta = {"744/2025-10-29": {"atv_dok_nr": "744", "dokumento_id": "D1", "priimtas": "2025-10-29",
                               "paskelbta_tar": "2026-06-01", "isigalioja": "2026-07-01",
                               "pavadinimas": "Dėl Lietuvos Respublikos Vyriausybės 2017 m. birželio 21 d. nutarimo Nr. 496 "
                                              "„Dėl Lietuvos Respublikos darbo kodekso įgyvendinimo“ pakeitimo"},
            "XV-1": {"atv_dok_nr": "XV-1", "dokumento_id": "D2", "priimtas": "2026-05-01",
                     "paskelbta_tar": "2026-06-01", "isigalioja": "2026-07-01",
                     "pavadinimas": "Lietuvos Respublikos darbo kodekso Nr. XII-2603 6 straipsnio pakeitimo įstatymas"}}
    cands = _candidate_laws(act, {"genitive": "darbo kodekso", "number": "XII-2603"}, MetaLaws(meta), "2026-10-19")
    assert [law.nr for law, _ in cands] == ["XV-1"]


def test_a_law_amending_an_addition_law_is_found():
    """XV-648 amends "… Įstatymo papildymo 10¹ straipsniu įstatymo Nr. XV-445" (its entry article): it re-dates
    XV-445, whose title ends in "papildymo … straipsniu", not "pakeitimo" (B45)."""
    meta = {"XV-648": {"atv_dok_nr": "XV-648", "dokumento_id": "D1", "priimtas": "2025-12-09", "paskelbta_tar": "2025-12-15",
                       "isigalioja": "2025-12-16",
                       "pavadinimas": "Lietuvos Respublikos pakuočių ir pakuočių atliekų tvarkymo įstatymo Nr. IX-517 2, 6, 7 "
                                      "straipsnių pakeitimo ir Įstatymo papildymo 10-1 straipsniu įstatymo Nr. XV-445 10 "
                                      "straipsnio pakeitimo įstatymas"}}
    assert [d["atv_dok_nr"] for d in MetaLaws(meta).amended_by("XV-445")] == ["XV-648"]


def test_articles_of_an_added_chapter_are_targets():
    """XV-609: "6 straipsnis. Įstatymo papildymo V¹ skyriumi" adds 18¹–18³ (headings inside the quoted wording; B44)."""
    text = ("6 straipsnis. Įstatymo papildymo V1 skyriumi\nPapildyti Įstatymą V1 skyriumi:\n„V1 SKYRIUS\nSPORTININKAI\n"
            "181 straipsnis. Pirmas\nTekstas.\n182 straipsnis. Antras\nTekstas.“\n"
            "7 straipsnis. Įstatymo įsigaliojimas\nŠis įstatymas įsigalioja 2026 m. sausio 1 d.\n")
    law = parse_amending("XV-609", text, "2026-01-01")
    assert law.targets[6] == ["181", "182"]


def test_new_wording_source_line():
    """Today's text from a resolution's new wording names it as such (B47)."""
    from ltlaw.render import _today_source
    from ltlaw.today import TodayText
    tt = TodayText(article=None, origin="new wording", version_from="2026-05-01", version_to=None, ref="260/2026-04-15")
    assert _today_source(tt) == ("Vyriausybės 2026 m. balandžio 15 d. nutarimo Nr. 260 nauja redakcija, taikoma nuo 2026-05-01 "
                                 "(oficialus tekstas; suvestinė redakcija atviruose duomenyse dar neparengta)")


def test_narrow_no_break_space_in_headings():
    """XV-734 writes "1 straipsnis. 1 straipsnio pakeitimas": still a heading (B49)."""
    law = parse_amending("XV-734", "1 straipsnis. 1 straipsnio pakeitimas\nPakeisti 1 straipsnio 2 dalį.\n", "2026-02-01")
    assert law.targets[1] == ["1"]


def test_new_articles_running_on_are_plain_numbers():
    from ltlaw.currency import _new_labels
    labels = [str(k) for k in range(1, 21)]
    assert _new_labels(["21", "22"], labels) == {"21": "21", "22": "22"}      # after 20: not 2¹, 2² (B49)
    assert _new_labels(["311"], ["30", "31", "32"]) == {"311": "31-1"}


def _amender(nr, targets):
    from ltlaw.currency import AmendingLaw
    law = AmendingLaw(nr, "2025-11-26", all_dates={"2025-11-26"})
    law.targets = targets
    return law


def test_law_of_law_entry_and_final_articles_name_no_article_of_the_act():
    """XV-579 changes XIV-2961's 2nd (→ ATĮ 4) and 10th (its entry article): not every ATĮ article in the title.
    XV-528 changes only XIII-2398's 13th (its final provisions): no VSTĮ article at all, not VSTĮ 13."""
    from ltlaw.currency import AmendingLaw
    x = AmendingLaw("XIV-2961", "2024-09-01", all_dates={"2024-09-01"})
    x.targets, x.entry_articles = {1: ["2"], 2: ["4"], 3: ["25"]}, {10}
    laws = MetaLaws({})
    laws._cache["XIV-2961"] = x
    law = _amender("XV-579", {1: ["2"], 2: ["10"]})
    laws._remap_law_of_law(law, "Lietuvos Respublikos atliekų tvarkymo įstatymo Nr. VIII-787 2, 4, 25 straipsnių pakeitimo "
                                "įstatymo Nr. XIV-2961 2 ir 10 straipsnių pakeitimo įstatymas")
    assert law.targets == {1: ["4"], 2: []} and law.of_law == "XIV-2961"
    y = AmendingLaw("XIII-2398", "2019-10-01", all_dates={"2019-10-01"})
    y.targets, y.entry_articles = {1: ["5"], 2: ["6"]}, {13}
    laws._cache["XIII-2398"] = y
    law = _amender("XV-528", {1: ["13"]})
    laws._remap_law_of_law(law, "Lietuvos Respublikos valstybės turto įstatymo Nr. VIII-729 5, 6 straipsnių pakeitimo "
                                "įstatymo Nr. XIII-2398 13 straipsnio pakeitimo įstatymas")
    assert law.targets == {} and law.title_targets == []


PROMULGATION = """Suvestinė redakcija nuo 2024-01-01
LIETUVOS RESPUBLIKOS
BANDOMASIS ĮSTATYMAS
11 straipsnis. Įstatymų pasirašymo tvarka
3. Įstatymo teksto pabaigoje prieš Respublikos Prezidento parašą įrašoma: „Skelbiu šį Lietuvos Respublikos Seimo priimtą įstatymą.“
12 straipsnis. Dovanos
1. Dovanos yra valstybės turtas.
Vadovaudamasis Lietuvos Respublikos Konstitucijos 71 straipsnio antrąja dalimi, skelbiu šį Lietuvos Respublikos Seimo priimtą įstatymą.
SEIMO PIRMININKAS
"""


def test_the_promulgation_formula_quoted_in_an_article_is_text():
    # Prezidento įstatymas 11 quotes it: articles 12–24 were read as signature lines (2026-11-02); the Speaker's form
    # opening with "Vadovaudamasis … dalimi," is a real one (PVMĮ)
    a = parse(PROMULGATION)
    assert [(x.label, len(x.blocks)) for x in a.main.articles] == [("11", 1), ("12", 1)]
    assert a.main.signature[0].startswith("Vadovaudamasis")


WRAPPED = """LIETUVOS RESPUBLIKOS
VIENKARTINIO TURTO DEKLARAVIMO
ĮSTATYMAS
2003 m. gruodžio 4 d. Nr. IX-1874
Vilnius
I SKYRIUS
BENDROSIOS
NUOSTATOS
1
straipsnis. Įstatymo paskirtis
Šis Įstatymas
nustato vienkartinį
gyventojams
nuosavybės teise priklausančio
turto
deklaravimą.
2
straipsnis. Turtą deklaruojantys asmenys
Pagal šį
Įstatymą turtą deklaruoja:
1) nuolatiniai
gyventojai;
2) kiti asmenys.
"""


def test_a_hard_wrapped_consolidation_is_joined_back_into_paragraphs():
    # SLTKĮ, VGTDĮ (2026-11-03): numbers alone before "straipsnis.", sentences broken over lines: 0 articles before
    a = parse(WRAPPED)
    assert [(x.label, x.title) for x in a.main.articles] == [("1", "Įstatymo paskirtis"), ("2", "Turtą deklaruojantys asmenys")]
    assert [b.text for b in a.main.articles[0].blocks] == ["Šis Įstatymas nustato vienkartinį gyventojams nuosavybės teise priklausančio turto deklaravimą."]
    assert [b.text for b in a.main.articles[1].blocks] == ["Pagal šį Įstatymą turtą deklaruoja:", "1) nuolatiniai gyventojai;",
                                                            "2) kiti asmenys."]
    assert a.main.headings[0].title == "BENDROSIOS NUOSTATOS"


def test_e_tar_editions_with_new_and_old_version_ids():
    # versions from before e-tar keep ids like "TAIS_82194": they were skipped, so 9 old acts looked unverifiable (B66)
    from ltlaw.etar import editions
    page = ('<tr><td><a href="/portal/lt/legalAct/TAR.40E832B5515A/TAIS_82194">Suvestinė nuo 1999-05-20</a></td><td></td>'
            '<td>1999-05-20 įstatymas Nr. VIII-1196</td></tr>'
            '<tr><td><a href="/portal/lt/legalAct/df9ce4f0/zqElJTQeVq">Suvestinė nuo 2027-01-01</a></td><td>2027-12-31</td></tr>')
    assert editions("TAR.40E832B5515A", page) == [{"id": "TAIS_82194", "valid_from": "1999-05-20", "valid_to": None}]
    assert editions("df9ce4f0", page) == [{"id": "zqElJTQeVq", "valid_from": "2027-01-01", "valid_to": "2027-12-31"}]


def test_the_registers_part_markers_are_not_text():
    # "part_<hex>_end" closes a document part in the open data; inside a point it was shown (SEANM 31, EĮBNAA; B67)
    a = parse(WRAPPED.replace("deklaravimą.", "deklaravimą.\npart_9e8c2e6c9c144c049d1b8408f3cf1fb0_end"))
    assert "part_" not in " ".join(b.text for x in a.main.articles for b in x.blocks)
    assert [b.text for b in a.main.articles[0].blocks][-1].endswith("deklaravimą.")


def test_a_very_long_name_gives_a_short_unique_alias():
    from ltlaw.render import act_alias
    long1 = "Jūrinės teritorijos naudojimo atsinaujinančius energijos išteklius naudojančių elektrinių plėtrai ir " \
            "eksploatacijai konkurso, organizuojamo pagal Lietuvos Respublikos atsinaujinančių išteklių energetikos " \
            "įstatymo 22-1 straipsnį, sąlygų aprašas"
    a1, a2 = act_alias(None, long1, "X", None), act_alias(None, long1.replace("sąlygų", "tvarkos"), "Y", None)
    assert len(a1.encode()) < 160 and a1 != a2 and a1.startswith("jurines-teritorijos-naudojimo-")
    assert act_alias(None, "Viešųjų įstaigų įstatymas", "VšĮĮ", None) == "viesuju-istaigu-istatymas"  # short names as before
    assert act_alias(None, "Darbo kodeksas", "DK", "DK") == "dk"


def test_a_ministers_order_in_the_first_person_and_letter_spaced():
    # "P a k e i č i u … 1.3. Pakeičiu VI skyrių ir jį išdėstau taip" (1-144/2025 for NGDSTVBA 28–36): the chapter rule
    # knew only the Government's "Pakeisti", so the order changed no points there; "N u s t a t a u, kad:" dates it
    t = ("1. P a k e i č i u Naujų gamtinių dujų sistemų prijungimo tvarkos aprašą:\n1.1. Pakeičiu 1 punktą ir jį išdėstau taip:\n"
         "„1. Aprašas nustato.“\n1.3. Pakeičiu VI skyrių ir jį išdėstau taip:\n„VI SKYRIUS\n28. Sistemos perkeliamos.\n"
         "29. Asmuo pateikia prašymą.“\n2. N u s t a t a u, kad:\n2.1. šis įsakymas įsigalioja 2025 m. birželio 1 d.")
    law = currency.parse_amending_resolution("1-144/2025-05-28", t, "2025-06-01")
    assert law.targets == {2: ["1"]} and law.chapters == {3: ["VI"]} and law.default == "2025-06-01"


def test_a_ministers_order_setting_out_the_whole_description_anew():
    # "P a k e i č i u … tvarkos aprašą ir jį išdėstau nauja redakcija:" (D1-434/2024): the whole document, as a
    # resolution's "Pakeisti … ir jį išdėstyti nauja redakcija" (B69)
    t = ("1. P a k e i č i u Priklausomųjų želdynų plotų normų apskaičiavimo tvarkos aprašą ir jį išdėstau nauja redakcija:\n"
         "„1. Normos nustatomos.\n2. Sąvokos.“\n2. N u s t a t a u, kad šis įsakymas įsigalioja 2024 m. gruodžio 6 d.")
    law = currency.parse_amending_resolution("D1-434/2024-12-05", t, "2024-12-06")
    assert law.rewrite_own == 1 and law.default == "2024-12-06"


def test_an_annex_snippet_says_whose_annex_and_how_it_begins():
    """The annex's heading in capitals alone was the whole snippet (Bing: descriptions too short, 2026-11-21)."""
    from types import SimpleNamespace as N
    from ltlaw.render import _annex_description
    caps = "ĮGYVENDINAMI EUROPOS SĄJUNGOS TEISĖS AKTAI"
    x = N(title=caps, blocks=[N(text=caps), N(text="1. 2001 m. gruodžio 3 d. Europos Parlamento ir Tarybos direktyva "
                                                    "2001/95/EB dėl bendros gaminių saugos (OL 2004 m. specialusis leidimas).")])
    d = _annex_description("Lietuvos Respublikos produktų saugos įstatymo priedas", x)
    assert d.startswith("Lietuvos Respublikos produktų saugos įstatymo priedas · 1. 2001 m.") and caps not in d
    assert len(d) <= 155 and d.endswith("…")
    assert _annex_description("Taisyklių 2 priedas", N(title="Prašymo forma", blocks=[])) == "Taisyklių 2 priedas · Prašymo forma"
    form = N(title="(Paraiškos forma)", blocks=[N(text="□[] Pirminė paraiška □[] Patikslinta paraiška")])
    assert _annex_description("Taisyklių 1 priedas", form) == "Taisyklių 1 priedas · (Paraiškos forma) · Pirminė paraiška Patikslinta paraiška"


STATUTE_AFTER_SIGNATURE = """Suvestinė redakcija nuo 2024-07-01
LIETUVOS RESPUBLIKOS BANDOMOJO STATUTO PATVIRTINIMO ĮSTATYMAS
1999 m. gegužės 20 d. Nr. VIII-1
Vilnius
1 straipsnis. Bandomojo statuto patvirtinimas
Patvirtinti bandomąjį statutą (pridedama).
Skelbiu šį Lietuvos Respublikos Seimo priimtą įstatymą.
RESPUBLIKOS PREZIDENTAS VARDAS PAVARDĖ
BANDOMASIS STATUTAS
I DALIS
BENDROSIOS NUOSTATOS
1 straipsnis. Statuto paskirtis
Statuto paskirtis – bandyti.
2 straipsnis. Taikymas
Statutas taikomas kariams.
"""


def test_document_after_the_approval_laws_signature_is_the_main_act():
    """LKDSP2Į (2026-11-25): no "PATVIRTINTA" stamp; the statute's title follows the signature."""
    act = parse(STATUTE_AFTER_SIGNATURE)
    assert [s.kind for s in act.segments] == ["approval", "main"]
    assert act.main.title == "BANDOMASIS STATUTAS"
    assert [(a.label, a.blocks[0].text) for a in act.main.articles] == [
        ("1", "Statuto paskirtis – bandyti."), ("2", "Statutas taikomas kariams.")]
    assert not act.main.signature


def test_an_alias_holds_no_character_a_file_name_cant():
    # 2026-11-26: "M 1:5 000" in a rule set's name gave api/v1/refs/…m-1:5-000….json; the artifact upload refused it
    from ltlaw.render import act_alias
    a = act_alias(None, "Lietuvos Respublikos teritorijos M 1:5 000 kontrolinių žemės sklypų aprašas", "X", None)
    assert a == "lietuvos-respublikos-teritorijos-m-1-5-000-kontroliniu-zemes-sklypu-aprasas"
    assert act_alias(None, "Tvarkos aprašas, AB „Operatorius“ – 2014–2020", "X", None) == "tvarkos-aprasas,-ab-„operatorius“-–-2014–2020"  # others as before
