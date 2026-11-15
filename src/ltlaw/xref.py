"""Cross-reference links inside one act (ROADMAP Features 1): "šio kodekso 52 straipsnio 2 dalyje" → /…/str/52/#d2.

Only links whose target exists: the article (or point) is in the act, the part anchor is on its page. A flattened
superscript in the text ("211 straipsnio": 21¹ or 211?) is linked only when exactly one reading is an article of
the act. The words are never changed, only wrapped in a link (D-002); everything else is escaped.
Other acts in scope: "Lietuvos Respublikos darbo kodekso 52 straipsnio" → that act's article (class Others).
Lists and ranges of articles ("šio kodekso 52 ir 53 straipsniuose", "5–7 straipsnių") and of parts ("šio straipsnio
1 ir 2 dalyse", "šio kodekso 52 straipsnio 2–4 dalyse"): each number is linked (a range by its two ends).
"""
from __future__ import annotations

import re

from markupsafe import Markup, escape

from .numbers import candidates, split_roman

PART = r"(\d+(?:-\d+)?) dal(?:is|ies|į|imi|yje)\b"
POINT = r"(\d+(?:-\d+)?) punkt(?:as|o|ą|u|e)\b"
# "šio straipsnio 2 dalyje", "šio straipsnio 3 dalies 1 punkte"
RE_HERE = re.compile(rf"\bšio straipsnio {PART}(?: {POINT})?", re.I)
# "šio kodekso 52 straipsnio 2 dalyje", "šio Įstatymo 21-1 straipsnyje" (a flattened "211" is resolved below)
RE_ACT = re.compile(rf"\bšio (?:kodekso|įstatymo|statuto|reglamento|direktyvos|sprendimo) (\d+(?:\.\d+)?(?:-\d+)?[a-z]{{0,2}}) straipsn(?:is|io|į|iu|yje)\b(?: {PART})?(?: {POINT})?", re.I)
# lists and ranges: "šio kodekso 52 ir 53 straipsniuose", "šio įstatymo 5–7, 9 straipsnių" (each number is linked)
_NUM = r"\d+(?:\.\d+)?(?:-\d+)?"
RE_ACT_LIST = re.compile(rf"\bšio (?:kodekso|įstatymo|statuto|reglamento|direktyvos|sprendimo) ({_NUM}(?:(?:, | ir | bei |\s?–\s?){_NUM})+) "
                         r"straipsn(?:iai|ių|iams|ius|iais|iuose)\b", re.I)
# lists of parts: "šio straipsnio 1 ir 2 dalyse", "… 52 straipsnio 2–4 dalių" (plural forms only)
_PN = r"\d+(?:-\d+)?"
_PLIST = rf"({_PN}(?:(?:, | ir | bei |\s?–\s?){_PN})+) dal(?:ys|ių|ims|is|imis|yse)\b"
RE_HERE_LIST = re.compile(rf"\bšio straipsnio {_PLIST}", re.I)
RE_PARTS_AFTER = re.compile(rf" {_PLIST}")
# an EU act's own articles, named bare ("kaip nurodyta 6 straipsnio 1 dalyje", D-037): another act's article always has
# that act's name right before the number ("Reglamento (ES) 2019/1020 2 straipsnio", "SESV 290 straipsnį"), so a bare
# number is the act's own unless the word before it names a document, ends a citation (")", "2019/1020") or is a number
RE_EU_SELF = re.compile(rf"(?:(?<=\s)|^)(\d+[a-z]{{0,2}}) straipsn(?:is|io|į|iu|yje)\b(?: {PART})?")
OTHER_DOC = re.compile(r"(?i:reglament|direktyv|sprendim|sutart|veikim|konvencij|chartij|protokol|susitarim|kodeks|įstatym|"
                       r"nutarim|akt)\w*$|[)\d/]|^[A-ZĄČĘĖĮŠŲŪŽ]{2,}$")  # the last: an abbreviation ("SESV")
