# AI Agent Guidelines for SightLine

This repository is maintained with strict AI agent architecture principles:

1. **Only Gemma**: Use Gemma models exclusively via `google-genai` and `GEMMA_MODEL` (default: `gemma-4-26b-a4b-it`).
2. **Never Execute Model Code**: Model outputs are structured text or JSON only. All outputs are strictly validated before use.
3. **Evidence Requirement**:
   - For website findings: `element_number` must match an actual element present in the snapshot.
   - For repository findings: `evidence` must match an exact verbatim quote from the inspected files.
   - Drop unverified findings.
4. **Mock Mode**: Setting `MOCK=1` causes Gemma calls to return canned fixtures without network access.
5. **No Outer Folders**: The repository root is the current folder (`SightLine`).
