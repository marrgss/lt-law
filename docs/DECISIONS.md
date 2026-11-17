# Decisions (append-only)

Each decision keeps its date. Later decisions amend or supersede earlier ones instead of rewriting them; wording was tidied once for publication (2026-10-18) without changing any decision.

## D-001 (2026-10-17): Static, server-side-rendered HTML per article is the primary product, and MCP is secondary
AI assistants reach the web through search and then fetch, and those fetchers don't execute JS. An MCP server only helps people who install it.
Evidence: `research/2026-10-17_seo_ai_discoverability.md`.

## D-002 (2026-10-17): Never consolidate texts ourselves
We mirror the consolidations the Chancellery prepares and flag pending amendments. The UK needed a decade and paid editors to clear its consolidation backlog, and errors carry liability.

## D-003 (2026-10-17): v1 is about 30 normative codes and laws, not the whole register
This avoids the crawl-budget trap, keeps parse validation feasible, and fits a free static host. It also keeps individual acts that name people out of scope.
Red-team findings #6 and #8.

## D-004 (2026-10-17): No e-tar fetching at scale without the Chancellery's written view
e-tar HTML isn't covered by the CC BY 4.0 dataset licence, and the database right is separate from copyright. The preferred sources, in order:
1. the Chancellery refreshing the dump;
2. a free data-receipt contract;
3. polite fetching of the ~30 acts.

The fallback is an honest stale-data banner.

## D-005 (2026-10-17): No API keys or registration, ever
Abuse is handled with edge rate limits and bulk dumps. A second-model critique suggested keys, and we rejected that because it contradicts the project's purpose.

## D-006 (2026-10-17): Production never depends on a personal computer
No unattended jobs run on personal machines, and a public service mustn't depend on a home PC. CI (GitHub Actions) does the nightly work. The PC is used only for one-off snapshots and experiments.

## D-007 (2026-10-17): No LLM-generated text on pages in v1
Liability, and LLM output in Lithuanian legal language is not reliable enough. LLMs may help with offline tooling only.

## D-008 (2026-10-17): Examples lead with the Labour and Civil Codes
Examples and the pilot use DK and CK: the codes people ask about most. The project is independent and personal.

## D-009 (2026-10-18): Dokumentas newest consolidation is the primary text source, archived daily
`Dokumentas.tekstas_lt` holds the newest consolidation the Chancellery prepared. It's fresh within days, but there's one version per act and it's often future-dated (`research/2026-10-18_dokumentas_holds_consolidations.md`). We use it first:
- its header gives the validity period;
- a version that has already started is shown as current;
- a future one is shown as "įsigalios nuo …".

Archiving every daily snapshot builds our own version history from now on. e-tar fetching (D-004) is needed only for the in-between version that is in force today when the newest one is future-dated.

## D-010 (2026-10-18): Uncertain means flagged; never shown as current
An article is shown as "Galioja šiandien" only if both hold:
- every amendment in its notes, and in its headings' notes, is in force for it by today, with staged entry-into-force dates resolved from the amending law's text;
- no law already in force is missing from the stored text.

Anything else is "Įsigalios …", "Gali būti pasenęs" or "Nepatikrinta" (and, since D-020, "Neteko galios …"), with a link to e-tar. The measured cost is 1 false alarm per 3,639 articles; the requirement is 0 silent errors (bin/validate_currency.py).

## D-011 (2026-10-18): Amending laws adopted before 2020 use their metadata entry date
We don't fetch their texts, to keep load on data.gov.lt low. That their staged parts don't fall after today is an assumption; bin/validate_currency.py checks it against e-tar when run by hand (0 silent errors on 2026-10-18). Revisit if a miss appears.

## D-012 (2026-10-18): Every build is noindex unless --indexable
Pages carry `<meta name="robots" content="noindex">` and robots.txt says `Disallow: /`, so a test deploy can't be indexed. Launch flips one flag (P3).
Contents pages are split by book, part and chapter to at most 300 articles each (< 100 KB).

## D-013 (2026-10-18): Energy laws are in scope
The energy laws (Energetikos, Elektros energetikos, Gamtinių dujų, Atsinaujinančių išteklių energetikos, Šilumos ūkio) are normal scope items. Examples still lead with DK and CK (D-008).

## D-014 (2026-10-18): EU sources come from the act's own annex, linked by CELEX
"Which EU act is this based on" is answered from the annex "ĮGYVENDINAMI EUROPOS SĄJUNGOS TEISĖS AKTAI" of the official text, and from EU acts mentioned in an article's text. Nothing is inferred or matched by topic.
- Each reference becomes a CELEX number and links to EUR-Lex in Lithuanian.
- Entries without a standard CELEX (e.g. a 1995 convention) are shown as text without a link.
- Repealed entries ("Neteko galios") are skipped.

Coverage on the first 5 codes: every numbered annex entry yields exactly one EU act, or is a repealed entry or that one convention.

## D-015 (2026-10-18): v1 scope is generated from a seed list
`scope/v1_seed.yaml` (abbreviation + exact title, or the law number for codes) goes through `bin/resolve_scope.py` to produce `scope/v1.yaml`. Resolution is by exact match against the open-data metadata and never guessed; ambiguous seeds fail loudly. Example: the 1994 ABĮ I-528 is wrongly marked "galioja" in the metadata, so the seed pins VIII-1835.

## D-016 (2026-10-18): Today's text may come from an older official consolidation, never from our own edits
For an article whose stored text isn't today's, we look in our archive of earlier Dokumentas snapshots and in the Chancellery's frozen Suvestine consolidations. A candidate is used only if both hold:
- the currency rules say the article is current in it;
- every law the newer stored text lists for the article, but the candidate lacks, takes effect only after today.

`bin/validate_today_text.py` checks every such text against e-tar: all correct on 2026-10-18 (169 of 169 on the first 34 acts; 218 of 218 on 66 acts after D-020). The page shows today's text first and the future text verbatim in its own section; the word diff sits only in a collapsed "Kas keičiasi" section.

## D-017 (2026-10-18): JavaScript as progressive enhancement only
One shared `/app.js` (defer, no framework) adds three things:
- search over `/search-index.json`;
- remembering a hidden sidebar;
- "Kopijuoti citatą".

Every word of legal text and every link is in the server-rendered HTML, so AI fetchers and crawlers, which don't run JS, see the complete page. The site check changes from "no scripts" to "only /app.js, and the page text is complete without it".

## D-018 (2026-10-18): data.gov.lt rejects GitHub Actions; fetching must run elsewhere
*Superseded by D-019 (the cause turned out to be location: non-European traffic is refused).*
Measured in three CI runs: every request from GitHub's runners returns HTTP 500 with an HTML error page, even data.gov.lt's home page, while the same requests from a home connection in Lithuania succeed. Most likely a firewall rule against cloud data-centre addresses.
- **Until fixed:** the nightly job still rebuilds every night from its cached data, so labels move with the date. `status.json` records the warning and data dates, so freshness is visible.
- **Options, in order of preference:**
  1. A Cloudflare Worker on a cron schedule fetches the small daily delta (new laws plus 66 act texts) into R2, and GitHub Actions reads it from there. Free; whether data.gov.lt accepts Cloudflare's addresses must be tested once the account exists.
  2. Ask the data.gov.lt operators (atviriduomenys@vssa.lt) whether automated read-only access from cloud CI is blocked on purpose, and whether it can be allowed.
  3. A small EU VPS (about €4/month) runs only the fetch step.

  Not a personal computer (D-006).

