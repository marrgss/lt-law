"""Parse a TAR consolidated text (plain open-data text or e-tar HTML) into a tree.

Act
 └ Segment            approval law ("patvirtinimo įstatymas") and/or the main act (the code itself)
    └ Heading*        KNYGA > DALIS > SKYRIUS > SKIRSNIS (any may be absent)
       └ Article      "52 straipsnis. Nuotolinis darbas"
          └ Block     part "1." / point "1)" / sub-point "a)" / paragraph, each with notes

Notes are the editorial amendment references ("Straipsnio dalies pakeitimai:" + "Nr. …" lines)
and attach to the block, article or heading they follow. We never alter legal text: blocks
keep the source lines verbatim (whitespace normalised).
"""
from __future__ import annotations

import html as htmllib
import re
import unicodedata
from dataclasses import dataclass, field

import datetime as _dt

from .numbers import Num, Sequence, candidates, split_roman

# --- notes -----------------------------------------------------------------------------------
# "Nr. XV-1, 2025-06-01, …"; rarely the "Nr." is missing ("XI-1046, 2010-09-30, Žin., …", VIĮ)
REF = re.compile(r"^(?:Nr\.\s*|(?=[IVXL]+-\d+,\s*\d{4}-))([^,]+?)\s*,\s*(\d{4}[- ]\d{2}[- ]\d{2})(?:,\s*paskelbta TAR (\d{4}-\d{2}-\d{2}))?"
                 r"(?:,\s*i\.\s*k\.\s*(\S+))?")


@dataclass
class Ref:
    nr: str              # amending act number, e.g. XV-969 (or a Constitutional Court ruling id)
    adopted: str
    published: str | None
    tar_ik: str | None


@dataclass
class Note:
    label: str           # "Straipsnio dalies pakeitimai", "Papildyta straipsnio punktu", ...
    refs: list[Ref] = field(default_factory=list)

    @property
    def level(self) -> str:
        """Which node the note describes: article, part, point, heading or annex."""
        l = self.label.lower()
        if re.search(r"papunk", l):
            return "point"
        if re.search(r"punkt", l):
            return "point"
        if re.search(r"dal(ies|imi)\b", l) and "straipsni" in l or l.startswith("dalies"):
            return "part"
        if re.search(r"skyri|skirsn|knyg", l):
            return "heading"
        if "pried" in l:
            return "annex"
        return "article"


# --- tree --------------------------------------------------------------------------------------
@dataclass
class Block:
    kind: str            # part | point | sub | para | editorial
    num: str | None      # decoded label: "3-1" for 3¹, "a" for a)
    text: str
    notes: list[Note] = field(default_factory=list)
    anchor: str = ""     # id within the article page: d3-1, d3-1-p2, ...


@dataclass
class Article:
    num: Num
    title: str
    blocks: list[Block] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    path: list["Heading"] = field(default_factory=list)  # ancestors, outermost first
    # dated variants inside one consolidation ("53 straipsnio redakcija nuo 2025 m. sausio 1 d.:")
    valid_from: str | None = None
    valid_to: str | None = None
    variants: list["Article"] = field(default_factory=list)
    # the same article printed again with no dates (a source defect, e.g. VTAĮ 48): which applies is unknown
    duplicates: list["Article"] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.num.label()

    def variant_on(self, day: str) -> "Article":
        """The text that applies on `day` when the article carries dated variants."""
        for v in [self, *self.variants]:
            if (v.valid_from or "0000") <= day and (v.valid_to is None or day <= v.valid_to):
                return v
        return self

    @property
    def repealed(self) -> bool:
        return self.title.lower().startswith("neteko galios")

    def all_refs(self) -> list[Ref]:
        """Every amendment reference that touches this article, including its headings'."""
        out = [r for n in self.notes for r in n.refs]
        out += [r for b in self.blocks for n in b.notes for r in n.refs]
        out += [r for h in self.path for n in h.notes for r in n.refs]
        out += [r for d in self.duplicates for r in d.all_refs()]
        return out


@dataclass
class Heading:
    kind: str            # knyga | dalis | antraštinė dalis (EU) | skyrius | skirsnis
    num: str             # "I", "XIX-1", "1", "bendroji"
    title: str
    notes: list[Note] = field(default_factory=list)
    remarks: list[str] = field(default_factory=list)  # "TAR pastaba …" for the whole chapter/section

    @property
    def rank(self) -> int:
        return RANK[self.kind]


@dataclass
class Annex:
    num: str             # "1", "" for a single unnumbered annex
    header: str          # "Lietuvos Respublikos darbo kodekso priedas"
    title: str
    blocks: list[Block] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    history: list[str] = field(default_factory=list)  # the annex's own "Pakeitimai:" list (raw)


@dataclass
class Segment:
    kind: str            # approval | main
    title: str
    articles: list[Article] = field(default_factory=list)
    headings: list[Heading] = field(default_factory=list)
    annexes: list[Annex] = field(default_factory=list)
    signature: list[str] = field(default_factory=list)  # "Skelbiu šį ... įstatymą." + signatories
    tail: list[str] = field(default_factory=list)  # anything after the last article we couldn't place
    preamble: list[str] = field(default_factory=list)  # text between the title and the first heading/article
    warnings: list[str] = field(default_factory=list)


@dataclass
class Act:
    version_from: str | None
    version_to: str | None
    published: str | None
    title: str
    segments: list[Segment]
    amendments: list[dict]          # act-level "Pakeitimai:" list (nr, adopted, title, ...)
    rewrites: list[tuple[str, str]] = field(default_factory=list)  # "Nauja redakcija nuo D: Nr. X" (whole act replaced)
    expires: str | None = None      # header "Įstatymas netenka galios 2027-01-01:" (the whole act is repealed)
    header_notes: list[str] = field(default_factory=list)  # act-level notes before the version line (TAR pastaba …)
    prepared: str | None = None     # when the Chancellery prepared this consolidation, if known (Suvestine; set by callers)
    documents: list[str] = field(default_factory=list)  # a resolution's approved documents (titles), when it has several

    @property
    def main(self) -> Segment:
        return next((s for s in self.segments if s.kind == "main"), None) or \
            (self.segments[-1] if self.segments else Segment("main", self.title))


