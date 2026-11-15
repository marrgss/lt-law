#!/usr/bin/env node
// Run the agents' MCP/REST Worker (worker-mcp/index.js) locally against a built site, no network.
//
// Usage: node bin/check_mcp.mjs [out/site]            the checks below (exit 1 if one fails)
//        node bin/check_mcp.mjs out/site '<json-rpc>'  one MCP message, its answer printed
//
// fetch() is replaced by reads from the site directory, so this checks the Worker and the /api/v1 files
// together, exactly as deployed (D-028).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(process.argv[2] || "out/site");
const here = path.dirname(fileURLToPath(import.meta.url));
const worker = (await import(path.join(here, "..", "worker-mcp", "index.js"))).default;
const ORIGIN = "http://site.local";

globalThis.fetch = async (url) => {
  const p = new URL(url).pathname;
  const f = path.join(root, decodeURIComponent(p));
  if (!f.startsWith(root) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) return new Response("not found", { status: 404 });
  return new Response(fs.readFileSync(f), { status: 200, headers: { "Content-Type": "application/json" } });
};
const hist = process.env.HISTORY_DIR;  // optional: an export_history.py tree, served as the R2 bucket
const env = { SITE_ORIGIN: ORIGIN, HISTORY: hist ? { get: async (k) => {
  const f = path.join(hist, k);
  return fs.existsSync(f) ? { json: async () => JSON.parse(fs.readFileSync(f, "utf8")) } : null;
} } : undefined };

async function mcp(msg) {
  const r = await worker.fetch(new Request("http://mcp.local/mcp", { method: "POST", body: JSON.stringify(msg),
                                                                     headers: { "Content-Type": "application/json" } }), env);
  return r.status === 202 ? null : r.json();
}
async function call(name, args) {
  const r = await mcp({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } });
  return r.result.structuredContent;
}
async function html(q) {  // a dated page for people (D-030)
  const r = await worker.fetch(new Request("http://mcp.local" + q), env);
  return { status: r.status, text: r.status === 302 ? "" : await r.text(), location: r.headers.get("Location") };
}
async function rest(q) {
  return (await worker.fetch(new Request("http://mcp.local" + q), env)).json();
}

if (process.argv[3]) {
  console.log(JSON.stringify(await mcp(JSON.parse(process.argv[3])), null, 1));
  process.exit(0);
}

let failed = 0;
const check = (what, ok, got) => {
  console.log(`${ok ? "OK  " : "FAIL"} ${what}${ok ? "" : "  → " + JSON.stringify(got).slice(0, 300)}`);
  if (!ok) failed++;
};
const t0 = Date.now();
const init = await mcp({ jsonrpc: "2.0", id: 0, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "check" } } });
check("initialize", init.result && init.result.protocolVersion === "2025-06-18" && init.result.capabilities.tools, init);
check("notification gets no answer", (await mcp({ jsonrpc: "2.0", method: "notifications/initialized" })) === null);
const list = await mcp({ jsonrpc: "2.0", id: 2, method: "tools/list" });
check("tools/list: 11 tools (8 for the acts, 3 for the Seimas votes)", list.result.tools.length === 11, list);

let r = await call("get_article", { act: "DK", article: "52" });
check("get_article DK 52: text and label", r.number === "52" && r.text.length > 0 && r.status.label && r.cite && r.url.includes("/str/52/"), r);
r = await call("get_article", { act: "DK", n: "52", part: "2" });  // feedback S4, S6
check("get_article one part (n, part)", r.part === "d2" && r.text.length >= 1 && r.text.every((b) => b.anchor.startsWith("d2")), r);
r = await call("get_article", { act: "2016-23709", article: "52" });
check("act by TAR code", r.number === "52", r);
r = await call("get_article", { act: "DK" });
check("missing article: named in the error", /missing parameter `article`/.test(r.error || ""), r);
r = await call("find_definition", { term: "darbuotojas" });  // feedback S2
check("find_definition: a defined term, with its act and anchor", (r.results || []).length > 0 && r.results.every((x) => x.url && x.cite), r);
r = await call("find_definition", { term: "vartotojo objektas", act: "2020-14529" });  // feedback P10: rules → EEĮ
check("find_definition: an act's terms defined in another act (by reference)",
  (r.results || []).some((x) => x.act === "eei") && (r.by_reference || []).some((x) => x.acts.includes("eei")), r);
