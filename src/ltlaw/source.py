"""Read-only access to the TAR open data on data.gov.lt (Spinta API).

Everything we fetch is saved under data/ so builds and tests run offline, and so each
snapshot becomes part of our own version history (D-009).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import eurlex

# LTLAW_RELAY_URL / LTLAW_RELAY_KEY: fetch through the Cloudflare relay (worker/, D-019), set in CI only.
RELAY = os.environ.get("LTLAW_RELAY_URL", "").rstrip("/")
API = (RELAY or "https://get.data.gov.lt") + "/datasets/gov/lrsk/teises_aktai"
UA = "lt-law/0.1 (open civic project; read-only)"
DATA = pathlib.Path("data")
VALIDATION = pathlib.Path("validation")  # tracked: dated results of the e-tar checks (run locally, D-004)


# The nightly's limits on a source that doesn't answer (limit_run). 2026-11-04: data.gov.lt gave no answer at all; 3 forms
# of the first query × 4 tries × 2 minutes, then 34 revision batches × 2 × 1 minute, and both runs were cancelled at the
# job's 90 minutes before building anything: the site stayed on the day before. Tools run by hand wait outages out.
DOWN_AFTER = 5  # attempts in a row with no answer (a timeout, a gateway error): the source is down for this run
DOWN: str | bool = False  # the reason, for the night's warning
DEADLINE: float | None = None  # time.time() after which nothing more is fetched
_no_answer = [0]
_limited = [False]


def limit_run(budget_s: int) -> None:
    """From now on this process stops asking after DOWN_AFTER attempts in a row with no answer, or after budget_s."""
    global DEADLINE
    DEADLINE, _limited[0] = time.time() + budget_s, True


def _no_answer_seen(e: Exception) -> None:
    global DOWN
    if isinstance(e, urllib.error.HTTPError) and e.code not in (502, 503, 504, 520, 521, 522, 523, 524):
        return  # it answered (a 500 for one query form, a 429): the deadline bounds those
    _no_answer[0] += 1
    if _limited[0] and _no_answer[0] >= DOWN_AFTER:
        DOWN = f"{_no_answer[0]} attempts in a row without an answer, the last {type(e).__name__}"


def _get(url: str, tries: int = 4, timeout: int = 120) -> dict:
    for i in range(tries):
        if DOWN:
            raise TimeoutError(f"data.gov.lt skipped for this run: {DOWN}")
        if DEADLINE and time.time() > DEADLINE:
            raise TimeoutError("data.gov.lt skipped for this run: the fetching budget is spent")
        try:
            headers = {"User-Agent": UA}
            if RELAY:
                headers["x-relay-key"] = os.environ.get("LTLAW_RELAY_KEY", "")
            req = urllib.request.Request(url, headers=headers)
            # 2 minutes: a stalled source must fail within minutes, not eat the run's 90 (2026-10-21: cancelled)
            t = time.time()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
            finally:
                NET[0] += time.time() - t
                NET[1] += 1
            NET[2] += len(raw)
            data = json.loads(raw)
            _no_answer[0] = 0
            return data
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            _no_answer_seen(e)
            if i == tries - 1 or DOWN:
                raise
            time.sleep(15 * (i + 1))
    raise AssertionError("unreachable")


def query(model: str, q: str, tries: int = 4, timeout: int = 120) -> list[dict]:
    """Run one Spinta query; `q` is the raw query string, e.g. 'select(a,b)&x="1"&limit(5)'.

    Suvestine (the consolidations table) can be extremely slow for hours (2026-10-24: over 10 minutes a query): its
    queries get one try of 60 s, and after a timeout every later Suvestine query of this run fails at once
    (SUVESTINE_DOWN), so the night goes on with the cached texts instead of waiting out its 90 minutes.
    A quick server error (5xx) is not a stalled table: the query is asked again twice, seconds apart, and only
    SUVESTINE_5XX_LIMIT queries failing that way end Suvestine for the night (2026-11-18 and -20: one 500 among the
    version lists cost every Suvestine text of the night; the same queries answer in 0.1 s by day)."""
    global SUVESTINE_DOWN
    url = f"{API}/{model}?" + urllib.parse.quote(q + FRESH, safe='()&=,"_-<>!/')
    if model != "Suvestine":
        return _get(url, tries=tries, timeout=timeout).get("_data", [])
    for attempt in range(3):
        if SUVESTINE_DOWN:
            raise TimeoutError(f"Suvestine skipped for this run (failed earlier: {SUVESTINE_DOWN})")
        try:
            return _get(url, tries=1, timeout=60).get("_data", [])
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited, for minutes after big downloads (2026-11-02): not down, the caller may wait
                RATE_LIMITED[0] += 1
                raise
            if 500 <= e.code < 600:
                if attempt < 2:
                    time.sleep(SUVESTINE_RETRY_S * (attempt + 1))
                    continue
                SUVESTINE_5XX[0] += 1
                if SUVESTINE_5XX[0] < SUVESTINE_5XX_LIMIT:
                    raise  # this query failed; the table is not given up on yet
            SUVESTINE_DOWN = f"HTTP {e.code}"
            raise
        except Exception as e:
            doc = re.search(r'dokumento_id="([^"]+)"', q)  # the reason, for the night's warning
            SUVESTINE_DOWN = type(e).__name__ + (f" asking for {doc[1]}" if doc else "")
            raise
    raise AssertionError("unreachable")


# data.gov.lt's nginx caches a query's answer by its URL and, after 60 s, serves the old answer (X-Cache: STALE) to the
# first request while it refreshes: the same query every night got the previous night's answer (2026-10-31: newest
# publication 10-26 again, though 10-27..10-29 were in; SŽNSĮ XV-1230 missed). A filter no row matches, new each run,
# makes the night's URLs its own; the run's own repeats still share the cache.
FRESH = f'&_id!="{uuid.uuid4()}"'
SUVESTINE_DOWN: str | bool = False  # set by query() after a Suvestine failure (its reason): the rest of the run skips Suvestine
SUVESTINE_5XX = [0]  # Suvestine queries that failed with a server error after their retries, this run
SUVESTINE_5XX_LIMIT = 3
SUVESTINE_RETRY_S = 5
SUVESTINE_429_WAIT_S = 60  # the version lists wait out a 429 this long, at most SUVESTINE_429_WAITS times a run
SUVESTINE_429_WAITS = 3
NET = [0.0, 0, 0]  # this run's data.gov.lt requests: seconds waited, requests, bytes (a slow act's tick says how much was network)
RATE_LIMITED = [0]  # Suvestine answers HTTP 429 (Too Many Requests) tonight


def fetch_dokumentas(dokumento_id: str, tries: int = 4, timeout: int = 120) -> dict:
    rows = query("Dokumentas", f'dokumento_id="{dokumento_id}"&limit(2)', tries=tries, timeout=timeout)
    if len(rows) != 1:
        raise LookupError(f"{dokumento_id}: expected 1 Dokumentas row, got {len(rows)}")
    return rows[0]


def revisions(dokumento_ids: list[str], batch: int = 25) -> dict[str, str]:
    """Dokumentas rows' `_revision` (it changes with any change to the row), 25 acts a query: a second for the whole
    scope instead of every act's text (85 KB to megabytes each). Best effort: an act missing here is fetched in full."""
    out: dict[str, str] = {}
    for k in range(0, len(dokumento_ids), batch):
        ids = dokumento_ids[k:k + batch]
        try:
            rows = query("Dokumentas", "select(dokumento_id,_revision)&or(%s)&limit(%d)"
                         % (",".join(f'dokumento_id="{i}"' for i in ids), 2 * len(ids)), tries=2, timeout=60)
        except Exception:
            continue
        seen: dict[str, list[str]] = {}
        for r in rows:
            seen.setdefault(r.get("dokumento_id"), []).append(r.get("_revision"))
        out.update({i: v[0] for i, v in seen.items() if i in ids and len(v) == 1 and v[0]})
    return out


