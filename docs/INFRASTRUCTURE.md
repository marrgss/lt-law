# Infrastructure: where things run, where data live, limits

One page for the operator (state of 2026-11-11). How the code works: [ARCHITECTURE.md](ARCHITECTURE.md). Settings and runbook: [OPERATIONS.md](OPERATIONS.md).

## Accounts
| Service | Account | What it holds | Cost |
|---|---|---|---|
| GitHub | `marrgss`: the working repository `marrgss/atviri-teises-aktai` (private) and the public code repository `marrgss/lt-law` (snapshots, D-055) | code, workflows, secrets, the `state` release asset and its weekly copies | free plan; Actions budget $5/month with a stop at the limit |
| Cloudflare | the maintainer's account, **Workers Paid** | the Worker `lt-law-mcp` serving the site (D-032), the relay Worker, the R2 bucket `lt-law-history` (EU), the Pages project (fallback), DNS, Bulk Redirects, firewall rules, email routing | $5/month (10 M Worker requests included) |
| Domain registrar | `atviri-teises-aktai.lt`, paid 2 years | nameservers point to Cloudflare | ~€10/year |
| healthchecks.io | the maintainer's | the nightly heartbeat | free |
| data.gov.lt | none: public API, no key | the source | free |
| MCP registry | domain-authenticated (`/.well-known/mcp-registry-auth`) | the entry `lt.atviri-teises-aktai/lithuanian-law` | free |

No server of our own, no database, no personal computer in production (D-006).

## Domain, DNS and mail
| Record | Value | Why |
|---|---|---|
| CNAME `@`, `www` | `atviri-teises-aktai.pages.dev` (proxied) | the Pages custom domain; the Worker route `atviri-teises-aktai.lt/*` sits in front of it (D-032) |
| MX ×3 | `route1–3.mx.cloudflare.net` | Cloudflare Email Routing: `kontaktai@` → the maintainer's mailbox; catch-all off |
| TXT `@` (SPF) | `v=spf1 include:_spf.mx.cloudflare.net ~all` | written by Email Routing |
| TXT `cf2024-1._domainkey` | DKIM key | written by Email Routing |
| TXT `_dmarc` | `v=DMARC1; p=reject` | the domain sends no mail: forged mail "from" it is rejected |

`www` redirects to the domain (Bulk Redirects). HSTS 6 months with subdomains. The launch removed the Access gate (D-031).

**Protection and cost limits (zone and account):**
- rate limit "Worker paths": 50 requests per 10 s per address on `/mcp`, `/api/`, `/kaip-buvo` → block;
- firewall rule "Block RU and BY" (first, 2026-10-29): `ip.src.country in {"RU" "BY"}` → block, the whole site incl. `/mcp` and `/api/` (Russia: ~880 requests a week, 0.5%, mostly crawlers; a VPN gets round it);
- firewall rule "crawlers off dated pages": known AI and SEO crawlers blocked on `/kaip-buvo` (noindex pages; Meta's crawler ignored robots.txt, 2026-10-26);
- the Worker's CPU cap: 50 ms a request;
- usage alerts: Workers requests 2 M, CPU 10 M ms, R2 class B reads 5 M a month.

**Tokens, least privilege:**
- GitHub secret `CLOUDFLARE_PAGES_TOKEN` ("lt-law GitHub: deploy site (Pages)"): Pages only; the fallback deploy;
- GitHub secret `CLOUDFLARE_MCP_TOKEN` ("lt-law GitHub: deploy MCP (Workers)"): Workers Scripts and Routes, R2; the nightly deploy of the site's Worker since D-032 (accepted: Cloudflare can't limit it to one Worker);
- GitHub secret `CLOUDFLARE_RELAY_TOKEN` ("lt-law GitHub: deploy relay (Workers)"): the relay workflow;
- `RELAY_KEY`: shared with the relay Worker; the build job holds no Cloudflare token;
- the maintainer's local Cloudflare token ("lt-law local (maintainer PC)": DNS, Access, Pages, Bulk Redirects/Rulesets/Lists, zone and account analytics read) and `GITHUB_READ_TOKEN` (fine-grained, read only: Plan, and this repository's Actions, Contents, Variables, Administration), R2 keys and the MCP registry signing key never leave the maintainer's machine (`~/.config/lt-law/`, chmod 600).

## Where compute runs
```
 00:05 Vilnius  Cloudflare cron (relay Worker) ──dispatch──► GitHub Actions "nightly"
                                                             (GitHub's own cron as fallback)
 GitHub Actions runner (US, Ubuntu, 10–40 min)
   ├─ restore state  ◄── GitHub release asset "state" (state.tar.zst, ~165 MB)
   ├─ fetch  ──► relay Worker (Cloudflare, pinned to Stockholm) ──► get.data.gov.lt   (budgets: ARCHITECTURE §6)
   ├─ build site (Python, ~100k files), checks, ledger
   ├─ save state ──► release asset "state" (weekly dated copies kept)
   └─ deploy job ──► Worker lt-law-mcp: code + static assets + route /*;
                     Worker lt-law-site-2: static assets for /ta/1* (bin/split_site.py, D-051)
 Readers and bots ──► Cloudflare: static files (no code runs, free)
 /mcp, /api/*, /kaip-buvo/, unmatched paths ──► the Worker's code (R2 history for past versions)
```
- **Why the relay:** data.gov.lt refuses requests from outside Europe (D-018/D-019).
- **e-tar.lt** is used only by the validators, run by hand on the maintainer's machine (D-004).
- **EUR-Lex** (EU acts, D-037) and the **Seimas votes** (D-054, data.gov.lt) are fetched the same way.

