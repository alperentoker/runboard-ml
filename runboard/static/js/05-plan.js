/* ================= the run plan: edit, copy, add, remove ================= */
// Every change is previewed as the exact lines that will change in the runs file, then saved with the version of the
// file this page loaded; if the file changed in between (an editor, git), the server refuses and the plan reloads.
let PLAN = null;
const planCols = () => [...PLAN.order, ...Object.keys(PLAN.fields).filter(k => !PLAN.order.includes(k))];
function planCard() {
  if (!PLAN) return "";
  const cols = planCols(), canAdd = !PLAN.locked;
  const canCopy = !PLAN.locked || PLAN.extra_fields.length;
  const cell = (r, k) => k in r.own ? `<span class="own">${esc(short(r.own[k]))}</span>`
    : r.effective[k] != null ? `<span class="inh">${esc(short(r.effective[k]))}</span>` : `<span class="muted">—</span>`;
  return `<div class="card"><div class="ch"><h2>${t("plan_title")}</h2><span class="muted mono">${esc(PLAN.file)}</span>
      <div class="sp">${canCopy ? `<button class="btn" id="psweep">${t("sweep")}</button> ` : ""}${canAdd ? `<button class="btn primary" id="pnew">+ ${t("new_run")}</button>` : ""}</div></div>
    <div class="cb" style="padding-bottom:4px"><p class="desc" style="margin:0">${t(PLAN.locked ? "plan_locked_desc" : "plan_desc")}</p></div>
    <div class="cb flush tw"><table><tr><th>${t("run")}</th>${cols.map(k => `<th>${en(k)}</th>`).join("")}<th>${t("status")}</th><th></th></tr>
    ${PLAN.runs.map(r => `<tr><td><b>${esc(r.id)}</b>${r.extra ? ` ${chip("", t("extra"))}` : ""}</td>${cols.map(k => `<td>${cell(r, k)}</td>`).join("")}
      <td>${r.why_locked === "locked" ? chip("lock", t("preregistered")) : chip(run(r.id)?.status)}</td>
      <td class="acts">${!r.why_locked ? `<button class="btn" data-pedit="${esc(r.id)}">${t("edit")}</button> ` : ""}${canCopy ? `<button class="btn" data-pcopy="${esc(r.id)}">${t("copy")}</button> ` : ""}${!r.why_locked ? `<button class="btn danger" data-pdel="${esc(r.id)}">${t("remove")}</button>` : ""}</td></tr>`).join("")}</table></div></div>`;
}
function wirePlan() {
  if ($("#pnew")) $("#pnew").onclick = () => runForm("add");
  if ($("#psweep")) $("#psweep").onclick = sweepForm;
  document.querySelectorAll("[data-pedit]").forEach(b => b.onclick = () => runForm("edit", b.dataset.pedit));
  document.querySelectorAll("[data-pcopy]").forEach(b => b.onclick = () => runForm("copy", b.dataset.pcopy));
  document.querySelectorAll("[data-pdel]").forEach(b => b.onclick = () => removeRun(b.dataset.pdel));
}
async function reloadPlan() { PLAN = await api(`/api/p/${P.key}/plan`); if (route.tab === "settings") { await refresh(); renderSettings(); } }
function diffHtml(d) {
  const rows = d.split("\n").filter(l => l && !l.startsWith("---") && !l.startsWith("+++"));
  return `<div class="diff">${rows.map(l => `<div class="${l.startsWith("@@") ? "hunk" : l[0] === "+" ? "add" : l[0] === "-" ? "del" : ""}">${esc(l.startsWith("@@") ? "⋯" : l)}</div>`).join("")}</div>`;
}
function fieldInput(k, rule, value, dflt) {
  const ph = dflt != null ? `${t("default_lbl")}: ${short(dflt)}` : "";
  const v = value == null ? "" : String(value);
  if (rule.choices) return `<select data-f="${esc(k)}"><option value="">${esc(ph ? `— ${ph}` : "—")}</option>${rule.choices.map(c => `<option value="${esc(c)}" ${String(c) === v ? "selected" : ""}>${esc(short(c))}</option>`).join("")}</select>`;
  if (rule.bool) return `<select data-f="${esc(k)}"><option value="">${esc(ph ? `— ${ph}` : "—")}</option>${["true", "false"].map(c => `<option ${c === v ? "selected" : ""}>${c}</option>`).join("")}</select>`;
  const num = rule.int || rule.float;
  return `<input data-f="${esc(k)}" ${num ? `type="number" step="${rule.int ? 1 : "any"}" min="${num[0]}" max="${num[1]}"` : `type="text" spellcheck="false"`} value="${esc(v)}" placeholder="${esc(ph || (rule.file ? rule.file : t("any_value")))}">`;
}
function dialog() {
  let d = $("#dlg");
  if (!d) { d = document.createElement("dialog"); d.id = "dlg"; d.className = "form-dlg"; document.body.append(d); }
  return d;
}
function runForm(mode, rid) {
  const src = rid ? PLAN.runs.find(r => r.id === rid) : null, viaExtra = mode === "copy" && PLAN.locked;
  const keys = viaExtra ? PLAN.extra_fields : planCols().filter(k => PLAN.fields[k]);
  const start = mode === "edit" ? src.own : mode === "copy" ? (viaExtra ? src.effective : src.own) : {};
  const title = mode === "edit" ? t("edit_title", {run: rid}) : mode === "copy" ? t("copy_title", {run: rid}) : t("new_title");
  const d = dialog();
  d.innerHTML = `<form method="dialog"><div class="dh2"><h2>${esc(title)}</h2><span class="sp"></span>${viaExtra ? chip("", t("extra")) : ""}</div>
    <div class="db"><div class="form">
      ${mode !== "edit" && !viaExtra ? `<label>${t("run_id")}<input id="frid" spellcheck="false" placeholder="${esc(mode === "copy" ? `${rid}-copy` : "run")}"></label>` : ""}
      ${keys.map(k => `<label>${en(k)}${fieldInput(k, PLAN.fields[k] || {}, start[k], mode === "edit" || !src ? PLAN.defaults[k] ?? PLAN.fields[k]?.default : src.effective[k])}</label>`).join("")}
      ${mode !== "edit" ? `<label class="wide">${t("note")}<input id="fnote"></label>` : ""}
    </div><div id="fout"></div></div>
    <div class="df"><button type="button" class="btn" id="fx">${t("dismiss")}</button><button class="btn primary" id="fgo" value="">${viaExtra ? t("add") : t("continue_")}</button></div></form>`;
  let reviewed = false;
  const out = $("#fout"), go = $("#fgo");
  $("#fx").onclick = () => d.close();
  const values = () => Object.fromEntries([...d.querySelectorAll("[data-f]")].map(i => [i.dataset.f, i.value === "" ? null : i.value]));
  d.querySelectorAll("input, select").forEach(i => i.oninput = () => { reviewed = false; go.textContent = viaExtra ? t("add") : t("continue_"); out.innerHTML = ""; });
  const send = dry => {
    const body = {values: values(), version: PLAN.version, dry};
    if (mode === "edit") return api(`/api/p/${P.key}/plan/runs/${encodeURIComponent(rid)}`, {method: "PUT", json: body});
    return api(`/api/p/${P.key}/plan/runs`, {json: {...body, id: $("#frid")?.value.trim() || null, copy_from: mode === "copy" ? rid : null, note: $("#fnote")?.value || ""}});
  };
  go.onclick = async e => {
    e.preventDefault(); go.disabled = true;
    try {
      if (viaExtra || reviewed) {
        const j = await send(false); d.close(); toast(`${t("saved")}${j.id ? " · " + j.id : ""}`); await reloadPlan();
      } else {
        const j = await send(true);
        if (!j.diff) out.innerHTML = `<div class="msg warn" style="margin-top:12px">${t("no_change")}</div>`;
        else { out.innerHTML = `<p class="desc" style="margin:14px 0 0">${esc(t("diff_title", {f: PLAN.file}))}</p>${diffHtml(j.diff)}`; reviewed = true; go.textContent = t("save"); }
      }
    } catch (err) {
      if (err.code === "conflict") { PLAN = await api(`/api/p/${P.key}/plan`); reviewed = false; go.textContent = t("continue_"); out.innerHTML = `<div class="msg warn" style="margin-top:12px">${t("conflict")}</div>`; }
      else out.innerHTML = `<div class="msg bad" style="margin-top:12px">${esc(err.message)}</div>`;
    }
    go.disabled = false;
  };
  d.showModal();
}
/* ================= shared settings and the whole file ================= */
function settingInput(sec, k, v, rule) {
  const a = `data-ss="${esc(sec)}" data-sk="${esc(k)}"`, cur = typeof v === "object" && v !== null ? JSON.stringify(v) : String(v ?? "");
  if (rule?.choices) return `<select ${a} data-orig="${esc(cur)}">${rule.choices.map(c => `<option value="${esc(c)}" ${String(c) === cur ? "selected" : ""}>${esc(short(c))}</option>`).join("")}</select>`;
  if (typeof v === "boolean") return `<select ${a} data-orig="${cur}">${["true", "false"].map(c => `<option ${c === cur ? "selected" : ""}>${c}</option>`).join("")}</select>`;
  return `<input ${a} data-orig="${esc(cur)}" value="${esc(cur)}" spellcheck="false" ${typeof v === "number" ? `type="number" step="any"` : ""}>`;
}
function sharedCard() {
  const secs = Object.entries(PLAN.sections);
  if (!secs.length) return "";
  return `<div class="card" id="sharedcard"><div class="ch"><h2>${t("shared")}</h2><span class="muted mono">${esc(PLAN.file)}</span></div><div class="cb">
    <p class="desc">${t("shared_edit_desc")}</p>
    ${secs.map(([sec, vals]) => `<div class="card tw" style="margin-bottom:12px"><table><tr><th colspan="3">${esc(sec)}</th></tr>
      ${Object.entries(vals).map(([k, v]) => `<tr class="setrow"><td class="mono">${esc(k)}</td><td>${settingInput(sec, k, v, sec === PLAN.defaults_name ? PLAN.fields[k] : null)}</td>
        <td class="acts"><button class="btn danger" data-srm="${esc(sec)}|${esc(k)}" title="${t("remove")}">×</button></td></tr>`).join("")}
      <tr class="setrow"><td><input class="snk" data-sec="${esc(sec)}" placeholder="+ ${esc(t("setting_name"))}" spellcheck="false"></td><td><input class="snv" data-sec="${esc(sec)}" placeholder="${esc(t("value"))}" spellcheck="false"></td><td></td></tr>
    </table></div>`).join("")}
    <div id="sout" data-keep></div>
    <div class="toolbar" style="margin:12px 0 0"><span class="sp"><button class="btn primary" id="sgo">${t("continue_")}</button></span></div></div></div>`;
}
// A whole file in a text box: checked on the server shortly after each pause in typing, saved after its diff is seen.
// Used for the runs file, plan.yaml and runboard.yaml; `n` prefixes the element ids.
function editorCard(n, title, file, desc, extra = "", reason = false) {
  return `<div class="card" id="${n}card"><div class="ch"><h2>${esc(title)}</h2><span class="muted mono">${esc(file)}</span>${extra}<span class="rawstate" id="${n}state"></span></div><div class="cb">
    <p class="desc">${desc}</p><div id="${n}box" data-keep></div><div id="${n}out" data-keep></div>
    ${reason ? `<div class="form" style="margin-top:12px"><label class="wide">${t("h_reason")}<input id="${n}reason" data-keep></label></div>` : ""}
    <div class="toolbar" style="margin:12px 0 0"><span class="sp"><button class="btn" id="${n}reset">${t("restore")}</button> <button class="btn primary" id="${n}go">${t("continue_")}</button></span></div></div></div>`;
}
const rawCard = (deviation = false) => editorCard("raw", t("raw_title"), PLAN.file, t(deviation ? "raw_dev_desc" : "raw_desc"),
  deviation ? chip("lock", t("h_locked")) : "", deviation);
