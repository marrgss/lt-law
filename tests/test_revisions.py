"""D-039: a text whose Dokumentas revision is unchanged is not fetched again (within FULL_EVERY_DAYS).
D-056: the nightly checks the unchanged first, fetches the changed, then re-fetches a few unchanged ones in full."""
import datetime as dt
import importlib.util
import json
import pathlib
import urllib.parse

from ltlaw import source

spec = importlib.util.spec_from_file_location("nightly", pathlib.Path(__file__).resolve().parents[1] / "bin" / "nightly.py")
nightly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nightly)


def _row(text, rev):
    return {"dokumento_id": "X1", "tekstas_lt": text, "galioj_busena": "galioja", "_revision": rev}


def test_unchanged_revision_skips_the_fetch(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(source, "fetch_dokumentas", lambda d: calls.append(d) or _row("text v1", "r1"))
    first = source.snapshot("X1", root=tmp_path, day="2026-10-01")
    assert calls == ["X1"] and (tmp_path / "X1" / "revision.txt").read_text().startswith("r1 ")
    assert source.full_fetched("X1", tmp_path)
    skips = source.REVISION_SKIPS
    assert source.snapshot("X1", root=tmp_path, day="2026-10-02", revision="r1") == first
    assert calls == ["X1"] and source.REVISION_SKIPS == skips + 1  # not fetched, counted as checked
    assert (tmp_path / "X1" / "checked.txt").exists()


def test_changed_or_missing_revision_fetches(tmp_path, monkeypatch):
    rows = iter([_row("text v1", "r1"), _row("text v2", "r2"), _row("text v2", "r3")])
    monkeypatch.setattr(source, "fetch_dokumentas", lambda d: next(rows))
    source.snapshot("X1", root=tmp_path, day="2026-10-01")
    p = source.snapshot("X1", root=tmp_path, day="2026-10-02", revision="r2")  # new revision: fetched, new text
    assert json.loads(p.read_text())["row"]["tekstas_lt"] == "text v2"
    q = source.snapshot("X1", root=tmp_path, day="2026-10-03")  # no revision given: fetched; same text, newer revision kept
    assert q == p and (tmp_path / "X1" / "revision.txt").read_text().startswith("r3 ")


def test_old_full_fetch_is_fetched_again(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(source, "fetch_dokumentas", lambda d: calls.append(d) or _row("text v1", "r1"))
    source.snapshot("X1", root=tmp_path, day="2026-10-01")
    old = (dt.datetime.now().astimezone() - dt.timedelta(days=source.FULL_EVERY_DAYS + 1)).isoformat(timespec="seconds")
    (tmp_path / "X1" / "revision.txt").write_text(f"r1 {old}")
    source.snapshot("X1", root=tmp_path, day="2026-10-02", revision="r1")
    assert calls == ["X1", "X1"]


def test_revisions_batches_and_drops_ambiguous(monkeypatch):
    seen = []
    def query(model, q, tries=4, timeout=120):
        seen.append(q)
        if "B2" in q:
            return [{"dokumento_id": "B2", "_revision": "x"}, {"dokumento_id": "B2", "_revision": "y"}]
        if "C3" in q:
            raise TimeoutError
        return [{"dokumento_id": "A1", "_revision": "a"}]
    monkeypatch.setattr(source, "query", query)
    assert source.revisions(["A1", "B2", "C3"], batch=1) == {"A1": "a"}  # two rows: unknown; a failed batch: unknown
    assert len(seen) == 3 and all(q.startswith("select(dokumento_id,_revision)&or(") for q in seen)


def test_every_query_url_is_new_each_run(monkeypatch):
    # data.gov.lt serves a cached answer to a repeated URL (X-Cache: STALE): the 10-31 night got 10-30's answer
    urls = []
    monkeypatch.setattr(source, "_get", lambda url, **kw: urls.append(url) or {"_data": []})
    source.query("Dokumentas", 'select(_id)&rusis="Įstatymas"&limit(5)')
    assert urls[0].endswith(urllib.parse.quote(source.FRESH, safe='()&=,"_-<>!/'))
    assert '_id!="' in urls[0]


def test_a_rate_limited_suvestine_is_not_down(monkeypatch):
    import urllib.error
    def busy(url, **kw):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(source, "_get", busy)
    monkeypatch.setattr(source, "SUVESTINE_DOWN", False)
    monkeypatch.setattr(source, "RATE_LIMITED", [0])
    try:
        source.query("Suvestine", 'select(_id)&limit(1)')
    except urllib.error.HTTPError:
        pass
    assert source.SUVESTINE_DOWN is False and source.RATE_LIMITED == [1]


def test_todays_text_waits_out_a_429(tmp_path, monkeypatch):
    import urllib.error
    from ltlaw import today
    monkeypatch.setattr(source, "STATE", tmp_path / "state")
    monkeypatch.setattr(source, "DATA", tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "suvestine_scope.jsonl").write_text(json.dumps(
        {"dokumento_id": "X1", "suvestines_id": "s1", "galioja_nuo": "2026-11-01", "galioja_iki": None}) + "\n")
    calls = []
    def q(model, query):
        calls.append(query)
        if len(calls) == 1:
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        return [{"suvestines_id": "s1", "galioja_nuo": "2026-11-01", "galioja_iki": None, "tekstas_lt": "1 straipsnis. A"}]
    monkeypatch.setattr(source, "query", q)
    monkeypatch.setattr(today, "RATE_WAIT_S", 0)
    monkeypatch.setattr(today, "_FETCH", {"spent": 0.0, "skipped": 0})
    r = today._suvestine_valid_on("X1", "2026-11-02")
    assert r["tekstas_lt"] == "1 straipsnis. A" and len(calls) == 2


def test_a_text_checked_earlier_today_is_not_fetched_again(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(source, "fetch_dokumentas", lambda d: calls.append(d) or _row("text v1", "r1"))
    first = source.snapshot("X1", root=tmp_path, day="2026-10-01")
    (tmp_path / "X1" / "checked.txt").write_text("2026-10-02T02:40:00+03:00")
    again = source.snapshot("X1", root=tmp_path, day="2026-10-02")
    assert again == first and calls == ["X1"]


def test_upcoming_versions_are_fetched_soonest_first_and_paced(tmp_path, monkeypatch):
    from ltlaw import today
    monkeypatch.setattr(source, "STATE", tmp_path / "state")
    monkeypatch.setattr(source, "DATA", tmp_path)
    monkeypatch.setattr(source, "SUVESTINE_DOWN", False)
    (tmp_path / "state").mkdir()
    rows = [{"dokumento_id": "X1", "suvestines_id": "later", "galioja_nuo": "2026-12-01T00:00:00", "galioja_iki": None},
            {"dokumento_id": "X1", "suvestines_id": "soon", "galioja_nuo": "2026-11-05T00:00:00", "galioja_iki": "2026-11-30T00:00:00"},
            {"dokumento_id": "X1", "suvestines_id": "far", "galioja_nuo": "2027-06-01T00:00:00", "galioja_iki": None},
            {"dokumento_id": "X1", "suvestines_id": "now", "galioja_nuo": "2026-10-01T00:00:00", "galioja_iki": "2026-11-04T00:00:00"}]
    (tmp_path / "state" / "suvestine_scope.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    asked = []
    def q(model, query):
        sid = query.split('suvestines_id="')[1].split('"')[0]
        asked.append(sid)
        return [{"suvestines_id": sid, "tekstas_lt": "1 straipsnis. A"}]
    monkeypatch.setattr(source, "query", q)
    got = today.prefetch_upcoming(["X1"], "2026-11-02", horizon_days=45, gap_s=0)
    assert asked == ["soon", "later"] and got == {"fetched": 2, "left": 0}   # not today's, not beyond 45 days
    assert today.prefetch_upcoming(["X1"], "2026-11-02", gap_s=0) == {"fetched": 0, "left": 0}  # cached now


def test_a_full_fetch_ignores_the_revision_and_todays_check(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(source, "fetch_dokumentas", lambda d: calls.append(d) or _row("text v1", "r1"))
    first = source.snapshot("X1", root=tmp_path, day="2026-10-01")
    assert source.revision_unchanged("X1", "r1", tmp_path) and not source.revision_unchanged("X1", "r2", tmp_path)
    assert not source.revision_unchanged("X1", None, tmp_path) and source.seen_revision("X1", tmp_path) == "r1"
    (tmp_path / "X1" / "checked.txt").write_text("2026-10-02T02:40:00+03:00")
    assert source.snapshot("X1", root=tmp_path, day="2026-10-02", revision="r1", full=True) == first
    assert calls == ["X1", "X1"]


def _night(tmp_path, monkeypatch, texts, revs_now, row_revs=None):
    """Three acts fetched in full some days ago (C the longest ago), then a night with `texts` at the source and
    `revs_now` read first (`row_revs`: the rows' revisions when their texts are fetched, if they changed meanwhile)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(source, "DOWN", False)
    monkeypatch.setattr(source, "awaiting_consolidation", lambda scope, day: set())
    rows = {i: {"dokumento_id": i, "tekstas_lt": f"{i} v1", "galioj_busena": "galioja", "_revision": f"{i}1"} for i in "ABC"}
    calls = []
    monkeypatch.setattr(source, "fetch_dokumentas", lambda d: calls.append(d) or rows[d])
    now = dt.datetime.now().astimezone()
    for n, i in enumerate("CAB"):
        source.snapshot(i, day="2026-10-01")
        when = (now - dt.timedelta(days=9 - n)).isoformat(timespec="seconds")
        pathlib.Path("data/dokumentas", i, "revision.txt").write_text(f"{i}1 {when}")
        pathlib.Path("data/dokumentas", i, "checked.txt").write_text(when)
    calls.clear()
    for i, t in texts.items():
        rows[i] = dict(rows[i], tekstas_lt=t, _revision=(row_revs or revs_now)[i])
    monkeypatch.setattr(source, "revisions", lambda ids: dict(revs_now))
    log, warnings = {"steps": {}}, []
    failed = nightly.refresh_texts([{"dokumento_id": i, "abbr": i} for i in "ABC"], now.date().isoformat(), log, warnings)
    return calls, log["steps"], warnings, failed


def test_the_night_fetches_the_changed_text_first_then_re_fetches_unchanged_ones(tmp_path, monkeypatch):
    calls, steps, warnings, failed = _night(tmp_path, monkeypatch, {"B": "B v2"}, {"A": "A1", "B": "B2", "C": "C1"})
    assert calls == ["B", "C", "A"]  # the changed one; then the backstop, the longest unfetched first
    assert steps["texts_changed"] == ["B"] and steps["texts_by_revision"]["refetched_in_full"] == 2
    assert not warnings and not failed
    assert all(pathlib.Path("data/dokumentas", i, "checked.txt").read_text()[:10] == dt.date.today().isoformat() for i in "ABC")


def test_without_backstop_time_only_the_changed_text_is_fetched(tmp_path, monkeypatch):
    monkeypatch.setattr(nightly, "BACKSTOP_S", -1)
    calls, steps, warnings, _ = _night(tmp_path, monkeypatch, {"B": "B v2"}, {"A": "A1", "B": "B2", "C": "C1"})
    assert calls == ["B"] and steps["texts_by_revision"]["refetched_in_full"] == 0 and not warnings


def test_a_text_changed_under_the_same_revision_is_found_and_reported(tmp_path, monkeypatch):
    calls, steps, warnings, _ = _night(tmp_path, monkeypatch, {"C": "C v2"}, {"A": "A1", "B": "B1", "C": "C1"})
    assert calls == ["C", "A", "B"] and steps["texts_changed"] == ["C"]
    assert len(warnings) == 1 and "without a new revision" in warnings[0] and "['C']" in warnings[0]


def test_a_row_changed_during_the_night_is_no_alarm(tmp_path, monkeypatch):
    # the revisions were read, then the row changed (data.gov.lt's update): the full re-fetch sees a new revision
    calls, steps, warnings, _ = _night(tmp_path, monkeypatch, {"C": "C v2"}, {"A": "A1", "B": "B1", "C": "C1"}, row_revs={"C": "C2"})
    assert calls == ["C", "A", "B"] and steps["texts_changed"] == ["C"] and not warnings


def test_a_passing_suvestine_500_is_retried_not_down(monkeypatch):
    """One quick server error among the night's Suvestine queries must not cost the night's texts (2026-11-18, -20)."""
    calls = []

    def flaky(url, tries=4, timeout=120):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)
        return {"_data": [{"suvestines_id": "x"}]}
    monkeypatch.setattr(source, "_get", flaky)
    monkeypatch.setattr(source, "SUVESTINE_DOWN", False)
    monkeypatch.setattr(source, "SUVESTINE_5XX", [0])
    monkeypatch.setattr(source, "SUVESTINE_RETRY_S", 0)
    assert source.query("Suvestine", 'select(suvestines_id)&limit(1)') == [{"suvestines_id": "x"}]
    assert len(calls) == 2 and source.SUVESTINE_DOWN is False


def test_suvestine_is_given_up_after_repeated_server_errors_and_at_once_on_a_timeout(monkeypatch):
    def broken(url, tries=4, timeout=120):
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)
    monkeypatch.setattr(source, "_get", broken)
    monkeypatch.setattr(source, "SUVESTINE_DOWN", False)
    monkeypatch.setattr(source, "SUVESTINE_5XX", [0])
    monkeypatch.setattr(source, "SUVESTINE_RETRY_S", 0)
    for n in range(source.SUVESTINE_5XX_LIMIT):
        assert source.SUVESTINE_DOWN is False
        try:
            source.query("Suvestine", f'select(suvestines_id)&n="{n}"')
        except urllib.error.HTTPError:
            pass
    assert source.SUVESTINE_DOWN == "HTTP 500"

    def stalled(url, tries=4, timeout=120):
        raise TimeoutError("timed out")
    monkeypatch.setattr(source, "_get", stalled)
    monkeypatch.setattr(source, "SUVESTINE_DOWN", False)
    try:
        source.query("Suvestine", 'select(suvestines_id)&limit(1)')
    except TimeoutError:
        pass
    assert source.SUVESTINE_DOWN == "TimeoutError"


def test_version_lists_wait_out_a_429_and_go_on(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "STATE", tmp_path)
    monkeypatch.setattr(source, "SUVESTINE_DOWN", False)
    monkeypatch.setattr(source, "SUVESTINE_429_WAIT_S", 0)
    asked = []

    def q(model, query):
        doc = query.split('dokumento_id="')[1].split('"')[0]
        asked.append(doc)
        if len(asked) == 2:
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        return [{"_id": doc, "dokumento_id": doc, "suvestines_id": f"s-{doc}", "galioja_nuo": "2026-01-01"}]
    monkeypatch.setattr(source, "query", q)
    acts = [{"dokumento_id": d} for d in ("A", "B", "C")]
    assert source.update_suvestine_lists(acts, per_run=10) == 3
    assert asked == ["A", "B", "B", "C"]
    assert sorted(json.loads((tmp_path / "suvestine_checked.json").read_text())) == ["A", "B", "C"]


def test_a_stalled_suvestine_names_the_act_it_was_asking_for(monkeypatch):
    def stalled(url, tries=4, timeout=120):
        raise TimeoutError("timed out")
    monkeypatch.setattr(source, "_get", stalled)
    monkeypatch.setattr(source, "SUVESTINE_DOWN", False)
    try:
        source.query("Suvestine", 'select(_id)&dokumento_id="TAR.X1"&limit(5)')
    except TimeoutError:
        pass
    assert source.SUVESTINE_DOWN == "TimeoutError asking for TAR.X1"


def _newer_setup(tmp_path, monkeypatch, cached=True):
    monkeypatch.setattr(source, "STATE", tmp_path / "state")
    monkeypatch.setattr(source, "DATA", tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "suvestine_scope.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"dokumento_id": "X1", "suvestines_id": "old", "galioja_nuo": "2015-10-31T00:00:00", "galioja_iki": "2024-10-31T00:00:00"},
        {"dokumento_id": "X1", "suvestines_id": "new", "galioja_nuo": "2024-11-01T00:00:00", "galioja_iki": None,
         "suv_duom_atnaujinimas": "2024-10-08T10:48:37"}]))
    if cached:
        (tmp_path / "suvestine" / "X1").mkdir(parents=True)
        (tmp_path / "suvestine" / "X1" / "new.json").write_text(json.dumps(
            {"suvestines_id": "new", "galioja_nuo": "2024-11-01T00:00:00", "galioja_iki": None,
             "suv_duom_atnaujinimas": "2024-10-08T10:48:37", "tekstas_lt": "1. Nauja redakcija."}))
    source._SCOPE_ROWS.clear()


def test_an_ended_dokumentas_text_gives_way_to_todays_cached_consolidation(tmp_path, monkeypatch):
    _newer_setup(tmp_path, monkeypatch)
    ended = "Suvestinė redakcija nuo 2015-10-31 iki 2024-10-31\n\n1. Sena."
    t, info = source.suvestine_newer_today("X1", ended, day="2026-11-22")
    assert t.startswith("Suvestinė redakcija nuo 2024-11-01\n") and "Nauja redakcija" in t
    assert info["origin"] == "Suvestine" and info["suvestines_id"] == "new" and info["prepared"].startswith("2024-10-08")
    # a Dokumentas version still running, or one with no end date, is kept
    assert source.suvestine_newer_today("X1", "Suvestinė redakcija nuo 2015-10-31 iki 2027-01-01\n", day="2026-11-22") is None
    assert source.suvestine_newer_today("X1", "Suvestinė redakcija nuo 2015-10-31\n", day="2026-11-22") is None
    # Dokumentas newer than the Suvestine version valid today: kept
    assert source.suvestine_newer_today("X1", "Suvestinė redakcija nuo 2025-01-01 iki 2025-12-31\n", day="2026-11-22") is None


def test_an_uncached_newer_consolidation_is_not_fetched_here(tmp_path, monkeypatch):
    _newer_setup(tmp_path, monkeypatch, cached=False)
    monkeypatch.setattr(source, "query", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no request")))
    assert source.suvestine_newer_today("X1", "Suvestinė redakcija nuo 2015-10-31 iki 2024-10-31\n", day="2026-11-22") is None


def test_todays_version_is_fetched_on_a_fetching_night_else_the_newest_cached_one(tmp_path, monkeypatch):
    _newer_setup(tmp_path, monkeypatch)
    with (tmp_path / "state" / "suvestine_scope.jsonl").open("a") as f:
        f.write(json.dumps({"dokumento_id": "X1", "suvestines_id": "newest", "galioja_nuo": "2026-11-20T00:00:00",
                            "galioja_iki": None}) + "\n")
    source._SCOPE_ROWS.clear()
    ended = "Suvestinė redakcija nuo 2015-10-31 iki 2024-10-31\n"
    monkeypatch.setattr(source, "SUVESTINE_DOWN", False)
    monkeypatch.setattr(source, "REFRESH_SUVESTINE", False)
    assert source.suvestine_newer_today("X1", ended, day="2026-11-22")[1]["suvestines_id"] == "new"  # no request: cached one
    monkeypatch.setattr(source, "REFRESH_SUVESTINE", True)
    monkeypatch.setattr(source, "query", lambda m, q: [{"suvestines_id": "newest", "galioja_nuo": "2026-11-20T00:00:00",
                                                        "galioja_iki": None, "tekstas_lt": "1. Naujausia."}])
    t, info = source.suvestine_newer_today("X1", ended, day="2026-11-22")
    assert info["suvestines_id"] == "newest" and "Naujausia" in t
    assert (tmp_path / "suvestine" / "X1" / "newest.json").exists()


def test_a_later_consolidation_in_place_of_an_ended_text_may_have_fewer_points():
    import importlib.util as iu
    spec = iu.spec_from_file_location("nightly", pathlib.Path(__file__).parents[1] / "bin" / "nightly.py")
    nightly = iu.module_from_spec(spec)
    spec.loader.exec_module(nightly)
    prev = {"articles": 41, "version_from": "2004-12-15", "labels": [str(i) for i in range(1, 42)]}
    b = {"abbr": "HN41", "n": 15, "labels": [str(i) for i in range(1, 16)], "unit": "punktas", "rewrites": [],
         "consolidation_valid_from": "2016-06-01", "consolidation_valid_to": None}
    assert "lost" in nightly.check_act(b, prev, set())
    assert nightly.check_act({**b, "instead_of": "Dokumentas 2004-12-15 – 2016-05-31"}, prev, set()) is None


def test_an_act_repealed_on_a_known_day_is_labelled_repealed_not_uncertain():
    from ltlaw.currency import ActStatus, Status, apply_register_state
    st = ActStatus("2026-11-22", "current")
    st.articles = {"1": Status("current", []), "2": Status("current", [])}
    row = {"galioj_busena": "negalioja", "negalioja": "2026-04-28", "priemusi_inst": "Europos Sąjunga"}
    assert apply_register_state(st, row, "2026-11-22") == (False, True)
    assert {v.state for v in st.articles.values()} == {"repealed"} and st.expires == "2026-04-28"
    assert st.notices == ["Šis teisės aktas neteko galios 2026-04-28 (EUR-Lex)"]
    st2 = ActStatus("2026-11-22", "current")
    st2.articles = {"1": Status("current", [])}
    apply_register_state(st2, {"galioj_busena": "negalioja", "negalioja": None}, "2026-11-22")  # no day: uncertain
    assert st2.articles["1"].state == "unknown"
