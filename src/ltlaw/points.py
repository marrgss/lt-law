"""Acts made of numbered points: Government resolutions approving rules (Kelių eismo taisyklės, KET).

Act
 └ Segment "approval"   the resolution itself ("1. Patvirtinti Kelių eismo taisykles (pridedama).")
 └ Segment "main"       the approved rules
    └ Heading*          SKYRIUS (and SKIRSNIS, if any)
       └ Article        a top-level point "52. …" (the unit, like an article of a law)
          └ Block       its text, sub-points "52.1. …", "77.1.2. …", paragraphs, each with notes
    └ Annex*            "Kelių eismo taisyklių 1 priedas"

The same data classes as laws (parse.py), so currency, rendering and validation work unchanged. Flattened
superscripts ("662" for 66², "3.21" for 3.2¹) are decoded by the same increasing-sequence rule.
Resolution numbers repeat every year, so references are keyed by number and adoption date ("875/2025-12-03").
"""
from __future__ import annotations

import re

from .numbers import Num, Sequence, candidates, from_roman, to_roman

# flattened in the open data ("662."), explicit from e-tar HTML ("66-2."): both decode to 66²
RE_PT = re.compile(r"^(\d+(?:-\d+)?)\.\s+(.*)$")                          # "52. Text"
# a repealed chapter's stub, its points gone: "8 skyrius. Neteko galios nuo 2026-06-02" (ITIVKDĮN on e-tar, 2026-06-02):
# a heading, not the last point's words
RE_GONE_HEAD = re.compile(r"^(\d+|[IVXLC]+) (skyrius|skirsnis)\. (Neteko galios nuo \d{4}-\d\d-\d\d)$", re.I)
RE_SUBPT = re.compile(r"^(\d+(?:-\d+)?(?:\.\d+(?:-\d+)?)+)\.\s+(.*)$")  # "52.1. Text", "77.1.2. Text"
# "Kelių eismo taisyklių 1 priedas", a lone "priedas"; e-tar's "5<sup>1</sup> priedas" reads "5-1 priedas" (EĮAT)
_DOC_GEN = r"(?:aprašo|taisyklių|metodikos|nuostatų|reikalavimų|tvarkos|sąlygų|plano|programos)"
RE_PANNEX = re.compile(r"^(?P<pre>[A-ZĄČĘĖĮŠŲŪŽ][^\d]{0,80}? |(?:[A-ZĄČĘĖĮŠŲŪŽ]|(?P<cont>[a-ząčęėįšųūž]))[^\d.;:]{0,300}?"
                       + _DOC_GEN + r" )?(?:(?P<num>\d+(?:-\d+)?) )?priedas$")
# (a long header on one line: "Atskirų … nustatymo bei taikymo metodikos 1 priedas", AEKRSNBM; its last line only, in
# lower case, when the header is split over several: "Energijos išteklių … / … / parengimo tvarkos aprašo 1 priedas", EIEEVSIA)
# an older rule set's chapter: "II. SĄVOKOS, SANTRUMPOS", "XI. SIURBLINIŲ REIKALAVIMAI" (DSPĮT, ŠTTŠPĮT, EETEKT: 197 rule
# sets); until 2026-11-11 read as the last line of the point before it, the act without chapters
RE_RHEAD = re.compile(r"^([IVXLC]+)\.\s+(\S.{1,160})$")


def _upperish(t: str) -> bool:
    letters = [c for c in t if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) >= 0.8


def _roman_heading(lines: list[str], i: int) -> tuple[int, str, str] | None:
    """"II. SĄVOKOS": its number, figure and title, if the line can be an older rule set's chapter or section: in
    capitals, or a short line (no closing punctuation) a point follows ("I. bendrosios nuostatos", DSPĮT)."""
    m = RE_RHEAD.match(lines[i])
    if not m:
        return None
    try:
        n = from_roman(m.group(1))
    except KeyError:
        return None
    t = m.group(2).strip()
    if t[:1].isdigit() and not _upperish(t):  # "VI. 3–35 kV ĮTAMPOS …" (EĮRAAĮT), not "II. 1. …"
        return None
    nxt = lines[i + 1] if i + 1 < len(lines) else ""
    # (in ordinary case: "V. Dujinių prietaisų įrengimas" / "I. BENDRIEJI NURODYMAI", DSPĮT)
    if (_upperish(t) and not t.endswith((";", ",", ":"))) or (len(t) < 160 and not t.endswith((".", ";", ",", ":")) and (
            RE_PT.match(nxt) or ((mn := RE_RHEAD.match(nxt)) and _upperish(mn.group(2))))):
        return n, m.group(1), t
    return None


