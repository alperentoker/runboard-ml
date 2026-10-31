/* ================= project: data ================= */
let dataBuild = null;
async function renderData() {
  if (!$("#jobbox")) $("#content").innerHTML = `<div class="card"><div class="empty">…</div></div>`;
  let d; try { d = await api(`/api/p/${P.key}/data`); } catch (e) { if (!stale("data")) $("#content").innerHTML = `<div class="msg bad">${esc(e.message)}</div>`; return; }
  if (stale("data")) return;
  const remote = Object.fromEntries(d.remote.map(x => [x.key, x])), cols = d.columns;
  const uses = k => P.runs.filter(r => r.data_key === k).map(r => r.id).join(", ");
  const size = r => cols.size_mb ? fsize(r[cols.size_mb]) : "—";
  dataBuild = d.build;
  morph($("#content"), `
  <div class="kpis">
    <div class="kpi"><div class="l">${t("packages")} · ${t("local")}</div><div class="v">${d.rows.filter(r => r._on_disk).length}</div></div>
    <div class="kpi"><div class="l">${t("on_kaggle")}</div><div class="v">${d.remote.filter(x => x.exists).length}<small> / ${d.rows.length}</small></div></div>
    ${cols.size_mb ? `<div class="kpi"><div class="l">${t("total_size")}</div><div class="v">${fsize(d.rows.reduce((a, r) => a + +(r[cols.size_mb] || 0), 0))}</div></div>` : ""}
  </div>
  <div class="card"><div class="ch"><h2>${t("packages")}</h2><div class="sp"><button class="btn" id="dref">${t("refresh")}</button>${d.build ? `<button class="btn" id="build">${esc(tx(P.jobs[d.build]?.title) || t("rebuild"))}</button>` : ""}<button class="btn primary" id="up">${t("upload")}</button></div></div>
    <div class="cb" style="padding-bottom:6px"><p class="desc">${t("data_desc")}</p>${d.error ? `<div class="msg bad">Kaggle: ${esc(d.error)}</div>` : ""}</div>
    <div class="cb flush tw"><table><tr><th style="width:36px"></th><th>${t("data")}</th>${Object.keys(cols).filter(k => k !== "size_mb").map(k => `<th class="${k === "folder" ? "" : "n"}">${T[LANG][k] ? t(k) : en(k)}</th>`).join("")}<th class="n">${t("size")}</th><th>Kaggle</th><th>${t("runs")}</th></tr>
    ${d.rows.map(r => { const k = remote[r._key];
      return `<tr><td><input type="checkbox" class="pk" value="${esc(r._key)}" ${r._on_disk ? "" : "disabled"} aria-label="${esc(r._key)}"></td><td><b>${esc(r._key)}</b>${r._on_disk ? "" : ` <span class="muted">(${t("missing")})</span>`}</td>
      ${Object.entries(cols).filter(([k]) => k !== "size_mb").map(([k, c]) => k === "folder" ? `<td class="mono">${esc(r[c])}</td>` : `<td class="n">${(+r[c] || 0).toLocaleString(LANG)}</td>`).join("")}<td class="n">${size(r)}</td>
      <td>${k?.exists ? `${chip(k.status === "ready" ? "ready" : "running", k.status === "ready" ? t("ready") : k.status || "?")} <span class="muted" style="font-size:12px">${esc(k.dataset)} · v${k.version} · ${fsize(k.gb * 1024)}${k.private ? " · " + t("private") : ""}</span>${k.private === false ? ` <span class="chip ERROR">${t("public")}</span>` : ""}` : `<span class="muted">${t("not_uploaded")}</span>`}</td>
      <td class="muted" style="font-size:12px">${esc(uses(r._key))}</td></tr>`; }).join("")}</table></div></div>
  <div class="card"><div class="ch"><h2>${t("job")}</h2></div><div class="cb" id="jobbox" data-keep><span class="muted">${t("no_job")}</span></div></div>`);
  $("#dref").onclick = renderData;
  $("#up").onclick = async () => {
    const keys = [...document.querySelectorAll(".pk:checked")].map(x => x.value);
    if (!keys.length) return say(t("pick"));
    if (!await ask(t("sure_upload", {k: keys.join(", ")}))) return;
    try { await api(`/api/p/${P.key}/data/upload`, {json: {keys}}); } catch (e) { say(e.message); }
  };
  if ($("#build")) $("#build").onclick = async () => {
    if (!await ask(t("sure_job", {j: tx(P.jobs[d.build]?.title) || d.build}))) return;
    try { await api(`/api/p/${P.key}/job/${d.build}`, {json: {}}); } catch (e) { say(e.message); }
  };
  showJobs(P.key);
}

