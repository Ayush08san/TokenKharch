const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtInt = (n) => Number(n || 0).toLocaleString("en-IN");
const fmtUsd = (n) => {
  n = Number(n || 0);
  if (n === 0) return "$0";
  if (n < 1) return "$" + n.toFixed(Math.min(8, 1 - Math.floor(Math.log10(n)) + 1)); // 3 significant digits
  return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
};
const fmtInr = (n) => "₹" + Number(n || 0).toFixed(n < 1 ? 4 : 2);

const SAMPLES = {
  verbose: `Hi! I was wondering if you could please help me out. You are a very helpful assistant. Could you just basically summarize the attached quarterly report in order to help me understand it? Please make sure to keep it short. Please make sure to keep it short.

It is important to note that I would like you to also list the top 3 risks, due to the fact that my manager will actually ask about them at this point in time.`,
  system: `You are an expert, world-class customer support assistant for an e-commerce company. As an AI language model, you should always be polite. Please kindly make sure that you answer every question. Please kindly make sure that you answer every question. In the event that a customer asks for a refund, you should check the order status prior to responding. In order to check the order status, you have the ability to call the get_order tool. Do not ever under any circumstances share internal notes.    Always reply in English.



If you are able to resolve the issue, close the ticket.`,
  clean: `Summarize the attached report in 5 bullet points, then list the top 3 risks with one-line mitigations. Output as Markdown.`,
};

let lastOptimized = "";

function setBusy(on) {
  ["btnAnalyze", "btnOptimize", "btnSend"].forEach((id) => ($(id).disabled = on));
  $("busy").hidden = !on;
}
function showError(msg) { $("error").textContent = msg; $("error").hidden = !msg; }

async function api(path, body, method = "POST") {
  const res = await fetch(path, {
    method, headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join("; ") : d || res.statusText);
  }
  return data;
}

function payload() {
  return {
    prompt: $("prompt").value,
    document: $("document").value.trim() || null,
    model: $("model").value,
    expected_output_tokens: Number($("out").value) || 500,
    mode: $("mode").value,
  };
}

