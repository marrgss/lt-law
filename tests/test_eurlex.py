"""EU acts from EUR-Lex (D-037): the XHTML as the register's text layout, and from when each article applies."""
import re

import pytest

from ltlaw import eurlex
from ltlaw.parse import parse

X = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="title-doc-first">EUROPOS PARLAMENTO IR TARYBOS REGLAMENTAS (ES) 2099/1</p>
<p class="title-division-1">I SKYRIUS</p><p class="title-division-2">Bendrosios nuostatos</p>
<div class="eli-subdivision" id="art_1"><p class="title-article-norm">1 straipsnis</p>
 <div class="eli-title"><p class="stitle-article-norm">Dalykas</p></div>
 <div class="norm"><span class="no-parag">1.  </span><div class="norm inline-element"><span class="boldface">►C1</span> Šiuo reglamentu nustatomos taisyklės.<span class="boldface"> ◄ </span> Jei reikia, išimtys.</div></div>
 <div class="norm"><span class="no-parag">2.  </span><div class="norm inline-element"><p class="norm inline-element">Jis netaikomas, kai:</p>
  <div class="grid-container grid-list"><div class="list grid-list-column-1"><span>a) </span></div>
   <div class="grid-list-column-2"><p class="norm">duomenys tvarkomi <span class="arrow">►M1</span> namuose ◄ 2 kartus;</p></div></div>
  <div class="grid-container grid-list"><div class="list grid-list-column-1"><span>— </span></div>
   <div class="grid-list-column-2"><div class="list">kitais atvejais.</div></div></div></div></div>
</div>
<div><p class="title-division-1">II</p><p class="title-division-2">SKYRIUS</p><p class="title-division-2">Baigiamosios nuostatos</p></div>
<div class="eli-subdivision" id="art_1a"><p class="title-article-norm">1a straipsnis</p>
 <div class="eli-title"><p class="stitle-article-norm">Įsigaliojimas ir taikymas</p></div>
 <p class="norm">Šis reglamentas įsigalioja dvidešimtą dieną po jo paskelbimo.</p>
 <p class="norm">Jis taikomas nuo 2030 m. sausio 1 d. Tačiau 1 straipsnis taikomas nuo 2020 m. sausio 1 d.</p>
</div>
<div id="anx_I "><p class="title-annex-1">I PRIEDAS</p><p class="title-annex-2">Sąrašas</p><p class="norm">1. Vienas.</p></div>
</body></html>"""


def test_xhtml_becomes_the_register_layout_word_for_word():
    text, info = eurlex.to_text(X, "2099-01-01")
    assert info["articles"] == 2 and info["title"].startswith("EUROPOS PARLAMENTO")
    act = parse(text)
    assert act.version_from == "2099-01-01"
    a1, a1a = act.main.articles
    assert (a1.label, a1.title, a1a.label) == ("1", "Dalykas", "1a")           # an inserted article "1a" is its own
    assert [h.kind + " " + h.num for h in a1a.path] == ["skyrius II"]           # "II" / "SKYRIUS" read as one heading
    texts = [b.text for b in a1.blocks]
    assert "a) duomenys tvarkomi namuose 2 kartus;" in texts                   # markers gone, the "2" after ◄ kept
    assert "— kitais atvejais." in texts                                       # a list item's text right in a div
    assert "1. Šiuo reglamentu nustatomos taisyklės. Jei reikia, išimtys." in texts  # the letter after "◄ " kept (GDPR 43)
    assert [x.num for x in act.main.annexes] == ["I"]
    assert eurlex.check(X, text) == []
    bad = text.replace("1. Vienas.", "1. Vienas")
    assert eurlex.check(X, bad) == ["annex I: text differs"]                   # annexes are checked too


def test_a_later_general_date_makes_articles_pending_except_earlier_ones():
    act = parse(eurlex.to_text(X, "2099-01-01")[0])
    stages, notices = eurlex.application(act, "2026-10-29")
    assert "1" not in stages                                                   # applies since 2020
    assert stages["1a"][:2] == ("pending", "2030-01-01")
    assert notices and "2030-01-01" in notices[0]
    assert eurlex.application(act, "2031-01-01") == ({}, [])                   # everything applies by then
    text = ("Suvestinė redakcija nuo 2026-06-22\n6a straipsnis. Solidarumas\nTekstas.\n22 straipsnis. Įsigaliojimas\n"
            "Jis taikomas nuo 2017 m. lapkričio 1 d. 6a straipsnis taikomas iki 2027 m. gruodžio 31 d.\n")
    stages, notices = eurlex.application(parse(text), "2026-10-30")             # until, not from (2017/1938 22)
    assert stages == {} and notices == ["Kai kurios nuostatos taikomos tik iki 2027-12-31 – žr. 22 straipsnį."]


def test_cited_names_cover_the_usual_lithuanian_forms():
    names = eurlex.cited_names({"number": "(ES) Nr. 910/2014", "genitive": "Reglamento (ES) Nr. 910/2014", "kind": "Reglamentas"})
    assert "reglamento (ES) Nr. 910/2014" in names and "reglamento (ES) 910/2014" in names
    # an EU decision (2026-11-11: the market stability reserve 2015/1814) is cited as "Sprendimo (ES) 2015/1814"
    names = eurlex.cited_names({"number": "(ES) 2015/1814", "genitive": "Sprendimo (ES) 2015/1814", "kind": "Sprendimas"})
    assert "sprendimo (ES) 2015/1814" in names and not any(n.startswith("reglamento") for n in names)


def test_a_decision_cites_its_own_articles():
    from ltlaw import xref
    m = xref.RE_ACT.search("pagal šio sprendimo 1 straipsnio 5 dalį")
    assert m and m.group(1) == "1"


FLAT = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="title-doc-first">EUROPOS PARLAMENTO IR TARYBOS DIREKTYVA 2099/1/EB</p>
<p class="norm">PRIĖMĖ ŠIĄ DIREKTYVĄ:</p>
<p class="title-article-norm">1 straipsnis</p><p class="stitle-article-norm">Taikymo sritis</p>
<p class="modref"><a href="x">▼M2</a></p>
<p class="norm">1.  Ši direktyva papildo Direktyvą 95/46/EB (Pagrindų direktyva) (<a href="#E0008" id="src.E0008"><span class="superscript">8</span></a>).</p>
<div style="margin-left: 24pt"><p class="norm">a) „naudotojas“ — fizinis asmuo;</p></div>
<p class="title-article-norm">2 straipsnis</p><p class="stitle-article-norm">Adresatai</p>
<p class="norm">Ši direktyva skirta valstybėms narėms.</p>
<hr class="separator-short"/><p class="footnote">( 8 ) OL L 108, 2002 4 24, p. 33.</p>
</body></html>"""


