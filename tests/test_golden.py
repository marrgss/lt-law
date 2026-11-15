"""Golden tests on real TAR data, pinned to the 2026-10-18 snapshot (each case was checked
against e-tar.lt by bin/validate_scope.py and bin/validate_currency.py).

Needs data/ (gitignored): run `uv run bin/snapshot_scope.py` on the snapshot day and
`bin/fetch_meta.py` for metadata. Skipped when the snapshot is absent.
"""
import json
import pathlib

import pytest

from ltlaw.currency import Laws, assess
from ltlaw.parse import parse

DAY = "2026-10-18"
DATA = pathlib.Path("data")
DOC = {"DK": "f6d686707e7011e6b969d7ae07280e89", "CK": "TAR.8A39C83848CB", "BK": "TAR.2B866DFF7D43",
       "ANK": "4ebe66c0262311e5bf92d6af3f6a2e8b", "PVMĮ": "TAR.ED68997709F5"}
SCOPE = {"DK": ("darbo kodekso", "XII-2603"), "CK": ("civilinio kodekso", "VIII-1864"),
         "BK": ("baudžiamojo kodekso", "VIII-1968"), "ANK": ("administracinių nusižengimų kodekso", "XII-1869"),
         "PVMĮ": ("pridėtinės vertės mokesčio įstatymo", "IX-751")}

pytestmark = pytest.mark.data


def snap(abbr):
    p = DATA / "dokumentas" / DOC[abbr] / f"{DAY}.json"
    if not p.exists():
        pytest.skip(f"no {DAY} snapshot for {abbr}")
    return parse(json.loads(p.read_text())["row"]["tekstas_lt"])


@pytest.fixture(scope="module")
def laws():
    if not ((DATA / "state" / "laws.jsonl").exists() or (DATA / "raw" / "dokumentas.jsonl").exists()):
        pytest.skip("no law metadata (bin/compact_state.py or bin/fetch_meta.py)")
    return Laws(fetch=False)


def status(abbr, laws):
    g, n = SCOPE[abbr]
    return assess(snap(abbr), {"abbr": abbr, "genitive": g, "number": n}, laws, DAY)


# --- structure ---------------------------------------------------------------------------------
def test_codes_have_approval_law_and_code():
    a = snap("DK")
    assert [s.kind for s in a.segments] == ["approval", "main"]
    assert a.main.title == "LIETUVOS RESPUBLIKOS DARBO KODEKSAS"
    assert len(a.main.articles) == 257
    assert a.version_from == "2027-01-01" and a.version_to is None


def test_superscripts_decoded_like_etar():
    dk = {x.label for x in snap("DK").main.articles}
    assert "211" in dk and "21-1" not in dk          # DK 211 is a real article (after 210)
    assert "72-1" in dk                               # DK 72¹
    ck = {x.label: x for x in snap("CK").main.articles}
    assert ck["6.228-1"].title.startswith("Vartojimo sutarties samprata")
    assert "6.2281" not in ck


def test_dated_variants_ank53():
    a = {x.label: x for x in snap("ANK").main.articles}["53"]
    assert [(v.valid_from, v.valid_to) for v in [a, *a.variants]] == \
        [(None, "2022-12-31"), ("2023-01-01", "2024-12-31"), ("2025-01-01", None)]
    assert a.variant_on(DAY).valid_from == "2025-01-01"


def test_annex_and_signature_are_not_article_text():
    dk = snap("DK").main
    assert len(dk.annexes) == 1 and dk.annexes[0].title == "ĮGYVENDINAMI EUROPOS SĄJUNGOS TEISĖS AKTAI"
    assert all("direktyva" not in b.text for b in dk.articles[-1].blocks)
    pvm = snap("PVMĮ").main
    assert pvm.signature and "skelbiu šį" in pvm.signature[0].lower()
    assert [x.num for x in pvm.annexes] == ["1", "2"]
    assert "PAULAUSKAS" not in pvm.annexes[0].header


def test_notes_attach_to_parts():
    a = {x.label: x for x in snap("DK").main.articles}["52"]
    part8 = next(b for b in a.blocks if b.anchor == "d8")
    assert any(r.nr == "XV-969" for n in part8.notes for r in n.refs)


# --- currency (which stored texts apply today) ------------------------------------------------
def test_staged_entry_dk23_148_pending(laws):
    st = status("DK", laws)
    for k in ("23", "148"):  # XV-969 arts 2 and 17 apply only from 2027-01-01
        assert st.articles[k].state == "pending" and st.articles[k].applies_from == "2027-01-01"
    assert st.articles["52"].state == "pending" and st.articles["52"].applies_from == "2026-11-01"  # XV-1058
    assert st.articles["1"].state == "current"


