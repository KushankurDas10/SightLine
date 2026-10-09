# SightLine Examples & Recipes

This directory provides practical examples of using SightLine via CLI commands and programmatic Python scripts.

---

## 1. CLI Usage Recipes

### Inspect a Live Website
Capture the DOM and full-page screenshot, run deterministic accessibility checks, prompt Gemma 4 for visual review, and verify fixes:
```bash
sightline site https://example.com
```

Save output artifacts (annotated screenshots, side-by-side comparison images, and `result.json`) into a specific directory:
```bash
sightline site https://example.com --out out/my_site_audit
```

### Inspect a GitHub Repository
Fetch repository metadata, tree structure, licenses, workflows, and README; run repository health checks, and prompt Gemma 4:
```bash
sightline repo https://github.com/octocat/Hello-World
```

Combine repository inspection with a live audit of the project's homepage URL:
```bash
sightline repo https://github.com/octocat/Hello-World --with-site
```

### Launch the Interactive Web UI
Start the local FastAPI web server at `http://localhost:8000`:
```bash
sightline --web
```
Or with custom host and port:
```bash
sightline --web --host 127.0.0.1 --port 8080
```

---

## 2. Programmatic Python API

You can import SightLine into Python scripts or automation workflows:

```python
from pathlib import Path
from sightline.pipeline import run

# Run website inspection
result = run(mode="site", url="https://example.com", out_dir=Path("out/site_run"))

# Print findings
for finding in result.findings:
    print(f"[{finding.severity.upper()}] {finding.rule}: {finding.problem}")
    if finding.verified:
        print(f"  -> Verified fix: {finding.fix_snippet}")
```

Run the included example script:
```bash
python examples/run_inspection.py
```

---

## 3. Offline / Demo Mode (No API Key Required)

SightLine can run completely offline without an active network connection or Gemini API key:
- Set `MOCK=1` in your environment or `.env` file to use deterministic canned fixtures.
- Open `http://localhost:8000?demo=site` or `http://localhost:8000?demo=repo` in your browser to inspect pre-rendered results with verified before/after visual cards and alternative fixes.
