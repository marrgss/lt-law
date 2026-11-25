// Atviri teisės aktai: MCP server and REST API for agents (D-028).
//
// Read-only. Every answer comes from the site's static files under /api/v1/ (src/ltlaw/api.py), fetched from
// SITE_ORIGIN and cached; no database, no state, no secrets except an optional Access service token while the
// site is private. Sized for the Workers free plan (10 ms CPU per request): no file is parsed whole to answer.
//
//   POST /mcp                  MCP (Streamable HTTP, JSON responses): tools search_law, get_article, get_articles,
//                              related, find_definition, list_acts, get_act_contents, upcoming_changes
//   GET  /api/search?q=…[&act=…][&limit=…]
//   GET  /api/article?act=…&n=…
//   GET  /api/articles?ref=…&ref=…   GET /api/related?act=…[&article=…][&part=…]
//   GET  /api/acts             GET /api/upcoming[?days=…][&act=…]
//
// Every answer carries the status day, the official-source notice and links to e-tar.lt: the text is unofficial.

import { datedPage } from "./dated.js";

const SERVER = { name: "atviri-teises-aktai", version: "1.0.0" };
const PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];
const LT = "ąčęėįšųūž", ASCII = "aceeisuuz";
const SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹";

const fold = (s) => (s || "").toLowerCase().replace(/[ąčęėįšųūž]/g, (c) => ASCII[LT.indexOf(c)]);
const stemOf = (w) => w.slice(0, Math.min(6, Math.max(4, w.length - 2)));  // as fulltext.stem

export function fnv1a(s) {  // as api.fnv1a
  let h = 0x811c9dc5;
  for (const b of new TextEncoder().encode(s)) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

// "21¹" -> "21-1", "6.228¹ str." -> "6.228-1", "52 straipsnis" -> "52"
export function articleLabel(s) {
  let t = String(s || "").trim().replace(/(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)/g, (m, d, x) => d + "-" + [...x].map((c) => SUP.indexOf(c)).join(""));
  if (/pried|annex/i.test(t)) {  // an annex: "6 priedas", "V priedas" (EU), "priedas-6"; no number: the act's only one
    // (lettered: "A priedas" (2015/848); an appendix numbered by its annex: "priedas-I-A", "II-B priedėlis" (2021/2139))
    const app = t.match(/(?:^|\s)([IVXLC]+|\d+)\s+priedo\s+([A-Z])\s+priedėl/i);  // "I priedo A priedėlis" (the site's label)
    if (app) return "priedas-" + app[1].toUpperCase() + "-" + app[2].toUpperCase();
    const n = t.match(/(?:^|[\s-])((?:\d+(?:-\d+)?|[IVXLC]+[a-z]?)(?:-[A-Z])?|[A-Z])(?=$|[\s.-])/);
    return "priedas-" + (n ? n[1] : "1");
  }
  const m = t.match(/\d+(?:\.\d+)*(?:-\d+)?(?:[a-z]{1,2}(?![a-ząčęėįšųūž]))?/);  // "4a": an EU act's inserted article
  return m ? m[0] : null;
}

// --- data --------------------------------------------------------------------------------------------
const memo = new Map();  // per isolate: small, frequently used files

async function getJSON(env, path, opts = {}) {
  // one request's own cache (`env._files`, set by the calls that read many files: alternative wordings, batches): a file
  // read once however many searches or articles need it
  if (!env._files) return loadJSON(env, path, opts);
  if (!env._files.has(path)) env._files.set(path, loadJSON(env, path, opts));
  return env._files.get(path);
}

// a request's own file cache, once (nested calls keep the outer one); the bindings (ASSETS, HISTORY) stay reachable
const ownFiles = (env) => (env._files ? env : Object.assign(Object.create(env), { _files: new Map() }));

async function loadJSON(env, path, { keep = false, text = false } = {}) {
  const hit = memo.get(path);
  if (hit && Date.now() - hit.t < 10 * 60 * 1000) return hit.v;
  const headers = { "User-Agent": "atviri-teises-aktai-mcp" };
  if (env.ACCESS_CLIENT_ID) {  // while the site is behind Cloudflare Access (private staging)
    headers["CF-Access-Client-Id"] = env.ACCESS_CLIENT_ID;
    headers["CF-Access-Client-Secret"] = env.ACCESS_CLIENT_SECRET || "";
  }
  const r = env.ASSETS ? await asset(env, path)  // the site deployed with this Worker (D-032): no subrequest
    : await fetch(env.SITE_ORIGIN.replace(/\/$/, "") + path, { headers, cf: { cacheTtl: 3600, cacheEverything: true } });
  if (!r.ok) {
    if (r.status === 404) return null;
    throw new Error(`site answered ${r.status} for ${path}`);
  }
  const v = text ? await r.text() : await r.json();
  if (keep) memo.set(path, { t: Date.now(), v });
  return v;
}

// A site file from the static assets; their redirects (".html" dropped, trailing slashes) followed, as fetch() would.
async function asset(env, path) {
  let r;
  for (let i = 0, u = new URL(path, "https://assets.invalid"); i < 3; i++) {
    r = await env.ASSETS.fetch(new Request(u));
    if (r.status < 300 || r.status >= 400 || !r.headers.get("Location")) break;
    u = new URL(r.headers.get("Location"), u);
  }
  return r;
}

const meta = (env) => getJSON(env, "/api/v1/meta.json", { keep: true });
const acts = async (env) => (await getJSON(env, "/api/v1/acts.json", { keep: true })).acts;

async function findAct(env, name) {
  if (!name) return null;
  const all = await acts(env);
  const f = fold(String(name)).replace(/\s+/g, " ").trim();
  const tar = (a) => (a.url || "").split(/\/(?:ta|es)\//)[1]?.split("/")[0] || "";  // the TAR code (CELEX for EU acts), as in the URLs
  const ft = f.replace(/\//g, "-");  // "110203NISAK14/3-742": its pages are at /ta/110203NISAK14-3-742/
  return all.find((a) => [a.key, a.abbr, a.abbreviation, a.cite].some((x) => x && fold(x) === f) || (tar(a) && fold(tar(a)) === ft))
    || foldedActs(all).get(f) || foldedActs(all).get("=" + f) || euNumbered(all, f)
    || all.find((a) => fold(a.name) === f)
    || all.find((a) => fold(a.name).startsWith(f) && f.length >= 6)
    || null;
}

function envelope(m) {
  return {
    unofficial: true,
    notice: "Neoficialus tekstas. Oficialus skelbimas – tik Teisės aktų registre (e-tar.lt), ES teisės – Europos Sąjungos oficialiajame leidinyje " +
      "(EUR-Lex). Unofficial text; the official publication is e-tar.lt (Lithuanian law) or the EU Official Journal (EUR-Lex).",
    status_day: m && m.status_day, data_checked: m && m.data_checked,
    open_data_newest_publication: m && m.register_newest_publication,
  };
}

// --- dated answers (D-029): the official consolidations since 2020, in the R2 bucket HISTORY ---------------
async function r2json(env, key) {
  const o = await env.HISTORY.get(key);
  return o ? o.json() : null;
}

export function isoDate(s) {
  const m = String(s || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));  // a real calendar day ("9999-99-99" is not one)
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3] ? `${m[1]}-${m[2]}-${m[3]}` : null;
}

async function articleOn(env, a, label, date, m) {
  if (!env.HISTORY) return { error: "dated answers are not enabled on this server yet; without `date` you get today's text" };
  const vs = await r2json(env, `v1/${a.key}/versions.json`);
  const v = vs && vs.versions.filter((x) => x.from <= date && date <= x.to).pop();
  if (!v) {
    const before = vs && vs.versions.filter((x) => x.to < date).pop(), after = vs && vs.versions.find((x) => x.from > date);
    return { ...envelope(m), act: { key: a.key, cite: a.cite, name: a.name, official_url: a.official_url }, date,
             error: `the open data hold no official consolidation of ${a.cite} for ${date}` +
                    ` (covered: ${vs ? vs.covered_from + " – " + vs.covered_to + (vs.gaps.length ? ", with gaps" : "") : "nothing"}); ` +
                    "see the version list on e-tar.lt",
             nearest: { before: before && { from: before.from, to: before.to }, after: after && { from: after.from, to: after.to } } };
  }
  const man = await r2json(env, `v1/${a.key}/m/${v.manifest}`);
  let l = label, entry = man && man.articles[l], anchor = null;
  if (!entry && label.includes(".") && a.unit === "punktas") { l = label.split(".")[0]; entry = man && man.articles[l]; anchor = "p" + label; }
  if (!entry) return { ...envelope(m), error: `${a.cite} had no ${a.unit} ${label} on ${date} (consolidation ${v.from} – ${v.to})` };
  const art = await r2json(env, `v1/a/${entry[0]}.json`);
  const variant = (art.variants || []).find((x) => (!x.from || x.from <= date) && (!x.to || date <= x.to));
  return {
    ...envelope(m), act: { key: a.key, cite: a.cite, name: a.name, official_url: a.official_url },
    label: l, number: l.replace(/-(\d+)/, (x, d) => [...d].map((c) => SUP[+c]).join("")), date, title: art.title,
    status: { label: `Seimo kanceliarijos suvestinė redakcija, galiojusi ${v.from} – ${v.to}`, state: "as_of_date",
              note: v.open_end ? `the open data's last consolidation (the table stopped updating on ${v.to}); later changes are not shown`
                               : "the Chancellery's official consolidation in force on that date" },
    text: (variant ? variant.text : art.text).map((t) => ({ text: t })), amended_by: art.amended_by,
    version: { from: v.from, to: v.to, source: v.source, id: v.id, prepared: v.prepared },
    url: anchor ? `#${anchor}` : undefined,
    cite: `${a.cite} ${l} (redakcija, galiojusi ${date}; Seimo kanceliarijos suvestinė redakcija ${v.from} – ${v.to})`,
  };
}

// --- tools -------------------------------------------------------------------------------------------
export async function getArticle(env, { act, article, n, part, date, find, offset }) {
  article = article ?? n;  // REST used `n`, MCP `article`: both everywhere
  if (!act) return { error: "missing parameter `act` (key, abbreviation, TAR code or name; see list_acts)" };
  if (article === undefined || article === null || article === "") return { error: "missing parameter `article` (or `n`): an article or point number, e.g. \"52\"" };
  const a = await findAct(env, act);
  if (!a) return { error: `unknown act "${act}"; see list_acts` };
  const label = articleLabel(article);
  if (!label) return { error: `"${article}" is not an article or point number` };
  const isAnnex = label.startsWith("priedas-");
  if (date && isAnnex) return { error: "past wordings of annexes are not kept (articles and points only): without `date` you get the annex of the stored consolidation" };
  if (date) {
    const m = await meta(env), d = isoDate(date);
    if (!d) return { error: `"${date}" is not a date (YYYY-MM-DD)` };
    if (d < m.status_day) return articleOn(env, a, label, d, m);
    // today or later: today's text, whose answer says what changes when (status, future)
  }
  const tryLabel = async (l) => {
    const chunk = await getJSON(env, `/api/v1/text/${a.key}/${fnv1a(l) % a.chunks}.json`);
    return chunk && chunk[l] ? chunk[l] : null;
  };
  let art = await tryLabel(label);
  let anchor = null;
  if (!art && label.includes(".") && a.unit === "punktas") {  // a sub-point ("52.1"): its point's page, anchor p52.1
    art = await tryLabel(label.split(".")[0]);
    anchor = art ? "p" + label : null;
  }
  if (!art) return { error: isAnnex ? `${a.cite} has no annex ${label.slice(8)} on this site (see get_act_contents: annexes)`
                                    : `${a.cite} has no ${a.unit} ${label} in the current text`, act: a.key, url: a.url };
  const out = { act: { key: a.key, cite: a.cite, name: a.name, official_url: a.official_url }, ...art,
                url: anchor ? art.url + "#" + anchor : art.url };
  return part ? onePart(out, String(part)) : pageOfText(out, find, offset);
}

// A long annex in pieces: CLP's annex VI is 1.4 million characters, too much for an agent's context in one answer. `find`:
// the blocks (table rows, paragraphs) holding these words, e.g. a substance's name or CAS number; otherwise from `offset`,
// up to MAX_TEXT characters, saying how to go on. Shorter texts are untouched.
const MAX_TEXT = 60000;
const blockText = (b) => (typeof b === "string" ? b : (b && b.text) || "");
function pageOfText(out, find, offset) {
  const blocks = Array.isArray(out.text) ? out.text : [];
  if (find) {
    const words = fold(String(find)).split(/\s+/).filter(Boolean);
    const hits = blocks.filter((b) => { const t = fold(blockText(b)); return words.every((w) => t.includes(w)); });
    return { ...out, text: hits.slice(0, 50), find: String(find), found: hits.length, blocks_total: blocks.length,
             note: hits.length > 50 ? `the first 50 of ${hits.length}: use more words` : hits.length ? undefined : `no block of this ${out.annex ? "annex" : "text"} holds all these words` };
  }
  const from = Math.max(0, Math.floor(Number(offset) || 0));
  let to = from, size = 0;
  while (to < blocks.length && (to === from || size + blockText(blocks[to]).length <= MAX_TEXT)) size += blockText(blocks[to++]).length;
  if (from === 0 && to >= blocks.length) return out;
  return { ...out, text: blocks.slice(from, to), blocks_total: blocks.length, offset: from,
           next_offset: to < blocks.length ? to : undefined,
           note: to < blocks.length ? `blocks ${from}–${to - 1} of ${blocks.length}: next with offset=${to}, or look something up with \`find\`` : `the last blocks, ${from}–${to - 1} of ${blocks.length}` };
}

// One part of an article ("d107" or "107"; a rule's sub-point "p8.12" or "8.12"): its block and those under it, and the
// future wording of that part when there is one, so an agent needn't load a 100-part definitions article (feedback P5)
function onePart(out, part) {
  const p = part.replace(/^#/, "").replace(/(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)/g, (x, d, s) => d + "-" + [...s].map((c) => SUP.indexOf(c)).join(""));
  const want = /^[dp]/.test(p) ? [p] : ["d" + p, "p" + p, "p" + out.label + "." + p];
  const mine = (b) => want.some((w) => b.anchor === w || (b.anchor || "").startsWith(w + "-") || (b.anchor || "").startsWith(w + "."));
  const blocks = (out.text || []).filter(mine);
  if (!blocks.length) return { error: `${out.cite ? out.cite.split(" (")[0] : out.label} has no part "${part}"; parts: ` +
    (out.text || []).map((b) => b.anchor).filter(Boolean).slice(0, 40).join(", "), url: out.url };
  const num = want[0].replace(/^[dp]/, "").replace(/-(\d+)$/, (x, d) => [...d].map((c) => SUP[+c]).join(""));
  const futureText = out.future && Array.isArray(out.future.text)
    ? out.future.text.filter((t) => t.startsWith(num + ".") || t.startsWith(num.replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹]+/, (s) => [...s].map((c) => SUP.indexOf(c)).join("")) + ".")) : null;
  return { ...out, text: blocks, part: blocks[0].anchor, url: out.url.split("#")[0] + "#" + blocks[0].anchor,
           future: out.future ? { ...out.future, text: futureText } : out.future };
}

