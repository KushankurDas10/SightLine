"""Top-level analysis pipelines for website and repo targets."""

import json
import logging
import time
from dataclasses import asdict
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
from sightline.site.verify import verify_fixes

logger = logging.getLogger(__name__)


def _compute_stats(
    findings: list[Finding],
    timings: dict[str, float] | None = None,
) -> dict[str, Any]:
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
        "timings": timings or {},
    }


def run(
    mode: str,
    url: str,
    out_dir: str | Path | None = None,
    on_step: Callable[[str], None] | None = None,
    with_site: bool = False,
    on_partial: Callable[[dict[str, Any]], None] | None = None,
) -> AnalysisResult:
    """Run full analysis pipeline for website or GitHub repository target.

    Args:
        mode: "site" or "repo"
        url: target URL to analyze
        out_dir: destination directory for artifacts (default: settings.out_dir)
        on_step: optional progress callback receiving step name strings
        with_site: if True and in repo mode with a homepage, runs site analysis too
        on_partial: optional callback receiving partial measured findings early
    """
    out_path = Path(out_dir) if out_dir else settings.out_dir
    out_path.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    timings: dict[str, float] = {}
    current_step: str | None = None
    run_start: float = time.perf_counter()
    step_start: float = run_start

    def _step(name: str) -> None:
        nonlocal current_step, step_start
        now = time.perf_counter()
        if current_step is not None:
            timings[current_step] = round(now - step_start, 2)
        current_step = name
        step_start = now
        if on_step is not None:
            try:
                on_step(name)
            except Exception as exc:
                logger.warning("on_step callback error on %r: %s", name, exc)

    def _end_timing() -> None:
        nonlocal current_step, step_start
        now = time.perf_counter()
        if current_step is not None:
            timings[current_step] = round(now - step_start, 2)
            current_step = None
        timings["total"] = round(sum(v for k, v in timings.items() if k != "total"), 2)

    if mode == "site":
        _step("Opening website")
        snapshot = site_capture.capture(
            url,
            out_dir=out_path,
            on_screenshot=lambda: _step("Taking screenshot"),
        )

        _step("Running checks")
        measured = site_checks.run_all(snapshot)

        if on_partial is not None:
            partial_data = {
                "mode": "site",
                "url": url,
                "title": snapshot.title or url,
                "partial": True,
                "findings": [asdict(f) for f in measured],
                "stats": _compute_stats(measured, timings=dict(timings)),
                "notes": list(notes),
            }
            try:
                on_partial(partial_data)
            except Exception as exc:
                logger.warning("on_partial callback error: %s", exc)

        _step("Marking elements")
        marked_path = out_path / "marked.png"
        try:
            marks.mark_elements(snapshot, marked_path)
        except Exception as exc:
            notes.append(f"Failed to mark elements: {exc}")
            marked_path = Path(snapshot.screenshot_path)

        elapsed = time.perf_counter() - run_start
        if elapsed >= 90.0:
            notes.append("Skipped Gemma review: run reached 90s time limit")
            findings = list(measured)
        else:
            gemma_timeout = min(45.0, max(5.0, 90.0 - elapsed))
            _step("Asking Gemma")
            try:
                findings = review_site(
                    snapshot, marked_path, measured, timeout_seconds=gemma_timeout
                )
            except Exception as exc:
                notes.append(f"Gemma site review failed: {exc}")
                findings = list(measured)

        _step("Verifying fixes")
        try:
            findings = verify_fixes(url, snapshot, findings)
        except Exception as exc:
            notes.append(f"Fix verification failed: {exc}")

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

        _end_timing()

        title = snapshot.title or url
        stats = _compute_stats(findings, timings=timings)

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

        if on_partial is not None:
            partial_data = {
                "mode": "repo",
                "url": url,
                "title": f"{repo_snapshot.owner}/{repo_snapshot.name}",
                "partial": True,
                "findings": [asdict(f) for f in measured],
                "stats": _compute_stats(measured, timings=dict(timings)),
                "notes": list(notes),
            }
            try:
                on_partial(partial_data)
            except Exception as exc:
                logger.warning("on_partial callback error: %s", exc)

        elapsed = time.perf_counter() - run_start
        if elapsed >= 90.0:
            notes.append("Skipped Gemma review: run reached 90s time limit")
            findings = list(measured)
        else:
            gemma_timeout = min(45.0, max(5.0, 90.0 - elapsed))
            _step("Asking Gemma")
            try:
                findings = review_repo(repo_snapshot, measured, timeout_seconds=gemma_timeout)
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

        _end_timing()

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
        stats = _compute_stats(findings, timings=timings)

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
