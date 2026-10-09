# Adding an Analyzer to SightLine

SightLine supports both measured deterministic analyzers and AI-assisted reviewers.

## Adding a Measured Rule
1. For websites, define the check in `sightline/site/checks.py`.
2. For repositories, define the check in `sightline/repo/checks.py`.
3. Construct a `Finding` with `source="measured"`, a descriptive rule name, severity, and clear fix suggestion.

## Adding AI Prompt Guidance
1. Edit `sightline/prompts/site_review.txt` or `sightline/prompts/repo_review.txt`.
2. Ensure new rules require verifiable evidence (verbatim quotes for repos, element numbers for sites).
