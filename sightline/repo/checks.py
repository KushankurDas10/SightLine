"""Measured deterministic checks for repository structure and documentation."""

import json
import re
from pathlib import PurePosixPath
from typing import Any

from sightline.models import Finding, RepoSnapshot


def _extract_headings(markdown_text: str) -> list[str]:
    """Extract all heading titles from markdown text."""
    headings: list[str] = []
    lines = markdown_text.splitlines()
    for i, line in enumerate(lines):
        trimmed = line.strip()
        # ATX headings: # Heading
        match = re.match(r"^#{1,6}\s+(.*)", trimmed)
        if match:
            headings.append(match.group(1).strip())
            continue

        # HTML headings: <h1>Heading</h1>
        html_match = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", trimmed, re.IGNORECASE)
        if html_match:
            headings.append(html_match.group(1).strip())
            continue

        # Setext headings: Line followed by === or ---
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line and (
                set(next_line) == {"="} or (set(next_line) == {"-"} and len(next_line) >= 3)
            ):
                headings.append(trimmed)

    return headings


def _extract_makefile_targets(content: str) -> set[str]:
    """Extract target names from a Makefile."""
    targets: set[str] = set()
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        if trimmed.startswith(".PHONY:"):
            parts = trimmed[len(".PHONY:") :].split()
            targets.update(p.strip() for p in parts if p.strip())
        elif ":" in trimmed and not line.startswith("\t"):
            target_part = trimmed.split(":", 1)[0].strip()
            # Skip variable assignments or pattern rules like %.o
            if not any(ch in target_part for ch in ("=", "%", "$")):
                for token in target_part.split():
                    targets.add(token.strip())
    return targets


def _extract_npm_scripts(content: str) -> set[str]:
    """Extract script names from package.json content."""
    try:
        data: dict[str, Any] = json.loads(content)
        scripts = data.get("scripts", {})
        if isinstance(scripts, dict):
            return set(scripts.keys())
    except Exception:
        pass
    return set()


def check_license(snapshot: RepoSnapshot) -> Finding | None:
    """Check for open source LICENSE file."""
    license_patterns = {
        "license",
        "license.md",
        "license.txt",
        "licence",
        "licence.md",
        "licence.txt",
        "copying",
        "copying.md",
        "copying.txt",
        "unlicense",
    }
    for file_path in snapshot.files:
        name = PurePosixPath(file_path).name.lower()
        if name in license_patterns or name.startswith("license.") or name.startswith("licence."):
            return None

    return Finding(
        id="repo-missing-license",
        source="measured",
        target="repo",
        rule="missing-license",
        severity="high",
        problem="Repository is missing an open source LICENSE file",
        why_it_matters=(
            "Without a license, default copyright laws apply, meaning others cannot "
            "legally use, modify, or distribute the codebase."
        ),
        fix="Add an open source license file (such as MIT or Apache-2.0) at the repository root.",
    )


def check_contributing(snapshot: RepoSnapshot) -> Finding | None:
    """Check for contribution guidelines."""
    for file_path in snapshot.files:
        name = PurePosixPath(file_path).name.lower()
        if name in ("contributing", "contributing.md", "contributing.rst"):
            return None

    return Finding(
        id="repo-missing-contributing",
        source="measured",
        target="repo",
        rule="missing-contributing",
        severity="medium",
        problem="Repository is missing contribution guidelines (CONTRIBUTING.md)",
        why_it_matters=(
            "Guidelines help external contributors understand project workflow, test "
            "conventions, and how to submit pull requests."
        ),
        fix="Add a CONTRIBUTING.md file detailing setup, coding standards, and PR guidelines.",
    )


def check_code_of_conduct(snapshot: RepoSnapshot) -> Finding | None:
    """Check for Code of Conduct."""
    for file_path in snapshot.files:
        name = PurePosixPath(file_path).name.lower()
        if (
            name in ("code_of_conduct", "code_of_conduct.md", "code-of-conduct.md")
            or "code_of_conduct" in name
            or "code-of-conduct" in name
        ):
            return None

    return Finding(
        id="repo-missing-code-of-conduct",
        source="measured",
        target="repo",
        rule="missing-code-of-conduct",
        severity="low",
        problem="Repository is missing a Code of Conduct (CODE_OF_CONDUCT.md)",
        why_it_matters="A Code of Conduct promotes an inclusive, respectful, and safe community.",
        fix="Add a CODE_OF_CONDUCT.md file (such as the Contributor Covenant).",
    )