r = await call("get_article", { act: "darbo kodeksas", article: "52 str." });
check("act by name, article with 'str.'", r.number === "52", r);
r = await call("get_article", { act: "CK", article: "6.228¹" });
check("CK 6.228¹ (superscript)", r.label === "6.228-1", r);
r = await call("get_article", { act: "KET", article: "52.1" });
check("KET 52.1 → point 52, anchor", r.label === "52" && r.url.endsWith("#p52.1"), r);
r = await call("get_article", { act: "vidutinis-darbo-uzmokestis", article: "5" });
check("a resolution's document (average pay 5)", r.label === "5" && /Vidutinio darbo/.test(r.cite), r);
r = await call("get_article", { act: "XYZ", article: "1" });
check("unknown act: an error, not a crash", Boolean(r.error), r);

r = await call("search_law", { query: "DK 52" });
check("search 'DK 52' → that article", r.results.length === 1 && r.results[0].label === "52" && r.results[0].cite === "DK", r);
r = await call("search_law", { query: "kasmetinės atostogos", act: "DK" });
check("search words within DK", r.results.length > 0 && r.results.every((x) => x.act === "dk") && /atostog/i.test(r.results[0].title), r);
r = await call("search_law", { query: "darbo kodeksas nuotolinis darbas" });
check("act named in words + full text", r.results.length > 0 && r.results.every((x) => x.act === "dk"), r);
r = await call("search_law", { query: "vidutinis darbo užmokestis" });
check("words across acts", r.results.length > 0, r);
r = await call("search_law", { query: "pranešimas apie incidentą" });
check("an act guessed from the words but empty there: every act ('apie' names none)", r.results.some((x) => x.cite === "KSĮ" || /incident/i.test(x.title)), r);
r = await call("search_law", { query: "viešieji pirkimai skirstomųjų tinklų operatorius" });
check("few articles have every word: those first, then all but one, saying which", r.results.length > 1
  && r.results.some((x) => x.lacks_word) && r.results.findIndex((x) => x.lacks_word) >= r.results.filter((x) => !x.lacks_word).length
  && /all but one/.test(r.hint), r);
r = await call("search_law", { query: "energijos bendrija" });
// (since 2026-11-03 the query names an act, the renewable-energy community status rules: their points come first)
check("closer title words first: bendrijų before bendrieji (RfG)", (/bendrij/i.test(r.results[0].title || "") || /bendrij/i.test(r.results[0].act_name || ""))
  && r.results[0].act !== "rfg", r.results[0]);
r = await call("search_law", { query: "ankstyvasis įspėjimas" });
check("words together first: NIS2 11 'ankstyvuosius perspėjimus, įspėjimus', not ANK's apart", r.results[0].act !== "ank" && r.results[0].words_in_part === "2/2", r.results[0]);
r = await call("search_law", { query: "ankstyvas įspėjimas tėvams" });
check("words apart in every result: a hint", /lie apart/.test(r.hint || ""), r);
check("answers carry the notice and status day", r.unofficial === true && r.status_day && /e-tar/.test(r.notice), r);