def test_the_older_flat_layout_reads_as_articles_without_footnote_references():
    text, info = eurlex.to_text(FLAT, "2009-12-19")
    act = parse(text)
    assert [(a.label, a.title) for a in act.main.articles] == [("1", "Taikymo sritis"), ("2", "Adresatai")]
    assert [b.text for b in act.main.articles[0].blocks] == [
        "1. Ši direktyva papildo Direktyvą 95/46/EB (Pagrindų direktyva).", "a) „naudotojas“ — fizinis asmuo;"]
    assert "OL L 108" not in text                                              # the footnotes stay out
    assert eurlex.check(FLAT, text) == []
    assert eurlex.check(FLAT, "Suvestinė redakcija nuo 2009-12-19\n")[:3] == ["no articles parsed"] + [
        "article 1: not parsed", "article 2: not parsed"]                     # an unread layout never passes as empty


FLAT_ANNEXES = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="title-doc-first">KOMISIJOS REGLAMENTAS (ES) 2099/3</p>
<p class="title-article-norm">1 straipsnis</p><p class="stitle-article-norm">Išimtys</p>
<p class="norm">I priede išvardytos nuostatos Lietuvos perdavimo sistemos operatoriui netaikomos.</p>
<p class="title-article-norm">2 straipsnis</p><p class="stitle-article-norm">Įsigaliojimas</p>
<p class="norm">Šis reglamentas įsigalioja dvidešimtą dieną po jo paskelbimo.</p>
<p class="norm">Šis reglamentas privalomas visas ir tiesiogiai taikomas visose valstybėse narėse.</p>
<p><br/></p><hr class="separator-annex"/><p><br/></p>
<p class="title-annex-1">I PRIEDAS</p><p class="norm">Nuostatos, kurios netaikomos:</p>
<div class="grid-container grid-list"><div class="list grid-list-column-1"><span>1) </span></div>
 <div class="grid-list-column-2"><p class="norm">16 straipsnio 2 dalies d, e ir f punktai;</p></div></div>
<hr class="separator-annex"/>
<p class="title-annex-1">II PRIEDAS</p><p class="norm">Galia didesnė nei 10<span class="superscript">25</span> operacijų.</p>
<hr class="separator-annex"/>
<p class="title-annex-1">KOMISIJOS PAREIŠKIMAS</p><p class="norm">Komisija mano, kad ribinių verčių nustatyti negalima.</p>
<hr class="separator-short"/><p class="footnote">( 1 ) OL L 108, 2002 4 24, p. 33.</p>
</body></html>"""

OJ_FINAL = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="oj-doc-ti">KOMISIJOS REGLAMENTAS (ES) 2099/4</p>
<div class="eli-subdivision" id="art_1"><p class="oj-ti-art">1 straipsnis</p>
 <div class="eli-title" id="art_1.tit_1"><p class="oj-sti-art">Įsigaliojimas</p></div>
 <p class="oj-normal">Šis reglamentas įsigalioja dvidešimtą dieną po jo paskelbimo.</p></div>
<div class="eli-subdivision" id="fnp_1"><div class="oj-final">
 <p class="oj-normal">Šis reglamentas privalomas visas ir tiesiogiai taikomas visose valstybėse narėse.</p>
 <p class="oj-normal">Priimta Briuselyje 2099 m. rugpjūčio 17 d.</p>
 <div class="oj-signatory"><p class="oj-signatory">Komisijos vardu</p><p class="oj-signatory">Pirmininkas</p></div>
</div></div>
<hr class="oj-separator"/><p class="oj-normal">ELI: http://data.europa.eu/eli/reg/2099/4/oj</p>
</body></html>"""


def test_the_older_layouts_annexes_and_the_closing_words_are_read_and_checked_independently():
    text, _ = eurlex.to_text(FLAT_ANNEXES, "2021-03-15")
    act = parse(text)
    assert [a.header for a in act.main.annexes] == ["I PRIEDAS", "II PRIEDAS"]  # left out until 2026-10-30 (SOGL)
    assert act.main.annexes[0].blocks[-1].text == "1) 16 straipsnio 2 dalies d, e ir f punktai;"
    assert "nei 10²⁵ operacijų" in text                                        # not "10-25" (AI Act 51)
    assert "PAREIŠKIMAS" not in text and "OL L 108" not in text                # a statement, a footnote: not the act's
    assert eurlex.check(FLAT_ANNEXES, text) == []
    lost = text.replace("1) 16 straipsnio 2 dalies d, e ir f punktai;\n", "")
    assert any("in the XHTML, 0 here" in p for p in eurlex.check(FLAT_ANNEXES, lost))  # what both read alike, but missing
    twice = text.replace("Nuostatos, kurios netaikomos:\n", "Nuostatos, kurios netaikomos:\n" * 2)
    assert eurlex.check(FLAT_ANNEXES, twice)                                   # and what is there twice
    text, _ = eurlex.to_text(OJ_FINAL, "2099-09-07")
    a = parse(text).main.articles[0]
    assert a.title == "Įsigaliojimas" and a.blocks[-1].text.startswith("Šis reglamentas privalomas visas")
    assert "Priimta" not in text and "Pirmininkas" not in text and "ELI" not in text
    assert eurlex.check(OJ_FINAL, text) == []


