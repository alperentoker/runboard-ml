/* ================= project: code (runboard/code.py) ================= */
// The project's scripts and configs: read anywhere, changed on this computer only. The text box sits over a
// highlighted copy of itself; saving shows the diff first and the server compiles Python before it writes.
let CODE = {key: null, list: null, open: null, filter: ""};
const HL = {
  py: /(#[^\n]*)|("""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|[rbfu]?"(?:\\.|[^"\\\n])*"|[rbfu]?'(?:\\.|[^'\\\n])*')|\b(\d+(?:\.\d+)?(?:e-?\d+)?)\b|\b(def|class|return|if|elif|else|for|while|in|import|from|as|with|try|except|finally|raise|not|and|or|is|None|True|False|lambda|yield|pass|break|continue|global|nonlocal|assert|async|await|del)\b|(@[\w.]+)/g,
  yaml: /(#[^\n]*)|("(?:\\.|[^"\\\n])*"|'(?:[^'\n]|'')*')|(^[ \t]*-?[ \t]*[\w.\-/]+(?=:(?:\s|$)))|\b(\d+(?:\.\d+)?)\b|\b(true|false|null|yes|no)\b/gm,
  json: /()("(?:\\.|[^"\\\n])*"(?=\s*:))|("(?:\\.|[^"\\\n])*")|\b(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)\b|\b(true|false|null)\b/g,
  sh: /(#[^\n]*)|("(?:\\.|[^"\\\n])*"|'[^'\n]*')|(\$\{?\w+\}?)|\b(\d+)\b|\b(if|then|else|fi|for|do|done|in|case|esac|function|export|echo|cd)\b/g,
};
const HL_CLS = {py: ["c", "s", "n", "k", "d"], yaml: ["c", "s", "k", "n", "b"], json: ["c", "k", "s", "n", "b"], sh: ["c", "s", "v", "n", "k"]};
function highlight(text, path) {
  const ext = (path.split(".").pop() || "").toLowerCase();
  const lang = ext === "py" ? "py" : ["yaml", "yml"].includes(ext) ? "yaml" : ["json", "ipynb"].includes(ext) ? "json" : ["sh", "ps1"].includes(ext) ? "sh" : null;
  if (!lang) return esc(text);
  let out = "", last = 0;
  text.replace(HL[lang], (m, ...g) => {
    const at = g[g.length - 2], i = g.slice(0, 5).findIndex(x => x !== undefined && x !== "");
    if (i < 0 || !m) return m;
    out += esc(text.slice(last, at)) + `<span class="h${HL_CLS[lang][i]}">${esc(m)}</span>`; last = at + m.length; return m;
  });
  return out + esc(text.slice(last));
}
function codeList() {
  const f = CODE.filter.toLowerCase(), items = CODE.list.files.filter(x => !f || x.path.toLowerCase().includes(f));
  let dir = null;
  return items.map(x => {
    const d = x.path.includes("/") ? x.path.slice(0, x.path.lastIndexOf("/")) : "", name = x.path.slice(d.length ? d.length + 1 : 0);
    const head = d !== dir ? `<div class="cdir">${esc(d || "/")}</div>` : ""; dir = d;
    return head + `<div class="cfile ${CODE.open?.path === x.path ? "on" : ""}" tabindex="0" role="link" data-cf="${esc(x.path)}">${esc(name)}
      ${x.template ? `<span class="muted">${esc(x.template)}</span>` : ""}${x.locked ? " 🔒" : ""}${x.special ? ` <span class="muted">${t("c_settings")}</span>` : ""}</div>`;
  }).join("") + (CODE.list.more ? `<div class="desc">${t("c_more")}</div>` : "");
}
function codeEditor() {
  const o = CODE.open;
  if (!o) return `<div class="empty" style="padding:30px">${t("c_pick")}</div>`;
  const item = CODE.list.files.find(x => x.path === o.path) || {};
  const tpl = o.template ? chip(o.template.state === "owned" ? "lock" : "COMPLETE", `${o.template.template} ${o.template.version} · ${t(o.template.state === "owned" ? "tpl_owned" : "tpl_pristine")}`) : "";
  const ro = !CODE.list.can_write || o.special;
  return `<div class="ch"><h2 class="mono" style="font-size:14px">${esc(o.path)}</h2>${o.new ? chip("QUEUED", t("c_new")) : ""}${tpl}${item.locked ? chip("lock", t("h_locked")) : ""}<span class="rawstate" id="cstate"></span></div>
    <div class="cb">
      ${o.special ? `<div class="msg warn">${t("c_special")} <a href="#/p/${P.key}/settings">${t("settings")}</a></div>` : ""}
      ${!CODE.list.can_write ? `<div class="msg warn">${t("c_local")}</div>` : ""}
      ${o.template?.state === "pristine" && !ro ? `<p class="desc">${t("c_tpl_note")}</p>` : ""}
      <div id="cbox" data-keep></div><div id="cout" data-keep></div>
      ${ro ? "" : `${item.locked && CODE.list.locked ? `<div class="form" style="margin-top:12px"><label class="wide">${t("h_reason")}<input id="creason" data-keep></label></div>` : ""}
      <div class="toolbar" style="margin:12px 0 0"><span class="sp"><button class="btn" id="creset">${t("restore")}</button> <button class="btn primary" id="cgo">${t("continue_")}</button></span></div>`}</div>`;
}
async function openCode(path, isNew = false) {
  if (isNew) CODE.open = {path, text: "", version: null, new: true};
  else { try { CODE.open = await api(`/api/p/${P.key}/code/file?path=${encodeURIComponent(path)}`); } catch (e) { return say(e.message); } }
  store(`rb-code-${P.key}`, path); renderCode();
}
async function renderCode() {
  if (CODE.key !== P.key) CODE = {key: P.key, list: null, open: null, filter: ""};
  try { CODE.list = await api(`/api/p/${P.key}/code`); } catch (e) { if (!stale("code")) $("#content").innerHTML = `<div class="msg bad">${esc(e.message)}</div>`; return; }
  if (stale("code")) return;
  if (!CODE.open) { const last = store(`rb-code-${P.key}`); if (last && CODE.list.files.some(f => f.path === last && !f.big)) return openCode(last); }
  morph($("#content"), `<div class="codewrap">
    <div class="card codelist"><div class="cb"><input id="cfilter" value="${esc(CODE.filter)}" placeholder="${esc(t("c_filter"))}" spellcheck="false">
      ${CODE.list.can_write ? `<div class="pathrow" style="margin:8px 0 0"><input id="cnewpath" placeholder="scripts/new.py" spellcheck="false"><button class="btn" id="cnew">+</button></div>` : ""}
      <div class="cfiles">${codeList()}</div></div></div>
    <div class="card codeed">${codeEditor()}</div></div>`);
  wireCode();
}
function wireCode() {
  document.querySelectorAll("[data-cf]").forEach(el => el.onclick = () => { const f = CODE.list.files.find(x => x.path === el.dataset.cf); if (f?.big) return say(t("c_big")); openCode(el.dataset.cf); });
  if ($("#cfilter")) $("#cfilter").oninput = e => { CODE.filter = e.target.value; $(".cfiles").innerHTML = codeList(); wireCode(); };
  if ($("#cnew")) $("#cnew").onclick = () => { const p = $("#cnewpath").value.trim(); if (p) openCode(p, true); };
  const o = CODE.open, box = $("#cbox"); if (!o || !box) return;
  const ro = !CODE.list.can_write || o.special;
  if (!box.firstChild) box.innerHTML = `<div class="codeedit"><pre aria-hidden="true"><code id="chl"></code></pre><textarea id="ced" spellcheck="false" wrap="off"></textarea></div>`;
  const ta = $("#ced"), hl = $("#chl"), st = $("#cstate"), out = $("#cout"), go = $("#cgo");
  const paint = () => { hl.innerHTML = highlight(ta.value, o.path) + "\n"; hl.parentElement.scrollTop = ta.scrollTop; hl.parentElement.scrollLeft = ta.scrollLeft; };
  if (ta.dataset.path !== o.path || ta.dataset.version !== String(o.version)) { ta.value = o.text; ta.dataset.path = o.path; ta.dataset.version = String(o.version); ta.dataset.orig = o.text; }
  ta.readOnly = !!ro; paint();
  ta.onscroll = () => { hl.parentElement.scrollTop = ta.scrollTop; hl.parentElement.scrollLeft = ta.scrollLeft; };
  if (ro) return;
  let reviewed = false, timer = null;
  const state = (cls, txt) => { st.className = "rawstate " + cls; st.textContent = txt; };
  const send = dry => api(`/api/p/${P.key}/code/file`, {method: "PUT", json: {path: o.path, text: ta.value, version: o.version, dry, ...($("#creason") ? {reason: $("#creason").value} : {})}});
  const check = async () => {
    reviewed = false; go.textContent = t("continue_"); out.innerHTML = "";
    if (ta.value === ta.dataset.orig && !o.new) return state("", t("raw_same"));
    try { await send(true); state("ok", "✓ " + t("c_ok")); } catch (e) { state("bad", "✕ " + e.message); }
  };
  ta.oninput = () => { paint(); clearTimeout(timer); timer = setTimeout(check, 600); };
  ta.onkeydown = e => { if (e.key === "Tab") { e.preventDefault(); ta.setRangeText("    ", ta.selectionStart, ta.selectionEnd, "end"); ta.oninput(); } };
  $("#creset").onclick = () => { ta.value = ta.dataset.orig; ta.oninput(); };
  go.onclick = async () => {
    go.disabled = true;
    try {
      if (reviewed) { await send(false); toast(t("saved")); CODE.open = null; await openCode(o.path); }
      else { const j = await send(true); if (!j.diff) { state("", t("raw_same")); } else { out.innerHTML = `<p class="desc" style="margin:14px 0 0">${esc(t("diff_title", {f: o.path}))}</p>${diffHtml(j.diff)}`; reviewed = true; go.textContent = t("save"); state("ok", "✓ " + t("c_ok")); } }
    } catch (e) { if (e.code === "conflict") { toast(t("conflict")); CODE.open = null; await openCode(o.path); } else state("bad", "✕ " + e.message); }
    go.disabled = false;
  };
}
