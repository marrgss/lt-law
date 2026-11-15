"""The name and document checks (ltlaw.scopecheck) and bin/add_acts.py's area edit."""
import importlib.util
import pathlib

from ltlaw import scopecheck as sc

RULES = {"dokumento_id": "x", "adopted": "2010-04-07", "unit": "punktas"}
LAW = {"dokumento_id": "y"}

ORDER = """Suvestinė redakcija nuo 2021-09-07
LIETUVOS RESPUBLIKOS ENERGETIKOS MINISTRAS
ĮSAKYMAS
DĖL DEGALINIŲ EKSPLOATAVIMO TAISYKLIŲ PATVIRTINIMO
PATVIRTINTA
Lietuvos Respublikos energetikos ministro
2009 m. balandžio 23 d. įsakymu Nr. 1-62
(Lietuvos Respublikos energetikos ministro 2021 m. rugsėjo 1 d. įsakymo Nr. 1-264 redakcija)
DEGALINIŲ ĮRENGIMO IR EKSPLOATAVIMO TAISYKLĖS
I SKYRIUS
BENDROSIOS NUOSTATOS
1. Taisyklės nustato…"""

TWO = """LIETUVOS RESPUBLIKOS APLINKOS MINISTRAS
PATVIRTINTA
Lietuvos Respublikos aplinkos ministro 2011 m. sausio 5 d. įsakymu Nr. D1-14
KIETOJO BIOKURO PELENŲ IR ŠLAKO PANAUDOJIMO REIKALAVIMŲ APRAŠAS
I SKYRIUS
BENDROSIOS NUOSTATOS
1. Aprašas nustato…
PATVIRTINTA
Lietuvos Respublikos aplinkos ministro 2011 m. sausio 5 d. įsakymu Nr. D1-14
KIETOJO BIOKURO PELENŲ IR ŠLAKO ATLIEKŲ NEBELAIKYMO ATLIEKOMIS KRITERIJŲ APRAŠAS
I SKYRIUS
BENDROSIOS NUOSTATOS
1. Aprašas nustato…"""


def test_renamed_rules_are_reported():
    old = dict(RULES, abbr="DET", name="Degalinių eksploatavimo taisyklės")
    assert "name differs" in sc.check(ORDER, old)[0]
    assert sc.check(ORDER, dict(old, name="Degalinių įrengimo ir eksploatavimo taisyklės")) == []
    assert sc.check(ORDER, dict(old, name_checked=True)) == []


def test_our_document_must_come_first():
    first = dict(RULES, abbr="A", name="Kietojo biokuro pelenų ir šlako panaudojimo reikalavimų aprašas")
    second = dict(RULES, abbr="B", name="Kietojo biokuro pelenų ir šlako atliekų nebelaikymo atliekomis kriterijų aprašas")
    assert sc.check(TWO, first) == []
    assert "ours is not the first" in sc.check(TWO, second)[0]
    assert sc.check(TWO, dict(second, document="kietojo biokuro pelenų ir šlako atliekų")) == []


def test_law_title_letter_spaced_and_future_versions():
    text = "Suvestinė redakcija nuo 2026-01-12\nLIETUVOS RESPUBLIKOS\nAPLINKOS APSAUGOS VALSTYBINĖS PRIEŽIŪROS\nĮ S T A T Y M A S\n1 straipsnis."
    assert sc.check(text, dict(LAW, abbr="AAVKĮ", name="Aplinkos apsaugos valstybinės priežiūros įstatymas")) == []
    old = dict(LAW, abbr="AAVKĮ", name="Aplinkos apsaugos valstybinės kontrolės įstatymas")
    assert "name differs" in sc.check(text, old, "2026-11-03")[0]
    assert sc.check(text, old, "2025-12-31") == []  # a coming version's heading is a coming name


def test_a_standards_year_with_a_space_is_the_same_name():
    text = "PATVIRTINTA\nLietuvos Respublikos sveikatos apsaugos ministro 2007 m. rugsėjo 13 d. įsakymu Nr. V-713\nLIETUVOS HIGIENOS NORMA HN 18: 2007 PRIEIGOS TAŠKAI\nI SKYRIUS\nBENDROSIOS NUOSTATOS\n1. Norma…"
    assert sc.check(text, dict(RULES, abbr="HN18", name="Lietuvos higienos norma HN 18:2007 „Prieigos taškai“")) == []


def test_a_first_chapter_in_lower_case_is_not_part_of_the_heading():
    text = ("PATVIRTINTA\nLietuvos Respublikos socialinės apsaugos ir darbo ministro 2011 m. birželio 2 d. \nįsakymu Nr. A1-266/V-575\n\xa0\n"
            "Įmonių DARBUOTOJŲ SAUGOS IR SVEIKATOS TARNYBŲ PAVYZDINIAI \nNUOSTATAI\n\xa0\n\n\nI. skyrius\nBENDROSIOS NUOSTATOS \n1. Įmonių…")
    assert sc.check(text, dict(RULES, abbr="ĮDSSTPN", name="Įmonių darbuotojų saugos ir sveikatos tarnybų pavyzdiniai nuostatai")) == []
    text = ("PATVIRTINTA\nLietuvos Respublikos aplinkos ministro 1999 m. sausio 29 d. įsakymu Nr. 33\n\xa0\nLEIDIMŲ PAŽEMINTI VANDENS LYGĮ "
            "TVENKINIUOSE IR UŽTVENKTUOSE EŽERUOSE IŠDAVIMO TVARKOS APRAŠAS\n\xa0\n\n\nI. bendrosios nuostatos\n\xa0\n\n\n1. Leidimų…")
    act = dict(RULES, abbr="L", name="Leidimų pažeminti vandens lygį tvenkiniuose ir užtvenktuose ežeruose išdavimo tvarkos aprašas")
    assert sc.check(text, act) == []
    assert "name differs" in sc.check(text, dict(act, name="Leidimų vandens lygiui keisti tvenkiniuose ir užtvenktuose ežeruose išdavimo taisyklės"))[0]


