"""EU law from EUR-Lex's open data (CELLAR), in Lithuanian (D-037).

An EU act is in scope as `dokumento_id: EU.<CELEX>` ("EU.32016R0679"); `source.snapshot` comes here for those ids. The
newest consolidated version in force (CELEX "0" + base + "-YYYYMMDD", from the SPARQL endpoint), else the act as
published in the Official Journal, is read as XHTML and written as the register's plain-text layout (a version header,
"N straipsnis. Title", parts "1. …", headings "I SKYRIUS" + title), so the parser, labels, pages and API treat it like a
Lithuanian act. The words are never changed (D-002); the consolidation markers (▼B, ►M1 … ◄) and articles' footnotes that
only cite a source are left out, other footnotes go to the end of their annex or article (D-047). An act adopted before
2004 with no XHTML comes from the older HTML (legacy_to_text).

Consolidated texts are "for information only": the authentic text is the Official Journal (eur-lex.europa.eu), as
e-tar's is for Lithuanian law. Reuse: Commission Decision 2011/833/EU, source acknowledged.
"""
from __future__ import annotations

import copy
import html as htmllib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .parse import HEADING, QUOTED, RE_ANNEX, RE_ART, _heading, parse

SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"
CELLAR = "http://publications.europa.eu/resource/celex/"
UA = "atviri-teises-aktai (https://atviri-teises-aktai.lt; kontaktai@atviri-teises-aktai.lt)"
X = "{http://www.w3.org/1999/xhtml}"


def celex_of(dokumento_id: str) -> str:
    return dokumento_id.split(".", 1)[1]


def is_eu(dokumento_id: str) -> bool:
    return dokumento_id.startswith("EU.")


def eurlex_url(celex: str) -> str:
    return f"https://eur-lex.europa.eu/legal-content/LT/TXT/?uri=CELEX:{celex}"


