"""Render parsed acts to static HTML + JSON (no JavaScript).

Layout (all directory indexes, so URLs have no .html):
  /                              list of acts
  /ta/<tar_kodas>/               act: table of contents (or list of books for CK)
  /ta/<tar_kodas>/knyga/<n>/[dalis/<n>/]  contents split by book/part when an act is long
  /ta/<tar_kodas>/str/<label>/   one article: 52, 21-1, 6.228-1
  /ta/<tar_kodas>/priedas/<n>/   one annex
  /ta/<tar_kodas>/data.json      the whole act with statuses and provenance
  /_redirects                    aliases /dk/52 -> canonical (Cloudflare Pages format)
  /sitemap.xml, /robots.txt
Pages carry <meta name="robots" content="noindex"> unless indexable=True (P3 launch switch).
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import pathlib
import re
from dataclasses import dataclass

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

import difflib
import html as htmlmod

from . import eu
from .currency import ActStatus, Laws, _article_repealed, apply_register_state, assess
from .today import _suvestine_valid_on, _with_header, find_today, find_today_only
from .validate import dropped_lines
from .xref import Linker, Others
from . import eurlex
from . import api, definitions, feeds, fulltext, seimas
from .parse import Act, Article, Block, Note, parse
from . import source

ETAR_ACT = "https://www.e-tar.lt/portal/lt/legalAct/{}/asr"
ETAR_DOC = "https://www.e-tar.lt/portal/lt/legalAct/{}"
STATE_LABEL = {"current": "Galioja šiandien", "pending": "Įsigalios {}", "outdated": "Gali būti pasenęs", "unknown": "Neaišku, ar galioja",
               "repealed": "Neteko galios {}"}
STATES = ("current", "pending", "outdated", "unknown", "repealed")
ANNEX_LABEL = "Priedas: ar galioja šiandien, netikrinama"
ANNEX_NOTE = ("an annex of the consolidation in `text` (the stored one, or the one valid today when the stored one is past or "
              "future, source Suvestine): whether it is in force today and has today's wording is not checked; check "
              "e-tar.lt / EUR-Lex")
# a formula is an image on e-tar and absent from the open data: all that is left of it is its number alone on a line
# ("(6.6a)"; 2026-11-04: 496 such lines in 30 acts, VERT's price methodology among them, B73)
EQUATION_ONLY = re.compile(r"\(\s*\d+(?:\.\d+)*[a-z]?\s*\)")
FORMULA_MARK = "[formulė šaltinio tekste pateikta paveikslėliu – žr. e-tar.lt]"
FORMULAS_NOTICE = ("Šio teisės akto formulės oficialiame tekste pateiktos paveikslėliais, o atviruose duomenyse jų nėra: "
                   "čia matyti tik jų numeriai. Skaičiavimams naudokite tekstą e-tar.lt.")
FLATTENED_NOTE = "A table in the official text, given one cell per line in the open data: check the figures there."
STALE_DAYS = 2   # pages say so when the data were last checked longer ago than this
REGISTER_LAG_DAYS = 2  # article pages warn when more working days than this have no publication in the open data yet
# (TAR publishes on working days; the open data takes 1 day (60%) or 2 (30%), A19. 2026-10-31: the newest was 10-26,
# 4 working days missing, 5 calendar days: the old calendar threshold of 5 said nothing, and SŽNSĮ XV-1230 was among them)
HOLIDAYS = {"01-01", "02-16", "03-11", "05-01", "06-24", "07-06", "08-15", "11-01", "11-02", "12-24", "12-25", "12-26"}


def annex_label(x) -> str:
    """How an annex is named in lists, the API and the MCP answers: "6¹ priedas", "V priedas"; an appendix "1 priedėlis"
    (REACH XVII), or with its annex where the letters repeat (_appendix_nums: "I-A" -> "I priedo A priedėlis",
    2021/2139); the MCP server reads all of these back (worker-mcp articleLabel)."""
    num = re.sub(r"-(\d+)", lambda m: m.group(1).translate(SUP), x.num or "")
    if "priedėlis" in (x.header or "").lower():
        m = re.fullmatch(r"([IVXLC]+|\d+)-([A-Z])", x.num or "")
        return f"{m[1]} priedo {m[2]} priedėlis" if m else f"{num + ' ' if num else ''}priedėlis"
    return f"{num + ' ' if num else ''}priedas"


def annex_heading(x) -> str:
    """The page's heading: the header as printed ("I PRIEDAS", "1 priedėlis"); an appendix whose letter repeats in
    another annex says whose it is ("I priedo A priedėlis"), so its page title is not the same as II's."""
    if "priedėlis" in (x.header or "").lower() and re.fullmatch(r"([IVXLC]+|\d+)-([A-Z])", x.num or ""):
        return annex_label(x)
    return x.header or annex_label(x)


def _easter(y: int) -> dt.date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l_) // 433
    month, day = divmod(h + l_ - 7 * m + 90, 25)
    return dt.date(y, month, (h + l_ - 7 * m + 33 * month + 19) % 32)


def working_days_between(after: str, before: str) -> int:
    """Lithuanian working days strictly between two ISO days (Labour Code art. 123 holidays, Easter Monday)."""
    d, end, n = dt.date.fromisoformat(after) + dt.timedelta(days=1), dt.date.fromisoformat(before), 0
    while d < end:
        n += d.weekday() < 5 and d.strftime("%m-%d") not in HOLIDAYS and d != _easter(d.year) + dt.timedelta(days=1)
        d += dt.timedelta(days=1)
    return n
DATA_LICENSE = "https://creativecommons.org/licenses/by/4.0/deed.lt"
# IndexNow (bin/indexnow.py): public by design, served as /<key>.txt for the search engines to check
SKILL_PATH = "/skills/lithuanian-law-research/SKILL.md"
INDEXNOW_KEY = "f180eb8eacb25a690b2eef66a5f653fe"
# The official MCP registry checks this public key to accept "lt.atviri-teises-aktai/*" entries from us (bin/mcp_registry.py;
# the private key stays on the maintainer's PC, ~/.config/lt-law/mcp-registry-ed25519.pem)
MCP_REGISTRY_PUBKEY = "ahGaP+7P6sD21TpRevLjXEgnqgTdyUG9uAY3ZBgM8+o="
CONTACT = "kontaktai@atviri-teises-aktai.lt"  # Cloudflare Email Routing → the maintainer (docs/OPERATIONS.md)


def ld_json(obj: dict) -> str:
    """JSON for a <script> element: '<' escaped so text can never close the element."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def _day_before(d: str) -> str:
    return (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()

env = Environment(loader=FileSystemLoader(pathlib.Path(__file__).parent / "templates"),
                  autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)


def act_key_of(sa: dict) -> str:
    """An act's key in the API (`act` in definitions, search results): its slug, or its abbreviation."""
    return sa.get("slug") or (slug("-".join(sa["name"].split())) if sa.get("no_abbr") else slug(sa["abbr"]))


def slug(s: str) -> str:
    return s.lower().translate(str.maketrans("ąčęėįšųūž", "aceeisuuz"))


# the unit of an act: an article of a law, a point of rules approved by a Government resolution (KET). Both
# nouns are masculine, so "šis …", "šio …", "šiame …" agree either way
UNITS = {"straipsnis": {"seg": "str", "nom": "straipsnis", "gen": "straipsnio", "acc": "straipsnį", "loc": "straipsnyje",
                        "short": "str.", "plural": "straipsniai", "ins_pl": "straipsniais", "gen_pl": "straipsnių",
                        "amender": "įstatymas", "part": "dalis"},
         "punktas": {"seg": "p", "nom": "punktas", "gen": "punkto", "acc": "punktą", "loc": "punkte",
                     "short": "p.", "plural": "punktai", "ins_pl": "punktais", "gen_pl": "punktų",
                     "amender": "nutarimas", "part": "papunktis"}}


def unit_name(u: dict, pretty: str, title: str) -> str:
    """'52 straipsnis. Nuotolinis darbas'; a point has no title: '52 punktas'."""
    return f"{pretty} {u['nom']}" + (f". {title}" if title else "")


# a resolution's or order's key: '875/2025-12-03', 'D1-188/2026-10-19', '1-348/D1-1014/3-742/2024-11-29' (a joint
# order); the whole number before the date ("D1-Nr. 188" was shown for D1-188 until 2026-11-24)
RE_KEY = re.compile(r"(?<![\w/-])(?!\d{4}-\d{2}-\d{2}/)((?:[A-ZĄČĘĖĮŠŲŪŽ0-9]+-)*\d+(?:/(?:[A-ZĄČĘĖĮŠŲŪŽ0-9]+-)*\d+)*)"
                    r"/(\d{4}-\d{2}-\d{2})\b")


def nr_text(s: str) -> str:
    """Resolution and order keys in text for people: '875/2025-12-03' -> 'Nr. 875 (2025-12-03)', 'D1-188/2026-10-19'
    -> 'Nr. D1-188 (2026-10-19)'."""
    return RE_KEY.sub(r"Nr. \1 (\2)", s or "")


env.filters["nrs"] = nr_text
LAW_DOCS: dict[str, str] = {}  # amending act number or key -> dokumento_id (filled by Site), for links on pages
ADOPTED: dict[str, dict] = {}  # law number -> the Seimas vote that adopted it (seimas.adopted_votes, filled by Site)


def law_links(text: str):
    """A reason for readers with each amending act linked to e-tar: 'XV-659' and '875/2025-12-03' (shown as
    'Nr. 875 (2025-12-03)'). Escaped first; only our own links are added."""
    from markupsafe import Markup, escape
    def link(nr: str, shown: str) -> str:
        doc = LAW_DOCS.get(nr)
        return f'<a href="{escape(ETAR_DOC.format(doc))}">{shown}</a>' if doc else shown
    t = str(escape(text or ""))
    t = RE_KEY.sub(lambda m: link(m.group(0), f"Nr. {m.group(1)} ({m.group(2)})"), t)
    t = re.sub(r"(?<![\w-])([IVXL]+-\d+)\b", lambda m: link(m.group(1), m.group(1)), t)
    return Markup(t)


env.filters["lawlinks"] = law_links


def vote_text(v: dict | None):
    """'; Seime už 90, prieš 0, susilaikė 1' after an amending law's date in the notes, linked to the lrs.lt record."""
    from markupsafe import Markup, escape
    if not v:
        return ""
    t = f"už {v['for']}, prieš {v['against']}, susilaikė {v['abstain']}"
    if v.get("record"):
        t = f'<a href="{escape(v["record"])}" title="Seimo balsavimas dėl įstatymo priėmimo {escape(v["at"])}">{t}</a>'
    return Markup(f"; Seime {t}")


env.filters["vote"] = vote_text
env.filters["ucfirst"] = lambda t: (t[:1].upper() + t[1:]) if t else t  # keeps "XV-659" (capitalize would not)


def acts_count(n: int, prefix: str = "") -> str:
    """Lithuanian agreement after a number: 1 ES teisės aktą, 2 ES teisės aktus, 11 ES teisės aktų."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {prefix}teisės aktą"
    if 2 <= n % 10 <= 9 and not 12 <= n % 100 <= 19:
        return f"{n} {prefix}teisės aktus"
    return f"{n} {prefix}teisės aktų"


env.filters["acts_count"] = acts_count


def approved_by(name: str) -> str:
    """"patvirtintas / patvirtinta / patvirtinti / patvirtintos", agreeing with the document's head noun: "aprašas,
    patvirtintas …", "metodika, patvirtinta …", "reikalavimai, patvirtinti …", "taisyklės, patvirtintos …"."""
    # the head noun: the last word in the nominative, quoted titles and designations aside ("Statybos techninis
    # reglamentas STR 1.07.03:2017 „…“" -> "reglamentas"; "Duomenų tvarkymo operacijų, kurioms …, sąrašas" -> "sąrašas";
    # "… asmens duomenų tvarkymo sutartyse" -> "sąlygos" before it)
    words = [x.lower() for x in re.sub(r"„[^“]*“?", " ", name).replace(",", " ").split() if re.fullmatch(r"[^\W\d]+", x) and not x.isupper()]
    w = next((x for x in reversed(words) if x.endswith(("as", "is", "us", "ai", "a", "ė", "os", "ės"))), "")
    if re.search(r"\w(?:as|is|us) ir ", re.sub(r"„[^“]*“?", " ", name)) and w.endswith(("as", "is", "us")):
        return "patvirtinti"  # two documents: "… sąrašas ir … aprašas" (PAILGA)
    if w.endswith(("as", "is", "us")):
        return "patvirtintas"
    if w.endswith("ai"):
        return "patvirtinti"
    if w.endswith(("a", "ė")):
        return "patvirtinta"
    return "patvirtintos"  # "taisyklės", "sąlygos", "nuostatos"


def lt_count(n: int, one: str, few: str, many: str) -> str:
    """A number with its noun in the nominative: 1 teisės aktas, 7 teisės aktai, 11 (or 20) teisės aktų."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    return f"{n} {few}" if 2 <= n % 10 <= 9 and not 12 <= n % 100 <= 19 else f"{n} {many}"


env.filters["lt_count"] = lt_count
env.globals["contact"] = CONTACT
CODE_URL = "https://github.com/marrgss/lt-law"  # the public code repository (D-055)
env.globals["code_url"] = CODE_URL


AREAS = pathlib.Path(__file__).resolve().parents[2] / "scope" / "areas.yaml"
STATIC_REDIRECTS = 2000  # the host's limit on a `_redirects` file's static rules


def _area_groups(acts: list[dict]) -> list[dict]:
    """The home page list by area (scope/areas.yaml), each in the file's order; acts not listed go under "Kiti"."""
    import yaml
    areas = yaml.safe_load(AREAS.read_text())["areas"] if AREAS.exists() else []
    by = {a["abbr"]: a for a in acts}
    out, used = [], set()
    for g in areas:
        mine = [by[x] for x in g["acts"] if x in by]
        used |= {a["abbr"] for a in mine}
        if mine:
            out.append({"name": g["name"], "slug": g.get("slug"), "acts": mine})
    rest = [a for a in acts if a["abbr"] not in used]
    if rest:
        out.append({"name": "Kiti" if out else "Teisės aktai", "acts": rest})
    return out


def _plain(a) -> str:
    """An article's title and text, one string (for finding defined terms)."""
    return " ".join([a.title or ""] + [b.text for b in a.blocks])


def act_alias(seed_slug: str | None, name: str, abbr: str, tag: str | None) -> str:
    """The act's short URL (/dk/, /viesuju-istaigu-istatymas/): the seed's slug, the abbreviation in use, or the name.
    A file name is at most 255 bytes (api/v1/refs/<alias>.json): a name longer than 220 (the longest kept whole) gives its
    first words and a hash of the whole (2026-11-03: rules with 250–500-byte names)."""
    alias = seed_slug or (slug("-".join(name.split())) if not tag else slug(abbr))
    if len(alias.encode()) > 220:
        cut = alias.encode()[:150].decode("utf-8", "ignore").rsplit("-", 1)[0].rstrip(",-")
        alias = f"{cut}-{hashlib.sha1(alias.encode()).hexdigest()[:6]}"
    return alias

SITEMAP_URLS = 45000  # the protocol's limit is 50,000 a file (64,799 in one until 2026-11-04)


