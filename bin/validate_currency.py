#!/usr/bin/env python3
"""Validate "which article texts apply today" against e-tar's version in force today.

Usage: uv run bin/validate_currency.py [scope/p2.yaml] [--day YYYY-MM-DD] [--show N]

For every article of each act's stored consolidation (Dokumentas), currency.assess() says
current / pending / outdated / unknown. e-tar's version valid on --day is the answer key:
  current + identical text      correct
  current + different/missing   SILENT ERROR (must be 0 before publishing)
  flagged + different           correct flag
  flagged + identical           false alarm (costs a link to e-tar, nothing worse)
Fetches amending laws (data/amending/) and e-tar pages (data/etar/) only when not cached.
Exit code 1 if any silent error.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import yaml  # noqa: E402

from ltlaw import etar, source  # noqa: E402
from ltlaw.today import find_today_only  # noqa: E402
from ltlaw.currency import _article_repealed, apply_register_state, article_expiry, Laws, assess  # noqa: E402
from ltlaw.parse import html_to_text, parse  # noqa: E402
from ltlaw.validate import article_text, law_text, norm  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scope", nargs="?", default="scope/p2.yaml")
    ap.add_argument("--day", default=dt.date.today().isoformat())
    ap.add_argument("--show", type=int, default=5)
    a = ap.parse_args()
    laws = Laws()
    silent_total, unverified = 0, []
    summary = {"day": a.day, "answer_key": "e-tar.lt version in force on day", "acts": {}}
    for act in yaml.safe_load(open(a.scope))["acts"]:
        if act["dokumento_id"].startswith("EU."):  # EU acts are checked against EUR-Lex when fetched (D-037)
            continue
        doc = act["dokumento_id"]
        text, origin = source.act_text(doc)
        ours = parse(text, act.get("document"))
        ours.prepared = origin.get("prepared")
        st = assess(ours, act, laws, a.day, source.first_seen(doc, ours.version_from))
        apply_register_state(st, source.latest_snapshot(doc)["row"], a.day, act)  # as the pages show it
        v = etar.version_valid_on(doc, a.day)
        row = source.latest_snapshot(doc)["row"]
        if v is None and ((ours.version_from is None and row.get("galioj_busena") == "galioja")
                          or etar.original_in_force(doc, ours.version_from, row)):  # B83
            # in force and never amended (TMĮ, KPTAĮ, …): e-tar has no consolidation to compare, the original is the
            # text; not counted as checked, and not as wrong (it was, as 70 "wrong labels" on the home page, 2026-10-26)
            print(f"{act['abbr']:5s} never consolidated, original text in force: not compared")
            summary["acts"][act["abbr"]] = {"articles": len(st.articles), "original_only": True, "current_ok": 0,
                                            "flagged": sum(1 for s in st.articles.values() if s.state != "current"), "silent_errors": 0}
            continue
        if v is None:  # adopted, not in force yet (NTRgĮ): no version applies today; every article must be flagged
            unflagged = [l for l, s in st.articles.items() if s.state == "current"]
            print(f"{act['abbr']:5s} no e-tar version in force on {a.day}: {len(unflagged)} articles labelled current")
            summary["acts"][act["abbr"]] = {"articles": len(st.articles), "not_in_force": True, "current_ok": 0,
                                            "flagged": len(st.articles) - len(unflagged), "silent_errors": len(unflagged)}
            silent_total += len(unflagged)
            continue
        html = etar.version_html_or_none(doc, v["id"])
        if html is None:  # nothing to check the labels against: the act can't be released as checked
            print(f"{act['abbr']:5s} UNVERIFIED: e-tar gives today's version ({v['valid_from']}) only as files, no HTML")
            summary["acts"][act["abbr"]] = {"articles": len(ours.main.articles), "unverified": True}
            unverified.append(act["abbr"])
            continue
        truth = parse(html_to_text(html), act.get("document"))
        T = {x.label: x for x in truth.main.articles}
        c = collections.Counter()
        silent, fa = [], []
        for art in ours.main.articles:
            s = st.articles[art.label].state
            t = T.get(art.label)
            same = t is not None and norm(article_text(art.variant_on(a.day))) == norm(article_text(t.variant_on(a.day)))
            # the law's words alike, only an editorial note differs ("TAR pastaba. 3 straipsnio 2 dalis įsigalioja
            # 2014-10-01": kept in our older consolidation, dropped from e-tar's once past; IAENĮ 3, SGDTĮ 5, 9)
            note_only = not same and t is not None and norm(law_text(art.variant_on(a.day))) == norm(law_text(t.variant_on(a.day)))
            if s == "current":
                c["current_ok" if same else "current_ok_note_diff" if note_only else "SILENT"] += 1
                if not same and not note_only:
                    silent.append(art.label)
            elif s == "repealed":  # correct when e-tar's text in force today also has no such article in force
                gone = t is None or _article_repealed(t.variant_on(a.day))[0] or \
                    (article_expiry(t.variant_on(a.day), art.label) or "9999") <= a.day  # "N straipsnis netenka galios D"
                c["repealed_correct" if gone else "SILENT"] += 1
                if not gone:
                    silent.append(art.label)
            else:
                c[f"{s}_{'false_alarm' if same else 'correct'}"] += 1
                if same:  # which flags were unnecessary, and the rule's reason: what to work on
                    fa.append([art.label, s, (st.articles[art.label].reasons or [""])[0][:200]])
        # in force today on e-tar, but no page of ours (not stored, not recovered): a silent error too
        only = find_today_only(ours, doc, act, laws, a.day)
        recovered = {x.article.label for x in only} | {n["label"] for n in st.added}
        for x in only:  # a recovered page labelled current must also have e-tar's text (H1, iteration 2)
            t = T.get(x.article.label)
            if x.status.state == "current" and (t is None or norm(article_text(x.article)) != norm(article_text(t.variant_on(a.day)))):
                c["SILENT"] += 1
                silent.append(f"{x.article.label} (recovered)")
        absent = [k for k in T if k not in {x.label for x in ours.main.articles} and k not in recovered
                  and not (lambda g: g[0] and (g[1] or "0000") <= a.day)(_article_repealed(T[k].variant_on(a.day)))]
        c["ABSENT"] += len(absent)
        silent += [f"{k} (absent)" for k in absent]
        silent_total += len(silent)
        summary["acts"][act["abbr"]] = {"articles": len(ours.main.articles), "silent_errors": len(silent),
                                        "current_ok": c["current_ok"] + c["current_ok_note_diff"],
                                        "flagged": sum(n for k, n in c.items() if k not in ("current_ok", "current_ok_note_diff", "SILENT", "ABSENT")),
                                        "false_alarms": sum(n for k, n in c.items() if k.endswith("false_alarm")),
                                        "false_alarm_list": fa,
                                        "etar_version": f"{v['valid_from']}..{v['valid_to'] or ''}"}
        print(f"{act['abbr']:5s} stored {ours.version_from}..{ours.version_to or ''} ({st.version_state}), "
              f"e-tar today {v['valid_from']}..{v['valid_to'] or ''}: {dict(sorted(c.items()))}"
              f"{' | in force today but absent from stored: ' + str(absent[:8]) if absent else ''}")
        if st.missing:
            print(f"      laws in force but not in stored text: {[(m['nr'], m['in_force'], m['articles'][:6]) for m in st.missing][:6]}")
        if st.act_level_flags:
            print(f"      act-level flags: {st.act_level_flags[:3]}")
        for k in silent[: a.show]:
            if k.endswith(("(absent)", "(recovered)")):
                print(f"      SILENT {k}: in force on e-tar, no page here")
                continue
            refs = sorted({r.nr for r in ours.main.articles[[x.label for x in ours.main.articles].index(k)].all_refs()})
            print(f"      SILENT {k}: refs {refs[-6:]}")
    summary["silent_errors"] = silent_total
    summary["unverified"] = unverified
    out = source.VALIDATION / "currency.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    sys.exit(1 if silent_total or unverified else 0)


if __name__ == "__main__":
    main()