r = await call("list_acts", {});
check("list_acts: a page, the total and how to go on", r.acts.length === 50 && r.total > 100 && /offset 50/.test(r.more), r.total);
r = await call("list_acts", { query: "darbo kodeksas" });
check("list_acts: by words of the name", r.acts.some((a) => a.key === "dk"), r.acts && r.acts.length);
r = await call("list_acts", { query: "gdpr" });
check("list_acts: by a common name", r.total === 1 && r.acts[0].cite === "BDAR", r.acts);
// the forms people cite an act in
for (const [q, key, label] of [["GDPR 17", "bdar", "17"], ["gdpr article 6", "bdar", "6"], ["NIS2 21", "tis2-direktyva", "21"], ["AI Act 5", "dirbtinio-intelekto-aktas", "5"], ["dk52", "dk", "52"],
  ["Reglamento (ES) 2016/679 6 straipsnis", "bdar", "6"], ["2019/944 15", "elektros-rinkos-direktyva", "15"], ["Energetikos įstatymo 15 straipsnis", "ei", "15"]]) {
  r = await call("search_law", { query: q });
  check(`search "${q}": ${key} ${label}`, r.results && r.results[0] && r.results[0].act === key && r.results[0].label === label, r.results && r.results[0]);
}
// a long annex in pieces, and a look-up inside it (CLP VI: 1.4 million characters)
r = await call("get_article", { act: "clp", article: "VI priedas" });
check("a very long annex comes in pieces", r.next_offset > 0 && r.blocks_total > r.text.length && JSON.stringify(r.text).length < 90000, r.note);
const firstPiece = r.next_offset;
r = await call("get_article", { act: "clp", article: "VI priedas", offset: firstPiece });
check("the next piece goes on from there", r.offset === firstPiece && r.text.length > 0, r.note);
r = await call("get_article", { act: "clp", article: "VI priedas", find: "50-00-0" });
check("find inside an annex: formaldehyde by its CAS number", r.found >= 1 && /50-00-0/.test(JSON.stringify(r.text)), r.found);
r = await call("get_article", { act: "dk", article: "52" });
check("a normal article is untouched", r.next_offset === undefined && r.blocks_total === undefined, r.label);
r = await call("search_law", { query: "alimentai" });
check("search: everyday words find the law's article first", r.results[0].suggested && r.results[0].label === "3.192", r.results[0]);
r = await call("search_law", { query: "šmeižtas" });
check("search: another ending of the word", r.results.some((x) => x.label === "154"), r.results[0]);
r = await call("search_law", { query: "vairavimas išgėrus" });
check("search: never nothing for a two-word question", r.results.length > 0, r);
r = await call("get_act_contents", { act: "CK", offset: 0, limit: 5 });
check("get_act_contents CK, paged", r.items.length === 5 && r.total > 1000, r);
r = await call("upcoming_changes", { days: 30 });
check("upcoming_changes", Array.isArray(r.changes), r);