// --- definitions (feedback S2): where a term is defined, in every act -------------------------------------------
const defWords = (t) => (fold(String(t || "")).match(/[a-z]{4,}/g) || []).map((w) => (w.startsWith("asmen") ? "asmuo" : w));
const sameWord = (a, b) => {  // as definitions.same: one word, inflected (a shared start of all but the last 3 letters, ≥ 4)
  let n = 0;
  while (n < a.length && n < b.length && a[n] === b[n]) n++;
  return (n === a.length && n === b.length) || n >= Math.max(4, Math.max(a.length, b.length) - 3);
};
const seqMatch = (q, t) => q.length === t.length && q.every((w, i) => sameWord(w, t[i]));
const endsWith = (q, t) => q.length < t.length && q.every((w, i) => sameWord(w, t[t.length - q.length + i]));

export async function findDefinition(env, { term, act, limit }) {
  const m = await meta(env);
  const q = defWords(term).slice(0, 8);
  if (!q.length) return { error: "missing or too short parameter `term`: a word or phrase of 4+ letters, e.g. \"vartotojo objektas\"" };
  limit = Math.max(1, Math.min(Number(limit) || 20, 50));
  let only = null;
  if (act) {
    only = await findAct(env, act);
    if (!only) return { error: `unknown act "${act}"; see list_acts` };
  }
  const keys = [...new Set([q[0].slice(0, 2), q[q.length - 1].slice(0, 2)])];
  const rows = (await Promise.all(keys.map((k) => getJSON(env, `/api/v1/defs/${k}.json`)))).flat().filter(Boolean);
  // an act whose terms are "suprantamos taip, kaip jos apibrėžtos … įstatyme" (feedback P10): those acts' definitions too
  let via = [], from = new Set();
  if (only) {
    const refs = ((await getJSON(env, "/api/v1/definitions_by_reference.json")) || {}).references || [];
    via = refs.filter((r) => r.act === only.key && (!r.terms || r.terms.some((t) => seqMatch(q, defWords(t)))));
    for (const r of via) for (const a of r.acts) from.add(a.act);
  }
  const seen = new Set(), exact = [], narrower = [];
  for (const r of rows) {
    if (only && r.act !== only.key && !from.has(r.act)) continue;
    const id = r.url;
    if (seen.has(id)) continue;
    const tw = defWords(r.term), aw = defWords(r.alias);
    if (seqMatch(q, tw) || (aw.length && seqMatch(q, aw))) { seen.add(id); exact.push(r); }
    else if (endsWith(q, tw)) { seen.add(id); narrower.push(r); }  // "vartotojas" → "Elektros energijos vartotojas"
  }
  const out = (x) => ({ term: x.term, alias: x.alias || undefined, definition: x.definition, act: x.act, cite: x.cite,
                        act_name: x.act_name, number: x.number, anchor: x.anchor, url: x.url, status: x.status,
                        kind: x.kind === "title" ? "concept named by the article's title (candidate)" : "definition" });
  // the act's own definition first; one it takes from another act only if it has none of its own
  const own = only ? exact.filter((x) => x.act === only.key) : exact;
  const used = only && !own.length ? exact : own;
  const acts = new Set(used.map((x) => x.act));
  const by_reference = via.length ? via.map((r) => ({ text: r.text, url: r.url, terms: r.terms, acts: r.acts.map((a) => a.act),
                                                     not_on_site: r.not_on_site.length ? r.not_on_site : undefined })) : undefined;
  return { ...envelope(m), term: String(term), results: used.slice(0, limit).map(out),
           narrower_terms: narrower.filter((x) => !only || x.act === only.key || !own.length).slice(0, limit).map(out),
           by_reference,
           note: only && !own.length && used.length ? `${only.name || only.key} does not define this term itself; it says its terms are understood as defined in the acts in by_reference.`
             : acts.size > 1 ? `Defined in ${acts.size} acts: the meanings can differ; use the act that governs your case.` : undefined };
}

// Alternative wordings in one call ("telefono numeris | ryšio duomenys", at most 3): each searched, the results merged in
// turn (first of each, then second …), each found once; every result says which wording found it (D-036)
export async function searchLaw(env, args) {
  env = ownFiles(env);
  // the small files every search needs, read together rather than one after another (each read is a round trip on the
  // host: a search took 9-15 of them, 1.2-2.7 s, 2026-11-09)
  // and the index files the query's words fall in (text, titles, definitions), in the same round: a file read the first
  // time at a Cloudflare location takes 250-430 ms whatever its size, 60 ms after (2026-11-11), so a search costs its
  // rounds of reads, not its bytes. A word that turns out to name an act ("darbo kodeksas") reads one in vain.
  const pre = [...new Set(fold(String(args.query || "").slice(0, 300)).split(/[^a-z]+/).filter((w) => w.length >= 4).slice(0, 12)
    .map((w) => w.slice(0, 2)))];
  for (const p of [meta(env), acts(env), getJSON(env, "/api/v1/cited.json", { keep: true }), getJSON(env, "/api/v1/topics.json", { keep: true }),
    ...pre.flatMap((k) => [getJSON(env, `/paieska/t/${k}.json`), getJSON(env, `/api/v1/titles/${k}.json`), getJSON(env, `/api/v1/defs/${k}.json`)])])
    p.catch(() => {});  // their own callers handle a failure
  const alts = String(args.query || "").split("|").map((x) => x.trim()).filter(Boolean).slice(0, 3);
  if (alts.length < 2) {
    const [base, topic] = await Promise.all([searchOne(env, args), topicFirst(env, args)]);  // the topic's articles meanwhile
    return withTopic(args, base, topic);
  }
  const limit = Math.max(1, Math.min(Number(args.limit) || 10, 30));
  const runs = await Promise.all(alts.map((q) => searchOne(env, { ...args, query: q, limit }, false)));
  const err = runs.find((r) => r.error);
  if (err) return err;
  const seen = new Set(), results = [];
  for (let i = 0; results.length < limit && runs.some((r) => i < r.results.length); i++)
    runs.forEach((r, k) => { const x = r.results[i]; if (x && !seen.has(x.url) && results.length < limit) { seen.add(x.url); results.push({ ...x, found_by: alts[k] }); } });
  const { results: _r, more: _m, hint: _h, defined_in: _d, ...env0 } = runs[0];
  const all = await acts(env), byKey = new Map(all.map((a) => [a.key, a]));
  const snips = await snippets(env, results.slice(0, 10).map((x) => [byKey.get(x.act), x.label, x._words || []]));
  results.forEach((x, j) => { Object.assign(x, snips[j] || {}); delete x._words; });
  return { ...env0, results, wordings: alts.map((q, k) => ({ query: q, results: runs[k].results.length, more: runs[k].more, hint: runs[k].hint })),
           defined_in: runs.map((r) => r.defined_in).filter(Boolean).flat().slice(0, 5) };
}

// Everyday words → the article people look for (scope/topics.yaml): first, the ordinary results after them, each once.
// The longest match wins: "bandomasis laikotarpis" and the like, where the law's own words differ.
async function topicFirst(env, args) {
  if (args.act) return [];
  const words = fold(String(args.query || "")).split(/[^a-z0-9]+/).filter(Boolean);
  if (!words.length || words.length > 12) return [];
  try {
    const { topics } = (await getJSON(env, "/api/v1/topics.json", { keep: true }).catch(() => null)) || {};
    let best = null, size = 0;
    for (const t of topics || []) for (const w of t.when)
      if (w.length > size && w.every((st) => words.some((x) => x.startsWith(st)))) { best = t; size = w.length; }
    if (!best) return [];
    const found = (await Promise.all(best.refs.slice(0, 3).map(([act, n]) => getArticle(env, { act, article: n })))).filter((r) => !r.error);
    const all = await acts(env), byKey = new Map(all.map((a) => [a.key, a]));
    const snips = await snippets(env, found.map((r) => [byKey.get(r.act.key), r.label, words.filter((w) => w.length >= 4)]));
    return found.map((r, j) => ({ ...summary(r), suggested: true, ...(snips[j] || {}) }));
  } catch { return []; }  // the ordinary results still come (a failed read fails searchOne itself, as before)
}

function withTopic(args, base, first) {
  if (args.act || base.error || !first.length) return base;
  const limit = Math.max(1, Math.min(Number(args.limit) || 10, 30));
  const seen = new Set(first.map((x) => x.url));
  return { ...base, results: first.concat((base.results || []).filter((x) => !seen.has(x.url))).slice(0, limit) };
}

// words of a question that name no act ("pranešimas apie incidentą" is not the VDAI order "Pranešimo apie asmens
// duomenų saugumo pažeidimą … tvarkos aprašas")
const NAME_STOP = new Set(["apie", "pagal", "arba", "taip", "kaip", "prie", "tarp", "kuris", "kuri", "kurie", "kurios", "kurio",
  "kuriu", "kada", "kodel", "kiek", "koks", "kokia", "kokie", "kokios", "kokius", "kokiu", "turi", "gali", "reikia", "privalo"]);
