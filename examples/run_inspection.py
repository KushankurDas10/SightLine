"""Example script demonstrating programmatic usage of SightLine's Python API."""

from pathlib import Path

from sightline.pipeline import run


def inspect_repository_example() -> None:
    """Run an offline repository inspection and display summary findings."""
    print("--- SightLine Programmatic Inspection Example ---")

    # Run inspection in offline/mock mode if no tokens are configured
    target_repo = "https://github.com/octocat/Hello-World"
    out_dir = Path("out/example_run")

    print(f"Inspecting repository: {target_repo}")
    result = run(mode="repo", url=target_repo, out_dir=out_dir)

    print(f"\nInspection Title: {result.title}")
    print(f"Total findings: {result.stats.get('total_findings', len(result.findings))}")
    print(f"Measured findings: {result.stats.get('by_source', {}).get('measured', 0)}")
    print(f"AI findings: {result.stats.get('by_source', {}).get('ai', 0)}")

    print("\nTop Findings:")
    for idx, finding in enumerate(result.findings[:5], start=1):
        status = "[VERIFIED]" if finding.verified else "[PROPOSED]"
        print(f"  {idx}. {status} [{finding.severity.upper()}] {finding.rule}: {finding.problem}")
        if finding.fix:
            print(f"     Suggested Fix: {finding.fix}")

    if result.repo_info:
        print(f"\nRepository Stars: {result.repo_info.get('stars', 0)}")
        print(f"Primary Language: {result.repo_info.get('language')}")


if __name__ == "__main__":
    inspect_repository_example()
