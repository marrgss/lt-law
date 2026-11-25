# The problem, in detail

Working draft, 2026-10-17. Evidence comes from our own probes (`research/`) unless a URL is cited.

## 1. What a person sees

You ask ChatGPT, Gemini, Copilot or Claude: *"Ką sako Darbo kodekso 52 straipsnis?"* or *"What does Article 21 of the Lithuanian Electricity Law say today?"* One of three things happens:

1. **It answers from memory.** The text is whatever the model saw during training, months or years old, possibly paraphrased, with no date and no source. Lithuanian law changes constantly. The Electricity Law alone has had **8 amending laws published since May 2025**.
2. **It searches and lands on the wrong page.** That might be a draft amendment on e-seimas, a VMI PDF, a news story, or a commercial site that only shows part of the text.
3. **It tries the official source and gets nothing usable.** It then says "I couldn't access e-tar.lt" or guesses.

None of these is a model-quality problem. **The current text of Lithuanian law is not published in a form these tools can read.**

**How big the problem is (red-team test, 2026-10-17):**
- **Popular articles mostly work.** "Darbo kodekso 52 straipsnis" got a correct answer through lrvalstybe.lt.
- **The long tail fails:**
  - Electricity Law Art. 21: stale version reported as current.
  - CK 6.188: no article text at all, only drafts and PDFs.
  - Government resolutions and orders: barely reachable.
- **"Which version applies today?" fails almost everywhere.**
- **Wrong answers are silent.** Users don't notice, so demand is invisible until something better exists.

The real target is therefore **the long tail plus correct versions**, not "DK 52".

## 2. Why: four layers, each broken in a different way

### Layer A: the official website (e-tar.lt) is current but machine-hostile
Measured on 2026-10-17 using the Electricity Law page (`TAR.F57794B7899F/asr`):
- The page is a **1.29 MB shell**. The law text isn't in it; it loads inside an `<iframe>` (`/rs/actualedition/…`), which is another **2 MB** of HTML.
- AI fetch tools (ChatGPT-User, Claude, Perplexity) **don't run JavaScript and don't follow iframes**. They see a table of contents. A fetcher that did follow the iframe would still drop most of a 2 MB page.
- There are **no per-article URLs**, so a tool can't fetch "Article 21" on its own.
- There's no sitemap, no meta description, no canonical tag and no ELI metadata. Search engines index it poorly at article level.
- e-seimas.lrs.lt sits behind a **Cloudflare bot challenge** (HTTP 403 for non-browsers).

### Layer B: the official open data is machine-friendly but stale where it matters
Since mid-2025 (announced 2025-07-02) the Seimas Chancellery has published the register on data.gov.lt (`gov/lrsk/teises_aktai`). That's a real step forward:
- `Dokumentas`: **480,063 acts** with full text and metadata. **Current**: newest act published 2026-10-15, checked 2026-10-17. *(Corrected 2026-10-18.)* For amended acts, the text is **the newest consolidated version**, often a *future* one (DK from 2027-01-01, PVMĮ from 2029-07-01). It is not the original act. See `research/2026-10-18_dokumentas_holds_consolidations.md`.
- `Suvestine`: **333,292 consolidated versions** with valid-from and valid-to dates. **A one-time load**: no row has been refreshed after **2025-06-01**. The dataset changelog says "2025-06-13: consolidated data added; consolidated texts currently reachable via the given link". When asked for API access to current consolidations (data request 14363), the Chancellery answered that it requires **a signed data-receipt contract**. So this is a policy gap, not an unnoticed bug.

**What that means in practice.** For the Electricity Law, the dump's newest consolidation was built on 2025-05-02. e-tar.lt today shows a version valid **2026-09-15 to 2026-10-31**, and that version isn't in the dump. The dump also contains "future" versions (2026-01-01, 2027-01-01, 2030-01-01) computed in May 2025, before 8 later amendments. **Anyone who builds on the dump and asks "what applies today" gets a confident, wrong answer.**

The `Dokumentas` table does contain the amending acts themselves. Until the official consolidations catch up, the honest move is to show the last official consolidation and, next to it, list the amendments published since.

