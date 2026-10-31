/* ================= helpers ================= */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = (v, d = 2) => v == null || v === "" || Number.isNaN(+v) ? "—" : Number(v).toFixed(d);
const short = v => String(v ?? "").replace(/\.(pt|pth|ckpt)$/, "");
const en = s => `<span lang="en">${esc(s)}</span>`;  // English terms keep their letters under Turkish uppercase (size ≠ SİZE)
const stale = tab => tab === "system" ? route.view !== "system" : tab === "new" ? route.view !== "new" : (route.view !== "project" || route.tab !== tab || P?.key !== route.key);
const fsize = mb => mb == null || mb === "" ? "—" : +mb >= 1024 ? (mb / 1024).toFixed(2) + " GB" : (+mb).toFixed(+mb < 10 ? 1 : 0) + " MB";
const hms = s => [s / 3600, s % 3600 / 60, s % 60].map(x => String(Math.floor(x)).padStart(2, "0")).join(":");
const ACTIVE = ["QUEUED", "STARTING", "RUNNING", "CANCELLING"];
const COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)"];
const PALETTE = ["#2c6b5a", "#2558a8", "#b0562b", "#7a4fa3", "#8a6d1f", "#1f7a8a"];
const chip = (st, txt) => `<span class="chip ${st || ""}">${txt || (st ? t(st) : t("st_none"))}</span>`;
const okColor = c => /^#[0-9a-f]{3,8}$|^[a-z]{3,20}$/i.test(c || "") ? c : null;  // only a colour reaches style=""
const avatar = (p, size) => p.logo ? `<span class="avatar"${size ? ` style="width:${size}px;height:${size}px"` : ""}><img src="/api/p/${p.key}/logo" alt=""></span>`
  : `<span class="avatar" style="background:${okColor(p.color) || PALETTE[[...p.key].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length]}${size ? `;width:${size}px;height:${size}px` : ""}">${esc((p.name || p.key).split(/[\s\-_]+/).map(w => w[0]).join("").slice(0, 2).toLocaleUpperCase(LANG))}</span>`;
