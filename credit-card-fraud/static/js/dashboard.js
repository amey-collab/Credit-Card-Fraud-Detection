/* dashboard.js */
"use strict";

// ── Theme ─────────────────────────────────────────────────────────────────────
function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
}
(function () {
  const saved = localStorage.getItem("theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
})();

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, type = "info") {
  const c = document.getElementById("toastContainer");
  const t = document.createElement("div");
  t.className = `toast toast-${type}`;
  t.innerHTML = `<span>${msg}</span><button class="toast-close" onclick="this.parentElement.remove()">✕</button>`;
  c.appendChild(t);
  setTimeout(() => {
    t.style.animation = "toastOut 0.3s ease forwards";
    setTimeout(() => t.remove(), 300);
  }, 5000);
}

// ── Animated counter ──────────────────────────────────────────────────────────
function animateCount(el, target, prefix = "", suffix = "") {
  const start = 0;
  const duration = 800;
  const startTime = performance.now();
  function step(now) {
    const progress = Math.min((now - startTime) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = prefix + Math.round(start + (target - start) * eased).toLocaleString() + suffix;
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ── Chart helpers ─────────────────────────────────────────────────────────────
const COLORS = {
  fraud:  "#e94560",
  legit:  "#00d4aa",
  blue:   "#0f3460",
  purple: "#533483",
  orange: "#f5a623",
  info:   "#4fc3f7",
  grid:   "rgba(255,255,255,0.06)",
};

function baseOpts(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: true,
    animation: { duration: 600 },
    plugins: {
      legend: { labels: { color: "#aaa", font: { size: 11 }, boxWidth: 12 } },
      tooltip: { backgroundColor: "rgba(10,10,20,0.9)", titleColor: "#fff", bodyColor: "#ccc", borderColor: "rgba(255,255,255,0.1)", borderWidth: 1 },
    },
    ...extra,
  };
}

function xyScales() {
  return {
    x: { ticks: { color: "#888" }, grid: { color: COLORS.grid } },
    y: { ticks: { color: "#888" }, grid: { color: COLORS.grid } },
  };
}

const charts = {};
function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

// ── Load Stats ────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const res  = await fetch("/api/stats");
    const data = await res.json();
    if (data.error) { showToast("Stats error: " + data.error, "fraud"); return; }

    animateCount(document.getElementById("totalTx"), data.total);
    animateCount(document.getElementById("fraudTx"), data.fraud);
    animateCount(document.getElementById("legitTx"), data.legit);
    document.getElementById("fraudRate").textContent = data.fraud_rate + "%";
    document.getElementById("avgFraudAmt").textContent = "$" + data.avg_fraud_amount.toLocaleString();
    document.getElementById("avgLegitAmt").textContent = "$" + data.avg_legit_amount.toLocaleString();
    document.getElementById("lastUpdated").textContent = "Last updated: " + new Date().toLocaleTimeString();

    // Update sidebar alert badge
    fetch("/api/history").then(r => r.json()).then(h => {
      const fraudCount = (h.history || []).filter(x => x.risk_level === "High").length;
      const badge = document.getElementById("sidebarAlertCount");
      if (badge) badge.textContent = fraudCount;
    });

    renderDonut(data.fraud, data.legit);
    renderHourChart(data.by_hour);
    renderMerchantChart(data.by_merchant);
    renderAmountChart(data.fraud_amounts, data.legit_amounts);
    renderAgeChart(data.by_age || {});
    renderTable(data.preview, data.columns);
  } catch (e) {
    showToast("Failed to load stats: " + e.message, "fraud");
  }
}

// ── Donut Chart ───────────────────────────────────────────────────────────────
function renderDonut(fraud, legit) {
  destroyChart("donut");
  const ctx = document.getElementById("donutChart").getContext("2d");
  charts["donut"] = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Fraud", "Legitimate"],
      datasets: [{ data: [fraud, legit], backgroundColor: [COLORS.fraud, COLORS.legit], borderWidth: 0, hoverOffset: 6 }],
    },
    options: { ...baseOpts(), cutout: "68%", plugins: { ...baseOpts().plugins, legend: { position: "bottom", labels: { color: "#aaa", font: { size: 11 } } } } },
  });
}

