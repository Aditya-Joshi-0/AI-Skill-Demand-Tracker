"""
src/api/routes/ingest.py
─────────────────────────
POST /ingest — trigger the ingestion pipeline via HTTP.

Why expose this as an API endpoint?
  - Lets an external scheduler (cron, GitHub Actions, Render cron job)
    trigger ingestion with a simple HTTP POST
  - Useful for on-demand refreshes from the dashboard
  - The APScheduler also calls run_pipeline() directly, so this is
    just a thin HTTP wrapper around the same function

FastAPI concept: Background Tasks
  We run the pipeline in a BackgroundTask so the HTTP response
  returns immediately (202 Accepted) rather than blocking for
  the full 30-60 second pipeline run.

  But for simplicity in Phase 3 we run it synchronously with
  asyncio — you can upgrade to BackgroundTasks in Phase 4 if needed.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from src.api.schemas import IngestRequest, IngestResponse
from src.pipeline import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, tags=["pipeline"])
async def trigger_ingest(body: IngestRequest = IngestRequest()):
    """
    Trigger the ingestion pipeline. Fetches jobs, extracts skills, saves to DB.
    This call blocks until the pipeline completes (~30-90s depending on sources).
    """
    logger.info(f"API triggered ingest: sources={body.sources}, max_jobs={body.max_jobs_per_source}")

    try:
        result = await run_pipeline(
            sources=body.sources,
            max_jobs_per_source=body.max_jobs_per_source,
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

    return IngestResponse(
        status="completed",
        new_jobs_saved=result.new_jobs_saved,
        duplicate_jobs=result.duplicate_jobs,
        total_fetched=result.total_fetched,
        extraction_failures=result.extraction_failures,
        duration_seconds=result.duration_seconds,
        by_source=result.by_source,
        errors=result.errors,
    )