IMAGES = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="oj-doc-ti">EUROPOS PARLAMENTO IR TARYBOS REGLAMENTAS (ES) 2099/5</p>
<div class="eli-subdivision" id="art_1"><p class="oj-ti-art">1 straipsnis</p>
 <p class="oj-normal">Reglamentas (ES) 2017/1938 iš dalies keičiamas taip:</p>
 <table><tbody><tr><td><p class="oj-normal">1)</p></td>
  <td><p class="oj-normal">įterpiamas šis straipsnis:</p>
  <div><p class="oj-ti-art">„8a straipsnis</p>
  <p class="oj-sti-art">Kibernetinio saugumo priemonės</p>
  <p class="oj-normal">Valstybės narės imasi priemonių.“</p></div>;</td></tr></tbody></table>
 <p class="oj-normal">Profilis:</p><figure><img src="data:image/jpg;base64,AAAA" alt="image"/></figure>
</div>
<div class="eli-container" id="anx_I"><p class="oj-doc-ti">I PRIEDAS</p>
 <p class="oj-doc-ti">Skaičiavimas pagal N – 1 formulę</p>
 <p class="container-center"><img src="data:image/jpg;base64,BBBB" alt="image"/></p>, N – 1 ≥ 100 %<p class="oj-normal">Parametrai pagrįsti.</p>
 <div class="oj-enumeration-spacing"><p style="display: inline;">3.   </p>
  <span>Atsižvelgiama į rekomendaciją 2012/148/ES <a id="ntc1-X" href="#ntr1-X">(<span class="oj-super oj-note-tag">1</span>)</a>, tiek, kiek taikytina.</span>
  <p class="oj-normal">Taip pat atsižvelgiama į sinergiją.</p></div>
</div></body></html>"""


def test_images_loose_text_quoted_titles_and_inline_numbers_are_kept():
    text, info = eurlex.to_text(IMAGES, "2099-01-01")
    lines = text.splitlines()
    assert "„8a straipsnis" in lines and "Kibernetinio saugumo priemonės" in lines  # an article quoted in an amendment
    assert "Valstybės narės imasi priemonių.“;" in lines                       # its "“;", as in a point
    assert "[paveikslas 1]" in lines and info["images"] == {"1": "data:image/jpg;base64,AAAA", "2": "data:image/jpg;base64,BBBB"}
    assert "[paveikslas 2], N – 1 ≥ 100 %" in lines                            # the text between two blocks
    assert "3. Atsižvelgiama į rekomendaciją 2012/148/ES, tiek, kiek taikytina." in lines  # a bare <span>, no " ,"
    assert eurlex.check(IMAGES, text) == []
    assert eurlex.check(IMAGES, text.replace(", N – 1 ≥ 100 %", ""))           # the plain reading misses nothing
    from ltlaw import render
    render.IMAGES.clear(); render.IMAGES.update({"2": "/es/X/img/2.jpg"})
    out = render._blocks([b for b in parse(text).main.annexes[0].blocks], {})
    assert '<img src="/es/X/img/2.jpg"' in str(out[0]["html"]) and ", N – 1" in str(out[0]["html"])
    render.IMAGES.clear()


def test_an_eu_title_is_the_level_above_its_chapters():
    text = ("Suvestinė redakcija nuo 2025-02-04\nII ANTRAŠTINĖ DALIS\nENISA\nI SKYRIUS\nĮGALIOJIMAI\n"
            "3 straipsnis. Įgaliojimai\nTekstas.\n")
    a = parse(text).main.articles[0]
    assert [(h.kind, h.num, h.title) for h in a.path] == [("antraštinė dalis", "II", "ENISA"), ("skyrius", "I", "ĮGALIOJIMAI")]
    text = ("Suvestinė redakcija nuo 2021-03-15\nI DALIS\nBENDROSIOS NUOSTATOS\n1 straipsnis. Dalykas\nTekstas.\n"
            "II DALIS\nEKSPLOATAVIMO SAUGUMAS\n1 ANTRAŠTINĖ DALIS\nEKSPLOATAVIMO SAUGUMO REIKALAVIMAI\nI SKYRIUS\n"
            "SISTEMOS BŪSENOS\n18 straipsnis. Būsenos\nTekstas.\n")
    a1, a18 = parse(text).main.articles                                        # SOGL: part > title > chapter
    assert [(h.kind, h.num) for h in a18.path] == [("dalis", "II"), ("antraštinė dalis", "1"), ("skyrius", "I")]
    assert a1.blocks[-1].text == "Tekstas."                                    # a title's heading never ends an article


TABLES = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="oj-doc-ti">KOMISIJOS ĮGYVENDINIMO REGLAMENTAS (ES) 2099/2</p>
<div class="eli-subdivision" id="art_1"><p class="oj-ti-art">1 straipsnis</p><p class="oj-normal">Taikomas priedas.</p></div>
<div id="anx_1"><p class="oj-doc-ti">PRIEDAS</p>
<table><tbody><tr><td/><td><p class="oj-normal">1.1.1.</p></td>
 <td><span>Politika turi atitikti šiuos reikalavimus:</span><table><tbody><tr><td><p>a)</p></td><td><p>ji nustatoma;</p></td></tr>
 <tr><td><p>b)</p></td><td><p>ji peržiūrima.</p></td></tr></tbody></table></td></tr></tbody></table>
<table><tbody><tr><td><p>Sektorius</p></td><td><p>Subsektorius</p></td><td><p>Subjekto rūšis</p></td></tr>
 <tr><td rowspan="2"><p>1. Energetika</p></td><td><p>a) Elektra</p></td>
  <td><p>— Direktyvos (ES) 2019/944<a href="#ntr1-X"> (<span class="oj-super">1</span>)</a>2 straipsnio operatoriai</p><p>— Gamintojai</p></td></tr>
 <tr><td><p>b) Nafta</p></td><td><p>— Naftotiekių operatoriai</p></td></tr></tbody></table>
</div></body></html>"""