def check_ci(snapshot: RepoSnapshot) -> Finding | None:
    """Check for continuous integration workflows in .github/workflows."""
    for file_path in snapshot.files:
        norm = file_path.replace("\\", "/")
        if norm.startswith(".github/workflows/") and (
            norm.endswith(".yml") or norm.endswith(".yaml")
        ):
            return None

    return Finding(
        id="repo-missing-ci",
        source="measured",
        target="repo",
        rule="missing-ci",
        severity="medium",
        problem="No continuous integration workflow found in .github/workflows",
        why_it_matters=(
            "CI workflows automatically build, test, and validate changes to prevent regressions."
        ),
        fix="Add a GitHub Actions workflow in .github/workflows/ (such as ci.yml).",
    )


def check_issue_templates(snapshot: RepoSnapshot) -> Finding | None:
    """Check for GitHub issue templates."""
    for file_path in snapshot.files:
        norm = file_path.replace("\\", "/").lower()
        if (
            norm.startswith(".github/issue_template")
            or ".github/issue_template" in norm
            or norm == ".github/issue_template.md"
        ):
            return None

    return Finding(
        id="repo-missing-issue-templates",
        source="measured",
        target="repo",
        rule="missing-issue-templates",
        severity="medium",
        problem="Repository is missing GitHub issue templates",
        why_it_matters=(
            "Issue templates provide contributors with structured forms to report "
            "bugs and suggest features."
        ),
        fix="Add issue templates in .github/ISSUE_TEMPLATE/ for bug reports and feature requests.",
    )


def check_readme_too_short(snapshot: RepoSnapshot) -> Finding | None:
    """Check if README is missing or under 300 characters."""
    readme_content = (snapshot.readme or "").strip()
    if len(readme_content) < 300:
        return Finding(
            id="repo-readme-too-short",
            source="measured",
            target="repo",
            rule="readme-too-short",
            severity="medium",
            problem=f"README is too short ({len(readme_content)} characters, minimum is 300)",
            why_it_matters=(
                "A thorough README introduces visitors to the project's features, architecture, "
                "and usage."
            ),
            fix="Expand the README with an overview, features, installation, and usage examples.",
        )
    return None


def check_readme_missing_install(snapshot: RepoSnapshot) -> Finding | None:
    """Check if README has an installation or setup heading."""
    if not snapshot.readme:
        return Finding(
            id="repo-readme-missing-install",
            source="measured",
            target="repo",
            rule="readme-missing-install",
            severity="medium",
            problem="README is missing an installation or setup section",
            why_it_matters=(
                "New users need clear instructions to install and configure the project."
            ),
            fix="Add an 'Installation' or 'Getting Started' heading to the README.",
        )

    install_keywords = [
        "install",
        "installation",
        "setup",
        "getting started",
        "getting-started",
        "build",
    ]
    headings = _extract_headings(snapshot.readme)
    has_install = any(
        kw in heading.lower() for heading in headings for kw in install_keywords
    )

    if not has_install:
        return Finding(
            id="repo-readme-missing-install",
            source="measured",
            target="repo",
            rule="readme-missing-install",
            severity="medium",
            problem="README is missing an installation or setup section",
            why_it_matters=(
                "New users need clear instructions to install and configure the project."
            ),
            fix="Add an 'Installation' or 'Getting Started' heading to the README.",
        )
    return None


def check_readme_missing_usage(snapshot: RepoSnapshot) -> Finding | None:
    """Check if README has a usage or examples heading."""
    if not snapshot.readme:
        return Finding(
            id="repo-readme-missing-usage",
            source="measured",
            target="repo",
            rule="readme-missing-usage",
            severity="medium",
            problem="README is missing a usage or quick-start section",
            why_it_matters="Developers need quick-start examples to run and test the project.",
            fix="Add a 'Usage' or 'Quick Start' heading with sample code to the README.",
        )

    usage_keywords = [
        "usage",
        "quick start",
        "quickstart",
        "how to use",
        "example",
        "examples",
        "running",
    ]
    headings = _extract_headings(snapshot.readme)
    has_usage = any(
        kw in heading.lower() for heading in headings for kw in usage_keywords
    )

    if not has_usage:
        return Finding(
            id="repo-readme-missing-usage",
            source="measured",
            target="repo",
            rule="readme-missing-usage",
            severity="medium",
            problem="README is missing a usage or quick-start section",
            why_it_matters="Developers need quick-start examples to run and test the project.",
            fix="Add a 'Usage' or 'Quick Start' heading with sample code to the README.",
        )
    return None


