"""The energy regulator's decisions (D-034): VERT (until 2019 VKEKK) price, tariff and approval decisions.

Unlike rules (read like resolutions, D-025/D-033), these are one-off decisions: the register keeps every one "in force"
(ESO's 2019 prices still are), the next period's decision replaces the last, and the price tables are annexes that the
open data doesn't carry (e-tar only, D-004). So a decision's label comes from what can be read honestly:

  - the period in its own title ("2026 metams", "2022–2026 m.", "2026 metų antrajam pusmečiui"): current, earlier, later;
  - its entry into force (not yet: "įsigalios");
  - in a recurring price series (same subject, the years left out): a later decision of the series;
  - otherwise the register's own status, said to be the register's.

A decision that only amends or repeals another ("Dėl … 2023 m. spalio 27 d. nutarimo Nr. O3E-1603 … pakeitimo") is
shown with the decision it changes, not as a series of its own.
"""
from __future__ import annotations

import re

from . import source

REGULATORS = ("Valstybinė energetikos reguliavimo taryba", "Valstybinė kainų ir energetikos kontrolės komisija")
# the sectors shown (D-034): electricity first (ESO, the monopoly DSO), then gas and heat; water and waste are not energy
ELECTRICITY = re.compile(r"elektr|persiunt|skirstymo paslaug|perdavimo paslaug|balansav|visuomeninio tiek|visuomenin[ėi]s kain|"
                         r"viešuosius interesus|gaminanč|sistemini", re.I)
GAS = re.compile(r"duj|SGD|suskystint", re.I)
HEAT = re.compile(r"šilum|karšto vandens", re.I)
OTHER = re.compile(r"geriamojo|nuotek|atliek", re.I)
SECTORS = {"elektra": "Elektra", "dujos": "Gamtinės dujos", "siluma": "Šiluma"}
# a subject whose decisions are replaced by the next period's: prices, fees, caps, components, levels, quotas
RECURRING = re.compile(r"kain|įkain|tarif|dedamosios|viršutin|rodikl|patikimumo lyg|kvot|normatyv", re.I)
VERBS = r"paskelbimo|nustatymo|tvirtinimo|patvirtinimo|perskaičiavimo|koregavimo|derinimo|pratęsimo|galiojimo"
CITED = re.compile(r"(\d{4}) m\. (\w+) (\d{1,2}) d\. nutarimo Nr\. ?([\w-]+(?:/[\w-]+)*)")
_MONTHS = {m: i + 1 for i, m in enumerate(source._GEN_MONTHS)}


def is_regulator(row: dict) -> bool:
    return (row.get("priemusi_inst") or "") in REGULATORS and row.get("rusis") == "Nutarimas"


def sector(row: dict) -> str | None:
    """"elektra", "dujos", "siluma" or None (water, waste, the regulator's own affairs); heat before gas ("šilumos …
    gamtinių dujų kainos dedamoji" is a heat price), gas before electricity ("dujų … persiuntimo")."""
    t = row.get("pavadinimas") or ""
    if OTHER.search(t):
        return None
    if HEAT.search(t):
        return "siluma"
    if GAS.search(t):
        return "dujos"
    if ELECTRICITY.search(t):
        return "elektra"
    return None


def is_electricity(row: dict) -> bool:
    return sector(row) == "elektra"


def key_of(row: dict) -> str:
    return f"{row['atv_dok_nr']}/{row['priimtas']}"  # numbers restart every year (as resolutions, B58)


def changes(row: dict) -> str | None:
    """The decision this one amends or repeals ("Dėl … 2023 m. spalio 27 d. nutarimo Nr. O3E-1603 „…“ pakeitimo"), or None."""
    t = row.get("pavadinimas") or ""
    if not re.search(r"pakeitimo|papildymo|pripažinimo netekusi|panaikinimo", t):
        return None
    head = t.split("„")[0]  # the cited decision comes before its quoted title
    m = CITED.search(head)
    if not m or m.group(2) not in _MONTHS:
        return None
    return f"{m.group(4)}/{m.group(1)}-{_MONTHS[m.group(2)]:02d}-{int(m.group(3)):02d}"


def series_key(title: str) -> str:
    """The subject without its period and verb: "Dėl AB „Energijos skirstymo operatorius“ elektros energijos persiuntimo
    paslaugos kainų ir jų taikymo tvarkos 2026 metams paskelbimo …" -> "ab „energijos skirstymo operatorius“ elektros
    energijos persiuntimo paslaugos kainų ir jų taikymo tvarkos"."""
    t = re.sub(r"^(?:Nutarimas\s+)?[Dd]ėl\s+", "", title or "")
    t = re.split(r"\b(?:19|20)\d\d\b", t)[0]
    t = re.sub(rf"\b(?:{VERBS})\b.*$", "", t)
    t = re.sub(r"\b(?:vienašališk\w*|koreguot\w*|perskaičiuot\w*)\s*", "", t)  # how, not what ("vienašališko nustatymo")
    t = re.sub(r"\bkainos dedamųjų\b", "kainų dedamųjų", t)
    t = re.sub(r"uždarosios akcinės bendrovės", "UAB", t)
    t = re.sub(r"akcinės bendrovės", "AB", t)
    return " ".join(t.lower().replace("‒", "-").replace("–", "-").split()).strip(" ,")