def _get(url: str, accept: str, timeout: int = 120, data: bytes | None = None, tries: int = 3) -> bytes:
    for i in range(tries):  # CELLAR answers an occasional 404 or 5xx for a document it has: try again
        req = urllib.request.Request(url, data=data, headers={"Accept": accept, "Accept-Language": "lit", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if i == tries - 1 or e.code == 404 and i:  # a second 404: it is not there
                raise
            time.sleep(5 * (i + 1))
            continue
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def sparql(query: str, timeout: int = 120) -> list[dict]:
    body = urllib.parse.urlencode({"query": query}).encode()
    out = json.loads(_get(SPARQL, "application/sparql-results+json", timeout, body))
    return [{k: v["value"] for k, v in b.items()} for b in out["results"]["bindings"]]


def versions(celex: str) -> list[str]:
    """The consolidated versions' CELEX numbers, oldest first ("02016R0679-20160504")."""
    q = ("PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>\nSELECT DISTINCT ?celex WHERE { ?c "
         f'cdm:resource_legal_id_celex ?celex . FILTER(STRSTARTS(STR(?celex), "0{celex[1:]}-")) }}')
    return sorted(r["celex"] for r in sparql(q))


def metadata(celex: str) -> dict:
    """Title (Lithuanian), date of the document, entry into force, end of validity, in force or not."""
    q = ("PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>\n"
         "SELECT ?date ?eif ?end ?force ?title WHERE { ?w cdm:resource_legal_id_celex ?c . "
         f'FILTER(STR(?c) = "{celex}") '
         "OPTIONAL { ?w cdm:work_date_document ?date } OPTIONAL { ?w cdm:resource_legal_date_entry-into-force ?eif } "
         "OPTIONAL { ?w cdm:resource_legal_date_end-of-validity ?end } OPTIONAL { ?w cdm:resource_legal_in-force ?force } "
         "OPTIONAL { ?e cdm:expression_belongs_to_work ?w . ?e cdm:expression_uses_language "
         "<http://publications.europa.eu/resource/authority/language/LIT> . ?e cdm:expression_title ?title } } LIMIT 20")
    rows = sparql(q)
    # several values: the first date; "1001-01-01" is the register's placeholder (REMIT's entry into force)
    pick = lambda k: min((r[k] for r in rows if r.get(k) and r[k] >= "1950"), default=None)  # noqa: E731
    # end of validity: one per consolidated version as well (2019/944: 2025-10-11 and 9999-12-31, in force): the latest
    end = max((r["end"] for r in rows if r.get("end") and r["end"] >= "1950"), default=None)
    # entry into force: never before the act's own date (2022/2065 has 2022-11-16 and an impossible 2022-02-17)
    date = pick("date")
    eif = min((r["eif"] for r in rows if r.get("eif") and r["eif"] >= (date or "1950")), default=None) or pick("eif")
    return {"date": date, "entry_into_force": eif, "end_of_validity": end,
            "in_force": any(r.get("force") in ("true", "1") for r in rows), "title": next((r["title"] for r in rows if r.get("title")), None)}


def adopted_by(title: str) -> str:
    """"… Europos Parlamento ir Tarybos reglamentas …" -> "Europos Parlamentas ir Taryba" (who adopted it)."""
    t = title.lower()
    if "europos parlamento ir tarybos" in t:
        return "Europos Parlamentas ir Europos Sąjungos Taryba"
    if "komisijos" in t:
        return "Europos Komisija"
    if "tarybos" in t:
        return "Europos Sąjungos Taryba"
    return "Europos Sąjunga"


def cited_names(scope_act: dict) -> list[str]:
    """How Lithuanian texts name an EU act before an article number (genitive): "Reglamento (ES) 2016/679", also as
    "Įgyvendinimo reglamento (ES) 2024/2690" and with "Nr." ("Reglamento (ES) Nr. 910/2014" / "(ES) 910/2014")."""
    num = scope_act["number"]  # "(ES) 2016/679", "(ES) Nr. 910/2014"
    kind = {"Direktyva": "direktyvos", "Sprendimas": "sprendimo"}.get(scope_act.get("kind") or "", "reglamento")
    nums = {num, num.replace("Nr. ", "")}
    names = {f"{kind} {n}" for n in nums} | {scope_act["genitive"]}
    return sorted(names)


def fetch_xhtml(celex: str) -> str:
    return _get(CELLAR + celex, "application/xhtml+xml").decode("utf-8")


# --- XHTML -> the register's text layout ---------------------------------------------------------------------
# a stored EU text was converted by this version: bump it with any change to the conversion that alters a text, and
# the nightly converts every EU act again (2: GDPR 43 and 65 lost a letter after "◄" under an earlier marker rule;
# 3: footnote references "( -1 )" dropped; both 2026-10-29; 4: tables keep their columns, lists laid out as tables
# with a blank first column or "1.1.1." numbers read as lists, a footnote reference between two words leaves a space;
# 2026-10-30; 5: the older layout's annexes (SOGL, NC ER: left out), the closing "Šis reglamentas privalomas visas
# …" in the last article, superscript digits as ¹²³ (AI Act 51: 10²⁵ showed as "10-25"); 6: images kept
# ("[paveikslas N]", the files in the row's `eu_images`), text between blocks, quoted articles' titles, a point's
# number and its inline text on one line, no space before "," after a footnote reference; all 2026-10-30; 7: not noted;
# 8, 2026-11-04: annexes' footnotes kept where they are at the end of the document, words after an inline element or a
# formula kept, a marker no longer taken for a first paragraph, "c)" before nested blocks, parts and sections below
# chapters, headings with no number of their own, appendices inside annexes, annexes numbered "II.A" or "A", "50 ºC")
CONVERTER = 8
# the number of a list item laid out as a table: "a)", "(iv)", "1.", "1.1.1.", "5a.", "„29." (a quoted wording), "—"
BLOCK = {X + t for t in ("p", "div", "table", "ul", "ol")}
LIST_NUM = r"„?(?:\(?[0-9a-z]{1,4}\)|\d+[a-z]?(?:\.\d+)*\.|[—–-])"
SUPERSCRIPT = str.maketrans("0123456789+−-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻")
MARKERS = re.compile(r"[▼►][A-Z]\d*|◄")  # consolidation markers: ▼B, ▼M1, ►C1 … ◄ (never the number after them)


# the layouts: a consolidated text's classes, the Official Journal's ("oj-…", an act not consolidated yet), and the
# Journal's older one (no prefix: acts as published about 2004, Directive 2004/48)
ART_TITLE = {"title-article-norm", "oj-ti-art", "ti-art"}
ART_SUBTITLE = {"stitle-article-norm", "oj-sti-art", "sti-art"}
DOC_TITLE = {"title-doc-first", "oj-doc-ti", "doc-ti"}
TITLES = ART_TITLE | ART_SUBTITLE | {"title-annex-1", "title-annex-2", "oj-doc-ti", "doc-ti"}
DIV1, DIV2 = {"title-division-1", "oj-ti-section-1", "ti-section-1"}, {"title-division-2", "oj-ti-section-2", "ti-section-2"}
# the Journal's layout may give a chapter's number a class of its own ("II SKYRIUS" in oj-ti-grseq-1, only its title in
# oj-ti-section-2: Regulation 1024/2013); that class is also used for other headings, so only a chapter's words count
NUMBERED = re.compile(r"(?:[IVXLC]+[A-Z]?|\d+[A-Z]?)\s+(?:SKYRIUS|SKIRSNIS|POSKIRSNIS|DALIS|ANTRAŠTINĖ DALIS)", re.I)


def _group_flat(root) -> None:
    """The older layout (consolidations before about 2012, ePrivacy 2002/58): article titles and their paragraphs are
    siblings in the body. Each article's elements go into a <div class="eli-subdivision" id="art_N">, its subtitle into
    a <div class="eli-title">, as the newer layout has them, so the rest reads both alike."""
    grouped = any(k.tag == X + "div" and (k.get("id") or "").startswith("art_") for k in root.iter())
    for parent in list(root.iter()):
        kids = list(parent)
        starts = [i for i, k in enumerate(kids) if k.tag == X + "p" and ART_TITLE & set(_cls(k).split())]
        if not starts or grouped:
            continue
        for i in reversed(starts):
            end = i + 1
            while end < len(kids) and not (end in starts or kids[end].tag == X + "hr"
                                           or {"footnote", "title-annex-1", "title-annex-2"} & set(_cls(kids[end]).split())
                                           or (DIV1 | DIV2) & set(_cls(kids[end]).split()) and not _subheading(kids, end)):
                end += 1
            group = kids[i:end]
            num = _strip_art(_text(kids[i]))
            div = ET.Element(X + "div", {"class": "eli-subdivision", "id": f"art_{num}"})
            for k in group:
                parent.remove(k)
                if (DIV1 | DIV2) & set(_cls(k).split()):
                    k.set("class", "norm")
                # right after the article's title, a marker aside ("1 straipsnis" ▼M1 "Dalykas …", 96/71)
                if k.tag == X + "p" and ART_SUBTITLE & set(_cls(k).split()) and all(x is div[0] or "modref" in _cls(x) for x in div):
                    t = ET.SubElement(div, X + "div", {"class": "eli-title"})
                    t.append(k)
                else:
                    div.append(k)
            parent.insert(i, div)
            kids = list(parent)
    _group_flat_annexes(root)
    _nest_appendices(root)
    _final_formula(root)
    _kept_notes(root)
    for n, img in enumerate(root.iter(X + "img"), 1):  # "[paveikslas 3]" where the image is (IMAGE)
        img.set("data-n", str(n))


SIGNED = re.compile(r"Priimta \w+,? \d{4} m\.")


def _nest_appendices(root) -> None:
    """Appendices laid out after their annex, as its siblings (<div id="app_A"> after <div id="anx_I">: the taxonomy act
    2021/2139, whose annexes I and II each end with appendices A–E): moved into the annex, as REACH XVII has them, so
    they are read with it. Left out until 2026-11-09 (the word check held the act)."""
    for parent in list(root.iter()):
        last = None
        for k in list(parent):
            i = (k.get("id") or "").strip()
            if k.tag == X + "div" and re.fullmatch(r"anx_[^_]+", i):
                last = k
            elif k.tag == X + "div" and i.startswith("app_") and last is not None:
                parent.remove(k)
                last.append(k)
            elif k.tag == X + "div" and i.startswith("art_"):
                last = None


def _final_formula(root) -> None:
    """The closing words after the last article ("Šis reglamentas privalomas visas ir tiesiogiai taikomas visose
    valstybėse narėse.", <div id="fnp_1">): the last paragraph of the last article, as the older consolidated layout
    has them (left out of 12 regulations until 2026-10-30: GDPR, the AI Act, RfG …). The place, date and signatures are not."""
    arts = [e for e in root.iter(X + "div") if "eli-subdivision" in _cls(e).split() and (e.get("id") or "").startswith("art_")]
    parent = {c: p for p in root.iter() for c in p}
    for final in [e for e in root.iter(X + "div") if (e.get("id") or "").startswith("fnp_")]:
        for p in [p for p in final.iter(X + "p") if {"norm", "oj-normal"} & set(_cls(p).split())]:
            if arts and not SIGNED.match(_text(p)):
                parent[p].remove(p)
                if len(arts[-1]):  # a paragraph apart from the one before it, however the XHTML is laid out
                    arts[-1][-1].tail = (arts[-1][-1].tail or "") + "\n"
                arts[-1].append(p)


# an image (a formula, a figure: RfG's voltage profiles, RED's GHG formulas, the N – 1 formula) in the text: shown on
# the page from the act's `eu_images` (dropped without a trace until 2026-10-30)
IMAGE = re.compile(r"\[paveikslas (\d+)\]")

ANNEX_TITLE = re.compile(r"(?:([IVXLC]+(?:\.?[A-Za-z]+)?|\d+[A-Za-z]?|[A-Z])\s+)?PRIEDAS")  # "II.A PRIEDAS" (2011/92), "XVIa"


def _group_flat_annexes(root) -> None:
    """Annexes in the older layout (SOGL 2017/1485, NC ER 2017/2196 consolidations): "I PRIEDAS" and its text are
    siblings after an <hr class="separator-annex">; each goes into a <div id="anx_I"> as the newer layout has it. They
    were left out until 2026-10-30 (SOGL's eight annexes, NC ER's one). A "KOMISIJOS PAREIŠKIMAS" with the same class
    (REMIT) is a statement, not an annex: not shown."""
    inside = {id(x) for e in root.iter() if (e.get("id") or "").startswith("anx_") for x in e.iter()}
    for parent in list(root.iter()):
        if id(parent) in inside:
            continue
        kids = list(parent)
        titled = [i for i, k in enumerate(kids) if k.tag == X + "p" and "title-annex-1" in _cls(k).split()]
        starts = [i for i in titled if ANNEX_TITLE.fullmatch(_text(kids[i]))]
        ends = lambda i: next((j for j in range(i + 1, len(kids)) if kids[j].tag == X + "hr" or "title-annex-1" in _cls(kids[j]).split()  # noqa: E731
                               or (kids[j].get("id") or "").startswith("anx_")), len(kids))
        for n, i in reversed(list(enumerate(starts, 1))):
            end = ends(i)
            div = ET.Element(X + "div", {"id": f"anx_{ANNEX_TITLE.fullmatch(_text(kids[i])).group(1) or n}"})
            for k in kids[i:end]:
                parent.remove(k)
                div.append(k)
            parent.insert(i, div)
        # a text between annexes under a title of its own ("II–VI Priedų Preambulė", 1223/2009; "II.A PRIEDAS" above
        # with ids on the others, 2011/92): it follows the annex before it, its title a line of its text
        kids = list(parent)
        for i in reversed([i for i, k in enumerate(kids) if k.tag == X + "p" and "title-annex-1" in _cls(k).split() and "PAREIŠKIMAS" not in _text(k).upper()]):
            before = next((k for k in reversed(kids[:i]) if k.tag == X + "div" and (k.get("id") or "").startswith("anx_")), None)
            if before is None:
                continue
            for k in kids[i:ends(i)]:
                parent.remove(k)
                before.append(k)
            kids[i].set("class", "norm")
            kids = list(parent)


NOTE_CLASSES = {"footnote", "note", "oj-note"}


# a note that only cites a source: an Official Journal reference, an act's or a standard's full name
CITATION = re.compile(r"\bOL\b|Oficialiojo leidinio|ELI:|^\W*\S+\W*\s*(?:\d{4} m\.|Tarybos|Komisijos|Europos Parlamento|ISO\b|EN\b)")


def _kept_notes(root) -> None:
    """Footnotes kept at the end of the document go to the end of the annex or article that refers to them, the
    reference stays in its place ("(*8)"). Until 2026-11-04 both were dropped, with words that matter: the energy-
    efficiency thresholds of Waste Directive 2008/98 annex II R1, "Santykinių verčių bazinė įtampa yra žemesnė nei
    300 kV" under RfG 25's tables, 168 more in 29 acts' annexes. A note's text may go on in the elements after it (R1's
    list, Habitats' note 2): they belong to it. An article's notes that only cite a source stay left out (D-037); an
    annex keeps all, as it does those printed inside it."""
    parent = {c: p for p in root.iter() for c in p}
    notes: dict[str, list] = {}
    for p in list(root.iter()):
        if p.tag == X + "p" and NOTE_CLASSES & set(_cls(p).split()) and (a := p.find(X + "a")) is not None and a.get("id"):
            sib = list(parent[p])
            rest = []
            for k in sib[sib.index(p) + 1:]:
                if NOTE_CLASSES & set(_cls(k).split()) and k.find(X + "a") is not None or k.tag == X + "hr" or (k.get("id") or "").startswith(("art_", "anx_")) \
                        or TITLES & set(_cls(k).split()) or (DIV1 | DIV2) & set(_cls(k).split()):
                    break
                rest.append(k)
            notes[a.get("id")] = [p, *rest]
    for k in {id(x): x for v in notes.values() for x in v[1:]}.values():
        k.set("class", (_cls(k) + " footnote").strip())  # a note's continuation is the note: not the act's text when left out
    moved: set[str] = set()
    for box in [e for e in root.iter(X + "div") if re.fullmatch(r"anx_[^_]+", (e.get("id") or "").strip())
                or ("eli-subdivision" in _cls(e).split() and (e.get("id") or "").startswith("art_"))]:
        annex = (box.get("id") or "").startswith("anx_")
        inside = set(map(id, box.iter()))
        shown: dict[str, str] = {}  # the same words under the same mark (RfG 25's tables print each note for each table)
        for a in [a for a in box.iter(X + "a") if (a.get("href") or "").startswith("#") and a.get("href")[1:] in notes]:
            key = a.get("href")[1:]
            els = notes[key]
            if id(els[0]) in inside:
                continue
            words = " ".join("".join(els[0].itertext()).split())
            words = re.sub(r"^\(\s*\S*\s*\)\s*", "", words)
            if not annex and CITATION.search(words):
                continue
            # (a note's own mark may be empty in EUR-Lex, "( <span/> )": CRA 2024/2847, 2024/1157; the reference has it)
            mark = _plain_ref(a, parent)
            if key in moved or shown.get(words) == mark:
                continue
            shown[words] = mark
            moved.add(key)
            _plain_ref(els[0].find(X + "a"), parent, mark)
            for el in els:
                parent[el].remove(el)
                el.set("class", " ".join(c for c in _cls(el).split() if c not in NOTE_CLASSES) or "norm")
                el.tail = None
                box.append(el)
                parent[el] = box


def _plain_ref(a, parent, default: str = "") -> str:
    """A footnote reference as plain text: "(" <a><span>*8</span></a> ")" -> "(*8)"; returns its mark."""
    t = "".join(a.itertext()).strip() or default
    for k in list(a):
        a.remove(k)
    a.text, a.tail = t, (a.tail or "")
    for k in ("id", "href"):
        a.attrib.pop(k, None)
    up = parent[a]
    kids = list(up)
    i = kids.index(a)
    if i:
        if (kids[i - 1].tail or "").rstrip().endswith("("):
            kids[i - 1].tail = kids[i - 1].tail.rstrip()
    elif (up.text or "").rstrip().endswith("("):
        up.text = up.text.rstrip()
    if a.tail.lstrip().startswith(")"):
        a.tail = a.tail.lstrip()
    return t


def _subheading(kids: list, i: int) -> bool:
    """A heading class on text inside an article ("A) Procedūra ir teisės apimtis" in 987/2009 25, its paragraphs after
    it): what follows is more text, not the next article, as after a chapter's heading."""
    for k in kids[i + 1:]:
        c = set(_cls(k).split())
        if ART_TITLE & c or k.tag == X + "hr" or c & {"title-annex-1", "title-annex-2", "footnote"} or (k.get("id") or "").startswith("art_"):
            return False  # (the articles after it may be grouped already)
        if not (DIV1 | DIV2) & c and "modref" not in c and _text(k):
            return True
    return False


def _strip_art(t: str) -> str:
    # EUR-Lex prints a few as "70 straipsnis." (2018/1972), "2 STRAIPSNIS" (2024/573), "26 straipsniai" (CRR)
    t = re.sub(r"\s*straipsni(?:s|ai)\.?$", "", t, flags=re.I).rstrip(".")
    # and typos in a heading: "30J straipsnis" (2003/87), "18 straipsnis b" (2003/96): the article is 30j, 18b
    # (none of the stored texts had either form on 2026-11-09, so no article already on the site changes)
    m = re.fullmatch(r"(\d+)(?:\s*straipsnis\s+([a-z])|([A-Z]))", t)
    return f"{m.group(1)}{(m.group(2) or m.group(3)).lower()}" if m else t


def _art_num(e) -> str:
    p = next(x for x in e if x.tag == X + "p" and ART_TITLE & set(_cls(x).split()))
    return _strip_art(_text(p))


def _cls(e) -> str:
    return e.get("class") or ""


def _text(e, skip=("arrow", "modref", "footnote", "super", "superscript")) -> str:
    """The element's words, consolidation markers and footnote references left out; superscript digits as ¹²³, other
    superscripts as -n (as html_to_text)."""
    out = []

    def walk(x):
        c = _cls(x)
        if x.tag == X + "img":
            out.append(f" [paveikslas {x.get('data-n')}] " + (x.tail or ""))
            return
        if x.tag == X + "a" and (x.get("href") or "").startswith("#ntr"):  # a footnote reference "(1)"
            if x.tail:  # "2019/944 (1)2 straipsnio" (NIS2 annex I): its words apart, as the reference kept them
                if x.tail[:1] in ",.;:)" and out:  # "2012/148/ES (1), tiek" is "2012/148/ES, tiek" (2024/1788 II)
                    out[-1] = out[-1].rstrip()
                out.append((" " if x.tail[:1].isalnum() else "") + x.tail)
            return
        if x.tag == X + "a" and (x.get("id") or "").startswith("src.") and (x.get("href") or "").startswith("#"):
            # a footnote reference to the Official Journal: "(" <a id="src.E0008" href="#E0008">8</a> ")", brackets
            # and all (it showed as "( -1 )" until 2026-10-29; the footnotes themselves are not shown)
            tail = x.tail or ""
            if out and out[-1].rstrip().endswith("(") and tail.lstrip().startswith(")"):
                out[-1] = out[-1].rstrip()[:-1].rstrip()
                tail = tail.lstrip()[1:]
                if tail[:1].isalnum() or tail[:1] in "(„":
                    tail = " " + tail
            out.append(tail)
            return
        if any(s in c.split() for s in skip[:2]):
            if x.tail and x is not e:
                out.append(x.tail)
            return
        if x.tag == X + "span" and {"superscript", "oj-super"} & set(c.split()):
            # digits as superscripts (10²⁵, a footnote mark "standartuose¹"): an EU act numbers nothing with them, and
            # the register's "-n" (5-1 straipsnis) would read 10²⁵ as "10-25"
            s = "".join(x.itertext()).strip()
            # the degree's "o" ("50 ºC (122 ºF)", 1272/2008 VI) showed as "50-oC"
            out.append(s.translate(SUPERSCRIPT) if re.fullmatch(r"[0-9+−-]+", s) else "º" if s == "o" else "-" + s)
            if x.tail:
                out.append(x.tail)
            return
        if x.text:
            out.append(x.text)
        for ch in x:
            walk(ch)
        if x.tail and x is not e:
            out.append(x.tail)
    walk(e)
    return " ".join(MARKERS.sub(" ", "".join(out)).split())


def _blocks(e, lines: list[str], top: bool = True) -> None:
    """Lines of an article (or annex) body, in document order: a numbered part "1. …", a point "a) …", a paragraph."""
    if e.get("data-wrap") is None:
        _inline_runs(e)
    children = list(e)
    for i, ch in enumerate(children):
        if i and e.get("data-wrap") is None:  # text between two blocks: ", N – 1 ≥ 100 %" after a formula (2017/1938 II)
            _loose(children[i - 1].tail, lines)
        c = _cls(ch).split()
        if ch.tag == X + "div" and "eli-title" in c:
            continue
        # an appendix inside its annex: "anx_…" (REACH XVII), "app_A" (taxonomy 2021/2139, lost until 2026-11-09)
        if ch.tag == X + "div" and (ch.get("id") or "").startswith(("anx_", "app_")):
            lines += _annex_titles(ch)
            _blocks(ch, lines, False)
            continue
        # the article's own title is its first line already; an article quoted in an amendment ("„8a straipsnis",
        # 2024/1789 84) keeps its title (lost until 2026-10-30). Annex titles are taken from anywhere in the annex.
        if ch.tag == X + "p" and TITLES & set(c) and (top or not (ART_TITLE | ART_SUBTITLE) & set(c)):
            continue
        if ch.tag == X + "div" and "grid-container" in c:  # a point: "a)" + its text, sub-points nested in it
            cols = [x for x in ch if x.tag == X + "div"]
            num = _text(cols[0]) if cols else ""
            body = cols[1] if len(cols) > 1 else None
            if body is None:
                continue
            # its first paragraph after the number, then everything else in order (sub-points, further paragraphs, the
            # ";" closing a quoted wording: AI Act 108)
            kids = list(body)
            head = (body.text or "").strip()
            k = 0
            if not head and kids and (kids[0].tag == X + "p" or _leaf(kids[0])):
                head, k = _text(kids[0]), 1
            lines.append(f"{num} {head}".strip())
            if k:  # the words after a formula that opens the point (CRR 325bc)
                _loose(kids[0].tail, lines)
            for x in kids[k:]:
                if x.tag == X + "p":
                    if t := _text(x):
                        lines.append(t)
                else:
                    _blocks(_wrap(x), lines, False)
                if x.tail and x.tail.strip():  # text after a quoted wording ("“;"): it ends that line
                    t = " ".join(x.tail.split())
                    lines[-1] += t if t[:1] in ";:,.)" else " " + t
            continue
        if ch.tag == X + "div" and "norm" in c and any(x.tag == X + "span" and "no-parag" in _cls(x) for x in ch):
            num = next(_text(x) for x in ch if x.tag == X + "span" and "no-parag" in _cls(x))
            rest = [x for x in ch if not (x.tag == X + "span" and "no-parag" in _cls(x))]
            head = rest[0] if rest else None
            if head is not None and "inline-element" in _cls(head):
                _inline_runs(head)
                first, k = _head_of_part(head)
                lines.append(f"{num} {first}".strip())
                for x in list(head)[k:]:
                    _blocks(_wrap(x), lines, False)
                    _loose(x.tail, lines)  # the words after a formula in its own paragraph ("<p><img/></p>), apskaičiuoto …", CRR 132)
                for x in rest[1:]:
                    _blocks(_wrap(x), lines, False)
                    _loose(x.tail, lines)
            else:
                lines.append(num)
                for x in rest:
                    _blocks(_wrap(x), lines, False)
                    _loose(x.tail, lines)
            continue
        if ch.tag == X + "table":
            rows = [tr for body in [ch, *ch.findall(X + "thead"), *ch.findall(X + "tbody")] for tr in body.findall(X + "tr")]
            spans: dict[int, int] = {}  # column -> rows still covered by a cell above (rowspan)
            for tr in rows:  # not nested tables' rows
                tds = [td for td in tr if td.tag in (X + "td", X + "th")]
                lead = next((i for i, td in enumerate(tds) if _text(td) or len(td)), len(tds))
                item = tds[lead:]  # a list laid out as a table: ["", ] "a)" | text, "1.1.1." | text (2024/2690)
                if not spans and len(item) == 2 and re.fullmatch(LIST_NUM, _text(item[0])):
                    num, kids = _text(item[0]), list(item[1])
                    k = next((i for i, x in enumerate(kids) if x.tag in BLOCK), len(kids))  # its text: inline up to a block
                    lead = ET.Element(X + "div")
                    lead.text = item[1].text
                    lead.extend(copy.deepcopy(x) for x in kids[:k])
                    if k:  # the tail of the last inline element is still the head's
                        lead[-1].tail = kids[k - 1].tail
                    head = _text(lead)
                    if not head and k < len(kids) and (kids[k].tag == X + "p" or _leaf(kids[k])):
                        head, k = _text(kids[k]), k + 1
                        lines.append(f"{num} {head}".strip())
                        _loose(kids[k - 1].tail, lines)
                    else:
                        lines.append(f"{num} {head}".strip())
                    for x in kids[k:]:
                        if x.tag not in _OWN_LINE:  # an inline element between two paragraphs: "(H" <span>T</span> "(τ)) –"
                            if t := _text(x):  # (2013/59/Euratom 4(15), 4(33): the subscript was lost until 2026-11-10)
                                lines[-1] += " " + t
                        else:
                            _blocks(_wrap(x), lines, False)
                        if x.tail and x.tail.strip():  # "“;" after a quoted article (2024/1789 84), as in a point
                            t = " ".join(x.tail.split())
                            lines[-1] += t if t[:1] in ";:,.)" else " " + t
                    continue
                # a table: one line a row, its cells joined by " | ", a cell spanning rows or columns leaves empty
                # cells where it reaches, so every row of the table has as many cells and the columns stay in line
                cells, col = [], 0
                for td in tds:
                    while spans.get(col):
                        spans[col] -= 1
                        cells.append("")
                        col += 1
                    paras = [_text(x) for x in td if x.tag in BLOCK] if not (td.text or "").strip() else []
                    cells.append(paras if len(paras) > 1 and all(paras) and _squash(_text(td)) == _squash("".join(paras)) else _text(td))
                    n = int(td.get("colspan") or 1)
                    for j in range(col, col + n):
                        if int(td.get("rowspan") or 1) > 1:
                            spans[j] = int(td.get("rowspan")) - 1
                    cells += [""] * (n - 1)
                    col += n
                while spans.get(col):  # spanned cells at the end of the row
                    spans[col] -= 1
                    cells.append("")
                    col += 1
                spans = {j: v for j, v in spans.items() if v}
                # a cell of several paragraphs ("— …" entries, NIS2 annex I): one line each, the other cells empty below;
                # only the row's last cell with text, so the words keep their order (else the paragraphs share one line)
                split = [i for i, c in enumerate(cells) if isinstance(c, list)]
                if len(split) != 1 or any(cells[split[0] + 1:]):
                    cells = [" ".join(c) if isinstance(c, list) else c for c in cells]
                depth = max((len(c) for c in cells if isinstance(c, list)), default=1)
                for i in range(depth):
                    row = [(c[i] if i < len(c) else "") if isinstance(c, list) else (c if i == 0 else "") for c in cells]
                    if any(row):
                        lines.append(" | ".join(row))
            continue
        if ch.tag == X + "div" and "oj-enumeration-spacing" in c:
            # "3." in an inline <p>, its text in inline <p>s or a bare <span> (lost until 2026-10-30), then paragraphs:
            # one line "3. …" (2024/1788 annex II)
            kids = list(ch)
            k = 0
            while k < len(kids) and (kids[k].tag == X + "span" or "display: inline" in (kids[k].get("style") or "")):
                k += 1
            if head := " ".join(t for t in (_text(x) for x in kids[:k]) if t):
                lines.append(head)
            for x in kids[k:]:
                _blocks(_wrap(x), lines, False)
            continue
        if ch.tag == X + "p":
            t = _text(ch)
            if t:
                lines.append(t)
            continue
        if ch.tag == X + "div" and _leaf(ch):  # a list item's text right in a <div class="list"> (GDPR 53)
            if t := _text(ch):
                lines.append(t)
            continue
        if ch.tag == X + "img":  # a figure's image (RfG 14's profiles)
            img = copy.copy(ch)
            img.tail = None  # the text after it is placed below (_loose)
            lines.append(_text(_wrap(img)))
            continue
        if ch.tag in (X + "div", X + "figure"):
            # a number right in the div before its nested blocks ("c)" <div>— …, 2004/38 7; "1)" <div>a) …, 1215/2012 7):
            # on the first line inside (lost until 2026-11-04); other text before them as a line of its own
            t = " ".join((ch.text or "").split())
            ch.text = None
            n = len(lines)
            _blocks(ch, lines, False)
            if t:
                if re.fullmatch(LIST_NUM, t) and len(lines) > n:
                    lines[n] = f"{t} {lines[n]}"
                else:
                    lines.insert(n, t)
    if children and e.get("data-wrap") is None:
        _loose(children[-1].tail, lines)


# what a line can't be broken inside: an element in the middle of the text between two blocks
_OWN_LINE = BLOCK | {X + "figure", X + "img", X + "hr"}


def _inline_runs(e) -> None:
    """Text between blocks with an inline element in it (<p><img/></p> "kai α yra 1 %, T"<span>k</span>" ir T"<span>l</span>
    " yra …", CRR 325ay; the span and the words after it were lost until 2026-11-04) as a paragraph of its own. Plain text
    between blocks stays a tail for _loose."""
    kids = list(e)
    if not any(k.tag in _OWN_LINE for k in kids) or all(k.tag in _OWN_LINE for k in kids):
        return
    out, run = [], []
    for k in kids + [None]:
        if k is not None and k.tag not in _OWN_LINE:
            run.append(k)
            continue
        if run:
            para = ET.Element(X + "p", {"class": "norm"})
            if out:
                para.text, out[-1].tail = out[-1].tail, None
            else:
                para.text, e.text = e.text, None
            para.extend(run)  # the last one's tail, the end of the text, stays with it
            out.append(para)
            run = []
        if k is not None:
            out.append(k)
    for k in kids:
        e.remove(k)
    e.extend(out)


def _annex_titles(e) -> list[str]:
    """An annex's title lines: those before its text, without the appendices inside it. A title further down ("1–6
    priedėliai", REACH XVII) stays where it is, a line of the text."""
    nested = {id(x) for d in e.iter(X + "div") if d is not e and (d.get("id") or "").startswith(("anx_", "app_")) for x in d.iter()}
    titles, leading = [], True
    for p in e.iter(X + "p"):
        if id(p) in nested:
            continue
        if {"title-annex-1", "title-annex-2", "oj-doc-ti"} & set(_cls(p).split()):
            if leading:
                if t := _text(p):
                    titles.append(t)
            else:
                p.set("class", "norm")
        elif _text(p):
            leading = False
    return titles


def _loose(tail: str | None, lines: list[str]) -> None:
    if t := " ".join((tail or "").split()):
        if lines and t[:1] in ";:,.)":
            lines[-1] += t
        else:
            lines.append(t)


def _squash(t: str) -> str:
    return re.sub(r"[\s|]+", "", t)


def _leaf(e) -> bool:
    """A div holding only text and inline elements (no paragraphs, lists or divs of its own)."""
    return e.tag == X + "div" and not any(x.tag in (X + "p", X + "div", X + "table") for x in e) and bool(_text(e))


def _wrap(x):
    w = ET.Element(X + "div", {"data-wrap": "1"})  # its child's tail is the caller's to place
    w.append(x)
    return w


def _head_of_part(e) -> tuple[str, int]:
    """A numbered part's first line: its text up to its first list, table or second paragraph, and how many child
    elements that took (the rest become lines of their own)."""
    c = ET.Element(e.tag, e.attrib)
    c.text = e.text
    k = 0
    for x in e:
        if x.tag == X + "div" and ("grid-container" in _cls(x).split() or x.find(f".//{X}div[@class]") is not None and
                                   any("grid-container" in _cls(y).split() for y in x.iter(X + "div"))):
            break
        # a second paragraph, or text after the first in plain divs ("A metodas", PSD2 9): lines of their own; a marker
        # before the first paragraph is no paragraph (MiFIR 35, IED 73 lost their first one until 2026-11-04, "►M8" <p>…)
        if x.tag in (X + "p", X + "div") and _text(c):
            break
        if x.tag == X + "table":  # a list laid out as tables ("1)" | definition: SOGL 3)
            break
        c.append(x)
        k += 1
    return _text(c), k


def _structural(l: str) -> bool:
    return not l.startswith("„") and bool(RE_ART.match(l) or _heading(l) or RE_ANNEX.match(l))  # („: the parser reads a quote)


def _joined_headings(lines: list[str]) -> list[str]:
    """A heading split over two lines ("II" / "SKYRIUS", eIDAS; "II" / "ANTRAŠTINĖ DALIS", the customs code; "3A" /
    "SKYRIUS", EMIR; "II ANTRAŠTINĖ" / "DALIS KRIPTOTURTAS, …", MiCA; "1" / "POSKIRSNIS", 2014/24) or three ("II" /
    "ANTRAŠTINĖ" / "DALIS TABAKO GAMINIAI", 2014/40), or run into its title ("2 SKIRSNIS. BUDRUMAS", MDR): the number
    and kind on one line, the title on the next, as the parser reads headings."""
    out: list[str] = []
    for l in lines:
        if out and re.fullmatch(r"(?:SKYRIUS|SKIRSNIS|SKIRISNIS|POSKIRSNIS|DALIS|ANTRAŠTINĖ|ANTRAŠTINĖ DALIS)", l) and re.fullmatch(r"[IVXLC]+[A-Z]?|\d+[A-Z]?", out[-1]):
            out[-1] = f"{out[-1]} {l}"
        elif out and (m := re.fullmatch(r"DALIS (.+)", l)) and re.fullmatch(r"(?:[IVXLC]+[A-Z]?|\d+[A-Z]?) ANTRAŠTINĖ", out[-1]) \
                and m.group(1).isupper():
            out[-1] = f"{out[-1]} DALIS"
            out.append(m.group(1))
        elif (m := re.fullmatch(r"(\d+[A-Z]? (?:SKYRIUS|SKIRSNIS|DALIS))\.(?: ([^a-ząčęėįšųūž]+))?", l)):
            out += [m.group(1)] + ([m.group(2)] if m.group(2) else [])  # ("2 SKIRSNIS." alone, MDR)
        else:
            out.append(l)
    return out


def to_text(xhtml: str, version_from: str, version_to: str | None = None) -> tuple[str, dict]:
    """The act as the register's text layout, and what was found (title, article count) for the checks."""
    xhtml = re.sub(r"<!DOCTYPE[^>]*>", "", xhtml)
    root = ET.fromstring(xhtml)
    _group_flat(root)
    body = root.find(X + "body")
    lines = [f"Suvestinė redakcija nuo {version_from}" + (f" iki {version_to}" if version_to else "")]
    title: list[str] = []
    n_art = 0
    in_annex = False
    div_lines: set[str] = set()
    # an article's own text (a chapter quoted in an amendment, CRR 520) is read with the article
    in_art = {id(x) for e in body.iter(X + "div") if "eli-subdivision" in _cls(e).split() and (e.get("id") or "").startswith("art_")
              for x in e.iter() if x is not e}
    for e in body.iter():
        if id(e) in in_art:
            continue
        c = _cls(e).split()
        if e.tag == X + "p" and DOC_TITLE & set(c) and not n_art and not in_annex:
            if _text(e) not in title:  # a consolidated text repeats the title (cover, then the act)
                title.append(_text(e))
        elif e.tag == X + "p" and ((DIV1 | DIV2) & set(c) or "oj-ti-grseq-1" in c and NUMBERED.fullmatch(_text(e))) and not in_annex:
            lines.append(_text(e).upper())
            div_lines.add(lines[-1])
        elif e.tag == X + "div" and "eli-subdivision" in c and (e.get("id") or "").startswith("art_") and not in_annex:
            num = _art_num(e)
            sub = e.find(f"{X}div[@class='eli-title']")
            lines.append(f"{num} straipsnis" + (f". {_text(sub)}" if sub is not None and _text(sub) else ""))
            body_lines: list[str] = []
            _blocks(e, body_lines)
            # a chapter and articles quoted in an amendment, with no „ to tell (CRR 520): text of this article
            lines += [QUOTED + l if _structural(l) else l for l in _joined_headings(body_lines)]
            n_art += 1
        elif e.tag == X + "div" and re.fullmatch(r"anx_[^_]+", (e.get("id") or "").strip()):  # "I PRIEDAS", its title, its text
            in_annex = True
            lines += _annex_titles(e)
            _blocks(e, lines)
    lines = _joined_headings(lines)
    # a heading with no number of its own, before an article (Habitats 92/43: "RŪŠIŲ APSAUGA"): not a chapter's title
    for i, l in enumerate(lines):
        if RE_ANNEX.match(l):  # (an annex's title may read the same: 883/2004 X)
            break
        if l in div_lines and not _heading(l) and not (i and (_heading(lines[i - 1]) or lines[i - 1] in div_lines)):
            lines[i] = HEADING + l
    text = "\n".join(lines) + "\n"
    images = {img.get("data-n"): img.get("src") for img in root.iter(X + "img")
              if (img.get("src") or "").startswith("data:image/") and f"[paveikslas {img.get('data-n')}]" in text}
    return text, {"title": " ".join(title), "articles": n_art, "images": images}


def check(xhtml: str, text: str) -> list[str]:
    """Every article's words and every annex's text, in order, as in the XHTML (markers and footnote references
    aside): the problems found."""
    root = ET.fromstring(re.sub(r"<!DOCTYPE[^>]*>", "", xhtml))
    _group_flat(root)
    act = parse(text)
    ours = {a.label: " ".join(" ".join([a.title or ""] + [b.text for b in a.blocks]).split()) for a in act.main.articles}
    problems = [] if act.main.articles else ["no articles parsed"]  # a layout we can't read must not pass as empty
    for e in root.iter(X + "div"):
        if "eli-subdivision" in _cls(e).split() and (e.get("id") or "").startswith("art_"):
            num = _art_num(e)
            want = re.sub(re.escape(num) + r"\s+straipsni(?:s|ai)\.?", "", _text(e), count=1, flags=re.I)
            head = _text(next(x for x in e if x.tag == X + "p" and ART_TITLE & set(_cls(x).split())))
            if not re.match(re.escape(num) + r"\s+straipsni", head, flags=re.I):  # a heading typo _strip_art reads ("18 straipsnis b")
                want = _text(e).replace(head, "", 1)
            got = ours.get(num.replace(" ", ""))
            # NFC as the parse reads it: "·" U+0387 in the XHTML is U+00B7 here (RfG 13); a space before ";" aside
            # ("“ ;" after a quoted article is "“;" here, 2024/1789 84)
            # (a space after a formula aside: the words after it may be a line of their own, CRR 154)
            norm = lambda t: unicodedata.normalize("NFC", re.sub(r"(\[paveikslas \d+\][;:,.)]*)\s+", r"\1", re.sub(r"\s+(?=[;:,.)])", "", re.sub(r"\s+", " ", re.sub(r"[|]", " ", t))).strip()))  # noqa: E731
            if got is None:
                problems.append(f"article {num}: not parsed")
            elif norm(got) != norm(want):
                problems.append(f"article {num}: text differs")
    # annexes, in order: letters and punctuation as in the XHTML; spacing aside, as a table cell's heading runs
    # into its first paragraph there with no space ("išskaidymas<p>Vartotojo", EERD I)
    theirs = [e for e in root.iter(X + "div") if re.fullmatch(r"anx_[^_]+", (e.get("id") or "").strip())]
    # an annex's appendices ("1 PRIEDĖLIS", REACH XVII) are in its element here, pages of their own in ours
    parsed: list[list] = []
    for a in act.main.annexes:
        t = _squash(" ".join([a.header, a.title] + [b.text for b in a.blocks]))
        if "priedėlis" in a.header.lower() and parsed:
            parsed[-1][1] += t
        else:
            parsed.append([a, t])
    if len(theirs) != len(parsed):
        problems.append(f"annexes: {len(parsed)} parsed, {len(theirs)} in the XHTML")
    for (a, t), e in zip(parsed, theirs):
        if t != unicodedata.normalize("NFC", _squash(_text(e))):
            problems.append(f"annex {a.num or e.get('id')[4:].strip()}: text differs")
    return problems + _check_words(root, text)


def _plain_words(root) -> list[str]:
    """Every word of the document from the first article on, read plainly (itertext, not the conversion's reading):
    footnote references, consolidation markers and footnotes outside annexes left out (annexes keep theirs, as shown),
    and the statements after the act (REMIT), the place, date and signatures, the Official Journal's ELI/ISSN lines."""
    out: list[str] = []
    started = False

    def walk(e, in_annex: bool) -> None:
        nonlocal started
        c, i = set(_cls(e).split()), e.get("id") or ""
        if not started and (i.startswith("art_") or (e.tag == X + "p" and (ART_TITLE | DIV1 | DIV2) & c)):
            started = True
        in_annex = in_annex or i.startswith(("anx_", "art_"))  # footnotes in an article: an amendment's, shown
        skip = (c & {"arrow", "modref", "oj-signatory", "signatory"} or ("toc-item" in c and not in_annex) or (c & {"footnote", "note", "oj-note"} and not in_annex)
                or (e.tag == X + "a" and ((e.get("href") or "").startswith("#ntr") or (e.get("id") or "").startswith("src.")))
                or (e.tag == X + "p" and re.match(r"(ELI: http|ISSN \d)", _text(e)) or SIGNED.match(_text(e))))
        block = e.tag in {X + t for t in ("p", "div", "td", "th", "tr", "li", "br", "table")}
        # a statement published after the act, as a document of its own (Regulation 2018/302: "Komisijos pareiškimas")
        if e.tag == X + "div" and started and any("pareiškimas" in _text(p).lower() for p in e.iter(X + "p") if "oj-doc-ti" in _cls(p).split()):
            skip = True
        if not skip:
            if started and (e.text or block):
                out.append((" " if block else "") + (e.text or ""))
            statement = False
            for ch in e:
                if ch.tag == X + "p" and "title-annex-1" in _cls(ch).split():
                    statement = "PAREIŠKIMAS" in _text(ch).upper()
                elif ch.tag == X + "hr":
                    statement = False
                if statement:
                    if started and ch.tail:
                        out.append(ch.tail)
                    continue
                walk(ch, in_annex)
        if started and (e.tail or block):
            out.append((" " if block else "") + (e.tail or ""))

    walk(root.find(X + "body"), False)
    return _words("".join(out))


def _words(t: str) -> list[str]:
    t = IMAGE.sub(" ", MARKERS.sub(" ", t))  # an image's place: no words in the XHTML
    return re.findall(r"\w+", unicodedata.normalize("NFKC", t).lower())  # NFKC: ²⁵ is 25


def _check_words(root, text: str, run: int = 4) -> list[str]:
    """An independent check of the whole text: no run of `run` or more words of the XHTML missing from ours, none in
    ours that the XHTML hasn't (the checks above read the XHTML as the conversion does, so a part it never reads, such
    as the older layout's annexes until 2026-10-30, passed them unseen). Shorter differences are left to them:
    a footnote number run into the word before it in a plain reading ("2019/9442" for "2019/944 (2)"). Our version
    line is not compared."""
    import difflib
    theirs, ours = _plain_words(root), _words(text.split("\n", 1)[1])
    problems = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, theirs, ours, autojunk=False).get_opcodes():
        # the list of annex titles some acts print after their closing formula ("PRIEDAI I Bendrieji … II …", MDR,
        # IVDR): an index, not text; each annex follows in full and is checked above
        if tag == "delete" and theirs[i1:i1 + 1] == ["priedai"] and theirs[max(0, i1 - 3):i1] == ["visose", "valstybėse", "narėse"]:
            continue
        if tag != "equal" and max(i2 - i1, j2 - j1) >= run:
            where = " ".join(theirs[max(0, i1 - 5):i1])
            problems.append(f"after „…{where}“: {i2 - i1} words in the XHTML, {j2 - j1} here "
                            f"(„{' '.join((theirs[i1:i2] or ours[j1:j2])[:8])} …“)")
    return problems


# --- the older HTML: acts adopted before Lithuania joined ---------------------------------------------------------
# Directive 2003/88, Regulation 261/2004, Directive 2001/55 have no XHTML in Lithuanian, and were held as "no Lithuanian
# text" until 2026-11-04: CELLAR has it as text/html from the Special Edition, a <p> a line, footnotes as "[1]".
LEGACY_FIGURE = "+++++ TIFF +++++"  # EUR-Lex's own placeholder for what it holds only as a picture
LEGACY_FIGURE_NOTE = "[paveikslas: šio teksto duomenyse jo nėra – žr. oficialų tekstą EUR-Lex]"
_LEGACY_REF = re.compile(r"\s*\[\d+\]")
_LEGACY_NOTE = re.compile(r"\[\d+\]\s")
_LEGACY_ART = re.compile(r"\d+[a-z]{0,2} straipsnis")
_LEGACY_ANNEX = re.compile(r"(?:[IVXLC]+|\d+)?\s*PRIEDAS")


def fetch_legacy(celex: str) -> str:
    return _get(CELLAR + celex, "text/html").decode("utf-8")


def _legacy_lines(html: str, celex: str = "") -> list[str]:
    """The act's lines after "PRIĖMĖ …:"; LookupError if this is not its Lithuanian text."""
    m = re.search(r"<TXT_TE>(.*?)</TXT_TE>", html, re.S)
    if not m or not re.search(r'<html[^>]*\blang="LT"', html):  # another language is never a fallback
        raise LookupError(f"{celex}: no Lithuanian text on EUR-Lex")
    lines = [" ".join(htmllib.unescape(re.sub(r"<[^>]+>", "", p)).split()) for p in re.findall(r"<p>(.*?)</p>", m.group(1), re.S)]
    start = next((i for i, l in enumerate(lines) if l.startswith("PRIĖMĖ")), None)
    if start is None:
        raise ValueError(f"{celex}: no enacting words in the text")
    return [l for l in lines[start + 1:] if l]


def legacy_to_text(html: str, version_from: str, celex: str = "") -> tuple[str, dict]:
    """The act as the register's text layout, as to_text: footnotes and their references left out outside annexes, the
    place, date and signatures left out."""
    src = _legacy_lines(html, celex)
    out = [f"Suvestinė redakcija nuo {version_from}"]
    in_annex = signing = False
    n_art = i = 0
    while i < len(src):
        l, i = src[i], i + 1
        if not l.strip("-"):
            signing = False
            continue
        if _LEGACY_ANNEX.fullmatch(l):
            in_annex, signing = True, False
        elif signing or (not in_annex and l.startswith("Priimta ")):
            signing = not _LEGACY_NOTE.match(l)
            if signing:
                continue
        if not in_annex:
            if _LEGACY_NOTE.match(l):
                continue
            l = _LEGACY_REF.sub("", l)
        if l == LEGACY_FIGURE:
            out.append(LEGACY_FIGURE_NOTE)
        elif not in_annex and _LEGACY_ART.fullmatch(l):
            n_art += 1
            # its title, if the next line is one: no number, no end of a sentence
            t = _LEGACY_REF.sub("", src[i]) if i < len(src) else ""
            if t and t[0].isupper() and t[-1] not in ".;:," and len(t) < 200 and not _LEGACY_ART.fullmatch(t) and not t.isupper():
                out.append(f"{l}. {t}")
                i += 1
            else:
                out.append(l)
        else:
            out.append(re.sub(r"\s*\|$", "", l))  # a table's row: "a | b |"
    return "\n".join(out) + "\n", {"title": "", "articles": n_art, "images": {}}


def check_legacy(html: str, text: str, celex: str = "", run: int = 4) -> list[str]:
    """Every word of the source in ours in order (footnote references aside; the block from "Priimta" to the end of the
    footnotes left out), nothing of ours that isn't there; every article and annex read."""
    import difflib
    src = [l for l in _legacy_lines(html, celex) if l != LEGACY_FIGURE]
    act = parse(text)
    problems = [] if act.main.articles else ["no articles parsed"]
    arts, annexes = sum(1 for l in src if _LEGACY_ART.fullmatch(l)), sum(1 for l in src if _LEGACY_ANNEX.fullmatch(l))
    if arts != len(act.main.articles):
        problems.append(f"articles: {len(act.main.articles)} parsed, {arts} in the text")
    if annexes != len(act.main.annexes):
        problems.append(f"annexes: {len(act.main.annexes)} parsed, {annexes} in the text")
    problems += [f"article {a.label}: empty" for a in act.main.articles if not a.blocks]
    theirs = _words(_LEGACY_REF.sub(" ", " ".join(src)))
    ours = _words(_LEGACY_REF.sub(" ", text.split("\n", 1)[1].replace(LEGACY_FIGURE_NOTE, " ")))
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, theirs, ours, autojunk=False).get_opcodes():
        if tag == "delete" and theirs[i1:i1 + 1] == ["priimta"]:
            continue
        if tag != "equal" and max(i2 - i1, j2 - j1) >= run:
            where = " ".join(theirs[max(0, i1 - 5):i1])
            problems.append(f"after „…{where}“: {i2 - i1} words in the source, {j2 - j1} here („{' '.join((theirs[i1:i2] or ours[j1:j2])[:8])} …“)")
    return problems


