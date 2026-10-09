"""FastAPI web server for SightLine."""

import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sightline.config import settings
from web import jobs

app = FastAPI(
    title="SightLine API",
    description="Fast, measured, and AI-assisted accessibility and repository inspector",
    version="0.1.0",
)

# Directories
STATIC_DIR = Path(__file__).resolve().parent / "static"
OUT_DIR = settings.out_dir
OUT_DIR.mkdir(parents=True, exist_ok=True)


class AnalyzeRequest(BaseModel):
    """Payload for starting an analysis job."""

    mode: str
    url: str
    with_site: bool = False


@app.get("/api/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/analyze")
def start_analysis(payload: AnalyzeRequest) -> dict[str, str]:
    """Validate input and schedule analysis job."""
    mode = payload.mode.strip().lower()
    raw_url = payload.url.strip()

    # 1. URL length check
    if len(raw_url) > 300:
        raise HTTPException(
            status_code=400,
            detail="URL length exceeds maximum of 300 characters.",
        )

    if not raw_url:
        raise HTTPException(
            status_code=400,
            detail="URL cannot be empty.",
        )

    # 2. Mode validation
    if mode not in ("site", "repo"):
        raise HTTPException(
            status_code=400,
            detail="Invalid mode. Must be either 'site' or 'repo'.",
        )

    # 3. URL scheme and domain validation
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail=f"{mode.capitalize()} mode only accepts http:// or https:// URLs.",
        )

    if mode == "repo":
        netloc = parsed.netloc.lower().split(":")[0]
        if netloc not in ("github.com", "www.github.com"):
            raise HTTPException(
                status_code=400,
                detail="Repository mode only accepts github.com links.",
            )

    # 4. Concurrency limit (at most 5 queued jobs)
    if jobs.count_active_jobs() >= 5:
        raise HTTPException(
            status_code=400,
            detail="Job queue is full. At most 5 concurrent jobs are allowed.",
        )

    job_id = jobs.create_job(mode=mode, url=raw_url, with_site=payload.with_site)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Return status and result/error of an analysis job."""
    job_data = jobs.get_job(job_id)
    if job_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found.",
        )
    return job_data


@app.get("/files/{file_path:path}")
def serve_file(file_path: str) -> FileResponse:
    """Serve generated analysis artifacts securely, preventing directory traversal."""
    parts = file_path.replace("\\", "/").split("/")
    if ".." in parts:
        raise HTTPException(
            status_code=403,
            detail="Access denied: path traversal detected.",
        )
    base_dir = OUT_DIR.resolve()
    target_path = (base_dir / file_path).resolve()
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Access denied: path traversal detected.",
        )
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(target_path)


@app.get("/demo/{file_path:path}")
def serve_demo(file_path: str) -> FileResponse:
    """Serve demo static assets."""
    base_dir = (STATIC_DIR / "demo").resolve()
    target_path = (base_dir / file_path).resolve()
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Access denied: path traversal detected.",
        )
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="Demo file not found.")
    return FileResponse(target_path)


# Serve assets from web/static at /static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    """Serve the main web frontend interface."""
    return FileResponse(STATIC_DIR / "index.html")