def period(title: str) -> tuple[str, str] | None:
    """The dates a decision is for, from its title: "2026 metams" -> ("2026-01-01", "2026-12-31"); "2022‒2026 metų" and
    "2027–2031 m. reguliavimo periodui": from the first year's start to the last's end; a half-year ("2026 metų antrajam
    pusmečiui", "2026 m. II pusmečio", "2023 m. I pusm.") -> its six months. None if the title names no period (a year
    in a cited act's date, "2015 m. sausio 15 d. nutarimu", is not one)."""
    t = CITED.sub(" ", title or "")
    t = re.sub(r"\d{4} m\. \w+ \d{1,2} d\.", " ", t)  # any other full date
    # any dash or none: "2022‒2026", "2025−2029" (a minus sign), "2027 2031 metams" (O3-1304)
    m = re.search(r"\b((?:19|20)\d\d)\s*[‒–—−-]?\s*((?:19|20)\d\d)\s*(?:m\.|metų|metams|met)", t)
    if m:
        return f"{m.group(1)}-01-01", f"{m.group(2)}-12-31"
    m = re.search(r"\b((?:19|20)\d\d)\s*(?:metams|metų|m\.)(\s*(?:I{1,2}\s*pusm\w*\.?|(?:pirm|antr)\w*\s+pusmeč\w*))?", t)
    if not m:
        return None
    y, half = m.group(1), (m.group(2) or "").strip().lower()
    if half.startswith(("ii", "antr")):
        return f"{y}-07-01", f"{y}-12-31"
    if half.startswith(("i", "pirm")):
        return f"{y}-01-01", f"{y}-06-30"
    return f"{y}-01-01", f"{y}-12-31"


def _span(p: tuple[str, str]) -> str:
    a, b = p
    if a[:4] == b[:4]:
        half = {"01-01/06-30": " I pusm.", "07-01/12-31": " II pusm."}.get(f"{a[5:]}/{b[5:]}", "")
        return f"{a[:4]} m.{half}"
    return f"{a[:4]}–{b[:4]} m."


def _applies(row: dict, day: str) -> bool:
    """In force by `day` and its period (if any) begun: ESO's 2027 cap, adopted in October 2026, doesn't replace 2026's."""
    p = period(row.get("pavadinimas") or "")
    return (row.get("isigalioja") or row.get("priimtas") or "") <= day and (p is None or p[0] <= day)


def label(row: dict, later: dict | None, day: str) -> dict:
    """The decision's status on `day`: {"state": current|pending|earlier|replaced|register|repealed, "text": …}."""
    ent = row.get("isigalioja") or ""
    if row.get("galioj_busena") == "negalioja":
        return {"state": "repealed", "text": f"Neteko galios{(' ' + row['negalioja']) if row.get('negalioja') else ''} (Teisės aktų registras)"}
    if ent and ent > day:
        return {"state": "pending", "text": f"Įsigalios {ent}"}
    p = period(row.get("pavadinimas") or "")
    if p and p[1] < day:
        return {"state": "earlier", "text": f"Ankstesnio laikotarpio ({_span(p)})"}
    if later is not None and _applies(later, day):  # a later decision only replaces this one once it applies
        return {"state": "replaced", "text": f"Vėliau priimtas tos pačios srities sprendimas Nr. {later['atv_dok_nr']} ({later['priimtas']})"}
    if p and p[0] <= day <= p[1]:
        return {"state": "current", "text": f"Taikomas: {_span(p)}"}
    if p and day < p[0]:
        return {"state": "pending", "text": f"Taikomas nuo {p[0]}"}
    return {"state": "register", "text": "Teisės aktų registre: galioja"}


def build(rows: list[dict], day: str) -> list[dict]:
    """The regulator's electricity, gas and heat decisions with their series, labels and the decisions that changed them, newest
    first. `rows`: metadata (state/decisions.jsonl)."""
    mine = [r for r in rows if is_regulator(r) and sector(r) and (r.get("paskelbta_tar") or r.get("priimtas") or "") <= day]
    by_key = {key_of(r): r for r in mine}
    changed_by: dict[str, list[dict]] = {}
    base = []
    for r in mine:
        tgt = changes(r)
        if tgt and tgt in by_key:
            changed_by.setdefault(tgt, []).append(r)
        else:
            base.append(r)
    keys = {key_of(r): series_key(r.get("pavadinimas") or "") for r in base}
    # a decision on several subjects belongs to its first subject's series ("… persiuntimo paslaugos kainų ir jų
    # taikymo tvarkos, visuomeninių … kainų … bei …" with "… persiuntimo paslaugos kainų ir jų taikymo tvarkos", O3-398)
    plain = {k for k in keys.values() if RECURRING.search(k)}
    for kk, k in keys.items():
        heads = [s for s in plain if s != k and re.match(re.escape(s) + r"(?:,| bei | ir )", k)]
        if heads:
            keys[kk] = max(heads, key=len)
    series: dict[str, list[dict]] = {}
    for r in base:
        k = keys[key_of(r)]
        if RECURRING.search(k):
            series.setdefault(k, []).append(r)
    later_of: dict[str, dict] = {}
    for k, rs in series.items():
        rs.sort(key=lambda r: (r.get("isigalioja") or r["priimtas"], r["priimtas"]))
        for a, b in zip(rs, rs[1:]):
            later_of[key_of(a)] = b
    out = []
    for r in base:
        k = keys[key_of(r)]
        out.append({**r, "key": key_of(r), "sector": sector(r), "series": k if RECURRING.search(k) else None,
                    "label": label(r, later_of.get(key_of(r)), day),
                    "changed_by": sorted(changed_by.get(key_of(r), []), key=lambda x: x["priimtas"])})
    return sorted(out, key=lambda r: r["priimtas"], reverse=True)


def wants_text(d: dict) -> bool:
    """Whose text the site carries: recent decisions (2023 on) and any not shown as earlier/replaced/repealed."""
    return d["priimtas"] >= "2023-01-01" or d["label"]["state"] in ("current", "pending", "register")