FULL_EVERY_DAYS = 60  # the ceiling: an older full fetch is repeated whatever the revision (the nightly's backstop, D-056,
#                       re-fetches the longest unfetched texts a few minutes a night, so this is rarely reached)
REVISION_SKIPS = 0  # texts not fetched this run: their revision unchanged (nightly log)


def revision_unchanged(dokumento_id: str, revision: str | None, root: pathlib.Path = DATA / "dokumentas") -> bool:
    """Whether `revision` (from revisions()) is the one this act's last full fetch saw, that fetch within
    FULL_EVERY_DAYS: the text we hold is the source's, no fetch needed. Never for EU acts (EUR-Lex has no revisions)."""
    rev_file = root / dokumento_id / "revision.txt"  # "<_revision> <time of the full fetch that saw it>"
    if not revision or not rev_file.exists() or eurlex.is_eu(dokumento_id):
        return False
    seen, _, when = rev_file.read_text().strip().partition(" ")
    try:
        fresh = (dt.datetime.now().astimezone() - dt.datetime.fromisoformat(when)).days < FULL_EVERY_DAYS
    except ValueError:
        fresh = False
    return seen == revision and fresh and bool(snapshots(dokumento_id, root))


def seen_revision(dokumento_id: str, root: pathlib.Path = DATA / "dokumentas") -> str:
    """The `_revision` this act's last full fetch saw ("" if none is kept)."""
    p = root / dokumento_id / "revision.txt"
    return p.read_text().strip().partition(" ")[0] if p.exists() else ""


def full_fetched(dokumento_id: str, root: pathlib.Path = DATA / "dokumentas") -> str:
    """When this act's text was last fetched in full ("" if never, or before revisions were kept)."""
    p = root / dokumento_id / "revision.txt"
    return p.read_text().strip().partition(" ")[2] if p.exists() else ""


def snapshot(dokumento_id: str, root: pathlib.Path = DATA / "dokumentas", day: str | None = None,
             revision: str | None = None, full: bool = False) -> pathlib.Path:
    """Save today's Dokumentas row as <root>/<id>/<YYYY-MM-DD>.json (idempotent per day).

    With `revision` (from revisions()): when it is the one the last full fetch saw, within FULL_EVERY_DAYS, the text is
    not fetched again; the act counts as checked (checked.txt), as an unchanged full fetch would. `full` fetches the
    text whatever was checked today or by revision (the nightly's backstop, D-056)."""
    day = day or dt.date.today().isoformat()
    out = root / dokumento_id / f"{day}.json"
    if out.exists():
        return out
    # checked earlier today and unchanged (no day file): a second run the same day doesn't fetch it again (2026-11-02:
    # a manual re-run spent its 20 minutes on 429s re-fetching unchanged texts)
    chk = root / dokumento_id / "checked.txt"
    if not full and day != "fixed" and chk.exists() and chk.read_text()[:10] == day and (prev := snapshots(dokumento_id, root)):
        return prev[-1]
    if not full and revision_unchanged(dokumento_id, revision, root):
        global REVISION_SKIPS
        REVISION_SKIPS += 1
        (root / dokumento_id / "checked.txt").write_text(dt.datetime.now().astimezone().isoformat(timespec="seconds"))
        return snapshots(dokumento_id, root)[-1]
    if eurlex.is_eu(dokumento_id):
        prev = sorted(out.parent.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))
        row = eu_row(dokumento_id, day, json.loads(prev[-1].read_text())["row"] if prev else None)
    else:
        row = fetch_dokumentas(dokumento_id)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    out.parent.mkdir(parents=True, exist_ok=True)
    prev = sorted(out.parent.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))
    if day != "fixed" and prev:
        last = json.loads(prev[-1].read_text())
        if all(last["row"].get(k) == row.get(k) for k in ("tekstas_lt", "galioj_busena", "eu_converter")):
            (out.parent / "checked.txt").write_text(now)  # unchanged: keep the archive small, remember the check
            if row.get("_revision"):
                (out.parent / "revision.txt").write_text(f"{row['_revision']} {now}")
            return prev[-1]
    out.write_text(json.dumps({"fetched": now, "row": row}, ensure_ascii=False))
    (out.parent / "checked.txt").write_text(now)
    if row.get("_revision"):
        (out.parent / "revision.txt").write_text(f"{row['_revision']} {now}")
    return out


