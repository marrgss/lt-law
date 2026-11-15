#!/usr/bin/env python3
"""The next acts to add (D-042): in force, not in the scope, ranked by how often our stored texts cite them.

Usage: uv run bin/rank_candidates.py laws  [--min N] [--max N] [--seeds]
       uv run bin/rank_candidates.py rules [--min N] [--max N] [--issuer TEXT] [--kind KIND] [--seeds]

laws:  laws and codes from data/raw/dokumentas.jsonl (amending, ratification, budget-indicator, entry-into-force and
       "Dėl …" laws left out), cited as "<title core> įstatym…" / "kodeks…".
rules: Government resolutions, ministers' and VERT orders approving one set of rules ("Dėl … taisyklių / tvarkos aprašo
       / nuostatų / metodikos … patvirtinimo"), cited by the rules' genitive name. Agencies' orders ("… prie … ministerijos")
       are left out (resolve_scope.py takes ministers' orders only); so are titles approving two documents at once.
--issuer keeps rules whose issuer contains TEXT ("energetikos"), cited or not.
--seeds prints seed lines for scope/v1_seed.yaml (a coined internal abbreviation, no_abbr: true; for rules the
nominative name, which a human checks against the heading in the text: amendments rename rules, the register keeps
the title as adopted).
"""
import argparse
import collections
import glob
import json
import re

import yaml

# amending, ratification, budget, entry-into-force and one-off laws (a year's base pay, a reorganisation, a loan)
LAW_SKIP = re.compile(r"(pakeitimo|papildymo|pripažinimo netekusi\w* galios|ratifikav\w*|biudžet\w* .*rodikl\w*|rodiklių patvirtinimo|"
                      r"įsigaliojimo|įgyvendinimo|reorganizavimo|taikomo \d{4} metais|metų biudžeto|paskolos|laikinasis|"
                      r"akcijų įsigijimo)\b", re.I)
RULE = re.compile(r"^Dėl (.+?(?:taisyklių|tvarkos aprašo|aprašo|nuostatų|reglamento|metodikos|reikalavimų|normų))\s+patvirtinimo$", re.I)
# two or more documents approved at once ("… normų ir Priklausomųjų …", "… taisyklių, Veiklos tęstinumo valdymo plano ir …"):
# each needs its own act with `document:` (2026-11-03: four went in under one name, showing only the first)
TWO = re.compile(r"(aprašo|taisyklių|nuostatų|sąrašo|metodikos|reglamento|normų|plano|reikalavimų|programos)(?:,| ir) [A-ZĄČĘĖĮŠŲŪŽ]")
NOUN = [("tvarkos aprašo", "tvarkos aprašas", "A"), ("aprašo", "aprašas", "A"), ("taisyklių", "taisyklės", "T"),
        ("nuostatų", "nuostatai", "N"), ("reglamento", "reglamentas", "R"), ("metodikos", "metodika", "M"),
        ("reikalavimų", "reikalavimai", "R"), ("normų", "normos", "N")]
FEM = {"taisyklės", "normos"}
PROPER = re.compile(r"(Lietuvos|Europos|Klaipėdos|Vilniaus|Kauno)\b")


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^lietuvos respublikos\s+", "", t.lower().strip()))


def stored_texts() -> str:
    out = []
    for f in glob.glob("data/dokumentas/*/*.json"):
        try:
            out.append(json.load(open(f))["row"].get("tekstas_lt") or "")
        except Exception:
            pass
    return re.sub(r"\s+", " ", "\n".join(out).lower())


