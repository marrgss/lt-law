# Atviri teisės aktai

**[atviri-teises-aktai.lt](https://atviri-teises-aktai.lt)** · for agents: [MCP and REST](https://atviri-teises-aktai.lt/llms.txt) (`lt.atviri-teises-aktai/lithuanian-law` in the [MCP registry](https://registry.modelcontextprotocol.io))

**Lithuanian codes, laws and rules, one page per article or point, each marked whether its text is in force today.** Free, unofficial, no registration, readable by people, search engines and AI assistants alike. Live at **https://atviri-teises-aktai.lt** since 2026-10-23: 1,400 acts (2026-11-11): the Constitution, every code and 528 laws and statutes in all, 703 sets of rules (Government, ministers, the energy regulator) and 169 EU acts.

> **Unofficial text, not legal advice.** The only official publication is the Register of Legal Acts, [e-tar.lt](https://www.e-tar.lt). Every page links to the official text; check it there before relying on it.

## Why
The official site (e-tar.lt) is current but hard for machines: the text loads in an iframe, there are no per-article addresses, and AI fetchers see an empty shell. The official open data on [data.gov.lt](https://data.gov.lt/datasets/2613/) is machine-friendly, but it says neither which version of an article applies *today* nor which amendments are already in force but missing from the text. So assistants often quote outdated or wrong text. More: [docs/PROBLEM.md](docs/PROBLEM.md).

This project takes the official consolidated texts unchanged and splits them into one page per article. It works out from the amending laws whether each article's text applies today, and says plainly when it can't be sure.

## What you get
- `/ta/<TAR code>/str/<article>/`: one article (superscripts as `-n`: `21-1`, `6.228-1`), with anchors `#d2` (part) and `#d2-p3` (point). Short forms such as `/dk/52/` redirect there.
- `/es/<CELEX>/str/<article>/`: EU law that applies in Lithuania, in Lithuanian from EUR-Lex (GDPR, NIS2, the AI Act, the Data Act and more; D-037), checked word for word against EUR-Lex; an article that applies only later says "Taikomas nuo D".
- A status badge on every article:

  | Badge | Meaning |
  |---|---|
  | **Galioja šiandien** | the text applies today |
  | **Įsigalios D** | adopted, applies from D |
  | **Gali būti pasenęs** | an amendment in force is not in the text yet |
  | **Nepatikrinta** | could not be established |
  | **Neteko galios D** | repealed |

- When the newest official version starts in the future, today's text comes from an older official consolidation and the future text is shown beside it, with a word diff.
- EU acts each law implements, linked to EUR-Lex.
- Cross-references within an act and to other acts in scope are links ("šio kodekso 52 straipsnio 2 dalyje" → that part); each article lists the defined terms it uses, linked to their definition.
- Constitutional Court rulings that an article conflicts with the Constitution are flagged until the consolidation includes them.
- Machine-readable: per-act `data.json`, `/index.json`, `/llms.txt`, JSON-LD, `/status.json`. All of them describe exactly the text the page shows.
- **Earlier versions** of every article since 2020 at `/kaip-buvo/` (the official consolidation in force on a chosen day, with "what changed"; D-030).
- **Energy, covered in depth** (D-033, D-034): the energy laws, the rules approved by Energy Minister's orders and by the energy regulator (VERT), and `/vert/`: the regulator's electricity price and tariff decisions, with which of them apply today.
- **Topic pages** (`/sritis/energetika/` and 10 others) and full-text search.
- For agents: a static API under `/api/v1/`, and an MCP server and REST API at `https://atviri-teises-aktai.lt/mcp` (listed in the official MCP registry as `lt.atviri-teises-aktai/lithuanian-law`): `search_law`, `get_article` (text, status, label end date, citation, or the text on a past `date`), `get_articles` (up to 20 in one call), `related` (references both ways, incl. the regulator's decisions; D-036), `find_definition`, `list_acts`, `get_act_contents`, `upcoming_changes`.

## How trustworthy is it
- Texts are never edited or consolidated by us (D-002). Only the letter case of headings changes.
- An article is called "in force today" only when every amendment affecting it is in force and no law in force is missing from the text. Anything uncertain gets flagged (D-010).
- **Checked against e-tar.lt** before any act goes in: its text against e-tar's same version, its "current" labels against e-tar's version in force, recovered texts against e-tar's (`bin/add_acts.py`; failures wait in `scope/queued_seed.yaml` with the reason). Parser changes are checked by re-parsing every stored text and comparing the acts that change with e-tar. The last run over the whole scope (2026-11-02, 375 acts; results in [`validation/`](validation/)):
  - the text of 360 of 360 acts that have a consolidation to compare is identical to e-tar's same version (13 more were never amended, so the original is the text; 1 is not in force until 2027);
  - **0** of the 23,944 articles and points called current were wrong (26,509 compared);
  - 901 of 901 texts recovered from other official versions are correct.

  The price of caution: 144 articles and points (0.5%) were flagged although e-tar shows them unchanged. The acts added since (1,425 on the site by 2026-11-14) were each checked this way when they went in; a random sample of 120 of them checked again on 2026-11-15: 0 of 4,568 labels "current" wrong.
- **Checked against history** (2026-10-23, 219 acts): the rules applied to the Chancellery's own 2023–2025 consolidations would have called 0.067% of articles current wrongly ([`docs/ACCURACY.md`](docs/ACCURACY.md)). The acts added since will be back-tested once the open data's consolidation table answers again.
- Each page says when its data were last checked. If the data are more than 2 days old, the page carries a warning.

## Data and licences
- **Source:** Lietuvos Respublikos Seimo kanceliarija, Teisės aktų registro atviri duomenys ([data.gov.lt](https://data.gov.lt/datasets/2613/)), licence [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Legal acts themselves are not objects of copyright in Lithuania (Autorių teisių ir gretutinių teisių įstatymas, Art. 5).
- **Code:** [MIT](LICENSE).
- Only normative acts are in scope; individual acts naming people (citizenship, pardons, awards) are excluded. The energy regulator's decisions on one company's prices are in (the distribution grid is a monopoly); their price tables are annexes that the open data doesn't carry, so each decision links to them on e-tar.lt.

## Run it yourself
Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).
```bash
uv sync
uv run pytest -q    # data-dependent tests skip until data/ exists
uv run bin/fetch_meta.py Dokumentas data/raw/dokumentas.jsonl \
  --fields dokumento_id,tar_kodas,atv_dok_nr,rusis,galioj_busena,priemusi_inst,priimtas,paskelbta_tar,isigalioja,negalioja,pavadinimas
uv run bin/compact_state.py         # the law list the status rules need (~15k laws)
uv run bin/nightly.py               # fetch the act texts and amending laws, build out/site (noindex)
```
The metadata download pages through about 480,000 acts politely, so expect it to take a while. data.gov.lt answers only European addresses. `bin/nightly.py` refuses to build with an incomplete law list, because the labels would then miss older amendments. Every script in `bin/` has `--help`. Data go to `data/`, which is not in git.

## Documentation
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how it works: sources, parsing, the status rules, outputs, the nightly job.
- [docs/DECISIONS.md](docs/DECISIONS.md): design decisions and their reasons (D-001…).
- [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md): accounts, where compute runs and data live, limits, what readers and AI agents get.
- [docs/OPERATIONS.md](docs/OPERATIONS.md): settings, workflows, runbook, launch checklist.
- [docs/ACCURACY.md](docs/ACCURACY.md): every failure mode found, how it is detected, and the measured results.
- [docs/ROADMAP.md](docs/ROADMAP.md): what's next.
- [docs/PROBLEM.md](docs/PROBLEM.md): the problem in detail.
- [research/](research/): dated research notes with sources.

## Contributing and contact
Errors in a text or a label: open an issue with the article URL and what e-tar.lt shows. See [CONTRIBUTING.md](CONTRIBUTING.md) and, for security issues, [SECURITY.md](SECURITY.md).

An independent personal project, not affiliated with the Seimas, its Chancellery or any other institution.