EU_BATCH: dict[str, dict] = {"versions": {}, "metadata": {}}  # this run's answers for many acts at once (D-056)


def prefetch_eu(dokumento_ids: list[str]) -> int:
    """Ask EUR-Lex for every EU act's version list and metadata in a few queries (seconds for 170 acts; one act at a
    time took 6–15 s each, most of the night's text budget). eu_row uses them; an act missing here is asked for alone,
    as before. Returns how many acts got both answers."""
    celexes = [eurlex.celex_of(i) for i in dokumento_ids if eurlex.is_eu(i)]
    if not celexes:
        return 0
    EU_BATCH["versions"], EU_BATCH["metadata"] = eurlex.versions_of(celexes), eurlex.metadata_of(celexes)
    return sum(c in EU_BATCH["versions"] and c in EU_BATCH["metadata"] for c in celexes)


def eu_row(dokumento_id: str, day: str, prev: dict | None = None) -> dict:
    """An EU act (D-037) as a Dokumentas-like row: the newest consolidated version applying on `day`, else the act as
    published; its text in the register's layout, checked word for word against the XHTML (an article lost or changed
    in the conversion stops it here: the act keeps its previous text)."""
    celex = eurlex.celex_of(dokumento_id)
    meta = EU_BATCH["metadata"].get(celex) or eurlex.metadata(celex)
    listed = EU_BATCH["versions"].get(celex)
    # not in the batch's answer, or a version we held is missing from it (a version list only grows): the slow query,
    # which reads every CELEX number, decides. Never an older wording as today's because one query's link was incomplete
    if listed is None or (prev and not set(prev.get("eu_versions") or []) <= set(listed)):
        listed = eurlex.versions(celex)
    vs = [v for v in listed if v.rsplit("-", 1)[1] <= day.replace("-", "")]
    # the same version as last time, converted the same way: its text is kept (EUR-Lex is asked for the version list
    # and metadata only)
    if prev and prev.get("eu_versions") == vs and prev.get("tekstas_lt") and prev.get("eu_converter") == eurlex.CONVERTER:
        return dict(prev, galioj_busena="galioja" if meta["in_force"] else "negalioja", negalioja=meta["end_of_validity"])
    # the newest consolidation with a Lithuanian text (the register lists some it has none for: NIS2's), else the original
    xhtml = src = None
    for cand in [*reversed(vs), celex]:
        try:
            xhtml, src = eurlex.fetch_xhtml(cand), cand
            break
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    legacy = None
    if xhtml is None:  # adopted before 2004: the Special Edition's text in the older HTML, the act as adopted
        if vs and vs[-1].rsplit("-", 1)[1] > (meta["entry_into_force"] or meta["date"] or "").replace("-", ""):
            raise LookupError(f"{celex}: no Lithuanian text of its newest consolidation {vs[-1]}")  # never an older wording as today's
        src = celex
        legacy = eurlex.fetch_legacy(celex)
    d = src.rsplit("-", 1)[1] if src != celex else (meta["entry_into_force"] or meta["date"] or day).replace("-", "")
    vfrom = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    text, info = eurlex.legacy_to_text(legacy, vfrom, celex) if legacy else eurlex.to_text(xhtml, vfrom)
    if problems := eurlex.check_legacy(legacy, text, celex) if legacy else eurlex.check(xhtml, text):
        raise ValueError(f"{src}: the conversion lost words: {problems[:5]}")
    kind = {"R": "Reglamentas", "L": "Direktyva", "D": "Sprendimas"}.get(celex[5], "ES teisės aktas")
    return {"dokumento_id": dokumento_id, "tar_kodas": celex, "pavadinimas": meta["title"] or info["title"], "rusis": kind,
            "galioj_busena": "galioja" if meta["in_force"] else "negalioja", "priimtas": meta["date"],
            "isigalioja": meta["entry_into_force"], "negalioja": meta["end_of_validity"], "priemusi_inst": "Europos Sąjunga",
            "eu_version": src if src != celex else None, "eu_versions": vs, "eu_converter": eurlex.CONVERTER,
            "tekstas_lt": text, "eu_images": info["images"]}  # "[paveikslas N]" -> a data: URI (formulas, figures)


def first_seen(dokumento_id: str, version_from: str | None, root: pathlib.Path = DATA / "dokumentas") -> str | None:
    """The day we first archived the version starting `version_from` (laws published well before
    that are in it or flagged; anchoring on this day keeps labels from drifting as days pass)."""
    if not version_from:
        return None
    for p in snapshots(dokumento_id, root):
        t = (json.loads(p.read_text())["row"].get("tekstas_lt") or "")[:3000]
        if f"Suvestinė redakcija nuo {version_from}" in t:
            return p.stem
    snaps = snapshots(dokumento_id, root)  # e.g. Suvestine-origin texts: the day we started watching the act
    return snaps[0].stem if snaps else None


REFRESH_SUVESTINE = False  # bin/nightly.py turns this on when it fetches
SUVESTINE_FAILED: list[str] = []  # refresh problems (nightly health)
PINNED: dict[str, pathlib.Path] = {}  # dokumento_id -> snapshot to use instead of the newest (nightly fallback)


def snapshots(dokumento_id: str, root: pathlib.Path = DATA / "dokumentas") -> list[pathlib.Path]:
    return sorted((root / dokumento_id).glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))  # daily snapshots only


def last_checked(dokumento_id: str, root: pathlib.Path = DATA / "dokumentas") -> str:
    """When this act's text was last fetched ("" if never): the newest snapshot's day or checked.txt's time."""
    files, ck = snapshots(dokumento_id, root), root / dokumento_id / "checked.txt"
    return max(files[-1].stem if files else "", ck.read_text().strip() if ck.exists() else "")


