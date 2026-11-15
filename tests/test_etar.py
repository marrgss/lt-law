"""e-tar answer-key helpers that need no network: the act page's "no consolidated version" (B83)."""
from ltlaw import etar

NONE = """<html><script>var x = "Suvestinė nuo 2020-01-01";</script><body>
<span>Galiojanti suvestinė redakcija:</span> <span>Nėra</span>
<h3>Suvestinių redakcijų sąrašas pagal datą:</h3>
  <span>Nėra</span>
<table><tr><td>Data nuo</td><td>Data iki</td></tr></table></body></html>"""

SOME = """<html><body><h3>Suvestinių redakcijų sąrašas pagal datą:</h3>
<table><tr><td><a href="/portal/lt/legalAct/TAR.X/abcdefghij">Suvestinė nuo 2024-01-01</a></td><td>2025-01-01</td></tr></table>
</body></html>"""


def _fake(monkeypatch, tmp_path, page):
    monkeypatch.setattr(etar, "ROOT", tmp_path)
    monkeypatch.setattr(etar, "_get", lambda url: page if "legalActEditions" in url else "")


def test_an_act_e_tar_says_has_no_consolidated_version(monkeypatch, tmp_path):
    _fake(monkeypatch, tmp_path, NONE)
    assert etar.never_consolidated("TAR.X") is True
    row = {"galioj_busena": "galioja", "pakeista": None, "isigalioja": "2026-03-07"}
    assert etar.original_in_force("TAR.X", "2026-03-07", row)  # Suvestine dates the original (EOSPPSAA)
    assert etar.original_in_force("TAR.X", None, row)
    assert not etar.original_in_force("TAR.X", "2026-05-01", row)  # a later date: not the original
    assert not etar.original_in_force("TAR.X", "2026-03-07", {**row, "pakeista": "2026-04-01"})  # amended
    assert not etar.original_in_force("TAR.X", "2026-03-07", {**row, "galioj_busena": "negalioja"})


def test_an_act_with_versions_or_an_unread_page_is_not_taken_as_never_consolidated(monkeypatch, tmp_path):
    _fake(monkeypatch, tmp_path, SOME)
    assert etar.never_consolidated("TAR.X") is False
    _fake(monkeypatch, tmp_path / "b", "<html>Klaida</html>")  # an error page lists nothing, but says nothing either
    assert etar.never_consolidated("TAR.X") is False
