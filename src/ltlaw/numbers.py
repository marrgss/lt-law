"""Article / part / chapter numbers, including superscripts.

The open-data plain text flattens superscripts: article 21¹ is printed "211", CK 6.228¹ is
"6.2281", chapter XIX¹ is "XIX1", part 3¹ of an article is "31.". e-tar HTML keeps them as
<sup>, which we render as "21-1" (the spelling amending-act titles use too).

Decoding rule: numbers inside one sequence (articles of one act segment, parts of one
article, ...) only increase. A flattened token is read as the smallest valid number greater
than the previous one. "211" right after article 21 is 21¹; after article 210 it is 211.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


@dataclass(frozen=True, order=True)
class Num:
    """A sortable number: optional book (CK "6."), base, superscript (0 = none), letter (EU acts' inserted articles,
    "4a" after 4: D-037)."""
    book: int
    base: int
    sup: int = 0
    letter: str = ""

    def label(self, roman: bool = False) -> str:
        """URL/display form: '52', '21-1', '6.228-1', 'XIX-1', '4a'."""
        b = to_roman(self.base) if roman else str(self.base)
        s = f"{self.book}.{b}" if self.book else b
        return (f"{s}-{self.sup}" if self.sup else s) + self.letter

    def pretty(self, roman: bool = False) -> str:
        """Human form with a real superscript: '21¹', '6.228¹'."""
        b = to_roman(self.base) if roman else str(self.base)
        s = f"{self.book}.{b}" if self.book else b
        return (s + "".join("⁰¹²³⁴⁵⁶⁷⁸⁹"[int(c)] for c in str(self.sup)) if self.sup else s) + self.letter


def from_roman(s: str) -> int:
    total = 0
    for i, ch in enumerate(s):
        v = ROMAN[ch]
        total += -v if i + 1 < len(s) and ROMAN[s[i + 1]] > v else v
    return total


def to_roman(n: int) -> str:
    out = ""
    for v, r in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + r, n - v
    return out


def candidates(token: str) -> list[Num]:
    """All readings of a flattened token: '211' -> 211, 21¹, 2¹¹. Explicit '21-1' -> 21¹ only."""
    book = 0
    if "." in token:
        b, token = token.split(".", 1)
        book = int(b)
    if m := re.fullmatch(r"(\d+)(-?[a-z]{1,2})", token):  # an EU act's inserted article "4a" (D-037), "69-a" (2011/61 prints a second 69a so): exactly that
        return [Num(book, int(m.group(1)), 0, m.group(2))]
    m = re.fullmatch(r"(\d+|[IVXLC]+)(?:-(\d+))?", token)
    if not m:
        raise ValueError(f"not a number: {token!r}")
    head, sup = m.groups()
    if head.isdigit():
        if sup:
            return [Num(book, int(head), int(sup))]
        out = [Num(book, int(head))]
        for k in range(1, len(head)):
            if head[k] != "0":  # a superscript never starts with 0
                out.append(Num(book, int(head[:k]), int(head[k:])))
        return out
    return [Num(book, from_roman(head), int(sup or 0))]  # roman: split_roman made any sup explicit


def split_roman(token: str) -> str:
    """'XIX1' -> 'XIX-1' (digits glued to a roman numeral are always a superscript)."""
    m = re.fullmatch(r"([IVXLC]+)(\d+)", token)
    return f"{m.group(1)}-{m.group(2)}" if m else token


class Sequence:
    """Decodes a run of numbers that must increase (one per act segment / article / ...)."""

    def __init__(self) -> None:
        self.prev: Num | None = None
        self.ambiguous: list[tuple[str, Num]] = []

    def next(self, token: str) -> Num:
        token = split_roman(token)
        cands = candidates(token)
        if self.prev is None:
            # first number: a plain reading, unless explicitly superscripted
            pick = cands[0]
        else:
            greater = sorted(c for c in cands if c > self.prev)
            if greater:
                pick = greater[0]
            else:
                # numbering went backwards (a source error): take the plain reading, report it
                pick = cands[0]
                self.ambiguous.append((token, pick))
        self.prev = pick
        return pick