def awaiting_consolidation(scope: list[dict], day: str, window_days: int = 60) -> set[str]:
    """Acts (dokumento_id) that a law, resolution or order put in force in the last `window_days` days changes, while
    their stored text starts before it: their new consolidation is due, so the nightly fetches them first (the
    20-minute budget refreshes ~40 acts a night when data.gov.lt is slow; oldest first alone could leave a just-amended
    act for nine days). Matched by the act's number in the amender's title; the rules by date and number."""
    path = STATE / "laws.jsonl"
    if not path.exists():
        return set()
    lo = (dt.date.fromisoformat(day) - dt.timedelta(days=window_days)).isoformat()
    recent = [r for r in map(json.loads, path.open()) if lo <= (r.get("isigalioja") or "") <= day]
    out = set()
    for a in scope:
        n, adopted = a.get("number"), a.get("adopted")
        if not n or not snapshots(a["dokumento_id"]):
            continue
        if (n, adopted) in POINT_ACTS:
            hit = [r for r in recent if names_points_act(r.get("pavadinimas"), n, adopted)]
        else:
            pat = re.compile(r"Nr\. ?" + re.escape(n) + r"(?![\w-])")
            hit = [r for r in recent if r.get("atv_dok_nr") != n and pat.search(r.get("pavadinimas") or "")]
        if not hit:
            continue
        head = (latest_snapshot(a["dokumento_id"])["row"].get("tekstas_lt") or "")[:300]
        m = re.search(r"Suvestinė redakcija nuo (\d{4}-\d{2}-\d{2})", head)
        if not m or m.group(1) < max(r["isigalioja"] for r in hit):
            out.add(a["dokumento_id"])
    return out


def latest_snapshot(dokumento_id: str, root: pathlib.Path = DATA / "dokumentas") -> dict:
    if dokumento_id in PINNED and root == DATA / "dokumentas":
        return json.loads(PINNED[dokumento_id].read_text())
    files = snapshots(dokumento_id, root)
    if not files:
        raise FileNotFoundError(f"no snapshot for {dokumento_id}; run bin/snapshot_scope.py")
    return json.loads(files[-1].read_text())


STATE = DATA / "state"
UPDATE_LOG: list[str] = []  # which query form worked (nightly status)
COVERAGE: dict = {}         # did the law update reach back to what we had (nightly status)
LAW_TYPES = ("Įstatymas", "Kodeksas", "Konstitucinis įstatymas", "Statutas")  # Statutas: the Seimas Statute and its amendments
# points acts in scope (Government resolutions approving rules, KET): (number, adoption date). Resolutions
# amending them are kept in laws.jsonl too, keyed by number/date (resolution numbers repeat every year)
POINT_ACTS: list[tuple[str, str]] = []
# points acts' document types and how titles cite them ("… 2010 m. vasario 11 d. įsakymo Nr. 1-38 …"): Government
# resolutions and ministers' orders (D-033); POINT_KIND: (number, adoption date) -> type
POINT_TYPES = {"Nutarimas": "nutarimo", "Įsakymas": "įsakymo"}
POINT_KIND: dict[tuple[str, str], str] = {}
_GEN_MONTHS = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", "liepos", "rugpjūčio", "rugsėjo",
               "spalio", "lapkričio", "gruodžio"]


def use_scope(acts: list[dict]) -> None:
    # acts approved by a resolution or an order (`adopted`): made of points, or of articles (unit: straipsnis, the TSO
    # methodologies VERT approves, PORFPSDR); either way amended by resolutions or orders cited by date and number
    POINT_ACTS[:] = [(a["number"], a["adopted"]) for a in acts if a.get("adopted")]
    POINT_KIND.clear()
    POINT_KIND.update({(a["number"], a["adopted"]): a.get("kind", "Nutarimas") for a in acts if a.get("adopted")})


def act_path(scope_act: dict, tar: str) -> str:
    """Where an act's pages live: "ta/<TAR>/", or "ta/<TAR>/<document>/" for one of several documents approved by the
    same resolution (scope `document:` + `docslug:`, D-027). A slash in an old TAR code ("110203NISAK14/3-742", the
    joint fuel-quality order) becomes "-": one path segment per act. An EU act: "es/<CELEX>/" (D-037)."""
    if eurlex.is_eu(scope_act.get("dokumento_id") or ""):
        return f"es/{tar}/"
    return f"ta/{tar.replace('/', '-')}/" + (f"{scope_act['docslug']}/" if scope_act.get("docslug") else "")


def lt_date(iso: str) -> str:
    """'2002-12-11' -> '2002 m. gruodžio 11 d.' (as act titles cite each other)."""
    y, m, d = iso.split("-")
    return f"{y} m. {_GEN_MONTHS[int(m) - 1]} {int(d)} d."


def names_points_act(title: str, number: str, adopted: str, kind: str | None = None) -> bool:
    """"Dėl Lietuvos Respublikos Vyriausybės 2002 m. gruodžio 11 d. nutarimo Nr. 1950 „…“ pakeitimo"; an order:
    "Dėl Lietuvos Respublikos energetikos ministro 2010 m. vasario 11 d. įsakymo Nr. 1-38 „…“ pakeitimo"."""
    gen = POINT_TYPES[kind or POINT_KIND.get((number, adopted), "Nutarimas")]
    t = " ".join((title or "").lower().split()) + " "
    return any(f"{lt_date(adopted)} {gen} nr. {n.lower()} " in t for n in number_forms(number))


def number_forms(number: str) -> list[str]:
    """The forms other acts cite a number in. VERT's resolutions are "O3E-296" (energy) or "O3-…", and its amending
    resolutions cite either for the same one: O3-1235 of 2026-09-18 amends "nutarimo Nr. O3-296" of 2019-08-02, which
    is O3E-296 (VSIA; B84). The date must match too, so the two never meet another resolution."""
    m = re.fullmatch(r"O3E?-(\d+)", number or "")
    return [f"O3E-{m.group(1)}", f"O3-{m.group(1)}"] if m else [number]


