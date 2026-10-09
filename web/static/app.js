// SightLine - Accessible Web Application Frontend
document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const form = document.getElementById("audit-form");
  const urlInput = document.getElementById("url-input");
  const urlLabel = document.getElementById("url-label");
  const urlHint = document.getElementById("url-hint");
  const analyzeBtn = document.getElementById("analyze-btn");
  const modeSiteRadio = document.getElementById("mode-site");
  const modeRepoRadio = document.getElementById("mode-repo");
  const loadDemoBtn = document.getElementById("load-demo-btn");
  const quickDemoBtn = document.getElementById("quick-demo-btn");

  const errorBanner = document.getElementById("error-banner");
  const errorMessage = document.getElementById("error-message");
  const errorDismissBtn = document.getElementById("error-dismiss-btn");

  const progressArea = document.getElementById("progress-area");
  const progressStatusText = document.getElementById("progress-status-text");
  const progressStepText = document.getElementById("progress-step-text");
  const stepsList = document.getElementById("steps-list");

  const emptyState = document.getElementById("empty-state");
  const resultsContainer = document.getElementById("results-container");

  const resultBadgeMode = document.getElementById("result-badge-mode");
  const resultsUrlLink = document.getElementById("results-url-link");
  const repoSummaryCard = document.getElementById("repo-summary-card");
  const repoSummaryText = document.getElementById("repo-summary-text");
  const screenshotCard = document.getElementById("screenshot-card");
  const annotatedImage = document.getElementById("annotated-image");

  const statTotal = document.getElementById("stat-total");
  const statMeasured = document.getElementById("stat-measured");
  const statAi = document.getElementById("stat-ai");
  const statVerified = document.getElementById("stat-verified");

  const filterChips = document.querySelectorAll(".filter-chips .chip");
  const findingsList = document.getElementById("findings-list");
  const toast = document.getElementById("toast");
  const toastMessage = document.getElementById("toast-message");

  let currentResult = null;
  let activeFilter = "all";
  let pollIntervalId = null;

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function showToast(message) {
    if (!toast) return;
    toastMessage.textContent = message;
    toast.classList.remove("hidden");
    setTimeout(() => {
      toast.classList.add("hidden");
    }, 2500);
  }

  function showError(msg) {
    errorMessage.textContent = msg;
    errorBanner.classList.remove("hidden");
    errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function hideError() {
    errorBanner.classList.add("hidden");
    errorMessage.textContent = "";
  }

  // -------------------------------------------------------------------------
  // Mode Toggle Handling
  // -------------------------------------------------------------------------

  function handleModeChange() {
    const isRepo = modeRepoRadio.checked;
    if (isRepo) {
      urlLabel.textContent = "GitHub Repository URL";
      urlInput.placeholder = "https://github.com/owner/repo";
      urlHint.textContent = "Enter a public GitHub repository link (e.g., https://github.com/owner/repo).";
    } else {
      urlLabel.textContent = "Website URL";
      urlInput.placeholder = "https://example.com";
      urlHint.textContent = "Enter a public or permitted local HTTP/HTTPS webpage URL.";
    }
  }

  modeSiteRadio.addEventListener("change", handleModeChange);
  modeRepoRadio.addEventListener("change", handleModeChange);
  errorDismissBtn.addEventListener("click", hideError);

  // -------------------------------------------------------------------------
  // Rendering Results
  // -------------------------------------------------------------------------

  function renderStats(result) {
    const findings = result.findings || [];
    const total = findings.length;
    const measuredCount = findings.filter((f) => f.source === "measured").length;
    const aiCount = findings.filter((f) => f.source === "ai").length;
    const verifiedCount = findings.filter((f) => f.verified).length;

    statTotal.textContent = String(total);
    statMeasured.textContent = String(measuredCount);
    statAi.textContent = String(aiCount);
    statVerified.textContent = String(verifiedCount);
  }

  function buildIssueMarkdown(finding, result) {
    if (result && result.issues && result.issues[finding.id]) {
      return result.issues[finding.id];
    }

    const sev = (finding.severity || "medium").toUpperCase();
    let text = `# [${sev}] ${finding.rule || "Issue"}: ${finding.problem}\n\n`;
    text += `## What's wrong\n\n${finding.problem}\n\n`;
    text += `## Evidence\n\n`;
    if (finding.element_number !== null && finding.element_number !== undefined) {
      text += `- **Element number**: #${finding.element_number}\n`;
    }
    if (finding.file_path) {
      text += `- **File**: \`${finding.file_path}\`\n`;
    }
    text += `- **Evidence**: ${finding.evidence || "Observed during automated inspection."}\n\n`;
    text += `## Why it matters\n\n${finding.why_it_matters || "Affects user experience or code quality."}\n\n`;
    text += `## Suggested fix\n\n${finding.fix || "Apply recommended fixes."}\n`;
    if (finding.fix_value) {
      text += `\n**Recommended value**: \`${finding.fix_value}\`\n`;
    }
    if (finding.fix_snippet) {
      text += `\n\`\`\`\n${finding.fix_snippet}\n\`\`\`\n`;
    }
    text += `\n## How it was found\n\n`;
    text += finding.source === "measured"
      ? "Measured deterministically by SightLine automated checks."
      : "AI analysis via Gemma 4 and SightLine.";
    if (finding.verified) {
      text += `\n**Status**: Verified (${finding.verified_note || "Passed validation"}).`;
    }
    text += `\n\n## Checklist\n\n- [ ] Review proposed fix\n- [ ] Apply changes\n- [ ] Verify fix\n- [ ] Close issue\n`;
    return text;
  }

  function copyToClipboard(text, btnElement) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        handleCopySuccess(btnElement);
      }).catch(() => {
        fallbackCopy(text, btnElement);
      });
    } else {
      fallbackCopy(text, btnElement);
    }
  }

  function fallbackCopy(text, btnElement) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand("copy");
      handleCopySuccess(btnElement);
    } catch (e) {
      console.error("Copy failed", e);
    }
    document.body.removeChild(textarea);
  }

  function handleCopySuccess(btnElement) {
    btnElement.classList.add("copied");
    const originalText = btnElement.innerHTML;
    btnElement.innerHTML = `✓ Copied!`;
    showToast("GitHub issue Markdown copied to clipboard!");
    setTimeout(() => {
      btnElement.classList.remove("copied");
      btnElement.innerHTML = originalText;
    }, 2000);
  }

  function renderFindings(findings, result) {
    findingsList.innerHTML = "";

    const filtered = findings.filter((f) => {
      if (activeFilter === "all") return true;
      if (activeFilter === "high") return f.severity === "high";
      if (activeFilter === "medium") return f.severity === "medium";
      if (activeFilter === "low") return f.severity === "low";
      if (activeFilter === "measured") return f.source === "measured";
      if (activeFilter === "ai") return f.source === "ai";
      if (activeFilter === "verified") return !!f.verified;
      return true;
    });

    if (filtered.length === 0) {
      findingsList.innerHTML = `
        <div class="card" style="text-align: center; color: var(--text-muted); padding: 2rem;">
          <p style="margin: 0; font-size: 1rem;">No findings match the selected filter.</p>
        </div>
      `;
      return;
    }

    filtered.forEach((finding, index) => {
      const card = document.createElement("article");
      const sev = (finding.severity || "medium").toLowerCase();
      card.className = `finding-card severity-${sev}`;
      card.setAttribute("aria-labelledby", `finding-title-${index}`);

      // Badges
      let badgesHtml = `<span class="badge badge-sev-${sev}">${escapeHtml(sev.toUpperCase())}</span>`;
      if (finding.source === "measured") {
        badgesHtml += `<span class="badge badge-measured">Measured</span>`;
      } else {
        badgesHtml += `<span class="badge badge-ai">AI-suggested</span>`;
      }

      if (finding.verified) {
        badgesHtml += `<span class="badge badge-verified">Verified fix</span>`;
      }

      if (finding.element_number !== null && finding.element_number !== undefined) {
        badgesHtml += `<span class="badge badge-subtle">Element #${escapeHtml(finding.element_number)}</span>`;
      } else if (finding.file_path) {
        badgesHtml += `<span class="badge badge-subtle">${escapeHtml(finding.file_path)}</span>`;
      }

      let fixSnippetHtml = "";
      if (finding.fix_snippet) {
        fixSnippetHtml = `<pre class="fix-snippet-pre"><code>${escapeHtml(finding.fix_snippet)}</code></pre>`;
      }

      let fixValueHtml = "";
      if (finding.fix_value) {
        fixValueHtml = `<p style="margin: 0.35rem 0 0 0; font-size: 0.875rem;"><strong>Recommended value:</strong> <code>${escapeHtml(finding.fix_value)}</code></p>`;
      }

      card.innerHTML = `
        <div class="card-top">
          <div class="badges-group">
            ${badgesHtml}
          </div>
          <span style="font-size: 0.8125rem; font-family: var(--font-mono); color: var(--text-muted);">${escapeHtml(finding.rule || "")}</span>
        </div>

        <h4 id="finding-title-${index}" class="finding-problem">${escapeHtml(finding.problem)}</h4>

        <div class="finding-section">
          <span class="section-label">Why it matters</span>
          <p class="finding-why">${escapeHtml(finding.why_it_matters || "No explanation provided.")}</p>
        </div>

        <div class="finding-section">
          <span class="section-label">Evidence</span>
          <div class="evidence-box">${escapeHtml(finding.evidence || "Observed during inspection.")}</div>
        </div>

        <div class="finding-section">
          <span class="section-label">Suggested Fix</span>
          <div class="fix-box">
            <div>${escapeHtml(finding.fix || "Review and update element.")}</div>
            ${fixValueHtml}
            ${fixSnippetHtml}
          </div>
        </div>

        <div class="card-footer">
          <button type="button" class="btn-copy copy-issue-btn" aria-label="Copy finding #${index + 1} as GitHub issue">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>Copy as GitHub issue</span>
          </button>
        </div>
      `;

      const copyBtn = card.querySelector(".copy-issue-btn");
      copyBtn.addEventListener("click", () => {
        const issueMd = buildIssueMarkdown(finding, result);
        copyToClipboard(issueMd, copyBtn);
      });

      findingsList.appendChild(card);
    });
  }

  function displayResult(result) {
    currentResult = result;
    hideError();
    emptyState.classList.add("hidden");
    progressArea.classList.add("hidden");
    resultsContainer.classList.remove("hidden");

    // Header updates
    const isRepo = result.mode === "repo";
    resultBadgeMode.textContent = isRepo ? "GitHub Repository" : "Website Audit";
    resultsUrlLink.textContent = result.url || "Target URL";
    resultsUrlLink.href = result.url || "#";

    // Mode-specific sections
    if (isRepo) {
      screenshotCard.classList.add("hidden");
      const summaryContent = result.summary || (result.notes && result.notes.length ? result.notes.join("\n\n") : "");
      if (summaryContent) {
        repoSummaryText.textContent = summaryContent;
        repoSummaryCard.classList.remove("hidden");
      } else {
        repoSummaryCard.classList.add("hidden");
      }
    } else {
      repoSummaryCard.classList.add("hidden");
      if (result.annotated_image) {
        annotatedImage.src = result.annotated_image;
        screenshotCard.classList.remove("hidden");
      } else {
        screenshotCard.classList.add("hidden");
      }
    }

    renderStats(result);
    renderFindings(result.findings || [], result);
  }

  // -------------------------------------------------------------------------
  // Filter Chips Interactions
  // -------------------------------------------------------------------------

  filterChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      filterChips.forEach((c) => {
        c.classList.remove("active");
        c.setAttribute("aria-pressed", "false");
      });
      chip.classList.add("active");
      chip.setAttribute("aria-pressed", "true");
      activeFilter = chip.dataset.filter || "all";
      if (currentResult) {
        renderFindings(currentResult.findings || [], currentResult);
      }
    });
  });

  // -------------------------------------------------------------------------
  // Demo Mode (?demo=1)
  // -------------------------------------------------------------------------

  function loadDemoData() {
    hideError();
    emptyState.classList.add("hidden");
    resultsContainer.classList.add("hidden");
    progressArea.classList.remove("hidden");

    progressStatusText.textContent = "Loading demo sample audit...";
    progressStepText.textContent = "Fetching pre-recorded multi-source findings (?demo=1)...";
    stepsList.innerHTML = `<li class="current">Reading web/sample_result.json</li>`;

    const sampleUrl = "/static/sample_result.json";
    fetch(sampleUrl)
      .then((res) => {
        if (!res.ok) {
          return fetch("/sample_result.json");
        }
        return res;
      })
      .then((res) => {
        if (!res.ok) throw new Error(`Could not load sample data (HTTP ${res.status})`);
        return res.json();
      })
      .then((data) => {
        setTimeout(() => {
          displayResult(data);
        }, 150);
      })
      .catch((err) => {
        progressArea.classList.add("hidden");
        emptyState.classList.remove("hidden");
        showError(`Failed to load sample demo: ${err.message}`);
      });
  }

  loadDemoBtn.addEventListener("click", loadDemoData);
  quickDemoBtn.addEventListener("click", loadDemoData);

  // Auto-trigger demo if url query has ?demo=1
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("demo") === "1" || window.location.search.includes("demo=1")) {
    loadDemoData();
  }

  // -------------------------------------------------------------------------
  // Form Submission & API Pipeline Connection
  // -------------------------------------------------------------------------

  function pollJob(jobId) {
    fetch(`/api/jobs/${encodeURIComponent(jobId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Status polling error (${res.status})`);
        return res.json();
      })
      .then((data) => {
        if (data.step) {
          progressStepText.textContent = data.step;
          // Add step to list if not already present
          const existing = Array.from(stepsList.children).map((li) => li.textContent);
          if (!existing.includes(data.step)) {
            Array.from(stepsList.children).forEach((li) => li.classList.remove("current"));
            const li = document.createElement("li");
            li.className = "current";
            li.textContent = data.step;
            stepsList.appendChild(li);
          }
        }

        if (data.status === "done") {
          clearInterval(pollIntervalId);
          pollIntervalId = null;
          analyzeBtn.disabled = false;
          displayResult(data.result);
        } else if (data.status === "error") {
          clearInterval(pollIntervalId);
          pollIntervalId = null;
          analyzeBtn.disabled = false;
          progressArea.classList.add("hidden");
          emptyState.classList.remove("hidden");
          showError(data.error || "Analysis job failed.");
        }
      })
      .catch((err) => {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
        analyzeBtn.disabled = false;
        progressArea.classList.add("hidden");
        emptyState.classList.remove("hidden");
        showError(`Network error while polling job: ${err.message}`);
      });
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    hideError();

    const mode = modeRepoRadio.checked ? "repo" : "site";
    const rawUrl = urlInput.value.trim();

    if (!rawUrl) {
      showError("Please enter a valid URL.");
      urlInput.focus();
      return;
    }

    if (rawUrl.length > 300) {
      showError("URL length exceeds maximum of 300 characters.");
      return;
    }

    // Client-side URL scheme validation
    try {
      const parsed = new URL(rawUrl);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        showError("Only http:// and https:// URLs are supported.");
        return;
      }
      if (mode === "repo" && !parsed.hostname.includes("github.com")) {
        showError("Repository mode only accepts github.com links.");
        return;
      }
    } catch (_) {
      showError("Please enter a valid, complete URL starting with http:// or https://");
      return;
    }

    // Start progress
    emptyState.classList.add("hidden");
    resultsContainer.classList.add("hidden");
    progressArea.classList.remove("hidden");
    analyzeBtn.disabled = true;

    progressStatusText.textContent = `Analyzing ${mode === "repo" ? "repository" : "website"}...`;
    progressStepText.textContent = "Scheduling analysis job...";
    stepsList.innerHTML = `<li class="current">Job submitted</li>`;

    fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, url: rawUrl }),
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().then((errData) => {
            throw new Error(errData.detail || `Server error ${res.status}`);
          });
        }
        return res.json();
      })
      .then((data) => {
        const jobId = data.job_id;
        if (!jobId) throw new Error("No job ID returned from server.");
        pollIntervalId = setInterval(() => pollJob(jobId), 600);
      })
      .catch((err) => {
        analyzeBtn.disabled = false;
        progressArea.classList.add("hidden");
        emptyState.classList.remove("hidden");
        showError(err.message || "Failed to start analysis job.");
      });
  });
});
