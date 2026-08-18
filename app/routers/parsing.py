"""
Parsing endpoints — job-based, matching the same background-job pattern
already proven on Kokoro's audio export (start -> poll status -> fetch
result). A single blocking POST was the wrong shape once real rate-limit
retry logic was added to scene_parser.py: large scripts hitting Groq's
free-tier limits can now legitimately take several minutes to parse
(retrying scenes with real backoff instead of dropping them), which
exceeded the frontend's own request timeout — the backend was actually
succeeding, just after the frontend had already given up and shown a
"service unavailable" fallback message.
"""
import asyncio
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.parsing_schemas import ParsedScript
from app.services.parsing_pipeline import parse_script

router = APIRouter(prefix="/api/parse", tags=["parsing"])

_parse_jobs: dict[str, dict] = {}


class ParseRequest(BaseModel):
    raw_text: str
    title: str | None = None
    # Opt-in — when False (default), parsing is identical to before this
    # feature existed: same prompt, same cost, same latency. Only set to
    # True when the frontend's sound-effects toggle is on.
    detect_sound_effects: bool = False


async def _run_parse_job(job_id: str, req: ParseRequest) -> None:
    job = _parse_jobs[job_id]

    def on_progress(done: int, total: int):
        job["done"] = done
        job["total"] = total

    try:
        result = await parse_script(
            req.raw_text,
            title=req.title,
            detect_sound_effects=req.detect_sound_effects,
            on_progress=on_progress,
        )
    except Exception as e:
        job["status"] = "error"
        job["error"] = f"Parsing failed: {e}"
        return

    if not result.scenes:
        job["status"] = "error"
        job["error"] = "No scenes could be parsed."
        return

    job["status"] = "done"
    job["result"] = result


@router.post("/start")
async def parse_start(req: ParseRequest):
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty.")

    job_id = uuid.uuid4().hex[:12]
    _parse_jobs[job_id] = {
        "status": "running",
        "done": 0,
        "total": 0,  # updated once scene-splitting completes, early in the job
        "started": time.time(),
        "result": None,
        "error": None,
    }

    loop = asyncio.get_event_loop()
    loop.create_task(_run_parse_job(job_id, req))

    return {"job_id": job_id}


@router.get("/status/{job_id}")
async def parse_status(job_id: str):
    job = _parse_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {
        "status": job["status"],
        "done": job["done"],
        "total": job["total"],
        "elapsed": round(time.time() - job["started"], 1),
        "error": job["error"],
    }


@router.get("/result/{job_id}", response_model=ParsedScript)
async def parse_result(job_id: str):
    job = _parse_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    if job["status"] == "error":
        raise HTTPException(status_code=502, detail=job["error"])
    if job["status"] != "done":
        raise HTTPException(status_code=425, detail=f"Job not ready yet (status: {job['status']})")

    result = job["result"]
    # Clean up after a successful fetch — this is a single-tenant backend
    # with no need to keep finished jobs in memory indefinitely.
    del _parse_jobs[job_id]
    return result


# Kept for any caller that hasn't migrated to the job-based flow yet —
# same blocking behavior as before, now genuinely just a thin wrapper
# around the job functions rather than a separate code path to maintain.
@router.post("/structure", response_model=ParsedScript)
async def structure_script(req: ParseRequest):
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty.")

    try:
        result = await parse_script(
            req.raw_text, title=req.title, detect_sound_effects=req.detect_sound_effects,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Parsing failed: {e}")

    if not result.scenes:
        raise HTTPException(status_code=422, detail="No scenes could be parsed.")

    return result
