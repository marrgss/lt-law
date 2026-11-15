// The dated pages (D-030): /kaip-buvo/?u=<article page path>[&data=YYYY-MM-DD]. One article's text as the
// Chancellery's official consolidation had it on a past date, and the periods its text stayed the same, from the R2
// history (bin/export_history.py: v1/<act>/h/<label>.json + v1/a/<hash>.json, two reads a page). The look comes
// from the site's own shell (/api/v1/dated.html, rendered from base.html at build time). Never indexed.

const SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹";
const UNIT = { straipsnis: ["straipsnis", "straipsnio", "str."], punktas: ["punktas", "punkto", "p."] };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pretty = (l) => l.replace(/-(\d+)/, (x, d) => [...d].map((c) => SUP[+c]).join(""));
const shift = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * 86400000).toISOString().slice(0, 10);
const nextDay = (d) => shift(d, 1);

/** "/ta/<tar>[/<doc>]/(str|p)/<label>/" -> [act path, label], or null. */
export function parseArticlePath(u) {
  const m = String(u || "").replace(/^https?:\/\/[^/]+/, "").match(/^(\/ta\/[A-Za-z0-9._\-]+(?:\/[a-z0-9\-]+)?\/)(str|p)\/([0-9A-Za-z.\-]+)\/$/);
  return m ? [m[1], m[3]] : null;
}

/** The period of `tl` in force on `date`, or null. */
export function periodOn(tl, date) {
  return (tl.periods || []).find((p) => p.from <= date && date <= p.to) || null;
}

/** "Kas pakeista": this period against the one before, as stored by bin/export_history.py (word diff, escaped). */
export function changesHtml(tl, p) {
  const i = tl.periods.indexOf(p), prev = i > 0 ? tl.periods[i - 1] : null;
  if (!prev || !(p.changes || []).length) return "";
  const rows = p.changes.map((c) => `<p><span class="aka">${esc(c.kind)}:</span> ${c.html}</p>`).join("\n");
  return `<details open><summary>Kas pakeista nuo ${p.from} (palyginti su redakcija, galiojusia ${prev.from} – ${prev.to})</summary>
<div class="law diff">${rows}</div></details>`;
}

function page(shell, title, main) {
  return shell.replaceAll("%%TITLE%%", esc(title)).replace("%%MAIN%%", main);
}

function timelineHtml(tl, a, path, chosen, today) {
  const href = (d) => `/kaip-buvo/?u=${encodeURIComponent(path)}&amp;data=${d}`;
  const rows = [];
  let prevTitle = null;
  tl.periods.forEach((p, i) => {
    const range = p.open_end ? `nuo ${p.from} (bent iki ${p.to})` : `${p.from} – ${p.to}`;
    const here = chosen && chosen.from === p.from ? ' aria-current="page"' : "";
    const renamed = i && p.title !== prevTitle ? ` <span class="path">pavadinimas: „${esc(p.title || "")}“</span>` : "";
    const n = (p.changes || []).length, what = n ? ` <span class="path">· pakeitimų: ${n}</span>` : "";
    rows.push(`<li><a href="${href(p.from)}"${here}>${range}</a>${what}${renamed}</li>`);
    prevTitle = p.title;
    const nxt = tl.periods[i + 1];
    if (nxt && nextDay(p.to) < nxt.from)
      rows.push(`<li><span class="path">${nextDay(p.to)} – ${shift(nxt.from, -1)}: atviruose duomenyse šios redakcijos nėra</span></li>`);
  });
  const last = tl.periods[tl.periods.length - 1];
  if (last && last.to < today)
    rows.push(`<li><span class="path">${nextDay(last.to)} – šiandien: oficialių suvestinių redakcijų atviruose duomenyse nėra (žr. e-tar.lt)</span></li>`);
  rows.push(`<li><a href="${esc(path)}"><strong>Šiandien galiojantis tekstas →</strong></a></li>`);
  return `<h2 id="redakcijos">Šio ${UNIT[a.unit]?.[1] || "straipsnio"} redakcijos nuo 2020 m.</h2>
<ul class="toc">${rows.join("")}</ul>
<form action="/kaip-buvo/" method="get"><input type="hidden" name="u" value="${esc(path)}">
<label>Kaip buvo kitą dieną? <input type="date" name="data" min="2020-01-01" max="${today}"${chosen ? ` value="${esc(chosen.date)}"` : ""} required></label> <button>Rodyti</button></form>
<p class="aka">Tekstai – Seimo kanceliarijos oficialios suvestinės redakcijos iš atvirų duomenų (data.gov.lt), nekeisti; laikotarpis – kol šio ${UNIT[a.unit]?.[1] || "straipsnio"} tekstas nesikeitė. Prieš remdamiesi, patikrinkite <a href="${esc(a.official_url)}">e-tar.lt ↗</a>.</p>`;
}

/**
 * The response for /kaip-buvo/. `site` = { acts(), meta(), shell() }; `env.HISTORY` = the R2 bucket.
 */
