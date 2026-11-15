# Architecture

How the site is built today (2026-11-11). The reasons behind each choice are in [DECISIONS.md](DECISIONS.md) (D-xxx); what is not built yet is in [ROADMAP.md](ROADMAP.md).

## Goals, in priority order
1. **Correct and honest.** Every page says the text is unofficial, links to the official text on e-tar.lt, gives the version dates and when the data were last checked. An article is called "in force today" only when that can be established (D-010).
2. **Readable by any machine.** Static HTML, one URL per article, the full text in the HTML, JavaScript optional (D-001, D-017).
3. **Small enough to be right.** 1,425 acts (2026-11-14), each validated against e-tar before it goes in (D-003, `bin/add_acts.py`).
4. **Survives neglect.** No server of our own; a scheduled job; pages say when their data are old.
5. **No sign-up, no keys, free to read** (D-005). Hosting costs the Workers Paid plan ($5/month, D-032).

## Overview

```
 data.gov.lt (TAR open data, CC BY 4.0)          GitHub Actions, nightly (.github/workflows/nightly.yml)
 ┌──────────────────────────────┐               ┌──────────────────────────────────────────────────────┐
 │ Dokumentas: every act with   │   relay       │ build job (bin/nightly.py)                           │
 │ its newest consolidation     │◄──Worker──────│  1 new laws → data/state/laws.jsonl (no gaps)        │
 │ Suvestine: consolidations,   │  (Stockholm,  │  2 act texts → data/dokumentas/<id>/<date>.json      │
 │ frozen since 2025-06         │   D-019)      │  3 parse, assess currency, render ~100k files        │
 └──────────────────────────────┘               │  4 per-act checks; fallback to previous snapshot     │
                                                │  5 status.json, manifest; state → release asset      │
 e-tar.lt: validation only, run by hand (D-004) │ deploy job: wrangler (pinned) → Workers lt-law-mcp + │
                                                │   lt-law-site-2 (the site split by route, D-051)     │
                                                │ keepalive job: keeps the schedule enabled            │
                                                └──────────────────────────────────────────────────────┘
 Readers, bots, agents ──► Cloudflare: static files (free) │ /mcp, /api/*, /kaip-buvo/ → the Worker's code
                                                            (R2 bucket lt-law-history, EU: past versions)
```

## 1. Sources
- **`Dokumentas.tekstas_lt`** is the primary text: the newest consolidation the Seimas Chancellery prepared, refreshed within days, one version per act, often dated in the future (D-009). Each day's text is archived only when it changed; the archive is our own version history.
- **`Suvestine`** holds older official consolidations but stopped being refreshed in mid-2025. It is used for acts whose `Dokumentas` text is not a consolidation (the Constitution and four laws, listed in `status.json`), and as one of the places where today's text can be found (D-016).
- **Law metadata** (number, title, adoption, publication, entry into force) for every law, kept in `data/state/laws.jsonl`. Each night the newest 3,000 acts are merged; if they don't reach back to the newest act we already had, the update pages back until it does, so an outage can't leave a gap.
- **Amending-law texts**, fetched once per law (adopted since 2020), for their entry-into-force articles; likewise the amending resolutions and orders of the rules in scope.
- **The energy regulator's decisions** (D-034): metadata in `data/state/decisions.jsonl` (the regulator's newest 300 merged nightly), each decision's text fetched once into `data/decisions/` (its price annexes are not in the open data).
- **EU acts** (D-037): EUR-Lex's XHTML of the newest consolidation (`eurlex.py`, converted to the same plain text the
  parser reads; `CONVERTER` versions the conversion), fetched when an act is added and when EUR-Lex lists a newer version.
- **e-tar.lt** is used only by the validators, run locally and rarely (D-004). Their dated results are in [`validation/`](../validation/).
- **Seimas votes** (D-054, in the MCP tools since 2026-11-15): the Chancellery's
  `datasets/gov/lrsk/balsavimai` (`Balsavimas`, `IndividualusBalsavimai`) on the same open-data portal; section 8.