const tile = (label, value, sub = "", cls = "") =>
  `<div class="tile ${cls}"><div class="label">${esc(label)}</div><div class="value">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;

function renderAnalysis(a) {
  $("analysisCard").hidden = false;
  $("tiles").innerHTML =
    tile("Input tokens", fmtInt(a.tokens.total_input), a.tokens.document ? `${fmtInt(a.tokens.prompt)} prompt + ${fmtInt(a.tokens.document)} doc` : "prompt only") +
    tile("Est. cost / call", fmtUsd(a.cost.total_usd), `${fmtInr(a.cost.total_inr)} · incl. ${fmtInt(a.tokens.expected_output)} out`) +
    tile("Cost per 1M calls", fmtUsd(a.cost.total_usd * 1e6), "at this size") +
    tile("Efficiency score", `${a.efficiency_score}<span class="muted small">/100</span>`, "share of non-wasted tokens", a.efficiency_score >= 85 ? "good" : "");
  $("tokenizerNote").textContent = `Tokenizer: ${a.tokenizer}`;
  $("warnings").innerHTML = a.warnings.map((w) => `<div class="warn">${esc(w)}</div>`).join("");
  $("issues").innerHTML = a.issues.length
    ? a.issues.map((i) => `<li><div class="head"><span>${esc(i.type.replace(/_/g, " "))}</span>
        <span><span class="sev ${i.severity}">${i.severity}</span> · ~${i.token_impact} tok</span></div>
        <div class="small">${esc(i.description)}</div>
        ${i.examples.length ? `<div class="ex">${i.examples.map(esc).join(" · ")}</div>` : ""}</li>`).join("")
    : `<li class="muted">No waste patterns found - this prompt is already lean.</li>`;
  renderBars(a.model_comparison, a.model);
}

function renderBars(rows, selected) {
  $("cmpCard").hidden = false;
  const max = Math.max(...rows.map((r) => r.total_usd), 1e-12);
  $("bars").innerHTML = rows.map((r) => `
    <div class="bar ${r.model === selected ? "sel" : ""}" role="listitem"
         data-tip="${esc(r.model)} (${esc(r.provider)}): in ${fmtUsd(r.input_usd)} + out ${fmtUsd(r.output_usd)}">
      <span class="name">${esc(r.model)}</span>
      <span class="track"><span class="fill" style="display:block;width:${(100 * r.total_usd) / max}%"></span></span>
      <span class="val">${fmtUsd(r.total_usd)}</span>
    </div>`).join("");
}

function renderOptimize(o) {
  $("optCard").hidden = false;
  lastOptimized = o.optimized;
  $("optTiles").innerHTML =
    tile("Tokens", `${fmtInt(o.tokens_before)} → ${fmtInt(o.tokens_after)}`, `${o.tokens_saved} saved`) +
    tile("Reduction", `${o.reduction_pct}%`, o.mode + " mode", o.reduction_pct > 0 ? "good" : "") +
    tile("Saved per 1M calls", fmtUsd(o.saved_per_million_calls_usd), "input cost only", o.saved_usd > 0 ? "good" : "");
  $("diff").innerHTML = o.diff.map((d) =>
    d.op === "equal" ? esc(d.text) : `<span class="${d.op === "delete" ? "del" : "ins"}">${esc(d.text)}</span>`).join("");
  $("rules").innerHTML = o.applied.length
    ? o.applied.map((r) => `<li><span>${esc(r.rule)}</span><span class="muted">−${r.tokens_saved} tok</span></li>`).join("")
    : `<li class="muted">Nothing to optimize.</li>`;
}

function renderSend(s) {
  if (s.optimization) renderOptimize(s.optimization);
  $("respCard").hidden = false;
  const r = s.response;
  if (r.error) {
    $("respTiles").innerHTML = "";
    $("response").textContent = "API error: " + r.error;
    return;
  }
  $("respTiles").innerHTML =
    tile("Billed input", fmtInt(r.input_tokens), r.demo ? "estimated (demo)" : "from API usage") +
    tile("Billed output", fmtInt(r.output_tokens)) +
    tile("Actual cost", r.demo ? "$0" : fmtUsd(s.actual_cost.total_usd), r.demo ? "demo mode - no API call" : fmtInr(s.actual_cost.total_inr)) +
    tile("Latency", r.demo ? "–" : `${fmtInt(r.latency_ms)} ms`);
  $("response").textContent = r.text;
}

function renderChart(days) {
  const el = $("chart");
  if (!days.length) { el.innerHTML = `<p class="muted small">No requests yet - send a prompt to start the ledger.</p>`; return; }
  const W = Math.max(300, el.clientWidth || 720), H = 200, P = { l: 48, r: 8, t: 10, b: 24 };
  const max = Math.max(...days.map((d) => d.tokens), 1);
  const step = (W - P.l - P.r) / days.length;
  const bw = Math.min(40, step - 6);
  const y = (v) => H - P.b - (v / max) * (H - P.t - P.b);
  const ticks = [0, max / 2, max];
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tokens sent per day">`;
  ticks.forEach((t) => {
    svg += `<line class="grid-line" x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}"/>`;
    svg += `<text class="axis" x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end">${fmtInt(Math.round(t))}</text>`;
  });
  days.forEach((d, i) => {
    const x = P.l + i * step + (step - bw) / 2, top = y(d.tokens), h = Math.max(1, H - P.b - top);
    const r = Math.min(4, h, bw / 2);
    // rounded top, square baseline
    svg += `<path class="col" data-tip="${esc(d.day)}: ${fmtInt(d.tokens)} tokens, ${fmtInt(d.saved)} saved, ${fmtUsd(d.cost_usd)}"
      d="M${x},${H - P.b} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${H - P.b} Z"/>`;
    svg += `<text class="axis" x="${x + bw / 2}" y="${H - 6}" text-anchor="middle">${esc(d.day.slice(5))}</text>`;
  });
  el.innerHTML = svg + "</svg>";
}