check("REST /api/article", (await rest("/api/article?act=BK&n=1")).number === "1");
check("REST /api/search", (await rest("/api/search?q=CK%201.1")).results.length === 1);
r = await call("get_article", { act: "DK", article: "52", date: "2020-01-01" });
if (hist) {
  r = await call("get_article", { act: "DK", article: "52", date: "2024-08-01" });
  check("dated: DK 52 on 2024-08-01", r.status && r.status.state === "as_of_date" && r.version.from <= "2024-08-01" && r.text.length > 0, r);
  r = await call("get_article", { act: "DK", article: "52", date: "2025-09-01" });
  check("dated: a gap is said so, with the nearest versions", Boolean(r.error) && r.nearest, r);
  r = await call("get_article", { act: "KET", article: "52.1", date: "2025-06-01" });
  check("dated: a point of KET", r.label === "52" && r.status.state === "as_of_date", r);
  const dk52 = "/kaip-buvo/?u=%2Fta%2F2016-23709%2Fstr%2F52%2F";
  let h = await html(dk52);
  check("dated page: DK 52's periods, the site's look", h.status === 200 && /Šio straipsnio redakcijos/.test(h.text)
        && (h.text.match(/data=20\d\d-\d\d-\d\d/g) || []).length >= 3 && /<footer>/.test(h.text) && !/%%/.test(h.text)
        && /noindex/.test(h.text), h.text.slice(0, 300));
  h = await html(dk52 + "&data=2024-03-01");
  check("dated page: DK 52 on 2024-03-01, its text", h.status === 200 && /Redakcija, galiojusi 2024-03-01/.test(h.text)
        && /<div class="law"><p>/.test(h.text) && /aria-current/.test(h.text), h.text.slice(0, 300));
  check("dated page: what changed against the period before", /Kas pakeista nuo 2022-09-01 \(palyginti su redakcija, galiojusia 2022-08-01 – 2022-08-31\)/.test(h.text)
        && /<(ins|del)>/.test(h.text) && /pakeitimų: \d/.test(h.text), h.text.slice(0, 300));
  h = await html(dk52 + "&data=2025-09-01");
  check("dated page: the gap said so", /nėra šio straipsnio redakcijos, galiojusios 2025-09-01/.test(h.text), h.text.slice(0, 300));
  h = await html(dk52 + "&data=2999-01-01");
  check("dated page: today or later goes to the article", h.status === 302 && /\/ta\/2016-23709\/str\/52\/$/.test(h.location), h);
  h = await html("/kaip-buvo/?u=%2Fta%2F1021100NUTA00001950%2Fp%2F52%2F&data=2025-06-01");
  check("dated page: a KET point", h.status === 200 && /52 punktas/.test(h.text) && /<div class="law"><p>/.test(h.text), h.text.slice(0, 300));
  h = await html("/kaip-buvo/?u=%3Cscript%3E");
  check("dated page: a bad path is 404, nothing echoed", h.status === 404 && !/<script>/.test(h.text.split("</header>")[1] || ""), h.status);
} else {
  check("dated without the bucket: said so", Boolean(r.error) && /not enabled/.test(r.error), r);
  const h = await html("/kaip-buvo/?u=%2Fta%2F2016-23709%2Fstr%2F52%2F");
  check("dated page without the bucket: said so", h.status === 200 && /Ankstesnių šio straipsnio redakcijų/.test(h.text), h.text.slice(0, 300));
}

r = await call("get_article", { act: "DK", article: "52", date: "9999-99-99" });
check("not a calendar day: an error", Boolean(r.error) && /not a date/.test(r.error), r);
// several at once and references both ways (D-036)
r = await call("get_articles", { refs: ["DK 52", "DK 52 str. 2 d.", { act: "KET", article: "3" }, "nėra 1"] });
check("get_articles: four answers in order", r.articles.length === 4 && r.articles[0].number === "52" && r.articles[1].part === "d2" &&
      r.articles[2].url && r.articles[3].error && !r.articles[0].notice && r.notice, r);
r = await rest("/api/articles?ref=DK+52&ref=CK+6.228-1");
check("REST /api/articles", r.articles && r.articles.length === 2 && r.articles.every((x) => x.url), r);
r = await call("get_articles", { refs: Array.from({ length: 25 }, () => "DK 1") });
check("get_articles: at most 20", r.articles.length === 20 && r.more, { n: r.articles.length });
r = await call("related", { act: "EEĮ", article: "9" });
check("related EEĮ 9: cited by regulator decisions", r.counts.cited_by_regulator_decisions > 0 && r.cited_by_regulator_decisions[0].number, r);
r = await call("related", { act: "EĮ", article: "23" });
check("related EĮ 23: cited by other acts (bare name)", r.counts.cited_by_other_acts > 0 && r.cited_by_other_acts.every((x) => x.act !== "ei" && x.url), r);
r = await call("related", { act: "DK", article: "52" });
check("related DK 52: cites and cited within the act", r.cites !== undefined && r.counts.cited_by_same_act >= 0 && !r.error, r);
r = await rest("/api/related?act=nera&article=1");
check("related: unknown act", r.error && r.error.includes("unknown act"), r);