// everyday words that are also an act's short name once folded: "turi" (TurĮ), "kai" (KAĮ), "tai", "ši" (ŠĮ), "ant",
// "pat" ("taip pat": PatĮ), "abi" (ABĮ), "keli", "pati". In a query they name the act only written as one ("TurĮ 7",
// "KAĮ", "ABĮ 2": a capital after the first letter); "uždarosios akcinės bendrovės įstatinis kapitalas turi būti ne
// mažesnis" was searched in the Tourism Law alone (2026-11-25). Found by comparing the acts' folded keys with the
// words of the texts (`bin/check_mcp.mjs` checks one).
const WORD_LIKE = new Set(["turi", "kai", "tai", "si", "sis", "ant", "pat", "abi", "keli", "kelis", "pati", "pats", "pan", "kas",
  "ka", "ar", "yra", "tas", "jie", "per", "nuo", "iki", "del", "kad", "jei", "nes", "bet", "dar", "jau", "gal", "gali", "kur",
  "kam", "kuo", "visi", "ten"]);
const asAbbr = (tok) => /\p{Lu}/u.test(String(tok).slice(1));  // "TurĮ", "KAĮ", "ŠĮ", "ABI"; not "Kai" opening a sentence
// the words of a question that no article holds for its meaning ("ką daryti, kai darbdavis nemoka atlyginimo", "ar galima
// dirbti dviejuose darbuose"): left out of the search when other words remain (2026-11-25: "daryti" made every result
// "all but one word")
const FILLER = new Set(["daryti", "padaryti", "galima", "galiu", "galime", "reikia", "noriu", "norime", "turiu", "turime",
  "kokia", "kokie", "kokios", "koks", "kokiu", "kada", "kaip", "kodel", "kiek", "budu", "reiketi", "privalau", "galeciau"]);

async function searchOne(env, { query, act, limit }, snip = true, guess = true) {
  const m = await meta(env);
  const all = await acts(env);
  limit = Math.max(1, Math.min(Number(limit) || 10, 30));
  // a long query costs CPU (10 ms a request on the free plan) and means nothing: the first 300 characters
  let q = String(query || "").slice(0, 300).replace(/(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)/g, (x, d, s) => d + "-" + [...s].map((c) => SUP.indexOf(c)).join(""));
  let words = fold(q).replace(/\bstr\.?(?=\s|$)|\bstraipsni\w*|\bp\.(?=\s|$)|\bpunkt\w*|\barticles?\b|\bart\.?(?=\s|$)/g, " ").split(/[\s,;]+/).filter(Boolean)
    .slice(0, 12);  // the act-name matching below is quadratic in the words: 12 is plenty for a question
  // "dk52", "ck6.228": an act's short name run into the number
  words = words.flatMap((w) => { const g = /^([a-z]{2,10})(\d[\d.-]*)$/.exec(w); return g && foldedActs(all).has(g[1]) ? [g[1], g[2]] : [w]; });
  // an act named in the query ("DK 52", "darbo kodeksas atostogos") or given as `act`
  let only = act ? await findAct(env, act) : null;
  if (act && !only) return { error: `unknown act "${act}"; see list_acts` };
  // an EU act by its number, in any form: "Reglamento (ES) 2016/679 6 straipsnis", "2019/944 15", "direktyvos 2003/88 7"
  if (!only && (only = euNumbered(all, words.join(" ")))) words = words.filter((w) => !EU_NUMBER.test(w) && !EU_WORDS.test(w));
  if (!only) {
    const written = new Set(String(q).split(/[\s,;]+/).filter(asAbbr).map(fold));  // the words written as short names
    for (let n = Math.min(words.length, 8); n >= 1 && !only; n--) {
      for (let i = 0; i + n <= words.length && !only; i++) {
        if (n === 1 && WORD_LIKE.has(words[i]) && !written.has(words[i])) continue;
        const a = await findActQuiet(all, words.slice(i, i + n).join(" "));
        if (a) { only = a; words = words.slice(0, i).concat(words.slice(i + n)); }
      }
    }
  }
  // an act named in plain words ("pridėtinės vertės mokesčio tarifas", "asmens duomenų tvarkymas"): its name carries
  // at least two of the query's words and half of them, and no other act's name as many; the rest is searched in it,
  // and in every act if that finds nothing (a guess, not the user's choice: "viešieji pirkimai skirstomųjų tinklų
  // operatorius" is not ESO's network-access order, whose name has three of the words)
  const generic = genericNameStems(all);  // "įstatymas", "taisyklės": in most acts' names, they name none
  // how often other acts cite each act (api.write_refs): the law a question is most likely about, among equals
  const cited = (await getJSON(env, "/api/v1/cited.json", { keep: true }).catch(() => null)) || {};
  let guessed = false;
  if (!only && guess) {
    const qs = words.filter((w) => /^[a-z]{4,}$/.test(w) && !NAME_STOP.has(w)).map(stemOf).filter((s) => !generic.has(s));
    const hits = (a) => { const nw = fold(a.name || "").split(/[^a-z]+/); return qs.filter((s) => nw.some((x) => x.startsWith(s))); };
    // names as good in words: the one whose name is nothing but the query's words ("Pridėtinės vertės mokesčio
    // įstatymas", not the rules on "… importo pridėtinės vertės mokesčiu ir akcizais", 2026-11-03), or the act the law
    // relies on when one clearly is (cited by other acts 10+ times and 5 times more than the next)
    const ranked = all.map((a) => [hits(a), a]).sort((x, y) => y[0].length - x[0].length || (cited[y[1].key] || 0) - (cited[x[1].key] || 0));
    const whole = (h, a) => fold(a.name || "").split(/[^a-z]+/).filter((x) => x.length >= 4 && !generic.has(stemOf(x)) && !NAME_STOP.has(x))
      .every((x) => h.some((st) => x.startsWith(st)));
    let [best, second] = ranked;
    if (best && second && second[0].length === best[0].length) {
      const c1 = cited[best[1].key] || 0, c2 = cited[second[1].key] || 0;
      if ((c1 >= 10 && c1 >= 5 * c2) || (whole(...best) && !whole(...second))) second = null;
      else if (whole(...second) && !whole(...best)) [best, second] = [second, null];
    }
    // a narrow act whose long name happens to hold the words is no guess (the clauses of data processing contracts for
    // "asmens duomenų tvarkymas", the producers' reporting rules for "gaminantis vartotojas"): only a name that is the
    // query, or an act other acts cite
    const wholeName = (h, a) => fold(a.name || "").split(/[^a-z]+/).filter((x) => x.length >= 4 && !generic.has(stemOf(x)) && !NAME_STOP.has(x))
      .filter((x) => !h.some((st) => x.startsWith(st))).length <= 1;
    // then an act whose whole name is in the query, if there is one: a rule set naming "pridėtinės vertės mokesčio tarifą"
    // among much else must not end the guess at the VAT law (2026-11-04)
    if (best && !wholeName(...best) && (cited[best[1].key] || 0) < 3) {
      best = ranked.find(([h, a]) => h.length >= 2 && whole(h, a)) || null;
      second = null;
    }
    if (best && best[0].length >= 2 && best[0].length * 2 >= qs.length && (!second || second[0].length < best[0].length)) {
      only = best[1];
      guessed = true;
      const used = new Set(best[0]);
      words = words.filter((w) => !(/^[a-z]{4,}$/.test(w) && used.has(stemOf(w))) && !NAME_STOP.has(w));
      if (!words.length) {  // nothing left but the act's name: the act's first articles
        const c = await getActContents(env, { act: only.key, limit });
        if (!c.error) return { ...envelope(m), act: c.act, results: c.items.map((x) => ({ act: only.key, cite: only.cite, act_name: only.name,
          number: x.number, label: x.label, title: x.title, url: x.url, status_label: x.status_label })), hint: `the act's contents: ${c.total} articles` };
      }
    }
  }
  if (only && !words.length) {  // an act named and nothing else: its contents
    const c = await getActContents(env, { act: only.key, limit });
    if (!c.error) return { ...envelope(m), act: c.act, results: c.items.map((x) => ({ act: only.key, cite: only.cite, act_name: only.name,
      number: x.number, label: x.label, title: x.title, url: x.url, status_label: x.status_label })), hint: `the act's contents: ${c.total} articles` };
  }
  const appx = words.findIndex((w) => /^priedel/.test(w));  // an appendix: "TAKSKDR I priedo A priedėlis", "II-A priedėlis", "1 priedėlis"
  if (only && appx > 0) {
    const before = words.slice(0, appx).join(" ");
    const g = /(?:^|\s)([ivxlc]+|\d+)(?:\s+priedo\s+|-)([a-z])$/.exec(before) || /(?:^|\s)(\d+)()$/.exec(before);
    if (g) {
      const r = await getArticle(env, { act: only.key, article: g[2] ? `${g[1].toUpperCase()}-${g[2].toUpperCase()} priedėlis` : `${g[1]} priedėlis` });
      if (!r.error) return { ...envelope(m), results: [summary(r)] };
    }
  }
  const annexAsked = words.some((w) => /^pried/.test(w));  // "MPTMRT 6 priedas", "MID V priedas": that annex
  const num = words.find((w) => /^\d/.test(w)) || (annexAsked ? (words.find((w) => /^[ivxlc]+$/.test(w)) || "").toUpperCase() || undefined : undefined);
  if (only && num) {  // a reference: that article
    const r = await getArticle(env, { act: only.key, article: annexAsked ? num + " priedas" : num });
    if (!r.error) return { ...envelope(m), results: [summary(r)] };
  }
  const common = new Set((m.fulltext && m.fulltext.common) || []);
  if (words.some((w) => /^[a-z]{4,}$/.test(w) && !FILLER.has(w))) words = words.filter((w) => !FILLER.has(w));
  const longw = words.filter((w) => /^[a-z]{4,}$/.test(w));
  const terms = longw.filter((w) => !common.has(stemOf(w)));
  // the titles index has its own (shorter) common list: "darbas" is too common for the text index, not for titles
  const tcommon = new Set((m.titles && m.titles.common) || []);
  const tterms = m.titles ? longw.filter((w) => !tcommon.has(stemOf(w))) : [];
  if (!terms.length && !tterms.length) return { ...envelope(m), results: [], hint: "Name an act and an article (\"DK 52\"), or use words of 4+ letters." };
  const lookup = async (path, w) => {
    const stem = stemOf(w);
    const shard = (await getJSON(env, `${path}${stem.slice(0, 2)}.json`)) || {};
    const ids = new Set();
    for (const k in shard) if (k === stem || (stem.length < m.fulltext.stem && k.startsWith(stem))) for (const i of shard[k]) ids.add(i);
    // no article has that form: one letter shorter ("šmeižtas" and the law's "šmeižimas" share "šmeiž", not "šmeižt")
    if (!ids.size && stem.length >= 5) for (const k in shard) if (k.startsWith(stem.slice(0, -1))) for (const i of shard[k]) ids.add(i);
    return ids;
  };
  const inAll = (sets) => (sets.length ? [...sets[0]].filter((i) => sets.every((s) => s.has(i))) : []);
  // the text index: every word somewhere in the article; the titles index: words in its title (ranked first)
  // (both read together, and the definitions meanwhile)
  const defsP = definedIn(env, query, only);
  const tsetsP = Promise.all(tterms.map((w) => lookup(m.titles.path, w)));
  tsetsP.catch(() => {});
  const textSets = terms.length ? await Promise.all(terms.map((w) => lookup(m.fulltext.path, w))) : [];
  let titleIds = [], titleAll = [];
  if (tterms.length) {
    const tsets = await tsetsP;
    titleIds = titleAll = inAll(tsets);
    if (terms.length) { const inText = new Set(inAll(textSets)); titleIds = titleIds.filter((i) => inText.has(i)); }
  }
  let ids = terms.length ? inAll(textSets) : titleIds;
  const range = only && m.item_ranges && m.item_ranges[only.key];
  const inRange = (i) => !range || (i >= range[0] && i <= range[1]);
  // no article has every word (a question in many words: "viešieji pirkimai skirstomųjų tinklų operatorius"): those
  // with all but one, each saying which it lacks, rather than nothing (which word matters can't be told from how common
  // it is: "pirkimai" is in thousands of articles). Not for a guessed act: every act is tried first.
  // Fewer than 3 with every word (one article of a fee methodology happens to have all five, far apart): those first,
  // then the ones with all but one, rather than the one alone.
  let lacking = null;  // id -> the word it lacks
  const full = ids.filter(inRange);
  if (!guessed && ((terms.length >= 3 && full.length < 3) || (terms.length === 2 && !full.length))) {
    lacking = new Map();
    for (const i of new Set(textSets.flatMap((s) => [...s]))) {
      const miss = inRange(i) ? terms.filter((_, k) => !textSets[k].has(i)) : [];
      if (miss.length === 1) lacking.set(i, miss[0]);
    }
    const fullSet = new Set(full);
    ids = full.concat([...lacking.keys()]);
    titleIds = titleIds.filter((i) => fullSet.has(i)).concat(titleAll.filter((i) => lacking.has(i)));
  }
  const size = new Map(terms.map((w, k) => [w, textSets[k].size]));  // lacking a common word ranks first
  // candidates: title matches first, then the rest of the text matches, item blocks of the act if one is named
  let ordered = [...new Set(titleIds.concat(ids))];
  if (range) ordered = ordered.filter(inRange);  // only that act's items
  const idset = new Set(ordered);
  // load the items' blocks (500 each); at most 8 blocks, the act's if one is named
  // at most 8 item blocks: those holding the most matches (a title match counts 5), where the words cluster
  // an act whose own name has the query's words ("valstybinė pensija" → Valstybinių pensijų įstatymas) ranks its
  // articles higher, and its blocks are read first
  const qstems = longw.map(stemOf);
  const nstems = qstems.filter((s) => !generic.has(s));  // "pagal įstatymą" must not favour every law's articles
  // (a long name that merely holds a word says nothing: "… pailgintas atostogas, sąrašo ir šių atostogų trukmės aprašas" is
  // not the act about "atostoginiai"; at least a third of the name's own words must be the query's)
  const nameScore = (a) => {
    const nw = fold(a.name || "").split(/[^a-z]+/).filter((x) => x.length >= 4 && !generic.has(stemOf(x)) && !NAME_STOP.has(x));
    const hit = nstems.filter((s) => nw.some((x) => x.startsWith(s))).length;
    return hit && nw.filter((x) => nstems.some((s) => x.startsWith(s))).length * 3 >= nw.length ? hit : 0;
  };
  const spans = Object.entries(m.item_ranges || {}).map(([k, r]) => [r[0], r[1], k]).sort((x, y) => x[0] - y[0]);
  const actOf = (i) => {  // binary search: a common word can match thousands of articles
    let lo = 0, hi = spans.length - 1;
    while (lo <= hi) { const mid = (lo + hi) >> 1, sp = spans[mid]; if (i < sp[0]) hi = mid - 1; else if (i > sp[1]) lo = mid + 1; else return sp[2]; }
    return null;
  };
  const byKeyA = new Map(all.map((a) => [a.key, a]));
  const nameOf = new Map();
  for (const k in (m.item_ranges || {})) { const a = byKeyA.get(k); if (a) nameOf.set(k, nameScore(a)); }
  const weight = new Map(), inTitle = new Set(titleIds);
  for (const i of ordered) {
    const k = Math.floor(i / m.items_per_file);
    weight.set(k, (weight.get(k) || 0) + (inTitle.has(i) ? 5 : 1) + 3 * (nameOf.get(actOf(i)) || 0));
  }
  const files = [...weight.entries()].sort((x, y) => y[1] - x[1]).slice(0, 8).map(([k]) => k);
  const blocks = await Promise.all(files.map((k) => getJSON(env, `/api/v1/items/${k}.json`)));
  const items = [], idOf = new Map();
  files.forEach((k, j) => (blocks[j] || []).forEach((it, n) => {
    const id = k * m.items_per_file + n;
    if (idset.has(id) && (!only || m.item_acts[it[0]] === only.key)) { items.push(it); idOf.set(it, id); }
  }));
  const lacks = (it) => lacking && lacking.get(idOf.get(it));
  const isAnnex = (it) => it[1].startsWith("priedas-");
  // a rule set's points have no headings: their "title" is the point's first words, so the words there say less than
  // in an article's heading ("šilumos kaina": ŠŪĮ 32 "Šilumos kainodara" before a contract clause opening with them;
  // benchmark 73 -> 75 of 80 top-1, 2026-11-09); an annex's first line neither
  const heading = (it) => (byKeyA.get(m.item_acts[it[0]])?.unit !== "punktas" && !isAnnex(it) ? 1 : 0);  // a long annex has many words: after articles as good in title words
  // how closely the title's words match beyond the stem: "bendrijų" shares "bendrij" with "bendrija", "bendrieji" (RfG's
  // "Bendrieji reikalavimai") only "bendri"
  const lcp = (a, b) => { let n = 0; while (n < a.length && a[n] === b[n]) n++; return n; };
  // (the words that go at least one letter past the stem: an ending is no closer than another, "kasmetinių" as near as
  // "kasmetinės", so DK 126 isn't behind a special law's "Kasmetinės atostogos"; "bendrijų" still before "bendrieji")
  const closeness = (tw) => longw.filter((w) => tw.some((x) => x.startsWith(stemOf(w)) && lcp(w, x) >= Math.min(w.length, stemOf(w).length + 1))).length;
  let scored = items.map((it) => {
    const tw = fold(it[2] || "").split(/[^a-z]+/);
    // then, among equals, the act's name (the share of the query's words in it) and how much the law relies on it
    // (citations, logarithmic): DK before the extra-leave rules, the State Pensions Law before the judges' pension rules
    const ak = m.item_acts[it[0]];
    return [qstems.filter((s) => tw.some((x) => x.startsWith(s))).length,
            3 * (nameOf.get(ak) || 0) / Math.max(1, nstems.length) + Math.log10(1 + (cited[ak] || 0)), it, closeness(tw),
            longw.filter((w) => tw.includes(w)).length];  // the very word: DK 130 "Atostoginiai" before 125 "Atostogų rūšys"
  }).sort((x, y) => !!lacks(x[2]) - !!lacks(y[2]) || y[0] - x[0] || (y[0] > 0 && heading(y[2]) - heading(x[2])) || isAnnex(x[2]) - isAnnex(y[2]) || y[3] - x[3] || (size.get(lacks(y[2])) || 0) - (size.get(lacks(x[2])) || 0) || y[1] - x[1] || y[4] - x[4]
                    || (byKeyA.get(m.item_acts[y[2][0]])?.n || 0) - (byKeyA.get(m.item_acts[x[2][0]])?.n || 0))
    .map(([s, , it, c]) => [s, it, c]).slice(0, limit);  // last: the general act (more articles) before a special one
  if (!scored.length && guessed) return searchOne(env, { query, act, limit }, snip, false);
  const byKey = byKeyA;
  const snipWords = terms.length ? terms : longw;  // a word an article lacks finds no part there: harmless
  let snips = snip ? await snippets(env, scored.slice(0, 10).map(([, it]) => [byKey.get(m.item_acts[it[0]]), it[1], snipWords])) : [];
  // the words together: in the title, or all in one part of the text (the snippets' parts, read anyway). Among the first
  // ten, equal in title words, those first; when none has them, the words lie apart: "ankstyvasis įspėjimas" finds ANK
  // articles with "ankstyvas" in one part and "įspėjimą" (a penalty) in another, the law's term is "ankstyvasis perspėjimas"
  const together = (j) => scored[j][0] >= qstems.length || (snips[j] && /^(\d+)\/\1$/.test(snips[j].words_in_part || ""));
  // (with all-but-one results after them: among those with every word only)
  const hasAll = (j) => !lacks(scored[j][1]);
  let apart = false;
  if (snips.length && snips.some(Boolean) && terms.length >= 2 && (!lacking || full.length)) {
    const order = snips.map((_, j) => j).sort((a, b) => hasAll(b) - hasAll(a) || scored[b][0] - scored[a][0]
                                                       || (scored[b][0] > 0 && heading(scored[b][1]) - heading(scored[a][1])) || scored[b][2] - scored[a][2]
                                                       || together(b) - together(a) || a - b);
    apart = !order.some((j) => hasAll(j) && together(j));
    scored = order.map((j) => scored[j]).concat(scored.slice(order.length));
    snips = order.map((j) => snips[j]);
  }
  return {
    ...envelope(m),
    results: scored.map(([s, it], j) => {
      const a = byKey.get(m.item_acts[it[0]]) || {};
      return { act: a.key, cite: a.cite, act_name: a.name, number: it[4], label: it[1], title: it[2], url: it[3],
               status_label: it[5], title_match: s, ...(lacking ? { lacks_word: lacks(it) } : {}),
               ...(snip ? snips[j] || {} : { _words: snipWords }) };
    }),
    more: ordered.length > items.length ? `${ordered.length} articles contain ${lacking ? "all the words or all but one" : "all the words"}; name an act to narrow` : undefined,
    hint: lacking && full.length ? `Only ${full.length} article${full.length > 1 ? "s have" : " has"} all the words (first)${apart ? ", and they lie apart there (the law may use another term)" : ""}; then those with all but one (lacks_word). Try other wordings ("a | b").`
      : lacking && scored.length ? "No article has all the words: these have all but one (lacks_word). Try other wordings (\"a | b\")."
      : lacking ? "No article has all the words or all but one: search with fewer words, the law's own terms (\"skaitiklių patikra | matavimo priemonių patikra\"), not the whole question."
      : apart ? "The words lie apart in these articles (no title or part has them all): the law may use another term. Try other wordings (\"a | b\")."
      : undefined,
    defined_in: await defsP,  // the query is a defined term: where it is defined (feedback S8)
  };
}