RANK = {"knyga": 1, "dalis": 2, "antraštinė dalis": 3, "skyrius": 4, "skirsnis": 5, "poskirsnis": 6}
ORD = {w: i for i, ws in enumerate([
    (), ("PIRMASIS", "PIRMOJI"), ("ANTRASIS", "ANTROJI"), ("TREČIASIS", "TREČIOJI"), ("KETVIRTASIS", "KETVIRTOJI"),
    ("PENKTASIS", "PENKTOJI"), ("ŠEŠTASIS", "ŠEŠTOJI"), ("SEPTINTASIS", "SEPTINTOJI"), ("AŠTUNTASIS", "AŠTUNTOJI"),
    ("DEVINTASIS", "DEVINTOJI"), ("DEŠIMTASIS", "DEŠIMTOJI"), ("VIENUOLIKTASIS", "VIENUOLIKTOJI"),
    ("DVYLIKTASIS", "DVYLIKTOJI"), ("TRYLIKTASIS", "TRYLIKTOJI"), ("KETURIOLIKTASIS", "KETURIOLIKTOJI"),
    ("PENKIOLIKTASIS", "PENKIOLIKTOJI"), ("ŠEŠIOLIKTASIS", "ŠEŠIOLIKTOJI"), ("SEPTYNIOLIKTASIS", "SEPTYNIOLIKTOJI"),
    ("AŠTUONIOLIKTASIS", "AŠTUONIOLIKTOJI"), ("DEVYNIOLIKTASIS", "DEVYNIOLIKTOJI"), ("DVIDEŠIMTASIS", "DVIDEŠIMTOJI"),
]) for w in ws}

UPPER = "A-ZĄČĘĖĮŠŲŪŽ"


def ordinal_number(word: str) -> int | None:
    """'KETVIRTASIS' -> 4, 'DVIDEŠIMT KETVIRTASIS' -> 24, 'TRISDEŠIMTASIS' -> 30 (masculine/feminine nominative)."""
    w = word.upper().split()
    if len(w) == 2 and w[0] in TENS_WORDS and w[1] in ORD:
        return TENS_WORDS[w[0]] + ORD[w[1]]
    if len(w) == 1:
        if w[0] in ORD:
            return ORD[w[0]]
        for t, v in TENS_WORDS.items():  # "TRISDEŠIMTASIS", "KETURIASDEŠIMTOJI"
            if w[0] in (t + "ASIS", t + "OJI"):
                return v
    return None
TENS = TENS_WORDS = {"DVIDEŠIMT": 20, "TRISDEŠIMT": 30, "KETURIASDEŠIMT": 40, "PENKIASDEŠIMT": 50, "ŠEŠIASDEŠIMT": 60}
# "DVIDEŠIMT KETVIRTASIS SKIRSNIS", "DVIDEŠIMT ŠEŠTASIS1 SKIRSNIS", "… AŠTUNTASIS(1) …" (Seimo statutas)
RE_HEAD = re.compile(rf"^(?:([IVXLC]+(?:-?\d+)?)|((?:(?:{'|'.join(TENS)}) )?[{UPPER}][a-ząčęėįšųūž{UPPER}]+?)-?\(?(\d*)\)?) "
                     rf"(KNYGA|DALIS|SKYRIUS|SKIRSNIS)\.?(?: (.+))?$", re.I)
RE_VARIANT = re.compile(r"^(\d+(?:\.\d+)?(?:-\d+)?) straipsnio redakcija nuo (\d{4}) m\. (\w+) (\d{1,2}) d\."
                        r"(?: iki (\d{4}) (?:m\. )?(\w+) (\d{1,2}) d\.)?:$")
MONTHS = {m: i + 1 for i, m in enumerate(["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", "liepos",
                                          "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"])}
# "52 straipsnis. Title" or a bare "1 straipsnis" (Konstitucija); a stray opening quote left from the amending law
# ("„11³ straipsnis. …", SEAKĮ on e-tar 2026) is not part of the heading
# what only eurlex.to_text knows, from the XHTML's classes, before a line:
QUOTED = "\u2060"  # a line of the article's text that would read as a heading or an article ("50a straipsnis" quoted in CRR 520)
HEADING = "\u2063"  # a heading with no number of its own ("RŪŠIŲ APSAUGA", Habitats 92/43)
RE_ART = re.compile(r"^„?(\d+(?:\.\d+)?(?:-\d+)?(?:-?[a-z]{1,2})?) straipsnis(?:\.\s*(.*)|)$")  # "4a": EU acts (D-037)
RE_PART = re.compile(r"^(\d+(?:-\d+)?)\.\s+(.*)$")
RE_POINT = re.compile(r"^(\d+(?:-\d+)?)\)\s+(.*)$")
RE_SUB = re.compile(r"^([a-zščž])\)\s+(.*)$")
RE_VERSION = re.compile(r"^Suvestinė redakcija nuo (\d{4}-\d{2}-\d{2})(?: iki (\d{4}-\d{2}-\d{2}))?")
RE_APPROVED = re.compile(r"^PATVIRTINT(A|AS|I|OS)$")
RE_ANNEX = re.compile(r"^(?:(?:įstatymo|kodekso|statuto) )?(?:(\d+(?:-\d+)?|[IVXLC]+(?:\.?[A-Z])?|[A-Z]) )?(?:priedas|priedėlis)$", re.I)  # "I PRIEDAS": EU  # GPMĮ: "… įstatymo priedas"


def _day_before(day: str) -> str:
    return (_dt.date.fromisoformat(day) - _dt.timedelta(days=1)).isoformat()


def _annex_num(num: str, before: list) -> str:
    """A flattened superscript in an annex number: "21 priedas" right after "2 priedas" is 2¹ ("2-1"), as e-tar
    shows (LBĮ); "12" after "11" is just 12."""
    if not num.isdigit() or not before or not before[-1].num:
        return num
    base = before[-1].num.split("-")[0]
    if base.isdigit() and int(num) != int(base) + 1 and num.startswith(base) and len(num) > len(base) and num[len(base)] != "0":
        return f"{base}-{num[len(base):]}"
    return num


def _appendix_nums(annexes: list) -> None:
    """Appendices numbered again in each annex (the taxonomy act 2021/2139: annexes I and II both have appendices A–D)
    get their annex's number ("I-A", "II-A"), so their pages don't collide; where every appendix number is unique (REACH
    XVII's 1–12) they keep their own, as before."""
    apps = [a for a in annexes if "priedėlis" in a.header.lower()]
    if len({a.num for a in apps}) == len(apps):
        return
    parent = ""
    for a in annexes:
        if "priedėlis" not in a.header.lower():
            parent = a.num
        elif parent and a.num:
            a.num = f"{parent}-{a.num}"


def _cf_email(hexs: str) -> str:
    """Cloudflare's email obfuscation on e-tar pages ("[email protected]", data-cfemail): the address back."""
    try:
        k = int(hexs[:2], 16)
        return "".join(chr(int(hexs[i:i + 2], 16) ^ k) for i in range(2, len(hexs), 2))
    except ValueError:
        return ""


