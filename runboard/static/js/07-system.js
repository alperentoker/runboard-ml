/* ================= system ================= */
async function renderSystem() {
  setTitle(t("system_title"), "runboard");
  let s, conn, dv; try { [s, conn, dv] = await Promise.all([api("/api/system"), api("/api/connections"), api("/api/devices")]); } catch (e) { if (!stale("system")) $("#content").innerHTML = `<div class="msg bad">${esc(e.message)}</div>`; return; }
  if (stale("system")) return;
  const row = (k, v) => `<tr><td class="muted">${k}</td><td><b>${v}</b></td></tr>`;
  const kb = kaggleBox(conn.kaggle, () => renderSystem()), L = ME?.local, devs = dv?.devices || [];
  morph($("#content"), `
  <div class="card"><div class="ch"><h2>${t("connections")}</h2></div><div class="cb"><p class="desc">${t("connections_desc")}</p><div id="kbox">${kb.html}</div></div></div>
  <div class="card"><div class="ch"><h2>${t("backends")}</h2></div><div class="cb flush tw"><table>
    ${Object.values(s.backends).map(b => `<tr><td><b>${esc(b.label)}</b></td><td>${b.ok ? chip("COMPLETE", t("available")) : chip("ERROR", t("unavailable"))}</td>
      <td class="muted">${b.ok ? [b.user, b.quota ? `${t("gpu_quota")} ${b.quota.used_h} / ${b.quota.total_h} h` : "", b.gpu ? `${b.gpu} · ${t("gpu_mem", {f: b.free_gb, t: b.total_gb})}` : (b.name === "local" ? t("no_gpu") : "")].filter(Boolean).map(esc).join(" · ") : esc(b.error || "")}</td></tr>`).join("")}
    <tr><td><b>Colab</b></td><td>${chip("", t("planned"))}</td><td class="muted">${t("w_colab_desc")}</td></tr></table></div></div>
  <div class="cols" style="margin-top:16px">
    <div class="card"><div class="ch"><h2>${t("tablet_access")}</h2>${s.lan_on ? chip("COMPLETE", t("on")) : chip("", t("off"))}</div><div class="cb">
      <p class="desc">${t("tablet_desc")}</p>
      ${L ? `<label class="tog"><input type="checkbox" id="lan" ${s.lan_on ? "checked" : ""}> ${t("lan_lbl")}</label>` : `<div class="msg warn">${t("local_only")}</div>`}
      ${s.lan_on ? `<div class="card tw" style="margin-top:12px"><table>${row(t("this_machine"), `http://localhost:${s.port}`)}${row(t("tablet"), esc(s.lan))}${row(t("compact"), esc(s.lan) + "/mini")}</table></div>
        ${L ? `<div class="toolbar" style="margin-top:12px"><button class="btn primary" id="pair">${t("pair_device")}</button></div><div id="pairbox" data-keep></div>` : ""}
        <h3 class="wh">${t("devices")}</h3>
        ${devs.length ? `<div class="card tw"><table><tr><th>${t("device")}</th><th>${t("paired_at")}</th><th>${t("last_seen")}</th><th></th></tr>${devs.map(d => `<tr><td><b>${esc(d.name)}</b>${ME?.device?.id === d.id ? ` <span class="muted">(${t("this_device")})</span>` : ""}</td><td>${esc(d.created)}</td><td>${esc(d.last_seen || "—")}</td><td class="n">${L ? `<button class="btn danger" data-unpair="${esc(d.id)}">${t("remove")}</button>` : ""}</td></tr>`).join("")}</table></div>` : `<p class="desc">${t("no_devices")}</p>`}
        <p class="desc" style="margin:12px 0 0">${t("firewall")}</p>` : ""}
    </div></div>
    <div class="card"><div class="ch"><h2>${t("env")}</h2></div><div class="cb flush tw"><table>${row("runboard", s.version)}${row("python", s.python)}${row("os", esc(s.os))}${row("home", esc(s.home))}${row("disk", `${s.disk.free_gb} / ${s.disk.total_gb} GB`)}</table></div>
      <div class="cb"><div class="toolbar" style="margin:0">${L && s.autostart != null ? `<label class="tog"><input type="checkbox" id="auto" ${s.autostart ? "checked" : ""}> ${t("autostart")}</label>` : ""}<span class="sp"><button class="btn" id="restart">${t("restart_srv")}</button></span></div></div></div>
  </div>
  <div class="card" style="margin-top:16px"><div class="ch"><h2>${t("jobs")}</h2></div><div class="cb"><p class="desc">${t("jobs_desc")}</p>
    ${PS.projects.map(p => `<div class="toolbar">${avatar(p, 24)}<b>${esc(p.name)}</b><span class="sp" id="jb-${p.key}"></span></div><div id="jobbox-${p.key}" data-keep></div>`).join("")}</div></div>`);
  kb.bind($("#kbox"));
  if ($("#auto")) $("#auto").onchange = async e => { try { await api("/api/system/autostart", {json: {on: e.target.checked}}); } catch (err) { say(err.message); e.target.checked = !e.target.checked; } };
  if ($("#lan")) $("#lan").onchange = async e => {
    const on = e.target.checked;
    if (!await ask(t(on ? "sure_lan_on" : "sure_lan_off"))) { e.target.checked = !on; return; }
    try { await api("/api/system/lan", {json: {on}}); toast(t("restarting")); setTimeout(() => location.reload(), 6000); } catch (err) { say(err.message); e.target.checked = !on; }
  };
  if ($("#pair")) $("#pair").onclick = startPairing;
  document.querySelectorAll("[data-unpair]").forEach(b => b.onclick = async () => {
    if (!await ask(t("sure_unpair"), true)) return;
    try { await api(`/api/devices/${b.dataset.unpair}`, {method: "DELETE"}); renderSystem(); } catch (e) { say(e.message); }
  });
  $("#restart").onclick = async () => { if (!await ask(t("sure_restart"))) return; await api("/api/system/restart", {method: "POST"}).catch(() => {}); toast(t("restarting")); setTimeout(() => location.reload(), 6000); };
  const infos = await Promise.all(PS.projects.map(p => api(`/api/p/${p.key}`).catch(() => null)));  // all at once
  if (stale("system")) return;
  for (const [i, p] of PS.projects.entries()) {
    const info = infos[i]; if (!info) continue;
    morph($(`#jb-${p.key}`), Object.entries(info.jobs).filter(([, j]) => !j.per_run).map(([k, j]) => `<button class="btn" data-j="${k}" data-p="${p.key}">${esc(tx(j.title))}</button>`).join(" "));
    showJobs(p.key);
  }
  document.querySelectorAll("[data-j]").forEach(b => b.onclick = async () => {
    if (!await ask(t("sure_job", {j: b.textContent}))) return;
    try { await api(`/api/p/${b.dataset.p}/job/${b.dataset.j}`, {json: {}}); } catch (e) { say(e.message); }
  });
}

