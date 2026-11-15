# Lithuanian legal-information landscape: research notes (2026-10-17)

A research subagent produced these notes, which Claude reviewed. Markers: [V] = read or fetched at the source; [3P] = third-party claim or search snippet.

## Official sources

### e-tar.lt (TAR)
- [V] Offers search, consolidated-version search, subscriptions and a "Data from TAR" menu. There is no robots.txt (404), and scripted fetches work. https://www.e-tar.lt/portal/lt/index
- [V] In 2019 the Seimas said that article structure exists only inside the DOCX source files; the HTML is converted from them. Companies can get a daily batch of new acts under a contract. https://gitlab.com/atviriduomenys/manifest/-/issues/786
- [V] **data.gov.lt request 14363:** API access to consolidated versions requires a signed data-receipt contract. The request is marked "Įvykdytas" (done). https://data.gov.lt/requests/14363/

### Dataset 2613 (https://data.gov.lt/datasets/2613/)
- [V] Licence **CC BY 4.0**. Labelled "Atnaujinama kasdien" (updated daily). Publisher: VDA. Preparer: the Seimas Chancellery. Contact: atverimas@stat.gov.lt.
- [V] Changelog:
  - "2025-06-13: consolidated data added; consolidated texts currently reachable via the given link".
  - "2026-03-02: annex texts added (scanned docs/pdf)".
- **So Suvestine was a one-time load, not a feed that broke.** It matches our measurement: no updates after 2025-06-01.
- Other requests: 14362 (act type, done); 14453 (missing entry-into-force dates before 2014, analysed at https://github.com/harismck/atviri-duomenys/blob/master/tar.ipynb).

### New legal framework, in force since 2026-07-01
- [V] Law XV-1042 (2026-06-18) amends the Law on the Fundamentals of Legislation (Teisėkūros pagrindų įstatymas). TAR becomes **TARIS**. https://www.e-tar.lt/portal/lt/legalAct/c1e498f2715c11f1b53dfa020e517810
- [V] TARIS regulations: Chancellor's order 400-ĮVK-229 (2026-06-30). https://www.e-tar.lt/portal/lt/legalAct/b7a2a862746711f1b53dfa020e517810 They introduce:
  - an **ELI link field** per act (p. 16.1.14.5);
  - a **classifier of structural parts** (p. 20.7);
  - delivery by web, open data, batch mode and recipient contracts (pp. 34–35);
  - a duty to open datasets for reuse (pp. 9.2, 56).
- [V] EUR-Lex ELI register: Lithuania "Pillar 1 currently being implemented". https://eur-lex.europa.eu/eli-register/lithuania.html

### VYTIS (successor system)
- [V] Tender of 2026-05-18 to modernise TAIS and TAR into VYTIS: **€2.64M** excl. VAT, 37 months, bids due 2026-07-23, no award found. https://lt.openprocurements.com/tender/teises-aktu-informacines-sistemos-atnaujinimo-teises-aktu-projektu-rengykles-sukurimo-ir-duomenu-mig/
- [V] TAR/TAIS maintenance: UAB Asseco Lietuva, €202,500.
- [3P] Built on Akoma Ntoso + ELI.
- [3P] Chancellery plan: TAIS 2028–30, with TAR after it. https://www.lrs.lt/sip/getFile3?p_fid=135041
- **Implication:** official article-level structured data is realistically **2029+**.

### e-seimas / lrs.lt and the Seimas XML API
- [V] e-seimas and lrs.lt sit behind a Cloudflare JS challenge (403 for scripts).
- [V] The Seimas XML API (apps.lrs.lt, CC BY 4.0) covers parliamentary data and the `p2b.tais_docs` draft events. It has **no adopted-act texts**.

### State AI work
- [V] VDA announced on 2025-07-02 that AI training and legal-consultation tools are intended uses of the TAR data. https://vda.lrv.lt/lt/naujienos/valstybes-duomenu-agentura-ir-seimo-kanceliarija-teises-aktu-duomenis-atvere-inovacijoms-dabar-pasiekiami-atviru-duomenu-formatu/
- [3P] The Seimas plans a virtual translator and an internal chatbot. https://jp.lt/seimas-atveria-kelia-dirbtiniam-intelektui-atsiras-ir-virtualus-asistentai/
- [V] EIMIN has €12M for Lithuanian AI corpora, none of it legal.

## Community requests
- [V] gitlab atviriduomenys/manifest **#786**, opened by Mantas Zimnickas in 2019: article- and point-level IDs plus amendment→target links. Still open; the project is archived; last activity 2019.

## Commercial and private sites

| Site | What it is | AI access | Notes |
|---|---|---|---|
| **INFOLEX** (Lexnet [3P]) | €29–57/mo; per-article URLs with each article version's effective date; article text visible without login | robots.txt allows **only Googlebot** | |
| **Temidy** (temidy.lt) | 2.1M court decisions; LT and EU acts with current, historical and future versions plus diffs; AI on articles; change monitoring; 4,000+ users | **MCP server (`mcp.temidy.ai`, OAuth) for paid plans only** (≈€40–250/mo); robots.txt blocks `/teises-aktas/` for some AI bots | public act pages show current versions (e.g. CK "Redakcija nuo 2026-09-27"), so it gets fresh consolidations somewhere; **the strongest competitor** |
| **lrvalstybe.lt** | ad-funded, one article per page | | ranks for article queries; **its versions can be stale** (the DK 52 page cites 2017) |
| **eteismai.lt** | free mirror of the codes and court decisions, with a forum | | |
| teise.pro | news only | | |

## Legal-tech, academia, datasets
- Lexu AI (LV), COBALT/Harvey, Dokas (a free e-commerce-law GPT).
- On Hugging Face: `endomorphosis/ipfs_lithuania_laws` (7.5k acts, 37.7k articles, partial, scraped), `joelniklaus/Multi_Legal_Pile`, `legal-lithuanian-roberta-base`.
- Elsewhere: an ELRC monolingual legal corpus, and the VDU 3.9B-word general corpus with embeddings (2026).
- No dedicated legal-NLP group found at VU, MRU or KTU.

## Courts
- [V] LITEKO: public search, no bulk export.
- [V] TAR registers Supreme Court and Supreme Administrative Court decisions (some are already in Dokumentas).
- [V] AtvirasTeismas.lt: beta, HTTP-only, data frozen at 2009–2015.

## Legal status (Claude's summary of the agent's reading; not legal advice)
- **Copyright Act, Art. 5** [V, 2003 EN version]: legal acts, official documents, their official translations and registered drafts are not protected. The current LT wording has not been re-checked.
- **Law on the Fundamentals of Legislation (Teisėkūros pagrindų įstatymas)** [V, read via infolex]:
  - Art. 2(5): a consolidated version is a text *prepared on the basis of* the official texts. It is not itself called official.
  - Art. 19(3): only registration and publication in TARIS is official publication.
  - **Art. 19(7): TAR data are public and provided free of charge.**
  - Art. 6(6): the Chancellery must publish consolidated versions within 5–10 working days and is responsible for preparing them.
- **No exclusivity:** nothing found that bars third parties from publishing consolidations. The risk is liability for errors and misleading presentation, not illegality.
- **Mitigations:**
  - label every page "unofficial";
  - link to the e-tar original and the official consolidation;
  - show the as-of date and TAR ID;
  - CC BY attribution with changes noted.
- **Database right:** the open dataset is licensed under CC BY 4.0, which covers the sui generis right for what we take from it. Anything taken from e-tar HTML falls outside that licence; Art. 19(7) "public and free" helps, but this is the grey zone.