def html_to_text(raw: str) -> str:
    """e-tar HTML -> the same line format as the open-data text, with <sup>n</sup> as '-n'."""
    # e-tar serves addresses hidden by Cloudflare ("[email protected]"): the open data has them plain (PESTA 5, B57)
    raw = re.sub(r'<(a|span)[^>]*data-cfemail="([0-9a-fA-F]+)"[^>]*>.*?</\1>', lambda m: _cf_email(m.group(2)), raw, flags=re.S)
    raw = re.sub(r'<a[^>]*href="/cdn-cgi/l/email-protection#([0-9a-fA-F]+)"[^>]*>.*?</a>', lambda m: _cf_email(m.group(1)), raw, flags=re.S)
    # an empty superscript ("158<sup>1</sup>.<sup> </sup>", JARN; "6<sup>5</sup>.<sup>&nbsp;</sup>", EĮPTA)
    raw = re.sub(r"<sup[^>]*>(?:\s|&nbsp;|&#160;|\xa0)*</sup>", " ", raw, flags=re.I)
    raw = re.sub(r"<sup[^>]*>\s*([^<]+?)\s*</sup>", r"-\1", raw, flags=re.I)
    raw = re.sub(r"(\d-\d+)(straipsn)", r"\1 \2", raw)  # "40<sup>1</sup>straipsnis" (no space, TeisĮ on e-tar)
    raw = re.sub(r"</?(p|div|br|tr|li|h\d)[^>]*>", "\n", raw, flags=re.I)
    return htmllib.unescape(re.sub(r"<[^>]+>", "", raw))


SPACES = str.maketrans({c: " " for c in "\xa0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"})


def spaces(s: str) -> str:
    """Every no-break, narrow, thin or figure space as a plain one ("1\u202fstraipsnis", XV-734; B49)."""
    return s.translate(SPACES)


def _lines(text: str) -> list[str]:
    out = []
    # NFC: a few texts spell a letter as base + combining mark ("Šis" as S + caron, 42 amending laws): the same
    # words, but no pattern would match them
    # "part_<32 hex>_end": the register's marker where a document part ends (383 stored texts): not law text; inside a
    # point it was shown as words (SEANM 31), and e-tar's copy has another id, so the validators saw a change
    text = re.sub(r"part_[0-9a-f]{32}_end", "", text)
    for l in spaces(unicodedata.normalize("NFC", text)).split("\n"):
        l = re.sub(r"[ \t]+", " ", l).strip()
        if l:
            out.append(l)
    return _unwrap(out)


def _unwrap(lines: list[str]) -> list[str]:
    """A consolidation printed hard-wrapped (SLTKĮ, VGTDĮ: "1" / "straipsnis. Įstatymo paskirtis" / "Šis įstatymas" /
    "nustato …"; half the lines start in lowercase, against under a tenth elsewhere): its lines joined back into
    paragraphs. Only such texts: an article number alone on its line before "straipsnis" twice or more, and over a
    quarter of the lines starting in lowercase."""
    lone = sum(1 for k, l in enumerate(lines[:-1]) if re.fullmatch(r"\d+(?:-\d+)?", l) and lines[k + 1].startswith("straipsnis"))
    low = sum(1 for l in lines if re.match(r"[a-ząčęėįšųūž]", l))
    if lone < 2 or low <= len(lines) / 4:
        return lines
    out: list[str] = []
    for l in lines:
        if out and re.fullmatch(r"\d+(?:-\d+)?", out[-1]) and l.startswith("straipsnis"):
            out[-1] += " " + l  # "1" / "straipsnis. …"
        elif out and not re.search(r"[.!?;:“\"]$", out[-1]) and not out[-1].isupper() \
                and not re.match(r"\d+(?:-\d+)? straipsnis", out[-1]) and not l.isupper() \
                and not re.match(r"\d|[a-ząčęėįšųūž]{1,2}\)|„?\d+(?:-\d+)? straipsnis", l):
            out[-1] += " " + l  # a sentence going on ("Šis įstatymas" / "nustato …", "Pagal šį" / "Įstatymą …"), not a
            # new part ("2. …", "1) …", "a) …") or a title
        elif out and l.isupper() and out[-1].isupper() and not re.search(r"(SKYRIUS|SKIRSNIS|DALIS|KNYGA)$", out[-1]):
            out[-1] += " " + l  # a heading over two lines ("BENDROSIOS" / "NUOSTATOS")
        else:
            out.append(l)
    return out


_TITLE_END = re.compile(r"(ĮSTATYMAS|KODEKSAS|STATUTAS|K\s*O\s*N\s*S\s*T\s*I\s*T\s*U\s*C\s*I\s*J\s*A|"
                        r"Į\s*S\s*T\s*A\s*T\s*Y\s*M\s*A\s*S)\s*$")


def _preamble(title_lines: list[str]) -> list[str]:
    """The Constitution's "LIETUVIŲ TAUTA, …" and any other preamble: the lines after the act's
    title, minus the adoption line, date, number and place. Empty for ordinary laws."""
    ends = [k for k, l in enumerate(title_lines) if _TITLE_END.search(l)]
    if not ends:
        return []
    rest, skip = [], False
    for l in title_lines[ends[0] + 1:]:
        if re.match(r"^(TAR pastaba|Nauja (įstatymo|kodekso) redakcija|Įstatymas paskelbtas|Kodeksas paskelbtas)", l):
            skip = True  # a note with its reference lines: shown as a header note, not a preamble
            continue
        if skip and (l.startswith("Nr.") or re.match(r"^Lietuvos Respublikos (Seimas|Vyriausybė)", l)
                     or re.search(r"(įstatymo|kodekso).*(pakeitimo|papildymo).*įstatymas$", l)):
            continue
        skip = False
        if not re.match(r"^\(.*\)$|^\d{4} m\.|^Nr\.|^Vilnius$|^įstatymu Nr", l):
            rest.append(l)
    return rest if sum(len(re.findall(r"[a-ząčęėįšųūž]{4,}", l)) for l in rest) >= 8 else []


_HEADER_SPECIFIC = re.compile(r"^(Lietuvos Respublikos[a-ząčęėįšųūž ,-]*|[a-ząčęėįšųūž ,-]*(įstatymo|kodekso|statuto|nutarimo|įsakymo)"
                              r"( Nr\. [IVXL]+-\d+)?|\d{4} ?m\. [a-ząčęėįšųūž]+ \d{1,2} d\.)$")
_HEADER_LINE = re.compile(r"^(Lietuvos Respublikos[a-ząčęėįšųūž ,-]*|[a-ząčęėįšųūž ,-]*(įstatymo|kodekso|statuto|nutarimo|įsakymo)"
                          r"( Nr\. [IVXL]+-\d+)?|\d{4} ?m\. [a-ząčęėįšųūž]+ \d{1,2} d\.|[a-ząčęėįšųūž][a-ząčęėįšųūž ,-]+)$")