// ── Hour Chart ────────────────────────────────────────────────────────────────
function renderHourChart(byHour) {
  destroyChart("hour");
  const labels = Array.from({ length: 24 }, (_, i) => i + ":00");
  const values = labels.map((_, i) => byHour[i] || 0);
  const ctx = document.getElementById("hourChart").getContext("2d");
  charts["hour"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Fraud Count", data: values, backgroundColor: values.map(v => v > 0 ? COLORS.fraud : "rgba(233,69,96,0.2)"), borderRadius: 4 }],
    },
    options: { ...baseOpts(), scales: xyScales() },
  });
}

// ── Merchant Chart ────────────────────────────────────────────────────────────
function renderMerchantChart(byMerchant) {
  destroyChart("merchant");
  const sorted = Object.entries(byMerchant).sort((a, b) => b[1] - a[1]);
  const ctx = document.getElementById("merchantChart").getContext("2d");
  charts["merchant"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: sorted.map(e => e[0]),
      datasets: [{ label: "Fraud Count", data: sorted.map(e => e[1]), backgroundColor: COLORS.purple, borderRadius: 4 }],
    },
    options: { ...baseOpts(), indexAxis: "y", scales: xyScales() },
  });
}

// ── Age Chart ─────────────────────────────────────────────────────────────────
function renderAgeChart(byAge) {
  destroyChart("age");
  const ctx = document.getElementById("ageChart").getContext("2d");
  charts["age"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: Object.keys(byAge),
      datasets: [{ label: "Fraud by Age", data: Object.values(byAge), backgroundColor: COLORS.orange, borderRadius: 4 }],
    },
    options: { ...baseOpts(), scales: xyScales() },
  });
}

// ── Amount Distribution ───────────────────────────────────────────────────────
function renderAmountChart(fraudAmts, legitAmts) {
  destroyChart("amount");
  function bucket(arr, bins = 20) {
    const max = Math.max(...arr, 1);
    const step = max / bins;
    const counts = Array(bins).fill(0);
    arr.forEach(v => { const i = Math.min(Math.floor(v / step), bins - 1); counts[i]++; });
    return { labels: Array.from({ length: bins }, (_, i) => "$" + Math.round(i * step)), counts };
  }
  const f = bucket(fraudAmts);
  const l = bucket(legitAmts);
  const ctx = document.getElementById("amountChart").getContext("2d");
  charts["amount"] = new Chart(ctx, {
    type: "line",
    data: {
      labels: f.labels,
      datasets: [
        { label: "Fraud", data: f.counts, borderColor: COLORS.fraud, backgroundColor: "rgba(233,69,96,0.1)", fill: true, tension: 0.4, pointRadius: 2 },
        { label: "Legit", data: l.counts, borderColor: COLORS.legit, backgroundColor: "rgba(0,212,170,0.07)", fill: true, tension: 0.4, pointRadius: 2 },
      ],
    },
    options: { ...baseOpts(), scales: xyScales() },
  });
}