// --- several articles at once and references both ways (D-036): fewer round trips for an agent's research ------------
// "EEĮ 2 str. 15 d.", "KET 3.2", "CK 6.228¹", "darbo kodeksas 52 str. 2 dalis" -> { act, article, part }
export async function parseRef(env, ref) {
  if (ref && typeof ref === "object") return { act: ref.act, article: ref.article ?? ref.n, part: ref.part, date: ref.date };
  const words = String(ref || "").trim().split(/\s+/).slice(0, 16);
  for (let i = words.length - 1; i >= 1; i--) {  // the longest start that names an act ("Statybos techninio reglamento STR 1.07.03:2017")
    const annex = /^pried/i.test(words[i + 1] || "");  // "MPTMRT 6 priedas", "Direktyvos 2014/32/ES V priedas"
    if (!/^\d/.test(words[i]) && !(annex && /^[IVXLC]+[a-z]?(?:-[A-Z])?$/.test(words[i]))) continue;
    const a = await findAct(env, words.slice(0, i).join(" "));
    if (!a) continue;
    // the rest, so that an appendix keeps its letter: "I priedo A priedėlis", "II-A priedėlis" (2021/2139)
    if (annex) return { act: a.key, article: /^priedo$/i.test(words[i + 1]) ? words.slice(i).join(" ") : words[i] + " priedas" };
    const rest = words.slice(i).join(" ");
    const part = rest.match(/^\S+\s*(?:str\.?|straipsn\w*|p\.?|punkt\w*)?\s*(\d+(?:-\d+)?)\s*(?:d\.|dal\w*)/i);
    return { act: a.key, article: words[i], part: part ? part[1] : undefined };
  }
  return { error: `"${ref}": name an act and an article, e.g. "DK 52", "EEĮ 2 str. 15 d.", "KET 3.2"` };
}

