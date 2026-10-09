"""Deduplication and merging of measured and AI findings."""

from typing import Any

from sightline.models import Finding

SEVERITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


def _finding_dedup_key(finding: Finding) -> tuple[Any, ...]:
    """Generate a deduplication key for a finding."""
    if finding.target == "site" and finding.element_number is not None:
        return ("site", finding.rule, finding.element_number)
    if finding.target == "repo" and finding.file_path:
        norm_problem = " ".join((finding.problem or "").lower().split())
        return ("repo", finding.rule, finding.file_path, norm_problem)
    return ("id", finding.id)


def merge_findings(
    measured_enriched: list[Finding],
    ai_new: list[Finding],
) -> list[Finding]:
    """Merge measured (enriched) findings with new AI findings.

    Removes duplicates and sorts by severity (high first), verified status,
    and confidence.
    """
    seen_keys: set[tuple[Any, ...]] = set()
    combined: list[Finding] = []

    # Process measured findings first so they take precedence on collision
    for finding in measured_enriched:
        key = _finding_dedup_key(finding)
        if key not in seen_keys:
            seen_keys.add(key)
            combined.append(finding)

    for finding in ai_new:
        key = _finding_dedup_key(finding)
        if key not in seen_keys:
            seen_keys.add(key)
            combined.append(finding)

    def sort_key(f: Finding) -> tuple[int, int, float]:
        sev_rank = SEVERITY_ORDER.get(f.severity.lower(), 1)
        ver_rank = 0 if f.verified else 1
        conf_rank = -float(f.confidence)
        return (sev_rank, ver_rank, conf_rank)

    return sorted(combined, key=sort_key)
