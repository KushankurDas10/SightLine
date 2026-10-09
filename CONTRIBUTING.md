# Contributing to SightLine

Thank you for contributing to SightLine!

## Development Guidelines

1. **AI Model**: Only use Gemma models through the Gemini API (`google-genai`). Never hardcode API keys.
2. **Dependencies**: Respect the minimal dependency list:
   `fastapi`, `uvicorn`, `playwright`, `pillow`, `google-genai`, `httpx`, `python-dotenv`, `pytest`, `ruff`.
3. **Tests**:
   - Fast unit tests must not require live API keys or browsers:
     `pytest -m "not live and not browser"`
   - Browser tests: `pytest -m browser`
   - Live tests: `pytest -m live`
4. **Code Quality**:
   - Check formatting and linting: `ruff check .`
   - Use type hints and keep functions focused and readable.