def is_ruling(r: dict) -> bool:
    """A Constitutional Court ruling ("KT44-A-N4/2026": its numbers are unique), ACCURACY B3."""
    return r.get("rusis") == "Nutarimas" and (r.get("atv_dok_nr") or "").startswith("KT")


def keep_meta(r: dict) -> bool:
    if r.get("rusis") in LAW_TYPES:
        return bool(r.get("atv_dok_nr"))
    if is_ruling(r):
        return True
    return r.get("rusis") in POINT_TYPES and bool(r.get("atv_dok_nr")) and \
        any(names_points_act(r.get("pavadinimas"), n, a) for n, a in POINT_ACTS)


AMENDER_SEARCH_SINCE = "2026-11-02"  # searched before: by the exact cited form, missing titles with non-breaking spaces
AMENDER_SEARCH_SINCE_VERT = "2026-11-12"  # VERT's searched before by one number form only (B84)


def update_point_amenders(refresh_days: int = 7, budget_s: int = 600) -> int:
    """Resolutions and orders amending each points act in scope (KET), by a title search: one request per act. The
    newest-n window of update_recent_laws brings new ones every night, but not the older ones, which a new act needs.
    A title search is slow on data.gov.lt (51 acts took 45 minutes on 2026-10-28), so: acts never searched first, then
    each act again about once a week, within `budget_s`; the rest next night. Returns rows added."""
    path = STATE / "laws.jsonl"
    have = {json.loads(l)["dokumento_id"] for l in path.open()} if path.exists() else set()
    seen_path = STATE / "point_amenders_checked.json"
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}
    today = dt.date.today()
    due = [(n, a) for n, a in POINT_ACTS
           if seen.get(f"{n}/{a}", "") < (AMENDER_SEARCH_SINCE_VERT if number_forms(n) != [n] else AMENDER_SEARCH_SINCE) or (today - dt.date.fromisoformat(seen[f"{n}/{a}"])).days >= refresh_days]
    due.sort(key=lambda x: seen.get(f"{x[0]}/{x[1]}", ""))
    added, t0 = [], time.time()
    for number, adopted in due:
        if time.time() - t0 > budget_s:
            break
        kind = POINT_KIND.get((number, adopted), "Nutarimas")
        # the number, month and year (no spaces: titles have non-breaking ones, "22\xa0d.", NPKR's amenders missed);
        # then the cited form ("2001 m. sausio 25 d. nutarimo Nr. 86 ") by keep_meta, whitespace-normalised
        y, m, _ = adopted.split("-")
        # VERT's numbers: by the digits, as amenders cite "O3E-296" as "O3-296" too (number_forms)
        key = number if number_forms(number) == [number] else f"-{number.split('-')[1]}"
        try:
            rows = query("Dokumentas", f'select(_id,{META_FIELDS})&pavadinimas.contains("{key}")'
                                       f'&pavadinimas.contains("{_GEN_MONTHS[int(m) - 1]}")&pavadinimas.contains("{y}")'
                                       f'&rusis="{kind}"&limit(2000)', tries=2, timeout=90)
        except Exception:  # noqa: BLE001  next night
            continue
        added += [r for r in rows if keep_meta(r) and r["dokumento_id"] not in have]
        seen[f"{number}/{adopted}"] = today.isoformat()
    STATE.mkdir(parents=True, exist_ok=True)
    seen_path.write_text(json.dumps(seen, indent=0, sort_keys=True))
    if added:
        with path.open("a") as f:
            for r in {r["dokumento_id"]: r for r in added}.values():
                f.write(json.dumps({k: r.get(k) for k in META_FIELDS.split(",")}, ensure_ascii=False) + "\n")
    return len({r["dokumento_id"] for r in added})


def update_missing_types() -> int:
    """A law type newly kept in laws.jsonl (e.g. "Statutas", 2026-10-20) has its older rows backfilled once: the
    newest-n window of update_recent_laws only brings new ones. One request per missing type; nothing when present."""
    path = STATE / "laws.jsonl"
    rows = [json.loads(l) for l in path.open()] if path.exists() else []
    have_types = {r.get("rusis") for r in rows}
    have = {r["dokumento_id"] for r in rows}
    added = []
    for t in LAW_TYPES:
        if t in have_types:
            continue
        got = query("Dokumentas", f'select(_id,{META_FIELDS})&rusis="{t}"&limit(5000)')
        added += [r for r in got if keep_meta(r) and r["dokumento_id"] not in have]
    if added:
        with path.open("a") as f:
            for r in {r["dokumento_id"]: r for r in added}.values():
                f.write(json.dumps({k: r.get(k) for k in META_FIELDS.split(",")}, ensure_ascii=False) + "\n")
    return len(added)


def update_rulings() -> int:
    """Constitutional Court rulings, backfilled once (kept since 2026-10-21; new ones come with update_recent_laws).
    One request; nothing when laws.jsonl already holds some."""
    path = STATE / "laws.jsonl"
    rows = [json.loads(l) for l in path.open()] if path.exists() else []
    if any(is_ruling(r) for r in rows):
        return 0
    have = {r["dokumento_id"] for r in rows}
    got = query("Dokumentas", f'select(_id,{META_FIELDS})&rusis="Nutarimas"&atv_dok_nr.startswith("KT")&limit(2000)')
    added = {r["dokumento_id"]: r for r in got if is_ruling(r) and r["dokumento_id"] not in have}
    if added:
        with path.open("a") as f:
            for r in added.values():
                f.write(json.dumps({k: r.get(k) for k in META_FIELDS.split(",")}, ensure_ascii=False) + "\n")
    return len(added)