def test_tables_keep_their_columns_and_lists_laid_out_as_tables_read_as_lists():
    text, _ = eurlex.to_text(TABLES, "2099-01-01")
    lines = text.splitlines()
    assert "1.1.1. Politika turi atitikti šiuos reikalavimus:" in lines        # a blank first column, a "1.1.1." number,
    assert "a) ji nustatoma;" in lines and "b) ji peržiūrima." in lines        # its text in a span, its own list
    i = lines.index("Sektorius | Subsektorius | Subjekto rūšis")
    assert lines[i + 1:i + 4] == [
        "1. Energetika | a) Elektra | — Direktyvos (ES) 2019/944 2 straipsnio operatoriai",  # the footnote's space kept
        " |  | — Gamintojai",                                                  # a cell's next paragraph, a row below
        " | b) Nafta | — Naftotiekių operatoriai"]                             # under a cell spanning two rows
    assert eurlex.check(TABLES, text) == []


def test_table_rows_become_one_table_on_the_page():
    from ltlaw.render import _table_rows
    out = [{"text": "Įvadas."}, {"text": "A | B"}, {"text": "| c"}, {"text": "D | E | F"}, {"text": "Pabaiga."}]
    _table_rows(out)
    assert [x.get("cells") for x in out] == [None, ["A", "B"], ["", "c"], ["D", "E", "F"], None]
    assert [(x.get("tbl_open"), x.get("tbl_close")) for x in out[1:4]] == [(True, False), (False, True), (True, True)]


def test_the_latest_end_of_validity_counts(monkeypatch):
    # EUR-Lex gives one end per consolidated version too: 2019/944 had 2025-10-11 and 9999-12-31 while in force
    rows = [{"date": "2019-06-05", "eif": "2019-07-04", "end": "2025-10-11", "force": "1"},
            {"end": "9999-12-31", "force": "1"}]
    monkeypatch.setattr(eurlex, "sparql", lambda q, timeout=120: rows)
    m = eurlex.metadata("32019L0944")
    assert m["end_of_validity"] == "9999-12-31" and m["in_force"]



def test_an_entry_into_force_before_the_acts_date_is_ignored(monkeypatch):
    # CELLAR gives 2022/2065 (Digital Services Act, of 2022-10-19) two: 2022-02-17 (impossible) and 2022-11-16
    rows = [{"date": "2022-10-19", "eif": "2022-02-17", "force": "1"}, {"eif": "2022-11-16"}]
    monkeypatch.setattr(eurlex, "sparql", lambda q, timeout=120: rows)
    assert eurlex.metadata("32022R2065")["entry_into_force"] == "2022-11-16"

QUIRKS = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="title-doc-first">EUROPOS PARLAMENTO IR TARYBOS REGLAMENTAS (ES) 2099/2</p>
<div class="eli-subdivision" id="art_1"><p class="title-article-norm">1 straipsnis.</p>
 <div class="eli-title"><p class="stitle-article-norm">Dalykas</p></div>
 <p class="norm">Šiuo reglamentu nustatomos taisyklės.</p>
</div>
<div class="eli-subdivision" id="art_2"><p class="title-article-norm">2 straipsnis</p>
 <div class="eli-title"><p class="stitle-article-norm">Direktyvos 2008/98/EB dalinis pakeitimas</p></div>
 <p class="norm">Direktyvos 2008/98/EB 8a straipsnio 7 dalis papildoma šia pastraipa:</p>
 <p class="norm">„Valstybės narės imasi priemonių.</p>
</div>
<div id="cpt_II"><p class="title-division-1">II SKYRIUS</p><p class="title-division-2">Baigiamosios nuostatos</p>
<div class="eli-subdivision" id="art_3"><p class="title-article-norm">3 straipsnis</p>
 <div class="eli-title"><p class="stitle-article-norm">Įsigaliojimas</p></div>
 <p class="norm">Šis reglamentas įsigalioja dvidešimtą dieną po jo paskelbimo.</p>
</div></div>
</body></html>"""


def test_a_heading_with_a_stop_and_an_unclosed_quote_before_a_chapter():
    # "70 straipsnis." (2018/1972); a quote EUR-Lex never closes, right before the act's own chapter (2023/1542 92)
    text, _ = eurlex.to_text(QUIRKS, "2099-01-01")
    act = parse(text)
    assert [a.label for a in act.main.articles] == ["1", "2", "3"]
    a2, a3 = act.main.articles[1:]
    assert a2.blocks[-1].text == "„Valstybės narės imasi priemonių."                # the quote ends with its article
    assert [h.kind + " " + h.num for h in a3.path] == ["skyrius II"]
    assert eurlex.check(QUIRKS, text) == []


SPLIT_HEADINGS = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="title-doc-first">EUROPOS PARLAMENTO IR TARYBOS REGLAMENTAS (ES) 2099/3</p>
<div class="eli-subdivision" id="art_1"><p class="title-article-norm">1 straipsnis</p>
 <div class="eli-title"><p class="stitle-article-norm">Dalykas</p></div>
 <p class="norm">Šiuo reglamentu nustatomos taisyklės.</p></div>
<div id="tis_II"><p class="title-division-1">II</p>
<p class="title-division-1">ANTRAŠTINĖ DALIS</p>
<p class="title-division-2">MUITAI</p>
<div class="eli-subdivision" id="art_2"><p class="title-article-norm">2 straipsnis</p>
 <div class="eli-title"><p class="stitle-article-norm">Muitai</p></div>
 <p class="norm">Muitai taikomi.</p></div>
<div id="cpt_3A"><p class="title-division-1">3A</p>
<p class="title-division-1">SKYRIUS</p>
<p class="title-division-2">KOMITETAS</p>
<div class="eli-subdivision" id="art_2a"><p class="title-article-norm">2a straipsnis</p>
 <div class="eli-title"><p class="stitle-article-norm">Komitetas</p></div>
 <p class="norm">Įsteigiamas komitetas.</p></div>
<div id="cpt_3A.sct_2"><p class="title-division-1">2 SKIRSNIS.</p>
<p class="title-division-2">BUDRUMAS</p>
<div class="eli-subdivision" id="art_3"><p class="title-article-norm">3 straipsnis</p>
 <div class="eli-title"><p class="stitle-article-norm">Budrumas</p></div>
 <p class="norm">Budrumas užtikrinamas.</p></div></div></div></div>
</body></html>"""


