"use strict";

// Builds the charts and tables from the CSV files the analysis writes to output/.
(() => {
  const root = document.documentElement;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const SVGNS = "http://www.w3.org/2000/svg";
  const STORE_KEY = "mbs-mode";
  const TOP_N = 10;
  // The README names these players as the clearest cases of each pattern.
  const README_IGNORED = ["Kalif Raymond", "Cole Beasley", "Adam Humphries", "Ezekiel Elliott"];
  const README_FED = ["Travis Kelce", "Kyle Pitts", "Ja'Marr Chase"];
  const MINUS = "\u2212";

  const $ = (s, c = document) => c.querySelector(s);
  const $$ = (s, c = document) => Array.from(c.querySelectorAll(s));
  const motionOK = () => !reduceMotion.matches;
  const mode = () => (root.dataset.mode === "article" ? "article" : "game");
  const pct = (v, d = 1) => (v * 100).toFixed(d) + "%";
  const yd = (v) => {
    const s = Math.abs(v).toFixed(2);
    return s === "0.00" ? s : (v > 0 ? "+" : MINUS) + s;
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const lastName = (n) => n.split(" ").slice(1).join(" ") || n;
  const lin = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  const median = (vals) => {
    const s = [...vals].sort((a, b) => a - b);
    const m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  const pearson = (xs, ys) => {
    const n = xs.length, mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
    let sxy = 0, sxx = 0, syy = 0;
    for (let i = 0; i < n; i++) {
      sxy += (xs[i] - mx) * (ys[i] - my);
      sxx += (xs[i] - mx) ** 2;
      syy += (ys[i] - my) ** 2;
    }
    return sxy / Math.sqrt(sxx * syy);
  };

  function parseCSV(text) {
    const rows = [];
    let row = [], field = "", quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (c === '"') quoted = false;
        else field += c;
      } else if (c === '"') quoted = true;
      else if (c === ",") { row.push(field); field = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(field); rows.push(row); row = []; field = "";
      } else field += c;
    }
    if (field || row.length) { row.push(field); rows.push(row); }
    const head = rows.shift() || [];
    return rows.filter((r) => r.length === head.length).map((r) => Object.fromEntries(head.map((h, j) => [h, r[j]])));
  }

  async function fetchCSV(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return parseCSV(await res.text());
  }

  const setState = (source, state) => $$(`[data-source="${source}"]`).forEach((b) => { b.dataset.state = state; });

  function svg(tag, attrs, parent) {
    const n = document.createElementNS(SVGNS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function label(parent, x, y, str, attrs = {}) {
    const t = svg("text", { x, y, ...attrs }, parent);
    t.textContent = str;
    return t;
  }
  function textBlock(parent, x, y, rows, attrs, lh) {
    const t = svg("text", { x, y, ...attrs }, parent);
    rows.forEach((r, i) => {
      const s = svg("tspan", { x, dy: i ? lh : 0 }, t);
      if (r.sub) s.setAttribute("class", "sub");
      s.textContent = r.text;
    });
    return t;
  }

  // Charts redraw when their container changes width, and after a mode switch (new fonts, new sizes).
  const charts = [];
  const ro = "ResizeObserver" in window ? new ResizeObserver((entries) => {
    entries.forEach((e) => {
      const c = charts.find((x) => x.el === e.target);
      const w = Math.round(e.contentRect.width);
      if (c && w && w !== c.w) { c.w = w; requestAnimationFrame(c.draw); }
    });
  }) : null;
  function chart(el, draw) {
    charts.push({ el, draw, w: 0 });
    if (ro) ro.observe(el);
    else window.addEventListener("resize", draw);
    draw();
  }
  const redrawAll = () => charts.forEach((c) => c.draw());

  // Mode toggle
  function syncToggle() {
    const input = document.getElementById("mode-" + mode());
    if (input) input.checked = true;
  }

  function anchorPoint() {
    const header = $(".masthead");
    const line = header ? Math.max(0, header.getBoundingClientRect().bottom) : 0;
    const n = $$("main h1, main h2, main h3, main p, main li, main tr, main figure, main pre")
      .find((el) => el.getClientRects().length && el.getBoundingClientRect().bottom > line + 4);
    return n ? { n, top: n.getBoundingClientRect().top } : null;
  }

  function fontsFor(m) {
    if (!document.fonts || !document.fonts.load) return Promise.resolve();
    const specs = m === "article" ? ['600 16px "Newsreader"', '400 16px "Newsreader"'] : ['800 16px "Barlow Condensed"', '600 16px "Barlow Condensed"'];
    const loaded = Promise.all(specs.map((s) => document.fonts.load(s))).catch(() => {});
    return Promise.race([loaded, new Promise((r) => setTimeout(r, 700))]);
  }

  let switching = false;
  async function switchMode(next) {
    if (switching) return;
    if (next === mode()) { syncToggle(); return; }
    switching = true;
    const anchor = anchorPoint();
    const wipe = $(".wipe");
    const animate = motionOK() && wipe && typeof wipe.animate === "function";
    const timing = { duration: 260, easing: "cubic-bezier(0.7, 0, 0.3, 1)", fill: "forwards" };
    if (animate) {
      wipe.dataset.to = next;
      wipe.style.transformOrigin = "left center";
      await wipe.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], timing).finished;
    }
    root.dataset.mode = next;
    try { localStorage.setItem(STORE_KEY, next); } catch (e) { /* Storage blocked: the choice lasts for this visit only. */ }
    syncToggle();
    await fontsFor(next);
    redrawAll();
    if (anchor) {
      // Keep the reader on the same paragraph; the new layout has different heights.
      root.style.scrollBehavior = "auto";
      window.scrollBy(0, anchor.n.getBoundingClientRect().top - anchor.top);
      root.style.scrollBehavior = "";
    }
    if (animate) {
      wipe.style.transformOrigin = "right center";
      await wipe.animate([{ transform: "scaleX(1)" }, { transform: "scaleX(0)" }], timing).finished;
      wipe.getAnimations().forEach((a) => a.cancel());
      wipe.style.transformOrigin = "";
    }
    switching = false;
    const picked = $('input[name="mode"]:checked');
    if (picked && picked.value !== mode()) switchMode(picked.value);
  }

  function initToggle() {
    syncToggle();
    $$('input[name="mode"]').forEach((input) => {
      input.addEventListener("change", () => { if (input.checked) switchMode(input.value); });
    });
  }

  // Header score bug: shows the section in the middle of the screen.
  function initBug() {
    const q = $("[data-bug-q]"), t = $("[data-bug-t]");
    if (!q || !t || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { q.textContent = e.target.dataset.q; t.textContent = e.target.dataset.t; }
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    $$("main > section[data-q]").forEach((s) => io.observe(s));
  }

  // Separation payoff: two small line charts drawn from the table in the page.
  function initPayoff() {
    const rows = $$("#payoff-data tbody tr").map((tr) => {
      const v = $$("td", tr).map((td) => parseFloat(td.textContent));
      return { tick: tr.querySelector("th").dataset.tick, manT: v[0], zoneT: v[1], manC: v[2], zoneC: v[3] };
    });
    if (rows.length !== 6 || rows.some((r) => [r.manT, r.zoneT, r.manC, r.zoneC].some((x) => !Number.isFinite(x)))) return;
    const target = $("#payoff-target"), caught = $("#payoff-caught");
    chart(target, () => linePanel(target, rows, "manT", "zoneT", {
      max: 40, ticks: [0, 10, 20, 30, 40], callouts: [0, 4],
      aria: `Line chart. Against man coverage, wide receivers and tight ends are targeted on ${rows[0].manT}% of routes with under 1 yard of separation, rising to ${rows[4].manT}% at 4 to 6 yards. Against zone, ${rows[0].zoneT}% rising to ${rows[5].zoneT}% at 6 yards or more.`,
    }));
    chart(caught, () => linePanel(caught, rows, "manC", "zoneC", {
      max: 100, ticks: [0, 25, 50, 75, 100], callouts: [0, 3],
      aria: `Line chart. Against man coverage, ${rows[0].manC}% of passes to wide receivers and tight ends with under 1 yard of separation are caught, rising to ${rows[3].manC}% at 3 to 4 yards and ${rows[5].manC}% at 6 yards or more. Against zone, ${rows[0].zoneC}% rising to ${rows[5].zoneC}%.`,
    }));
  }

  function linePanel(el, rows, kMan, kZone, o) {
    const w = el.clientWidth;
    if (!w) return;
    const h = Math.round(Math.min(280, Math.max(200, w * 0.66)));
    const m = { t: 22, r: 44, b: 26, l: 38 };
    const x = (i) => m.l + (i * (w - m.l - m.r)) / (rows.length - 1);
    const y = lin(0, o.max, h - m.b, m.t);
    el.replaceChildren();
    const s = svg("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": o.aria }, el);
    const g = svg("g", { class: "grid" }, s);
    o.ticks.forEach((t) => {
      svg("line", { x1: m.l, x2: w - m.r, y1: y(t), y2: y(t) }, g);
      label(s, m.l - 6, y(t) + 4, t + "%", { class: "tick", "text-anchor": "end" });
    });
    rows.forEach((r, i) => label(s, x(i), h - 6, r.tick, { class: "tick", "text-anchor": "middle" }));
    const ends = {};
    [["zone", kZone], ["man", kMan]].forEach(([cls, k]) => {
      const pts = rows.map((r, i) => [x(i), y(r[k])]);
      svg("polyline", { class: `series series--${cls}`, points: pts.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" ") }, s);
      pts.forEach(([cx, cy]) => svg("circle", { class: `pt pt--${cls}`, cx, cy, r: 3.5 }, s));
      const last = pts[pts.length - 1];
      ends[cls] = { x: last[0] + 8, y: last[1] + 4 };
    });
    // Push the two end labels apart when the lines finish close together.
    const overlap = 13 - Math.abs(ends.man.y - ends.zone.y);
    if (overlap > 0) {
      const [hi, lo] = ends.man.y <= ends.zone.y ? [ends.man, ends.zone] : [ends.zone, ends.man];
      hi.y -= overlap / 2;
      lo.y += overlap / 2;
    }
    label(s, ends.man.x, ends.man.y, "Man", { class: "series-label series-label--man" });
    label(s, ends.zone.x, ends.zone.y, "Zone", { class: "series-label series-label--zone" });
    o.callouts.forEach((i) => {
      const v = rows[i][kMan], other = rows[i][kZone];
      label(s, x(i), y(v) + (other > v ? 20 : -10), Math.round(v) + "%", { class: "callout", "text-anchor": i === 0 ? "start" : "middle" });
    });
  }

  // Leaderboard
  function initBoard(players) {
    const table = $("#board-table"), body = $("tbody", table), more = $("#board-more");
    const count = $("#board-count"), empty = $("#board-empty");
    const ranked = [...players].sort((a, b) => b.score - a.score);
    ranked.forEach((p, i) => { p.rank = i + 1; });
    const D = 1.5;
    const at = (v) => (((Math.max(-D, Math.min(D, v)) + D) / (2 * D)) * 100).toFixed(2) + "%";
    let pos = "All", showAll = false;
    const noun = () => (pos === "All" ? "players" : pos + "s");

    function row(p) {
      const lo = p.score - 1.96 * p.se, hi = p.score + 1.96 * p.se;
      const tr = document.createElement("tr");
      if (p.ignored) tr.className = "is-ignored";
      tr.innerHTML =
        `<td class="b-rank">${p.rank}</td>` +
        `<th scope="row" class="b-player"><span class="b-name">${esc(p.name)}</span>` +
        `<span class="b-meta">${esc(p.pos)} · ${p.routes} routes<span class="b-meta-target"> · targeted ${pct(p.target)}</span></span>` +
        (p.ignored ? `<span class="tag">Open but ignored</span>` : "") + `</th>` +
        `<td class="b-score"><div class="cell-score"><span class="track" aria-hidden="true">` +
        `<span class="tick" style="left:${at(-1)}"></span><span class="tick" style="left:${at(1)}"></span>` +
        `<span class="ci" style="left:${at(lo)};width:calc(${at(hi)} - ${at(lo)})"></span>` +
        `<span class="dot" style="left:${at(p.score)}"></span></span>` +
        `<span class="num">${yd(p.score)}<span class="sr-only"> yards, 95% interval ${yd(lo)} to ${yd(hi)}</span></span></div></td>` +
        `<td class="b-target">${pct(p.target)}</td>`;
      return tr;
    }

    function render() {
      const list = ranked.filter((p) => pos === "All" || p.pos === pos);
      const shown = showAll ? list : list.slice(0, TOP_N);
      body.replaceChildren(...shown.map(row));
      table.hidden = list.length === 0;
      empty.hidden = list.length > 0;
      more.hidden = list.length <= TOP_N;
      more.textContent = showAll ? `Show the top ${TOP_N} only` : `Show all ${list.length} ${noun()}`;
      more.setAttribute("aria-expanded", String(showAll));
      count.textContent = list.length ? `Showing ${shown.length} of ${list.length} ${noun()}, highest score first.` : "";
    }

    $$('input[name="pos"]').forEach((input) => {
      input.addEventListener("change", () => { if (input.checked) { pos = input.value; render(); } });
    });
    more.addEventListener("click", () => {
      showAll = !showAll;
      render();
      if (!showAll) more.scrollIntoView({ block: "nearest" });
    });
    render();

    // Game mode: marks slide out from the expected line the first time the table is on screen.
    if (mode() === "game" && motionOK() && "IntersectionObserver" in window) {
      const io = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) { table.classList.add("is-revealed"); io.disconnect(); }
      }, { threshold: 0.2 });
      io.observe(table);
    } else {
      table.classList.add("is-revealed");
    }
  }

  async function loadScores() {
    setState("scores", "loading");
    try {
      const rows = await fetchCSV("site/data/man_beater_scores.csv");
      const players = rows.map((r) => ({
        id: r.nflId, name: r.displayName, pos: r.pos, routes: Math.round(+r.routes_man),
        score: +r.man_beater, se: +r.soe_se_man, target: +r.target_rate_man,
      })).filter((p) => p.name && Number.isFinite(p.score) && Number.isFinite(p.target));
      if (!players.length) { setState("scores", "empty"); return; }
      const mid = median(players.map((p) => p.target));
      players.forEach((p) => { p.ignored = p.score > 0 && p.target < mid; });
      setState("scores", "ready");
      initBoard(players);
    } catch (e) {
      setState("scores", "error");
    }
  }

  // The scatter, the lower-third list and the fit chart aren't built yet, so their sections stay hidden.
  ["open-vs-fed", "open-but-ignored", "line-fit"].forEach((id) => {
    const s = document.getElementById(id);
    if (s) s.hidden = true;
  });
  $$('[data-retry="scores"]').forEach((b) => b.addEventListener("click", loadScores));
  initToggle();
  initBug();
  initPayoff();
  loadScores();
})();