export async function getArticles(env, { refs, date }) {
  env = ownFiles(env);
  const m = await meta(env);
  const list = (Array.isArray(refs) ? refs : String(refs || "").split(/[;\n]+/)).filter((x) => x && String(x).trim()).slice(0, 20);
  if (!list.length) return { error: "missing parameter `refs`: up to 20 references, e.g. [\"DK 52\", \"EEĮ 2 str. 15 d.\", \"KET 3.2\"]" };
  const one = async (ref) => {
    const r = await parseRef(env, ref);
    if (r.error) return { ref, error: r.error };
    const x = await getArticle(env, { act: r.act, article: r.article, part: r.part, date: r.date ?? date });
    const { unofficial, notice, status_day, data_checked, open_data_newest_publication, ...rest } = x;  // said once, above
    return { ref, ...rest };
  };
  return { ...envelope(m), articles: await Promise.all(list.map(one)),
           more: (Array.isArray(refs) ? refs.length : list.length) > 20 ? "at most 20 references a call: the rest were not read" : undefined };
}

export async function related(env, { act, article, n, part, limit }) {
  article = article ?? n;
  const m = await meta(env);
  if (!act) return { error: "missing parameter `act` (key, abbreviation, TAR code or name; see list_acts)" };
  const a = await findAct(env, act);
  if (!a) return { error: `unknown act "${act}"; see list_acts` };
  const label = article === undefined || article === null || article === "" ? "" : articleLabel(article);
  if (label === null) return { error: `"${article}" is not an article or point number` };
  limit = Math.max(1, Math.min(Number(limit) || 50, 200));
  const all = (await getJSON(env, `/api/v1/refs/${a.key}.json`)) || {};
  let mine = all[label] || { cites: [], cited_by: [] };
  if (!all[label] && label.includes(".") && a.unit === "punktas") mine = all[label.split(".")[0]] || mine;  // a sub-point: its point
  if (part) {
    const p = String(part).replace(/^#/, "");
    const at = (anc) => anc && [p, "d" + p, "p" + p].some((w) => anc === w || anc.startsWith(w + "-") || anc.startsWith(w + "."));
    mine = { cites: mine.cites.filter((x) => at(x.from_part)), cited_by: mine.cited_by.filter((x) => at(x.to_part)) };
  }
  const decisions = mine.cited_by.filter((x) => x.kind === "decision").sort((x, y) => (y.adopted || "").localeCompare(x.adopted || ""));
  const byActs = mine.cited_by.filter((x) => x.kind !== "decision");
  const other = byActs.filter((x) => x.act !== a.key), same = byActs.filter((x) => x.act === a.key);
  const cut = (xs) => xs.slice(0, limit);
  return {
    ...envelope(m), act: { key: a.key, cite: a.cite, name: a.name }, article: label || undefined, part: part || undefined,
    cites: cut(mine.cites), cited_by_other_acts: cut(other), cited_by_same_act: cut(same), cited_by_regulator_decisions: cut(decisions),
    counts: { cites: mine.cites.length, cited_by_other_acts: other.length, cited_by_same_act: same.length,
              cited_by_regulator_decisions: decisions.length },
    note: "From the references the texts make with the act's name (\"Lietuvos Respublikos … įstatymo 9 straipsnio\", \"šio kodekso 52 " +
          "straipsnio\", \"Taisyklių 66 punkto\"): what is listed is cited; a reference worded otherwise (\"Įstatymo\" alone, an act not on " +
          "this site) is not listed. Use search_law for those.",
  };
}

// For search (D-036): where in the article the words are, so an agent can pick what to read: the first part holding
// all of them (else the most), its anchor and the words around the first one. The first 10 results; never fails a search.
async function snippets(env, hits) {
  try {
    const files = new Map();
    const load = (a, label) => {
      const path = `/api/v1/text/${a.key}/${fnv1a(label) % a.chunks}.json`;
      if (!files.has(path)) files.set(path, getJSON(env, path));
      return files.get(path);
    };
    return await Promise.all(hits.map(async ([a, label, words]) => {
      const stems = [...new Set((words || []).map(stemOf))];
      if (!a || !a.chunks || !stems.length) return null;
      const art = ((await load(a, label)) || {})[label];
      if (!art) return null;
      // the part with the most of the words; between equals, the one with the word rarest in the article ("kontaktiniai
      // duomenys": the part with "kontaktiniai", not the first of many with "duomenys")
      const has = (art.text || []).map((b) => { const f = fold(b.text); return stems.map((s) => new RegExp("(^|[^a-z])" + s).test(f)); });
      const freq = stems.map((_, i) => has.filter((h) => h[i]).length);
      let best = null, bestN = 0, bestR = 0;
      has.forEach((h, k) => {
        const n = h.filter(Boolean).length, r = Math.max(0, ...h.map((x, i) => (x ? 1 / freq[i] : 0)));
        if (n > bestN || (n === bestN && n && r > bestR)) { best = art.text[k]; bestN = n; bestR = r; }
      });
      if (!best) return null;
      const f = fold(best.text);
      const at = Math.min(...stems.map((s) => { const i = f.search(new RegExp("(^|[^a-z])" + s)); return i < 0 ? Infinity : i; }));
      const from = Math.max(0, at - 80), to = Math.min(best.text.length, at + 220);
      return { part: best.anchor || undefined, words_in_part: `${bestN}/${stems.length}`,
               snippet: (from ? "…" : "") + best.text.slice(from, to).trim() + (to < best.text.length ? "…" : "") };
    }));
  } catch { return []; }
}

// For search: the query's exact definitions (at most 5), or undefined; never fails the search
async function definedIn(env, query, only) {
  try {
    const q = String(query || "").slice(0, 120);
    if (defWords(q).length === 0 || defWords(q).length > 5) return undefined;
    const r = await findDefinition(env, { term: q, act: only ? only.key : undefined, limit: 5 });
    return r.results && r.results.length ? r.results.map((x) => ({ term: x.term, cite: x.cite, number: x.number, url: x.url })) : undefined;
  } catch { return undefined; }
}

const genericMemo = new WeakMap();  // per acts list: stems found in more than a quarter of the acts' names
function genericNameStems(all) {
  let g = genericMemo.get(all);
  if (!g) {
    const n = new Map();
    for (const a of all) for (const s of new Set(fold(a.name || "").split(/[^a-z]+/).filter((w) => w.length >= 4).map(stemOf))) n.set(s, (n.get(s) || 0) + 1);
    g = new Set([...n].filter(([, c]) => c * 4 > all.length).map(([s]) => s));
    genericMemo.set(all, g);
  }
  return g;
}

const folded = new WeakMap();  // per acts list (memoised with it): the folded names, made once, not per comparison
function foldedActs(all) {
  let f = folded.get(all);
  if (!f) {
    f = new Map();
    for (const a of all) {
      for (const x of [a.key, a.abbr, a.abbreviation, a.cite]) if (x && !f.has(fold(x))) f.set(fold(x), a);
      if (a.abbreviation && /į$/i.test(a.abbreviation) && fold(a.abbreviation).length >= 4) {  // "PVM" for PVMĮ, "GPM" for GPMĮ
        const k = "~" + fold(a.abbreviation).slice(0, -1);
        if (!f.has(k)) f.set(k, a);
      }
      if (!f.has("=" + fold(a.name))) f.set("=" + fold(a.name), a);
      for (const n of a.names || []) if (!f.has(fold(n))) f.set(fold(n), a);  // "gdpr", "ai act" (scope/names.yaml)
      // how texts cite it: "Energetikos įstatymo 15 straipsnis", "Lietuvos Respublikos energetikos įstatymo"
      if (a.genitive) for (const g of [fold(a.genitive), fold(a.genitive).replace(/^lietuvos respublikos /, "")]) if (!f.has("=" + g)) f.set("=" + g, a);
      // its number: "2016/679", "1907/2006", "92/43" from the CELEX in its URL
      const c = /\/es\/3(\d{4})[A-Z](\d{4})\//.exec(a.url || "");
      if (c) {
        const y = +c[1], n = +c[2], forms = c[1] >= "2015" || /\/es\/3\d{4}L/.test(a.url) ? [`${y}/${n}`, `${n}/${y}`] : [`${n}/${y}`, `${y}/${n}`];
        if (y < 2000) forms.push(`${y % 100}/${n}`, `${n}/${y % 100}`);
        for (const x of forms) if (!f.has("#" + x)) f.set("#" + x, a);
      }
    }
    folded.set(all, f);
  }
  return f;
}

// "2016/679", "(ES) 2016/679", "2003/88/EB": the EU act with that number
const EU_NUMBER = /^\(?(\d{1,4}\/\d{1,4})(?:\/[a-z]+)?\)?[.,;]?$/;
function euNumbered(all, phrase) {
  for (const w of String(phrase).split(/\s+/)) {
    const m = EU_NUMBER.exec(w);
    if (m && foldedActs(all).has("#" + m[1])) return foldedActs(all).get("#" + m[1]);
  }
  return null;
}
// the words around such a number that name no more than it does: "Reglamento (ES) Nr. 2016/679"
const EU_WORDS = /^\(?(?:reglament\w*|direktyv\w*|sprendim\w*|es|eb|eeb|nr\.?|igyvendinimo|deleguot\w*|komisijos|tarybos|europos|parlamento|ir|regulation|directive|eu|ec)\)?$/;

async function findActQuiet(all, phrase) {
  const f = phrase.trim();
  if (!f || /^\d/.test(f)) return null;
  const m = foldedActs(all);
  return m.get(f) || m.get("~" + f) || m.get("=" + f) || null;
}

function summary(r) {
  return { act: r.act.key, cite: r.act.cite, act_name: r.act.name, number: r.number, label: r.label, title: r.title,
           url: r.url, status_label: r.status && r.status.label };
}

// `query`: acts whose name, abbreviation or other name holds these words. All acts run to half a megabyte, too much for
// an agent's context in one call: MCP asks for a page (limit), the REST API for everything unless it says otherwise.
export async function listActs(env, { query, limit, offset } = {}) {
  const m = await meta(env);
  const words = fold(String(query || "")).split(/[^a-z0-9/]+/).filter(Boolean);
  const all = (await acts(env)).filter((a) => { const h = fold([a.cite, a.abbr, a.name, ...(a.names || [])].join(" ")); return words.every((w) => h.includes(w)); });
  const off = Math.max(0, Number(offset) || 0), lim = limit === undefined ? all.length : Math.max(1, Math.min(Number(limit) || 50, 200));
  const brief = limit !== undefined;  // a page for an agent: what it needs to name an act; the rest from get_act_contents
  return { ...envelope(m), total: all.length, offset: off,
    more: off + lim < all.length ? `${all.length} acts${words.length ? " match" : ""}; next page: offset ${off + lim}, or narrow with \`query\`` : undefined,
    acts: all.slice(off, off + lim).map((a) => (brief ? { key: a.key, cite: a.cite, name: a.name, unit: a.unit, articles: a.n, url: a.url }
      : { key: a.key, cite: a.cite, name: a.name, unit: a.unit, articles: a.n, url: a.url, official_url: a.official_url, counts: a.counts })) };
}

export async function getActContents(env, { act, offset, limit }) {
  const a = await findAct(env, act);
  if (!a) return { error: `unknown act "${act}"; see list_acts` };
  const idx = await getJSON(env, new URL(a.url).pathname + "articles.json");
  const off = Math.max(0, Number(offset) || 0), lim = Math.max(1, Math.min(Number(limit) || 100, 300));
  const arts = (idx && idx.articles) || [];
  return { ...envelope(await meta(env)), act: { key: a.key, cite: a.cite, name: a.name, url: a.url, official_url: a.official_url },
           total: arts.length, offset: off,
           items: arts.slice(off, off + lim).map((x) => ({ number: x.pretty, label: x.label, title: x.title, place: x.path, status_label: x.status_label,
                                                            label_valid_until: x.label_valid_until, url: x.url })),
           annexes: ((idx && idx.annexes) || []).map((x) => ({ number: x.pretty, label: x.label, title: x.title, status_label: x.status_label, url: x.url })) };
}

export async function upcomingChanges(env, { days, act }) {
  const m = await meta(env);
  const u = (await getJSON(env, "/api/v1/upcoming.json", { keep: true })).label_changes_next_30_days || [];
  const until = new Date(Date.parse(m.status_day) + (Math.min(Number(days) || 30, 30)) * 86400000).toISOString().slice(0, 10);
  const a = act ? await findAct(env, act) : null;
  return { ...envelope(m), until,
           changes: u.filter((x) => x.on <= until && (!a || x.act === a.abbr)).slice(0, 200) };
}

// --- Seimas votes (D-054, proof of concept: the branch seimas-votes, not released) ---------------------------------
// From the Chancellery's open data (datasets/gov/lrsk/balsavimai), built by src/ltlaw/seimas.py into /api/v1/seimas/.
// Shown as it is: who voted how, on what, with the lrs.lt record; nothing scored or ranked.
const SEIMAS = "/api/v1/seimas";
const CHOICE_LT = { 1: "už", 2: "prieš", 3: "susilaikė" };
const CHOICE_EN = { 1: "for", 2: "against", 3: "abstain" };
const NO_IND = { consensus: "decided by consensus (\"Pritarta bendru sutarimu\"): no individual votes exist",
                 secret: "a secret ballot: no individual votes exist",
                 "not published yet": "the individual votes are not in the open data yet (they come a few days after the totals)",
                 "none in the data": "the open data have no individual votes for it" };

// the term asked for; without one, the term of the day asked about (`from`, else `to`), else the current one
async function seimasTerm(env, term, day) {
  const m = await getJSON(env, `${SEIMAS}/meta.json`, { keep: true });
  if (!m || !m.terms || !m.terms.length) return { error: "Seimas votes are not available on this server" };
  const loaded = () => m.terms.map((x) => `term ${x.term} (votes ${x.first.slice(0, 10)} – ${x.last.slice(0, 10)})`).join(", ");
  let t;
  if (term) t = m.terms.find((x) => String(x.term) === String(term));
  else if (day) {
    // the term whose votes span the day, or the next one (a day between two terms: the new Seimas)
    t = m.terms.find((x) => day <= x.last.slice(0, 10)) || m.terms[m.terms.length - 1];
    if (day < m.terms[0].first.slice(0, 10)) return { error: `${day} is before the loaded votes: ${loaded()}` };
  } else t = m.terms[m.terms.length - 1];
  if (!t) return { error: `term ${term} is not loaded: ${loaded()}` };
  const ix = await getJSON(env, `${SEIMAS}/${t.term}/index.json`, { keep: true });
  return { meta: m, term: t, ix };
}

// a date range past the term's votes: one term a call, the rest said
function spanNote(s, from, to) {
  const later = to && s.meta.terms.find((x) => x.term > s.term.term && to >= x.first.slice(0, 10));
  const earlier = from && s.meta.terms.find((x) => x.term < s.term.term && from <= x.last.slice(0, 10));
  return later || earlier ? `only term ${s.term.term}'s votes: the dates reach into term ${(later || earlier).term} (ask again with \`term\`)` : undefined;
}

function seimasEnvelope(s) {
  return { unofficial: true, source: s.meta.source, term: s.term.term, votes_from: s.term.first, votes_to: s.term.last,
           individual_votes_until: s.term.individual_until, data_lacks: s.meta.lacks };
}

function voteOut(s, v, all) {
  const it = s.ix.items[v.it] || {};
  const a = it.act ? all.find((x) => x.key === it.act) : null;
  return { id: v.id, at: v.at, sitting: v.s, item: it.t || null, draft: it.draft, amends_law_no: it.law,
           act: a ? { key: a.key, name: a.name, url: a.url } : undefined,
           question: v.q || null, alternative: v.qa, type: v.ty, for: v.f ?? null, against: v.a ?? null, abstain: v.ab ?? null,
           verdict: v.v || null, record: v.r ? s.ix.record + v.r : null,
           individual: typeof v.ind === "number" ? "get_vote lists every MP's choice" : NO_IND[v.ind] || v.ind,
           // two alternatives: one votes "for the first" or "for the second" (Seimo statutas 118 str. 1 d.); the data put them
           // in the for and against columns
           reading: v.v === "nepritarta" && (v.f || 0) > (v.a || 0) + (v.ab || 0) ? "not passed although most votes cast were " +
             "for: a decision needs the votes of a majority of the MPs present (registered), who are not in the data " +
             "(Konstitucijos 69 str., Seimo statuto 113 str.); constitutional laws more" :
             v.ty === "Alternatyvus balsavimas" && v.qa ? `an alternative vote (Seimo statuto 118 str. 1 d.): "for" counts ` +
             `those who chose "${v.q}", "against" those who chose "${v.qa}"` :
             // "P": not explained by the source; in terms 9-10 "for" was at most half the votes cast in 2,261 of 2,566
             // (not adopted, it seems) but more in 305: only the arithmetic is said
             v.v === "P" && v.f != null ? `the result "P" is not explained by the source; "for" was ${v.f} of ` +
             `${v.f + (v.a || 0) + (v.ab || 0)} votes cast (${2 * v.f > v.f + (v.a || 0) + (v.ab || 0) ? "more" : "not more"} than half)` : undefined,
           note: v.bare ? `The open data have no agenda item or record link for this vote${v.bare === 3 ? "" : " and no totals"}` +
             (v.bare === 2 ? "; the totals are counted from the individual votes" : "") +
             ": the sitting's transcript on lrs.lt for that day says what was voted on." : undefined };
}

// the votes of the term in the dates that no query but dates can find (no agenda item in the open data): said, so that
// "not found" isn't read as "not voted on" (the partnership bill's first vote, 2021-05-25, is one)
function unfindable(s, f, from, to) {
  if (f.how === "all") return undefined;
  const n = s.ix.votes.filter((v) => v.bare && inDates(v, from, to)).length;
  return n ? `${n} votes of term ${s.term.term}${from || to ? " in these dates" : ""} have no agenda item in the open data: ` +
    "no words, draft or act find them; list them by date (query \"\" with from/to)" : undefined;
}

// A query: a draft number ("XVP-1885"), a law number ("XIV-1381"), an act on the site ("DK", "darbo kodeksas"),
// or words that must all be in the agenda item or the question (stems, as search_law)
async function voteFilter(env, s, query) {
  // "72¹" is "72-1" in the agenda items, as in search_law
  const q = String(query || "").trim().slice(0, 200).replace(/(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)/g, (x, d, sup) => d + "-" + [...sup].map((c) => SUP.indexOf(c)).join(""));
  if (!q) return { test: () => true, how: "all" };
  const dr = /\b([IVXL]*P-\d+)(\([^)]*\))?/i.exec(q);
  if (dr) {
    const want = dr[1].toUpperCase() + (dr[2] || "");
    const ok = new Set(s.ix.items.map((x, i) => [x, i]).filter(([x]) => x.draft && (dr[2] ? x.draft === want : x.draft.split("(")[0] === want)).map(([, i]) => i));
    return { test: (v) => ok.has(v.it), how: `draft ${want}` };
  }
  const ln = /\b([IVXL]+-\d+)\b/i.exec(q);
  if (ln) {
    const ok = new Set(s.ix.items.map((x, i) => [x, i]).filter(([x]) => x.law === ln[1].toUpperCase()).map(([, i]) => i));
    return { test: (v) => ok.has(v.it), how: `law No. ${ln[1].toUpperCase()}` };
  }
  const a = (await findAct(env, q)) || (await findActQuiet(await acts(env), fold(q)));  // "PVM": PVMĮ
  if (a) {
    const ok = new Set(s.ix.items.map((x, i) => [x, i]).filter(([x]) => x.act === a.key).map(([, i]) => i));
    if (ok.size) return { test: (v) => ok.has(v.it), how: `act ${a.cite || a.key} (by its number or name in the agenda item)` };
  }
  // an act and article numbers ("DK 138", "darbo kodekso 138 straipsnis", "PVMĮ 19"): the act's votes whose agenda item
  // names every number ("Darbo kodekso 127 ir 138 straipsnių pakeitimo …"; 12-1 for 12¹)
  const toks = fold(q).split(/[^a-z0-9-]+/).filter(Boolean);
  const nums = toks.filter((w) => /^\d+(-\d+)?$/.test(w));
  if (nums.length) {
    const rest = toks.filter((w) => !nums.includes(w) && !/^(str|straipsn\w*|p|punkt\w*|dal\w*|d)$/.test(w));
    const all = await acts(env);
    let act = rest.length ? (await findAct(env, rest.join(" "))) || (await findActQuiet(all, rest.join(" "))) : null;
    for (let n = rest.length; n >= 1 && !act; n--)
      for (let i = 0; i + n <= rest.length && !act; i++) act = await findActQuiet(all, rest.slice(i, i + n).join(" "));
    if (act) {
      const has = (t) => nums.every((n) => new RegExp(`(^|[^0-9-])${n}($|[^0-9-])`).test(t));
      const ok = new Set(s.ix.items.map((x, i) => [x, i]).filter(([x]) => x.act === act.key && has(x.t || "")).map(([, i]) => i));
      return { test: (v) => ok.has(v.it), how: `act ${act.cite || act.key}, agenda items naming ${nums.join(", ")} (the articles a draft changes; the votes on one article inside a draft are not told apart)` };
    }
  }
  // stems a little longer than search_law's: "nepasitikėjimas" must not find "nepasiturintiems" (both "nepasi")
  // (a number is matched whole: "2026", not "202…")
  const stems = [...new Set(fold(q).split(/[^a-z0-9]+/).filter((w) => w.length >= 4 || /^\d+$/.test(w))
    .map((w) => /^\d+$/.test(w) ? w + " " : w.slice(0, Math.max(4, w.length - (w.length >= 8 ? 3 : 2)))))].slice(0, 12);
  const short = [...new Set(fold(q).split(/[^a-z0-9]+/).filter((w) => w && w.length < 4 && !/^\d+$/.test(w)))];
  const ign = short.length ? ` (ignored, under 4 letters: ${short.join(", ")})` : "";
  if (!stems.length) return { error: "Name a draft (\"XVP-1885\"), a law number (\"XIV-1381\"), an act (\"DK\") or words of 4+ letters" };
  const hay = s.ix.items.map((x) => " " + fold(x.t || "").replace(/[^a-z0-9]+/g, " "));
  const missing = (v) => { const h = hay[v.it] + " " + fold(v.q || "").replace(/[^a-z0-9]+/g, " ") + " ";
                           return stems.filter((st) => !h.includes(" " + st)); };
  if (stems.length < 3 || s.ix.votes.some((v) => !missing(v).length))
    return { test: (v) => !missing(v).length, how: `words: ${stems.map((x) => x.trim()).join(", ")}${ign}` };
  // no vote has every word ("pridėtinės vertės mokesčio tarifas": no agenda item says "tarifas"): those lacking one, the
  // word named, rather than nothing
  const lacks = new Map(stems.map((st) => [st, 0]));
  for (const v of s.ix.votes) { const m = missing(v); if (m.length === 1) lacks.set(m[0], lacks.get(m[0]) + 1); }
  const drop = [...lacks].filter(([, n]) => n).sort((x, y) => y[1] - x[1])[0];
  if (!drop) return { test: () => false, how: `words: ${stems.map((x) => x.trim()).join(", ")}` };
  return { test: (v) => { const m = missing(v); return m.length === 1 && m[0] === drop[0]; },
           how: `words: ${stems.filter((st) => st !== drop[0]).map((x) => x.trim()).join(", ")} (no vote's agenda item or question has all; "${drop[0].trim()}…" left out)${ign}` };
}

