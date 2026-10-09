// SightLine - Modern, Accessible Inspector Frontend
document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const form = document.getElementById("audit-form");
  const urlInput = document.getElementById("url-input");
  const urlLabel = document.getElementById("url-label");
  const urlHint = document.getElementById("url-hint");
  const analyzeBtn = document.getElementById("analyze-btn");
  const modeSiteRadio = document.getElementById("mode-site");
  const modeRepoRadio = document.getElementById("mode-repo");

  const themeToggle = document.getElementById("theme-toggle");
  const loadDemoBtn = document.getElementById("load-demo-btn");
  const quickDemoBtn = document.getElementById("quick-demo-btn");
  const quickDemoRepoBtn = document.getElementById("quick-demo-repo-btn");
  const demoSiteLink = document.getElementById("demo-site-link");
  const demoRepoLink = document.getElementById("demo-repo-link");

  const errorBanner = document.getElementById("error-banner");
  const errorMessage = document.getElementById("error-message");
  const errorDismissBtn = document.getElementById("error-dismiss-btn");

  const progressArea = document.getElementById("progress-area");
  const progressStatusText = document.getElementById("progress-status-text");
  const progressStepText = document.getElementById("progress-step-text");
  const stepsList = document.getElementById("steps-list");
  const stepperBar = document.getElementById("stepper-bar");
  const skeletonContainer = document.getElementById("skeleton-container");

  const emptyState = document.getElementById("empty-state");
  const resultsContainer = document.getElementById("results-container");
  const partialBanner = document.getElementById("partial-banner");
  const partialBadge = document.getElementById("partial-badge");

  const resultBadgeMode = document.getElementById("result-badge-mode");
  const resultsUrlLink = document.getElementById("results-url-link");
  const repoCard = document.getElementById("repo-card");
  const repoCardLink = document.getElementById("repo-card-link");
  const repoCardDesc = document.getElementById("repo-card-desc");
  const repoFactsPills = document.getElementById("repo-facts-pills");
  const repoSummaryCard = document.getElementById("repo-summary-card");
  const repoSummaryText = document.getElementById("repo-summary-text");

  const screenshotCard = document.getElementById("screenshot-card");
  const screenshotContainer = document.getElementById("screenshot-container");
  const annotatedImage = document.getElementById("annotated-image");
  const screenshotOverlay = document.getElementById("screenshot-overlay");
  const screenshotPlaceholder = document.getElementById("screenshot-placeholder");

  const statTotal = document.getElementById("stat-total");
  const statMeasured = document.getElementById("stat-measured");
  const statAi = document.getElementById("stat-ai");
  const statVerified = document.getElementById("stat-verified");

  const explainerDetails = document.getElementById("explainer-details");
  const filterChips = document.querySelectorAll(".filter-chips .chip");
  const findingsList = document.getElementById("findings-list");
  const toast = document.getElementById("toast");
  const toastMessage = document.getElementById("toast-message");

  const compareModal = document.getElementById("compare-modal");
  const compareModalClose = document.getElementById("compare-modal-close");
  const compareModalImg = document.getElementById("compare-modal-img");
  const compareModalNote = document.getElementById("compare-modal-note");
  const compareModalTitle = document.getElementById("compare-modal-title");

  if (compareModal && compareModalClose) {
    compareModalClose.addEventListener("click", () => compareModal.close());
    compareModal.addEventListener("click", (e) => {
      const rect = compareModal.getBoundingClientRect();
      const isInDialog = (
        rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
        rect.left <= e.clientX && e.clientX <= rect.left + rect.width
      );
      if (!isInDialog) compareModal.close();
    });
  }

  let currentResult = null;
  let activeFilter = "all";
  let pollIntervalId = null;
  let activeBoxElement = null;

  // -------------------------------------------------------------------------
  // 1. Theme Management (Light / Dark)
  // -------------------------------------------------------------------------
  function getPreferredTheme() {
    try {
      const stored = localStorage.getItem("sightline-theme");
      if (stored === "dark" || stored === "light") return stored;
    } catch (_) {
      // localStorage may fail in restricted/iframe contexts
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("sightline-theme", theme);
    } catch (_) {}
  }

  applyTheme(getPreferredTheme());

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || getPreferredTheme();
      const next = current === "dark" ? "light" : "dark";
      applyTheme(next);
    });
  }

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

  function formatCount(n) {
    if (n === null || n === undefined || isNaN(n) || n <= 0) return "0";
    const val = Number(n);
    if (val >= 1000000) {
      const m = (val / 1000000).toFixed(1);
      return (m.endsWith(".0") ? m.slice(0, -2) : m) + "M";
    }
    if (val >= 1000) {
      const k = (val / 1000).toFixed(1);
      return (k.endsWith(".0") ? k.slice(0, -2) : k) + "k";
    }
    return String(val);
  }

  function formatRelativeTime(isoString) {
    if (!isoString) return "recently";
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
      if (isNaN(diffSec) || diffSec < 0) return "recently";
      if (diffSec < 3600) return "recently";
      const hours = Math.floor(diffSec / 3600);
      if (hours < 24) return `${hours}h ago`;
      const days = Math.floor(hours / 24);
      if (days < 30) return `${days}d ago`;
      const months = Math.floor(days / 30);
      if (months < 12) return `${months}mo ago`;
      const years = Math.floor(days / 365);
      return `${years}y ago`;
    } catch (_) {
      return "recently";
    }
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
  // Mode Selection
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
  // Stepper & Progress State
  // -------------------------------------------------------------------------
  const STEP_KEYS = ["init", "checks", "gemma", "verify", "done"];

  function updateStepper(stepName) {
    if (!stepperBar) return;
    const lower = (stepName || "").toLowerCase();
    let activeIndex = 0;

    if (lower.includes("opening") || lower.includes("fetching") || lower.includes("setup")) {
      activeIndex = 0;
    } else if (lower.includes("checks") || lower.includes("screenshot") || lower.includes("marking")) {
      activeIndex = 1;
    } else if (lower.includes("gemma") || lower.includes("review")) {
      activeIndex = 2;
    } else if (lower.includes("verify") || lower.includes("verifying")) {
      activeIndex = 3;
    } else if (lower.includes("done") || lower.includes("completed") || lower.includes("drawing") || lower.includes("writing")) {
      activeIndex = 4;
    }

    const items = stepperBar.querySelectorAll(".step-item");
    items.forEach((item, idx) => {
      item.classList.remove("step-active", "step-done", "step-pending");
      if (idx < activeIndex) {
        item.classList.add("step-done");
      } else if (idx === activeIndex) {
        item.classList.add("step-active");
      } else {
        item.classList.add("step-pending");
      }
    });
  }

  // -------------------------------------------------------------------------
  // Clipboard Copy Handlers
  // -------------------------------------------------------------------------
  function copyToClipboard(text, btnElement, successLabel, toastLabel) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        handleCopySuccess(btnElement, successLabel, toastLabel);
      }).catch(() => {
        fallbackCopy(text, btnElement, successLabel, toastLabel);
      });
    } else {
      fallbackCopy(text, btnElement, successLabel, toastLabel);
    }
  }

  function fallbackCopy(text, btnElement, successLabel, toastLabel) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand("copy");
      handleCopySuccess(btnElement, successLabel, toastLabel);
    } catch (e) {
      console.error("Copy failed", e);
    }
    document.body.removeChild(textarea);
  }

  function handleCopySuccess(btnElement, successLabel, toastLabel) {
    btnElement.classList.add("copied");
    const originalHtml = btnElement.innerHTML;
    btnElement.innerHTML = `<span>✓ ${escapeHtml(successLabel || "Copied!")}</span>`;
    showToast(toastLabel || "Copied to clipboard!");
    setTimeout(() => {
      btnElement.classList.remove("copied");
      btnElement.innerHTML = originalHtml;
    }, 2000);
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

  // -------------------------------------------------------------------------
  // Screenshot Overlays & Box Highlighting
  // -------------------------------------------------------------------------
  function clearHighlightBox() {
    if (screenshotOverlay) {
      screenshotOverlay.innerHTML = "";
    }
    document.querySelectorAll(".finding-card.selected-card").forEach((c) => {
      c.classList.remove("selected-card");
    });
  }

  function highlightElementOnScreenshot(finding, cardElement) {
    clearHighlightBox();
    if (!screenshotCard || screenshotCard.classList.contains("hidden")) return;
    if (!annotatedImage || annotatedImage.classList.contains("hidden")) return;

    cardElement.classList.add("selected-card");

    const box = finding.box;
    if (!box) return;

    // Natural dimensions or default
    const pageW = (currentResult && currentResult.page_width) || annotatedImage.naturalWidth || 1280;
    const natH = annotatedImage.naturalHeight || 800;

    // Use percentage coordinates to stay accurate on resize
    const leftPct = (box.x / pageW) * 100;
    const topPct = (box.y / natH) * 100;
    const widthPct = (box.w / pageW) * 100;
    const heightPct = (box.h / natH) * 100;

    const boxEl = document.createElement("div");
    boxEl.className = "screenshot-highlight-box";
    boxEl.style.left = `${leftPct}%`;
    boxEl.style.top = `${topPct}%`;
    boxEl.style.width = `${widthPct}%`;
    boxEl.style.height = `${heightPct}%`;

    if (finding.element_number !== null && finding.element_number !== undefined) {
      const badge = document.createElement("span");
      badge.className = "screenshot-highlight-badge";
      badge.textContent = `Element #${finding.element_number}`;
      boxEl.appendChild(badge);
    }

    screenshotOverlay.appendChild(boxEl);

    // Scroll screenshot container to bring box into view
    const renderedH = annotatedImage.clientHeight || natH;
    const targetScrollY = (box.y / natH) * renderedH - 60;
    screenshotContainer.scrollTo({
      top: Math.max(0, targetScrollY),
      behavior: "smooth",
    });
  }

  // Screenshot image error fallback
  if (annotatedImage) {
    annotatedImage.addEventListener("error", () => {
      if (screenshotPlaceholder) screenshotPlaceholder.classList.remove("hidden");
      annotatedImage.classList.add("hidden");
    });
    annotatedImage.addEventListener("load", () => {
      if (screenshotPlaceholder) screenshotPlaceholder.classList.add("hidden");
      annotatedImage.classList.remove("hidden");
    });
  }

  // -------------------------------------------------------------------------
  // Explainer Navigation
  // -------------------------------------------------------------------------
  function openExplainer() {
    if (explainerDetails) {
      explainerDetails.open = true;
      explainerDetails.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // -------------------------------------------------------------------------
  // Rendering Findings & Cards
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

  function renderFindings(findings, result) {
    findingsList.innerHTML = "";
    clearHighlightBox();

    const isRepo = result.mode === "repo";

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
        <div class="card" style="text-align: center; color: var(--text-muted); padding: 2.5rem 1.5rem;">
          <p style="margin: 0; font-size: 1rem; font-weight: 500;">No findings match the selected filter.</p>
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
      let badgesHtml = `
        <span class="badge badge-sev-${sev}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          ${escapeHtml(sev.toUpperCase())}
        </span>
      `;

      if (finding.source === "measured") {
        badgesHtml += `
          <span class="badge badge-measured">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
            Measured
            <button type="button" class="badge-help-link" title="Learn about Measured checks" aria-label="Learn about Measured checks">?</button>
          </span>
        `;
      } else {
        badgesHtml += `
          <span class="badge badge-ai">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"></path></svg>
            AI-suggested
            <button type="button" class="badge-help-link" title="Learn about AI findings" aria-label="Learn about AI findings">?</button>
          </span>
        `;
      }

      if (finding.verified) {
        badgesHtml += `
          <span class="badge badge-verified">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>
            Verified fix
            <button type="button" class="badge-help-link" title="Learn about Verified fixes" aria-label="Learn about Verified fixes">?</button>
          </span>
        `;
      }

      if (finding.element_number !== null && finding.element_number !== undefined) {
        badgesHtml += `<span class="badge badge-subtle">Element #${escapeHtml(finding.element_number)}</span>`;
      } else if (finding.file_path) {
        badgesHtml += `<span class="badge badge-subtle">${escapeHtml(finding.file_path)}</span>`;
      }

      // Fix details
      let fixSnippetHtml = "";
      if (finding.fix_snippet) {
        fixSnippetHtml = `<pre class="fix-snippet-pre"><code>${escapeHtml(finding.fix_snippet)}</code></pre>`;
      }

      let fixValueHtml = "";
      if (finding.fix_value) {
        fixValueHtml = `<p style="margin: 0.35rem 0 0 0; font-size: 0.875rem;"><strong>Recommended value:</strong> <code>${escapeHtml(finding.fix_value)}</code></p>`;
      }

      // Footer Action: Repo gets "Copy as GitHub issue", Site gets "Copy fix snippet"
      let footerActionHtml = "";
      if (isRepo) {
        footerActionHtml = `
          <button type="button" class="btn-copy copy-issue-btn" aria-label="Copy finding #${index + 1} as GitHub issue">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>Copy as GitHub issue</span>
          </button>
        `;
      } else {
        footerActionHtml = `
          <button type="button" class="btn-copy copy-snippet-btn" aria-label="Copy fix snippet for finding #${index + 1}">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="16 18 22 12 16 6"></polyline>
              <polyline points="8 6 2 12 8 18"></polyline>
            </svg>
            <span>Copy fix snippet</span>
          </button>
        `;
      }

      // Comparison HTML under the fix
      let compareHtml = "";
      const hasCompare = !!(finding.verified && finding.compare_image);
      if (hasCompare) {
        const jobId = (currentResult && (currentResult.job_id || currentResult.id)) || "site";
        const compSrc = finding.compare_image.includes("?")
          ? `${finding.compare_image}&v=${encodeURIComponent(jobId)}`
          : `${finding.compare_image}?v=${encodeURIComponent(jobId)}`;
        const ruleName = escapeHtml(finding.rule || "accessibility");
        const altText = `Before and after: ${ruleName} fix`;
        const noteText = finding.compare_note ? escapeHtml(finding.compare_note) : "";

        compareHtml = `
          <div class="finding-section compare-section">
            <span class="section-label">Before &amp; After Fix</span>
            <figure class="compare-figure">
              <button type="button" class="compare-img-btn" aria-label="Enlarge before and after comparison for ${ruleName}">
                <img 
                  src="${compSrc}" 
                  alt="${altText}" 
                  loading="lazy" 
                  class="compare-preview-img"
                >
                <span class="compare-expand-pill" aria-hidden="true">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="15 3 21 3 21 9"></polyline>
                    <polyline points="9 21 3 21 3 15"></polyline>
                    <line x1="21" y1="3" x2="14" y2="10"></line>
                    <line x1="3" y1="21" x2="10" y2="14"></line>
                  </svg>
                  Click to enlarge
                </span>
              </button>
              <figcaption class="compare-caption">
                ${noteText ? `<span class="compare-note-badge">${noteText}</span>` : ""}
              </figcaption>
            </figure>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="card-top">
          <div class="badges-group">${badgesHtml}</div>
          <span class="rule-code">${escapeHtml(finding.rule || "")}</span>
        </div>

        <h4 id="finding-title-${index}" class="finding-problem">${escapeHtml(finding.problem)}</h4>

        <div class="finding-section">
          <span class="section-label">Why it matters</span>
          <p class="finding-why">${escapeHtml(finding.why_it_matters || "Affects accessibility or code quality.")}</p>
        </div>

        <div class="finding-section">
          <span class="section-label">Evidence</span>
          <div class="evidence-box">${escapeHtml(finding.evidence || "Observed during inspection.")}</div>
        </div>

        <button type="button" class="finding-details-toggle" aria-expanded="${hasCompare ? "true" : "false"}" id="toggle-details-${index}">
          <span class="details-arrow" aria-hidden="true">▶</span>
          <span class="details-label">${hasCompare ? "Hide fix" : "Show fix"}</span>
        </button>

        <div class="finding-collapsible ${hasCompare ? "" : "hidden"}" id="collapsible-${index}">
          <div class="finding-section">
            <span class="section-label">Suggested Fix</span>
            <div class="fix-box">
              <div>${escapeHtml(finding.fix || "Review and update element.")}</div>
              ${fixValueHtml}
              ${fixSnippetHtml}
            </div>
          </div>
          ${compareHtml}
        </div>

        <div class="card-footer">
          ${footerActionHtml}
        </div>
      `;

      // Collapsible details toggle
      const detailsBtn = card.querySelector(`#toggle-details-${index}`);
      const collapsibleContent = card.querySelector(`#collapsible-${index}`);
      detailsBtn.addEventListener("click", () => {
        const isExpanded = detailsBtn.getAttribute("aria-expanded") === "true";
        detailsBtn.setAttribute("aria-expanded", String(!isExpanded));
        if (isExpanded) {
          collapsibleContent.classList.add("hidden");
          detailsBtn.querySelector(".details-label").textContent = "Show fix";
        } else {
          collapsibleContent.classList.remove("hidden");
          detailsBtn.querySelector(".details-label").textContent = "Hide fix";
        }
      });

      // Comparison preview image handlers
      const compImg = card.querySelector(".compare-preview-img");
      if (compImg) {
        compImg.addEventListener("error", () => {
          const compSec = card.querySelector(".compare-section");
          if (compSec) compSec.classList.add("hidden");
        });
      }

      const compBtn = card.querySelector(".compare-img-btn");
      if (compBtn && compImg && compareModal) {
        compBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          compareModalImg.src = compImg.src;
          compareModalImg.alt = compImg.alt;
          if (compareModalNote) {
            compareModalNote.textContent = finding.compare_note || "";
          }
          if (compareModalTitle) {
            compareModalTitle.textContent = `Before & After: ${finding.rule || "Accessibility"} Fix`;
          }
          compareModal.showModal();
        });
      }

      // Badges "?" help link targets explainer
      card.querySelectorAll(".badge-help-link").forEach((helpBtn) => {
        helpBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          openExplainer();
        });
      });

      // Interactive Click to highlight box on screenshot
      card.addEventListener("click", (e) => {
        // Skip if clicked button or code block
        if (e.target.closest("button") || e.target.closest("a") || e.target.closest("pre")) {
          return;
        }
        highlightElementOnScreenshot(finding, card);
      });

      // Action button listeners
      const copyIssueBtn = card.querySelector(".copy-issue-btn");
      if (copyIssueBtn) {
        copyIssueBtn.addEventListener("click", () => {
          const issueMd = buildIssueMarkdown(finding, result);
          copyToClipboard(issueMd, copyIssueBtn, "Copied!", "GitHub issue Markdown copied to clipboard!");
        });
      }

      const copySnippetBtn = card.querySelector(".copy-snippet-btn");
      if (copySnippetBtn) {
        copySnippetBtn.addEventListener("click", () => {
          const snippetText = finding.fix_snippet || finding.fix_value || finding.fix || "";
          copyToClipboard(snippetText, copySnippetBtn, "Copied!", "Fix snippet copied to clipboard!");
        });
      }

      findingsList.appendChild(card);
    });
  }

  function displayResult(result, isPartial = false) {
    currentResult = result;
    hideError();
    emptyState.classList.add("hidden");

    if (!isPartial) {
      progressArea.classList.add("hidden");
      if (partialBanner) partialBanner.classList.add("hidden");
      if (partialBadge) partialBadge.classList.add("hidden");
    } else {
      if (partialBanner) partialBanner.classList.remove("hidden");
      if (partialBadge) partialBadge.classList.remove("hidden");
    }

    resultsContainer.classList.remove("hidden");

    // Header updates
    const isRepo = result.mode === "repo";
    resultBadgeMode.textContent = isRepo ? "GitHub Repository" : "Website Audit";
    resultsUrlLink.textContent = result.url || "Target URL";
    resultsUrlLink.href = result.url || "#";

    // Mode-specific sections
    if (isRepo) {
      screenshotCard.classList.add("hidden");

      // Populate and show Repo Card if repo_info is present
      if (result.repo_info && repoCard) {
        const info = result.repo_info;
        const ownerName = `${info.owner || ""}/${info.name || ""}`;
        if (repoCardLink) {
          repoCardLink.textContent = ownerName;
          repoCardLink.href = info.html_url || `https://github.com/${ownerName}`;
        }
        if (repoCardDesc) {
          repoCardDesc.textContent = info.description || "No description provided.";
        }

        if (repoFactsPills) {
          repoFactsPills.innerHTML = "";

          // Stars pill (star icon, formatted like 1.2k, readable aria-label)
          const starsVal = Number(info.stars || 0);
          const starsPill = document.createElement("span");
          starsPill.className = "repo-fact-pill repo-fact-stars";
          starsPill.setAttribute("aria-label", `${starsVal.toLocaleString()} stars`);
          starsPill.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
            </svg>
            <span class="repo-fact-stars-count">${formatCount(starsVal)}</span>
          `;
          repoFactsPills.appendChild(starsPill);

          // Forks pill
          const forksVal = Number(info.forks || 0);
          const forksPill = document.createElement("span");
          forksPill.className = "repo-fact-pill repo-fact-forks";
          forksPill.setAttribute("aria-label", `${forksVal.toLocaleString()} forks`);
          forksPill.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="6" y1="3" x2="6" y2="15"></line>
              <circle cx="18" cy="6" r="3"></circle>
              <circle cx="6" cy="18" r="3"></circle>
              <path d="M18 9a9 9 0 0 1-9 9"></path>
            </svg>
            <span>${formatCount(forksVal)}</span>
          `;
          repoFactsPills.appendChild(forksPill);

          // Language pill
          if (info.language) {
            const langPill = document.createElement("span");
            langPill.className = "repo-fact-pill repo-fact-lang";
            langPill.setAttribute("aria-label", `Primary language: ${info.language}`);
            langPill.innerHTML = `
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polyline points="16 18 22 12 16 6"></polyline>
                <polyline points="8 6 2 12 8 18"></polyline>
              </svg>
              <span>${escapeHtml(info.language)}</span>
            `;
            repoFactsPills.appendChild(langPill);
          }

          // License pill
          const licensePill = document.createElement("span");
          licensePill.className = "repo-fact-pill repo-fact-license";
          const licName = info.license_name || "No license";
          licensePill.setAttribute("aria-label", `License: ${licName}`);
          licensePill.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
            </svg>
            <span>${escapeHtml(licName)}</span>
          `;
          repoFactsPills.appendChild(licensePill);

          // Open issues pill
          const issuesVal = Number(info.open_issues || 0);
          const issuesPill = document.createElement("span");
          issuesPill.className = "repo-fact-pill repo-fact-issues";
          issuesPill.setAttribute("aria-label", `${issuesVal.toLocaleString()} open issues`);
          issuesPill.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>${formatCount(issuesVal)} issues</span>
          `;
          repoFactsPills.appendChild(issuesPill);

          // Updated pill
          if (info.pushed_at) {
            const updatedPill = document.createElement("span");
            updatedPill.className = "repo-fact-pill repo-fact-updated";
            const relTime = formatRelativeTime(info.pushed_at);
            updatedPill.setAttribute("aria-label", `Updated ${relTime}`);
            updatedPill.innerHTML = `
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10"></circle>
                <polyline points="12 6 12 12 16 14"></polyline>
              </svg>
              <span>Updated ${escapeHtml(relTime)}</span>
            `;
            repoFactsPills.appendChild(updatedPill);
          }
        }

        repoCard.classList.remove("hidden");
      } else if (repoCard) {
        repoCard.classList.add("hidden");
      }

      const summaryContent = result.summary || (result.notes && result.notes.length ? result.notes.join("\n\n") : "");
      if (summaryContent) {
        repoSummaryText.textContent = summaryContent;
        repoSummaryCard.classList.remove("hidden");
      } else {
        repoSummaryCard.classList.add("hidden");
      }
    } else {
      if (repoCard) repoCard.classList.add("hidden");
      repoSummaryCard.classList.add("hidden");
      if (result.annotated_image) {
        // Cache bust if generated in /files/
        const srcUrl = result.annotated_image.startsWith("/files/")
          ? `${result.annotated_image}?t=${Date.now()}`
          : result.annotated_image;
        annotatedImage.src = srcUrl;
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
  // Demo Mode (?demo=site, ?demo=repo, ?demo=1)
  // -------------------------------------------------------------------------
  function loadDemo(type = "site") {
    hideError();
    emptyState.classList.add("hidden");
    resultsContainer.classList.add("hidden");
    progressArea.classList.remove("hidden");

    progressStatusText.textContent = `Loading ${type === "repo" ? "repository" : "website"} demo audit...`;
    progressStepText.textContent = `Fetching verified sample findings (?demo=${type})...`;
    updateStepper("init");
    stepsList.innerHTML = `<li class="current">Reading sample_${type}.json</li>`;

    const sampleUrl = type === "repo" ? "/static/sample_result_repo.json" : "/static/sample_result_site.json";

    fetch(sampleUrl)
      .then((res) => {
        if (!res.ok) throw new Error(`Could not load sample data (${res.status})`);
        return res.json();
      })
      .then((data) => {
        setTimeout(() => {
          updateStepper("done");
          displayResult(data);
        }, 120);
      })
      .catch((err) => {
        progressArea.classList.add("hidden");
        emptyState.classList.remove("hidden");
        showError(`Failed to load demo: ${err.message}`);
      });
  }

  if (loadDemoBtn) {
    loadDemoBtn.addEventListener("click", () => {
      const mode = modeRepoRadio.checked ? "repo" : "site";
      loadDemo(mode);
    });
  }

  if (quickDemoBtn) {
    quickDemoBtn.addEventListener("click", () => loadDemo("site"));
  }

  if (quickDemoRepoBtn) {
    quickDemoRepoBtn.addEventListener("click", () => loadDemo("repo"));
  }

  if (demoSiteLink) {
    demoSiteLink.addEventListener("click", () => loadDemo("site"));
  }

  if (demoRepoLink) {
    demoRepoLink.addEventListener("click", () => loadDemo("repo"));
  }

  // Auto-detect demo query parameters
  const urlParams = new URLSearchParams(window.location.search);
  const demoParam = urlParams.get("demo");
  if (demoParam === "repo") {
    loadDemo("repo");
  } else if (demoParam === "site" || demoParam === "1" || window.location.search.includes("demo=1")) {
    loadDemo("site");
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
          updateStepper(data.step);

          const existing = Array.from(stepsList.children).map((li) => li.textContent);
          if (!existing.includes(data.step)) {
            Array.from(stepsList.children).forEach((li) => li.classList.remove("current"));
            const li = document.createElement("li");
            li.className = "current";
            li.textContent = data.step;
            stepsList.appendChild(li);
          }
        }

        // Partial results surfaced while running
        if (data.status === "running" && data.partial && data.partial.findings) {
          displayResult(data.partial, true);
        }

        if (data.status === "done") {
          clearInterval(pollIntervalId);
          pollIntervalId = null;
          analyzeBtn.disabled = false;
          updateStepper("done");
          displayResult(data.result, false);
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
    updateStepper("init");
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
        pollIntervalId = setInterval(() => pollJob(jobId), 500);
      })
      .catch((err) => {
        analyzeBtn.disabled = false;
        progressArea.classList.add("hidden");
        emptyState.classList.remove("hidden");
        showError(err.message || "Failed to start analysis job.");
      });
  });
});
