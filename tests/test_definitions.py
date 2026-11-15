"""Defined terms (definitions.py)."""
from ltlaw.definitions import Finder, terms_of
from ltlaw.parse import parse

ACT = """Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
2016 m. rugsėjo 14 d. Nr. XII-1
Vilnius
1 straipsnis. Įstatymo paskirtis
Šis įstatymas nustato tvarką.
2 straipsnis. Pagrindinės šio įstatymo sąvokos
1. Apmokestinamasis asmuo – asmuo, kuris verčiasi veikla.
2. Asmuo – fizinis arba juridinis asmuo.
3. Viešojo pirkimo sutartis (toliau – pirkimo sutartis) – sutartis tarp perkančiosios organizacijos ir tiekėjo.
4. Pirkimo sutartis – kita sutartis.
3 straipsnis. Prievolės
Apmokestinamojo asmens prievolės nustatomos šio įstatymo. Asmuo sudaro viešojo pirkimo sutartį.
4 straipsnis. Kita
Asmuo moka.
"""


def test_terms_and_short_forms():
    act = parse(ACT)
    ts = terms_of(act.main.articles)
    assert [(t.term, t.anchor) for t in ts] == [("Apmokestinamasis asmuo", "d1"), ("Asmuo", "d2"),
                                                ("Viešojo pirkimo sutartis", "d3"), ("pirkimo sutartis", "d3"),
                                                ("Pirkimo sutartis", "d4")]


def test_found_by_stems_in_order():
    act = parse(ACT)
    texts = {a.label: " ".join([a.title] + [b.text for b in a.blocks]) for a in act.main.articles}
    f = Finder(terms_of(act.main.articles), texts)
    got = [t.term for t in f.found("3", texts["3"])]
    # inflected ("apmokestinamojo asmens"); the longer term hides the shorter inside it; "Asmuo" is in most articles
    assert got == ["Apmokestinamasis asmuo", "Viešojo pirkimo sutartis"]
    assert f.found("2", texts["2"]) == []  # not on the definitions page itself


def test_word_matching():
    from ltlaw.definitions import same
    assert same("darbdavys", "darbdavio") and same("sutartis", "sutarti") and same("imone", "imoniu")
    assert not same("draudejas", "draudikas") and not same("statinys", "statyba") and not same("darbdavys", "darbas")
    assert same("apmokestinamasis", "apmokestinamojo", 4) and not same("apmokestinamasis", "apmokestinamojo")


# --- definitions by reference (feedback P10) ---
from ltlaw.definitions import References  # noqa: E402

ACTS = [{"genitive": g, "act": k, "name": n, "url": f"/ta/{k}/"} for g, k, n in [
    ("elektros energetikos įstatymo", "eei", "Elektros energetikos įstatymas"),
    ("energetikos įstatymo", "ei", "Energetikos įstatymas"),
    ("baudžiamojo kodekso", "bk", "Baudžiamasis kodeksas"),
    ("nelaimingų atsitikimų darbe ir profesinių ligų socialinio draudimo įstatymo", "nadplsdi", "NADPLSD įstatymas"),
]]


def test_reference_names_inflected_and_longest_first():
    R = References(ACTS)
    [r] = R.find("4. Kitos Taisyklėse vartojamos sąvokos suprantamos taip, kaip jos apibrėžtos Lietuvos Respublikos "
                 "energetikos įstatyme, Lietuvos Respublikos elektros energetikos įstatyme ir Lietuvos Respublikos "
                 "baudžiamajame kodekse.")
    assert [a["act"] for a in r["acts"]] == ["ei", "eei", "bk"]
    assert r["terms"] is None and r["not_on_site"] == [] and not r["also_other_acts"]


def test_reference_terms_eu_and_others():
    R = References(ACTS)
    [r] = R.find("Sąvokos „piko valanda“ ir „skirtasis matuoklis“ suprantamos taip, kaip apibrėžiamos Reglamente (ES) 2019/943.")
    assert r["terms"] == ["piko valanda", "skirtasis matuoklis"] and r["acts"] == [] and r["not_on_site"] == ["Reglamente (ES) 2019/943"]
    [r] = R.find("5.17. Kitos šiame Apraše vartojamos sąvokos atitinka Elektros energetikos įstatyme ir kituose teisės aktuose "
                 "apibrėžtas sąvokas.")
    assert [a["act"] for a in r["acts"]] == ["eei"] and r["also_other_acts"]
    [r] = R.find("30-3. Pagalbinis vaistinis preparatas – ši sąvoka atitinka sąvoką „pagalbinis vaistas“ ir vartojama ta pačia "
                 "reikšme, kaip ji apibrėžta Reglamento (ES) Nr. 536/2014 2 straipsnio.")
    assert r["terms"] == ["Pagalbinis vaistinis preparatas"]  # this act's term, which takes the other's meaning


def test_reference_alias_and_own_definitions():
    R = References(ACTS)
    al = R.aliases(["1. Nuostatai parengti pagal Lietuvos Respublikos nelaimingų atsitikimų darbe ir profesinių ligų socialinio "
                    "draudimo įstatymą (toliau – Įstatymas)."])
    assert al["Įstatymas"]["act"] == "nadplsdi"
    [r] = R.find("2. Nuostatuose vartojamos sąvokos suprantamos taip, kaip jos apibrėžtos Įstatyme.", al)
    assert [a["act"] for a in r["acts"]] == ["nadplsdi"]
    assert R.find("Sąvoka suprantama taip, kaip apibrėžta šio įstatymo 2 straipsnyje.") == []  # its own
    assert R.find("Sąvokos suprantamos taip, kaip jos apibrėžtos kituose įstatymuose.", al)[0]["acts"] == []
    # another act's concept matching one of its own: not a reference out
    assert R.find("Reglamento (ES) 2024/1309 nurodyta sąvoka „tinklas“ atitinka šio straipsnio 37 dalyje apibrėžtą sąvoką „t“.") == []


# --- the concept graph (feedback S11) ---
GRAPH = """Suvestinė redakcija nuo 2026-01-01
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
2016 m. rugsėjo 14 d. Nr. XII-2
Vilnius
1 straipsnis. Pagrindinės šio įstatymo sąvokos
1. Buitinis elektros energijos vartotojas – fizinis asmuo, perkantis elektros energiją savo reikmėms.
2. Pažeidžiamas vartotojas – buitinis elektros energijos vartotojas, kuriam taikoma apsauga.
3. Vartotojas – asmuo, perkantis energiją.
2 straipsnis. Apsauga
Pažeidžiamam vartotojui taikoma apsauga.
"""


def test_concepts_broader_and_used_in():
    from ltlaw.definitions import concepts
    act = parse(GRAPH, None)
    terms = terms_of(act.main.articles)
    url_of = lambda t: f"/str/{t.label}/#{t.anchor}"  # noqa: E731
    defs = {url_of(t): b.text.split(" – ", 1)[1] for t in terms for a in act.main.articles for b in a.blocks
            if a.label == t.label and b.anchor == t.anchor}
    rows = {r["term"]: r for r in concepts(terms, defs, url_of, {"/str/1/#d2": ["2"]}, "bi", "BĮ")}
    assert rows["Pažeidžiamas vartotojas"]["broader"]["term"] == "Buitinis elektros energijos vartotojas"  # the longest
    assert rows["Pažeidžiamas vartotojas"]["used_in"] == ["2"]
    assert rows["Vartotojas"]["broader"] is None and rows["Buitinis elektros energijos vartotojas"]["broader"] is None