def test_headings_split_over_lines_or_numbered_with_a_letter():
    # "II" / "ANTRAŠTINĖ DALIS" (the customs code), "3A" / "SKYRIUS" (EMIR), "2 SKIRSNIS." alone (MDR): each was run
    # into the article before it (2026-11-03, converter 7)
    text, _ = eurlex.to_text(SPLIT_HEADINGS, "2099-01-01")
    act = parse(text)
    assert [a.label for a in act.main.articles] == ["1", "2", "2a", "3"]
    assert act.main.articles[0].blocks[-1].text == "Šiuo reglamentu nustatomos taisyklės."
    assert [h.kind + " " + h.num for h in act.main.articles[3].path] == ["antraštinė dalis II", "skyrius 3A", "skirsnis 2"]
    assert eurlex.check(SPLIT_HEADINGS, text) == []


def _doc(body: str) -> str:  # (as EUR-Lex lays it out: white space between blocks)
    return f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{re.sub(r"(</p>|</div>)(?=<)", r"\1 ", body)}</body></html>'


def _art(num: str, inner: str, title: str = "") -> str:
    sub = f'<div class="eli-title"><p class="stitle-article-norm">{title}</p></div>' if title else ""
    return f'<div class="eli-subdivision" id="art_{num}"><p class="title-article-norm">{num} straipsnis</p>{sub}{inner}</div>'


def _part(num: str, inner: str) -> str:
    return f'<div class="norm"><span class="no-parag">{num}.  </span><div class="norm inline-element">{inner}</div></div>'


def _ok(body: str) -> list[str]:
    x = _doc(body)
    text, _ = eurlex.to_text(x, "2099-01-01")
    assert eurlex.check(x, text) == []
    return text.splitlines()


def test_a_marker_before_a_parts_first_paragraph_is_not_a_paragraph():  # MiFIR 35, IED 73 lost it
    lines = _ok(_art("35", _part("1", '<span><a title="M8"><span class="boldface">►M8</span></a></span> <p class="norm">Pirma pastraipa ilgesnė.</p><p class="norm">Antra pastraipa.</p>')))
    assert "1. Pirma pastraipa ilgesnė." in lines and "Antra pastraipa." in lines


def test_plain_divs_after_a_first_paragraph_are_not_read_twice():  # PSD2 9
    lines = _ok(_art("9", _part("1", '<p class="norm">Metodai:</p><div class="list">A metodas</div><div class="list">Lėšos turi būti ne mažesnės.</div>')))
    assert lines[2:] == ["1. Metodai:", "A metodas", "Lėšos turi būti ne mažesnės."]


def test_words_after_a_formula_and_inline_elements_between_blocks_are_kept():  # CRR 132, 284, 325ay, 325bc
    img = '<p class="container-center"><img src="data:image/jpg;base64,AAAA"/></p>'
    lines = _ok(_art("1", _part("1", f'<p class="norm">Pradžia:</p>{img}), apskaičiuotas pagal formulę.')))
    assert "), apskaičiuotas pagal formulę." in " ".join(lines) or "apskaičiuotas pagal formulę." in " ".join(lines)
    lines = _ok(_art("2", _part("1", f'<p class="norm">Pradžia:</p><p class="modref"><a>▼B</a></p>kai koeficientus {img} galima taikyti.')))
    assert sum("kai koeficientus" in l for l in lines) == 1
    lines = _ok(_art("3", _part("1", f'<p class="norm">Pradžia:</p>{img} kai α yra 1 %, T<span class="subscript">k</span> ir T<span class="subscript">l</span> yra terminai.')))
    assert "kai α yra 1 %, Tk ir Tl yra terminai." in lines
    grid = f'<div class="grid-container grid-list"><div class="list grid-list-column-1"><span>d) </span></div><div class="grid-list-column-2">{img} įvesties duomenys.</div></div>'
    assert "įvesties duomenys." in _ok(_art("4", f'<p class="norm">Sąrašas:</p>{grid}'))


def test_a_number_right_in_a_div_stays_with_what_it_numbers():  # Brussels I 7, 2004/38 7
    indent = 'style="margin-left: 24pt"'
    lines = _ok(_art("7", f'<p class="norm">Ieškinys pareiškiamas:</p><div {indent}>1)<span> </span><div {indent}><p class="norm">a) bylose dėl sutarčių;</p></div></div>'))
    assert "1) a) bylose dėl sutarčių;" in lines


FLAT_HEADS = """<p class="title-article-norm">1 straipsnis</p><p class="modref"><a>▼M1</a></p><p class="stitle-article-norm">Dalykas</p>
<p class="title-division-2">A) Procedūra</p><p class="norm">1. Pirma dalis.</p><p class="title-division-2">B) Tvarka</p><p class="norm">2. Antra dalis.</p>
<p class="title-division-1">II skyrius</p><p class="title-division-2">Kitos nuostatos</p>
<p class="title-article-norm">2 straipsnis</p><p class="norm">Tekstas.</p>"""


def test_a_heading_inside_a_flat_article_is_its_text_a_chapters_is_not():  # 987/2009 25, 96/71 1
    lines = _ok(FLAT_HEADS)
    assert lines[1:5] == ["1 straipsnis. Dalykas", "A) Procedūra", "1. Pirma dalis.", "B) Tvarka"]
    assert lines[lines.index("II SKYRIUS") + 1:] == ["KITOS NUOSTATOS", "2 straipsnis", "Tekstas."]