r = await call("search_law", { query: "kasmetinės atostogos" });
check("search: snippet and part of the first results", r.results[0].snippet && r.results[0].words_in_part, r.results[0]);
r = await call("search_law", { query: "kasmetinės atostogos | nėštumo atostogos", limit: 6 });
check("search: alternative wordings merged", r.results.length === 6 && r.wordings.length === 2 && r.results.some((x) => x.found_by.startsWith("nėšt")), r);
// EU law from EUR-Lex (D-037)
r = await call("get_article", { act: "BDAR", article: "6", part: "1" });
check("EU act: BDAR 6 part 1, official text on EUR-Lex", r.part === "d1" && r.url.includes("/es/32016R0679/str/6/") && r.act.official_url.includes("eur-lex"), r);
r = await call("get_article", { act: "32024R2847", article: "10" });
check("EU act by CELEX; an article applying later is labelled so", r.status && /^(Taikomas nuo|Galioja)/.test(r.status.label), r);
r = await call("related", { act: "BDAR", article: "28" });
check("related: Lithuanian acts citing a GDPR article", r.counts.cited_by_other_acts > 0, r.counts);
// annexes: searched and read like articles, labelled as not checked for today (2026-11-03)
r = await call("search_law", { query: "elektros energijos skaitikliai periodinė patikra atrankos būdu" });
check("search: an annex's list (MPTMRT 6: meters verified by sampling)", r.results.some((x) => x.label === "priedas-6" && x.url.includes("/priedas/6/")), r.results.map((x) => x.cite + " " + x.label));
r = await call("get_articles", { refs: ["MPTMRT 6 priedas", "Direktyvos 2014/32/ES V priedas"] });
check("get_articles: annexes by reference (numbered, Roman), status not checked",
  r.articles.every((x) => x.label && x.label.startsWith("priedas-") && x.text.length && /netikrinama/.test(x.status.label)), r.articles.map((x) => x.error || x.label));
r = await call("get_articles", { refs: ["TAKSKDR I priedo A priedėlis", "TAKSKDR II-A priedėlis", "TAKSKDR II priedas"] });
check("references: an appendix keeps its annex and letter (2021/2139: I-A and II-A)",
  r.articles.map((x) => x.label).join() === "priedas-I-A,priedas-II-A,priedas-II" && /I priedo A priedėlis/.test(r.articles[0].cite), r.articles.map((x) => x.error || x.label));
r = await call("search_law", { query: "TAKSKDR I priedo A priedėlis" });
check("search: a reference to an appendix is that appendix", r.results.length === 1 && r.results[0].label === "priedas-I-A", r.results);
r = await call("search_law", { query: "MPTMRT 6 priedas" });
check("search: a reference to an annex is that annex, not point 6", r.results.length === 1 && r.results[0].label === "priedas-6", r.results);
r = await call("get_act_contents", { act: "MPTMRT" });
check("contents: the annexes listed", (r.annexes || []).some((x) => x.label === "priedas-6"), r.annexes);
r = await call("get_article", { act: "MPTMRT", article: "6 priedas", date: "2025-01-01" });
check("an annex with a date: says past annexes are not kept", /annexes are not kept/.test(r.error || ""), r);
let pr = await mcp({ jsonrpc: "2.0", id: 3, method: "prompts/list" });
check("prompts/list: the research recipe", pr.result.prompts.length === 1 && pr.result.prompts[0].name === "research_lithuanian_law", pr);
pr = await mcp({ jsonrpc: "2.0", id: 4, method: "prompts/get", params: { name: "research_lithuanian_law", arguments: { question: "Kas yra vartotojas?" } } });
const ptext = pr.result && pr.result.messages[0].content.text;
check("prompts/get: the skill without its header, and the question", ptext && ptext.includes("get_articles") && !ptext.startsWith("---") && ptext.includes("Kas yra vartotojas?"), pr);

const bad = await mcp({ jsonrpc: "2.0", id: 9, method: "nope" });
check("unknown method: JSON-RPC error", bad.error && bad.error.code === -32601, bad);

