"""Joint orders of several ministers ("1-348/D1-1014/3-742"): numbers and TAR codes with slashes."""
import importlib.util
import pathlib

from ltlaw import source
from ltlaw.points import ref_key


def _resolve_scope():
    p = pathlib.Path(__file__).resolve().parents[1] / "bin" / "resolve_scope.py"
    spec = importlib.util.spec_from_file_location("resolve_scope", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_joint_order_issuer():
    h = {"atv_dok_nr": "1-348/D1-1014/3-742", "rusis": "Įsakymas",
         "priemusi_inst": "Lietuvos Respublikos aplinkos ministerija\nLietuvos Respublikos energetikos ministerija\n"
                          "Lietuvos Respublikos susisiekimo ministerija"}
    f = _resolve_scope().order_fields(h)
    assert f["issuer"] == ("Lietuvos Respublikos aplinkos ministro, Lietuvos Respublikos energetikos ministro ir "
                           "Lietuvos Respublikos susisiekimo ministro")


def test_joint_order_paths_and_keys():
    assert source.act_path({}, "110203NISAK14/3-742") == "ta/110203NISAK14-3-742/"
    assert ref_key("1-7/D1-21/3-10", "2020-01-15") == "1-7/D1-21/3-10/2020-01-15"
    assert "1-7/D1-21/3-10/2020-01-15".rsplit("/", 1) == ["1-7/D1-21/3-10", "2020-01-15"]
    title = ("Dėl Lietuvos Respublikos energetikos ministro, Lietuvos Respublikos aplinkos ministro ir Lietuvos Respublikos "
             "susisiekimo ministro 2010 m. gruodžio\xa022\xa0d. įsakymo Nr. 1-348/D1-1014/3-742 „Dėl …“ pakeitimo")
    assert source.names_points_act(title, "1-348/D1-1014/3-742", "2010-12-22", "Įsakymas")


def test_vert_resolutions_are_cited_as_o3e_or_o3():
    # O3-1235 (2026-09-18) amends VSIA, approved by O3E-296 of 2019-08-02, and cites it as "Nr. O3-296" (B84)
    t = ("Dėl Valstybinės energetikos reguliavimo tarybos 2019 m. rugpjūčio 2 d. nutarimo Nr. O3-296 „Dėl Viešai "
         "skelbiamos informacijos tvarkos aprašo patvirtinimo“ pakeitimo")
    assert source.names_points_act(t, "O3E-296", "2019-08-02", "Nutarimas")
    assert source.names_points_act(t.replace("O3-296", "O3E-296"), "O3-296", "2019-08-02", "Nutarimas")
    assert not source.names_points_act(t, "O3E-296", "2019-08-03", "Nutarimas")  # the date must match too
    assert not source.names_points_act(t, "O3E-29", "2019-08-02", "Nutarimas")
    assert source.number_forms("1-38") == ["1-38"] and source.number_forms("O3E-296") == ["O3E-296", "O3-296"]


def test_a_ministers_order_numbered_like_a_roman_numeral_is_keyed_with_its_date():
    # B88: "V-300" (health, education, defence ministers' orders) was read as a Seimas number, so its note never met
    # the order's metadata ("V-300/2016-03-03") and every point it changed was "unknown"
    assert ref_key("V-300", "2016-03-03") == "V-300/2016-03-03"
    assert ref_key("XV-969", "2025-12-18") == "XV-969" and ref_key("I-1240", "1996-03-19") == "I-1240"
    assert ref_key("VIII-1864", "2000-07-18") == "VIII-1864" and ref_key("XIV-2404", "2023-12-19") == "XIV-2404"
    assert ref_key("IX-785", "2002-03-14") == "IX-785" and ref_key("X-1367", "2007-12-13") == "X-1367"
