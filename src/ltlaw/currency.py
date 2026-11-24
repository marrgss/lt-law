"""Which articles of a stored consolidation apply on a given day (D-009, D-010).

The open data holds one consolidated version per act. It applies from S (its "Suvestinė
redakcija nuo S"), which may be before or after today D. Every article has change dates: the
entry dates of the amending acts that touch it, resolved down to the part/article level from each
amending law's own "Įstatymo įsigaliojimas" article (laws are often staged over years).

  S > D (future text):        the article differs from today's if it changes on a date in (D, S]  -> pending
  S <= D (past/current text): the article differs if it changes on a date in (S, D]                -> outdated
  any S:                      a law already in force that targets the article but is absent from
                              its notes was not consolidated into the text                         -> outdated

Anything we cannot establish is flagged, never shown as current. We never edit text.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from dataclasses import dataclass, field

from . import source
from .numbers import candidates, split_roman, from_roman, to_roman
from .parse import Block, Act, spaces
from .points import ref_key

MONTHS = {m: i + 1 for i, m in enumerate(["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", "liepos",
                                          "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"])}
RE_DATE = re.compile(r"(\d{4}) m\. (" + "|".join(MONTHS) + r") (\d{1,2}) d\.")
NUMLIST = r"(?:\d+(?:\.\d+)?(?:-\d+)?)(?:(?:\s*,\s*|\s+ir\s+|\s*–\s*)\d+(?:\.\d+)?(?:-\d+)?)*"  # "–": a range
RE_NUMLIST = re.compile(rf"({NUMLIST})\s+straipsni")
# an own-article list inside an entry sentence: "3 ir 6 straipsniai", "1 straipsnio 2 dalis", "11, 14 ir 17 straipsnius"
_N = r"\d+(?:\s*[–-]\s*\d+)?"  # a number or a range "16–20" / "1-3" (own articles have no superscripts)
RE_OWN = re.compile(rf"(?<![\w.])({_N}(?:(?:\s*,\s*|\s+ir\s+){_N})*)\s+straipsn(?:i)?(s|ai|o|ų|us|ams|uose|yje|į|iu)(?!\w)")
RE_VERB = re.compile(r"įsigalioja(?!\w)")
WHOLE_ENDINGS = {"s", "ai", "us", "į"}  # "3 straipsnis/straipsniai/straipsnius/straipsnį" = the whole article
RE_CONDITION = re.compile(r"\bjeigu\b|\bjei\b|\barba praėjus\b|\bdieną,? kai\b|\bpo to,? kai\b|,\s*kai\b|"
                          r"su sąlyga,? kad|ne anksčiau kaip")


def _clause(after: str) -> str:
    """The rest of one sentence after "įsigalioja": up to a full stop that isn't part of a date."""
    # a full stop then a capital ends the sentence, also after a date ("… 1 d. Vyriausybė iki …"), except
    # before a name ("… 1 d. Lietuvos Respublikos …") or after "m." / "Nr."
    m = re.search(r"\.\s+(?=[A-ZĄČĘĖĮŠŲŪŽ0-9])(?<!\bm\.\s)(?<!\bNr\.\s)(?!Lietuvos|Europos|Respublikos)", after)
    return after[:m.start() + 1] if m else after[:300]  # keep the full stop: "… 11 d." ends a date


def _own_nums(s: str) -> list[int]:
    """'2–9, 11–15 ir 29' -> [2..9, 11..15, 29]."""
    out = []
    for a, b in re.findall(r"(\d+)(?:\s*[–-]\s*(\d+))?", s):
        out += list(range(int(a), int(b) + 1)) if b and int(b) >= int(a) and int(b) - int(a) < 200 else [int(a)]
    return out
TAR_NOTE = re.compile(r"TAR pastaba.*?(\d+(?:-\d+)?) straipsni\w*.*?įsigalioja (\d{4}-\d{2}-\d{2})")


def _date(m: re.Match) -> str:
    return f"{m.group(1)}-{MONTHS[m.group(2)]:02d}-{int(m.group(3)):02d}"


def _sup_parens(s: str) -> str:
    """Seimo statutas amendments write superscripts in parentheses: "15(5) straipsnio" is 15⁵ ("15-5")."""
    return re.sub(r"(?<=\d)\((\d{1,2})\)", r"-\1", s or "")


def _range_nums(s: str) -> list[str]:
    """Heading numbers with en-dash ranges expanded: '191–193' -> 191, 192, 193 (each later read as 191 or 19¹ …;
    SPĮ XIV-2357 "Įstatymo 191–193 straipsnių pernumeravimas"). A hyphen is a superscript ("19-1"), not a range."""
    out = []
    for part in re.split(r"\s*,\s*|\s+ir\s+", s):
        m = re.fullmatch(r"(\d+)\s*–\s*(\d+)", part.strip())
        if m and 0 < int(m.group(2)) - int(m.group(1)) < 200:
            out += [str(x) for x in range(int(m.group(1)), int(m.group(2)) + 1)]
        else:
            out += _nums(part)
    return out