## D-019 (2026-10-18): Fetch data.gov.lt through a Cloudflare Worker relay pinned to Europe
**Context:** D-018: data.gov.lt answers every request from GitHub's runners with HTTP 500. Tested from Cloudflare's network (Workers playground, 2026-10-18): all three probe requests answered **200 with real data** (newest act 2026-10-16) in 170–470 ms.
**Decision:** a minimal relay Worker (`worker/fetch-relay.js`) on the project's free Cloudflare account. It forwards only GET requests for `/datasets/gov/lrsk/teises_aktai/*` to get.data.gov.lt, only with the shared key `RELAY_KEY` (header `x-relay-key`), sends an identifying User-Agent, and passes the answer through unchanged. The `relay` workflow deploys it (D-021); the nightly build tests it and sets `LTLAW_RELAY_URL` for `bin/nightly.py`; `source.py` uses the relay only when that is set. Local runs stay direct.
**Why not a cron Worker + R2 store:** that would duplicate the fetch logic in JS and add storage. The relay keeps one Python fetcher, and the volume is small (about 100 requests a night; the free plan allows 100,000 a day).
**Note:** our use is the intended one: a public open-data API, read-only, low volume, identified. If the operators (atviriduomenys@vssa.lt) object to the relay, we stop and ask them for access.
**Update (same day, verified):** the deployed relay first got the same HTTP 500 that GitHub gets, while the playground got 200 with identical headers. A Worker runs in the Cloudflare location nearest its caller (GitHub's runners are in the US); the playground ran near the maintainer in Europe. So data.gov.lt evidently refuses non-European traffic rather than GitHub as such. Fix: `[placement] region = "aws:eu-north-1"` (Stockholm) in `worker/wrangler.toml`. Verified: run 39135841787, `cf-placement: remote-ARN`, HTTP 200, nightly without warnings.

## D-020 (2026-10-18): One view of each article for pages and data; repeals; freshness; no silent gaps
After a red-team review of the built site:
- **One view.** `data.json`, JSON-LD and the page describe the same text: `blocks` is the text shown, `status` its state on the status day, `future` an adopted later text. Before this, two-version articles had the future text as the main JSON text (e.g. VSDĮ 40), so an agent could quote it as today's.
- **Repeals.** A new state "Neteko galios": for an act whose header says "… netenka galios D" (NTRĮ, from 2027-01-01), and for articles left only as "Neteko galios nuo D". 220 such articles had been labelled "Galioja šiandien"; e-tar confirms all 220.
- **Freshness.**
  - Every page gives the status day and when the data were last checked.
  - Every page carries a banner when the data are over 2 days old.
  - `app.js` warns when a page's own status day is old, which covers a stopped pipeline.
- **No silent gaps.** The nightly law update must reach back to the newest law already known; otherwise it pages back.
- **Keep the last good text.** An act whose new text fails the checks is rebuilt from its previous snapshot. Whole-act rewrites and acts named in `accept` pass the article-drop check.
- **Health, not labels.** Version dates that no detected law explains are reported in `status.json`, not turned into labels. On 2026-10-18 only CPK has them, where e-tar's own versions follow the disputed XIV-2317/XV-1028 dates and the affected articles are already "Nepatikrinta".
- **Validation results** are tracked in `validation/` with their dates, and shown on the site as dated results.

## D-021 (2026-10-18): Pipeline security
- Actions are pinned by commit SHA. No job keeps credentials in `.git`. Workflows default to no permissions.
- npm code (wrangler) runs only from `deploy/package-lock.json`, in jobs with read-only repository access, never next to a write token.
- The relay is deployed by its own workflow only when its code changes.
- Its `workers.dev` address is masked in logs.
- A keepalive job re-enables the nightly schedule, which GitHub otherwise disables after 60 days without activity.

## D-022 (2026-10-18): Publishing the repository
- When it goes public, the repository starts from **one fresh commit**, with a GitHub noreply author. The working history stays private.
- **Code: MIT.** Data and legal texts: the Seimas Chancellery's TAR open data under CC BY 4.0, attributed on every page. Legal acts themselves are not objects of copyright under Lithuanian law (Autorių teisių ir gretutinių teisių įstatymas, Art. 5).
- Kept out of the public repository:
  - the AI-assistant working file (`CLAUDE.md`);
  - working notes (status log, work queue, phase plan, now merged into ROADMAP);
  - correspondence with institutions.

  Research notes stay, dated, without personal names or internal identifiers.

## D-023 (2026-10-18): Review iterations, and the rules they produced
Accuracy is improved in **iterations**, recorded in `docs/ACCURACY.md`. Each iteration uses three methods:
- an empirical hunt for actually-wrong labels in the data;
- an analytical review of the register against the code;
- a second-model critique.

The fixes are then adopted with tests, the validators are re-run, and the register is updated. **Stop criterion:** an iteration with no new high-impact failure mode.

Rules adopted in iteration 1:
- **TAR notes are read.** A part with a later date → "Įsigalios D", with a box saying only part of the article waits. A conditional start, or two wordings printed side by side → "Nepatikrinta". Transitional notes change nothing.
- **Entry provisions:**
  - only "straipsnis / straipsniai / straipsnius / straipsnį" mean the whole article;
  - a date followed by "jeigu" or "arba praėjus" is conditional;
  - "Baigiamosios / pereinamosios nuostatos" count as entry provisions;
  - a law the register marks "neįsigaliojęs" with no date is not in force.
- **Every article in force today has a page.** It comes from the consolidation valid today (with that text's labels), or is a stub when only the adding law is known. The validator counts any missing one as a silent error.
- **The look-back for candidate laws is anchored on the day the stored version was first seen,** so labels don't drift with the calendar.
- **Amending laws are refetched** when a later law amends them. A failed fetch flags instead of stopping the site.
- **The page states until when its label holds.** Builds run just after midnight Vilnius, with a backup.

## D-024 (2026-10-19): Quality policy: fail safe, measure, review on change
Rules cannot cover every drafting form in Lithuanian law: four review iterations kept finding new forms, and in the last ones mostly flaws in the previous fixes. So accuracy rests on three things, not on rule completeness:
1. **Fail safe.** When a rule doesn't understand something, the page says "Nepatikrinta", never "Galioja šiandien". A gap in a rule costs usefulness, not correctness.
2. **Measure against an answer key.**
   - the hand-run e-tar validators;
   - from now on, the **prediction ledger** (`src/ltlaw/ledger.py`, TARGET T3): every night each article's label and text fingerprint are recorded; when a new official consolidation covers past days, our past labels are compared with it.
3. **Invariants every night:**
   - every source line is shown;
   - every in-force article has a page;
   - HTML and JSON-LD agree;
   - version dates are explained by known laws.

**The bar, published on `/apie/`:**
- no known confidently wrong label or missing in-force text, and each one found is fixed within days;
- 100% of source text shown;
- at most 5% unnecessary flags;
- data at most 2 days old, or a banner.

**Reviews.** Open-ended LLM review rounds stop after iteration 5. From then on:
- one review per change of rule code;
- a data hunt each quarter;
- immediate investigation of anything the ledger or the error reports find.


## D-025 (2026-10-19): Rules approved by a Government resolution (KET): the point is the unit
Kelių eismo taisyklės (resolution No. 1950) are the first act that isn't a law. They are made of numbered points, are amended by other resolutions, and resolution numbers repeat every year.

**Decided:**
- **Unit:** a top-level point ("52. …") is a page, like an article: `/ta/<TAR>/p/52/`, alias `/ket/52/`. Sub-points are anchors (`#p52.1`). Flattened superscripts ("662", "3.21") are decoded by the same increasing-sequence rule.
- **One parser per form:** `points.py` handles an act with no "N straipsnis" line, an approval line ("PATVIRTINTA …") and many numbered points. It produces the same data classes, so currency, rendering and validation are shared.
- **References keyed by number and date:** "Nr. 875, 2025-12-03" becomes `875/2025-12-03` at parse time, and the metadata of resolutions amending a points act in scope is stored under the same key (`source.keep_meta`, `meta_key`). A title must name the act by its adoption date and number ("2002 m. gruodžio 11 d. nutarimo Nr. 1950").
- **Amending resolutions:** their numbered items are their own articles. Items under "Pakeisti N priedą" are annex points, not rule points, and are ignored; "šio nutarimo 1.3 papunktis įsigalioja D" dates that item. Any dated part we can't place makes the resolution unresolved (every date applies).
- **No sibling margin for resolutions:** every reading of a flattened number is checked against the act's numbers ("1782" can be 178², not 178¹). Laws keep the margin until the back-test shows it can go.
- **Shown as published:** the road-sign and marking images aren't in the open data; annex pages say so and link to e-tar.

**Why:** KET is the most searched legal text in the country; the open data's consolidation is the 2024-12-01 one (to 2025-12-31), so its value depends on flagging what came later (No. 875, point 66²).

**Checked on 2026-10-19:** 256/256 points and 4/4 annexes identical to e-tar's same version; today 245 points correctly current, 10 correctly repealed, 66² correctly flagged; 0 wrong, 0 unnecessary flags.


## D-026 (2026-10-21): No coined abbreviations; laws not yet in force; court rulings
**Decided:**
- **Abbreviations:** an act is shown with an abbreviation only if one is in real use (DK, CK, FABĮ, TPVCAPDĮ). Otherwise the seed marks it `no_abbr`: pages, titles, citations, feeds and search results name it by its genitive ("Vyriausybės įstatymo 5 str."), the short alias is its name, and the abbreviation is only an internal key (`index.json` gives `cite`). Search doesn't narrow by such keys: a coined one can be an ordinary word ("KelĮ").
- **A law adopted but not in force** (register "neįsigaliojęs", with an entry date) can be in scope: every article is "Įsigalios D", the act says it doesn't apply until D, and no today's text is looked for. First case: Nekilnojamojo turto registravimo įstatymas (XV-1072), replacing NTRĮ from 2027-01-01.
- **Constitutional Court rulings** are read like amending laws, but only their operative part, and only a present-tense conflict counts (ACCURACY B3). The text is never changed; the article is flagged until the consolidation notes the ruling.
- **Acts are not left out because the source lags** (decided 2026-10-21): an act is shown as the open data hold it, with honest labels; only an act with no usable text at all is left out.

**Why:** an invented abbreviation is a small fabrication that AI answers would repeat; a law already adopted is what people search for before it applies; a voided provision shown as "Galioja šiandien" is a confident wrong answer.

**Addendum (2026-10-21, later): more rules approved by Government resolutions.** Eight single-document resolutions join KET, chosen for everyday use among those in force and amended since 2021 (amendment counts alone favour lists and budgets). None has an established abbreviation: all are `no_abbr`, cited by name ("Ligos ir motinystės socialinio draudimo išmokų nuostatų 5 p."). A resolution approving several documents is not taken until each document can have its own pages.


## D-027 (2026-10-21): One of several documents approved by a resolution
Resolutions such as No. 496 (Labour Code implementation: 12 documents, among them the average-pay rules) and No. 526 (per diems and business-trip expenses) approve several documents, each with its own point numbering.

**Decided:**
- **Each document is its own act in scope**, sharing the resolution's TAR id: seed `document:` (its title's first words) picks it, `docslug:` gives its pages, `/ta/<TAR>/<docslug>/p/N/`. Every reader of the text (pages, validators, today's-text recovery, back-test) parses the resolution with that selector, so like is compared with like.
- **Amending resolutions are read per document**: an item whose nearest opening names another document of the resolution ("1.2. Pakeisti … Darbo laiko … aprašą: …") is ignored for this one; a resolution naming only other documents is ignored entirely; an item naming none stays (fail safe: unnecessary flags at worst).
- The resolution's own items (the approval part) are shown with every document.

**Why:** these are among the most-used rules (HR, accounting); one page per point with a document of its own keeps the citation unambiguous ("Vidutinio darbo užmokesčio skaičiavimo tvarkos aprašo 5 p.").

**Checked on 2026-10-21:** 5 documents, 5/5 identical to e-tar's same version, 0 wrong labels, 3 unnecessary flags of 70; back-test 0 wrong of 448 situations.


## D-028 (2026-10-21): An MCP server and REST API for agents, on static files
Agents (and the people who ask them) need to find and fetch an article without a browser: the search page runs in JavaScript, and `data.json` is too big for one question (CK: 4 MB).

**Decided:**
- **Static API files, built nightly** (`src/ltlaw/api.py`, under `/api/v1/`): the act list, article texts in ~40-article chunks (the chunk of label L is `fnv1a(L) % chunks`, no index), search items in blocks of 500, a title-word index, upcoming changes, data dates. Texts exactly as on the pages. About 670 files: the site stays under Pages' 20,000-file free limit.
- **A Worker (`worker-mcp/`) answers MCP (Streamable HTTP, JSON) and REST** from those files: `search_law`, `get_article`, `list_acts`, `get_act_contents`, `upcoming_changes`. No database, no state, no dependencies; read-only. Every answer carries the status day, the unofficial-text notice and e-tar.lt links; `get_article` gives the label, until when it is certain, amending acts, the future wording, defined terms and a citation line.
- **Checked nightly**: `bin/check_mcp.mjs` runs the Worker's code against the night's build (a gate).
- **Cost**: the Workers Free plan (100,000 requests a day, 10 ms CPU each): over the limit requests fail, nothing is billed. Not deployed until approved (OPERATIONS); while the site is private, it goes behind the same Access gate.

**Why:** for an agent to ground a decision in the site (the test set on 2026-10-21) it needs search and article fetch it can call; MCP is how assistants call tools, REST for everything else. Static files keep the hosting free and the answers identical to the pages.


## D-029 (2026-10-22): Dated answers from the official consolidations, in R2
"What applied when the contract was signed" needs past texts; static files can't hold them (Pages' file limit).

**Decided:**
- **Only the Chancellery's own consolidations answer a past date**, never ours: the frozen Suvestine table (versions since 2020) and the closed versions of our nightly archive. A version answers the dates of its range; the frozen table's open last version only up to the table's last preparation (2025-05-20), since it can't say whether the act changed later. Other dates are gaps, said so with the nearest versions and the e-tar link; today and later go to today's text with its rules.
- **Stored once**: each distinct article text is one object (`v1/a/<hash>.json`); a version is a manifest of label → text; a dated question reads three objects. Every old version gets the pages' coverage check (`lines_not_shown`).
- **R2's free tier** (decided 2026-10-22); the Worker binds the bucket as `HISTORY`.

**Why:** the official consolidation in force on a date is what a lawyer would cite for that date; the gap between the frozen table and our archive (mid-2025 to 2026-10) is real and must be visible, not papered over.


## D-030 (2026-10-23): Dated pages for people, from the same R2 history
D-029's dated answers were for agents only; a person checking "what did DK 52 say when I signed" had to use e-tar.

**Decided:**
- **`/kaip-buvo/?u=<article page>[&data=YYYY-MM-DD]`**, served by the agents' Worker (one more route, same free plan): the article's periods since 2020 (`v1/<act>/h/<label>.json`, written by `bin/export_history.py`: a new period only when the text itself changes) and, for a date, that period's official text. Two R2 reads a page. Every article page links "ankstesnės redakcijos" there (`rel=nofollow`).
- **Same rules as D-029:** only the Chancellery's consolidations; the frozen table's open version shown as "nuo X (bent iki Y)"; gaps and the 2025–2026 hole said so with the e-tar link; today or later redirects to the article page.
- **The site's own look:** the build writes the shell `/api/v1/dated.html` from `base.html` (one stylesheet, one footer); the Worker fills it. Never indexed (`noindex`, `X-Robots-Tag`): one URL per date would flood search engines with near-duplicates.

**Why:** the history was already paid for (D-029) and is the part of the law competitors charge for; people need it as much as agents. Static pages per version would not fit Pages' file limit (13,822 articles × periods).


## D-031 (2026-10-23): Public launch; the repository stays private
**Decided (2026-10-23):** the site goes public now, without restrictions, for everyone; usage and problems are checked day by day; the GitHub repository stays private for now.
- The login gate is removed and the site is indexable (`INDEXABLE=true`); the MCP server and REST API are announced in `llms.txt`, `index.json` and `/apie/`.
- The repository stays private (D-022's fresh public commit is postponed); nothing on the site links to it.
- Usage is watched from Cloudflare's own aggregate request statistics only: the site promises no cookies and no visitor tracking (`/apie/`), so no analytics script.
- Releases: main → release after the checks, as before; expansion beyond the free plan's 20,000 files (Workers Paid, $5/month) is a separate, later decision.

**Why:** the site is stable (nightly green since 2026-10-21; e-tar today: 0 silent of 17,227 articles; back-test 0.067%), and it is only useful once people and agents can reach it.


## D-032 (2026-10-25; approved 2026-10-26): The site as the MCP Worker's static assets
**Problem:** the site has 19,498 files; Cloudflare Pages allows 20,000 a deployment, and Workers Paid does not raise
that (the Pages upload token's `max_file_count_allowed` is still 20,000 on 2026-10-25). Article pages are 89% of the
files, so no new act fits.
**Proposal:** the Worker `lt-law-mcp` serves the whole built site as static assets (`worker-mcp/wrangler.site.toml`):
100,000 files a version on Workers Paid; asset requests are free and unlimited; the script runs only for its own
paths (`run_worker_first`) and for paths no file matches (404s). `_headers`, `_redirects`, 404.html and the trailing
slash behave as on Pages (checked locally against the live site, 2026-10-25); short aliases stay Bulk Redirects.
- **No DNS change:** one Worker route `atviri-teises-aktai.lt/*` sits in front of the Pages project.
- **The way back:** set `vars.SITE_ON_WORKER` to false and run mcp.yml (wrangler.toml: no `/*` route), or delete the
  `/*` route in the dashboard. Pages keeps receiving each night's site while it fits.
- **The cost of it (accepted 2026-10-26):** the nightly deploy then uses the Workers token (`CLOUDFLARE_MCP_TOKEN`, already in
  GitHub for mcp.yml) instead of the Pages-only one. Cloudflare cannot limit it to one Worker, so pinned npm code
  (wrangler, lockfile) in the nightly could also change the relay Worker. Today the same token and code run only when
  mcp.yml is started by hand.
- The Worker reads the site's data from its own assets (no subrequests, no hour-old cache after a deploy).


## D-033 (2026-10-27): Ministers' orders read like Government resolutions; energy covered first
**Decided (2026-10-26):** energy and electricity are to be fully covered.
- In practice electricity is governed by rules approved by Energy Minister's orders (supply and use, grid connection
  and use, installation and operating safety, standard household contracts, heat supply). Orders approve rules made of
  points, number from 1 again every year and are amended by later orders citing date and number, exactly as Government
  resolutions do (D-025, D-027). So the same parser and currency rules read them: the scope marks such an act
  `kind: Įsakymas` with its issuer from the register (`resolve_scope.order_fields`), titles are matched as "… 2010 m.
  vasario 11 d. įsakymo Nr. 1-38 …", "šio įsakymo" items are the order's own, and pages say "patvirtintos Lietuvos
  Respublikos energetikos ministro … įsakymu Nr. …". Joint orders of several ministries are not supported.
- Order of work: the 15 energy laws still missing; seven sets of rules approved by Energy Minister's orders; then
  energy Government resolutions (public-service obligations, renewables, gas supply security, oil stocks, heat
  licensing); the regulator's (VERT) decisions only by demand: mostly one company's prices at a time.
- Only public law from the register is used.

**Why:** the laws alone leave out most of what a household or business needs about electricity; the order support is a
generalisation, not a new parser (the 14 resolution-based rule sets validate identically before and after).


## D-034 (2026-10-27): The energy regulator's (VERT) decisions
**Asked (2026-10-27):** the regulator's decisions are needed even when they address one company: the distribution operator is a monopoly, so its prices and terms bind every consumer.
- **Rules approved by VERT** (until 2019 VKEKK): read like the Government's and ministers' (D-025, D-033), the issuer
  from the register (`resolve_scope.RESOLUTION_ISSUERS`). First 14 for electricity: the transmission/distribution/
  public-supply price methodology (O3-3/2015), the procedures for using the transmission (O3-468) and ESO's distribution
  grid (O3-470), ESO's flexibility trading (O3-88) and data platform (O3E-1351), reliability indicators (O3-75),
  sector permits (O3E-1156), renewable output (O3E-262), trade supervision (O3-450), unbundling (O3E-468), investment
  approval (O3-100), state control (O3E-1352), certification (O3E-1388), complaints (O3E-225).
- **Price and approval decisions** (ESO's transmission prices for a year, connection fees, prosumer fees, reliability
  levels, …) are different: the register keeps every one "in force" (ESO's 2019 prices still are), the next year's
  decision replaces the last, and **the prices themselves are an annex not in the open data** (O3E-1676/2025: the
  decision's 2,243 characters; ESO's price table only on e-tar). Proposed: a series view (the newest decision of each
  series applies; older ones "replaced by Nr. …"), the decision's own text, and a link to the annex on e-tar. Copying the
  annex from e-tar would break D-004: a decision to take, or a question for the Chancellery.
- **Built (2026-10-27), option A:** `/vert/` lists the electricity decisions that
  apply today by company (ESO first) and the register's other one-off decisions; `/vert/<TAR>/` per decision (817):
  label, the decision's own text (fetched once: 2023 on and anything not earlier/replaced), the decisions that changed
  it, the same series' other decisions, and the e-tar link for its annexes. Labels (`ltlaw.decisions`): the period in
  the title ("2026 metams", "2026 m. II pusmečio", "2022–2026 m.") → applies / earlier; not yet in force → pending;
  a later decision in a recurring price series → replaced; else the register's status, said to be the register's.
  `/api/v1/vert.json` for agents. Nightly: new decisions (newest 300 of the regulator), texts in a 5-minute budget,
  kept in the state archive. **Gas and heat added the same day:** `/vert/` is an overview, `/vert/elektra/`, `/vert/dujos/`, `/vert/siluma/` the sectors (2,713 decisions). Most heat decisions are one company's price components with no period in the title: they keep the register's status, said to be the register's.


## D-035 (2026-10-28): The agents' interface, from a user's report
**Input:** a usage report from someone extracting legal definitions for a business glossary through the site's machine
interfaces (`~/Downloads/atviri_teises_aktai_usage_feedback.md`, 2026-10-27: P1–P14, S1–S12). Taken as product feedback
only; the glossary work itself is not ours.
- **Definitions are first-class:** `/api/v1/definitions.json` (every definition shown today: term, alias split from
  "(toliau – …)", definition, act, article, part anchor, URL, status; kind "title" for a concept named by an article's
  title and defined in its first part, a candidate), small per-word files `/api/v1/defs/<xx>.json`, the MCP tool and
  REST `find_definition(term[, act])` (inflection-tolerant; all acts that define the word, plus narrower terms ending in
  it, and a note when meanings may differ); `search_law` adds `defined_in`.
- **Smaller, consistent answers:** `get_article(part=…)`; `article` and `n` everywhere; acts by key, abbreviation, TAR
  code or name; a missing parameter is named; `GET /api` lists the endpoints; the home page lists MCP and REST;
  `llms.txt` slim, the act list in `llms-full.txt`.
- **Clearer data:** future text and diffs show superscript numbers as the current text does ("64¹", not "641");
  `future.changed_parts`; an `explain` block in `data.json` (which level says what applies today); annexes marked
  "not checked".
- Not done yet: a concept-graph export (S11; candidates only) and links for definitions by reference (P10).
- **P10 done (2026-10-28):** sentences like "Kitos … sąvokos suprantamos taip, kaip jos apibrėžtos Lietuvos Respublikos
  elektros energetikos įstatyme" are found (`definitions.References`); the acts they name are matched by name, each
  word inflected ("baudžiamojo kodekso" / "baudžiamajame kodekse"), longest names first, and by an alias the act
  gives ("… įstatymu (toliau – Įstatymas)" → "apibrėžtos Įstatyme"). Names not on the site and EU acts are kept as
  written. On the block in `data.json` (`defined_by_reference`), in `/api/v1/definitions_by_reference.json`, as a line
  under the article, and `find_definition(term, act)`: when the act does not define the term itself, the definitions
  of the acts it refers to, with the sentence. Matching by name, so a candidate list: the sentence is always included.
- **S11 done (2026-10-28):** `/api/v1/concepts.json`, one row per term of an act's definitions article: aliases, the
  articles using it (`used_in`, the same finder as the pages' "rastos apibrėžtos sąvokos"), and `broader`: the act's
  defined term the definition starts with, word forms exact (nominative) and in order within two extra words. Marked
  as candidates: on a sample of 30, about 25 right; the misses are definitions that start with a list.


## D-036 (2026-10-29): Fewer round trips for agents' research: `get_articles` and `related`
**Input:** our own research through the MCP server (a topic across energy laws, rules and regulator decisions)
took many calls: several searches, one call per article, then guessing which rules apply an article.
- **`get_articles(refs[, date])`** (REST `/api/articles?ref=…&ref=…`): up to 20 references in one call, as strings
  ("DK 52", "EEĮ 2 str. 15 d.", "KET 3.2", "Statybos techninio reglamento STR 1.07.03:2017 12": the longest start that
  names an act) or objects; each answer as `get_article`'s, the notice said once.
- **`related(act[, article][, part])`** (REST `/api/related`): what the article cites; the articles of other acts and
  of the same act that cite it; the energy regulator's decisions that cite it (newest first); "" = the act as a whole
  (decisions citing the order that approved rules). From `/api/v1/refs/<key>.json`, written from the links the pages
  make (`xref.Linker`'s `sink`; only the page's own text, not older wordings shown below it; rolled back with a
  rejected act). Only references written with the act's name are found, so the lists say what is cited and never
  guess; the answer says so.
- **References to other laws without "Lietuvos Respublikos":** a capitalised name ("Energetikos įstatymo 23
  straipsnio", the usual form in rules after the first mention) is now linked too, on the pages and in `related`: a
  capital never starts a name inside another ("atominės energetikos įstatymo" is not EĮ). References from other acts
  444 → 2,014, from regulator decisions 937 → 1,159; a sample of 15 all right.
- **`search_law`:** the first 10 results carry the part where the words are (`part`, `snippet`, `words_in_part`; between
  parts with as many words, the one with the word rarest in the article); up to 3 alternative wordings separated by "|"
  in one call, merged in turn, each result with `found_by`. A per-request file cache (`env._files`) keeps three
  wordings or a 20-article batch inside the Worker's 50 ms CPU (measured locally: 29 ms and 9 ms, file reads included).
- **A research recipe for any agent:** `/skills/lithuanian-law-research/SKILL.md` (an Agent Skill: when to use the site,
  the tools, wordings → definitions → a batch → references both ways → labels → cite), linked from `llms.txt` and
  `/api`; the same text is the MCP prompt `research_lithuanian_law(question)`, and the server's `instructions` give
  the short form.
- No cost: static files and the existing Worker; a batch is fewer requests, not more.

## D-037 (2026-10-29): EU law from EUR-Lex, article by article
**Input:** the focus on data, IT and cyber security in the energy sector. The heaviest rules there
are EU regulations, which no Lithuanian register holds. Links alone would have to be redone once the texts were here,
so the texts come straight in.
- **Source:** EUR-Lex open data (CELLAR), in Lithuanian: the newest consolidated version applying today (its CELEX
  "0…-YYYYMMDD" from the SPARQL endpoint), else the act as published in the Official Journal (the register lists some
  consolidations with no Lithuanian text: NIS2's; the next older, then the original). Reuse: Commission Decision
  2011/833/EU, source acknowledged on every page. No relay, no key, no cost; a night asks EUR-Lex for the version list
  and metadata, and downloads a text only when a new version appears.
- **One path for both laws:** an EU act is `dokumento_id: EU.<CELEX>`; `source.snapshot` writes its XHTML (both
  layouts: consolidated and "oj-") as the register's plain-text layout, so the parser, labels, pages, links, API and MCP
  are the same code. Words never changed (D-002); consolidation markers (▼B, ►M1 … ◄) and footnote references left out.
  Each fetch is checked word for word, article by article, against the XHTML (`eurlex.check`): any difference stops it
  and the act keeps its previous text. First set (11 acts): 0 differences.
- **What changed in the shared code:** inserted articles "4a" (`Num.letter`), headings "2 SKIRSNIS" and annexes
  "I PRIEDAS", definitions numbered "1)" in an "Apibrėžtys" article, an unclosed quote ends at the act's own next article
  (EUR-Lex's CRA 66 lacks its closing quote). The Lithuanian acts' validation is unchanged (0 silent, 761/761).
- **Labels:** EU acts apply in stages. The final article ("Jis taikomas nuo …. Tačiau …") is read for dates after
  today only: an article applying later is "Taikomas nuo D" (the act is in force; not "Įsigalios"); a part of one, or one
  applying later only in some cases while it already applies in others, keeps "Galioja šiandien" with a note and the
  badge "Dalis taikoma nuo D". A later date naming nothing readable is an act-level notice, never a guess. On
  2026-10-29: the Cyber Resilience Act 53 of 71 articles from 2027-12-11; the AI Act's high-risk sections (III/1–3)
  from 2027-12-02, article 5 in part from 2026-12-02; the Data Act's article 13 in part from 2027-09-12.
- **Directives** bind the Member States: the page says so and lists the Lithuanian acts whose annex names the
  directive (NIS2: KSĮ, ANK).
- **Links:** Lithuanian texts cite EU acts as "Reglamento (ES) 2016/679 6 straipsnio" (any case, a short name in
  brackets allowed): linked to the EU article, and listed by `related` both ways (BDAR: 44 references from Lithuanian
  acts, among them ESO's data platform rules on article 28). EU acts' own "šio reglamento 6 straipsnio" too, and (same day)
  the bare "6 straipsnio 1 dalyje", EU acts' usual form for their own articles: another act's article always has that
  act's name right before the number, so a bare number is the act's own unless the word before it names a document,
  carries a number or slash, or is an abbreviation (SESV); never inside a quoted amendment of another act. 1,621 links
  in the 11 acts; a sample of 18 all right.
- URLs `/es/<CELEX>/str/<n>/`; citations as Lithuanian texts cite them ("Reglamento (ES) 2024/1689 5 str."), BDAR by
  its established abbreviation; official short names (TIS 2 direktyva, Dirbtinio intelekto aktas, Duomenų aktas,
  Kibernetinio atsparumo aktas), never coined.

## D-038 (2026-10-29): Rules approved by agencies' heads; the construction and security set
- **Agencies' orders** approving rules are read like ministers' (D-033): `ORDER_ISSUERS` gives the citation genitive
  (Nacionalinio kibernetinio saugumo centro prie Krašto apsaugos ministerijos direktoriaus, Valstybinės duomenų
  apsaugos inspekcijos direktoriaus); numbers like "1T-35 (1.12.E)" work as they are (amenders are matched as "<date>
  įsakymo Nr. <number>"). A points act needs 8 numbered points, not 11 (VDAI's DPIA list has 10).
- **"…, patvirtintas …":** the participle agrees with the last nominative of the name, quoted titles and designations
  aside ("reglamentas STR … „…“" → patvirtintas, "…, sąrašas" → patvirtintas, "… rodikliai" → patvirtinti; two
  documents "… sąrašas ir … aprašas" → patvirtinti). Fixed five existing acts' titles (PAILGA, PAPILA, VERTKM, EĮIVDA,
  GDSPTA).
- Added: fuel quality, 8 STRs, NSUSOAĮ, VTPĮ, the energy companies' protection requirements (Energy Minister 1-9),
  3 NKSC and 4 VDAI orders. Each checked against e-tar (12 of 13 of the first batch identical; STR 2.02.01 left out,
  ROADMAP) and by the currency check (0 silent). Acts are held in `scope/queued_seed.yaml` until their text is fetched
  and checked, so the nightly can never add an unchecked act.

### D-037 addendum (2026-10-29, evening): annexes checked; converter version
- `eurlex.check` now compares annexes too (in order, letters and punctuation; spacing aside, because EUR-Lex runs a
  table cell's heading into its first paragraph). All 41 annexes of the 11 acts match.
- Found while adding it: GDPR 43 and 65 had lost a letter after "◄" ("ei akreditavimas"), from a marker rule fixed
  before release but after GDPR was fetched. The check missed it because it reads the XHTML with the same
  extraction as the conversion. Lesson: the check proves the parse, not the extraction; extraction fixes need
  existing texts converted again.
- So each stored EU text records `eu_converter` (`eurlex.CONVERTER`); a text converted by an older version is fetched
  and converted again by the nightly. Bump it with any change to the conversion. The 11 texts were converted again
  locally (only GDPR changed: 2 words) and the state asset updated.
- Same evening, 4 more acts: CER 2022/2557, REMIT 1227/2011 (consolidated with 2024/1106), the Cybersecurity Act
  2019/881, ePrivacy 2002/58. Three conversion gaps found and closed, each caught by the check or by inspection:
  the older flat layout (ePrivacy's 2009 consolidation: article titles and paragraphs as siblings; grouped into the
  newer layout's article containers first, `_group_flat`); "II ANTRAŠTINĖ DALIS" (an EU title, read as a `dalis` above
  its chapters; the Cybersecurity Act); footnote references to the Official Journal, shown as "( -1 )" in 7 of the
  first 11 acts since their release, now dropped with their brackets (converter 3). The check now fails an act with
  no articles: ePrivacy first passed as empty. REMIT's entry into force came as the placeholder "1001-01-01"; dates
  before 1950 are ignored.

### D-037 addendum (2026-10-30): EU tables (converter 4)
- Before, a table row was its cells joined by " | ", a cell spanning rows was simply missing below, so the columns
  shifted ("a | b | c" text on the CER and NIS2 annexes). Now a spanning cell leaves empty cells where it reaches,
  so every row of a table has as many cells; the pages show such rows as an HTML table (`render._table_rows`), the
  API and MCP keep the " | " lines (an agent reads them as rows). Lithuanian texts have no "|".
- A cell of several paragraphs (NIS2 annex I's "— …" entity types) gives one row each, other cells empty, when it is
  the row's last cell with text; else the paragraphs share one line, so the words keep their order (the check
  failed 944 annex III and 1162 when every such cell was split).
- Lists laid out as tables with a blank first column and "1.1.1." numbers (NIS2 implementing regulation 2024/2690,
  all ~150 requirements, were "| 1.1.1. | …" with their a)–k) lists run into one line), "5a." (eIDAS 3) and quoted
  "„29." (Data Act 47–48) read as lists. The item's text may be a span, not a paragraph (2024/2690).
- A footnote reference with no space after it ("2019/944 (1)2 straipsnio", the Official Journal's own text) ran the
  numbers together: "2019/9442 straipsnio", 13 times in NIS2's annexes. A space is kept. The annex check compares
  without spaces and shares the extraction, so it could not see this; found by reading the page.
- Every EU text converted again: words unchanged but for those 13 spaces; all 15 pass the check.
- Same day, 4 electricity network codes: RfG 2016/631, DCC 2016/1388 (the act as published: EUR-Lex has no Lithuanian
  consolidation), SOGL 2017/1485 (consolidated 2021-03-15), NC ER 2017/2196. Two gaps, both stopped by the check
  before anything was stored: SOGL's definitions laid out as one-row tables ("1)" | text) were also read into the
  paragraph's first line (each definition twice); SOGL's "1 ANTRAŠTINĖ DALIS" (a title with a figure, below
  "II DALIS", a part) ran into the article before. An EU title is now its own level, `antraštinė dalis`, between
  `dalis` and `skyrius` (the Cybersecurity Act's titles were shown as "dalis"). And the check reads NFC as the parse
  does: RfG writes "·" as U+0387, which NFC makes U+00B7 (same character).
- Lists of EU acts on Lithuanian acts' pages ("įgyvendina … ES teisės aktus", "minimi ES teisės aktai") link to this
  site's page of an EU act in the scope, EUR-Lex otherwise (they all went to EUR-Lex). `celex` stays in the data.

### 2026-10-30 (afternoon): STR 2.02.12:2026 „Pastatai“; points going back; acronyms
- STR 2.02.12:2026 „Pastatai“ (order D1-129, 2026-07-08) applies from 2027-01-01 and repeals STR 2.02.01 (residential,
  queued since 2026-10-29), 2.02.02 (public buildings), 2.02.09 (in the scope) and more on that day. Added now, shown
  as not yet in force (like NTRgĮ). `resolve_scope.py` accepts an approving order "neįsigaliojęs" with an entry date,
  as it did for laws. STR 2.02.01 stays queued: its replacement is here and it ends in two months.
- Points acts: a number going back inside a point ("1. … 2. …" under STR 2.02.12 54's table: the table's notes) was a
  point "printed again further on" and reset the sequence, so 55–59 read as 5⁵–5⁹. Now such a line is the current
  point's text and the sequence stays. Of the 74 points acts only GDKR changed besides: its tables' footnotes
  ("1. 1Vykdant …") had been points 1–4 "printed again" (6 false warnings); now GDKR matches e-tar (8/8). A leftover
  "N. Neteko galios" further on is still a duplicate (IVSMN).
- "102.." (a typo) is point 102 only right after 101; EEPPKRA's "261.." stays in point 26 as on e-tar (a first,
  wider rule made it 26¹: the validators failed it, 2 silent).
- Headings keep an act's own acronyms of 5–8 capitals (ENISA, ENTSO, CSIRT, LITGRID, MARPOL): words written in
  capitals inside the act's ordinary sentences, not in quotes („PAVOJUS“), not Roman numerals. 25 headings in 9
  acts changed, all from "Enisa"-style to the acronym.

### D-037 addendum (2026-10-30, 10:30): an independent check of EU texts; what it found (converter 5)
- `eurlex.check` compared each article and annex with the XHTML as the conversion reads it, so a part the conversion
  never reads passed unseen. A second reading now compares the whole text, from the first article on, with the
  XHTML read plainly (every word in document order: footnote references, markers, footnotes outside annexes, the
  statements after the act, place, date, signatures and ELI lines aside). A run of 4 or more words missing or added
  stops the conversion (the act keeps its previous text). On the 19 acts the remaining differences are at most 2
  words (a footnote number run into the word before it in the plain reading). Dropping or doubling any one line of
  12+ words was caught in each act (tested once by hand); the unit test plants both.
- What it found, all fixed:
  1. **SOGL's 8 annexes and NC ER's annex were missing.** The older consolidated layout has no `anx_` divs ("I PRIEDAS"
     and its text are siblings after a separator), so the conversion and the annex count both saw 0. Among them SOGL
     annex I: the SOGL provisions that don't apply to the Lithuanian, Latvian and Estonian TSOs (2 straipsnio 4 dalis);
     NC ER's: the under-frequency load-shedding parameters per synchronous area. Grouped now like the older layout's
     articles. REMIT's "KOMISIJOS PAREIŠKIMAS" / "TARYBOS PAREIŠKIMAS" use the same class: statements, not shown.
  2. **The closing words** ("Šis reglamentas privalomas visas ir tiesiogiai taikomas visose valstybėse narėse.") sit
     after the last article (`fnp_1`) in the newer layouts: left out of 12 regulations. Now the last paragraph of the
     last article, as the older consolidated layout prints them. The place, date and signatures are not shown.
  3. **AI Act 51(2): "10-25" for 10²⁵.** The register's "-n" for a superscript (5-1 straipsnis) read as a range or a
     subtraction. EU acts number nothing with superscripts: digits are now superscript characters (10²⁵, a footnote
     mark "standartuose¹", annex footnotes "(¹)" in NIS2/CER). Only these two superscripts occur in the 19 acts'
     articles and annexes.
- Converter 5: the nightly would convert again by itself; the local snapshots were converted from the same EUR-Lex
  versions and given to it with the state asset (backup `private/backups/eu-snapshots-2026-10-30-before-converter5/`).

### D-036 addendum (2026-10-30): search_law answers questions it returned nothing for
A test with 25 questions on energy, cyber security and data (as an agent asks them) found 4 with no results at all:
- **An act guessed from plain words narrowed the search to it, even when nothing in it matched.** "pranešimas apie
  incidentą" went to VDAI's breach-notification order ("Pranešimo apie asmens duomenų saugumo pažeidimą …": two of the
  words), "kibernetinio saugumo reikalavimai energetikos subjektams" to NKSC's compliance checks, "viešieji pirkimai
  skirstomųjų tinklų operatorius" to ESO's network-access order. Now a guessed act that finds nothing gives way to every
  act (an act named by its abbreviation or `act` still restricts). Question words name no act: "apie", "pagal", "kaip",
  "kokie", "turi" … are not counted toward a name match.
- **Every word must occur, so a long question could find nothing.** When no article has them all (3+ words), the
  articles with all but one come back, each naming the word it lacks (`lacks_word`) and a hint to reword. Dropping the
  most common word instead was tried and rejected: "pirkimai" is in thousands of articles yet half of the question.
- **Stems of 6 letters merge words:** "bendrija" (community) and "bendrieji" (general). Between equal title matches, the
  title whose words share more letters with the query's comes first ("energijos bendrija": AIEĮ 20-2, not RfG 13).
- Left as is: "ankstyvasis įspėjimas" (NIS2 23) ranks ANK first: its articles have "ankstyvosios intervencijos" and
  "įspėjimą" (a penalty). Fixing it needs the words' proximity in the text, not only in titles; agents can name the act.
- 3 checks in `bin/check_mcp.mjs` (each failing on the old code).

### D-037 addendum (2026-10-30, afternoon): gas, renewables, efficiency, balancing; images (converter 6)
- **7 EU acts added (396 acts, 26 EU):** the Methane Regulation 2024/1787 (leak detection and repair for gas networks),
  the gas and hydrogen market regulation 2024/1789 and directive 2024/1788 (the 2024 package; ESO distributes gas too),
  gas security of supply 2017/1938 (consolidated 2026-06-22), the renewable energy directive 2018/2001 (RED III,
  consolidated 2024-07-16), the energy efficiency directive 2023/1791 (consolidated 2026-08-05), EBGL 2017/2195.
  Area energetika. 2024/1787, 2024/1789 and 2024/1788: as published (no Lithuanian consolidation).
- The checks stopped three of them; the conversion now also reads: an article quoted in an amendment keeps its title
  ("„8a straipsnis", 2024/1789 84; the act's own title stays its first line), and the "“;" after it in a list laid out
  as a table; a numbered item whose text is a bare `<span>` (2024/1788 II 3, lost); text between two blocks
  (", N – 1 ≥ 100 %" after the N – 1 formula, 2017/1938 II, lost). No space before "," after a footnote reference.
- **Images:** formulas and figures were dropped without a trace (RfG's voltage profiles, 1162's process diagrams; now
  RED's greenhouse-gas formulas, the efficiency directive's, the N – 1 formula): 68 images, 2 MB. The text has
  "[paveikslas N]" where each is; the row keeps them (`eu_images`, data URIs); the pages show them (files beside the
  act's pages, `/es/<CELEX>/img/N.jpg`), the API gives their URLs (`images` per block). Lithuanian acts' "formulė
  šaltinio tekste pateikta paveikslėliu – žr. e-tar.lt" no longer lands on EU texts that end "apskaičiuojamas taip:".
- **"taikomi iki" is an end date:** 2017/1938 22 "6a–6d straipsniai … taikomi iki 2027 m. gruodžio 31 d." had made
  those articles "taikomas nuo 2027-12-31" (wrong both ways). Only dates after "nuo" start anything; an "iki" date is
  an act-level notice. No other act's labels changed.

### D-036 addendum (2026-10-30, late afternoon): words together, or a hint that they lie apart
- "ankstyvasis įspėjimas" was not a ranking problem: the law's term is "ankstyvasis **per**spėjimas" (KSĮ 18, NIS2 23),
  and the articles with both of the asked words are ANK's, where they lie in different parts. A word index cannot
  see that; the first ten results' texts are read anyway (for `snippet`), and they can.
- Among the first ten, equal in title words (and title closeness), an article whose title or one part has all the
  words comes first: NIS2 11 ("ankstyvuosius perspėjimus, įspėjimus") now leads, and its wording shows the term. When
  none of the ten has them together, a hint says the words lie apart and the law may use another term. No extra
  reads: only the snippets' texts, so no CPU or request cost.
- Not attempted: the whole candidate set by proximity (its texts are megabytes; 10 ms CPU per request), synonym lists.
- Known: 6-letter stems merge "vandenilis" (hydrogen) with "vandens" (water), "nuotėkis" (leak) with "nuotekos"
  (waste water, same letters once folded). Longer stems would grow the index; the snippets name the matched part.
- 2 checks in `bin/check_mcp.mjs` (both failing on the old code).

### D-037 addendum (2026-10-30, evening): crisis preparedness, charging, buildings
- Added 2019/941 (risk preparedness in the electricity sector: crisis scenarios, plans, art. 14 "išankstinis
  perspėjimas"), AFIR 2023/1804 (charging infrastructure: targets, smart and bidirectional charging; art. 15(4)
  regulators assess it with TSOs' and DSOs' input) and EPBD 2024/1275 (buildings: solar, recharging pre-cabling, data
  exchange; it names no DSO duties). 399 acts, 29 EU. All three passed both checks on
  the first conversion (converter 6): 24, 26 and 38 articles as the acts have them; 2019/941 has no consolidation
  (never amended), so its OJ text.
- EPBD annex IX's title reads "A DALIS": the annex has no title of its own, only parts A and B, as published.

## D-039 (2026-10-31): Act texts by revision: only changed ones fetched
- The nightly fetched every act's whole Dokumentas row (85 KB to megabytes) each night: 20 of its 47 minutes, the
  step's full budget; with more acts, some would have waited for the next night. Usually 2 of ~370 change.
- Spinta gives every row a `_revision` that changes with any change to it. One query reads 25 acts' revisions
  (`select(dokumento_id,_revision)&or(...)`, 50 got a 502): the whole scope in 15–22 s. An act whose revision is the
  one its last full fetch saw is checked without fetching (checked.txt, as an unchanged fetch); `revision.txt` keeps
  "<revision> <time of that fetch>".
- Still, a seventh of the texts (the longest unfetched) is fetched in full each night, so each about weekly, spread
  evenly; a 10-day backstop inside `snapshot`. A revision read that fails, a missing one, or two rows for one act:
  that act is fetched as before. EU acts are unchanged (EUR-Lex version lists, D-037).
- Measured here: a full pass 481 s; with revisions, after the first night, 310 of 311 not fetched (the one fetched
  had changed). Rows did change during a pass (15 at ~06:00, data.gov.lt's update): fetched the next pass, as meant.
- Why now: GitHub Actions minutes (private repo, 2,000 free a month): October used 1,573 with the nightly ~47 min;
  this saves ~15 minutes a night and lifts the cap on how many acts fit.
- 2026-11-17: the weekly full re-fetch and its 10-day ceiling did not scale to 1,425 acts: changed by D-056.

## D-040 (2026-10-31): The change feeds say why a text changed
- Every changed article text was announced as "tekstas pasikeitė (nauja Seimo kanceliarijos suvestinė redakcija)".
  Most were our own fixes (a parser fix on 2026-10-23 made 508 such entries, converter 6 put EU articles under the
  Chancellery's name), so the feed claimed changes in the law that never happened, one entry per article.
- The build now records, per act, where the shown texts came from (`data/state/act_sources.json`: a hash of the
  stored text, the EUR-Lex version, and per article the other version shown today), for tonight and the last
  earlier day (a second run on a day compares with the same day as the ledger). The wording follows:
  - another version shown: "tekstas pasikeitė (rodoma redakcija, galiojanti nuo D)";
  - the stored text new: "… (nauja Seimo kanceliarijos suvestinė redakcija)", or "… (nauja EUR-Lex suvestinė
    redakcija)" when the EU version changed;
  - shown from the stored text both nights and that text the same (or the same EU version converted anew): our fix.
    One entry per act: "DK: svetainėje pataisytas teksto nuskaitymas (15 str.: 1, 2, …); teisės akto tekstas
    nepasikeitė" ("perkėlimas iš EUR-Lex" for EU acts);
  - anything else (no record of the last day; the same other version re-read, whose source we don't track): plain
    "tekstas pasikeitė", no cause claimed.
- Feed entry ids were "<day>:<act>:<article>:<position>", the position in tonight's list: each night's new entries
  moved the old ones, and readers could show them again as new. Now "<day>:<act>:<article or kind>" (one change
  per article a day, one fix entry per act). Article numbers as the pages print them: "41¹ str.", not "41^1".

### D-038 addendum (2026-10-31): the operating and protection rules of electricity networks; gas licensing
- Added the Energy Minister's Elektrinių ir elektros tinklų eksploatavimo taisyklės (1-211, 2012; 1,692 points) and
  Elektros tinklų apsaugos taisyklės (1-93, 2010: protection zones, works near lines), and the Government's gas
  licensing rules (1246, 2011). 402 acts. All three parse completely (missing 0, text-diff 0).
- The open data's texts lag: EETEKT's stored version ends 2024-12-31, ETAT's 2022-07-22, GDLT's 2018-01-22. Their
  amending orders were not in the points-acts' amenders until `update_point_amenders` ran (it found 14); before it,
  61 articles would have been "Galioja šiandien" with an old text (silent errors). After: EETEKT 1,690 current (checked
  against e-tar), 2 "Gali būti pasenęs"; ETAT 28 current, 9 outdated; GDLT all 62 "Neaišku, ar galioja" (a 2018
  text; shown as it is, labelled so). Silent 0.
- The procedure for a points act therefore includes `update_point_amenders` before `snapshot_scope --amending`.

### D-040 addendum (2026-10-31): a feed per area
- `/sritis/<area>/atom.xml` (12 areas, scope/areas.yaml): the changes of the area's acts, newest 200. A DSO's lawyer
  follows "Energetika" (82 acts) with one subscription, not 82. Linked on the area page and in its `<head>`; named in
  llms.txt and the API's meta. Older stored entries print "48¹", not "48^1", too (at writing; the stored text stays).

### D-038 addendum (2026-10-31, morning): connection fee methodologies; a table cell that repeats the point's number
- Added VERT's connection fee methodologies: electricity (O3-235, 2011; text from 2026-05-01, 66 points, all current
  and checked) and gas (O3-187, 2008; 28 current, 16 "Gali būti pasenęs"). 404 acts.
- Left out (queued): the gas regulated prices methodology (O3-367): e-tar gives its versions since 2022 only as
  DOCX/PDF/ODT files, so no label can be checked, and the open data's text is the 2022 version.
- The electricity methodology's point 10 table has a cell "10.  10.13.  10.14.1. 1 Vartotojas …" (as on e-tar): read as
  point 10 printed again, the rest of the table (10.14.x: who pays for moving or rebuilding network equipment, ~570
  words) went to a hidden duplicate. Now the point's number followed by its own subpoints' numbers is its text.
  Full regression: every other act unchanged (validate_scope: no text differences anywhere).
- The validators stopped at the first act e-tar has no HTML for (404) and validated none after it; now that act is
  "unverified" (currency.json `unverified`, exit 1) and the run goes on.
- ŠĮ (A22) passes: the open data's new ŠĮ text (2026-10-31) no longer has the sentence e-tar lacks.

### D-036 addendum (2026-10-31): few articles with every word
- One article of the new electricity methodology has all five words of "viešieji pirkimai skirstomųjų tinklų
  operatorius", far apart; the search returned it alone, hiding EEĮ 40-1 and the others with four of five. When
  fewer than 3 articles have every word (3+ words), they come first, then those with all but one (`lacks_word`); the
  hint says so, and whether the full ones have the words apart. "dirbtinio intelekto sistemos didelės rizikos": 2 → 5.

### D-037 addendum (2026-11-01): TEN-E
- Added 2022/869 (trans-European energy infrastructure: the PCI/PMI process, smart electricity grids as a category,
  permit-granting deadlines, regulatory incentives, and its amendments to 2019/943 and 2019/944) with the Union list
  (annex VII, 21 tables; Harmony Link 3.3.6, the Nordic–Baltic hydrogen corridor 11.2, Klaipėda CO2 terminals).
  405 acts, 30 EU. Both checks passed on the first conversion (converter 6): 33 articles, annexes I–VII.
- EUR-Lex lists an end of validity per consolidated version too (2022/869: 2024-08-03, 2025-02-04, 9999-12-31; 2019/944
  was stored "negalioja 2025-10-11" while in force): the latest one counts now. Not shown anywhere, so nothing changed
  on the pages; the rows correct themselves on the next night.

### D-041 (2026-11-02): spread data.gov.lt's downloads over the weeks before a version takes effect
- data.gov.lt rate-limits: after a few big Suvestine texts it answers HTTP 429 for minutes, counting requests rather
  than bytes (a 9 KB text waited as long as a 600 KB one; sustained, about one heavy request a minute got through).
  On 2026-11-02, 51 versions took effect at once (11-01: DK, ANK, VPĮ, SĮ, AIEĮ…); the night fetched none, and ~125
  articles showed their future text for the morning.
- The Chancellery prepares versions weeks ahead (of 117 versions taking effect since 2026-10-01, 110 were prepared over
  30 days before). So each night, after the build, the texts of versions taking effect within 45 days are fetched,
  soonest first, 10 s apart, a 429 waited out, within 5 minutes (`today.prefetch_upcoming`). Version lists are
  refreshed for 80 acts a night, each act about every 4 nights (was 40, ~9–10 nights), so new versions are known early.
- Not chosen (yet): a second scheduled job during the day. The repo is private (2,000 Actions minutes a month; October
  used 1,573), and with the look-ahead a night has little left to fetch. Revisit if `upcoming_texts.left` keeps growing.
- 429 is not "down" (4a470ad): today's texts wait it out within their budget; the night's warning names the cause.

### D-037 addendum (2026-11-02): Gigabit Infrastructure Act, Data Governance Act, Cyber Solidarity Act, ACER
- Added 2024/1309 (GIA: network operators, energy ones included, must share physical infrastructure and coordinate
  civil works for gigabit networks; area energetika and duomenys-it), 2022/868 (Data Governance Act), 2025/38 (Cyber
  Solidarity Act) and 2019/942 (ACER). 409 acts, 34 EU. All passed both checks first time (converter 6): 19, 38, 26
  and 47 articles; the correlation tables stay in their annexes (GIA's annex is unnumbered: "PRIEDAS").
- Demand check first (Search Console, 7 days to 11-01): the topic queries without an act were company formation
  ("UAB steigimas", "individualios įmonės steigimas") and annual building inspections, all acts we have (ranking, not
  scope); so the additions follow the project's priorities (energy, IT, cyber, data) instead.

### D-037 addendum (2026-11-02, evening): the EU acts our Lithuanian texts cite most
- Chosen by citations instead of guesses: the uncovered EU acts named most often in our stored Lithuanian texts, in
  the priority areas. Added the Energy Union governance regulation 2018/1999 (cited by 18 of our acts), DORA 2022/2554
  (14), the whistleblower directive 2019/1937 (14), the Digital Services Act 2022/2065 (7), CACM 2015/1222 (7), the
  battery regulation 2023/1542 (7) and the European Electronic Communications Code 2018/1972 (8). 416 acts, 41 EU;
  about 670 article pages of Lithuanian acts now link to them. Left out though cited more: financial-market
  regulations (EMIR 648/2012, CRR 575/2013, ESMA 1093/2010) and product rules (accreditation 765/2008,
  standardisation 1025/2012), outside the priority areas; the repealed 714/2009 and 715/2009.
- Three EUR-Lex quirks, each caught by the word-for-word check and fixed in the converter (no stored text changed but
  the battery regulation's): a heading "70 straipsnis." with a full stop (2018/1972); a quote EUR-Lex never closes
  right before the act's own chapter heading (2023/1542 92: "XIV SKYRIUS" was read into the quote; it now ends there,
  as it already did at the act's own next article); an entry into force before the act's date (CELLAR gives 2022/2065
  2022-02-17 and 2022-11-16: dates before the act's own are ignored; no other act has one).
- Battery regulation 11 (removable portable batteries) is "Taikomas nuo 2027-02-18"; everything else applies today.

## D-042 (2026-11-02): New acts chosen by how often our own texts cite them
**Input:** keep expanding. Search Console's topic queries without an act turned out to be acts we have
(ranking, not scope), so demand from search can't pick the next acts yet.
- **Rule:** the next acts are those in force that the acts already on the site cite most and the scope lacks. A reader
  following a law's text meets these names; a citation now links instead of leaving the site. Counted over the stored
  texts: EU acts by "Reglamento (ES) 2018/1999" and the like (D-037 addendum, 7 acts), laws by "… įstatymo" against the
  register's laws in force.
- **First batch, 25 laws** (cited 86 … 4 times): financial sustainability, recognition of professional qualifications,
  defence and security procurement, financial conglomerates, intelligence, state environmental control, strategic
  management, protected species, mobilisation, diplomatic service, municipal infrastructure, personal data processed
  for crime prevention and national security, protection of minors from harmful information, metrology, the defence
  industry, environmental monitoring, criminal intelligence, martial law, fiscal governance, official statistics and
  state data governance, the basics of national security, secondary use of health data, conformity assessment, the
  President, the state border. 441 acts. Left out despite citations: the old 1994 company law I-528 (in the register as
  "in force", replaced by VIII-1835 which we have).
- **Checks:** e-tar text 25/25 identical; currency 0 silent; today's texts 33 of 38 recovered, 33 correct; the rest
  stay labelled (the martial law's 2026-11-01 consolidation isn't in the open data yet: 3 articles "no today's text").
- **Found on the way:** the Law on the President quotes the promulgation formula in article 11 ("… įrašoma: „Skelbiu
  šį …“"); the parser took it for the signature and lost articles 12–24. The formula now counts only opening its line
  or after "Vadovaudamasis … Konstitucijos 71 straipsnio antrąja dalimi," (the Speaker's form: PVMĮ, VKĮ, the law on
  the right to obtain information); no other stored text parses differently (3,060 compared). The build's gate caught it
  (12 article pages without text); the e-tar comparison didn't, as it reads e-tar's text with the same parser.
- **Wording:** an act whose newest consolidation starts after today says so on its page ("būsima; straipsniai rodomi
  su šiandien galiojančiu tekstu") and on its unchanged articles ("būsima redakcija; šio straipsnio tekstas joje toks
  pat kaip šiandien"): DK's page read "suvestinė redakcija nuo 2027-01-01" above "Šiandien: galioja 257" (ROADMAP:
  mobile, two dates).
- `bin/snapshot_scope.py` waits out data.gov.lt's 429s and paces amending-law fetches (it stopped after two laws).

### D-042 addendum (2026-11-02, night): metrology for meters
- A test question: must every smart meter pass initial verification in an independent laboratory, or is
  sampling enough? The Metrology Law (in the 25) answers only in outline (19 str.: sampling "in the minister's cases";
  2 str. 11 d. and 21 str.: instruments under technical regulations have conformity assessment, not verification).
  Added what decides it: the MID 2014/32/EU (V priedas: electricity meters MI-003, B+F, B+D or H1; module F tests every
  instrument or a statistical sample), the economy minister's Measuring Instruments Technical Regulation (4-699, the
  MID's transposition, 104 points) and the Rules of legal metrological regulation (4-761: 52 p. and 6 priedas —
  electricity meters by sampling for periodic verification only). 444 acts.
- Left out: the list of instrument groups and periodic verification intervals (4-523), a single table with no points
  (the parser finds none); `scope/queued_seed.yaml` until tables can have pages.
- 4-761's stored consolidation ends 2025-11-30; today's (from 2025-12-01) differs in annex 5 only (item 35 added):
  the annex page names its consolidation and says annexes aren't checked for today; the points are all current.

## D-043 (2026-11-03): Annexes are searchable and readable through the API, labelled as not checked for today
Context: a test question ("must every smart meter get its initial verification individually, or is sampling
enough?") turns on two annexes: 4-761's annex 6 (the instruments that may be verified by sampling; electricity meters
"taikoma tik periodinė patikra") and the MID's annex V (MI-003). The site had their pages, but the agents' API and the
full-text search held articles and points only: an agent could not find or read them.
Decision: every annex is a search item and an API text entry with the label `priedas-<n>` (`priedas-6`, `priedas-V`),
number "6 priedas", the annex's title, and the status `unknown` labelled "Priedas: ar galioja šiandien, netikrinama"
(annexes are not checked against today's consolidation; the stored one is named in `source`). `get_article`,
`get_articles` ("MPTMRT 6 priedas", "Direktyvos 2014/32/ES V priedas") and a search for a reference read it;
`get_act_contents` lists the annexes; with `date`, an annex says past wordings are not kept. In search ranking an annex
comes after an article equal in title words (a long annex has many words). The site's search shows "6 priedas".
Measured: 750 annexes; +7 MB of API text, +1 MB of index, +122 files; the largest text chunk 390 → 650 KB (≈1 ms to parse);
everyday-question ranking unchanged (top-1 18/25, top-3 18/25); the test question in its own wording now finds annex 6
first, and "elektros energijos skaitikliai atitikties vertinimas" finds the MID's annex V.
Not done: annexes taken from today's consolidation when it is cached (they stay the stored consolidation's).

### D-042 addendum (2026-11-03): the big batch, 444 → 673 acts
- Decided: keep expanding quickly. Coverage measured against the register (laws in force, amendments, ratifications,
  budget and one-off laws left out): ~656 distinct substantive laws, 319 on the site; rules (Government resolutions,
  ministers' and VERT orders approving rules, procedures, methodologies) ~8,500 in force, ~60 on the site.
- Added by the same rule (citations in our stored texts) and, for laws, lasting general laws not cited yet:
  66 laws cited 3+ times, 100 laws cited once or twice or not at all (treaty, reorganisation, loan, boundary, free-zone,
  company-specific and COVID laws left out), 63 sets of rules cited twice or more by name (half of them energy: electric
  lines, gas pipelines, relay protection, heat networks, connection contracts, VERT methodologies).
- Every act went through the usual checks (validate_scope, validate_currency, validate_today_text, the gate); **28 were
  held back** to `scope/queued_seed.yaml`, each with its reason: 10 with articles that would be labelled current with
  another wording than e-tar's today (currency-engine cases: a law whose dates later laws moved, KPPPFĮ's 2027
  e-road toll; amending-law article maps), 9 where e-tar has no version to check against, 7 the parser can't read yet
  (an article number on its own line in some consolidations; rules layouts; flattened superscripts 281 = 28¹; figure
  placeholders read as tables), 1 whose whole new wording is missing from the open data (CVVTVĮ), 1 with a wrong
  recovered today's text (EBĮ 7). Rules whose names were changed by amendment keep the name in their text (the register
  keeps the title as adopted).
- The nightly's Suvestine version-list refresh now takes a quarter of the scope a night (was a fixed 80), so each act is
  still re-read about every 4 nights.

### D-043 addendum (2026-11-03, afternoon): annexes from the consolidation in force today
- When the stored consolidation is past or future and the open data have the one valid today (Suvestine, cached as for
  today's article texts), the annexes are taken from it: MPTMRT's stored text ends 2025-11-30, today's annex 5 has an
  item 35 more. The page's strip names that consolidation and says later changes aren't checked; the API's `text` gives
  its period and `source: Suvestine`; data.json's annexes say so too. Otherwise the stored text's annexes, as before.
- Every rules act's annex said its road-sign images are missing from the open data (a KET note shown for any act made
  of points): now KET only.

### D-037 addendum (2026-11-03): converter 7, headings EUR-Lex splits or numbers with a letter
- "II" / "ANTRAŠTINĖ DALIS" (the customs code), "3A" / "SKYRIUS" (EMIR), "IVA ANTRAŠTINĖ DALIS" (MiFIR), "II ANTRAŠTINĖ" /
  "DALIS KRIPTOTURTAS, …" (MiCA), "2 SKIRSNIS." alone (MDR): the heading ran into the article before it and the word
  check stopped the fetch. Joined in the conversion; the parser reads lettered numbers. The list of annex titles some
  acts print after the closing formula (MDR, IVDR) is an index, not text: the word check passes it (the annexes follow
  in full and are checked). All EU texts are converted again with converter 7 (checked locally before release).

### D-042 addendum (2026-11-03, afternoon): energy rules in full, rules cited once, EU acts; 673 → 891 acts
- Every set of rules the energy minister and VERT have in force (cited or not; program measures, past auctions and
  internal administration left out): 118; rules our texts cite by name once: 87; EU acts in force cited most: 30;
  back from the queue after the fixes (B65, B66, B67): 11. Candidates from `bin/rank_candidates.py`, the open-data side
  by `bin/fetch_new_acts.py`.
- Held back by the checks, with reasons in `scope/queued_seed.yaml`: 11 with points labelled current with another
  wording than e-tar's, 5 with no e-tar version in force to check, 7 whose layout gives no points, 3 the parser reads
  differently from e-tar, 3 EU acts the word check still stops (CRR: EUR-Lex's own typos; MiFIR 35; PSD2 9), the anthem
  law (no numbered articles). Today's texts recovered for the new rules: 497 of 497 correct.
- An act's URL alias: a name over 220 bytes gives its first words and a hash (`render.act_alias`): the file name limit
  (255) stopped the build at refs/<alias>.json; no existing alias changes.
- Search on everyday questions fell with breadth (top-1 18/25 at 673 acts, 15/25 at 891: special laws' "Kasmetinės
  atostogos" beat DK 126 "Kasmetinių atostogų sąvoka ir trukmė" on closer word forms). Two quick changes were tried and
  dropped (reading title blocks first: no change; abbreviated acts first: 13/25, CK then won child care and burial).
  Next: a larger question set and ranking work on it, before more breadth.

## D-044 (2026-11-03): Search ranks the law a question is most likely about first among equals
**Problem:** with 891 acts, everyday questions went to special laws (top-1 18/25 at 673 acts, 15/25 at 891): "kasmetinės
atostogos" found the diplomatic service's "Kasmetinės atostogos" before DK 126 "Kasmetinių atostogų sąvoka ir trukmė";
"pridėtinės vertės mokesčio tarifas" no longer named PVMĮ (the rules on imports' VAT have as many of its words);
"asmens duomenų tvarkymas" was read as naming the standard clauses of data processing contracts.
**Benchmark:** `bin/search_questions.json`, 80 questions in people's words (the 25 of 2026-10-23 and 55 more: work, tax,
civil, criminal, data and cyber, energy, other), each with every act that rightly answers it (a specific rule set where
it is the answer: STR 1.05.01:2017 for "statybą leidžiantis dokumentas"), run by `bin/check_search_ranking.mjs`.
**Changes** (each kept only if no question got worse; 59 → 69 of 80 top-1, 64 → 71 top-3; the first 25: 16 → 21):
- word forms: a title word counts as close when it goes one letter past the stem, not by how many ("kasmetinių" as near
  as "kasmetinės"; "bendrijų" still before "bendrieji");
- among equally good articles: the share of the query's words in the act's name, plus how often other acts cite the
  act (`/api/v1/cited.json`, written with the references, D-036; log scale): DK (cited 68 times) before the extra-leave
  rules (0), the State Pensions Law before the judges' pension rules, BK before ANK for "vagystė";
- naming an act in plain words: among names as good, the one that is nothing but the query's words, or one cited 10+
  times and 5 times more than the next; and no guess at a narrow act whose long name merely holds the words (more than
  one other word in it, cited fewer than 3 times).
**Tried and dropped:** reading title blocks first (no change); abbreviated acts first (13/25); a name's word density
alone (gained VAT, lost the administrative-court and energy-audit questions).
*2026-11-04:* a guess rejected as a narrow act now falls back to an act whose whole name is in the query: a new rule set
naming "pridėtinės vertės mokesčio tarifą" among much else had ended the guess at the VAT law (68 → 69, PVMĮ 19 first).
Leaving narrow acts out before ranking also fixed it, but guessed the courts' administration law for "skundas
administraciniam teismui" (a tie with a narrow act had been holding that wrong guess back).
**Still missed** (11): the law's words differ from the question's ("dronai": bepiločiai orlaiviai; "smulkusis
chuliganizmas": the term left the law), DK's own titles lack the words ("išeitinė išmoka", "bandomasis laikotarpis",
"darbuotojo materialinė atsakomybė"), and a few with defensible other answers. No synonym list: guessing a user's
meaning is the agent's job, and the hint asks for the law's own terms.

## D-045 (2026-11-03): Pages without the list of every act; the build stays whole; the way past 100,000 files
**Measured** (the nightly of 2026-11-03, 444 acts on GitHub; a 60-act sample of 897 locally): fetching 577 s (its own
budgets), building 243 s, checks ~160 s, keeping and fetching the built site 93 s, the deploy 428 s, of which 375 s
uploading 37,476 of 37,956 files: every page changes every night (it carries the day). Every page's sidebar listed every
act: 128 KB of a 143 KB page, 37 % of the build's time in rendering it, and one act added changed every page.
**Change:** the sidebar lists the areas and the act one is in; the home page and the area pages list all acts. Average
page 151 → 20 KB, rendering 33 → 3.5 s per 60 acts, the build a third faster, the upload about 7 times fewer bytes.
**Not done, and why:**
- *an incremental build* (re-render only acts whose inputs changed): labels change with the date, and an act's pages
  depend on the others (links, names, definitions, the EU acts it implements); a cache would bring last night's site
  back each night and one stale entry is a confidently wrong label. After the sidebar change the rendering is minutes;
  the fetching and the labels must run every night anyway.
- *pages that stay the same when nothing changed* (only changed files uploaded): the day in a page is the guard that
  says a page is old (app.js after 2 days) and the footer's "Žymos nustatytos"; moving it to a fetched file changes that
  guard. Later, if the deploy's time matters again.
**The file limit:** 100,000 files per Worker version on Workers Paid (docs, 2026-11-03), about 72 per act: about 1,350
acts. Two ways past it:
1. *a second Worker* with the same site code serving part of `/ta/` by route (`atviri-teises-aktai.lt/ta/1*`; the most
   specific route wins, wildcards only at the end): its own 100,000 files. Requests to static assets are free and
   unlimited; Workers Paid (paid already) covers up to 500 Workers. **Cost: €0**; one more deploy step, the build split
   by path.
2. *article pages from R2 through the Worker*: every view of such a page becomes a Worker request (10 M a month
   included, then $0.30 a million) and an R2 read (10 M a month free, then $0.36 a million); storage within R2's free
   10 GB; nightly writes within its free 1 M only if unchanged pages are not rewritten (above). At today's traffic
   (11,000–105,000 requests a day, ~0.75 M a month) **€0**; a crawler storm of 10 M page views a month would cost about
   $7.
Recommendation: (1) when the site nears 95,000 files; to be decided before it is deployed (it changes how the site
is served, D-032).
*Addendum 2026-11-04, the host's other limit:* a `_redirects` file takes 2,000 static rules; two lines an act passed it
at 1,011 acts and the deploy was refused after a good build. The acts' own lines stay (Bulk Redirects land on them: one
per act, room to 2,000 acts); bare aliases fill the rest, shortest first ("/dk" is typed; Bulk Redirects match "/dk/" and
below, not "/dk"), so a long name's alias without its final slash can 404. The gate now fails on this limit and on files
over 25 MiB, before the deploy. **Past 2,000 acts** the `/ta/<act>/str/` lines must go too: Bulk Redirects aiming at the
act's page directly would do it (free). Bulk Redirects' own limit: 10,000 entries.
- *Addendum 2026-11-03 (3), the first batch through `bin/add_acts.py`:* every rule set our texts cite (129) and 25 laws
  of lasting substance (status of resistance participants and signatories, the free economic zones, the constitutional
  law on acquiring land, military statutes and training grounds; the one-off laws left out: reorganisations, debts,
  a year's army structure). 108 added (903 → 1,011 acts, 72,138 files); 46 held with reasons: 22 because data.gov.lt's
  Suvestine answered 500 while their texts were read (to add again), 10 named by a guess that differs from the text's
  heading (the check caught them; renamed for a retry), 4 with labels e-tar contradicts, 3 joint orders with an agency,
  2 unverifiable, 3 parser layouts, 1 order whose second document is ours, and the army's disciplinary statute (an
  approval law whose statute repeats article numbers: 103 empty pages, caught by the gate). Search benchmark 68/80
  top-1 (one lost: a new rule set on tax accounting documents now comes before PVMĮ for "pridėtinės vertės mokesčio
  tarifas").

## D-046 (2026-11-04): Up to 1,196 acts, chosen for what people meet; hygiene norms and building regulations
**Added** through `bin/add_acts.py`, all against e-tar or EUR-Lex: 26 held acts back after renames and the Suvestine
outage; 32 EU acts (those our texts cite most and those people need, in force, converted exactly: social security
coordination, consumer rights, Rome I, the food law, the supervisory authorities' regulations…); 127 hygiene norms (HN),
building regulations (STR) and Government rule sets (names and codes from the texts' own headings: HN 109:2005 is
HN 109:2016 now). 1,196 acts, 85,803 files, room to about 92,000 by the plan (D-045).
**Held with reasons** (130 in `scope/queued_seed.yaml`): 29 EU acts whose text fails the conversion check (REACH, CLP, the
waste, habitats and procurement directives: annexes or articles differ; to look at together, as a converter change), and
the Air Passenger Rights regulation (no Lithuanian text on EUR-Lex under that CELEX). Left out of the batch: HN 121, 16, 28,
78, 97, 130, 42, 66, STR 1.01.01, 1.02.03, 1.04.03, 1.05.03, 1.05.06, 2.01.01(2): no stamp, two documents or a
mixed-case heading.
**Formulas:** B73: the structural design regulations (STR 2.05.x) rest on formulas the open data lacks; they are in, each
such line marked and the act's page saying so (show as it is), rather than held back.
**Search:** 68/80 at this size: "sukčiavimas" finds an ESMA article before BK 182 (third). A title that is exactly the query
first fixes it and loses "kasmetinės atostogos" and "ligos išmoka" again (D-044): not adopted.

## D-047 (2026-11-04): The EU converter takes what it held back; annex footnotes are shown; the older HTML
**Why:** 29 EU acts failed the word check at D-046, 3 more were held earlier (CRR, MiFIR, PSD2), 3 of them as "no
Lithuanian text". The check was right more often than assumed when holding them: real text was being lost.
**Lost words the check caught, now kept:** a marker before a part's first paragraph taken for a paragraph (MiFIR 35, IED 73:
a whole first paragraph), words after an inline formula (CRR 132, 284, 325bc), an inline element between blocks (CRR 325ay's
"Tk ir Tl"), a number right in a div before its nested blocks ("c)" 2004/38 7, "1)" Brussels I 7), plain divs read twice
(PSD2 9), a heading class on text inside a flat article ending the article early (987/2009 25: its parts lost).
**Layouts now read:** the Journal's older classes (2004/48), a chapter's number in its own class (1024/2013), parts of
sections "POSKIRSNIS" (a heading rank of its own), headings with no number (92/43, marked by the converter, which knows
them from the XHTML's class; a heuristic on capitals changed 4 Lithuanian acts and was dropped), headings split over three
lines (2014/40), appendices inside an annex (REACH XVII: read twice, 69,396 words), annexes "II.A" and "A" and those with no
id, a text between annexes ("II–VI Priedų Preambulė", under the annex before it), articles quoted with no „ (CRR 520: a
chapter and articles of another regulation, marked as text of the article by the converter), "2 STRAIPSNIS", "26
straipsniai", "3 SKIRISNIS", "SEPTINTA A DALIS", "69-a" (EUR-Lex prints a second 69a so in 2011/61), "50-oC" as "50ºC".
**Not the act's text, left out of the check as of the page:** a Commission statement after the act (2018/302, Rome II), a
list of annexes before them (REACH).
**Footnotes (B74):** an annex's notes are shown at its end, with their marks; an article's too, unless they only cite a
source. D-037's "footnote references left out" now means those citations. 32 live acts gain 6,724 words; none lose any.
**The older HTML:** CELLAR answers `text/html` with the Lithuanian Special Edition text for acts adopted before accession
that have no XHTML: Working Time 2003/88, Air Passengers 261/2004, Temporary Protection 2001/55 (`eurlex.legacy_to_text`,
`check_legacy`). Another language is never taken (`lang="LT"` required). A figure EUR-Lex holds only as a picture ("+++++ TIFF
+++++", 2001/55 annex I) says so on the page. It is the act as adopted, so it is taken only when no later consolidation is
listed: never an older wording as today's. Six more tried, all pass the check (not added): 89/391, 93/13, 85/374, 2000/31,
1999/44, 2000/78; those amended since need the guard's answer first.
**Checked:** 133 EU acts through the check; old and new conversion of the 101 live ones compared word by word; the parse of
all 1,095 Lithuanian acts identical before and after. The nightly reconverts nothing: the state carries today's texts by
converter 8.

**Sitemap, found on the way:** one file held 64,799 URLs live, 80,775 at this size; the protocol's limit is 50,000. Above
45,000 `sitemap.xml` is now an index of `sitemap-N.xml` parts (`render.sitemap_files`, test); robots.txt still names
`sitemap.xml`, bin/indexnow.py reads the parts. Search Console should show whether Google had rejected it.

**Result:** 1,228 acts (133 EU), 90,329 files, 98 held; gate OK, no warnings, MCP OK, search 67/80 top-1 (68 at D-046; floor 65).
Order of the release matters: the state asset with converter 8's texts goes up only after the night on the old code, which
would otherwise convert all EU acts again by the old converter.

## D-048 (2026-11-05): 20 held acts back; the back-test's findings of 11-05 read
**Added** through `bin/add_acts.py`: 20 of the 30 retried (names corrected to the texts' headings, data.gov.lt answering
again): HN 18, HN 32, STR 2.01.01(3), 2.02.08, 2.05.10, 2.05.14, the address rules, the qualifications framework, the
vehicle register's rules, the flood risk and protected areas' rules and others. 1,248 acts, the room to 92,000 nearly used:
the next batch needs the second Worker or R2 (D-045), a decision to take.
**Held again, for what the checks found (78 in the queue now):** HN 122 (3 points labelled current with another wording than e-tar's), SGPNLT (1),
STR 2.01.01(4), (5), (6) and 2.05.05 (e-tar has no version matching, or a text difference), VSGPNAŠA (e-tar has today's
version only as files), and VSSEAT, VVNPKPVA, DTDSAA (a hard-wrapped old consolidation the parser doesn't read).
**The back-test:** B75. Its other findings were amendments reaching us days late in data.gov.lt's outage, flagged when they
did: no rule error. The name check treats "HN 18: 2007" as HN 18:2007.

## D-049 (2026-11-05): Search for the words people use; an audit of what works
**An audit from outside** (scenarios, every page and link of the build, Search Console): articles, dated pages, labels (97% confident),
feeds, structured data and links are sound. What wasn't: B76; `/api/related` and `/api/articles`, documented, 404 (not in
`run_worker_first`; a test now reads the Worker's routes against the list); errors answered HTTP 200; `list_acts` half a megabyte in an
agent's context; Google's sitemap report showed an error and 50,000 submitted (D-047's split); and search.
**Search, measured:** 112 realistic questions and citations written for this: about a third first before the work. The citations people
actually use failed outright: "GDPR 17", "NIS2 21", "AI Act 5", "dk52", "2019/944 15" nothing; "Energetikos įstatymo 15 straipsnis" and
"Reglamento (ES) 2016/679 6 straipsnis" a wrong article. Now: `scope/names.yaml` (GDPR for BDAR, also as addresses, /gdpr/17/), an act's
genitive and its EU number in any form; an act named alone gives its contents.
**Everyday words:** the law's words differ from people's ("alimentai", "bandomasis laikotarpis", "savo noru" are not in the articles'
titles). `scope/topics.yaml` sends them to the article, first, marked `suggested`; plain and reviewable, each target read against its
title when written (a third of the first draft was wrong from memory) and checked on every build. Not embeddings: a Worker has 50 ms of
CPU, and an answer must be explainable.
**General ranking:** an act's name counts only if a third of its own words are the query's (a long rule set merely holding "atostogas" no
longer outranks DK); the very word breaks ties inside an act; a word with no article tries one letter shorter; two words with no common
article give those with one of them, marked.
**Honest numbers:** the 80-question benchmark 67 → 75 first (top three 70 → 78); the 112 questions 105 first, but topics were written with
them in view. On 60 fresh questions the general ranking alone gave 34 first and 41 in the top three, and 45 and 51 after topics written from
their misses: expect roughly the first figure on what nobody has listed yet, and read Search Console for what to add.

**Also for people and agents (same day):** `/pakeitimai/` and each area's `/sritis/<slug>/pakeitimai/`: what changed in 14 days, by day and act (3,838 events until now only in Atom, which few read). "Kur šis straipsnis minimas" on article pages: references both ways, read from `/api/related` when opened, so no page grows. A page not found tries what its address meant (`/DK/52/` goes to the article, `/sukciavimas/` suggests BK 182). `get_article` gives a very long text in pieces with `next_offset`, and `find` looks inside it (CLP VI by CAS number): 1.4 million characters in one answer until now. The home page's "neteko galios" chip beside the Civil Code read as the whole code repealed: it now says how many articles; "nepatikrinti" is "neaišku", as the legend says.
**Left:** a term's link can name a part of a coming version only (133 links, 24 parts: it opens the article, not the part). Search takes 1.5 to 2.7 s when nothing is cached.

## D-050 (2026-11-09): A build every second day, and on the night a label changes
**Why:** GitHub Actions minutes (private repo: 2,000 free a month, then a $5 cap that stops the schedule when spent). With data.gov.lt
slow, a build took 60 to 80 minutes; by 11-09, 1,066 minutes were used and the month would have ended near the cap.
**What:** a small `plan` job decides. A scheduled run builds when the live site is two days old (or its day can't be read), or when
`api/v1/upcoming.json` has a label change after the live day and by today (in the next 30 days: 3 such days); otherwise it pings the
heartbeat and stops in seconds. A manual run always builds. A failed build is retried the next night by the same rule. Two schedules a
night instead of three; keepalive and the heartbeat job run only with a build.
**What it costs readers:** articles change state on known dates, and those nights still build. A newly published amendment shows up on
the next build, up to a day later than before; pages already say the day their labels were set. app.js's "labels set more than 2 days
ago" box stays off unless a build fails. The site says so on /apie/.
**Expected:** about 15 builds a month instead of 30-45 runs: roughly half the minutes. Going public would make standard runners free
(the end goal, after the pre-public review).

## D-051 (2026-11-09): A second Worker for the site's files
**Why:** a Worker version holds at most 100,000 static files; the site had 91,600 and the `_redirects` file was at its
2,000 rules. More acts need more room (decided 2026-11-09: a second Worker for the additional pages).
**What:** `lt-law-site-2`, files only (no `main`), route `atviri-teises-aktai.lt/ta/1*`: the acts whose TAR code starts with
"1" (582 acts, 41,384 files on 11-09); the main Worker keeps 50,219 (the other acts, EU, VERT, `api/v1/`, the MCP/REST
code). Split by route prefix because routes allow a wildcard only at the end of a path and the most specific route wins;
no service binding, so no Worker code runs for those pages. `bin/split_site.py` (standard library: the deploy job runs it)
plans the split from the `wrangler.site<N>.toml` routes; the nightly gate checks each part against the limits; the deploy
job moves the files, deploys the extra Workers first, then the main one, then asks one page of each part.
**Room:** about 50,000 more files on each Worker, so about 2,000 more acts of today's average size before a third Worker,
which is one more configuration file. Redirect rules are counted per Worker too (main 1,416, second 584).
**Cost:** none on Workers Paid ("Requests to static assets are free and unlimited"; no script). Same token, no new rights.
**Way back:** delete the route; deploy without the split while the site fits one Worker (OPERATIONS, "Second Worker").

## D-052 (2026-11-10): Rules approved by a resolution may be written in articles
**Why:** the TSO methodologies VERT approves (GADTMM, PPNMM, BTMMM; PORFPSDR held on 11-09) are drafted like EU network codes:
recitals ("Visi PSO, atsižvelgdami į tai, kas išdėstyta toliau: 1. … 17. …"), then "1 straipsnis" with the title on its own line
or on the same line without a period. `unit: punktas` was set for every act approved by a resolution or an order, so their pages
said "1 punktas" for article 1; the recitals were dropped; PORFPSDR was read as one article.
**What:** a seed with `resolution:` may say `unit: straipsnis`. Being approved by a resolution or an order (amenders found by date
and number: `source.POINT_ACTS`, `fetch_new_acts --amenders`) now follows `adopted`, not the unit; all 701 earlier such acts had
both. The parser reads "N straipsnis Title" where the whole document is written so; in a document after an approval stamp that
has numbered recitals it keeps the text between the stamp and article 1 as the preamble, takes an article's title from the next
line, and shows the resolution's own words ("Vadovaudamasi … nutaria: / Patvirtinti …") as for points acts. Re-parsing all
4,818 stored texts changes these four only.
**Way back:** drop `unit: straipsnis` from the four seeds (pages /str/N/ go back to /p/N/; none were live with /p/ yet).

## D-053 (2026-11-11): Older rule sets' "II. SĄVOKOS" are chapters, their restarted "I. …" sections
**Why:** rule sets drafted before 2014 head their chapters "II. SĄVOKOS, SANTRUMPOS" (no word "SKYRIUS"), some with sections
numbered from I again inside a chapter (EETEKT, ELIĮT, SPTPEĮĮT). The points parser knew only "II SKYRIUS": in 197 live rule sets
1,700 such lines were read as the last line of the point before them (the first chapter's into the act's tail), and the acts had
no chapters at all.
**What:** "N. TITLE" in the main document is a chapter (`skyrius`), and one numbered from I again inside it a section
(`skirsnis`); under the act's own "N SKYRIUS" chapters they are sections and their parts. The texts call these divisions
"skyrius" far more often than anything else (SPTPEĮĮT 32 times, ELIĮT 13), so the pages' paths say "II skyrius"; the heading's
words are the text's own. A line is one only in turn (a gap allowed, longer in capitals: repealed chapters), in capitals or a
short line a point follows, never right after "…:" (a list's item), and a chapter I only before the first point or after a
part's heading (else a table's row). Acts whose points start from 1 in each chapter (GAAPT: a standard per chapter) keep the
lines as text: chapter-scoped point numbers aren't modelled. Lines between such a heading and the next point stay where they
were. Re-parsing all stored texts: 271 change, in headings and those lines only; 16 changed energy acts match e-tar's copies.
**Way back:** revert the `_roman_heading` branch in points.py; the pages lose the chapter paths, the point URLs are unchanged.

## D-054 (2026-11-11): Seimas votes, a second part next to the acts (exploring; not released)
**Why:** asked how an MP voted on a law, an agent or a reader today has to open one lrs.lt page per vote; the
Chancellery publishes the votes as open data (`datasets/gov/lrsk/balsavimai` on data.gov.lt: 76,000 votes since 1997, 5.2 M
individual votes), but as raw rows with the draft and the law named only inside the agenda text, and nobody serves them
in a usable form (manoseimas.lt is gone, the Seimas' XML services didn't answer us). The aim: an API-reachable
register of votes, at least by the names of the laws: how one or another politician voted on a given law.
**What:** a separate part, `/seimas/`, beside the acts, from the same open-data portal and the same licence. First a proof
of concept on the branch `seimas-votes`: the current term (2024–2028), MCP tools `search_votes`, `get_vote`, `mp_votes`,
JSON served by the Worker (no HTML per vote: 76,000 more files). Votes are linked to the acts on the site by the law
number in the agenda item (57% of this term's votes name one of our 1,400 acts). Shown as it is: who voted how, on what,
with the lrs.lt record; no scores, rankings or measures of loyalty. Every answer says what the data lack: factions,
individual votes for consensus decisions (30% this term) and secret ballots, and presence.
**Way back:** the branch is not merged; nothing in the acts' part depends on it.

**Release plan (2026-11-12, prepared on the branch, not merged):** MCP tools only at first (no `/seimas/` pages). The
relay also forwards `/datasets/gov/lrsk/balsavimai/*` (still GET only, with the key; the relay redeploys on a push to
`main` that changes `worker/`, so merging is a deliberate step). The nightly fetches the newest term (~25 requests;
its time not measured yet: data.gov.lt's dataset queries hung on 2026-11-12) and builds the vote files after the acts' pages; a failure of either is a warning,
never a stop. The on-switch is `data/seimas` in the state asset (`bin/state_asset.py` packs it when present).

**Released (2026-11-15):** merged as planned; the relay
redeployed with the votes' path; `data/seimas` (terms 9 and 10, 10 files) added to the state asset that morning. A
term's full fetch took 162 s from Lithuania; the nightly gives it at most 10 minutes, none on a night whose fetches
already took 30, so the acts' job keeps its 90 minutes. Live with the next build (D-050: every second day).
Way back now: drop `data/seimas` from the state asset (the nightly stops fetching; the tools say the votes are missing),
or revert the merge.

## D-055 (2026-11-15): The code is published as snapshot commits; the working repository stays private
- **What:** a public repository (`marrgss/lt-law`) holds the working repository's tracked files as one commit per publication
  (`bin/publish_code.py`), authored with a GitHub noreply address. The working repository, with its history, the build,
  the secrets and the `state` asset, stays private.
- **Why not make the working repository public** (D-022 planned a fresh single commit there): commits that a rewritten
  history no longer reaches stay retrievable on GitHub by their hash, and the earlier runs' logs would become public
  with the repository. A new repository has neither.
- **Why now:** in early November Google dropped the site from its index (pages crawled but not indexed, every request
  answered 200: a judgement of the site as a whole, not a fault of its pages). Open code is one of the few honest
  signals of what the site is; the MCP registry entry can name its source; others can check and correct the rules.
- **The guard:** every publication is scanned for local paths, mail addresses, wording about who asked for what, and a
  private list of names and identifiers; a hit stops it.
- **Later, if wanted:** the build moves to the public repository, its secrets set there anew (the relay's address as a
  secret: a variable is printed in a run's log). Actions minutes are then free and the build can run every night again
  (D-050).
- **Way back:** delete the public repository; nothing in production reads it.

## D-056 (2026-11-17): The night fetches only what changed; the site artifact is deleted once deployed
- **What prompted it:** GitHub's notice that 90% of the plan's 0.5 GB-month of Actions storage was used by the 17th,
  and the minutes: 1,499 of the 2,000 free by 2026-11-16.
- **Storage:** the built site goes from the build job to the deploy job as an artifact: 684 MB zipped, kept 1 day (the
  shortest GitHub allows), so each build cost 0.023 GB-month, and November's first half had 29 builds. The last job
  now deletes it after a successful deploy: minutes of storage instead of a day. That job gets `actions: write` and
  runs no code from the repository; a failed deploy keeps the artifact for its day, for "Re-run failed jobs".
- **Minutes, measured (the build of 2026-11-16, 58 minutes):** fetching 29, building the pages 14, checks and saving 5,
  deploy 10. Of the fetching, the texts step used its whole 20-minute budget on each of the last four builds and
  still left 125 to 1,298 acts "not refreshed": a warning every night, which therefore said nothing.
- **Why the texts step was slow, though nothing had changed** (that night no Lithuanian text's revision differed from
  the one its last full fetch saw):
  1. EU acts were asked for one at a time, two queries each; the version list's query reads every CELEX number there
     is (6–15 s). 170 acts: 17–40 minutes on their own.
  2. D-039's full re-fetch (a seventh of the texts a night, a 10-day ceiling) was sized for 375 acts and nightly
     builds. With 1,425 acts and a build every second night most texts were always due, and the order (longest
     unchecked first) put them ahead of a text that had really changed.
- **Now:**
  - the acts whose revision is unchanged are checked first, without a request (all of them in a second); then the ones
    that need the network: amended acts, Lithuanian before EU, the longest unchecked first;
  - EU acts: every version list and all metadata in a few queries (`eurlex.versions_of`, `metadata_of`: typed values,
    which the endpoint finds by its index; 3 s for 170 acts). Checked against the lists the slow query had stored:
    the same for all 170 acts with the link "based on"; the link "consolidates" missed versions for 16 acts and is
    not used. If the batch's list ever lacks a version we held, the slow query decides for that act, so an older
    wording never becomes today's because a link was incomplete;
  - the full re-fetch stays as a backstop: 5 minutes a night, the longest unfetched first (40–300 texts by the
    source's speed), with a ceiling of 60 days in `snapshot`. A text that differs there under the revision we were
    told is reported in the night's warnings: revisions could not be trusted then.
- **Why revisions can carry this:** over 17 days (2026-10-31 to 11-17) on 369 acts, 13 revisions changed and all 13
  texts had changed; 356 revisions did not change and none of those texts had.
- **Rehearsed** on a copy of the build's state with real requests: the texts step took 173 s instead of 1,200: all
  1,425 acts checked, nothing to fetch, 122 texts re-fetched in full in 2 minutes, no warnings.
- **Expected:** a build ~44 minutes instead of ~58; a month of builds every second night ~800 of the 2,000 minutes
  (was ~1,100), storage near zero.
- **Considered, not done:**
  - *Stopping the schedule and building by hand:* a build by hand costs the same minutes, and between builds the
    labels would age without anyone deciding so (D-050 already skips the nights when nothing can change).
  - *Building or uploading only the changed pages:* every page states the day its labels were set, so every file
    differs each build (the deploy uploads all ~99,700; 7 minutes). Pages without that day would upload in seconds,
    but the day on the page is what a reader, or an assistant that runs no scripts, checks a label against.
  - *Moving the build to the public repository (D-055):* minutes and storage are free there. Still the answer if the
    scope doubles; not needed at these numbers.
- **Way back:** `BACKSTOP_S` and `FULL_EVERY_DAYS`; without the `prefetch_eu` call each EU act is asked for alone, as
  before; without the workflow's last step the artifact expires in a day.
