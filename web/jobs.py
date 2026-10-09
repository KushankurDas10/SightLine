"""Background job runner and progress tracker for web requests."""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sightline.pipeline import run

logger = logging.getLogger(__name__)

# Single background worker thread so sync Playwright runs outside asyncio
_executor = ThreadPoolExecutor(max_workers=1)
_lock = threading.Lock()

# In-memory store: job_id -> job dict
JOBS: dict[str, dict[str, Any]] = {}
MAX_CONCURRENT_JOBS = 5


def count_active_jobs() -> int:
    """Return the number of currently queued or running jobs."""
    with _lock:
        return sum(1 for j in JOBS.values() if j.get("status") == "running")


def _execute_job(job_id: str, mode: str, url: str, with_site: bool) -> None:
    """Execute pipeline in worker thread and update job status."""
    from sightline.config import settings

    job_out_dir = settings.out_dir / job_id
    job_out_dir.mkdir(parents=True, exist_ok=True)

    def on_step(step_name: str) -> None:
        with _lock:
            if job_id in JOBS:
                JOBS[job_id]["step"] = step_name

    def on_partial(partial_data: dict[str, Any]) -> None:
        with _lock:
            if job_id in JOBS:
                JOBS[job_id]["partial"] = partial_data

    try:
        try:
            result = run(
                mode=mode,
                url=url,
                out_dir=job_out_dir,
                with_site=with_site,
                on_step=on_step,
                on_partial=on_partial,
            )
        except TypeError:
            # Fallback for monkeypatched run signatures without out_dir/on_partial
            result = run(mode=mode, url=url, with_site=with_site, on_step=on_step)

        res_dict = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        if isinstance(res_dict, dict):
            if res_dict.get("annotated_image"):
                res_dict["annotated_image"] = f"/files/{job_id}/annotated.png"
            for f_dict in res_dict.get("findings", []):
                if isinstance(f_dict, dict) and f_dict.get("compare_image"):
                    f_dict["compare_image"] = f"/files/{job_id}/compare/{f_dict['id']}.png"
        if hasattr(result, "annotated_image") and result.annotated_image:
            result.annotated_image = f"/files/{job_id}/annotated.png"
        if hasattr(result, "findings") and result.findings:
            for f in result.findings:
                if getattr(f, "compare_image", None):
                    f.compare_image = f"/files/{job_id}/compare/{f.id}.png"

        with _lock:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["step"] = "Completed"
                JOBS[job_id]["result"] = res_dict
    except Exception as exc:
        logger.exception("Pipeline job %s failed: %s", job_id, exc)
        with _lock:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["step"] = "Failed"
                JOBS[job_id]["error"] = str(exc)


def create_job(mode: str, url: str, with_site: bool = False) -> str:
    """Register a new analysis job and submit to background worker thread."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        JOBS[job_id] = {
            "id": job_id,
            "status": "running",
            "step": "Queued",
            "partial": None,
            "result": None,
            "error": None,
        }

    _executor.submit(_execute_job, job_id, mode, url, with_site)
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    """Retrieve job details for API response, or None if not found."""
    with _lock:
        job = JOBS.get(job_id)
        if not job:
            return None

        data: dict[str, Any] = {
            "status": job["status"],
            "step": job["step"],
        }
        if job.get("partial") is not None and job["status"] == "running":
            data["partial"] = job["partial"]
        if job["result"] is not None:
            data["result"] = job["result"]
        if job["error"] is not None:
            data["error"] = job["error"]
        return data


def clear_jobs() -> None:
    """Clear in-memory jobs store (primarily for test isolation)."""
    with _lock:
        JOBS.clear()