/* ================= jobs ================= */
// Job output arrives as `job` events (everything once, then only new lines); each box shows one job at a time and a
// running job takes the box over.
const JOBS = {};
function jobEvent(j) {
  const k = `${j.project}:${j.kind}`, prev = JOBS[k];
  JOBS[k] = {...j, lines: j.reset || !prev ? j.lines : prev.lines.concat(j.lines).slice(-2000)};
  paintJob(j.project, j.kind, j.reset || !prev ? null : j.lines);
}
function jobBox(pkey, kind) {
  if (route.view === "system") return $(`#jobbox-${pkey}`);
  if (route.view === "project" && route.tab === "data" && pkey === P?.key && (kind === "upload" || kind === dataBuild)) return $("#jobbox");
}
function paintJob(pkey, kind, added) {
  const el = jobBox(pkey, kind), J = JOBS[`${pkey}:${kind}`]; if (!el || !J) return;
  const cur = el.dataset.job;
  if (cur && cur !== kind && JOBS[`${pkey}:${cur}`]?.status === "running" && J.status !== "running") return;
  if (cur !== kind) { el.dataset.job = kind; el.innerHTML = `<div class="toolbar jh"></div><div class="log short"></div>`; added = null; }
  morph(el.querySelector(".jh"), `<b>${esc(tx(J.title))}</b>${chip(J.status === "running" ? "RUNNING" : J.status === "ok" ? "COMPLETE" : "ERROR", t(J.status === "running" ? "RUNNING" : J.status === "ok" ? "COMPLETE" : "ERROR"))}<span class="muted" style="font-size:12px">${J.seconds} s</span>`);
  const lg = el.querySelector(".log"), end = !lg.childNodes.length || atEnd(lg);
  if (added && lg.childNodes.length && lg.childNodes.length < 400) { if (added.length) lg.append("\n" + added.join("\n")); }
  else lg.textContent = J.lines.join("\n");
  if (end) lg.scrollTop = lg.scrollHeight;
}
function showJobs(pkey) {  // a freshly drawn box: show what is already known (a running job first)
  const mine = Object.values(JOBS).filter(j => j.project === pkey && jobBox(pkey, j.kind));
  const pick = mine.find(j => j.status === "running") || mine.at(-1);
  if (pick) paintJob(pkey, pick.kind);
}