def check_tests(snapshot: RepoSnapshot) -> Finding | None:
    """Check if repository contains automated tests."""
    for file_path in snapshot.files:
        norm = file_path.replace("\\", "/").lower()
        parts = norm.split("/")
        basename = parts[-1]

        # Directory indicator
        if any(d in ("test", "tests", "spec", "__tests__") for d in parts[:-1]):
            return None

        # Filename indicator
        if (
            basename.startswith("test_")
            or basename.endswith("_test.py")
            or basename.endswith("_test.go")
            or basename.endswith(".test.js")
            or basename.endswith(".test.ts")
            or basename.endswith(".test.jsx")
            or basename.endswith(".test.tsx")
            or basename.endswith(".spec.js")
            or basename.endswith(".spec.ts")
            or basename in ("test.py", "tests.py")
        ):
            return None

    return Finding(
        id="repo-no-tests",
        source="measured",
        target="repo",
        rule="no-tests",
        severity="low",
        problem="No automated tests found in repository",
        why_it_matters="Automated tests are critical to detect bugs and ensure software stability.",
        fix="Add automated tests under a tests/ directory (e.g. using pytest, jest, or go test).",
    )


def check_readme_command_mismatch(snapshot: RepoSnapshot) -> list[Finding]:
    """Find commands in README code blocks/inline code and verify existence against repo files."""
    if not snapshot.readme:
        return []

    findings: list[Finding] = []
    seen_problems: set[str] = set()

    # Pre-extract package scripts and Makefile targets
    pkg_content = snapshot.key_files.get("package.json", "")
    npm_scripts = _extract_npm_scripts(pkg_content) if pkg_content else set()

    makefile_content = (
        snapshot.key_files.get("Makefile")
        or snapshot.key_files.get("makefile")
        or snapshot.key_files.get("GNUmakefile")
        or ""
    )
    make_targets = (
        _extract_makefile_targets(makefile_content) if makefile_content else set()
    )

    # Normalize files list for fast lookup
    file_set = {f.replace("\\", "/").strip("./") for f in snapshot.files}

    def _file_exists(target_file: str) -> bool:
        clean = target_file.replace("\\", "/").strip("./")
        if clean in file_set:
            return True
        # Check if matches any basename or suffix
        return any(f.endswith("/" + clean) for f in file_set)

    in_fenced_block = False
    idx = 0

    for raw_line in snapshot.readme.splitlines():
        line = raw_line.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fenced_block = not in_fenced_block
            continue

        # Extract candidates: whole line if in code block, or inline code spans `...`
        code_candidates: list[str] = []
        if in_fenced_block:
            if line and not line.startswith("#"):
                code_candidates.append(line)
        else:
            inline_spans = re.findall(r"`([^`]+)`", raw_line)
            code_candidates.extend(inline_spans)

        for candidate in code_candidates:
            # 1. npm run X
            npm_match = re.search(r"\bnpm\s+run\s+([a-zA-Z0-9_\-:]+)", candidate)
            if npm_match:
                script_name = npm_match.group(1).strip()
                if script_name not in npm_scripts:
                    prob_key = f"npm:{script_name}"
                    if prob_key not in seen_problems:
                        seen_problems.add(prob_key)
                        idx += 1
                        findings.append(
                            Finding(
                                id=f"repo-readme-command-mismatch-{idx}",
                                source="measured",
                                target="repo",
                                rule="readme-command-mismatch",
                                severity="medium",
                                problem=(
                                    f"README command 'npm run {script_name}' references a script "
                                    "not found in package.json"
                                ),
                                why_it_matters=(
                                    f"Executing 'npm run {script_name}' will fail because "
                                    "the script is missing from package.json."
                                ),
                                fix=(
                                    f"Add '{script_name}' to package.json 'scripts' or "
                                    "update the README."
                                ),
                                evidence=raw_line.strip(),
                                confidence=1.0,
                                verified=True,
                                verified_note="checked against the repo files",
                            )
                        )

            # 2. make X
            make_match = re.search(r"\bmake\s+([a-zA-Z0-9_\-]+)", candidate)
            if make_match:
                target_name = make_match.group(1).strip()
                if not target_name.startswith("-") and target_name not in make_targets:
                    prob_key = f"make:{target_name}"
                    if prob_key not in seen_problems:
                        seen_problems.add(prob_key)
                        idx += 1
                        findings.append(
                            Finding(
                                id=f"repo-readme-command-mismatch-{idx}",
                                source="measured",
                                target="repo",
                                rule="readme-command-mismatch",
                                severity="medium",
                                problem=(
                                    f"README command 'make {target_name}' references a target not "
                                    "found in Makefile"
                                ),
                                why_it_matters=(
                                    f"Running 'make {target_name}' will fail because the target "
                                    "does not exist in Makefile."
                                ),
                                fix=f"Define '{target_name}:' in Makefile or update the README.",
                                evidence=raw_line.strip(),
                                confidence=1.0,
                                verified=True,
                                verified_note="checked against the repo files",
                            )
                        )

            # 3. pip install -r FILE
            pip_match = re.search(
                r"\bpip\s+install\s+(?:[^\n`]*?\s+)?-r\s+([a-zA-Z0-9_\-\./\\]+)", candidate
            )
            if pip_match:
                req_file = pip_match.group(1).strip("`'\";,").strip()
                if not _file_exists(req_file):
                    prob_key = f"pip:{req_file}"
                    if prob_key not in seen_problems:
                        seen_problems.add(prob_key)
                        idx += 1
                        findings.append(
                            Finding(
                                id=f"repo-readme-command-mismatch-{idx}",
                                source="measured",
                                target="repo",
                                rule="readme-command-mismatch",
                                severity="medium",
                                problem=(
                                    f"README command references requirements file '{req_file}' "
                                    "which does not exist in repository"
                                ),
                                why_it_matters=(
                                    f"Running 'pip install -r {req_file}' will fail because "
                                    "the file is missing."
                                ),
                                fix=(
                                    f"Create '{req_file}' or update the README command with "
                                    "the correct path."
                                ),
                                evidence=raw_line.strip(),
                                confidence=1.0,
                                verified=True,
                                verified_note="checked against the repo files",
                            )
                        )

            # 4. python FILE
            py_match = re.search(r"\bpython(?:3)?\s+([a-zA-Z0-9_\-\./\\]+)", candidate)
            if py_match:
                py_file = py_match.group(1).strip("`'\";,").strip()
                if not py_file.startswith("-") and not _file_exists(py_file):
                    prob_key = f"python:{py_file}"
                    if prob_key not in seen_problems:
                        seen_problems.add(prob_key)
                        idx += 1
                        findings.append(
                            Finding(
                                id=f"repo-readme-command-mismatch-{idx}",
                                source="measured",
                                target="repo",
                                rule="readme-command-mismatch",
                                severity="medium",
                                problem=(
                                    f"README command 'python {py_file}' references a file that "
                                    "does not exist in repository"
                                ),
                                why_it_matters=(
                                    f"Running 'python {py_file}' will fail with a "
                                    "FileNotFoundError."
                                ),
                                fix=f"Create '{py_file}' or update the command in README.",
                                evidence=raw_line.strip(),
                                confidence=1.0,
                                verified=True,
                                verified_note="checked against the repo files",
                            )
                        )

            # 5. node FILE
            node_match = re.search(r"\bnode\s+([a-zA-Z0-9_\-\./\\]+)", candidate)
            if node_match:
                node_file = node_match.group(1).strip("`'\";,").strip()
                if not node_file.startswith("-"):
                    exists = _file_exists(node_file) or _file_exists(f"{node_file}.js")
                    if not exists:
                        prob_key = f"node:{node_file}"
                        if prob_key not in seen_problems:
                            seen_problems.add(prob_key)
                            idx += 1
                            findings.append(
                                Finding(
                                    id=f"repo-readme-command-mismatch-{idx}",
                                    source="measured",
                                    target="repo",
                                    rule="readme-command-mismatch",
                                    severity="medium",
                                    problem=(
                                        f"README command 'node {node_file}' references a file that "
                                        "does not exist in repository"
                                    ),
                                    why_it_matters=(
                                        f"Running 'node {node_file}' will fail because the module "
                                        "does not exist."
                                    ),
                                    fix=f"Create '{node_file}' or update the command in README.",
                                    evidence=raw_line.strip(),
                                    confidence=1.0,
                                    verified=True,
                                    verified_note="checked against the repo files",
                                )
                            )

    return findings