function badDates(from, to) {
  for (const [k, d] of [["from", from], ["to", to]])
    if (d && !(/^\d{4}-\d{2}-\d{2}$/.test(String(d)) && !isNaN(Date.parse(String(d))) && new Date(String(d)).toISOString().slice(0, 10) === String(d)))
      return { error: `${k}: a day as YYYY-MM-DD, e.g. 2026-06-30` };
  if (from && to && String(from) > String(to)) return { error: "from is after to" };
  return null;
}

function inDates(v, from, to) {
  return (!from || v.at >= String(from)) && (!to || v.at.slice(0, 10) <= String(to));
}

export async function searchVotes(env, { query, term, from, to, limit } = {}) {
  const bd = badDates(from, to);
  if (bd) return bd;
  const s = await seimasTerm(env, term, from || to);
  if (s.error) return s;
  const f = await voteFilter(env, s, query);
  if (f.error) return f;
  limit = Math.max(1, Math.min(Number(limit) || 20, 100));
  const all = await acts(env);
  const hits = s.ix.votes.filter((v) => f.test(v) && inDates(v, from, to)).reverse();
  return { ...seimasEnvelope(s), term_note: spanNote(s, from, to), matched_by: f.how, total: hits.length, not_findable: unfindable(s, f, from, to), results: hits.slice(0, limit).map((v) => voteOut(s, v, all)),
           hint: hits.length > limit ? `newest first; ${hits.length - limit} more (narrow with from/to or more words)` : undefined };
}