# (the last form: a header split mid-phrase, "asmens duomenų teisinės apsaugos" / "įstatymo")


def _header_line(l: str) -> bool:
    """A line of an annex header ("Lietuvos Respublikos / akcizų įstatymo / 2002 m. … / 2 priedas"); never a
    whole title in the nominative ("… įstatymo pakeitimo įstatymas") or a person's name."""
    l = l.strip()
    return bool(_HEADER_LINE.match(l)) and not re.search(r"(įstatymas|kodeksas|nutarimas|įsakymas|statutas)$", l)


def _titleish(l: str) -> bool:
    """A title line: upper case, mostly upper case ("TEISĖS GAUTI INFORMACIJĄ IR duomenų …"), or spaced out
    ("k o d e k s a s", "Į S T A T Y M A S")."""
    if re.match(r"^Nr\.|^\d", l.strip()):
        return False  # "Nr. VIII-940, 1998.11.24, Žin., …" is metadata, not a title
    letters = [c for c in re.sub(r"\b[IVXLC]+\b", "", l) if c.isalpha()]
    # a title in lower case but for its document type ("suskystintų … pajėgumų nustatymo  TVARKOS APRAŠAS", No. 1354)
    typed = bool(re.search(r"\b(?:APRAŠAS|TAISYKLĖS|NUOSTATAI|METODIKA|REGLAMENTAS|TVARKA|SĄLYGOS|REIKALAVIMAI)\s*$", l.strip()))
    return _is_upper(l) or typed or bool(re.fullmatch(r"([^\W\d] ){3,}[^\W\d]", l.strip())) or \
        (len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) >= 0.6)


def _is_upper(l: str) -> bool:
    letters = re.sub(rf"[^a-ząčęėįšųūž{UPPER}]", "", l)
    return len(letters) >= 3 and letters == letters.upper()


def _heading(l: str) -> tuple[str, str] | None:
    """'XIX1 SKYRIUS' -> ('skyrius', 'XIX-1'); 'PIRMASIS SKIRSNIS' -> ('skirsnis', '1'); 'BENDROJI DALIS' -> ('dalis', 'bendroji')."""
    if m := re.fullmatch(r"(\d+[A-Z]?) SKIRISNIS", l):  # EUR-Lex's misprint (CRR)
        return "skirsnis", m.group(1)
    if m := re.fullmatch(rf"([{UPPER}]+ [A-Z]) DALIS", l):  # "SEPTINTA A DALIS" (CRR)
        return "dalis", m.group(1).lower()
    if m := re.fullmatch(r"(\d+[A-Z]?|[IVXLC]+[A-Z]) (SKIRSNIS|SKYRIUS|DALIS)", l):  # EU acts number sections in figures, in
        # capitals (D-037), some with a letter inserted later ("3A SKYRIUS", EMIR)
        return m.group(2).lower(), m.group(1)
    if m := re.fullmatch(r"([IVXLC]+[A-Z]?|\d+[A-Z]?) POSKIRSNIS", l):  # below a section (2009/138, 2013/36, 2015/849)
        return "poskirsnis", m.group(1)
    if m := re.fullmatch(r"([IVXLC]+[A-Z]?|\d+[A-Z]?) ANTRAŠTINĖ DALIS", l):  # an EU act's title ("II ANTRAŠTINĖ DALIS", "IVA …",
        return "antraštinė dalis", m.group(1)  # Cybersecurity Act): above its chapters, below a part ("I DALIS", SOGL)
    m = RE_HEAD.match(l)
    if not m:
        return None
    roman, word, sup, kind, inline = m.groups()
    if inline and not _is_upper(inline):
        return None  # "II skyrius taikomas ..." is a sentence, not a heading
    kind = kind.lower()
    if roman and re.fullmatch(r"[IVXLC]+(?:-?\d+)?", roman):
        return kind, split_roman(roman) if "-" not in roman else roman
    word = (word or roman).upper()
    n = ordinal_number(word)
    if n is None:
        return kind, word.lower()
    return kind, f"{n}-{sup}" if sup else str(n)


def _parse_amendment_list(lines: list[str]) -> list[dict]:
    out, cur = [], None
    for l in lines:
        if re.fullmatch(r"\d+\.", l):
            cur = {"n": int(l[:-1]), "issuer": None, "nr": None, "adopted": None, "tar_ik": None, "title": ""}
            out.append(cur)
        elif cur is None:
            continue
        elif cur["issuer"] is None:
            cur["issuer"] = l
        elif cur["nr"] is None and l.startswith("Nr."):
            m = REF.match(l)
            if m:
                cur["nr"], cur["adopted"], _, cur["tar_ik"] = m.group(1), m.group(2), m.group(3), m.group(4)
            else:
                cur["nr"] = l
        else:
            cur["title"] = (cur["title"] + " " + l).strip()
    return out


def _next_article(cur, token: str) -> bool:
    """Is `token` the article right after `cur` (cur + 1, or an inserted one: 66a, 66¹)?"""
    try:
        cands = candidates(split_roman(token))
    except ValueError:
        return False
    return any(c > cur and c.book == cur.book and c.base <= cur.base + 1 for c in cands)


RE_ART_BARE = re.compile(r"^(\d+(?:-\d+)?) straipsnis ([A-ZĄČĘĖĮŠŲŪŽ].*)$")


def _bare_articles(lines: list[str]) -> list[str]:
    """"1 straipsnis Dalykas ir apimtis": article headings without the period, as in the TSOs' methodologies that VERT
    approves (PORFPSDR, O3E-12: only the untitled "6 straipsnis" was read, the 18 others folded into it). Read as the
    usual "1 straipsnis. Dalykas ir apimtis" only where the whole document is written so (at least 3, the first is 1,
    more than the usual form), so that a sentence starting "5 straipsnis Lietuvos ..." elsewhere is left alone."""
    bare = {i for i, l in enumerate(lines) if RE_ART_BARE.match(l)}
    if len(bare) < 3 or len(bare) <= sum(1 for l in lines if RE_ART.match(l)) \
            or RE_ART_BARE.match(lines[min(bare)]).group(1) != "1":
        return _lower_sections(lines)
    out = [RE_ART_BARE.sub(r"\1 straipsnis. \2", l) if i in bare else l for i, l in enumerate(lines)]
    for i in range(len(out) - 2, -1, -1):  # "6 straipsnis" / "Bendrosios pareigos": its title on the next line
        if re.fullmatch(r"\d+(?:-\d+)? straipsnis", out[i]) and len(out[i + 1]) < 100 and out[i + 1][:1].isupper() \
                and not out[i + 1].endswith((".", ":", ";")) and not re.match(r"^\d", out[i + 1]):
            out[i:i + 2] = [f"{out[i]}. {out[i + 1]}"]
    while out and set(out[-1]) <= {"_", " "}:  # the closing rule "____": not the last article's text
        out.pop()
    return _lower_sections(out)


