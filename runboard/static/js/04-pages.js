/* ================= chrome ================= */
function renderChrome() {
  const inP = route.view === "project" && P;
  $("#ver").textContent = PS ? `v${PS.version}` : "";
  morph($("#projbox"), inP ? `<div class="proj">${avatar(P, 30)}<div class="t"><b>${esc(P.name)}</b><small tabindex="0" role="link" data-go="#/">← ${t("all_projects")}</small></div></div>` : "");
  const items = inP ? [["overview"], ["runs", P.busy.length], ["settings"], ["code"], ...(P.has_data ? [["data"]] : []), ["results"], ...(P.v2 ? [["hypotheses"]] : [])]
                    : [["projects"]];
  $("#nav").classList.toggle("inproj", !!inP);
  const busyAll = PS ? PS.projects.reduce((a, p) => a + p.active.length, 0) : 0;
  morph($("#nav"), (inP ? `<div class="sec">${t("projects")}</div><button data-go="#/"><svg viewBox="0 0 24 24">${ICONS.projects}</svg><span>${t("all_projects")}</span></button><div class="sec">${esc(P.name)}</div>` : "") +
    items.map(([k, badge]) => `<button class="${(inP ? (route.tab === k || (k === "runs" && route.tab === "run")) : route.view === "home" && k === "projects") ? "on" : ""}" data-go="${inP ? `#/p/${P.key}/${k}` : "#/"}" aria-label="${t(k)}"><svg viewBox="0 0 24 24">${ICONS[k]}</svg><span>${t(k)}</span>${badge ? `<em class="badge">${badge}</em>` : !inP && busyAll ? `<em class="badge">${busyAll}</em>` : ""}</button>`).join("") +
    `<button class="glob ${route.view === "new" ? "on" : ""}" data-go="#/new" aria-label="${t("new_project")}"><svg viewBox="0 0 24 24">${ICONS.plus}</svg><span>${t("new_project")}</span></button>` +
    `<button class="glob ${route.view === "system" ? "on" : ""}" data-go="#/system" aria-label="${t("system")}"><svg viewBox="0 0 24 24">${ICONS.system}</svg><span>${t("system")}</span></button>`);
  const q = PS?.backends?.kaggle?.quota;
  morph($("#foot"), `${q ? `<div>Kaggle · ${q.used_h} / ${q.total_h} h<div class="bar"><i style="width:${Math.min(100, q.used_h / q.total_h * 100)}%"></i></div></div>` : ""}
    <div class="lang"><button class="${LANG === "en" ? "on" : ""}" data-lang="en">EN</button><button class="${LANG === "tr" ? "on" : ""}" data-lang="tr">TR</button></div>
    <div class="lang" role="group" aria-label="${t("theme")}">${["dark", "light", "auto"].map(k => `<button class="${document.documentElement.dataset.theme === k ? "on" : ""}" data-theme-set="${k}">${t("th_" + k)}</button>`).join("")}</div>
    <a href="/mini" target="_blank" rel="noopener">${t("compact")} ↗</a>`);
  const act = PS?.projects.flatMap(p => p.active.map(r => ({...r, pkey: p.key, pname: p.name})))[0];
  $("#live").classList.toggle("hide", !act);
  if (act) { morph($("#live"), `<span class="dot RUNNING"></span><b>${esc(act.id)}</b> <span ${L_("pill", act.pkey, act.id)}></span>`); $("#live").onclick = () => go(`#/p/${act.pkey}/run/${encodeURIComponent(act.id)}`); }
  tick();
  const onTab = $("#nav .on")?.dataset.go;  // the phone bar scrolls sideways: show the open page, once per page
  if (onTab && onTab !== renderChrome.shown) { renderChrome.shown = onTab; $("#nav .on").scrollIntoView({block: "nearest", inline: "nearest"}); }
}
function setLang(l) { LANG = l; store("rb-lang", l); document.documentElement.lang = l; render(); if (ES) setConn(ES.readyState === 1); }
function setTitle(title, crumb) { $("#title").textContent = title; $("#crumb").innerHTML = crumb || ""; document.title = `${title} · runboard`; }

/* ================= home ================= */
function renderHome() {
  setTitle(t("projects"), PS ? `runboard v${PS.version}` : "");
  if (!PS) return;
  const act = PS.projects.reduce((a, p) => a + p.active.length, 0), k = PS.backends.kaggle, l = PS.backends.local;
  morph($("#content"), `
  <div class="kpis home-kpis">
    <div class="kpi"><div class="l">${t("projects_count")}</div><div class="v">${PS.projects.length}</div></div>
    <div class="kpi"><div class="l">${t("active_runs")}</div><div class="v">${act}</div></div>
    <div class="kpi"><div class="l">Kaggle · ${t("gpu_quota")}</div><div class="v">${k?.quota ? `${k.quota.used_h}<small> / ${k.quota.total_h} h</small>` : "—"}</div>${k?.quota ? `<div class="bar"><i style="width:${Math.min(100, k.quota.used_h / k.quota.total_h * 100)}%"></i></div>` : `<div class="s">${esc(k?.error || "")}</div>`}</div>
    <div class="kpi"><div class="l">${t("local_gpu")}</div><div class="v" style="font-size:18px">${l?.gpu ? esc(l.gpu.replace("NVIDIA GeForce ", "")) : "—"}</div><div class="s">${l?.gpu ? t("gpu_mem", {f: l.free_gb, t: l.total_gb}) : ""}</div></div>
  </div>
  ${Object.entries(PS.errors).map(([p, e]) => `<div class="msg bad" style="margin-top:16px">${t("broken")}: <span class="mono">${esc(p)}</span> — ${esc(e)}</div>`).join("")}
  ${queueCard()}
  <div class="grid">
    ${PS.projects.map(p => { const a = p.active[0];
      return `<div class="pcard" tabindex="0" role="link" data-go="#/p/${p.key}/overview">
        <div class="hd">${avatar(p)}<div style="min-width:0"><h3>${esc(p.name)}</h3><div class="path">${esc(p.path)}</div></div></div>
        ${p.description ? `<p>${esc(tx(p.description))}</p>` : ""}
        ${a ? `<div class="act"><div style="display:flex;justify-content:space-between"><span><span class="dot RUNNING"></span> ${esc(a.id)} · <span ${L_("lbl", p.key, a.id)}></span></span><span ${L_("pct", p.key, a.id)}></span></div><div class="bar"><i ${L_("bar", p.key, a.id)}></i></div></div>` : ""}
        <div><div class="row"><span>${t("plan")} ${p.done}/${p.runs}</span><span>${p.best ? `${esc(tx(p.primary_label))} ${t("highest")}: <b style="color:var(--ink)">${esc(p.best.id)} · ${fmt(p.best.value)}</b>` : ""}</span></div>
          <div class="bar"><i style="width:${p.runs ? p.done / p.runs * 100 : 0}%"></i></div></div>
        <div class="row"><span>${p.backends.map(b => esc(PS.backends[b]?.label || b)).join(" · ")}</span><span>${p.key}</span></div></div>`; }).join("")}
    <div class="pcard addp" tabindex="0" role="link" data-go="#/new"><span class="plus">+</span><b>${t("new_project")}</b><span class="desc" style="margin:0">${t("new_project_desc")}</span></div>
  </div>`);
  tick();
}

/* ================= project: overview ================= */
const valOf = r => r?.metrics?.primary ?? (r?.status === "COMPLETE" ? r?.progress?.best : null);
function renderOverview() {
  const act = P.runs.find(r => ACTIVE.includes(r.status)), p = act?.progress || {};
  const plan = P.runs.filter(r => !r.extra), done = plan.filter(r => r.status === "COMPLETE").length;
  const best = P.runs.filter(r => valOf(r) != null).sort((a, b) => valOf(b) - valOf(a))[0];
  if (stale("overview")) return;
  const H = act && activeDetail?.id === act.id ? seriesOf(activeDetail) : [], q = P.backend_info?.kaggle?.quota, lab = tx(P.labels.primary) || "score";
  const finished = P.runs.filter(r => r.status === "COMPLETE").sort((a, b) => (b.pushed_at || "").localeCompare(a.pushed_at || ""));
  const phases = P.phases.length ? P.phases : [{id: "", title: t("runs"), runs: P.runs.map(r => r.id)}];
  morph($("#content"), `
  <div class="kpis ${q ? "k6" : ""}">
    <div class="kpi"><div class="l">${t("active_run")}</div><div class="v">${act ? esc(act.id) : "—"}</div><div class="s">${act ? esc(Object.values(act.fields).map(short).join(" · ")) : t("no_active")}</div></div>
    <div class="kpi"><div class="l">${t("progress")}</div><div class="v">${act ? `${p.epoch || 0}<small> / ${p.epochs || act.epochs || "?"}</small>` : "—"}</div><div class="bar"><i ${act ? L_("bar", P.key, act.id) : ""} style="width:${act ? (live(act).frac * 100).toFixed(1) : 0}%"></i></div></div>
    <div class="kpi"><div class="l">${esc(lab)}</div><div class="v">${act ? fmt(p.best) : "—"}</div><div class="s">${act ? `${t("best")} · ${t("last")} ${fmt(p.map)}` : ""}</div></div>
    <div class="kpi"><div class="l">${t("eta")}</div><div class="v">${act && p.eta_at ? new Date(p.eta_at * 1000).toLocaleTimeString(LANG, {hour: "2-digit", minute: "2-digit"}) : "—"}</div><div class="s">${act ? `${t("left")} <span ${L_("left", P.key, act.id)}></span>` : ""}</div></div>
    <div class="kpi"><div class="l">${t("plan")}</div><div class="v">${done}<small> / ${plan.length}</small></div><div class="bar"><i style="width:${plan.length ? done / plan.length * 100 : 0}%"></i></div></div>
    ${q ? `<div class="kpi"><div class="l">Kaggle · ${t("gpu_quota")}</div><div class="v">${q.used_h}<small> / ${q.total_h} h</small></div><div class="bar"><i style="width:${Math.min(100, q.used_h / q.total_h * 100)}%"></i></div></div>` : ""}
  </div>
  ${queueCard(P.key)}
  <div class="cols">
    <div class="card"><div class="ch"><h2>${act ? `${esc(act.id)} · ${t("live")}` : t("active_run")}</h2>${act ? chip(act.status) : ""}<div class="sp">${act ? `<button class="btn" data-go="${runPage(act.id)}">${t("details")}</button>` : ""}</div></div>
      <div class="cb">${act ? `
        <div class="prog"><div class="lbl"><span ${L_("lbl", P.key, act.id)}></span><span ${L_("pct", P.key, act.id)}></span></div><div class="bar big"><i ${L_("bar", P.key, act.id)}></i></div></div>
        ${p.stage ? `<div class="stage">${esc(p.stage)}${p.its ? ` · ${p.its.toFixed(1)} it/s` : ""} <span class="est" ${L_("epleft", P.key, act.id)}></span></div>` : ""}
        <div style="margin-top:14px">${activeDetail?.id === act.id ? chart(lab, [{name: act.id, color: COLORS[0], pts: pts(H, "map")}], {h: 220}) : `<div class="chart"><div class="t"><b>${esc(lab)}</b></div><div class="empty" style="padding:90px 0">${t("loading")}</div></div>`}</div>`
        : `<div class="empty">${t("no_active")}<br><button class="btn primary" style="margin-top:12px" data-go="#/p/${P.key}/runs">${t("start_run")}</button></div>`}</div></div>
    <div class="card"><div class="ch"><h2>${t("roadmap")}</h2><span class="muted" style="font-size:12px">${done}/${plan.length}</span></div>
      <div class="cb" style="padding-top:4px;padding-bottom:4px">${phases.map(ph => `<div class="phase"><div class="pn"><b>${esc([ph.id, tx(ph.title)].filter(Boolean).join(" · "))}</b><span>${esc(tx(ph.subtitle))}</span></div>
        <div class="pills">${ph.runs.map(id => { const r = run(id); return r ? `<span class="pill" tabindex="0" role="link" data-go="${runPage(id)}"><span class="dot ${r.status || ""}"></span>${esc(id)}${valOf(r) != null ? ` <small>${fmt(valOf(r), 1)}</small>` : ""}</span>` : ""; }).join("")}</div></div>`).join("")}</div></div>
  </div>
  <div class="card" style="margin-top:16px"><div class="ch"><h2>${t("finished")}</h2>${best ? `<span class="muted" style="font-size:12px">${esc(lab)} ${t("highest")}: <b style="color:var(--ink)">${esc(best.id)} · ${fmt(valOf(best))}</b></span>` : ""}</div>
    <div class="cb flush tw">${finished.length ? `<table><tr><th>${t("run")}</th>${Object.keys(finished[0].fields).map(f => `<th>${en(f)}</th>`).join("")}<th class="n">${esc(lab)}</th>${P.labels.secondary ? `<th class="n">${esc(tx(P.labels.secondary))}</th>` : ""}<th class="n">${t("best_epoch")}</th><th class="n">${t("duration")}</th></tr>
      ${finished.map(r => `<tr class="click" tabindex="0" role="link" data-go="${runPage(r.id)}"><td><b>${esc(r.id)}</b></td>${Object.values(r.fields).map(v => `<td>${esc(short(v))}</td>`).join("")}<td class="n"><b>${fmt(r.metrics?.primary)}</b></td>${P.labels.secondary ? `<td class="n">${fmt(r.metrics?.secondary)}</td>` : ""}<td class="n">${r.metrics?.best_epoch != null ? `${r.metrics.best_epoch}/${r.metrics.epochs ?? "?"}` : "—"}</td><td class="n">${dur(r.metrics?.hours)}</td></tr>`).join("")}</table>` : `<div class="empty">${t("none_finished")}</div>`}</div></div>
  ${Object.entries(P.jobs || {}).some(([, j]) => !j.per_run) ? `<div class="card" style="margin-top:16px"><div class="ch"><h2>${t("jobs")}</h2><div class="sp">${Object.entries(P.jobs).filter(([, j]) => !j.per_run).map(([k, j]) => `<button class="btn" data-pj="${esc(k)}">${esc(tx(j.title))}</button>`).join(" ")}</div></div>
    <div class="cb"><div id="pjob" data-keep></div></div></div>` : ""}`);
  document.querySelectorAll("[data-pj]").forEach(b => b.onclick = async () => {
    if (!await ask(t("sure_job", {j: b.textContent}))) return;
    try { await api(`/api/p/${P.key}/job/${encodeURIComponent(b.dataset.pj)}`, {json: {}}); } catch (e) { say(e.message); }
  });
  showJobs(P.key);
  tick();
}

/* ================= project: runs ================= */
function renderRunsTab() {
  if (!route.run || !run(route.run)) { const def = P.runs.find(r => ACTIVE.includes(r.status)) || P.runs.find(r => r.status) || P.runs[0]; if (def) { location.replace(runHref(def.id)); return; } }
  if (!$("#runlist")) $("#content").innerHTML = `<div class="split"><div class="card rl" id="runlist"></div><div id="detail"></div></div>`;
  const groups = [...(P.phases.length ? P.phases.map(ph => [[ph.id, tx(ph.title)].filter(Boolean).join(" · "), ph.runs]) : [[t("runs"), P.runs.filter(r => !r.extra).map(r => r.id)]]),
                  [t("extra"), P.runs.filter(r => r.extra).map(r => r.id)]];
  const listed = new Set(groups.flatMap(g => g[1]));
  const rest = P.runs.filter(r => !listed.has(r.id)).map(r => r.id); if (rest.length) groups.push(["—", rest]);
  const queued = new Set((PS?.queue || []).filter(e => e.project === P.key).map(e => e.run));
  const fresh = P.runs.filter(r => !r.status && r.ready && !r.extra && !queued.has(r.id)).map(r => r.id);  // never started
  morph($("#runlist"), (fresh.length > 1 ? `<div class="toolbar" style="margin:10px 12px 4px"><button class="btn" id="enqall">${t("enq_all", {n: fresh.length})}</button></div>` : "") +
    groups.filter(g => g[1].length).map(([title, ids]) => `<div class="grp">${esc(title)}</div>` + ids.map(id => {
    const r = run(id); if (!r) return ""; const p = r.progress || {}, on = ACTIVE.includes(r.status);
    const val = valOf(r) != null ? fmt(valOf(r), 1) : "";
    const m = r.ready ? Object.values(r.fields).map(short).join(" · ") : `${t("waits")} ${r.missing.join(", ")}`;
    return `<div class="ri ${id === route.run ? "sel" : ""}" tabindex="0" role="link" data-go="${runHref(id)}"><span class="dot ${r.status || ""}"></span><b>${esc(id)}</b><span class="val">${on ? `e${p.epoch || 0}/${p.epochs || r.epochs || "?"}` : val}</span><span class="m">${esc(m)}</span></div>`;
  }).join("")).join(""));
  if ($("#enqall")) $("#enqall").onclick = async () => {
    try { await api("/api/queue", {json: {project: P.key, runs: fresh, backend: P.default_backend}}); toast(t("queued_ok")); } catch (e) { say(e.message); }
    refresh();
  };
  loadDetail();
}
function renderRunPage() {
  if (!run(route.run)) { go(`#/p/${P.key}/runs`); return; }
  if (!$("#runpage")) $("#content").innerHTML = `<div id="runpage"><div id="detail"></div></div>`;
  loadDetail();
}
// The open run's details arrive as `run` events; a fetch is only needed for the first paint and for compared runs.
async function loadDetail() {
  if (route.view !== "project" || !["runs", "run"].includes(route.tab) || !route.run) return;
  const id = route.run;
  if (detail?.id !== id) { const d = await api(`/api/p/${P.key}/run/${encodeURIComponent(id)}`).catch(() => null); if (d && route.run === id && detail?.id !== id) detail = d; }
  for (const c of compare) if (!compCache[c] || (ACTIVE.includes(run(c)?.status) && Date.now() - compCache[c]._t > 30000)) {
    const d = await api(`/api/p/${P.key}/run/${encodeURIComponent(c)}`).catch(() => null); if (d) compCache[c] = {...d, _t: Date.now()};
  }
  renderDetail();
}
function renderDetail() {
  const d = detail; if (!d || d.id !== route.run || !$("#detail")) return;
  const r = run(d.id) || {}, p = d.progress || {}, active = ACTIVE.includes(r.status), H = seriesOf(d), f = d.final, met = r.metrics || {};
  const bk = P.backends, bnow = r.backend || P.default_backend, binfo = P.backend_info?.[bnow] || {};
  const kv = (l, v, s = "") => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ""}</div>`;
  const lab = tx(P.labels.primary) || "score", lab2 = tx(P.labels.secondary) || "";
  let body = "";
  if (!r.status) body = `<div class="empty">${d.ready ? t("not_started") : `${t("waits")} ${d.missing.join(", ")}`}</div>`;
  else if (sub === "charts") {
    const others = P.runs.filter(x => x.id !== d.id && x.status);
    const comp = [...compare].filter(id => id !== d.id && compCache[id]).map((id, i) => ({name: id, color: COLORS[(i + 1) % 5], dash: true, rows: seriesOf(compCache[id])}));
    const has = k => H.some(x => x[k] != null);
    const lossKeys = [...new Set(H.flatMap(x => Object.keys(x).filter(k => k.endsWith("_loss") && !k.startsWith("val_"))))];
    const vlossKeys = [...new Set(H.flatMap(x => Object.keys(x).filter(k => k.startsWith("val_") && k.endsWith("_loss"))))];
    body = `${others.length ? `<div class="toolbar"><span class="muted" style="font-size:13px;font-weight:600">${t("compare")}</span>${others.map(o => `<label class="tog"><input type="checkbox" class="cmp" value="${esc(o.id)}" ${compare.has(o.id) ? "checked" : ""}>${esc(o.id)}</label>`).join("")}<span class="sp muted" style="font-size:12px">${t("source")}: ${d.curves?.length ? "results.csv" : t("live_log")}</span></div>` : ""}
      <div class="charts">
      ${chart(lab, [{name: d.id, color: COLORS[0], pts: pts(H, "map")}, ...comp.map(s => ({...s, pts: pts(s.rows, "map")}))])}
      ${has("map50") ? chart(lab2 || "map50", [{name: d.id, color: COLORS[0], pts: pts(H, "map50")}, ...comp.map(s => ({...s, pts: pts(s.rows, "map50")}))]) : ""}
      ${has("p") || has("r") ? chart(t("ch_pr"), [{name: t("precision"), color: COLORS[1], pts: pts(H, "p")}, {name: t("recall"), color: COLORS[2], pts: pts(H, "r")}], {better: "max"}) : ""}
      ${lossKeys.length && vlossKeys.length ? chart(t("ch_loss_tv"), [{name: t("s_train"), color: COLORS[0], pts: lossSum(H, lossKeys)}, {name: t("s_val"), color: COLORS[1], dash: true, pts: lossSum(H, vlossKeys)}], {better: "min"}) : ""}
      ${lossKeys.length ? chart(t("ch_tloss"), lossKeys.map((k, i) => ({name: k.replace("_loss", ""), color: COLORS[i % 5], pts: pts(H, k)})), {better: "min"}) : ""}
      ${vlossKeys.length ? chart(t("ch_vloss"), vlossKeys.map((k, i) => ({name: k.replace("val_", "").replace("_loss", ""), color: COLORS[i % 5], pts: pts(H, k)})), {better: "min"}) : ""}
      ${has("lr") ? chart(t("ch_lr"), [{name: "lr", color: COLORS[3], pts: pts(H, "lr")}], {better: null}) : ""}
      </div>`;
  } else if (sub === "result") {
    const pcNode = f?.per_class;
    body = f || r.metrics ? `${f ? `<div class="tw"><table><tr><th>${t("class")}</th><th class="n">${esc(lab)}</th><th class="n">${esc(lab2)}</th></tr>
      <tr><td><b>${t("all")}</b></td><td class="n"><b>${fmt(met.primary ?? (f.map50_95 != null ? 100 * f.map50_95 : null))}</b></td><td class="n">${fmt(met.secondary ?? (f.map50 != null ? 100 * f.map50 : null))}</td></tr>
      ${pcNode ? Object.entries(pcNode).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="n">${fmt(100 * (v.map50_95 ?? v.map ?? 0))}</td><td class="n">${fmt(100 * (v.ap50 ?? v.map50 ?? 0))}</td></tr>`).join("") : ""}</table></div>` : ""}
      <div class="kpis" style="margin:16px 0 0">${f?.precision != null ? kv(t("precision"), fmt(100 * f.precision)) : ""}${f?.recall != null ? kv(t("recall"), fmt(100 * f.recall)) : ""}${kv(t("best_epoch"), met.best_epoch != null ? `${met.best_epoch}/${met.epochs ?? "?"}` : "—")}${kv(t("duration"), dur(met.hours))}</div>
      <p class="desc" style="margin-top:14px">${t("output")}: <span class="mono">${esc(d.output)}</span></p>` : r.check?.error ? `<div class="msg bad">${esc(r.check.error)}</div>` : `<div class="empty">${t("no_data")}</div>`;
  } else if (sub === "table") {
    const keys = [...new Set(H.flatMap(x => Object.keys(x)))].filter(k => !["e", "t", "secs", "lr"].includes(k));
    body = H.length ? `<div class="tw" data-scroll="etable" style="max-height:520px;overflow:auto"><table><tr><th class="n">${t("epoch")}</th>${keys.map(k => `<th class="n">${en(k)}</th>`).join("")}</tr>
      ${[...H].reverse().map(x => `<tr><td class="n">${x.e}</td>${keys.map(k => `<td class="n">${fmt(x[k], k.includes("loss") ? 3 : 2)}</td>`).join("")}</tr>`).join("")}</table></div>` : `<div class="empty">${t("no_data")}</div>`;
  } else {
    body = `<div class="toolbar"><label class="tog"><input type="checkbox" id="all" ${allLog ? "checked" : ""}> ${t("all_lines")}</label><span class="sp muted" style="font-size:12px">${t("autoscroll")}</span></div><div class="log" id="log" data-keep></div>`;
  }
  const startable = d.ready && !active;
  morph($("#detail"), `
  <div class="card"><div class="cb">
    <div class="dh">${route.tab === "run" ? `<a class="btn back" href="${runHref(d.id)}" title="${t("run_list")}" aria-label="${t("run_list")}">←</a>` : ""}<h2>${esc(d.id)}</h2>${chip(r.status)}${d.extra ? chip("lock", t("extra")) : ""}
      <div class="sp">
        ${route.tab === "runs" ? `<a class="btn" href="${runPage(d.id)}" title="${t("full_page")}">⤢ ${t("full_page")}</a>` : ""}
        ${r.url ? `<a class="btn" href="${esc(r.url)}" target="_blank" rel="noopener">${t("open_kaggle")} ↗</a>` : ""}
        ${active && P.backend_info?.[bnow]?.can_cancel ? `<button class="btn danger" id="cancel">${t("cancel")}</button>` : ""}
        ${r.status === "COMPLETE" && r.backend ? `<button class="btn" id="collect">${t("recollect")}</button>` : ""}
        ${Object.entries(P.jobs || {}).filter(([k, j]) => j.per_run && (k !== "revalidate" || r.status === "COMPLETE")).map(([k, j]) => `<button class="btn" data-rj="${esc(k)}">${esc(tx(j.title))}</button>`).join("")}
        ${r.status && !active && r.own_remote ? `<button class="btn danger" id="del">${t("delete_remote")}</button>` : ""}
        ${bk.length > 1 && startable ? `<select id="bsel" aria-label="${t("backend")}">${bk.map(b => `<option value="${b.name}" ${b.name === P.default_backend ? "selected" : ""}>${esc(b.label)}</option>`).join("")}</select>` : ""}
        ${d.ready && !active && !(PS?.queue || []).some(e => e.project === P.key && e.run === d.id) ? `<button class="btn" id="enq">${t("enqueue")}</button>` : ""}
        ${["ERROR", "CANCELLED"].includes(r.status) && P.backends.find(x => x.name === r.backend)?.resume ? `<button class="btn" id="resume" title="${esc(t("resume_desc"))}">${t("resume")}</button>` : ""}
        <button class="btn primary" id="start" ${startable ? "" : "disabled"}>${r.status ? t("restart") : t("start")}</button>
      </div></div>
    <div class="meta"><b>${esc(d.name || "—")}</b> · ${Object.entries(d.fields).map(([k, v]) => `${esc(k)} ${esc(short(v))}`).join(" · ")}${r.backend ? ` · ${esc(P.backend_info?.[r.backend]?.label || r.backend)}${r.version ? ` ${esc(r.kernel || "")} v${r.version}` : ""}` : ""}${p.optimizer ? ` · ${esc(p.optimizer)} lr0 ${esc(p.lr0)}` : ""}</div>
    ${r.failure ? `<div class="msg bad" style="margin-top:12px">${esc(r.failure)}</div>` : ""}
    ${r.changed_since_start?.length ? `<div class="msg warn" style="margin-top:12px">${t("changed_after")} <b>${r.changed_since_start.map(esc).join(", ")}</b></div>` : ""}
    ${d.provenance?.git || d.provenance?.data ? `<p class="desc" style="margin:10px 0 0">${t("prov")}: ${d.provenance.git ? `commit <span class="mono">${esc(d.provenance.git.commit.slice(0, 10))}</span>${d.provenance.git.dirty ? ` <b>${t("prov_dirty")}</b>` : ""}` : t("prov_nogit")}${d.provenance.data ? ` · ${t("prov_data")} <span class="mono">${esc(d.provenance.data.key)}</span>${d.provenance.data.files ? ` (${d.provenance.data.files} ${t("prov_files")})` : ""}` : ""}${d.provenance.locked ? ` · ${t("h_locked")}` : ""}</p>` : ""}
    ${r.status ? `<div class="prog"><div class="lbl"><span ${active ? L_("lbl", P.key, d.id) : ""}>${lbl(live(r), r.status === "COMPLETE" ? (met.epochs ?? H.at(-1)?.e) : undefined)}</span><span ${L_("pct", P.key, d.id)}></span></div><div class="bar big"><i ${L_("bar", P.key, d.id)}></i></div></div>
      ${active && p.stage ? `<div class="stage">${esc(p.stage)} <span class="est" ${L_("epleft", P.key, d.id)}></span></div>` : ""}` : ""}
  </div></div>
  ${!r.status ? "" : active ? `<div class="kpis k6" style="margin-top:16px">
    ${kv(`${t("last")} ${esc(lab)}`, fmt(p.map), `${t("epoch")} ${p.epoch || 0}`)}${kv(t("best"), fmt(p.best))}${lab2 || p.map50 != null ? kv(`${t("last")} ${esc(lab2 || "mAP50")}`, fmt(p.map50)) : ""}
    ${kv(t("epoch_time"), p.epoch_secs ? hms(p.epoch_secs) : "—")}${kv(t("speed"), p.its ? p.its.toFixed(1) + " it/s" : "—")}
    ${kv(t("left"), `<span ${L_("left", P.key, d.id)}>—</span>`, p.eta_at ? `${t("eta")} ${new Date(p.eta_at * 1000).toLocaleTimeString(LANG, {hour: "2-digit", minute: "2-digit"})}` : "")}
  </div>` : `<div class="kpis k6" style="margin-top:16px">
    ${kv(esc(lab), fmt(met.primary ?? p.best))}${lab2 || met.secondary != null || p.map50 != null ? kv(esc(lab2 || "mAP50"), fmt(met.secondary ?? p.map50)) : ""}
    ${f?.per_class ? Object.entries(f.per_class).slice(0, 3).map(([k, v]) => kv(esc(k), fmt(100 * (v.map50_95 ?? v.map ?? 0)))).join("") : ""}
    ${kv(t("best_epoch"), met.best_epoch != null ? `${met.best_epoch}/${met.epochs ?? "?"}` : "—")}
    ${kv(t("duration"), dur(met.hours), H.at(-1)?.t ? `${t("per_epoch")} ${hms(H.at(-1).t / H.length)}` : p.epoch_secs ? `${t("per_epoch")} ${hms(p.epoch_secs)}` : "")}
  </div>`}
  <div class="card" style="margin-top:16px">
    <div class="tabs">${[["charts", t("charts")], ["result", t("result")], ["table", t("epoch_table")], ["log", t("log")]].map(([k, l]) => `<button data-sub="${k}" class="${k === sub ? "on" : ""}">${l}</button>`).join("")}</div>
    <div class="cb">${body}</div></div>
  <div id="runjob" data-keep style="margin-top:16px"></div>`);
  if (sub === "log") paintLog();
  showJobs(P.key);
  document.querySelectorAll("[data-sub]").forEach(b => b.onclick = () => { sub = b.dataset.sub; store("rb-sub", sub); renderDetail(); subscribe(); });
  if ($("#start")) $("#start").onclick = async () => {
    const b = $("#bsel")?.value || P.default_backend, lab_ = P.backends.find(x => x.name === b)?.label || b;
    if (!await ask(t("sure_start", {run: d.id, b: lab_}))) return;
    $("#start").disabled = true;
    try { await api(`/api/p/${P.key}/start/${encodeURIComponent(d.id)}`, {json: {backend: b}}); toast(t("sent", {run: d.id, b: lab_})); } catch (e) { say(e.message); }
    refresh();
  };
  const on = (id, f) => { if ($(id)) $(id).onclick = f; };  // property handlers: a patched page never gets a second copy
  on("#resume", async () => {
    if (!await ask(t("sure_resume", {run: d.id}))) return;
    try { await api(`/api/p/${P.key}/start/${encodeURIComponent(d.id)}`, {json: {backend: r.backend, resume: true}}); toast(t("sent", {run: d.id, b: P.backend_info?.[r.backend]?.label || r.backend})); } catch (err) { say(err.message); }
    refresh();
  });
  on("#enq", async e => {
    const b = $("#bsel")?.value || P.default_backend;
    try { await api("/api/queue", {json: {project: P.key, run: d.id, backend: b}}); toast(t("queued_ok")); } catch (err) { say(err.message); }
    refresh();
  });
  on("#cancel", async e => await ask(t("sure_cancel", {run: d.id}), true) && act(e, `/api/p/${P.key}/cancel/${encodeURIComponent(d.id)}`));
  on("#collect", e => act(e, `/api/p/${P.key}/collect/${encodeURIComponent(d.id)}`));
  document.querySelectorAll("[data-rj]").forEach(b => b.onclick = async () => {
    if (!await ask(t("sure_job", {j: `${b.textContent} · ${d.id}`}))) return;
    try { await api(`/api/p/${P.key}/job/${encodeURIComponent(b.dataset.rj)}`, {json: {run: d.id}}); } catch (e) { say(e.message); }
  });
  on("#del", async e => await ask(t("sure_delete", {run: d.id}), true) && act(e, `/api/p/${P.key}/delete/${encodeURIComponent(d.id)}`));
  if ($("#all")) $("#all").onchange = e => { allLog = e.target.checked; subscribe(); paintLog(); };
  document.querySelectorAll(".cmp").forEach(cb => cb.onchange = () => { cb.checked ? compare.add(cb.value) : compare.delete(cb.value); loadDetail(); });
  tick();
}
async function act(e, path, json, then) {
  const b = e.target, txt = b.textContent; b.disabled = true; b.textContent = "…";
  try { await api(path, json ? {json} : {method: "POST"}); then?.(); } catch (err) { say(err.message); }
  b.disabled = false; b.textContent = txt; refresh();
}
// A log follows new lines only while the reader is at its end; otherwise it stays where they scrolled.
const atEnd = el => el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
// Log lines arrive as `log` events (the whole log once, then only new lines) and are appended, never redrawn.
let LOG = {run: null, all: null, lines: null};
function logEvent(j) {
  if (j.run !== route.run) return;
  const fresh = j.reset || LOG.run !== j.run || LOG.all !== allLog || !LOG.lines;
  LOG = {run: j.run, all: allLog, lines: fresh ? j.lines : LOG.lines.concat(j.lines).slice(-3000)};
  paintLog(fresh ? null : j.lines, fresh);
}
function paintLog(added, force) {
  const el = $("#log"); if (!el) return;
  const shown = `${LOG.run}|${LOG.all}`;
  if (LOG.run !== route.run || LOG.all !== allLog || !LOG.lines) { el.textContent = "…"; el.dataset.shown = ""; return; }
  const end = el.dataset.shown !== shown || atEnd(el);
  if (added && el.dataset.shown === shown && +el.dataset.n > 0 && el.childNodes.length < 400) { if (added.length) el.append("\n" + added.join("\n")); }
  else if (force || added || el.dataset.shown !== shown || +el.dataset.n !== LOG.lines.length) el.textContent = LOG.lines.length ? LOG.lines.join("\n") : t("no_log");
  el.dataset.shown = shown; el.dataset.n = LOG.lines.length;
  if (end) el.scrollTop = el.scrollHeight;
}