function signedOut() {  // the browser dropped the login: say so instead of failing silently
  if (document.querySelector("#signin")) return;
  const d = document.createElement("div"); d.id = "signin"; d.className = "msg warn"; d.style.cssText = "position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:30";
  d.innerHTML = `${t("signed_out")} <button class="btn" style="margin-left:8px" data-href="/pair">${t("sign_in")}</button>`; document.body.append(d);
}
// Screens are built as HTML strings and patched into what is already on the page: nodes that did not change stay,
// so scroll positions, focus, open menus and half-typed inputs survive every update. [data-keep] fills itself.
function morph(el, html) {
  const tpl = document.createElement("template"); tpl.innerHTML = html;
  patchKids(el, tpl.content);
}
function patchKids(a, b) {
  const an = [...a.childNodes], bn = [...b.childNodes];
  bn.forEach((n, i) => { const o = an[i]; if (!o) a.append(n); else if (sameNode(o, n)) patchNode(o, n); else a.replaceChild(n, o); });
  for (let i = bn.length; i < an.length; i++) an[i].remove();
}
const sameNode = (o, n) => o.nodeType === n.nodeType && o.nodeName === n.nodeName && (o.nodeType !== 1 || (o.id || "") === (n.id || ""));
function patchNode(o, n) {
  if (o.nodeType !== 1) { if (o.nodeValue !== n.nodeValue) o.nodeValue = n.nodeValue; return; }
  if (o.hasAttribute("data-keep")) return;
  const isInput = o.tagName === "INPUT", oldVal = isInput && o.getAttribute("value"), oldChk = isInput && o.hasAttribute("checked");
  for (const {name, value} of [...n.attributes]) if (o.getAttribute(name) !== value) o.setAttribute(name, value);
  for (const {name} of [...o.attributes]) if (!n.hasAttribute(name) && !(name === "open" && o.tagName === "DETAILS")) o.removeAttribute(name);
  if (isInput) {  // follow the new markup only where it changed, so what someone typed or ticked is not undone
    if (o.hasAttribute("checked") !== oldChk) o.checked = o.hasAttribute("checked");
    if (o.getAttribute("value") !== oldVal && o !== document.activeElement) o.value = o.getAttribute("value") ?? "";
    return;
  }
  if (o.tagName === "SELECT" && o === document.activeElement) return;
  patchKids(o, n);
}
function toast(msg, kind = "") { const d = document.createElement("div"); d.className = "toast " + kind; d.textContent = msg; d.setAttribute("role", kind ? "alert" : "status"); document.body.append(d); setTimeout(() => d.remove(), kind ? 9000 : 6000); }
const say = msg => toast(msg, "bad");  // errors: the dashboard's own notice instead of the browser's alert box
// Questions in the dashboard's own dialog: keyboard (Enter / Esc), the interface language, and a red button when
// something is removed or stopped. Resolves to true or false.
function ask(msg, danger = false) {
  return new Promise(resolve => {
    const d = document.createElement("dialog");
    d.className = "form-dlg askdlg";
    d.innerHTML = `<div class="db"><p class="askmsg"></p></div><div class="df"><button type="button" class="btn" data-a="0">${t("dismiss")}</button><button type="button" class="btn ${danger ? "danger solid" : "primary"}" data-a="1">${t("ok")}</button></div>`;
    d.querySelector(".askmsg").textContent = msg;
    let settled = false;
    const done = v => { if (settled) return; settled = true; if (d.open) d.close(); d.remove(); resolve(v); };
    d.querySelectorAll("[data-a]").forEach(b => b.onclick = () => done(b.dataset.a === "1"));
    d.oncancel = e => { e.preventDefault(); done(false); };  // Esc
    d.onclose = () => done(false);
    document.body.append(d);
    d.showModal();
    d.querySelector(`[data-a="${danger ? 0 : 1}"]`).focus();  // Enter never removes anything by accident
  });
}
async function api(path, opts = {}) {
  if (opts.json) opts = {...opts, method: opts.method || "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(opts.json)};
  const r = await fetch(location.origin + path, opts);
  if (r.status === 401) { signedOut(); throw new Error(t("signed_out")); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(errText(j) || r.statusText), {code: j.code});
  return j;
}
// Server errors come with a code and values (runboard/errors.py); English uses the server's own text.
const ERR_TR = {
  one_of: "{field}: şunlardan biri olmalı: {choices}", range: "{field}: {lo} ile {hi} arasında olmalı", required: "{field}: boş bırakılamaz",
  number: "{field}: sayı olmalı", bool: "{field}: true ya da false olmalı", file: "{field}: proje içinde {pattern} biçiminde bir dosya olmalı",
  empty: "{field}: boş", not_editable: "Düzenlenebilir bir alan değil: {fields}", bad_key: "Geçersiz ayar adı: {key}",
  bad_run_id: "Koşu kodu '{run}': harf, rakam, '-', '_' ya da '.'; en çok 41 karakter",
  locked: "Bu plan ön kayıtlı: kararlarıyla değişir ya da ek deney eklenir (ortak ayarlar ve dosyanın kendisi salt okunur).",
  started: "Bu koşu başladı; ayarları olduğu gibi kalır. Değiştirmek için kopyala.", started_entry: "{run} başladı; satırı çalıştığı gibi kalmalı",
  no_extras: "Bu proje ek deneye izin vermiyor (runboard.yaml içinde runs.extras)", extras_direct: "Ön kayıtlı plana yalnızca ek deney eklenir; doğrudan eklenir",
  not_extra: "Yalnızca ek deneyler silinebilir", launched: "Başlatılmış bir koşu silinemez", unknown_run: "Böyle bir koşu yok: {run}",
  exists: "{run} zaten var", block_only: "Burada yalnızca satır başına bir koşu yazılmış dosyalardan silinebilir",
  not_section: "'{name}' bir ortak ayar bölümü değil", run_mapping: "{run}: bir koşu alan–değer çiftlerinden oluşmalı",
  keep_runs: "Dosyada koşuların bulunduğu '{section}:' bölümü kalmalı", stay_mapping: "'{section}' alan–değer bölümü olarak kalmalı",
  yaml_line: "satır {line}: YAML yazım hatası ({problem})", yaml: "Geçerli YAML değil: {problem}", broken: "{problem}", file_mapping: "{file} alan–değer biçiminde olmalı",
  section_missing: "{file} içinde '{section}' bulunamadı", would_break: "Bu değişiklik {file} dosyasını bozardı: {problem}",
  plan_key: "plan.yaml içinde '{key}' bölümü olmaz; dosya sorular, hipotezler, protokol, gruplar, kararlar ve kilit içerir", plan_shape: "{what} şöyle olmalı: {shape}",
  plan_ref: "{item}, olmayan bir şeye başvuruyor: {ref}", plan_dup: "{id} iki kez kullanılmış", not_v2: "Bu projede henüz plan.yaml yok; önce `runboard migrate` çalıştır",
  already_v2: "Bu proje zaten plan.yaml kullanıyor", in_plan: "{key} bu projede plan.yaml içinde durur", keep_version: "Manifest sürümü yalnızca `runboard migrate` ile değişir",
  manifest_runs: "runboard.yaml'da runs.file var olan bir koşu dosyasını göstermeli", migrate_by_hand: "{what} geçişin taşıyamayacağı biçimde yazılmış; elle taşı",
  criterion: "Ölçüt: {problem}", evidence: "{file}: {problem}", already_locked: "Plan zaten kilitli",
  deviation_reason: "Plan kilitli: neden değiştiğini yaz (en az 10 karakter); değişiklik sapma olarak kaydedilir",
  not_locked: "Plan kilitli değil", research: "Araştırma planı: {problem}", unknown_template: "{name} adında bir şablon yok", not_template: "{file} bu şablondan yazılmamış; başka bir yol seç",
  owned: "{file} senin değişikliklerini içeriyor; runboard onu bir daha yazmaz", template_param: "{field}: şöyle yaz: {shape}", bad_path: "{path}: proje içinde bir .py dosyası ver",
  not_as_intended: "{file} istendiği gibi çıkmadı; hiçbir şey yazılmadı", conflict: "{file} bu sayfa açıldıktan sonra değişti; yeniden yükleyip tekrar dene",
  unknown_decision: "Böyle bir karar yok", finish_first: "Önce bütün aday koşular bitmeli", from_candidates: "Değer aday koşulardan birinden gelmeli",
  reason_short: "Bir gerekçe yaz (en az 10 karakter)", decided: "Bu karar zaten verildi",
  no_manifest: "{path} bulunamadı (examples/ ve docs/manifest.md'ye bak)", not_ready: "{run}: {fields} henüz belirlenmedi",
  unknown_backend: "Bilinmeyen ortam: {backend}", not_configured: "{backend} bu proje için ayarlanmamış", busy: "{backend} meşgul: {runs}",
  unknown_job: "Bilinmeyen iş", no_resume: "{backend} için sürdürme komutu yok (runboard.yaml'da backends.<ad>.resume)",
  cannot_resume: "Yalnızca duran (hata vermiş ya da durdurulmuş) bir koşu, çalıştığı ortamda sürdürülebilir", resume_missing: "Önceki çıktı bulunamadı: {path}", job_running: "Zaten çalışan bir iş var: {job}", not_on_kaggle: "{data} henüz Kaggle'da değil (Veri sekmesi)", kaggle_error: "Kaggle reddetti: {problem}",
  no_local_command: "runboard.yaml içinde backends.local.command tanımlı değil", only_finished_delete: "Yalnızca bitmiş koşular silinebilir", not_launched: "Henüz başlatılmadı; durdurulacak bir şey yok",
  foreign_kernel: "Bu koşu runboard'un oluşturmadığı bir not defterine bağlı; Kaggle'dan sil", unknown_project: "Böyle bir proje yok",
  not_run_yet: "Henüz çalıştırılmadı", nothing_selected: "Hiçbir şey seçilmedi",
  queue_unknown: "{run} kuyrukta değil", queue_has: "{run} zaten kuyrukta",
  queue_quota: "{run} için Kaggle kotası yetmiyor: yaklaşık {need} saat gerekiyor, {left} saat kaldı",
  sweep_empty: "Taranan her alan için en az bir değer seç", sweep_too_many: "{n} koşu oluşacaktı; sınır {limit}",
  local_only: "Yalnızca runboard'un çalıştığı bilgisayardan yapılabilir", not_paired: "Bu cihaz eşleşmemiş", wrong_code: "Kod yanlış ya da süresi dolmuş",
  lan_off: "Önce tablet erişimini aç", unknown_device: "Böyle bir cihaz yok", bad_token: "Bu bir Kaggle API anahtarına benzemiyor (Settings → API Tokens → Generate New Token)",
  token_rejected: "Kaggle anahtarı reddetti: {why}", autostart_windows: "Otomatik başlatma yalnızca Windows'ta; başka sistemlerde servis yöneticisini kullan",
  not_folder: "Klasör değil: {path}", choose_dataset: "Veri setinin YAML dosyasını seç (sınıfları ve train/val klasörlerini listeler)",
  choose_script: "Eğitim betiğini seç", add_run: "En az bir koşu ekle",
};
function errText(j) {
  if (!j?.code) return j?.detail;
  const tpl = LANG === "tr" ? ERR_TR[j.code] : null;
  if (!tpl) return j.detail;
  const p = j.params || {}, txt = tpl.replace(/\{(\w+)\}/g, (_, k) => p[k] ?? "");
  return j.run && !tpl.includes("{run}") ? `${j.run}: ${txt}` : txt;
}
const ICONS = {
  projects: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  overview: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
  runs: '<path d="M4 19V5M4 19h16M8 15l3-4 3 2 5-6"/>',
  settings: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  data: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  results: '<path d="M4 20h16M7 16V9M12 16V5M17 16v-4"/>',
  hypotheses: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3"/><path d="M7.5 15h9"/>',
  system: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};

/* ================= state & routing ================= */
let ME = null, PS = null, P = null, route = {}, detail = null, sub = store("rb-sub") || "charts", allLog = false;
let compare = new Set(), compCache = {}, prevStatus = {}, activeDetail = null, SYS = null;
function parseRoute() {
  const h = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (h[0] === "p" && h[1]) return {view: "project", key: h[1], tab: h[2] || "overview", run: h[3] ? decodeURIComponent(h[3]) : null};
  if (h[0] === "system") return {view: "system"};
  if (h[0] === "new") return {view: "new"};
  return {view: "home"};
}
function go(h) { if (location.hash === h) render(); else location.hash = h; }
// The keyboard: Enter or Space on a focused link, chart title or legend item does what a click does.
document.addEventListener("keydown", e => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches?.('[tabindex="0"][data-go], [tabindex="0"][data-open], .chart .lg')) {
    e.preventDefault(); e.target.click();
  }
});
// Links of the page: data-go (a dashboard route), data-lang, data-href. No inline handlers, so the content security
// policy can refuse every script that is not the page's own.
document.addEventListener("click", e => {
  const el = e.target.closest?.("[data-go], [data-lang], [data-href]");
  if (!el || e.defaultPrevented) return;
  if (el.dataset.go != null) go(el.dataset.go);
  else if (el.dataset.lang) setLang(el.dataset.lang);
  else if (el.dataset.href) location.href = el.dataset.href;
});
window.addEventListener("hashchange", () => { route = parseRoute(); detail = null; render(); window.scrollTo(0, 0); });
const run = id => P?.runs.find(r => r.id === id);
const runHref = id => `#/p/${route.key}/runs/${encodeURIComponent(id)}`;      // run list + details side by side
const runPage = id => `#/p/${route.key}/run/${encodeURIComponent(id)}`;       // details alone, full width

