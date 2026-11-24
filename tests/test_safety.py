"""Safety rules added after the 2026-10-18 red team: repeals, gates, machine-readable output."""
import importlib.util
import pathlib

from ltlaw.currency import Laws, _article_repealed, assess
from ltlaw.parse import parse
from ltlaw.render import ld_json

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nightly", ROOT / "bin" / "nightly.py")
nightly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nightly)

ACT = """Įstatymas netenka galios 2027-01-01:
Lietuvos Respublikos Seimas, Įstatymas
Nr. XV-1072, 2026-06-25, paskelbta TAR 2026-07-03, i. k. 2026-11525
Suvestinė redakcija nuo 2024-01-01 iki 2026-12-31
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
1 straipsnis. Paskirtis
Šis įstatymas nustato tvarką.
2 straipsnis. Neteko galios nuo 2021-02-01
"""


class NoLaws(Laws):
    def __init__(self):
        self.meta, self.fetch, self._cache = {}, False, {}


def test_act_expiry_header_and_repealed_state():
    act = parse(ACT)
    assert act.expires == "2027-01-01"
    sa = {"genitive": "bandomojo įstatymo", "number": "XV-0"}
    before = assess(act, sa, NoLaws(), "2026-10-18")
    assert before.expires == "2027-01-01" and before.articles["1"].state == "current"
    assert before.articles["2"].state == "repealed" and before.articles["2"].applies_from == "2021-02-01"
    after = assess(act, sa, NoLaws(), "2027-01-02")
    assert {s.state for s in after.articles.values()} == {"repealed"}  # never "current" after the act is gone


def test_article_repealed_titles():
    class A:
        def __init__(self, title):
            self.title, self.blocks = title, []
    assert _article_repealed(A("Neteko galios nuo 2021-02-01")) == (True, "2021-02-01")
    assert _article_repealed(A("Neteko galios nuo 2011 m. balandžio 1 d.")) == (True, "2011-04-01")
    assert _article_repealed(A("Neteko galios.")) == (True, None)
    assert _article_repealed(A("Galiojimo terminas"))[0] is False


def test_check_act_gate():
    b = {"abbr": "X", "n": 90, "consolidation_valid_from": "2026-11-20", "rewrites": [], "labels": []}
    prev = {"articles": 100, "version_from": "2026-06-01"}
    assert "lost" in nightly.check_act(b, prev, set())
    assert nightly.check_act(dict(b, rewrites=["2026-11-20"]), prev, set()) is None  # whole-act rewrite
    assert nightly.check_act(b, prev, {"X"}) is None                                 # accepted by hand
    assert "backwards" in nightly.check_act(dict(b, n=100, consolidation_valid_from="2026-01-01"), prev, set())
    # a closed slice prepared before the old version is not a step back (CK 2027-01-01..2027-10-31 before 2027-11-01, B62)
    ck_prev = {"articles": 100, "version_from": "2027-11-01"}
    assert nightly.check_act(dict(b, n=100, consolidation_valid_from="2027-01-01", consolidation_valid_to="2027-10-31"), ck_prev, set()) is None
    assert "backwards" in nightly.check_act(dict(b, n=100, consolidation_valid_from="2027-01-01", consolidation_valid_to=None), ck_prev, set())
    assert nightly.check_act(dict(b, n=0), None, set()) == "no articles parsed"
    # one article lost from the same version is rejected however small the share (A8)
    same = {"abbr": "X", "n": 99, "consolidation_valid_from": "2026-06-01", "rewrites": [], "labels": [str(i) for i in range(1, 100)]}
    prev_l = dict(prev, labels=[str(i) for i in range(1, 101)])
    assert "disappeared" in nightly.check_act(same, prev_l, set())
    assert nightly.check_act(dict(same, consolidation_valid_from="2026-07-01"), prev_l, set()) is None  # new version: allowed
    # a rule set whose points start further on lost its start (MPT from 14, 2026-11-09), new act or not
    pts = {"abbr": "P", "n": 20, "unit": "punktas", "consolidation_valid_from": "2024-01-11", "rewrites": [], "labels": [str(i) for i in range(14, 34)]}
    assert "start at 14" in nightly.check_act(pts, None, set())
    assert nightly.check_act(dict(pts, labels=["1-1", "2"]), None, set()) is None
    assert nightly.check_act(dict(pts, unit="straipsnis"), None, set()) is None  # a law may start anywhere (a part of a code)


