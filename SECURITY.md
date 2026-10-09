# Security Policy

SightLine takes security seriously. This document outlines our security policies, how to report vulnerabilities, and the defensive controls engineered directly into the system.

---

## Supported Versions

| Version | Supported          |
| :---    | :---               |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

---

## Reporting a Vulnerability

If you discover a security vulnerability in SightLine, please **do not open a public GitHub issue**. Instead, report it privately through one of the following methods:

1. **GitHub Private Vulnerability Reporting**: Use the "Report a vulnerability" button under the **Security** tab of the GitHub repository.
2. **Direct Contact**: Contact the repository maintainers directly with details of the vulnerability.

Please include:
- A description of the issue and potential impact.
- Step-by-step reproduction instructions or proof-of-concept.
- Any suggested mitigations.

We will acknowledge receipt within 48 hours and work with you on a coordinated disclosure timeline.

---

## Security Architecture & Defenses

SightLine processes untrusted URLs, repository contents, and AI model outputs. The following safeguards are built into the architecture:

### 1. SSRF (Server-Side Request Forgery) Prevention
- In website inspection mode, all URLs undergo rigorous validation in `sightline.site.capture.validate_url`.
- The validator resolves DNS hostnames and rejects:
  - Loopback addresses (`127.0.0.0/8`, `::1`, `localhost`)
  - Private RFC 1918 networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
  - Link-local and cloud metadata endpoints (`169.254.169.254`)
  - Non-HTTP/HTTPS schemes (e.g., `file://`, `ftp://`, `gopher://`)
- Inspection of private endpoints is strictly disabled by default and can only be enabled for offline test harnesses by setting `ALLOW_PRIVATE_URLS=1`.

### 2. Isolation of AI Model Outputs (No Code Execution)
- AI model outputs from Gemma are treated as untrusted data.
- SightLine **never executes** code generated or returned by an LLM (`eval()`, `exec()`, or dynamic scripting).
- Model responses are parsed strictly into structured JSON against typed schemas (`sightline.models.Finding`).
- Fix application in the verification engine (`sightline.site.verify`) uses fixed, deterministic code paths only:
  - `missing-name`: Sanitized plain text `aria-label` (max 80 chars, special characters stripped).
  - `low-contrast`: Strictly checked against regex `^#[0-9a-fA-F]{6}$`.
  - `small-target`: Enforces fixed CSS `min-width: 24px; min-height: 24px`.

### 3. Strict Evidence Verification
- Every AI finding (`source: "ai"`) is subject to automated evidence verification:
  - **Websites**: The referenced `element_number` must match a DOM element present in the captured snapshot.
  - **Repositories**: The `evidence` field must match an exact verbatim quote in the repository files.
- Any finding that fails evidence verification is automatically dropped to prevent hallucinations from polluting results.

### 4. Credential & Secret Protection
- Credentials (`GEMINI_API_KEY`, `GITHUB_TOKEN`) are loaded from environment variables or gitignored `.env` files via `python-dotenv`.
- Credentials are never logged, never returned in API payloads, and never included in error messages.