def dedupe_versions(rows: list[dict], prefer: str) -> list[dict]:
    """One row per validity range. The Chancellery re-prepares old consolidations now and then (EEĮ's 2023 versions
    again on 2026-07-02; B51): the same range twice, texts that can differ. `prefer`: "earliest" (what was available
    at the time: the back-test) or "latest" (its current view: today's text, dated answers)."""
    best: dict = {}
    for r in rows:
        k = ((r.get("galioja_nuo") or "")[:10], (r.get("galioja_iki") or "")[:10])
        prep = r.get("suv_duom_atnaujinimas") or ""
        if k not in best or (prep < (best[k].get("suv_duom_atnaujinimas") or "") if prefer == "earliest"
                             else prep > (best[k].get("suv_duom_atnaujinimas") or "")):
            best[k] = r
    return list(best.values())


def update_suvestine_lists(acts: list[dict], refresh_days: int = 7, per_run: int = 40, budget_s: int = 600) -> int:
    """The Suvestine version lists (no texts): today's-text recovery and the back-test read them from
    suvestine_scope.jsonl. New acts first, then each act again about once a week (`per_run` a night): the table is not
    entirely frozen after its 2025 bulk load (DK got 2026-06-07 – 2026-10-31 on 2026-07-01; ACCURACY B50), and an open
    version can be closed later. Rows are merged by suvestines_id. Returns the rows added or changed."""
    path, seen_p = STATE / "suvestine_scope.jsonl", STATE / "suvestine_checked.json"
    keys = ("_id", "dokumento_id", "suvestines_id", "galioja_nuo", "galioja_iki", "suv_duom_atnaujinimas")
    rows = {}
    if path.exists():
        for l in path.open():
            r = json.loads(l)
            rows[r["suvestines_id"]] = r
    have = {r["dokumento_id"] for r in rows.values()}
    checked = json.loads(seen_p.read_text()) if seen_p.exists() else {}
    if isinstance(checked, list):  # the old format: acts asked once, no date
        checked = {d: "2000-01-01" for d in checked}
    today = dt.date.today().isoformat()
    stale = (dt.date.today() - dt.timedelta(days=refresh_days)).isoformat()
    due = [a for a in acts if a["dokumento_id"] not in have and a["dokumento_id"] not in checked] + \
        sorted((a for a in acts if (a["dokumento_id"] in have or a["dokumento_id"] in checked)
                and checked.get(a["dokumento_id"], "2000-01-01") < stale), key=lambda a: checked.get(a["dokumento_id"], ""))
    import time
    changed, failed, t0 = 0, 0, time.time()
    todo, waits = list(due[:per_run]), 0
    while todo:
        if time.time() - t0 > budget_s:  # a slow night (the API through the relay): the rest next night
            break
        doc = todo[0]["dokumento_id"]
        if SUVESTINE_DOWN:  # tripped by an earlier query tonight: the rest next night
            break
        try:
            got = query("Suvestine", f'select(_id,dokumento_id,suvestines_id,galioja_nuo,galioja_iki,suv_duom_atnaujinimas)'
                                     f'&dokumento_id="{doc}"&limit(2000)')
        except urllib.error.HTTPError as e:
            # 429 (rate limited for a minute or so, 2026-11-22: it ended the list after 203 of 314 acts): wait and ask
            # the same act again, within the budget; not counted as checked
            if e.code == 429 and waits < SUVESTINE_429_WAITS and time.time() - t0 + SUVESTINE_429_WAIT_S < budget_s:
                waits += 1
                time.sleep(SUVESTINE_429_WAIT_S)
                continue
            failed += 1
            checked[doc] = today
            break
        except Exception:  # this act's query timed out (an act the table lacks makes it scan everything, 2026-10-24):
            failed += 1      # counted as checked, so it goes to the back of the queue and is asked again next week
            checked[doc] = today
            break
        todo.pop(0)
        for r in got:
            c = {k: r.get(k) for k in keys}
            if rows.get(c["suvestines_id"]) != c:
                rows[c["suvestines_id"]] = c
                changed += 1
        checked[doc] = today
    if changed or due[:per_run]:
        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()))
        tmp.replace(path)
    seen_p.write_text(json.dumps(checked, sort_keys=True))
    if failed:
        SUVESTINE_FAILED.append(f"version lists: {failed} acts not read (asked again next night)")
    return changed


def register_watermark() -> str | None:
    """The newest TAR publication date the open data hold (written by update_recent_laws): acts published after it
    are not visible to our rules yet, whatever they change (ACCURACY A19)."""
    p = STATE / "register_watermark.json"
    if p.exists():
        return json.loads(p.read_text()).get("newest_publication")
    newest = ""
    if (STATE / "laws.jsonl").exists():  # before the first nightly with this file: the laws we know (a lower bound)
        for line in (STATE / "laws.jsonl").open():
            newest = max(newest, json.loads(line).get("paskelbta_tar") or "")
    return newest or None


def meta_key(d: dict) -> str:
    """A law's or a Constitutional Court ruling's number (XV-969, KT44-A-N4/2026: unique); a resolution's
    number/adoption date ("875/2025-12-03")."""
    return d["atv_dok_nr"] if d.get("rusis") in LAW_TYPES or is_ruling(d) else f"{d['atv_dok_nr']}/{d.get('priimtas')}"
META_FIELDS = "dokumento_id,tar_kodas,atv_dok_nr,rusis,galioj_busena,priimtas,paskelbta_tar,isigalioja,negalioja,pavadinimas"


def act_metadata(path: pathlib.Path | None = None) -> dict[str, dict]:
    path = path or (STATE / "laws.jsonl" if (STATE / "laws.jsonl").exists() else DATA / "raw" / "dokumentas.jsonl")
    return _act_metadata(path)


