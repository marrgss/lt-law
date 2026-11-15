# International analogues: research notes (2026-10-17)

A research subagent produced these notes, which Claude reviewed. Markers: [V] verified on an official page, API or repo metadata · [S] seen in a search snippet of an official URL · [3P] third-party claim.

## Lithuania today

- **MateMatic `lt-eli-mcp`.** Commercial, Apache-2.0, first release 2026-06-29. It searches act titles and returns the full current text. It has no point-in-time versions and no article IDs, and it uses e-tar.lt URLs because Lithuania has no data.europa.eu ELI. [V] https://raw.githubusercontent.com/matematicsolutions/lt-eli-mcp/main/README.md
- **Ansvar `Lithuanian-law-mcp`.** The repo was created 2026-02-21 and is now **archived** (1 star, last push 2026-07-07). The corpus is served only through their OAuth gateway. [V] https://github.com/Ansvar-Systems/Lithuanian-law-mcp
- **ELI.** Lithuania implements only Pillar 1 (URI templates). It has no ontology, no RDFa and no Atom or sitemap pillars. Denmark and Finland implement all four. [V] https://eur-lex.europa.eu/eli-register/implementing_countries.html (updated 2026-10-02)

## UK: legislation.gov.uk (the closest model)

- **Run by the state** (The National Archives) under OGL v3, and built API-first: append `/data.xml`, `/data.rdf`, `/data.feed` or `/data.akn` to any page URL. No registration needed. [V] https://www.legislation.gov.uk/developer
- **Point-in-time versions** live at dated URLs, and the metadata lists "unapplied changes outstanding". [V] https://legislation.github.io/data-documentation/api/overview.html
- **A red "Changes to Legislation" box** on each provision lists recorded effects that haven't been applied yet. Changes normally go in "within two weeks". [S] https://www.legislation.gov.uk/changes
- **The backlog history.** At one point about half of all laws were out of date. TNA recruited private editors through the Expert Participation Programme in 2012, and by July 2018 95.8% of primary legislation was up to date. [3P] https://www.infolaw.co.uk/newsletter/?p=355, https://www.infolaw.co.uk/newsletter/?p=4682
- **Fair use** is capped at 1,500 requests per 5 minutes, and anonymous user agents are banned. [V] https://www.legislation.gov.uk/fair-use-policy
- **Traffic.** 2M unique visitors a month and 500M+ page views a year (2013). [3P] https://e-pluribusunum.org/2013/12/30/uk-national-archives-good-law-open-data-platform-crowdsourcing/
- **i.AI "Lex"** is the only official government MCP server for legislation I found. It covers 220k acts and SIs with semantic search, is MIT-licensed and is labelled experimental. [V] https://cdn.jsdelivr.net/gh/i-dot-ai/lex@main/README.md, https://lex.lab.i.ai.gov.uk

## US

- **Cornell LII** (a nonprofit) had 45M+ visitors and 166M page views in FY2023. Fewer than 5% of visits come via referral links, so search dominates. It is funded by ads, partners and donations, with no direct Cornell funding. [V] https://blog.law.cornell.edu/blog/2023/09/13/annual-report-2023
- **eCFR** offers point-in-time versions back to 2017 and redline comparisons, with no key needed. [3P]
- **uscode.house.gov** publishes USLM XML release points. [S]
- **congress.gov and govinfo** need api.data.gov keys. [3P]
- **CourtListener** (nonprofit Free Law Project) runs an official MCP server (OAuth, free account). [3P] It was integrated into Gemini Enterprise for Legal in August 2026. [V] https://www.googlecloudpresscorner.com/2026-08-25-The-Power-of-CourtListener-Now-Integrates-With-Google-Clouds-Gemini-Enterprise-for-Legal
- **Justia** gets more than 80% of its traffic from search. [3P]
- **Copyright.** *Georgia v. Public.Resource.Org* (2020) held that even annotations to an official code can't be copyrighted.

## EU and national

- **EUR-Lex Cellar** offers SPARQL and REST access by CELEX number. [3P]
- **France.**
  - The LEGI dump (consolidated codes and laws) is free under Licence Ouverte 2.0.
  - The Légifrance API through PISTE needs registration.
  - The dump has 48 listed reuses. [V] https://www.data.gouv.fr/datasets/legi-codes-lois-et-reglements-consolides/reuses_and_dataservices
  - The civic git mirrors stalled; `steeve/france.code-civil` has had no push since 2015. [V]