/* ================= project: results ================= */
async function renderResults() {
  let d; try { d = await api(`/api/p/${P.key}/results`); } catch (e) { if (!stale("results")) $("#content").innerHTML = `<div class="msg bad">${esc(e.message)}</div>`; return; }
  if (stale("results")) return;
  const R = d.rows, lab = tx(d.labels.primary) || "score", lab2 = tx(d.labels.secondary) || "";
  const v = (id, k = "primary") => R[id]?.metrics?.[k];
  // the column after the run: results.column in runboard.yaml, else the second field of the plan
  const col = d.column || Object.keys(Object.values(R)[0]?.fields || {})[1] || "";
  const head = `<tr><th>${t("run")}</th><th>${en(col)}</th><th class="n">${esc(lab)}</th>${lab2 ? `<th class="n">${esc(lab2)}</th>` : ""}${d.classes.map(c => `<th class="n">${en(c)}</th>`).join("")}<th class="n">${t("best_epoch")}</th><th class="n">${t("duration")}</th></tr>`;
  const row = id => { const r = R[id]; if (!r) return ""; const f2 = r.fields?.[col];
    return `<tr class="click" tabindex="0" role="link" data-go="${runPage(id)}"><td><b>${esc(id)}</b></td><td>${f2 == null ? `<span class="muted">${t("pending")}</span>` : esc(short(f2))}</td><td class="n"><b>${fmt(v(id))}</b></td>${lab2 ? `<td class="n">${fmt(v(id, "secondary"))}</td>` : ""}${d.classes.map(c => `<td class="n">${fmt(r.classes?.[c])}</td>`).join("")}<td class="n">${v(id, "best_epoch") != null ? `${v(id, "best_epoch")}/${v(id, "epochs") ?? "?"}` : "—"}</td><td class="n">${v(id, "hours") != null ? v(id, "hours") + " h" : "—"}</td></tr>`; };
  const stat = ids => { const xs = ids.map(i => v(i)).filter(x => x != null); if (!xs.length) return "—";
    const m = xs.reduce((a, b) => a + b) / xs.length, s = xs.length > 1 ? Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / (xs.length - 1)) : null;
    return `<b>${m.toFixed(2)}</b>${s != null ? " ± " + s.toFixed(2) : ""} <span class="muted">(n=${xs.length})</span>`; };
  const tables = d.tables.length ? d.tables : [{title: t("results"), runs: Object.keys(R)}];
  const extras = Object.values(R).filter(r => r.extra).map(r => r.id);
  morph($("#content"), `<div class="msg warn">${esc(tx(d.note) || t("results_note"))}</div>` + tables.map(tb => {
    if (tb.groups) return `<div class="card"><div class="ch"><h2>${esc(tx(tb.title))}</h2>${tb.subtitle ? `<span class="muted" style="font-size:12px">${esc(tx(tb.subtitle))}</span>` : ""}</div><div class="cb flush tw"><table>
      <tr><th></th><th>${t("runs")}</th><th class="n">${esc(lab)}</th></tr>${tb.groups.map(g => `<tr><td>${esc(tx(g.label))}</td><td>${esc(g.runs.join(", "))}</td><td class="n">${stat(g.runs)}</td></tr>`).join("")}</table></div>
      ${tb.note ? `<div class="cb muted" style="font-size:12px;border-top:1px solid var(--line)">${esc(tx(tb.note))}</div>` : ""}</div>`;
    const cpts = tb.curve ? Object.entries(tb.curve.x).filter(([i]) => v(i) != null).map(([i, x]) => [x, v(i)]) : [];
    const curve = !tb.curve ? "" : cpts.length >= 2 ? `<div class="cb" style="border-top:1px solid var(--line)">${chart(`${lab} · ${tx(tb.curve.label) || ""}`, [{name: lab, color: COLORS[0], pts: cpts}], {xlabel: tx(tb.curve.label) || "x"})}</div>`
      : `<div class="cb muted" style="border-top:1px solid var(--line);font-size:12px">${esc(tx(tb.curve.label) || "")} · ${t("curve_wait")}</div>`;
    return `<div class="card"><div class="ch"><h2>${esc(tx(tb.title))}</h2>${tb.subtitle ? `<span class="muted" style="font-size:12px">${esc(tx(tb.subtitle))}</span>` : ""}</div><div class="cb flush tw"><table>${head}${tb.runs.map(row).join("")}</table></div>${curve}</div>`;
  }).join("") + (extras.length ? `<div class="card"><div class="ch"><h2>${t("extra")}</h2></div><div class="cb flush tw"><table>${head}${extras.map(row).join("")}</table></div></div>` : ""));
}

