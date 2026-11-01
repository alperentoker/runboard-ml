/* ================= project: hypotheses (plan.yaml, docs/design-v2.md) ================= */
// Questions and their hypotheses, each with the verdict runboard computes from the evaluation files: the margin of
// every comparison on the whole set and its 95 % interval over the shared bootstrap replicates.
// Each verdict has its own colour and its own mark, so the two never depend on colour alone.
const VERDICT_MARK = {supported: "✓", refuted: "✕", indistinguishable: "≈", not_ready: "◷", invalid: "!", no_criterion: "–"};
const verdictChip = v => `<span class="vchip ${esc(v)}"><b aria-hidden="true">${VERDICT_MARK[v] || ""}</b>${t("v_" + v)}</span>`;
const num = v => v == null ? "—" : (+v).toFixed(2);
const sgn = v => v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
const extent = p => Math.max(Math.abs(p.margin ?? 0), ...(p.ci || []).map(Math.abs)) || 0;
function niceExtent(e) { const tk = niceTicks(0, e || 1, 2), st = tk[1] - tk[0] || 1; return {e: Math.ceil((e || 1) / st - 1e-9) * st, st}; }
// The margin on an axis centred on zero: right of zero favours the hypothesis.
const fpos = (v, e) => 50 + v / e * 45;
function forestBar(p, e) {
  if (!p) return `<div class="fp"><span class="z" style="left:50%"></span></div>`;
  const [a, b] = p.ci || [p.margin, p.margin];
  return `<div class="fp v-${esc(p.verdict)}"><span class="z" style="left:50%"></span>${p.ci ? `<span class="ci" style="left:${fpos(a, e)}%;width:${fpos(b, e) - fpos(a, e)}%"></span>` : ""}<span class="pt" style="left:${fpos(p.margin, e)}%"></span></div>`;
}
function forestCard(hs) {
  const rows = hs.flatMap(h => (h.parts || []).length ? h.parts.map((p, i) => ({h, p, first: i === 0})) : [{h, p: null, first: true}]);
  if (!rows.some(r => r.p)) return "";
  const ex = rows.filter(r => r.p).map(r => extent(r.p)).filter(x => x > 0);
  const own = ex.length > 1 && Math.max(...ex) / Math.min(...ex) > 25;  // one axis would squash the small ones to dots
  const {e: E, st} = niceExtent(Math.max(...ex, 0) * 1.05);
  let ticks = []; for (let v = -E; v <= E + st * 1e-6; v += st) ticks.push(+v.toFixed(8));
  if (ticks.length > 7) ticks = ticks.filter(v => Math.round(v / st) % 2 === 0);
  const row = ({h, p, first}) => {
    const e = own ? niceExtent(extent(p || {}) * 1.05).e : E;
    return `<div class="frow" tabindex="0" role="link" data-hgo="${esc(h.id)}"><span class="fid">${first ? esc(h.id) : ""}</span>
      <span class="ftx" title="${esc(p?.text || h.criterion || "")}">${esc(p?.text || h.criterion || "—")}</span><span>${verdictChip(p?.verdict || h.verdict)}</span>
      ${p ? forestBar(p, e) : `<div class="fp"><span class="wait">${h.missing?.length ? `${t("h_waiting")} ${h.missing.map(esc).join(", ")}` : ""}</span></div>`}
      <span class="fnum">${p ? `${sgn(p.margin)} <span>${p.ci ? `[${sgn(p.ci[0])}, ${sgn(p.ci[1])}]` : ""}</span>` : ""}</span>
      <span class="fnum">${p?.share == null ? "" : `<span>${p.share}%</span>`}</span></div>`;
  };
  return `<div class="card"><div class="ch"><h2>${t("h_glance")}</h2><span class="muted" style="font-size:12px">${t("h_glance_desc")}</span></div>
    <div class="frow head"><span></span><span>${t("h_comparison")}</span><span></span><span class="faxis" style="height:auto"><span class="l" style="left:0">← ${t("h_against")}</span><span class="r" style="left:100%">${t("h_for")} →</span>&nbsp;</span><span style="text-align:right">${t("h_margin")} [95 %]</span><span style="text-align:right">&gt; 0</span></div>
    ${rows.map(row).join("")}
    <div class="frow head" style="padding-top:2px;padding-bottom:10px"><span></span><span></span><span></span>${own ? `<span class="muted" style="text-transform:none;letter-spacing:0;font-weight:500">${t("h_own_scale")}</span>`
      : `<div class="faxis">${ticks.map(v => `<span style="left:${fpos(v, E)}%">${v > 0 ? "+" : v < 0 ? "−" : ""}${+Math.abs(v).toFixed(4)}</span>`).join("")}</div>`}<span></span><span></span></div></div>`;
}
function histCard(p) {
  const hs = p.hist; if (!hs) return "";
  const n = hs.n, top = Math.max(...n) || 1, w = (hs.hi - hs.lo) / n.length || 1, reps = n.reduce((a, b) => a + b, 0);
  const [a, b] = p.ci || [-Infinity, Infinity], zero = (0 - hs.lo) / (hs.hi - hs.lo) * 100;
  const z = zero >= 0 && zero <= 100 ? `<span class="z" style="left:${zero}%"><span>0</span></span>`
    : zero < 0 ? `<span class="off l">← ${t("h_zero_left")}</span>` : `<span class="off r">${t("h_zero_right")} →</span>`;
  return `<div class="hist v-${esc(p.verdict)}"><div class="t"><b title="${esc(p.text)}">${esc(p.text)}</b><span>${reps} ${t("h_reps")}</span></div>
    <div class="hbars" role="img" aria-label="${esc(t("h_dist"))}: ${esc(p.text)}">${n.map((k, i) => { const c = hs.lo + (i + .5) * w; return `<i class="${c >= a && c <= b ? "in" : ""}" style="height:${k / top * 100}%" title="${num(hs.lo + i * w)} … ${num(hs.lo + (i + 1) * w)}: ${k}"></i>`; }).join("")}${z}</div>
    <div class="hx"><span>${sgn(hs.lo)}</span><span>${p.ci ? `${t("h_inside")}: ${sgn(a)} … ${sgn(b)}` : ""}</span><span>${sgn(hs.hi)}</span></div></div>`;
}
function hypothesisCard(h) {
  const parts = (h.parts || []).map(p => `<tr><td class="mono">${esc(p.text)}</td><td class="n">${num(p.left)}</td><td class="n">${num(p.right)}</td>
    <td class="n"><b>${sgn(p.margin)}</b></td><td class="n">${p.ci ? `[${sgn(p.ci[0])}, ${sgn(p.ci[1])}]` : "—"}</td>
    <td class="n">${p.share == null ? "—" : p.share + " %"}</td><td>${verdictChip(p.verdict)}</td></tr>`).join("");
  const groups = !(h.parts || []).length ? "" : Object.entries(h.groups || {}).map(([k, g]) => `<div class="desc">${esc(k)}: ${g.runs.map((r, i) => `${esc(r)} ${num(g.points[i])}`).join(" · ")} · ${t("h_seed_sd")} ${num(g.sd)}</div>`).join("");
  const fns = Object.values(h.functions || {}).map(f => `<div class="desc mono">${esc(f)}</div>`).join("");
  return `<div class="card" data-h="${esc(h.id)}"><div class="ch"><h2>${esc(h.id)}</h2>${verdictChip(h.verdict)}</div><div class="cb">
    ${h.text ? `<p class="desc">${esc(tx(h.text))}</p>` : ""}
    ${h.criterion ? `<p class="desc">${t("h_criterion")} <code>${esc(h.criterion)}</code></p>` : `<div class="msg warn">${t("h_no_criterion")}</div>`}
    ${h.error ? `<div class="msg bad">${esc(errText(h.error))}</div>` : ""}
    ${h.missing?.length ? `<div class="msg warn">${t("h_waiting")} ${h.missing.map(esc).join(", ")}</div>` : ""}
    ${parts ? `<div class="card tw"><table><tr><th>${t("h_comparison")}</th><th class="n">${t("h_left")}</th><th class="n">${t("h_right")}</th><th class="n">${t("h_margin")}</th><th class="n">${t("h_ci")}</th><th class="n">${t("h_share")}</th><th></th></tr>${parts}</table></div>` : ""}
    ${(h.parts || []).some(p => p.hist) ? `<div class="hists">${h.parts.map(histCard).join("")}</div>` : ""}
    ${groups}${fns}</div></div>`;
}
function lockCard(s) {
  const rec = s.record;
  if (!rec) return `<div class="card"><div class="ch"><h2>${t("h_lock")}</h2>${s.locked ? chip("lock", t("h_locked_by_flag")) : chip("", t("h_open"))}</div><div class="cb">
    <p class="desc">${t(s.locked ? "h_flag_desc" : "h_open_desc")}</p>
    ${ME?.local ? `<button class="btn primary" id="hlock">${t("h_lock_now")}</button>` : `<div class="msg warn">${t("h_lock_local")}</div>`}</div></div>`;
  const ok = (good, label) => chip(good ? "COMPLETE" : "ERROR", `${label} ${good ? "✓" : "✕"}`);
  const git = rec.git ? `${t("h_commit")} <span class="mono">${esc(rec.git.commit.slice(0, 10))}</span>${rec.git.dirty ? ` · <b>${t("h_dirty")}</b>` : ""}` : t("h_no_git");
  const fine = s.plan_ok && s.runs_ok && s.code_ok !== false;
  return `<div class="card"><div class="ch"><h2>${t("h_lock")}</h2>${chip("lock", t("h_locked"))}${ok(s.plan_ok, esc(rec.plan))} ${ok(s.runs_ok, esc(rec.runs))}${s.code_ok == null ? "" : " " + ok(s.code_ok, t("tpl_code"))}</div><div class="cb">
    <p class="desc">${t("h_locked_at")} ${esc(rec.locked_at.replace("T", " ").slice(0, 16))} · ${git}</p>
    ${fine ? "" : `<div class="msg bad">${t("h_tampered")}${s.code_changed?.length ? ` (${s.code_changed.map(esc).join(", ")})` : ""}</div>
      <div class="form" style="margin:10px 0 14px"><label class="wide">${t("h_reason")}<input id="hdevr"></label><button class="btn" id="hdev">${t("h_record")}</button></div>`}
    ${s.deviations.length ? `<div class="card tw"><table><tr><th>${t("h_when")}</th><th>${t("h_file")}</th><th>${t("reason")}</th></tr>${s.deviations.map(d => `<tr><td class="mono">${esc((d.time || "").replace("T", " ").slice(0, 16))}</td><td class="mono">${esc(d.file)}</td><td>${esc(d.reason)}</td></tr>`).join("")}</table></div>`
      : `<p class="desc">${t("h_no_deviations")}</p>`}</div></div>`;
}
function ledgerCard(s) {
  if (!s.sealed?.length && !s.ledger?.length) return "";
  const twice = new Set(), seen = new Set();
  for (const r of s.ledger) { const k = r.set + "|" + r.weights; if (seen.has(k)) twice.add(k); seen.add(k); }
  return `<div class="card"><div class="ch"><h2>${t("h_ledger")}</h2><span class="muted">${s.sealed.map(esc).join(", ")}</span></div><div class="cb">
    <p class="desc">${t("h_ledger_desc")}</p>
    ${s.ledger.length ? `<div class="card tw"><table><tr><th>${t("h_when")}</th><th>${t("run")}</th><th>${t("h_set")}</th><th>${t("h_weights")}</th></tr>${s.ledger.map(r => `<tr><td class="mono">${esc((r.time || "").replace("T", " ").slice(0, 16))}</td><td>${esc(r.run)}</td><td>${esc(r.set)}</td><td class="mono">${esc((r.weights || "").slice(0, 12))}${twice.has(r.set + "|" + r.weights) ? ` ${chip("ERROR", t("h_again"))}` : ""}</td></tr>`).join("")}</table></div>` : `<p class="desc">${t("h_ledger_empty")}</p>`}</div></div>`;
}
async function renderHypotheses() {
  let d; try { d = await api(`/api/p/${P.key}/hypotheses`); } catch (e) { if (!stale("hypotheses")) $("#content").innerHTML = `<div class="msg bad">${esc(e.message)}</div>`; return; }
  if (stale("hypotheses")) return;
  if (!d.status.v2) { morph($("#content"), `<div class="msg warn">${t("plan_v1")}</div>`); return; }
  const byQ = {};
  for (const h of d.hypotheses) (byQ[h.question ?? ""] ??= []).push(h);
  const qs = d.questions.map(q => `<h3 class="qhead">${esc(q.id)} · ${esc(tx(q.text))}</h3>${(byQ[q.id] || []).map(hypothesisCard).join("") || `<p class="desc">${t("h_none")}</p>`}`).join("");
  const loose = (byQ[""] || []).concat(Object.entries(byQ).filter(([k]) => k && !d.questions.some(q => q.id === k)).flatMap(([, v]) => v));
  const pr = d.protocol;
  const exp = ME?.local ? `<div class="toolbar" style="margin:0 0 12px"><span class="desc" style="margin:0">${t("x_desc")}</span><span class="sp"><button class="btn" id="hexport">${t("x_export")}</button></span></div><div id="hxout" data-keep></div>` : "";
  const order = d.questions.flatMap(q => byQ[q.id] || []).concat(loose);
  morph($("#content"), `${exp}${forestCard(order)}${lockCard(d.status)}
    <p class="desc">${t("h_protocol", {metric: pr.metric, sets: Object.keys(pr.sets).join(", ") || "—", dir: pr.dir})}</p>
    ${qs}${loose.length ? `<h3 class="qhead">${t("h_other")}</h3>${loose.map(hypothesisCard).join("")}` : ""}
    ${!d.hypotheses.length ? `<div class="msg warn">${t("h_empty")}</div>` : ""}
    ${ledgerCard(d.status)}`);
  document.querySelectorAll("[data-hgo]").forEach(r => r.onclick = () => document.querySelector(`.card[data-h="${CSS.escape(r.dataset.hgo)}"]`)?.scrollIntoView({behavior: "smooth", block: "start"}));
  if ($("#hdev")) $("#hdev").onclick = async () => {
    try { await api(`/api/p/${P.key}/deviation`, {json: {reason: $("#hdevr").value}}); toast(t("saved")); renderHypotheses(); } catch (e) { say(e.message); }
  };
  if ($("#hexport")) $("#hexport").onclick = async () => {
    try {
      const j = await api(`/api/p/${P.key}/export`, {method: "POST"});
      $("#hxout").innerHTML = `<div class="msg ok" style="margin-bottom:12px">${t("x_done", {dir: j.dir})} ${j.files.map(f => `<a href="/api/p/${P.key}/paper/${f}" ${f.endsWith(".html") ? 'target="_blank" rel="noopener"' : ""}>${esc(f)}</a>`).join(" · ")}</div>`;
    } catch (e) { say(e.message); }
  };
  if ($("#hlock")) $("#hlock").onclick = async () => {
    if (!await ask(t("h_lock_sure"))) return;
    try { await api(`/api/p/${P.key}/lock`, {method: "POST"}); toast(t("h_locked")); renderHypotheses(); } catch (e) { say(e.message); }
  };
}
