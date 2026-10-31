/* ================= project: hypotheses (plan.yaml, docs/design-v2.md) ================= */
// Questions and their hypotheses, each with the verdict runboard computes from the evaluation files: the margin of
// every comparison on the whole set and its 95 % interval over the shared bootstrap replicates.
const VERDICT_CHIP = {supported: "COMPLETE", refuted: "ERROR", invalid: "ERROR", not_ready: "QUEUED", indistinguishable: "", no_criterion: ""};
const verdictChip = v => chip(VERDICT_CHIP[v] ?? "", t("v_" + v));
const num = v => v == null ? "—" : (+v).toFixed(2);
function hypothesisCard(h) {
  const parts = (h.parts || []).map(p => `<tr><td class="mono">${esc(p.text)}</td><td class="n">${num(p.left)}</td><td class="n">${num(p.right)}</td>
    <td class="n"><b>${p.margin > 0 ? "+" : ""}${num(p.margin)}</b></td><td class="n">${p.ci ? `[${num(p.ci[0])}, ${num(p.ci[1])}]` : "—"}</td>
    <td class="n">${p.share == null ? "—" : p.share + " %"}</td><td>${verdictChip(p.verdict)}</td></tr>`).join("");
  const groups = Object.entries(h.groups || {}).map(([k, g]) => `<div class="desc">${esc(k)}: ${g.runs.map((r, i) => `${esc(r)} ${num(g.points[i])}`).join(" · ")} · ${t("h_seed_sd")} ${num(g.sd)}</div>`).join("");
  const fns = Object.values(h.functions || {}).map(f => `<div class="desc mono">${esc(f)}</div>`).join("");
  return `<div class="card" data-h="${esc(h.id)}"><div class="ch"><h2>${esc(h.id)}</h2>${verdictChip(h.verdict)}</div><div class="cb">
    ${h.text ? `<p class="desc">${esc(tx(h.text))}</p>` : ""}
    ${h.criterion ? `<p class="desc">${t("h_criterion")} <code>${esc(h.criterion)}</code></p>` : `<div class="msg warn">${t("h_no_criterion")}</div>`}
    ${h.error ? `<div class="msg bad">${esc(errText(h.error))}</div>` : ""}
    ${h.missing?.length ? `<div class="msg warn">${t("h_waiting")} ${h.missing.map(esc).join(", ")}</div>` : ""}
    ${parts ? `<div class="card tw"><table><tr><th>${t("h_comparison")}</th><th class="n">${t("h_left")}</th><th class="n">${t("h_right")}</th><th class="n">${t("h_margin")}</th><th class="n">${t("h_ci")}</th><th class="n">${t("h_share")}</th><th></th></tr>${parts}</table></div>` : ""}
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
  morph($("#content"), `${lockCard(d.status)}
    <p class="desc">${t("h_protocol", {metric: pr.metric, sets: Object.keys(pr.sets).join(", ") || "—", dir: pr.dir})}</p>
    ${qs}${loose.length ? `<h3 class="qhead">${t("h_other")}</h3>${loose.map(hypothesisCard).join("")}` : ""}
    ${!d.hypotheses.length ? `<div class="msg warn">${t("h_empty")}</div>` : ""}
    ${ledgerCard(d.status)}`);
  if ($("#hdev")) $("#hdev").onclick = async () => {
    try { await api(`/api/p/${P.key}/deviation`, {json: {reason: $("#hdevr").value}}); toast(t("saved")); renderHypotheses(); } catch (e) { say(e.message); }
  };
  if ($("#hlock")) $("#hlock").onclick = async () => {
    if (!await ask(t("h_lock_sure"))) return;
    try { await api(`/api/p/${P.key}/lock`, {method: "POST"}); toast(t("h_locked")); renderHypotheses(); } catch (e) { say(e.message); }
  };
}