async function refreshLedger() {
  const s = await api("/api/stats", null, "GET");
  const t = s.totals;
  $("ledgerTiles").innerHTML =
    tile("Requests", fmtInt(t.requests)) +
    tile("Tokens sent", fmtInt(t.input_tokens + t.output_tokens), `${fmtInt(t.input_tokens)} in · ${fmtInt(t.output_tokens)} out`) +
    tile("Spend", fmtUsd(t.cost_usd), "real API calls only") +
    tile("Tokens saved", fmtInt(t.tokens_saved), `${fmtUsd(t.saved_usd)} input cost avoided`, t.tokens_saved ? "good" : "");
  renderChart(s.by_day);
  $("recent").querySelector("tbody").innerHTML = s.recent.length
    ? s.recent.map((r) => `<tr><td>${esc(new Date(r.ts).toLocaleString("en-IN", { dateStyle: "short", timeStyle: "short" }))}</td>
      <td>${esc(r.model)}${r.demo ? '<span class="badge">demo</span>' : ""}</td>
      <td class="num">${fmtInt(r.input_tokens)}</td><td class="num">${fmtInt(r.output_tokens)}</td>
      <td class="num">${fmtInt(r.tokens_saved)}</td><td class="num">${fmtUsd(r.cost_usd)}</td>
      <td class="preview" title="${esc(r.preview)}">${esc(r.preview)}</td></tr>`).join("")
    : `<tr><td colspan="7" class="muted">Empty.</td></tr>`;
}

async function run(fn) {
  showError("");
  if (!$("prompt").value.trim()) return showError("Enter a prompt first.");
  setBusy(true);
  try { await fn(); } catch (e) { showError(e.message); } finally { setBusy(false); }
}

$("btnAnalyze").onclick = () => run(async () => renderAnalysis(await api("/api/analyze", payload())));
$("btnOptimize").onclick = () => run(async () => {
  const p = payload();
  const [a, o] = await Promise.all([api("/api/analyze", p), api("/api/optimize", p)]);
  renderAnalysis(a); renderOptimize(o);
});
$("btnSend").onclick = () => run(async () => {
  const p = payload();
  const [a, s] = await Promise.all([api("/api/analyze", p),
    api("/api/send", { prompt: p.prompt, document: p.document, model: p.model, max_tokens: Math.min(p.expected_output_tokens, 8192), mode: p.mode })]);
  renderAnalysis(a); renderSend(s); refreshLedger();
});
$("btnUse").onclick = () => { if (lastOptimized) { $("prompt").value = lastOptimized; $("btnAnalyze").click(); } };
$("btnReset").onclick = async () => { await api("/api/stats", null, "DELETE"); refreshLedger(); };
document.querySelectorAll("[data-sample]").forEach((b) => (b.onclick = () => {
  $("prompt").value = SAMPLES[b.dataset.sample]; $("btnAnalyze").click();
}));

// hover tooltips for bars / chart columns
const tip = $("tip");
document.addEventListener("mousemove", (e) => {
  const t = e.target.closest("[data-tip]");
  if (!t) { tip.hidden = true; return; }
  tip.textContent = t.dataset.tip; tip.hidden = false;
  const x = Math.min(e.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + "px"; tip.style.top = e.clientY + 14 + "px";
});

(async function init() {
  const [st, models] = await Promise.all([api("/api/status", null, "GET"), api("/api/models", null, "GET")]);
  $("model").innerHTML = models.map((m) =>
    `<option value="${esc(m.name)}" ${m.name === st.default_model ? "selected" : ""}>${esc(m.name)} · $${m.input}/$${m.output}</option>`).join("");
  $("pills").innerHTML =
    `<span class="pill ${st.live_llm ? "live" : ""}"><span class="dot"></span><b>${st.live_llm ? "Live Claude API" : "Demo mode"}</b></span>` +
    `<span class="pill">Tokenizer: <b>${esc(st.tokenizer)}</b></span><span class="pill">v${esc(st.version)}</span>`;
  refreshLedger();
})().catch((e) => showError("Could not reach the TokenKharch API: " + e.message));
