# Contributing to SightLine

Thank you for contributing to SightLine! We welcome contributions ranging from new accessibility rules and repository analyzers to bug fixes and documentation improvements.

---

## Code of Conduct

All contributors and maintainers are expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md). Please treat all community members with respect and kindness.

---

## Development Environment Setup

### 1. Prerequisites
- **Python**: Version 3.11 or higher
- **Git**
- *(Optional)* Gemini API Key (`GEMINI_API_KEY`) for live AI evaluation
- *(Optional)* GitHub Token (`GITHUB_TOKEN`) to avoid unauthenticated API rate limits

### 2. Clone and Install
```bash
# Clone the repository
git clone https://github.com/KushankurDas10/SightLine.git
cd SightLine

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# Install package in editable mode with development dependencies
pip install -e ".[dev]"

# Install Chromium for Playwright headless browser testing
playwright install chromium
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` (gitignored):
```bash
cp .env.example .env
```
For local testing without an API key, set `MOCK=1` in your `.env` or shell.

---

## Running Linters & Tests

Always run the linter and test suite before committing changes:

### 1. Code Style & Linting
We use [Ruff](https://docs.astral.sh/ruff/) for formatting and linting:
```bash
ruff check .
```

### 2. Fast Unit Tests (Offline / Mock Mode)
Runs in ~1 second with zero network or external dependencies:
```bash
pytest -m "not live and not browser"
```

### 3. Browser Tests (Playwright Headless)
Verifies DOM extraction, screenshot badge marking, verified fixes, and web UI:
```bash
pytest -m browser
```

### 4. Live API Tests (Requires Valid API Keys)
Tests live integration with Gemini API and GitHub:
```bash
pytest -m live
```

---

## Contributing New Analyzers

If you want to add a new measured check for websites or repositories:
- Read our tutorial: [docs/ADDING_AN_ANALYZER.md](docs/ADDING_AN_ANALYZER.md).
- Browse starter tasks: [docs/GOOD_FIRST_ISSUES.md](docs/GOOD_FIRST_ISSUES.md).

---

## Pull Request Workflow

1. **Branch Naming**: Create a descriptive branch from `main`:
   - `feat/missing-html-lang`
   - `fix/contrast-rounding-error`
   - `docs/clarify-prefetch-script`
2. **One Logical Change**: Keep pull requests focused on a single feature, bug fix, or documentation update.
3. **Evidence Requirement**: If introducing new rules, ensure findings include mathematically precise `evidence` (never fabricated).
4. **No Direct Secret Commits**: Never include `.env`, keys, or test tokens in commits.
5. **Update Tests**: Add unit tests in `tests/` covering new rules, edge cases, and invalid inputs.
6. **Submit PR**: Open a pull request against `main`. Fill out the [Pull Request Template](.github/PULL_REQUEST_TEMPLATE.md).
