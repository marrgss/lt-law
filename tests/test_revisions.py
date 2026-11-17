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
