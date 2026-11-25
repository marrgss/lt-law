# Target architecture (to-be)

Where the system should end up, why, and the steps from today's [ARCHITECTURE.md](ARCHITECTURE.md). Each step closes rows of the [accuracy register](ACCURACY.md) or a scaling limit, and none is started before the go/no-go in [ROADMAP.md](ROADMAP.md) asks for it, except the accuracy steps (T1–T3), which come first.

## End state in one paragraph
Every Lithuanian law in force (about 720 base laws, measured 2026-10-18), the main Government resolutions and the Constitutional Court rulings, one page per article. Each page carries a label that is right not only on the day we checked it but every day, because:
- amendments are found from what the laws *say*, not what their titles say;
- our own predictions are checked against every new official consolidation;
- labels change at midnight, not at the next build.

People, search engines and AI agents read the same static pages. Agents additionally get a small API, and an MCP server, over the same data.

## Principles (unchanged)
1. Never consolidate texts ourselves.
2. Uncertain means flagged.
3. Every word of law is in the HTML.
4. No keys, no sign-up.
5. No dependence on a personal computer.

## Target components

### T0. Use what the data already says (first; closes more than T1)
- Read every field the register provides: `pakeista` (dates a law was itself amended), `isigal_sal_lt` and `isigalioja_po_salygu` (conditional entry), `galioj_busena`, `pask_atitaisymas` (corrected publication).
- Refetch any cached text whose metadata changed.
- Read the Chancellery's TAR notes. Done 2026-10-18 (D-023).
- Report data problems back to the Chancellery: stuck `Dokumentas` texts (15 of 66 ended before today), the frozen `Suvestine`, character corruption.

### T1. Amendment graph instead of title matching (closes B1, B2, B5; helps B7)
Today, candidate amending laws are found by title. Target: a graph of *law → act → article → date* built from three sources:
1. the amendment notes in every consolidation (ground truth for the past);
2. **the text of every new law**, scanned for references to any scope act: "… kodekso N straipsnį pakeisti", "pripažinti netekusiu galios", "netenka galios";
3. the register's own relations data, if it is ever exposed.

A law that touches a scope act anywhere in its text becomes a candidate, whatever its title. New laws are few (a few per working day), so scanning all their texts is cheap.

### T2. Constitutional Court rulings (closes B3) — built 2026-10-21
The rulings are documents in the same dataset (`priemusi_inst` = Konstitucinis Teismas; 508 rulings).
- A ruling that declares a provision unconstitutional takes effect on its official publication, unless it sets a later date.
- Rulings naming a scope act and article mark that article "Nepatikrinta" until a consolidation reflects them, or "Gali būti pasenęs" when the provision is fully voided.

### T3. Prediction ledger and back-testing (makes the accuracy claim continuous) — built 2026-10-19 (`ledger.py`)
Every night, store each article's label and the evidence behind it. When a new official consolidation arrives, it is ground truth for the days it covers. Compare what we said on those days with what the Chancellery published:
- each "current" that turned out to be changed is a **silent error** found after the fact;
- each flag on an unchanged article is a false alarm.

This replaces the one-day e-tar check with a measurement that runs every day and needs no e-tar requests.

**Limits:**
- It sees only acts whose `Dokumentas` text moves forward, so it is blind where the risk is highest: the stuck texts of T0.
- `Dokumentas` skips intermediate versions.
- Renumbering breaks comparison by label.
- Ground truth for a day is a later consolidation whose start date is on or before that day.

So the published figure must say what it covers ("N tikrinimų, M klaidų, per 90 dienų, X aktų").

### T4. Labels that change at midnight (closes E1, most of E2)
Done in part on 2026-10-18:
- each label states until when it holds;
- `data-changes-on` and app.js flip it on the day;
- builds run just after midnight, with a backup run;
- `index.json` lists the changes due in the next 30 days.

Still to do: the same validity window in JSON-LD, and making the stated date the primary signal for agents that don't run JS.

### T5. Regression corpus for the date rules (hardens B4, B6)
Every entry-into-force article of every law since 2020 (a few thousand) with its parsed result, reviewed once and frozen as test data. A change to the date rules must leave the corpus unchanged or explain each difference. New wordings that the parser can't resolve go into a review queue, not into a guess.