def test_past_version_bk162_outdated(laws):
    st = status("BK", laws)
    assert st.version_state == "past"
    assert st.articles["162"].state == "outdated" and "XV-1089" in st.articles["162"].reasons[0]
    assert st.articles["182"].state == "current"


def test_two_dates_ank589(laws):
    s = status("ANK", laws).articles["589"]
    assert (s.state, s.changes_on, s.applies_from) == ("pending", "2026-11-01", "2027-01-02")


def test_ck_long_tail_current(laws):
    assert status("CK", laws).articles["6.228-1"].state == "current"


# --- v1 scope cases (2026-10-18), each found by bin/validate_currency.py ------------------------
V1 = {"AKĮ": ("TAR.B9E1D301256F", "akcizų įstatymo", "IX-569"), "CPK": ("TAR.2E7C18F61454", "civilinio proceso kodekso", "IX-743"),
      "VTAĮ": ("TAR.D790096B17EE", "vartotojų teisių apsaugos įstatymo", "I-657")}


def v1_status(abbr, laws):
    from ltlaw import source
    doc, g, n = V1[abbr]
    if not (DATA / "dokumentas" / doc / f"{DAY}.json").exists():
        pytest.skip(f"no {DAY} snapshot for {abbr}")
    act = parse(source.act_text(doc)[0])
    return act, assess(act, {"abbr": abbr, "genitive": g, "number": n}, laws, DAY)


def test_multi_year_excise_rates_akciz24_pending(laws):
    _, st = v1_status("AKĮ", laws)
    assert st.articles["24"].state == "pending"  # XIV-2769 staged 2025/2026/2027; stored text is 2027's


def test_redated_amending_law_cpk82_unknown(laws):
    _, st = v1_status("CPK", laws)
    s = st.articles["82"]
    assert s.state == "unknown" and any("XV-1028" in r for r in s.reasons)  # XV-1028 moved XIV-2317's dates


def test_duplicated_article_vtai48_unknown(laws):
    act, st = v1_status("VTAĮ", laws)
    a = {x.label: x for x in act.main.articles}["48"]
    assert len(a.duplicates) == 1 and st.articles["48"].state == "unknown"


def test_article_headings_without_the_period_where_the_whole_document_is_written_so():  # PORFPSDR (VERT O3E-12), 2026-11-10
    from ltlaw.parse import parse
    body = "\n".join(f"{n} straipsnis{' ' + t if t else ''}\n1. Tekstas {n}.\n2. Dar {n}." for n, t in
                     [(1, "Dalykas ir apimtis"), (2, "Apibrėžimai"), (3, "Bendrosios pareigos"), (4, "")])
    a = parse(body)
    assert [x.num.base for x in a.main.articles] == [1, 2, 3, 4]
    assert a.main.articles[1].title == "Apibrėžimai"
    # one such line in an ordinary law is a sentence, not a heading
    law = "1 straipsnis. Paskirtis\nTekstas.\n2 straipsnis. Sąvokos\n5 straipsnis Lietuvos Respublikos įstatymo taikymas.\n3 straipsnis. Kita\nTekstas."
    assert [x.num.base for x in parse(law).main.articles] == [1, 2, 3]


def test_a_methodology_approved_by_a_resolution_keeps_its_recitals_and_split_titles():  # PORFPSDR, BTMMM (VERT), 2026-11-10
    from ltlaw.parse import parse
    text = "\n".join(["VALSTYBINĖ ENERGETIKOS REGULIAVIMO TARYBA", "NUTARIMAS", "DĖL METODIKOS PATVIRTINIMO",
                      "2019 m. sausio 17 d. Nr. O3E-12", "Vilnius", "Vadovaudamasi įstatymu, Taryba n u t a r i a:",
                      "Patvirtinti metodiką (pridedama).", "Tarybos pirmininkė Vardenė Pavardenė", "PATVIRTINTA",
                      "Tarybos 2019 m. sausio 17 d.", "nutarimu Nr. O3E-12", "VISŲ PSO PASIŪLYMAS DĖL METODIKOS",
                      "Visi PSO, atsižvelgdami į tai, kas išdėstyta toliau:", "1. Pirma priežastis.", "2. Antra priežastis.",
                      "teikia šią metodiką:", "1 straipsnis Dalykas", "1. Tekstas.", "2 straipsnis Apibrėžimai", "1. Tekstas.",
                      "3 straipsnis", "Bendrosios pareigos", "1. Tekstas.", "4 straipsnis Kalba", "Tekstas.",
                      "____________________________"])
    m = parse(text).main
    assert [(x.num.base, x.title) for x in m.articles] == [(1, "Dalykas"), (2, "Apibrėžimai"), (3, "Bendrosios pareigos"),
                                                                   (4, "Kalba")]
    assert m.preamble[1] == "1. Pirma priežastis." and not m.tail
    assert m.articles[-1].blocks[-1].text == "Tekstas."
    ap = parse(text).segments[0]  # the resolution's own words, as a points act's
    assert ap.kind == "approval" and ap.preamble == ["Vadovaudamasi įstatymu, Taryba n u t a r i a:", "Patvirtinti metodiką (pridedama)."]
    assert ap.signature == ["Tarybos pirmininkė Vardenė Pavardenė"]


