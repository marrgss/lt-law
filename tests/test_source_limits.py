"""The nightly's limits on a source that doesn't answer (source.limit_run; 2026-11-04: two runs cancelled at 90 minutes)."""
import io
import json
import urllib.error

import pytest

from ltlaw import source


@pytest.fixture
def clean(monkeypatch):
    monkeypatch.setattr(source, "DOWN", False)
    monkeypatch.setattr(source, "DEADLINE", None)
    monkeypatch.setattr(source, "_no_answer", [0])
    monkeypatch.setattr(source, "_limited", [False])
    monkeypatch.setattr(source.time, "sleep", lambda s: None)


def answers(monkeypatch, *script):
    """urlopen that plays `script`: an exception to raise, or a dict to return. Returns the list of calls made."""
    calls = []

    def fake(req, timeout=None):
        x = script[min(len(calls), len(script) - 1)]
        calls.append(req.full_url)
        if isinstance(x, Exception):
            raise x
        return io.BytesIO(json.dumps(x).encode())
    monkeypatch.setattr(source.urllib.request, "urlopen", fake)
    return calls


def test_no_answer_stops_the_run_at_the_limit(clean, monkeypatch):
    calls = answers(monkeypatch, TimeoutError("timed out"))
    source.limit_run(3600)
    with pytest.raises(TimeoutError):
        source._get("http://x/a", tries=4)  # 4 attempts
    with pytest.raises(TimeoutError):
        source._get("http://x/b", tries=4)  # the 5th: down
    assert len(calls) == source.DOWN_AFTER and source.DOWN
    with pytest.raises(TimeoutError, match="skipped for this run"):  # nothing more is asked
        source._get("http://x/c", tries=4)
    assert len(calls) == source.DOWN_AFTER


def test_an_answer_resets_the_count(clean, monkeypatch):
    calls = answers(monkeypatch, TimeoutError(), TimeoutError(), TimeoutError(), {"_data": []}, TimeoutError(), TimeoutError(),
                    TimeoutError(), {"_data": []})
    source.limit_run(3600)
    assert source._get("http://x/a", tries=4) == {"_data": []}
    assert source._get("http://x/b", tries=4) == {"_data": []}
    assert not source.DOWN and len(calls) == 8


def test_a_500_is_an_answer_a_gateway_error_is_not(clean, monkeypatch):
    err = lambda code: urllib.error.HTTPError("http://x", code, "e", {}, None)  # noqa: E731
    answers(monkeypatch, err(500))
    source.limit_run(3600)
    for _ in range(3):
        with pytest.raises(urllib.error.HTTPError):
            source._get("http://x/a", tries=4)
    assert not source.DOWN
    answers(monkeypatch, err(524))
    with pytest.raises(urllib.error.HTTPError):
        source._get("http://x/b", tries=5)
    assert source.DOWN


def test_the_budget_ends_fetching(clean, monkeypatch):
    calls = answers(monkeypatch, {"_data": []})
    source.limit_run(-1)
    with pytest.raises(TimeoutError, match="budget"):
        source._get("http://x/a")
    assert calls == []


def test_tools_run_by_hand_are_not_limited(clean, monkeypatch):
    calls = answers(monkeypatch, TimeoutError())
    for _ in range(3):
        with pytest.raises(TimeoutError):
            source._get("http://x/a", tries=4)
    assert len(calls) == 12 and not source.DOWN
