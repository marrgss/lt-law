#!/usr/bin/env python3
"""Resolve a seed list (abbreviation + exact title) into a scope file with TAR ids.

Usage: uv run bin/resolve_scope.py [scope/v1_seed.yaml] [--out scope/v1.yaml]

Matches "Lietuvos Respublikos <title>" against data/raw/dokumentas.jsonl: in force, type
law/code/constitution, exact title (whitespace-normalised). A seed `number:` disambiguates, and
also resolves codes, which are published inside their approval law under a longer title.
Reports seeds with zero or several matches instead of guessing. A seed with `resolution: <TAR id>` is a
Government resolution approving rules made of points (KET), or a minister's order (D-033): taken by id, with its
number and adoption date. A seed with `eu: <CELEX>` is an EU act read from EUR-Lex (D-037), with its `number` as
cited ("(ES) 2016/679").
"""
import argparse
import json
import pathlib
import re
import sys

import yaml

TYPES = {"Įstatymas", "Kodeksas", "Konstitucija", "Konstitucinis įstatymas", "Statutas"}


def genitive(title: str) -> str:
    t = title.lower().rstrip(".")
    for nom, gen in (("kodeksas", "kodekso"), ("įstatymas", "įstatymo"), ("konstitucija", "konstitucijos"), ("statutas", "statuto")):
        if t.endswith(nom):
            return t[: -len(nom)] + gen
    return t


# issuers of resolutions other than the Government (D-034): the register's name -> its genitive in citations
RESOLUTION_ISSUERS = {"Valstybinė energetikos reguliavimo taryba": "Valstybinės energetikos reguliavimo tarybos",
                      "Valstybinė kainų ir energetikos kontrolės komisija": "Valstybinės kainų ir energetikos kontrolės komisijos"}
# agencies whose head's orders approve rules (2026-10-29: cyber security, personal data): the register's name -> the
# genitive in citations ("… direktoriaus 2019 m. kovo 14 d. įsakymu Nr. 1T-35 (1.12.E)")
ORDER_ISSUERS = {"Nacionalinis kibernetinio saugumo centras prie Krašto apsaugos ministerijos":
                 "Nacionalinio kibernetinio saugumo centro prie Krašto apsaugos ministerijos direktoriaus",
                 "Valstybinė duomenų apsaugos inspekcija": "Valstybinės duomenų apsaugos inspekcijos direktoriaus"}