## Where data live
| Data | Where | Kept |
|---|---|---|
| Act texts, daily snapshots (only when changed) | `data/dokumentas/` in the state asset | release asset `state` (overwritten nightly; weekly copies `state-YYYY-Www`, newest 12) |
| Law, resolution and order metadata | `data/state/laws.jsonl` | state asset |
| Amending-act texts | `data/amending/` | state asset |
| Older official versions (Suvestine) | `data/suvestine/`, `data/dokumentas/<id>/suvestine.json` | state asset |
| The regulator's decisions: metadata, texts | `data/state/decisions.jsonl`, `data/decisions/` | state asset |
| Prediction ledger | `data/state/ledger.json` | state asset |
| Article history since 2020 (dated pages and answers) | R2 `lt-law-history` (EU), from `bin/export_history.py` / `upload_history.py` | R2 |
| Validation results | `validation/` | git |
| The built site | the Worker's assets (each deploy a version); Pages; a GitHub artifact between the build and deploy jobs, deleted once deployed (D-056) | Cloudflare keeps versions |
| Secrets | GitHub secrets; Worker secrets; `~/.config/lt-law/` | never in git |

## Limits and thresholds
| Limit | Value | Our use | When it bites |
|---|---|---|---|
| Worker static assets: files per version | 100,000 per Worker (Workers Paid) | 116,918 on two Workers (1,666 acts, 2026-11-24: 62,769 + 54,149; ~70 per act) | a third Worker at ~2,800 acts (`bin/split_site.py`) |
| Static asset requests | free, unlimited | all page traffic | never |
| Worker requests | 10 M/month included, then ~$0.30/M | ~1–40 k/day (agents, dated pages, 404s) | alerts at 2 M |
| Worker CPU | 50 ms cap per request (ours) | search is the heaviest | an oversized query is cut (300 characters, 12 words) |
| R2 | 10 GB, 10 M reads/month free | the article history | alerts at 5 M reads |
| Bulk Redirects | 10,000 entries account-wide | 1,433 (2026-11-11) | not soon |
| Pages (fallback) | 20,000 files | exceeded since 2026-10-26: the fallback keeps the newest site that fit | — |
| GitHub Actions | 2,000 min/month free (private repo) | a build every second day (D-050) | the $5 budget, then stop |
| GitHub release asset | 2 GB per file | ~165 MB | not soon |
| data.gov.lt | no published limit; often slow | one request at a time, budgets | an outage: rebuild from cache, banner after 2 days |

**Our own thresholds:** data older than 2 days → a banner on every page; an act losing more than 2% of its articles → its previous text is kept; a law list under 10,000 → the run fails; HTML and JSON-LD disagree → the run fails; the quality bar (D-024): no known wrong "current" label.

**Watching it:** `uv run bin/checkup.py` (availability, integrity, probes, security headers, secrets, freshness, Cloudflare usage, GitHub billing and Dependabot): exit 2 means critical.

## What a reader or an AI gets
| For | URL | Content |
|---|---|---|
| Everyone | `/ta/<TAR code>/str/<n>/`, `/p/<n>/` | one article or point: text, status badge with its end date, notes, future text |
| Short forms | `/dk/52/`, `/vandens-istatymas/5/` | redirect to the article |
| Earlier versions | `/kaip-buvo/?u=<article>&data=<date>` | the official text in force that day (since 2020), periods, "Kas pakeista" |
| Topics | `/sritis/<area>/` | the acts of an area |
| Energy regulator | `/vert/`, `/vert/<TAR>/` | which price and tariff decisions apply today; each decision's text; e-tar link to its annexes |
| Agents: MCP | `https://atviri-teises-aktai.lt/mcp` (MCP registry: `lt.atviri-teises-aktai/lithuanian-law`) | `search_law`, `get_article` (also `date=`), `get_articles`, `related`, `find_definition`, `list_acts`, `get_act_contents`, `upcoming_changes` |
| Agents: REST | `/api/search`, `/api/article`, `/api/acts`, `/api/contents`, `/api/upcoming` | the same as JSON |
| Agents: entry point | `/llms.txt`, `/index.json` | what the site is, URL scheme, every act, guidelines |
| Agents: whole act | `/ta/<TAR code>/data.json`, `/articles.json` | every article exactly as the pages show it |
| Agents: decisions | `/api/v1/vert.json` | the regulator's decisions with labels |
| Health | `/status.json` | last good build, data dates, warnings, ledger totals |

Not yet: a bulk dump of all acts (a weekly zip, or Hugging Face: later).
