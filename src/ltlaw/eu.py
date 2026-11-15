"""EU legal acts behind a Lithuanian act: what it implements (annex) and mentions (articles).

Codes and many laws end with an annex "ĮGYVENDINAMI EUROPOS SĄJUNGOS TEISĖS AKTAI" listing the
directives/regulations they transpose. We turn each reference into a CELEX number and a link to
EUR-Lex in Lithuanian. References are parsed from the official text; nothing is inferred.

Numbering conventions (EUR-Lex):
  directives, decisions, framework decisions: year/number   91/383/EEB, 2009/72/EB, (ES) 2019/944
  regulations before 2015:                    Nr. number/year  (EB) Nr. 338/97, (ES) Nr. 1303/2013
  regulations from 2015:                      year/number   (ES) 2016/679
CELEX = 3 + year + type letter (L directive, R regulation, D decision, F framework decision) + 4-digit number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import Act, Article

TYPE = r"(?P<type>direktyv[aąosų]\w*|reglament[aąouų]\w*|pagrindų sprendim\w*|sprendim[aąoųu]\w*)"
ORG = r"(?:\((?P<org>ES|EB|EEB|EEB, Euratomas|ES, Euratomas|EB, Euratomas|Euratomas)\)\s*)?"
NUM = r"(?P<nr>Nr\.\s*)?(?P<a>\d{1,4})/(?P<b>\d{1,4})(?:/(?P<suffix>EEB|EB|ES|TVR|TVR\)|Euratomas|EAPB))?"
RE_EU = re.compile(TYPE + r"\s+" + ORG + NUM, re.I)
EURLEX = "https://eur-lex.europa.eu/legal-content/LT/TXT/?uri=CELEX:{}"
KIND = {"L": "direktyva", "R": "reglamentas", "D": "sprendimas", "F": "pagrindų sprendimas"}


@dataclass(frozen=True)
class EuRef:
    celex: str
    kind: str        # direktyva | reglamentas | sprendimas | pagrindų sprendimas
    cite: str        # as written: "direktyva (ES) 2019/944"
    ident: str = ""  # the number part as written: "(ES) 2019/944", "91/383/EEB"

    @property
    def url(self) -> str:
        return EURLEX.format(self.celex)

    @property
    def short(self) -> str:
        """The citation as written in the source, nominative: 'Direktyva 91/383/EEB', 'Reglamentas (ES) 2016/679'."""
        return f"{self.kind.capitalize()} {self.ident}" if self.ident else self.cite


def _year(s: str) -> int:
    y = int(s)
    if y >= 1000:
        return y
    return 1900 + y if y >= 50 else 2000 + y


def find(text: str) -> list[EuRef]:
    """All EU act references in a text, in order of appearance, without duplicates."""
    out, seen = [], set()
    for m in RE_EU.finditer(text):
        t = m.group("type").lower()
        letter = "L" if t.startswith("direktyv") else "R" if t.startswith("reglament") else \
            "F" if t.startswith("pagrindų") or (m.group("suffix") or "").startswith("TVR") else "D"
        a, b = m.group("a"), m.group("b")
        org = (m.group("org") or "").upper()
        if len(a) == 4 and 2015 <= int(a) <= 2100 and (letter == "R" or m.group("nr")) and org in ("", "ES", "ES, EURATOMAS"):
            year, num = int(a), int(b)            # "(ES) Nr. 2024/3234": from 2015 the year comes first, "Nr." or not
        elif m.group("nr") or (letter == "R" and org.startswith(("EEB", "EB", "EURATOMAS"))):
            num, year = int(a), _year(b)          # "(EB) Nr. 338/97", "sprendimas Nr. 676/2002/EB": number/year
        else:
            year, num = _year(a), int(b)          # everything else: year/number
        if letter == "D" and not (m.group("org") or m.group("suffix")):
            continue  # "sprendimas 12/2019" without an EU marker is probably a national decision
        if not (1951 <= year <= 2100) or num == 0 or num > 9999:
            continue
        celex = f"3{year}{letter}{num:04d}"
        if celex in seen:
            continue
        seen.add(celex)
        out.append(EuRef(celex, KIND[letter], m.group(0).strip(), m.group(0)[len(m.group("type")):].strip()))
    return out


@dataclass
class Implemented:
    ref: EuRef | None  # None: an EU-related instrument without a standard CELEX (e.g. a 1995 convention)
    entry: str         # the annex entry text (title of the EU act as given)


def implemented(act: Act) -> list[Implemented]:
    """EU acts listed in the act's 'ĮGYVENDINAMI EUROPOS SĄJUNGOS TEISĖS AKTAI' annex(es)."""
    out, seen = [], set()
    for ax in act.main.annexes:
        if "EUROPOS SĄJUNGOS" not in (ax.title + " " + ax.header).upper():
            continue
        for b in ax.blocks:
            numbered = bool(re.match(r"^\d+\.", b.text))
            entry = re.sub(r"^\d+\.\s*", "", b.text)
            if entry.lower().startswith("neteko galios"):
                continue
            refs = find(entry)
            if not refs:
                if numbered:  # an EU-related instrument without a standard CELEX number
                    out.append(Implemented(None, entry))
                continue      # unnumbered lines without an EU act are headings/explanations
            first = refs[0]  # the entry's own act; later refs are "with amendments made by ..."
            if first.celex not in seen:
                seen.add(first.celex)
                out.append(Implemented(first, entry))
    return out


def mentioned(article: Article) -> list[EuRef]:
    return find(" ".join([article.title] + [b.text for b in article.blocks]))