def _restarting(lines: list[str]) -> bool:
    """Points numbered from 1 again after a chapter line "II. KVIEČIAI" (GAAPT: a standard per chapter): such chapters
    can't be told apart by point numbers yet, so none of the act's "N. TITLE" lines is read as a chapter (as before
    2026-11-11), rather than some."""
    last = 0
    for k, x in enumerate(lines):
        if mp := RE_PT.match(x):
            last = int(mp.group(1)) if mp.group(1).isdigit() else last
        elif last and (h := _roman_heading(lines, k)) and h[0] >= 2:  # (after "I.": the rules after the order's points)
            nxt = next((m2.group(1) for y in lines[k + 1:k + 60] if (m2 := RE_PT.match(y))), None)
            if nxt is not None and nxt.isdigit() and int(nxt) < last and int(nxt) <= 2:
                return True
    return False


def _roman_level(lines: list[str], i: int, n: int, top: int, sub: int) -> str | None:
    """Which level "N. TITLE" is: "top" (the next chapter), "sub" (the next section of the current chapter, numbered
    from I in each: EETEKT, ELIĮT), or None (out of turn: a list item in a point). One number of either may be gone
    (repealed), more if in capitals. Both possible ("III." after chapter II's section II): a chapter if the next such
    heading is "I." (its sections begin), else a section."""
    caps = _upperish(RE_RHEAD.match(lines[i]).group(2))  # in capitals: chapters repealed in between (ŠTVT: IV, then IX)
    is_sub = top >= 1 and (n == sub + 1 or (sub >= 1 and (n == sub + 2 or (caps and n > sub)))
                           or (sub == 0 and caps and n == 2 and n <= top))  # (ŠTŠVĮPET IV: its sections from II)
    is_top = n == top + 1 or (top >= 1 and (n == top + 2 or (caps and n > top)))
    if is_sub and is_top and (n == top + 1) != (n == sub + 1):
        return "top" if n == top + 1 else "sub"  # one level in turn exactly, the other only past a gap
    if is_sub and is_top:
        nxt = next((h for k in range(i + 1, min(len(lines), i + 3000)) if (h := _roman_heading(lines, k))), None)
        return "top" if nxt is not None and nxt[0] == 1 else "sub"
    return "top" if is_top else "sub" if is_sub else None


RE_SIGNER = re.compile(r"^(Ministras Pirmininkas|Ministrė Pirmininkė|[A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+ (ministras|ministrė))\b")
RE_SEPARATOR = re.compile(r"^[–—_-]{5,}$")
# the approval stamp's own lines ("Lietuvos Respublikos aplinkos ministro", "2009 m. birželio 15 d. įsakymu Nr. D1-331",
# "(… redakcija)"): not a document's title
_STAMP_LINE = re.compile(r"(?:nutarimu|įsakymu|sprendimu|nutarimo|įsakymo|sprendimo)\s+Nr\.|redakcija\)?\s*$|^\(|^Lietuvos Respublikos [\w ]*(?:ministro|Vyriausybės|tarybos)$|\d{4}\s*m\.", re.I)
# the line before a document's first point: its title (ends with its type, any case) or a chapter line "I. Bendrosios nuostatos"
_DOC_START = re.compile(r"\b(?:aprašas|taisyklės|nuostatai|metodika|reglamentas|tvarka|sąlygos|reikalavimai|norma|planas|programa|"
                        r"sąrašas|statutas|instrukcija|kodeksas|aprašai|nuostatos)\W*$|^[IVXLC]+\.\s+\S", re.I)
RE_APPROVED_DOC = re.compile(r"^PATVIRTINTA\b", re.I)  # also "Patvirtinta" (No. 260/1999), not the verb "Patvirtinti"


