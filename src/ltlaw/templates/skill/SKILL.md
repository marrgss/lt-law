---
name: lithuanian-law-research
description: Research Lithuanian law (codes, laws, Government and ministers' rules, the energy regulator's decisions) and the EU law that applies in Lithuania (GDPR, NIS2, AI Act, Data Act and more, in Lithuanian) through the unofficial article-by-article mirror atviri-teises-aktai.lt, with a status label for every article. Use when a question needs what Lithuanian legal acts say, which article applies today, what a term means legally, or which rules and decisions apply an article of a law.
---

# Lithuanian law research (atviri-teises-aktai.lt)

The site mirrors the Seimas Chancellery's open data: the text of each article unchanged, and a label saying whether it applies today. It is unofficial: the official publication is e-tar.lt. Everything below works without a key, through the MCP server `{{BASE}}/mcp` or the REST API `{{BASE}}/api`.

## The tools

| Need | MCP tool | REST |
|---|---|---|
| Find articles by words or a reference ("DK 52") | `search_law` | `/api/search?q=…` |
| Read one article, one part, or the text on a past date | `get_article` | `/api/article?act=…&n=…[&part=…][&date=…]` |
| Read many at once (up to 20) | `get_articles` | `/api/articles?ref=…&ref=…` |
| What an article cites, and what cites it (other acts, rules, regulator decisions) | `related` | `/api/related?act=…&article=…` |
| Where a term is legally defined, in every act | `find_definition` | `/api/definition?term=…[&act=…]` |
| The acts, an act's contents, coming changes | `list_acts`, `get_act_contents`, `upcoming_changes` | `/api/acts`, `/api/contents`, `/api/upcoming` |

## A research recipe

1. **Search in Lithuanian, with the words of the law, not of the question.** Every word of 4+ letters must occur; inflection is handled by word stems ("telefono numeris" also finds "telefono numerį"). If no article has them all (or fewer than three do: those first), you get those with all but one, each with `lacks_word`: a sign to reword, not an answer. A hint that the words "lie apart" (no title or part has them all) is the same sign: the law may use another term ("ankstyvasis perspėjimas", not "įspėjimas"). Try two or three wordings (synonyms, the formal term) rather than one long query; one call takes up to three, separated by "|" ("telefono numeris | kontaktiniai duomenys"). Name the act when you know it ("EEĮ vartotojas"). The first results show the part where the words are (`part`, `snippet`): read only what looks relevant.
2. **Pin down the terms.** `find_definition` returns every act that defines a word; the meanings differ between acts. Pass `act` to get the one that governs your case; an act that borrows another act's definitions says so (`by_reference`).
3. **Read in batches.** Collect the article references from the searches and read them with one `get_articles` call. Ask for one part (`"EEĮ 2 str. 15 d."`) when a long article (definitions!) is not needed whole.
4. **Follow the references both ways.** `related` on the key articles: the law articles they rely on (`cites`), and the rules, other laws and energy regulator (VERT) decisions that apply them (`cited_by_*`). The lists hold references written with the act's name; one worded otherwise is not listed, so a search is still worth it.
5. **Check every label before relying on a text.** "Galioja šiandien" = applies today; "Įsigalios D" = adopted, applies from D; "Gali būti pasenęs" = an amendment in force is not in this text yet; "Neaišku, ar galioja" = could not be established; "Neteko galios" = repealed. Anything but the first: say so and point to e-tar.lt. `label_valid_until` and `future` tell when the text changes.
6. **Past situations:** `get_article(date=YYYY-MM-DD)` gives the official consolidation in force that day (since 2020).
7. **Cite** as the site gives it (`cite`), with the article URL, and say the official text is on e-tar.lt.

## Good to know

- Acts are named by abbreviation ("DK", "CK", "EEĮ", "KET", "BDAR"), key, TAR code, CELEX number ("32016R0679") or name ("darbo kodeksas").
- EU law is here too, in Lithuanian from EUR-Lex: GDPR (BDAR), NIS2 and its implementing regulation, the AI Act, the Data Act, the Cyber Resilience Act, eIDAS, the electricity market regulation and directive, the electricity cyber security network code and the metering-data regulation. "Taikomas nuo D" on an EU article: the act is in force, that article applies from D. A directive binds the Member States: read the Lithuanian act that transposes it (its page lists them; `related` shows the Lithuanian articles citing an EU article).
- Rules approved by the Government, a minister or the regulator are made of points: "KET 3.2" is point 3, sub-point 3.2.
- Every answer carries `status_day` and `data_checked`: the labels are recomputed at least every second day and for every day a label changes; `status_day` is the day they are for.
- The regulator's price tables are annexes on e-tar.lt only; the decisions here link to them.