// Pairing: a one-time QR code / 6-digit code from the server; the list refreshes once the tablet has used it.
let pairTimer = null;
async function startPairing() {
  clearInterval(pairTimer);
  let p; try { p = await api("/api/devices/pair", {method: "POST"}); } catch (e) { return say(e.message); }
  const box = $("#pairbox"); if (!box) return;
  const before = (await api("/api/devices").catch(() => ({devices: []}))).devices.length, end = Date.now() + p.seconds * 1000;
  box.innerHTML = `<div class="pairing"><div class="qr">${p.qr}</div><div><p class="desc">${t("pair_scan")}</p><p class="desc">${t("pair_or")}<br><span class="mono">${esc(p.base)}</span></p>
    <div class="paircode">${esc(p.code.slice(0, 3))} ${esc(p.code.slice(3))}</div><p class="muted" id="pairleft" style="font-size:12px"></p></div></div>`;
  const step = async () => {
    const left = Math.round((end - Date.now()) / 1000), el = $("#pairleft");
    if (!el) return clearInterval(pairTimer);
    if (left <= 0) { clearInterval(pairTimer); box.innerHTML = `<p class="muted">${t("pair_expired")}</p>`; return; }
    el.textContent = `${t("pair_left")} ${left} s`;
    if (left % 2) return;
    const d = await api("/api/devices").catch(() => null);
    if (d && d.devices.length > before) { clearInterval(pairTimer); box.innerHTML = ""; toast(t("paired_ok", {name: d.devices.at(-1).name})); renderSystem(); }
  };
  step(); pairTimer = setInterval(step, 1000);
}