The pipeline runs in GitHub Actions only (D-006). data.gov.lt refuses requests from outside Europe, so the build job fetches through a small Cloudflare Worker pinned to Stockholm (`worker/`, D-018/D-019). It forwards only read requests for the TAR dataset, and only with a shared key.

## 2. Parsing (`src/ltlaw/parse.py`, `numbers.py`)
Plain text from the open data becomes a tree: segments (approval law, annexed code), headings (knyga, dalis, skyrius, skirsnis), articles with parts and points, amendment notes with references to amending laws, dated variants ("N straipsnio redakcija nuo …"), annexes and signatures. Flattened superscripts ("211" = 21¹, "6.2281" = 6.228¹) are decoded by a monotonic-sequence rule. The header gives the version period, whole-act rewrites ("Nauja redakcija nuo …") and a whole-act repeal ("Įstatymas netenka galios …").

Check: `bin/validate_scope.py` compares every article with e-tar's text of the same version (319 of 319 identical, 2026-10-27).

**Rules made of points (D-025, D-033, D-034).** Rules approved by a Government resolution (KET), a minister's order or the energy regulator's resolution have no articles: `points.py` reads the approving act, the approved rules (top-level points as units, sub-points as anchors, chapters) and their annexes into the same structures. The scope says which kind and issuer (`kind: Įsakymas`, `issuer`, from the register via `bin/resolve_scope.py`). Their numbers restart every year, so references to amending acts are keyed `number/adoption date` (B58); `currency.parse_amending_resolution` reads their items ("šio nutarimo / šio įsakymo") and entry clauses. Some rule sets are written in articles (VERT's TSO methodologies: `unit: straipsnis`, D-052). Older rule sets head their chapters "II. SĄVOKOS" and may number sections from I again inside a chapter: read as chapters and sections (D-053). A point printed out of place (the amended 191 after 118) is kept where printed and flagged; the numbering goes on from the point before it.

## 3. Which text applies today (`currency.py`, `today.py`)
Each article gets one state for the build day (Europe/Vilnius):

| State | Label | Meaning |
|---|---|---|
| current | Galioja šiandien | every amendment in its notes is in force for it by today, and no law already in force is missing from the text |
| pending | Įsigalios D | the text shown is adopted but applies only from D; today's text is not in the open data |
| outdated | Gali būti pasenęs | a law already in force changes this article, but the stored text doesn't include it yet |
| unknown | Nepatikrinta | could not be established (conditional entry into force, re-dated laws, duplicated article…) |
| repealed | Neteko galios D | the article, or the whole act, is no longer in force |

Entry dates come from each amending law's own entry provisions ("įsigaliojimas", "baigiamosios/pereinamosios nuostatos"), including staged, part-level and conditional dates ("…, jeigu …"), ranges, the next-day default and laws that re-date other laws. A law later amended by another law is refetched. The Chancellery's **TAR notes** inside an article are read as well: a part with its own later date, a conditional start, or two wordings printed side by side (D-023). Anything uncertain is flagged, never shown as current (D-010).

Articles in force today that the stored text lacks get pages too:
- from the consolidation valid today, with that text's own labels (VKĮ 21¹ before the 2026-11-20 rewrite; ABĮ 30³);
- as a stub saying the text isn't in the open data yet, when only the adding law is known (PMĮ 30³).

The look-back for candidate laws is anchored on the day the stored version was first seen, so labels don't drift as days pass.

When the stored text is a future version, today's text is looked for in older official consolidations (our archive, then Suvestine). One is used only if every law it lacks takes effect after today (D-016). The page then shows today's text first and the future text in its own section, verbatim.

Checks:
- `bin/validate_currency.py` compares every "current" label with e-tar's version in force, and counts any in-force article without a page (0 silent errors on 21,834, 2026-10-27).
- `bin/validate_today_text.py` checks every recovered text (705 of 705 correct).
- The nightly job also reports version dates that no detected law explains (`health.unexplained_version_dates` in `status.json`).

## 4. Output (`render.py`, `templates/`)
- `/ta/<tar_kodas>/` act contents (split into parts above 300 articles), with act-level notices (e.g. articles added by a law but not in the text yet); `/ta/<tar_kodas>/str/<n>/` one article (`52`, `21-1`, `6.228-1`), with anchors `#d2` (part) and `#d2-p3` (point); `/ta/<tar_kodas>/priedas/<n>/` annexes.
- Short aliases `/dk/52/` and name aliases (`/vandens-istatymas/5/`) → canonical, as Cloudflare Bulk Redirects (one per act, `bin/cf_redirects.py`); `www` → the domain.
- `/sritis/<area>/`: the acts of a topic (`scope/areas.yaml`); `/paieska/`: search.
- `/kaip-buvo/?u=<article>&data=<date>` (the Worker, D-030): the official consolidation of an article in force on a past day since 2020, with its periods and "Kas pakeista".
- `/vert/` and `/vert/<TAR>/` (D-034, `decisions.py`): the regulator's electricity decisions, labelled from the period in their title and their series, with each decision's text and the e-tar link for its annexes; `/api/v1/vert.json`.
- `/mcp`, `/api/search|article|acts|contents|upcoming` (the Worker, D-028): MCP and REST for agents over `/api/v1/`; `date=` answers from the R2 history; annexes as `priedas-<n>` (D-043).
- Article page: breadcrumbs, the status badge and the date until which it holds ("Žyma teisinga iki D"), source and dates, warning box if needed, the text with amendment notes linked to e-tar, the future text and a word diff when there is one, EU acts mentioned, previous and next.
- Machine-readable, all describing the same text as the page:
  - JSON-LD `Legislation`: identifier, `legislationDateVersion`, `legislationLegalForce`, licence;
  - `data-state` and `data-status-day` on `<main>`;
  - `/ta/<tar_kodas>/data.json`: the whole act, each article exactly as shown;
  - `/index.json`, `/llms.txt`, `/search-index.json`, `/status.json`;
  - `sitemap.xml` with `lastmod` from content changes.
- EU law: the act's own annex of implemented EU acts and EU acts named in an article, as CELEX numbers linked to EUR-Lex (D-014).
- `noindex` and `robots.txt: Disallow` unless the build is `--indexable` (D-012).
- JavaScript (`/app.js`) only adds search, a remembered sidebar, "copy citation" and a stale-page warning (D-017).

**Cross-references (`xref.py`).** On article pages, references inside the same act become links ("šio kodekso 52 straipsnio 2 dalyje" → `/str/52/#d2`), only when the target exists; the words are unchanged (data.json keeps plain text). The nightly gate fails a build with a link that has no target.

## 5. Freshness
- The footer of every page gives the status day and the date the data were last checked.
- A label that changes on a known date says so on the page; `data-changes-on` lets app.js flip it on that day, and `index.json` lists the changes due in the next 30 days.
- If the data are more than 2 days old at build time, every page carries a red banner.
- `app.js` adds a warning when a page's status day is more than 2 days before today. This covers a stopped pipeline or a cached copy.
- An act whose new text fails the checks keeps its previous text, and `status.json` says so.

## 6. The nightly job (`bin/nightly.py`, `.github/workflows/nightly.yml`)
Scheduled at 22:10 UTC (00:10 winter, 01:10 summer time in Vilnius) with a backup at 01:30 UTC, or run by hand (with `accept` for an expected big change).

**Deploy (D-032, D-051):** the site is static files on two Workers: `lt-law-site-2` (files only) has the route `/ta/1*`, the main Worker `lt-law-mcp` everything else and the MCP/REST code; `bin/split_site.py` splits the build by the routes.

**Plan job (D-050):** a scheduled run builds only when the live site is two days old (or its day can't be read), or when `api/v1/upcoming.json` has a label change after the live day and by today; otherwise it pings the heartbeat and stops (~10 s). So a build at least every second day: app.js's box for labels more than 2 days old stays off unless a build failed.

**Build job:**
1. Restore the state (the `state` release asset, about 165 MB).
2. Check the relay.
3. Run the tests.
4. Fetch, build, check.
5. Save the state; hand the site to the deploy job.

**Per-act checks:** articles parsed; no more than 2% lost unless the act was rewritten as a whole; the version not moving backwards. A failing act is rebuilt from its previous snapshot. If that fails too, the run fails and nothing is deployed.

**Site checks:** every article page has text or is marked repealed; the laws list didn't shrink and is complete.

**Ledger** (`ledger.py`, D-024): each article's label and text fingerprint go on record nightly. When an act's text changes and the new consolidation covers past days, the past labels are checked against it. Totals are shown in `status.json` → `ledger` and on `/apie/`.

**Health** in `status.json`: fallbacks, unexplained version dates, articles not in the stored text, notices, amending-law fetch failures and refreshes, corrupted characters, unrendered text, acts on the frozen Suvestine.

**Regulator decisions** (D-034): new ones merged, texts fetched once within 5 minutes a night.

**Fetch budgets:** data.gov.lt is often slow: the Suvestine table gets one try of 60 s (then skipped for the run), act texts 20 minutes (acts whose amendment took effect in the last 60 days and whose stored text predates it first, then longest unchecked), today's-text versions 10 minutes. A new act that can't be built, or has no text yet, waits for the next night; an existing one keeps its previous text. A run takes 10–40 minutes. Amending resolutions/orders of the rule sets (a slow title search per act: 45 minutes on 2026-10-28) are searched for never-searched acts first, then each act about weekly, within 10 minutes; regulator decision texts one try each, 5 minutes.

**Deploy job:** wrangler from `deploy/package-lock.json`, read-only repository access. With `SITE_ON_WORKER` it deploys the two Workers with the site as static assets (`worker-mcp/wrangler.site.toml` and `wrangler.site2.toml`, 100,000 files each; 2026-11-11: 55,062 and 45,005). Pages, the old way back, takes 20,000 files and keeps the newest site that fit (2026-10-26).

**Adding acts and the state** (OPERATIONS: Releases): `bin/add_acts.py` runs the whole procedure locally against a copy of the state; `bin/state_asset.py pack` and `upload` replace the asset. The nightly saves the state at its end, so the local data must first take in the asset's (a build ahead); a parser fix that drops a live act's articles needs `--accept` at the gate and the act's new labels in the uploaded manifest, or the nightly's gate stops the build.

**Keepalive job:** re-enables the schedule, which GitHub would otherwise switch off after 60 days without commits.

Actions are pinned by commit SHA, and no job keeps credentials on disk.

Operating it: [OPERATIONS.md](OPERATIONS.md). Accounts, data locations and limits: [INFRASTRUCTURE.md](INFRASTRUCTURE.md).

## 7. Limits and cost
- Worker static assets (Workers Paid): 100,000 files per version per Worker (the site has ~100k over two Workers, D-051), 25 MiB per file; requests for static files are free. A third Worker is a route and a config away (`bin/split_site.py`).
- The Worker's own requests (MCP, REST, dated pages, unmatched paths): 10 million a month included; a CPU cap of 50 ms a request; a rate limit (50 requests per 10 s per address) and a firewall rule keeping crawlers off `/kaip-buvo/`.
- GitHub Actions: 2,000 free minutes a month (private repository), budget $5 with a stop; a build every second day (D-050).
- Cost: the domain (about €10 a year) and Workers Paid ($5/month); usage alerts on Workers requests, CPU and R2 reads.

## 8. Seimas votes (D-054; MCP tools, released 2026-11-15)
A second part next to the acts: how the Seimas voted, from the Chancellery's open data on data.gov.lt.
- **Data:** `Balsavimas` (one row per vote: term, sitting, agenda item with the draft number "Nr. XVP-1885" and the law it
  amends "Nr. XIV-1381", what was voted on, for/against/abstain, the result, the lrs.lt record) and
  `IndividualusBalsavimai` (one row per MP and vote: 1 for, 2 against, 3 abstained; MPs who didn't vote have no row). The
  totals are a day behind, the individual votes a few days.
- **Sync** (`bin/fetch_votes.py`): one term at a time into `data/seimas/<term>/`, the whole term each run (~25 requests,
  pages of 20,000 rows); the votes the open data hold without a term (no agenda item, no totals) taken in by date. A short
  answer (fewer votes or individual votes than the last fetch, beyond 0.5%) never replaces a full one.
- **Nightly** (released 2026-11-15): the newest term with the other fetches, through the relay (its
  allowed paths: the acts' and the votes' datasets); the vote files built into the site after the acts' pages
  (`bin/build_votes.py`). Either failing is a warning, never a stop: the acts' build doesn't wait on the votes, and the
  tools say what is missing. On-switch: `data/seimas` in the state asset (earlier terms are closed and kept there; the
  nightly fetches only when it finds the folder).
- **Terms:** the POC has terms 10 (2024–2028) and 9 (2020–2024). A tool without `term` takes the term of its dates, else
  the current one; an MP not in the current term is answered from the newest term they voted in, said so. An MP's id
  (`seimo_nario_id`) is the term's own; `asmens_id` is the same person in every term (`persons.json`, `person`).
- **Votes without an agenda item** (12% of each term: no item, no record link, in term 10 no totals either): found only by
  date; a search by words, draft or act says how many such votes its dates hold (the partnership bill's first vote,
  2021-05-25, 63/58/7, is one). The result "P" is not explained by the source: the answer gives the arithmetic only.
- **Served** as JSON by the Worker (`api/v1/seimas/`), not as HTML pages: per-vote pages would add 76,000 files. MCP tools
  `search_votes` (words, draft number, law number or name), `get_vote` (every MP's choice), `mp_votes` (an MP's votes,
  optionally on matching items).
- **Linked to the acts:** a vote names the law it amends ("Nr. XIV-1381"), matched to the act on the site by its number;
  later, the adoption vote matched to the amending law (title and day), shown on the article pages it changed.
- **Not in the data:** factions, individual votes for consensus decisions and secret ballots, presence. Said in every answer.

## 9. Repository map
```
src/ltlaw/      source, parse, points, numbers, currency, today, decisions, eu, eurlex (EUR-Lex), xref, definitions,
                fulltext, ledger, feeds, render, api (the static API), scopecheck (a new act's name and document),
                validate, etar (validation only)
src/ltlaw/templates/   Jinja2 pages and app.js
bin/            nightly.py, build_site.py, split_site.py (the two Workers), add_acts.py (the procedure for new acts),
                rank_candidates.py, fetch_new_acts.py, snapshot_scope.py, fetch_meta.py, resolve_scope.py,
                validate_scope.py, validate_currency.py, validate_today_text.py, diagnose_silent.py,
                state_asset.py (the nightly's data), cf_redirects.py, check_mcp.mjs, check_search_ranking.mjs,
                checkup.py, mcp_registry.py, export_history.py / upload_history.py (R2), compact_state.py,
                research tools (analyze_staleness, crosscheck_versions, backtest_history, etar_*)
scope/          v1_seed.yaml (edit this) → v1.yaml (generated)
tests/          unit and golden tests (pytest)
validation/     dated results of the e-tar checks
worker/         the fetch relay (Cloudflare Worker)
worker-mcp/     the site's Worker: static assets, MCP/REST, dated pages (wrangler.site.toml; wrangler.toml = without the site)
deploy/         pinned deploy tooling (wrangler)
research/       dated research notes with sources
```
