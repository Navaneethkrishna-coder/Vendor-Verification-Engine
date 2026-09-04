// ============================================================
// Vendor Onboarding Verification Frontend Application
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initPresetScenarios();
  initFormSubmission();
  initDashboard();
  initModal();
});

let currentScenarios = {};
let liveEventSource = null;

// The ordered verification stages (Stage 1 Sanctions screening runs first)
const STAGE_ORDER = [
  { id: 1, key: "sanctions", title: "Sanctions & Restricted-Party Screening" },
  { id: 2, key: "intake", title: "Intake & Schema Validation" },
  { id: 3, key: "documents", title: "Document Validation" },
  { id: 4, key: "extraction", title: "Field Extraction from Documents" },
  { id: 5, key: "consistency", title: "Cross-Document Consistency Check" },
  { id: 6, key: "tax_bank", title: "Tax ID & Bank Country Consistency" },
  { id: 7, key: "history", title: "Risk & Vendor History Check" },
  { id: 8, key: "decision", title: "Decision Priority & Risk Synthesis" }
];

// -------------------------------------------------------------
// 1. Navigation & View Switching
// -------------------------------------------------------------
function initNavigation() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const targetView = tab.getAttribute("data-view");
      switchView(targetView);
    });
  });

  document.getElementById("btn-reset-db").addEventListener("click", async () => {
    if (confirm("Reset database? This will clear past runs and vendor history.")) {
      try {
        const res = await fetch("/api/reset-db", { method: "POST" });
        if (res.ok) {
          alert("Database cleared successfully.");
          loadDashboardRuns();
          loadLedgerEntries();
        }
      } catch (err) {
        console.error("Reset failed", err);
      }
    }
  });

  document.getElementById("btn-clear-form").addEventListener("click", () => {
    document.getElementById("vendor-submission-form").reset();
    document.getElementById("scenario_preset").value = "";
    resetDocBoxStatuses();
  });
}

function switchView(viewId) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));

  const targetViewElem = document.getElementById(viewId);
  const targetTabElem = document.querySelector(`.nav-tab[data-view="${viewId}"]`);

  if (targetViewElem) targetViewElem.classList.add("active");
  if (targetTabElem) targetTabElem.classList.add("active");

  if (viewId === "ledger-view") {
    loadDashboardRuns();
    loadLedgerEntries();
  }
}

// -------------------------------------------------------------
// 2. Scenario Presets Loading
// -------------------------------------------------------------
async function initPresetScenarios() {
  try {
    const res = await fetch("/api/scenarios");
    const scenarios = await res.json();
    scenarios.forEach(sc => {
      currentScenarios[sc.key] = sc;
    });
  } catch (e) {
    console.warn("Could not fetch scenario definitions", e);
  }

  const presetButtons = document.querySelectorAll(".btn-scenario-load");
  presetButtons.forEach(btn => {
    btn.addEventListener("click", (e) => {
      const card = e.target.closest(".scenario-card");
      const scenarioKey = card.getAttribute("data-scenario");
      loadAndRunScenario(scenarioKey);
    });
  });
}

function loadAndRunScenario(scenarioKey) {
  const sc = currentScenarios[scenarioKey];
  if (!sc) return;

  const form = document.getElementById("vendor-submission-form");
  const data = sc.form_data;

  // Fill form fields
  for (const [key, val] of Object.entries(data)) {
    const input = form.elements[key];
    if (input) {
      input.value = val;
    }
  }

  document.getElementById("scenario_preset").value = scenarioKey;

  // Mark document upload boxes as loaded
  document.getElementById("status-reg-cert").textContent = `Pre-generated ${scenarioKey}_reg_cert.pdf attached`;
  document.getElementById("status-tax-cert").textContent = `Pre-generated ${scenarioKey}_tax_cert.pdf attached`;
  document.getElementById("status-bank-letter").textContent = `Pre-generated ${scenarioKey}_bank_letter.pdf attached`;

  document.getElementById("box-reg-cert").classList.add("loaded");
  document.getElementById("box-tax-cert").classList.add("loaded");
  document.getElementById("box-bank-letter").classList.add("loaded");

  // Automatically execute verification stream
  executeVerificationStream(new FormData(form));
}