def run_all(snapshot: RepoSnapshot) -> list[Finding]:
    """Execute all deterministic repository checks and return list of Findings."""
    findings: list[Finding] = []

    # 1. missing-license
    license_finding = check_license(snapshot)
    if license_finding:
        findings.append(license_finding)

    # 2. missing-contributing
    contributing_finding = check_contributing(snapshot)
    if contributing_finding:
        findings.append(contributing_finding)

    # 3. missing-code-of-conduct
    conduct_finding = check_code_of_conduct(snapshot)
    if conduct_finding:
        findings.append(conduct_finding)

    # 4. missing-ci (.github/workflows)
    ci_finding = check_ci(snapshot)
    if ci_finding:
        findings.append(ci_finding)

    # 5. missing-issue-templates
    templates_finding = check_issue_templates(snapshot)
    if templates_finding:
        findings.append(templates_finding)

    # 6. readme-too-short (<300 chars)
    short_readme_finding = check_readme_too_short(snapshot)
    if short_readme_finding:
        findings.append(short_readme_finding)

    # 7. readme-missing-install
    install_finding = check_readme_missing_install(snapshot)
    if install_finding:
        findings.append(install_finding)

    # 8. readme-missing-usage
    usage_finding = check_readme_missing_usage(snapshot)
    if usage_finding:
        findings.append(usage_finding)

    # 9. no-tests
    tests_finding = check_tests(snapshot)
    if tests_finding:
        findings.append(tests_finding)

    # 10. readme-command-mismatch
    findings.extend(check_readme_command_mismatch(snapshot))

    return findings
