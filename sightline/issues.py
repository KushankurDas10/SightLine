"""GitHub issue generation from validated findings."""

from typing import Any

from sightline.models import Finding


def to_issue(finding: Finding, context: Any = None) -> str:
    """Format a finding into a structured GitHub issue in Markdown.

    Includes title line, What's wrong, Evidence, Why it matters,
    Suggested fix with code snippet, How it was found attribution, and a checklist.
    Performs no model calls.
    """
    severity_label = finding.severity.upper()
    title = f"# [{severity_label}] {finding.rule}: {finding.problem}"

    # Evidence formatting
    evidence_lines = []
    if finding.target == "site" and finding.element_number is not None:
        evidence_lines.append(f"- **Element number**: #{finding.element_number}")
    elif finding.target == "repo" and finding.file_path:
        evidence_lines.append(f"- **File path**: `{finding.file_path}`")

    if finding.evidence:
        evidence_lines.append(f"- **Observable evidence**: `{finding.evidence}`")
    else:
        evidence_lines.append("- Observed directly during automated inspection.")

    evidence_block = "\n".join(evidence_lines)

    # Suggested fix formatting
    fix_body = finding.fix or "Apply recommended adjustments to resolve the issue."
    if finding.fix_value:
        fix_body += f"\n\n**Recommended value**: `{finding.fix_value}`"

    if finding.fix_snippet:
        snippet_lang = "css" if finding.target == "site" else ""
        fix_body += f"\n\n```{snippet_lang}\n{finding.fix_snippet}\n```"

    # Attribution formatting
    if finding.source == "measured":
        how_found = "Measured deterministically by SightLine automated checks."
    else:
        how_found = "AI analysis via Gemma 4 and SightLine."

    if finding.verified:
        note = finding.verified_note or "passed evidence validation"
        how_found += f"\n**Status**: Verified ({note})."

    # Context optional note
    context_note = ""
    if context and isinstance(context, str):
        context_note = f"\n\n**Context**: {context}"

    issue_markdown = f"""{title}

## What's wrong

{finding.problem}

## Evidence

{evidence_block}

## Why it matters

{finding.why_it_matters or "Affects usability, user experience, or developer workflow."}

## Suggested fix

{fix_body}

## How it was found

{how_found}{context_note}

## Checklist

- [ ] Review the proposed fix
- [ ] Apply code or design changes
- [ ] Verify fix visually or run test suite
- [ ] Close issue
"""
    return issue_markdown.strip() + "\n"
