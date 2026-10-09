# AI Agent Guidelines for SightLine

This repository is maintained with strict AI agent architecture principles and HARD RULES:

1. **Only Gemma**: Use Gemma models exclusively via `google-genai` and `GEMMA_MODEL` (default: `gemma-4-26b-a4b-it`). Never use `gemini-*`, OpenAI, or Anthropic models.
2. **Never Put Keys in Code**: Read `GEMINI_API_KEY` and `GITHUB_TOKEN` from the environment (`.env` via `python-dotenv`). `.env` is gitignored.
3. **Never Execute Model Code**: Model outputs are structured text or JSON only. All outputs are strictly validated before use.
4. **Evidence Requirement**: Every Finding has source `"measured"` (our code is sure) or `"ai"` (Gemma). Every AI finding needs evidence. Drop AI findings whose evidence cannot be verified:
   - For website findings: `element_number` must match an actual element present in the snapshot.
   - For repository findings: `evidence` must match an exact verbatim quote from the inspected files.
5. **Mock Mode for Tests**: Tests must not need network, a browser, or an API key unless marked `@pytest.mark.browser` or `@pytest.mark.live`. `MOCK=1` causes `gemma.ask_json` to return canned fixtures without network access.
6. **No Outer Folders & Phase Scope**: The repository root is the current folder (`SightLine`). Only edit files that belong to the current phase. Do not change `models.py`, `config.py`, or `pyproject.toml` without informing the user.
7. **Allowed Dependencies**: `fastapi`, `uvicorn`, `playwright`, `pillow`, `google-genai`, `httpx`, `python-dotenv`, `pytest`, `ruff`. Nothing else.
8. **Code Quality**: Small, readable code with type hints and short docstrings.
9. **Phase Completion**: After each phase: run the listed tests and ruff, show the output, summarize the changes, then STOP and wait until the user says "next".
