# SightLine Architecture

SightLine operates in two primary modes:

1. **Website Mode**:
   - Captures page DOM and screenshots via Playwright.
   - Evaluates deterministic measured rules (contrast, missing alt/label, touch targets, lang, title).
   - Generates numbered badges on screenshots for element identification.
   - Prompts Gemma with the numbered screenshot for visual UX/design analysis.
   - Re-checks suggested fixes in the browser.

2. **Repository Mode**:
   - Inspects GitHub repositories via the GitHub REST API.
   - Performs deterministic structure checks (license, CI workflows, test suite, contributing guidelines, README commands).
   - Prompts Gemma with repository metadata, file tree, README, and key files.
   - Verifies all AI findings against verbatim quotes in repository files.

## Evidence Verification Rule
Findings originating from Gemma (`source: "ai"`) must provide verifiable evidence:
- **Website mode**: The referenced `element_number` must match a DOM element present in the snapshot.
- **Repository mode**: The `evidence` field must match an exact substring in the provided repository files.
Any AI finding lacking verifiable evidence is dropped.