def test_a_methodology_titled_in_ordinary_case_with_lower_case_sections():  # RMM (VERT O3E-43), 2026-11-10
    from ltlaw.parse import parse
    text = "\n".join(["VALSTYBINĖ KAINŲ IR ENERGETIKOS KONTROLĖS KOMISIJA", "NUTARIMAS", "DĖL METODIKOS PATVIRTINIMO",
                      "2018 m. vasario 5 d. Nr. O3E-43", "Vilnius", "Vadovaudamasi įstatymu, Komisija n u t a r i a:",
                      "Patvirtinti metodiką (pridedama).", "Komisijos pirmininkė Vardenė Pavardenė", "PATVIRTINTA",
                      "Valstybinės kainų ir energetikos kontrolės komisijos", "2018 m. vasario 5 d. nutarimu Nr. O3E-43",
                      "Rezervinė metodika, pateikta visų operatorių pasiūlymu", "Kadangi",
                      "(1) Pirma priežastis.", "(2) Antra priežastis.", "1 straipsnis", "Dalykas", "Tekstas.",
                      "2 straipsnis", "Apibrėžtys", "1. Sąvoka.", "1 skirsnis", "Bendrosios procedūros", "3 straipsnis",
                      "Aprašymas", "1. Tekstas.", "2 skirsnis", "Kitos procedūros", "4 straipsnis", "Kalba", "Tekstas."])
    a = parse(text)
    m = a.main
    assert m.title == "Rezervinė metodika, pateikta visų operatorių pasiūlymu"
    assert [(x.num.base, x.title) for x in m.articles] == [(1, "Dalykas"), (2, "Apibrėžtys"), (3, "Aprašymas"), (4, "Kalba")]
    assert m.preamble == ["Kadangi", "(1) Pirma priežastis.", "(2) Antra priežastis."]
    assert [(h.kind, h.title) for h in m.headings] == [("skirsnis", "Bendrosios procedūros"), ("skirsnis", "Kitos procedūros")]
    assert m.articles[1].blocks[-1].text == "1. Sąvoka."  # the section line is not article 2's text
    assert a.segments[0].kind == "approval" and a.segments[0].signature == ["Komisijos pirmininkė Vardenė Pavardenė"]


def test_rules_of_points_whose_stamp_lacks_patvirtinta():  # IAVPNPKA (1-52), TAPĮKĮEA (1-159), 2026-11-10
    from ltlaw.parse import parse
    points = [f"{n}. Punktas {n}." for n in range(1, 10)]
    head = ["LIETUVOS RESPUBLIKOS ENERGETIKOS MINISTRAS", "ĮSAKYMAS", "DĖL APRAŠO PATVIRTINIMO", "2011 m. vasario 25 d. Nr. 1-52",
            "Vilnius", "1. T v i r t i n u Informacijos teikimo tvarkos aprašą (pridedama).", "2. Pavedu agentūrai teikti.",
            "Energetikos ministras Vardenis Pavardenis"]
    stamp = ["Lietuvos Respublikos energetikos ministro", "2011 m. vasario 25 d. įsakymu Nr. 1-52"]
    for text in ("\n".join(head + stamp + ["INFORMACIJOS TEIKIMO TVARKOS APRAŠAS"] + points),
                 "\n".join(head + ["INFORMACIJOS TEIKIMO TVARKOS APRAŠAS"] + points)):  # no stamp at all
        a = parse(text)
        assert [s.kind for s in a.segments] == ["approval", "main"]
        assert a.main.title == "INFORMACIJOS TEIKIMO TVARKOS APRAŠAS" and len(a.main.articles) == 9
    # an order that approves nothing attached is not read so
    assert parse("\n".join(head[:5] + ["1. Nustatau tvarką.", "Energetikos ministras Vardenis Pavardenis"] + points)).main.title != "INFORMACIJOS TEIKIMO TVARKOS APRAŠAS"
