// Progressive enhancement only: every word of law and every link is in the HTML without this file.
(function () {
  "use strict";
  var wide = window.matchMedia("(min-width: 1100px)");
  var nav = document.getElementById("nav");

  // 1. Remember a hidden sidebar on wide screens (on phones the menu starts closed anyway).
  try {
    if (nav && wide.matches && localStorage.getItem("navHidden") === "1") nav.checked = true;
    if (nav) nav.addEventListener("change", function () {
      if (wide.matches) localStorage.setItem("navHidden", nav.checked ? "1" : "0");
    });
  } catch (e) { /* storage unavailable: just don't remember */ }

  // 2. "Kopijuoti citatą" on article pages.
  var main = document.querySelector("main[data-cite]");
  if (main && navigator.clipboard) {
    var h1 = main.querySelector("h1");
    var b = document.createElement("button");
    b.type = "button"; b.className = "cite"; b.textContent = "Kopijuoti citatą";
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(main.getAttribute("data-cite") + " " + location.href.split("#")[0]).then(function () {
        b.textContent = "Nukopijuota ✓"; setTimeout(function () { b.textContent = "Kopijuoti citatą"; }, 1800);
      });
    });
    if (h1) h1.insertAdjacentElement("afterend", b);
  }

  // 3. A page copied, cached or left behind by a stopped build: say so when its status day is old (builds come at least every
  //    second day, D-050, so more than 2 days means something stopped).
  try {
    var day = document.body.getAttribute("data-day");
    var today = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Vilnius" });
    if (day && (Date.parse(today) - Date.parse(day)) / 864e5 > 2 && !document.querySelector(".box-stale")) {
      var w = document.createElement("div"); w.className = "box box-stale"; w.setAttribute("role", "alert");
      w.innerHTML = "<strong>Šio puslapio žymos nustatytos " + day + ".</strong> Nuo tada tekstas galėjo pasikeisti – tikrinkite <a href=\"https://www.e-tar.lt\">e-tar.lt</a>.";
      var m = document.querySelector("main"); if (m) m.insertBefore(w, m.firstChild);
    }
  } catch (e) { /* no Intl time zones: skip */ }

  // 4. The label's own end date has come (labels are computed at night, a build is due that night (D-050) but comes hours
  //    after midnight, when laws change).
  try {
    var mm = document.querySelector("main[data-changes-on]");
    var now = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Vilnius" });
    if (mm && now >= mm.getAttribute("data-changes-on")) {
      var on = mm.getAttribute("data-changes-on"), st = mm.getAttribute("data-state");
      var msg = st === "pending" ? "Nuo " + on + " žemiau pateiktas tekstas jau taikomas."
              : st === "current" ? "Nuo " + on + " taikomas naujas tekstas – žr. skyrių „Nuo " + on + " bus taip“."
              : "Nuo " + on + " šio puslapio žyma nebegalioja.";
      var n = document.createElement("div"); n.className = "box box-unknown"; n.setAttribute("role", "status");
      n.innerHTML = "<strong>" + msg + "</strong> Šio puslapio žymos dar neatnaujintos; tikrinkite <a href=\"https://www.e-tar.lt\">e-tar.lt</a>.";
      var badge = mm.querySelector(".strip .badge"); if (badge) { badge.className = "badge b-unknown"; badge.textContent = "Keitėsi " + on; }
      mm.insertBefore(n, mm.querySelector(".strip") ? mm.querySelector(".strip").nextSibling : mm.firstChild);
    }
  } catch (e) { /* no Intl time zones: skip */ }

  // 4a. An article's references both ways, read when opened (none in the HTML: 80,000 pages stay light; D-049).
  var rel = document.querySelector("details.rel");
  if (rel) {
    rel.hidden = !rel.dataset.relN;
    rel.addEventListener("toggle", function () {
      if (!rel.open || rel.dataset.done) return;
      rel.dataset.done = "1";
      var div = rel.querySelector("div"), say = function (t) { var p = document.createElement("p"); p.className = "aka"; p.textContent = t; div.appendChild(p); };
      say("Ieškoma…");
      fetch("/api/related?limit=40&act=" + encodeURIComponent(rel.dataset.relAct) + "&n=" + encodeURIComponent(rel.dataset.relN)).then(function (r) {
        if (!r.ok) throw new Error("status " + r.status);
        return r.json();
      }).then(function (d) {
        div.textContent = "";
        var c = d.counts || {}, group = function (title, list, total) {
          if (!list || !list.length) return;
          var h = document.createElement("p"), ul = document.createElement("ul");
          h.innerHTML = "<strong></strong>"; h.firstChild.textContent = title + " (" + total + ")";
          list.forEach(function (x) {
            var li = document.createElement("li"), a = document.createElement("a");
            a.href = x.url; a.textContent = x.title && x.kind === "decision" ? x.title : (x.cite || "") + " " + (x.number || x.label || "") + (x.title ? ". " + x.title : "");
            li.appendChild(a);
            ul.appendChild(li);
          });
          div.appendChild(h); div.appendChild(ul);
          if (total > list.length) say("Rodoma " + list.length + " iš " + total + ".");
        };
        group("Mini kiti teisės aktai", d.cited_by_other_acts, c.cited_by_other_acts);
        group("Mini reguliuotojo sprendimai", d.cited_by_regulator_decisions, c.cited_by_regulator_decisions);
        group("Mini kiti šio akto straipsniai", d.cited_by_same_act, c.cited_by_same_act);
        group("Šis tekstas mini", d.cites, c.cites);
        if (!div.children.length) say("Nuorodų neradome.");
        say("Pagal teisės aktų tekstuose esančias nuorodas į šiame puslapyje esančius aktus; kitaip suformuluotų nuorodų sąraše nėra.");
      }).catch(function () { div.textContent = ""; say("Nepavyko įkelti. Bandykite vėliau."); });
    });
  }

  // 4b. A page that isn't there: what its address may have meant. "/DK/52/", "/darbo-kodeksas/52" go straight to the
  // article; otherwise up to three suggestions from the site's search.
  var nf = document.getElementById("nf-suggest");
  if (nf) {
    var said = decodeURIComponent(location.pathname).split("/").filter(function (x) { return x && !/^(ta|es|str|p|priedas)$/.test(x); }).join(" ").replace(/-/g, " ");
    if (said) fetch("/api/search?limit=3&q=" + encodeURIComponent(said)).then(function (r) { return r.ok ? r.json() : {}; }).then(function (d) {
      var rs = (d.results || []).filter(function (x) { return x.url && new URL(x.url).origin === location.origin; });
      if (!rs.length) return;
      var n = said.match(/ (\d[\d.-]*)$/);
      if (n && rs[0].label === n[1]) { location.replace(rs[0].url); return; }
      var ul = nf.querySelector("ul");
      rs.forEach(function (x) {
        var li = document.createElement("li"), a = document.createElement("a");
        a.href = x.url; a.textContent = (x.cite || x.act_name || "") + " " + (x.number || "") + (x.title ? ". " + x.title : "");
        li.appendChild(a); ul.appendChild(li);
      });
      nf.hidden = false;
    }).catch(function () {});
  }

  // 5. Search page: client-side search over the article index (numbers, titles, abbreviations).
  var box = document.getElementById("search-results");
  if (!box) return;
  var fold = function (s) {
    return s.toLowerCase().replace(/[ąčęėįšųūž]/g, function (c) { return "aceeisuuz"["ąčęėįšųūž".indexOf(c)]; });
  };
  var q = new URLSearchParams(location.search).get("q") || "";
  document.querySelectorAll("input[name=q]").forEach(function (i) { i.value = q; });  // the page's box and the sidebar's
  if (!q.trim()) return;
  box.textContent = "Ieškoma…";
  // first the site's search service (/api/search: ranked by titles and act names, the same as for AI assistants);
  // if it isn't there (a copy of the site, an outage), slow, or finds nothing: the search in this page below
  var ctl = window.AbortController ? new AbortController() : null;
  var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 4000);
  fetch("/api/search?limit=30&q=" + encodeURIComponent(q), ctl ? { signal: ctl.signal } : {}).then(function (r) {
    clearTimeout(timer);
    if (!r.ok) throw new Error("status " + r.status);
    return r.json();
  }).then(function (d) {
    if (!d || !d.results || !d.results.length) throw new Error("nothing");
    showApi(d);
  }).catch(function () { clearTimeout(timer); localSearch(); });
  function showApi(d) {
    box.textContent = "";
    var p = document.createElement("p"); p.className = "aka";
    p.textContent = "Rasta: " + d.results.length + (d.more ? " (yra daugiau – patikslinkite, pvz. pridėkite akto santrumpą)" : "");
    box.appendChild(p);
    var ul = document.createElement("ul"); ul.className = "toc";
    d.results.forEach(function (r) {
      var li = document.createElement("li"), link = document.createElement("a");
      link.href = r.url; link.textContent = (r.cite || "") + " " + r.number + " " + (/\/p\//.test(r.url) ? "p." : "str.");
      li.appendChild(link); li.appendChild(document.createTextNode(" " + (r.title || "") + " – " + (r.act_name || "")));
      if (r.status_label && r.status_label !== "Galioja šiandien") {  // never show a result without its status
        var st = document.createElement("span"); st.className = "badge b-unknown"; st.textContent = r.status_label;
        li.appendChild(document.createTextNode(" ")); li.appendChild(st);
      }
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }
  function localSearch() {
  fetch(box.getAttribute("data-index")).then(function (r) { return r.json(); }).then(function (idx) {
    q = q.replace(/(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)/g, function (m, d, s) {  // "52¹" -> "52-1"
      return d + "-" + s.split("").map(function (c) { return "⁰¹²³⁴⁵⁶⁷⁸⁹".indexOf(c); }).join("");
    });
    var words = fold(q).replace(/\bstr\.?\b|\bstraipsni\w*|\bp\.(?=\s|$)|\bpunkt\w*/g, " ").split(/\s+/).filter(Boolean);
    var acts = {}; idx.acts.forEach(function (a, i) { acts[i] = a; });
    var hits = [];
    idx.items.forEach(function (it) {
      var a = acts[it[0]], label = it[1], hay = fold(a[0] + " " + a[1] + " " + label + " " + it[2]);
      var score = 0, ok = words.every(function (w) {
        if (a[0] && w === fold(a[0])) { score += 5; return true; }          // abbreviation: "dk"
        if (w === label || w === label.replace("-", "")) { score += 10; return true; } // "52", "6.228-1"
        if (/^\d/.test(w)) {                                   // a number: only that article (and 52-1, 52-2 …)
          if (label.indexOf(w + "-") === 0) { score += 4; return true; }
          return false;
        }
        if (hay.indexOf(w) >= 0) { score += 1; return true; }
        return false;
      });
      if (ok) hits.push([score, it, a]);
    });
    hits.sort(function (x, y) { return y[0] - x[0]; });
    // full text: every ordinary word (4+ letters) must occur in the article; act abbreviations narrow the acts
    var abbrs = {}; idx.acts.forEach(function (a, i) { if (a[0]) abbrs[fold(a[0])] = i; });
    var only = words.filter(function (w) { return w in abbrs; }).map(function (w) { return abbrs[w]; });
    // the build's stem (fulltext.stem): 6 letters, or a short word without its ending; common stems are skipped
    var stemOf = function (w) { return w.slice(0, Math.min(6, Math.max(4, w.length - 2))); };
    var common = {}; ((idx.fulltext || {}).common || []).forEach(function (c) { common[c] = 1; });
    var terms = words.filter(function (w) { return !(w in abbrs) && /^[a-z]{4,}$/.test(w) && !common[stemOf(w)]; });
    var hasNumber = words.some(function (w) { return /^\d/.test(w); });
    var ft = idx.fulltext;
    var more = (!ft || !terms.length || hasNumber) ? Promise.resolve([]) : Promise.all(terms.map(function (w) {
      var stem = stemOf(w);
      return fetch(ft.path + stem.slice(0, 2) + ".json").then(function (r) { return r.ok ? r.json() : {}; })
        .then(function (shard) {
          var ids = {};
          Object.keys(shard).forEach(function (k) {
            if (k === stem || (stem.length < ft.stem && k.indexOf(stem) === 0)) shard[k].forEach(function (i) { ids[i] = 1; });
          });
          return ids;
        });
    })).then(function (sets) {
      var first = sets[0], out = [];
      Object.keys(first).forEach(function (i) {
        if (sets.every(function (s) { return s[i]; })) out.push(+i);
      });
      return out;
    });
    more.then(function (ids) {
      var seen = {}; hits.forEach(function (h) { seen[h[1][3]] = 1; });
      var text = [];
      ids.forEach(function (i) {
        var it = idx.items[i];
        if (!it || seen[it[3]] || (only.length && only.indexOf(it[0]) < 0)) return;
        // rank: how many query stems also begin a word of the title ("kasmetinių atostogų" for "kasmetinės atostogos")
        var tw = fold(it[2] || "").split(/[^a-z]+/);
        var score = terms.filter(function (w) { var st = stemOf(w); return tw.some(function (x) { return x.indexOf(st) === 0; }); }).length;
        text.push([score, it, acts[it[0]], "text"]);
      });
      text.sort(function (x, y) { return y[0] - x[0]; });  // stable: equal scores keep the act's order
      show(hits.concat(text));
    });
  }).catch(function () { box.textContent = "Paieškos indeksas nepasiekiamas."; });
  }
  function show(hits) {
    box.textContent = "";
    var p = document.createElement("p"); p.className = "aka";
    var inText = hits.filter(function (h) { return h[3] === "text"; }).length;
    p.textContent = hits.length ? "Rasta: " + hits.length + (inText ? " (iš jų tekste: " + inText + ")" : "") + (hits.length > 50 ? "; rodomi 50" : "") : "Nieko nerasta.";
    box.appendChild(p);
    var ul = document.createElement("ul"); ul.className = "toc";
    hits.slice(0, 50).forEach(function (h) {
      var li = document.createElement("li"), link = document.createElement("a");
      link.href = h[1][3]; link.textContent = (h[2][3] || h[2][0]) + " " + h[1][4] + (h[1][1].indexOf("priedas") === 0 ? "" : " " + (h[2][2] || "str."));  // "6 priedas"
      li.appendChild(link); li.appendChild(document.createTextNode(" " + h[1][2] + " – " + h[2][1]));
      if (h[1][5] && h[1][5] !== "Galioja šiandien") {  // never show a result without its status
        var st = document.createElement("span"); st.className = "badge b-unknown"; st.textContent = h[1][5];
        li.appendChild(document.createTextNode(" ")); li.appendChild(st);
      }
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }
})();