def test_jsonld_cannot_close_script():
    assert "</script>" not in ld_json({"name": "a</script><script>alert(1)</script>"})


def test_article_repealed_from_an_event():
    class A:
        def __init__(self, title):
            self.title, self.blocks = title, []
    assert _article_repealed(A("Neteko galios nuo Šengeno konvencijos įsigaliojimo Lietuvos Respublikai dienos.")) == (True, None)


STAGED = """1 straipsnis. 29 straipsnio pakeitimas
Pakeisti 29 straipsnį.
2 straipsnis. VII skyriaus pavadinimo pakeitimas
Pakeisti VII skyriaus pavadinimą.
3 straipsnis. VII skyriaus pakeitimas
Pakeisti VII skyrių ir jį išdėstyti taip:
„VII SKYRIUS
ATSAKOMYBĖ
30 straipsnis. Atsakomybė
Naujas tekstas.“
4 straipsnis. Įstatymo įsigaliojimas
1. Šis įstatymas, išskyrus šio įstatymo 3 straipsnį, įsigalioja 2026 m. rugpjūčio 1 d.
2. Šio įstatymo 3 straipsnis įsigalioja 2027 m. sausio 1 d.
"""


def _chapter_act(frm, to):
    return parse(f"""Suvestinė redakcija nuo {frm}{' iki ' + to if to else ''}
LIETUVOS RESPUBLIKOS BANDOMASIS ĮSTATYMAS
VII SKYRIUS
AUTORIŲ TEISIŲ APSAUGA
Pakeistas skyriaus pavadinimas:
Nr. XV-9, 2026-06-25, paskelbta TAR 2026-07-03, i. k. 2026-11526
30 straipsnis. Autorių teisių apsauga
1. Senas tekstas.
""")


def test_a_staged_chapter_law_is_settled_by_the_consolidations_range():
    # GKĮ 30 (XV-1073: 2026-08-01 and 2027-01-01): the consolidation valid 08-01..12-31 holds exactly the first stage
    from ltlaw.currency import parse_amending

    class OneLaw(NoLaws):
        def __init__(self):
            super().__init__()
            self._cache = {"XV-9": parse_amending("XV-9", STAGED, "2026-08-01")}
    sa = {"genitive": "bandomojo įstatymo", "number": "XV-0"}
    state = lambda frm, to: assess(_chapter_act(frm, to), sa, OneLaw(), "2026-11-02").articles["30"].state  # noqa: E731
    assert state("2026-08-01", "2026-12-31") == "current"
    # open-ended from the first stage: the next stage (after today) gets a consolidation of its own, so this text holds
    # the first stage only (RŽNTKŽŠA from 2026-10-20: D1-188's 2027 wording of point 7 is not in it), and the chapter
    # set out anew from 2027-01-01 is a known later change
    assert state("2026-08-01", None) == "current"
    st = assess(_chapter_act("2026-08-01", None), sa, OneLaw(), "2026-11-02").articles["30"]
    assert st.future_change == ("2027-01-01", "XV-9", True) and st.changes_on == "2027-01-01"
    assert state("2026-07-15", "2026-12-31") == "unknown"    # a stage inside the range
    assert state("2026-07-15", None) == "unknown"            # open-ended, but a stage between its start and today


def test_backtest_survives_a_text_it_cannot_read(monkeypatch):
    """2026-11-07: Suvestine down, an act with no cached consolidation: two nightly runs stopped before building."""
    seen = []

    class Led:
        def backtest(self, abbr, act, day):
            seen.append(abbr)
            return {"article_days": 1}

    def act_text(doc):
        if doc == "bad":
            raise TimeoutError("Suvestine skipped for this run (failed earlier: HTTP 500)")
        return "1 straipsnis. Pavadinimas\nTekstas.", {"origin": "Dokumentas"}

    monkeypatch.setattr(nightly.source, "act_text", act_text)
    scope = [{"abbr": "BAD", "dokumento_id": "bad"}, {"abbr": "OK", "dokumento_id": "ok"}, {"abbr": "SAME", "dokumento_id": "same"}]
    warnings = []
    out = nightly.backtest_changed(scope, ["BAD", "OK"], Led(), "2026-11-07", warnings)
    assert list(out) == ["OK"] and seen == ["OK"]                  # the other act is still compared, the unchanged one isn't
    assert len(warnings) == 1 and "BAD" in warnings[0] and "TimeoutError" in warnings[0]

