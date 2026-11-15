# Operations

GitHub Actions builds the site every second night, and on any night a label changes (D-050); the Cloudflare Worker `lt-law-mcp` serves it as static assets together with the MCP/REST API and the dated pages (Workers Paid, $5/month, D-032); another Worker relays requests to data.gov.lt. There is no server of our own. Secrets are entered by the maintainer on the GitHub and Cloudflare websites and never committed. Accounts, tokens and limits: [INFRASTRUCTURE.md](INFRASTRUCTURE.md).

## Settings

Repository → Settings → Secrets and variables → Actions.

| Name                     | Kind     | Purpose                                                                                                                                                                                                                                                                                          |
| ------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `CLOUDFLARE_PAGES_TOKEN` | secret   | Cloudflare **account** token "lt-law GitHub: deploy site (Pages)", **Pages Write only**, used by the deploy job (it runs npm code, so it must not be able to change the relay). **Leave TTL empty**: a start date in the future gives a token that verifies as active but is refused everywhere. |
| `CLOUDFLARE_RELAY_TOKEN` | secret   | Cloudflare **account** token "lt-law GitHub: deploy relay (Workers)", for the `relay` workflow only: Workers Scripts Write, Account Settings Read. Same TTL advice.                                                                                                                              |
| `CLOUDFLARE_ACCOUNT_ID`  | secret   | the 32-character ID in the dashboard URL (`dash.cloudflare.com/<id>/…`)                                                                                                                                                                                                                          |
| `RELAY_KEY`              | secret   | random key shared by the build job and the relay (`openssl rand -hex 32`)                                                                                                                                                                                                                        |
| `GH_DISPATCH_TOKEN`      | secret   | optional. A fine-grained GitHub token for **this repository only**, permission **Actions: Read and write** only. The relay Worker uses it to start the nightly build at 00:05 Vilnius time; GitHub's own schedule started runs 2–5 hours late. After adding it, run the `relay` workflow once.   |
| `HEALTHCHECK_URL`        | secret   | optional. The ping URL of a healthchecks.io check (see Heartbeat below). The last job pings it with "ok" or "/fail"; without the secret the heartbeat is off.                                                                                                                                    |
| `RELAY`                  | variable | `true`: fetch through the relay (needed: data.gov.lt refuses non-European traffic, D-018/D-019)                                                                                                                                                                                                  |
| `RELAY_URL`              | secret   | required with `RELAY`: the Worker's address, `https://lt-law-fetch-relay.<subdomain>.workers.dev`. A secret because the subdomain is the account's name and a variable is printed in the run's log (a variable of the same name still works). The build job holds no Cloudflare token. |
| `DEPLOY`                 | variable | `true`: deploy after a good build (the Worker with `SITE_ON_WORKER`, and Pages)                                                                                                                                                                                                                                            |
| `SITE_URL`               | variable | canonical base, default `https://atviri-teises-aktai.lt`                                                                                                                                                                                                                                         |
| `INDEXABLE`              | variable | `true` only at launch: removes `noindex` and opens `robots.txt` (D-012)                                                                                                                                                                                                                          |
| `CLOUDFLARE_MCP_TOKEN`   | secret   | Cloudflare token "lt-law GitHub: deploy MCP (Workers)": Workers Scripts Edit, Account Settings Read, Workers Routes Edit (zone), R2 Edit. The `mcp` workflow and, since D-032, the nightly deploy of the site's Worker. |
| `SITE_ON_WORKER`         | variable | `true` (since 2026-10-26): the site is the Worker's static assets (D-032); the file gate allows 100,000; the `mcp` workflow refuses to run (it would deploy the Worker without the site). |
| `MCP`                    | variable | `true`: the `mcp` workflow may deploy `worker-mcp/` (only while `SITE_ON_WORKER` is off). |

When pasting a secret, paste only the value: no name, no `=`, no spaces. The workflows strip stray whitespace anyway.

## Cloudflare setup (once)
1. **Domain:** add `atviri-teises-aktai.lt` to the account (Free plan) and set the two Cloudflare nameservers at the registrar.
2. **workers.dev subdomain:** open Workers & Pages once; if asked, pick any name. The relay lives there.
3. **Pages project:** don't create it by hand. The dashboard's "Upload assets" button creates a *Worker*, not a Pages project. The first run with `DEPLOY=true` creates the Direct Upload project `atviri-teises-aktai` (`*.pages.dev`).
4. **Custom domain:** after the first deploy, open the Pages project → Custom domains → add `atviri-teises-aktai.lt` (and `www.` if wanted).

