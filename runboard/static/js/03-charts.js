/* ================= chart ================= */
/* ================= charts ================= */
// Every chart is kept by its title, so hover and the large view work without redrawing the page. Small charts: the
// legend switches series, ⤢ or a click opens the large view. Large view: other charts of the page, wheel / drag /
// arrow keys to zoom and pan, smoothing, log scale, best points, values at the cursor and a CSV of what is shown.
const CHARTS = {}, HIDDEN = {};
let BIG = null;
const better = title => /loss/i.test(title) ? "min" : /learning rate|^lr$/i.test(title) ? null : "max";
const fmtv = v => v == null ? "—" : Math.abs(v) >= 100 ? v.toFixed(1) : Math.abs(v) >= 1 ? v.toFixed(2) : Math.abs(v) >= 0.01 ? v.toFixed(3) : v.toPrecision(3);
const ema = (pts, w) => { if (!w) return pts; let a = null; return pts.map(([x, y]) => [x, a = a === null ? y : a * w + y * (1 - w)]); };
function niceTicks(a, b, n) {
  const step0 = (b - a) / n, mag = 10 ** Math.floor(Math.log10(step0 || 1));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(st => st >= step0) || 10 * mag, out = [];
  for (let v = Math.ceil(a / step) * step; v <= b + step * 1e-6; v += step) out.push(+v.toFixed(8));
  return out;
}
function bestPoint(pts, how) {
  if (!how || !pts.length) return null;
  return pts.reduce((a, p) => (how === "max" ? p[1] > a[1] : p[1] < a[1]) ? p : a);
}
const PW = 640, PL = 44, PR = 12;  // plot box in viewBox units: width, left margin (y labels), right margin
let clipN = 0;
// logx: x on a log scale (sizes of data); dots: a ring on every point (few points); area: a light fill under a lone
// series; bestLabel: the best point's value written next to its ring (the small charts show it in their title instead)
function plot(id, series, {h = 180, range = null, smooth = 0, log = false, best = null, xticks = 0, endDot = true, logx = false, dots = false, area = false, bestLabel = true} = {}) {
  const W = PW, H = h, Lm = PL, R = PR, Tm = 10, B = 24;
  // smoothing runs over the whole series, so zooming never changes a value; a zoomed view keeps one point past each
  // edge so the lines run to the border (clipped there) and the axis is exactly the chosen range: moving is smooth
  const shown = series.map(s => {
    const all = ema(s.pts, smooth);
    if (!range) return {...s, raw: s.pts, pts: all, line: all, rawLine: s.pts};
    let i = s.pts.findIndex(p => p[0] >= range[0]); if (i < 0) i = s.pts.length;
    let j = s.pts.length - 1; while (j >= 0 && s.pts[j][0] > range[1]) j--;
    const a = Math.max(0, i - 1), b = Math.min(s.pts.length, j + 2);
    return {...s, raw: s.pts.slice(i, j + 1), pts: all.slice(i, j + 1), line: all.slice(a, b), rawLine: s.pts.slice(a, b)};
  }).filter(s => s.line.length);
  if (!shown.length) return `<div class="empty" style="padding:50px 0">${t("no_data")}</div>`;
  const xs = shown.flatMap(s => s.pts.map(p => p[0]));
  let [x0, x1] = range || [Math.min(...xs), Math.max(...xs)];
  if (x1 === x0) x1 = x0 + 1;
  const ys = shown.flatMap(s => (s.pts.length ? s.raw.concat(s.pts) : s.rawLine.concat(s.line)).map(p => p[1]));
  const lo = Math.min(...ys), hi = Math.max(...ys);
  log = log && lo > 0;
  const T = v => log ? Math.log10(v) : v, U = v => log ? 10 ** v : v;
  let t0 = T(lo), t1 = T(hi);
  const pad = (t1 - t0) * .08 || (log ? .1 : Math.abs(t0) * .05 || 1);
  t0 -= pad; t1 += pad;
  if (!log && t0 < 0 && lo >= 0) t0 = 0;  // a value that cannot be negative gets no negative axis
  logx = logx && x0 > 0 && !range;
  const LX = v => logx ? Math.log10(v) : v;
  const X = x => Lm + (LX(x) - LX(x0)) / (LX(x1) - LX(x0)) * (W - Lm - R), Y = y => Tm + (1 - (T(y) - t0) / (t1 - t0)) * (H - Tm - B);
  CHARTS[id].geom = {W, H, Lm, R, Tm, B, x0, x1, t0, t1, log, logx, series: shown};
  const clip = range ? `cl${++clipN}` : "";
  const pc = (v, of) => (v / of * 100).toFixed(2) + "%", line = (pts, color, extra = "") => `<polyline points="${pts.map(p => X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1)).join(" ")}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke" ${clip ? `clip-path="url(#${clip})"` : ""} ${extra}/>`;
  const nice = log ? [] : niceTicks(t0, t1, 4).filter(v => v >= t0 && v <= t1);  // round values, as people read an axis
  const yticks = nice.length >= 3 ? nice : [0, .25, .5, .75, 1].map(f => U(t0 + f * (t1 - t0)));
  const allx = [...new Set(xs)].sort((a, b) => a - b);
  const xt = logx ? allx.filter((_, i) => i % Math.ceil(allx.length / 8) === 0) : xticks ? niceTicks(x0, x1, xticks).filter(v => v >= x0 && v <= x1) : [x0, x1];
  const marks = best ? shown.map(s => { const b = bestPoint(s.raw, best); return b ? `<i class="bm" style="left:${pc(X(b[0]), W)};top:${pc(Y(b[1]), H)};border-color:${s.color}"></i>${bestLabel ? `<span class="bml" style="left:${pc(X(b[0]), W)};top:${pc(Y(b[1]), H)};color:${s.color}">${fmtv(b[1])} · ${b[0]}</span>` : ""}` : ""; }).join("") : "";
  const rings = dots && shown.reduce((a, s) => a + s.pts.length, 0) <= 60 ? shown.map(s => s.pts.map(p => `<i class="pd" style="left:${pc(X(p[0]), W)};top:${pc(Y(p[1]), H)};border-color:${s.color}"></i>`).join("")).join("") : "";
  const fill = area && shown.length === 1 && shown[0].line.length > 1 ? (s => `<polygon points="${s.line.map(p => X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1)).join(" ")} ${X(s.line.at(-1)[0]).toFixed(1)},${H - B} ${X(s.line[0][0]).toFixed(1)},${H - B}" fill="${s.color}" fill-opacity=".09" stroke="none" ${clip ? `clip-path="url(#${clip})"` : ""}/>`)(shown[0]) : "";
  const last = shown[0].pts.at(-1);
  // the plot stretches to the card; labels and markers sit on top as text so they never get squeezed
  return `<div class="cw"><svg class="c" style="height:${h}px" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">
    ${clip ? `<clipPath id="${clip}"><rect x="${Lm}" y="0" width="${W - Lm - R}" height="${H}"/></clipPath>` : ""}
    ${yticks.map(v => `<line x1="${Lm}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)" vector-effect="non-scaling-stroke"/>`).join("")}
    ${xticks || logx ? xt.map(v => `<line x1="${X(v)}" x2="${X(v)}" y1="${Tm}" y2="${H - B}" stroke="var(--line)" stroke-dasharray="2 4" vector-effect="non-scaling-stroke"/>`).join("") : ""}
    ${fill}${smooth ? shown.map(s => line(s.rawLine, s.color, 'opacity=".22"')).join("") : ""}
    ${shown.map(s => line(s.line, s.color, s.dash ? 'stroke-dasharray="5 4"' : "")).join("")}</svg>
    ${yticks.map(v => `<span class="yl" style="top:${pc(Y(v), H)};width:${pc(Lm - 6, W)}">${fmtv(v)}</span>`).join("")}
    ${xt.map((v, i) => `<span class="xl" style="left:${pc(X(v), W)};transform:translateX(${i === 0 && !xticks ? "0" : i === xt.length - 1 && !xticks ? "-100%" : "-50%"})">${+v.toFixed(2)}</span>`).join("")}
    ${rings}${marks}${endDot && last && !rings ? `<i class="dot" style="left:${pc(X(last[0]), W)};top:${pc(Y(last[1]), H)};background:${shown[0].color}"></i>` : ""}</div>`;
}
function chart(title, series, {h = 180, empty = true, xlabel = null, better: how, logx = false, dots = false} = {}) {
  const id = title;
  series = series.filter(s => s.pts.length);
  const prev = CHARTS[id];
  CHARTS[id] = {title, series, xlabel, better: how !== undefined ? how : better(title), geom: prev?.geom};
  if (BIG?.key === id && !BIG.dragging && series.reduce((a, x) => a + x.pts.length, 0) !== BIG.n) setTimeout(drawBig);  // live run: the large view follows
  if (!series.length) return empty ? `<div class="chart"><div class="t"><b>${esc(title)}</b></div><div class="empty" style="padding:50px 0">${t("no_data")}</div></div>` : "";
  const off = HIDDEN[id] || new Set(), vis = series.filter(x => !off.has(x.name));
  const bw = CHARTS[id].better, bp = bw && vis.length ? bestPoint(vis[0].pts, bw) : null;  // the best of the first series, in the title
  return `<div class="chart" data-chart="${esc(id)}"><div class="t"><b class="ct" data-open="${esc(id)}" tabindex="0" role="button">${esc(title)}</b>
    ${series.map(x => `<span class="lg ${off.has(x.name) ? "off" : ""}" data-lg="${esc(x.name)}" tabindex="0" role="switch" aria-checked="${!off.has(x.name)}" title="${esc(t("chart_toggle"))}"><i style="background:${x.color}${x.dash ? ";opacity:.6" : ""}"></i>${esc(x.name)}</span>`).join("")}
    ${bp && !dots ? `<span class="bst">${t("best_at")} <b>${fmtv(bp[1])}</b> · ${bp[0]}</span>` : ""}
    <button type="button" class="cx" data-open="${esc(id)}" title="${esc(t("chart_open"))}" aria-label="${esc(t("chart_open"))}">⤢</button></div>
    ${vis.length ? plot(id, vis, {h, logx, dots, area: !dots, best: dots ? null : bw, bestLabel: false}) : `<div class="empty" style="padding:${h / 2 - 10}px 0">—</div>`}</div>`;
}
function rerenderCharts() {
  if (route.view !== "project") return;
  if (route.tab === "overview") renderOverview();
  else if (["runs", "run"].includes(route.tab)) renderDetail();
  else if (route.tab === "results") renderResults();
}
function chartAt(cw, clientX) {  // the chart under the pointer and the nearest x it has data for
  const c = CHARTS[cw.closest("[data-chart]")?.dataset.chart], g = c?.geom; if (!g) return null;
  const r = cw.getBoundingClientRect(), fx = (clientX - r.left) / r.width * g.W, lx = v => g.logx ? Math.log10(v) : v;
  const xv = lx(g.x0) + (fx - g.Lm) / (g.W - g.Lm - g.R) * (lx(g.x1) - lx(g.x0));  // on the axis' own scale
  let at = null;
  for (const x of g.series) for (const p of x.pts) if (at === null || Math.abs(lx(p[0]) - xv) < Math.abs(lx(at) - xv)) at = p[0];
  const sx = x => r.left + ((g.Lm + (lx(x) - lx(g.x0)) / (lx(g.x1) - lx(g.x0)) * (g.W - g.Lm - g.R)) / g.W) * r.width;
  const sy = y => r.top + ((g.Tm + (1 - ((g.log ? Math.log10(y) : y) - g.t0) / (g.t1 - g.t0)) * (g.H - g.Tm - g.B)) / g.H) * r.height;
  return {c, g, r, xv, at, sx, sy};
}
const floater = (id, cls) => {
  let el = document.getElementById(id);
  if (!el) { el = document.createElement("div"); el.id = id; el.className = cls; el.hidden = true; }
  // an open modal dialog sits above everything in the page: in the large view the values must live inside it
  const host = document.querySelector("#chartdlg[open]") || document.body;
  if (el.parentNode !== host) host.append(el);
  return el;
};
function hideHover() { document.querySelectorAll(".ctip, .cguide, .cpt").forEach(el => el.hidden = true); }
document.addEventListener("pointermove", e => { if (e.pointerType !== "touch") hoverAt(e.target.closest?.(".chart .cw"), e); });
document.addEventListener("pointerdown", e => { if (e.pointerType === "touch" && !e.target.closest?.(".chart .cw")) hideHover(); });
function hoverAt(cw, e) {
  const a = cw && chartAt(cw, e.clientX);
  if (!a || a.at === null || BIG?.dragging) return hideHover();
  const rows = a.g.series.map(x => [x, x.pts.find(p => p[0] === a.at), x.raw?.find(p => p[0] === a.at)]).filter(r => r[1]);
  const ref = rows[0]?.[2] || rows[0]?.[1];
  const tip = floater("ctip", "ctip"), guide = floater("cguide", "cguide");
  tip.innerHTML = `<b>${esc(a.c.xlabel || t("epoch"))} ${a.at}</b>` + rows.map(([x, p, raw], i) => {
    const v = (raw || p)[1], d = i && ref ? v - ref[1] : null;
    return `<div><i style="background:${x.color}"></i>${esc(x.name)}<span>${fmtv(v)}${d !== null ? ` <em class="${d >= 0 ? "up" : "down"}">${d >= 0 ? "+" : ""}${fmtv(d)}</em>` : ""}</span></div>`;
  }).join("");
  rows.forEach(([x, p], i) => { const dot = floater(`cpt${i}`, "cpt"); Object.assign(dot.style, {left: a.sx(p[0]) + "px", top: a.sy(p[1]) + "px", borderColor: x.color}); dot.hidden = false; });
  for (let i = rows.length; document.getElementById(`cpt${i}`); i++) document.getElementById(`cpt${i}`).hidden = true;
  Object.assign(guide.style, {left: a.sx(a.at) + "px", top: a.r.top + "px", height: a.r.height + "px"});
  tip.hidden = guide.hidden = false;
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  if (e.pointerType && e.pointerType !== "mouse") {  // a finger covers what is under it: the values go above it
    tip.style.left = Math.max(8, Math.min(innerWidth - tw - 8, e.clientX - tw / 2)) + "px";
    tip.style.top = (e.clientY - th - 40 >= 8 ? e.clientY - th - 40 : Math.min(innerHeight - th - 8, e.clientY + 40)) + "px";
  } else {
    tip.style.left = (e.clientX + 16 + tw > innerWidth ? e.clientX - tw - 16 : e.clientX + 16) + "px";
    tip.style.top = Math.max(8, Math.min(innerHeight - th - 8, e.clientY - th / 2)) + "px";
  }
  if (cw.closest("#chartdlg")) {  // the table under the large view follows the cursor
    $("#bcurh") && ($("#bcurh").textContent = `${a.c.xlabel || t("epoch")} ${a.at}`);
    BIG.cursor = a.at;
    document.querySelectorAll("#chartdlg [data-bc]").forEach(td => {
      const x = a.g.series.find(z => z.name === td.dataset.bc), raw = x?.raw.find(p => p[0] === a.at);
      td.textContent = raw ? fmtv(raw[1]) : "—";
      const dd = document.querySelector(`#chartdlg [data-bd="${CSS.escape(td.dataset.bc)}"]`);
      if (dd) { const d = raw && ref && x !== rows[0]?.[0] ? raw[1] - ref[1] : null; dd.textContent = d === null ? "—" : (d >= 0 ? "+" : "") + fmtv(d); dd.className = "n " + (d === null ? "" : d >= 0 ? "up" : "down"); }
    });
  }
}
document.addEventListener("scroll", hideHover, true);
document.addEventListener("click", e => {
  const lg = e.target.closest?.(".chart .lg");
  if (lg && !lg.closest("#chartdlg")) {  // legend: switch a series off and on in this chart
    const key = lg.closest("[data-chart]").dataset.chart, set = HIDDEN[key] ??= new Set();
    set.has(lg.dataset.lg) ? set.delete(lg.dataset.lg) : set.add(lg.dataset.lg);
    hideHover(); rerenderCharts(); return;
  }
  const opener = e.target.closest?.("[data-open]") || (e.target.closest?.(".chart .cw") && !e.target.closest("#chartdlg") ? e.target.closest(".chart") : null);
  if (!opener) return;
  const key = opener.dataset.open || opener.dataset.chart;
  if (CHARTS[key]?.series.length) openBig(key);
});
function openBig(key) {
  BIG = {key, hidden: new Set(HIDDEN[key] || []), range: null, smooth: +(store("rb-smooth") || 0), log: false, best: true};
  let dlg = $("#chartdlg");
  if (!dlg) {
    dlg = document.createElement("dialog"); dlg.id = "chartdlg"; dlg.className = "form-dlg big-chart"; document.body.append(dlg);
    dlg.onclose = () => { BIG = null; hideHover(); };
    dlg.addEventListener("keydown", bigKeys);
  }
  hideHover(); drawBig(); dlg.showModal();
}
function fullExtent(c) { const xs = c.series.flatMap(x => x.pts.map(p => p[0])); return [Math.min(...xs), Math.max(...xs)]; }
function minSpan(c) {  // the narrowest view: three steps between points
  const xs = [...new Set(c.series.flatMap(x => x.pts.map(p => p[0])))].sort((a, b) => a - b), [a, b] = fullExtent(c);
  let gap = Infinity; for (let i = 1; i < xs.length; i++) gap = Math.min(gap, xs[i] - xs[i - 1]);
  return Math.min(b - a, isFinite(gap) ? gap * 3 : (b - a) / 50) || 1;
}
const curRange = () => BIG.range || fullExtent(CHARTS[BIG.key]);
function setRange(lo, hi) {  // a view that reaches an end keeps its width, so moving never squeezes it
  const c = CHARTS[BIG.key], [a, b] = fullExtent(c);
  if (Number.isNaN(lo) || Number.isNaN(hi)) return;
  const span = Math.max(Math.min(hi - lo, b - a), minSpan(c));
  if (!(span < b - a)) BIG.range = null;
  else { lo = Math.min(Math.max(lo, a), b - span); BIG.range = [lo, lo + span]; }
  paintSoon();
}
function zoomAt(xv, f) { const [a, b] = curRange(); setRange(xv - (xv - a) * f, xv + (b - xv) * f); }
function pan(f) { const [a, b] = curRange(), d = (b - a) * f; setRange(a + d, b + d); }
function bigKeys(e) {
  if (!BIG || e.target.matches("select, input[type=range]")) return;
  const [a, b] = curRange(), mid = (a + b) / 2;
  const act = {ArrowLeft: () => pan(-.15), ArrowRight: () => pan(.15), "+": () => zoomAt(mid, .7), "=": () => zoomAt(mid, .7),
               "-": () => zoomAt(mid, 1 / .7), "0": () => setRange(-Infinity, Infinity)}[e.key];
  if (act) { e.preventDefault(); act(); }
}
let paintQ = false;
function paintSoon() {  // at most once a frame while fingers or the mouse move (the timer covers a hidden page)
  if (paintQ) return;
  paintQ = true;
  const run = () => { if (paintQ) { paintQ = false; paintBig(); } };
  requestAnimationFrame(run); setTimeout(run, 50);
}
function overview(c, vis) {  // the whole run, small, under the chart: where the view is and a handle to move it
  const H = 48, [a, b] = fullExtent(c), ys = vis.flatMap(x => x.pts.map(p => p[1]));
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const X = x => PL + (x - a) / (b - a || 1) * (PW - PL - PR), Y = y => 5 + (1 - (y - lo) / (hi - lo || 1)) * (H - 10);
  return `<svg viewBox="0 0 ${PW} ${H}" preserveAspectRatio="none" aria-hidden="true">${vis.map(x => `<polyline points="${x.pts.map(p => X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1)).join(" ")}" fill="none" stroke="${x.color}" stroke-width="1.5" opacity=".8" vector-effect="non-scaling-stroke"/>`).join("")}</svg>`;
}
function drawBig() {
  const dlg = $("#chartdlg"), c = BIG && CHARTS[BIG.key]; if (!dlg || !c) return;
  const pageCharts = [...document.querySelectorAll("#content .chart[data-chart]")].map(el => el.dataset.chart).filter((k, i, all) => CHARTS[k] && all.indexOf(k) === i);
  CHARTS.__big__ = {title: c.title, series: c.series, xlabel: c.xlabel, better: c.better};
  BIG.n = c.series.reduce((a, x) => a + x.pts.length, 0);
  const vis = c.series.filter(x => !BIG.hidden.has(x.name)), canLog = c.series.every(x => x.pts.every(p => p[1] > 0));
  const xl = c.xlabel || t("epoch"), first = vis[0];
  const stat = x => { const b = bestPoint(x.pts, c.better), last = x.pts.at(-1); return {b, last}; };
  const zb = (z, label, text) => `<button type="button" class="btn" data-z="${z}" title="${esc(t(label))}" aria-label="${esc(t(label))}">${text}</button>`;
  dlg.innerHTML = `<div class="dh2"><select id="bigsel" aria-label="${esc(t("chart_pick"))}">${(pageCharts.includes(BIG.key) ? pageCharts : [BIG.key, ...pageCharts]).map(k => `<option value="${esc(k)}" ${k === BIG.key ? "selected" : ""}>${esc(CHARTS[k].title)}</option>`).join("")}</select>
      <span class="sp"></span>${c.series.map(x => `<label class="tog"><input type="checkbox" data-bs="${esc(x.name)}" ${BIG.hidden.has(x.name) ? "" : "checked"}><i class="sw" style="background:${x.color}"></i>${esc(x.name)}</label>`).join("")}
      <button type="button" class="btn" id="bigx" aria-label="${esc(t("dismiss"))}">×</button></div>
    <div class="db">
      <div class="bigbar">
        <label>${t("smooth")} <input type="range" id="bsm" min="0" max="0.95" step="0.05" value="${BIG.smooth}"> <b>${BIG.smooth.toFixed(2)}</b></label>
        <label class="tog"><input type="checkbox" id="blog" ${BIG.log && canLog ? "checked" : ""} ${canLog ? "" : "disabled"}> ${t("log_scale")}</label>
        ${c.better ? `<label class="tog"><input type="checkbox" id="bbest" ${BIG.best ? "checked" : ""}> ${t(c.better === "max" ? "best_high" : "best_low")}</label>` : ""}
        <span class="sp"></span>
        <button type="button" class="btn" id="bcsv">${t("csv")}</button>
      </div>
      <div class="zbar"><div class="zbtns" role="group" aria-label="${esc(t("chart_zoom"))}">${zb("out", "zoom_out", "−")}${zb("in", "zoom_in", "+")}${zb("left", "pan_left", "‹")}${zb("right", "pan_right", "›")}
        <button type="button" class="btn" data-z="all" id="bigreset">${t("chart_reset")}</button></div><span class="muted" id="brange"></span></div>
      <div class="chart flat" id="bigplot" data-chart="__big__"></div>
      ${vis.length ? `<div class="bigov" id="bigov" title="${esc(t("chart_overview"))}">${overview(c, vis)}<div class="win" id="bigwin"><i></i><i></i></div></div>` : ""}
      <div class="tw" style="margin-top:12px"><table class="bigstats"><tr><th></th><th class="n">${t("last")}</th>${c.better ? `<th class="n">${t(c.better === "max" ? "best_high" : "best_low")}</th>` : ""}<th class="n" id="bcurh">${esc(xl)} —</th><th class="n">Δ ${esc(first?.name || "")}</th></tr>
        ${vis.map(x => { const st = stat(x); return `<tr><td><i class="sw" style="background:${x.color}"></i> <b>${esc(x.name)}</b></td><td class="n">${fmtv(st.last[1])} <span class="muted">· ${st.last[0]}</span></td>${c.better ? `<td class="n">${st.b ? `${fmtv(st.b[1])} <span class="muted">· ${st.b[0]}</span>` : "—"}</td>` : ""}<td class="n" data-bc="${esc(x.name)}">—</td><td class="n" data-bd="${esc(x.name)}">—</td></tr>`; }).join("")}</table></div>
      <p class="muted" style="font-size:12px;margin:10px 0 0">${t("chart_hint")}</p></div>`;
  $("#bigx").onclick = () => dlg.close();
  $("#bigsel").onchange = e => { BIG.key = e.target.value; BIG.hidden = new Set(HIDDEN[BIG.key] || []); BIG.range = null; drawBig(); };
  dlg.querySelectorAll("[data-bs]").forEach(cb => cb.onchange = () => { cb.checked ? BIG.hidden.delete(cb.dataset.bs) : BIG.hidden.add(cb.dataset.bs); drawBig(); });
  $("#bsm").oninput = e => { BIG.smooth = +e.target.value; store("rb-smooth", BIG.smooth); drawBig(); $("#bsm")?.focus(); };
  $("#blog").onchange = e => { BIG.log = e.target.checked; drawBig(); };
  if ($("#bbest")) $("#bbest").onchange = e => { BIG.best = e.target.checked; drawBig(); };
  dlg.querySelectorAll("[data-z]").forEach(b => b.onclick = () => {
    const [a, z] = curRange(), mid = (a + z) / 2;
    ({out: () => zoomAt(mid, 1 / .6), in: () => zoomAt(mid, .6), left: () => pan(-.25), right: () => pan(.25), all: () => setRange(-Infinity, Infinity)})[b.dataset.z]();
  });
  $("#bcsv").onclick = () => {  // what is shown: the visible range, raw values, one column per series
    const xs = [...new Set(vis.flatMap(x => x.pts.map(p => p[0])))].filter(x => !BIG.range || (x >= BIG.range[0] && x <= BIG.range[1])).sort((a, b) => a - b);
    const csv = [[xl, ...vis.map(x => x.name)].join(","), ...xs.map(x => [x, ...vis.map(z => z.pts.find(p => p[0] === x)?.[1] ?? "")].join(","))].join("\n");
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv + "\n"], {type: "text/csv"}));
    a.download = `${c.title.replace(/[^\w.-]+/g, "_")}${BIG.range ? `_${Math.round(BIG.range[0])}-${Math.round(BIG.range[1])}` : ""}.csv`; a.click(); URL.revokeObjectURL(a.href);
  };
  bindPlot($("#bigplot"));
  if ($("#bigov")) bindOverview($("#bigov"));
  paintBig();
}
function paintBig() {  // only the plot and what shows the view; the rest of the dialog stays, and so do the fingers on it
  const c = BIG && CHARTS[BIG.key], box = $("#bigplot"); if (!c || !box) return;
  const vis = c.series.filter(x => !BIG.hidden.has(x.name)), canLog = c.series.every(x => x.pts.every(p => p[1] > 0));
  box.innerHTML = vis.length ? plot("__big__", vis, {h: Math.max(240, Math.round(innerHeight * .5)), range: BIG.range, smooth: BIG.smooth, log: BIG.log && canLog, best: BIG.best && c.better, xticks: 8, endDot: false}) : `<div class="empty" style="padding:80px 0">—</div>`;
  box.classList.toggle("zoomed", !!BIG.range);
  const [a, b] = fullExtent(c), [lo, hi] = curRange(), frac = v => (PL + (v - a) / (b - a || 1) * (PW - PL - PR)) / PW * 100;
  const win = $("#bigwin");
  if (win) { win.style.left = frac(lo) + "%"; win.style.width = (frac(hi) - frac(lo)) + "%"; win.classList.toggle("all", !BIG.range); }
  const fx = v => +v.toFixed(hi - lo < 10 ? 2 : 1);
  $("#brange").textContent = `${c.xlabel || t("epoch")} ${fx(lo)}–${fx(hi)}${BIG.range ? "" : ` · ${t("chart_all")}`}`;
  const off = {out: !BIG.range, all: !BIG.range, left: lo <= a, right: hi >= b, in: hi - lo <= minSpan(c) * 1.001};
  document.querySelectorAll("#chartdlg [data-z]").forEach(btn => btn.disabled = off[btn.dataset.z]);
}
function bindPlot(box) {
  // one finger or the mouse: drag moves a zoomed view (at full view a finger reads values and the mouse picks a range;
  // Shift + drag always picks one); two fingers: pinch to zoom and move together, the point between them stays put;
  // a tap shows the values there, a double tap or click zooms in, and on a zoomed view shows everything again
  const down = new Map(); let g = null, lastTap = null;
  const cw = () => box.querySelector(".cw");
  const area = () => { const r = cw()?.getBoundingClientRect(); return r && {r, left: r.left + PL / PW * r.width, w: (PW - PL - PR) / PW * r.width}; };
  const valAt = (x, rng, A) => rng[0] + (x - A.left) / A.w * (rng[1] - rng[0]);
  const begin = (x, type, shift) => {
    const A = area(), rng = curRange(), touch = type !== "mouse";
    return A && {kind: BIG.range && !(shift && !touch) ? "pan" : touch ? "scrub" : "select", A, rng, x0: x, moved: false, touch};
  };
  box.addEventListener("pointerdown", ev => {
    if (ev.button > 0 || !BIG || !cw()) return;
    ev.preventDefault();
    try { box.setPointerCapture(ev.pointerId); } catch {}
    down.set(ev.pointerId, ev.clientX);
    if (down.size === 2) {
      const [x1, x2] = [...down.values()], A = area(), rng = curRange();
      g = {kind: "pinch", A, rng, d0: Math.max(24, Math.abs(x1 - x2)), v: valAt((x1 + x2) / 2, rng, A)};
      BIG.dragging = true; hideHover(); floater("csel", "csel").hidden = true;
    } else if (down.size === 1) {
      g = begin(ev.clientX, ev.pointerType, ev.shiftKey);
      if (g?.kind === "scrub") hoverAt(cw(), ev);
    }
  });
  box.addEventListener("pointermove", ev => {
    if (!g || !down.has(ev.pointerId)) return;
    down.set(ev.pointerId, ev.clientX);
    if (g.kind === "pinch") {
      if (down.size < 2) return;
      const [x1, x2] = [...down.values()], span = (g.rng[1] - g.rng[0]) * g.d0 / Math.max(24, Math.abs(x1 - x2));
      const lo = g.v - ((x1 + x2) / 2 - g.A.left) / g.A.w * span;
      return setRange(lo, lo + span);
    }
    const dx = ev.clientX - g.x0;
    if (Math.abs(dx) > 5) g.moved = true;
    if (!g.moved) return;
    if (g.kind === "scrub") return hoverAt(cw(), ev);
    BIG.dragging = true; hideHover();
    if (g.kind === "pan") { box.classList.add("panning"); const d = -dx / g.A.w * (g.rng[1] - g.rng[0]); return setRange(g.rng[0] + d, g.rng[1] + d); }
    const sel = floater("csel", "csel"), x = Math.max(g.A.left, Math.min(g.A.left + g.A.w, ev.clientX));
    Object.assign(sel.style, {top: g.A.r.top + "px", height: g.A.r.height + "px", left: Math.min(g.x0, x) + "px", width: Math.abs(x - g.x0) + "px"});
    sel.hidden = false;
  });
  const end = ev => {
    if (!down.delete(ev.pointerId) || !g) return;
    box.classList.remove("panning");
    if (g.kind === "pinch") {  // a finger lifted: the other one goes on moving the view
      if (down.size === 1) { g = begin([...down.values()][0], "touch", false); if (g) g.moved = true; }
      else { g = null; if (BIG) BIG.dragging = false; }
      return;
    }
    if (g.kind === "select" && g.moved) {
      floater("csel", "csel").hidden = true;
      const x = Math.max(g.A.left, Math.min(g.A.left + g.A.w, ev.clientX)), p = valAt(g.x0, g.rng, g.A), q = valAt(x, g.rng, g.A);
      setRange(Math.min(p, q), Math.max(p, q));
    } else if (!g.moved && ev.type === "pointerup") {
      const now = Date.now();
      if (lastTap && now - lastTap.t < 350 && Math.abs(ev.clientX - lastTap.x) < 30) {
        lastTap = null; hideHover();
        BIG.range ? setRange(-Infinity, Infinity) : zoomAt(valAt(ev.clientX, g.rng, g.A), 1 / 3);
      } else {
        lastTap = {t: now, x: ev.clientX};
        if (g.touch) hoverAt(cw(), ev);  // the values stay where the finger tapped
      }
    }
    g = null; if (BIG) BIG.dragging = false;
  };
  box.addEventListener("pointerup", end);
  box.addEventListener("pointercancel", end);
  box.addEventListener("wheel", ev => {  // wheel zooms at the cursor; a sideways scroll (or Shift + wheel) moves
    const A = area(); if (!A || !BIG) return;
    ev.preventDefault();
    const side = Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : ev.shiftKey ? ev.deltaY : 0;
    if (side) return pan(side / A.w);
    const k = ev.deltaMode ? 0.1 : ev.ctrlKey ? 0.01 : 0.0025;  // ctrl: a touchpad pinch, in small steps
    zoomAt(valAt(ev.clientX, curRange(), A), Math.exp(Math.max(-.7, Math.min(.7, ev.deltaY * k))));
  }, {passive: false});
}
function bindOverview(ov) {
  // drag the window to move the view, its edges to resize it, or across the strip to pick a new range; a tap moves
  // the view there (at full view it zooms in to a quarter around that point)
  let g = null;
  const geo = () => { const r = ov.getBoundingClientRect(); return {left: r.left + PL / PW * r.width, w: (PW - PL - PR) / PW * r.width}; };
  ov.addEventListener("pointerdown", ev => {
    if (ev.button > 0 || !BIG) return;
    ev.preventDefault();
    try { ov.setPointerCapture(ev.pointerId); } catch {}
    const [a, b] = fullExtent(CHARTS[BIG.key]), G = geo(), [lo, hi] = curRange();
    const px = v => G.left + (v - a) / (b - a) * G.w, grab = ev.pointerType === "mouse" ? 8 : 18, x = ev.clientX;
    const kind = !BIG.range ? "new" : Math.abs(x - px(lo)) <= grab ? "lo" : Math.abs(x - px(hi)) <= grab ? "hi" : x > px(lo) && x < px(hi) ? "move" : "new";
    g = {kind, a, b, G, lo, hi, x0: x, v0: a + (x - G.left) / G.w * (b - a), moved: false};
    BIG.dragging = true; hideHover();
  });
  ov.addEventListener("pointermove", ev => {
    if (!g) return;
    if (Math.abs(ev.clientX - g.x0) > 4) g.moved = true;
    if (!g.moved) return;
    const v = Math.max(g.a, Math.min(g.b, g.a + (ev.clientX - g.G.left) / g.G.w * (g.b - g.a)));
    if (g.kind === "move") setRange(g.lo + v - g.v0, g.hi + v - g.v0);
    else if (g.kind === "lo") setRange(Math.min(v, g.hi), g.hi);
    else if (g.kind === "hi") setRange(g.lo, Math.max(v, g.lo));
    else setRange(Math.min(g.v0, v), Math.max(g.v0, v));
  });
  const end = ev => {
    if (!g) return;
    if (!g.moved && ev.type === "pointerup") {
      const span = BIG.range ? g.hi - g.lo : (g.b - g.a) / 4;
      setRange(g.v0 - span / 2, g.v0 + span / 2);
    }
    g = null; if (BIG) BIG.dragging = false;
  };
  ov.addEventListener("pointerup", end);
  ov.addEventListener("pointercancel", end);
}
const pts = (rows, k) => (rows || []).filter(x => x[k] != null).map(x => [x.e, x[k]]);
// the whole loss of an epoch: its parts (box, cls, dfl, ...) added up, where every part is known
const lossSum = (rows, keys) => (rows || []).filter(x => keys.every(k => x[k] != null)).map(x => [x.e, keys.reduce((a, k) => a + x[k], 0)]);
const seriesOf = d => d?.curves?.length ? d.curves : (d?.progress?.history || []);

