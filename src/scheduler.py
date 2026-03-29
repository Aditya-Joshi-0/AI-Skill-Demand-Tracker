"""
src/scheduler.py
─────────────────
APScheduler: runs the ingestion pipeline automatically every day at midnight IST.

Key concept: why a scheduler inside the app vs an external cron job?
  External cron (GitHub Actions, Render cron, system cron):
    + Simpler, decoupled
    + Runs even if the app is down
    - Requires infrastructure setup on every platform

  In-process scheduler (APScheduler):
    + Zero external dependencies — app is self-contained
    + Easier to deploy anywhere (Railway, Fly.io, Render)
    + Can be toggled via env var
    - Dies if the app process dies

  For a portfolio project: in-process scheduler wins.
  In production at scale: external scheduler wins.

APScheduler concepts:
  BackgroundScheduler: runs jobs in background threads
  CronTrigger: cron-style scheduling ("0 0 * * *" = midnight IST daily)
  IntervalTrigger: run every N minutes/hours (useful for testing)
"""

import asyncio
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Module-level scheduler instance
_scheduler: BackgroundScheduler | None = None


def _run_pipeline_sync():
    """
    Sync wrapper around the async pipeline.
    APScheduler runs jobs in threads (not async), so we need
    asyncio.run() to create a new event loop for the async pipeline.
    """
    logger.info("Scheduled pipeline run starting...")
    try:
        from src.pipeline import run_pipeline
        result = asyncio.run(run_pipeline())
        logger.info(
            f"Scheduled run complete: {result.new_jobs_saved} new jobs, "
            f"{result.total_fetched} fetched, "
            f"{result.duration_seconds:.1f}s"
        )
    except Exception as e:
        logger.error(f"Scheduled pipeline run failed: {e}", exc_info=True)


def start_scheduler() -> None:
    """
    Start the background scheduler.
    Called once at app startup (in the lifespan context manager).

    Set SCHEDULER_ENABLED=false in .env to disable (useful in tests).
    Set SCHEDULER_INTERVAL_MINUTES=30 to run every 30 minutes (for testing).
    """
    global _scheduler

    if os.getenv("SCHEDULER_ENABLED", "true").lower() == "false":
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # Check if we should use interval mode (for testing) or daily cron
    interval_minutes = os.getenv("SCHEDULER_INTERVAL_MINUTES")

    if interval_minutes:
        # Test mode: run every N minutes
        minutes = int(interval_minutes)
        trigger = IntervalTrigger(minutes=minutes)
        logger.info(f"Scheduler: interval mode — every {minutes} minutes")
    else:
        # Production: run at midnight IST every day
        # Cron: minute=0, hour=0 = 00:00 IST daily
        trigger = CronTrigger(hour=0, minute=0, timezone="Asia/Kolkata")
        logger.info("Scheduler: cron mode — daily at 00:00 IST")

    _scheduler.add_job(
        _run_pipeline_sync,
        trigger=trigger,
        id="daily_ingest",
        name="Daily Skill Ingestion Pipeline",
        replace_existing=True,
        misfire_grace_time=3600,   # if job missed by <1hr, still run it
    )

    _scheduler.start()
    logger.info("APScheduler started ✓")


def stop_scheduler() -> None:
    """Stop the scheduler on app shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped ✓")


def get_scheduler_status() -> dict:
    """Return scheduler status — used by health endpoint."""
    if _scheduler is None:
        return {"running": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time),
        })

    return {
        "running": _scheduler.running,
        "jobs": jobs,
    }