/* ================= live estimate ================= */
function live(r) {
  const p = r?.progress || {}, now = Date.now() / 1000, on = ACTIVE.includes(r?.status);
  const epochs = p.epochs || r?.epochs || 1, ep = p.epoch || 0, cur = p.current_epoch || ep;
  let batch = p.batch, est = false;
  if (on && p.beat_at && p.its && p.batches && cur > ep && batch != null) {
    const dt = Math.max(0, now - p.beat_at); batch = Math.min(p.batches, Math.floor(batch + p.its * dt)); est = dt > 1.5;
  }
  const inEpoch = on && batch != null && p.batches && cur > ep;
  const frac = r?.status === "COMPLETE" ? 1 : Math.min(1, (ep + (inEpoch ? batch / p.batches : 0)) / epochs);
  return {on, frac, batch, batches: p.batches, cur, ep, epochs, est, inEpoch, val: inEpoch && batch >= p.batches,
          left: on && p.eta_at ? Math.max(0, p.eta_at - now) : null, epLeft: inEpoch && p.its ? Math.max(0, (p.batches - batch) / p.its) : null};
}
const lbl = (L, done) => `${t("epoch")} ${done ?? L.ep}/${L.epochs}` + (L.inEpoch ? ` · e${L.cur} ${L.val ? t("validating") : `${t("batch")} ${L.batch}/${L.batches}`}${L.est && !L.val ? " ≈" : ""}` : "");
function findRun(pkey, id) { if (P && P.key === pkey) return run(id); return PS?.projects.find(x => x.key === pkey)?.active.find(r => r.id === id); }
function tick() {
  document.querySelectorAll("[data-live]").forEach(el => {
    const r = findRun(el.dataset.p, el.dataset.run); if (!r) return;
    const L = live(r), k = el.dataset.live;
    if (k === "bar") el.style.width = (L.frac * 100).toFixed(2) + "%";
    else if (k === "pct") el.textContent = (L.frac * 100).toFixed(1) + "%";
    else if (k === "lbl") el.textContent = lbl(L);
    else if (k === "left") el.textContent = L.left != null ? hms(L.left) : "—";
    else if (k === "epleft") el.textContent = L.epLeft != null ? (L.val ? t("validating") : `${t("ep_left")} ${t("left")} ${hms(L.epLeft)}`) : "";
    else if (k === "pill") el.textContent = `e${L.inEpoch ? L.cur : L.ep}/${L.epochs} · ${(L.frac * 100).toFixed(1)}%${L.left != null ? " · " + hms(L.left) : ""}`;
  });
}
setInterval(tick, 1000);
const L_ = (k, pkey, id, inner = "") => `data-live="${k}" data-p="${pkey}" data-run="${esc(id)}"`;

