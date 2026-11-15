"""The prediction ledger (T3, D-024): past labels checked against a later official consolidation."""
from ltlaw.ledger import Ledger, fingerprint
from ltlaw.parse import parse

OLD = "Suvestinė redakcija nuo 2026-01-01\nĮSTATYMAS\n1 straipsnis. Pirmas\nSenas tekstas.\n2 straipsnis. Antras\nTas pats.\n"
NEW = "Suvestinė redakcija nuo 2026-10-02\nĮSTATYMAS\n1 straipsnis. Pirmas\nNaujas tekstas.\n2 straipsnis. Antras\nTas pats.\n"


def test_backtest_finds_silent_errors_and_false_alarms(tmp_path):
    led = Ledger(tmp_path / "ledger.json")
    old = {a.label: a for a in parse(OLD).main.articles}
    for d in ("2026-10-01", "2026-10-02", "2026-10-03"):
        led.record(d, "X", "1", "current", fingerprint(old["1"]))   # we kept saying the old text applies
        led.record(d, "X", "2", "unknown", fingerprint(old["2"]))   # we hesitated about an unchanged text
    assert led.acts["X"]["1"] == [["2026-10-01", "2026-10-03", "current", fingerprint(old["1"])]]
    r = led.backtest("X", parse(NEW), "2026-10-04")                 # the official text from 2026-10-02
    assert r == {"article_days": 4, "silent": 2, "false_alarms": 2}
    assert {f["day"] for f in led.findings} == {"2026-10-02", "2026-10-03"}
    assert led.backtest("X", parse(NEW), "2026-10-05")["article_days"] == 0  # each version is checked once
    led.save()
    assert Ledger(tmp_path / "ledger.json").totals["silent"] == 2


def test_a_future_version_checks_nothing(tmp_path):
    led = Ledger(tmp_path / "ledger.json")
    led.record("2026-10-01", "X", "1", "current", "abc")
    assert led.backtest("X", parse(NEW.replace("2026-10-02", "2027-01-01")), "2026-10-04")["article_days"] == 0