export async function datedPage(env, url, site) {
  const html = (status, body, extra = {}) => new Response(body, { status, headers: {
    "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=3600", "X-Robots-Tag": "noindex", ...extra } });
  const shell = await site.shell();
  const u = url.searchParams.get("u") || "", parsed = parseArticlePath(u);
  const m = await site.meta(), today = m.status_day;
  const all = await site.acts();
  const a = parsed && all.find((x) => new URL(x.url).pathname === parsed[0]);
  if (!a) return html(404, page(shell, "Nerasta – Atviri teisės aktai",
    `<h1>Nerasta</h1><p>Nurodykite straipsnio puslapį, pvz. <a href="/kaip-buvo/?u=%2Fta%2F2016-23709%2Fstr%2F52%2F">DK 52 straipsnio redakcijos</a>.</p>`));
  const [path0, label] = parsed, path = u.replace(/^https?:\/\/[^/]+/, "");  // the article page (validated above)
  const unit = UNIT[a.unit] || UNIT.straipsnis, num = pretty(label);
  const head = (title) => `<nav class="crumbs"><a href="${esc(path0)}">${esc(a.name)}${a.abbreviation ? ` (${esc(a.abbreviation)})` : ""}</a> › <a href="${esc(path)}">${esc(num)} ${unit[0]}</a></nav>
<h1>${esc(num)} ${unit[0]}${title ? ". " + esc(title) : ""}</h1>`;
  const o = env.HISTORY && await env.HISTORY.get(`v1/${a.key}/h/${label}.json`);
  const tl = o ? await o.json() : null;
  if (!tl || !tl.periods.length) return html(200, page(shell, `${a.cite} ${num} ${unit[2]} – ankstesnės redakcijos | Atviri teisės aktai`,
    `${head("")}<div class="box box-unknown"><strong>Ankstesnių šio ${unit[1]} redakcijų atviruose duomenyse nėra</strong> (Seimo kanceliarijos suvestinės redakcijos nuo 2020 m.). Jas rasite <a href="${esc(a.official_url)}">e-tar.lt ↗</a>.</div>
<p><a href="${esc(path)}">Šiandien galiojantis tekstas →</a></p>`));
  const latestTitle = tl.periods[tl.periods.length - 1].title;
  const raw = url.searchParams.get("data");
  const date = raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null;
  if (date && date >= today) return Response.redirect(new URL(path, url).toString(), 302);  // today or later: the page itself
  if (!date) return html(200, page(shell, `${a.cite} ${num} ${unit[2]} – ankstesnės redakcijos | Atviri teisės aktai`,
    head(latestTitle) + `<p class="aka">Kaip šis ${unit[0]} buvo parašytas anksčiau: pasirinkite laikotarpį arba datą.</p>` + timelineHtml(tl, a, path, null, today)));
  const p = periodOn(tl, date);
  const title = `${a.cite} ${num} ${unit[2]}, redakcija ${date} | Atviri teisės aktai`;
  if (!p) {
    const before = tl.periods.filter((x) => x.to < date).pop(), after = tl.periods.find((x) => x.from > date);
    const near = [before && `ankstesnė – iki ${before.to}`, after && `vėlesnė – nuo ${after.from}`].filter(Boolean).join(", ");
    return html(200, page(shell, title, head(latestTitle) +
      `<div class="box box-unknown"><strong>Atviruose duomenyse nėra šio ${unit[1]} redakcijos, galiojusios ${date}.</strong>${near ? ` Artimiausios: ${near}.` : ""} Visas redakcijas rasite <a href="${esc(a.official_url)}">e-tar.lt ↗</a>.</div>` +
      timelineHtml(tl, a, path, { date }, today)));
  }
  const ao = await env.HISTORY.get(`v1/a/${p.hash}.json`);
  const art = ao && await ao.json();
  if (!art) throw new Error(`history object v1/a/${p.hash}.json is missing`);
  const variant = (art.variants || []).find((x) => (!x.from || x.from <= date) && (!x.to || date <= x.to));
  const text = (variant ? variant.text : art.text).map((t) => `<p>${esc(t)}</p>`).join("\n");
  const range = p.open_end ? `nuo ${p.from} (atvirų duomenų lentelė paskutinį kartą atnaujinta ${p.to})` : `${p.from} – ${p.to}`;
  return html(200, page(shell, title, head(art.title) +
    `<div class="strip"><span class="badge b-unknown">Redakcija, galiojusi ${date}</span> Šaltinis: Seimo kanceliarijos suvestinė redakcija; šio ${unit[1]} tekstas buvo toks ${range} · <a href="${esc(a.official_url)}">oficialus tekstas e-tar.lt ↗</a></div>
<div class="box box-unknown"><strong>Tai ne šiandien galiojantis tekstas.</strong> Šiandien galiojantis – <a href="${esc(path)}">${esc(num)} ${unit[0]}</a>.</div>
${changesHtml(tl, p)}
<div class="law">${text}</div>
${art.amended_by && art.amended_by.length ? `<div class="notes">Keitė: ${art.amended_by.map(esc).join(", ")}</div>` : ""}` +
    timelineHtml(tl, a, path, { from: p.from, date }, today)));
}