def test_headings_below_sections_and_with_no_number_end_the_article():
    from ltlaw.parse import parse
    body = (_art("1", '<p class="norm">Vienas.</p>') + '<p class="title-division-1">1</p><p class="title-division-1">poskirsnis</p>'
            '<p class="title-division-2">Tiekimas</p>' + _art("2", '<p class="norm">Du.</p>') +
            '<p class="title-division-1">Rūšių apsauga</p>' + _art("3", '<p class="norm">Trys.</p>') +
            '<p class="title-division-1">3 skirisnis</p><p class="title-division-2">Kita</p>' + _art("4", '<p class="norm">Keturi.</p>'))
    lines = _ok(body)
    arts = parse("\n".join(lines)).main.articles
    assert [(h.kind, h.num) for h in arts[1].path] == [("poskirsnis", "1")]
    assert arts[2].path[-1].title == "RŪŠIŲ APSAUGA" and arts[1].blocks[-1].text == "Du."
    assert [(h.kind, h.num) for h in arts[3].path][-1] == ("skirsnis", "3")


def test_a_chapters_number_in_the_journals_other_class_is_kept():  # 1024/2013 showed the title alone
    lines = _ok('<p class="oj-ti-grseq-1"><span class="oj-italic">II</span>   <span class="oj-italic">SKYRIUS</span></p>'
                '<div class="eli-title"><p class="oj-ti-section-2">Bendradarbiavimas</p></div>' +
                _art("3", '<p class="oj-normal">Tekstas.</p>'))
    assert lines[1:3] == ["II SKYRIUS", "BENDRADARBIAVIMAS"]


def test_a_chapter_and_articles_quoted_without_a_quote_mark_stay_in_the_article():  # CRR 520
    from ltlaw.parse import parse
    quoted = ('<div class="grid-container grid-list"><div class="list grid-list-column-1"><span>1) </span></div><div class="grid-list-column-2">'
              '<p class="norm">Dalis papildoma šiuo skyriumi:</p><p class="title-division-1">4</p><p class="title-division-2">SKYRIUS</p>'
              '<p class="title-article-norm">50a straipsnis</p><p class="norm">Citata.</p></div></div>')
    x = _doc(_art("520", quoted) + _art("521", '<p class="norm">Toliau.</p>'))
    text, _ = eurlex.to_text(x, "2099-01-01")
    assert eurlex.check(x, text) == []
    arts = parse(text).main.articles
    assert [a.label for a in arts] == ["520", "521"]
    assert [b.text for b in arts[0].blocks][-3:] == ["4 SKYRIUS", "50a straipsnis", "Citata."]


def test_articles_printed_in_capitals_or_as_a_second_number():  # 2024/573, CRR, 2011/61
    from ltlaw.parse import parse
    lines = _ok('<div class="eli-subdivision" id="art_2"><p class="title-article-norm">2 STRAIPSNIS</p><p class="norm">Du.</p></div>'
                '<div class="eli-subdivision" id="art_3"><p class="title-article-norm">3 straipsniai</p><p class="norm">Trys.</p></div>'
                '<div class="eli-subdivision" id="art_3a"><p class="title-article-norm">3a straipsnis</p><p class="norm">Pirmas.</p></div>'
                '<div class="eli-subdivision" id="art_3a"><p class="title-article-norm">3-a straipsnis</p><p class="norm">Antras.</p></div>')
    assert [a.label for a in parse("\n".join(lines)).main.articles] == ["2", "3", "3a", "3-a"]


def test_annex_footnotes_at_the_end_of_the_document_go_with_the_annex():  # Waste 2008/98 II R1, Habitats 92/43
    x = _doc(_art("1", '<p class="norm">Žr. priedą (<a id="src.E0001" href="#E0001"><span class="superscript">1</span></a>).</p>') +
             '<div id="anx_II"><p class="title-annex-1">II PRIEDAS</p><p class="norm">R 1 Deginimas (<a id="src.E0002" href="#E0002"><span class="superscript">*8</span></a>)</p></div>'
             '<hr class="separator-short"/>'
             '<p class="footnote">(<a id="E0001" href="#src.E0001"><span class="superscript">1</span></a>) OL L 1, p. 1.</p>'
             '<p class="footnote">(<a id="E0002" href="#src.E0002"><span class="superscript">*8</span></a>) Kai naudingumas ne mažesnis negu:</p>'
             '<div class="grid-container grid-list"><div class="list grid-list-column-1"><span>— </span></div><div class="grid-list-column-2"><div class="list">0,60 veikiantiems,</div></div></div>'
             '<p class="footnote">naudojantis šia formule:</p>')
    text, _ = eurlex.to_text(x, "2099-01-01")
    assert eurlex.check(x, text) == []
    lines = text.splitlines()
    assert "R 1 Deginimas (*8)" in lines and "(*8) Kai naudingumas ne mažesnis negu:" in lines
    assert "— 0,60 veikiantiems," in lines and "naudojantis šia formule:" in lines
    assert not any("OL L 1" in l for l in lines)  # a note on an article stays left out
    assert "Žr. priedą." in lines


def test_annexes_lettered_or_without_an_id_and_text_between_annexes():  # 2015/848, 2011/92, 1223/2009
    from ltlaw.parse import parse
    body = (_art("1", '<p class="norm">Tekstas.</p>') + '<div id="anx_I"><p class="title-annex-1">I PRIEDAS</p><p class="norm">Pirmo turinys.</p></div>'
            '<hr class="separator-annex"/><p class="title-annex-1">II.A PRIEDAS</p><p class="norm">Antro turinys.</p>'
            '<hr class="separator-annex"/><p class="title-annex-1">III–VI Priedų Preambulė</p><p class="norm">Preambulės turinys.</p>'
            '<hr class="separator-annex"/><div id="anx_A"><p class="title-annex-1">A PRIEDAS</p><p class="norm">Raidinio turinys.</p></div>')
    lines = _ok(body)
    annexes = parse("\n".join(lines)).main.annexes
    assert [a.num for a in annexes] == ["I", "II.A", "A"]
    assert [annexes[1].title] + [b.text for b in annexes[1].blocks] == ["Antro turinys.", "III–VI Priedų Preambulė", "Preambulės turinys."]