def sitemap_files(urls: list[tuple[str, str]], base: str, day: str, limit: int = SITEMAP_URLS) -> list[tuple[str, str]]:
    """(file name, content): one sitemap.xml, or above the limit parts sitemap-1.xml … and sitemap.xml as their index
    (robots.txt names sitemap.xml either way)."""
    head = '<?xml version="1.0" encoding="UTF-8"?>\n<%s xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    def urlset(part):
        return head % "urlset" + "".join(f"<url><loc>{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in part) + "</urlset>\n"
    if len(urls) <= limit:
        return [("sitemap.xml", urlset(urls))]
    parts = [urls[i:i + limit] for i in range(0, len(urls), limit)]
    index = head % "sitemapindex" + "".join(f"<sitemap><loc>{base}/sitemap-{n}.xml</loc><lastmod>{day}</lastmod></sitemap>\n"
                                            for n in range(1, len(parts) + 1)) + "</sitemapindex>\n"
    return [("sitemap.xml", index)] + [(f"sitemap-{n}.xml", urlset(part)) for n, part in enumerate(parts, 1)]


def redirect_lines(rules: list[str], static_limit: int = STATIC_REDIRECTS) -> list[str]:
    """The `_redirects` file within the host's limits: 100 dynamic rules ("/dk/:n"; beyond them the aliases are served
    only by the account's Bulk Redirects, bin/cf_redirects.py) and 2,000 static ones (2026-11-04: 2,022 at 1,011 acts,
    the deploy refused). Bulk Redirects match "/dk/" and its subpaths, not "/dk": the bare aliases fill what is left,
    shortest first ("/dk" is typed, a 150-letter name isn't). The acts' own lines stay: Bulk Redirects land on them."""
    dynamic = [r for r in rules if ":n" in r]
    if len(dynamic) <= 100 and len(rules) <= static_limit:
        return rules
    static = [r for r in rules if ":n" not in r]
    bare = [r for r in static if re.match(r"/[^/ ]+ ", r)]
    own = [r for r in static if not re.match(r"/[^/ ]+ ", r)]
    return own + sorted(bare, key=len)[:max(0, static_limit - len(own))]


def cite_of(scope_act: dict) -> str:
    """What precedes an article number: the established abbreviation ("DK 52 str."), or for an act with none in use
    the genitive of its name ("Vyriausybės įstatymo 5 str."): abbreviations are never coined (ROADMAP)."""
    if not scope_act.get("no_abbr"):
        return scope_act["abbr"]
    g = scope_act["genitive"]
    return re.sub(r"„(\w)", lambda m: "„" + m.group(1).upper(), g[:1].upper() + g[1:])


@dataclass
class ActInfo:
    abbr: str     # the key (URLs, data); shown only when it is an established abbreviation (`tag`)
    name: str
    genitive_cap: str
    number: str
    tar: str
    doc: str
    etar_url: str
    full_title: str
    u: dict = None  # unit words (UNITS)
    paren: str = ""  # " (DK)" after the name, or ""
    tag: str = ""   # the abbreviation shown ("DK"), or "" for an act with none in use (seed `no_abbr`): cited by name
    cite: str = ""  # what precedes an article number: "DK" or "Vyriausybės įstatymo" ("… 5 str.")
    # where the official text is and whose consolidation this is (D-037: EU acts from EUR-Lex)
    official_site: str = "e-tar.lt"
    consolidation: str = "Seimo kanceliarijos suvestinė redakcija"
    eu: bool = False


def _refs(notes: list[Note], meta: dict) -> list[dict]:
    out = []
    for n in notes:
        refs = []
        for r in n.refs:
            d = meta.get(r.nr)
            url = ETAR_DOC.format(d["dokumento_id"]) if d else "https://www.e-tar.lt"
            refs.append({"nr": r.nr.split("/")[0], "adopted": r.adopted, "url": url,  # '875/2025-12-03' shown as 875
                         **({"vote": ADOPTED[r.nr]} if r.nr in ADOPTED else {})})
        out.append({"label": n.label, "refs": refs})
    return out


SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def display_text(b: Block) -> str:
    """The text with its own flattened superscript number shown as such: '161. …' → '16¹. …' when the
    anchor says the part is 16¹ (the anchor is decoded by the parser; the text keeps the source form)."""
    t = b.text
    if b.anchor and (m := __import__("re").search(r"(\d+)-(\d+)$", b.anchor)):
        n, k = m.groups()
        for flat in (n + k, f"{n}-{k}"):  # "161." or, after points.parse_points (B60), "22-1."
            if t.startswith(flat) and t[len(flat):len(flat) + 1] in (".", ")"):
                t = n + k.translate(SUP) + t[len(flat):]
                break
    if t == b.text and b.num and "-" in b.num and b.kind in ("part", "point"):  # points: "662." → "66².", "3.21." → "3.2¹."
        flat = b.num.replace("-", "")
        if t.startswith(flat) and t[len(flat):len(flat) + 1] in (".", ")"):
            t = re.sub(r"-(\d+)", lambda m: m.group(1).translate(SUP), b.num) + t[len(flat):]
    if not EU_ACT and (t.rstrip().endswith(("pagal šią formulę:", "pagal formulę:", "apskaičiuojamas taip:")) or EQUATION_ONLY.fullmatch(t.strip())):
        t += " " + FORMULA_MARK
    return t


def _unique_anchors(blocks: list[dict]) -> list[dict]:
    """Two wordings of one part printed side by side (TAR pastaba "… redakcija nuo D") share an anchor."""
    seen: dict[str, int] = {}
    for b in blocks:
        a = b.get("anchor")
        if a:
            seen[a] = seen.get(a, 0) + 1
            if seen[a] > 1:
                b["anchor"] = f"{a}-r{seen[a]}"
    return blocks


# what the version fields of data.json mean (feedback P7, S7): which level to trust for "does this apply today"
DATA_EXPLAIN = {
    "applies_today": "Use each article's `status` and `blocks`: that is today's text and its label, recomputed every night. "
                     "`text.source` says which official consolidation the text comes from.",
    "act.consolidation_valid_from": "The newest consolidation the open data holds for the act (one per act). It can be a "
                                    "future or a past version: it is the source we read, not a statement about today. "
                                    "`version_state_today` says which (current, future, past).",
    "laws_in_force_not_in_text": "Amending acts already in force that this consolidation doesn't include yet. The articles they "
                                 "change are labelled 'Gali būti pasenęs', unless today's text was found in another official "
                                 "consolidation (then the article shows that text, labelled current).",
    "future": "An adopted later wording of an article, from `applies_from`; `changed_parts` lists the parts whose wording "
              "changes (anchors). Empty future with a `future_change` in the status: the change is known from the amending "
              "act, its consolidated text not yet.",
    "annexes": "Shown as published, without a status label.",
}


def _changed_parts(today: list[Block], future: list[Block]) -> list[str]:
    """The parts whose wording differs between today's text and the future one, by anchor ("d102"; added or removed
    ones too): a 100-part definitions article changes in one or two parts, not as a whole (feedback P9)."""
    norm = lambda b: " ".join(display_text(b).split())  # noqa: E731
    a = {b.anchor: norm(b) for b in today if b.anchor}
    f = {b.anchor: norm(b) for b in future if b.anchor}
    order = [b.anchor for b in future if b.anchor] + [b.anchor for b in today if b.anchor and b.anchor not in f]
    return [k for k in dict.fromkeys(order) if a.get(k) != f.get(k)]


# the act being rendered: "[paveikslas N]" in an EU act's text -> its image's path on the site (Renderer.act)
IMAGES: dict[str, str] = {}
EU_ACT = False  # an EU act's formulas are its images, shown (not "see e-tar")


def _blocks(blocks: list[Block], meta: dict, link=None, here: str | None = None, record: bool = False) -> list[dict]:
    """Blocks for a page; with a Linker, also "html": the same text with cross-reference links (pages only).
    `record`: the page's own text, whose references the agents' `related` lists (D-036)."""
    from markupsafe import Markup
    out = [{"kind": b.kind, "text": display_text(b), "anchor": b.anchor, "notes": _refs(b.notes, meta)} for b in blocks]
    if link is not None:
        for x in out:
            x["html"] = link.html(x["text"], here, x["anchor"], record)
    for x in out:  # an EU act's formula or figure where the text has it
        if IMAGES and "[paveikslas " in x["text"]:
            h = str(x.get("html") or htmlmod.escape(x["text"], quote=False))
            x["html"] = Markup(eurlex.IMAGE.sub(lambda m: f'<img src="{IMAGES[m.group(1)]}" alt="Paveikslas {m.group(1)} '
                                                          f'(formulė ar schema)" loading="lazy">' if m.group(1) in IMAGES
                                                else m.group(0), h))
    _table_rows(out)
    return _unique_anchors(out)


def _table_rows(out: list[dict]) -> None:
    """An EU act's table comes as one line a row, its cells joined by " | " (eurlex, converter 4): such lines get
    "cells" (and "cells_html"), and a run of rows with as many cells opens and closes one table. Lithuanian texts
    have no "|"."""
    from markupsafe import Markup
    for x in out:
        if "|" in x["text"]:
            x["cells"] = [c.strip() for c in x["text"].split("|")]
            if x.get("html"):
                x["cells_html"] = [Markup(c.strip()) for c in str(x["html"]).split("|")]
    for i, x in enumerate(out):
        if x.get("cells"):
            same = lambda y: bool(y and y.get("cells") and len(y["cells"]) == len(x["cells"]))
            x["tbl_open"] = not same(out[i - 1] if i else None)
            x["tbl_close"] = not same(out[i + 1] if i + 1 < len(out) else None)


def _title_case(upper: str) -> str:
    """'LIETUVOS RESPUBLIKOS DARBO KODEKSAS' -> 'Lietuvos Respublikos darbo kodeksas'."""
    s = upper.lower().capitalize()
    return s.replace("lietuvos respublikos", "Lietuvos Respublikos").replace("Lietuvos respublikos", "Lietuvos Respublikos")


SHORT_WORDS = {"IR", "IŠ", "SU", "Į", "AR", "NUO", "DĖL", "PO", "BE", "PER", "KAI", "KUR", "TAI", "JŲ", "JO", "JOS",
               "ARBA", "BEI", "AT", "IKI", "TIK", "NE", "KAIP", "UŽ", "PRIE", "TARP", "APIE", "ANT", "PAS", "VIS"}


PROPER = [("lietuvos respublikos", "Lietuvos Respublikos"), ("lietuvos respublika", "Lietuvos Respublika"),
          ("europos sąjung", "Europos Sąjung"), ("europos bendrij", "Europos Bendrij"), ("lietuvos", "Lietuvos"),
          ("europos", "Europos"), ("konstitucij", "Konstitucij"), ("seimo", "Seimo"), ("vyriausybės", "Vyriausybės"),
          ("vyriausybė", "Vyriausybė"), ("respublikos prezident", "Respublikos Prezident"),
          ("konstitucinis teismas", "Konstitucinis Teismas"), ("konstitucinio teismo", "Konstitucinio Teismo"),
          ("europos komisij", "Europos Komisij"), ("seimas", "Seimas")]


def long_acronyms(texts) -> set[str]:
    """Words of 5-8 capitals an act writes inside its ordinary sentences (ENISA, ENTSO, SCADA, LITGRID): kept in capitals
    in its all-caps headings. Not from text mostly in capitals (a quoted heading), nor within „…“ (a sign's words,
    "„PAVOJUS“"), nor Roman numerals."""
    out = set()
    for t in texts:
        t = re.sub(r"„[^“]*“", " ", t)
        letters = [c for c in t if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) <= 0.3:
            out |= {w for w in re.findall(r"\b[A-ZĄČĘĖĮŠŲŪŽ]{5,8}\b", t) if not re.fullmatch(r"[IVXLCDM]+", w)}
    return out


def sentence_case(t: str, acronyms: set[str] | None = None) -> str:
    """'III SKYRIUS PVM TARIFAI'-style titles -> 'PVM tarifai'; mixed-case titles are kept.

    All-caps words of 2-4 letters that aren't common short words are taken as acronyms
    (PVM, ES, EB, VMI) and kept upper-case.
    """
    if not t:
        return t
    def odd(w: str) -> bool:  # small-caps residue ("teritoriJOS") or a long all-caps word
        core = "".join(c for c in w if c.isalpha())
        return (any(c.isupper() for c in core[1:]) and not core.isupper()) or (len(core) >= 5 and core.isupper())
    # small-caps residue the source left as a lowercase start ("viešosios informacijos … Reikalavimai", VIĮ)
    lower_start = t[0].islower() and any(w[:1].isupper() for w in t.split(" ")[1:])
    if not lower_start and not any(odd(w) for w in t.split(" ")):
        return t  # a normal title: keep it exactly
    t = t.upper()
    words = t.split(" ")
    out = []
    for i, w in enumerate(words):
        core = w.strip(",.;:()–-")
        if core.isalpha() and ((2 <= len(core) <= 4 and core not in SHORT_WORDS and (acronyms is None or core in acronyms))
                               or (acronyms is not None and len(core) > 4 and core in acronyms)):  # ENISA, ENTSO
            out.append(w)
        else:
            out.append(w.lower())
    s = " ".join(out)
    for low, proper in sorted(PROPER, key=lambda x: -len(x[0])):
        s = s.replace(low, proper)
    # a capital after a full stop, but not after abbreviations ("2020 m. sausio 1 d. nuostatos")
    s = re.sub(r"(?<!\bm)(?<!\bd)(?<!\bnr)(?<!\bstr)(?<!\bp)([.!?] )([a-ząčęėįšųūž])",
               lambda m: m.group(1) + m.group(2).upper(), s)
    return s[:1].upper() + s[1:]


def _word_diff(a: str, b: str) -> str:
    """HTML of b relative to a: removed words in <del>, added in <ins> (escaped)."""
    wa, wb = a.split(), b.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(htmlmod.escape(" ".join(wa[i1:i2])))
        else:
            if i2 > i1:
                out.append("<del>" + htmlmod.escape(" ".join(wa[i1:i2])) + "</del>")
            if j2 > j1:
                out.append("<ins>" + htmlmod.escape(" ".join(wb[j1:j2])) + "</ins>")
    return " ".join(out)


def _changes(today: list[Block], future: list[Block]) -> list[dict]:
    """Changed paragraphs between two versions of one article (aligned by paragraph text)."""
    return text_changes([display_text(b) for b in today], [display_text(b) for b in future])  # "641." = "64¹." (P8)


def text_changes(ta: list[str], fb: list[str]) -> list[dict]:
    """The same for paragraphs as plain strings (the dated pages' "Kas pakeista", bin/export_history.py)."""
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, fb, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        old_t, new_t = " ".join(ta[i1:i2]), " ".join(fb[j1:j2])
        out.append({"html": _word_diff(old_t, new_t), "kind": "pakeista" if old_t and new_t else ("išbraukta" if old_t else "nauja")})
    return out


CHANGES_DAYS = 14  # how far back the pages of what changed go; the Atom feeds keep more
SCOPE_DIR = pathlib.Path(__file__).resolve().parents[2] / "scope"
# names people use for an act besides its abbreviation (GDPR for BDAR): search, the API and MCP find it by them
ACT_NAMES: dict[str, list[str]] = yaml.safe_load((SCOPE_DIR / "names.yaml").read_text())["names"]
RESERVED_PATHS = {"api", "ta", "es", "mcp", "apie", "paieska", "sritis", "vert", "skills", "kaip-buvo"}


def short_names(a: dict, acts: list[dict]) -> dict:
    """{"short": ["gdpr"]}: the names that can be an address too, for the act's index row (bin/cf_redirects.py)."""
    names = {slug(n) for n in a.get("names") or [] if " " not in n and n.isascii()}
    taken = {x["alias"].rstrip("/").rsplit("/", 1)[-1] for x in acts} | RESERVED_PATHS
    return {"short": sorted(names - taken)} if names - taken else {}


def version_words(start: str | None, end: str | None = None) -> str:
    """"nuo 2024-01-01 iki 2025-01-01"; nothing for an act with no consolidation date ("nuo None" on 8,000 pages until 2026-11-05)."""
    return f"nuo {start}" + (f" iki {end}" if end else "") if start else ""


def _today_source(tt) -> str:
    """Where today's text comes from, for the source line (today.TodayText)."""
    if tt.origin == "new wording":  # B47: the amending act's own text; no consolidation of it yet
        nr = tt.ref.rsplit("/", 1)  # a joint order's number has slashes too: "1-348/D1-1014/3-742/2010-12-22"
        return (f"{tt.issuer or 'Vyriausybės'} {source.lt_date(nr[1])} {tt.kind_gen or 'nutarimo'} Nr. {nr[0]} nauja redakcija, taikoma nuo {tt.version_from}"
                " (oficialus tekstas; suvestinė redakcija atviruose duomenyse dar neparengta)") if len(nr) == 2 else \
               f"{tt.ref} nauja redakcija, taikoma nuo {tt.version_from}"
    return (f"Seimo kanceliarijos suvestinė redakcija nuo {tt.version_from}" + (f" iki {tt.version_to}" if tt.version_to else "")
            + (" (atvirų duomenų suvestinių archyvas)" if tt.origin == "Suvestine" else " (mūsų archyvas)"))


def list_title(a: Article) -> str:
    """The title in lists (contents, navigation, search): a point has none, so its first words."""
    if a.title:
        return a.title
    # the opening text, and when it ends in a colon its list too ("… pripažįstama: 1) …; 2) …"): a snippet that stops
    # at "pripažįstama:" says nothing (CK 3.88 in Google, 2026-10-28)
    first = ""
    for b in a.blocks:
        if b.kind not in ("part", "para", "point", "sub") or not b.text:
            continue
        t = re.sub(r"^\d+(-\d+)?\.\s*", "", b.text) if not first else b.text
        first = f"{first} {t}".strip()
        if not first.endswith(":") or len(first) > 160:
            break
    return first if len(first) <= 90 else first[:88].rsplit(" ", 1)[0] + "…"


def act_description(info, u: dict) -> str:
    """An act's contents page in search results. People search "… įstatymas aktuali redakcija" and the act's name
    (Search Console, 2026-10-28): say that this is today's text, article by article, and what each page adds."""
    s = (f"{info.name}{info.paren}: aktuali, šiandien galiojanti redakcija {u['ins_pl']}. Prie kiekvieno – ar galioja "
         f"šiandien, būsimi pakeitimai ir nuoroda į e-tar.lt.")
    return s if len(s) <= 160 else f"{info.name}{info.paren}: aktuali redakcija {u['ins_pl']}, su galiojimo žymomis ir nuoroda į e-tar.lt."


def _description(a: Article, lead: str = "") -> str:
    """The search snippet. With `lead` ("DK 52 str. · Galioja šiandien") the status comes first and the title (already
    the page's <title>) is left out: a reader sees in the results whether the text applies."""
    # the opening text, and when it ends in a colon its list too ("… pripažįstama: 1) …; 2) …"): a snippet that stops
    # at "pripažįstama:" says nothing (CK 3.88 in Google, 2026-10-28)
    first = ""
    for b in a.blocks:
        if b.kind not in ("part", "para", "point", "sub") or not b.text:
            continue
        t = re.sub(r"^\d+(-\d+)?\.\s*", "", b.text) if not first else b.text
        first = f"{first} {t}".strip()
        if not first.endswith(":") or len(first) > 160:
            break
    if lead:
        s = f"{lead} · {first or a.title or ''}".rstrip(" ·")
    else:
        s = f"{a.title}. {first}" if first and a.title else first or a.title  # a point has no title
    return s if len(s) <= 155 else s[:152].rsplit(" ", 1)[0] + "…"


def _annex_description(heading: str, x: Article) -> str:
    """An annex's search snippet: which act's annex, its name, and the opening of its text. The name alone was often a
    heading in capitals ("ĮGYVENDINAMI EUROPOS SĄJUNGOS TEISĖS AKTAI"), the snippet Bing called too short (2026-11-21)."""
    title = (x.title or "").strip()
    if title.isupper():  # a heading in capitals says the same as the text below it: the text it is
        title = ""
    text = ""
    for b in x.blocks:
        t = re.sub(r"[□☐■]\s*(?:\[\s*\])?\s*", "", b.text or "").strip()  # form tick boxes ("□[] Pirminė paraiška")
        if not t or t.isupper() or t == title:
            continue
        text = f"{text} {t}".strip()
        if len(text) > 160:
            break
    s = " · ".join(p for p in (heading, title.rstrip("."), text) if p)
    return s if len(s) <= 155 else s[:152].rsplit(" ", 1)[0] + "…"


FAVICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#1f5fa8"/>'
               '<path d="M16 18h32M16 29h32M16 40h22M16 51h14" stroke="#fff" stroke-width="6" stroke-linecap="round"/></svg>')


