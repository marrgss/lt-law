#!/usr/bin/env node
// Search ranking on everyday questions (worker-mcp searchLaw against a built site): top-1 / top-3 hits.
// Usage: node bin/check_search_ranking.mjs [out/site] [--worker path/to/index.js] [--quiet]
// The questions and their right acts: bin/search_questions.json (a hit: the result's act name starts with one of the
// expected names, or names it in brackets, "(eIDAS)"; with `article`, that label too).
// 2026-10-23: 14/25 -> 20/25 top-1 (title words, act names, scoping); 2026-11-03: 80 questions.
import fs from "node:fs"; import path from "node:path";
const args = process.argv.slice(2);
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args.splice(i, 2)[1] : null; };
const worker = opt("--worker") || "worker-mcp/index.js";
const quiet = args.includes("--quiet") && args.splice(args.indexOf("--quiet"), 1);
const root = path.resolve(args[0] || "out/site");
globalThis.fetch = async (url) => { const f = path.join(root, decodeURIComponent(new URL(url).pathname));
  return fs.existsSync(f) && !fs.statSync(f).isDirectory() ? new Response(fs.readFileSync(f)) : new Response("", { status: 404 }); };
const { searchLaw } = await import(path.resolve(worker));
const env = { SITE_ORIGIN: "http://site.local" };
const here = path.dirname(new URL(import.meta.url).pathname);
const { questions } = JSON.parse(fs.readFileSync(path.join(here, "search_questions.json"), "utf8"));
const ok = (x, want) => { const n = (x.act_name || "").toLowerCase();
  return want.acts.some((a) => n.startsWith(a) || n.includes(`(${a})`)) && (!want.article || x.label === want.article); };
let hit1 = 0, hit3 = 0;
for (const want of questions) {
  const r = await searchLaw(env, { query: want.q, limit: 5 });
  const res = r.results || [];
  const i = res.findIndex((x) => ok(x, want));
  if (i === 0) hit1++; if (i >= 0 && i < 3) hit3++;
  if (!quiet) console.log(`${i === 0 ? "1 " : i > 0 && i < 3 ? "3 " : "- "} ${want.q.padEnd(46)} ${res.slice(0, 3).map((x) => `${x.act.slice(0, 28)}:${x.label}`).join("  ")}`);
}
console.log(`top-1 ${hit1}/${questions.length}, top-3 ${hit3}/${questions.length}`);
