"""Command line interface for SightLine."""

import argparse
import os
import sys
from pathlib import Path

from sightline.config import settings
from sightline.pipeline import run
from sightline.repo.github import format_count


def build_parser() -> argparse.ArgumentParser:
    """Construct the command line parser for SightLine."""
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--out",
        "-o",
        default=None,
        help="Destination directory for output artifacts (default: out)",
    )
    common_parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode using canned responses without network",
    )

    parser = argparse.ArgumentParser(
        prog="sightline",
        description="SightLine: AI-assisted accessibility and repository inspector",
        parents=[common_parser],
    )
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Analysis mode")

    site_parser = subparsers.add_parser(
        "site",
        parents=[common_parser],
        help="Analyze a website",
    )
    site_parser.add_argument("url", help="URL of the website to analyze")

    repo_parser = subparsers.add_parser(
        "repo",
        parents=[common_parser],
        help="Analyze a GitHub repository",
    )
    repo_parser.add_argument("url", help="GitHub repository URL or owner/repo")
    repo_parser.add_argument(
        "--with-site",
        action="store_true",
        help="Also analyze the repository homepage website if available",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the sightline CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mock:
        os.environ["MOCK"] = "1"

    out_dir = Path(args.out) if args.out else settings.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    def on_step(step_name: str) -> None:
        print(f"-> {step_name}...")

    try:
        result = run(
            mode=args.mode,
            url=args.url,
            out_dir=out_dir,
            on_step=on_step,
            with_site=getattr(args, "with_site", False),
        )
    except Exception as exc:
        print(f"\nError executing SightLine pipeline: {exc}", file=sys.stderr)
        return 1

    # Write issues/*.md files
    issues_dir = out_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    for finding in result.findings:
        content = result.issues.get(finding.id, "")
        issue_file = issues_dir / f"{finding.id}_{finding.rule}.md"
        issue_file.write_text(content, encoding="utf-8")

    # Print human-readable summary
    print("\n" + "=" * 60)
    if result.mode == "repo" and result.repo_info:
        info = result.repo_info
        stars_str = format_count(info.get("stars", 0))
        forks_str = format_count(info.get("forks", 0))
        lang_str = info.get("language") or "Unknown"
        print(
            f"SightLine Analysis: {result.title} "
            f"({stars_str} stars, {forks_str} forks, {lang_str}) [REPO]"
        )
    else:
        print(f"SightLine Analysis: {result.title} [{result.mode.upper()}]")
    print("=" * 60)
    print(f"Target URL:    {result.url}")
    print(f"Total Issues:  {result.stats['total_findings']}")
    sev = result.stats["by_severity"]
    print(f"By Severity:   High: {sev['high']} | Medium: {sev['medium']} | Low: {sev['low']}")
    src = result.stats["by_source"]
    print(f"By Source:     Measured: {src['measured']} | AI: {src['ai']}")
    print(f"Verified:      {result.stats['verified']}")
    if result.annotated_image:
        print(f"Annotated UI:  {result.annotated_image}")
    print(f"Saved Output:  {out_dir / 'result.json'}")
    print(f"Issues Saved:  {issues_dir} ({len(result.findings)} markdown files)")
    if result.notes:
        print(f"Notes:         {'; '.join(result.notes)}")

    if "timings" in result.stats and result.stats["timings"]:
        print("\nStage Timings:")
        for stage, sec in result.stats["timings"].items():
            if stage != "total":
                print(f"  - {stage:<22} : {sec:>6.2f}s")
        if "total" in result.stats["timings"]:
            print(f"  - {'Total Pipeline':<22} : {result.stats['timings']['total']:>6.2f}s")

    print("-" * 60)

    for idx, f in enumerate(result.findings, start=1):
        ver_tag = "[VERIFIED]" if f.verified else ""
        print(f"{idx}. [{f.severity.upper()}] {f.rule} {ver_tag}")
        print(f"   Problem: {f.problem}")
        if f.evidence:
            print(f"   Evidence: {f.evidence}")
        if f.fix:
            print(f"   Fix: {f.fix}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