def _favicon_ico() -> bytes:
    """The same mark as a 32×32 ICO (a PNG inside), for browsers and crawlers that ask for /favicon.ico."""
    import struct
    import zlib
    n, blue, white = 32, (31, 95, 168, 255), (255, 255, 255, 255)
    lines = [(8, 9, 24), (8, 14, 24), (8, 19, 19), (8, 24, 15)]  # (x0, y, x1) at 32 px: the SVG's lines halved
    px = []
    for y in range(n):
        row = []
        for x in range(n):
            corner = min(x, n - 1 - x) < 6 and min(y, n - 1 - y) < 6 and \
                (min(x, n - 1 - x) - 6) ** 2 + (min(y, n - 1 - y) - 6) ** 2 > 36
            on = any(x0 <= x <= x1 and abs(y - ly) <= 1 for x0, ly, x1 in lines)
            row.append((0, 0, 0, 0) if corner else white if on else blue)
        px.append(row)
    raw = b"".join(b"\x00" + bytes(c for p in row for c in p) for row in px)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)  # noqa: E731
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", n, n, 0, 0, 1, 32, len(png), 22) + png


def _icon_png(n: int = 512) -> bytes:
    """FAVICON_SVG's mark as an n×n PNG (for the MCP registry's icon and apps that want a bitmap; 2026-11-09): the
    SVG's geometry on a 64-unit grid, 4×4 samples a pixel, standard library only."""
    import struct
    import zlib
    segs = [(16, 18, 48), (16, 29, 48), (16, 40, 38), (16, 51, 30)]  # (x0, y, x1); stroke 6, round caps

    def inside_rect(x: float, y: float) -> bool:  # 64×64, corner radius 12
        cx, cy = min(max(x, 12), 52), min(max(y, 12), 52)
        return (x - cx) ** 2 + (y - cy) ** 2 <= 144 and 0 <= x <= 64 and 0 <= y <= 64

    def on_line(x: float, y: float) -> bool:
        return any((x - min(max(x, x0), x1)) ** 2 + (y - ly) ** 2 <= 9 for x0, ly, x1 in segs)
    s, raw = 4, bytearray()
    for py in range(n):
        raw.append(0)
        for px in range(n):
            cover = white = 0
            for i in range(s):
                for j in range(s):
                    x, y = (px + (i + 0.5) / s) * 64 / n, (py + (j + 0.5) / s) * 64 / n
                    if inside_rect(x, y):
                        cover += 1
                        white += on_line(x, y)
            k = s * s
            if not cover:
                raw += b"\x00\x00\x00\x00"
                continue
            w = white / cover  # share of white within the shape; alpha from the rounded corners
            raw += bytes([round(31 + (255 - 31) * w), round(95 + (255 - 95) * w), round(168 + (255 - 168) * w), round(255 * cover / k)])
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


