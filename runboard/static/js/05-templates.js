/* ================= code templates (runboard/templating.py) ================= */
// Scripts written into the project from runboard's templates. A file nobody changed is "unchanged" and can be
// rewritten (new parameters, a newer template); once changed it is the user's and runboard leaves it alone.
let TPL = null;
const TPL_STATE = {pristine: ["COMPLETE", "tpl_pristine"], owned: ["lock", "tpl_owned"], missing: ["ERROR", "tpl_missing"], untracked: ["ERROR", "tpl_untracked"]};
function paramInput(k, rule, v) {
  const val = v ?? rule.default, shown = Array.isArray(val) ? val.join(", ") : val && typeof val === "object" ? Object.entries(val).map(([a, b]) => `${a}=${b}`).join(", ") : String(val ?? "");
  if (rule.bool) return `<label class="chk"><input type="checkbox" data-tp="${esc(k)}" ${val ? "checked" : ""}> ${esc(k)}</label>`;
  if (rule.choices) return `<label>${esc(k)}<select data-tp="${esc(k)}">${rule.choices.map(c => `<option ${c === val ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>`;
  return `<label>${esc(k)}<input data-tp="${esc(k)}" value="${esc(shown)}" spellcheck="false" ${rule.int || rule.float ? `type="number" step="any"` : ""}></label>`;
}
function templatesCard() {
  if (!TPL) return "";
  const rows = TPL.files.map(f => { const [cls, key] = TPL_STATE[f.state] || ["", f.state];
    return `<tr><td class="mono">${esc(f.path)}</td><td>${esc(f.template)} ${esc(f.version || "")}</td><td>${chip(cls, t(key))}${f.update ? ` ${chip("QUEUED", t("tpl_update", {v: f.latest}))}` : ""}</td>
      <td class="acts">${TPL.can_write && f.state === "pristine" ? `<button class="btn" data-tedit="${esc(f.path)}">${t(f.update ? "tpl_do_update" : "tpl_change")}</button>` : ""}</td></tr>`; }).join("");
  return `<div class="card" id="tplcard"><div class="ch"><h2>${t("tpl_title")}</h2></div><div class="cb">
    <p class="desc">${t("tpl_desc")}</p>
    ${rows ? `<div class="card tw" style="margin-bottom:12px"><table><tr><th>${t("h_file")}</th><th>${t("tpl_template")}</th><th>${t("status")}</th><th></th></tr>${rows}</table></div>` : ""}
    ${TPL.can_write ? `<div class="form"><label>${t("tpl_add")}<select id="tplsel"><option value="">—</option>${TPL.catalog.map(c => `<option value="${esc(c.name)}">${esc(tx(c.title))}</option>`).join("")}</select></label></div>
      <div id="tplform" data-keep></div>` : `<div class="msg warn">${t("tpl_local")}</div>`}</div></div>`;
}
function openTemplate(name, path, params) {
  const c = TPL.catalog.find(x => x.name === name), box = $("#tplform"); if (!c || !box) return;
  box.innerHTML = `<div class="card" style="margin-top:12px"><div class="cb"><p class="desc"><b>${esc(tx(c.title))}</b> · ${esc(tx(c.desc))}</p>
    <div class="form">${Object.entries(c.params).map(([k, r]) => paramInput(k, r, params?.[k])).join("")}
      <label class="wide">${t("tpl_path")}<input id="tplpath" value="${esc(path || c.target)}" spellcheck="false"></label>
      ${TPL.locked ? `<label class="wide">${t("h_reason")}<input id="tplreason"></label>` : ""}</div>
    <div id="tplout"></div><div class="toolbar" style="margin:12px 0 0"><span class="sp"><button class="btn" id="tplx">${t("cancel")}</button> <button class="btn primary" id="tplgo">${t("continue_")}</button></span></div></div></div>`;
  let reviewed = false;
  const go = $("#tplgo"), out = $("#tplout");
  const body = dry => ({params: Object.fromEntries([...box.querySelectorAll("[data-tp]")].map(i => [i.dataset.tp, i.type === "checkbox" ? i.checked : i.value])),
    path: $("#tplpath").value, dry, ...($("#tplreason") ? {reason: $("#tplreason").value} : {})});
  box.querySelectorAll("input").forEach(i => i.oninput = () => { reviewed = false; go.textContent = t("continue_"); out.innerHTML = ""; });
  $("#tplx").onclick = () => { box.innerHTML = ""; if ($("#tplsel")) $("#tplsel").value = ""; };
  go.onclick = async () => {
    go.disabled = true;
    try {
      const j = await api(`/api/p/${P.key}/templates/${encodeURIComponent(name)}`, {json: body(!reviewed)});
      if (reviewed) { toast(t("saved")); box.innerHTML = ""; await refresh(); renderSettings(); }
      else if (!j.diff) out.innerHTML = `<div class="msg warn" style="margin-top:12px">${t("no_change")}</div>`;
      else { out.innerHTML = `<p class="desc" style="margin:14px 0 0">${esc(t("diff_title", {f: j.path}))}</p>${diffHtml(j.diff)}`; reviewed = true; go.textContent = t("save"); }
    } catch (e) { out.innerHTML = `<div class="msg bad" style="margin-top:12px">${esc(e.message)}</div>`; }
    go.disabled = false;
  };
}
function wireTemplates() {
  if (!TPL || !$("#tplcard")) return;
  if ($("#tplsel")) $("#tplsel").onchange = e => e.target.value ? openTemplate(e.target.value) : ($("#tplform").innerHTML = "");
  document.querySelectorAll("[data-tedit]").forEach(b => b.onclick = () => {
    const f = TPL.files.find(x => x.path === b.dataset.tedit); if (f) openTemplate(f.template, f.path, f.params);
  });
}