def test_appendices_inside_an_annex_are_read_once_in_place():  # REACH XVII
    from ltlaw.parse import parse
    lines = _ok(_art("1", '<p class="norm">Tekstas.</p>') + '<div id="anx_XVII"><p class="title-annex-1">XVII PRIEDAS</p><p class="title-annex-2">APRIBOJIMAI</p>'
                '<p class="norm">Pastaba.</p><p class="title-annex-2">1–6 priedėliai</p>'
                '<div id="anx_XVII.app_1"><p class="title-annex-1">1 priedėlis</p><p class="norm">Lentelė viena.</p></div>'
                '<div id="anx_XVII.app_2 "><p class="title-annex-1">2 priedėlis</p><p class="norm">Lentelė dvi.</p></div></div>')
    assert lines.count("Lentelė viena.") == 1
    assert lines.index("APRIBOJIMAI") < lines.index("Pastaba.") < lines.index("1–6 priedėliai") < lines.index("1 priedėlis") < lines.index("Lentelė viena.")
    assert [a.num for a in parse("\n".join(lines)).main.annexes] == ["XVII", "1", "2"]


def test_appendices_after_their_annex_are_read_with_it_and_numbered_by_it():  # taxonomy 2021/2139, held 2026-11-09
    from ltlaw.parse import parse
    anx = lambda n, app: (f'<div id="anx_{n}"><p class="title-annex-1">{n} PRIEDAS</p><p class="norm">Priedo {n} tekstas.</p></div>'  # noqa: E731
                          + "".join(f'<div id="app_{a}"><p class="title-annex-1">{a} priedėlis</p><p class="title-annex-2">KRITERIJAI {n}{a}</p>'
                                    f'<p class="norm">Priedėlio {n}{a} tekstas.</p></div>' for a in app))
    lines = _ok(_art("1", '<p class="norm">Tekstas.</p>') + anx("I", "AB") + anx("II", "AB"))
    assert lines.index("Priedo I tekstas.") < lines.index("A priedėlis") < lines.index("Priedėlio IA tekstas.") < lines.index("II PRIEDAS")
    annexes = parse("\n".join(lines)).main.annexes
    assert [a.num for a in annexes] == ["I", "I-A", "I-B", "II", "II-A", "II-B"]
    from ltlaw.render import annex_heading, annex_label  # whose appendix it is, in lists and on the page (2026-11-10)
    assert [annex_label(a) for a in annexes[:3]] == ["I priedas", "I priedo A priedėlis", "I priedo B priedėlis"]
    assert [annex_heading(a) for a in annexes[:2]] == ["I PRIEDAS", "I priedo A priedėlis"]


def test_statements_and_lists_of_annexes_are_not_the_acts_text():  # 2018/302, Rome II, REACH
    lines = _ok(_art("1", '<p class="oj-normal">Tekstas.</p>') + '<hr class="oj-doc-sep"/><div><div class="eli-container"><p class="oj-doc-ti">Komisijos pareiškimas</p>'
                '<p class="oj-normal">Komisija susipažino su šio straipsnio tekstu ir pareiškia savo nuomonę apie jį.</p></div></div>')
    assert not any("susipažino" in l for l in lines)
    lines = _ok(_art("1", '<p class="norm">Tekstas.</p>') + '<hr class="separator-annex"/><p class="title-annex-1">Komisijos pareiškimas dėl peržiūros</p>'
                '<p class="norm">Komisija ne vėliau kaip per metus pateiks tyrimą apie šią sritį.</p>')
    assert not any("pateiks tyrimą" in l for l in lines)


def test_the_degree_sign_is_no_hyphen():  # CLP VI: "50-oC"
    lines = _ok(_art("1", '<p class="norm">Verda 50<span class="superscript">o</span>C temperatūroje.</p>'))
    assert "Verda 50ºC temperatūroje." in lines