def test_add_to_area_keeps_comments_and_lists(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("add_acts", pathlib.Path(__file__).parents[1] / "bin" / "add_acts.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    f = tmp_path / "areas.yaml"
    f.write_text("areas:\n  - name: Energetika\n    slug: energetika\n    # VERT rules\n    acts: [EĮ, ŠŪĮ,\n           GDĮ]\n"
                 "  - name: Transportas\n    slug: transportas\n    acts: [KET]\n")
    monkeypatch.setattr(m, "AREAS", f)
    m.add_to_area("energetika", ["NEW", "EĮ"])
    s = f.read_text()
    assert "    # VERT rules\n    acts: [EĮ, ŠŪĮ,\n           GDĮ, NEW]\n" in s and "acts: [KET]\n" in s


def test_remove_from_areas_keeps_lines(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("add_acts", pathlib.Path(__file__).parents[1] / "bin" / "add_acts.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    f = tmp_path / "areas.yaml"
    f.write_text("areas:\n  - name: A\n    slug: a\n    acts: [X, Y,\n           Z, ĄĮ]\n  - name: B\n    slug: b\n    acts: [ĄĮ, Q]\n")
    monkeypatch.setattr(m, "AREAS", f)
    m.remove_from_areas({"ĄĮ", "Y"})
    assert f.read_text() == "areas:\n  - name: A\n    slug: a\n    acts: [X,\n           Z]\n  - name: B\n    slug: b\n    acts: [Q]\n"


def test_redirects_stay_within_the_hosts_limits():
    from ltlaw.render import redirect_lines
    acts = [("dk", "2016-1"), ("a-very-long-alias-made-of-a-whole-name", "2016-2"), ("ket", "2016-3")]
    rules = [x for al, t in acts for x in (f"/{al}/:n /ta/{t}/str/:n/ 301", f"/{al} /ta/{t}/ 301", f"/ta/{t}/str/ /ta/{t}/ 301")]
    assert redirect_lines(rules, 100) == rules  # within the limits: untouched
    out = redirect_lines(rules, 5)
    assert not any(":n" in r for r in out) or len(out) == 5
    out = redirect_lines([r for r in rules if ":n" not in r], 5)
    assert out == ["/ta/2016-1/str/ /ta/2016-1/ 301", "/ta/2016-2/str/ /ta/2016-2/ 301", "/ta/2016-3/str/ /ta/2016-3/ 301",
                   "/dk /ta/2016-1/ 301", "/ket /ta/2016-3/ 301"]  # the acts' own lines, then the shortest aliases


def test_a_formula_left_only_as_its_number_is_marked():
    from ltlaw import render
    from ltlaw.parse import Block
    b = lambda t: Block(kind="text", text=t, num=None, anchor=None)  # noqa: E731
    for t in ("(6.6a)", "(1)", " (7.10) "):
        assert render.FORMULA_MARK in render.display_text(b(t))
    for t in ("(1) Pirma dalis.", "1 punktas (2)", "(a)"):
        assert render.FORMULA_MARK not in render.display_text(b(t))


def test_a_big_sitemap_becomes_an_index_of_parts():
    from ltlaw.render import sitemap_files
    urls = [(f"https://x/p{i}/", "2026-11-04") for i in range(5)]
    assert [n for n, _ in sitemap_files(urls, "https://x", "2026-11-05", 5)] == ["sitemap.xml"]
    files = dict(sitemap_files(urls, "https://x", "2026-11-05", 2))
    assert list(files) == ["sitemap.xml", "sitemap-1.xml", "sitemap-2.xml", "sitemap-3.xml"]
    assert "<sitemapindex" in files["sitemap.xml"] and "<loc>https://x/sitemap-3.xml</loc>" in files["sitemap.xml"]
    assert files["sitemap-3.xml"].count("<url>") == 1 and "<loc>https://x/p4/</loc><lastmod>2026-11-04</lastmod>" in files["sitemap-3.xml"]


def test_every_rest_endpoint_reaches_the_worker():  # /api/related and /api/articles were documented and 404 until 2026-11-05
    import re
    root = pathlib.Path(__file__).parents[1] / "worker-mcp"
    served = set(re.findall(r'url\.pathname === "(/api/[a-z]+)"', (root / "index.js").read_text()))
    first = re.search(r"run_worker_first = \[(.*?)\]", (root / "wrangler.site.toml").read_text()).group(1)
    assert served and not {p for p in served if f'"{p}"' not in first}


def test_scope_tables_name_acts_that_exist():
    import yaml
    root = pathlib.Path(__file__).parents[1] / "scope"
    abbrs = {a["abbr"] for a in yaml.safe_load((root / "v1_seed.yaml").read_text())["acts"]}
    assert not set(yaml.safe_load((root / "names.yaml").read_text())["names"]) - abbrs
    for t in yaml.safe_load((root / "topics.yaml").read_text())["topics"]:
        assert t["when"] and all(w == w.lower() and w.isascii() for w in t["when"]), t
        assert not {r.rpartition(" ")[0] for r in t["refs"]} - abbrs, t

