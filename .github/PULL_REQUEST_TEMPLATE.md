## Description
Briefly describe the change and its motivation or context. If it fixes an issue, reference it (e.g. `Fixes #123`).

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature / analyzer (non-breaking change which adds functionality)
- [ ] Documentation update
- [ ] Refactor or performance enhancement

## Checklist
- [ ] Code follows project style guidelines and passes linter: `ruff check .`
- [ ] Fast unit tests pass: `pytest -m "not live and not browser"`
- [ ] Browser tests pass (if modifying site capture/verify/frontend): `pytest -m browser`
- [ ] No external API keys or secrets committed (`.env` remains untracked)
- [ ] Evidence verification preserved: all AI findings require verifiable evidence
- [ ] Dependency constraints respected: only allowed packages (`fastapi`, `uvicorn`, `playwright`, `pillow`, `google-genai`, `httpx`, `python-dotenv`, `pytest`, `ruff`)
- [ ] Added or updated tests covering the changes
