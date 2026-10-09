# Adding an Analyzer to SightLine

SightLine uses **deterministic, measured checks** to discover accessibility defects and repository structure issues with 100% confidence, complemented by Gemma 4 for contextual visual and documentation review.

This guide provides a step-by-step walkthrough for creating, testing, and registering a new measured analyzer.

---

## 1. Anatomy of a Finding

All analyzers return `sightline.models.Finding` objects. When creating a measured finding, adhere strictly to these conventions:

```python
from sightline.models import Finding

Finding(
    id="site-005",             # Unique ID generated via counter/uuid
    source="measured",         # MUST be "measured" for deterministic code checks
    target="site",             # "site" or "repo"
    rule="missing-html-lang",  # Kebab-case identifier
    severity="high",           # "high", "medium", or "low"
    problem="HTML element is missing a language attribute.",
    why_it_matters="Screen readers need the lang attribute to pronounce text correctly.",
    fix="Add a valid lang attribute to the <html> tag, e.g., <html lang=\"en\">.",
    fix_snippet="<html lang=\"en\">",
    fix_value="en",
    evidence="Element <html> has no lang attribute present in DOM facts",
    confidence=1.0,            # Always 1.0 for measured code checks
    element_number=1,          # Optional: int matching DOM snapshot element
    box=None,                  # Optional: Box(x, y, w, h) for spatial bounding
    file_path=None,            # Optional: str path for repo findings
)
```

---

## 2. Adding a Website Analyzer (`sightline/site/checks.py`)

Website checks operate over a `PageSnapshot` object containing DOM facts and element bounding boxes collected by Playwright in `sightline/site/capture.py`.

### Step 1: Inspect Available Facts
Each element in `snapshot.elements` has:
- `number`: Assigned sequential integer badge.
- `tag`: Lowercase tag name (e.g. `button`, `a`, `img`, `input`).
- `role`: ARIA role.
- `name`: Accessible name computed via accessibility tree.
- `text`: Visible inner text.
- `box`: Bounding box (`x`, `y`, `w`, `h`).
- `meta`: Dictionary containing computed CSS properties (`color`, `background`, `font_px`, `font_weight`, etc.).

### Step 2: Implement the Check Function
Add your rule in `sightline/site/checks.py`. For example, checking for images with empty or missing alt text:

```python
def check_image_alt(elements: list[ElementSnapshot], make_id: Callable[[], str]) -> list[Finding]:
    """Flag <img> elements missing alt text or an accessible label."""
    findings = []
    for el in elements:
        if el.tag == "img" and not el.name and not el.meta.get("alt"):
            findings.append(
                Finding(
                    id=make_id(),
                    source="measured",
                    target="site",
                    rule="missing-alt",
                    severity="high",
                    problem="Image has no accessible alternative text.",
                    why_it_matters="Users who rely on screen readers cannot understand the content or purpose of the image.",
                    fix='Add a descriptive alt attribute, e.g. <img alt="Company Logo">.',
                    fix_snippet='alt="Description of image"',
                    fix_value="Description",
                    evidence=f"Element #{el.number} <img> has empty alt attribute and empty accessible name",
                    confidence=1.0,
                    element_number=el.number,
                    box=el.box,
                )
            )
    return findings
```

### Step 3: Call the Check in `run_checks`
Register your function inside `sightline.site.checks.run_checks(snapshot)`:

```python
# In sightline/site/checks.py:
findings.extend(check_image_alt(snapshot.elements, make_id))
```

### Step 4: Write Unit Tests
Add offline unit tests in `tests/test_checks.py`:

```python
def test_missing_alt_check():
    snapshot = PageSnapshot(
        url="https://example.com",
        title="Test Page",
        elements=[
            ElementSnapshot(number=1, tag="img", role="img", name="", box=Box(0, 0, 100, 100), meta={})
        ]
    )
    findings = run_checks(snapshot)
    alt_findings = [f for f in findings if f.rule == "missing-alt"]
    assert len(alt_findings) == 1
    assert alt_findings[0].element_number == 1
```

---

## 3. Adding a Repository Analyzer (`sightline/repo/checks.py`)

Repository checks operate over a `RepoSnapshot` object containing:
- `owner`, `name`, `default_branch`, `description`, `stars`, `forks`, etc.
- `files`: Complete flat list of repository relative paths (e.g. `["README.md", ".github/workflows/ci.yml"]`).
- `file_contents`: Dictionary mapping lowercase filenames to string contents (e.g., `{"readme.md": "# Title\n..."}`).

### Step 1: Implement the Check Function
Add your check function in `sightline/repo/checks.py`:

```python
def check_contributing_guide(snapshot: RepoSnapshot, make_id: Callable[[], str]) -> list[Finding]:
    """Check if repository contains a CONTRIBUTING guide."""
    contributing_files = {"contributing", "contributing.md", ".github/contributing.md"}
    has_guide = any(f.lower() in contributing_files for f in snapshot.files)

    if not has_guide:
        return [
            Finding(
                id=make_id(),
                source="measured",
                target="repo",
                rule="missing-contributing",
                severity="medium",
                problem="Repository does not provide a CONTRIBUTING.md guide.",
                why_it_matters="Contributing instructions guide community members on environment setup, style rules, and PR workflows.",
                fix="Create a CONTRIBUTING.md file in the root or .github/ folder.",
                fix_snippet="## Contributing\n\n1. Fork and clone the repository\n2. Install dependencies\n3. Run tests",
                fix_value="CONTRIBUTING.md",
                evidence="No CONTRIBUTING or CONTRIBUTING.md file found in repository file list",
                confidence=1.0,
                file_path=None,
            )
        ]
    return []
```

### Step 2: Register in `run_checks`
Call the check inside `sightline.repo.checks.run_checks(snapshot)`:

```python
# In sightline/repo/checks.py:
findings.extend(check_contributing_guide(snapshot, make_id))
```

### Step 3: Add Unit Tests
Add offline unit tests in `tests/test_repo.py`:

```python
def test_missing_contributing_guide():
    snapshot = RepoSnapshot(
        owner="test-org",
        name="test-repo",
        default_branch="main",
        files=["README.md", "LICENSE"],
        file_contents={"readme.md": "# Test Repo"}
    )
    findings = run_checks(snapshot)
    assert any(f.rule == "missing-contributing" for f in findings)
```

---

## 4. Verification & Linting Checklist

Before submitting a pull request with a new analyzer:
1. **Deterministic evidence**: Ensure every finding provides precise `evidence` (never fabricated).
2. **Zero external dependencies**: Use Python standard library or existing dependencies only.
3. **Run linter**: `ruff check .`
4. **Run offline test suite**: `pytest -m "not live and not browser"`
5. **Update documentation**: Add your new rule to the table in `README.md` and `docs/ARCHITECTURE.md`.
