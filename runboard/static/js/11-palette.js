/* ================= quick search (Ctrl+K) ================= */
// One box to reach anything: projects, the pages of the open project, its runs, and a few actions (new project,
// theme, language). Type to narrow it, arrows to move, Enter to go, Escape to close.
let PAL = null;
function palItems() {
  const out = [], k = P?.key, inP = route.view === "project" && P;
  for (const p of PS?.projects || []) out.push({group: t("projects"), label: p.name, sub: p.path, go: `#/p/${p.key}/overview`});
  if (inP) {
    for (const tab of ["overview", "runs", "settings", "code", ...(P.has_data ? ["data"] : []), "results", ...(P.v2 ? ["hypotheses"] : [])])
      out.push({group: P.name, label: t(tab), go: `#/p/${k}/${tab}`});
    for (const r of P.runs) out.push({group: t("runs"), label: r.id, sub: [t(r.status || "st_none"), ...Object.values(r.fields || {}).map(short)].join(" · "), go: runPage(r.id)});
  }
  out.push({group: t("pal_actions"), label: t("new_project"), go: "#/new"}, {group: t("pal_actions"), label: t("system"), go: "#/system"});
  for (const th of ["dark", "light", "auto"]) out.push({group: t("pal_actions"), label: `${t("theme")}: ${t("th_" + th)}`, act: () => document.querySelector(`[data-theme-set=${th}]`)?.click()});
  for (const l of ["en", "tr"]) out.push({group: t("pal_actions"), label: l === "en" ? "English" : "Türkçe", act: () => setLang(l)});
  return out;
}
function palOpen() {
  let dlg = $("#paldlg");
  if (!dlg) {
    dlg = document.createElement("dialog"); dlg.id = "paldlg"; dlg.className = "form-dlg paldlg"; document.body.append(dlg);
    dlg.addEventListener("close", () => { PAL = null; });
    dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });  // a click outside the box closes it
  }
  PAL = {items: palItems(), q: "", i: 0};
  dlg.innerHTML = `<input id="palq" type="text" autocomplete="off" spellcheck="false" placeholder="${esc(t("pal_ph"))}" aria-label="${esc(t("pal_ph"))}"><div id="pall" role="listbox"></div><div class="palh">${t("pal_hint")}</div>`;
  const q = $("#palq");
  q.oninput = () => { PAL.q = q.value; PAL.i = 0; palPaint(); };
  q.onkeydown = e => {
    const n = palShown().length;
    if (e.key === "ArrowDown") { e.preventDefault(); PAL.i = Math.min(n - 1, PAL.i + 1); palPaint(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); PAL.i = Math.max(0, PAL.i - 1); palPaint(); }
    else if (e.key === "Enter") { e.preventDefault(); palPick(palShown()[PAL.i]); }
  };
  palPaint(); dlg.showModal(); q.focus();
}
// every word typed must appear in the label, the group or the line under it, in any order
function palShown() {
  const words = PAL.q.toLocaleLowerCase(LANG).split(/\s+/).filter(Boolean);
  return PAL.items.filter(x => { const hay = `${x.label} ${x.group} ${x.sub || ""}`.toLocaleLowerCase(LANG); return words.every(w => hay.includes(w)); }).slice(0, 60);
}
function palPaint() {
  const shown = palShown(); let last = null;
  $("#pall").innerHTML = shown.length ? shown.map((x, i) => { const head = x.group !== last ? `<div class="palg">${esc(x.group)}</div>` : ""; last = x.group;
    return `${head}<div class="pali ${i === PAL.i ? "on" : ""}" role="option" aria-selected="${i === PAL.i}" data-pi="${i}"><b>${esc(x.label)}</b>${x.sub ? `<small>${esc(x.sub)}</small>` : ""}</div>`; }).join("")
    : `<div class="empty" style="padding:24px">${t("pal_none")}</div>`;
  $("#pall .pali.on")?.scrollIntoView({block: "nearest"});
  document.querySelectorAll("#pall [data-pi]").forEach(el => el.onclick = () => palPick(shown[+el.dataset.pi]));
}
function palPick(x) {
  if (!x) return;
  $("#paldlg").close();
  if (x.act) x.act(); else go(x.go);
}
$("#palbtn").onclick = () => palOpen();
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); PAL ? $("#paldlg").close() : palOpen(); }
});