# rules approved by a resolution (KET): "Taisyklių 66 punkte", "šių Taisyklių 3.21 papunktyje"
RE_RULES = re.compile(r"\b(?:šių )?Taisyklių (\d+(?:-\d+)?(?:\.\d+(?:-\d+)?)*) (?:punkt|papunkt)\w*")


def resolve(token: str, labels) -> str | None:
    """'52' -> '52'; a flattened '211' -> '21-1' only if exactly one reading is an article of the act."""
    hits = {c.label() for c in candidates(split_roman(token)) if c.label() in labels}
    if token in labels and ("-" in token or "." in token):
        return token
    return hits.pop() if len(hits) == 1 else None


class Others:
    """References to other acts in scope: "Lietuvos Respublikos darbo kodekso 52 straipsnio" → DK 52, and without
    "Lietuvos Respublikos" when the name starts with a capital ("Energetikos įstatymo 23 straipsnio", the usual form in
    rules after the first mention; D-036): a capital never starts a name inside another ("atominės energetikos
    įstatymo" is not EĮ). Longest names first; article pages only (their part anchors depend on that act's build)."""

    def __init__(self, acts: list[dict]):
        # acts: {"genitive", "url" (the act's base URL), "seg", "labels"[, "eu_names"]}
        # EU acts (D-037) by their numbered names in any case ("Reglamento (ES) 2016/679", "… Tarybos reglamento (ES)
        # 2016/679"): a number names one act, so no other act's name can hide inside it
        self.by_eu = {n.lower(): a for a in acts for n in a.get("eu_names") or []}
        eu = sorted(self.by_eu, key=len, reverse=True)
        self.re_eu = re.compile(r"\b(?i:(" + "|".join(re.escape(n) for n in eu) + r"))(?: \([^()]{2,80}\))?"
                                r" (\d+[a-z]{0,2}) straipsn(?:is|io|į|iu|yje)\b") if eu else None
        acts = [a for a in acts if not a.get("eu_names")]
        self.by_gen = {a["genitive"].lower(): a for a in acts if a.get("genitive") and a.get("seg") == "str"}
        names = sorted(self.by_gen, key=len, reverse=True)
        full = "|".join(re.escape(n) for n in names)
        bare = "|".join(re.escape(n[:1].upper() + n[1:]) for n in names)
        self.re = re.compile(r"(?:\b(?i:Lietuvos Respublikos) (?i:(" + full + r"))|(?<![Rr]espublikos )\b(" + bare + r"))"
                             r"(?: \(?Nr\. [^\s)]+\)?)? (\d+(?:\.\d+)?(?:-\d+)?) straipsn(?:is|io|į|iu|yje)\b") if names else None

    def find(self, text: str):
        if self.re_eu is not None:
            for m in self.re_eu.finditer(text):
                act = self.by_eu[m.group(1).lower()]
                lab = resolve(m.group(2), act["labels"])
                if lab:
                    yield m.start(), m.end(), f"{act['url']}str/{lab}/"
        if self.re is None:
            return
        for m in self.re.finditer(text):
            act = self.by_gen.get((m.group(1) or m.group(2)).lower())
            lab = resolve(m.group(3), act["labels"]) if act else None
            if lab:
                yield m.start(), m.end(), f"{act['url']}str/{lab}/"


