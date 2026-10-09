"""Top-level analysis pipelines for website and repo targets."""

import json
import logging
from pathlib import Path
from typing import Any, Callable

from sightline.config import settings
from sightline.gemma_review import review_repo, review_site
from sightline.issues import to_issue
from sightline.models import AnalysisResult, Finding
from sightline.repo import checks as repo_checks
from sightline.repo import github
from sightline.site import capture as site_capture
from sightline.site import checks as site_checks
from sightline.site import marks

logger = logging.getLogger(__name__)


def _compute_stats(findings: list[Finding]) -> dict[str, Any]:
    """Compute aggregate statistics for findings."""
    return {
        "total_findings": len(findings),
        "by_source": {
            "measured": sum(1 for f in findings if f.source == "measured"),
            "ai": sum(1 for f in findings if f.source == "ai"),
        },
        "by_severity": {
            "high": sum(1 for f in findings if f.severity == "high"),
            "medium": sum(1 for f in findings if f.severity == "medium"),
            "low": sum(1 for f in findings if f.severity == "low"),
        },
        "verified": sum(1 for f in findings if f.verified),
    }


def run(
    mode: str,
    url: str,
    out_dir: str | Path | None = None,
    on_step: Callable[[str], None] | None = None,
    with_site: bool = False,
) -> AnalysisResult:
    """Run full analysis pipeline for website or GitHub repository target.

    Args:
        mode: "site" or "repo"
        url: target URL to analyze
        out_dir: destination directory for artifacts (default: settings.out_dir)
        on_step: optional progress callback receiving step name strings
        with_site: if True and in repo mode with a homepage, runs site analysis too
    """
    out_path = Path(out_dir) if out_dir else settings.out_dir
    out_path.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []

    def _step(name: str) -> None:
        if on_step is not None:
            try:
                on_step(name)
            except Exception as exc:
                logger.warning("on_step callback error on %r: %s", name, exc)

    if mode == "site":
        _step("Opening website")
        _step("Taking screenshot")
        snapshot = site_capture.capture(url, out_dir=out_path)

        _step("Running checks")
        measured = site_checks.run_all(snapshot)

        _step("Marking elements")
        marked_path = out_path / "marked.png"
        try:
            marks.mark_elements(snapshot, marked_path)
        except Exception as exc:
            notes.append(f"Failed to mark elements: {exc}")
            marked_path = Path(snapshot.screenshot_path)

        _step("Asking Gemma")
        try:
            findings = review_site(snapshot, marked_path, measured)
        except Exception as exc:
            notes.append(f"Gemma site review failed: {exc}")
            findings = list(measured)

        _step("Drawing results")
        annotated_path = out_path / "annotated.png"
        annotated_image: str | None = None
        try:
            marks.annotate(snapshot, findings, annotated_path)
            annotated_image = str(annotated_path)
        except Exception as exc:
            notes.append(f"Failed to draw annotated results: {exc}")

        _step("Writing issues")
        issues: dict[str, str] = {}
        for f in findings:
            try:
                issues[f.id] = to_issue(f, context=f"Page URL: {snapshot.url}")
            except Exception as exc:
                notes.append(f"Failed to format issue for {f.id}: {exc}")

        title = snapshot.title or url
        stats = _compute_stats(findings)

        result = AnalysisResult(
            mode="site",
            url=url,
            title=title,
            findings=findings,
            annotated_image=annotated_image,
            issues=issues,
            notes=notes,
            stats=stats,
        )

        result_file = out_path / "result.json"
        result_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    elif mode == "repo":
        _step("Fetching repository")
        repo_snapshot = github.fetch(url)

        _step("Running checks")
        measured = repo_checks.run_all(repo_snapshot)

        _step("Asking Gemma")
        try:
            findings = review_repo(repo_snapshot, measured)
        except Exception as exc:
            notes.append(f"Gemma repo review failed: {exc}")
            findings = list(measured)

        _step("Writing issues")
        issues: dict[str, str] = {}
        for f in findings:
            try:
                issues[f.id] = to_issue(f, context=f"Repository URL: {repo_snapshot.url}")
            except Exception as exc:
                notes.append(f"Failed to format issue for {f.id}: {exc}")

        annotated_image = None

        if with_site and repo_snapshot.homepage:
            homepage_url = repo_snapshot.homepage.strip()
            if not homepage_url.startswith(("http://", "https://")):
                homepage_url = f"https://{homepage_url}"
            try:
                site_out = out_path / "site"
                site_res = run(
                    mode="site",
                    url=homepage_url,
                    out_dir=site_out,
                    on_step=on_step,
                    with_site=False,
                )
                findings.extend(site_res.findings)
                issues.update(site_res.issues)
                notes.extend(site_res.notes)
                notes.append(f"Included site analysis for homepage: {homepage_url}")
                if site_res.annotated_image:
                    annotated_image = site_res.annotated_image
            except Exception as exc:
                notes.append(f"Homepage site analysis failed: {exc}")

        title = f"{repo_snapshot.owner}/{repo_snapshot.name}"
        stats = _compute_stats(findings)

        result = AnalysisResult(
            mode="repo",
            url=url,
            title=title,
            findings=findings,
            annotated_image=annotated_image,
            issues=issues,
            notes=notes,
            stats=stats,
        )

        result_file = out_path / "result.json"
        result_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    else:
        raise ValueError(f"Unknown mode '{mode}'. Expected 'site' or 'repo'.")