# --- when an EU act's articles apply (D-037) -----------------------------------------------------------------
# An EU act's final article says from when it applies, often in stages ("Jis taikomas nuo 2027 m. gruodžio 11 d.
# Tačiau 14 straipsnis taikomas nuo 2026 m. rugsėjo 11 d., o IV skyrius (35–51 straipsniai) – nuo 2026 m. birželio
# 11 d."). Only dates after today change a label: an article that applies later is "pending" from that date; a part
# of one, or one applying later only in some cases ("kiek tai susiję su …"), keeps its label with a note naming the
# date. Nothing is guessed: a sentence with a later date that names nothing we can read becomes an act-level notice.
_LT_MONTHS = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", "liepos", "rugpjūčio", "rugsėjo",
              "spalio", "lapkričio", "gruodžio"]
RE_DATE = re.compile(r"(\d{4}) m\. (" + "|".join(_LT_MONTHS) + r") (\d{1,2}) d\.")
_N = r"\d+[a-z]{0,2}"
RE_ARTS = re.compile(rf"((?:{_N}(?:\s*[–-]\s*{_N})?)(?:(?:,\s*| ir | bei )(?:{_N}(?:\s*[–-]\s*{_N})?))*) straipsn(?:is|io|į|iai|ių|ius|iuose)\b")
RE_ART_PART = re.compile(rf"({_N}) straipsnio\b")
RE_CHAPTERS = re.compile(r"((?:[IVXLC]+[A-Z]?)(?:(?:,\s*| ir | bei )(?:[IVXLC]+[A-Z]?))*) skyri(?:us|ai|ių|ių|ų)\b")
RE_SECTIONS = re.compile(r"([IVXLC]+[A-Z]?) skyriaus ((?:\d+)(?:(?:,\s*| ir )\d+)*) skirsni(?:s|ai|ų)\b")
RE_ONE_CHAPTER = re.compile(r"([IVXLC]+[A-Z]?) skyrius\b")
CONDITIONAL = re.compile(r"kiek tai susiję|sutartims|gaminiams|kurie įsigalioja po|kai\b|jeigu|atveju", re.I)