// ── Model Comparison + Confusion Matrix ───────────────────────────────────────
async function loadModelResults() {
  try {
    const res  = await fetch("/api/model_results");
    const data = await res.json();
    if (data.error) return;

    const names   = Object.keys(data.results);
    const f1s     = names.map(n => data.results[n].f1);
    const aucs    = names.map(n => data.results[n].roc_auc);
    const recalls = names.map(n => data.results[n].recall);

    destroyChart("model");
    const ctx = document.getElementById("modelChart").getContext("2d");
    charts["model"] = new Chart(ctx, {
      type: "bar",
      data: {
        labels: names,
        datasets: [
          { label: "F1 Score",  data: f1s,     backgroundColor: COLORS.fraud,  borderRadius: 4 },
          { label: "ROC-AUC",   data: aucs,    backgroundColor: COLORS.legit,  borderRadius: 4 },
          { label: "Recall",    data: recalls, backgroundColor: COLORS.orange, borderRadius: 4 },
        ],
      },
      options: { ...baseOpts(), scales: xyScales() },
    });

    // Feature importance
    if (data.importances && Object.keys(data.importances).length) {
      const sorted = Object.entries(data.importances).sort((a, b) => b[1] - a[1]);
      destroyChart("feature");
      const ctx2 = document.getElementById("featureChart").getContext("2d");
      charts["feature"] = new Chart(ctx2, {
        type: "bar",
        data: {
          labels: sorted.map(e => e[0]),
          datasets: [{ label: "Importance", data: sorted.map(e => e[1]), backgroundColor: COLORS.purple, borderRadius: 4 }],
        },
        options: { ...baseOpts(), indexAxis: "y", scales: xyScales() },
      });
    }

    // Confusion matrix for best model
    const best = data.best_model;
    if (best && data.results[best]?.confusion_matrix) {
      renderConfusionMatrix(data.results[best].confusion_matrix, best);
    }
  } catch (e) {
    console.warn("Model results unavailable:", e.message);
  }
}

function renderConfusionMatrix(cm, modelName) {
  const container = document.getElementById("confusionMatrix");
  if (!container || !cm) return;
  const labels = ["Legit (Pred)", "Fraud (Pred)"];
  const rowLabels = ["Legit (Actual)", "Fraud (Actual)"];
  const colors = [["rgba(0,212,170,0.2)", "rgba(233,69,96,0.15)"], ["rgba(233,69,96,0.15)", "rgba(0,212,170,0.2)"]];
  let html = `<div style="text-align:center;margin-bottom:0.5rem;font-size:0.8rem;color:var(--text-muted)">Best Model: <strong style="color:var(--text)">${modelName}</strong></div>`;
  html += `<table style="border-collapse:collapse;font-size:0.85rem;margin:0 auto">`;
  html += `<tr><th style="padding:0.5rem 1rem;color:var(--text-muted)"></th>`;
  labels.forEach(l => { html += `<th style="padding:0.5rem 1rem;color:var(--accent);font-size:0.78rem">${l}</th>`; });
  html += `</tr>`;
  cm.forEach((row, i) => {
    html += `<tr><td style="padding:0.5rem 1rem;color:var(--text-muted);font-size:0.78rem;white-space:nowrap">${rowLabels[i]}</td>`;
    row.forEach((val, j) => {
      html += `<td style="padding:0.75rem 1.5rem;text-align:center;background:${colors[i][j]};border-radius:8px;font-weight:700;font-size:1.1rem">${val.toLocaleString()}</td>`;
    });
    html += `</tr>`;
  });
  html += `</table>`;
  container.innerHTML = html;
}

// ── Transaction Table ─────────────────────────────────────────────────────────
function renderTable(rows, cols) {
  const head = document.getElementById("txHead");
  const body = document.getElementById("txBody");
  head.innerHTML = "<tr>" + cols.map(c => `<th>${c}</th>`).join("") + "</tr>";
  body.innerHTML = rows.map(row => {
    const isFraud = row["is_fraud"] == 1;
    const cells = cols.map(c => `<td>${row[c] ?? ""}</td>`).join("");
    return `<tr class="${isFraud ? "fraud-row" : ""}">${cells}</tr>`;
  }).join("");
}

