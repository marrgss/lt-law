"""Prediction ledger and back-test (TARGET T3, D-024): accuracy measured every night, without e-tar.

Every night we record, per article, the label we showed and a fingerprint of the text we showed, as date
ranges (an entry grows while nothing changes). When the Chancellery publishes a new consolidation of an
act whose period starts in the past, that text is the answer for those past days: we compare what we
said on each of them with what was in force.

- "current" while the official text that day differs (or the article wasn't in force): a silent error
  found after the fact, the thing this project must not do;
- a flag ("Gali būti pasenęs", "Neaišku, ar galioja", "Įsigalios") while the text we showed was in fact the
  official one: a false alarm.

Limits (docs/TARGET.md T3): only acts whose texts move forward are checked, the open data skip some
intermediate versions, and articles are matched by number.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib

from . import source
from .currency import _article_repealed
from .validate import article_text, norm

FLAGS = ("outdated", "unknown", "pending")


def fingerprint(article) -> str:
    return hashlib.sha1(norm(article_text(article)).encode()).hexdigest()[:12] if article is not None else ""


def _days(a: str, b: str):
    d, end = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    while d <= end:
        yield d.isoformat()
        d += dt.timedelta(days=1)


def _day_before(d: str) -> str:
    return (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()


class Ledger:
    def __init__(self, path: pathlib.Path | None = None):
        self.path = path or source.STATE / "ledger.json"
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.acts: dict = data.get("acts", {})          # abbr -> label -> [[from, to, state, fingerprint], ...]
        self.checked: dict = data.get("checked", {})    # abbr -> versions already back-tested
        self.totals: dict = data.get("totals", {"article_days": 0, "silent": 0, "false_alarms": 0, "since": None})
        self.findings: list = data.get("findings", [])  # the silent errors found (newest last, capped)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"acts": self.acts, "checked": self.checked, "totals": self.totals,
                                         "findings": self.findings[-200:]}, ensure_ascii=False, separators=(",", ":")))

    def record(self, day: str, abbr: str, label: str, state: str, fp: str) -> None:
        rows = self.acts.setdefault(abbr, {}).setdefault(label, [])
        if rows and rows[-1][2] == state and rows[-1][3] == fp and rows[-1][1] in (day, _day_before(day)):
            rows[-1][1] = day
        elif not (rows and rows[-1][0] == day):
            rows.append([day, day, state, fp])
        else:
            rows[-1] = [day, day, state, fp]  # rebuilt the same day: the last build counts
        self.totals["since"] = self.totals.get("since") or day

    def backtest(self, abbr: str, act, today: str) -> dict:
        """Compare our past labels with a newly published consolidation `act` for the days it covers."""
        V, T = act.version_from, act.version_to
        key = f"{V}..{T or ''}"
        out = {"article_days": 0, "silent": 0, "false_alarms": 0}
        if not V or V >= today or key in self.checked.get(abbr, []) or abbr not in self.acts:
            return out
        truth = {a.label: a for a in act.main.articles}
        last = min(_day_before(today), T) if T else _day_before(today)
        for label, rows in self.acts[abbr].items():
            art = truth.get(label)
            for a, b, state, fp in rows:
                lo, hi = max(a, V), min(b, last)
                if lo > hi:
                    continue
                for d in _days(lo, hi):
                    shown = art.variant_on(d) if art is not None else None
                    gone = shown is None or _article_repealed(shown)[0]
                    ok_text = not gone and fingerprint(shown) == fp
                    out["article_days"] += 1
                    if state == "current" and not ok_text:
                        out["silent"] += 1
                        self.findings.append({"act": abbr, "article": label, "day": d, "version": key,
                                              "said": state, "official": "not in force" if gone else "different text"})
                    elif state == "repealed" and not gone:
                        out["silent"] += 1
                        self.findings.append({"act": abbr, "article": label, "day": d, "version": key,
                                              "said": state, "official": "in force"})
                    elif state in FLAGS and ok_text:
                        out["false_alarms"] += 1
        self.checked.setdefault(abbr, []).append(key)
        for k in out:
            self.totals[k] = self.totals.get(k, 0) + out[k]
        return out
