// Run the site's search (app.js) on a local build with a tiny fake DOM, no browser needed.
// Usage: node bin/check_search.js out/site "DK kasmetinės atostogos"
const fs = require("fs"), path = require("path");
const site = process.argv[2], q = process.argv[3];
function el(tag) { return { tag, children: [], textContent: "", className: "", href: "", attrs: {},
  appendChild(c) { this.children.push(c); return c; }, getAttribute(k) { return this.attrs[k]; },
  setAttribute(k, v) { this.attrs[k] = v; }, addEventListener() {}, querySelector() { return null; },
  querySelectorAll() { return []; }, classList: { add() {}, remove() {}, toggle() {} }, style: {} }; }
const box = el("div"); box.attrs["data-index"] = "http://x/search-index.json";
global.document = { getElementById: (id) => (id === "search-results" ? box : null), querySelector: () => null,
  querySelectorAll: () => [], createElement: el, createTextNode: (t) => ({ tag: "#text", textContent: t }),
  body: el("body"), documentElement: el("html"), addEventListener() {} };
global.matchMedia = () => ({ matches: true, addEventListener() {}, addListener() {} });
global.window = global; global.location = { search: "?q=" + encodeURIComponent(q), pathname: "/paieska/" };
global.localStorage = { getItem() { return null; }, setItem() {} }; global.navigator = { clipboard: null };
global.URLSearchParams = URLSearchParams;
global.fetch = (u) => { const p = path.join(site, u.replace(/^https?:\/\/[^/]+/, "")); const ok = fs.existsSync(p);
  return Promise.resolve({ ok, json: () => Promise.resolve(ok ? JSON.parse(fs.readFileSync(p, "utf8")) : {}) }); };
require(path.resolve(site, "app.js"));
setTimeout(() => {
  const text = (n) => (n.textContent || "") + (n.children || []).map(text).join("");
  console.log(text(box.children[0] || {}));
  const ul = box.children[1]; (ul ? ul.children.slice(0, 5) : []).forEach((li) => console.log("  " + text(li).slice(0, 90)));
}, 300);