function resetDocBoxStatuses() {
  document.getElementById("status-reg-cert").textContent = "Auto-loaded when preset is selected";
  document.getElementById("status-tax-cert").textContent = "Auto-loaded when preset is selected";
  document.getElementById("status-bank-letter").textContent = "Auto-loaded when preset is selected";

  document.getElementById("box-reg-cert").classList.remove("loaded");
  document.getElementById("box-tax-cert").classList.remove("loaded");
  document.getElementById("box-bank-letter").classList.remove("loaded");
}

// -------------------------------------------------------------
// 3. Form Submission & Real-Time SSE Streaming
// -------------------------------------------------------------
function initFormSubmission() {
  const form = document.getElementById("vendor-submission-form");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    executeVerificationStream(formData);
  });

  document.getElementById("btn-copy-msg").addEventListener("click", () => {
    const msg = document.getElementById("vendor-msg-text").textContent;
    navigator.clipboard.writeText(msg).then(() => {
      alert("Vendor message copied to clipboard!");
    });
  });
}

async function executeVerificationStream(formData) {
  // Switch to live view
  switchView("live-view");

  // Setup UI for live stream
  const vendorName = formData.get("legal_company_name") || "Unnamed Vendor";
  const country = formData.get("country") || "Unknown";
  const taxId = formData.get("tax_id") || "-";
  const bank = formData.get("bank_name") || "-";

  document.getElementById("live-vendor-name").textContent = vendorName;
  document.getElementById("live-tag-country").textContent = `Country: ${country}`;
  document.getElementById("live-tag-tax").textContent = `Tax ID: ${taxId}`;
  document.getElementById("live-tag-bank").textContent = `Bank: ${bank}`;

  // Reset live indicators
  document.getElementById("live-pulse").classList.remove("hidden");
  const verdictPill = document.getElementById("live-verdict-pill");
  verdictPill.className = "live-verdict-pill verdict-idle";
  verdictPill.textContent = "VERIFYING...";

  document.getElementById("live-risk-val").textContent = "-";
  document.getElementById("live-risk-bar").style.width = "0%";
  document.getElementById("live-progress-bar").style.width = "0%";
  document.getElementById("live-progress-text").textContent = "Starting Pipeline...";
  document.getElementById("live-progress-percent").textContent = "0%";

  document.getElementById("vendor-message-card").classList.add("hidden");

  // Reset all 8 stages to idle
  for (let i = 1; i <= 8; i++) {
    const card = document.getElementById(`stage-card-${i}`);
    if (card) {
      card.className = "stage-card stage-idle";
      const badge = card.querySelector(".stage-badge");
      if (badge) {
        badge.className = "stage-badge badge-idle";
        badge.textContent = "WAITING";
      }
      const sum = card.querySelector(".stage-summary");
      if (sum) sum.textContent = "Awaiting engine stage...";
      const det = card.querySelector(".stage-details");
      if (det) det.innerHTML = "";
    }
  }

  // Stream POST via fetch with ReadableStream reader
  try {
    const response = await fetch("/api/verify-stream", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      throw new Error(`Server returned HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop(); // keep partial chunk

      for (const block of lines) {
        if (!block.trim()) continue;
        
        let eventName = "message";
        let dataStr = "";

        const blockLines = block.split("\n");
        for (const line of blockLines) {
          if (line.startsWith("event: ")) {
            eventName = line.substring(7).trim();
          } else if (line.startsWith("data: ")) {
            dataStr = line.substring(6).trim();
          }
        }

        if (dataStr) {
          try {
            const parsed = JSON.parse(dataStr);
            handleStreamEvent(eventName, parsed);
          } catch (err) {
            console.error("Error parsing SSE data", err, dataStr);
          }
        }
      }
    }

  } catch (err) {
    console.error("Stream failed", err);
    verdictPill.className = "live-verdict-pill verdict-rejected";
    verdictPill.textContent = "ERROR";
    document.getElementById("live-pulse").classList.add("hidden");
  }
}

function handleStreamEvent(eventName, payload) {
  if (eventName === "stage_update" && payload.stage) {
    const stage = payload.stage;
    const progress = payload.progress || 0;
    updateStageCard(stage);

    document.getElementById("live-progress-bar").style.width = `${progress}%`;
    document.getElementById("live-progress-text").textContent = `Stage ${stage.stage_number} of 8: ${stage.stage_name}`;
    document.getElementById("live-progress-percent").textContent = `${progress}%`;
  }

  if (eventName === "complete" && payload.result) {
    const res = payload.result;
    document.getElementById("live-pulse").classList.add("hidden");
    document.getElementById("live-progress-bar").style.width = "100%";
    document.getElementById("live-progress-text").textContent = "Verification Pipeline Finished";
    document.getElementById("live-progress-percent").textContent = "100%";

    // Final Verdict Pill
    const verdictPill = document.getElementById("live-verdict-pill");
    if (res.verdict === "Approved") {
      verdictPill.className = "live-verdict-pill verdict-approved";
      verdictPill.textContent = "APPROVED";
    } else if (res.verdict === "Pending") {
      verdictPill.className = "live-verdict-pill verdict-pending";
      verdictPill.textContent = "PENDING";
    } else {
      verdictPill.className = "live-verdict-pill verdict-rejected";
      verdictPill.textContent = "REJECTED";
    }

    // Risk Gauge
    document.getElementById("live-risk-val").textContent = res.risk_score;
    document.getElementById("live-risk-bar").style.width = `${res.risk_score}%`;

    // Vendor message
    if (res.vendor_message) {
      document.getElementById("vendor-message-card").classList.remove("hidden");
      document.getElementById("vendor-msg-text").textContent = res.vendor_message;
    }
  }
}

function updateStageCard(stage) {
  const card = document.getElementById(`stage-card-${stage.stage_number}`);
  if (!card) return;

  const status = stage.status;
  const badge = card.querySelector(".stage-badge");

  card.className = "stage-card";
  badge.className = "stage-badge";

  if (status === "PASS") {
    card.classList.add("stage-pass");
    badge.classList.add("badge-approved");
    badge.textContent = "PASS";
  } else if (status === "WARNING") {
    card.classList.add("stage-warning");
    badge.classList.add("badge-pending");
    badge.textContent = "WARNING";
  } else if (status === "FAIL") {
    card.classList.add("stage-fail");
    badge.classList.add("badge-rejected");
    badge.textContent = "FAIL";
  } else {
    card.classList.add("stage-info");
    badge.classList.add("badge-info");
    badge.textContent = "INFO";
  }

  card.querySelector(".stage-summary").textContent = stage.summary;

  // Format details
  // Format details
  const detailsBox = card.querySelector(".stage-details");
  let detailsHtml = "";

  if (stage.notes && stage.notes.length > 0) {
    detailsHtml += `<div style="margin-bottom: 6px; color: #CBD5E1;"><strong>Key Checks & Notes:</strong></div>`;
    stage.notes.forEach(n => {
      detailsHtml += `<div style="margin-bottom: 2px;">• ${escapeHtml(n)}</div>`;
    });
  }

  if (stage.details) {
    // If field discrepancies exist
    if (stage.details.discrepancies && stage.details.discrepancies.length > 0) {
      detailsHtml += `<div style="margin-top: 8px; border-top: 1px dashed var(--border); padding-top: 6px; color: var(--warning);"><strong>Field Discrepancies:</strong></div>`;
      stage.details.discrepancies.forEach(d => {
        detailsHtml += `<div style="font-size: 0.75rem; margin-top: 2px;">• <strong>${escapeHtml(d.field)}</strong> (${escapeHtml(d.document)}): Form <code style="color:#F59E0B;">'${escapeHtml(d.form_value)}'</code> vs Doc <code style="color:#94A3B8;">'${escapeHtml(d.doc_value)}'</code></div>`;
      });
    }

    if (stage.details.critical_mismatches && stage.details.critical_mismatches.length > 0) {
      detailsHtml += `<div style="margin-top: 8px; border-top: 1px dashed var(--border); padding-top: 6px; color: var(--danger);"><strong>Critical Document Mismatches:</strong></div>`;
      stage.details.critical_mismatches.forEach(d => {
        detailsHtml += `<div style="font-size: 0.75rem; margin-top: 2px;">• <strong>${escapeHtml(d.document)}</strong>: Issued to <code style="color:#EF4444;">'${escapeHtml(d.doc_value)}'</code> vs Applicant <code style="color:#F8FAFC;">'${escapeHtml(d.form_value)}'</code> (${(d.similarity*100).toFixed(1)}% match)</div>`;
      });
    }
  }

  detailsBox.innerHTML = detailsHtml || "<em>No additional details.</em>";
}

// -------------------------------------------------------------
// 4. Dashboard & Runs History
// -------------------------------------------------------------
function initDashboard() {
  document.getElementById("filter-verdict").addEventListener("change", loadDashboardRuns);
  document.getElementById("filter-search").addEventListener("input", debounce(loadDashboardRuns, 300));
  document.getElementById("btn-refresh-runs").addEventListener("click", () => {
    loadDashboardRuns();
    loadLedgerEntries();
  });
}

async function loadDashboardRuns() {
  const status = document.getElementById("filter-verdict").value;
  const search = document.getElementById("filter-search").value;

  let url = `/api/runs?limit=100`;
  if (status) url += `&status=${encodeURIComponent(status)}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    const runs = data.runs || [];

    renderRunsTable(runs);
    updateMetrics(runs);
  } catch (err) {
    console.error("Failed to load runs", err);
  }
}

function updateMetrics(runs) {
  let approved = 0;
  let pending = 0;
  let rejected = 0;

  runs.forEach(r => {
    if (r.verdict === "Approved") approved++;
    else if (r.verdict === "Pending") pending++;
    else if (r.verdict === "Rejected") rejected++;
  });

  document.getElementById("metric-total-runs").textContent = runs.length;
  document.getElementById("metric-approved").textContent = approved;
  document.getElementById("metric-pending").textContent = pending;
  document.getElementById("metric-rejected").textContent = rejected;
}

function renderRunsTable(runs) {
  const tbody = document.getElementById("runs-tbody");
  if (runs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-4">No matching verification runs found.</td></tr>`;
    return;
  }

  tbody.innerHTML = runs.map(r => {
    const dateFormatted = new Date(r.created_at).toLocaleString();
    let verdictBadge = "";
    if (r.verdict === "Approved") verdictBadge = `<span class="scenario-badge badge-approved">Approved</span>`;
    else if (r.verdict === "Pending") verdictBadge = `<span class="scenario-badge badge-pending">Pending</span>`;
    else verdictBadge = `<span class="scenario-badge badge-rejected">Rejected</span>`;

    let reasonBadge = "";
    if (r.reason_code) {
      const isSanctions = r.reason_code.startsWith("sanctions");
      reasonBadge = `<div style="margin-top: 4px;"><span class="scenario-badge ${isSanctions ? 'badge-rejected' : 'badge-pending'}" style="font-size: 0.68rem; padding: 2px 6px;">${escapeHtml(r.reason_code)}</span></div>`;
    }

    return `
      <tr>
        <td><code>${r.run_id}</code></td>
        <td><strong>${escapeHtml(r.company_name)}</strong></td>
        <td>${escapeHtml(r.country)}</td>
        <td>${verdictBadge}${reasonBadge}</td>
        <td><strong style="color: ${r.risk_score > 50 ? 'var(--danger)' : (r.risk_score > 20 ? 'var(--warning)' : 'var(--success)')};">${r.risk_score}/100</strong></td>
        <td style="max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(r.primary_reason || '')}">${escapeHtml(r.primary_reason || '-')}</td>
        <td class="text-sm text-muted">${dateFormatted}</td>
        <td>
          <button class="btn-secondary btn-sm" onclick="openRunTraceModal('${r.run_id}')">View Trace</button>
        </td>
      </tr>
    `;
  }).join("");
}

async function loadLedgerEntries() {
  try {
    const res = await fetch("/api/ledger");
    const data = await res.json();
    const records = data.records || [];
    const tbody = document.getElementById("ledger-tbody");

    if (records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">No records in vendor ledger.</td></tr>`;
      return;
    }

    tbody.innerHTML = records.map((rec, idx) => {
      let vBadge = rec.verdict === "Approved" ? `<span class="scenario-badge badge-approved">Approved</span>` :
                   (rec.verdict === "Pending" ? `<span class="scenario-badge badge-pending">Pending</span>` : `<span class="scenario-badge badge-rejected">Rejected</span>`);
      return `
        <tr>
          <td>${rec.id}</td>
          <td><strong>${escapeHtml(rec.company_name)}</strong></td>
          <td><code>${escapeHtml(rec.tax_id)}</code></td>
          <td><code>${escapeHtml(rec.bank_account_number)}</code></td>
          <td>${escapeHtml(rec.country)}</td>
          <td>${vBadge}</td>
          <td class="text-sm text-muted">${new Date(rec.created_at).toLocaleDateString()}</td>
        </tr>
      `;
    }).join("");
  } catch (e) {
    console.error("Failed to load ledger", e);
  }
}

// -------------------------------------------------------------
// 5. Trace Modal Inspection
// -------------------------------------------------------------
function initModal() {
  document.getElementById("btn-modal-close").addEventListener("click", () => {
    document.getElementById("trace-modal").classList.add("hidden");
  });

  document.getElementById("trace-modal").addEventListener("click", (e) => {
    if (e.target.id === "trace-modal") {
      document.getElementById("trace-modal").classList.add("hidden");
    }
  });
}

window.openRunTraceModal = async function(runId) {
  try {
    const res = await fetch(`/api/runs/${runId}`);
    if (!res.ok) throw new Error("Run not found");
    const data = await res.json();

    document.getElementById("modal-title").textContent = `Audit Trace: ${data.run_id}`;
    document.getElementById("modal-subtitle").textContent = `${data.company_name} (${data.country}) — Verdict: ${data.verdict} (Risk: ${data.risk_score}/100)`;

    let modalHtml = `
      <div style="margin-bottom: 1.5rem; background: var(--bg-primary); padding: 1rem; border-radius: 8px;">
        <h4 style="margin-bottom: 0.5rem; color: var(--primary);">Primary Decision Rationale</h4>
        <p style="font-size: 0.9rem; color: #F1F5F9;">${escapeHtml(data.primary_reason || 'Clean verification.')}</p>
        <div style="margin-top: 6px; font-size: 0.8rem; color: var(--text-muted);">Internal Reason Code: <code style="color: var(--primary);">${escapeHtml(data.reason_code || 'all_clean')}</code></div>
      </div>

      <h4 style="margin-bottom: 0.75rem;">8-Stage Execution Breakdown</h4>
      <div style="display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1.5rem;">
    `;

    data.stages.forEach(s => {
      const badgeClass = s.status === "PASS" ? "badge-approved" : (s.status === "WARNING" ? "badge-pending" : "badge-rejected");
      modalHtml += `
        <div style="border: 1px solid var(--border); padding: 0.8rem; border-radius: 6px; background: var(--bg-primary);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <strong>Stage ${s.stage_number}: ${escapeHtml(s.stage_name)}</strong>
            <span class="scenario-badge ${badgeClass}">${s.status}</span>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-main); margin-bottom: 4px;">${escapeHtml(s.summary)}</div>
          ${s.notes && s.notes.length > 0 ? `<div style="font-size: 0.75rem; color: var(--text-muted);">${s.notes.map(n => `• ${escapeHtml(n)}`).join("<br>")}</div>` : ''}
        </div>
      `;
    });

    modalHtml += `</div>`;

    if (data.vendor_message) {
      modalHtml += `
        <h4 style="margin-bottom: 0.5rem; color: var(--warning);">Vendor-Facing Message Generated</h4>
        <pre class="vendor-msg-box" style="margin-bottom: 1.5rem;">${escapeHtml(data.vendor_message)}</pre>
      `;
    }

    modalHtml += `
      <h4 style="margin-bottom: 0.5rem;">Submitted Profile Parameters</h4>
      <pre class="vendor-msg-box" style="font-size: 0.75rem; max-height: 200px; overflow-y: auto;">${escapeHtml(JSON.stringify(data.submission, null, 2))}</pre>
    `;

    document.getElementById("modal-body").innerHTML = modalHtml;
    document.getElementById("trace-modal").classList.remove("hidden");
  } catch (err) {
    console.error("Modal trace loading error", err);
  }
};

// Utilities
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}