def _starts(t: str) -> list[str]:
    return [_iso(m) for m in RE_DATE.finditer(t) if not re.search(r"\biki\s*$", t[:m.start()])]


def _ends(t: str) -> list[str]:
    return [_iso(m) for m in RE_DATE.finditer(t) if re.search(r"\biki\s*$", t[:m.start()])]


def _iso(m: re.Match) -> str:
    return f"{m.group(1)}-{_LT_MONTHS.index(m.group(2)) + 1:02d}-{int(m.group(3)):02d}"


def _expand(spec: str, labels: list[str]) -> list[str]:
    """"25, 27 ir 30" / "47–50" / "35–51" -> the article labels (in the act's order for a range)."""
    out = []
    for part in re.split(r",\s*| ir | bei ", spec):
        if m := re.fullmatch(rf"({_N})\s*[–-]\s*({_N})", part.strip()):
            a, b = m.groups()
            if a in labels and b in labels:
                out += labels[labels.index(a): labels.index(b) + 1]
        elif part.strip() in labels:
            out.append(part.strip())
    return out


def _named(clause: str, act) -> tuple[set[str], set[str]]:
    """What a clause names: whole articles (directly, or as chapters and sections), and articles of which only a part."""
    labels = [a.label for a in act.main.articles]
    whole, parts = set(), set()
    t = clause
    for m in RE_SECTIONS.finditer(t):  # "III skyriaus 1, 2 ir 3 skirsniai"
        secs = set(re.split(r",\s*| ir ", m.group(2)))
        whole |= {a.label for a in act.main.articles
                  if any(h.kind == "skyrius" and h.num == m.group(1) for h in a.path)
                  and any(h.kind == "skirsnis" and h.num in secs for h in a.path)}
    t = RE_SECTIONS.sub(" ", t)
    for m in RE_CHAPTERS.finditer(t):  # "I ir II skyriai", "V skyrius"
        chs = set(re.split(r",\s*| ir | bei ", m.group(1)))
        whole |= {a.label for a in act.main.articles if any(h.kind == "skyrius" and h.num in chs for h in a.path)}
    for m in RE_ART_PART.finditer(t):  # "6 straipsnio 1 dalis", "5 straipsnio 1 dalies … punktus"
        if m.group(1) in labels:
            parts.add(m.group(1))
    t = RE_ART_PART.sub(" ", t)
    for m in RE_ARTS.finditer(t):
        whole |= set(_expand(m.group(1), labels))
    return whole, parts - whole