// Seimas votes (D-054, proof of concept): only when the build has them (bin/build_votes.py)
if (fs.existsSync(path.join(root, "api/v1/seimas/meta.json"))) {
  let t1 = Date.now();
  r = await call("search_votes", { query: "GPMĮ", limit: 5 });
  check(`votes: an act's votes by its law number (${Date.now() - t1} ms cold)`, r.total > 0 && r.results.every((x) => x.act && x.act.key === "gpmi" && x.record !== undefined) && r.data_lacks, r);
  r = await call("search_votes", { query: "darbo kodeksas", limit: 50 });
  check("votes: a code's votes by its name (no number in the agenda item)", r.total > 0 && r.results.every((x) => x.act && x.act.key === "dk"), r.results && r.results.slice(0, 2));
  const d = r.results.find((x) => x.draft);
  const byDraft = await call("search_votes", { query: d.draft });
  check("votes: a draft's votes by its number", byDraft.total > 0 && byDraft.results.every((x) => x.draft === d.draft), byDraft);
  r = await call("search_votes", { query: "pridėtinės vertės mokesčio tarifas" });
  check("votes: words, all but one when none has all (the word named)", r.total > 0 && /left out/.test(r.matched_by), r.matched_by);
  const withInd = (await call("search_votes", { query: "dėl šio įstatymo priėmimo", limit: 100 })).results.find((x) => /get_vote/.test(x.individual));
  r = await call("get_vote", { id: withInd.id });
  check("votes: one vote, every MP's choice adding up to the totals",
    r.for.length === r.vote.for && r.against.length === r.vote.against && r.abstain.length === r.vote.abstain && r.not_listed, r.vote);
  const cons = (await call("search_votes", { query: "po pateikimo", limit: 100 })).results.find((x) => /consensus/.test(x.individual));
  r = await call("get_vote", { id: cons.id });
  check("votes: a consensus decision says it has no individual votes", !r.for && /consensus/.test(r.vote.individual), r.vote);
  const mp = r.vote && (await call("get_vote", { id: withInd.id })).for[0];
  r = await call("mp_votes", { mp: mp.split(" ").slice(-1)[0], limit: 3 });
  check("votes: an MP's votes by surname, with counts", (r.mp === mp || r.candidates) && (r.candidates || r.total === r.counts.for + r.counts.against + r.counts.abstain), r);
  r = await call("mp_votes", { mp: "Nėramtokio Pavardės" });
  check("votes: an unknown MP is an error", /no MP/.test(r.error || ""), r);
  r = await call("search_votes", { query: "DK 138" });
  check("votes: an act and an article number", r.total > 0 && r.results.every((x) => x.act.key === "dk" && /(^|\D)138(\D|$)/.test(x.item)), r.results && r.results.slice(0, 2));
  r = await call("search_votes", { query: "EEĮ 72¹" });
  check("votes: a superscript article number is the agenda items' 72-1", r.total > 0 && r.results.every((x) => /72-1/.test(x.item)), r.matched_by);
  r = await call("search_votes", { query: "PVM", limit: 1 });
  check("votes: a short name (PVM) is the act", /PVMĮ/.test(r.matched_by || ""), r);
  r = await call("search_votes", { query: "nepasitikėjimas" });
  check("votes: word stems not too short (nepasitikėjimas is not nepasiturintiems)", r.results.every((x) => !/nepasiturinti/i.test(x.item)), r.results.map((x) => x.item));
  r = await call("search_votes", { query: "12345" });
  check("votes: a number is matched whole", r.total === 0, r.matched_by);
  check("votes: a bad day and a reversed range are errors",
    /YYYY-MM-DD/.test((await call("search_votes", { query: "biudžetas", from: "2026-13-40" })).error || "") &&
    /after/.test((await call("search_votes", { query: "biudžetas", from: "2026-06-01", to: "2026-01-01" })).error || ""));
  r = await call("search_votes", { query: "biudžetas", term: 3 });
  check("votes: a term not loaded says which are", /not loaded.*term 10/.test(r.error || ""), r);
  // several terms (term 9: 2020–2024): a tool without `term` takes the term of its dates; an MP of an earlier term only
  // is answered from it, said so; a vote id of an earlier term is found
  const terms = JSON.parse(fs.readFileSync(path.join(root, "api/v1/seimas/meta.json"), "utf8")).terms;
  if (terms.length > 1) {
    const [old, cur] = [terms[terms.length - 2], terms[terms.length - 1]];
    const y = old.first.slice(0, 4) * 1 + 1;
    r = await call("search_votes", { query: "biudžetas", from: `${y}-01-01`, to: `${y}-12-31`, limit: 100 });
    check(`votes: dates in term ${old.term} take that term`, r.term === old.term && r.total > 0 && r.results.every((x) => x.at.startsWith(String(y))) && !r.term_note, { term: r.term, total: r.total, note: r.term_note });
    r = await call("search_votes", { query: "biudžetas", from: old.last.slice(0, 10), to: cur.first.slice(0, 10) });
    check("votes: dates across two terms say so", r.term === old.term && new RegExp(`term ${cur.term}`).test(r.term_note || ""), { term: r.term, note: r.term_note });
    const mpsOf = (t) => JSON.parse(fs.readFileSync(path.join(root, `api/v1/seimas/${t}/mps.json`), "utf8"));
    const now = new Set(mpsOf(cur.term).map((x) => x.person));  // (an MP's id is the term's own; the person's isn't)
    const gone = mpsOf(old.term).find((x) => !now.has(x.person) && x.votes > 100);
    const both = mpsOf(old.term).find((x) => now.has(x.person) && x.votes > 100);
    r = await call("mp_votes", { mp: both.name, limit: 1 });
    check(`votes: an MP of both terms: the current one, the other named`, r.term === cur.term && (r.also_in_terms || []).includes(old.term), { mp: both.name, term: r.term, also: r.also_in_terms });
    r = await call("mp_votes", { mp: gone.name, limit: 1 });
    check(`votes: an MP of term ${old.term} only is answered from it, said so`, r.term === old.term && r.mp === gone.name && /not an MP in term/.test(r.term_note || ""), { mp: gone.name, term: r.term, note: r.term_note, error: r.error });
    const oldId = JSON.parse(fs.readFileSync(path.join(root, `api/v1/seimas/${old.term}/index.json`), "utf8")).votes.find((x) => typeof x.ind === "number").id;
    r = await call("get_vote", { id: oldId });
    check(`votes: a vote id of term ${old.term} without \`term\``, r.term === old.term && r.vote && r.for, { id: oldId, term: r.term, error: r.error });
  }
  r = await call("get_vote", {});
  check("votes: get_vote without an id", /missing parameter/.test(r.error || ""), r);
  const lowTurnout = (await call("search_votes", { query: "dėl šio įstatymo priėmimo", limit: 100 })).results.find((x) => x.verdict === "nepritarta" && x.for > x.against + x.abstain);
  check("votes: 'nepritarta' with most votes for explains the MPs present", lowTurnout && /present/.test(lowTurnout.reading), lowTurnout);
  const pv = (await call("search_votes", { query: "dėl pasiūlymo", limit: 100 })).results.find((x) => x.verdict === "P" && x.for !== null && x.type === "Atviras");
  check("votes: a \"P\" result is said to be unexplained, with the arithmetic", pv && /not explained.*votes cast/.test(pv.reading), pv);
  const bareDay = (await call("search_votes", { query: "", limit: 100 })).results.find((x) => x.note && /no agenda item/.test(x.note)).at.slice(0, 10);
  r = await call("search_votes", { query: "įstatymo", from: bareDay, to: bareDay });
  check("votes: a word search says how many votes in its dates no words can find", /no agenda item/.test(r.not_findable || ""), r.not_findable);
  r = await call("mp_votes", { mp: "Mažylis", limit: 1 });
  check("votes: an MP's first and last vote", r.voted_from && r.voted_to && r.voted_to < "2025-01-01", r);
  check("tools/list has the vote tools", (await mcp({ jsonrpc: "2.0", id: 3, method: "tools/list" })).result.tools.some((x) => x.name === "mp_votes"));
}

console.log(`${failed ? "FAILED " + failed : "all OK"} in ${Date.now() - t0} ms`);
process.exit(failed ? 1 : 0);