### Layer C: the existing mirrors are closed to AI, partial, or thin
| Who | What it has | What it lacks for AI use |
|---|---|---|
| infolex.lt (commercial) | article pages, sitemap | **blocks GPTBot, OAI-SearchBot, Claude-SearchBot, PerplexityBot** in robots.txt |
| lrvalstybe.lt | article pages | **blocks ClaudeBot, GPTBot, OAI-SearchBot, CCBot** |
| temidy.lt (commercial, has its own AI) | AI-friendly, good SEO | only about 10 codes; wrong titles for CK dotted articles |
| temidy.lt MCP | current, historical and future versions, diffs, 2.1M court decisions | **paid plans only** (about €40–250/mo), OAuth |
| lrvalstybe.lt | | also serves **stale** versions (its DK 52 page cites 2017) |
| Ansvar MCP | about 12k statutes, 90k provisions | OAuth sign-up; laws only; repo archived; probably built on the stale dump |
| MateMatic lt-eli-mcp | local MCP | title search only, whole act, no versions, no article IDs |

Article-level mirrors already outrank e-tar in search for queries like "DK 52 str.", so the format works. But each one has a catch:
- **Partial access for AI.** Infolex lets in only Googlebot and Bingbot, so Gemini and Copilot can use it but ChatGPT, Claude and Perplexity can't.
- **Training bots only.** lrvalstybe blocks training bots, not user fetchers.
- **Narrow coverage.** temidy's free pages cover about 10 codes.
- **Stale text.** lrvalstybe serves outdated versions.

Nobody offers **open, current, versioned, article-level** text for the whole body of law.

### Layer D: assistants don't know any of this exists
Even a perfect MCP server only helps people who install it, and almost nobody installs MCP servers. The default path for every assistant is **web search, then fetch the page**:
- ChatGPT search uses OAI-SearchBot plus Bing.
- Gemini uses the Google index.
- Copilot uses Bing.
- Claude uses Brave.
- Perplexity uses its own index.

**The site that wins is the one that ranks in Bing, Google and Brave for "DK 52 straipsnis" and serves the article as plain HTML.** That's an SEO problem, not an AI problem.

## 3. Why nobody has fixed it

- **The state** made a big move in 2025 (the open dump) and stopped there. It implements only ELI Pillar 1, has no article-level IDs, and gives current consolidations only under contract. The fix is on its roadmap, but slowly:
  - the new TARIS rules (in force 2026-07-01) add an ELI field and a classifier of structural parts;
  - the €2.64M **VYTIS** modernisation was tendered in 2026-05 for 37 months;
  - the Chancellery's plan puts TAR after TAIS, around 2028–30.
  
  Realistically, official article-level open data arrives **2029 or later**. That's the window this project fills.
- **Commercial providers** make money from access. Blocking AI crawlers, or putting an MCP behind a paywall (temidy), is rational for them.
- **Foreign MCP vendors** wrap whatever the dump contains, staleness included, behind a sign-up.
- **Civic projects elsewhere** show the usual pattern: a volunteer builds a mirror, it's great for 2–3 years, then the maintainer stops and it dies (France's `france.code-civil` in 2015, Germany's `bundestag/gesetze` in 2022).

## 4. What "solved" looks like

Anyone, or any AI, asking about a Lithuanian legal provision can within one search and one fetch get:
1. the exact text of that provision, as of a given date;
2. the official TAR link and the date the text was last checked;
3. any amendments published but not yet reflected, flagged at article level;
4. no sign-up, no install, no JavaScript required.

If the state later publishes this itself, the project has succeeded and can retire. What carries over then is the example (addresses, labels and their rules, the machine formats), not the pipeline: the register's own systems already hold what this project rebuilds from the open dump (D-061).

## 5. What this project is not
- Not legal advice, and no AI-generated answers or summaries presented as law.
- Not an unofficial consolidation. **We never apply amendments ourselves.** We mirror the consolidations the Seimas Chancellery prepares and flag what's pending. Consolidations aren't legally "official" either: only publication in TARIS is (Teisėkūros pagrindų įstatymas Art. 19(3), Art. 2(5)).
- Not a home for individual acts that name people (citizenship, pardons, awards, appointments).
- Not a commercial competitor to infolex. The audience is people and AI assistants that infolex blocks.
- Not affiliated with any institution, company or employer; an independent personal project.