### T6. Version store and dated permalinks (from D-009) — built 2026-10-23 as `/kaip-buvo/` and `date=` (D-029, D-030); feeds built
- The daily snapshots become an immutable, weekly-copied archive.
- A page per article *as of* a past date (`/ta/<tar>/str/<n>/2026-05-01/`, noindex) for citing "as of".
- Atom feeds of changes per act and site-wide come from the same diffs.

### T7. Serving beyond 20,000 files — done 2026-10-26 (D-032): option 1, the site as the Worker's static assets (100,000 files)
The full corpus is about 50–100k article pages, over the Cloudflare Pages free limit. Options, to be decided on measured traffic:
1. Workers static assets with a paid plan;
2. R2 + a small Worker that renders from per-act JSON;
3. split by first letter across several Pages projects.

Short aliases moved to Cloudflare Bulk Redirects (10,000 entries), not the Worker.

### T8. Agent interfaces — built 2026-10-21/23 (D-028): MCP and REST, in the MCP registry since 2026-10-25
- A per-article JSON (`…/str/<n>.json`) and a small read-only API: `get_article(act, n, date)`, `search`, `changes_since`.
- An MCP server over the same, listed in the MCP Registry.
- Same data, same labels, same evidence as the pages.

### T9. Monitoring — heartbeat (healthchecks.io) and `bin/checkup.py` built; no public status page beyond `status.json`
- An external heartbeat: a ping from each good build, and an alert when 26 hours pass without one.
- A public status page from `status.json`: last good build, data dates, ledger totals, fallbacks.
- The failed-run email remains the first alarm.

### T10. Article identity across versions
Renumbering ("Straipsnio numeracijos pakeitimas"), whole-act rewrites (VKĮ 2026-11-20) and splits mean a URL can later show a different article. Target:
- keep a mapping of old → new labels from the amendment notes;
- the old URL redirects, or shows "nuo D šis straipsnis yra N";
- dated permalinks (T6) keep the old text citable.

### T11. Tables, formulas, annexes
- Take tables and formula images from the register's own HTML or the `Priedas` model, where the open data provides them.
- Otherwise each affected page points to e-tar (done for formulas, 2026-10-18).
- Annex currency: assess annexes like articles.

## Scope
"Every law in force" means the base laws whose register state is "galioja" (about 720), excluding:
- amending, ratification and approval laws;
- individual acts naming people.

Government resolutions, ministers' orders and the energy regulator's acts are in by area (energy first, D-033/D-034); more by search demand; municipal acts are out of scope.

## Gap from today
| Area | As-is | To-be | Step |
|---|---|---|---|
| Finding amendments | titles | titles + full text of new laws + notes graph | T1 |
| Court rulings | tracked (2026-10-21) | tracked from the same dataset | T2 ✓ |
| Proof of accuracy | e-tar check by hand after every expansion; ledger nightly; back-test 2023–2025 | daily back-test against new consolidations + occasional e-tar check | T3 (mostly) |
| Label timing | changes at the 03:30–04:30 build | changes at midnight | T4 |
| Date rules | unit tests for known forms | frozen corpus of all entry articles since 2020 | T5 |
| History | `/kaip-buvo/`, `date=`, Atom feeds (2026-10-23) | immutable archive, dated permalinks, feeds | T6 ✓ |
| Scale | 1,666 acts, ~117k files on two Workers, room for more Workers (2026-11-26) | ~720 laws + resolutions, 50–100k pages | T7 ✓ (serving); corpus growing |
| Agents | data.json, articles.json, /api/v1, REST, MCP (registry) | per-article JSON, API, MCP | T8 ✓ |
| Monitoring | failed-run email, status.json, heartbeat, checkup | heartbeat, status page | T9 (mostly) |

## Order
1. **T0** (what the data already says), then **T3 ledger** (measurement), the rest of **T4** (validity window), then **T1 graph**: accuracy first. These make every later expansion safe.
2. **T5 corpus**, **T2 court rulings**, **T10 article identity**, **T11 tables**.
3. Launch, measure (ROADMAP go/no-go).
4. **T6 history and feeds**, **T9 monitoring**.
5. Only on "go": **T7 scale**, then **T8 API and MCP**.

Each step gets a decision entry (D-0xx) and updates the accuracy register.
