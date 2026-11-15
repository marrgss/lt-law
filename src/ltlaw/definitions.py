"""Defined terms (ROADMAP Features 5): the act's "Pagrindinės … sąvokos" article(s), and on every other article page
the defined terms found in its text, linked to their definition ("Apmokestinamasis asmuo" → /str/2/#d2).

A definition is a part "N. Term (toliau – short) – meaning". A term is found in a text when its words occur in that
order, consecutive, each inflected: two words match if they share all but the last 3 letters of the longer (a one-word
term) or 4 (a word of a longer term), and at least 4 ("darbdavys" / "darbdavio", "apmokestinamasis asmuo" /
"apmokestinamojo asmens"; not "draudėjas" / "draudikas", "statinys" / "statyba"); "asmuo" / "asmens" by name. Words
under 4 letters ("ir", "ar") are skipped on both sides. A one-word term whose stem is in more than a quarter of the act's articles ("asmuo", "darbdavys") is
not listed: on every page it would say nothing. The law text is never changed (D-002): this is a list below it, and
it says "rastos" (found): a term written with another stem ("vanduo" / "vandens") can be missed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .fulltext import FOLD

RE_DEFS_TITLE = re.compile(r"(?:^|\s)sąvokos$|sąvokų (?:apibrėžtys|apibrėžimai)$|^(?:terminų )?apibrėžtys$", re.I)  # EU acts: "Apibrėžtys" (D-037)
RE_DEF = re.compile(r"^\d+(?:-\d+)?\.\s*(?P<term>[^–()„“]{2,120}?)\s*(?:\((?:toliau|toliau vadinama\w*)\s*[–-]\s*"
                    r"(?P<short>[^)]{2,80})\))?\s+[–-]\s+\S")
MAX_SHOWN = 15


@dataclass
class Term:
    term: str          # as written in the definition ("Apmokestinamasis asmuo")
    label: str         # the definitions article ("2")
    anchor: str        # its part ("d2")
    stems: tuple       # the term's words in order (folded)


def _word(w: str) -> str:
    w = w.translate(FOLD)
    return "asmuo" if w.startswith("asmen") else w  # the one alternation that matters: asmuo, asmens, asmeniui …


def _seq(text: str) -> list[str]:
    return [_word(w) for w in re.findall(r"[a-ząčęėįšųūž]{4,}", (text or "").lower())]


def same(a: str, b: str, slack: int = 3) -> bool:
    """One word, inflected: a common prefix of all but the last `slack` letters of the longer, and at least 4."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n == len(a) == len(b) or n >= max(4, max(len(a), len(b)) - slack)


def terms_of(articles) -> list[Term]:
    """Every defined term of an act (from its definitions articles), in the order defined."""
    out = []
    for a in articles:
        if not (a.title and RE_DEFS_TITLE.search(a.title.strip().rstrip("."))):
            continue
        for b in a.blocks:
            if b.kind != "part" or not b.anchor or not (m := RE_DEF.match(b.text)):
                continue
            for t in (m.group("term"), m.group("short")):
                t = (t or "").strip(" ,„“\"")
                s = tuple(_seq(t))
                if s:
                    out.append(Term(t, a.label, b.anchor, s))
    return out


class Finder:
    """The defined terms found in one act's article texts."""

    def __init__(self, terms: list[Term], article_texts: dict[str, str]):
        seqs = {k: _seq(v) for k, v in article_texts.items()}
        n = max(1, len(seqs))
        share = {}
        for t in terms:
            if len(t.stems) == 1:
                share[t.stems] = sum(1 for s in seqs.values() if any(same(t.stems[0], w) for w in s)) / n
        self.terms = [t for t in terms if len(t.stems) > 1 or share.get(t.stems, 0) <= 0.25]

    def found(self, label: str, text: str) -> list[Term]:
        """Terms in `text` (an article's shown title and text), by first occurrence, not on their own definitions page."""
        seq = _seq(text)
        hits = []
        seen = set()
        for t in self.terms:
            if t.label == label or t.term.lower() in seen:
                continue
            k = len(t.stems)
            slack = 3 if k == 1 else 4  # several words in a row: each may differ more
            pos = next((i for i in range(len(seq) - k + 1)
                        if seq[i][:3] == t.stems[0][:3] and all(same(x, y, slack) for x, y in zip(t.stems, seq[i:i + k]))), None)
            if pos is not None:
                hits.append((pos, t))
                seen.add(t.term.lower())
        # a longer term found at the same place hides a shorter one inside it ("pirkimo sutartis" in "viešojo pirkimo sutartis")
        hits.sort(key=lambda x: (x[0], -len(x[1].stems)))
        out, covered = [], set()
        for pos, t in hits:
            span = set(range(pos, pos + len(t.stems)))
            if span <= covered:
                continue
            covered |= span
            out.append(t)
        return out[:MAX_SHOWN]