def application(act, day: str) -> tuple[dict[str, tuple[str, str, str]], list[str]]:
    """Per article: (state, date, note) where today's label must change, and act-level notices; {} when all apply."""
    final = next((a for a in reversed(act.main.articles) if re.search(r"taikym|įsigaliojim", a.title or "", re.I)), None)
    if final is None:
        return {}, []
    cite = f"{final.label} straipsnį"  # "žr. 71 straipsnį"
    text = " ".join(b.text for b in final.blocks)
    # clauses: sentences, and the lettered items of "Tačiau: a) …; b) …"
    clauses = [c.strip() for c in re.split(r"(?<=[.;])\s+(?=(?:[a-z]\)|[A-ZĄČĘĖĮŠŲŪŽ0-9]))", text) if c.strip()]
    general = None
    for c in clauses:
        if (m := re.search(r"(?:reglamentas|direktyva|sprendimas|Jis|Ji) taikom\w* nuo " + RE_DATE.pattern, c)) and not RE_ARTS.search(c) \
                and not RE_CHAPTERS.search(c) and "išskyrus" not in c:
            general = f"{m.group(1)}-{_LT_MONTHS.index(m.group(2)) + 1:02d}-{int(m.group(3)):02d}"
    out: dict[str, tuple[str, str, str]] = {}
    notices: list[str] = []
    earlier: set[str] = set()  # articles that apply earlier than a later general date
    rows = []  # (named whole, named parts, dates, conditional)
    for c in clauses:
        # "…, išskyrus X, kurie taikomi nuo D": X and D are the exception; "…, išskyrus X, taikomi nuo D": D is the clause's
        head, sep, rest = c.partition("išskyrus")
        excl, own_dates = "", True
        if sep:
            excl, comma, after = rest.partition(",")
            if re.match(r"\s*kuri", after):
                excl, own_dates = excl + after, False
            else:
                head += after
        # "taikomi iki 2027 m. gruodžio 31 d." (2017/1938 22): they apply now and stop then; only "nuo" dates start
        hd, xd = _starts(head), _starts(excl)
        if until := [x for x in _ends(head) + _ends(excl) if x >= day]:
            notices.append(f"Kai kurios nuostatos taikomos tik iki {min(until)} – žr. {cite}.")
        whole, parts = _named(head, act)
        ex_whole, ex_parts = _named(excl, act) if excl else (set(), set())
        if hd:
            rows.append((whole - ex_whole, parts, hd, bool(CONDITIONAL.search(head))))
        if xd and not own_dates:
            rows.append((ex_whole, ex_parts, xd, bool(CONDITIONAL.search(excl))))
        elif ex_parts and hd:  # a part left out of a later date applies already: the article applies in part
            rows.append((set(), ex_parts & whole, [], False))
        if (hd or xd) and not (whole or parts or ex_whole or ex_parts) and c != clauses[0] \
                and not re.search(r"(?:reglamentas|direktyva|sprendimas|Jis|Ji) taikom", c) and any(x > day for x in hd + xd):
            notices.append(f"Kai kurios nuostatos taikomos nuo {min(x for x in hd + xd if x > day)} – žr. {cite}.")
    applies_now = {a for w, p, ds, _ in rows if ds and min(ds) <= day for a in w}
    for whole, parts, dates, cond in rows:
        if not dates:
            for a in parts:
                if out.get(a, ("",))[0] == "pending":
                    out[a] = ("part", out[a][1], f"dalis nuostatų taikoma nuo {out[a][1]} – žr. {cite}")
            continue
        if general and general > day and min(dates) <= day:
            earlier |= whole
            continue
        later = [x for x in dates if x > day]
        if not later:
            continue
        when = min(later)  # "taikomi nuo: i) 2027 …, ii) 2028 …": the first
        for a in whole:
            if cond and a in applies_now:  # already applies, in other cases later
                out[a] = ("part", when, f"kai kuriais atvejais taikomas nuo {when} – žr. {cite}")
            else:
                out[a] = ("pending", when, ("kai kuriais atvejais – dar vėliau, " if len(later) > 1 else "") + f"žr. {cite}")
        for a in parts - whole:
            if a not in out:
                out[a] = ("part", when, f"dalis nuostatų taikoma nuo {when} – žr. {cite}")
    if general and general > day:
        for a in act.main.articles:
            if a.label not in earlier and a.label not in out:
                out[a.label] = ("pending", general, f"žr. {cite}")
        notices.insert(0, f"Šis teisės aktas taikomas nuo {general}" + (" (kai kurios nuostatos – anksčiau)" if earlier else "") + f": žr. {cite}.")
    return out, notices
