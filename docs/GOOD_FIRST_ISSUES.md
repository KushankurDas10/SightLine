# Good First Issues for New Contributors

Thank you for your interest in contributing to SightLine! Below are 6 well-scoped, realistic tasks designed for new and intermediate contributors. Each issue describes the background, exact files to modify, and clear acceptance criteria.

---

### Issue 1: Detect Missing or Empty `<html lang>` Attribute
- **Difficulty**: Beginner
- **Area**: Website Accessibility Check
- **Context**: WCAG 2.1 Success Criterion 3.1.1 (Language of Page) requires every HTML document to specify a default human language via the `lang` attribute on the `<html>` tag. Screen readers rely on this to load the correct pronunciation rules and speech synthesizers.
- **Files to Change**:
  - `sightline/site/capture.py` (extract `html_lang` from DOM facts)
  - `sightline/site/checks.py` (add `check_html_lang` rule function)
  - `tests/test_checks.py` (add unit tests for missing, empty, and valid `lang`)
- **Acceptance Criteria**:
  - When `<html lang="...">` is missing or whitespace-only, emit a `Finding` with:
    - `rule`: `"missing-html-lang"`
    - `severity`: `"high"`
    - `problem`: `"HTML document does not declare a language attribute on the <html> tag."`
    - `fix`: `"Add a valid lang attribute to the <html> tag (e.g., <html lang=\"en\">)."`
  - When a valid language tag is present (e.g. `lang="en"` or `lang="fr"`), no finding is produced.
  - All existing unit tests continue to pass.

---

### Issue 2: Detect Ambiguous or Non-Descriptive Link Text
- **Difficulty**: Beginner
- **Area**: Website Accessibility Check
- **Context**: WCAG 2.1 Success Criterion 2.4.4 (Link Purpose in Context) emphasizes that users who tab through links or read them out of context via screen reader link lists cannot understand links with vague text like "click here", "read more", or "learn more".
- **Files to Change**:
  - `sightline/site/checks.py` (add `check_vague_links` function)
  - `tests/test_checks.py` (unit test covering positive and negative test cases)
- **Acceptance Criteria**:
  - Flag `<a>` elements whose accessible text or text content matches common vague phrases (e.g., `"click here"`, `"more"`, `"read more"`, `"link"`, `"here"`).
  - Emit a `Finding` with `rule: "vague-link-text"` and `severity: "medium"`.
  - Provide fix guidance suggesting descriptive destination text (e.g., "Read more about our privacy policy").

---

### Issue 3: Add `--json` Output Flag to CLI for Machine-Readable Export
- **Difficulty**: Beginner
- **Area**: CLI / Developer Experience
- **Context**: Developers frequently integrate SightLine into automated CI/CD pipelines, pre-commit hooks, or external dashboards where they need JSON emitted directly to standard output.
- **Files to Change**:
  - `sightline/cli.py` (add `--json` argument to both `site` and `repo` subcommands)
  - `tests/test_pipeline.py` (add test verifying CLI output when `--json` is supplied)
- **Acceptance Criteria**:
  - When `--json` is passed, `sightline` prints only valid serialized JSON (`result.to_dict()`) to `sys.stdout`.
  - Human-oriented terminal formatting (ANSI colored banners, step spinners) is suppressed when `--json` is active.
  - Exits with status code 0 on successful inspection.

---

### Issue 4: Check for Security Policy (`SECURITY.md`) in Repositories
- **Difficulty**: Beginner
- **Area**: Repository Health Check
- **Context**: Open source security best practices encourage repositories to publish a vulnerability disclosure policy in `SECURITY.md` or `.github/SECURITY.md`.
- **Files to Change**:
  - `sightline/repo/checks.py` (add `check_security_policy` function)
  - `tests/test_repo.py` (add unit test for repository fixtures with and without `SECURITY.md`)
- **Acceptance Criteria**:
  - Check whether `SECURITY.md` or `.github/SECURITY.md` exists in `repo_snapshot.files`.
  - If missing, emit a `Finding` with:
    - `rule`: `"missing-security-policy"`
    - `severity`: `"low"`
    - `problem`: `"Repository is missing a SECURITY.md vulnerability reporting policy."`
    - `fix`: `"Add a SECURITY.md file at root or in .github/ documenting disclosure procedures."`
  - Passes when either file path is detected.

---

### Issue 5: Keyboard Shortcut for Web UI Theme Toggle (`Shift + D`)
- **Difficulty**: Beginner
- **Area**: Web UI / Frontend Accessibility
- **Context**: SightLine provides light and dark themes. Adding a global keyboard shortcut improves navigation efficiency for keyboard-only users and reviewers testing accessibility in both color modes.
- **Files to Change**:
  - `web/static/app.js` (add global keyboard event listener)
  - `web/static/index.html` (document shortcut in theme toggle tooltip/label)
- **Acceptance Criteria**:
  - Pressing `Shift + D` toggles the application theme between light and dark.
  - Shortcut is ignored when focus is currently inside an input field (`<input>`, `<textarea>`).
  - The preference is preserved in `localStorage` and announced to screen readers.

---

### Issue 6: Target Size Exemption for Inline Text Links
- **Difficulty**: Intermediate
- **Area**: Browser Capture & WCAG 2.2 Conformance
- **Context**: WCAG 2.2 Success Criterion 2.5.8 (Target Size Minimum, 24x24px) explicitly exempts inline links within sentences or blocks of text. Currently, `check_small_targets` evaluates all interactive elements equally.
- **Files to Change**:
  - `sightline/site/capture.py` (capture display property or compute whether an `<a>` element is inline inside text)
  - `sightline/site/checks.py` (update `check_small_targets` to respect the inline text link exemption)
  - `tests/test_checks.py` (test confirming inline links in text blocks are exempt while standalone buttons/icons are flagged)
- **Acceptance Criteria**:
  - Standalone buttons, icon buttons, and navigation links under 24x24px are flagged as `small-target`.
  - Inline links that flow within standard paragraph body copy are exempted per WCAG 2.2 guidelines.
  - All existing browser capture tests continue to pass.