function filterTable() {
  const q = document.getElementById("tableSearch").value.toLowerCase();
  document.querySelectorAll("#txBody tr").forEach(r => {
    r.style.display = r.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}

// ── Train Model ───────────────────────────────────────────────────────────────
async function trainModel() {
  const modal  = document.getElementById("trainModal");
  const fill   = document.getElementById("trainProgress");
  const status = document.getElementById("trainStatus");
  modal.style.display = "flex";
  fill.style.width = "0%";

  const steps = [
    [10, "Loading dataset..."],
    [30, "Balancing classes with SMOTE..."],
    [55, "Training all models..."],
    [80, "Evaluating performance..."],
    [95, "Saving best model..."],
  ];

  let i = 0;
  const tick = setInterval(() => {
    if (i < steps.length) { fill.style.width = steps[i][0] + "%"; status.textContent = steps[i][1]; i++; }
  }, 700);

  try {
    const res  = await fetch("/api/train", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ strategy: "smote" }) });
    const data = await res.json();
    clearInterval(tick);
    fill.style.width = "100%";
    if (data.error) {
      status.textContent = "Error: " + data.error;
      showToast("Training failed: " + data.error, "fraud");
    } else {
      status.textContent = `✅ Best: ${data.best_model}`;
      showToast("Model trained! Best: " + data.best_model, "success");
    }
    setTimeout(() => { modal.style.display = "none"; loadModelResults(); }, 1800);
  } catch (e) {
    clearInterval(tick);
    status.textContent = "Error: " + e.message;
    setTimeout(() => { modal.style.display = "none"; }, 2000);
  }
}

// ── Upload Dataset ────────────────────────────────────────────────────────────
async function uploadDataset(input) {
  const file = input.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  showToast("Uploading dataset...", "info");
  const res  = await fetch("/api/upload", { method: "POST", body: form });
  const data = await res.json();
  if (data.error) { showToast("Upload failed: " + data.error, "fraud"); return; }
  showToast("Dataset uploaded. Refreshing stats...", "success");
  loadStats();
}

// ── Real-time Simulation ──────────────────────────────────────────────────────
let simInterval = null;
let simCounts = { total: 0, fraud: 0, legit: 0 };

async function startSimulation() {
  const btn  = document.getElementById("simBtn");
  const feed = document.getElementById("simFeed");

  if (simInterval) {
    clearInterval(simInterval);
    simInterval = null;
    btn.textContent = "▶ Start";
    btn.className = "btn btn-primary btn-sm";
    return;
  }

  btn.textContent = "⏹ Stop";
  btn.className = "btn btn-danger btn-sm";

  async function tick() {
    try {
      const tx   = await (await fetch("/api/simulate")).json();
      const pred = await (await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(tx),
      })).json();
      if (pred.error) return;

      const isFraud = pred.label === "Fraud";
      simCounts.total++;
      isFraud ? simCounts.fraud++ : simCounts.legit++;
      document.getElementById("simTotal").textContent = simCounts.total;
      document.getElementById("simFraudCount").textContent = simCounts.fraud;
      document.getElementById("simLegitCount").textContent = simCounts.legit;

      const item = document.createElement("div");
      item.className = "sim-item " + (isFraud ? "sim-fraud" : "sim-legit");
      item.innerHTML = `
        <div>
          <div>💳 $${tx.amount} &nbsp;|&nbsp; ${tx.merchant_category} &nbsp;|&nbsp; ${tx.transaction_hour}:00</div>
          <div class="sim-meta">Age ${tx.cardholder_age} &nbsp;·&nbsp; Device trust: ${tx.device_trust_score} &nbsp;·&nbsp; Velocity: ${tx.velocity_last_24h}</div>
        </div>
        <div style="text-align:right">
          <div>${isFraud ? "🚨 FRAUD" : "✅ Legit"}</div>
          <div class="sim-meta">${pred.probability}% &nbsp;·&nbsp; ${pred.risk_level}</div>
        </div>`;
      feed.prepend(item);
      if (feed.children.length > 25) feed.lastChild.remove();

      if (isFraud && pred.risk_level === "High") {
        showToast("🚨 High-risk fraud! $" + tx.amount + " at " + tx.merchant_category, "fraud");
      }
    } catch (e) { /* silent */ }
  }

  tick();
  simInterval = setInterval(tick, 2500);
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadStats();
loadModelResults();