# --- the site-wide definitions index (feedback S2, P3, P12): /api/v1/definitions.json and find_definition ---------
RE_DEF_ANY = re.compile(r"^\d+(?:[.-]\d+)*(?:\.|\))\s*(?P<term>[^–()„“]{2,120}?)\s*(?:\((?:toliau|toliau vadinama\w*)\s*[–-]\s*"
                        r"(?P<short>[^)]{2,80})\))?\s+[–-]\s+(?P<meaning>\S.*)$", re.S)


def _clean(t: str | None) -> str | None:
    t = (t or "").strip(" ,„“\"")
    return t or None


def definitions_in(art) -> list[dict]:
    """The definitions one article (or point) makes, as shown today:
    - a law's definitions article ("Pagrindinės … sąvokos"): each part "N. Term (toliau – alias) – meaning";
    - a rule's definitions point ("3. Apraše vartojamos sąvokos:"): each sub-point "3.1. Term – meaning";
    - a concept named by an article's title and defined in its first part (CK 4.57 "Bešeimininkis daiktas": "1. …
      daiktas yra …"): kind "title", a candidate (feedback P12)."""
    title = (art.title or "").strip().rstrip(".")
    blocks = [b for b in art.blocks if b.kind in ("part", "point", "sub", "para") and b.text]
    if not blocks:
        return []
    out = []
    defs_article = bool(title and RE_DEFS_TITLE.search(title))
    defs_point = not defs_article and bool(re.search(r"\bsąvok", blocks[0].text[:200], re.I))
    if defs_article or defs_point:
        for b in blocks:
            if re.match(r"\d+\)", b.text) and (b.anchor or "").startswith("d"):
                continue  # "1)" inside a part is an item of one definition (VPĮ 2 str. 34 d.), not a term of its own
            if (m := RE_DEF_ANY.match(b.text)) and _seq(m.group("term")):
                out.append({"term": _clean(m.group("term")), "alias": _clean(m.group("short")),
                            "definition": m.group("meaning").strip(), "anchor": b.anchor, "kind": "definition"})
        return out
    if title and 1 <= len(title.split()) <= 5:
        first = re.sub(r"^\d+(?:\.\d+)*\.\s*", "", blocks[0].text)
        tw = _seq(title)
        bw = _seq(first)[:len(tw)]
        # the defining word right after the title's words ("Nutartis yra …", "Jungtinė hipoteka – …"), not somewhere later
        # ("Valdymo organas veikia …, kai yra …")
        toks = first.split()[: len(title.split()) + 3]
        verb = any(re.fullmatch(r"–|yra|laikom\w*|reiškia|pripažįstam\w*", w) for w in toks[len(title.split()) - 1:])
        if tw and len(bw) == len(tw) and all(same(x, y) for x, y in zip(tw, bw)) and verb:
            out.append({"term": title, "alias": None, "definition": first, "anchor": blocks[0].anchor, "kind": "title"})
    return out


def shard_key(term: str) -> str | None:
    """Which /api/v1/defs/<key>.json holds a term: the first two letters of its first word of 4+ letters (folded)."""
    s = _seq(term)
    return s[0][:2] if s else None


def shard_keys(row: dict) -> set[str]:
    """Every file a definition is listed in: its term's first and last (head) word, its alias's first word, so that
    "vartotojas" finds "Elektros energijos vartotojas" too."""
    keys = {shard_key(row["term"]), shard_key(row.get("alias") or "")}
    s = _seq(row["term"])
    if s:
        keys.add(s[-1][:2])
    return keys - {None}


# --- definitions by reference (feedback P10): "sąvokos suprantamos taip, kaip jos apibrėžtos … įstatyme" --------------
# A sentence that says where its act's terms are defined: "Kitos … sąvokos suprantamos taip, kaip jos apibrėžtos
# Lietuvos Respublikos elektros energetikos įstatyme", "… ši sąvoka atitinka Reglamento (ES) Nr. 1143/2014 … apibrėžtą
# sąvoką". The acts it names are matched by their names (each word may be inflected: "baudžiamojo kodekso" /
# "baudžiamajame kodekse"), and by an alias the act gives itself ("… įstatymu (toliau – Įstatymas)"). Names not on
# the site and EU acts are kept as written; "kituose įstatymuose" is only a flag. The text is never changed (D-002).
RE_REF_SENT = re.compile(r"(?:suprantam\w*|vartojam\w*|apibrėžiam\w*)\s*(?:taip|ta pačia reikšme),?\s+kaip\b"
                         r"|\bsąvok\w* atitinka\b|\batitinka\b[^.]{0,200}?\bapibrėžt\w* sąvok\w*", re.I)