def coin(words: list[str], letter: str, used: set) -> str:
    base = "".join(w[0].upper() for w in words if w.lower() not in {"ir", "ar", "bei", "su", "prie", "pagal", "už", "į", "jų", "jo", "tam", "tikrų"})[:7] + letter
    ab, k = base, 2
    while ab in used:
        ab, k = base[:-1] + str(k) + base[-1], k + 1
    used.add(ab)
    return ab


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["laws", "rules"])
    ap.add_argument("--min", type=int, default=0)
    ap.add_argument("--max", type=int, default=10**9)
    ap.add_argument("--issuer", default="")
    ap.add_argument("--kind", dest="issuer_kind", default="",  # its own name: "kind" is the positional's (2026-11-09: every rule dropped)
                    help="rules: only Vyriausybė, ministras or VERT (a tenth of the time for Vyriausybė)")
    ap.add_argument("--seeds", action="store_true")
    a = ap.parse_args()
    acts = yaml.safe_load(open("scope/v1.yaml"))["acts"]
    ours = {x.get("dokumento_id") for x in acts} | {x.get("tar_kodas") for x in acts}
    names = {norm(x.get("name") or "") for x in acts}
    seeds = open("scope/v1_seed.yaml").read() + open("scope/queued_seed.yaml").read()
    used = {x["abbr"] for x in acts} | set(re.findall(r"abbr: ([^,}]+)", seeds))
    queued = set(re.findall(r"resolution: ([\w.]+)", open("scope/queued_seed.yaml").read()))
    cands = []
    for line in open("data/raw/dokumentas.jsonl"):
        d = json.loads(line)
        if d["galioj_busena"] != "galioja" or d["dokumento_id"] in ours or d["tar_kodas"] in ours:
            continue
        t, inst = re.sub(r"\s+", " ", (d["pavadinimas"] or "").strip()), d["priemusi_inst"] or ""
        if a.kind == "laws":
            if d["rusis"] not in ("Įstatymas", "Kodeksas", "Konstitucinis įstatymas") or LAW_SKIP.search(t) \
                    or t.lower().startswith("dėl ") or "įstatymas dėl" in t.lower() or norm(t) in names:
                continue
            m = re.match(r"Lietuvos Respublikos (.+?)\s+(įstatymas|kodeksas|konstitucinis įstatymas)$", t)
            if m:
                cands.append({"title": t[len("Lietuvos Respublikos "):], "core": m.group(1), "kind": m.group(2),
                              "id": d["dokumento_id"], "nr": d["atv_dok_nr"]})
        else:
            if d["rusis"] == "Nutarimas" and inst.startswith("Lietuvos Respublikos Vyriausybė"):
                k = "Vyriausybė"
            elif d["rusis"] == "Įsakymas" and all(x.strip().endswith("ministerija") for x in inst.split("\n") if x.strip()) \
                    and " prie " not in inst:  # ministers' orders, joint ones too; not with an agency (VMVT)
                k = "ministras"
            elif d["rusis"] == "Nutarimas" and "energetikos reguliavimo" in inst:
                k = "VERT"
            else:
                continue
            if a.issuer_kind and k != a.issuer_kind:
                continue
            m = RULE.match(t)
            if not m or d["dokumento_id"] in queued:
                continue
            name = re.sub(r"[„“\"]", "", m.group(1)).strip()
            if len(name.split()) < 3 or TWO.search(name) or (a.issuer and a.issuer.lower() not in inst.lower()):
                continue
            cands.append({"name": name, "kind": k, "inst": inst, "id": d["dokumento_id"], "nr": d["atv_dok_nr"]})
    blob = stored_texts()
    for c in cands:
        c["n"] = len(re.findall(re.escape(c["core"].lower()) + r"\s+(?:įstatym|kodeks)", blob)) if a.kind == "laws" \
            else blob.count(c["name"].lower())
    same = collections.Counter(c.get("title") or c["name"] for c in cands)
    cands = [c for c in cands if same[c.get("title") or c["name"]] == 1]  # two in force under one name: a human decides
    pick = sorted((c for c in cands if a.min <= c["n"] <= a.max or (a.issuer and a.kind == "rules")), key=lambda c: -c["n"])
    for c in pick:
        if not a.seeds:
            print(c["n"], c.get("kind"), c["nr"], c.get("title") or c["name"])
        elif a.kind == "laws":
            ab = coin(re.findall(r"[\wąčęėįšųūžĄČĘĖĮŠŲŪŽ]+", c["core"]), "K" if c["kind"] == "kodeksas" else "Į", used)
            print(f'  - {{abbr: {ab}, no_abbr: true, title: "{c["title"]}", number: {c["nr"]}}}  # cited {c["n"]}')
        else:
            g = c["name"]
            noun = next((x for x in NOUN if g.endswith(" " + x[0])), None)
            if not noun:  # its noun in another form ("Taisyklių" capitalised, a name of one word): a human writes this seed
                print(f"# not generated: {c['nr']} {g[:100]}")
                continue
            gen, nom, letter = noun
            words = g[: -len(gen)].split()
            if words and nom == "reglamentas" and words[-1].endswith("inio"):  # "slėginės įrangos techninio" -> "techninis"
                words[-1] = words[-1][:-4] + "inis"
            elif words and re.search(r"(ųjų|inių|alių)$", words[-1]) and nom != "tvarkos aprašas":  # an agreeing adjective
                w = words[-1]
                words[-1] = w[:-3] + ("osios" if nom in FEM else "ieji") if w.endswith("ųjų") else \
                    w[:-2] + (("ės" if nom in FEM else "iai") if w.endswith("inių") else ("ios" if nom in FEM else "ūs"))
            lower = lambda s: s if PROPER.match(s) else s[0].lower() + s[1:]
            ab = coin(re.findall(r"[\wąčęėįšųūžĄČĘĖĮŠŲŪŽ]+", g[: -len(gen)]), letter, used)
            print(f'  - {{abbr: {ab}, no_abbr: true, title: "{lower(" ".join(words + [nom]))}", genitive: "{lower(g)}", '
                  f'resolution: {c["id"]}}}  # cited {c["n"]}, {c["kind"]} {c["nr"]}')
    print(f"# {len(pick)} of {len(cands)} candidates", flush=True)


if __name__ == "__main__":
    main()
