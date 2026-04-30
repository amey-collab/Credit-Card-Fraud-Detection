/* predict.js */
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

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.getElementById("panelSingle").style.display = tab === "single" ? "" : "none";
  document.getElementById("panelBatch").style.display  = tab === "batch"  ? "" : "none";
  document.getElementById("tabSingle").className = tab === "single" ? "btn btn-primary btn-sm" : "btn btn-outline btn-sm";
  document.getElementById("tabBatch").className  = tab === "batch"  ? "btn btn-primary btn-sm" : "btn btn-outline btn-sm";
}

// ── Predict ───────────────────────────────────────────────────────────────────
async function submitPrediction(e) {
  e.preventDefault();
  const btn = document.getElementById("predictBtn");
  btn.textContent = "Analyzing...";
  btn.disabled = true;

  const payload = {
    amount:              parseFloat(document.getElementById("amount").value),
    transaction_hour:    parseInt(document.getElementById("transaction_hour").value),
    merchant_category:   document.getElementById("merchant_category").value,
    device_trust_score:  parseFloat(document.getElementById("device_trust_score").value),
    velocity_last_24h:   parseInt(document.getElementById("velocity_last_24h").value),
    cardholder_age:      parseInt(document.getElementById("cardholder_age").value),
    foreign_transaction: parseInt(document.getElementById("foreign_transaction").value),
    location_mismatch:   parseInt(document.getElementById("location_mismatch").value),
  };

  try {
    const res  = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.error) { showToast("Error: " + data.error, "fraud"); return; }

    showResult(data);
    loadHistory();

    if (data.risk_level === "High") {
      showToast("🚨 High-risk fraud detected! " + data.probability + "%", "fraud");
    } else if (data.label === "Legitimate") {
      showToast("✅ Transaction appears legitimate (" + data.probability + "%)", "success");
    }
  } catch (err) {
    showToast("Request failed: " + err.message, "fraud");
  } finally {
    btn.textContent = "🔍 Analyze Transaction";
    btn.disabled = false;
  }
}

function showResult(data) {
  const card      = document.getElementById("resultCard");
  const badge     = document.getElementById("resultBadge");
  const probBar   = document.getElementById("probBar");
  const probPct   = document.getElementById("probPct");
  const riskBadge = document.getElementById("riskBadge");
  const reasons   = document.getElementById("reasonsList");
  const modelUsed = document.getElementById("modelUsed");

  card.style.display = "block";

  const isFraud = data.label === "Fraud";
  badge.textContent = isFraud ? "🚨 FRAUDULENT" : "✅ LEGITIMATE";
  badge.className   = "result-badge " + (isFraud ? "result-fraud" : "result-legit");

  // Animate probability bar
  probBar.style.width = "0%";
  setTimeout(() => { probBar.style.width = data.probability + "%"; }, 50);

  probPct.textContent = data.probability + "%";
  probPct.style.color = isFraud ? "var(--accent)" : "var(--success)";

  riskBadge.textContent = data.risk_level;
  riskBadge.className   = "risk-badge risk-" + data.risk_level;

  reasons.innerHTML = data.reasons.map(r => `<li>${r}</li>`).join("");

  if (data.model_used) {
    modelUsed.textContent = "Model: " + data.model_used;
  }

  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ── History ───────────────────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const res  = await fetch("/api/history");
    const data = await res.json();
    const list = document.getElementById("historyList");
    const items = data.history || [];

    if (!items.length) {
      list.innerHTML = `<p style="color:var(--text-muted);font-size:0.85rem;padding:0.5rem">No predictions yet.</p>`;
      return;
    }

    list.innerHTML = items.slice(0, 20).map(item => {
      const isFraud = item.label === "Fraud";
      const ts = item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : "";
      return `<div class="history-item ${isFraud ? 'fraud' : 'legit'}" onclick="fillFromHistory(${JSON.stringify(item).replace(/"/g, '&quot;')})">
        <div>
          <div>$${item.amount} &nbsp;·&nbsp; ${item.merchant_category}</div>
          <div class="history-meta">${ts} &nbsp;·&nbsp; ${item.model_used || ''}</div>
        </div>
        <div style="text-align:right">
          <span class="badge ${isFraud ? 'badge-danger' : 'badge-success'}">${item.label}</span>
          <div class="history-meta">${item.probability}%</div>
        </div>
      </div>`;
    }).join("");
  } catch (e) {
    console.warn("History load failed:", e.message);
  }
}

function fillFromHistory(item) {
  const fields = ["amount","transaction_hour","device_trust_score","velocity_last_24h","cardholder_age","foreign_transaction","location_mismatch"];
  fields.forEach(f => {
    const el = document.getElementById(f);
    if (el && item[f] !== undefined) el.value = item[f];
  });
  const sel = document.getElementById("merchant_category");
  if (sel && item.merchant_category) {
    for (const opt of sel.options) {
      if (opt.value === item.merchant_category) { opt.selected = true; break; }
    }
  }
  showToast("Loaded from history", "info");
}

// ── Random fill ───────────────────────────────────────────────────────────────
function fillRandom() {
  fetch("/api/simulate")
    .then(r => r.json())
    .then(tx => {
      document.getElementById("amount").value              = tx.amount;
      document.getElementById("transaction_hour").value    = tx.transaction_hour;
      document.getElementById("device_trust_score").value  = tx.device_trust_score;
      document.getElementById("velocity_last_24h").value   = tx.velocity_last_24h;
      document.getElementById("cardholder_age").value      = tx.cardholder_age;
      document.getElementById("foreign_transaction").value = tx.foreign_transaction;
      document.getElementById("location_mismatch").value   = tx.location_mismatch;
      const sel = document.getElementById("merchant_category");
      for (const opt of sel.options) {
        if (opt.value === tx.merchant_category) { opt.selected = true; break; }
      }
    });
}

function clearForm() {
  document.getElementById("predictForm").reset();
  document.getElementById("resultCard").style.display = "none";
}

// ── Batch Predict ─────────────────────────────────────────────────────────────
function handleBatchDrop(e) {
  e.preventDefault();
  document.getElementById("batchZone").classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) runBatchPredict(file);
}

async function runBatchPredict(file) {
  if (!file) return;
  const status = document.getElementById("batchStatus");
  status.textContent = "⏳ Processing batch...";
  showToast("Running batch prediction...", "info");

  const form = new FormData();
  form.append("file", file);

  try {
    const res = await fetch("/api/batch_predict", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json();
      status.textContent = "Error: " + err.error;
      showToast("Batch failed: " + err.error, "fraud");
      return;
    }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = "batch_predictions.csv"; a.click();
    URL.revokeObjectURL(url);
    status.textContent = "✅ Done! Results downloaded.";
    showToast("Batch predictions downloaded", "success");
  } catch (e) {
    status.textContent = "Error: " + e.message;
    showToast("Batch failed: " + e.message, "fraud");
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadHistory();