LEGACY = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"><html lang="LT"><head></head><body><h1>32003L0088</h1><div id="TexteOnly"><p>
<TXT_TE><p>Direktyva 2003/88/EB</p><p>kadangi:</p><p>(1) Bendrija [1],</p><p>PRIĖMĖ ŠIĄ DIREKTYVĄ:</p><p>I SKYRIUS</p><p>TAIKYMO SRITIS</p>
<p>1 straipsnis</p><p>Tikslas</p><p>1. Ši direktyva nustato reikalavimus [2].</p><p>2. Ji taikoma &quot;darbuotojams&quot;.</p>
<p>2 straipsnis</p><p>Ši direktyva skirta valstybėms narėms.</p><p></p><p>Priimta Briuselyje, 2003 m. lapkričio 4 d.</p><p>Tarybos vardu</p><p>Pirmininkas</p><p>A. Vardenis</p>
<p>[1] OL C 61, 2003 3 14, p. 123.</p><p>[2] OL C 62.</p><p>--------------------------------------------------</p>
<p>I PRIEDAS</p><p>+++++ TIFF +++++</p><p>--------------------------------------------------</p><p>II PRIEDAS</p><p>KORELIACIJOS LENTELĖ</p><p>Direktyva 93/104/EB | Ši direktyva |</p><p>1 straipsnis | 1 straipsnis |</p><p>--------------------------------------------------</p></TXT_TE></p></div></body></html>"""


def test_the_older_html_of_acts_adopted_before_accession():
    from ltlaw.parse import parse
    text, info = eurlex.legacy_to_text(LEGACY, "2004-08-02", "32003L0088")
    assert eurlex.check_legacy(LEGACY, text, "32003L0088") == []
    lines = text.splitlines()
    assert lines[1:7] == ["I SKYRIUS", "TAIKYMO SRITIS", "1 straipsnis. Tikslas", "1. Ši direktyva nustato reikalavimus.", '2. Ji taikoma "darbuotojams".', "2 straipsnis"]
    assert not any("Priimta" in l or "OL C" in l or "Vardenis" in l for l in lines)
    assert eurlex.LEGACY_FIGURE_NOTE in lines and "1 straipsnis | 1 straipsnis" in lines
    act = parse(text)
    assert [a.label for a in act.main.articles] == ["1", "2"] and [a.num for a in act.main.annexes] == ["I", "II"]
    # a lost line is caught, another language is never a fallback
    assert eurlex.check_legacy(LEGACY, text.replace("1. Ši direktyva nustato reikalavimus.\n", ""), "32003L0088")
    with pytest.raises(LookupError):
        eurlex.legacy_to_text(LEGACY.replace('lang="LT"', 'lang="EN"'), "2004-08-02", "32003L0088")


def test_the_older_html_is_taken_only_when_nothing_amended_the_act_since(monkeypatch):
    import urllib.error
    from ltlaw import source

    def no_xhtml(c):
        raise urllib.error.HTTPError(c, 404, "no", None, None)
    meta = {"date": "2003-11-04", "entry_into_force": "2004-08-02", "end_of_validity": None, "in_force": True, "title": "Direktyva"}
    monkeypatch.setattr(eurlex, "metadata", lambda c: meta)
    monkeypatch.setattr(eurlex, "fetch_xhtml", no_xhtml)
    monkeypatch.setattr(eurlex, "fetch_legacy", lambda c: LEGACY)
    monkeypatch.setattr(eurlex, "versions", lambda c: ["02003L0088-20031118"])
    row = source.eu_row("EU.32003L0088", "2026-11-04")
    assert row["eu_version"] is None and row["tekstas_lt"].startswith("Suvestinė redakcija nuo 2004-08-02\nI SKYRIUS")
    monkeypatch.setattr(eurlex, "versions", lambda c: ["02003L0088-20150101"])
    with pytest.raises(LookupError):
        source.eu_row("EU.32003L0088", "2026-11-04")



def test_heading_typos_read_as_the_article():
    """EUR-Lex typos in article headings (2026-11-09): "30J straipsnis" (2003/87), "18 straipsnis b" (2003/96)."""
    from ltlaw.eurlex import _strip_art
    assert [_strip_art(x) for x in ["30J straipsnis", "18 straipsnis b", "18a straipsnis", "70 straipsnis.", "2 STRAIPSNIS", "26 straipsniai"]] \
        == ["30j", "18b", "18a", "70", "2", "26"]


def test_an_inline_element_between_paragraphs_of_a_list_laid_out_as_a_table():  # 2013/59/Euratom 4(15), held 2026-11-10
    row = ('<table><col/><col/><tr><td><p class="dlist-term">15)</p></td><td><p class="normal">kaupiamoji lygiavertė dozė (H</p>'
           '<span class="subscript">T</span> <p class="normal">(τ)) – </p><p class="norm">lygiavertės dozės galios integralas.</p>'
           '</td></tr></table>')
    lines = _ok(_art("4", f'<p class="norm">Apibrėžtys:</p>{row}'))
    assert "15) kaupiamoji lygiavertė dozė (H T" in lines  # the subscript was lost


def test_many_acts_versions_in_one_query_keep_only_their_own_numbers(monkeypatch):
    asked = []
    def sparql(q, timeout=120):
        asked.append(q)
        if '"32019L0944"' not in q:
            raise TimeoutError
        return [{"bc": "32019L0944", "celex": "02019L0944-20240716"}, {"bc": "32019L0944", "celex": "02019L0944-20190614"},
                {"bc": "32019L0944", "celex": "02012L0027-20200101"}]  # another act's version, linked to this one
    monkeypatch.setattr(eurlex, "sparql", sparql)
    got = eurlex.versions_of(["32019L0944", "32016R0679", "32022L2555"], batch=2)
    # 2016/679 has no consolidation (an empty list, an answer); 2022/2555's query failed (no answer: asked for alone later)
    assert got == {"32019L0944": ["02019L0944-20190614", "02019L0944-20240716"], "32016R0679": []}
    assert len(asked) == 2 and "act_consolidated_based_on_resource_legal" in asked[0] and '"32016R0679"^^xsd:string' in asked[0]


def test_many_acts_metadata_in_one_query(monkeypatch):
    rows = [{"c": "32019L0944", "date": "2019-06-05", "eif": "2019-07-04", "end": "2025-10-11", "force": "1"},
            {"c": "32019L0944", "end": "9999-12-31", "force": "1", "title": "Direktyva"},
            {"c": "32016R0679", "date": "2016-04-27", "force": "0"}]
    monkeypatch.setattr(eurlex, "sparql", lambda q, timeout=120: rows)
    got = eurlex.metadata_of(["32019L0944", "32016R0679", "32099R0001"])
    assert got["32019L0944"]["end_of_validity"] == "9999-12-31" and got["32019L0944"]["title"] == "Direktyva"
    assert not got["32016R0679"]["in_force"] and "32099R0001" not in got  # no row: asked for alone, as before


def test_an_eu_act_uses_the_nights_batch_but_never_loses_a_version_it_held(monkeypatch):
    from ltlaw import source
    meta = {"date": "2019-06-05", "entry_into_force": "2019-07-04", "end_of_validity": "9999-12-31", "in_force": True, "title": "D"}
    prev = {"eu_versions": ["02019L0944-20190614", "02019L0944-20240716"], "tekstas_lt": "1 straipsnis", "eu_converter": eurlex.CONVERTER}
    slow = []
    monkeypatch.setattr(eurlex, "metadata", lambda c: slow.append("metadata") or meta)
    monkeypatch.setattr(eurlex, "versions", lambda c: slow.append("versions") or list(prev["eu_versions"]))
    monkeypatch.setattr(source, "EU_BATCH", {"versions": {"32019L0944": list(prev["eu_versions"])}, "metadata": {"32019L0944": dict(meta, in_force=False)}})
    row = source.eu_row("EU.32019L0944", "2026-11-17", prev)
    assert not slow and row["tekstas_lt"] == "1 straipsnis" and row["galioj_busena"] == "negalioja"  # the batch's answers, no other query
    # the batch's list lacks a version we held: the slow query decides, the text stays
    monkeypatch.setattr(source, "EU_BATCH", {"versions": {"32019L0944": ["02019L0944-20190614"]}, "metadata": {"32019L0944": meta}})
    row = source.eu_row("EU.32019L0944", "2026-11-17", prev)
    assert slow == ["versions"] and row["eu_versions"] == prev["eu_versions"] and row["tekstas_lt"] == "1 straipsnis"
