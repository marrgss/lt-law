# SEO and AI discoverability: research notes (2026-10-17)

A research subagent produced these notes, which Claude reviewed. Claims carry their source URLs; anything without a source is inference.

## How the Lithuanian sources look to a machine (curl probes)

| Site | Finding |
|---|---|
| **e-tar.lt** | `robots.txt` returns 404, so crawling is allowed; there is no sitemap. The act page `…/TAR.F57794B7899F/asr` returns 200 and weighs 1.29 MB. Its `<title>` is "VIII-1881 … elektros energetikos įstatymas". The page has no meta description, no canonical tag and no ELI metadata. **The law text is not in the page HTML.** It loads in `<iframe src="/rs/actualedition/TAR.F57794B7899F/oKareqodNT/">`, which returns 2.0 MB (about 790k characters). A non-JS fetcher that doesn't follow iframes sees only the table of contents, and even one that follows the iframe gets 2 MB, far more than any fetch tool keeps. |
| **e-seimas.lrs.lt** | Returns 403 with a Cloudflare challenge ("Just a moment…") for both robots.txt and act pages. Non-browser fetchers get nothing. |
| **infolex.lt** (commercial) | `robots.txt` disallows everyone except Googlebot, bingbot, Slurp, Facebook and Screaming Frog. **GPTBot, OAI-SearchBot, Claude-SearchBot and PerplexityBot are blocked.** It has article pages (`/ta/368200:str52`, 107 KB) and a sitemap. |
| **lrvalstybe.lt** | Explicitly disallows ClaudeBot, GPTBot, OAI-SearchBot, GoogleOther and CCBot. It has per-article pages. |
| **temidy.lt** (commercial, has an AI assistant) | Allows AI bots and renders on the server. It sets canonical tags, og:title "DK 52 str. – Nuotolinis darbas \| Darbo kodeksas", JSON-LD `LegalDocument` and llms.txt. Only about 10 codes have article pages, and the titles are wrong for dotted Civil Code (CK) articles: 6.188 shows as "CK 6 str.". |
| **teise.pro** | A news and commentary blog, not a mirror. |

In Claude's own web search, Lithuanian legal queries returned mostly e-seimas draft amendments and lrv.lt PDFs, not consolidated article text.

## How each assistant retrieves pages (2026)

