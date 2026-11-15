#!/usr/bin/env python3
"""Print one article from a saved e-tar consolidation (see bin/etar_fetch.py).

Usage: bin/etar_article.py DOKUMENTO_ID ARTICLE [--chars 1500] [--root data/etar]
  ARTICLE as written in amending-act titles: 52, 21-1 (for 21¹), 6.228-1 (for 6.228¹).

Prints the heading, the beginning of the text and the article's "Straipsnio pakeitimai" notes.
A throwaway prototype of the P2 parser: <sup>n</sup> becomes "-n", block tags become newlines.
"""
import argparse
import html
import json
import pathlib
import re


def to_text(raw: str) -> str:
    raw = re.sub(r"<sup[^>]*>\s*([^<]+?)\s*</sup>", r"-\1", raw, flags=re.I)
    raw = re.sub(r"</?(p|div|br|tr|li|h\d)[^>]*>", "\n", raw, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", raw)).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc")
    ap.add_argument("article")
    ap.add_argument("--chars", type=int, default=1500)
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path("data/etar"))
    a = ap.parse_args()
    d = a.root / a.doc
    meta = json.loads((d / "meta.json").read_text())
    t = to_text((d / f"{meta['suvestines_id']}.html").read_text())
    head = re.compile(rf"^\s*{re.escape(a.article)} straipsnis\.(.*)$", re.M)
    m = None
    for m in head.finditer(t):  # last match = the article itself, not a TOC entry
        pass
    if not m:
        raise SystemExit(f"article {a.article} not found")
    nxt = re.compile(r"^\s*\d+(?:\.\d+)?(?:-\d+)? straipsnis\.", re.M).search(t, m.end())
    body = t[m.start(): nxt.start() if nxt else len(t)]
    notes_at = body.find("Straipsnio pakeitimai")
    print(f"[{meta['title'][:70]}] version {meta['valid_from']}..{meta['valid_to']} ({meta['suvestines_id']})")
    print(body[: notes_at if notes_at >= 0 else len(body)][: a.chars].strip())
    if notes_at >= 0:
        print("--", " ".join(body[notes_at:].split())[:600])


if __name__ == "__main__":
    main()