/* ================= project: settings ================= */
async function renderSettings() {
  let c; try { [c, PLAN, FILES, TPL] = await Promise.all([api(`/api/p/${P.key}/config`), api(`/api/p/${P.key}/plan`), api(`/api/p/${P.key}/files`), api(`/api/p/${P.key}/templates`)]); } catch (e) { if (!stale("settings")) $("#content").innerHTML = `<div class="msg bad">${esc(e.message)}</div>`; return; }
  if (stale("settings")) return;
  const lab = tx(P.labels.primary) || "score";
  const dec = c.decisions.map(d => {
    const vals = d.candidates.map(x => x.metrics?.primary).filter(v => v != null);
    const best = d.ready ? d.candidates.reduce((a, b) => (b.metrics.primary > a.metrics.primary ? b : a)) : null;
    const gap = d.ready && vals.length ? Math.max(...vals) - Math.min(...vals) : null;
    return `<div class="card"><div class="ch"><h2>${esc(d.id)} · ${esc(tx(d.title))}</h2>${d.done ? chip("COMPLETE", t("decided")) : chip("", d.ready ? t("waiting_dec") : t("running_dec"))}</div><div class="cb">
      ${d.rule ? `<p class="desc">${esc(tx(d.rule))}</p>` : ""}
      <div class="card tw"><table><tr><th>${t("run")}</th><th>${en(d.field)}</th><th>${t("status")}</th><th class="n">${esc(lab)}</th>${P.labels.secondary ? `<th class="n">${esc(tx(P.labels.secondary))}</th>` : ""}<th class="n">${t("best_epoch")}</th><th class="n">${t("duration")}</th></tr>
      ${d.candidates.map(x => `<tr class="click" tabindex="0" role="link" data-go="${runPage(x.id)}"><td><b>${esc(x.id)}</b></td><td>${esc(short(x[d.field]))}</td><td>${chip(run(x.id)?.status)}</td><td class="n"><b>${fmt(x.metrics?.primary)}</b></td>${P.labels.secondary ? `<td class="n">${fmt(x.metrics?.secondary)}</td>` : ""}<td class="n">${x.metrics?.best_epoch != null ? `${x.metrics.best_epoch}/${x.metrics.epochs ?? "?"}` : "—"}</td><td class="n">${dur(x.metrics?.hours)}</td></tr>`).join("")}</table></div>
      <div style="margin-top:14px">${d.done ? `<div class="msg ok">${t("dec_done")}</div>` : !d.ready ? `<div class="msg warn">${t("dec_wait")}</div>` : `
        <div class="msg ${d.tie != null && gap < d.tie ? "warn" : "ok"}">${d.tie != null && gap < d.tie ? t("dec_tie") : `${t("dec_ready")}: ${esc(short(best[d.field]))} (${fmt(best.metrics.primary)}) · ${t("dec_gap")} ${fmt(gap)}`}</div>
        <div class="form"><label>${t("winner")}<select class="dv" data-d="${esc(d.id)}">${[...new Set(d.candidates.map(x => x[d.field]))].map(v => `<option ${best && v === best[d.field] ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
          <label class="wide">${t("reason")}<input class="dr" data-d="${esc(d.id)}" placeholder="${esc(t("reason_ph"))}"></label>
          <button class="btn primary dsave" data-d="${esc(d.id)}">${t("save_dec")}</button></div>`}</div></div></div>`; }).join("");
  const ex = c.extras;
  morph($("#content"), `${dec}
  ${planCard()}
  ${ex && PLAN.locked ? `<div class="card"><div class="ch"><h2>${t("add_extra")}</h2></div><div class="cb"><p class="desc">${t("extra_desc")}</p>
    <div class="form">${Object.entries(ex.fields || {}).map(([k, rule]) => `<label>${esc(k)}${c.extra_choices[k] ? `<select class="xf" data-k="${esc(k)}">${c.extra_choices[k].map(v => `<option ${v === rule.default ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`
      : `<input class="xf" data-k="${esc(k)}" type="${rule.int ? "number" : "text"}" value="${esc(rule.default ?? "")}" ${rule.int ? `min="${rule.int[0]}" max="${rule.int[1]}"` : ""}>`}</label>`).join("")}
      <label class="wide">${t("note")}<input id="xnote"></label><button class="btn primary" id="xadd">${t("add")}</button></div></div></div>` : ""}
  ${PLAN && !PLAN.locked ? sharedCard() + rawCard() : P.v2 && PLAN?.locked ? rawCard(true) : Object.keys(c.shared).length ? `<div class="card"><div class="ch"><h2>${t("shared")}</h2>${c.locked ? chip("lock", t("readonly")) : ""}</div><div class="cb"><p class="desc">${t("shared_desc")}</p>
    ${Object.entries(c.shared).map(([s, v]) => `<div class="card tw" style="margin-bottom:12px"><table><tr><th colspan="2">${esc(s)}</th></tr>${typeof v === "object" && v ? Object.entries(v).map(([k, x]) => `<tr><td class="mono">${esc(k)}</td><td><b>${esc(JSON.stringify(x))}</b></td></tr>`).join("") : `<tr><td colspan="2"><b>${esc(JSON.stringify(v))}</b></td></tr>`}</table></div>`).join("")}
    <details><summary>${esc(c.runs_file)}</summary><pre class="raw">${esc(c.raw)}</pre></details></div></div>` : ""}
  ${c.decision_log ? `<div class="card"><div class="ch"><h2>${t("decision_log")}</h2></div><div class="cb"><pre class="raw">${esc(c.decision_log)}</pre></div></div>` : ""}
  ${filesCards()}
  ${templatesCard()}
  ${ME?.local ? `<div class="card"><div class="ch"><h2>${t("remove_proj")}</h2></div><div class="cb"><p class="desc">${t("remove_desc", {path: P.path})}</p>
    <button class="btn danger" id="prm">${t("remove_proj")}</button></div></div>` : ""}`);
  if ($("#prm")) $("#prm").onclick = async () => {  // out of the dashboard only: the folder and its files stay
    if (!await ask(t("sure_remove_proj", {name: P.name}), true)) return;
    try { await api(`/api/projects/${encodeURIComponent(P.key)}`, {method: "DELETE"}); await loadProjects(); go("#/"); } catch (e) { say(e.message); }
  };
  document.querySelectorAll(".dsave").forEach(b => b.onclick = async () => {
    const id = b.dataset.d, v = document.querySelector(`.dv[data-d="${id}"]`).value, reason = document.querySelector(`.dr[data-d="${id}"]`).value;
    if (!await ask(t("sure_decide", {d: id, v}))) return;
    try { await api(`/api/p/${P.key}/decide/${encodeURIComponent(id)}`, {json: {value: v, reason}}); await refresh(); renderSettings(); } catch (e) { say(e.message); }
  });
  if ($("#xadd")) $("#xadd").onclick = async () => {
    const values = Object.fromEntries([...document.querySelectorAll(".xf")].map(i => [i.dataset.k, i.type === "number" ? +i.value : i.value]));
    try { const j = await api(`/api/p/${P.key}/runs`, {json: {values, note: $("#xnote").value}}); toast(j.id); $("#xnote").value = ""; await refresh(); renderSettings(); } catch (e) { say(e.message); }
  };
  wirePlan(); wireShared(); wireFiles(); wireTemplates();
}