- **Germany.**
  - The civic `bundestag/gesetze` mirror stalled in 2022. [V]
  - The Tech4Germany 2020 API prototype was replaced by the state's own project. [V] https://github.com/tech4germany/rechtsinfo_api
  - NeuRIS (rechtsinformationen.bund.de) is in a test phase, with bulk and point-in-time access "planned" and completion targeted for 2028. [V] https://digitalservice.bund.de/en/projects/new-legal-information-system
- **Netherlands.** BWB SRU, released under CC0. [S]
- **Finland.** Finlex open data in Akoma Ntoso covers original and consolidated texts, with no registration; overload returns 429. [V] https://www.finlex.fi/en/open-data/integration-quick-guide
- **Norway.** Lovdata offers a public bulk download of current laws and regulations, rebuilt daily. [V] https://api.lovdata.no/v1/publicData/list
- **Denmark.** The Retsinformation API allows 1 call per 10 seconds, between 03:00 and 23:45 only. [S]
- **Austria.** The RIS OGD API is keyless and CC BY 4.0. [3P]
- **Poland.** api.sejm.gov.pl/eli. [V, existence only]
- **Czechia.** e-Sbírka has been live since 2024 and holds consolidated texts back to 1945. [S]
- **Estonia.** Riigi Teataja publishes XML; its English translations are unofficial. [S]
- **Latvia.** likumi.lv is "informative", meaning not the official text, and is funded by the publisher. [3P, 2015]

## Comparison

| Service | Operator | Bulk | API key? | Point-in-time | Provision-level URLs | Licence |
|---|---|---|---|---|---|---|
| legislation.gov.uk | state | feeds | no | yes | yes | OGL v3 |
| UK Lex (i.AI) | state, experimental | – | no | partial | yes | MIT |
| Cornell LII | university nonprofit | no | – | no | yes | mixed |
| eCFR | state | yes | no | yes (2017+) | yes | public domain |
| Légifrance/LEGI | state | yes | yes (PISTE) | yes | yes | LO 2.0 |
| DE rechtsinformationen | state, beta | planned | no | planned | yes (ELI) | open |
| Finlex | state | via API | no | yes | yes (AKN) | ? |
| Lovdata public | foundation | yes | no | no | yes | NLOD [3P] |
| Retsinformation | state | harvest | no | yes | yes (full ELI) | open |
| lt-eli-mcp | commercial | no | no | **no** | **no** | Apache-2.0 |

## Civic projects and the state: handoffs and replacements

- **Washington DC.** Civic pressure got the DC Code released uncopyrighted. The Council then partnered with the nonprofit Open Law Library and made GitHub the *authoritative* source, and it accepted a citizen's pull request. [3P] https://dcist.com/story/18/11/28/github-is-a-programming-website-so-what-is-d-c-s-legal-code-doing-on-there. Maryland later adopted Open Law Library. [3P]
- **Kenya.** Kenya Law (a state body) consolidates and publishes on Laws.Africa's open Indigo platform. [3P, vendor case study]
- **Germany went the other way.** The state replaced the civic prototype with its own system.
- **openlaws.eu** started as an EU grant project and became a commercial company. [3P]

## Lessons

1. **Compete on what nobody offers:** per-article stable URLs, point-in-time versions, static HTML and a bulk dump.
2. **Search is the distribution channel.** Make URLs permanent from day one.
3. **Never hide the lag.** Use UK-style "changes not yet applied" notices and an "as of" date. Don't consolidate the law yourself; it took the UK a decade and outside editors.
4. **Fill the ELI gap** with metadata, RDFa and Atom on TAR identifiers. That also makes a state takeover easy.
5. **The legal risk is database rights, not copyright.** In Norway, HR-2019-1725-A closed the volunteer site rettspraksis.no over Lovdata's database right. [V] https://www.domstol.no/en/supremecourt/rulings/2019/supreme-court-civil-cases/hr-2019-1725-a/. Use only the licensed open-data dump, attribute it, and never scrape commercial databases.
6. **Design for near-zero running cost.** Civic mirrors die with their maintainer, and even AustLII lost a third of its staff when funding was cut. Automated rebuilds onto a CDN survive neglect.
7. **Bulk dumps protect the API.** Every national API throttles.
8. **Plan to be adopted, or replaced.** Either counts as success.
9. **An MCP wrapper alone is low value.** The lasting value is clean, versioned, citable data.
