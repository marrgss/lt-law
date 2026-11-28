# Roadmap

What isn't built yet, in order. How the current system works is in [ARCHITECTURE.md](ARCHITECTURE.md); why, in [DECISIONS.md](DECISIONS.md).

## Where we are (2026-11-25)
- **Public since 2026-10-23** (D-031); repository private. Served by two Workers as static assets (D-032, D-051: the main
  Worker `lt-law-mcp` with the MCP/REST code, `lt-law-site-2` for `/ta/1*`), Workers Paid. A build every second day, or
  sooner when a label changes (D-050), to stay within the $5 Actions cap.
- **1,865 acts** (1,666 live from the 2026-11-26 build, 199 more with the next release): the Constitution, every code and the
  laws and statutes (530 in all); 1,164 sets of rules approved by Government resolutions, ministers' orders and the energy regulator (D-025, D-033,
  D-034, D-052); 171 EU acts from EUR-Lex (D-037). Energy in depth first: `/sritis/energetika/` (every cited rule set the
  energy minister and VERT have in force is in) and `/vert/` (the regulator's decisions). Since 2026-11-24 every sector
  (D-060): every rule set our texts cite is in, and the rest are added by how often they are amended (6+ times, then 3–5 times: health, education,
  farming and food, transport, social security, environment, the state). Held back by the checks:
  `scope/queued_seed.yaml`, each with its reason.
- **Checked against e-tar** before an act goes in (`bin/add_acts.py`: text, labels, recovered texts); the whole scope
  last on 2026-10-27 (0 wrong "current" labels on 22,244 articles and points). Parser changes are checked by re-parsing
  every stored text and comparing changed acts with e-tar (2026-11-11: D-053 and the annex-header fix).
- For agents: MCP and REST at `/mcp` and `/api/*` (D-028), in the official MCP registry; past versions since 2020
  (`date=`, `/kaip-buvo/`, D-029/D-030). Search answers in ~1 s for a new query, 0.1 s repeated.
- Built and in daily use: change feeds (Atom), cross-reference links, full-text search, defined terms, the ledger (D-024),
  Constitutional Court rulings (B3), print stylesheet, topic pages, Seimas votes (MCP since 2026-11-15; each amending
  law's adoption vote on article pages and in the API from 2026-11-26, D-059).

## Next
1. **Energy, the rest** (D-033, D-034):
   - ~~fuel quality (the joint order 1-348/D1-1014/3-742)~~ (added 2026-10-29);
   - ~~links from decision texts to the rules, orders and law articles they cite~~ (done 2026-10-28: a law article links to today's text for a decision that applies now, to the article as it was on the decision's day for older ones since 2020).
2. **The regulator's price tables** (D-034 option B): the annexes are on e-tar only. Ask the Chancellery whether copying them is acceptable (with the follow-up letter); until then each decision links to them.
3. **The back-test for the acts added since 2026-10-23** (and KET: its Suvestine versions aren't in `suvestine_scope.jsonl`), once the open data's Suvestine table answers again (it times out nightly since 2026-10-24).
4. **Fewer unnecessary flags:** 137 articles and points (0.6%, 2026-10-28, after B63 and B64; 258 on 2026-10-27) are flagged although e-tar shows them unchanged; most are true warnings now (MSĮ: the Chancellery's lag; ŠTVT: a past stored text).
5. **A weekly e-tar sample check.** Validation runs by hand after big changes (D-004); ask the Chancellery whether a small weekly automated check is acceptable.
6. **SEO from data** (after 2–4 weeks of Search Console): titles and descriptions for the queries that bring people (done 2026-10-28: act titles say "aktuali redakcija", snippets continue past a colon); `bin/search_console.py` reads the numbers with the read-only key (OPERATIONS); the AI panel re-run (`research/ai_panel/queries.md`).
   - Demand seen 2026-10-22..26: STR 1.07.03:2017 (statinių techninė priežiūra). ~~Added 2026-10-29~~ with 8 more of the most-amended STRs; STR 2.02.01:2004 (gyvenamieji pastatai) left out: its text prints points 1–10 twice and point 259 decodes as 2⁵⁹ (a silent error); it is repealed from 2027-01-01 (`scope/queued_seed.yaml`). Its replacement STR 2.02.12:2026 „Pastatai“ (from 2027-01-01) added 2026-10-30. Re-check positions for "statinių priežiūra" in a week.

7. **EU law (D-037, from 2026-10-29):** 15 acts from EUR-Lex for data, IT and cyber security (GDPR, NIS2 and
   2024/2690, the AI Act, the Data Act, the Cyber Resilience Act, eIDAS, the electricity regulation and directive, the
   electricity cyber security network code, the metering-data regulation). ~~EU acts' own bare references as links~~
   (done 2026-10-29). ~~Annexes checked against EUR-Lex like the articles~~ (done 2026-10-29). Added the same evening: CER
   2022/2557, REMIT, the Cybersecurity Act 2019/881, ePrivacy 2002/58. ~~Tables as tables~~ (done 2026-10-30). ~~An independent check of the whole text~~ (done 2026-10-30: it found SOGL's and NC ER's annexes missing). Added
   2026-10-30: the electricity network codes RfG 2016/631, DCC 2016/1388, SOGL 2017/1485, NC ER 2017/2196 (19 EU acts). Added 2026-10-30 afternoon: gas (Methane Regulation 2024/1787, the gas and hydrogen package 2024/1789 and 2024/1788, gas security 2017/1938), RED 2018/2001, the efficiency directive 2023/1791, EBGL 2017/2195 (26 EU acts); images (formulas, figures) shown.
   Next: more acts by demand (DORA is finance; HVDC 2016/1447 and CACM 2015/1222 are cited, less for a distribution
   operator; the RfG/DCC revision once adopted). Lithuanian side added 2026-10-29: NKSC's
   (compliance checks, audit methodology, training) and VDAI's orders (DPIA list, breach notification, standard
   processing-contract clauses, fines), the national-security objects and state-secrets laws, the energy companies'
   protection requirements. Government resolution No. 818 added the same day: the cyber security requirements, the
   entity identification methodology, enforcement measures and the national incident plan (its stored consolidation is
   the 2031–2035 version; today's text comes from the 2026-06-27 consolidation, checked).
8. **Agents' research (D-036, done 2026-10-29):** `get_articles`, `related` (references both ways, incl. regulator
   decisions), search snippets and alternative wordings, the research Skill and MCP prompt. Next, if usage shows the
   need: references to rules' points from other acts ("Taisyklių 12 punktas" of another act: today only within the act).
9. **From the user report (D-035), still open:** ~~definitions by reference~~ (P10, done 2026-10-28); ~~a concept-graph export~~ (S11, done 2026-10-28). Nothing left from the report.

10. **Seimas votes (D-054; step 1, the MCP tools, released 2026-11-15).** A second part of
    the site next to the acts: who voted how in the Seimas, from the Chancellery's open data (`datasets/gov/lrsk/balsavimai`
    on data.gov.lt: 76,000 votes since 1997, 5.2 M individual votes). Nobody serves this in a usable form (lrs.lt one page per
    vote, apps.lrs.lt didn't answer us, manoseimas.lt is gone).
    - Step 1 (POC): the current term's votes, nightly sync, MCP tools `search_votes`, `get_vote`, `mp_votes`; JSON served
      by the Worker, no HTML pages (the file limit).
    - Step 2: ~~on an article page, the adoption vote of the law that changed it~~ (done 2026-11-24, D-059: in the notes
      and the API's `adoption_votes`, 2,124 laws of terms 9–10); `/seimas/` pages per draft (its stages and votes) and
      per MP: not yet (the file limit).
    - Step 3: earlier terms (back to 1997); the drafts' metadata (`pasiulyti_ta`).
    - Not in the data, said on the pages: factions; individual votes for consensus decisions ("bendru sutarimu", 30% this
      term) and secret ballots; who was present but didn't vote. Draft texts are only on e-seimas (linked).
    - Shown as it is: no scores, rankings or loyalty measures; every vote links to its lrs.lt record.
11. **Search under 1 s for new queries:** measured 2026-11-11, a file's first read at a Cloudflare location takes
    250–430 ms whatever its size (60 ms after), so a new search costs its rounds of reads (the acts' list, the index
    files, the item blocks, the article texts for the snippets: 4 rounds, 0.9–1.5 s), not its bytes; splitting the large
    shards would add files to be read cold, not speed. ~~The index files read with the acts' list~~ (done 2026-11-11: one
    round less on a fresh Worker). ~~Fewer item blocks~~ (measured 2026-11-13 on the 11-13 build, 80 questions: at most 8/5/4/3 blocks → top-1 75/76/75/73, top-3 78/78/77/75, 6.0/3.9/3.1/2.4 reads a search; the reads run at once, so 6 → 4 saves ~10 ms of the slowest, while lower results shift both ways ("smulkusis chuliganizmas" gets electrical rules at 2–3): not worth it, kept at 8). What costs is the number of rounds; the next idea would be one round less (the snippets' texts read with the item blocks).
12. **Tables as pages:** VERT's technical requirements (BTRN2MRR, BTRN2MR2R) and the meter list (MPGPIS) are tables; held
    until a table can be a unit.
13. ~~**EU decisions**~~ (CELEX `3…D…`; done 2026-11-11, on main, not released: the market stability reserve 2015/1814,
    RSRS; its kind "Sprendimas", cited as "Sprendimo (ES) 2015/1814 1 straipsnio" from the ETS directive and others (20
    pages link to it), "šio sprendimo N straipsnio" within it). More decisions by demand.

## Corpus
- **More laws and rules, chosen by search demand** (Search Console, the MCP search log is not kept: aggregate counts only). Candidates are ranked by how often other acts amend them.
- **Every sector** (D-060, 2026-11-24): 240 acts added across health, education, farming and food, transport, social
  security, environment and the state (`rank_candidates.py rules --by amendments`); next (2026-11-26), 217 rule sets
  amended 3–5 times and at least twice since 2022 (`scope/batch-2026-11-26-amended3to5.yaml`; one institution's statutes,
  ministries' internal rules and closed programmes left out by hand); after that, the laws still left out and rule sets
  amended fewer times.
- Left out on purpose: individual acts naming people. (Profesinių sąjungų įstatymas was left out as "only the 1991 text"; its
  2013 consolidation was there under an old e-tar id, B66: added 2026-11-03.) Acts held back by the checks wait in
  `scope/queued_seed.yaml`, each with its reason.
- **The procedure for every new act** (OPERATIONS: Releases), one command since 2026-11-03:
  0. candidates: `bin/rank_candidates.py laws|rules [--issuer …] --seeds` (in force, not on the site, ranked by citations in
     our texts); the seed lines go into a batch file, each with `area: <slug>`;
  1. `bin/add_acts.py <batch.yaml>`: seed, resolve, fetch (amending orders first for points acts: without them an old
     text reads as current, 61 silent errors on 2026-10-31; then snapshots, version lists, today's texts, through
     data.gov.lt's 500s and 429s), the name/document/area checks (`ltlaw.scopecheck`), the three validators on the batch
     (`validation/*.json` put back after), failures held in `scope/queued_seed.yaml` with reasons, areas, the gate.
     Resumable: a rerun goes on after the last finished step (`--from STEP` to redo);
  2. review the report and `bin/diagnose_silent.py` for held acts worth fixing; commit;
  3. `bin/state_asset.py pack` and `upload` (the nightly's data), release, then `bin/cf_redirects.py --apply` and `--check`.

## Features
All progressive enhancement: every word of law and every link stays in the HTML (D-017).
- **Accessibility, still to do:** the sidebar after `<main>` in the source (the skip link covers it meanwhile; moving it would make the visual and reading order differ on mobile). ~~Real headings in contents pages~~ (done 2026-10-29: parts, chapters and sections are h2–h6).
- **Mobile:** clearer two-date wording on pages that have a future version.
- **KET:** sign and marking images exist only on e-tar (annex pages say so); watch whether the open data's KET consolidation (ends 2025-12-31) gets a newer one.
- **Bulk downloads** (a weekly zip; Hugging Face: later).
- **The public repository** (D-055; `marrgss/lt-law`, since 2026-11-15): the code as snapshot commits
  (`bin/publish_code.py`); the working history and the build stay private. Next: the MCP registry entry gets `repository` (url, source, GitHub id;
  `bin/mcp_registry.py`) and a new version. Later, if wanted: the build moves there, GitHub Actions minutes become free
  and the build can go back to every night (D-050).

## Go / no-go (4–12 weeks after launch)
**Measure:**
- indexed pages and impressions (Search Console, Bing Webmaster Tools);
- citations in AI answers (Bing's AI performance report, the AI panel each month) and assistants fetching pages (`ChatGPT-User`, `Claude-User` in Cloudflare's statistics: ~90 a day by 2026-10-26).

**Go:** impressions grow and AI answers start citing the site, or the Chancellery shows interest (in the ideas: addresses, labels and their rules, the formats; not in running this pipeline, D-061). Then all laws in force and the most-used rules.

**Stop or pivot:**
- if the official sources start offering the same (current text per article, machine-readable), retire the project and point to them;
- if nothing gets indexed, rethink distribution before writing more code.
