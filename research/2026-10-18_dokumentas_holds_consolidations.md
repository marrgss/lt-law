# Dokumentas.tekstas_lt is the newest consolidated text, not the original (2026-10-18)

Found while checking whether Dokumentas alone is enough. This **corrects** earlier notes that called Dokumentas "acts as originally published".

## Evidence
For base acts, the `Dokumentas.tekstas_lt` text starts with "Suvestinė redakcija nuo X [iki Y]" and carries the full amendment notes. Compared with e-tar's version in force today (`data/etar/`, fetched 2026-10-18):

| Act | Version held in Dokumentas (its own header) | e-tar version in force today | Amendments in Dokumentas but not in e-tar's current version |
|---|---|---|---|
| GPMĮ | 2026-06-11 – 2026-12-31 | same | none (identical lists, 49) |
| DK | from 2027-01-01 | 2026-06-07 – 10-31 | XV-1058, XV-1082, XV-1125 (adopted June 2026, in force later) |
| CK | from 2027-11-01 | 2026-09-27 – 12-08 | XV-1080 |
| PVMĮ | from 2029-07-01 | 2026-07-01 – 12-31 | XV-1036 |
| ANK | 2027-01-02 – 2027-04-30 | 2026-10-01 – 10-31 | XV-1144, XV-1149 |
| VPĮ | 2026-11-01 – 2026-12-31 | (not fetched) | already includes XV-1197, published **2026-10-01** |

## What it means
- **Dokumentas is fresh in content.** Every amendment we checked is applied, including one published 16 days earlier (VPĮ). The Chancellery's consolidation work *is* reaching open data, but only as **one version per act**: apparently the most recently prepared one, which is often a **future** version.
- **`Suvestine` is still frozen** (2025-05). So the open data has: old version history (to May 2025), plus the newest prepared version (today). The versions in between, including the one in force today when the newest is a future one, are missing.
- **For an act whose newest version has already started** (GPMĮ now, VPĮ from 11-01), the open data gives the current text. No e-tar needed.
- **For an act whose newest version is a future one** (DK, CK, PVMĮ, ANK today), the open data gives tomorrow's law, not today's. Showing it as current would be wrong in the other direction.
- **If we snapshot Dokumentas daily from now on, we build our own version history.** Each newly prepared consolidation gets archived as it appears. We still lose versions that are prepared together (one amending act with several entry dates) or superseded before our next snapshot.
- Never-amended acts have no header. Their Dokumentas text is the original, which is also their current text.

## Open questions
- What exactly is the selection rule? The ANK row holds 2027-01-02–04-30, not the later 2027-05-01 or 2028-01-10 versions, so "latest valid_from" doesn't fit. "Most recently prepared" is a guess.
- How many in-force acts currently hold a future version? Measuring that needs the headers of all texts, which is a large download. For the v1 scope (~30 acts) it's cheap.
- The letter is unaffected: `Suvestine` really is frozen. A follow-up could ask whether Dokumentas always holds the most recently prepared version.

## Recovering today's text from a future-dated Dokumentas version (test, 2026-10-18)
**Method:** an article is "current" if no amending law listed in its notes has `isigalioja` > today. In that case the future version's article text should equal today's. Checked against e-tar's in-force text (`data/etar/`), comparing normalised text with the notes removed:

| Act | Articles compared | Predicted current | of which identical to e-tar | **wrongly predicted current** | Flagged pending (all really differ) |
|---|---|---|---|---|---|
| DK | 256 | 216 | 214 | **2** (23, 148) | 40 |
| ANK | 692 | 685 | 681 | **4** (99, 241, 369, 466) | 7 |
| PVMĮ | 131 | 126 | 126 | 0 | 5 |
| CK | 2007 | 2002 | 1992 | **10** (3.217, 6.291–6.299) | 5 |

**Cause of the DK misses: staged entry into force.** XV-969 Art. 23 says the law takes effect on 2026-06-07 *except* its Arts. 2 and 17, which take effect on 2027-01-01. The metadata field `isigalioja` holds only the main date.
**Fix for P2:** parse each amending law's "Įstatymo įsigaliojimas" article (exceptions with their dates) and map "N straipsnis. X straipsnio pakeitimas" to the target article. The ANK and CK misses are still undiagnosed: possibly chapter-level notes, or the same staged-date pattern.

**Status:** promising (~99.5% correct on 3,000 articles, no false alarms), but **not safe to publish** until the misses are 0 on the validation set. Any article we're unsure about is flagged with a link to e-tar. We never write text ourselves; we only decide whether an official text can be shown as current (D-002 holds).