export async function getVote(env, { id, term } = {}) {
  if (id === undefined || id === null || id === "") return { error: "missing parameter `id`: a vote id from search_votes or mp_votes, e.g. \"-60610\"" };
  let s = await seimasTerm(env, term);
  if (s.error) return s;
  let v = s.ix.votes.find((x) => x.id === String(id));
  if (!v && !term) {  // an id from an earlier term (ids are the Chancellery's, one series)
    for (const t of s.meta.terms.slice(0, -1).reverse()) {
      const o = await seimasTerm(env, t.term);
      const w = !o.error && o.ix.votes.find((x) => x.id === String(id));
      if (w) { s = o; v = w; break; }
    }
  }
  if (!v) return { error: `no vote ${id} in ${term ? `term ${s.term.term}` : "the loaded terms"} (ids come from search_votes)` };
  const out = { ...seimasEnvelope(s), vote: voteOut(s, v, await acts(env)) };
  if (typeof v.ind !== "number") return out;
  const [block, mps] = await Promise.all([getJSON(env, `${SEIMAS}/${s.term.term}/v/${v.ind}.json`), getJSON(env, `${SEIMAS}/${s.term.term}/mps.json`, { keep: true })]);
  const c = (block || {})[v.id];
  if (!c) return { ...out, error: "the individual votes could not be read" };
  const names = (l) => l.map((i) => mps[i].name).sort();
  return { ...out, for: names(c.for), against: names(c.against), abstain: names(c.abstain),
           not_listed: "MPs not listed did not vote (absent, present without voting, or not an MP that day: the data don't tell)" };
}

export async function mpVotes(env, { mp, query, term, choice, from, to, limit } = {}) {
  const bd = badDates(from, to);
  if (bd) return bd;
  let s = await seimasTerm(env, term, from || to);
  if (s.error) return s;
  mp = String(mp ?? "").slice(0, 80);  // a name, not a text
  const words = fold(mp).split(/[^a-z]+/).filter((w) => w.length >= 2).slice(0, 5);
  if (!words.length) return { error: "missing parameter `mp`: an MP's name or surname, e.g. \"Kubilius\"" };
  const match = (list) => list.filter((x) => { const n = fold(x.name).split(/[^a-z]+/); return words.every((w) => n.some((p) => p.startsWith(w))); });
  let mps = await getJSON(env, `${SEIMAS}/${s.term.term}/mps.json`, { keep: true });
  let found = match(mps), elsewhere;
  if (!found.length && !term && !from && !to) {  // not in the current term: the newest earlier term they voted in, said so
    for (const t of s.meta.terms.slice(0, -1).reverse()) {
      const l = await getJSON(env, `${SEIMAS}/${t.term}/mps.json`, { keep: true });
      if (l && match(l).length) { elsewhere = s.term.term; s = await seimasTerm(env, t.term); mps = l; found = match(l); break; }
    }
  }
  if (!found.length) return { error: `no MP "${mp}" voted in ${term || from || to ? `term ${s.term.term}` : "the loaded terms"}`, ...seimasEnvelope(s) };
  if (found.length > 1) return { error: `"${mp}" matches ${found.length} MPs: give the full name`, candidates: found.map((x) => x.name) };
  const who = found[0];
  // the same person in the other loaded terms (an MP's id is the term's own; `person`, the asmens_id, is not)
  const also = [];
  for (const t of s.meta.terms) if (t.term !== s.term.term) {
    const l = await getJSON(env, `${SEIMAS}/${t.term}/mps.json`, { keep: true });
    if (l && l.some((x) => (who.person ? x.person === who.person : x.name === who.name))) also.push(t.term);
  }
  const f = await voteFilter(env, s, query);
  if (f.error) return f;
  const want = choice ? Object.entries(CHOICE_EN).find(([, n]) => n === String(choice).toLowerCase())?.[0] ||
    Object.entries(CHOICE_LT).find(([, n]) => fold(n) === fold(String(choice)))?.[0] : null;
  if (choice && !want) return { error: "choice: for, against or abstain" };
  limit = Math.max(1, Math.min(Number(limit) || 30, 200));
  const rows = (await getJSON(env, `${SEIMAS}/${s.term.term}/mp/${who.i}.json`)) || [];
  const all = await acts(env);
  const hits = rows.filter(([pos, r]) => (!want || String(r) === want) && f.test(s.ix.votes[pos]) && inDates(s.ix.votes[pos], from, to)).reverse();
  // the matching votes with no individual record: say how many, so "not listed" isn't read as "didn't vote"
  // (within the MP's own time in this term: before their first vote or after their last they were no MP)
  const without = s.ix.votes.filter((v) => typeof v.ind !== "number" && f.test(v) && inDates(v, from, to) &&
                                           (!who.first || (v.at >= who.first && v.at <= who.last))).length;
  const counts = { for: 0, against: 0, abstain: 0 };
  for (const [, r] of hits) counts[CHOICE_EN[r]]++;
  return { ...seimasEnvelope(s), mp: who.name, voted_from: who.first, voted_to: who.last, also_in_terms: also.length ? also : undefined,
           term_note: elsewhere ? `not an MP in term ${elsewhere}: term ${s.term.term}'s votes (pass \`term\` for another)` : spanNote(s, from, to),
           matched_by: f.how, total: hits.length, counts,
           matching_votes_without_individual_record: without, not_findable: unfindable(s, f, from, to),
           results: hits.slice(0, limit).map(([pos, r]) => ({ choice: CHOICE_EN[r], choice_lt: CHOICE_LT[r], ...voteOut(s, s.ix.votes[pos], all) })),
           note: "Only the MP's recorded votes are listed: a vote of the same item without the MP means absent or not voting." };
}

// GET /api: what an agent can call (feedback P1: the API was only described inside llms.txt)
const API_INDEX = {
  name: "Atviri teisės aktai API", unofficial: true, docs: "https://atviri-teises-aktai.lt/llms.txt",
  mcp: { url: "/mcp", transport: "Streamable HTTP, JSON-RPC 2.0, no key",
         tools: ["search_law", "get_article", "get_articles", "related", "find_definition", "list_acts", "get_act_contents", "upcoming_changes",
                 "search_votes", "get_vote", "mp_votes"] },
  rest: {
    "/api/search": "q (required), act, limit (≤30)",
    "/api/article": "act (key, abbreviation, TAR code or name), article (or n), part (optional: \"107\" or \"d107\"), date (optional YYYY-MM-DD), find (optional: only the paragraphs and table rows with these words), offset (a long text comes in pieces)",
    "/api/definition": "term (required), act (optional): where a term is defined, in every act",
    "/api/articles": "ref (repeatable, up to 20: \"DK 52\", \"EEĮ 2 str. 15 d.\") or refs (separated by ;), date (optional)",
    "/api/related": "act (required), article, part, limit: what the article cites and what cites it (acts, regulator decisions)",
    "/api/acts": "q (words of a name or common name), limit, offset; without them every act",
    "/api/contents": "act, offset, limit",
    "/api/upcoming": "days, act",
  },
  errors: "{ error } with HTTP 404 (no such act or article) or 400 (a bad request)",
  skill: "/skills/lithuanian-law-research/SKILL.md",
  static: { acts: "/api/v1/acts.json", meta: "/api/v1/meta.json", definitions: "/api/v1/definitions.json", regulator_decisions: "/api/v1/vert.json",
            act: "/ta/<tar_kodas>/data.json", act_index: "/ta/<tar_kodas>/articles.json" },
  notice: "Unofficial text. Official publication only in the Register of Legal Acts (e-tar.lt).",
};

