"""Change feeds (Atom) from the ledger."""
import xml.etree.ElementTree as ET

from ltlaw import feeds
from ltlaw.ledger import Ledger


def test_detect_and_write(tmp_path):
    led = Ledger(tmp_path / "l.json")
    led.record("2026-10-19", "DK", "52", "pending", "a")
    led.record("2026-10-19", "DK", "53", "current", "b")
    today = {"DK": {"52": ("current", "a"), "53": ("current", "c")}, "NEW": {"1": ("current", "x")}}
    ev = feeds.detect(led, today, "2026-10-20", {("DK", "52"): "u52", ("NEW", None): "unew"}, {"NEW": "Naujas įstatymas"})
    texts = sorted(e["text"] for e in ev)
    assert texts == ["DK 52 str.: žyma: Įsigalios → Galioja šiandien",
                     "DK 53 str.: tekstas pasikeitė",  # no record of where last night's text came from: no cause claimed
                     "Pridėtas teisės aktas: Naujas įstatymas"]
    (tmp_path / "ta" / "T1").mkdir(parents=True)
    feeds.write(tmp_path, "http://x", ev, {"DK": ("ta/T1/", "Darbo kodeksas")}, "2026-10-20")
    for f in ("atom.xml", "ta/T1/atom.xml"):
        root = ET.parse(tmp_path / f).getroot()  # well-formed Atom
        assert root.tag.endswith("feed")
    assert len(ET.parse(tmp_path / "ta/T1/atom.xml").getroot().findall("{http://www.w3.org/2005/Atom}entry")) == 2


def _led(tmp_path, rows):
    led = Ledger(tmp_path / "l.json")
    for act, label, fp in rows:
        led.record("2026-10-19", act, label, "current", fp)
    return led


def test_cause_of_a_text_change(tmp_path):
    led = _led(tmp_path, [("DK", "1-1", "a"), ("DK", "2", "b"), ("DK", "3", "c"), ("AI", "51", "d")])
    today = {"DK": {"1-1": ("current", "A"), "2": ("current", "B"), "3": ("current", "c")}, "AI": {"51": ("current", "D")}}
    prev = {"DK": {"text": "t1", "today": {}, "from": "2026-01-01"}, "AI": {"text": "e1", "today": {}, "eu_version": "02024R1689-20240712"}}
    # DK: a new text of the act; 2 is shown from a version taking over today. AI: a new EUR-Lex version
    now = {"DK": {"text": "t2", "today": {"2": "2026-10-20"}, "from": "2026-01-01"},
           "AI": {"text": "e2", "today": {}, "eu_version": "02024R1689-20260101"}}
    ev = {e["text"] for e in feeds.detect(led, today, "2026-10-20", {}, {}, cites={"AI": "AI aktas"}, sources=now, sources_prev=prev)}
    assert ev == {"DK 1¹ str.: tekstas pasikeitė (nauja Seimo kanceliarijos suvestinė redakcija)",
                  "DK 2 str.: tekstas pasikeitė (rodoma redakcija, galiojanti nuo 2026-10-20)",
                  "AI aktas 51 str.: tekstas pasikeitė (nauja EUR-Lex suvestinė redakcija)"}


def test_our_fixes_make_one_entry_per_act(tmp_path):
    led = _led(tmp_path, [("DK", str(i), "x") for i in range(1, 16)] + [("AI", "51", "d")])
    today = {"DK": {str(i): ("current", "y") for i in range(1, 16)}, "AI": {"51": ("current", "D")}}
    src = {"DK": {"text": "t1", "today": {}, "from": "2026-01-01"}, "AI": {"text": "e1", "today": {}, "eu_version": "v1"}}
    now = dict(src, AI={"text": "e2", "today": {}, "eu_version": "v1"})  # AI: the same version converted anew
    ev = feeds.detect(led, today, "2026-10-20", {("DK", None): "udk"}, {}, sources=now, sources_prev=src)
    assert [e["kind"] for e in ev] == ["fix", "fix"]
    dk = next(e for e in ev if e["act"] == "DK")
    assert dk["url"] == "udk" and dk["text"].startswith("DK: svetainėje pataisytas teksto nuskaitymas (15 str.: 1, 2,")
    assert "ir dar 3" in dk["text"] and dk["text"].endswith("teisės akto tekstas nepasikeitė")
    assert "perkėlimas iš EUR-Lex (1 str.: 51)" in next(e for e in ev if e["act"] == "AI")["text"]


def test_feed_entry_ids_stay_the_same_as_entries_are_added(tmp_path):
    old = [{"day": "2026-10-19", "act": "DK", "article": "52", "kind": "change", "text": "x"}]
    new = [{"day": "2026-10-20", "act": "DK", "article": None, "kind": "fix", "text": "y"}] + old
    ids = []
    for evs in (old, new):
        feeds.write(tmp_path, "http://x", evs, {}, "2026-10-20")
        ids.append({e.find("{http://www.w3.org/2005/Atom}title").text: e.find("{http://www.w3.org/2005/Atom}id").text
                    for e in ET.parse(tmp_path / "atom.xml").getroot().findall("{http://www.w3.org/2005/Atom}entry")})
    assert ids[0]["x"] == ids[1]["x"] and len(set(ids[1].values())) == 2