def _nums(s: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?(?:-\d+)?", s)


def _matches(token: str, label: str) -> bool:
    return any(c.label() == label for c in candidates(split_roman(token)))


# "… įstatymo Nr. X": the law X that a law amends, when X is itself an amending law. X's title ends in "pakeitimo", or
# in "papildymo N straipsniu / skyriumi …" or "pripažinimo netekusiu galios" (XV-648 amends "… Įstatymo papildymo 10¹
# straipsniu įstatymo Nr. XV-445", B45)
OF_LAW = r"(?:pakeitimo|galios|papildymo [^ ]+(?: ir [^ ]+)? (?:straipsniu|straipsniais|skyriumi|skyriais|skirsniu|skirsniais|dalimi|dalimis|punktu|punktais|priedu|priedais)) įstatymo nr\.\s*([ivxl]+-\d+)"

# --- amending laws -----------------------------------------------------------------------------
@dataclass
class AmendingLaw:
    nr: str
    default: str | None                                          # main entry-into-force date
    own_dates: dict[int, set[str]] = field(default_factory=dict)  # own article -> its (part) entry dates
    exceptions: set[int] = field(default_factory=set)            # own articles excluded from the default
    partial: set[int] = field(default_factory=set)               # own articles with only some parts excluded
    whole: set[int] = field(default_factory=set)                 # own articles dated as a whole
    conditional: set[int] = field(default_factory=set)           # own articles entering on a condition (no date)
    has_default: bool = False                                    # a "Šis įstatymas ... įsigalioja <date>" sentence
    entry_amended: list[str] = field(default_factory=list)       # later laws that changed this law's entry dates
    mentions: set[str] = field(default_factory=set)              # law numbers in our copy (its amenders are noted there)
    entry_articles: set[int] = field(default_factory=set)        # own articles on entry into force
    rewrite_own: int | None = None                               # own article setting out the whole act anew
    staged: dict[str, set[str]] = field(default_factory=dict)    # target article (in that new wording) -> its later dates
    staged_cond: dict[str, str | None] = field(default_factory=dict)  # target article -> earliest date of a wording entering on a condition
    targets: dict[int, list[str]] = field(default_factory=dict)  # own article -> target article tokens
    title_targets: list[str] = field(default_factory=list)       # from the law's title (fallback)
    chapters: dict[int, list[str]] = field(default_factory=dict)  # own article -> chapters it replaces ("VII skyriaus pakeitimas")
    all_dates: set[str] = field(default_factory=set)
    unresolved: bool = False                                     # an exception we could not place
    not_in_force: bool = False                                   # register: "neįsigaliojęs", no entry date
    additions: set[int] = field(default_factory=set)             # own articles that add ("… papildymas … straipsniu")
    of_law: str | None = None                                    # it amends this amending law's content articles (targets remapped)
    final_of: str | None = None                                  # it changes only this amending law's entry/final articles
    redates: bool = False                                        # a resolution amending another amending resolution (its dates or wordings)
    redate_points: set[str] = field(default_factory=set)         # … its staged points, whose dates it may have moved
    preamble_only: bool = False                                  # it changes only the resolution's preamble, not the approved rules
    item_lead: dict[int, list[str]] = field(default_factory=dict)  # own item -> its and its parents' openings, nearest first
    other_doc: bool = False                                      # (per document) it changes only other documents of the resolution
    item_points: dict[str, list[str]] = field(default_factory=dict)    # a resolution's item label -> points it changes
    staged_item_points: dict[str, list[str]] = field(default_factory=dict)  # a staged item ("7") -> its points

    def dates_for(self, label: str) -> set[str]:
        """Every date on which this law changes target article `label`."""
        owns = [o for o, toks in self.targets.items() if any(_matches(t, label) for t in toks)]
        out: set[str] = set()
        for o in owns:
            out |= self.own_dates.get(o, set())
            if o not in self.exceptions and o not in self.whole and self.default:
                out.add(self.default)
        if not owns and self.default:
            out.add(self.default)
        if not owns and len(self.all_dates) > 1:
            out |= self.all_dates  # the article isn't named in the law's headings (e.g. a new section): any date
        if self.unresolved:
            out |= self.all_dates  # can't tell which part is late: assume any of them
        return out

    def rewrite_date(self) -> str | None:
        """When the whole act's new wording set out by this law applies."""
        if self.rewrite_own is None:
            return None
        ds = self.own_dates.get(self.rewrite_own)
        return min(ds) if ds else self.default

    def conditional_for(self, label: str) -> bool:
        owns = [o for o, toks in self.targets.items() if any(_matches(t, label) for t in toks)]
        return any(o in self.conditional for o in owns) or (not owns and bool(self.conditional) and not self.targets)

    def targets_article(self, label: str) -> bool:
        """Also true for sibling articles (21¹ vs 21²): flattened superscripts in amending-law headings
        ("113" for 11³) are ambiguous, and an error there must not make an article look current."""
        toks = [t for ts in self.targets.values() for t in ts] or self.title_targets
        # a title that spells superscripts out ("3-5") names plain articles plainly: its "33" is article 33
        plain = {t for t in self.title_targets if "-" not in t} if any("-" in t for t in self.title_targets) else set()
        if "/" in self.nr or not SIBLING_MARGIN:  # every reading of a flattened number is checked, no sibling margin
            return any(t == label if t in plain else _matches(t, label) for t in toks)
        base = label.split("-")[0]
        sib = "-" in label  # only superscripted articles (11²) have ambiguous siblings (11¹, 11³)
        return any(t == label if t in plain else
                   _matches(t, label) or sib and "-" not in t and  # only flattened tokens ("113") are ambiguous
                   any(c.sup and c.label().split("-")[0] == base for c in candidates(split_roman(t)))
                   for t in toks)


def _title_decides(law: AmendingLaw) -> None:
    """Headings flatten superscripts ("33 straipsnio pakeitimas" for 3³, "3424" for 34²⁴): ambiguous, so every
    3ˣ article would look changed. The title spells them out ("3-3, 34-24"): a flattened token equal to
    exactly one of those, and not itself in the title, is that article (XIV-595, XIV-2784)."""
    title = set(law.title_targets)
    hy = [t for t in title if "-" in t]
    if not hy:
        return
    for own, toks in law.targets.items():
        out = []
        for t in toks:
            m = [x for x in hy if x.replace("-", "") == t]
            out.append(m[0] if "-" not in t and t not in title and len(m) == 1 else t)
        law.targets[own] = out


# Flag every superscripted sibling of a flattened number's base ("441" → 4ˣ and 44ˣ), not only its readings
# (441, 44¹, 4⁴¹). Measured 2026-10-20: see ACCURACY B31.
SIBLING_MARGIN = False


def _next_day(day: str | None) -> str | None:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat() if day else None


def _quoted(text: str):
    """position -> inside „…“ (Lithuanian quotes, nested by depth)."""
    spans = _quoted_spans(text)
    return lambda pos: any(a < pos < b for a, b in spans)


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    spans, depth, start = [], 0, 0
    for m in re.finditer(r"[„“]", text):
        if m.group() == "„":
            if depth == 0:
                start = m.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                spans.append((start, m.end()))
    return spans


def _in_part(path, part: str) -> bool:
    """Is an article under chapter "VII", or section "III/4" (4th section of chapter III; "*/4": any chapter)?"""
    if "/" not in part:
        return any(h.kind == "skyrius" and h.num == part for h in path)
    ch, sec = part.split("/")
    return any(h.kind == "skirsnis" and h.num == sec for h in path) and \
        (ch == "*" or any(h.kind == "skyrius" and h.num == ch for h in path))


def _ordinal(word: str) -> int | None:
    """'ketvirt' (from ketvirtojo) -> 4; 'dvidešimt ketvirt' -> 24; 'trisdešimt' (from trisdešimtojo) -> 30."""
    from .parse import ORD, TENS_WORDS
    parts = word.upper().split()
    tens = TENS_WORDS.get(parts[0], 0) if len(parts) == 2 else 0
    w = parts[-1]
    if len(parts) == 1 and w in TENS_WORDS:
        return TENS_WORDS[w]
    unit = next((v for k, v in ORD.items() if k[:-4] == w or k[:-4] == w + "I"), None)
    return tens + unit if unit is not None else None


RE_PTLIST = re.compile(r"(\d+(?:\.\d+)*(?:\s*(?:,|ir|bei|–|-)\s*\d+(?:\.\d+)*)*)\s+(?:punkt|papunk)\w*")


def _names_document(lead: str, title: str) -> bool:
    """Does an item's opening ("1. Pakeisti Vidutinio darbo užmokesčio skaičiavimo tvarkos aprašą, patvirtintą …") name
    this approved document? Its first four words of 4+ letters, each matching a word of the opening by its first 5 letters."""
    words = [w[:5] for w in re.findall(r"[a-ząčęėįšųūž]{4,}", (title or "").lower())][:4]
    have = {w[:5] for w in re.findall(r"[a-ząčęėįšųūž]{4,}", (lead or "").lower())}
    return bool(words) and all(w in have for w in words)


def for_document(law: AmendingLaw, documents: list[str], ours: str) -> AmendingLaw:
    """An amending resolution seen from one of several approved documents (D-027): items whose opening names only another
    document are dropped; items naming none, or ours, stay (fail safe)."""
    from dataclasses import replace
    from .points import doc_matches
    def _named(chain: list[str]) -> list[str]:  # the nearest opening that names a document decides
        for lead in chain:
            if hits := [t for t in documents if _names_document(lead, t)]:
                return hits
        return []
    named = {own: _named(chain) for own, chain in law.item_lead.items()}
    any_named = {t for ts in named.values() for t in ts}
    if any_named and not any(doc_matches(t, ours) for t in any_named):
        # it names only other documents (No. 1049/2024: the temporary-employment rules): nothing here
        return replace(law, targets={}, rewrite_own=None, staged={}, chapters={}, other_doc=True)
    def other(own: int) -> bool:
        hits = named.get(own, [])
        return bool(hits) and not any(doc_matches(t, ours) for t in hits)
    keep = {o: t for o, t in law.targets.items() if not other(o)}
    rewrite = None if law.rewrite_own is not None and other(law.rewrite_own) else law.rewrite_own
    return replace(law, targets=keep, rewrite_own=rewrite, other_doc=bool(law.targets) and not keep and rewrite is None)


def _item_points(own_of: dict[str, int], targets: dict[int, list[str]]) -> dict[str, list[str]]:
    """Top-level item label ("1") -> the points its sub-items change."""
    out: dict[str, list[str]] = {}
    for lab, own in own_of.items():
        out.setdefault(lab.split(".")[0], []).extend(targets.get(own, []))
    return out


def _item_list(s: str) -> list[str]:
    """A resolution's own items named in a sentence, ranges expanded: "1.4, 1.10–1.12" -> 1.4, 1.10, 1.11, 1.12."""
    out = []
    for a, b in re.findall(r"(\d+(?:\.\d+)*)(?:\s*[–-]\s*(\d+(?:\.\d+)*))?", s):
        pa, pb = a.rsplit(".", 1) if "." in a else ("", a), b.rsplit(".", 1) if b and "." in b else ("", b)
        if b and pa[0] == pb[0] and pa[1].isdigit() and pb[1].isdigit() and 0 < int(pb[1]) - int(pa[1]) < 100:
            out += [f"{pa[0] + '.' if pa[0] else ''}{k}" for k in range(int(pa[1]), int(pb[1]) + 1)]
        else:
            out += [a] + ([b] if b else [])
    return out


def _with_subitems(labels: list[str], own_of: dict[str, int]) -> list[int]:
    return [own for lab, own in own_of.items() if any(lab == x or lab.startswith(x + ".") for x in labels)]


_CHANGE = r"(?:Pakeisti|Pakeičiu)"  # a resolution's infinitive, a minister's order's first person
_REPEAL = r"(?:Pripažinti|Pripažįstu) netekusi(?:u|ais) galios"
_ADD = r"(?:Papildyti|Papildau)"


# "Buvusius III‒X skyrius laikau atitinkamai IV‒XI skyriais": the order's later items name chapters by their new numbers
RE_RENUMBERED = re.compile(r"\b[Bb]uvus\w+ ([IVXLC]+)(?:\s*[‒–-]\s*([IVXLC]+))? skyri\w+ (?:atitinkamai )?laik\w+ (?:atitinkamai )?([IVXLC]+)"
                           r"(?:\s*[‒–-]\s*([IVXLC]+))? skyri\w+")


def _renumbered(t: str) -> dict[str, str]:
    """A chapter's new number -> the number it has in the text before this order."""
    out = {}
    for m in RE_RENUMBERED.finditer(t):
        first, new = from_roman(m.group(1)), from_roman(m.group(3))
        last = from_roman(m.group(2)) if m.group(2) else first
        out |= {to_roman(new + k): to_roman(first + k) for k in range(last - first + 1)}
    return out


def parse_amending_resolution(key: str, text: str, meta_date: str | None, published: str | None = None) -> AmendingLaw:
    """A Government resolution amending a points act. Its numbered items are its own articles:
    "1.3. Pakeisti 16 punktą ir jį išdėstyti taip: „…“"; "1.26. Pakeisti 1 priedą: 1.26.1. Pakeisti 1 punktą …"
    (an annex's points, not the rules'); "2.1. šis nutarimas, išskyrus šio nutarimo 1.3 papunktį, įsigalioja D1;
    2.2. šio nutarimo 1.3 papunktis įsigalioja D2". "1. Pakeisti … nuostatus … ir juos išdėstyti nauja redakcija
    (pridedama)" sets the whole document out anew (No. 260/2026 for No. 405). A document attached after
    "PATVIRTINTA" is the new wording, not instructions. Fail safe: a dated part we can't place makes it unresolved."""
    law = AmendingLaw(key, meta_date)
    text = spaces(unicodedata.normalize("NFC", text or ""))
    # an order's spaced verbs: "P a k e i č i u", "N u s t a t a u" -> "Pakeičiu", "Nustatau"
    text = re.sub(r"\b([A-ZĄČĘĖĮŠŲŪŽ])((?: [a-ząčęėįšųūž]){3,})(?=[\s,:])", lambda m: m.group(1) + m.group(2).replace(" ", ""), text)
    if m := re.search(r"(?m)^\s*PATVIRTINTA\b", text, re.I):
        text = text[:m.start()]
    plain, last = [], 0
    for a, b in _quoted_spans(text):  # the new wording („…“) is not instructions
        plain += [text[last:a], " "]
        last = b
    body = re.sub(r"\s+", " ", "".join(plain) + text[last:])
    marks = list(re.finditer(r"(?:^|(?<=\s))(\d+(?:\.\d+)*)\.\s+(?=[A-ZĄČĘĖĮŠŲŪŽa-ząčęėįšųūž])", body))
    items = [(m.group(1), body[m.end(): marks[k + 1].start() if k + 1 < len(marks) else len(body)])
             for k, m in enumerate(marks)] or [("1", body)]
    own_of = {lab: k + 1 for k, (lab, _) in enumerate(items)}
    annex = {lab for lab, t in items if re.search(r"\bpried(ą|o|us|ų|ai)\b", t.split(":")[0])}
    entry_text = ""
    # point wordings staged for a later date (No. 210/2024): "7. Nustatyti, kad 2025 m. sausio 1 d. įsigalioja tokia šio
    # nutarimo 1 punktu patvirtintų Taisyklių: 7.1. 4 punkto redakcija: „…“; 7.2. 15 punkto redakcija …"
    staged_items = set()
    for lab, t in items:
        sm = re.search(r"(\d{4}) m\. (\w+) (\d{1,2}) d\. įsigalioja tokia[^:]{0,200}?(?:Taisyklių|Nuostatų|Aprašo|aprašo|taisyklių|nuostatų)\s*:", t)
        if not sm or sm.group(2) not in MONTHS:
            continue
        d = f"{sm.group(1)}-{MONTHS[sm.group(2)]:02d}-{int(sm.group(3)):02d}"
        staged_items.add(lab)
        own_text = t[sm.end():] + " " + " ".join(st for sub, st in items if sub.startswith(lab + "."))
        staged_items |= {sub for sub, _ in items if sub.startswith(lab + ".")}
        own_text = re.sub(rf"(?:^|\s){re.escape(lab)}\.\d+\.\s", " ; ", " " + own_text)  # drop the "7.2." item marks
        for pm in RE_PTLIST.finditer(own_text):  # "4 punkto redakcija", "15.2–15.4 papunkčių redakcija", "38.9 papunktis netenka galios"
            for x in re.findall(r"\d+(?:\.\d+)*", pm.group(1)):
                law.staged.setdefault(x.split(".")[0], set()).add(d)
                law.staged_item_points.setdefault(lab.split(".")[0], []).append(x.split(".")[0])
        law.all_dates.add(d)
    setting: set[str] = set()  # "Nustatyti, kad:" items
    renumbered: dict[str, str] = {}  # (D1-188/2026 for RŽNTKŽŠA: "III‒X laikau IV‒XI", then "Pakeičiu IV skyriaus antrąjį skirsnį": III/2)
    for lab, t in items:
        own = own_of[lab]
        if lab in staged_items:
            continue
        if any(lab == x or lab.startswith(x + ".") for x in annex):
            continue  # an annex's own points ("1.26.1. Pakeisti 1 punktą" under "1.26. Pakeisti 1 priedą")
        # under "2. Nustatyti, kad:" every sub-item is a rule of its own, not a change: "2.2. darbuotojų … nepanaudotų
        # atostogų trukmė nustatoma vadovaujantis … 6 ir 8 punktų nuostatomis" names points it doesn't change (No. 744/2025)
        if RE_VERB.search(t) or re.match(r"\s*(?:Nustatyti|Nustatau), kad", t) or any(lab.startswith(x + ".") for x in setting):
            entry_text += "; " + t  # one item, one sentence ("2.1. šis nutarimas … įsigalioja D1. 2.2. šio nutarimo 1.12 …")
            law.entry_articles.add(own)
            if re.match(r"\s*(?:Nustatyti|Nustatau), kad\s*:", t):
                setting.add(lab)
            continue
        # (an order: "Pakeičiu … aprašą ir jį išdėstau nauja redakcija"; on an order approving several documents only
        # the scope's `document:` tells which one it rewrote: D1-434/2024 rewrote ARPŽPNPA's second document, B69)
        if re.search(rf"\b{_CHANGE}\b[^;]{{0,300}}?\b(?:nuostatus|taisykles|aprašą|tvarką|reglamentą|metodiką|nutarimą|įsakymą)\b[^;]{{0,400}}?"
                     r"ir (?:juos|jas|jį|ją) (?:išdėstyti|išdėstau) nauja redakcija", t):  # one item: dates' full stops are inside
            # "Pakeisti nurodytą nutarimą ir jį išdėstyti nauja redakcija (… aprašas nauja redakcija nedėstomas)": the
            # resolution's own wording, the approved document is not set out anew (No. 813/2026 for No. 916)
            if not re.search(r"nauja redakcija nedėstom", t):
                law.rewrite_own = own  # the whole approved document set out anew
            continue
        # the instruction names the targets; numbers inside the quoted new wording are that wording's own references
        # ("Pakeisti 59 punktą ir jį išdėstyti taip: „59. … Nuostatų 54 ir 56 punktuose …“", No. 52/2026; B43)
        t = re.sub(r"„[^“]*“", lambda q: " " * len(q.group(0)), t)
        for m in RE_PTLIST.finditer(t):
            if re.search(r"šio (?:nutarimo|įsakymo)\s*$", t[max(0, m.start() - 16):m.start()]):
                continue  # "šio nutarimo 1.3 papunktis": the resolution's own item
            for a, b in re.findall(r"(\d+(?:\.\d+)*)(?:\s*[–-]\s*(\d+(?:\.\d+)*))?", m.group(1)):
                if b and "." not in a and "." not in b and 0 < int(b) - int(a) < 100:
                    law.targets.setdefault(own, []).extend(str(x) for x in range(int(a), int(b) + 1))
                else:
                    law.targets.setdefault(own, []).extend([a.split(".")[0]] + ([b.split(".")[0]] if b else []))
        # a chapter replaced or repealed as a whole ("Pakeisti III skyrių", "Pripažinti netekusiu galios II skyrių"), not a
        # chapter named as a place ("Papildyti III skyriaus trečiąjį skirsnį 711 punktu", No. 848/2025) or its title
        # (a minister's order says it in the first person: "Pakeičiu VI skyrių ir jį išdėstau taip", 1-144/2025 for
        # NGDSTVBA's 28–36; "Pripažįstu netekusiu galios", "Papildau")
        for mc in re.finditer(rf"\b(?:(?:{_CHANGE}|{_REPEAL})\s+([IVXLC]+\d*)\s+skyri(?:ų|us)"
                              rf"|{_ADD}\s+([IVXLC]+\d*)\s+skyriumi)\b", t):  # or a chapter added ("Papildyti VIII1 skyriumi")
            ch = split_roman(mc.group(1) or mc.group(2))
            law.chapters.setdefault(own, []).append(renumbered.get(ch, ch))
        # a section ("Pripažinti netekusiu galios IV skyriaus septintąjį skirsnį", No. 660/2022; "Papildyti … šeštuoju skirsniu")
        for ms in re.finditer(rf"\b(?:{_CHANGE}|{_REPEAL}|{_ADD})\s+([IVXLC]+)\s+"
                              r"skyri(?:aus|ų)\s+((?:(?:dvidešimt|trisdešimt|keturiasdešimt) )?\w+?)(?:ąjį|uoju)\s+skirsn(?:į|iu)\b", t):
            if re.match(r"\s+\d+(?:\.\d+)*\s+(?:punkt|papunk)", t[ms.end():]):
                continue  # "Papildyti III skyriaus trečiąjį skirsnį 71¹ punktu": the section is the place, not the change (B48)
            if (k := _ordinal(ms.group(2))) is not None:
                law.chapters.setdefault(own, []).append(f"{renumbered.get(ms.group(1), ms.group(1))}/{k}")
        renumbered |= _renumbered(t)
    for seg in re.split(r";\s*|(?<=\.)\s+(?=[A-ZĄČĘĖĮŠŲŪŽ])|\s(?=\d+\.\d+\.\s)", entry_text):
        if not RE_VERB.search(seg):
            continue
        head, after = RE_VERB.split(seg, 1)
        dm = RE_DATE.search(after[:60])
        d = _date(dm) if dm else (_next_day(published) if re.match(r"\s*kitą dieną po", after) else None)
        if d:
            law.all_dates.add(d)
        if re.search(r"\bšis (?:nutarimas|įsakymas)\b", head, re.I):
            law.default, law.has_default = d or law.default, True
            if RE_CONDITION.search(_clause(after)):
                law.conditional |= set(law.targets) or {0}
            if "išskyrus" in head:
                law.exceptions |= set(_with_subitems(_item_list(head.split("išskyrus", 1)[1]), own_of))
            continue
        # an item with its sub-items: "šio nutarimo 1.2 papunktis įsigalioja 2026 m. sausio 1 d." dates 1.2.1 and 1.2.2,
        # which change the points (No. 744/2025: PAILGA 6, 8)
        mine = _with_subitems(_item_list(head), own_of) if re.search(r"šio (?:nutarimo|įsakymo)", head) else []
        if mine and d:
            for o in mine:
                law.own_dates.setdefault(o, set()).add(d)
                law.whole.add(o)
        elif d:
            law.unresolved = True  # a dated part we can't tie to the resolution's own items
    if not law.has_default and not law.all_dates:
        law.default = meta_date or _next_day(published)  # the day after publication (Teisėkūros pagrindų įstatymas)
    law.item_points = _item_points(own_of, law.targets)
    leads = {lab: t.split(":")[0][:300] for lab, t in items}
    law.item_lead = {own: [leads.get(".".join(lab.split(".")[:k]), "") for k in range(lab.count(".") + 1, 0, -1)]
                     for lab, own in own_of.items()}  # "1.1.3" -> openings of 1.1.3, 1.1, 1
    # "Pakeisti … nutarimą Nr. 309 … ir preambulę išdėstyti taip: „…“" (No. 22/2024): the rules are untouched
    law.preamble_only = not (law.targets or law.rewrite_own or law.staged or law.chapters) and \
        bool(re.search(r"\bpreambul", body)) and not re.search(r"\bpunkt|\bpapunk|\bskyri|\bpried|nauja redakcija", body)
    undated = law.exceptions - set(law.own_dates)
    if undated and published:  # excepted, no date of their own: the day after publication (Teisėkūros pagrindų įstatymas)
        for o in undated:
            law.own_dates.setdefault(o, set()).add(_next_day(published))
            law.whole.add(o)
        law.all_dates.add(_next_day(published))
    elif undated:
        law.unresolved = True  # excepted items without a date of their own
    law.all_dates |= {x for x in (meta_date, law.default) if x}
    return law


def parse_amending(nr: str, text: str, meta_date: str | None, title: str = "", published: str | None = None) -> AmendingLaw:
    """`published`: TAR publication date. A law (or an excepted part without its own date) takes
    effect the day after official publication unless it says otherwise (Teisėkūros pagrindų įstatymas)."""
    text = unicodedata.normalize("NFC", text or "")  # "Šis" as S + combining caron (XIV-2072): see parse._lines
    law = AmendingLaw(nr, meta_date)
    title = _sup_parens(title)
    law.title_targets = [n for m in RE_NUMLIST.finditer(title) for n in _nums(m.group(1))]
    text = _sup_parens(spaces(text))
    law.mentions = set(re.findall(r"\b([IVXL]+-\d+)\b", text))
    # "3 straipsnis. 5 straipsnio pakeitimas"; sometimes without the full stop ("14 straipsnis 342 straipsnio
    # pakeitimas", XIV-1200) - accepted only with such a title, so "5 straipsnis netenka galios" isn't a heading
    heads = list(re.finditer(r"^[ \t]*(\d+)[ \t]+straipsnis(?:\.[ \t]*(.*)|[ \t]+([^\n]*?(?:pakeitimas|papildymas|"
                             r"pripažinimas netekusiu galios|įsigaliojimas[^\n]*)))$", text, re.M))
    # headings inside quoted new wording („… 2 straipsnis. …“) are the target act's, not this law's own
    quoted = _quoted(text)
    heads = [h for h in heads if not quoted(h.start())]
    entry_body = ""
    for i, h in enumerate(heads):
        own, ttl = int(h.group(1)), h.group(2) if h.group(2) is not None else h.group(3)
        body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        if re.match(r"(šio )?((konstitucinio įstatymo|įstatymo|kodekso|nutarimo|įsakymo|statuto) )?(įsigalioj|baigiamosios|pereinamosios)", ttl.strip().lower()):
            entry_body += "\n" + body
            law.entry_articles.add(own)
            continue
        if re.search(r"papildym", ttl, re.I):
            law.additions.add(own)
        if m := RE_NUMLIST.search(ttl):
            law.targets.setdefault(own, []).extend(_range_nums(m.group(1)))
            if "pernumeravimas" in ttl and (mb := re.search(r"laikyti\s+(?:atitinkamai\s+)?(\d[\d\s–,ir-]*?)\s+straipsni(?:u|ais)\b", body)):
                # renumbered: the new numbers are targets too, so one the text lacks gets its "not yet here" page
                # ("Buvusius Statuto 186¹⁰–186¹⁴ straipsnius laikyti atitinkamai 186¹¹–186¹⁵ straipsniais", XV-1217)
                law.targets[own].extend(_range_nums(mb.group(1)))
        elif re.search(r"papildym(?:as|o)\b.*\b(?:skyriumi|skyriais|skirsniu|skirsniais)\b", ttl, re.I):
            # a chapter or section added ("Įstatymo papildymo V¹ skyriumi", sporto XV-609): its articles are new; their
            # headings are inside the quoted wording ("„… 18¹ straipsnis. …"), the targets (B44)
            law.targets.setdefault(own, []).extend(re.findall(r"^[ \t]*„?[ \t]*(\d+(?:-\d+)?)[ \t]+straipsnis\.", body, re.M))
        elif ms := re.search(r"\b(?:([IVXLC]+(?:-\d+)?|[IVXLC]+\d*) skyriaus )?((?:(?:dvidešimt|trisdešimt|keturiasdešimt|penkiasdešimt) )?[^\W\d]+?)(?:asis|ojo)-?(\d{1,2})? skirsnio (?:pakeitimas|pripažinimas netekusiu galios)", ttl, re.I):
            # a whole section set out anew ("III skyriaus ketvirtojo skirsnio pakeitimas", AlkKĮ XIV-2621) or
            # repealed ("Kodekso penktojo skirsnio pripažinimas netekusiu galios", GTK XV-390); with a superscript,
            # "Ketvirtojo¹ skirsnio pakeitimas" is section 4-1 (investicijų XIV-3041, B46)
            if (k := _ordinal(ms.group(2))) is not None:
                law.chapters.setdefault(own, []).append(f"{ms.group(1) or '*'}/{k}" + (f"-{ms.group(3)}" if ms.group(3) else ""))
        elif mr := re.search(r"\b([IVXLC]+) skirsnio (?:pakeitimas|pripažinimas netekusiu galios)", ttl):
            # a section numbered in Roman figures, in an act with sections only ("V skirsnio pakeitimas", SKĮ XIV-1997)
            law.chapters.setdefault(own, []).append(f"*/{mr.group(1)}")
        elif mc := re.search(r"\b([IVXLC]+(?:-\d+)?|[IVXLC]+\d*) skyriaus (?:pakeitimas|pripažinimas netekusiu galios)", ttl):
            # the whole chapter is set out anew (not "… skyriaus pavadinimo pakeitimas", a title only)
            law.chapters.setdefault(own, []).append(mc.group(1))
        elif re.search(r"(įstatymo|kodekso|statuto)(?: nr\. \S+)? nauja redakcija$|^(įstatymo|kodekso|statuto) pakeitimas$", ttl.strip().lower()) or \
                (re.search(r"^(?:lietuvos respublikos )?[\w ]+ (?:kodekso|statuto) pakeitimas$", ttl.strip().lower())
                 and re.search(r"ir (?:jį|ją) išdėstyti taip", body[:300])):  # "… vidaus tarnybos statuto pakeitimas" (VTS XIV-2404)
            law.rewrite_own = own  # "4 straipsnis. … įstatymo Nr. X-493 nauja redakcija" (SPĮ XIV-2357)
    _title_decides(law)
    if meta_date:
        law.all_dates.add(meta_date)
    if not entry_body:
        return law
    # editorial notes inside a consolidated amending law ("Straipsnio dalies pakeitimai: Nr. XV-1028, ...")
    # mean a later law changed the entry dates themselves: remember it, and keep notes out of the sentences
    note = re.compile(r"^[^\n]{0,60}(?:pakeitimai|papildyta|pakeista)[^\n]{0,40}:\s*\n((?:\s*Nr\.[^\n]*\n?)+)", re.I | re.M)
    for m in note.finditer(entry_body):
        law.entry_amended += re.findall(r"Nr\.\s*([IVXL]+-\d+)", m.group(1))
    body = re.sub(r"\s+", " ", note.sub(" ", entry_body))
    # a statute or a constitutional law says "Šis statutas / konstitucinis įstatymas įsigalioja …": same rules
    body = re.sub(r"\b([Šš])i(s|o) (?:konstitucinis įstatymas|statutas)\b", lambda m: f"{m.group(1)}is įstatymas", body)
    body = re.sub(r"\b([Šš])io (?:konstitucinio įstatymo|statuto)\b", lambda m: f"{m.group(1)}io įstatymo", body)
    # only dates in entry sentences ("… įsigalioja D"); deadlines ("iki D priima įgyvendinamuosius teisės
    # aktus") and transitional dates ("iki D pradėtos bylos") are not dates on which the text changes
    for mv in re.finditer(r"įsigalioja(?!\w)|pradedam\w* taikyti|taikom\w* nuo|netenka galios", body):
        # the sentence's own dates: before the verb ("2. 2031 m. sausio 1 d. įsigalioja tokia … redakcija")
        # and in the clause after it; not a later sentence's deadline ("… D1. Vyriausybė iki D2 priima …")
        starts = [m.end() for m in re.finditer(r"(?:^|[.:;]\s+)(?=[A-ZĄČĘĖĮŠŲŪŽ]|\d+\.\s)", body[:mv.start()])]
        before = body[(starts[-1] if starts else 0):mv.start()]
        law.all_dates |= {_date(m) for m in RE_DATE.finditer(before + " " + _clause(body[mv.end():])[:200])}
    # a whole new wording staged by article (VAĮ XIII-2987): "Šio įstatymo 1 straipsnyje išdėstyto … įstatymo 9
    # straipsnis įsigalioja D", "Nuo D įsigalioja tokia … išdėstyto … įstatymo 33 straipsnio (2 dalies) redakcija"
    if law.rewrite_own is not None:
        # a part, point or opening words of the article count too ("4 straipsnio 8 punkto redakcija", "33 straipsnio
        # 1 dalies nuostatos iki dvitaškio redakcija", KVCSĮ XIV-1640)
        for m in re.finditer(r"išdėstyto[^.;]{0,160}? (?:įstatymo|kodekso|statuto) (\d+(?:-\d+)?) straipsn\w*(?: \d+(?:-\d+)? (?:dal|punkt|papunk)\w*)* įsigalioja (\d{4}) m\. (\w+) (\d{1,2}) d\.", body):
            if m.group(3) in MONTHS:
                law.staged.setdefault(m.group(1), set()).add(f"{m.group(2)}-{MONTHS[m.group(3)]:02d}-{int(m.group(4)):02d}")
        for m in re.finditer(r"(\d{4}) m\. (\w+) (\d{1,2}) d\. įsigalioja tokia[^.;]{0,200}?išdėstyto[^.;]{0,160}? (?:įstatymo|kodekso|statuto) (\d+(?:-\d+)?) straipsnio[^.;:„]{0,80}? redakcija", body):
            if m.group(2) in MONTHS:
                law.staged.setdefault(m.group(4), set()).add(f"{m.group(1)}-{MONTHS[m.group(2)]:02d}-{int(m.group(3)):02d}")
        # on a condition (TPVCAPDĮ XIV-2388): "D arba <condition> dieną, atsižvelgiant į tai, kuri data vėlesnė, įsigalioja
        # tokia … išdėstyto … įstatymo 9 straipsnio redakcija"; "Šio straipsnio 13 dalyje nurodytą dieną … išdėstyto …
        # įstatymo 17 straipsnis papildomas 7 dalimi" (that part sets the day by a condition)
        for m in re.finditer(r"(\d{4}) m\. (\w+) (\d{1,2}) d\. arba [^;]{0,400}?kuri data vėlesnė, įsigalioja tokia[^.;]{0,200}?"
                             r"išdėstyto[^.;]{0,160}? (?:įstatymo|kodekso|statuto) (\d+(?:-\d+)?) straipsn", body):
            if m.group(2) in MONTHS:
                law.staged_cond[m.group(4)] = f"{m.group(1)}-{MONTHS[m.group(2)]:02d}-{int(m.group(3)):02d}"
        for m in re.finditer(r"[Šš]io straipsnio \d+ dalyje nurodytą dieną[^.;]{0,200}?išdėstyto[^.;]{0,160}? (?:įstatymo|kodekso|statuto) (\d+(?:-\d+)?) straipsn", body):
            law.staged_cond.setdefault(m.group(1), None)
        law.all_dates |= {d for ds in law.staged.values() for d in ds}
    for sent in re.split(r"(?<=\.)\s+(?=\d+\.\s|Šis|Šio)", body):
        sent = re.sub(r"^\d+\.\s*", "", sent.strip())
        if law.rewrite_own is not None and "išdėstyto" in sent and not sent.startswith("Šis įstatymas"):
            continue  # a target article's staged date (law.staged above), not one of this law's own articles
        if not RE_VERB.search(sent):  # the verb, not the participle "įsigaliojantį"
            continue
        after = RE_VERB.split(sent, 1)[1]
        dm = RE_DATE.search(after[:60])  # "įsigalioja 2027 m. rugsėjo 1 d." (not a later date in the sentence)
        d = _date(dm) if dm else None
        # "įsigalioja 2025 m. liepos 1 d., jeigu ... arba praėjus 2 mėnesiams po ...": the date is not certain
        cond = bool(RE_CONDITION.search(_clause(after)))
        if d is None and re.match(r"\s*kitą dieną po (jo |šio įstatymo )?(oficialaus )?paskelbimo", after):
            d = _next_day(published)
        if sent.startswith("Šis įstatymas"):
            if d:
                law.default, law.has_default = d, True
            if (not d or cond) and "išskyrus" not in RE_VERB.split(sent, 1)[0]:
                law.conditional |= set(law.targets) or {0}  # no certain date for the law as a whole
            if "išskyrus" in sent:
                exc = RE_VERB.split(sent.split("išskyrus", 1)[1], 1)[0]
                for m in RE_OWN.finditer(exc):
                    if exc[max(0, m.start() - 16):m.start()].rstrip().endswith("šio straipsnio"):
                        continue
                    before = exc[max(0, m.start() - 24):m.start()].lower()
                    if re.search(r"(kodekso|įstatymo)\s*$", before) and not before.rstrip().endswith("šio įstatymo"):
                        continue  # "Kodekso 2-3 straipsnio": another act's numbers
                    (law.exceptions if m.group(2) in WHOLE_ENDINGS else law.partial).update(_own_nums(m.group(1)))
            continue
        if not sent.startswith("Šio įstatymo"):
            law.unresolved = True  # e.g. "Kodekso 10 straipsnio 3 dalis ... įsigalioja": not mapped to own articles
            continue
        head = RE_VERB.split(sent, 1)[0]
        found = False
        for m in RE_OWN.finditer(head):
            before = head[max(0, m.start() - 24):m.start()].lower()
            if re.search(r"(kodekso|įstatymo)\s*$", before) and not before.rstrip().endswith("šio įstatymo"):
                continue  # a number of another act, not of this law
            for n in _own_nums(m.group(1)):
                found = True
                if m.group(2) in WHOLE_ENDINGS:  # "straipsnyje išdėstyto ... dalis" is only part of it
                    law.whole.add(n)
                if d:
                    law.own_dates.setdefault(n, set()).add(d)
                if not d or cond:
                    law.conditional.add(n)  # "įsigalioja tą dieną, kai ..." / "..., jeigu ..."
        if not found:
            law.unresolved = True
    undated = (law.exceptions | law.partial) - set(law.own_dates) - law.conditional
    if undated and published:
        # excepted from the general date but given no other: the statutory default applies
        for n in undated:
            law.own_dates.setdefault(n, set()).add(_next_day(published))
            if n in law.exceptions:
                law.whole.add(n)
        law.all_dates.add(_next_day(published))
    elif undated:
        law.unresolved = True  # an excepted article/part never got its own date
    return law


FETCH_FAILED: list[str] = []   # amending-law texts that could not be fetched this run (nightly health)
REFRESHED: list[str] = []      # amending-law texts refetched because a later law changed them
UNKNOWN_REFS: set[str] = set()  # amending acts a text names that the metadata lacks: looked up next night (source.update_cited)


class Laws:
    """Lazy cache of amending laws, from data/amending/ snapshots (fetched on first use)."""

    # Amending laws adopted before this date use their metadata entry date without their text
    # (staged parts of such old laws falling after today are assumed rare; the validator checks it).
    TEXT_SINCE = "2020-01-01"

    def __init__(self, fetch: bool = True):
        self.meta = source.act_metadata()
        self.fetch = fetch
        self._cache: dict[str, AmendingLaw | None] = {}

    def _amended_since(self, nr: str, path) -> bool:
        """A law amending `nr`, published in the last 120 days, that our copy of `nr` doesn't mention yet
        (its consolidated text lists its amenders); checked at most once a day."""
        got = json.loads(path.read_text())
        fetched = (got.get("fetched") or "0000-00-00")[:10]
        if fetched >= dt.date.today().isoformat():
            return False
        text = got["row"].get("tekstas_lt") or ""
        lo = (dt.date.today() - dt.timedelta(days=120)).isoformat()
        return any((x.get("paskelbta_tar") or "") >= lo and (x.get("atv_dok_nr") or "?") not in text
                   for x in self.amended_by(nr))

    def amended_by(self, nr: str) -> list[dict]:
        """Laws amending the amending law `nr` ("... pakeitimo įstatymo Nr. XIV-3118 ... pakeitimo")."""
        if not hasattr(self, "_amended_by"):
            idx: dict[str, list[dict]] = {}
            for d in self.meta.values():
                if source.is_ruling(d):
                    continue  # "Dėl … pakeitimo įstatymo Nr. XIV-2404 … atitikties Konstitucijai" reviews it, doesn't amend it
                for m in re.findall(OF_LAW, (d.get("pavadinimas") or "").lower()):
                    idx.setdefault(m.upper(), []).append(d)
            self._amended_by = idx
        return self._amended_by.get(nr, [])

    def get(self, nr: str) -> AmendingLaw | None:
        if nr in self._cache:
            return self._cache[nr]
        if nr.startswith("KT"):  # a Constitutional Court ruling in the notes: dated by its publication (assess)
            return None
        d = self.meta.get(nr)
        law = None
        if d and (d.get("priimtas") or d.get("paskelbta_tar") or "") < self.TEXT_SINCE:
            law = AmendingLaw(nr, d.get("isigalioja"), all_dates={d["isigalioja"]} if d.get("isigalioja") else set())
            law.title_targets = [n for m in RE_NUMLIST.finditer(_sup_parens(d.get("pavadinimas"))) for n in _nums(m.group(1))]
        elif d:
            path = source.DATA / "amending" / d["dokumento_id"] / "fixed.json"
            try:
                if not path.exists() and self.fetch:
                    source.snapshot(d["dokumento_id"], root=source.DATA / "amending", day="fixed")
                elif path.exists() and self.fetch and self._amended_since(nr, path):
                    # a later law re-dated or changed this law: its consolidated text has the new dates
                    row = source.fetch_dokumentas(d["dokumento_id"])
                    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
                    if row.get("tekstas_lt"):  # never replace a text with an empty one
                        path.write_text(json.dumps({"fetched": now, "row": row}, ensure_ascii=False))
                        REFRESHED.append(nr)
                    else:
                        FETCH_FAILED.append(f"{nr}: refetch returned no text, kept the old copy")
            except Exception as e:  # keep going: without its text the law is handled from metadata, flagged
                FETCH_FAILED.append(f"{nr}: {e}")
            if path.exists():
                text = json.loads(path.read_text())["row"].get("tekstas_lt") or ""
                if d.get("rusis") in source.POINT_TYPES:  # a resolution or an order (D-033)
                    law = parse_amending_resolution(nr, text, d.get("isigalioja"), d.get("paskelbta_tar"))
                else:
                    law = parse_amending(nr, text, d.get("isigalioja"), d.get("pavadinimas") or "", d.get("paskelbta_tar"))
                if d.get("galioj_busena") == "neįsigaliojęs" and not d.get("isigalioja"):
                    law.not_in_force = True  # the register says it hasn't taken effect, and gives no date
                    law.conditional |= set(law.targets) or {0}
        if law is not None and d:
            if "/" in nr:
                self._resolution_of_resolution(law, d.get("pavadinimas") or "")
            else:
                self._remap_law_of_law(law, d.get("pavadinimas") or "")
        self._cache[nr] = law
        return law

    def _resolution_of_resolution(self, law: AmendingLaw, title: str) -> None:
        """A resolution amending an amending resolution ("Dėl … 2024 m. kovo 27 d. nutarimo Nr. 210 „Dėl … 1999 m. kovo 9 d.
        nutarimo Nr. 260 … pakeitimo“ pakeitimo", No. 1067/2024): its items are that resolution's, often its staged dates.
        The points that resolution changes or stages are what it can affect; assess() flags them while it is recent."""
        tl = " ".join(title.lower().split())
        cited = [(f"{y}-{MONTHS[m]:02d}-{int(dd):02d}", n) for y, m, dd, n in
                 re.findall(r"(\d{4}) m\. (\w+) (\d{1,2}) d\. (?:nutarimo|įsakymo) nr\. ([\w-]+(?:/[\w-]+)*)", tl) if m in MONTHS]
        if len(cited) < 2 or (cited[0][1], cited[0][0]) in source.POINT_ACTS:
            return
        x_key = f"{cited[0][1]}/{cited[0][0]}"
        x = self.get(x_key) if x_key != law.nr else None
        if x is None:
            return
        # its own targets are the amended resolution's item numbers ("Pakeisti 7 punktą" = item 7 of No. 210)
        items = sorted({t.split(".")[0] for ts in law.targets.values() for t in ts})
        # only its staged dates: an item named as a whole ("Pakeisti 1 punktą", holding all 58 changes of No. 393) says
        # too little about which points; the consolidation's notes cover a content change once it is in
        redate = sorted({p for it in items for p in x.staged_item_points.get(it, [])})
        pts = redate
        law.targets, law.title_targets, law.of_law, law.redates = {0: pts}, pts, x_key, True
        law.redate_points = set(redate)

    def _older_text(self, nr: str) -> AmendingLaw | None:
        """An amending law older than TEXT_SINCE parsed from its cached text (never fetched here), for the laws that
        amend it: which of its articles are entry articles, which change the act."""
        d = self.meta.get(nr) or {}
        path = source.DATA / "amending" / (d.get("dokumento_id") or "?") / "fixed.json"
        if not path.exists() or d.get("rusis") in source.POINT_TYPES:
            return None
        text = json.loads(path.read_text())["row"].get("tekstas_lt") or ""
        return parse_amending(nr, text, d.get("isigalioja"), d.get("pavadinimas") or "", d.get("paskelbta_tar")) if text else None

    def _remap_law_of_law(self, law: AmendingLaw, title: str) -> None:
        """A law amending an amending law's content ("… kodekso 9 ir 23-1 straipsnių pakeitimo įstatymo Nr. XIV-1050 1 ir
        2 straipsnių pakeitimo įstatymas", GTK XIV-1323): its headings name that law's own articles (1, 2), which change
        the act's articles 9 and 23¹. Its targets become those (from the amended law's text, else its title); a law
        changing only the amended law's entry article (re-dating) is left as it is (_recent_redating)."""
        tl = " ".join(_sup_parens(title).lower().split())
        m = re.search(OF_LAW + r"\s+(" + NUMLIST + r")\s+straipsni\w*\s+(?:ir [^ ]+ )?pakeitimo įstatymas", tl)
        if not m:
            return
        x_nr = m.group(1).upper()
        x = self.get(x_nr) if x_nr != law.nr else None
        own = {int(t) for t in _own_nums(m.group(2))}
        if x is not None and not x.targets:
            x = self._older_text(x_nr) or x  # a law older than TEXT_SINCE is kept from metadata: its text, if cached
        final = x is not None and (x.entry_articles and own <= x.entry_articles or not x.targets and x.title_targets
                                   and min(own, default=0) > len(x.title_targets))
        if final:
            # it changes the amended law's own final provisions (re-dating it, or a transitional rule: XV-528 changes
            # XIII-2398's 13th article): its "13 straipsnio pakeitimas" is that law's article 13, not the act's, and
            # no text of the act will ever list it. Re-dating is handled from the amended law (_recent_redating).
            law.targets, law.title_targets, law.final_of = {}, [], x_nr
            return
        act_level = [n for mm in RE_NUMLIST.finditer(tl[:m.start()]) for n in _nums(mm.group(1))]
        mapped: dict[int, list[str]] = {}
        entry = x.entry_articles if x is not None else set()
        for o, toks in (law.targets.items() or {0: [str(t) for t in own]}.items()):
            out = []
            for t in toks:
                out += (x.targets.get(int(t)) if x is not None and t.isdigit() else None) or []
            # its change of the amended law's entry article re-dates that law (_recent_redating), it names no article
            # of the act: not "every article in the title" (XV-579 on XIV-2961's 10th, ATĮ)
            mapped[o] = out or ([] if toks and all(t.isdigit() and int(t) in entry for t in toks) else act_level)
        law.targets, law.title_targets, law.of_law = mapped, act_level, x_nr


    def ruling(self, nr: str) -> tuple[str | None, str]:
        """(effective date, operative part) of a Constitutional Court ruling; its text is fetched once."""
        d = self.meta.get(nr) or {}
        path = source.DATA / "amending" / (d.get("dokumento_id") or "?") / "fixed.json"
        try:
            if not path.exists() and self.fetch and d.get("dokumento_id"):
                source.snapshot(d["dokumento_id"], root=source.DATA / "amending", day="fixed")
        except Exception as e:
            FETCH_FAILED.append(f"{nr}: {e}")
        text = json.loads(path.read_text())["row"].get("tekstas_lt") or "" if path.exists() else ""
        text = unicodedata.normalize("NFC", text)
        return ruling_effective(text, d.get("paskelbta_tar")), ruling_operative(text)


# --- statuses ----------------------------------------------------------------------------------
@dataclass
class Status:
    state: str                     # current | pending | outdated | unknown | repealed
    reasons: list[str] = field(default_factory=list)
    changes_on: str | None = None   # pending: first date this article changes after `day`
    applies_from: str | None = None  # pending: date from which the stored (future) text applies in full
    part_pending: str | None = None  # current: a part of it (TAR pastaba) applies only from this date
    note: str | None = None          # current: what a TAR note tells the reader (e.g. which wording applies)
    future_change: tuple | None = None  # current: (date, law) of an adopted change not yet in this text


@dataclass
class ActStatus:
    day: str
    version_state: str             # past | current | future
    missing: list[dict] = field(default_factory=list)       # laws that name this act, in force, not in the text
    act_level_flags: list[str] = field(default_factory=list)
    articles: dict[str, Status] = field(default_factory=dict)
    expires: str | None = None     # the whole act is repealed from this date (header "... netenka galios D")
    unexplained: list[str] = field(default_factory=list)  # version boundaries no detected law explains (health metric)
    notices: list[str] = field(default_factory=list)      # act-level facts shown to readers (e.g. articles not in the text yet)
    added: list[dict] = field(default_factory=list)       # articles added by laws in force, missing from the text


def _recent_redating(law: AmendingLaw, laws: Laws, since: str) -> list[str]:
    """Later laws, adopted since `since`, that changed this law's own entry dates (its consolidated text
    notes them: official consolidations of the target act can disagree for a while, B5/B8), or that amend
    it and our copy doesn't include yet (its dates as we read them may be out of date)."""
    known = {n for n in law.entry_amended if (laws.meta.get(n, {}).get("priimtas") or "0000") >= since}
    pending = {d["atv_dok_nr"] for d in laws.amended_by(law.nr)
               if (d.get("priimtas") or "0000") >= since and d.get("atv_dok_nr") not in law.mentions
               and _may_redate(law, d.get("pavadinimas") or "")}
    return sorted(known | pending)


def _unsettled(nrs: list[str], law: AmendingLaw, laws: Laws, S: str) -> list[str]:
    """The re-dating laws that still leave doubt: unless our copy of the re-dated law already has its new dates (its
    consolidated text notes the re-dating law) and the re-dating law was adopted 90+ days before the text's start S,
    so the text's consolidators knew it too (ATĮ from 2026-10-01; XV-579 of 2025-11-13 re-dated XIV-2961). A copy
    without the new dates keeps the doubt (PPATĮ: XV-648 moved XV-445's dates; B63)."""
    lim = (dt.date.fromisoformat(S) - dt.timedelta(days=90)).isoformat() if S > "0001" else "0000"
    return [n for n in nrs if n not in law.entry_amended or (laws.meta.get(n, {}).get("priimtas") or "9999") >= lim]


def _may_redate(law: AmendingLaw, title: str) -> bool:
    """The amender's title names this law's entry article ("… įstatymo Nr. XIV-2317 43 straipsnio pakeitimo"),
    or names no article (a whole new wording), or we don't know which article is the entry one.
    "… Nr. XV-549 2 straipsnio pakeitimo" changes a wording only (XV-1027): its dates stand."""
    m = re.search(rf"nr\.\s*{re.escape(law.nr.lower())}\s+([\d,\s\-–ir]+?)\s*straipsni", title.lower())
    return not m or not law.entry_articles or bool(set(_own_nums(m.group(1))) & law.entry_articles)


def _candidate_laws(act: Act, scope_act: dict, laws: Laws, day: str, seen: str | None = None) -> list:
    """Laws naming this act (by title) that can matter for `day`:
    - published in the year before min(S, day) or later (the consolidation may lag behind them), or
    - with any change date (from their text, part-level) between S and day."""
    gen, num = scope_act["genitive"], scope_act.get("number") or ""
    S = act.version_from or "0000-00-00"
    lo, hi = min(S, day), max(S, day)
    # the look-back is anchored on when this version was first seen, not on `day`: otherwise a law we
    # flag today drops out a year later and its articles silently turn "current" again
    anchor = min(S, seen) if seen else lo
    lag_from = (dt.date.fromisoformat(anchor) - dt.timedelta(days=365)).isoformat() if act.version_from else "0000-00-00"
    old_from = (dt.date.fromisoformat(anchor) - dt.timedelta(days=6 * 365)).isoformat() if act.version_from else "0000-00-00"
    # a law adopted before this act cannot amend it: it amended an earlier act of the same name (tautinių mažumų
    # I-1007 of 1991 and the new law XIV-3079 of 2024, B52)
    born = (laws.meta.get(num) or {}).get("priimtas") or "" if not scope_act.get("adopted") else ""
    out = []
    for nr, d in laws.meta.items():
        if source.is_ruling(d):
            continue  # rulings: _rulings
        if born and (d.get("priimtas") or "9999") < born:
            continue
        tl = (d.get("pavadinimas") or "").lower()
        # "Lietuvos Respublikos energetikos įstatymo", not "... elektros energetikos įstatymo"
        # by number only if the number isn't that of the approval law ("… kodekso patvirtinimo, įsigaliojimo
        # ir įgyvendinimo įstatymo Nr. XII-2603 6 straipsnio pakeitimo" amends the approval law, not DK 6)
        by_num = bool(num) and f"nr. {num.lower()} " in tl + " " and not re.search(rf"patvirtinimo[^.]{{0,80}}nr\. {re.escape(num.lower())}\b", tl)
        if scope_act.get("adopted"):  # a resolution: numbers repeat every year, so the date must match too
            by_num = source.names_points_act(tl, num, scope_act["adopted"], scope_act.get("kind"))
        # by name outside quotes: „…“ is another act's title ("nutarimo Nr. 496 „Dėl … darbo kodekso įgyvendinimo“
        # pakeitimo" amends that resolution, not DK; B42)
        tn = re.sub(r"„[^“”]*[“”]", " ", tl)
        names = ((f"respublikos {gen}" in tn or tn.startswith(gen)) and ("patvirtinto" in tn or f"{gen} patvirtinimo" not in tn)) or by_num
        if not names or not re.search(r"pakeitimo|papildymo|pripažinimo", tl):
            continue
        pub = d.get("paskelbta_tar") or ""
        ent = d.get("isigalioja") or ""
        if pub < old_from and not ent > lo:
            continue
        law = laws.get(nr)
        if law is None:  # text unavailable: fall back to metadata date + article numbers in the title
            law = AmendingLaw(nr, d.get("isigalioja"), all_dates={ent} if ent else set(),
                              title_targets=[n for m in RE_NUMLIST.finditer(_sup_parens(d.get("pavadinimas")))
                                             for n in _nums(m.group(1))])
        if pub >= lag_from or any(lo < x <= hi for x in law.all_dates) or law.conditional or \
                _recent_redating(law, laws, lag_from):
            out.append((law, d))
    return out


def _rulings(act: Act, scope_act: dict, laws: Laws, day: str, seen: str | None = None) -> list[tuple[str, str, list[str] | None]]:
    """Constitutional Court rulings naming this act that our text doesn't note yet: (number, effective date,
    article tokens found in conflict with the Constitution now; [] = act named, no article read). Same look-back
    as for laws (a year before the version was first seen); rulings published after `day` are not known yet."""
    gen = scope_act.get("genitive") or ""
    if not gen or not act.version_from:
        return []
    anchor = min(act.version_from, seen) if seen else min(act.version_from, day)
    lag_from = (dt.date.fromisoformat(anchor) - dt.timedelta(days=365)).isoformat()
    noted = {r.nr for a in act.main.articles for v in [a, *a.variants] for r in v.all_refs()}
    out = []
    for nr, d in laws.meta.items():
        if not source.is_ruling(d) or nr in noted:
            continue
        pub = d.get("paskelbta_tar") or ""
        if not (lag_from <= pub <= day) or f"respublikos {gen.lower()}" not in (d.get("pavadinimas") or "").lower():
            continue
        eff, operative = laws.ruling(nr)
        eff = eff or pub
        if not (eff > act.version_from or (seen and seen < eff) or (act.prepared and act.prepared[:10] < eff)):
            continue  # our text was prepared after the ruling took effect and doesn't note it: nothing to change
        if not operative:  # text not available: we can't tell what it found; say so at act level
            out.append((nr, eff, []))
            continue
        toks = ruling_targets(operative, gen)
        if toks is not None:
            out.append((nr, eff, toks))
    return out


RE_SELF = re.compile(r"^Šio (?:įstatymo|kodekso|statuto) (.+?) (?:nauja redakcija|pakeitimas)$", re.I)


def _self_amendments(act: Act) -> list[tuple[str, list[str], str]]:
    """The act's own articles that set out other articles of it anew from a later date (SŽNSĮ 142 "Šio įstatymo II
    skyriaus antrojo skirsnio nauja redakcija", 143 "Šio įstatymo 10 straipsnio nauja redakcija", dated in its entry
    article: "… 142 straipsnis įsigalioja 2023 m. sausio 1 d."): (own article, target labels, date)."""
    arts = act.main.articles
    texts = " ".join(" ".join(b.text for b in a.blocks) for a in arts if a.title and re.search(r"įsigaliojim", a.title, re.I))
    if not texts:
        return []
    out = []
    for a in arts:
        m = RE_SELF.match((a.title or "").strip())
        if not m or not a.label.isdigit():
            continue
        spec = _sup_parens(m.group(1)).lower()
        if ms := re.fullmatch(rf"({NUMLIST}) straipsni\w*(?: [\d\s,ir–-]+ dal\w*)?", spec):
            targets = [t for t in _range_nums(ms.group(1)) if any(_matches(t, x.label) for x in arts)]
            targets = [x.label for x in arts if any(_matches(t, x.label) for t in targets)]
        elif ms := re.fullmatch(r"(?:([ivxlc]+) skyriaus )?((?:(?:dvidešimt|trisdešimt) )?\w+?)(?:ojo|asis) skirsni\w*", spec):
            k = _ordinal(ms.group(2))
            part = f"{(ms.group(1) or '*').upper()}/{k}"
            targets = [x.label for x in arts if k is not None and _in_part(x.path, part)]
        elif ms := re.fullmatch(r"([ivxlc]+) skyri\w*", spec):
            targets = [x.label for x in arts if _in_part(x.path, ms.group(1).upper())]
        else:
            continue
        # its date: a sentence of the entry article naming it ("… ir 142 straipsnis įsigalioja 2023 m. sausio 1 d.")
        for sent in re.split(r"(?<=\.)\s+(?=\d+\.\s|Šis|Šio)", texts):
            head = RE_VERB.split(sent, 1)
            if len(head) == 2 and a.label in [str(n) for mm in RE_OWN.finditer(head[0]) for n in _own_nums(mm.group(1))] \
                    and not re.search(r"išskyrus", head[0]) and (dm := RE_DATE.search(head[1][:60])):
                out.append((a.label, [t for t in targets if t != a.label], _date(dm)))
                break
    return out


RE_EXPIRY = re.compile(r"Pastaba\.\s*(.{0,60}?)\s+galioja iki (\d{4}) m\. (" + "|".join(MONTHS) + r") (\d{1,2}) d\.")


def _expired_articles(act: Act, day: str) -> dict[str, str]:
    """Editorial notes like 'Pastaba. Devintasis skirsnis galioja iki 2014 m. gruodžio 31 d.' (or
    '... straipsnis galioja iki ...'): articles of an expired section/article are not in force."""
    out: dict[str, str] = {}
    for a in act.main.articles:
        for b in a.blocks:
            m = RE_EXPIRY.search(b.text)
            if not m:
                continue
            until = f"{m.group(2)}-{MONTHS[m.group(3)]:02d}-{int(m.group(4)):02d}"
            if until >= day:
                continue
            subj = m.group(1).lower()
            why = f"pagal pastabą galiojo iki {until}"
            if "skirsnis" in subj or "skyrius" in subj:
                kind = "skirsnis" if "skirsnis" in subj else "skyrius"
                word = subj.split()[0].upper()
                from .parse import ORD
                num = str(ORD.get(word, "")) if word in ORD else None
                for x in act.main.articles:
                    if any(h.kind == kind and (num is None or h.num.split("-")[0] == num) for h in x.path[-1:] + x.path):
                        if num is not None or x is a:
                            out[x.label] = why
                out[a.label] = why
            else:
                out[a.label] = why
    return out


def _unexplained_boundaries(act: Act, cands: list, laws: Laws, day: str) -> list[str]:
    """Invariant: the stored version's start S, and the day after its end T (when that is not after
    `day`), should each be a date of some law we detected. If not, a change happened that we can't see.
    Reported as a health metric (status.json), not as labels: on 2026-10-18 only CPK trips it, where
    e-tar's own versions follow the disputed XIV-2317/XV-1028 dates and the affected articles are
    already 'unknown'."""
    dates = {w for w, _ in act.rewrites}
    for law, d in cands:
        dates |= set(law.all_dates) | ({d["isigalioja"]} if d.get("isigalioja") else set())
    for a in act.main.articles:
        for r in a.all_refs():
            law = laws.get(r.nr)
            dates |= law.all_dates if law else ({r.published} if r.published else set())
    out = []
    if act.version_from and act.version_from not in dates:
        out.append(f"version start {act.version_from}")
    if act.version_to and act.version_to < day:
        nxt = (dt.date.fromisoformat(act.version_to) + dt.timedelta(days=1)).isoformat()
        if nxt not in dates and nxt != act.expires:
            out.append(f"next version from {nxt}")
    return out


# "Netenka galios nuo 2010 m. liepos 1 d." (present tense, VSPĮ 22, 32, 44): the same, once the date has passed
RE_ART_REPEALED = re.compile(r"^Nete(?:ko|nka) galios(?: nuo)?\s*(?:(\d{4}-\d{2}-\d{2})|(\d{4}) m\. (" + "|".join(MONTHS)
                             + r") (\d{1,2}) d\.)?\.?$")


def _article_repealed(art) -> tuple[bool, str | None]:
    """An article left in the text only as 'N straipsnis. Neteko galios nuo 2021-02-01' (no body)."""
    title = (art.title or "").strip()
    if any(b.kind in ("part", "para", "point", "sub") and b.text.strip() for b in art.blocks):
        return False, None
    m = RE_ART_REPEALED.match(title)
    if not m:
        # "Neteko galios nuo Šengeno konvencijos įsigaliojimo Lietuvos Respublikai dienos." (UTPĮ 7): repealed
        # from an event; the past tense says it happened, the date isn't given
        # an older form keeps the heading with "(neteko galios)" and no text (KASOKTĮ 15, "Gynybos štabas (neteko galios)")
        return (True, None) if re.match(r"^Neteko galios nuo \D", title) or re.search(r"\(neteko galios\)$", title, re.I) \
            else (False, None)
    if m.group(1):
        return True, m.group(1)
    if m.group(2):
        return True, f"{m.group(2)}-{MONTHS[m.group(3)]:02d}-{int(m.group(4)):02d}"
    return (not title.startswith("Netenka")), None  # "Netenka galios" without a date: not known to have happened


def decode_new_label(token: str, labels: list[str]) -> str | None:
    """A target token for an article the text lacks, as a label: '52-1' stays; a flattened '303' is
    30³ when 303 is beyond the act's numbering and 30 exists (the same reading as the parser's)."""
    if "-" in token or "." in token:
        return token if re.fullmatch(r"[\d.]+(-\d+)?", token) else None
    if not token.isdigit():
        return None
    bases = {int(l.split("-")[0]) for l in labels if l.split("-")[0].isdigit()}
    top = max(bases, default=0)
    splits = [f"{token[:-k]}-{token[-k:]}" for k in (1, 2)
              if token[:-k] and int(token[:-k]) in bases and token[-k] != "0"]
    if int(token) <= top + 1:
        return None if splits else token  # "215" with 21 in the act could be 21⁵: don't guess
    for k in (1, 2):  # 303 -> 30-3, 1112 -> 111-2
        head, tail = token[:-k], token[-k:]
        if head and int(head) in bases and tail[0] != "0":
            return f"{head}-{tail}"
    return None


def _new_labels(tokens: list[str], labels: list[str]) -> dict[str, str | None]:
    """decode_new_label for a law's list of new articles: plain numbers running on from the act's last one ("21",
    "22" after 20, VSAĮ XV-734) are those numbers, not 2¹ and 2² (B49); otherwise one by one."""
    bases = {int(l.split("-")[0]) for l in labels if l.split("-")[0].isdigit()}
    top = max(bases, default=0)
    if tokens and all(t.isdigit() for t in tokens) and sorted(map(int, tokens)) == list(range(top + 1, top + 1 + len(tokens))):
        return {t: t for t in tokens}
    return {t: decode_new_label(t, labels) for t in tokens}


_D_ISO = r"(\d{4}-\d{2}-\d{2})"
_D_LT = r"(\d{4}) m\. (" + "|".join(MONTHS) + r") (\d{1,2}) d\."


def _first_date(t: str) -> str | None:
    m = re.search(_D_ISO + "|" + _D_LT, t)
    if not m:
        return None
    return m.group(1) or f"{m.group(2)}-{MONTHS[m.group(3)]:02d}-{int(m.group(4)):02d}"


def tar_note_effects(art, day: str, with_info: bool = False):
    """'TAR pastaba' notes the Chancellery prints inside an article (pending dates, reasons to flag).
    Transitional and applicability notes ('taikomos apskaičiuojant 2019 metų … pajamas', 'bylos
    baigiamos pagal …') don't change whether the text is in force and are left alone."""
    pending, unknown, info = [], [], []
    for b in art.blocks:
        t = b.text
        if "TAR pastaba" not in t:
            continue
        if m := re.search(r"redakcija nuo\s*(.{0,30})", t):
            d = _first_date(m.group(1))
            if d and d > day:
                pending.append(d)
            elif d:
                info.append(f"tekste pateiktos dvi dalies redakcijos: nuo {d} taikoma ta, kuri pažymėta TAR pastaba „redakcija nuo {d}“")
            continue
        if re.search(r"Konstitucinio Teismo", t) and re.search(r"prieštara|pripažin", t):
            info.append("Konstitucinis Teismas yra pripažinęs dalį šio straipsnio nuostatų prieštaraujančiomis Konstitucijai – žr. pastabą tekste")
        m = re.search(r"(įsigalioja|pradedam\w* taikyti|taikom\w* nuo)(.{0,200})", t, re.I)
        if not m:
            continue
        clause = re.split(r"\.\s+(?=[A-ZĄČĘĖĮŠŲŪŽ])", m.group(2), maxsplit=1)[0]
        if m.group(1).lower().startswith("taikom") and re.search(r"sudar|pradėt|paduot|sandor|byl|proces|laikotarp|pajam|išleist|įsigyt", clause):
            info.append("pagal TAR pastabą kai kurios nuostatos taikomos tik tam tikriems sandoriams, byloms ar laikotarpiams – žr. pastabą tekste")
            continue  # applicability to transactions, cases or periods: transitional, the text is in force
        d = _first_date(m.group(2)[:45]) or (_first_date(pm.group(1)) if (pm := re.search(r"įsigaliojimo dien\w*\s*\(([^)]{8,30})\)", m.group(2))) else None)
        if d and RE_CONDITION.search(m.group(2)):
            unknown.append("pagal TAR pastabą įsigaliojimas priklauso nuo sąlygos: " + t[12:150].strip(" .:") + "…")
        elif d:
            if d > day:
                pending.append(d)
        elif re.search(r"praėjus|\bkai\b|dienos|po to", m.group(2)):
            unknown.append("pagal TAR pastabą dalis nuostatų įsigalioja tik įvykus sąlygai: " + t[12:150].strip(" .:") + "…")
    return (pending, unknown, info) if with_info else (pending, unknown)


def article_expiry(art, label: str) -> str | None:
    """'125⁴ straipsnis netenka galios 2024-05-01.' (in the text or in a TAR note): a temporary article."""
    own = label.replace("-", "")
    for b in art.blocks:
        m = re.match(rf"^(?:TAR pastaba[.:]?\s*)?(?:{re.escape(own)}|{re.escape(label)}|Šis)\s+straipsnis\s+netenka galios\s+(.{{0,30}})", b.text)
        if m and (d := _first_date(m.group(1))):
            return d
    return None


def _future_change(label: str, refs, cands, day: str, labels: list[str] = (), version_from: str = "0000") -> tuple | None:
    """The first date after `day` on which an adopted law changes this article. Certain only when the
    law names it unambiguously: a flattened "42" that could also be 4² is only a possible change."""
    best = None
    in_text = {r.nr for r in refs}
    for law, _ in cands:
        toks = [t for ts in law.targets.values() for t in ts] or list(law.title_targets)
        explicit = any(_matches(t, label) and ("-" in t or "." in t or
                                               sum(1 for l in labels if _matches(t, l)) == 1) for t in toks)
        if any("-" in t for t in law.title_targets):  # the title spells superscripts out ("4-1"): it decides
            explicit = any(_matches(t, label) for t in law.title_targets)
            if not explicit:
                continue  # the title names 4¹, 4², not 41: this article isn't changed
        if not explicit and not law.targets_article(label):  # siblings (12³ vs "123"): only possibly
            continue
        if law.nr in in_text and law.unresolved:
            explicit = False  # its dates can't be tied to this article: at most a possible change
        for x in law.dates_for(label):
            if law.nr in in_text and x <= version_from:
                continue  # this change is already in the stored text (a later staged part is not)
            if x > day and (best is None or x < best[0] or x == best[0] and explicit and not best[2]):
                best = (x, law.nr, explicit)
    return best


KIND = {"Įstatymas": "įstatymas", "Konstitucinis įstatymas": "konstitucinis įstatymas", "Kodeksas": "kodeksas",
        "Statutas": "statutas", "Nutarimas": "nutarimas", "Įsakymas": "įsakymas"}  # all masculine: "jį keičiantis …, kurio"


def _kind(nr: str, rusis: str | None = None) -> str:
    """'įstatymas Nr. XV-659', 'statutas Nr. XV-12'; a resolution key ('875/2025-12-03') gets its 'Nr.' when shown."""
    if "/" in nr:
        return f"{'įsakymas' if rusis == 'Įsakymas' else 'nutarimas'} {nr}"
    return f"{KIND.get(rusis or '', 'įstatymas')} Nr. {nr}"


# --- Constitutional Court rulings not yet in the text (ACCURACY B3) ----------------------------------
# A ruling that a provision "prieštarauja" (present tense) the Constitution takes effect on its official publication;
# the Chancellery then notes it in the next consolidation ("Nr. KT44-A-N4/2026"). Until then our text can't show it.
# Read from the operative part ("nutaria: 1. Pripažinti, kad …"); "neprieštarauja" and "prieštaravo" (a wording no
# longer in force) change nothing.
RE_VERDICT = re.compile(r"\b(ne)?prieštara(?:uja|vo)\b")
RE_PUBLISH_ON = re.compile(r"turi būti oficialiai paskelbtas (\d{4}) m\. (" + "|".join(MONTHS) + r") (\d{1,2}) d\.")
_STANDARD = re.compile(r"straipsniui|straipsniams|daliai|dalims|punktui|punktams|papunkčiui|principui|principams")


def ruling_operative(text: str) -> str:
    """The operative part of a ruling, one line: after the last "nutaria:" up to "Šis … nutarimas yra galutinis"."""
    ms = list(re.finditer(r"\bn\s?u\s?t\s?a\s?r\s?i\s?a\s?:", text or ""))
    if not ms:
        return ""
    part = text[ms[-1].end():]
    end = re.search(r"Šis (?:Lietuvos Respublikos )?Konstitucinio Teismo nutarimas yra galutinis|Konstitucinio Teismo teisėjai", part)
    return " ".join(part[:end.start() if end else 4000].split())


def ruling_effective(text: str, published: str | None) -> str | None:
    """A ruling applies from its official publication; the Court may set that date later ("turi būti oficialiai
    paskelbtas 2026 m. balandžio 10 d.", KT19-N4/2025)."""
    m = RE_PUBLISH_ON.search(" ".join((text or "").split()))
    return _date(m) if m else published


def ruling_targets(operative: str, genitive: str) -> list[str] | None:
    """Article tokens of the act named by `genitive` that the ruling finds in conflict with the Constitution now
    ("prieštarauja", also "prieštaravo (prieštarauja)"). [] = the act is named so, but no article could be read
    (the whole act, or an unusual wording); None = no such finding for this act.
    Only the subject of each finding counts: not the provisions named in its "tiek, kiek …" clause, nor the
    standard after the verdict ("… prieštarauja … Konstitucijos 46 straipsniui"), nor the act's approval law
    ("civilinio kodekso patvirtinimo … įstatymo 28 straipsnis") or an amending law's own transitional articles."""
    if genitive.lower().startswith("konstitucijos"):
        return None
    t = _sup_parens(operative.replace("\u2011", "-").replace("\u2010", "-"))  # "72(3) straipsnio" (BK) is 72³
    t = re.sub(r"prieštaravo\s*\(prieštarauja\)", "prieštarauja", t)
    while re.search(r"\([^()]*\)", t):  # wordings and publication data: "(2017 m. birželio 6 d. redakcija; TAR, …)"
        t = re.sub(r"\s*\([^()]*\)", "", t)
    low, gen = t.lower(), genitive.lower()
    found: list[str] | None = None
    prev = 0
    for v in RE_VERDICT.finditer(low):
        seg, prev = low[prev:v.start()], v.end()
        if v.group(1) or not v.group(0).endswith("uja"):
            continue
        seg = re.split(r",? tiek, kiek\b|,? ta apimtimi\b", seg)[0]
        for m in re.finditer(rf"respublikos {re.escape(gen)}(?!\w)", seg):
            span = re.split(r"\bnuostat\w*|\blietuvos respublikos\b|\bpripažinti\b", seg[m.end():])[0]
            if _STANDARD.search(span) or re.match(r"\s*(?:patvirtinimo|nr\.\s*[ivxl]+-\d+\b.*?pakeitimo įstatymo)", span):
                continue
            found = found if found is not None else []
            for n in re.finditer(rf"({NUMLIST})\s+straipsn", span):
                found += _range_nums(n.group(1))
    return found


def _outdated_reason(items: list[tuple[str, str, str]], kinds: dict | None = None) -> str:
    """Laws in force, missing from the text, as one sentence for readers (and data.json):
    'Nuo 2025-12-24 galioja jį keičiantis įstatymas XV-659, kurio šiame tekste dar nėra'."""
    first = {}
    for when, nr, how in sorted(set(items)):
        first.setdefault((nr, how), when)
    laws = sorted(((w, nr, how) for (nr, how), w in first.items()))
    if len(laws) == 1:
        w, nr, how = laws[0]
        if how == "self":
            return f"Nuo {w} taikoma nauja šio straipsnio redakcija, nustatyta šio teisės akto {nr} straipsnyje; šiame tekste jos dar nėra"
        if how == "kt":
            return (f"Nuo {w} galioja Konstitucinio Teismo nutarimas Nr. {nr}, kuriuo šio straipsnio nuostatos (ar jų "
                    f"dalis) pripažintos prieštaraujančiomis Konstitucijai; šiame tekste to dar nėra")
        if how == "rewrite":
            return f"Nuo {w} galioja nauja akto redakcija ({_kind(nr, (kinds or {}).get(nr))}), kurios šiame tekste dar nėra"
        return f"Nuo {w} galioja jį keičiantis {_kind(nr, (kinds or {}).get(nr))}, kurio šiame tekste dar nėra"
    what = {"rewrite": "nauja akto redakcija, ", "kt": "Konstitucinio Teismo nutarimas, ", "self": "šio akto straipsnis, "}
    listed = ", ".join(f"{nr} ({what.get(how, '')}nuo {w})" for w, nr, how in laws)
    return f"Galioja jį keičiantys teisės aktai {listed}, kurių šiame tekste dar nėra"


def assess(act: Act, scope_act: dict, laws: Laws, day: str, seen: str | None = None) -> ActStatus:
    S, T = act.version_from or "0000-00-00", act.version_to
    state = "future" if S > day else ("past" if T and T < day else "current")
    st = ActStatus(day, state, expires=act.expires)
    if act.expires and act.expires <= day:  # the whole act is no longer in force
        for a in act.main.articles:
            st.articles[a.label] = Status("repealed", [f"visas teisės aktas neteko galios {act.expires}"],
                                          applies_from=act.expires)
        return st
    anchor = min(S, seen) if seen else min(S, day)  # stable over time (see _candidate_laws)
    since = (dt.date.fromisoformat(anchor) - dt.timedelta(days=365)).isoformat() if act.version_from else "0000-00-00"
    cands = _candidate_laws(act, scope_act, laws, day, seen)
    consolidated = {ref_key(x["nr"], x.get("adopted") or "") for x in act.amendments if x.get("nr")}
    if scope_act.get("document") and len(act.documents) > 1:  # one of several documents of a resolution (D-027)
        cands = [(for_document(law, act.documents, scope_act["document"]), d) for law, d in cands]
    labels = [a.label for a in act.main.articles]
    rulings = _rulings(act, scope_act, laws, day, seen)
    selfs = _self_amendments(act)
    for nr, eff, toks in rulings:
        if not toks:  # no text, or no article we could read: tell readers at act level
            st.notices.append(f"Konstitucinio Teismo nutarimas Nr. {nr} (galioja nuo {eff}) dėl šio teisės akto "
                              f"šiame tekste dar nepažymėtas")
    for law, d in cands:
        # a law in force after S that the text doesn't reference anywhere
        ent = d.get("isigalioja") or "9999"
        if ent > day or ent <= S or not any(x <= day for x in law.all_dates or {law.default or "9999"}):
            continue
        if law.redates or law.preamble_only or law.other_doc or law.final_of:
            continue  # it changes another resolution, only the preamble, another of its documents, or another law's
            # final provisions (XIV-2838 re-dating XIV-2241): not this text
        refs_anywhere = any(law.nr == r.nr for a in act.main.articles for r in a.all_refs())
        toks = [t for ts in law.targets.values() for t in ts] or list(law.title_targets)
        new = [t for t in toks if not any(_matches(t, l) for l in labels)]
        if refs_anywhere and not new and toks:
            continue
        # no article targets we can map (a structural change, or an older order known by its metadata only): the whole
        # act is uncertain, also where a note of the text names it: it took effect after this text's own start, so the
        # text can hold only an earlier part of it (B88: HN107's 2020 text names V-383, whose rest applies from 2022)
        if not toks:
            st.act_level_flags.append(f"{law.nr} (galioja nuo {ent}) dar neįtrauktas į tekstą")
        elif new:     # it adds (or renumbers) articles this text doesn't have yet
            dec = [_new_labels(sorted(set(new)), labels).get(t) for t in sorted(set(new))]
            sup = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
            shown = [(x.split("-")[0] + x.split("-")[1].translate(sup) if "-" in x else x) if x else t
                     for x, t in zip(dec, sorted(set(new)))]
            one = len(shown) == 1
            st.notices.append(f"{law.nr} (galioja nuo {ent}) papildo {', '.join(shown[:6])} "
                              f"{'straipsniu, kurio' if one else 'straipsniais, kurių'} šiame tekste dar nėra")
            st.added += [{"label": x, "law": law.nr, "from": ent} for x in dec if x]
    if S > day:  # a future text lacks an article that a law's addition put in force today (GKĮ 31¹: added from
        # 2026-08-01 by XV-1073, gone from its 2027 wording; B49): it exists today, with no text here
        have = {n["label"] for n in st.added}
        for law, d in cands:
            for o in law.additions:
                ds = law.own_dates.get(o) or ({law.default} - {None})
                toks = [t for t in law.targets.get(o, []) if not any(_matches(t, l) for l in labels)]
                if not ds or min(ds) > day or not toks:
                    continue
                for t, x in _new_labels(toks, labels).items():
                    if x and x not in have:
                        st.added.append({"label": x, "law": law.nr, "from": min(ds)})
                        sx = x.split("-")[0] + x.split("-")[1].translate(str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")) if "-" in x else x
                        st.notices.append(f"{law.nr} (galioja nuo {min(ds)}) papildė {sx} straipsniu, kurio šiame (būsimame) tekste nėra")
                        have.add(x)
    st.unexplained = _unexplained_boundaries(act, cands, laws, day)
    expired = _expired_articles(act, day)
    # a law setting out the whole act anew, not yet in this text (its header would list it): every article
    rewrites = list(act.rewrites) + [(w, law.nr) for law, _ in cands if (w := law.rewrite_date())
                                     and law.nr not in {n for _, n in act.rewrites} and w > S]
    revived = any(S < w <= day for w, _ in rewrites)  # a repealed article may come back in the new wording
    for w, nr in sorted(set(rewrites)):  # its new articles have no page here (EVEDĮ XV-237: 24–27, B53)
        if S <= day and S < w <= day and nr not in {n for _, n in act.rewrites}:
            st.notices.append(f"Nuo {w} galioja nauja viso akto redakcija ({nr}), kurios šiame tekste dar nėra: joje "
                              f"gali būti ir naujų straipsnių ar punktų, kurių čia nėra. Galiojantį tekstą žr. e-tar.lt")
    for a in act.main.articles:
        art = a.variant_on(day)
        gone, since_ = _article_repealed(art)
        exp = article_expiry(art, a.label)
        if exp and exp <= day:  # a temporary article whose own text says it lapses on `exp`
            gone, since_ = True, exp
        if gone and (since_ or "0000") <= day and not revived:
            # an amendment in force that the text lacks may have put it back (B86: MKPVKNSA 3, repealed in 2007 in the
            # 2009–2011 text, a new point 3 in force today): an act-level gap, or a law naming this very article
            back = [f"{law.nr} (galioja nuo {min(xs)}) keičia šį straipsnį, bet šiame tekste dar neįtrauktas"
                    for law, _ in cands if law.targets_article(a.label) and law.nr not in {r.nr for r in art.all_refs()}
                    and (xs := [x for x in law.dates_for(a.label) if S < x <= day])]
            if S <= day and (back or st.act_level_flags):
                st.articles[a.label] = Status("unknown", [f"šiame tekste straipsnis neteko galios{' ' + since_ if since_ else ''}, "
                                                          f"tačiau vėlesni pakeitimai į tekstą dar neįtraukti"]
                                              + back + list(st.act_level_flags))
                continue
            st.articles[a.label] = Status("repealed", [f"straipsnis neteko galios{' ' + since_ if since_ else ''}"],
                                          applies_from=since_)
            continue
        refs = art.all_refs()
        reasons, pending, outdated = [], [], []
        if a.label in expired:
            reasons.append(expired[a.label])
        for when, nr in rewrites:  # the whole act is replaced on `when`
            if S > day and day < when <= S:
                pending.append(when)
            elif S <= day and S < when <= day:
                outdated.append((when, nr, "rewrite"))
        for law, _ in cands:  # a new wording of this very article, staged inside a whole-act rewrite (VAĮ 33)
            for x in law.staged.get(a.label, ()):
                if S <= day and S < x <= day and not (art.valid_from and art.valid_from >= x):
                    outdated.append((x, law.nr, ""))
                elif S > day and day < x <= S:
                    pending.append(x)
            if a.label in law.staged_cond and (law.staged_cond[a.label] or "0000") <= day and \
                    law.nr not in {r.nr for r in art.all_refs()}:  # once in force, the consolidation notes it here
                lb = law.staged_cond[a.label]
                reasons.append(f"{law.nr}: nauja šio straipsnio redakcija įsigalioja pagal sąlygą"
                               + (f" (ne anksčiau kaip {lb})" if lb else ""))
        for own, targets, when in selfs:  # the act's own staged new wording of this article (SŽNSĮ 142, 143)
            if a.label in targets:
                if S <= day and S < when <= day:
                    outdated.append((when, own, "self"))
                elif S > day and day < when <= S:
                    pending.append(when)
        kt_later = []
        later_chapters = []  # (date, law): this article's chapter set out anew after today by a law in its notes
        for nr, eff, toks in rulings:
            if toks and any(_matches(t, a.label) for t in toks):
                if eff <= day:
                    outdated.append((eff, nr, "kt"))
                else:  # the Court set a later official publication (KT19-N4/2025: a year later)
                    kt_later.append((eff, nr))
        own_nrs = {r.nr for n in art.notes for r in n.refs} | {r.nr for b in art.blocks for n in b.notes for r in n.refs}
        for r in refs:
            law = laws.get(r.nr)
            if law is None:
                if re.fullmatch(r"[IVXL]+-\d+|[\w/-]+/\d{4}-\d{2}-\d{2}", r.nr):  # a law, resolution or order we don't know
                    reasons.append(f"{r.nr}: nežinoma įsigaliojimo data")
                    UNKNOWN_REFS.add(r.nr)
                    continue
                dates = {r.published or r.adopted}  # e.g. Constitutional Court rulings: from publication
            else:
                dates = law.dates_for(a.label)
                if r.nr not in own_nrs and not law.targets_article(a.label) and law.default:
                    # a chapter's note (the law changed the chapter, not this article by name): its staged
                    # dates for other named articles say nothing about this one. Use the general date and the
                    # dates of its own articles that change structure ("papildymas … skirsniu", BĮ XV-938 art 24)
                    dates = {law.default} | {d for o, ds in law.own_dates.items() if o not in law.targets for d in ds}
                    # a consolidation valid on `day` with no stage inside its range holds exactly the stages in force
                    # then, whichever this article's is (GKĮ 30, XV-1073: 2026-08-01 / 2027-01-01, text 08-01..12-31)
                    settled = T and S <= day <= T and all(x <= S or x > T for x in dates)
                    # the newest consolidation, open-ended, from S holds the stages up to S and none after today (the
                    # next stage gets a consolidation of its own): D1-188 for RŽNTKŽŠA, 2026-10-20 / 2027-01-01, text
                    # from 2026-10-20. A stage between S and today is still unsettled
                    settled = settled or (not T and S <= day and all(x <= S or x > day for x in dates))
                    later_chapters += [(w, law.nr) for o, chs in law.chapters.items() if any(_in_part(a.path, c) for c in chs)
                                       for w in law.own_dates.get(o) or {law.default} - {None} if w > day]
                    if min(dates) <= day < max(dates) and not settled:
                        kind = _kind(r.nr, laws.meta.get(r.nr, {}).get("rusis")).split()[0]
                        reasons.append(f"{r.nr}: skyrių keitęs {kind} įsigalioja dalimis "
                                       f"({', '.join(sorted(dates))}); neaišku, kuri dalis taikoma šiam straipsniui")
                        continue
                if law.conditional_for(a.label) and (state != "current" or law.not_in_force):
                    reasons.append(f"{r.nr}: dalis įsigalioja pagal sąlygą (be datos)")
                if (rd := _unsettled(_recent_redating(law, laws, since), law, laws, S)) and law.targets_article(a.label) and \
                        any(x > since for x in law.dates_for(a.label)):
                    reasons.append(f"{r.nr}: įsigaliojimo datas keitė ar keičia {', '.join(rd)}")
            if not dates:
                reasons.append(f"{r.nr}: nežinoma įsigaliojimo data")
            for x in dates:
                if S > day and day < x <= S:
                    pending.append(x)
                elif S <= day and S < x <= day:
                    outdated.append((x, r.nr, ""))
        ref_nrs = {r.nr for r in refs}
        for law, d in cands:
            if law.redates:  # it moved another resolution's staged dates (No. 1067 for No. 210)
                if a.label in law.redate_points and law.nr not in ref_nrs and (d.get("priimtas") or "") >= since:
                    reasons.append(f"{law.of_law}: įsigaliojimo datas keitė {law.nr}")
                continue
            # a law article that replaces this article's whole chapter changes it too (TeisĮ VII skyrius, XIV-1570)
            chap = {x for o, chs in law.chapters.items() for x in (law.own_dates.get(o) or {law.default} - {None})
                    if any(_in_part(a.path, c) for c in chs)}
            if law.nr in ref_nrs or not (law.targets_article(a.label) or chap):
                continue
            if chap and not law.targets_article(a.label) and law.nr in {r.nr for h in a.path for n in h.notes for r in n.refs}:
                continue  # the chapter's own note lists it ("Papildyta skyriumi: Nr. 848"): consolidated (VZSPNT III)
            amended = set(re.findall(OF_LAW, (d.get("pavadinimas") or "").lower()))
            if {n.upper() for n in amended} & ref_nrs and not law.of_law:
                continue  # it amends an amending law that the article's notes already list (re-dating it, or another part)
            if (rd := _unsettled(_recent_redating(law, laws, since), law, laws, S)) and any(x > since for x in law.dates_for(a.label)):
                reasons.append(f"{law.nr}: įsigaliojimo datas keitė ar keičia {', '.join(rd)}")
                continue
            ds = [x for x in (law.dates_for(a.label) if law.targets_article(a.label) else chap) if x <= day]
            if ds and any((r.adopted or "") > max(ds) for r in refs):
                continue  # the article was amended again after this law applied: consolidators had it then
            if ds and any(n == law.nr and w <= S for w, n in act.rewrites) and max(ds) <= S:
                continue  # the text is this law's new wording of the whole act, from S: its articles' notes don't list it (KPAKATĮ XIV-2729)
            if ds and law.nr in consolidated and max(law.all_dates | set(ds)) <= S:
                continue  # the consolidation's own "Pakeitimai:" list has it and all of it applied by S: consolidated even
                # where the article's notes don't name it (ŠTVT 47 and 1-399, ETNauT 27 and 1-333: e-tar shows the same
                # text). Not when any part comes later: its dates per point may be wrong (PAILGA 6, 8: No. 744's item 2
                # from 2026-01-01, read as 2025-10-31)
            if ds:
                outdated.append((min(ds), law.nr, ""))
                st.missing.append({"nr": law.nr, "in_force": min(ds), "title": d.get("pavadinimas"), "articles": [a.label]})
        def _for_me(r: str) -> bool:  # "TAR pastaba. 25 straipsnio 3 dalis …" concerns article 25 only
            named = re.findall(r"(\d+(?:-\d+)?)\s+straipsn", r)
            return not named or any(_matches(n, a.label) for n in named)
        section_notes = type("S", (), {"blocks": [Block("editorial", None, r) for h in a.path for r in h.remarks if _for_me(r)]})()
        note_pending, note_unknown, note_info = tar_note_effects(art, day, with_info=True)
        sp, su, si = tar_note_effects(section_notes, day, with_info=True)  # the chapter's/section's own notes
        note_pending, note_unknown, note_info = note_pending + sp, note_unknown + su, note_info + si
        reasons += note_unknown
        if a.duplicates:
            reasons.insert(0, f"šaltinio tekste šis straipsnis pateiktas {len(a.duplicates) + 1} kartus, be datų")
        if outdated:
            s = Status("outdated", [_outdated_reason(outdated, {nr: laws.meta.get(nr, {}).get("rusis") for _, nr, _ in outdated})])
        elif reasons:
            s = Status("unknown", list(dict.fromkeys(reasons)))  # one article may list the same law several times
        elif pending:
            s = Status("pending", [f"keičiama nuo {min(pending)}"], changes_on=min(pending), applies_from=max(pending))
        elif st.act_level_flags:
            s = Status("unknown", list(st.act_level_flags))
        else:
            s = Status("current")
        if s.state == "current" and kt_later:
            w, nr = min(kt_later)
            s.changes_on = w
            s.note = (f"Konstitucinio Teismo nutarimu Nr. {nr} šio straipsnio nuostatos (ar jų dalis) pripažintos "
                      f"prieštaraujančiomis Konstitucijai; nutarimas oficialiai skelbiamas ir taikomas nuo {w}")
        elif s.state == "current" and note_pending:
            s.part_pending, s.changes_on = min(note_pending), min(note_pending)
            s.note = f"pagal TAR pastabą dalis šio straipsnio nuostatų įsigalioja tik nuo {min(note_pending)}"
        elif s.state == "current" and note_info:
            s.note = note_info[0]
        elif s.state == "current" and any(r.nr.startswith("KT") for r in refs):
            s.note = "šį straipsnį yra paveikęs Konstitucinio Teismo nutarimas (žr. pakeitimų nuorodas)"
        if s.state == "current":
            if exp and exp > day:
                s.changes_on = min(x for x in (s.changes_on, exp) if x)
                s.note = s.note or f"šis straipsnis netenka galios {exp}"
            refs_all = [r for v in [a, *a.variants, *a.duplicates] for r in v.all_refs()]  # incl. dated wordings
            fc = _future_change(a.label, refs_all, cands, day, labels, S)  # a law already adopted changes it later
            for w, nr in rewrites:  # or sets out the whole act anew
                if w > day and (fc is None or w < fc[0]):
                    fc = (w, nr, True)
            for law, _ in cands:  # or a staged wording of this article in such a rewrite
                for w in law.staged.get(a.label, ()):
                    if w > day and (fc is None or w < fc[0]):
                        fc = (w, law.nr, True)
                # or its chapter set out anew on a later day (D1-188: RŽNTKŽŠA's chapter I again from 2027-01-01)
                for o, chs in law.chapters.items():
                    if any(_in_part(a.path, c) for c in chs):
                        for w in law.own_dates.get(o) or {law.default} - {None}:
                            if w > day and (fc is None or w < fc[0]):
                                fc = (w, law.nr, True)
            for w, nr in later_chapters:  # the same, found through the article's own notes
                if fc is None or w < fc[0]:
                    fc = (w, nr, True)
            if fc:
                s.future_change = fc
                s.changes_on = min(x for x in (s.changes_on, fc[0]) if x)
        st.articles[a.label] = s
    return st


def apply_register_state(st: ActStatus, row: dict, day: str, scope_act: dict | None = None) -> tuple[bool, bool]:
    """The act's own state in the register, applied to its labels (pages and validators alike):
    - adopted, not in force yet ("neįsigaliojęs" with a later entry date, NTRgĮ until 2027-01-01): every article
      is "Įsigalios D";
    - otherwise not "galioja" (and no repeal date in the text): nothing on its pages is "current";
    - repealed as a whole by another act's provision that neither the register's state nor any consolidation shows
      (the scope's `repealed: {from: D, by: "… papunktį"}`, read from the repealing act's text): every article "Neteko galios D".
    Returns (not_yet, register_bad)."""
    rep = (scope_act or {}).get("repealed")
    if rep and str(rep["from"]) <= day and not (st.expires and st.expires <= day):
        # VTPPMMT: aplinkos ministro įsakymas Nr. 623 repealed from 2012-12-22 by D1-416 item 5.3; the register still
        # says "galioja" (with "negalioja" 2010-05-18, the repealing order's date) and its last text ends 2010-05-22
        gone = str(rep["from"])
        st.expires = gone
        st.act_level_flags = []  # amendments the text lacks don't matter once the act itself is gone
        st.notices.append(f"Šis teisės aktas neteko galios {gone} pagal {rep['by']}")  # by: "… įsakymo Nr. D1-416 5.3 papunktį"
        for k in st.articles:
            st.articles[k] = Status("repealed", [f"visas teisės aktas neteko galios {gone}"], applies_from=gone)
        return False, True
    not_yet = row.get("galioj_busena") == "neįsigaliojęs" and (row.get("isigalioja") or "") > day
    register_bad = row.get("galioj_busena") not in (None, "galioja") and not st.expires and not not_yet
    if not_yet:
        d0 = row["isigalioja"]
        st.notices.append(f"Šis teisės aktas įsigalioja {d0}; iki tol jis netaikomas")
        for k, v in st.articles.items():
            if v.state in ("current", "pending"):
                st.articles[k] = Status("pending", [f"visas teisės aktas įsigalioja {d0}"], changes_on=d0,
                                        applies_from=max(d0, v.applies_from or d0))
    gone = (row.get("negalioja") or "")[:10]
    if register_bad and row.get("galioj_busena") == "negalioja" and gone and gone <= day:
        # repealed as a whole on a known day (REMITĮR: Regulation 1348/2014, repealed by 2026/256 from 2026-04-28):
        # every article is "Neteko galios D", as when the text itself says so, not "Neaišku"
        src = "EUR-Lex" if row.get("priemusi_inst") == "Europos Sąjunga" else "Teisės aktų registras"
        st.expires = gone
        st.notices.append(f"Šis teisės aktas neteko galios {gone} ({src})")
        for k in st.articles:
            st.articles[k] = Status("repealed", [f"visas teisės aktas neteko galios {gone}"], applies_from=gone)
        return not_yet, register_bad
    if register_bad:
        why = f"Teisės aktų registre šio akto būsena: „{row['galioj_busena']}“"
        st.notices.append(why)
        for k, v in st.articles.items():
            if v.state == "current":
                st.articles[k] = Status("unknown", [why])
    return not_yet, register_bad