const TOOLS = [
  { name: "search_law", run: searchLaw,
    description: "Find articles of Lithuanian codes, laws and Government-approved rules (unofficial mirror of e-tar.lt). " +
      "Use a reference (\"DK 52\", \"CK 6.228¹\", \"KET 52\", \"GDPR 17\", \"2019/944 15\", \"Energetikos įstatymo 15 straipsnis\") or Lithuanian " +
      "words (\"kasmetinės atostogos\", also everyday ones: \"alimentai\"). Returns articles with their URL, whether their text applies " +
      "today, and for the first 10 the part where the words are (`part`, `snippet`); `suggested`: chosen for these everyday words, not from the text. " +
      "Annexes are searched too (label \"priedas-6\"): lists, forms and tables that the articles refer to.",
    inputSchema: { type: "object", properties: {
      query: { type: "string", description: "A reference or Lithuanian words (4+ letters each; all must occur; when fewer than 3 " +
        "articles have them all, then also those with all but one, each naming the word it lacks in `lacks_word`). Up to 3 " +
        "alternative wordings separated by \"|\" are searched together: \"telefono numeris | ryšio duomenys\"" },
      act: { type: "string", description: "Optional: limit to one act (key, abbreviation or name, e.g. \"DK\")" },
      limit: { type: "integer", minimum: 1, maximum: 30, default: 10, description: "How many results, 1 to 30 (default 10)" } }, required: ["query"] } },
  { name: "get_article", run: getArticle,
    description: "The text of one article (or point) as published by the Seimas Chancellery, unchanged, with its status today " +
      "(Galioja šiandien / Įsigalios D / Gali būti pasenęs / Neaišku, ar galioja / Neteko galios), until when that label is " +
      "certain, amending acts, the future wording if adopted, defined terms used, a citation line and the official e-tar.lt link.",
    inputSchema: { type: "object", properties: {
      act: { type: "string", description: "Act key, abbreviation, TAR code or name: \"DK\", \"CK\", \"KET\", \"2016-23709\", \"darbo kodeksas\"" },
      article: { type: "string", description: "Article or point number: \"52\", \"21¹\" or \"21-1\", \"6.228-1\", \"3.2\" (also accepted as `n`); an annex: \"6 priedas\", \"V priedas\" (whether an annex is in force today is not checked: its status says so)" },
      part: { type: "string", description: "Optional: one part of the article, by number or anchor (\"107\" or \"d107\"; a rule's sub-point \"8.12\" or \"p8.12\"): only that part's text (and its future wording) instead of the whole article" },
      date: { type: "string", description: "Optional YYYY-MM-DD: the text in force on that date (the Chancellery's official consolidation " +
        "for it, since 2020, where the open data hold one); without it, today's text" },
      find: { type: "string", description: "Optional: only the paragraphs and table rows holding these words, e.g. a substance's name or CAS number in a long annex (\"formaldehidas\", \"50-00-0\")" },
      offset: { type: "number", description: "Optional: a very long text comes in pieces of about 60,000 characters; the answer's next_offset says where the next begins" } },
      required: ["act", "article"] } },
  { name: "find_definition", run: findDefinition,
    description: "Where a term is legally defined, in every act on the site: the term, its alias (\"toliau – …\"), the definition " +
      "text, the act and article/part with a link, and the article's status today. Inflection-tolerant (\"vartotojo objektas\" = " +
      "\"vartotojo objektą\"). The same word often means different things in different acts (\"vartotojas\" in EĮ, EEĮ, GDĮ, VTAĮ): " +
      "all are returned, plus narrower terms ending in it (\"elektros energijos vartotojas\").",
    inputSchema: { type: "object", properties: {
      term: { type: "string", description: "A word or phrase: \"vartotojo objektas\", \"bešeimininkis daiktas\"" },
      act: { type: "string", description: "Optional: the meaning in this act (key, abbreviation, TAR code or name). If the act " +
        "does not define the term itself but says its terms are understood as defined in other acts (\"sąvokos suprantamos " +
        "taip, kaip jos apibrėžtos … įstatyme\"), those acts' definitions are returned, with the sentence in by_reference" },
      limit: { type: "integer", default: 20, maximum: 50, description: "How many definitions, at most 50 (default 20)" } },
      required: ["term"] } },
  { name: "get_articles", run: getArticles,
    description: "Several articles (or points, or parts) in one call, up to 20: each as get_article returns it. Use it to read " +
      "everything a search or `related` found, instead of one call per article.",
    inputSchema: { type: "object", properties: {
      refs: { type: "array", maxItems: 20, items: { anyOf: [{ type: "string" }, { type: "object", properties: {
        act: { type: "string" }, article: { type: "string" }, part: { type: "string" } }, required: ["act", "article"] }] },
        description: "References: \"DK 52\", \"EEĮ 2 str. 15 d.\" (one part), \"KET 3.2\", \"CK 6.228¹\", or {act, article, part}" },
      date: { type: "string", description: "Optional YYYY-MM-DD for all of them (as get_article's `date`)" } },
      required: ["refs"] } },
  { name: "related", run: related,
    description: "References both ways for an article (or point, part, or a whole act): the articles it cites, and the articles of " +
      "other acts, of the same act and the energy regulator's (VERT) decisions that cite it. E.g. which rules and decisions " +
      "apply an article of a law. Each item has its status and URL; read them with get_articles.",
    inputSchema: { type: "object", properties: {
      act: { type: "string", description: "Act key, abbreviation, TAR code or name" },
      article: { type: "string", description: "Article or point number; omit for references to the act as a whole" },
      part: { type: "string", description: "Optional: one part (\"2\" or \"d2\"; a sub-point \"p8.12\")" },
      limit: { type: "integer", default: 50, maximum: 200, description: "Per list" } },
      required: ["act"] } },
  { name: "list_acts", run: (env, a) => listActs(env, { limit: 50, ...a }),
    description: "The acts on the site, 50 at a time: key, citation form, name, number of articles. Over 1,200 acts: give `query` (words of the name or a common name: \"energetikos\", \"GDPR\"). You rarely need this: search_law and get_article take an act's name, abbreviation, common name or EU number directly.",
    inputSchema: { type: "object", properties: {
      query: { type: "string", description: "Words of the act's name, abbreviation or common name" },
      limit: { type: "number", description: "Acts per page, at most 200 (default 50)" },
      offset: { type: "number", description: "Skip this many (from `more`)" } } } },
  { name: "get_act_contents", run: getActContents,
    description: "The articles of one act in order (number, title, chapter, status), paged, and its annexes (read one with get_article: \"6 priedas\").",
    inputSchema: { type: "object", properties: {
      act: { type: "string", description: "Act key, abbreviation, TAR code or name: \"DK\", \"CK\", \"2016-23709\", \"darbo kodeksas\"" },
      offset: { type: "integer", default: 0, description: "Skip this many entries of the contents (from the answer's next_offset)" },
      limit: { type: "integer", default: 100, maximum: 300, description: "Entries per page, at most 300 (default 100)" } },
      required: ["act"] } },
  { name: "search_votes", run: searchVotes,
    description: "Seimas votes (the Lithuanian parliament; preview): find votes by a draft number ('XVP-1885'), the number of the law a " +
      "draft amends ('XIV-1381'), an act on this site ('DK', 'darbo kodeksas') or Lithuanian words of the agenda item. Newest " +
      "first: when, what was voted on, for/against/abstain, the result, the lrs.lt record. Says what the data lack (factions, " +
      "consensus decisions and secret ballots have no individual votes).",
    inputSchema: { type: "object", properties: {
      query: { type: "string", description: "A draft number, a law number, an act (with article numbers: 'DK 138'), or words (all must occur); empty: the newest votes" },
      term: { type: "integer", description: "Seimas term (kadencija) id (10: 2024–2028, 9: 2020–2024); default the term of `from`/`to`, else the current one" },
      from: { type: "string", description: "Optional: from this day (YYYY-MM-DD)" },
      to: { type: "string", description: "Optional: to this day (YYYY-MM-DD)" },
      limit: { type: "integer", default: 20, maximum: 100 } }, required: ["query"] } },
  { name: "get_vote", run: getVote,
    description: "One Seimas vote (an id from search_votes or mp_votes): what was voted on, the totals and every MP's choice " +
      "(for, against, abstain), or why there are no individual votes.",
    inputSchema: { type: "object", properties: { id: { type: "string" }, term: { type: "integer" } }, required: ["id"] } },
  { name: "mp_votes", run: mpVotes,
    description: "How one MP voted: their recorded votes, optionally only on votes matching a query (draft, law number, act or " +
      "words, as search_votes) and one choice; newest first, with counts.",
    inputSchema: { type: "object", properties: {
      mp: { type: "string", description: "The MP's name or surname ('Kubilius', 'Andrius Kubilius')" },
      query: { type: "string", description: "Optional: only votes matching this (as search_votes)" },
      choice: { type: "string", description: "Optional: for, against or abstain" },
      term: { type: "integer" }, from: { type: "string" }, to: { type: "string" },
      limit: { type: "integer", default: 30, maximum: 200 } }, required: ["mp"] } },
  { name: "upcoming_changes", run: upcomingChanges,
    description: "Articles whose text or status changes in the next days (adopted amendments with a date).",
    inputSchema: { type: "object", properties: {
      days: { type: "integer", default: 30, maximum: 30, description: "How many days ahead from the labels' day, at most 30 (default 30)" },
      act: { type: "string", description: "Optional: only this act (key, abbreviation, TAR code or name)" } } } },
];

// --- MCP (JSON-RPC 2.0 over HTTP POST) -----------------------------------------------------------------
// The research recipe (D-036): the site's Agent Skill file, also offered as an MCP prompt
const SKILL_PATH = "/skills/lithuanian-law-research/SKILL.md";
const PROMPT = { name: "research_lithuanian_law",
  description: "How to research a question of Lithuanian law with this server's tools: wordings, definitions, batches, references both ways, status labels.",
  arguments: [{ name: "question", description: "The question to research (any language)", required: false }] };

function asText(result) {
  if (result.error) return result.error;
  return JSON.stringify(result, null, 1);
}

async function rpc(env, msg) {
  const { id, method, params } = msg || {};
  const reply = (result) => ({ jsonrpc: "2.0", id, result });
  const fail = (code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
  if (!msg || msg.jsonrpc !== "2.0" || typeof method !== "string") return fail(-32600, "invalid request");
  if (id === undefined) return null;  // a notification (notifications/initialized …): no reply
  switch (method) {
    case "initialize": {
      const asked = params && params.protocolVersion;
      return reply({ protocolVersion: PROTOCOLS.includes(asked) ? asked : PROTOCOLS[0],
                     capabilities: { tools: { listChanged: false }, prompts: { listChanged: false } },
                     serverInfo: SERVER,
                     instructions: "Unofficial article-by-article text of Lithuanian law with a status label per article. Always pass on the " +
                       "label and the e-tar.lt link; a label other than \"Galioja šiandien\" means: check the official text. " +
                       "To research a question: search_law with two or three Lithuanian wordings; find_definition for the key terms " +
                       "(meanings differ between acts); read the hits with one get_articles call; related on the key articles for the " +
                       "rules, laws and regulator decisions that apply or rely on them. The prompt research_lithuanian_law has the full recipe." });
    }
    case "ping": return reply({});
    case "prompts/list":
      return reply({ prompts: [{ name: PROMPT.name, description: PROMPT.description, arguments: PROMPT.arguments }] });
    case "prompts/get": {
      if (!params || params.name !== PROMPT.name) return fail(-32602, `unknown prompt ${params && params.name}`);
      const q = String((params.arguments && params.arguments.question) || "").slice(0, 2000);
      const skill = String((await getJSON(env, SKILL_PATH, { keep: true, text: true })) || "").replace(/^---[\s\S]*?---\s*/, "");
      return reply({ description: PROMPT.description, messages: [{ role: "user", content: { type: "text",
        text: skill + (q ? `\n\n## The question\n\n${q}\n\nAnswer it with the tools of this server, following the recipe above.` : "") } }] });
    }
    case "tools/list":
      return reply({ tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema, annotations: { readOnlyHint: true } })) });
    case "tools/call": {
      const tool = TOOLS.find((t) => t.name === (params && params.name));
      if (!tool) return fail(-32602, `unknown tool ${params && params.name}`);
      try {
        const result = await tool.run(env, (params && params.arguments) || {});
        return reply({ content: [{ type: "text", text: asText(result) }], structuredContent: result, isError: Boolean(result.error) });
      } catch (e) {
        return reply({ content: [{ type: "text", text: `The site's data could not be read: ${e.message}` }], isError: true });
      }
    }
    default: return fail(-32601, `method ${method} not found`);
  }
}

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
               "Access-Control-Allow-Headers": "Content-Type, Mcp-Session-Id, Mcp-Protocol-Version, Accept" };
// the REST API's answers: an error has its HTTP status too (404: no such act or article; 400: a bad request)
const rest = (v) => json(v, !v.error ? 200 : /unknown act|has no|had no|no official consolidation/.test(v.error) ? 404 : 400);
const json = (v, status = 200) => new Response(JSON.stringify(v), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...CORS } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    try {
      if (url.pathname === "/mcp") {
        if (request.method !== "POST") return json({ error: "POST JSON-RPC messages here (MCP Streamable HTTP)" }, 405);
        let body;
        try { body = await request.json(); } catch { return json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } }, 400); }
        if (Array.isArray(body)) {
          if (!body.length) return json({ jsonrpc: "2.0", id: null, error: { code: -32600, message: "invalid request: empty batch" } }, 400);
          const out = (await Promise.all(body.map((m) => rpc(env, m)))).filter(Boolean);
          return out.length ? json(out) : new Response(null, { status: 202, headers: CORS });
        }
        const out = await rpc(env, body);
        return out ? json(out) : new Response(null, { status: 202, headers: CORS });
      }
      if (url.pathname === "/kaip-buvo" || url.pathname === "/kaip-buvo/")  // the dated pages for people (D-030)
        return await datedPage(env, url, { acts: () => acts(env), meta: () => meta(env),
                                           shell: () => getJSON(env, "/api/v1/dated.html", { keep: true, text: true }) });
      const p = Object.fromEntries(url.searchParams);
      if (url.pathname === "/api/search") return rest(await searchLaw(env, { query: p.q, act: p.act, limit: p.limit }));
      if (url.pathname === "/api/article") return rest(await getArticle(env, { act: p.act, article: p.article ?? p.n, part: p.part, date: p.date, find: p.find, offset: p.offset }));
      if (url.pathname === "/api" || url.pathname === "/api/") return json(API_INDEX);
      if (url.pathname === "/api/definition") return rest(await findDefinition(env, { term: p.term ?? p.q, act: p.act, limit: p.limit }));
      if (url.pathname === "/api/articles") return rest(await getArticles(env, { refs: url.searchParams.getAll("ref").length ? url.searchParams.getAll("ref") : p.refs, date: p.date }));
      if (url.pathname === "/api/related") return rest(await related(env, { act: p.act, article: p.article ?? p.n, part: p.part, limit: p.limit }));
      if (url.pathname === "/api/acts") return rest(await listActs(env, { query: p.q ?? p.query, limit: p.limit, offset: p.offset }));
      if (url.pathname === "/api/contents") return rest(await getActContents(env, { act: p.act, offset: p.offset, limit: p.limit }));
      if (url.pathname === "/api/upcoming") return rest(await upcomingChanges(env, { days: p.days, act: p.act }));
      if (env.ASSETS) return env.ASSETS.fetch(request);  // any other path: the site's own answer (its 404 page)
      return json({ ...SERVER, mcp: "/mcp", rest: ["/api/search?q=", "/api/article?act=&n=", "/api/acts", "/api/contents?act=", "/api/upcoming"],
                    tools: TOOLS.map((t) => t.name), site: env.SITE_ORIGIN, unofficial: true });
    } catch (e) {
      return json({ error: `The site's data could not be read: ${e.message}` }, 502);
    }
  },
};