RE_SENTENCE = re.compile(r"(?<!Nr)(?<!\b[a-z])\.\s+(?=[A-ZĄČĘĖĮŠŲŪŽ0-9])")
RE_WORDS = re.compile(r"[A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž0-9]+")
RE_LT_NAME = re.compile(r"Lietuvos Respublikos (?:[^\s,.;]+ ){1,12}?(?:įstatym|kodeks)\w*")
RE_EU = re.compile(r"\b(?:reglament|direktyv)\w*\s*(?:\((?:ES|EB|EEB|ES, Euratomas|Euratomas)\)\s*)?(?:Nr\.\s*)?"
                   r"(\d{2,4}/\d+)(?:/(?:ES|EB|EEB))?", re.I)
RE_OTHER = re.compile(r"\bkit(?:uose|ais|ų|ame)\s+(?:\w+\s+)?(?:įstatym|teisės akt|kodeks)\w*", re.I)
RE_ALIAS = re.compile(r"\(toliau\s*(?:vadinam\w*\s*)?[–-]\s*([^)]{2,80})\)")
_SEP = {"respublikos", "ir", "bei", "kaip", "jos", "ji", "jie", "jis", "taip", "pat", "atitinka", "nurodytos", "nurodyta"}


def _inflected(a: str, b: str) -> bool:
    """Two words of a name, in any case: equal, or a common prefix of all but the last 3 letters of the shorter (and
    at least 4): "baudžiamojo" / "baudžiamajame", "įstatymo" / "įstatyme"; not "energetikos" / "energijos"."""
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= max(4, min(len(a), len(b)) - 3)


