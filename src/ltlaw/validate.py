"""Check our parse of the open-data text against e-tar's HTML of the SAME version.

Same version means the legal text must be identical, so every difference is a parser defect
(or a source difference worth reporting). e-tar keeps <sup>, so it also checks superscript
decoding (21¹ vs 211).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parse import Act, Article, Segment, spaces


def norm(s: str) -> str:
    """Compare letters and digits only: quotes, dashes and spacing differ between the two renderings."""
    return re.sub(r"[^0-9a-ząčęėįšųūž]+", "", s.lower())


def article_text(a: Article) -> str:
    return " ".join([a.title] + [b.text for b in a.blocks])


def law_text(a: Article) -> str:
    """The article's own words: without the register's editorial notes ("TAR pastaba. …")."""
    return " ".join([a.title] + [b.text for b in a.blocks if b.kind != "editorial"])


@dataclass
class Report:
    act: str
    version: str
    articles_ours: int = 0
    articles_etar: int = 0
    missing: list[str] = field(default_factory=list)      # in e-tar, not in ours
    extra: list[str] = field(default_factory=list)        # in ours, not in e-tar
    text_diff: list[str] = field(default_factory=list)    # same label, different text
    heading_diff: list[str] = field(default_factory=list)
    variants_ours: int = 0
    variants_etar: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.extra or self.text_diff or self.heading_diff) \
            and self.variants_ours == self.variants_etar

    def summary(self) -> str:
        s = (f"{self.act:5s} v{self.version}: articles {self.articles_ours}/{self.articles_etar} "
             f"missing {len(self.missing)} extra {len(self.extra)} text-diff {len(self.text_diff)} "
             f"heading-diff {len(self.heading_diff)} variants {self.variants_ours}/{self.variants_etar}")
        return ("OK   " if self.ok else "FAIL ") + s


def _by_label(seg: Segment) -> dict[str, Article]:
    return {a.label: a for a in seg.articles}


def compare(act: str, ours: Act, etar: Act) -> Report:
    r = Report(act, f"{ours.version_from}..{ours.version_to or ''}")
    o, e = ours.main, etar.main
    O, E = _by_label(o), _by_label(e)
    r.articles_ours, r.articles_etar = len(O), len(E)
    r.missing = [k for k in E if k not in O]
    r.extra = [k for k in O if k not in E]
    for k in O.keys() & E.keys():
        a, b = O[k], E[k]
        if len(a.duplicates) != len(b.duplicates):
            r.text_diff.append(k)
            continue
        for va, vb in zip([a, *a.variants, *a.duplicates], [b, *b.variants, *b.duplicates]):
            if norm(article_text(va)) != norm(article_text(vb)):
                r.text_diff.append(k)
                break
    ao = [(x.num, norm(x.title + " ".join(b.text for b in x.blocks))) for x in o.annexes]
    ae = [(x.num, norm(x.title + " ".join(b.text for b in x.blocks))) for x in e.annexes]
    if ao != ae:
        r.heading_diff.append(f"annexes ours {[x[0] for x in ao]} etar {[x[0] for x in ae]} "
                              f"text-equal {[x == y for x, y in zip(ao, ae)]}")
    r.variants_ours = sum(len(a.variants) for a in o.articles)
    r.variants_etar = sum(len(a.variants) for a in e.articles)
    ho = [(h.kind, h.num, norm(h.title)) for h in o.headings]
    he = [(h.kind, h.num, norm(h.title)) for h in e.headings]
    if ho != he:
        for i, (x, y) in enumerate(zip(ho, he)):
            if x != y:
                r.heading_diff.append(f"#{i}: ours {x[:2]} {x[2][:30]} | etar {y[:2]} {y[2][:30]}")
        if len(ho) != len(he):
            r.heading_diff.append(f"count ours {len(ho)} etar {len(he)}")
    r.warnings = o.warnings + [f"etar: {w}" for w in e.warnings]
    return r


def _n(s: str) -> str:
    return re.sub(r"\s+", " ", spaces(s)).strip()


def dropped_lines(text: str, act, signature_out: list | None = None) -> list[str]:
    """Source lines that no page renders (A10, A11). `shown` mirrors the templates: the main segment's
    articles (with variants and duplicates), headings and their notes, the preamble, the header notes,
    annexes with their histories, and a code's approval law. Signatures are deliberately not shown and
    are returned separately (`signature_out`). Lines are counted, so a duplicate that is shown once is
    caught. A parser bug that loses text shows up here even when the e-tar comparison agrees."""
    from collections import Counter
    from .parse import _bare_articles, _lines
    raw = _bare_articles(_lines(text))  # as parse() reads them ("1 straipsnis Dalykas" -> "1 straipsnis. Dalykas")
    if len(getattr(act, "documents", []) or []) > 1 and act.main is not None:
        # one of several approved documents (D-027): the resolution's own text and this document, not the others
        from .points import RE_APPROVED_DOC
        starts = [i for i, l in enumerate(raw) if RE_APPROVED_DOC.match(l)]
        mine = next((i for i, l in enumerate(raw) if l == act.main.title), None)
        if starts and mine is not None:
            begin = max((s for s in starts if s < mine), default=starts[0])
            end = min((s for s in starts if s > mine), default=len(raw))
            raw = raw[:starts[0]] + raw[begin:end]
    lines = [_n(l) for l in raw]
    shown: Counter = Counter()
    joined: list[str] = [_n(h) for h in act.header_notes]  # multi-line items rendered as one string
    main = act.main
    for a in main.articles:
        for v in [a, *a.variants, *a.duplicates]:
            shown.update(_n(b.text) for b in v.blocks)
            joined.append(_n(v.title))
    for h in main.headings:
        joined.append(_n(h.title))
        shown.update(_n(r) for r in h.remarks)
    for seg in act.segments:
        shown.update(_n(l) for l in seg.preamble)  # the act's, or a resolution's ("Vadovaudamasi … nutaria:")
    for x in main.annexes:
        shown.update(_n(b.text) for b in x.blocks)
        shown.update(_n(l) for l in x.history)
        joined += [_n(x.title), _n(x.header)]
    for seg in act.segments:
        if seg.kind == "approval":
            for a in seg.articles:
                shown.update(_n(b.text) for b in a.blocks)
                joined.append(_n(a.title))
    # "signature": the signing block itself (up to 8 lines, before any "Pakeitimai:"); what the parser put
    # after it is old amendment history (Žin.-era lists), excluded and counted apart; anything else counts
    sig, hist = Counter(), Counter()
    for seg in act.segments:
        k = next((j for j, l in enumerate(seg.signature) if _n(l) == "Pakeitimai:"), len(seg.signature))
        sig.update(_n(l) for l in seg.signature[:min(k, 8)])
        if k < len(seg.signature):
            hist.update(_n(l) for l in seg.signature[k:])
    big = "\n".join(joined)
    cut = len(lines)
    for k in range(len(lines) - 1, -1, -1):  # the act-level amendment list at the end (shown as notes)
        if lines[k] == "Pakeitimai:":
            cut = k
            break
    meta = re.compile(r"^(Suvestinė redakcija nuo|Įstatymas paskelbtas|Kodeksas paskelbtas|Konstitucija paskelbta|"
                      r"(?:Nutarimas|Įsakymas) paskelbtas|Nauja (?:nutarimo|įsakymo) redakcija nuo|Lietuvos Respublikos Vyriausybė$|nutarimas$|įsakymas$|"
                      r"Statutas paskelbtas|Konstitucinis įstatymas paskelbtas|konstituciniu įstatymu Nr\.|"
                      r"Nauja (įstatymo|kodekso) redakcija nuo|Redagavo:|Projektas|Vilnius|Įstatymas netenka galios|"
                      r"PATVIRTINTA|\d+(-\d+)? straipsnio redakcija nuo)|^(Vilnius, )?\d{4} ?m\. \w+ \d+ d\.|^Nr\.|^įstatymu Nr\.|^\(.*\)$", re.I)
    heading = re.compile(r"^[\wĄČĘĖĮŠŲŪŽąčęėįšųūž]+ (skyrius|skirsnis|dalis|knyga)\b|^[\d.]+(-\d+)? straipsnis\b", re.I)
    from .parse import REF, RE_ANNEX, RE_ART, _heading
    exact = set(joined)  # heading titles, annex headers and titles: an exact line match, any length
    titles = " ".join(_n(seg.title) for seg in act.segments)  # act/code titles: shown as the page title
    first = next((k for k, l in enumerate(raw) if RE_ART.match(l) or _heading(l)), len(raw))  # the header zone ends here
    out = []
    for k, l in enumerate(lines[:cut]):
        nxt = lines[k + 1] if k + 1 < len(lines) else ""
        if not l or set(l) <= set("_-– ") or REF.match(raw[k].strip()) or re.match(r"^Nr\.\s*[\w-]+(/\d+)?,\s*(\d{4}-|\d{2}\.\d{2}\.\d{2})", l):
            continue  # empty, a separator, or a note's reference line (shown as a link)
        if l in exact or RE_ANNEX.match(l) or (l.isupper() and l in titles):
            continue  # a heading or annex title, an annex header line, a title line
        if (k < first and (meta.match(l) or re.match(r"^[A-ZĄČĘĖĮŠŲŪŽ\s]+$", l) or l.startswith("("))) or \
                (len(l) < 45 and meta.match(l)):  # a code's "PATVIRTINTA / 2016 m. … / įstatymu Nr. …" block
            continue  # header zone: version line, publication, act title, adoption line
        if RE_ART.match(raw[k]) or _heading(raw[k]) or re.match(r"^\d+(-\d+)? straipsnio redakcija nuo", l):
            continue  # article and heading lines are shown in their own form
        if getattr(act, "unit", None) == "punktas" and re.match(r"^\d+(-\d+)?\. Neteko galios\b", l):
            continue  # a repealed point: its page's heading ("75 punktas. Neteko galios nuo …")
        if l.endswith(":") and (nxt.startswith("Nr.") or re.match(r"^[IVXL]+-\d+,\s*\d{4}-", nxt)
                                or nxt.startswith("TAR pastaba") or l == "Pakeitimai:"):
            continue  # a note label: rendered as the note it introduces
        if shown[l] > 0:
            shown[l] -= 1
            continue
        if sig[l] > 0 or hist[l] > 0:
            (sig if sig[l] > 0 else hist)[l] -= 1
            if signature_out is not None:
                signature_out.append(l)
            continue
        if not l.replace(" ", "").isdigit() and l in big and (len(l) >= 12 or any(j.endswith(l) for j in joined)):
            continue  # part of a multi-line title or header shown joined (a short last line: "… nuorašą")
        out.append(l)
    return out
