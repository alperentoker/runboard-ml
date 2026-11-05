/* ================= new-project wizard ================= */
// Steps depend on the kind: a research project adds its questions, designs, protocol and hypotheses (research.py).
const W = {step: 1, path: "", fs: null, scan: null, kind: "yolo", name: "", description: "", color: "#2c6b5a",
           yolo: {data: "", models: ["yolo11n.pt", "yolo11s.pt"], epochs: 50, imgsz: 640, batch: 16, seeds: "0", exclude_test: true},
           script: {file: "", runs: [{id: "run1", args: ""}], files: [], pip: "", data_dir: "", report: "{out}/summary.json", metric: "score", curves: "", epoch_column: "epoch", prereg: false},
           research: null, rmeta: null, remote: {host: "", workdir: "~/runboard/{project}", python: "python3", partition: "", gres: "gpu:1", time: "12:00:00"},
           backends: ["local"], default_backend: "local", conn: null, preview: null, error: null};
const MODELS = {yolo11: "YOLO11", yolo26: "YOLO26", yolov8: "YOLOv8"};
const DESIGN_TYPES = ["transfer", "curve", "architecture", "ablation"];
const ARCH = "yolov8s.pt, yolo11s.pt, yolo26s.pt";  // what an architecture design compares until you tick others
const ALL_MODELS = Object.keys(MODELS).flatMap(f => "nsmlx".split("").map(sz => `${f}${sz}.pt`));
// A card says what a choice does, what it does not and what it needs, so nobody finds out three steps later.
const limits = k => `<div class="wlim"><span class="wl-h">${t("w_can")}</span>${t(`w_${k}_can`).split("|").map(x => `<span class="wl-y">${esc(x)}</span>`).join("")}<span class="wl-h">${t("w_cant")}</span>${t(`w_${k}_cant`).split("|").map(x => `<span class="wl-n">${esc(x)}</span>`).join("")}<span class="wl-h">${t("w_needs")}</span><span class="wl-r">${esc(t(`w_${k}_needs`))}</span></div>`;
const about = step => `<div class="wabout"><b>${t("w_this_step")}</b> ${t("w_about_" + (step === "protocol" && W.kind === "script" ? "protocol_code" : step))}</div>`;
// the model of a design as a list of the known ones; anything else is still typed
const msel = (path, val) => { const known = ALL_MODELS.includes(val); return `<select data-r="${path}" class="wmsel">${ALL_MODELS.map(m => `<option ${m === val ? "selected" : ""}>${m}</option>`).join("")}<option value="" ${known ? "" : "selected"}>${t("w_other_model")}</option></select>${known ? "" : rin(path, val, "my-model.pt", "wmother")}`; };
const codePrereg = () => W.kind === "script" && W.script.prereg;  // your own code, pre-registered
const stepIds = () => ["folder", "kind", ...(W.kind === "research" ? ["questions", "design", "protocol", "hypotheses"]
  : codePrereg() ? ["questions", "protocol", "hypotheses"] : []), "where", "review"];