def _lower_sections(lines: list[str]) -> list[str]:
    """"1 skirsnis" / "Bendro kitos paros … procedūros": sections numbered in lower case, each with its title on the
    next line and an article after it (RMM, O3E-43), read as an EU act's "1 SKIRSNIS"; only where they run 1, 2, … (at
    least 2). (The AI Act's annex XI has "1 skirsnis" / its title / text: left alone.)"""
    at = [i for i in range(len(lines) - 2) if re.fullmatch(r"\d+ skirsnis", lines[i]) and len(lines[i + 1]) < 150
          and lines[i + 1][:1].isupper() and not lines[i + 1].endswith((".", ":", ";")) and RE_ART.match(lines[i + 2])]
    if len(at) < 2 or [int(lines[i].split()[0]) for i in at] != list(range(1, len(at) + 1)):
        return lines
    return [l.upper() if i in at else l for i, l in enumerate(lines)]


_STAMP_END = re.compile(r"\b(nutarimu|įsakymu|įstatymu|sprendimu)\s+Nr\.\s*\S+$", re.I)  # "… nutarimu Nr. O3E-59"
_RESOLVES = re.compile(r"(?:n ?u ?t ?a ?r ?i ?a|į ?s ?a ?k ?a ?u)\s*:$")
_SIGNER = re.compile(r"^\S+( \S+)? (pirminink\w*|ministr\w*|direktor\w*|vadov\w*)\b.{0,60}$|^(Komisijos|Tarybos) (pirminink|nar)\w*\b.{0,60}$", re.I)


def _resolution_body(title_lines: list[str]) -> tuple[list[str], list[str]] | None:
    """The resolution's text before "PATVIRTINTA", from its "… nutaria:" / "… įsakau:" line on, and its signer's
    line(s) apart; None without such a line (the header of a law)."""
    k = next((i for i, l in enumerate(title_lines) if _RESOLVES.search(l)), None)
    if k is None:
        return None
    body, sign = title_lines[k:], []
    while body and len(body[-1]) < 100 and _SIGNER.match(body[-1]):
        sign.insert(0, body.pop())
    return (body, sign) if body else None


def _recitals(lines: list[str]) -> bool:
    return sum(1 for l in lines if re.match(r"^\d+\. \S", l)) >= 2


def _tail_to_preamble(seg: "Segment", stamped: set, pending: dict, qualified: set) -> None:
    """In a document after an approval stamp ("PATVIRTINTA … nutarimu Nr. …"), the text before its first heading or
    article is its preamble (the TSOs' "atsižvelgdami į tai, kas išdėstyta toliau: 1. … 17. …" in the methodologies
    VERT approves: PORFPSDR, BTMMM), not text we couldn't place. `stamped`: ids of such segments."""
    if id(seg) in stamped and not seg.articles and not seg.headings and _recitals(seg.tail):  # not a stray date line
        seg.preamble, seg.tail = pending.pop(id(seg), []) + seg.preamble + seg.tail, []
        qualified.add(id(seg))


