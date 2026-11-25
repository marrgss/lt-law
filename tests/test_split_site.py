"""bin/split_site.py: the site split between Workers by their routes (D-051)."""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("split_site", ROOT / "bin" / "split_site.py")
split_site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split_site)


def _site(tmp_path):
    s = tmp_path / "site"
    for rel in ["index.html", "404.html", "_headers", "app.js", "api/v1/acts.json", "ta/1001010ISTAIII-1864/index.html",
                "ta/1001010ISTAIII-1864/str/1/index.html", "ta/1001010ISTAIII-1864/articles.json", "ta/2016-23709/str/52/index.html",
                "ta/0921010KONSRG922324/str/1/index.html", "ta/11/x/index.html", "es/32016R0679/str/17/index.html"]:
        (s / rel).parent.mkdir(parents=True, exist_ok=True)
        (s / rel).write_text(rel)
    (s / "_redirects").write_text("/ta/1001010ISTAIII-1864/str/ /ta/1001010ISTAIII-1864/ 301\n"
                                  "/ta/2016-23709/str/ /ta/2016-23709/ 301\n/ta/11/str/ /ta/11/ 301\n")
    return s


def test_split_by_routes_longest_prefix_wins(tmp_path):
    s = _site(tmp_path)
    parts = [{"name": "two", "prefixes": ["ta/1"], "dir": tmp_path / "two"},
             {"name": "three", "prefixes": ["ta/11"], "dir": tmp_path / "three"}]
    before = split_site.counts(s, parts)
    after = split_site.apply(s, parts)
    assert [c["files"] for c in before] == [c["files"] for c in after]  # the copies counted for both
    two, three = tmp_path / "two", tmp_path / "three"
    assert (two / "ta/1001010ISTAIII-1864/str/1/index.html").exists() and (two / "ta/1001010ISTAIII-1864/articles.json").exists()
    assert (three / "ta/11/x/index.html").exists() and not (two / "ta/11").exists()      # the more specific route wins
    assert not (s / "ta/1001010ISTAIII-1864/index.html").exists() and (s / "ta/2016-23709/str/52/index.html").exists()
    # the act's article list: served by its part, and a copy for the MCP Worker (get_act_contents, 2026-11-25)
    assert (s / "ta/1001010ISTAIII-1864/articles.json").exists() and sorted(p.name for p in (s / "ta/1001010ISTAIII-1864").iterdir()) == ["articles.json"]
    assert (s / "api/v1/acts.json").exists() and (s / "es/32016R0679/str/17/index.html").exists()  # the MCP Worker's files stay
    for d in (two, three):                                                                  # each part: its own 404 and headers
        assert (d / "404.html").read_text() == "404.html" and (d / "_headers").exists()
    assert (s / "_redirects").read_text() == "/ta/2016-23709/str/ /ta/2016-23709/ 301\n"
    assert (two / "_redirects").read_text().startswith("/ta/1001010ISTAIII-1864/str/") and "/ta/11/" in (three / "_redirects").read_text()


def test_limits_and_configs():
    assert split_site.over_limits([{"worker": "w", "files": 100_001, "redirect_rules": 2_001}]) == [
        "w: 100001 files (limit 100000)", "w: 2001 _redirects rules (limit 2000)"]
    parts = [split_site.part_of(c) for c in split_site.configs()]
    assert parts and all(p["prefixes"] and not any(x.startswith("api") for x in p["prefixes"]) for p in parts)
    assert len({p["dir"] for p in parts}) == len(parts) and all(p["dir"].name != "site" for p in parts)
