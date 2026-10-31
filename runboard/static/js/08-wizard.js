/* ================= new-project wizard ================= */
const W = {step: 1, path: "", fs: null, scan: null, kind: "yolo", name: "", description: "", color: "#2c6b5a",
           yolo: {data: "", models: ["yolo11n.pt", "yolo11s.pt"], epochs: 50, imgsz: 640, batch: 16, seeds: "0", exclude_test: true},
           script: {file: "", runs: [{id: "run1", args: ""}], files: [], pip: "", data_dir: "", report: "", metric: "score"},
           backends: ["local"], default_backend: "local", conn: null, preview: null, error: null};
const MODELS = {yolo11: "YOLO11", yolo26: "YOLO26", yolov8: "YOLOv8"};
function wSpec() {
  return {path: W.path, name: W.name, description: W.description, color: W.color, kind: W.kind, backends: W.backends,
          default_backend: W.default_backend,
          yolo: {...W.yolo, seeds: String(W.yolo.seeds).split(/[,\s]+/).filter(Boolean).map(Number)},
          script: {...W.script, pip: W.script.pip.split(/[,\s]+/).filter(Boolean)}};
}
async function renderWizard() {
  setTitle(t("new_project"), `<a href="#/">${t("projects")}</a> / ${t("new_project")}`);
  if (!ME?.local) { morph($("#content"), `<div class="msg warn">${t("local_only")}</div>`); return; }
  if (!W.fs) W.fs = await api("/api/fs").catch(() => ({roots: [], dirs: []}));
  if (W.step === 3 && !W.conn) W.conn = await api("/api/connections").catch(() => null);
  if (stale("new")) return;
  const steps = [t("w_folder"), t("w_kind"), t("w_where"), t("w_review")];
  const bar = `<div class="stepper">${steps.map((s, i) => `<div class="stp ${i + 1 === W.step ? "on" : i + 1 < W.step ? "done" : ""}"><span>${i + 1 < W.step ? "✓" : i + 1}</span>${s}</div>`).join("")}</div>`;
  let body = "";
  if (W.step === 1) {
    const fs = W.fs;
    body = `<p class="desc">${t("w_folder_desc")}</p>
      <div class="toolbar">${(fs.roots || []).map(r => `<button class="btn" data-dir="${esc(r.path)}">${esc(r.name)}</button>`).join("")}</div>
      <div class="pathrow"><input id="wpath" value="${esc(fs.path || W.path)}" placeholder="C:\\Users\\…\\my-project" spellcheck="false"><button class="btn" id="wgo">${t("open")}</button></div>
      ${fs.path ? `<div class="card fl">${fs.parent ? `<div class="fi" data-dir="${esc(fs.parent)}">↰ ..</div>` : ""}
        ${fs.dirs.length ? fs.dirs.map(d => `<div class="fi" data-dir="${esc(d.path)}"><svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>${esc(d.name)}${d.project ? chip("COMPLETE", "runboard") : ""}</div>`).join("") : `<div class="empty" style="padding:20px">${t("w_no_sub")}</div>`}</div>` : ""}
      <div class="wnav"><span class="muted mono" style="overflow:hidden;text-overflow:ellipsis">${esc(fs.path || "")}</span><button class="btn primary" id="wpick" ${fs.path ? "" : "disabled"}>${t("w_use_folder")}</button></div>`;
  } else if (W.step === 2) {
    const sc = W.scan, y = W.yolo, sp = W.script;
    if (!y.data && sc.datasets.length) y.data = sc.datasets[0].file;
    if (!sp.file && sc.scripts.length) sp.file = sc.scripts[0];
    const ds = sc.datasets.find(d => d.file === y.data);
    const nRuns = y.models.length * Math.max(1, String(y.seeds).split(/[,\s]+/).filter(Boolean).length);
    body = `${sc.has_manifest ? `<div class="msg ok">${t("w_has_manifest")} <button class="btn" id="wexisting" style="margin-left:8px">${t("w_add_existing")}</button></div>` : ""}
      <p class="desc">${t("w_kind_desc")}</p>
      <div class="choices">
        <div class="choice ${W.kind === "yolo" ? "on" : ""}" data-kind="yolo"><b>${t("w_yolo")}</b><span>${t("w_yolo_desc")}</span>${sc.datasets.length ? chip("COMPLETE", t("w_found_ds", {n: sc.datasets.length})) : ""}</div>
        <div class="choice ${W.kind === "script" ? "on" : ""}" data-kind="script"><b>${t("w_script")}</b><span>${t("w_script_desc")}</span>${sc.scripts.length ? chip("", t("w_found_py", {n: sc.scripts.length})) : ""}</div>
      </div>
      ${W.kind === "yolo" ? `<div class="form" style="margin-top:18px">
        <label class="wide">${t("w_dataset")}${sc.datasets.length ? `<select id="ydata">${sc.datasets.map(d => `<option value="${esc(d.file)}" ${d.file === y.data ? "selected" : ""}>${esc(d.file)}</option>`).join("")}</select>` : `<input id="ydata" value="${esc(y.data)}" placeholder="data/data.yaml">`}</label>
        <label>${t("w_epochs")}<input id="yep" type="number" min="1" max="1000" value="${y.epochs}"></label>
        <label>${t("w_imgsz")}<input id="yimg" type="number" min="64" step="32" value="${y.imgsz}"></label>
        <label>${t("w_batch")}<input id="ybatch" type="number" min="1" value="${y.batch}"></label>
        <label>${t("w_seeds")}<input id="yseeds" value="${esc(y.seeds)}" placeholder="0, 1, 2"></label></div>
        ${ds ? `<p class="desc" style="margin-top:10px">${t("w_classes")}: <b>${esc(ds.classes.join(", "))}</b></p>` : `<div class="msg warn" style="margin-top:12px">${t("w_no_ds")}</div>`}
        <h3 class="wh">${t("w_models")}</h3>
        <div class="models">${Object.entries(MODELS).map(([f, label]) => `<div class="mg"><b>${label}</b>${"nsmlx".split("").map(sz => { const m = `${f}${sz}.pt`; return `<label class="tog"><input type="checkbox" class="ym" value="${m}" ${y.models.includes(m) ? "checked" : ""}>${sz}</label>`; }).join("")}</div>`).join("")}</div>
        <p class="desc" style="margin-top:10px">${t("w_runs_will", {n: nRuns})}</p>
        <label class="tog"><input type="checkbox" id="yex" ${y.exclude_test ? "checked" : ""}> ${t("w_exclude_test")}</label>`
      : `<div class="form" style="margin-top:18px">
        <label class="wide">${t("w_script_file")}${sc.scripts.length ? `<select id="sfile">${sc.scripts.map(f => `<option ${f === sp.file ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>` : `<input id="sfile" value="${esc(sp.file)}" placeholder="train.py">`}</label>
        <label class="wide">${t("w_pip")}<input id="spip" value="${esc(sp.pip)}" placeholder="ultralytics timm"></label></div>
        <h3 class="wh">${t("w_runs")}</h3><p class="desc">${t("w_runs_desc")}</p>
        <div class="card tw"><table><tr><th style="width:180px">${t("run")}</th><th>${t("w_args")}</th><th style="width:60px"></th></tr>
        ${sp.runs.map((r, i) => `<tr><td><input class="srid" data-i="${i}" value="${esc(r.id)}" style="width:100%"></td><td><input class="sargs" data-i="${i}" value="${esc(r.args)}" placeholder="--epochs 50 --lr 0.01" style="width:100%"></td><td class="n">${sp.runs.length > 1 ? `<button class="btn danger sdel" data-i="${i}">×</button>` : ""}</td></tr>`).join("")}</table></div>
        <div class="toolbar" style="margin-top:10px"><button class="btn" id="sadd">+ ${t("run")}</button></div>
        <details style="margin-top:8px"><summary>${t("w_advanced")}</summary><div class="form" style="margin-top:12px">
          <label class="wide">${t("w_extra_files")}<select id="sfiles" multiple size="5">${[...sc.scripts, ...sc.configs].filter(f => f !== sp.file).map(f => `<option ${sp.files.includes(f) ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></label>
          <label>${t("w_data_dir")}<input id="sdata" value="${esc(sp.data_dir)}" placeholder="data/"></label>
          <label>${t("w_report")}<input id="sreport" value="${esc(sp.report)}" placeholder="{out}/metrics.json"></label>
          <label>${t("w_metric")}<input id="smetric" value="${esc(sp.metric)}"></label></div></details>`}
      <div class="wnav"><button class="btn" id="wback">← ${t("back")}</button><button class="btn primary" id="wnext">${t("next")} →</button></div>`;
  } else if (W.step === 3) {
    const k = W.conn?.kaggle, l = W.conn?.local || {};
    const kb = kaggleBox(k, async () => { W.conn = null; renderWizard(); });
    body = `<p class="desc">${t("w_where_desc")}</p>
      <div class="choices three">
        <label class="choice ${W.backends.includes("local") ? "on" : ""}"><input type="checkbox" class="wb" value="local" ${W.backends.includes("local") ? "checked" : ""}><b>${t("local_gpu")}</b><span>${l.gpu ? esc(l.gpu) + ` · ${l.total_gb} GB` : t("w_no_gpu")}</span><span>${t("w_local_desc")}</span></label>
        <label class="choice ${W.backends.includes("kaggle") ? "on" : ""}"><input type="checkbox" class="wb" value="kaggle" ${W.backends.includes("kaggle") ? "checked" : ""}><b>Kaggle</b><span>${t("w_kaggle_desc")}</span>${k?.ok ? chip("COMPLETE", t("connected")) : chip("", t("not_connected"))}</label>
        <div class="choice off"><b>Colab</b><span>${t("w_colab_desc")}</span>${chip("", t("planned"))}</div>
      </div>
      ${W.backends.includes("kaggle") && !k?.ok ? `<div class="card" style="margin-top:16px"><div class="cb" id="kbox">${kb.html}</div></div>` : ""}
      ${W.backends.length > 1 ? `<div class="form" style="margin-top:16px;max-width:360px"><label>${t("w_default")}<select id="wdef">${W.backends.map(b => `<option value="${b}" ${b === W.default_backend ? "selected" : ""}>${b === "local" ? t("local_gpu") : "Kaggle"}</option>`).join("")}</select></label></div>` : ""}
      <div class="wnav"><button class="btn" id="wback">← ${t("back")}</button><button class="btn primary" id="wnext" ${W.backends.length ? "" : "disabled"}>${t("next")} →</button></div>`;
    setTimeout(() => { const b = $("#kbox"); if (b) kb.bind(b); });
  } else {
    const pv = W.preview;
    body = `<div class="form"><label>${t("w_name")}<input id="wname" value="${esc(W.name)}"></label>
        <label class="wide">${t("w_desc")}<input id="wdesc" value="${esc(W.description)}" placeholder="${esc(t("w_desc_ph"))}"></label>
        <label>${t("w_color")}<input id="wcolor" type="color" value="${esc(W.color)}" style="height:36px;padding:2px"></label></div>
      <div class="summary">
        <div><span>${t("w_folder")}</span><b class="mono">${esc(W.path)}</b></div>
        <div><span>${t("w_kind")}</span><b>${W.kind === "yolo" ? t("w_yolo") : t("w_script")}</b></div>
        <div><span>${t("w_where")}</span><b>${W.backends.map(b => b === "local" ? t("local_gpu") : "Kaggle").join(" + ")}</b></div>
        <div><span>${t("runs")}</span><b>${pv ? pv.nruns : "—"}</b></div>
      </div>
      ${pv ? `<p class="desc">${t("w_files_will")}: ${Object.keys(pv.files).map(f => `<span class="mono">${esc(f)}</span>`).join(", ")}</p>
        <details><summary>${t("w_show_files")}</summary>${Object.entries(pv.files).filter(([f]) => f.endsWith(".yaml")).map(([f, c]) => `<p class="mono" style="margin:12px 0 0">${esc(f)}</p><pre class="raw">${esc(c)}</pre>`).join("")}</details>` : ""}
      ${W.error ? `<div class="msg bad" style="margin-top:12px">${esc(W.error)}</div>` : ""}
      <div class="wnav"><button class="btn" id="wback">← ${t("back")}</button><button class="btn primary" id="wcreate" ${pv ? "" : "disabled"}>${t("w_create")}</button></div>`;
  }
  morph($("#content"), `<div class="wizard">${bar}<div class="card"><div class="cb">${body}</div></div></div>`);
  wireWizard();
}
function readStep2() {
  const y = W.yolo, sp = W.script;
  if (W.kind === "yolo") {
    if (!$("#yep")) return;
    y.data = $("#ydata").value; y.epochs = +$("#yep").value || y.epochs; y.imgsz = +$("#yimg").value || y.imgsz;
    y.batch = +$("#ybatch").value || y.batch; y.seeds = $("#yseeds").value; y.exclude_test = $("#yex").checked;
    y.models = [...document.querySelectorAll(".ym:checked")].map(x => x.value);
  } else if ($("#sfile")) {
    sp.file = $("#sfile").value; sp.pip = $("#spip").value;
    sp.runs = [...document.querySelectorAll(".srid")].map((x, i) => ({id: x.value, args: document.querySelector(`.sargs[data-i="${i}"]`).value}));
    if ($("#sfiles")) { sp.files = [...$("#sfiles").selectedOptions].map(o => o.value); sp.data_dir = $("#sdata").value; sp.report = $("#sreport").value; sp.metric = $("#smetric").value; }
  }
}
function wireWizard() {
  const open = async dir => { try { W.fs = await api(`/api/fs?path=${encodeURIComponent(dir)}`); renderWizard(); } catch (e) { say(e.message); } };
  document.querySelectorAll("[data-dir]").forEach(el => el.onclick = () => open(el.dataset.dir));
  const on = (id, ev, f) => { const el = $(id); if (el) el["on" + ev] = f; };  // property handlers: re-wiring a patched page is harmless
  on("#wgo", "click", () => open($("#wpath").value));
  on("#wpath", "keydown", e => e.key === "Enter" && open(e.target.value));
  on("#wpick", "click", async () => {
    try { W.scan = await api("/api/wizard/scan", {json: {path: W.fs.path}}); W.path = W.scan.path; W.name = W.scan.name; W.kind = W.scan.suggest;
      W.yolo.data = ""; W.script.file = ""; W.step = 2; renderWizard(); } catch (e) { say(e.message); }
  });
  on("#wexisting", "click", async () => {
    const cmds = W.scan?.commands || [];
    if (cmds.length && !await ask(`${t("w_trust")}\n\n${cmds.join("\n")}`)) return;
    try { const j = await api("/api/projects", {json: {path: W.path}}); await loadProjects(); go(`#/p/${j.key}/overview`); } catch (e) { say(e.message); } });
  document.querySelectorAll("[data-kind]").forEach(el => el.onclick = () => { readStep2(); W.kind = el.dataset.kind; renderWizard(); });
  document.querySelectorAll(".ym, #yseeds, #ydata").forEach(el => el.onchange = () => { readStep2(); renderWizard(); });
  on("#sadd", "click", () => { readStep2(); W.script.runs.push({id: `run${W.script.runs.length + 1}`, args: ""}); renderWizard(); });
  document.querySelectorAll(".sdel").forEach(b => b.onclick = () => { readStep2(); W.script.runs.splice(+b.dataset.i, 1); renderWizard(); });
  document.querySelectorAll(".wb").forEach(cb => cb.onchange = () => {
    W.backends = [...document.querySelectorAll(".wb:checked")].map(x => x.value);
    if (!W.backends.includes(W.default_backend)) W.default_backend = W.backends[0] || "local"; renderWizard();
  });
  on("#wdef", "change", e => W.default_backend = e.target.value);
  on("#wback", "click", () => { if (W.step === 2) readStep2(); W.step--; W.error = null; renderWizard(); });
  on("#wnext", "click", async () => {
    if (W.step === 2) { readStep2(); if (W.kind === "yolo" && !W.yolo.models.length) return say(t("w_pick_model")); }
    if (W.step === 3) await previewWizard();
    W.step++; renderWizard();
  });
  [["#wname", "name"], ["#wdesc", "description"], ["#wcolor", "color"]].forEach(([id, k]) => on(id, "input", e => { W[k] = e.target.value; }));
  on("#wcreate", "click", () => createWizard(false));
}
async function previewWizard() {
  W.error = null;
  try {
    const j = await api("/api/wizard/preview", {json: wSpec()});
    const runsPart = (j.files["runboard_runs.yaml"] || "").split(/^runs:\s*$/m)[1] || "";
    W.preview = {files: j.files, nruns: runsPart.split("\n").filter(l => /^  [^\s#]/.test(l)).length};
  } catch (e) { W.preview = null; W.error = e.message; }
}
async function createWizard(overwrite) {
  try {
    const j = await api("/api/wizard/create", {json: {...wSpec(), overwrite}});
    toast(t("w_created")); await loadProjects(); Object.assign(W, {step: 1, preview: null, scan: null, name: "", error: null}); go(`#/p/${j.key}/overview`);
  } catch (e) {
    if (/Already exists/.test(e.message) && await ask(t("w_overwrite", {f: e.message.replace("Already exists: ", "")}), true)) return createWizard(true);
    W.error = e.message; renderWizard();
  }
}