def test_area_feed(tmp_path):
    (tmp_path / "sritis" / "energetika").mkdir(parents=True)
    ev = [{"day": "2026-10-20", "act": "EEĮ", "article": "2", "kind": "change", "text": "EEĮ 2 str.: tekstas pasikeitė"},
          {"day": "2026-10-20", "act": "DK", "article": "52", "kind": "change", "text": "DK 52 str.: tekstas pasikeitė"}]
    feeds.write(tmp_path, "http://x", ev, {}, "2026-10-20",
                [{"name": "Energetika", "slug": "energetika", "acts": ["EEĮ", "BEnĮ"]}, {"name": "Kiti", "acts": ["DK"]}])
    root = ET.parse(tmp_path / "sritis/energetika/atom.xml").getroot()
    titles = [e.find("{http://www.w3.org/2005/Atom}title").text for e in root.findall("{http://www.w3.org/2005/Atom}entry")]
    assert titles == ["EEĮ 2 str.: tekstas pasikeitė"]
    assert root.find("{http://www.w3.org/2005/Atom}title").text == "Energetika: pakeitimai"


def test_a_night_run_twice_gives_each_entry_once(tmp_path, monkeypatch):
    # 2026-10-28's events were stored three times (re-runs): one entry each, the last stored wording
    from ltlaw import source
    monkeypatch.setattr(source, "STATE", tmp_path / "state")
    ev = [{"day": "2026-10-28", "act": "EVKTA", "article": "17", "kind": "change", "text": "EVKTA 17 p.: žyma"}]
    for _ in range(3):
        stored = feeds.store(ev)
    assert len(stored) == 1
    old = ev * 3 + [dict(ev[0], text="EVKTA 17 p.: žyma, vėliau")]
    feeds.write(tmp_path, "http://x", old, {}, "2026-11-01")
    titles = [e.find("{http://www.w3.org/2005/Atom}title").text
              for e in ET.parse(tmp_path / "atom.xml").getroot().findall("{http://www.w3.org/2005/Atom}entry")]
    assert titles == ["EVKTA 17 p.: žyma, vėliau"]


def test_feed_links_are_on_the_sites_address(tmp_path):
    # a local build stores its own address in the events (2026-11-02: 136 http://127.0.0.1:8765 links went live)
    ev = [{"day": "2026-11-02", "act": "DK", "article": "23", "kind": "change",
           "url": "http://127.0.0.1:8765/ta/2016-23709/str/23/", "text": "DK 23 str.: tekstas pasikeitė"}]
    feeds.write(tmp_path, "https://atviri-teises-aktai.lt", ev, {}, "2026-11-02")
    xml = (tmp_path / "atom.xml").read_text()
    assert "127.0.0.1" not in xml and 'href="https://atviri-teises-aktai.lt/ta/2016-23709/str/23/"' in xml


def test_a_page_of_what_changed_by_day_and_act():
    from ltlaw import feeds
    acts = {"DK": {"name": "DK – Darbo kodeksas", "url": "https://x/ta/1/"}, "BK": {"name": "BK", "url": "https://x/ta/2/"}}
    ev = [{"day": "2026-11-05", "act": "DK", "article": "52", "kind": "change", "url": "http://127.0.0.1:8765/ta/1/str/52/", "text": "DK 52 str.: Galioja šiandien → Įsigalios"},
          {"day": "2026-11-05", "act": "DK", "article": "53", "kind": "change", "url": "https://x/ta/1/str/53/", "text": "DK 53 str.: tekstas pasikeitė"},
          {"day": "2026-11-05", "act": "BK", "article": None, "kind": "act_added", "url": "https://x/ta/2/", "text": "Pridėtas teisės aktas: BK"},
          {"day": "2026-11-05", "act": "GONE", "article": "1", "kind": "change", "url": "https://x/g/", "text": "G 1 str.: tekstas pasikeitė"},
          {"day": "2026-10-01", "act": "DK", "article": "1", "kind": "change", "url": "https://x/old/", "text": "DK 1 str.: tekstas pasikeitė"}]
    d = feeds.digest(ev, "https://x", "2026-11-05", acts, 14)
    assert [x["day"] for x in d] == ["2026-11-05"]                              # older than 14 days: left out
    row = d[0]["acts"][0]
    assert [x["name"] for x in d[0]["acts"]] == ["DK – Darbo kodeksas"]         # an act no longer on the site: left out
    assert (row["n_text"], row["n_mark"]) == (1, 1) and row["entries"][0]["label"] == "53 str."  # a new text first
    assert row["entries"][1]["url"] == "https://x/ta/1/str/52/"                    # this site's address, whatever the log holds
    assert d[0]["added"] == [{"name": "BK", "url": "https://x/ta/2/"}]
    assert feeds.digest(ev, "https://x", "2026-11-05", acts, 14, {"BK"})[0]["acts"] == []
    # the page itself renders, with the act named and the counts in words
    from ltlaw.render import Site
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as t:
        site = Site(pathlib.Path(t), "https://x", "2026-11-05", False, None)
        site.changes_pages(ev, [{"abbr": "DK", "tag": "DK", "name": "Darbo kodeksas", "url": "https://x/ta/1/"}, {"abbr": "BK", "tag": "", "name": "BK", "url": "https://x/ta/2/"}],
                           [{"name": "Darbas", "slug": "darbas", "acts": ["DK"]}])
        html = (pathlib.Path(t) / "pakeitimai" / "index.html").read_text()
        assert "DK – Darbo kodeksas" in html and "1 naujas tekstas, 1 žyma" in html and "53 str." in html
        assert "tekstas pasikeitė" in (pathlib.Path(t) / "sritis" / "darbas" / "pakeitimai" / "index.html").read_text()