def is_points(lines: list[str]) -> bool:
    """No "N straipsnis" anywhere, an approval line, and many numbered points: a points act. Short rules count too:
    3 points after the approval line (the order's own "1. Tvirtinu …" before it doesn't count): KPSPEAT has 6 points,
    MKPVKNSA 4, ITĮPTEBA 7 (2026-11-14), when point 1 follows the stamp within 10 lines (the stamp, the title, a
    chapter line): a document of paragraphs with a numbered list deep inside (PLNN2MLN, a TSO request) is not rules."""
    from .parse import RE_ART
    if any(RE_ART.match(l) for l in lines):
        return False
    first = next((i for i, l in enumerate(lines) if RE_APPROVED_DOC.match(l)), None)
    if first is None:
        return False
    if sum(1 for l in lines if RE_PT.match(l)) >= 8:  # VDAI's DPIA list has 10
        return True
    pts = [i for i, l in enumerate(lines[first:], first) if RE_PT.match(l)]
    return len(pts) >= 3 and RE_PT.match(lines[pts[0]]).group(1) == "1" and pts[0] - first <= 10


def implied_stamp(lines: list[str]) -> list[str] | None:
    """An order approving rules made of points whose stamp lacks the word "PATVIRTINTA": "Lietuvos Respublikos
    energetikos ministro / 2011 m. vasario 25 d. įsakymu Nr. 1-52" (IAVPNPKA), or no stamp at all, the rules' title
    right after the minister's name (TAPĮKĮEA, 1-159). The lines with "PATVIRTINTA" put where the stamp starts; None
    where the order doesn't say it approves something attached ("Tvirtinu … (pridedama)") or no such place is found."""
    from .parse import _SIGNER, _STAMP_END, _titleish
    if any(RE_APPROVED_DOC.match(l) for l in lines):
        return None
    tv = next((i for i, l in enumerate(lines[:60]) if "pridedam" in l and
               re.match(r"^(?:\d+\.\s*)?(?:t ?v ?i ?r ?t ?i ?n ?u|patvirtinti)\b", l, re.I)), None)
    if tv is None:
        return None
    for j in range(tv + 1, min(tv + 25, len(lines) - 1)):
        if re.match(r"^\d{4} m\. ", lines[j]) and _STAMP_END.search(lines[j]):  # "2011 m. … įsakymu Nr. 1-52"
            k = j
            while k > tv + 1 and j - k < 3 and re.search(r"(ministro|ministerijos|komisijos|tarybos|direktoriaus)$", lines[k - 1], re.I):
                k -= 1
            return lines[:k] + ["PATVIRTINTA"] + lines[k:] if k < j else None
        if _SIGNER.match(lines[j]) and _titleish(lines[j + 1]):  # "Energetikos ministras Rokas Masiulis" / "TRETIESIEMS …"
            return lines[:j + 1] + ["PATVIRTINTA"] + lines[j + 1:]
    return None


# a Seimas number: "I-" (1990–1996), then the term's numeral from VIII on. The numerals between were never used, and
# "V-300" is a minister's order (health, education, defence: numbered anew every year)
RE_SEIMAS_NR = re.compile(r"(?:I|VIII|IX|X{1,3}(?:IX|IV|V?I{0,3}))-\d+")


def ref_key(nr: str, adopted: str) -> str:
    """Seimas numbers (XV-969) and Court rulings are unique; a resolution's or an order's number is not ("1950",
    "1-208", "V-300", VERT's "O3-1284" restart every year): those are keyed with their adoption date (B58, B88)."""
    if RE_SEIMAS_NR.fullmatch(nr) or re.fullmatch(r"KT[\w()-]+/\d{4}", nr) or not adopted:
        return nr
    return f"{nr}/{adopted}"


def _sub_label(token: str, seqs: dict) -> str:
    """'3.21' -> '3.2-1' when it follows 3.2 (the last component may be a flattened superscript)."""
    head, last = token.rsplit(".", 1)
    seq = seqs.setdefault(head, Sequence())
    return f"{head}.{seq.next(last).label()}"


def _document_titles(lines: list[str]) -> list[str]:
    """Every approved document's title (the first title line after each "PATVIRTINTA"), in order."""
    from .parse import _heading, _titleish
    out, waiting = [], False
    for l in lines:
        if RE_APPROVED_DOC.match(l):
            waiting = True
        elif waiting and _titleish(l) and not _heading(l):
            out.append(l)
            waiting = False
    return out


