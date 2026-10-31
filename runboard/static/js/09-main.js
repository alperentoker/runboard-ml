/* ================= main loop ================= */
async function loadProjects() { PS = await api("/api/projects"); }
function notify() {
  for (const p of PS.projects) for (const r of (P && P.key === p.key ? P.runs : p.active)) {
    const k = p.key + ":" + r.id;
    if (prevStatus[k] && prevStatus[k] !== r.status && ["COMPLETE", "ERROR"].includes(r.status)) {
      const msg = t(r.status === "COMPLETE" ? "toast_done" : "toast_err", {run: `${p.name} · ${r.id}`});
      toast(msg); try { if (Notification.permission === "granted") new Notification("runboard", {body: msg}); } catch {}
    }
    prevStatus[k] = r.status;
  }
}
/* ================= live connection ================= */
// One EventSource per screen. The server sends what changed (projects, the open project, the open run) plus appended
// log and job lines; the page patches itself. The browser reconnects by itself after network drops.
let ES = null, esUrl = "";
function subscribe(force) {
  const q = new URLSearchParams();
  if (route.view === "project") {
    q.set("p", route.key);
    const rid = ["runs", "run"].includes(route.tab) ? route.run : route.tab === "overview" ? P?.runs.find(r => ACTIVE.includes(r.status))?.id : null;
    if (rid) q.set("run", rid);
    if (rid && rid === route.run && sub === "log") { q.set("log", "1"); if (allLog) q.set("all", "1"); }
    if (route.tab === "data") q.set("jobs", route.key);
  } else if (route.view === "system") q.set("jobs", "*");
  const url = "/api/events?" + q;
  if (!force && url === esUrl && ES && ES.readyState !== 2) return;
  ES?.close(); esUrl = url; ES = new EventSource(location.origin + url);
  const on = (name, f) => ES.addEventListener(name, e => { try { f(JSON.parse(e.data)); } catch (err) { console.error(name, err); } });
  on("projects", d => { PS = d; notify(); renderChrome(); if (route.view === "home") renderHome(); });
  on("project", d => { if (d.error || route.view !== "project" || d.key !== route.key) return; P = d; notify(); renderChrome(); projectChanged(); });
  on("run", d => {
    if (d.error || route.view !== "project") return;
    if (route.tab === "overview") { activeDetail = d; renderOverview(); }
    else if (d.id === route.run) { detail = d; renderDetail(); }
  });
  on("log", logEvent);
  on("job", jobEvent);
  ES.onopen = () => setConn(true);
  ES.onerror = () => {
    setConn(false);
    if (ES.readyState === 2) setTimeout(() => api("/api/projects").then(() => subscribe(true)).catch(() => setTimeout(() => subscribe(true), 5000)), 3000);
  };
}
function setConn(ok) { $("#upd").textContent = ok ? `● ${t("conn_live")}` : t("reconnecting"); $("#upd").classList.toggle("off", !ok); }
function projectChanged() {
  if (route.tab === "overview") { renderOverview(); subscribe(); }
  else if (route.tab === "runs") renderRunsTab();
  else if (route.tab === "run") renderRunPage();
  else if (route.tab === "results") renderResults();
}
async function render() {
  route = parseRoute();
  if (route.view === "project") {
    if (!P || P.key !== route.key) { try { P = await api(`/api/p/${route.key}`); } catch (e) { $("#content").innerHTML = `<div class="msg bad">${esc(e.message)}</div>`; return; } }
    const onRun = route.tab === "run";
    setTitle(onRun ? route.run : t(route.tab), `<a href="#/">${t("projects")}</a> / <a href="#/p/${P.key}/overview">${esc(P.name)}</a>${onRun ? ` / <a href="#/p/${P.key}/runs">${t("runs")}</a>` : ""}`);
    renderChrome();
    if (route.tab !== "runs") $("#content").innerHTML = "";
    ({overview: renderOverview, runs: renderRunsTab, run: renderRunPage, settings: renderSettings, data: renderData, results: renderResults})[route.tab]?.();
  } else {
    P = null; renderChrome();
    route.view === "system" ? renderSystem() : route.view === "new" ? renderWizard() : renderHome();
  }
  subscribe();
}
// After an action: fetch at once instead of waiting for the next event.
async function refresh() {
  try {
    await loadProjects();
    if (route.view === "project") { P = await api(`/api/p/${route.key}`); }
    notify(); renderChrome();
    if (route.view === "home") renderHome();
    if (route.view === "project" && route.tab === "overview") renderOverview();
    if (route.view === "project" && route.tab === "runs") renderRunsTab();
    if (route.view === "project" && route.tab === "run") renderRunPage();
  } catch (e) { setConn(false); }
}
try { if (window.Notification && Notification.permission === "default") document.addEventListener("click", () => Notification.requestPermission(), {once: true}); } catch {}
if (store("rb-side") === "mini") $("#app").classList.add("mini-side");
$("#collapse").onclick = () => { const on = $("#app").classList.toggle("mini-side"); store("rb-side", on ? "mini" : "full"); };
document.documentElement.lang = LANG;
Promise.all([loadProjects(), api("/api/me").then(m => { ME = m; })]).then(render).catch(() => { $("#upd").textContent = t("unreachable"); });