class Site:
    def __init__(self, out: pathlib.Path, base_url: str, day: str, indexable: bool, laws: Laws):
        self.out, self.base, self.day, self.indexable, self.laws = out, base_url.rstrip("/"), day, indexable, laws
        self.watermark = source.register_watermark()  # the open data's newest TAR publication (A19)
        if laws is not None:
            LAW_DOCS.update({k: v["dokumento_id"] for k, v in laws.meta.items() if v.get("dokumento_id")})
            if (source.DATA / "seimas").exists():  # the adoption vote next to an amending law in the notes (D-054 step 2)
                ADOPTED.update(seimas.adopted_votes(source.DATA / "seimas", laws.meta))
        self.built = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        self.sitemap: list[str] = []
        self.refs: list[tuple[str, str]] = []  # (from URL, to URL): links between articles and from decisions (D-036)
        self.decision_info: dict[str, dict] = {}
        self.eu_on_site: dict[str, str] = {}  # CELEX -> this site's page of an EU act in the scope: links go there, not EUR-Lex
        self.eu_implemented_by: dict[str, list[dict]] = {}  # CELEX -> the Lithuanian acts whose annex lists it (D-037)  # a regulator decision's page URL -> its number, date, title, label
        self.soft_warnings: list[str] = []  # problems the nightly reports without failing (decision pages, D-034)
        self.def_rows: list[dict] = []  # every definition made by an article shown today (definitions.definitions_in)
        self.def_refs: list[dict] = []
        self.concepts: list[dict] = []  # defined terms, what they narrow, where they are used (definitions.concepts)  # sentences that say where an act's terms are defined (definitions.References)
        self.acts_meta: list[dict] = []  # number, adoption date, issuer, URL of every act in scope (links from decisions)
        self.redirects: list[str] = []
        self.acts_index: list[dict] = []
        self.nav_acts: dict[str, dict] = {}  # abbr -> the act's sidebar entry (see prepare())
        # the sidebar lists the areas, not every act: 897 acts on each page were 90 % of its bytes (2026-11-03), and
        # one added act changed every page of the site
        self.nav_areas: list[dict] = []
        self.search_items: list[list] = []  # [act index, label, title, url, pretty] for /search-index.json
        self.search_stems: list[set] = []   # the words of each item's page, for full-text search (fulltext.py)
        self.search_acts: list[list] = []   # [abbr, name]
        self.act_index = -1
        self.aliases: dict[str, str] = {}
        self.alias_of: dict[str, str] = {}   # abbr -> short alias, for index.json / llms.txt
        self.upcoming: list[dict] = []       # articles whose label changes on a coming date
        self.ledger_today: dict = {}         # abbr -> label -> (state shown, text fingerprint) (ledger.py)
        self.sources_today: dict = {}        # abbr -> where the shown texts came from, for the feeds' wording (feeds.py)
        self.ledger_totals: dict | None = None
        lm = source.STATE / "lastmod.json"   # url -> [content hash, date it last changed]
        self.lastmod: dict[str, list[str]] = json.loads(lm.read_text()) if lm.exists() else {}

    def prepare(self, scope_acts: list[dict]) -> None:
        """Read each act's TAR code first: links between acts, and the sidebar's entry for each."""
        import yaml
        targets = []
        abbrs = {sa["abbr"] for sa in scope_acts}
        self.nav_areas = [{"name": g["name"], "url": f"{self.base}/sritis/{g['slug']}/", "slug": g["slug"]}
                          for g in (yaml.safe_load(AREAS.read_text())["areas"] if AREAS.exists() else [])
                          if g.get("slug") and abbrs & set(g["acts"])]
        for sa in scope_acts:
            row = source.latest_snapshot(sa["dokumento_id"])["row"]
            if eurlex.is_eu(sa["dokumento_id"]):
                self.eu_on_site[eurlex.celex_of(sa["dokumento_id"])] = f"{self.base}/{source.act_path(sa, row['tar_kodas'])}"
            self.nav_acts[sa["abbr"]] = {"abbr": sa["abbr"], "tag": "" if sa.get("no_abbr") else sa["abbr"], "name": sa["name"],
                                         "url": f"{self.base}/{source.act_path(sa, row['tar_kodas'])}"}
            self.acts_meta.append({"number": sa.get("number"), "adopted": sa.get("adopted"), "issuer": sa.get("issuer"),
                                   "url": f"{self.base}/{source.act_path(sa, row['tar_kodas'])}"})
            try:  # article numbers of every act, for links from other acts (xref.Others)
                labels = {x.label for x in parse(source.act_text(sa["dokumento_id"])[0], sa.get("document")).main.articles}
            except Exception:  # noqa: BLE001  the act's own build reports problems
                continue
            targets.append({"genitive": sa.get("genitive"), "url": f"{self.base}/{source.act_path(sa, row['tar_kodas'])}",
                            "seg": "p" if sa.get("unit") == "punktas" else "str", "labels": labels,
                            **({"eu_names": eurlex.cited_names(sa)} if eurlex.is_eu(sa["dokumento_id"]) else {})})
        self.others = Others(targets)
        # every act by its name, for "sąvokos suprantamos taip, kaip jos apibrėžtos … įstatyme" (feedback P10)
        self.references = definitions.References([
            {"genitive": sa.get("genitive"), "act": act_key_of(sa), "name": sa["name"],
             "url": f"{self.base}/{source.act_path(sa, source.latest_snapshot(sa['dokumento_id'])['row']['tar_kodas'])}"}
            for sa in scope_acts if sa.get("genitive")])

    def nav(self, here: str, abbr: str | None = None, **extra) -> dict:
        me = self.nav_acts.get(abbr) if abbr else None
        tag = me["tag"] if me else abbr
        return {"here": here, "act": me, "areas": self.nav_areas, "act_abbr": abbr, "act_tag": tag, "arts": None, "path": [], "contents": None,
                "more_before": False, "more_after": False, **extra}

    def write(self, path: str, html: str) -> None:
        p = self.out / path.strip("/") / "index.html" if not path.endswith((".json", ".xml", ".txt", ".js", ".html", ".ico", ".svg", ".png", ".md")) and \
            not path.endswith(("_redirects", "_headers")) else self.out / path.strip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(html) if isinstance(html, bytes) else p.write_text(html)

    def page(self, tpl: str, path: str, **ctx) -> None:
        ctx.setdefault("nav", self.nav("other"))
        canonical = self.base + path
        fetched = ctx.get("fetched")
        stale = fetched if fetched and (dt.date.fromisoformat(self.day) - dt.date.fromisoformat(fetched)).days > STALE_DAYS else None
        wm = self.watermark
        lag = working_days_between(wm, self.day) if wm and not ctx.get("eu") else None
        html = env.get_template(tpl).render(root=self.base, canonical=canonical, indexable=self.indexable,
                                            day=self.day, stale=stale, watermark=wm,
                                            register_lag=wm if lag is not None and lag > REGISTER_LAG_DAYS else None, **ctx)
        self.write(path, html)
        # sitemap lastmod = the day the page last changed, ignoring dates that move every day
        h = hashlib.sha1(html.replace(self.day, "").replace(fetched or "\0", "").replace(wm or "\0", "").encode()).hexdigest()[:16]
        old = self.lastmod.get(path)
        if not old or old[0] != h:
            self.lastmod[path] = [h, self.day]
        self.sitemap.append(canonical)  # always produced; robots.txt + noindex decide indexing

    def changes_pages(self, events: list[dict], built: list[dict], areas: list[dict]) -> None:
        """/pakeitimai/ and each area's: what changed, for people (the Atom feeds hold the same for readers). After the
        night's events are known, so bin/nightly.py calls it after finish(); finish() has put the addresses in the sitemap."""
        acts = {b["abbr"]: {"name": f"{b['tag']} – {b['name']}" if b.get("tag") else b["name"], "url": b["url"]} for b in built}
        groups = [g for g in areas if g.get("slug")]
        self.page("changes.html", "/pakeitimai/", page_title="Kas pasikeitė Lietuvos teisės aktuose – Atviri teisės aktai", jsonld=None, nav=self.nav("changes"),
                  description="Naujausi Lietuvos ir ES teisės aktų pakeitimai šioje svetainėje: nauji tekstai ir pasikeitusios žymos, pagal dienas ir sritis.",
                  group=None, days=CHANGES_DAYS, areas=groups, atom=f"{self.base}/atom.xml",
                  digest=feeds.digest(events, self.base, self.day, acts, CHANGES_DAYS))
        for g in groups:
            self.page("changes.html", f"/sritis/{g['slug']}/pakeitimai/", page_title=f"{g['name']}: kas pasikeitė – Atviri teisės aktai", jsonld=None, nav=self.nav("changes"),
                      description=f"{g['name']}: naujausi teisės aktų pakeitimai, nauji tekstai ir pasikeitusios žymos, pagal dienas.",
                      group=g, days=CHANGES_DAYS, areas=groups, atom=f"{self.base}/sritis/{g['slug']}/atom.xml",
                      digest=feeds.digest(events, self.base, self.day, acts, CHANGES_DAYS, set(g["acts"])))

    def checkpoint(self) -> dict:
        """State before building one act, so a rejected build can be undone (bin/nightly.py)."""
        return {"sitemap": len(self.sitemap), "redirects": len(self.redirects), "items": len(self.search_items),
                "acts": len(self.search_acts), "aliases": dict(self.aliases), "alias_of": dict(self.alias_of),
                "upcoming": len(self.upcoming), "refs": len(self.refs),
                "lastmod": {k: list(v) for k, v in self.lastmod.items()}}

    def rollback(self, cp: dict, act_dir: pathlib.Path | None) -> None:
        del self.sitemap[cp["sitemap"]:], self.redirects[cp["redirects"]:]
        del self.search_items[cp["items"]:], self.search_acts[cp["acts"]:], self.upcoming[cp["upcoming"]:]
        del self.search_stems[cp["items"]:], self.refs[cp["refs"]:]
        self.aliases, self.alias_of, self.lastmod = cp["aliases"], cp["alias_of"], cp["lastmod"]
        if act_dir and act_dir.exists():
            import shutil
            shutil.rmtree(act_dir)

    def label(self, state: str, applies_from: str | None) -> str:
        if state == "pending" and getattr(self, "eu_act", False):  # an EU act in force, this article applies later (D-037)
            return f"Taikomas nuo {applies_from}"
        return STATE_LABEL[state].format(applies_from or "").strip()

    # -------------------------------------------------------------------------------------
    def act(self, scope_act: dict) -> dict:
        snap = source.latest_snapshot(scope_act["dokumento_id"])
        row = snap["row"]
        fetched = (source.last_checked(scope_act["dokumento_id"]) or snap["fetched"])[:10]  # last check, not last change
        if scope_act["dokumento_id"] in source.PINNED:  # nightly fallback: the text is that older snapshot's
            fetched = snap["fetched"][:10]
        # [abbreviation typed to narrow ("" if none in use: a coined one could be an ordinary word), name, unit, cited as]
        self.search_acts.append(["" if scope_act.get("no_abbr") else scope_act["abbr"], scope_act["name"],
                                 UNITS[scope_act.get("unit", "straipsnis")]["short"], cite_of(scope_act)])
        self.act_index = len(self.search_acts) - 1
        text, origin = source.act_text(scope_act["dokumento_id"])
        srcs = self.sources_today[scope_act["abbr"]] = {
            "text": hashlib.sha1(text.encode()).hexdigest()[:12], "today": {},
            "eu_version": (row.get("eu_version") or row.get("tar_kodas")) if eurlex.is_eu(scope_act["dokumento_id"]) else None}
        act = parse(text, scope_act.get("document"))
        srcs["from"] = act.version_from
        act.prepared = origin.get("prepared")
        st = assess(act, scope_act, self.laws, self.day, source.first_seen(scope_act["dokumento_id"], act.version_from))
        self.eu_act = eurlex.is_eu(scope_act["dokumento_id"])
        if self.eu_act:  # from when each article applies: the act's final article (D-037)
            stages, notices = eurlex.application(act, self.day)
            for lab, (kind, when, note) in stages.items():
                s = st.articles.get(lab)
                if s is None or s.state == "repealed":
                    continue
                if kind == "pending":
                    s.state, s.applies_from, s.changes_on, s.reasons = "pending", when, when, [note]
                else:
                    s.part_pending, s.note = when, note
            st.notices += notices
            if scope_act.get("kind") == "Direktyva":
                st.notices.append("Tai direktyva: ji įpareigoja valstybes nares, o asmenims taikomi ją į nacionalinę teisę "
                                  "perkeliantys teisės aktai (Lietuvoje – žr. aktus, kurie ją įgyvendina).")
        if not eurlex.is_eu(scope_act["dokumento_id"]) and sum(EQUATION_ONLY.fullmatch(b.text.strip()) is not None
                                                               for x in act.main.articles for b in x.blocks) >= 3:
            st.notices.append(FORMULAS_NOTICE)
        not_yet, register_bad = apply_register_state(st, row, self.day, scope_act)
        meta = self.laws.meta
        # "Įstatymo „Dėl užsieniečių teisinės padėties“": the genitive is lower case (it is matched in titles)
        gen_cap = re.sub(r"„(\w)", lambda m: "„" + m.group(1).upper(), scope_act["genitive"][:1].upper() + scope_act["genitive"][1:])
        is_eu = eurlex.is_eu(scope_act["dokumento_id"])
        info = ActInfo(scope_act["abbr"], scope_act["name"], gen_cap,
                       scope_act["number"], row["tar_kodas"], row["dokumento_id"],
                       eurlex.eurlex_url(row.get("eu_version") or row["tar_kodas"]) if is_eu else ETAR_ACT.format(row["dokumento_id"]),
                       re.sub(r"\s*\(?Tekstas svarbus EEE\.?\s*\)?\s*$", "", " ".join(row["pavadinimas"].split())) if is_eu else
                       "Lietuvos Respublikos " + (scope_act["name"] if scope_act["name"] == "Konstitucija" else scope_act["name"][:1].lower() + scope_act["name"][1:]),
                       dict(UNITS[scope_act.get("unit", "straipsnis")],
                            **({"amender": "įsakymas"} if scope_act.get("kind") == "Įsakymas" else {})))
        info.tag, info.cite = ("" if scope_act.get("no_abbr") else info.abbr), cite_of(scope_act)
        info.paren = f" ({info.tag})" if info.tag else ""
        if is_eu:  # D-037
            info.official_site, info.eu = "EUR-Lex", True
            info.number = f"{scope_act.get('kind') or 'Reglamentas'} {scope_act['number']}"  # "Reglamentas (ES) 2016/679"
            info.consolidation = "ES Leidinių biuro konsoliduota redakcija" if row.get("eu_version") else "Oficialiajame leidinyje paskelbtas tekstas"
        elif not act.version_from:  # never consolidated: the open data hold the act as adopted
            info.consolidation = "Priimtas teisės akto tekstas (suvestinės redakcijos atviruose duomenyse nėra)"
        # the Constitution was adopted by referendum (1992): no single body to name
        passed_by = None if info.abbr == "Konstitucija" else \
            (scope_act.get("issuer_nom") or "Lietuvos Respublikos Vyriausybė") if scope_act.get("adopted") else "Lietuvos Respublikos Seimas"
        if is_eu:
            passed_by = eurlex.adopted_by(row["pavadinimas"])
        elif scope_act.get("adopted"):  # rules approved by a Government resolution or a minister's order (D-033)
            ins = "įsakymu" if scope_act.get("kind") == "Įsakymas" else "nutarimu"
            info.full_title = (f"{scope_act['name']}, {approved_by(scope_act['name'])} {scope_act.get('issuer') or 'Lietuvos Respublikos Vyriausybės'} "
                               f"{source.lt_date(scope_act['adopted'])} {ins} Nr. {scope_act['number']}")
        u = info.u
        base_path = "/" + source.act_path(scope_act, info.tar)
        global EU_ACT
        EU_ACT = is_eu
        IMAGES.clear()  # an EU act's images (formulas, figures: "[paveikslas N]" in its text) as files beside its pages
        for n, uri in (row.get("eu_images") or {}).items():
            if m := re.match(r"data:image/(\w+);base64,(.*)", uri, re.S):
                ext = {"jpeg": "jpg"}.get(m.group(1), m.group(1))
                f = self.out / base_path.strip("/") / "img" / f"{n}.{ext}"
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(base64.b64decode(m.group(2)))
                IMAGES[n] = f"{base_path.rstrip('/')}/img/{n}.{ext}"
        version = version_words(act.version_from, act.version_to)
        common = dict(act=info, act_url=self.base + base_path, version=version, version_from=act.version_from or "", fetched=fetched, eu=is_eu)
        arts = act.main.articles
        # acronyms are the words this act itself writes in capitals in its text (PVM, ES, VMI)
        acr = {w for x in arts for b in x.blocks for w in re.findall(r"\b[A-ZĄČĘĖĮŠŲŪŽ]{2,4}\b", b.text)}
        acr |= long_acronyms(b.text for x in arts for b in x.blocks)
        sc = lambda t: sentence_case(t, acr)  # noqa: E731
        url = {a.label: f"{base_path}{u['seg']}/{a.label}/" for a in arts}
        # cross-reference links within this act: every article (point) and the anchors its page can carry
        link = Linker(self.base + base_path, u["seg"], {}, points=u["seg"] == "p",  # anchors: after today_map below
                      others=getattr(self, "others", None), sink=self.refs, eu=eurlex.is_eu(scope_act["dokumento_id"]))

        # today's text from older consolidations (Suvestine): the register's only (D-037)
        today_map = {} if is_eu else find_today(act, st, scope_act["dokumento_id"], scope_act, self.laws, self.day)
        # the anchors each page will carry: today's recovered text where there is one, else the stored text
        link.anchors.update({a.label: {b.anchor for b in (today_map[a.label].article if a.label in today_map
                                                           else a.variant_on(self.day)).blocks if b.anchor} for a in arts})
        today_only = [] if is_eu else find_today_only(act, scope_act["dokumento_id"], scope_act, self.laws, self.day)
        if register_bad or not_yet:
            today_map, today_only = {}, []
        title_now = {k: list_title(v.article) for k, v in today_map.items() if st.articles[k].state != "repealed"}
        eu_impl = eu.implemented(act)
        eu_list = [{"celex": x.ref.celex if x.ref else None, "short": x.ref.short if x.ref else None,
                    "url": self.eu_on_site.get(x.ref.celex, x.ref.url) if x.ref else None, "kind": x.ref.kind if x.ref else None,
                    "entry": x.entry}
                   for x in eu_impl]
        eu_link = self.base + base_path + "#es"
        for x in eu_list:  # which Lithuanian acts transpose an EU act: shown on that act's page (D-037)
            if x["celex"]:
                mine = self.eu_implemented_by.setdefault(x["celex"], [])
                if not any(y["url"] == self.base + base_path for y in mine):
                    mine.append({"cite": info.cite, "name": info.name, "url": self.base + base_path})

        # sidebar: the articles of the same lowest heading (chapter/section), windowed if long
        group_of: dict[str, list[int]] = {}
        start = 0
        for j in range(1, len(arts) + 1):
            if j == len(arts) or (arts[j].path[-1] if arts[j].path else None) is not (arts[start].path[-1] if arts[start].path else None):
                for k in range(start, j):
                    group_of[arts[k].label] = list(range(start, j))
                start = j
        WINDOW = 30

        def side_nav(i: int) -> dict:
            g = group_of[arts[i].label]
            pos = g.index(i)
            lo, hi = max(0, pos - WINDOW), min(len(g), pos + WINDOW + 1)
            items = []
            for k in g[lo:hi]:
                x = arts[k]
                sx = st.articles[x.label]
                items.append({"pretty": x.num.pretty(), "title": title_now.get(x.label, list_title(x)), "url": self.base + url[x.label],
                              "current": k == i,
                              "state": "current" if x.label in today_map and sx.state != "repealed" else sx.state,
                              "state_label": self.label(sx.state, sx.applies_from)})
            path = [f"{h.num} {h.kind}" + (f" – {sc(h.title)}" if h.title else "") for h in arts[i].path]
            if sum(len(b.text) for b in arts[i].blocks) > 60000:  # a very long article: keep the page small
                items = [x for x in items if x["current"]]
            return self.nav("article", info.abbr, arts=items, path=path, contents=self.base + base_path,
                            more_before=lo > 0, more_after=hi < len(g))

        art_json: list[dict] = []
        from .ledger import fingerprint
        led = self.ledger_today[info.abbr] = {}
        # defined terms ("Pagrindinės … sąvokos"): listed below each article that uses them (definitions.py)
        finder = definitions.Finder(definitions.terms_of(arts), {a.label: _plain(a) for a in arts})
        act_key = act_key_of(scope_act)  # = alias below
        assert act_key == (scope_act.get("slug") or (slug("-".join(info.name.split())) if not info.tag else slug(info.abbr)))
        own_url = self.base + base_path
        ref_aliases = self.references.aliases(b.text for a in arts for b in a.blocks[:3])
        self.terms_total = getattr(self, "terms_total", 0) + len(finder.terms)
        used: dict[str, list[str]] = {}  # a defined term's URL -> the articles that use it (the concept graph, S11)
        for i, a in enumerate(arts):
            s = st.articles[a.label]
            tt = today_map.get(a.label) if s.state != "repealed" else None
            stored_shown = a.variant_on(self.day)
            shown = tt.article if tt else stored_shown
            shown_state = "current" if tt else s.state
            future = None
            if tt and s.state == "pending":
                ch = _changes(tt.article.blocks, stored_shown.blocks)
                size = sum(len(b.text) for b in tt.article.blocks + stored_shown.blocks)
                future_repeal = _article_repealed(stored_shown)[0]
                sm = difflib.SequenceMatcher(None, " ".join(display_text(b) for b in tt.article.blocks).split(),
                                             " ".join(display_text(b) for b in stored_shown.blocks).split(), autojunk=False)
                other_article = (not future_repeal and sm.real_quick_ratio() < 0.3 or not future_repeal and sm.ratio() < 0.3) \
                    and (tt.article.title or "").lower() != (stored_shown.title or "").lower()
                future = {"applies_from": s.applies_from, "changes_on": s.changes_on, "changes": [] if other_article else ch,
                          "blocks": _blocks(stored_shown.blocks, meta) if size < 25000 or other_article else None,
                          "title": stored_shown.title, "other_article": other_article, "repealed": future_repeal}
            if tt:
                today_src = _today_source(tt)
            # the stored text's other wordings; not when today's text is a new wording (B47): the stored one is then
            # simply the old text, not a wording "in this text" (its history is on the dated pages)
            others = [] if tt and tt.origin == "new wording" else [v for v in [a, *a.variants] if v is not shown]
            label = self.label(shown_state, s.applies_from)
            gone, gone_on = _article_repealed(shown)
            repeal_on = gone_on if gone and gone_on and gone_on > self.day and shown_state == "pending" else None
            if repeal_on:
                label = f"Netenka galios {repeal_on}"
            text_from, text_to = (tt.version_from, tt.version_to) if tt else (act.version_from, act.version_to)
            path_titles = [f"{h.num if h.kind != 'dalis' or h.num[:1].isupper() else h.num.capitalize()} "
                           f"{h.kind}{(' ' + sc(h.title)) if h.title else ''}" for h in a.path]
            title = f"{info.cite} {unit_name(u, a.num.pretty(), shown.title)} | {info.name}"
            # JSON-LD describes the text shown on the page: its consolidation date and legal force today
            ld = {"@context": "https://schema.org", "@type": "Legislation",
                  "name": f"{info.cite} {unit_name(u, a.num.pretty(), shown.title)}",
                  "legislationIdentifier": f"{info.number} {a.label} {u['short']}", "inLanguage": "lt",
                  "legislationJurisdiction": "EU" if is_eu else "LT", "url": self.base + url[a.label], "isBasedOn": info.etar_url,
                  "license": DATA_LICENSE, "legislationDateVersion": text_from,
                  "isPartOf": {"@type": "Legislation", "name": info.name, "legislationIdentifier": info.number,
                               "sameAs": info.etar_url}}
            if passed_by:  # who adopted the act (not who publishes this page: that is us, unofficially)
                ld["legislationPassedBy"] = {"@type": "GovernmentOrganization", "name": passed_by}
            force = {"current": "InForce", "pending": "NotInForce", "repealed": "NotInForce"}.get(shown_state)
            if force:
                ld["legislationLegalForce"] = f"https://schema.org/{force}"
            if repeal_on:
                ld.pop("legislationLegalForce", None)  # in force until repeal_on, but its text isn't shown here
            elif shown_state == "pending":
                ld["temporalCoverage"] = f"{s.applies_from}/.."
            note = ("" if tt or st.version_state == "current" or s.state != "current" else
                    f"vėlesnių šio {u['gen']} pakeitimų ši redakcija neapima" if st.version_state == "future"
                    else f"vėlesnių šio {u['gen']} pakeitimų neaptikta")
            ver = f"redakcija, galiojanti {self.day}" if shown_state == "current" else \
                f"redakcija nuo {act.version_from}" if act.version_from else "priimtas tekstas"
            # the next date on which this page's label stops being true (E1: app.js flips it on the day)
            # the first day this page's label stops being true: the first staged change, not the last
            changes_on = ((future["changes_on"] or future["applies_from"]) if shown_state == "current" and future else
                          repeal_on or (s.applies_from if shown_state == "pending" else None))
            if shown_state == "current" and not tt and s.changes_on:  # part dates, expiry, adopted later laws
                changes_on = min(x for x in (changes_on, s.changes_on) if x)
            fchange = (tt.status.future_change if tt and tt.status else None) if tt else s.future_change
            if shown_state == "current" and fchange:
                changes_on = min(x for x in (changes_on, fchange[0]) if x)
            if not changes_on and st.expires and st.expires > self.day:
                changes_on = st.expires
            if changes_on and shown_state == "current":
                ld["temporalCoverage"] = f"../{_day_before(changes_on)}"
            if changes_on:
                self.upcoming.append({"url": self.base + url[a.label], "act": info.abbr, "article": a.num.pretty(),
                                      "on": changes_on, "state_now": shown_state})
            eu_here = [{"short": r.short, "url": self.eu_on_site.get(r.celex, r.url), "celex": r.celex} for r in eu.mentioned(shown)]
            terms_here = [{"term": t.term, "url": self.base + url[t.label] + "#" + t.anchor}
                          for t in finder.found(a.label, _plain(shown)) if t.label in url]
            # sentences that say where this act's terms are defined (feedback P10): on the block, in the index, on the page
            by_ref = {}
            if shown_state != "repealed":
                for b in shown.blocks:
                    for r in self.references.find(b.text, ref_aliases):
                        r["acts"] = [x for x in r["acts"] if x["url"] != own_url]
                        if r["acts"] or r["not_on_site"] or r["also_other_acts"]:
                            by_ref.setdefault(b.anchor, []).append(r)
                            self.def_refs.append({"act": act_key, "cite": info.cite, "act_name": info.name, "label": a.label,
                                                  "number": a.num.pretty(), "anchor": b.anchor,
                                                  "url": self.base + url[a.label] + (f"#{b.anchor}" if b.anchor else ""), **r})
            refs_here = list({x["url"]: x for v in by_ref.values() for r in v for x in r["acts"]}.values())
            for t in terms_here:
                used.setdefault(t["url"], []).append(a.label)
            led[a.label] = (shown_state, fingerprint(shown))
            if tt:  # shown from another version than the stored text: which one (a new one taking over is no correction)
                srcs["today"][a.label] = tt.version_from
            art_json.append({
                "label": a.label, "pretty": a.num.pretty(), "title": shown.title, "url": self.base + url[a.label],
                "path": [{"kind": h.kind, "num": h.num, "title": h.title} for h in a.path],
                "status": {"state": shown_state, "label": label, "day": self.day, "repealed_from": repeal_on,
                           "future_change": {"from": fchange[0], "law": fchange[1], "certain": fchange[2]} if fchange else None,
                           "part_pending_from": None if tt else s.part_pending, "note": None if tt else s.note,
                           "label_valid_until": _day_before(changes_on) if changes_on else None,
                           "reasons": [] if tt else s.reasons,
                           "applies_from": s.applies_from if shown_state in ("pending", "repealed") else None},
                "text": {"consolidation_valid_from": text_from, "consolidation_valid_to": text_to,
                         "source": tt.origin if tt else "Dokumentas"},
                "blocks": [{"kind": x["kind"], "anchor": x["anchor"], "text": x["text"], "notes": x["notes"],
                            **({"defined_by_reference": by_ref[x["anchor"]]} if x["anchor"] in by_ref else {}),
                            **({"images": {n: self.base + IMAGES[n] for n in eurlex.IMAGE.findall(x["text"]) if n in IMAGES}}
                               if "[paveikslas " in x["text"] else {})}
                           for x in _blocks(shown.blocks, meta)],
                "notes": [{"label": n.label, "refs": [{**r.__dict__, **({"vote": ADOPTED[r.nr]} if r.nr in ADOPTED else {})}
                                                       for r in n.refs]} for n in shown.notes],
                "future": {"applies_from": future["applies_from"], "changes_on": future["changes_on"],
                           "different_article": future["other_article"], "repealed": future["repealed"],
                           "title": future["title"], "blocks": [{"kind": b.kind, "anchor": b.anchor, "text": display_text(b)}
                                                                for b in stored_shown.blocks],  # 64¹, as today's (P8)
                           "changed_parts": _changed_parts(shown.blocks, stored_shown.blocks)} if future else None,
                "other_versions": [{"valid_from": v.valid_from, "valid_to": v.valid_to, "blocks": [b.text for b in v.blocks]}
                                   for v in others],
                "eu_mentioned": eu_here, "defined_terms": terms_here})
            cite = f"{info.cite} {unit_name(u, a.num.pretty(), shown.title)} ({info.full_title}, {ver})."
            art_json[-1]["cite"] = cite
            self.search_items.append([self.act_index, a.label, list_title(shown), self.base + url[a.label], a.num.pretty(), label])
            if label != "Neteko galios" and not label.startswith("Neteko galios"):
                for d in definitions.definitions_in(shown):  # the site-wide definitions index (feedback S2)
                    self.def_rows.append({**d, "act": act_key, "cite": info.cite, "act_name": info.name, "label": a.label,
                                          "number": a.num.pretty(), "status": label,
                                          "url": self.base + url[a.label] + (f"#{d['anchor']}" if d["anchor"] else "")})
            self.search_stems.append(fulltext.stems(" ".join([shown.title or ""] + [b.text for b in shown.blocks])))
            crumbs_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Atviri teisės aktai", "item": self.base + "/"},
                {"@type": "ListItem", "position": 2, "name": info.name, "item": self.base + base_path},
                {"@type": "ListItem", "position": 3, "name": f"{a.num.pretty()} {u['nom']}"}]}
            self.page("article.html", url[a.label], page_title=title, source_note=note, jsonld2=ld_json(crumbs_ld),
                      description=_description(shown, f"{info.cite} {a.num.pretty()} {u['short']} · {label}"),
                      cite=cite,
                      nav=side_nav(i), eu_count=len(eu_list), eu_link=eu_link,
                      eu_mentioned=eu_here, defined_terms=terms_here, refs_here=refs_here, jsonld=ld_json(ld), expires=st.expires,
                      art={"pretty": a.num.pretty(), "title": shown.title, "label": a.label}, status=s, status_label=label,
                      today_src=today_src if tt else None, future=future,
                      shown_state=shown_state, repeal_on=repeal_on, changes_on=changes_on,
                      future_change=fchange,
                      crumbs=path_titles, blocks=_blocks(shown.blocks, meta, link, a.label, record=True), art_notes=_refs(shown.notes, meta),
                      section_remarks=[f"{h.num} {h.kind}: {r}" for h in a.path for r in h.remarks],
                      other_variants=[{"period": f"Redakcija {('nuo ' + v.valid_from) if v.valid_from else ''}"
                                                 f"{(' iki ' + v.valid_to) if v.valid_to else ''}".replace("Redakcija  iki", "Redakcija iki"),
                                       "blocks": _blocks(v.blocks, meta, link, a.label)} for v in others]
                                     + [{"period": f"Kitas šio {u['gen']} tekstas, šaltinyje pateiktas be datų",
                                         "blocks": _blocks(v.blocks, meta)} for v in a.duplicates],
                      prev={"pretty": arts[i - 1].num.pretty(), "url": self.base + url[arts[i - 1].label]} if i else None,
                      next={"pretty": arts[i + 1].num.pretty(), "url": self.base + url[arts[i + 1].label]} if i + 1 < len(arts) else None,
                      **common)

        for x in today_only:
            path_u = f"{base_path}{u['seg']}/{x.article.label}/"
            pretty = x.article.num.pretty()
            src_ = _today_source(x)
            st_x = x.status
            x_state = st_x.state
            led[x.article.label] = (x_state, fingerprint(x.article))
            srcs["today"][x.article.label] = x.version_from
            lbl = self.label(x_state, st_x.applies_from)
            # its end: the stored future version's start, or its own known change (one value everywhere)
            x_changes = min([d for d in (act.version_from if act.version_from > self.day else None,
                                         st_x.changes_on if x_state == "current" else None) if d] or [None])
            ld = {"@context": "https://schema.org", "@type": "Legislation", "name": f"{info.cite} {unit_name(u, pretty, x.article.title)}",
                  "legislationIdentifier": f"{info.number} {x.article.label} str.", "inLanguage": "lt", "legislationJurisdiction": "LT",
                  "url": self.base + path_u, "isBasedOn": info.etar_url, "license": DATA_LICENSE,
                  "legislationDateVersion": x.version_from}
            if x_state == "current":
                ld["legislationLegalForce"] = "https://schema.org/InForce"
                if x_changes:
                    ld["temporalCoverage"] = f"../{_day_before(x_changes)}"
            self.search_items.append([self.act_index, x.article.label, list_title(x.article), self.base + path_u, pretty, lbl])
            self.search_stems.append(fulltext.stems(" ".join([x.article.title or ""] + [b.text for b in x.article.blocks])))
            self.upcoming.append({"url": self.base + path_u, "act": info.abbr, "article": pretty, "on": x_changes,
                                  "state_now": x_state}) if x_changes and x_state == "current" else None
            self.page("article.html", path_u, page_title=f"{info.cite} {unit_name(u, pretty, x.article.title)} | {info.name}",
                      description=_description(x.article), source_note="", cite=f"{info.cite} {unit_name(u, pretty, x.article.title)} "
                      f"({info.full_title}, redakcija, galiojanti {self.day}).", nav=self.nav("article", info.abbr, contents=self.base + base_path),
                      eu_count=len(eu_list), eu_link=eu_link, eu_mentioned=[], jsonld=ld_json(ld), expires=st.expires,
                      art={"pretty": pretty, "title": x.article.title, "label": x.article.label}, status=st_x, status_label=lbl, today_src=src_, future=None,
                      shown_state=x_state, repeal_on=None, future_change=st_x.future_change,
                      changes_on=x_changes,
                      gone_from=act.version_from if act.version_from > self.day and x_state == "current" else None,
                      crumbs=[], blocks=_blocks(x.article.blocks, meta, link, x.article.label, record=True), art_notes=_refs(x.article.notes, meta),
                      other_variants=[], prev=None, next=None, **common)
            art_json.append({"label": x.article.label, "pretty": pretty, "title": x.article.title, "url": self.base + path_u, "path": [],
                             "status": {"state": x_state, "label": lbl, "day": self.day, "reasons": st_x.reasons,
                                        "label_valid_until": _day_before(x_changes) if x_changes else None,
                                        "future_change": {"from": st_x.future_change[0], "law": st_x.future_change[1],
                                                          "certain": st_x.future_change[2]} if st_x.future_change else None,
                                        "not_in_stored_text": True},
                             "text": {"consolidation_valid_from": x.version_from, "consolidation_valid_to": x.version_to, "source": x.origin},
                             "blocks": _blocks(x.article.blocks, meta), "notes": _refs(x.article.notes, meta),
                             "future": None, "other_versions": [], "eu_mentioned": []})

        self.concepts += definitions.concepts(finder.terms, {r["url"]: r["definition"] for r in self.def_rows if r["act"] == act_key},
                                              lambda t: self.base + url[t.label] + "#" + t.anchor if t.label in url else None,
                                              used, act_key, info.cite)
        have = {a.label for a in arts} | {x.article.label for x in today_only}
        stubs = [n for n in st.added if n["label"] not in have]
        for n in {n["label"]: n for n in stubs}.values():
            path_u = f"{base_path}{u['seg']}/{n['label']}/"
            pretty = n["label"].split("-")[0] + ("".join("⁰¹²³⁴⁵⁶⁷⁸⁹"[int(c)] for c in n["label"].split("-")[1]) if "-" in n["label"] else "")
            why = f"šį {u['acc']} nuo {n['from']} įrašė {u['amender']} {nr_text(n['law'])}; jo teksto atviruose duomenyse dar nėra"
            st_x = type(next(iter(st.articles.values())))("unknown", [why])
            self.search_items.append([self.act_index, n["label"], "(teksto dar nėra)", self.base + path_u, pretty, self.label("unknown", None)])
            self.search_stems.append(set())
            self.page("article.html", path_u, page_title=f"{info.cite} {pretty} {u['nom']} | {info.name}",
                      description=f"{info.cite} {pretty} {u['nom']}: tekstas dar neparengtas atviruose duomenyse.", source_note="",
                      cite=None, nav=self.nav("article", info.abbr, contents=self.base + base_path), eu_count=0, eu_link=eu_link,
                      eu_mentioned=[], jsonld=None, expires=st.expires, art={"pretty": pretty, "title": "", "label": n["label"]}, status=st_x,
                      status_label=self.label("unknown", None), today_src=None, future=None, shown_state="unknown", repeal_on=None,
                      changes_on=None, gone_from=None, crumbs=[], blocks=[{"kind": "editorial", "text": f"Šio {u['gen']} teksto atviruose duomenyse dar nėra. Jį įrašė {u['amender']} {nr_text(n['law'])}, galiojantis nuo {n['from']}.", "anchor": None, "notes": []}],
                      art_notes=[], other_variants=[], prev=None, next=None, **common)
            art_json.append({"label": n["label"], "pretty": pretty, "title": None, "url": self.base + path_u, "path": [],
                             "status": {"state": "unknown", "label": self.label("unknown", None), "day": self.day, "reasons": [why]},
                             "text": {"source": None, "not_in_open_data": True, "added_by": n["law"], "from": n["from"]},
                             "blocks": [], "notes": [], "future": None, "other_versions": [], "eu_mentioned": []})
            art_json[-1]["status"]["not_in_stored_text"] = True

        # table of contents, paginated by book when the act has books (CK)
        def toc_items(articles: list[Article]) -> list[dict]:
            items, prev_path = [], []
            for a in articles:
                for depth, h in enumerate(a.path):
                    if depth >= len(prev_path) or prev_path[depth] is not h:
                        items.append({"kind": "heading", "depth": depth, "title": sc(h.title),
                                      "label": f"{h.num} {h.kind}"})
                prev_path = a.path
                s = st.articles[a.label]
                items.append({"kind": "art", "depth": len(a.path), "url": self.base + url[a.label],
                              "pretty": a.num.pretty(), "title": title_now.get(a.label, list_title(a)), "state": eff[a.label],
                              "state_label": self.label(s.state, s.applies_from)})
            return items

        eff = {x["label"]: x["status"]["state"] for x in art_json}
        counts = {k: sum(1 for x in eff.values() if x == k) for k in STATES}
        counts["changes_later"] = sum(1 for x in art_json if x["future"])
        # the annexes: from the consolidation in force today when the stored one is past or future and the open data
        # have today's (MPTMRT: the stored text ends 2025-11-30, today's annex 5 has an item 35 more); else the stored
        annex_list, ann_from, ann_to, ann_src = act.main.annexes, act.version_from, act.version_to, "Dokumentas"
        if not is_eu and st.version_state != "current" and act.main.annexes:
            r = _suvestine_valid_on(scope_act["dokumento_id"], self.day)
            other = parse(_with_header(r), scope_act.get("document")) if r else None
            if other and other.main.annexes:
                annex_list, ann_from, ann_to, ann_src = other.main.annexes, other.version_from, other.version_to, "Suvestine"
        ann_version = version_words(ann_from, ann_to)
        annex_key, used = {}, set()
        for k, x in enumerate(annex_list, 1):  # unnumbered annexes (CPK has two) get distinct URLs
            key = x.num or "1"
            if key in used:
                key = str(k)
            used.add(key)
            annex_key[id(x)] = key
        annexes = [{"url": self.base + f"{base_path}priedas/{annex_key[id(x)]}/", "label": annex_label(x),
                    "heading": annex_heading(x), "title": x.title} for x in annex_list]
        flags = st.act_level_flags

        # contents pages: one page for small acts; otherwise split by book, then by part, so
        # that no contents page lists more than MAX_TOC articles (page size < 100 KB)
        MAX_TOC = 300

        def groups(articles: list[Article], depth: int) -> list[tuple[list, list[Article]]]:
            if len(articles) <= MAX_TOC:
                return [([], articles)]
            keys: list = []
            for a in articles:
                h = a.path[depth] if len(a.path) > depth and a.path[depth].kind in ("knyga", "dalis", "antraštinė dalis", "skyrius") else None
                if not keys or keys[-1][0] is not h:
                    keys.append((h, []))
                keys[-1][1].append(a)
            if len(keys) == 1 or any(h is None for h, _ in keys):
                return [([], articles)]  # no usable split level
            out = []
            for h, arts_h in keys:
                for sub_path, sub in groups(arts_h, depth + 1):
                    out.append(([h, *sub_path], sub))
            return out

        def toc_page(path: list, articles: list[Article]) -> str:
            seg = "".join(f"{slug(h.kind).replace(' ', '-')}/{h.num}/" for h in path)
            return f"{base_path}{seg}"

        page_list = groups(arts, 0)
        if len(page_list) == 1:
            self.page("act.html", base_path, page_title=f"{info.name}{info.paren} – aktuali redakcija {u['ins_pl']}", jsonld=None,
                      description=act_description(info, u),
                      part_title=None, parts=None, toc=toc_items(arts), counts=counts, act_flags=flags, annexes=annexes, expires=st.expires,
                      preamble=act.main.preamble, header_notes=act.header_notes, approval=self._approval(act), notices=st.notices, implemented_by=self.eu_implemented_by.get(info.tar) if is_eu else None, today_only=[{"url": self.base + f"{base_path}{u['seg']}/{x.article.label}/", "pretty": x.article.num.pretty(),
                                                       "title": x.article.title} for x in today_only]
                      + [{"url": self.base + f"{base_path}{u['seg']}/{n['label']}/", "pretty": n["label"].replace("-", "^"),
                          "title": "(teksto dar nėra)"} for n in stubs], future_from=act.version_from,
                      eu_list=eu_list, nav=self.nav("act", info.abbr), **common)
        else:
            parts = []
            for hp, sub in page_list:
                p = toc_page(hp, sub)
                label = ", ".join(f"{h.num} {h.kind}" for h in hp)
                ttl = " / ".join(sc(h.title) for h in hp)
                parts.append({"url": self.base + p, "label": label, "title": ttl, "n": len(sub)})
                self.page("act.html", p, page_title=f"{info.name}, {label} – {ttl}",
                          description=f"{info.name}{info.paren}, {label}: {u['gen_pl']} sąrašas.",
                          jsonld=None, part_title=label, parts=None, toc=toc_items(sub),
                          nav=self.nav("act", info.abbr, contents=self.base + base_path),
                          counts=counts, act_flags=flags, annexes=None, expires=st.expires, **common)
            self.page("act.html", base_path, page_title=f"{info.name}{info.paren} – aktuali redakcija {u['ins_pl']}", jsonld=None,
                      description=act_description(info, u),
                      part_title=None, parts=parts, toc=None, counts=counts, act_flags=flags, annexes=annexes, expires=st.expires,
                      preamble=act.main.preamble, header_notes=act.header_notes, approval=self._approval(act), notices=st.notices, implemented_by=self.eu_implemented_by.get(info.tar) if is_eu else None, today_only=[{"url": self.base + f"{base_path}{u['seg']}/{x.article.label}/", "pretty": x.article.num.pretty(),
                                                       "title": x.article.title} for x in today_only]
                      + [{"url": self.base + f"{base_path}{u['seg']}/{n['label']}/", "pretty": n["label"].replace("-", "^"),
                          "title": "(teksto dar nėra)"} for n in stubs], future_from=act.version_from,
                      eu_list=eu_list, nav=self.nav("act", info.abbr), **common)
        # the annexes are searchable and in the agents' API too, as "priedas-<n>" (2026-11-03: the meters that may be
        # verified by sampling are listed only in MPTMRT's annex 6); their status says that today's text is not checked
        annex_json = []
        for x, ax in zip(annex_list, annexes):
            short = sum(1 for b in x.blocks if len(b.text) < 25)
            x.flattened = len(x.blocks) >= 10 and short / len(x.blocks) > 0.4  # a table printed one cell per line
            self.page("annex.html", f"{base_path}priedas/{annex_key[id(x)]}/", page_title=f"{info.name} – {ax['heading']}",
                      description=_annex_description(ax["heading"], x), jsonld=None, annex=x, heading=ax["heading"], blocks=_blocks(x.blocks, meta), annex_today=ann_src == "Suvestine",
                      nav=self.nav("annex", info.abbr, contents=self.base + base_path), **dict(common, version=ann_version))
            alabel, a_path = f"priedas-{annex_key[id(x)]}", f"{base_path}priedas/{annex_key[id(x)]}/"
            annex_json.append({"label": alabel, "pretty": ax["label"], "title": x.title or x.header, "url": self.base + a_path,
                               "path": [], "status": {"state": "unknown", "label": ANNEX_LABEL, "day": self.day,
                                                      "note": ANNEX_NOTE + (" " + FLATTENED_NOTE if x.flattened else "")},
                               "text": {"consolidation_valid_from": ann_from, "consolidation_valid_to": ann_to, "source": ann_src},
                               "blocks": [{"kind": b.kind, "anchor": b.anchor, "text": display_text(b)} for b in x.blocks],
                               "cite": f"{info.cite} {ax['label']} ({info.full_title}" + (f", redakcija nuo {ann_from}" if ann_from else "") + ")."})
            self.search_items.append([self.act_index, alabel, x.title or x.header, self.base + a_path, ax["label"], ANNEX_LABEL])
            self.search_stems.append(fulltext.stems(" ".join([x.title or ""] + [b.text for b in x.blocks])))

        data = self._json(info, act, st, row, fetched, art_json)
        if annex_list is not act.main.annexes:  # today's consolidation's annexes, as the pages show them
            data["annexes"] = [{"num": x.num, "header": x.header, "title": x.title, "blocks": [b.text for b in x.blocks], "history": x.history,
                                "status": "not checked", "consolidation_valid_from": ann_from, "consolidation_valid_to": ann_to} for x in annex_list]
        data["act"]["notices"] = st.notices
        data["act"]["preamble"] = act.main.preamble
        data["act"]["header_notes"] = act.header_notes
        data["source"]["model"] = origin["origin"]
        data["eu_implemented"] = eu_list
        self.write(f"{base_path}data.json", json.dumps(data, ensure_ascii=False))
        # a small index for agents: every article with its status and URL, no text (CK's data.json is ~4 MB)
        self.write(f"{base_path}articles.json", json.dumps(
            {"unofficial": True, "act": data["act"], "status_day": self.day, "data_json": self.base + base_path + "data.json",
             "articles": [{"label": x["label"], "pretty": x["pretty"], "title": x["title"] or None, "url": x["url"],
                           "path": [f"{h['num']} {h['kind']}" for h in x.get("path") or []],
                           "state": x["status"]["state"], "status_label": x["status"]["label"],
                           "label_valid_until": x["status"].get("label_valid_until"),
                           "future_change_from": (x["status"].get("future_change") or {}).get("from")} for x in art_json],
             "annexes": [{"label": x["label"], "pretty": x["pretty"], "title": x["title"], "url": x["url"],
                          "status_label": ANNEX_LABEL} for x in annex_json]},
            ensure_ascii=False, separators=(",", ":")))
        # an act with no abbreviation in use gets its name as the alias (/viesuju-istaigu-istatymas/), not the key
        alias = act_alias(scope_act.get("slug"), info.name, info.abbr, info.tag)
        if alias in self.aliases:
            raise SystemExit(f"URL alias /{alias}/ used by both {self.aliases[alias]} and {info.abbr}: set `slug:` in the seed")
        self.aliases[alias] = info.abbr
        self.alias_of[info.abbr] = alias
        api_chunks = api.write_act(self.write, alias, art_json + annex_json)  # the agents' API (D-028)
        self.redirects.append(f"/{alias}/:n {base_path}{info.u['seg']}/:n/ 301")
        self.redirects.append(f"/{alias} {base_path} 301")
        # the bare alias ("/dk/") lands here through the account's Bulk Redirects (bin/cf_redirects.py): no page there
        self.redirects.append(f"{base_path}{info.u['seg']}/ {base_path} 301")
        return {"url": self.base + base_path, "path": base_path.lstrip("/"), "name": info.name, "abbr": info.abbr, "eu": is_eu, "tag": info.tag, "cite": info.cite, "unit": info.u["nom"], "seg": info.u["seg"],
                "n": len(arts), "counts": counts,
                "data_json": self.base + base_path + "data.json", "articles_json": self.base + base_path + "articles.json",
                "tar_kodas": info.tar, "number": info.number, "official_url": info.etar_url,
                "names": ACT_NAMES.get(info.abbr), "genitive": scope_act.get("genitive"),
                **({"kind": scope_act.get("kind", "Nutarimas"), "issuer": scope_act["issuer"]} if scope_act.get("issuer") else {}),
                "consolidation_valid_from": act.version_from, "consolidation_valid_to": act.version_to,
                "eu_implemented": len(eu_list), "fetched": fetched, "alias": self.base + f"/{alias}/",
                "expires": st.expires, "unexplained": st.unexplained, "rewrites": [w for w, _ in act.rewrites],
                "labels": [x.label for x in arts], "pages": len(art_json), "api_chunks": api_chunks,
                "origin": origin["origin"], "instead_of": origin.get("instead_of"), "pages_dir": str(self.out / base_path.strip("/")), "today_only": len(today_only),
                "notices": st.notices, "tail_lines": sum(len(sg.tail) for sg in act.segments),
                "dropped_lines": len(dropped_lines(text, act, excluded := [])),
                "excluded_lines": len(excluded),  # signatures and old amendment histories, never shown
                "corrupt_chars": [x["label"] for x in art_json
                                  if any(re.search(r"\w\?\w|\ufffd", b["text"]) for b in x["blocks"])],
                "example": {"url": self.base + url[arts[min(51, len(arts) - 1)].label] + "#d2",
                            "label": f"{info.cite} {arts[min(51, len(arts) - 1)].num.pretty()} str. 2 dalis"}}

    def _approval(self, act: Act) -> list[dict]:
        """The approval law of a code ("… kodekso patvirtinimo, įsigaliojimo ir įgyvendinimo įstatymas"): its
        articles, shown on the code's contents page. They are law too (e.g. DK's entry provisions)."""
        pre = [{"label": "", "title": "", "blocks": list(seg.preamble), "notes": []}
               for seg in act.segments if seg.kind == "approval" and seg.preamble]  # a resolution's "Vadovaudamasi … nutaria:"
        return pre + [{"label": a.num.pretty(), "title": a.title, "blocks": [display_text(b) for b in a.blocks],
                 "notes": [f"{n.label}: " + ", ".join(r.nr for r in n.refs) for n in a.all_notes()]
                 if hasattr(a, "all_notes") else [f"{n.label}: " + ", ".join(r.nr for r in n.refs) for n in a.notes]}
                for seg in act.segments if seg.kind == "approval" for a in seg.articles]

    def _json(self, info: ActInfo, act: Act, st: ActStatus, row: dict, fetched: str, articles: list[dict]) -> dict:
        """The act as data, article by article exactly as the pages show it: `blocks` is the text
        shown, `status` its state on `status.day`, `future` an adopted later text (if any)."""
        return {"unofficial": True,
                "notice": "Neoficialus tekstas. Oficialiai skelbiama tik Teisės aktų registre (e-tar.lt).",
                "source": {"dataset": "https://data.gov.lt/datasets/2613/", "license": "CC BY 4.0", "license_url": DATA_LICENSE,
                           "publisher": "Lietuvos Respublikos Seimo kanceliarija", "fetched": fetched,
                           "official_url": info.etar_url},
                "act": {"abbr": info.abbr, "name": info.name, "number": info.number, "tar_kodas": info.tar,
                        "dokumento_id": info.doc, "consolidation_valid_from": act.version_from,
                        "consolidation_valid_to": act.version_to, "version_state_today": st.version_state,
                        "repealed_from": st.expires},
                "laws_in_force_not_in_text": st.missing,
                "explain": DATA_EXPLAIN,
                "articles": articles,
                "approval_law": self._approval(act),
                "annexes": [{"num": x.num, "header": x.header, "title": x.title, "blocks": [b.text for b in x.blocks],
                             "history": x.history, "status": "not checked"}  # annexes get no label (feedback S12)
                            for x in act.main.annexes]}

    def decision_pages(self, fetched: str) -> None:
        """The energy regulator's electricity decisions (D-034): /vert/ and one page per decision; JSON for agents."""
        from markupsafe import Markup, escape

        from . import decisions
        rows = source.decision_rows()
        if not rows:
            return
        ds = decisions.build(rows, self.day)
        etar = lambda d: ETAR_ACT.format(d["dokumento_id"])  # noqa: E731
        by_series: dict[str, list[dict]] = {}
        for d in ds:
            d["url"] = f"{self.base}/vert/{d['tar_kodas']}/"
            d["etar"] = etar(d)
            d["company"] = (re.search(r"(?:AB|UAB|akcinės bendrovės|uždarosios akcinės bendrovės)\s*„([^“]+)“|(LITGRID AB)", d["pavadinimas"]) or [None, None, None])
            d["company"] = (d["company"][1] or d["company"][2] or "") if d["company"][0] else ""
            if d["series"]:
                by_series.setdefault(d["series"], []).append(d)
        # citations in a decision's text ("… 2015 m. sausio 15 d. nutarimu Nr. O3-3 …") → the rules' pages or other decisions
        rules = {f"{a['number']}/{a['adopted']}": a["url"] for a in self.acts_meta if a.get("adopted") and a.get("issuer")}
        targets = {f"{d['atv_dok_nr']}/{d['priimtas']}": d["url"] for d in ds} | rules  # the rules' own pages win
        months = {m: i + 1 for i, m in enumerate(source._GEN_MONTHS)}
        cite = re.compile(r"(\d{4}) m\. (\w+) (\d{1,2}) d\. (nutarim\w*|įsakym\w*) Nr\. ?([\w-]+(?:/[\w-]+)*)")

        def linked(line: str, d: dict) -> Markup:
            spans = []
            for m in cite.finditer(line):
                if m.group(2) not in months:
                    continue
                url = targets.get(f"{m.group(5)}/{m.group(1)}-{months[m.group(2)]:02d}-{int(m.group(3)):02d}")
                if url:
                    spans.append((m.start(), m.end(), url))
            # "Lietuvos Respublikos elektros energetikos įstatymo 9 straipsnio" → that article (xref.Others): today's
            # text for a decision that applies now; for an older one the article as it was on its adoption day (dated
            # pages: since 2020); before 2020 no link, as today's article can say something else
            here = f"{self.base}/vert/{d['tar_kodas']}/"
            self.refs += [(here, url) for *_, url in spans]  # the rules and decisions it cites (D-036)
            for a, b, url in (self.others.find(line) if getattr(self, "others", None) else []):
                self.refs.append((here, url))  # the article itself, whatever the page links to (D-036)
                if d["label"]["state"] in ("current", "pending"):
                    spans.append((a, b, url))
                elif d["priimtas"] >= "2020-01-01":
                    spans.append((a, b, f"{self.base}/kaip-buvo/?u={url[len(self.base):]}&data={d['priimtas']}"))
            out, last = [], 0
            for a, b, url in sorted(spans):
                if a < last:
                    continue
                out += [escape(line[last:a]), Markup(f'<a href="{escape(url)}">{escape(line[a:b])}</a>')]
                last = b
            return Markup("").join(out + [escape(line[last:])])
        for d in ds:
            self.decision_info[f"{self.base}/vert/{d['tar_kodas']}/"] = {"title": d["pavadinimas"], "number": d["atv_dok_nr"],
                                                                         "adopted": d["priimtas"], "status": d["label"]["text"]}
            text = source.decision_text(d["dokumento_id"])
            lines = [linked(l.strip(), d) for l in (text or "").split("\n") if l.strip()]
            series = sorted(by_series.get(d["series"] or "", []), key=lambda x: x["priimtas"], reverse=True) if d["series"] else []
            self.page("decision.html", f"/vert/{d['tar_kodas']}/", page_title=f"VERT nutarimas Nr. {d['atv_dok_nr']} ({d['priimtas']}) | Atviri teisės aktai",
                      jsonld=None, description=f"{d['pavadinimas'][:150]} – Valstybinės energetikos reguliavimo tarybos nutarimas; būsena: {d['label']['text']}.",
                      d=d, lines=lines, series=series, fetched=fetched, rules_url=rules.get(d["key"]))
        sectors = []
        for sec, name in decisions.SECTORS.items():
            mine = [d for d in ds if d["sector"] == sec]
            now = [d for d in mine if d["label"]["state"] in ("current", "pending")]
            reg = [d for d in mine if d["label"]["state"] == "register"]
            groups: dict[str, list[dict]] = {}
            for d in now:
                groups.setdefault(d["company"] or "Bendri sprendimai", []).append(d)
            order = sorted(groups, key=lambda c: (c == "Bendri sprendimai", c != "Energijos skirstymo operatorius", c))
            self.page("vert.html", f"/vert/{sec}/", page_title=f"VERT sprendimai: {name.lower()} – kainos ir tarifai",
                      jsonld=None, description=f"Valstybinės energetikos reguliavimo tarybos nutarimai ({name.lower()}): kurie taikomi šiandien, kurie ankstesni.",
                      sector=name, groups=[(c, groups[c]) for c in order], register=reg, n=len(mine), fetched=fetched)
            sectors.append({"slug": sec, "name": name, "n": len(mine), "now": len(now)})
        self.page("vert_index.html", "/vert/", page_title="Energetikos reguliavimo tarybos (VERT) sprendimai – elektra, dujos, šiluma",
                  jsonld=None, description="Valstybinės energetikos reguliavimo tarybos nutarimai dėl elektros, gamtinių dujų ir šilumos kainų, tarifų ir įkainių: kurie taikomi šiandien.",
                  sectors=sectors, fetched=fetched)
        self.write("/api/v1/vert.json", json.dumps({
            "unofficial": True, "status_day": self.day, "notice": "Labels are this site's reading of each decision's title and series; "
            "the register keeps every decision 'in force'. Price tables are annexes on e-tar.lt only.",
            "decisions": [{k: d.get(k) for k in ("atv_dok_nr", "priimtas", "isigalioja", "pavadinimas", "galioj_busena", "sector", "series", "url", "etar")}
                          | {"label": d["label"], "changed_by": [{"number": c["atv_dok_nr"], "adopted": c["priimtas"]} for c in d["changed_by"]]}
                          for d in ds]}, ensure_ascii=False, separators=(",", ":")))

    def _validation(self) -> dict | None:
        vdir = source.VALIDATION
        try:
            cur = json.loads((vdir / "currency.json").read_text())
            scp = json.loads((vdir / "scope.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        rows = []
        for abbr, c in cur["acts"].items():
            if c.get("original_only"):  # never consolidated: nothing on e-tar to compare with, so not "compared"
                continue
            sc = scp["acts"].get(abbr, {})
            rows.append({"abbr": abbr, "articles": c["articles"], "text_diff": sc.get("text_diff", "–"),
                         "current_ok": c.get("current_ok", 0), "flagged": c.get("flagged", c["articles"]),
                         "silent": c.get("silent_errors", c.get("current", 0))})  # not in force yet: all flagged, "current" are errors
        bt = None
        if (vdir / "backtest_history.json").exists():
            t = json.loads((vdir / "backtest_history.json").read_text())
            # wrong "Galioja šiandien" only (the list also holds articles called repealed while in force)
            wrong = sum(1 for x in t.get("silent", []) if x.get("said", "current") == "current")
            n = t["totals"].get("current_ok", 0) + wrong
            lt = lambda x: f"{x:,}".replace(",", "\u00a0").replace(".", ",")  # noqa: E731  Lithuanian: 120 319; 0,22
            bt = {"period": t["period"], "situations": lt(t["totals"].get("articles", 0)), "pairs": t["totals"].get("pairs", 0),
                  "silent": wrong, "silent_pct": lt(round(100 * wrong / max(n, 1), 2)),
                  "false_pct": lt(round(100 * t["totals"].get("false_alarm", 0) / max(t["totals"].get("articles", 1), 1), 1))}
        return {"day": cur["day"], "rows": rows, "compared": sum(r["articles"] for r in rows), "backtest": bt,
                "text_diffs": sum(r["text_diff"] for r in rows if isinstance(r["text_diff"], int)),
                "silent": cur["silent_errors"]}

    def finish(self, acts: list[dict]) -> None:
        v = self._validation()
        groups = _area_groups(acts)
        # a resolution approving several documents in scope (D-027): /ta/<TAR>/ lists them
        by_res: dict[str, list[dict]] = {}
        for a in acts:
            if a["path"].count("/") > 2:  # "ta/<TAR>/<docslug>/"
                by_res.setdefault("/".join(a["path"].split("/")[:2]) + "/", []).append(a)
        for path, docs in by_res.items():
            what = f"{docs[0].get('issuer') or 'Vyriausybės'} {'įsakymas' if docs[0].get('kind') == 'Įsakymas' else 'nutarimas'}"
            title = (f"{what} Nr. {docs[0]['number']}" if docs[0].get("number") else what)
            title = title[:1].upper() + title[1:]
            self.page("resolution.html", "/" + path, page_title=f"{title}: patvirtinti dokumentai", jsonld=None,
                      description=f"{title}: šioje svetainėje pateikiami jo patvirtinti dokumentai.", title=title,
                      docs=docs, official=docs[0]["official_url"], nav=self.nav("home"))
        # the site's "data checked": the day by which 90% of the acts were checked. The single oldest act made every page
        # say "not updated since" when one act lagged (CK, 2026-10-27: B62); a lagging act's own pages still say so
        days = sorted(a["fetched"] for a in acts)
        checked = days[len(days) // 10]
        self.page("index.html", "/", page_title="Atviri teisės aktai – Lietuvos teisės aktai straipsnis po straipsnio",
                  jsonld=json.dumps({"@context": "https://schema.org", "@type": "WebSite", "name": "Atviri teisės aktai",
                                     "inLanguage": "lt", "url": self.base + "/",
                                     "description": "Neoficialus, nemokamas Lietuvos teisės aktų tekstas straipsniais, su galiojimo žymomis ir nuorodomis į e-tar.lt."},
                                    ensure_ascii=False),
                  description="Lietuvos teisės aktai po vieną straipsnį, su žyma, ar tekstas galioja šiandien, ir nuoroda į oficialų tekstą e-tar.lt.",
                  acts=acts, groups=groups, validation=v, example=acts[0]["example"], fetched=checked, nav=self.nav("home"))
        for g in groups:  # one page per area (/sritis/energetika/): the acts of a topic, for people and search engines
            if not g.get("slug"):
                continue
            n_arts = sum(a["n"] for a in g["acts"])
            n_eu = sum(1 for a in g["acts"] if a.get("eu"))  # EU acts (D-037) are counted apart: not Lithuanian acts
            acts_count = " ir ".join(x for x in (
                lt_count(len(g["acts"]) - n_eu, "Lietuvos teisės aktas", "Lietuvos teisės aktai", "Lietuvos teisės aktų") if len(g["acts"]) > n_eu else "",
                lt_count(n_eu, "ES teisės aktas", "ES teisės aktai", "ES teisės aktų") if n_eu else "") if x)
            self.page("area.html", f"/sritis/{g['slug']}/", page_title=f"{g['name']} – teisės aktai straipsnis po straipsnio",
                      jsonld=None, description=(f"{g['name']}: {acts_count} "
                                                f"({lt_count(n_arts, 'straipsnis ar punktas', 'straipsniai ir punktai', 'straipsnių ir punktų')}), "
                                                "kiekvienas straipsnis su žyma, ar galioja šiandien, ir nuoroda į "
                                                + ("e-tar.lt ar EUR-Lex." if n_eu else "e-tar.lt.")),
                      group=g, n_arts=n_arts, n_eu=n_eu, acts_count=acts_count, fetched=checked, nav=self.nav("area", area=g["slug"]),
                      feed=f"{self.base}/sritis/{g['slug']}/atom.xml", feed_title=f"{g['name']}: pakeitimai")
        self.write("/api/v1/definitions.json", json.dumps({
            "unofficial": True, "status_day": self.day, "count": len(self.def_rows),
            "notice": "Definitions as the pages show them today. kind 'definition': a definitions article or point; kind 'title': "
                      "a concept named by an article's title and defined in its first part (a candidate). The same word can mean "
                      "different things in different acts.",
            "definitions": self.def_rows,
            "by_reference": self.def_refs}, ensure_ascii=False, separators=(",", ":")))
        self.write("/api/v1/concepts.json", json.dumps({
            "unofficial": True, "status_day": self.day, "count": len(self.concepts),
            "notice": "A concept graph of the terms in each act's definitions article, as candidates (found by words, not "
                      "read by a lawyer). broader: the defined term of the same act that the definition starts with "
                      "(\"Pažeidžiamas vartotojas – buitinis elektros energijos vartotojas, …\" -> buitinis vartotojas), "
                      "a candidate. used_in: the act's articles (labels) where the term was found, inflection-tolerant; a "
                      "term written with another stem can be missed, and one-word terms found in over a quarter of the "
                      "act's articles are left out. Across acts: definitions_by_reference.json.",
            "concepts": self.concepts}, ensure_ascii=False, separators=(",", ":")))
        self.write("/api/v1/definitions_by_reference.json", json.dumps({
            "unofficial": True, "status_day": self.day, "count": len(self.def_refs),
            "notice": "Sentences that say where an act's terms are defined (\"sąvokos suprantamos taip, kaip jos apibrėžtos … "
                      "įstatyme\"). terms: the terms it names, or null for all the act's other terms. acts: the acts on this site "
                      "it names (found by their names; check the text). not_on_site: other acts it names, as written (EU acts "
                      "included; an act only mentioned in passing can be among them). also_other_acts: it also says \"kituose "
                      "teisės aktuose\" or similar.",
            "references": self.def_refs}, ensure_ascii=False, separators=(",", ":")))
        shards: dict[str, list[dict]] = {}
        for r in self.def_rows:
            for k in definitions.shard_keys(r):
                shards.setdefault(k, []).append(r)
        for k, rows in shards.items():
            self.write(f"/api/v1/defs/{k}.json", json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
        try:  # an error here must not take the acts' pages down with it: the nightly reports it (site.soft_warnings)
            self.decision_pages(checked)
        except Exception as e:  # noqa: BLE001
            self.soft_warnings.append(f"regulator decision pages not built: {e!r}")
        self.page("about.html", "/apie/", page_title="Kaip veikia ši svetainė – šaltiniai, tikrinimas, ribojimai", jsonld=None,
                  description="Iš kur paimtas tekstas, kaip nustatoma, ar jis galioja šiandien, ir kaip tikrinama.",
                  validation=v, fetched=checked, ledger=self.ledger_totals, nav=self.nav("about"))
        index = {"name": "Atviri teisės aktai", "unofficial": True, "contact": CONTACT,
                 "notice": "Unofficial text. Official publication only in the Register of Legal Acts (e-tar.lt).",
                 "source": {"dataset": "https://data.gov.lt/datasets/2613/", "license": "CC BY 4.0",
                            "publisher": "Lietuvos Respublikos Seimo kanceliarija"},
                 "status_day": self.day, "data_checked": checked, "built": self.built,
                 "register_newest_publication": self.watermark,
                 "dates": "all dates are calendar dates in Lithuania (Europe/Vilnius); a label holds through label_valid_until",
                 "status_values": {"current": "text applies on status_day", "pending": "adopted text not yet in force (see applies_from); no text for today in the open data",
                                   "outdated": "an amendment already in force is not yet in this text",
                                   "unknown": "could not be established; check e-tar.lt",
                                   "repealed": "the article, or the whole act, is no longer in force (since applies_from)"},
                 "url_scheme": {"article": "/ta/<tar_kodas>/str/<number>/  (superscript as -n: 21-1, 6.228-1)",
                                "point": "/ta/<tar_kodas>/p/<number>/  (rules approved by a Government resolution, e.g. KET: one page per top-level point; sub-points #p3.1)",
                                "article_short": "/<alias>/<number>/ redirects to the article (alias per act below, e.g. /dk/52/)",
                                "part_anchor": "#d<part>", "point_anchor": "#d<part>-p<point>",
                                "act_json": "/ta/<tar_kodas>/data.json (articles exactly as shown on the pages: blocks = text shown, status, future)",
                                "act_index": "/ta/<tar_kodas>/articles.json (small: every article's number, title, status and URL; no text)",
                                "changes_feed": "/atom.xml (site-wide), /sritis/<area>/atom.xml (per area) and /ta/<tar_kodas>/atom.xml (per act): text and label changes, nightly, each saying why",
                                "dated_page": "/kaip-buvo/?u=/ta/<tar_kodas>/str/<number>/&data=YYYY-MM-DD (the official consolidation in force that day, since 2020)",
                                "area": "/sritis/<area>/ (acts by topic, e.g. energetika)",
                                "regulator_decisions": "/vert/ and /api/v1/vert.json (the energy regulator's electricity, gas and heat decisions with this site's labels; price annexes on e-tar.lt)",
                                "definitions": "/api/v1/definitions.json (every definition: term, alias, definition, act, article, part, URL, status)",
                                "concepts": "/api/v1/concepts.json (a concept graph, candidates: each defined term, the broader term its definition starts with, the articles using it)",
                                "definitions_by_reference": "/api/v1/definitions_by_reference.json (sentences saying an act's terms are understood as defined in other acts, with those acts)"},
                 "agents": {"mcp": self.base + "/mcp", "transport": "Streamable HTTP, JSON-RPC 2.0, no key",
                            "tools": ["search_law", "get_article", "get_articles", "related", "find_definition", "list_acts", "get_act_contents", "upcoming_changes"],
                            "endpoints": "/api",
                            "rest": {"search": "/api/search?q=", "article": "/api/article?act=&article=[&part=][&date=YYYY-MM-DD]",
                                     "definition": "/api/definition?term=[&act=]", "acts": "/api/acts",
                                     "contents": "/api/contents?act=", "upcoming": "/api/upcoming?days="}},
                 "validation": v,
                 "label_changes_next_30_days": sorted(
                     [u for u in self.upcoming if u["on"] <= (dt.date.fromisoformat(self.day) + dt.timedelta(days=30)).isoformat()],
                     key=lambda u: (u["on"], u["act"])),
                 "acts": [{k: a[k] for k in ("abbr", "cite", "name", "unit", "url", "alias", "data_json", "articles_json", "tar_kodas", "official_url", "n", "counts",
                                             "consolidation_valid_from", "consolidation_valid_to", "eu_implemented", "fetched",
                                             "expires")} | short_names(a, acts) for a in acts]}
        self.write("index.json", json.dumps(index, ensure_ascii=False, indent=1))
        assert len(self.search_stems) == len(self.search_items), "full-text index out of step with the search items"
        self.fulltext = fulltext.write(self.out, self.search_stems)
        self.write("search-index.json", json.dumps({"acts": self.search_acts, "items": self.search_items,
                                                    "fulltext": {"stem": fulltext.STEM, "path": self.base + "/paieska/t/",
                                                                 "common": self.fulltext["common"]}},
                                                    ensure_ascii=False, separators=(",", ":")))
        self.write("app.js", (pathlib.Path(__file__).parent / "templates" / "app.js").read_text())
        # titles only, for the agents' search: a match in an article's title ranks first (D-028)
        titles = fulltext.write(self.out, [fulltext.stems(it[2] or "") for it in self.search_items], max_share=0.05,
                                subdir="api/v1/titles")
        self.soft_warnings += api.write_topics(self.write, acts, SCOPE_DIR / "topics.yaml")
        api.write_site(self.write, acts, self.search_items, index["label_changes_next_30_days"],
                       {"unofficial": True, "status_day": self.day, "data_checked": checked, "notice": index["notice"],
                        "official_source": "https://www.e-tar.lt", "licence": "CC BY 4.0 (Lietuvos Respublikos Seimo kanceliarija)",
                        "register_newest_publication": index.get("register_newest_publication"),
                        "acts": len(acts), "fulltext": {"stem": fulltext.STEM, "path": "/paieska/t/", "common": self.fulltext["common"]},
                        "titles": {"path": "/api/v1/titles/", "common": titles["common"]},
                        "validation": {k: v[k] for k in ("day", "compared", "text_diffs", "silent") if v and k in v} if v else None},
                       self.search_acts)
        api.write_refs(self.write, self.base, acts, self.search_items, self.search_acts, self.refs, self.decision_info)
        # a research recipe any agent can load (an Agent Skill; the MCP server's prompt says the same, D-036)
        self.write(SKILL_PATH, (pathlib.Path(__file__).parent / "templates" / "skill" / "SKILL.md").read_text().replace("{{BASE}}", self.base))
        self.write(f"/{INDEXNOW_KEY}.txt", INDEXNOW_KEY)
        wk = self.out / ".well-known"  # the MCP registry's domain check (written directly: write() would make it a page)
        wk.mkdir(parents=True, exist_ok=True)
        (wk / "mcp-registry-auth").write_text(f"v=MCPv1; k=ed25519; p={MCP_REGISTRY_PUBKEY}")
        self.write("/favicon.svg", FAVICON_SVG)
        self.write("/favicon.ico", _favicon_ico())
        self.write("/icon-512.png", _icon_png(512))  # the MCP registry entry's icon (bin/mcp_registry.py)
        # a real 404 page: without one, Cloudflare Pages answers every unknown path with the home page and 200 (scanners'
        # "/.env", "/.git/config" got the home page: nothing leaked, but soft 404s for search engines). Never indexed.
        self.write("/404.html", env.get_template("404.html").render(
            root=self.base, canonical=self.base + "/404.html", indexable=False, day=self.day, stale=None,
            watermark=self.watermark, register_lag=None, page_title="Puslapis nerastas – Atviri teisės aktai",
            nav=self.nav("other"), fetched=checked))
        # the dated pages' shell (D-030): the site's look, filled by the Worker; never indexed (one URL per date)
        self.write("/api/v1/dated.html", env.get_template("dated.html").render(
            root=self.base, canonical=self.base + "/kaip-buvo/", indexable=False, day=self.day, stale=None,
            watermark=self.watermark, register_lag=None, page_title="%%TITLE%%", nav=self.nav("other"), fetched=checked))
        self.page("search.html", "/paieska/", page_title="Paieška – Atviri teisės aktai", jsonld=None,
                  description="Paieška pagal akto santrumpą, straipsnio numerį ir pavadinimą.", fetched=checked,
                  nav=self.nav("search"))
        llms = ["# Atviri teisės aktai (unofficial article-by-article mirror of Lithuanian law)", "",
                "> Lithuanian codes and laws, one page per article, each marked whether its text applies today "
                "(Galioja šiandien / Įsigalios <date> / Gali būti pasenęs / Neaišku, ar galioja / Neteko galios <date>). "
                f"Statuses are as of {self.day} (Lithuanian calendar dates, Europe/Vilnius); data last checked {checked}. Text taken unchanged from the Seimas "
                "Chancellery's Register of Legal Acts open data (CC BY 4.0); never consolidated by us. "
                f"Official publication: https://www.e-tar.lt. Errors and takedown requests: {CONTACT}", "",
                "## How to use", "",
                f"- Article URL: {self.base}/ta/<tar_kodas>/str/<number>/ (superscripts as -n: 21-1, 6.228-1); part #d2, point #d2-p3",
                f"- Point URL (rules approved by a Government resolution, a minister's order or the energy regulator, e.g. Kelių eismo taisyklės): {self.base}/ta/<tar_kodas>/p/<number>/; sub-point #p3.1",
                f"- EU law (D-037: GDPR, NIS2 and its implementing rules, AI Act, Data Act, Cyber Resilience Act, eIDAS, the electricity "
                f"market regulation and directive and their cyber security and metering-data rules), in Lithuanian from EUR-Lex: "
                f"{self.base}/es/<CELEX>/str/<number>/ (inserted articles as 4a). Label 'Taikomas nuo <date>' = the act is in force, "
                f"this article applies only from that date (read from the act's final article). A directive binds the Member States: "
                f"people and companies follow the Lithuanian act transposing it (listed on the directive's page)",
                f"- Topics: {self.base}/sritis/<area>/ (e.g. {self.base}/sritis/energetika/, {self.base}/sritis/duomenys-it/)",
                f"- Short form: {self.base}/<alias>/<number>/ redirects there, e.g. {self.base}/dk/52/ (aliases below)",
                "- Each article page carries its status in the badge, in data-state/data-status-day on <main>, and in JSON-LD (legislationLegalForce, legislationDateVersion)",
                f"- Whole act as JSON (structure, text, amendment refs, statuses): {self.base}/ta/<tar_kodas>/data.json",
                f"- Index of acts: {self.base}/index.json",
                f"- What changed (Atom): {self.base}/atom.xml, per area /sritis/<area>/atom.xml, per act /ta/<tar_kodas>/atom.xml",
                "- When citing, give the article URL and say the official text is on e-tar.lt. Check the status label.", "",
                "## Guidelines for AI agents", "",
                "- Check the status before relying on a text: 'Galioja šiandien' = applies today; 'Įsigalios <date>' = adopted, not yet "
                "in force; 'Gali būti pasenęs' = an amendment in force isn't in this text yet; 'Neaišku, ar galioja' = could not be "
                "established; 'Neteko galios' = repealed. Statuses are recomputed every night.",
                "- Prefer the JSON (data.json, articles.json), the REST API or the MCP server below to scraping the HTML.",
                "- Reliability (measured, see /apie/): every act's text is identical to e-tar.lt's version of the same date; "
                "labels are checked nightly and against e-tar.lt; texts are never consolidated or rewritten by us.",
                "- This is an unofficial mirror: cite the article URL and say the official publication is e-tar.lt.", "",
                "## For AI agents and programs", "",
                f"- MCP server (Streamable HTTP, JSON-RPC 2.0, no key): {self.base}/mcp; tools search_law, get_article (optional "
                "`part`: one part, e.g. \"107\"; optional `date` YYYY-MM-DD: the Chancellery's official consolidation in force that "
                "day, since 2020, gaps said so; optional `find`: only the paragraphs and table rows with these words; a very long annex "
                "comes in pieces, `offset`), get_articles (up to 20 references in one call: \"DK 52\", \"EEĮ 2 str. 15 d.\"), "
                "related (what an article cites, and the articles of other acts and the regulator's decisions that cite it), "
                "find_definition (where a term is defined, in every act), list_acts, get_act_contents, upcoming_changes",
                f"- REST, with every endpoint and parameter: {self.base}/api · e.g. {self.base}/api/article?act=DK&n=52&part=2 · "
                f"{self.base}/api/definition?term=vartotojas · {self.base}/api/search?q=DK+52 · "
                f"{self.base}/api/articles?ref=DK+52&ref=EE%C4%AE+2+str.+15+d. · {self.base}/api/related?act=E%C4%AE&article=23",
                "- Acts are named by key, abbreviation, TAR code or name (\"DK\", \"2016-23709\", \"darbo kodeksas\"); `article` and `n` are the same",
                f"- How to research with these tools, as an Agent Skill (search wordings, definitions, batches, references both ways, "
                f"labels): {self.base}{SKILL_PATH}",
                f"- Every definition on the site: {self.base}/api/v1/definitions.json (term, alias, definition, act, article, part, URL, status)",
                f"- Where an act says its terms are defined in other acts (\"sąvokos suprantamos taip, kaip jos apibrėžtos … įstatyme\"): "
                f"{self.base}/api/v1/definitions_by_reference.json; find_definition(term, act) follows these",
                f"- A concept graph, as candidates: {self.base}/api/v1/concepts.json (term, broader term, articles using it)",
                f"- Static files the server reads: {self.base}/api/v1/acts.json, {self.base}/api/v1/meta.json",
                f"- An article as it was on a date, for people: {self.base}/kaip-buvo/?u=/ta/<tar_kodas>/str/<number>/&data=YYYY-MM-DD",
                f"- The energy regulator's (VERT) decisions on electricity prices and tariffs: {self.base}/vert/ (people), "
                f"{self.base}/api/v1/vert.json (programs). The register keeps every such decision 'in force', so each carries "
                "this site's label: 'Taikomas: <period>' = its period (from its title) includes today; 'Įsigalios' = not yet; "
                "'Ankstesnio laikotarpio' = its period is over; 'Vėliau priimtas tos pačios srities sprendimas' = replaced in a "
                "recurring price series; otherwise the register's status. The price tables are annexes on e-tar.lt only.",
                "- Every answer carries the notice, the status day and the newest publication in the open data.",
                "- Programs: please send a User-Agent header that names your program.", "",
                "## Acts", "",
                f"- {len(acts)} acts. The list with every act's address, alias and JSON: {self.base}/llms-full.txt; as JSON: {self.base}/index.json",
                "", "## About", "", f"- [Method, sources, validation]({self.base}/apie/)",
                f"- [Source code and the rules behind every label]({CODE_URL}) (MIT)", ""]
        self.write("llms.txt", "\n".join(llms))  # slim: an agent reads the rules before its context fills (feedback P14)
        full = llms[: llms.index("## Acts") + 2]
        full += [f"- [{a['abbr'] + ' – ' if a.get('tag') else ''}{a['name']}]({a['url']}): {a['n']} {'points' if a.get('unit') == 'punktas' else 'articles'}; "
                 f"short {a['alias']}; index {a['articles_json']}; full JSON {a['data_json']}" for a in acts]
        full += ["", "## About", "", f"- [Method, sources, validation]({self.base}/apie/)",
                f"- [Source code and the rules behind every label]({CODE_URL}) (MIT)", ""]
        self.write("llms-full.txt", "\n".join(full))
        dynamic = [r for r in self.redirects if ":n" in r]
        lines = redirect_lines(self.redirects)
        if len(dynamic) > 100:
            print(f"_redirects: {len(dynamic)} aliases > 100: left to Bulk Redirects (run bin/cf_redirects.py --apply)")
        self.write("_redirects", "\n".join(lines) + "\n")
        self.sitemap += [f"{self.base}/pakeitimai/"] + [f"{g['url']}pakeitimai/" for g in self.nav_areas]  # (written later: changes_pages)
        for name, content in sitemap_files([(u, self.lastmod.get(u[len(self.base):], [None, self.day])[1]) for u in self.sitemap], self.base, self.day):
            self.write(name, content)
        source.STATE.mkdir(parents=True, exist_ok=True)
        (source.STATE / "lastmod.json").write_text(json.dumps(self.lastmod, separators=(",", ":")))
        bots = ["Googlebot", "Bingbot", "OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "Claude-User",
                "PerplexityBot", "Perplexity-User", "Bravebot", "CCBot"]
        # crawlers skip the dated pages (noindex, one per period of every article: Googlebot spent ~650 fetches a
        # day on them, 2026-10-25); assistants fetching for a person (*-User) may read them
        rule = lambda b: "Allow: /\n" if b.endswith("-User") else "Disallow: /kaip-buvo/\nAllow: /\n"
        robots = ("".join(f"User-agent: {b}\n{rule(b)}\n" for b in bots) + f"User-agent: *\n{rule('*')}\n"
                  if self.indexable else "User-agent: *\nDisallow: /\n\n")
        self.write("robots.txt", robots + f"Sitemap: {self.base}/sitemap.xml\n")
        # Pages response headers: no framing by other sites (clickjacking); nothing that could break the pages
        self.write("_headers", "/*\n  Content-Security-Policy: frame-ancestors 'self'\n  X-Frame-Options: SAMEORIGIN\n"
                   "/.well-known/mcp-registry-auth\n  Content-Type: text/plain; charset=utf-8\n")  # no extension: no type
