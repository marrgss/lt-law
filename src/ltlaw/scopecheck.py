"""Checks of a scope act against its own text: the name we show is the heading the text carries, and an order that
approves several documents says which one is ours (bin/add_acts.py before adding; the nightly reports both).

2026-11-03: 25 acts showed the name they were adopted under while their text had been renamed (AAVKĮ "… valstybinės
priežiūros įstatymas" since 2026-01-12, DET "Degalinių įrengimo ir eksploatavimo taisyklės"); four orders went in
under one name while approving two documents, showing only the first.
"""
import re

# the approval stamp ("PATVIRTINTA Lietuvos Respublikos … 2010 m. … įsakymu Nr. 1-111 (… redakcija)"), then the heading up to
# its first chapter or point; upper case PATVIRTINTA only (notes say "patvirtinta" in passing)
_STAMP = re.compile(r"\bPATVIRTINT(?:A|AS|I|OS)\s+[A-ZĄČĘĖĮŠŲŪŽ].{0,300}?(?:nutarimu|įsakymu|sprendimu)\s*Nr\.\s*[\w./()-]+?(?:\s*\([^)]{0,250}redakcija\))?\s+(.{3,500}?)"
                    r"\s+(?:I\s+SKYRIUS|I\s+Skyrius|I\s*\.\s+[A-ZĄČĘĖĮŠŲŪŽ]|PIRMASIS\s+SKIRSNIS|PIRMA\s+DALIS|BENDROSIOS\s+NUOSTATOS|1\s*\.\s+[A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž])", re.S)
_LAW = re.compile(r"LIETUVOS\s+RESPUBLIKOS\s+([^\d:]{3,300}?)\s*(ĮSTATYMAS|KODEKSAS|STATUTAS)\b", re.S)
# amendment notes printed inside a heading ("Pakeistas priedo pavadinimas: Nr. 1-253, …")
_NOTE = re.compile(r"\s*(?:pakeistas|keistas)\s+(?:priedo\s+)?pavadinimas[:.].*$|\s*(?:priedo|įstatymo)\s+pavadinimas\s+keistas.*$", re.I | re.S)


def norm(s: str) -> str:
    """Lower case, no quotes or brackets, letter-spaced words joined ("Į S T A T Y M A S"), one space."""
    s = re.sub(r"[\s\xa0]+", " ", re.sub(r"[„“\"”«»()]", "", s.lower()))
    s = re.sub(r"\b(?:\w ){2,}\w\b", lambda m: m.group(0).replace(" ", ""), s)
    s = re.sub(r"(?<=\d):\s+(?=\d)", ":", s)  # "HN 18: 2007" in a text is HN 18:2007
    return re.sub(r"\s*([,–-])\s*", r"\1 ", s).strip(" .")


def _clean(h: str) -> str:
    """A heading without what the stamp pattern can drag in: a second stamp before it, the first chapter after it."""
    h = norm(_NOTE.sub("", h))
    h = re.split(r"(?:nutarimu|įsakymu|sprendimu) nr\. ?[\w./()]+(?:- ?[\w./()]+)*(?: redakcija)?|redakcija ", h)[-1].strip()
    # ("I. skyrius", "I. bendrosios nuostatos", "I. taikymo sritis" (HN126) in lower case escape the stamp pattern's end: ĮDSSTPN, LVLKTUET 2026-11-09)
    return re.sub(r"\s+(?:(?:[ivx]+\.?|pirmasis|pirma)\s+(?:skyrius|skirsnis|dalis|bendrosios\s+nuostatos|taikymo\s+sritis)\b.*|i\.?)$", "", h).strip()


def headings(text: str, act: dict) -> list[str]:
    """The document headings the text carries: after each approval stamp (rules), or the law's own title."""
    t = re.sub(r"[\s\xa0]+", " ", (text or "")[:60000])
    if act.get("adopted") or act.get("unit") == "punktas":
        return [_clean(m.group(1)) for m in _STAMP.finditer(t)]
    t = re.sub(r"\b(?:[A-ZĄČĘĖĮŠŲŪŽ] ){2,}[A-ZĄČĘĖĮŠŲŪŽ]\b", lambda m: m.group(0).replace(" ", ""), t[:20000])
    return [norm(f"{_NOTE.sub('', m.group(1))} {m.group(2)}") for m in _LAW.finditer(t)]


def name_matches(name: str, heading: str) -> bool:
    """Our name is the heading, or ends with it (we may prefix the operator: "AB „Energijos skirstymo operatorius“ …")."""
    n, h = norm(name), heading
    return n == h or n.endswith(" " + h) or h.endswith(" " + n)  # the heading may keep "Lietuvos Respublikos"


def check(text: str, act: dict, day: str | None = None) -> list[str]:
    """Problems of one act (empty: fine). EU acts, acts that select their document (`document:`) and acts whose name
    was checked by hand (`name_checked: true`: the source heading has a typo, or we add the operator's name) are not
    checked."""
    if act["dokumento_id"].startswith("EU.") or act.get("document") or act.get("name_checked"):
        return []
    v = re.search(r"Suvestinė redakcija nuo (\d{4}-\d\d-\d\d)", (text or "")[:600])
    if day and v and v.group(1) > day:
        return []  # the stored text is a coming version: its heading may be a coming name (NTKadĮ, GKĮ from 2027)
    hs = headings(text, act)
    if not (act.get("adopted") or act.get("unit") == "punktas") and norm(act["name"]) in norm((text or "")[:20000]):
        return []  # a law's title anywhere in its opening (codes: inside their approval law)
    if not hs or name_matches(act["name"], hs[0]):
        return []  # the first document is ours: the parser reads the first one (MKPTNT, MPLT carry a second)
    later = [h for h in hs[1:] if name_matches(act["name"], h)]
    if later:
        return [f"approves {len(set(hs))} documents and ours is not the first (“{hs[0]}” comes first): set `document:` to ours"]
    return [f"name differs from the text's heading: “{act['name']}” vs “{hs[0]}”"]