## Private staging (before the public release)
The site runs on the real domain from now on, but only the maintainer can open it (Cloudflare Access, free for up to 50 users). Search engines and the public see a login page. The nightly job, the relay and GitHub are unaffected; Access only gates browsers.
1. **DNS:** in Cloudflare, *Add a domain* → `atviri-teises-aktai.lt` → Free plan. At the registrar, set the two Cloudflare nameservers it shows, then wait for "Active".
2. **First deploy:** on GitHub, set the variables `SITE_URL` = `https://atviri-teises-aktai.lt` and `DEPLOY` = `true`. Run the `nightly` workflow by hand. It creates the Pages project `atviri-teises-aktai` and deploys.
3. **Domain on the site:** Workers & Pages → `atviri-teises-aktai` → Custom domains → add `atviri-teises-aktai.lt` (and `www.atviri-teises-aktai.lt` if wanted).
4. **Lock it:** Zero Trust (Cloudflare One) → choose a team name and the Free plan → Access → Applications → *Add an application* → *Self-hosted*:
   - domains: `atviri-teises-aktai.lt`, `atviri-teises-aktai.pages.dev`, `*.atviri-teises-aktai.pages.dev`;
   - policy: *Allow*, include *Emails*: your address;
   - login method: *One-time PIN*.
5. **Preview deployments:** in the Pages project → Settings, enable the access policy for preview deployments.
6. **Check:** opening the site in a private window should show the Cloudflare login, not the site.