def doc_matches(title: str, selector: str) -> bool:
    """The approved document's title line starts with the scope's `document:` words (case and spacing ignored), as far
    as both go: two documents of one order may share their first 60 letters (PASPSPGA: "… konkrečių paslaugų sąrašas"
    and "… konkrečių paslaugų sąrašo sudarymo tvarkos aprašas"); a title cut at its first line still matches."""
    norm = lambda x: re.sub(r"[^a-ząčęėįšųūž]+", " ", (x or "").lower()).strip()
    t, s = norm(title), norm(selector)
    n = min(len(t), len(s))
    return n >= min(60, len(s)) and t[:n] == s[:n]


def parse_points(text: str, document: str | None = None):
    from .parse import (REF, RE_HEAD, RE_VERSION, Act, Annex, Article, Block, Heading, Note, Ref, Segment, _heading,
                        _annex_num, _lines, _parse_amendment_list, _titleish)
    # a point numbered with a real superscript ("22¹. Daugiabučio …", PŠKVSPA) reads as e-tar's "22-1." (B60)
    sup = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    lines = [re.sub(r"^(\d+(?:\.\d+)*)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)\.", lambda m: f"{m.group(1)}-{''.join(str(sup.index(c)) for c in m.group(2))}.", l)
             for l in _lines(text)]
    vfrom = vto = published = None
    for l in lines[:12]:
        if m := RE_VERSION.match(l):
            vfrom, vto = m.groups()
            break
    for l in lines[:12]:
        if m := re.search(r"paskelbtas: TAR (\d{4}-\d{2}-\d{2})", l):
            published = m.group(1)
    amend: list[dict] = []
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == "Pakeitimai:":
            amend = _parse_amendment_list(lines[i + 1:])
            lines = lines[:i]
            break
    rewrites = [(m.group(1), ref_key(m.group(2), m.group(3))) for m in re.finditer(
        r"Nauja (?:(?:nutarimo|įsakymo) )?redakcija nuo (\d{4}-\d{2}-\d{2}):\s*\nNr\.\s*([^,\s]+),\s*(\d{4}-\d{2}-\d{2})", "\n".join(lines[:30]))]

    title_lines: list[str] = []
    header_notes: list[str] = []
    approval = Segment("approval", "")
    main: Segment | None = None
    seg = None                          # the segment being filled
    art: Article | None = None
    stack: list[Heading] = []
    last_target = None
    annex: Annex | None = None
    annex_notes: list = []              # "Priedo pakeitimai" printed before the annex header
    seq = Sequence()
    subseqs: dict = {}
    stray: set[int] = set()             # points printed out of place (ids): the numbering goes on from before them
    roman_top = roman_sub = 0           # older rule sets' chapters "II. SĄVOKOS" and their sections: the last numbers
    roman: set[int] = set()             # those headings (ids)
    restarting = _restarting(lines)
    approved_last = ""                  # the last line read after a "PATVIRTINTA" stamp (a title in lower case)
    mode = "head"                       # head | approval | signing | approved | main | annex
    after_sep = False                   # after a "––––" line, before the next annex header
    i = 0
    while i < len(lines):
        l = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""

        # notes: a label line followed by "Nr." references
        if l.endswith(":") and REF.match(nxt) and not RE_PT.match(l) and not RE_SUBPT.match(l):
            note = Note(l.rstrip(": ").strip())
            i += 1
            while i < len(lines) and (m := REF.match(lines[i])):
                note.refs.append(Ref(ref_key(m.group(1), m.group(2).replace(" ", "-")), m.group(2).replace(" ", "-"), m.group(3), m.group(4)))
                i += 1
            low = note.label.lower()
            if "pried" in low and (after_sep or annex is None):
                annex_notes.append(note)  # after a separator line: the next annex's (KET 1 priedas)
                continue
            if mode == "annex" and annex is not None:
                annex.notes.append(note)
                continue
            if re.search(r"skyri|skirsn", low) and stack:
                stack[-1].notes.append(note)
            elif "papunk" in low and isinstance(last_target, Block) and last_target.kind == "point":
                last_target.notes.append(note)
            elif art is not None:
                art.notes.append(note)
            elif stack:
                stack[-1].notes.append(note)
            elif seg is not None:
                seg.warnings.append(f"note without a target: {note.label}")
            continue
        if l.startswith("TAR pastaba") and art is not None:
            art.blocks.append(Block("editorial", None, l))
            i += 1
            continue

        if mode == "head_signing":
            if RE_APPROVED_DOC.match(l):
                mode = "head"  # re-read: the approved document starts
                continue
            approval.signature.append(l)
            i += 1
            continue
        if mode == "head":
            if l.startswith("TAR pastaba") and not any(t.isupper() for t in title_lines):
                # a note on the whole act before its title (ALKLT: "TAR pastaba. Dėl netikslaus … Nr. 530 … suvestinė
                # redakcija nerengiama." + the act it names): shown on the act page, as for laws
                grp = [l]
                while i + 1 < len(lines) and not re.match(r"^(Nauja (?:(?:nutarimo|įsakymo) )?redakcija|(?:Nutarimas|Įsakymas) paskelbtas|TAR pastaba)", lines[i + 1]) \
                        and not lines[i + 1].isupper():
                    i += 1
                    grp.append(lines[i])
                header_notes.append(" ".join(grp))
                i += 1
                continue
            if RE_SIGNER.match(l) and title_lines:
                approval.signature.append(l)  # a resolution with no numbered items: its signatures (No. 86)
                mode = "head_signing"
                i += 1
                continue
            if RE_APPROVED_DOC.match(l) and title_lines:
                # a resolution with no numbered items ("Patvirtinti Ligos … nuostatus (pridedama).", No. 86): the
                # approved document starts here
                approval.title = " ".join(t for t in title_lines if _titleish(t) and not t.startswith("Nr."))
                mode, seg = "approved", approval
                i += 1
                continue
            if RE_PT.match(l):
                mode, seg = "approval", approval
                approval.title = " ".join(t for t in title_lines if _titleish(t) and not t.startswith("Nr."))
                continue  # re-read as a point
            if any(_titleish(t) for t in title_lines) and not _titleish(l) and (len(l) > 60 or l.endswith(":")
                                                                                or re.match(r"(Patvirtinti|Nustatyti|Pavesti|Pripažinti)\b", l)):
                approval.preamble.append(l)  # "Vadovaudamasi … Lietuvos Respublikos Vyriausybė nutaria:"
            else:
                title_lines.append(l)
            i += 1
            continue

        if RE_APPROVED_DOC.match(l):
            if main is not None and (document is None or doc_matches(main.title, document)):
                if document is None:  # several documents, none chosen (scope `document:`): the first, and say so
                    main.warnings.append("more than one approved document; only the first is read")
                break  # the chosen document ends here
            # (the first document, or one we skip: it is replaced by the next)
            main, stack, annex, annex_notes = None, [], None, []
            mode, art, last_target, approved_last = "approved", None, None, ""
            i += 1
            continue
        if mode == "approved":
            if _titleish(l) and not _heading(l):
                main = Segment("main", l)
                mode, seg, seq, subseqs = "main", main, Sequence(), {}
            elif _heading(l) or (RE_PT.match(l) and _DOC_START.search(approved_last)):
                # (a point only after a title or a chapter line: SPĮDAAPT opens with a table whose rows are numbered
                # "1. Chirurginė pižama"; its points come after "I. BENDROSIOS NUOSTATOS")
                # the document starts with no title in capitals ("Mažmeninės prekybos taisyklės" / "I SKYRIUS", MPT;
                # "keleivių įvežamų … taisyklės" / "1. …", KĮPNIPVT): its title is the line before, the rest is read as
                # the document. Until 2026-11-09 every point before the first capitalised title was skipped (MPT 1-13).
                main = Segment("main", approved_last if approved_last and not _STAMP_LINE.search(approved_last) else "")
                mode, seg, seq, subseqs = "main", main, Sequence(), {}
                continue  # re-read as a heading or point
            else:
                approved_last = l
            i += 1  # the rest of the approval line ("Lietuvos Respublikos Vyriausybės … nutarimu Nr. 1950")
            continue
        if mode in ("approval", "signing") and RE_SIGNER.match(l):
            approval.signature.append(l)
            mode, art = "signing", None
            i += 1
            continue
        if mode == "signing":
            approval.signature.append(l)
            i += 1
            continue

        if RE_SEPARATOR.match(l):
            art, last_target, after_sep = None, None, True
            i += 1
            continue
        if seg is main and main is not None and (ma := RE_PANNEX.match(l)) \
                and not (not ma.group("pre") and i and re.search(r"\b(?:LST|EN|ISO|IEC)\b.*\s[A-Z]$", lines[i - 1])):
            # (not "LST EN 1775 C" / "1 priedas": a standard's annex C.1 in a table cell, e-tar's copy of DSPĮT)
            src = annex.blocks if annex is not None else art.blocks if art is not None else main.tail
            last = (src[-1] if isinstance(src[-1], str) else src[-1].text if src[-1].kind == "para" else "") if src else ""
            if ma.group("cont") or (not ma.group("pre") and re.search(_DOC_GEN + r"$", last)):
                # the header's earlier lines were read as the last point's or annex's text or the tail: "Energijos
                # išteklių … / … / parengimo tvarkos aprašo 1 priedas" (EIEEVSIA); e-tar: "Kelių eismo taisyklių /
                # 3 priedas" (KET), "Atskirų … taikymo metodikos / 2 priedas" (AEKRSNBM)
                head = []
                while src and len(head) < 16:
                    t = src[-1] if isinstance(src[-1], str) else src[-1].text if src[-1].kind == "para" else ""
                    # header lines are short; only the one ending in "… taisyklių" may hold the whole header
                    if not t or len(t) > (300 if not head and not ma.group("cont") else 150) \
                            or t.rstrip().endswith((".", ";", ":")) or RE_PT.match(t) or RE_SUBPT.match(t):
                        break
                    head.insert(0, src.pop() if isinstance(src[-1], str) else src.pop().text)
                    if not (t[:1].islower() or t[:1] in "(„"):  # its first line: "Kelių …", "2014–2020 metų …"
                        break
                l = " ".join(head + [l])
            elif annex is None and art is not None and l.lower() == "priedas":
                # "Kitos paskirties valstybinės žemės / sklypų pardavimo ir nuomos / taisyklių / priedas" (No. 260):
                # the header lines were read as the last point's text; take them back
                head = []
                while art.blocks and art.blocks[-1].kind == "para" and len(head) < 4 and len(art.blocks[-1].text) < 60 \
                        and not art.blocks[-1].text.rstrip().endswith((".", ";", ":")):
                    head.insert(0, art.blocks.pop().text)
                l = " ".join(head + [l])
            ttl = ""
            if nxt and not nxt.endswith(":") and not RE_PT.match(nxt):
                ttl, i = nxt, i + 1
            # a flattened superscript: "51 priedas" right after "5 priedas" is 5¹ (open data, EĮAT), as for laws
            annex = Annex(_annex_num(ma.group("num") or "", main.annexes), l, ttl, notes=annex_notes)
            annex_notes, after_sep = [], False
            main.annexes.append(annex)
            mode, art, last_target, stack = "annex", None, annex, []
            i += 1
            continue
        if mode == "annex" and annex is not None:
            b = Block("part" if RE_PT.match(l) else "para", None, l)
            annex.blocks.append(b)
            i += 1
            continue

        if mode == "main" and not _heading(l) and (rh := _roman_heading(lines, i)) \
                and (level := _roman_level(lines, i, rh[0], roman_top, roman_sub)) and not restarting \
                and (roman_top or not main.articles or isinstance(last_target, Heading)) \
                and not (i and lines[i - 1].endswith(":")):
            # (chapter I comes before the first point or right after a part's heading, "ANTRA DALIS" (ŠTVT): else a
            # table's row, "I. GYVENAMOSIOS PASKIRTIES PASTATAI" in a point's table, STR 1.01.03; never right after
            # "…:", a list's item)
            if level == "top":
                roman_top, roman_sub = rh[0], 0
            else:
                roman_sub = rh[0]
            ttl = [re.sub(r"^SKYRIUS\s+", "", rh[2])]  # "I. SKYRIUS TAIKYMO SRITIS" (HN 117)
            while i + 1 < len(lines) and _upperish(lines[i + 1]) and not (RE_PT.match(lines[i + 1]) or _heading(lines[i + 1])
                                                                       or RE_RHEAD.match(lines[i + 1]) or RE_PANNEX.match(lines[i + 1])):
                i += 1
                ttl.append(lines[i])  # a title over two lines
            # under the act's own chapters ("1 SKYRIUS" / "I. …"), sections and their parts; else chapters and sections
            own = any(h.kind == "skyrius" and id(h) not in roman for h in main.headings)
            kind = ("skirsnis" if level == "top" else "poskirsnis") if own else ("skyrius" if level == "top" else "skirsnis")
            hd = Heading(kind, rh[1], " ".join(ttl))
            roman.add(id(hd))
            while stack and stack[-1].rank >= hd.rank:
                stack.pop()
            stack.append(hd)
            main.headings.append(hd)
            # (the lines up to the next point stay where they were read before 2026-11-11: an unnumbered subheading
            # "Bendrosios nuostatos", a chapter's opening sentence, with the point before; the act's tail is no place)
            last_target = hd
            i += 1
            continue
        gone = RE_GONE_HEAD.match(l) if mode == "main" else None
        if mode == "main" and (h := _heading(l) or (gone and (gone.group(2).lower(), gone.group(1)))):
            kind, num = h
            ttl = [inline] if (inline := (RE_HEAD.match(l).group(5) if RE_HEAD.match(l) else None)) else []  # "I SKYRIUS BENDROSIOS NUOSTATOS"
            if gone:
                # e-tar writes the stub's number in figures ("6 skyrius. Neteko galios …") whatever the act's own: in an
                # act numbering its chapters "VI." or "VI SKYRIUS", the stub is chapter VI of that series (the chapters
                # after it stay chapters, TAR.40D64F4085CB), not a chapter of its own kind
                n = int(gone.group(1)) if gone.group(1).isdigit() else from_roman(gone.group(1).upper())
                series = bool(roman_top or roman_sub)  # the act's chapters are "VI." headings (D-053)
                if series or any(x.kind == kind and re.fullmatch(r"[IVXLC]+", x.num) for x in main.headings):
                    num = to_roman(n)
                if series:  # one series with the "VI." headings: their level, kind and counters
                    level = "top" if kind == "skyrius" else "sub"
                    own = any(x.kind == "skyrius" and id(x) not in roman for x in main.headings)
                    kind = ("skirsnis" if level == "top" else "poskirsnis") if own else ("skyrius" if level == "top" else "skirsnis")
                    if level == "top":
                        roman_top, roman_sub = n, 0
                    else:
                        roman_sub = n
                hd = Heading(kind, num, gone.group(3))
                if series:
                    roman.add(id(hd))
                while stack and stack[-1].rank >= hd.rank:
                    stack.pop()
                stack.append(hd)
                main.headings.append(hd)
                art, last_target = None, hd
                i += 1
                continue
            roman_top = roman_sub = 0  # "PIRMA DALIS" / "I. ĮVADINĖS NUOSTATOS" (ŠTVT): each part's chapters from I
            while i + 1 < len(lines) and not (RE_PT.match(lines[i + 1]) or _heading(lines[i + 1]) or _roman_heading(lines, i + 1)
                                               or lines[i + 1].endswith(":") or RE_SEPARATOR.match(lines[i + 1])):
                i += 1
                ttl.append(lines[i])
            hd = Heading(kind, num, " ".join(ttl))
            while stack and stack[-1].rank >= hd.rank:
                stack.pop()
            stack.append(hd)
            main.headings.append(hd)
            art, last_target = None, hd
            i += 1
            continue

        # "102.. Text" right after point 101 (a typo, STR 2.02.12:2026): point 102; else text ("261.." stays in EEPPKRA 26,
        # as on e-tar)
        if (md := re.match(r"^(\d+)\.\.\s+(.*)$", l)) and seg is not None and seg.articles \
                and seg.articles[-1].label == str(int(md.group(1)) - 1):
            m = md
        elif (md := re.match(r"^(\d+)\.([A-ZĄČĘĖĮŠŲŪŽ].*)$", l)) and seg is not None and seg.articles \
                and seg.articles[-1].label == str(int(md.group(1)) - 1):
            m = md  # "52.Tarybos nutarimai …", no space, right after point 51 (SSTT): point 52
        else:
            m = RE_PT.match(l)
        if m:
            token, rest = m.groups()
            prev = next((x for x in reversed(seg.articles) if id(x) not in stray), None)
            if prev is not None and art is not None and any(c == prev.num for c in candidates(token)) \
                    and re.match(rf"{re.escape(token)}\.\d+\.", rest):
                # the point's number again, then its own subpoints' numbers: a stray table cell ("10.  10.13.  10.14.1. 1
                # Vartotojas …" in the connection fee methodology's table, as on e-tar), the point's text, not a copy of it
                art.blocks.append(Block("para", None, l))
                last_target = art.blocks[-1]
                i += 1
                continue
            if prev is not None and any(c == prev.num for c in candidates(token)):
                # printed twice: "76. Neteko galios nuo 2020-01-01" left over, then the point added anew (KET 76)
                if prev.repealed and not prev.blocks and not rest.startswith("Neteko galios"):
                    new = Article(prev.num, "", [Block("part", prev.label, l, anchor="")], path=list(stack))
                    new.blocks.append(Block("editorial", None, f"{prev.label}. {prev.title}"))
                    new.notes = list(prev.notes)
                    seg.articles[-1] = art = new
                    seg.warnings.append(f"point {prev.label}: a repealed entry followed by the point added anew")
                else:
                    dup = Article(prev.num, "", [Block("part", prev.label, l)], path=list(stack))
                    prev.duplicates.append(dup)
                    seg.warnings.append(f"point {prev.label} printed twice without dates")
                    art = dup
                last_target = art
                i += 1
                continue
            if prev is not None and not rest.startswith("Neteko galios") and \
                    all(c < prev.num for c in candidates(token)) and art is not None:
                # numbering going back inside a point: a table's notes ("1. Skaičiuojama …" under STR 2.02.12 54's
                # table), the point's own text; the sequence stays where it was, so "55." after them is 55, not 5⁵
                art.blocks.append(Block("para", None, l))
                last_target = art.blocks[-1]
                i += 1
                continue
            num = seq.next(token)
            if (same := next((x for x in seg.articles if x.num == num), None)) is not None:
                # the number again, further on (IVSMN: 42–44 in force in chapter VI, "42. Neteko galios nuo 2011-01-01"
                # left in chapter VII): the source prints it twice; kept as its other text, flagged (as for laws)
                dup = Article(num, rest if rest.startswith("Neteko galios") else "", [] if rest.startswith("Neteko galios")
                              else [Block("part", num.label(), l)], path=list(stack))
                same.duplicates.append(dup)
                seg.warnings.append(f"point {num.label()} printed again further on")
                art = last_target = dup
                i += 1
                continue
            if rest.startswith("Neteko galios"):
                art = Article(num, rest, path=list(stack))
            else:
                art = Article(num, "", [Block("part", num.label(), l)], path=list(stack))
            if prev is not None and num.base > prev.num.base + 1:
                # a point printed out of place: the next point goes on from the one before it (ŠTTŠPĮT: 118, the new
                # wording of 191, then 120 … 190 and the old 191, in the open data and on e-tar alike). Kept where it is
                # printed, flagged; until 2026-11-11 points 120–190 were read as its text.
                ahead = next((mp.group(1) for x in lines[i + 1:i + 400] if (mp := RE_PT.match(x))), None)
                if ahead is not None and any(prev.num < c < num for c in candidates(ahead)):
                    stray.add(id(art))
                    seq.prev = prev.num
                    seg.warnings.append(f"point {num.label()} printed out of place, after point {prev.label}")
            subseqs = {}
            seg.articles.append(art)
            last_target = art
            i += 1
            continue
        if (m := RE_SUBPT.match(l)) and art is not None:
            label = _sub_label(m.group(1), subseqs)
            b = Block("point", label, l, anchor="p" + label)
            art.blocks.append(b)
            last_target = b
            i += 1
            continue
        if art is not None:
            b = Block("para", None, l)
            art.blocks.append(b)
            last_target = b
        elif seg is approval and not approval.articles:
            approval.preamble.append(l)
        elif seg is not None:
            seg.tail.append(l)
        i += 1

    if document is not None and main is not None and not doc_matches(main.title, document):
        main = None  # the chosen document isn't in this text
    segments = [s for s in (approval, main) if s is not None]
    title = approval.title or (main.title if main else "")
    act = Act(vfrom, vto, published, title, segments, amend)
    act.rewrites = rewrites
    act.header_notes = header_notes
    act.documents = _document_titles(lines)
    act.unit = "punktas"  # (validate.dropped_lines, render)
    if main is None:
        approval.warnings.append("no approved rules found after PATVIRTINTA")
    return act