def update_recent_laws(n: int = 3000) -> int:
    """Merge the newest `n` acts (by TAR publication date) into the compact laws metadata.
    Nightly: ~0.5 s per 2000 rows, covering a few weeks of publications."""
    path0 = STATE / "laws.jsonl"
    newest = "0000-00-00"
    if path0.exists():
        for line in path0.open():
            newest = max(newest, json.loads(line).get("paskelbta_tar") or "")
    since = (dt.date.fromisoformat(newest) - dt.timedelta(days=7)).isoformat() if newest > "0000" else "2000-01-01"
    attempts = [f"select(_id,{META_FIELDS})&sort(-paskelbta_tar)&limit({n})",
                f"select(_id,{META_FIELDS})&sort(-paskelbta_tar)&limit(500)",
                f'select(_id,{META_FIELDS})&paskelbta_tar>="{since}"&limit({n})']
    rows, last_err = None, None
    for q in attempts:  # data.gov.lt sometimes returns 500 for one form and not another
        try:
            rows = query("Dokumentas", q)
            UPDATE_LOG.append(q.split("&", 1)[1])
            break
        except Exception as e:
            last_err = e
    if rows is None:
        raise last_err
    # No gap allowed: the rows must reach back to the newest publication we already had. After a
    # long outage the newest-n window doesn't, so page through everything published since then.
    oldest = min((r.get("paskelbta_tar") or "9999" for r in rows), default="9999")
    # the register's freshness: the newest publication of any act in the open data (all types, not only laws)
    newest_any = max((r.get("paskelbta_tar") or "" for r in rows), default="")
    if newest_any:
        (STATE / "register_watermark.json").parent.mkdir(parents=True, exist_ok=True)
        (STATE / "register_watermark.json").write_text(json.dumps(
            {"newest_publication": newest_any, "checked": dt.datetime.now().astimezone().isoformat(timespec="seconds")}))
    COVERAGE.update({"had_newest": newest, "window_oldest": oldest, "paged": 0})
    if newest > "0000" and oldest > newest:
        last, page = None, 2000
        while True:
            q = (f'select(_id,{META_FIELDS})&paskelbta_tar>="{newest}"&sort(_id)'
                 + (f'&_id>"{last}"' if last else "") + f"&limit({page})")
            batch = query("Dokumentas", q)  # errors propagate: a gap must not pass silently
            rows += batch
            COVERAGE["paged"] += len(batch)
            if len(batch) < page:
                break
            last = batch[-1]["_id"]
    path = STATE / "laws.jsonl"
    have = {}
    if path.exists():
        for line in path.open():
            d = json.loads(line)
            have[d["dokumento_id"]] = d
    added = 0
    for r in rows:
        if keep_meta(r):
            added += r["dokumento_id"] not in have
            have[r["dokumento_id"]] = {k: r.get(k) for k in META_FIELDS.split(",")}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        for d in have.values():
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return added


def _act_metadata(path: pathlib.Path) -> dict[str, dict]:
    """Metadata of amending acts, from bin/fetch_meta.py output: laws keyed by number (Seimas numbers, XV-969,
    are unique), and Government resolutions amending a points act in scope keyed by number/adoption date.
    From data/raw (everything) only laws and resolutions are read; laws.jsonl holds only what keep_meta keeps.
    """
    out: dict[str, dict] = {}
    if path.name == "laws.jsonl" and CITED.exists():  # acts our texts name, looked up one by one (update_cited, D-057)
        for line in CITED.open():
            d = json.loads(line)
            out[meta_key(d)] = d
    with path.open() as f:
        for line in f:
            d = json.loads(line)
            if d.get("rusis") in LAW_TYPES and d.get("atv_dok_nr"):
                out[d["atv_dok_nr"]] = d
            elif d.get("rusis") == "Nutarimas" and d.get("atv_dok_nr") and d.get("priimtas"):
                out[meta_key(d)] = d  # kept only when it amends a points act in scope (keep_meta)
            elif d.get("rusis") == "Įsakymas" and d.get("atv_dok_nr") and d.get("priimtas") and \
                    (path.name == "laws.jsonl" or keep_meta(d)):  # orders (D-033): laws.jsonl keeps only those amending
                out[meta_key(d)] = d                              # one in scope; from data/raw, filter here
    return out


CITED = STATE / "cited.jsonl"            # metadata of amending acts found by the number and date a text cites (D-057)
CITED_WANTED = STATE / "cited_wanted.json"  # the numbers the last build could not date (currency.UNKNOWN_REFS)
CITED_CHECKED = STATE / "cited_checked.json"  # number -> day last looked up (and not found): asked again after 30 days
CITED_TEXT_SINCE = "2020-01-01"  # = currency.Laws.TEXT_SINCE: older ones are dated from their metadata alone


def update_cited(budget_s: int = 180, retry_days: int = 30) -> dict:
    """The amending acts a text's notes name ("V-1862/2020-08-18") that the metadata lacks: their title cites the
    amended act in a form the title search misses (no space before „, another act's name first), or they are court
    decisions. Looked up by number and adoption date, one request each. Kept only when exactly one row answers and it
    is a resolution or an order (their texts are parsed as such), or any act adopted before CITED_TEXT_SINCE (dated from
    its metadata, its text never read): a court decision annulling points is one. Returns counts for the night's log."""
    wanted = json.loads(CITED_WANTED.read_text()) if CITED_WANTED.exists() else []
    checked = json.loads(CITED_CHECKED.read_text()) if CITED_CHECKED.exists() else {}
    have = set(_act_metadata(STATE / "laws.jsonl")) if (STATE / "laws.jsonl").exists() else set()
    today = dt.date.today()
    due = [n for n in wanted if n not in have and "/" in n
           and (today - dt.date.fromisoformat(checked.get(n, "2000-01-01"))).days >= retry_days]
    found, t0 = [], time.time()
    for key in due:
        if time.time() - t0 > budget_s:
            break
        number, _, adopted = key.rpartition("/")
        try:
            rows = query("Dokumentas", f'select(_id,{META_FIELDS})&atv_dok_nr="{number}"&priimtas="{adopted}"&limit(5)',
                         tries=2, timeout=60)
        except Exception:  # noqa: BLE001  next night
            continue
        rows = [r for r in rows if (r.get("priimtas") or "")[:10] == adopted]
        ok = len(rows) == 1 and (rows[0].get("rusis") in POINT_TYPES or adopted < CITED_TEXT_SINCE)
        if ok:
            found.append({k: rows[0].get(k) for k in META_FIELDS.split(",")})
        else:
            checked[key] = today.isoformat()
    if found:
        with CITED.open("a") as f:
            for r in found:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    STATE.mkdir(parents=True, exist_ok=True)
    CITED_CHECKED.write_text(json.dumps(checked, indent=0, sort_keys=True))
    return {"wanted": len(wanted), "asked": len(due), "found": len(found)}