class References:
    """Finds the sentences that define terms by reference, and the acts on the site they name.
    acts: {"genitive", "act" (its key), "name", "url"}."""

    def __init__(self, acts: list[dict]):
        self.acts = []
        for a in acts:
            words = [w.lower() for w in RE_WORDS.findall(a.get("genitive") or "")]
            if words:
                self.acts.append((words, a))
        self.acts.sort(key=lambda x: -len(x[0]))  # longest names first: "elektros energetikos" before "energetikos"

    def _matches(self, text: str, aliases: dict | None = None) -> list[tuple[int, int, dict]]:
        """(start, end, act) of each act named in `text`, longest names first, not overlapping."""
        toks = [(m.start(), m.end(), m.group(0)) for m in RE_WORDS.finditer(text)]
        low = [t[2].lower() for t in toks]
        taken: set[int] = set()
        out = []
        cands = list(self.acts) + [([w.lower() for w in RE_WORDS.findall(k)], a, k) for k, a in (aliases or {}).items()]
        for c in sorted(cands, key=lambda x: -len(x[0])):
            words, act = c[0], c[1]
            alias = c[2] if len(c) > 2 else None
            k = len(words)
            for i in range(len(toks) - k + 1):
                if any(j in taken for j in range(i, i + k)):
                    continue
                if not all(_inflected(w, x) for w, x in zip(words, low[i:i + k])):
                    continue
                if alias:  # "Įstatyme" (capital) is the alias; "kituose įstatymuose" is not
                    if toks[i][2][:1] != alias[:1]:
                        continue
                else:
                    prev = low[i - 1] if i else ""
                    gap = text[toks[i - 1][1]:toks[i][0]] if i else ""
                    if i and prev not in _SEP and "," not in gap and not prev.startswith(("apibrėž", "nustatyt", "vartojam")):
                        continue  # "energetikos įstatyme" inside a name not on the site
                taken.update(range(i, i + k))
                out.append((toks[i][0], toks[i + k - 1][1], act))
        return sorted(out, key=lambda x: x[0])

    def aliases(self, texts) -> dict[str, dict]:
        """The short names an act gives the acts it names: "… elektros energetikos įstatymu (toliau – Įstatymas)"."""
        out = {}
        for t in texts:
            for m in RE_ALIAS.finditer(t or ""):
                before = t[max(0, m.start() - 300):m.start()]
                hits = [h for h in self._matches(before) if len(before) - h[1] <= 60]
                name = m.group(1).strip(" „“\"")
                if hits and name[:1].isupper() and len(name.split()) <= 5:
                    out.setdefault(name, hits[-1][2])
        return out

    def find(self, text: str, aliases: dict | None = None) -> list[dict]:
        """Each sentence of a block that defines terms by reference: {"text", "terms" (null: all other terms), "acts",
        "not_on_site", "also_other_acts"}."""
        out = []
        sents = []
        for piece in RE_SENTENCE.split(text or ""):
            if sents and re.fullmatch(r"\d+(?:[.-]\d+)*", sents[-1]):
                sents[-1] += ". " + piece  # "30-3. Pagalbinis …": the part's number, not a sentence
            else:
                sents.append(piece)
        for sent in sents:
            m = RE_REF_SENT.search(sent)
            if not m or not re.search(r"sąvok", sent, re.I):
                continue
            if re.search(r"atitinka\s+(?:šio|šiame|šios)\b", sent):
                continue  # another act's concept that matches one of this act's own: not a definition from elsewhere
            hits = self._matches(sent, aliases)
            acts, seen = [], set()
            for _, _, a in hits:
                if a["url"] not in seen:
                    seen.add(a["url"])
                    acts.append({k: a[k] for k in ("act", "name", "url")})
            spans = [(s, e) for s, e, _ in hits]
            free = lambda s, e: not any(s < he and hs < e for hs, he in spans)  # noqa: E731
            missing = [x.group(0) for x in RE_LT_NAME.finditer(sent) if free(x.start(), x.end())]
            eu_seen = set()
            for x in RE_EU.finditer(sent):  # not "… kuriuo panaikinama Direktyva 95/46/EB": that one is gone
                if x.group(1) not in eu_seen and not re.search(r"panaikinam\w*\s*$|keičiam\w*\s*$", sent[max(0, x.start() - 40):x.start()]):
                    missing.append(x.group(0))
                eu_seen.add(x.group(1))
            other = bool(RE_OTHER.search(sent))
            if not acts and not missing and not other:
                continue  # "… kaip apibrėžta šio įstatymo 2 straipsnyje": the act's own definitions
            head = sent[:m.start()]
            terms = [t.strip() for t in re.findall(r"„([^“]{2,80})“", head)]
            if not terms and (d := re.match(r"^(?:\d+(?:[.-]\d+)*\.\s*)?([^–]{2,120}?)\s*(?:\(toliau[^)]*\)\s*)?[–-]\s+(?:ši )?sąvoka", sent)):
                terms = [d.group(1).strip()]
            out.append({"text": sent.strip(), "terms": terms or None, "acts": acts, "not_on_site": missing,
                        "also_other_acts": other})
        return out


# --- the concept graph (feedback S11): /api/v1/concepts.json, candidates -------------------------------------------
def concepts(terms: list[Term], definitions: dict[str, str], url_of, used: dict[str, list[str]], act: str, cite: str) -> list[dict]:
    """One row per defined term of an act: its URL, the articles that use it, and a broader term: the act's defined
    term its definition starts with ("Pažeidžiamas vartotojas – buitinis elektros energijos vartotojas, …"; words
    inflected; the longest such term). `definitions`: definition URL -> its text. An alias row joins its term's."""
    rows: dict[str, dict] = {}
    for t in terms:
        u = url_of(t)
        if not u:
            continue
        r = rows.setdefault(u, {"term": t.term, "aliases": [], "act": act, "cite": cite, "url": u, "broader": None,
                                "used_in": sorted(set(used.get(u, [])), key=_label_key)})
        if t.term != r["term"]:
            r["aliases"].append(t.term)
    for u, r in rows.items():
        seq = _seq(definitions.get(u, ""))
        best = None
        for t in terms:
            if url_of(t) == u or not _genus(t.stems, seq):
                continue
            if best is None or len(t.stems) > len(best.stems):
                best = t
        if best is not None:
            r["broader"] = {"term": best.term, "url": url_of(best)}
    return list(rows.values())


def _genus(stems: tuple, seq: list[str]) -> bool:
    """The definition starts with the term, in the nominative as the term is written: its first word first, its other
    words in order within the next few ("buitinis elektros energijos vartotojas" for "buitinis vartotojas"). Exact
    word forms: a genitive start ("elektros energijos tiekėjo … sutartis") names something else, not the genus."""
    if not seq or seq[0] != stems[0]:
        return False
    i = 1
    for w in stems[1:]:
        try:
            i = seq.index(w, i, len(stems) + 2) + 1  # "valstybė, kuri nėra valstybė narė" is not "valstybė narė"
        except ValueError:
            return False
    return True


def _label_key(label: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.-]", label))