class Linker:
    """Links for one act. `anchors`: article label -> the anchors on its page ("d2", "d3-p1", "p3.2")."""

    def __init__(self, base: str, seg: str, anchors: dict[str, set[str]], points: bool = False, others: Others | None = None,
                 sink: list | None = None, eu: bool = False):
        self.base, self.seg, self.anchors, self.points, self.others = base, seg, anchors, points, others
        self.eu = eu  # an EU act: its own articles are named bare (RE_EU_SELF)
        self.made = 0
        self.sink = sink  # (from URL, to URL) of every link to another article, for the agents' `related` (D-036)

    def label(self, token: str) -> str | None:
        return resolve(token, self.anchors)

    def _part(self, label: str, part: str | None, point: str | None) -> str:
        if not part:
            return ""
        have = self.anchors.get(label, set())
        for a in ([f"d{part}-p{point}"] if point else []) + [f"d{part}"]:
            if a in have:
                return "#" + a
        return ""

    def _part_list(self, label: str, m: re.Match, url: str) -> list[tuple[int, int, str]]:
        """Each part number of a list that has an anchor on `label`'s page (m.group(1) is the list)."""
        have = self.anchors.get(label, set())
        return [(m.start(1) + n.start(), m.start(1) + n.end(), f"{url}#d{n.group(0)}")
                for n in re.finditer(_PN, m.group(1)) if f"d{n.group(0)}" in have]

    def html(self, text: str, here: str, anchor: str | None = None, record: bool = False) -> Markup:
        """`record`: the page's own text (not an older wording shown below it): its links go to `sink`."""
        spans: list[tuple[int, int, str]] = []
        for m in RE_HERE.finditer(text):
            frag = self._part(here, m.group(1), m.group(2))
            if frag:
                spans.append((m.start(), m.end(), frag))
        for m in RE_HERE_LIST.finditer(text):
            spans += self._part_list(here, m, "")
        if not self.points:
            for m in RE_ACT_LIST.finditer(text):
                for n in re.finditer(_NUM, m.group(1)):
                    lab = self.label(n.group(0))
                    if lab:
                        spans.append((m.start(1) + n.start(), m.start(1) + n.end(), f"{self.base}{self.seg}/{lab}/"))
            for m in RE_ACT.finditer(text):
                lab = self.label(m.group(1))
                if lab:
                    url = f"{self.base}{self.seg}/{lab}/"
                    spans.append((m.start(), m.end(), url + self._part(lab, m.group(2), m.group(3))))
                    if not m.group(2) and (pl := RE_PARTS_AFTER.match(text, m.end())):
                        spans += self._part_list(lab, pl, url)
        else:
            for m in RE_RULES.finditer(text):
                tok = m.group(1)
                top = self.label(tok.split(".")[0])
                if top:
                    sub = "#p" + tok if "." in tok and "p" + tok in self.anchors.get(top, set()) else ""
                    spans.append((m.start(), m.end(), f"{self.base}{self.seg}/{top}/{sub}"))
        if self.eu:
            for m in RE_EU_SELF.finditer(text):
                head = text[:m.start()]
                if head.count("„") > head.count("“"):
                    continue  # inside a quoted wording of another act it amends: that act's article
                before = [w for w in head.split() if not re.fullmatch(r"\d+\.|[a-z]{1,3}\)|\(\w{1,4}\)", w)][-1:] \
                    if not re.fullmatch(r"\s*(?:\d+\.|[a-z]{1,3}\)|\(\w{1,4}\))\s*", head) else []  # "4. 2 straipsnio": the part's number
                lab = m.group(1) if m.group(1) in self.anchors else None
                if lab and lab != here and not (before and OTHER_DOC.search(before[-1].rstrip(",;:"))):
                    spans.append((m.start(), m.end(), f"{self.base}{self.seg}/{lab}/" + self._part(lab, m.group(2), None)))
        if self.others is not None:
            spans += list(self.others.find(text))
        if not spans:
            return Markup(escape(text))
        out, pos = [], 0
        for s, e, href in sorted(spans):
            if s < pos:
                continue  # overlapping matches: the first wins
            out += [str(escape(text[pos:s])), f'<a class="xref" href="{escape(href)}">{escape(text[s:e])}</a>']
            pos = e
            self.made += 1
            if record and self.sink is not None and not href.startswith("#"):  # a part of the same article: not a reference
                self.sink.append((f"{self.base}{self.seg}/{here}/" + (f"#{anchor}" if anchor else ""), href))
        out.append(str(escape(text[pos:])))
        return Markup("".join(out))