# the energy regulator's decisions (D-034): metadata in state, texts fetched once (a decision is not consolidated)
DECISIONS_STATE = STATE / "decisions.jsonl"
DECISION_FIELDS = META_FIELDS + ",priemusi_inst"
REGULATOR = "Valstybinė energetikos reguliavimo taryba"


def decision_rows() -> list[dict]:
    return [json.loads(l) for l in DECISIONS_STATE.open()] if DECISIONS_STATE.exists() else []


def update_decisions(n: int = 300) -> int:
    """Merge the regulator's newest `n` decisions (by publication) into state/decisions.jsonl; a known one is replaced
    (its register status can change). Returns how many are new."""
    rows = query("Dokumentas", f'select(_id,{DECISION_FIELDS})&priemusi_inst="{REGULATOR}"&sort(-paskelbta_tar)&limit({n})',
                 tries=2, timeout=90)
    have = {r["dokumento_id"]: r for r in decision_rows()}
    new = sum(1 for r in rows if r["dokumento_id"] not in have)
    for r in rows:
        r.pop("_id", None)
        have[r["dokumento_id"]] = r
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = DECISIONS_STATE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sorted(have.values(), key=lambda r: r.get("priimtas") or "")))
    tmp.replace(DECISIONS_STATE)
    return new


def decision_text(dokumento_id: str, fetch: bool = False) -> str | None:
    """A decision's own text (data/decisions/<id>.json), fetched once when `fetch`; None if not fetched (yet)."""
    p = DATA / "decisions" / f"{dokumento_id}.json"
    if p.exists():
        return json.loads(p.read_text())["row"].get("tekstas_lt") or None
    if not fetch:
        return None
    row = fetch_dokumentas(dokumento_id, tries=1, timeout=60)  # one slow text must not overrun the step's budget
    p.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    p.write_text(json.dumps({"fetched": now, "row": {k: row.get(k) for k in ("dokumento_id", "tekstas_lt", "galioj_busena")}}, ensure_ascii=False))
    return row.get("tekstas_lt") or None


def has_consolidation(text: str) -> bool:
    """True if a text is a consolidated version (header 'Suvestinė redakcija nuo ...' near the top)."""
    return any(l.strip().startswith("Suvestinė redakcija nuo") for l in (text or "").split("\n")[:40])


def fetch_suvestine_newest(dokumento_id: str, day: str) -> dict | None:
    """Newest official consolidation from Suvestine (frozen 2025-05) valid on `day`, else the newest one."""
    rows = query("Suvestine", f'select(suvestines_id,galioja_nuo,galioja_iki,suv_duom_atnaujinimas,tekstas_lt)'
                              f'&dokumento_id="{dokumento_id}"&sort(-galioja_nuo)&limit(20)')
    rows = [r for r in rows if r.get("tekstas_lt")]
    for r in rows:
        if (r["galioja_nuo"] or "")[:10] <= day and (not r["galioja_iki"] or day <= r["galioja_iki"][:10]):
            return r
    return rows[0] if rows else None


def act_text(dokumento_id: str) -> tuple[str, dict]:
    """The text we build from, plus where it came from (D-009).

    Normally Dokumentas (newest prepared consolidation). If Dokumentas holds an unconsolidated
    original (the Constitution does), fall back to the newest Suvestine consolidation, cached as
    <snapshot dir>/suvestine.json. The text gets a version header if it lacks one, so the parser
    and validators treat both sources alike.
    """
    snap = latest_snapshot(dokumento_id)
    text = snap["row"].get("tekstas_lt") or ""
    if eurlex.is_eu(dokumento_id):  # D-037
        return text, {"origin": "EUR-Lex", "eu_version": snap["row"].get("eu_version"), "fetched": snap["fetched"]}
    if has_consolidation(text):
        return text, {"origin": "Dokumentas", "fetched": snap["fetched"]}
    cache = DATA / "dokumentas" / dokumento_id / "suvestine.json"
    stale = cache.exists() and (dt.date.today() - dt.date.fromisoformat(
        (json.loads(cache.read_text()).get("fetched") or "2000-01-01")[:10])).days > 7
    if not cache.exists() or (stale and REFRESH_SUVESTINE):  # weekly, in case Suvestine updates resume
        old = json.loads(cache.read_text())["row"] if cache.exists() else None
        try:
            r = fetch_suvestine_newest(dokumento_id, snap["fetched"][:10])
            now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
            if r or not old:  # an empty answer never replaces a text we had
                cache.write_text(json.dumps({"fetched": now, "row": r}, ensure_ascii=False))
            else:
                SUVESTINE_FAILED.append(f"{dokumento_id}: empty answer, kept the cached text")
        except Exception as e:
            SUVESTINE_FAILED.append(f"{dokumento_id}: {e}")
            if not cache.exists():
                # nothing to fall back on: Dokumentas may hold only the original while Suvestine has the consolidation
                # (20 of the 74 laws added 2026-10-26); building from the original would show outdated text
                raise
    r = json.loads(cache.read_text())["row"]
    if not r:
        return text, {"origin": "Dokumentas (original, no consolidation available)", "fetched": snap["fetched"]}
    t = r["tekstas_lt"]
    if not has_consolidation(t):
        t = (f"Suvestinė redakcija nuo {r['galioja_nuo'][:10]}" + (f" iki {r['galioja_iki'][:10]}" if r.get("galioja_iki") else "")
             + "\n" + t)
    return t, {"origin": "Suvestine", "suvestines_id": r["suvestines_id"], "prepared": r.get("suv_duom_atnaujinimas"),
               "fetched": snap["fetched"]}