- **ChatGPT.** OAI-SearchBot builds its index, alongside Bing and partners. ChatGPT-User handles user fetches and ignores robots.txt. GPTBot crawls for training. A site that blocks OAI-SearchBot doesn't appear in ChatGPT search. Sources: https://developers.openai.com/docs/bots, https://www.notebookcheck.net/ChatGPT-search-relies-on-Bing-to-generate-search-results.911969.0.html
- **Gemini, AI Overviews and AI Mode.** These use the normal Google index, and Google says no special files or markup are needed. Google-Extended affects training only. Source: https://developers.google.com/search/docs/appearance/ai-features
- **Copilot.** Uses Bing. Bing Webmaster Tools added an "AI Performance" report (Feb 2026) that shows Copilot citations. Source: https://www.searchinfluence.com/blog/bing-ai-performance-report-copilot-citations/
- **Claude.** Search runs mostly on Brave (Brave is a listed subprocessor, and one test measured about 79% overlap), plus turbopuffer. Anthropic's agents are Claude-SearchBot, Claude-User and ClaudeBot, and all honour robots.txt. Brave's crawler follows the robots.txt rules for Googlebot. Brave has no webmaster console; the only option is https://search.brave.com/submit-url. Sources: https://support.claude.com/en/articles/8896518-what-is-claude-bot, https://simonwillison.net/2025/Mar/21/anthropic-use-brave/, https://search.brave.com/help/brave-search-crawler
- **Perplexity.** PerplexityBot builds the index and honours robots.txt. Perplexity-User handles user fetches and generally ignores robots.txt. Source: https://docs.perplexity.ai/docs/resources/perplexity-crawlers.md
- **JavaScript.** GPTBot, ChatGPT-User, ClaudeBot and PerplexityBot do not run JS (https://vercel.com/blog/the-rise-of-the-ai-crawler). Only Googlebot and Applebot render it. **Conclusion: serve static HTML.**

## Indexing a large new site

- Google's crawl-budget guide applies to sites with 1M+ URLs or with many pages stuck in "Discovered – currently not indexed". Crawl demand depends on perceived inventory, popularity and staleness. **`noindex` does not save crawl budget; only robots.txt does.** Use accurate `lastmod` values and support 304 responses. Source: https://developers.google.com/crawling/docs/crawl-budget
- There is no official figure for how long a new domain takes to get indexed. Expect weeks before the first pages appear and months before a meaningful share does. Inbound links matter more than sitemaps.
- IndexNow covers Bing, Yandex, Naver, Seznam and Yep in a single call. Bing feeds ChatGPT and Copilot, so this matters. Source: https://www.indexnow.org/documentation
- **Recommendation:**
  - Index the current act page and the current article pages. Start with codes and laws, then add government resolutions and the major orders.
  - Historical versions stay reachable but are marked `noindex` and left out of the sitemap. Don't canonicalise them to the current version, because the text differs. A version identical to the current one may point its canonical at it.
  - Don't create an article × version page matrix. Use anchors inside each version page instead.
  - Mark thin or repealed acts `noindex` at launch.

## Identical text vs. e-tar.lt

Google doesn't penalise duplicate content. It groups duplicates and picks the best page for each query. Mirrors such as LII and Justia rank because they are better pages for the query: one article per URL, clean titles, cross-links and inbound links. No rigorous study confirms this; it's an inference. To add value:
- Breadcrumbs.
- Each article's amendment history, linked to the amending acts.
- A "what changed" diff between versions.
- Linked cross-references.
- Pages for definitions.
- "Cited by" back-links.
- A visible link to the official e-tar source on every page.

Avoid AI summaries presented as if they were law.

## Structured data

- schema.org `Legislation` and `LegislationObject` (from ELI) are valid, but Google doesn't use them for rich results. They are still cheap and help other parsers. The pattern: an act as `Legislation`, with `legislationIdentifier`, `legislationDate`, `legislationLegalForce` and `sameAs` pointing to e-tar. Versions hang off it via `workExample` with `temporalCoverage`, articles via `hasPart`/`isPartOf`. Source: https://github.com/sparna-git/legislation-schema.org-howto
- Lithuania implements only ELI Pillar 1 (URI templates), and e-tar pages carry no ELI metadata.

## llms.txt

Mostly folklore. Ahrefs (May 2026, 137k domains) found that 97% of llms.txt files got zero requests, and SE Ranking found no correlation with citations (https://ppc.land/llms-txt-adoption-rises-8-8x-but-97-of-files-get-zero-ai-requests/). These channels work better:
- Presence in the Bing and Brave indexes.
- A listing in the official MCP Registry (registry.modelcontextprotocol.io).
- An OpenAPI spec.
- A GitHub repo.
- Allowing CCBot, the Common Crawl crawler.

## Lithuanian queries and who ranks

These results come from DuckDuckGo, which is largely backed by Bing. Google.lt returned a CAPTCHA, so it wasn't tested.

| Query | Results |
|---|---|
| "darbo kodekso 52 straipsnis" / "DK 52 str." | lrvalstybe, infolex, temidy, kizne.legal, e-tar (approving law), dirba.lt |
| "BK 182 straipsnis" | lrvalstybe, infolex, temidy |
| "CK 6.188" | infolex, an e-seimas amendment, temidy (wrong title), savadai.lt |
| "PVMĮ 19 str." | infolex, VMI PDFs, e-tar |
| "ABTĮ 2 straipsnis" | temidy first |

Article-level mirrors outrank the official sites. e-tar ranks mainly for whole-act queries.

**Page pattern:**
- Title: "DK 52 straipsnis. Nuotolinis darbas | Darbo kodeksas" (for CK: "CK 6.188 straipsnis. …").
- H1: "52 straipsnis. Nuotolinis darbas".
- Breadcrumbs with the full name and the abbreviation.
- A variants line: "DK 52 str. · Darbo kodekso 52 straipsnis".
- Stable ID URLs as canonical, with 301 aliases such as `/dk/52` and `/ck/6.188`.

## Zero-budget authority

- A data.gov.lt reuse listing and a data.europa.eu use case.
- A GitHub repo.
- Show HN, r/lithuania.
- Law faculties at VU, MRU and VDU.
- Journalists: a "law diff of the week".
- The open-data community.
- Wikipedia links are nofollow and self-linking breaks its conflict-of-interest rules, so expect little.

## Prioritised checklist

1. Static, server-rendered HTML with the text early on the page, article pages under about 100 KB, and no JS dependency.
2. A robots.txt that allows Googlebot, Bingbot, OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Claude-User, PerplexityBot, Perplexity-User and Bravebot, with a sitemap line.
3. Index current acts and current articles; mark versions `noindex`; build no article × version matrix.
4. A sitemap index with real `lastmod`, ETag/304 support, and an IndexNow push on each daily update.
5. Google Search Console and Bing Webmaster Tools (including the AI Performance report), plus a Brave URL submission.
6. Titles and aliases that match how people search, correct CK dotted numbering, and an abbreviation table.
7. Breadcrumbs, linked cross-references, amendment history, diffs, and the official link on every page.
8. JSON-LD `Legislation` with `hasPart`/`isPartOf` and `sameAs`, plus Open Graph tags and a meta description.
9. A listing in the MCP Registry, an OpenAPI spec, a GitHub repo, and CCBot allowed.
10. Outreach.
11. llms.txt, last.