def order_fields(h: dict) -> dict:
    """A minister's order approving rules (D-033): its type and issuer, from the register ("Lietuvos Respublikos
    energetikos ministerija" -> "… energetikos ministro"); a regulator's resolution (D-034, VERT): its issuer; a
    Government resolution needs none (the default)."""
    inst = h.get("priemusi_inst") or ""
    if h.get("rusis") == "Nutarimas":
        if inst in RESOLUTION_ISSUERS:
            return {"issuer": RESOLUTION_ISSUERS[inst], "issuer_nom": inst}
        if inst and "Vyriausybė" not in inst:
            raise SystemExit(f"{h['atv_dok_nr']}: a resolution of {inst!r}: add its genitive to RESOLUTION_ISSUERS")
        return {}
    if h.get("rusis") != "Įsakymas":
        return {}
    # "Lietuvos Respublikos energetikos ministerija (1990-1996)": the ministry of those years, cited the same way
    insts = [re.sub(r"\s*\(\d{4}-\d{4}\)$", "", x.strip()) for x in inst.split("\n") if x.strip()]
    if len(insts) == 1 and insts[0] in ORDER_ISSUERS:
        return {"kind": "Įsakymas", "issuer": ORDER_ISSUERS[insts[0]], "issuer_nom": insts[0]}
    if not insts or not all(x.endswith("ministerija") for x in insts):
        raise SystemExit(f"{h['atv_dok_nr']}: an order of {inst!r}: only ministers' orders are supported")
    # a joint order of several ministers ("1-348/D1-1014/3-742"): "…aplinkos ministro, … energetikos ministro ir …"
    gens = [x[: -len("ministerija")] + "ministro" for x in insts]
    issuer = gens[0] if len(gens) == 1 else ", ".join(gens[:-1]) + " ir " + gens[-1]
    return {"kind": "Įsakymas", "issuer": issuer, "issuer_nom": ", ".join(insts)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seed", nargs="?", default="scope/v1_seed.yaml")
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("scope/v1.yaml"))
    a = ap.parse_args()
    by_title: dict[str, list[dict]] = {}
    by_number: dict[str, list[dict]] = {}
    seeds = yaml.safe_load(open(a.seed))["acts"]
    wanted = {s["resolution"] for s in seeds if s.get("resolution")}
    by_id: dict[str, dict] = {}
    with open("data/raw/dokumentas.jsonl") as f:
        for line in f:
            d = json.loads(line)
            if d.get("dokumento_id") in wanted:
                by_id[d["dokumento_id"]] = d
            # an adopted law not yet in force ("neįsigaliojęs", with an entry date) can be in scope: its pages say
            # from when it applies (NTRgĮ replaces NTRĮ from 2027-01-01)
            if d.get("galioj_busena") in ("galioja", "neįsigaliojęs") and d.get("rusis") in TYPES:
                by_title.setdefault(" ".join((d.get("pavadinimas") or "").lower().split()), []).append(d)
                by_number.setdefault(d.get("atv_dok_nr") or "", []).append(d)
    out, problems = [], []

    def add(s: dict, act: dict) -> None:  # `name_checked: true`: the name differs from the text's heading on purpose (ltlaw.scopecheck)
        out.append({**act, **({"name_checked": True} if s.get("name_checked") else {})})
    for s in seeds:
        if s.get("eu"):  # an EU act from EUR-Lex (D-037), by CELEX: its number as cited ("(ES) 2016/679") in the seed
            add(s, {"abbr": s["abbr"], **({"slug": s["slug"]} if s.get("slug") else {}), **({"no_abbr": True} if s.get("no_abbr") else {}),
                        "name": s["title"][:1].upper() + s["title"][1:], "genitive": s["genitive"], "number": s["number"],
                        "dokumento_id": f"EU.{s['eu']}", "kind": s.get("kind") or {"R": "Reglamentas", "L": "Direktyva", "D": "Sprendimas"}[s["eu"][5]]})
            continue
        if s.get("resolution"):  # a Government resolution approving rules made of points (KET), by TAR id
            h = by_id.get(s["resolution"])
            # adopted, with an entry date, not in force yet: like a law (STR 2.02.12:2026 from 2027-01-01)
            if not h or not (h.get("galioj_busena") == "galioja" or h.get("galioj_busena") == "neįsigaliojęs" and h.get("isigalioja")):
                problems.append(f"{s['abbr']}: {s['resolution']} not found in force")
                continue
            try:  # an issuer we can't name (a joint order with an agency): that seed is unresolved, the rest go on
                of = order_fields(h)
            except SystemExit as e:
                problems.append(f"{s['abbr']}: {e}")
                continue
            add(s, {"abbr": s["abbr"], **({"slug": s["slug"]} if s.get("slug") else {}), **({"no_abbr": True} if s.get("no_abbr") else {}),
                        "name": s["title"][:1].upper() + s["title"][1:], "genitive": s["genitive"],
                        "number": h["atv_dok_nr"], "adopted": h["priimtas"], "dokumento_id": h["dokumento_id"],
                        **({} if s.get("unit") == "straipsnis" else {"unit": "punktas"}),  # written in articles (PORFPSDR)
                        **({"document": s["document"], "docslug": s["docslug"]} if s.get("document") else {}),
                        **of})
            continue
        want = " ".join(f"lietuvos respublikos {s.get('via') or s['title']}".lower().split())
        hits = by_title.get(want, [])
        if s.get("number"):
            # codes are published inside their approval law, so match those by number
            hits = [h for h in hits if h["atv_dok_nr"] == s["number"]] or by_number.get(s["number"], [])
        if len(hits) > 1:  # an old and a new act of the same title: the one in force, unless the seed names a number
            hits = [h for h in hits if h.get("galioj_busena") == "galioja"] or hits
        if len(hits) != 1:
            problems.append(f"{s['abbr']}: {len(hits)} matches for '{want}' "
                            + str([(h['atv_dok_nr'], h['dokumento_id'], h.get('priimtas')) for h in hits][:4]))
            continue
        h = hits[0]
        add(s, {"abbr": s["abbr"], **({"slug": s["slug"]} if s.get("slug") else {}), **({"no_abbr": True} if s.get("no_abbr") else {}), "name": s["title"][:1].upper() + s["title"][1:],
                    "genitive": s.get("genitive") or genitive(s["title"]), "number": h.get("atv_dok_nr") or "", "dokumento_id": h["dokumento_id"]})
    a.out.write_text("# Generated by bin/resolve_scope.py from scope/v1_seed.yaml. Edit the seed, not this file.\n"
                     + yaml.safe_dump({"acts": out}, allow_unicode=True, sort_keys=False))
    print(f"{len(out)} resolved -> {a.out}")
    for p in problems:
        print("  UNRESOLVED", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