const cur = () => stepIds()[W.step - 1];
const list = v => String(v ?? "").split(/[,\s]+/).filter(Boolean);
function newResearch() {
  const pk = (W.scan?.datasets || []).map(d => ({key: (d.file.split("/").slice(-2, -1)[0] || "data").toLowerCase().replace(/[^a-z0-9_]+/g, "_"), data: d.file}));
  const seen = new Set(); pk.forEach((p, i) => { if (seen.has(p.key)) p.key += i; seen.add(p.key); });
  return {packages: pk.length ? pk : [{key: "data", data: ""}], model: "yolo11s.pt", epochs: 100, imgsz: 640, batch: 16,
          questions: [{id: "S1", text: ""}], designs: [{type: "transfer", question: "S1", packages: pk.map(p => p.key).join(", "), seeds: "0"}],
          protocol: {sets: pk.map(p => `${p.key}=${p.data.replace(/[^/]*$/, "")}val.txt`).join(", "), sealed: "", metric: "map50_95", replicates: 200},
          hypotheses: [{id: "H1", question: "S1", text: "", criterion: ""}], check: true, lock: false};
}
// the research plan of the kind chosen: YOLO designs, or questions and hypotheses around your own runs
function newResearchCode() {
  return {packages: [], designs: [], questions: [{id: "S1", text: ""}], hypotheses: [{id: "H1", question: "S1", text: "", criterion: ""}],
          protocol: {sets: "val", sealed: "", metric: "score", script: ""}, lock: false};
}
function useResearch() {
  W.research = W.kind === "research" ? (W.ryolo ??= newResearch()) : codePrereg() ? (W.rcode ??= newResearchCode()) : null;
  W.rmeta = null;
}
function wSpec() {
  const r = W.research && (W.kind === "research" || codePrereg()) && {...W.research, designs: W.research.designs.map(d => ({...d, packages: list(d.packages), models: list(d.type === "architecture" ? d.models ?? ARCH : d.models)}))};
  return {path: W.path, name: W.name, description: W.description, color: W.color, kind: W.kind, backends: W.backends,
          default_backend: W.default_backend,
          yolo: {...W.yolo, seeds: String(W.yolo.seeds).split(/[,\s]+/).filter(Boolean).map(Number)},
          script: {...W.script, pip: W.script.pip.split(/[,\s]+/).filter(Boolean)}, research: r, remote: W.remote};
}
// research inputs carry their place in W.research (data-r="designs.0.fractions"), so one reader serves every step
function readR() {
  document.querySelectorAll("[data-r]").forEach(el => {
    if (el.classList.contains("wmother") && el.previousElementSibling?.value) return;  // a model picked from the list wins
    const k = el.dataset.r.split("."); let x = W.research;
    k.slice(0, -1).forEach(s => x = x[s]); x[k.at(-1)] = el.type === "checkbox" ? el.checked : el.value;
  });
}
const rin = (path, val, ph = "", cls = "") => `<input data-r="${path}" value="${esc(val ?? "")}" placeholder="${esc(ph)}" spellcheck="false" class="${cls}">`;
const qsel = (path, val) => `<select data-r="${path}"><option value="">—</option>${W.research.questions.map(q => `<option ${q.id === val ? "selected" : ""}>${esc(q.id)}</option>`).join("")}</select>`;
const psel = (path, val) => `<select data-r="${path}">${W.research.packages.map(p => `<option ${p.key === val ? "selected" : ""}>${esc(p.key)}</option>`).join("")}</select>`;
function designFields(d, i) {
  const p = `designs.${i}`, f = (label, html, wide) => `<label class="${wide ? "wide" : ""}">${label}${html}</label>`;
  const common = f(t("w_question"), qsel(`${p}.question`, d.question)) + f(t("w_seeds"), rin(`${p}.seeds`, d.seeds, "0, 1, 2"));
  if (d.type === "transfer") return common + f(t("w_pk_list"), rin(`${p}.packages`, d.packages, "ground, aerial"), true);
  if (d.type === "curve") return common + f(t("w_base"), psel(`${p}.base`, d.base)) + f(t("w_add_src"), psel(`${p}.add`, d.add))
    + f(t("w_fractions"), rin(`${p}.fractions`, d.fractions ?? "0.1, 0.25, 0.5")) + f(t("w_group"), rin(`${p}.group`, d.group, "^(vid\\d+)_"));
  if (d.type === "architecture") { const on = list(d.models ?? ARCH);
    return common + f(t("w_package"), psel(`${p}.package`, d.package)) + `<div class="wide"><span class="wl-h">${t("w_models_pick")}</span><div class="models">${Object.entries(MODELS).map(([fam, label]) => `<div class="mg"><b>${label}</b>${"nsmlx".split("").map(sz => { const m = `${fam}${sz}.pt`; return `<label class="tog"><input type="checkbox" class="wdm" data-i="${i}" value="${m}" ${on.includes(m) ? "checked" : ""}>${sz}</label>`; }).join("")}</div>`).join("")}</div></div>`; }
  return common + f(t("w_package"), psel(`${p}.package`, d.package)) + f(t("w_field"), rin(`${p}.field`, d.field, "mosaic")) + f(t("w_values"), rin(`${p}.values`, d.values, "1.0, 0.0"));
}
function designRuns(i) {  // what the server planned for design i (research.py), so a design is never a guess
  const ids = W.rmeta?.designs?.[i], byId = Object.fromEntries((W.rmeta?.runs || []).map(r => [r.id, r]));
  if (!ids?.length) return `<p class="desc wruns-wait">${t("w_design_wait")}</p>`;
  return `<div class="wruns"><b>${t("w_design_runs", {n: ids.length})}</b>${ids.map(id => { const r = byId[id] || {};
    return `<span class="wrun"><b>${esc(id)}</b> ${esc(r.package || "")} · ${esc(String(r.model || "").replace(/\.pt$/, ""))}${r.train ? ` · ${esc(Object.entries(r.train).map(([k, v]) => `${k}=${v}`).join(" "))}` : ""} · seed ${r.seed ?? 0}</span>`; }).join("")}</div>`;
}
function researchBody(step) {
  const r = W.research, del = (kind, i, n) => n > 1 ? `<button class="btn danger" data-rdel="${kind}" data-i="${i}">×</button>` : "";
  if (step === "questions") return `<p class="desc">${t("w_q_desc")}</p>
    <div class="card tw"><table><tr><th style="width:110px">${t("w_id")}</th><th>${t("w_q_text")}</th><th style="width:50px"></th></tr>
    ${r.questions.map((q, i) => `<tr><td>${rin(`questions.${i}.id`, q.id)}</td><td>${rin(`questions.${i}.text`, q.text, t("w_q_ph"), "wfull")}</td><td>${del("questions", i, r.questions.length)}</td></tr>`).join("")}</table></div>
    <div class="toolbar" style="margin-top:10px"><button class="btn" data-radd="questions">+ ${t("w_add_q")}</button></div>`;
  if (step === "design") return `<h3 class="wh">${t("w_packages")}</h3><p class="desc">${t("w_pk_desc")}</p>
    <div class="card tw"><table><tr><th style="width:140px">${t("w_key")}</th><th>${t("w_data_yaml")}</th><th style="width:50px"></th></tr>
    ${r.packages.map((p, i) => `<tr><td>${rin(`packages.${i}.key`, p.key)}</td><td>${(W.scan?.datasets || []).length ? `<select data-r="packages.${i}.data">${W.scan.datasets.map(d => `<option ${d.file === p.data ? "selected" : ""}>${esc(d.file)}</option>`).join("")}</select>` : rin(`packages.${i}.data`, p.data, "data/data.yaml", "wfull")}</td><td>${del("packages", i, r.packages.length)}</td></tr>`).join("")}</table></div>
    <div class="toolbar" style="margin-top:10px"><button class="btn" data-radd="packages">+ ${t("w_add_pk")}</button></div>
    <div class="form" style="margin-top:14px"><label>${t("w_model")}${msel("model", r.model)}</label><label>${t("w_epochs")}${rin("epochs", r.epochs)}</label>
      <label>${t("w_imgsz")}${rin("imgsz", r.imgsz)}</label><label>${t("w_batch")}${rin("batch", r.batch)}</label></div>
    <h3 class="wh">${t("w_designs")}</h3><p class="desc">${t("w_designs_desc")}</p>
    ${r.designs.map((d, i) => `<div class="card" style="margin-bottom:10px"><div class="cb"><div class="form">
      <label>${t("w_type")}<select data-r="designs.${i}.type" class="wdtype">${DESIGN_TYPES.map(x => `<option value="${x}" ${x === d.type ? "selected" : ""}>${t("d_" + x)}</option>`).join("")}</select></label>
      ${designFields(d, i)}<span style="align-self:end">${del("designs", i, r.designs.length)}</span></div>
      <p class="desc" style="margin:8px 0 0">${t("d_" + d.type + "_desc")}</p>${designRuns(i)}</div></div>`).join("")}
    <div class="toolbar"><button class="btn" data-radd="designs">+ ${t("w_add_design")}</button></div>`;
  if (step === "protocol" && W.kind === "script") return `<div class="form"><label class="wide">${t("w_sets_names")}${rin("protocol.sets", r.protocol.sets, "val, test", "wfull")}</label>
      <label>${t("w_sealed")}${rin("protocol.sealed", r.protocol.sealed, "test")}</label><label>${t("w_metric_name")}${rin("protocol.metric", r.protocol.metric)}</label>
      <label class="wide">${t("w_eval_script")}<select data-r="protocol.script"><option value="">—</option>${(W.scan?.scripts || []).map(f => `<option ${f === r.protocol.script ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></label></div>
    <h3 class="wh">${t("w_eval_how")}</h3><pre class="raw">import rb\nids = [path.name for path in items]          # the items of the set, the same for every run\nrb.resample_plan(\"val\", ids)              # the first evaluation fixes them; the rest must match\nfor run in [\"run1\", \"run2\"]:\n    scores = [...]                           # one value per item, in the order of ids\n    rb.write_samples(run, \"val\", {\"score\": scores})</pre>`;
  if (step === "protocol") return `<p class="desc">${t("w_proto_desc")}</p>
    <div class="form"><label class="wide">${t("w_sets")}${rin("protocol.sets", r.protocol.sets, "ground=data/ground/val.txt, aerial=data/aerial/val.txt", "wfull")}</label>
      <label>${t("w_sealed")}${rin("protocol.sealed", r.protocol.sealed, "test")}</label><label>${t("w_metric_name")}${rin("protocol.metric", r.protocol.metric)}</label>
      <label>${t("w_replicates")}${rin("protocol.replicates", r.protocol.replicates)}</label></div>
    <label class="tog" style="margin-top:12px"><input type="checkbox" data-r="check" ${r.check ? "checked" : ""}> ${t("w_check")}</label>`;
  const m = W.rmeta, probs = m?.problems || {};
  const used = new Set(r.hypotheses.map(h => (h.criterion || "").trim()));
  return `<p class="desc">${t("w_h_desc")}</p>
    ${m ? `<div class="summary"><div><span>${t("runs")}</span><b>${m.runs.length}</b></div><div><span>${t("w_sets")}</span><b>${m.sets.map(esc).join(", ")}</b></div>
      <div><span>${t("w_groups")}</span><b>${Object.keys(m.groups).map(esc).join(", ") || "—"}</b></div></div>
      <details style="margin-bottom:10px"><summary>${t("w_planned")}</summary><div class="card tw"><table>${W.kind === "script"
        ? `<tr><th>${t("run")}</th><th>${t("w_args")}</th></tr>${m.runs.map(x => `<tr><td class="mono">${esc(x.id)}</td><td class="mono">${esc(x.args || "")}</td></tr>`).join("")}`
        : `<tr><th>${t("run")}</th><th>${t("w_package")}</th><th>${t("w_model")}</th><th>seed</th></tr>${m.runs.map(x => `<tr><td class="mono">${esc(x.id)}</td><td>${esc(x.package)}${x.train ? ` <span class="muted mono">${esc(JSON.stringify(x.train))}</span>` : ""}</td><td>${esc(x.model)}</td><td>${x.seed ?? 0}</td></tr>`).join("")}`}</table></div></details>` : ""}
    ${r.hypotheses.map((h, i) => `<div class="card" style="margin-bottom:10px" data-wh="${i}"><div class="cb"><div class="form">
      <label>${t("w_id")}${rin(`hypotheses.${i}.id`, h.id)}</label><label>${t("w_question")}${qsel(`hypotheses.${i}.question`, h.question)}</label>
      <label class="wide">${t("w_h_text")}${rin(`hypotheses.${i}.text`, h.text, "", "wfull")}</label>
      <label class="wide">${t("h_criterion")}${rin(`hypotheses.${i}.criterion`, h.criterion, "R2.aerial >= 0.9 * R1.aerial", "wfull mono wcrit")}</label>
      <span style="align-self:end">${del("hypotheses", i, r.hypotheses.length)}</span></div>
      ${probs[h.id] ? `<div class="msg bad" style="margin-top:8px">${esc(probs[h.id])}</div>` : h.criterion?.trim() && m ? `<div class="msg ok" style="margin-top:8px">✓ ${t("w_crit_ok")}</div>` : ""}</div></div>`).join("")}
    <div class="toolbar"><button class="btn" data-radd="hypotheses">+ ${t("w_add_h")}</button></div>
    ${(m?.suggest || []).filter(s => !used.has(s.criterion)).length ? `<h3 class="wh">${t("w_suggest")}</h3>${m.suggest.filter(s => !used.has(s.criterion)).map((s, i) => `<div class="msg ok" style="margin-top:6px"><span class="mono">${esc(s.criterion)}</span> · ${esc(s.text)} <button class="btn" data-ruse="${i}" style="margin-left:8px">${t("w_use")}</button></div>`).join("")}` : ""}`;
}
function fileWhat(f) {  // one line on what each written file is for
  const k = f === "runboard.yaml" ? "manifest" : /runs\.yaml$/.test(f) ? "runs" : f === "runboard_train.py" ? "train" : /(^|\/)rb\.py$/.test(f) ? "rb"
    : f === "plan.yaml" ? "plan" : /evaluate\.py$/.test(f) ? "eval" : /check\.py$/.test(f) ? "check" : /subsets_?\d*\.py$/.test(f) ? "subsets" : f === ".gitignore" ? "ignore" : "";
  return k ? t("f_" + k) : "";
}
async function renderWizard() {
  setTitle(t("new_project"), `<a href="#/">${t("projects")}</a> / ${t("new_project")}`);
  if (!ME?.local) { morph($("#content"), `<div class="msg warn">${t("local_only")}</div>`); return; }
  if (!W.fs) W.fs = await api("/api/fs").catch(() => ({roots: [], dirs: []}));
  if (cur() === "where" && !W.conn) W.conn = await api("/api/connections").catch(() => null);
  if (stale("new")) return;
  const steps = stepIds().map(s => t({folder: "w_folder", kind: "w_kind", questions: "w_questions", design: "w_design", protocol: "w_protocol", hypotheses: "hypotheses", where: "w_where", review: "w_review"}[s]));
  const bar = `<div class="stepper">${steps.map((s, i) => `<div class="stp ${i + 1 === W.step ? "on" : i + 1 < W.step ? "done" : ""}"><span>${i + 1 < W.step ? "✓" : i + 1}</span>${s}</div>`).join("")}</div>`;
  const nav = (next = `<button class="btn primary" id="wnext">${t("next")} →</button>`) => `<div class="wnav"><button class="btn" id="wback">← ${t("back")}</button>${next}</div>`;
  let body = "";
  const step = cur();
  if (step === "folder") {
    const fs = W.fs;
    body = `<p class="desc">${t("w_folder_desc")}</p>
      <div class="toolbar">${(fs.roots || []).map(r => `<button class="btn" data-dir="${esc(r.path)}">${esc(r.name)}</button>`).join("")}</div>
      <div class="pathrow"><input id="wpath" value="${esc(fs.path || W.path)}" placeholder="C:\\Users\\…\\my-project" spellcheck="false"><button class="btn" id="wgo">${t("open")}</button></div>
      ${fs.path ? `<div class="card fl">${fs.parent ? `<div class="fi" data-dir="${esc(fs.parent)}">↰ ..</div>` : ""}
        ${fs.dirs.length ? fs.dirs.map(d => `<div class="fi" data-dir="${esc(d.path)}"><svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>${esc(d.name)}${d.project ? chip("COMPLETE", "runboard") : ""}</div>`).join("") : `<div class="empty" style="padding:20px">${t("w_no_sub")}</div>`}</div>` : ""}
      <div class="wnav"><span class="muted mono" style="overflow:hidden;text-overflow:ellipsis">${esc(fs.path || "")}</span><button class="btn primary" id="wpick" ${fs.path ? "" : "disabled"}>${t("w_use_folder")}</button></div>`;
  } else if (step === "kind") {
    const sc = W.scan, y = W.yolo, sp = W.script;
    if (!y.data && sc.datasets.length) y.data = sc.datasets[0].file;
    if (!sp.file && sc.scripts.length) sp.file = sc.scripts[0];
    const ds = sc.datasets.find(d => d.file === y.data);
    const nRuns = y.models.length * Math.max(1, String(y.seeds).split(/[,\s]+/).filter(Boolean).length);
    body = `${sc.has_manifest ? `<div class="msg ok">${t("w_has_manifest")} <button class="btn" id="wexisting" style="margin-left:8px">${t("w_add_existing")}</button></div>` : ""}
      <p class="desc">${t("w_kind_desc")}</p>
      <div class="choices three">
        <div class="choice ${W.kind === "yolo" ? "on" : ""}" data-kind="yolo"><b>${t("w_yolo")}</b><span>${t("w_yolo_desc")}</span><span class="cwn">${t("w_yolo_when")}</span>${limits("yolo")}${sc.datasets.length ? chip("COMPLETE", t("w_found_ds", {n: sc.datasets.length})) : ""}</div>
        <div class="choice ${W.kind === "research" ? "on" : ""}" data-kind="research"><b>${t("w_research")}</b><span>${t("w_research_desc")}</span><span class="cwn">${t("w_research_when")}</span>${limits("research")}${sc.datasets.length ? chip("COMPLETE", t("w_found_ds", {n: sc.datasets.length})) : ""}</div>
        <div class="choice ${W.kind === "script" ? "on" : ""}" data-kind="script"><b>${t("w_script")}</b><span>${t("w_script_desc")}</span><span class="cwn">${t("w_script_when")}</span>${limits("script")}${sc.scripts.length ? chip("", t("w_found_py", {n: sc.scripts.length})) : ""}</div>
      </div>
      ${W.kind === "research" ? `<p class="desc" style="margin-top:16px">${t("w_research_next")}</p>` : W.kind === "yolo" ? `<div class="form" style="margin-top:18px">
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
        <label class="tog" style="margin-top:14px"><input type="checkbox" id="sprereg" ${sp.prereg ? "checked" : ""}> ${t("w_prereg_code")}</label>
        ${sp.prereg ? `<p class="desc" style="margin:6px 0 0">${t("w_prereg_code_desc")}</p>` : ""}
        <h3 class="wh">${t("w_cmd_preview")}</h3><div class="wcmds">${sp.runs.map(r => `<div class="mono"><span class="muted">${esc(r.id)}</span> python -u ${esc(sp.file || "train.py")} ${esc(r.args)}</div>`).join("")}</div>
        <h3 class="wh">${t("w_watch")}</h3><p class="desc">${t("w_watch_desc")}</p>
        <div class="form"><label>${t("w_report")}<input id="sreport" value="${esc(sp.report)}" placeholder="{out}/metrics.json"></label>
          <label>${t("w_metric")}<input id="smetric" value="${esc(sp.metric)}"></label>
          <label>${t("w_curves")}<input id="scurves" value="${esc(sp.curves)}" placeholder="{out}/history.csv"></label>
          <label>${t("w_epoch_col")}<input id="sepoch" value="${esc(sp.epoch_column)}"></label></div>
        <p class="desc" style="margin-top:6px">${t("w_report_desc")}</p>
        <details style="margin-top:8px"><summary>${t("w_advanced")}</summary><div class="form" style="margin-top:12px">
          <label class="wide">${t("w_extra_files")}<select id="sfiles" multiple size="5">${[...sc.scripts, ...sc.configs].filter(f => f !== sp.file).map(f => `<option ${sp.files.includes(f) ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></label>
          <label>${t("w_data_dir")}<input id="sdata" value="${esc(sp.data_dir)}" placeholder="data/"></label></div></details>`}
      ${nav()}`;
  } else if (["questions", "design", "protocol", "hypotheses"].includes(step)) {
    body = researchBody(step) + (W.error ? `<div class="msg bad" style="margin-top:12px">${esc(W.error)}</div>` : "") + nav();
  } else if (step === "where") {
    const k = W.conn?.kaggle, l = W.conn?.local || {};
    const kb = kaggleBox(k, async () => { W.conn = null; renderWizard(); });
    body = `<p class="desc">${t("w_where_desc")}</p>
      <div class="choices three">
        <label class="choice ${W.backends.includes("local") ? "on" : ""}"><input type="checkbox" class="wb" value="local" ${W.backends.includes("local") ? "checked" : ""}><b>${t("local_gpu")}</b><span>${l.gpu ? esc(l.gpu) + ` · ${l.total_gb} GB` : t("w_no_gpu")}</span><span>${t("w_local_desc")}</span></label>
        <label class="choice ${W.backends.includes("kaggle") ? "on" : ""}"><input type="checkbox" class="wb" value="kaggle" ${W.backends.includes("kaggle") ? "checked" : ""}><b>Kaggle</b><span>${t("w_kaggle_desc")}</span>${k?.ok ? chip("COMPLETE", t("connected")) : chip("", t("not_connected"))}</label>
        <label class="choice ${W.backends.includes("ssh") ? "on" : ""}"><input type="checkbox" class="wb" value="ssh" ${W.backends.includes("ssh") ? "checked" : ""}><b>SSH</b><span>${t("w_ssh_desc")}</span></label>
        <label class="choice ${W.backends.includes("slurm") ? "on" : ""}"><input type="checkbox" class="wb" value="slurm" ${W.backends.includes("slurm") ? "checked" : ""}><b>SLURM</b><span>${t("w_slurm_desc")}</span></label>
        <div class="choice off"><b>Colab</b><span>${t("w_colab_desc")}</span>${chip("", t("planned"))}</div>
      </div>
      ${W.backends.some(b => b === "ssh" || b === "slurm") ? `<div class="form" style="margin-top:16px">
        <label>${t("w_host")}<input data-rm="host" value="${esc(W.remote.host)}" placeholder="gpu-box / user@host" spellcheck="false"></label>
        <label>${t("w_workdir")}<input data-rm="workdir" value="${esc(W.remote.workdir)}" spellcheck="false"></label>
        <label>Python<input data-rm="python" value="${esc(W.remote.python)}" spellcheck="false"></label>
        ${W.backends.includes("slurm") ? `<label>partition<input data-rm="partition" value="${esc(W.remote.partition)}" spellcheck="false"></label>
          <label>gres<input data-rm="gres" value="${esc(W.remote.gres)}" spellcheck="false"></label><label>time<input data-rm="time" value="${esc(W.remote.time)}" spellcheck="false"></label>` : ""}</div>
        <p class="desc" style="margin-top:8px">${t("w_remote_desc")}</p>` : ""}
      ${W.backends.includes("kaggle") && !k?.ok ? `<div class="card" style="margin-top:16px"><div class="cb" id="kbox">${kb.html}</div></div>` : ""}
      ${W.backends.length > 1 ? `<div class="form" style="margin-top:16px;max-width:360px"><label>${t("w_default")}<select id="wdef">${W.backends.map(b => `<option value="${b}" ${b === W.default_backend ? "selected" : ""}>${{local: t("local_gpu"), kaggle: "Kaggle", ssh: "SSH", slurm: "SLURM"}[b]}</option>`).join("")}</select></label></div>` : ""}
      ${nav(`<button class="btn primary" id="wnext" ${W.backends.length ? "" : "disabled"}>${t("next")} →</button>`)}`;
    setTimeout(() => { const b = $("#kbox"); if (b) kb.bind(b); });
  } else {
    const pv = W.preview;
    body = `<div class="form"><label>${t("w_name")}<input id="wname" value="${esc(W.name)}"></label>
        <label class="wide">${t("w_desc")}<input id="wdesc" value="${esc(W.description)}" placeholder="${esc(t("w_desc_ph"))}"></label>
        <label>${t("w_color")}<input id="wcolor" type="color" value="${esc(W.color)}" style="height:36px;padding:2px"></label></div>
      <div class="summary">
        <div><span>${t("w_folder")}</span><b class="mono">${esc(W.path)}</b></div>
        <div><span>${t("w_kind")}</span><b>${t({yolo: "w_yolo", research: "w_research", script: "w_script"}[W.kind])}</b></div>
        <div><span>${t("w_where")}</span><b>${W.backends.map(b => ({local: t("local_gpu"), kaggle: "Kaggle", ssh: "SSH", slurm: "SLURM"}[b])).join(" + ")}</b></div>
        <div><span>${t("runs")}</span><b>${pv ? pv.nruns : "—"}</b></div>
      </div>
      ${W.kind === "research" || codePrereg() ? `<label class="tog"><input type="checkbox" id="wlock" ${W.research.lock ? "checked" : ""}> ${t("w_lock")}</label><p class="desc">${t("w_lock_desc")}</p>` : ""}
      ${pv ? `<h3 class="wh">${t("w_files_title")}</h3><div class="card tw"><table>${Object.keys(pv.files).map(f => `<tr><td class="mono" style="width:40%">${esc(f)}</td><td class="muted">${esc(fileWhat(f))}</td></tr>`).join("")}</table></div>
        <p class="desc" style="margin-top:6px">${t("w_yours_safe")}</p>
        <div class="wabout" style="margin-top:12px"><b>${t("w_after")}</b> ${t("w_after_" + W.kind)}</div>
        <details><summary>${t("w_show_files")}</summary>${Object.entries(pv.files).filter(([f]) => f.endsWith(".yaml")).map(([f, c]) => `<p class="mono" style="margin:12px 0 0">${esc(f)}</p><pre class="raw">${esc(c)}</pre>`).join("")}</details>` : ""}
      ${W.error ? `<div class="msg bad" style="margin-top:12px">${esc(W.error)}</div>` : ""}
      ${nav(`<button class="btn primary" id="wcreate" ${pv ? "" : "disabled"}>${t("w_create")}</button>`)}`;
  }
  morph($("#content"), `<div class="wizard">${bar}<div class="card"><div class="cb">${about(step)}${body}</div></div></div>`);
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
    sp.report = $("#sreport").value; sp.metric = $("#smetric").value; sp.curves = $("#scurves").value; sp.epoch_column = $("#sepoch").value;
    if ($("#sfiles")) { sp.files = [...$("#sfiles").selectedOptions].map(o => o.value); sp.data_dir = $("#sdata").value; }
  }
}
function readStep() { if (cur() === "kind") readStep2(); if (W.research && document.querySelector("[data-r]")) readR(); }
async function checkResearch() {  // the planned runs, suggestions and each criterion's problems, from the server
  try { W.rmeta = (await api("/api/wizard/preview", {json: wSpec()})).research; W.error = null; }
  catch (e) { W.rmeta = null; W.error = e.message; }
}
function wireWizard() {
  const open = async dir => { try { W.fs = await api(`/api/fs?path=${encodeURIComponent(dir)}`); renderWizard(); } catch (e) { say(e.message); } };
  document.querySelectorAll("[data-dir]").forEach(el => el.onclick = () => open(el.dataset.dir));
  const on = (id, ev, f) => { const el = $(id); if (el) el["on" + ev] = f; };  // property handlers: re-wiring a patched page is harmless
  on("#wgo", "click", () => open($("#wpath").value));
  on("#wpath", "keydown", e => e.key === "Enter" && open(e.target.value));
  on("#wpick", "click", async () => {
    try { W.scan = await api("/api/wizard/scan", {json: {path: W.fs.path}}); W.path = W.scan.path; W.name = W.scan.name; W.kind = W.scan.suggest;
      W.yolo.data = ""; W.script.file = ""; W.research = null; W.rmeta = null; W.step = 2; renderWizard(); } catch (e) { say(e.message); }
  });
  on("#wexisting", "click", async () => {
    const cmds = W.scan?.commands || [];
    if (cmds.length && !await ask(`${t("w_trust")}\n\n${cmds.join("\n")}`)) return;
    try { const j = await api("/api/projects", {json: {path: W.path}}); await loadProjects(); go(`#/p/${j.key}/overview`); } catch (e) { say(e.message); } });
  document.querySelectorAll("[data-kind]").forEach(el => el.onclick = () => {
    readStep2(); W.kind = el.dataset.kind; useResearch(); renderWizard();
  });
  document.querySelectorAll(".ym, #yseeds, #ydata, #sfile").forEach(el => el.onchange = () => { readStep2(); renderWizard(); });
  // the command each run gets follows what is typed, without redrawing the inputs being typed in
  document.querySelectorAll(".sargs, .srid").forEach(el => el.oninput = () => {
    readStep2(); const rows = document.querySelectorAll(".wcmds div");
    W.script.runs.forEach((r, i) => { if (rows[i]) rows[i].innerHTML = `<span class="muted">${esc(r.id)}</span> python -u ${esc(W.script.file || "train.py")} ${esc(r.args)}`; });
  });
  on("#sprereg", "change", e => { readStep2(); W.script.prereg = e.target.checked; useResearch(); renderWizard(); });
  on("#sadd", "click", () => { readStep2(); W.script.runs.push({id: `run${W.script.runs.length + 1}`, args: ""}); renderWizard(); });
  document.querySelectorAll(".sdel").forEach(b => b.onclick = () => { readStep2(); W.script.runs.splice(+b.dataset.i, 1); renderWizard(); });
  // research: add and remove rows, switch a design's type, take a suggested hypothesis, check criteria as they are typed
  const blank = {questions: () => ({id: `S${W.research.questions.length + 1}`, text: ""}), packages: () => ({key: "", data: W.scan?.datasets?.[0]?.file || ""}),
                 designs: () => ({type: "architecture", seeds: "0", models: ARCH}), hypotheses: () => ({id: `H${W.research.hypotheses.length + 1}`, question: "", text: "", criterion: ""})};
  // on the design and hypotheses steps a row added or removed changes the planned runs: ask the server again
  const replan = async () => { if (["design", "hypotheses"].includes(cur())) await checkResearch(); renderWizard(); };
  document.querySelectorAll("[data-radd]").forEach(b => b.onclick = () => { readR(); W.research[b.dataset.radd].push(blank[b.dataset.radd]()); replan(); });
  document.querySelectorAll("[data-rdel]").forEach(b => b.onclick = () => { readR(); W.research[b.dataset.rdel].splice(+b.dataset.i, 1); replan(); });
  document.querySelectorAll(".wdtype").forEach(s => s.onchange = async () => { readR(); await checkResearch(); renderWizard(); });
  document.querySelectorAll(".wdm").forEach(cb => cb.onchange = async () => {
    readR(); W.research.designs[+cb.dataset.i].models = [...document.querySelectorAll(`.wdm[data-i="${cb.dataset.i}"]:checked`)].map(x => x.value).join(", ");
    await checkResearch(); renderWizard(); });
  if (cur() === "design") document.querySelectorAll("[data-r]").forEach(el => { if (!el.classList.contains("wdtype")) el.onchange = async () => { readR(); await checkResearch(); renderWizard(); }; });
  document.querySelectorAll("[data-ruse]").forEach(b => b.onclick = async () => {
    readR(); const used = new Set(W.research.hypotheses.map(h => (h.criterion || "").trim()));
    const s = W.rmeta.suggest.filter(x => !used.has(x.criterion))[+b.dataset.ruse];
    const empty = W.research.hypotheses.find(h => !h.criterion?.trim() && !h.text?.trim());
    const h = empty || (W.research.hypotheses.push({id: `H${W.research.hypotheses.length + 1}`}), W.research.hypotheses.at(-1));
    Object.assign(h, {question: s.question || h.question || "", text: s.text, criterion: s.criterion});
    await checkResearch(); renderWizard();
  });
  let timer = null;
  document.querySelectorAll(".wcrit").forEach(i => i.oninput = () => { clearTimeout(timer); timer = setTimeout(async () => { readR(); await checkResearch(); renderWizard(); }, 700); });
  document.querySelectorAll(".wb").forEach(cb => cb.onchange = () => {
    W.backends = [...document.querySelectorAll(".wb:checked")].map(x => x.value);
    if (!W.backends.includes(W.default_backend)) W.default_backend = W.backends[0] || "local"; renderWizard();
  });
  on("#wdef", "change", e => W.default_backend = e.target.value);
  document.querySelectorAll("[data-rm]").forEach(i => i.oninput = () => { W.remote[i.dataset.rm] = i.value; });
  on("#wlock", "change", e => W.research.lock = e.target.checked);
  on("#wback", "click", () => { readStep(); W.step--; W.error = null; renderWizard(); });
  on("#wnext", "click", async () => {
    readStep();
    if (cur() === "kind" && W.kind === "yolo" && !W.yolo.models.length) return say(t("w_pick_model"));
    if (["questions", "protocol"].includes(cur())) await checkResearch();  // the next step shows the planned runs
    if (cur() === "hypotheses" && W.rmeta && Object.keys(W.rmeta.problems).length) { await checkResearch(); return renderWizard(); }
    if (cur() === "where") await previewWizard();
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
    W.preview = {files: j.files, nruns: j.research ? j.research.runs.length : runsPart.split("\n").filter(l => /^  [^\s#]/.test(l)).length};
  } catch (e) { W.preview = null; W.error = e.message; }
}
async function createWizard(overwrite) {
  try {
    const j = await api("/api/wizard/create", {json: {...wSpec(), overwrite}});
    toast(t("w_created")); await loadProjects(); Object.assign(W, {step: 1, preview: null, scan: null, name: "", error: null, research: null, rmeta: null, ryolo: null, rcode: null}); go(`#/p/${j.key}/${W.kind === "research" || codePrereg() ? "hypotheses" : "overview"}`);
  } catch (e) {
    if (/Already exists/.test(e.message) && await ask(t("w_overwrite", {f: e.message.replace("Already exists: ", "")}), true)) return createWizard(true);
    W.error = e.message; renderWizard();
  }
}