**Scripted (steps 3–6):** `bin/cf_staging.py` does them through the API, each step safe to repeat: `access --email <yours>` (empty Pages project, one-time-PIN login, the Access app on the four hostnames, and a bypass for certificate validation and `/status.json`), `domain` (the registrar's parking A records out, the domain and `www` on the Pages project), `check` (a stranger must be redirected to `*.cloudflareaccess.com`), `status`, and `release` (removes the gate). Its token ("lt-law local (maintainer PC)", as `CLOUDFLARE_API_TOKEN` in `~/.config/lt-law/.env`; never in GitHub) needs Pages Write, Access apps/policies Write and Zone DNS Write on the domain (setting up the login method once also needed Access organizations/identity providers Write; remove that afterwards). Zero Trust itself (team name, Free plan) is enabled once by hand in the dashboard.

**At release:** `uv run bin/cf_staging.py release` (or delete the Access application by hand), set `INDEXABLE` = `true`, and run `nightly`.

## Releases
- Development happens on `main`. The site runs the code on the `release` branch; data update with every build regardless.
- A release is a deliberate merge `main` → `release` after the checks pass (tests, validators, back-test). **While the site is private, releases may be as often as useful** (2026-10-21). After the public launch the plan was **Fridays**, at most once a week. In practice (2026-10-24…27) a change is released once it has passed the full check: the tests, the three validators on the whole scope, and a local build with every gate (`SITE_ON_WORKER=true uv run bin/nightly.py scope/v1.yaml --no-fetch --indexable --out <dir>`). Fixes of something wrong on the site go out at once. Data still update with every build.
- To try development code on real data without deploying: Actions → nightly → Run workflow → `code` = `main`. Such a run saves neither the site nor the state (newer code may keep data the released code can't read, e.g. Constitutional Court rulings since 2026-10-21).
- **Adding acts**: `bin/add_acts.py <batch.yaml>` (seed lines from `bin/rank_candidates.py --seeds`, each with `area:`): seed → resolve → fetch → name, document and area checks → the three validators (batch only) → failures to `scope/queued_seed.yaml` with their reasons → areas → the gate. Resumable (`--from STEP`). Then review, commit, `bin/state_asset.py pack` (backs up the asset on GitHub, packs `data/`, refuses to drop files) and `bin/state_asset.py upload` (refuses while a nightly runs) → release.
  - **Before the gate, take in the asset** (2026-11-11): the nightly saves the state at its end, so after a build the asset is ahead of the local `data/`. Download it (`gh release download state --pattern state.tar.zst`), unpack it over `data/` (the asset wins; the batch's new files stay), then run the gate; `pack` must list only the batch's files as added and the manifest as changed.
  - **A parser fix that drops a live act's articles** (IASESASA 51 → 8 points, its annex read as points): `add_acts.py … --from gate --accept ABBR`, then copy that act's entry from `out/gate/status.json` (`acts`) into the manifest of the state to pack (`out/add/<batch>/state.before-gate/manifest.json`), or the nightly's gate stops the build on "articles disappeared".
- **An EU act** (D-037): a seed `{abbr, title, genitive, number: "(ES) 2016/679", eu: <CELEX>}`; `bin/snapshot_scope.py`
  (or `source.snapshot("EU.<CELEX>")`) reads EUR-Lex and stops if a single article's words differ from its XHTML; the
  e-tar validators skip EU acts. Check the act's final article against the labels (`eurlex.application`).
- **Chosen but not fetchable yet:** `scope/queued_seed.yaml` (nothing reads it); move an entry into the seed once its
  text is fetched and checked.
- **Give the nightly what you fetched** (since 2026-10-26: data.gov.lt is often too slow for a first night): download `state`, add the new acts' snapshots (`dokumentas/<id>/`), their `suvestine.json` caches, the amending texts (`amending/`) and the amending acts' metadata lines (`state/laws.jsonl`), and upload it again; keep the previous file in `private/backups/`. A new act that still can't be built waits for the next night with a warning; never build one from the original text when Dokumentas lacks the consolidation (the 2026-10-26 mistake).
- **After a release that adds acts or changes an alias:** once the deploy is done, `uv run bin/cf_redirects.py --apply`, then `--check` (new aliases take about a minute to spread). The first night with new acts fetches their version lists and amending laws once.

## Agents' MCP server (D-028) and dated answers (D-029)
`worker-mcp/` (Worker `lt-law-mcp`) answers MCP at `/mcp` and REST at `/api/search`, `/api/article`, `/api/acts`, `/api/contents`, `/api/upcoming` from the site's `/api/v1/` files; with an R2 bucket bound as `HISTORY` it also answers `date=` (the official consolidation in force that day, since 2020). Check locally: `node bin/check_mcp.mjs out/site` (a nightly gate; `HISTORY_DIR=out/history` adds the dated checks). The same Worker serves the dated pages for people at `/kaip-buvo/` (D-030; shell `/api/v1/dated.html` from the build, timelines `v1/<act>/h/` in R2). After a new export: `uv run bin/upload_history.py --apply` (only new or changed objects).

**History (2026-10-22):** deployed behind the Access gate first (1b), R2 for dated answers (2b); public since the launch (D-031). Costs now: Workers Paid (10 M requests a month included, then billed: hence the CPU cap, the rate limit and the usage alerts, INFRASTRUCTURE); R2's free tier (10 GB, 1 M writes and 10 M reads a month).

**One-time steps in the Cloudflare dashboard (by hand):**
1. *API token for the deploy*: My Profile → API Tokens → Create Token → Custom token, name `lt-law GitHub: deploy MCP (Workers)`. Permissions: Account · Workers Scripts · Edit; Account · Account Settings · Read; Zone · Workers Routes · Edit, zone resources: only `atviri-teises-aktai.lt`. (For 2b add: Account · Workers R2 Storage · Edit.) Save it in GitHub → Settings → Secrets and variables → Actions as `CLOUDFLARE_MCP_TOKEN`.
2. *Access service token* (the Worker reads the private site with it; also for testing): Zero Trust → Access controls → Service credentials → Service Tokens → Create, name `lt-law mcp`, duration 1 year. Save Client ID / Client Secret as GitHub secrets `MCP_ACCESS_CLIENT_ID`, `MCP_ACCESS_CLIENT_SECRET`, and in `~/.config/lt-law/.env` as the same names (for tests from the maintainer PC). Then the site's Access application → Policies → Add a policy: action **Service Auth**, include **Service Token** = `lt-law mcp`.
3. GitHub → Variables: `MCP` = `true`. Run Actions → **mcp** → Run workflow.
4. *For 2b*: R2 → add a payment method if asked (the free tier is not billed) → Create bucket `lt-law-history` (location: Eastern Europe) → R2 → Manage API tokens → Create, permission **Object Read & Write**, only that bucket: save Access Key ID / Secret / endpoint in `~/.config/lt-law/.env` as `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`. Then the maintainer uploads `out/history` (`bin/export_history.py`) and uncomments the bucket binding in `worker-mcp/wrangler.toml`. **The bucket is in the EU jurisdiction**, so the binding says `jurisdiction = "eu"`; without it wrangler silently creates and binds an empty default-jurisdiction bucket of the same name (happened 2026-10-22; a dated query then answers "covered: nothing"). The deploy log should show `env.HISTORY (lt-law-history (eu))`. *Done 2026-10-22: dated answers live behind the gate.*

Announced in `llms.txt`, `index.json` and on `/apie/` (launch), and in the official MCP registry (`bin/mcp_registry.py`, 2026-10-25: a new `--version` for every change of the entry). The Access service token and the Worker's `ACCESS_CLIENT_*` secrets are left over from the gate: delete them (by hand in the dashboard).

### The site on the Worker (D-032; switched 2026-10-26)
**Switch:** release main → release (worker-mcp with the assets code), then Settings → Variables → `SITE_ON_WORKER` =
`true`, run `nightly` (`code` = release). Its deploy job runs `wrangler deploy -c worker-mcp/wrangler.site.toml`
(the site + the Worker + the `/*` route). Check: `uv run bin/checkup.py` (all OK), a `cf-ray` page answers with the
Worker's headers, `/dk/52/` still redirects. The file gate then allows 100,000.
**Back:** `SITE_ON_WORKER` = `false`, run `mcp` (deploys wrangler.toml: only the Worker's own paths). If the `/*` route
is still listed under Workers Routes in the dashboard, delete it. Pages has the newest site that fit 20,000 files.
**Local check before switching:** `cd worker-mcp && ../deploy/node_modules/.bin/wrangler dev -c wrangler.site.toml
--assets <built site> --ip 127.0.0.1`, then compare a list of URLs with the live site.

## Workflows
| Workflow | When | What |
|---|---|---|
| `nightly` | 01:30 UTC, or *Run workflow* | build job, then deploy (if `DEPLOY`), plus keepalive. Input `accept`: acts whose big change is expected, e.g. `VKĮ` |
| `relay` | push to `worker/` or `deploy/package-lock.json`, or by hand | deploys the relay Worker and sets its key; run it by hand after changing `RELAY_KEY` |

`/status.json` on the site has the result of the last good build: data dates, warnings, fallbacks and health.

## Heartbeat (healthchecks.io, free)
GitHub mails a failed run, but not a run that never starts (a disabled schedule, an outage). A free healthchecks.io check covers that: the nightly's last job pings it, and healthchecks.io emails when a ping is missing or says "fail".
1. Sign up at healthchecks.io (free plan: 20 checks), with the address that should get the alerts.
2. *Add Check* → name `lt-law nightly`, schedule **Simple**: period **1 day**, grace **8 hours** (GitHub's schedule often starts 2–5 hours late; the punctual 00:05 start needs `GH_DISPATCH_TOKEN`).
3. Copy the check's ping URL (`https://hc-ping.com/<uuid>`) and save it as the GitHub secret `HEALTHCHECK_URL`.
4. Integrations: email is on by default; nothing else needed.

The first ping arrives with the next run; until then the check shows "new" and doesn't alert.

## Second Worker (D-051)
A Worker version holds at most 100,000 static files and a `_redirects` file at most 2,000 rules. The site is split:
`lt-law-site-2` (`worker-mcp/wrangler.site2.toml`, files only, no script: its requests are free) has the route
`atviri-teises-aktai.lt/ta/1*`, more specific than the main Worker's `/*`, and serves the act pages whose TAR code starts
with "1". Everything else, including all of `api/v1/` that the MCP code reads, stays with `lt-law-mcp`.
- **Build:** the gate counts files and `_redirects` rules per Worker as the split will be (`bin/split_site.py out/site --count`);
  it warns 5,000 files (or 100 rules) before a limit, fails over it.
- **Deploy:** `split_site.py --apply` moves those files into `out/site-2` (with copies of `404.html` and `_headers`, and the
  `_redirects` rules of those paths), deploys `lt-law-site-2` first, then the main Worker, then `--smoke` asks one page of
  each part for a 200.
- **A third Worker:** add `worker-mcp/wrangler.site3.toml` with its own route prefix(es) and `../out/site-3`; the most specific
  route wins (`/ta/11*` beats `/ta/1*`). Nothing else changes: the deploy loop and the gate read every `wrangler.site<N>.toml`.
- **Way back:** in the dashboard (Workers Routes) delete the `/ta/1*` route; those addresses fall to the main Worker, which
  has no such files until a deploy without the split (remove `wrangler.site2.toml` and release; possible while the whole
  site fits 100,000 files). `wrangler delete --name lt-law-site-2` removes the Worker.
- **Cost:** none on Workers Paid: requests served from static assets are free and unlimited, and no script runs.

## Runbook
| Symptom | Where to look | What to do |
|---|---|---|
| GitHub emails "nightly failed" | the run's log, the line `GATES FAILED` | Nothing was deployed and yesterday's site stays up. Fix the cause. If it's an expected big change (a whole act rewritten), run `nightly` by hand with `accept: <ABBR>`. |
| `status.json` → `fallbacks` lists an act | the same entry gives the reason | The act shows its previous text. Check the new text (parser change needed?), then accept or fix. |
| warnings "new laws not fetched" or "texts not refreshed" | the relay step in the log (`relay: HTTP …`) | 403: the relay key is wrong (re-run `relay`). 500: data.gov.lt or the relay is down; the site keeps rebuilding from cache, and pages show "duomenys tikrinti D". If it lasts, ask atviriduomenys@vssa.lt. |
| pages show the red "Duomenys nebuvo atnaujinti" banner | `status.json` → `data_checked` | Data are more than 2 days old: see the row above. |
| `health.unexplained_version_dates` gains an act | that act's amending laws | A version boundary no detected law explains: check the act against e-tar (`bin/validate_currency.py`). |
| `health.repealed_or_expiring` gains an act | the act's header | The act is being repealed: decide whether its replacement joins the scope (`scope/v1_seed.yaml`). |
| the schedule stopped running | Actions → nightly | The keepalive job should prevent this. Re-enable the workflow there. |
| healthchecks.io says "failed" but the site shows today's date | Actions → nightly: which run failed | Usually a backup run (01:30 UTC, often started hours late) that hit trouble after the midnight run had already deployed; the site is fine. The skip check reads `/status.json`, which the login gate lets through for that reason. Requests to data.gov.lt give up after 2 minutes (4 tries), so a stalled source can no longer use up the 90-minute limit (2026-10-21). |
| warnings "data.gov.lt slow: N acts' texts not refreshed" / "Suvestine table timed out" for days | `status.json` → `warnings`, `steps` | The budgets keep the run inside its time; the longest-unchecked acts go first, so a slow week rotates through all. Pages say when their data were checked. Nothing to do unless it lasts weeks (then ask atviriduomenys@vssa.lt). |
| a crawler hammers one path (Cloudflare analytics, `checkup.py` usage) | Security → Analytics; the Worker's requests per hour | Static pages cost nothing. If it hits the Worker's paths, extend the firewall rule "crawlers off dated pages" (its user agent) or add one; the rate limit already blocks single addresses. |
| `checkup.py`: github billing WARN, or a Dependabot alert | GitHub → Billing; Security → Dependabot | Minutes: fewer manual runs (the budget stops at $5). An alert in `deploy/`: bump or override the package (`overrides` in `deploy/package.json`), `wrangler deploy --dry-run`, release. |
| the state asset is lost or bad (history gone, an act's archive broken) | Releases: `state` and the weekly copies `state-YYYY-Www` (newest 12) | Restore a weekly copy over `state`: `gh release download state-2026-W43 --pattern state.tar.zst --dir /tmp` then `gh release upload state /tmp/state.tar.zst --clobber`, and run `nightly`. Days since that copy are re-fetched; only their daily snapshots are lost. |

## Validation (by hand, rarely)
These read e-tar.lt, so they run locally and rarely, never in CI (D-004):
```
uv run bin/validate_scope.py scope/v1.yaml        # our text = e-tar's same version
uv run bin/validate_currency.py scope/v1.yaml     # "current" labels vs e-tar's version in force: must be 0 silent
uv run bin/validate_today_text.py scope/v1.yaml   # texts recovered from older consolidations
```
They write dated results to `validation/`. Commit those files: the site's "Kaip tikriname" section shows them.

## Launch checklist
- [x] Domain active and attached to the Pages project; `DEPLOY=true`; one good deploy (2026-10-20, behind Access).
- [x] Wording review (2026-10-20): one name "Atviri teisės aktai", "Neaišku, ar galioja", readable reasons with linked laws, fewer repeated dates. Re-read on staging before launch.
- [x] A contact and takedown address: `kontaktai@atviri-teises-aktai.lt` (Cloudflare Email Routing to the maintainer, 2026-10-20) in every page's footer, on `/apie/#kontaktai`, in `index.json` and `llms.txt`.
- [ ] A courtesy note to atviriduomenys@vssa.lt about the read-only relay (D-019).
- [ ] Public repository: a fresh single-commit history with a noreply author (D-022). *Postponed (D-031): the repository stays private for now.*
- [x] `INDEXABLE=true`, then run `nightly` (2026-10-23, D-031: the login gate removed with `bin/cf_staging.py release`; robots.txt open, no noindex, sitemap served).
- [x] Agents' access: Browser Integrity Check off (2026-10-23). Since the site moved onto the Worker (D-032) the static files answer `Python-urllib` too (Pages' own rule refused it); llms.txt still asks programs to send a User-Agent. (Earlier, 2026-10-23, public: still 403 for `Python-urllib` only, on every path incl. /mcp; python-requests, curl, node, GPTBot, ClaudeBot, Googlebot get 200; Browser Integrity Check is switched off in the dashboard, the token can't): Cloudflare answers 403 to a plain `Python-urllib` request (seen 2026-10-23 behind Access; curl and browsers get through), so agents fetching pages, `/api/v1/` or `llms.txt` with a default client may be refused. After removing the Access gate, test with `curl -A Python-urllib/3.12` and a few AI crawlers' agents; if still 403, relax Security → Settings (Browser Integrity Check / Bot Fight Mode) for `/api/*`, `/mcp*`, `/llms.txt`, `/index.json` (a free WAF skip rule).
- [x] Google Search Console and Bing Webmaster Tools: domain added, `/sitemap.xml` submitted (2026-10-24); IndexNow after each deploy. Brave: https://search.brave.com/submit-url (not done).
- [ ] After 2–4 weeks: re-run the AI panel (`research/ai_panel/queries.md`).

## Checkups and taking the site down
`uv run bin/checkup.py` checks the public site from outside: availability, integrity (only our scripts and Cloudflare's
e-mail obfuscation; the unofficial-text notice present), probes (nothing echoed back unescaped, oversized and
traversal inputs), secrets in public files, freshness and the last nightly, and labels against the last checkup.
Also Cloudflare usage, GitHub billing and Dependabot (with `GITHUB_READ_TOKEN`), and Google search for the last 7 days
(with the Search Console key below). Log: `private/checkups/<day>.log`. Exit 2 = CRITICAL.

## Search Console, read only
`uv run bin/search_console.py [--days 28]` prints what Google search brings: totals against the previous period, the
queries by kind (an article by citation, an act by name, a topic), the acts with impressions, queries just below the
first page, and topic queries no act matches (scope candidates); rows saved to `private/search_console/`. It uses a
service account that can only read (the token asks for the `webmasters.readonly` scope; in Search Console it is a
*Restricted* user, which can't change settings, submit sitemaps or remove URLs). Free: the API has no charge.

**One-time setup (by hand):**
1. https://console.cloud.google.com → project picker → *New project*, name `lt-law-search` (no billing account needed).
2. APIs & Services → Library → **Google Search Console API** → Enable.
3. IAM & Admin → Service Accounts → *Create service account*, name `lt-law-search-read`; skip the optional role and
   user-access steps (no project roles: it gets nothing in Google Cloud).
4. The new account → Keys → Add key → Create new key → JSON. Move the downloaded file to
   `~/.config/lt-law/search-console.json` and `chmod 600` it (the script refuses a key others can read).
5. https://search.google.com/search-console → the `atviri-teises-aktai.lt` property → Settings → Users and permissions →
   Add user: the service account's e-mail (`<name>@<project>.iam.gserviceaccount.com` or as shown in
   step 3), permission **Restricted**.
6. Check: `uv run bin/search_console.py --brief`.

**Revoke:** remove the user in Search Console, or delete the key in Google Cloud (Service Accounts → Keys).

**Taking the site down** (a deliberate decision, never an automatic one): put the login
gate back with `uv run bin/cf_staging.py access --email <your address>` (the same Access app and policy as private
staging; nothing is deleted, the deploy stays), check from outside that a stranger gets the login, and write what and
why in `private/STATUS.md`. Back up: `uv run bin/cf_staging.py release`. Critical means the site harms people as it
stands: altered pages, an exploitable hole, an exposed secret, mass wrong labels. Downtime or slowness is not.