function wireEditor(n, {url, text, version, file, reload}) {
  const box = $(`#${n}box`); if (!box) return;
  if (!box.firstChild) box.innerHTML = `<textarea class="rawed" id="${n}ed" spellcheck="false"></textarea>`;
  const ta = $(`#${n}ed`), st = $(`#${n}state`), out = $(`#${n}out`), go = $(`#${n}go`);
  if (ta.dataset.version !== version) { ta.value = text; ta.dataset.version = version; ta.dataset.orig = text; }
  let timer = null, reviewed = false, lastErr = null;
  const state = (cls, txt) => { st.className = "rawstate " + cls; st.textContent = txt; };
  const reason = $(`#${n}reason`);  // a locked plan: the change is a deviation and needs one
  const send = dry => api(url, {method: "PUT", json: {text: ta.value, version, ...(dry ? {dry: true} : {}), ...(reason ? {reason: reason.value} : {})}});
  const check = async () => {
    reviewed = false; go.textContent = t("continue_"); out.innerHTML = "";
    if (ta.value === ta.dataset.orig) return state("", t("raw_same"));
    try { await send(true); lastErr = null; state("ok", "✓ " + t("raw_ok")); }
    catch (e) { lastErr = e.message; state("bad", "✕ " + e.message); }
  };
  ta.oninput = () => { clearTimeout(timer); timer = setTimeout(check, 600); };
  if (reason) reason.oninput = ta.oninput;
  ta.onkeydown = e => { if (e.key === "Tab") { e.preventDefault(); ta.setRangeText("  ", ta.selectionStart, ta.selectionEnd, "end"); ta.oninput(); } };
  st.onclick = () => {  // jump to the line the error names
    const m = /(?:line|satır) (\d+)/.exec(lastErr || ""); if (!m) return;
    const lines = ta.value.split("\n"), k = Math.min(+m[1], lines.length), pos = lines.slice(0, k - 1).join("\n").length + (k > 1 ? 1 : 0);
    ta.focus(); ta.setSelectionRange(pos, pos + lines[k - 1].length);
    ta.scrollTop = Math.max(0, (k - 4) * parseFloat(getComputedStyle(ta).lineHeight));
  };
  $(`#${n}reset`).onclick = () => { ta.value = ta.dataset.orig; check(); };
  go.onclick = async () => {
    if (ta.value === ta.dataset.orig) return state("", t("raw_same"));
    go.disabled = true;
    try {
      if (reviewed) { await send(false); toast(t("saved")); ta.dataset.version = ""; await reload(); }
      else { const j = await send(true); out.innerHTML = `<p class="desc" style="margin:14px 0 0">${esc(t("diff_title", {f: file}))}</p>${diffHtml(j.diff)}`; reviewed = true; go.textContent = t("save"); state("ok", "✓ " + t("raw_ok")); }
    } catch (e) {
      if (e.code === "conflict") { toast(t("conflict")); ta.dataset.version = ""; await reload(); }
      else { lastErr = e.message; state("bad", "✕ " + e.message); }
    }
    go.disabled = false;
  };
}
// plan.yaml (the science, locked with the plan) and runboard.yaml (how runs start: commands, so this computer only)
let FILES = null;
async function reloadFiles() { if (route.tab === "settings") { await refresh(); renderSettings(); } }
function filesCards() {
  if (!FILES) return "";
  const pl = FILES.files.plan, mf = FILES.files.manifest;
  const ro = (title, f, note) => `<div class="card"><div class="ch"><h2>${esc(title)}</h2><span class="muted mono">${esc(f.file)}</span>${chip("lock", t("readonly"))}</div><div class="cb">
    <p class="desc">${note}</p><details><summary>${esc(f.file)}</summary><pre class="raw">${esc(f.text)}</pre></details></div></div>`;
  const plan = !pl ? `<div class="card"><div class="ch"><h2>${t("plan_file")}</h2></div><div class="cb"><p class="desc">${t("plan_v1")}</p></div></div>`
    : editorCard("pf", t("plan_file"), pl.file, t(FILES.locked ? "plan_dev_desc" : "plan_desc"), FILES.locked ? chip("lock", t("h_locked")) : "", FILES.locked);
  const man = FILES.can_edit_manifest ? editorCard("mf", t("manifest_file"), mf.file, t("manifest_desc")) : ro(t("manifest_file"), mf, t("manifest_remote"));
  return plan + man;
}
function wireFiles() {
  if (!FILES) return;
  const f = FILES.files;
  if (f.plan) wireEditor("pf", {url: `/api/p/${P.key}/files/plan`, text: f.plan.text, version: f.plan.version, file: f.plan.file, reload: reloadFiles});
  if (FILES.can_edit_manifest) wireEditor("mf", {url: `/api/p/${P.key}/files/manifest`, text: f.manifest.text, version: f.manifest.version, file: f.manifest.file, reload: reloadFiles});
}
const affectsHtml = a => !a ? "" : (a.drafts.length || a.started.length) ? `<div class="msg ok" style="margin-top:10px">${a.drafts.length ? `${t("affects_drafts")} <b>${a.drafts.map(esc).join(", ")}</b>` : ""}${a.started.length ? `${a.drafts.length ? "<br>" : ""}${t("affects_started")} ${a.started.map(esc).join(", ")}` : ""}</div>` : `<div class="msg warn" style="margin-top:10px">${t("affects_none")}</div>`;
function wireShared() {
  if (!$("#sharedcard") && !$("#rawbox")) return;
  // shared settings form: removed keys are struck through until saved; the button first shows the diff
  let sReviewed = false;
  const sgo = $("#sgo"), sout = $("#sout");
  const sReset = () => { sReviewed = false; if (sgo) sgo.textContent = t("continue_"); if (sout) sout.innerHTML = ""; };
  document.querySelectorAll("#sharedcard input, #sharedcard select").forEach(i => i.oninput = sReset);
  document.querySelectorAll("[data-srm]").forEach(b => b.onclick = () => { const tr = b.closest("tr"); tr.classList.toggle("rm"); b.textContent = tr.classList.contains("rm") ? "↺" : "×"; sReset(); });
  const changes = () => {
    const out = {};
    document.querySelectorAll("[data-sk]").forEach(i => {
      const sec = i.dataset.ss, rm = i.closest("tr").classList.contains("rm");
      if (rm) (out[sec] ??= {})[i.dataset.sk] = null;
      else if (i.value !== i.dataset.orig) (out[sec] ??= {})[i.dataset.sk] = i.value;
    });
    document.querySelectorAll(".snk").forEach(i => { const v = document.querySelector(`.snv[data-sec="${i.dataset.sec}"]`).value; if (i.value.trim() && v !== "") (out[i.dataset.sec] ??= {})[i.value.trim()] = v; });
    return out;
  };
  if (sgo) sgo.onclick = async () => {
    const ch = Object.entries(changes());
    if (!ch.length) { sout.innerHTML = `<div class="msg warn" style="margin-top:12px">${t("no_change")}</div>`; return; }
    sgo.disabled = true;
    try {
      if (sReviewed) {
        for (const [sec, values] of ch) { const j = await api(`/api/p/${P.key}/plan/section/${encodeURIComponent(sec)}`, {method: "PUT", json: {values, version: PLAN.version}}); PLAN.version = j.version; }
        toast(t("saved")); await reloadPlan();
      } else {
        let html = "";
        for (const [sec, values] of ch) { const j = await api(`/api/p/${P.key}/plan/section/${encodeURIComponent(sec)}`, {method: "PUT", json: {values, version: PLAN.version, dry: true}}); html += diffHtml(j.diff) + affectsHtml(j.affects); }
        sout.innerHTML = `<p class="desc" style="margin:14px 0 0">${esc(t("diff_title", {f: PLAN.file}))}</p>${html}`; sReviewed = true; sgo.textContent = t("save");
      }
    } catch (err) {
      if (err.code === "conflict") { await reloadPlan(); toast(t("conflict")); }
      else sout.innerHTML = `<div class="msg bad" style="margin-top:12px">${esc(err.message)}</div>`;
    }
    sgo.disabled = false;
  };
  wireEditor("raw", {url: `/api/p/${P.key}/plan/raw`, text: PLAN.raw, version: PLAN.version, file: PLAN.file, reload: reloadPlan});
}
/* ================= sweep and queue ================= */
function sweepForm() {
  const locked = PLAN.locked, keys = locked ? PLAN.extra_fields : planCols().filter(k => PLAN.fields[k]);
  const bk = P.backends, d = dialog();
  d.innerHTML = `<form method="dialog"><div class="dh2"><h2>${t("sweep_title")}</h2><span class="sp"></span><b id="swn" class="muted"></b></div>
    <div class="db"><p class="desc" style="margin:0">${locked ? t("sweep_extras") + PLAN.extra_fields.map(esc).join(", ") + ". " : ""}${t("sweep_desc")}</p>
      <div class="sweepf">
        <b>${t("sweep_base")}</b><select id="swbase"><option value="">${t("none_lbl")}</option>${PLAN.runs.map(r => `<option>${esc(r.id)}</option>`).join("")}</select>
        ${locked ? "" : `<b>${t("prefix")}</b><input type="text" id="swpre" value="sweep" spellcheck="false">`}
        ${keys.map(k => { const rule = PLAN.fields[k] || {};
          return `<b>${en(k)}</b>${rule.choices ? `<div class="opts">${rule.choices.map(c => `<label class="tog"><input type="checkbox" data-sw="${esc(k)}" value="${esc(c)}">${esc(short(c))}</label>`).join("")}</div>`
            : `<input type="text" data-sw="${esc(k)}" placeholder="${esc(t("sweep_ph"))}${rule.int ? ` (${rule.int[0]}–${rule.int[1]})` : rule.float ? ` (${rule.float[0]}–${rule.float[1]})` : ""}" spellcheck="false">`}`; }).join("")}
      </div>
      <label class="tog" style="margin-top:14px"><input type="checkbox" id="swq"> ${t("also_queue")}</label>
      ${bk.length > 1 ? `<select id="swb" style="margin-left:8px">${bk.map(b => `<option value="${b.name}" ${b.name === P.default_backend ? "selected" : ""}>${esc(b.label)}</option>`).join("")}</select>` : ""}
      <div id="swout"></div></div>
    <div class="df"><button type="button" class="btn" id="swx">${t("dismiss")}</button><button class="btn primary" id="swgo">${t("continue_")}</button></div></form>`;
  const grid = () => {
    const g = {};
    d.querySelectorAll("[data-sw]").forEach(i => {
      const vals = i.type === "checkbox" ? (i.checked ? [i.value] : []) : i.value.split(",").map(x => x.trim()).filter(Boolean);
      if (vals.length) (g[i.dataset.sw] ??= []).push(...vals);
    });
    return g;
  };
  let reviewed = false;
  const out = $("#swout"), go = $("#swgo"), count = () => { const g = grid(), n = Object.values(g).reduce((a, v) => a * v.length, Object.keys(g).length ? 1 : 0); $("#swn").textContent = t("sweep_count", {n}); };
  d.querySelectorAll("input, select").forEach(i => i.oninput = i.onchange = () => { reviewed = false; go.textContent = t("continue_"); out.innerHTML = ""; count(); });
  $("#swx").onclick = () => d.close();
  count();
  const body = dry => ({grid: grid(), base: $("#swbase").value || null, prefix: $("#swpre")?.value || "", version: PLAN.version, dry});
  go.onclick = async e => {
    e.preventDefault(); go.disabled = true;
    try {
      if (!reviewed) {
        const j = await api(`/api/p/${P.key}/plan/sweep`, {json: body(true)});
        out.innerHTML = j.diff ? `<p class="desc" style="margin:14px 0 0">${esc(t("diff_title", {f: PLAN.file}))}</p>${diffHtml(j.diff)}`
          : `<div class="diff" style="margin-top:14px">${(j.runs || []).map(r => `<div class="add">+ ${esc(flowText(r))}</div>`).join("")}</div>`;
        reviewed = true; go.textContent = t("save");
      } else {
        const j = await api(`/api/p/${P.key}/plan/sweep`, {json: body(false)});
        if ($("#swq").checked && j.ids.length) await api("/api/queue", {json: {project: P.key, runs: j.ids, backend: $("#swb")?.value || P.default_backend}});
        d.close(); toast(`${t("saved")} · ${j.ids.join(", ")}`); await reloadPlan();
      }
    } catch (err) {
      if (err.code === "conflict") { PLAN = await api(`/api/p/${P.key}/plan`); reviewed = false; go.textContent = t("continue_"); }
      out.innerHTML = `<div class="msg ${err.code === "conflict" ? "warn" : "bad"}" style="margin-top:12px">${esc(err.code === "conflict" ? t("conflict") : err.message)}</div>`;
    }
    go.disabled = false;
  };
  d.showModal();
}
const flowText = o => "{" + Object.entries(o).map(([k, v]) => `${k}: ${v}`).join(", ") + "}";
function queueCard(pkey) {
  const all = PS?.queue || [], mine = pkey ? all.filter(e => e.project === pkey) : all;
  if (!mine.length) return "";  // an empty queue takes no room
  const firstOf = {};
  all.forEach(e => { firstOf[e.backend] ??= e.id; });
  const why = e => !e.waiting ? (firstOf[e.backend] === e.id ? t("w_next") : "") : e.waiting.startsWith("error") ? `${t("w_error")}: ${e.waiting.slice(7)}` : t("w_" + e.waiting);
  return `<div class="card" style="margin:16px 0"><div class="ch"><h2>${t("queue")}</h2><span class="muted" style="font-size:12px">${mine.length}</span></div><div class="cb">
    <p class="desc">${t("queue_desc")}</p>
    ${mine.map(e => `<div class="qrow"><span class="n">${all.indexOf(e) + 1}</span>${pkey ? "" : `<span class="muted">${esc(e.project_name)} ·</span>`}
      <b class="click" tabindex="0" role="link" data-go="#/p/${esc(e.project)}/run/${encodeURIComponent(e.run)}">${esc(e.run)}</b><span class="chip">${esc(e.backend_label)}</span>
      ${e.hours ? `<span class="muted">${esc(t("hours_est", {h: e.hours}))}</span>` : ""}<span class="w ${e.waiting?.startsWith("error") ? "bad" : ""}">${esc(why(e))}</span>
      <span class="sp"><button class="btn" data-qmv="${e.id}" data-by="-1" title="${t("up")}">↑</button><button class="btn" data-qmv="${e.id}" data-by="1" title="${t("down")}">↓</button><button class="btn danger" data-qrm="${e.id}" data-run="${esc(e.run)}" title="${t("remove")}">×</button></span></div>`).join("")}
  </div></div>`;
}
// queue buttons live in pages that are redrawn often, so one listener on the document handles them
document.addEventListener("click", async ev => {
  const mv = ev.target.closest("[data-qmv]"), rm = ev.target.closest("[data-qrm]");
  if (!mv && !rm) return;
  try {
    if (mv) await api(`/api/queue/${mv.dataset.qmv}/move`, {json: {by: +mv.dataset.by}});
    else if (await ask(t("sure_dequeue", {run: rm.dataset.run}), true)) await api(`/api/queue/${rm.dataset.qrm}`, {method: "DELETE"});
  } catch (e) { say(e.message); }
  refresh();
});
async function removeRun(rid) {
  let j; try { j = await api(`/api/p/${P.key}/plan/runs/${encodeURIComponent(rid)}?dry=true`, {method: "DELETE"}); } catch (e) { return say(e.message); }
  if (!await ask(`${t("sure_remove_run", {run: rid})}\n\n${j.diff.split("\n").filter(l => l.startsWith("-") && !l.startsWith("---")).join("\n")}`, true)) return;
  try { await api(`/api/p/${P.key}/plan/runs/${encodeURIComponent(rid)}?version=${PLAN.version}`, {method: "DELETE"}); toast(t("saved")); await reloadPlan(); }
  catch (e) { if (e.code === "conflict") { toast(t("conflict")); await reloadPlan(); } else say(e.message); }
}