def parse(text: str, document: str | None = None) -> Act:
    """`document`: for a resolution approving several documents, the one to read (its title's first words, scope
    `document:`); the others are left out (D-027)."""
    lines = _bare_articles(_lines(text))
    from .points import implied_stamp, is_points, parse_points
    if is_points(lines):  # a Government resolution approving rules made of points (KET)
        return parse_points(text, document)
    if (stamped := implied_stamp(lines)) and is_points(stamped):  # the same, its stamp without "PATVIRTINTA"
        return parse_points("\n".join(stamped), document)
    lines0 = list(lines)
    vfrom = vto = published = None
    for l in lines[:12]:  # editorial residue ("Projektas ...", "Redagavo: ...") may come first
        if m := RE_VERSION.match(l):
            vfrom, vto = m.groups()
            break
    for l in lines[:12]:
        if m := re.search(r"paskelbtas: TAR (\d{4}-\d{2}-\d{2})", l):
            published = m.group(1)
    expires = next((m.group(1) for l in lines[:6]
                    if (m := re.match(r"(?:Įstatymas|Kodeksas|Statutas|Teisės aktas) netenka galios (\d{4}-\d{2}-\d{2})", l))), None)

    # cut the act-level amendment list ("Pakeitimai:" ... to the end)
    amend: list[dict] = []
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == "Pakeitimai:":
            amend = _parse_amendment_list(lines[i + 1:])
            lines = lines[:i]
            break

    segments: list[Segment] = []
    title_lines: list[str] = []
    seg: Segment | None = None
    art: Article | None = None
    stack: list[Heading] = []
    last_target: object = None          # where a following note attaches
    pending_label: str | None = None    # a note label waiting for its "Nr." lines
    art_seq = Sequence()
    part_seq = point_seq = None
    cur_part: str | None = None
    approved_mode = False               # inside the "PATVIRTINTA ..." header of an annexed code
    annex: Annex | None = None          # inside an annex after the last article
    annex_history = False               # inside an annex's own "Pakeitimai:" list
    signing = False                     # inside the promulgation/signature block
    pending_variant: tuple[str, str | None] | None = None
    variant_of: Article | None = None
    quote_left = 0                      # inside a wording quoted in an article: lines it may still take
    i = 0

    def new_segment(kind: str, title: str) -> Segment:
        nonlocal art_seq, art, stack, last_target
        nonlocal annex
        s = Segment(kind, title)
        segments.append(s)
        art_seq, art, stack, last_target, annex = Sequence(), None, [], None, None
        return s

    stamped: set[int] = set()
    qualified: set[int] = set()     # stamped documents with the TSOs' numbered recitals (VERT's methodologies)
    pending: dict[int, list] = {}   # lines after the stamp, kept until such recitals show up
    res_body = None
    after_stamp: list[str] = []  # lines read in approved_mode before the document's title
    while i < len(lines):
        l = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if l.startswith(QUOTED) and art is not None:
            last_target = Block("para", None, l[1:])
            art.blocks.append(last_target)
            i += 1
            continue
        if l.startswith(HEADING) and seg is not None:
            hd = Heading("skirsnis" if any(h.kind == "skirsnis" for h in stack) else "skyrius", "", l[1:])
            while stack and stack[-1].rank >= hd.rank:
                stack.pop()
            stack.append(hd)
            seg.headings.append(hd)
            art, last_target = None, hd
            quote_left = 0
            i += 1
            continue
        # a wording quoted in an article ("Pakeisti … 10 straipsnį ir jį išdėstyti taip:" / "„10 straipsnis. …" … "“"),
        # SŽNSĮ 143 and its older versions quoting articles 6–13: text of the quoting article up to the closing quote,
        # never articles or headings of the act (at most 400 lines, should a closing quote be missing)
        if art is not None and annex is None and not quote_left and l.startswith("„") and i and lines[i - 1].rstrip().endswith(":"):
            quote_left = 400
        # an unclosed quote ends at the act's own next article: unquoted, numbered right after the quoting one (an EU act's
        # "„72. … (*1)." amending an annex, never closed in EUR-Lex: CRA 66–67, D-037); SŽNSĮ quotes 6–13 from 143
        if quote_left and (mq := RE_ART.match(l)) and not l.startswith("„") and art is not None and \
                _next_article(art.num, mq.group(1)):
            quote_left = 0
        # … also at the act's own chapter heading right before that article ("XIV SKYRIUS" / "BAIGIAMOSIOS NUOSTATOS"
        # after the battery regulation's 92, whose quote EUR-Lex never closes)
        if quote_left and art is not None and l.isupper() and not l.startswith("„"):
            j = i
            while j < min(i + 3, len(lines)) and lines[j].isupper() and not lines[j].startswith("„"):
                j += 1
            if j < len(lines) and (mq := RE_ART.match(lines[j])) and _next_article(art.num, mq.group(1)):
                quote_left = 0
        if quote_left:
            art.blocks.append(Block("para", None, l))
            last_target = art.blocks[-1]
            quote_left = 0 if re.search(r"“\W{0,2}$", l) else quote_left - 1
            i += 1
            continue

        # --- notes: a label line followed by "Nr." references --------------------------------
        # (a "TAR pastaba" may sit between the label and its references: keep it as text, keep the refs)
        k = i + 1
        while k < len(lines) and lines[k].startswith("TAR pastaba") and k - i <= 3:
            k += 1
        if l.endswith(":") and k < len(lines) and REF.match(lines[k]):
            note = Note(l.rstrip(": ").strip())
            for j in range(i + 1, k):  # the TAR notes in between belong to the article text
                if art is not None:
                    art.blocks.append(Block("editorial", None, lines[j]))
            i = k
            while i < len(lines) and (m := REF.match(lines[i])):
                note.refs.append(Ref(m.group(1), m.group(2).replace(" ", "-"), m.group(3), m.group(4)))  # "2000 10 10" (1990s)
                i += 1
            target = last_target
            if note.level == "heading" and (stack or art is not None):
                # "Skyriaus pakeitimai" belongs to the chapter, even after an article with no text
                want = next((kd for key, kd in (("skyri", "skyrius"), ("skirsn", "skirsnis"), ("knyg", "knyga"))
                             if key in note.label.lower()), None)
                target = next((h for h in reversed(stack) if want and h.kind == want), stack[-1] if stack else art)
            elif isinstance(target, Block) and note.level == "article" and art is not None:
                target = art
            if target is None:
                target = art or (stack[-1] if stack else None)
            if target is not None:
                target.notes.append(note)
            continue
        if l.startswith("TAR pastaba") and art is None and stack and annex is None and not signing:
            stack[-1].remarks.append(l)  # a note for the whole chapter/section, before its first article
            i += 1
            continue
        if l.startswith("TAR pastaba") and art is not None:
            b = Block("editorial", None, l)
            art.blocks.append(b)
            i += 1
            continue

        # --- segments ---------------------------------------------------------------------
        if RE_APPROVED.match(l):
            approved_mode, signing = True, False
            if seg is not None and seg.kind == "main":
                seg.kind = "approval"  # the articles so far belong to the approval law
            elif seg is None:
                res_body = _resolution_body(title_lines)  # used if the document turns out to be a TSO methodology
            i += 1
            continue
        if approved_mode:
            # a document whose title is in ordinary case ("Rezervinė metodika, pateikta …", RMM O3E-43): no title line
            # comes, its first article does. The line after the stamp is the title, the numbered recitals ("(1) …")
            # between them the preamble; nothing else is read so (only after a stamp "… nutarimu Nr. …")
            k = max((j for j, x in enumerate(after_stamp) if _STAMP_END.search(x)), default=None)
            if seg is None and RE_ART.match(l) and RE_ART.match(l).group(1) == "1" and k is not None \
                    and k + 1 < len(after_stamp) and not _titleish(after_stamp[k + 1]) \
                    and sum(1 for x in after_stamp[k + 2:] if re.match(r"^\(\d+\) \S", x)) >= 2:
                seg = new_segment("main", after_stamp[k + 1])
                stamped.add(id(seg))
                seg.preamble = after_stamp[k + 2:]
                qualified.add(id(seg))
                approved_mode, after_stamp = False, []
                continue  # the article line, read as one
            # skip "Lietuvos Respublikos / 2016 m. ... / įstatymu Nr. ..." until the code title
            if _titleish(l) and not _heading(l):
                ttl = [l]
                while i + 1 < len(lines) and _titleish(lines[i + 1]) and not _heading(lines[i + 1]) \
                        and not RE_ART.match(lines[i + 1]):
                    i += 1
                    ttl.append(lines[i])
                seg = new_segment("main", " ".join(ttl))
                stamped.add(id(seg))
                approved_mode = False
                # what stood between the stamp ("… nutarimu Nr. O3E-59") and this title: the document's own title and
                # recitals in the TSO methodologies VERT approves (GADTMM, PPNMM, BTMMM), not stamp lines
                if (k := max((j for j, x in enumerate(after_stamp) if _STAMP_END.search(x)), default=None)) is not None:
                    pre = after_stamp[k + 1:]
                    if _recitals(pre):  # GADTMM, PPNMM
                        seg.preamble = pre + ([seg.title] if seg.title.endswith(":") else [])  # "PSO, ATSIŽVELGDAMI Į
                        qualified.add(id(seg))  # VIRŠUJE MINIMUS DALYKUS, … TEIKIA ŠĮ GADPM PASIŪLYMĄ:": the recitals' end
                    elif pre:
                        pending[id(seg)] = pre  # BTMMM: its title here, the recitals after "BENDROSIOS NUOSTATOS"
                after_stamp = []
            else:
                after_stamp.append(l)
            i += 1
            continue

        # --- promulgation + signatures ("Skelbiu šį ... įstatymą.", names) -------------------
        # the formula opens its own line, or follows "Vadovaudamasis … Konstitucijos 71 straipsnio antrąja dalimi," (the
        # Speaker's, PVMĮ); quoted inside an article it is text (Prezidento įstatymas 11: "… įrašoma: „Skelbiu šį Lietuvos
        # Respublikos Seimo priimtą įstatymą.“" lost articles 12–24 as signature lines)
        if seg is not None and art is not None and annex is None and \
                re.match(r"(?:vadovaudam\w+\b[^„“]{0,120}?,\s*)?skelbiu šį\b", l.strip(), re.I):
            seg.signature.append(l)
            art, signing = None, True
            i += 1
            continue
        # older laws are signed without "Skelbiu ...": "LIETUVOS RESPUBLIKOS / AUKŠČIAUSIOSIOS TARYBOS /
        # PIRMININKAS V.LANDSBERGIS" (VSDĮ 1991); what follows is history, not article text
        msig = re.match(r"^(?:[A-ZĄČĘĖĮŠŲŪŽ ]+ )?(PIRMININKAS|PIRMININKĖ|PIRMININKO PAVADUOTOJA[SI]?|PREZIDENTAS|PREZIDENTĖ)\b", l)
        # a signer: the title followed by a name ("PIRMININKAS V.LANDSBERGIS"), never a chapter title
        # ("VI SKIRSNIS / RESPUBLIKOS PREZIDENTAS")
        if msig and seg is not None and art is not None and annex is None and not signing and len(l) < 80 \
                and not _heading(lines[i - 1] if i else "") and (l[msig.end():].strip()
                                                                  or re.match(r"^[A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž.]+\s+[A-ZĄČĘĖĮŠŲŪŽ]", nxt)):
            while art.blocks and art.blocks[-1].kind == "para" and _is_upper(art.blocks[-1].text) and len(art.blocks[-1].text) < 60:
                seg.signature.insert(0, art.blocks.pop().text)
            seg.signature.append(l)
            art, signing = None, True
            i += 1
            continue
        # an approval law whose document follows its signature with no stamp: "Patvirtinti Lietuvos kariuomenės drausmės
        # statutą (pridedama)." / "Skelbiu …" / "LIETUVOS KARIUOMENĖS DRAUSMĖS STATUTAS" / "I DALIS" (LKDSP2Į 2026-11-25:
        # the statute's 106 articles were read as headings, their text as signature lines)
        if signing and seg is not None and seg.kind == "main" and annex is None and _is_upper(l) \
                and _TITLE_END.search(l.strip()) and (_heading(nxt) or RE_ART.match(nxt)) \
                and any("pridedam" in b.text for a in seg.articles for b in a.blocks):
            seg.kind = "approval"
            seg = new_segment("main", l.strip())
            signing = False
            i += 1
            continue
        if signing and not (RE_ANNEX.match(l) or RE_APPROVED.match(l) or RE_ART.match(l) or _heading(l)):
            seg.signature.append(l)
            i += 1
            continue

        # --- annexes ("Lietuvos Respublikos / darbo kodekso / priedas") ----------------------
        if (ma := RE_ANNEX.match(l)) and seg is not None and (art is not None or annex is not None or signing
                                                              or seg.articles):
            head = []
            if signing:  # the annex header lines were read as signature lines; take them back
                while seg.signature and len(head) < 4 and _header_line(seg.signature[-1]):
                    head.insert(0, seg.signature.pop())
                signing = False
            elif art is None and annex is None:  # after the articles, outside any article (CPK): from the tail
                while seg.tail and len(seg.tail[-1]) < 80 and not seg.tail[-1].endswith((".", ":")) \
                        and not set(seg.tail[-1]) <= {"_", " "} and len(head) < 4:
                    head.insert(0, seg.tail.pop())
            elif annex is not None and annex_history and annex.history:  # header lines read as the previous annex's history
                while annex.history and len(head) < 4 and _header_line(annex.history[-1]):
                    head.insert(0, annex.history.pop())
            else:
                owner = annex if annex is not None else art
                # "Lietuvos Respublikos / akcizų įstatymo / 2 priedas": only such lines belong to the header;
                # a value ("423", "4,34 Eur") or an item ("6.4.2. …") is the previous annex's content
                while owner.blocks and owner.blocks[-1].kind == "para" and len(head) < 4 and \
                        _header_line(owner.blocks[-1].text) and \
                        (_HEADER_SPECIFIC.match(owner.blocks[-1].text.strip())
                         or head and head[0][:1].islower()):  # a bare lowercase phrase only as a continuation
                    head.insert(0, owner.blocks.pop().text)  # (a header split mid-phrase: "… ir gretutinių / teisių įstatymo")
            ttl = ""
            if nxt and not RE_PART.match(nxt) and not RE_ANNEX.match(nxt) and not nxt.endswith(":"):
                ttl = nxt
                i += 1
            annex = Annex(_annex_num(ma.group(1) or "", seg.annexes), " ".join(head + [l]), ttl)
            annex_history = False
            seg.annexes.append(annex)
            art, last_target = None, annex
            i += 1
            continue
        if annex is not None and seg is not None:
            if l == "Pakeitimai:":  # the annex's own amendment list: not annex content
                annex.history.append(l)
                annex_history = True
                i += 1
                continue
            if annex_history:
                annex.history.append(l)
                i += 1
                continue
            b = Block("part" if RE_PART.match(l) else "para", None, l)
            annex.blocks.append(b)
            last_target = b
            i += 1
            continue

        # --- headings ---------------------------------------------------------------------
        h = _heading(l)
        if h and seg is None and title_lines:  # laws (not codes): the first chapter comes before any article
            seg = new_segment("main", " ".join(t for t in title_lines if _titleish(t)))
            seg.preamble = _preamble(title_lines)
        if h and seg is not None:
            _tail_to_preamble(seg, stamped, pending, qualified)
            kind, num = h
            if stack and stack[-1].kind == kind == "dalis" and not stack[-1].title:
                # "I DALIS" followed by "BENDROJI DALIS": the second line is the title
                stack[-1].title = l
                i += 1
                continue
            inline = (m := RE_HEAD.match(l)) and m.group(5)  # none in "2 SKIRSNIS" (EU acts)
            ttl = [inline] if inline else []
            def structural(x: str) -> bool:
                return bool(_heading(x) or RE_ART.match(x) or RE_PART.match(x) or x.endswith(":") or x.startswith("Nr."))
            if not inline and i + 1 < len(lines) and not structural(lines[i + 1]):
                i += 1
                ttl.append(lines[i])
                # a heading has no body text: anything before the next structure continues its title
                while i + 1 < len(lines) and not structural(lines[i + 1]) and not lines[i + 1].startswith("TAR pastaba"):
                    i += 1
                    ttl.append(lines[i])
            hd = Heading(kind, num, " ".join(ttl))
            while stack and stack[-1].rank >= hd.rank:
                stack.pop()
            stack.append(hd)
            seg.headings.append(hd)
            art, last_target = None, hd
            i += 1
            continue

        # --- dated variants of the previous article ------------------------------------------
        if (mv := RE_VARIANT.match(l)) and art is not None and RE_ART.match(nxt):
            y, mo, d, y2, mo2, d2 = mv.groups()[1:]
            pending_variant = (f"{y}-{MONTHS[mo]:02d}-{int(d):02d}",
                               f"{y2}-{MONTHS[mo2]:02d}-{int(d2):02d}" if y2 else None)
            variant_of = seg.articles[-1]  # the article itself, not an earlier variant
            i += 1
            continue

        # --- articles ---------------------------------------------------------------------
        m = RE_ART.match(l)
        if m and pending_variant and variant_of is not None and \
                any(c == variant_of.num for c in candidates(split_roman(m.group(1)))):
            v = Article(variant_of.num, (m.group(2) or "").strip(), path=list(stack),
                        valid_from=pending_variant[0], valid_to=pending_variant[1])
            if not variant_of.variants and variant_of.valid_to is None:
                variant_of.valid_to = _day_before(pending_variant[0])  # the unmarked text ends here
            variant_of.variants.append(v)
            art, pending_variant = v, None
            part_seq, point_seq, cur_part = Sequence(), None, None
            last_target = art
            i += 1
            continue
        if m:
            if seg is None:
                seg = new_segment("main", " ".join(t for t in title_lines if _titleish(t)))
                seg.preamble = _preamble(title_lines)  # once, when the act's own text starts
            _tail_to_preamble(seg, stamped, pending, qualified)
            prev = seg.articles[-1] if seg.articles else None
            if prev is not None and any(c == prev.num for c in candidates(split_roman(m.group(1)))):
                dup = Article(prev.num, (m.group(2) or "").strip(), path=list(stack))
                prev.duplicates.append(dup)
                seg.warnings.append(f"article {prev.label} printed twice without dates")
                art = dup
                part_seq, point_seq, cur_part = Sequence(), None, None
                last_target = art
                i += 1
                continue
            num = art_seq.next(m.group(1))
            if seg.articles and num <= seg.articles[-1].num:
                seg.warnings.append(f"article order: {m.group(1)} after {seg.articles[-1].label}")
            art = Article(num, (m.group(2) or "").strip(), path=list(stack))
            seg.articles.append(art)
            part_seq, point_seq, cur_part = Sequence(), None, None
            last_target = art
            i += 1
            if not art.title and id(seg) in qualified and len(nxt) < 200 and nxt[:1].isupper() \
                    and not nxt.endswith((".", ":", ";")) and not re.match(r"^\d", nxt) and not RE_ART.match(nxt):
                art.title = nxt  # "1 straipsnis" / "Dalykas ir taikymo sritis" (BTMMM, GADTMM, PPNMM)
                i += 1
            continue

        # --- article content --------------------------------------------------------------
        if art is not None:
            if (m := RE_PART.match(l)) and not RE_POINT.match(l):
                n = part_seq.next(m.group(1)).label()
                cur_part, point_seq = n, Sequence()
                b = Block("part", n, l, anchor=f"d{n}")
            elif m := RE_POINT.match(l):
                if point_seq is None:
                    point_seq = Sequence()
                n = point_seq.next(m.group(1)).label()
                b = Block("point", n, l, anchor=(f"d{cur_part}-p{n}" if cur_part else f"p{n}"))
            elif m := RE_SUB.match(l):
                b = Block("sub", m.group(1), l)
            else:
                b = Block("para", None, l)
            art.blocks.append(b)
            last_target = b
        elif seg is None:
            title_lines.append(l)
        elif _is_upper(l) and len(l) <= 80 and RE_ART.match(nxt):
            # a bare heading line right before an article ("BAIGIAMOSIOS NUOSTATOS", Seimo statutas 261)
            _tail_to_preamble(seg, stamped, pending, qualified)
            if id(seg) in qualified and not seg.articles and not seg.headings and l.endswith(":"):
                seg.preamble.append(l)  # "PATEIKIAME ŠĮ BTMM PASIŪLYMĄ VISOMS REGULIAVIMO INSTITUCIJOMS:" (BTMMM)
                i += 1
                continue
            hd = Heading("skirsnis" if any(h.kind == "skirsnis" for h in stack) else "skyrius", "", l)
            while stack and stack[-1].rank >= hd.rank:
                stack.pop()
            stack.append(hd)
            seg.headings.append(hd)
            last_target = hd
        else:
            seg.tail.append(l)
        i += 1

    if res_body and any(id(x) in qualified for x in segments) and not any(x.kind == "approval" for x in segments):
        # the resolution approving a TSO methodology written in articles: its own words ("Vadovaudamasi … nutaria: /
        # Patvirtinti …") are shown as a points act's are (render._approval)
        ap = Segment("approval", " ".join(t for t in title_lines if _titleish(t)))
        ap.preamble, ap.signature = res_body
        segments.insert(0, ap)
    for seg in segments:
        _appendix_nums(seg.annexes)
    title = " ".join(t for t in title_lines if _titleish(t)) or (segments[0].title if segments else "")
    act = Act(vfrom, vto, published, title, segments, amend)
    act.expires = expires
    # notes about the whole act in the header ("TAR pastaba. …", "Įstatymas netenka galios D:") with the
    # reference lines that follow them, up to the next structural line
    grp, notes = None, []
    for l in lines0[:300]:  # up to the first heading or article (break below)
        if re.match(r"^(TAR pastaba|(Įstatymas|Kodeksas|Statutas) netenka galios)", l):
            grp = [l]
            notes.append(grp)
        elif grp is not None and l.strip() and not (_is_upper(l) or RE_VERSION.match(l) or
                                                    re.match(r"^(Nauja|Įstatymas paskelbtas|Kodeksas paskelbtas|Įstatymo pavadinimas)", l)):
            grp.append(l)
        else:
            grp = None
        if RE_ART.match(l) or _heading(l):
            break
    act.header_notes = [" ".join(g) for g in notes]
    # whole-act replacement noted in the header: "Nauja redakcija nuo 2026-11-20:" + "Nr. XV-822, ..."
    head = "\n".join(_lines(text)[:20])
    for m in re.finditer(r"Nauja (?:įstatymo |kodekso )?redakcija nuo (\d{4}-\d{2}-\d{2}):\s*\nNr\.\s*([IVXL]+-\d+)", head):
        act.rewrites.append((m.group(1), m.group(2)))
    return act
