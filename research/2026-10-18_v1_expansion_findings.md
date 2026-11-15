# v1 expansion to 34 acts: findings (2026-10-18)

Scope: `scope/v1.yaml` (34 acts: Constitution, 6 codes, tax, business, social, land/construction, energy).

## Results
- `bin/validate_scope.py`: **34/34 identical to e-tar's same version**.
- `bin/validate_currency.py`: **0 silent errors on 7,425 articles**: 6,904 correctly current, 521 flagged, of which 186 were unnecessary (2.5% of all articles).
- EU references (`ltlaw.eu`): 383 implemented EU acts from annexes, 234 mentioned in article texts. Every numbered annex entry maps to exactly one EU act, except one 1995 convention without a standard CELEX number, which is shown as text.

## Source and data findings
1. **The Constitution in Dokumentas is the original 1992 text** (no consolidation header, 0 amendment notes). We fall back to the newest Suvestine consolidation (version from 2022-05-22), which validates against e-tar.
2. **Editorial residue before the version header** ("Projektas XXXX XX XX Nr. –––––", "Redagavo: [vardas pavardė] (1997…") in 10 acts. The parser now looks in the first 12 lines.
3. **VTAĮ article 48 is printed twice, with no dates**, in both the open data and e-tar: an old copy (XI-1620, 2011) and the current one (XV-921). Which one applies can't be told from the text, so it's flagged "Nepatikrinta" and both texts are shown.
4. **The metadata marks the 1994 ABĮ (I-528) as "galioja"** although the 2000 law replaced it. The seed pins VIII-1835.
5. **CPK vs XIV-2317/XV-1028 (possible inconsistency in the official consolidation).**
   - XV-1028 (in force 2026-06-27) changed XIV-2317's Art. 43(4): its arts. 1, 8, 10, 11, 12(1), 19, 25, 38, 39 now enter on **2027-09-01**.
   - e-tar's CPK versions from 2026-07-01 and from 2026-09-01 are attributed to XIV-2317 and apply its changes to e.g. CPK 82 and 601.
   - Our reading: those consolidations apply postponed changes. We don't decide this. Every CPK article touched by XIV-2317 is "Nepatikrinta" ("įsigaliojimo datas pakeitė XV-1028").
   - Possibly worth a short question to the Chancellery (maintainer's call).

## Method changes this round (currency)
- Change dates per article and per part, from each amending law's entry article:
  - lists, ranges ("16–20") and part-level dates ("1 straipsnio 2 dalis");
  - no general date sentence;
  - the date taken right after "įsigalioja", not a later deadline in the same sentence;
  - editorial notes stripped first.
- Symmetric rule:
  - future stored text (S > today): "Įsigalios" if the article changes in (today, S];
  - past/current stored text: "Pasenęs" if it changes in (S, today].
- Per article: a law in force that targets the article but is absent from its notes means "Pasenęs". This covers consolidation lag, e.g. VTAĮ/XV-921 and EEĮ/XV-1153.
- Conditional entry (a part enters "tą dieną, kai …", no date) means "Nepatikrinta" when the stored version isn't today's.
- An amending law whose own entry dates were changed by a later law adopted in the last year means "Nepatikrinta" for the articles it targets.
- Candidate laws are chosen by any part-level date between S and today, or by publication in the year before today.