/* ================= connections (credentials) ================= */
function kaggleBox(k, onDone) {
  // Kaggle connection state; when not connected, a 3-step guide with a single token field.
  const ok = k?.ok;
  if (!ME?.local) return {html: `<div class="conn"><div class="conn-h"><b>Kaggle</b>${ok ? chip("COMPLETE", t("connected")) : chip("", t("not_connected"))}<span class="muted" style="font-size:12px">${ok ? esc(k.user || "") : ""}</span></div><p class="desc" style="margin:8px 0 0">${t("local_only")}</p></div>`, bind: () => {}};
  const html = `<div class="conn">
    <div class="conn-h"><b>Kaggle</b>${ok ? chip("COMPLETE", t("connected")) : chip("", t("not_connected"))}<span class="muted" style="font-size:12px">${ok ? `${esc(k.user)}${k.quota ? ` · ${t("gpu_quota")} ${k.quota.used_h} / ${k.quota.total_h} h` : ""}` : ""}</span></div>
    ${ok ? `<p class="desc" style="margin:8px 0 0">${t("token_where")} <span class="mono">${esc(k.file)}</span>${k.source === "env" ? " (KAGGLE_API_TOKEN)" : ""}</p>
      <div class="toolbar" style="margin:10px 0 0"><button class="btn" data-k="replace">${t("replace_token")}</button><button class="btn danger" data-k="forget">${t("disconnect")}</button></div>
      <div class="kform hide">` : `<ol class="steps">
        <li>${t("k_step1")} <a href="https://www.kaggle.com/settings/api" target="_blank" rel="noopener">kaggle.com/settings/api ↗</a></li>
        <li>${t("k_step2")}</li><li>${t("k_step3")}</li></ol><div class="kform">`}
      <div class="tokenrow"><input type="password" class="ktok" autocomplete="off" spellcheck="false" placeholder="KGAT_…" aria-label="Kaggle API token"><button class="btn primary" data-k="save">${t("save_test")}</button></div>
      <p class="desc" style="margin:6px 0 0">${t("token_note")}</p>${k && !k.installed ? `<div class="msg warn" style="margin-top:8px">pip install kaggle</div>` : ""}</div></div>`;
  const bind = root => {
    const on = (k, f) => { const b = root.querySelector(`[data-k="${k}"]`); if (b) b.onclick = f; };
    on("replace", () => root.querySelector(".kform").classList.toggle("hide"));
    on("forget", async () => {
      if (!await ask(t("sure_disconnect"), true)) return;
      await api("/api/connections/kaggle", {method: "DELETE"}).catch(e => say(e.message)); onDone?.();
    });
    on("save", async e => {
      const inp = root.querySelector(".ktok"), b = e.target; if (!inp.value.trim()) return inp.focus();
      b.disabled = true; b.textContent = "…";
      try { await api("/api/connections/kaggle", {json: {token: inp.value.trim()}}); inp.value = ""; toast(t("kaggle_ok")); await loadProjects(); onDone?.(); }
      catch (err) { say(err.message); b.disabled = false; b.textContent = t("save_test"); }
    });
  };
  return {html, bind};
}

