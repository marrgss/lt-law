"""e-tar.lt access for VALIDATION ONLY (D-004): hand-picked acts, a few requests each.

e-tar is the answer key: its HTML keeps <sup> markup and it lists every consolidated version
with its id. We use it to check that our parse of the open-data text is right, never as a
publishing source.
"""
from __future__ import annotations

import http.cookiejar
import json
import pathlib
import re
import time
import urllib.error
import urllib.request

ETAR = "https://www.e-tar.lt"
UA = "Mozilla/5.0 (lt-law validation; hand-picked acts only)"
ROOT = pathlib.Path("data/etar")
PAUSE = 3.0

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with _opener.open(req, timeout=300) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(PAUSE)
    return body


def versions(doc: str) -> list[dict]:
    """All consolidated versions of an act, newest first: [{id, valid_from, valid_to}].

    The editions page needs the JSF session cookie set by the act page, hence the order.
    Cached in <ROOT>/<doc>/versions.json.
    """
    cache = ROOT / doc / "versions.json"
    # the list grows as the Chancellery prepares versions: older than 3 days, ask again (it was cached for good, so new
    # versions went unseen: CK's 2027-01-01 slice, 2026-10-28, B62); if e-tar can't be reached, the cached list
    if cache.exists() and time.time() - cache.stat().st_mtime < 3 * 86400 and json.loads(cache.read_text()):
        return json.loads(cache.read_text())  # an empty list is asked again (old version ids were missed: B66)
    try:
        page = _editions_page(doc)
    except Exception:
        if cache.exists():
            return json.loads(cache.read_text())
        raise
    out = editions(doc, page)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def _editions_page(doc: str) -> str:
    _get(f"{ETAR}/portal/lt/legalAct/{doc}/asr")
    page = _get(f"{ETAR}/portal/lt/legalActEditions/{doc}")
    flag = ROOT / doc / "never_consolidated.json"
    flag.parent.mkdir(parents=True, exist_ok=True)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", " ", page, flags=re.S)))
    flag.write_text(json.dumps(bool(re.search(r"Suvestinių redakcijų sąrašas pagal datą: Nėra", text))
                               and not editions(doc, page)))
    return page


def never_consolidated(doc: str) -> bool:
    """True when e-tar's act page says outright that the act has no consolidated version ("Suvestinių redakcijų sąrašas
    pagal datą: Nėra"), not merely that none was read: with the open data's "never amended" (pakeista empty), the
    original is the text in force (EOSPPSAA, ŠESĮT: Suvestine still serves the original as a "consolidation" from the
    day it took effect, so our text has a version date e-tar has no version for; B83)."""
    flag = ROOT / doc / "never_consolidated.json"
    if not flag.exists() or time.time() - flag.stat().st_mtime >= 3 * 86400:
        _editions_page(doc)
    return json.loads(flag.read_text())


def original_in_force(doc: str, version_from: str | None, row: dict) -> bool:
    """In force and never amended, by both sources: e-tar lists no consolidated version, the open data has no amendment
    date, and our text is the original (no version date, or the date it took effect)."""
    return (row.get("galioj_busena") == "galioja" and not row.get("pakeista")
            and version_from in (None, (row.get("isigalioja") or "")[:10]) and never_consolidated(doc))


def editions(doc: str, page: str) -> list[dict]:
    """The consolidated versions listed on an act's editions page: [{id, valid_from, valid_to}]."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        # ids: "zqElJTQeVq"; versions from before e-tar keep their old ones, "TAIS_82194" (VHĮ 1999-05-20, B66)
        m = re.search(rf"legalAct/{re.escape(doc)}/([A-Za-z]{{10}}|TAIS_\d+)[^>]*>\s*Suvestinė nuo\s*([\d-]+)", row)
        if not m:
            continue
        cells = [re.sub(r"<[^>]+>", " ", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        to = re.search(r"\d{4}-\d{2}-\d{2}", cells[1]) if len(cells) > 1 else None  # cell 2 = "Data iki"
        out.append({"id": m.group(1), "valid_from": m.group(2), "valid_to": to.group(0) if to else None})
    return out


def version_html(doc: str, version_id: str) -> str:
    """HTML text of one consolidated version (cached)."""
    path = ROOT / doc / f"{version_id}.html"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_get(f"{ETAR}/rs/actualedition/{doc}/{version_id}/"))
    return path.read_text()


def version_html_or_none(doc: str, version_id: str) -> str | None:
    """As version_html, or None when e-tar has no HTML of the version (404: some acts' versions come only as DOCX, PDF
    and ODT files, the Gas regulated prices methodology's): nothing to compare with, the validators say so."""
    try:
        return version_html(doc, version_id)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def version_valid_on(doc: str, day: str) -> dict | None:
    for v in versions(doc):
        if v["valid_from"] <= day and (v["valid_to"] is None or day <= v["valid_to"]):
            return v
    return None


def version_from(doc: str, valid_from: str) -> dict | None:
    return next((v for v in versions(doc) if v["valid_from"] == valid_from), None)
