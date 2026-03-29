"""
src/pipeline.py
────────────────
The orchestrator: ties fetchers → extractor → database together.

Key concepts:
  asyncio.gather() — runs all 3 fetchers concurrently (not sequentially)
  This means fetching from HN, RemoteOK, and Arbeitnow happens in parallel.
  Total fetch time = slowest source, not sum of all sources.

Pipeline flow:
  1. Run all fetchers concurrently → pool of RawJobPost
  2. Deduplicate by source_id (in case of overlap)
  3. Run LLM extraction in batches
  4. Build JobRecord from (raw + extracted)
  5. Bulk save to SQLite
  6. Return a PipelineResult summary
"""

import asyncio
import logging
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

import aiohttp

from src.config import get_settings
from src.models import RawJobPost, JobRecord, JobSource
from src.fetchers.hn import HNFetcher
from src.fetchers.remoteok import RemoteOKFetcher
from src.fetchers.arbeitnow import ArbeitnowFetcher
from src.extractor import SkillExtractor, extract_skills_from_tags
from src.database import init_db, save_job_records_batch, get_stats

logger = logging.getLogger(__name__)


# ─── Result Summary ───────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """Summary returned after a pipeline run — used by the CLI to print results."""
    started_at: datetime
    finished_at: datetime
    by_source: dict[str, int] = field(default_factory=dict)
    total_fetched: int = 0
    total_extracted: int = 0
    extraction_failures: int = 0
    new_jobs_saved: int = 0
    duplicate_jobs: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


# ─── Source Registry ──────────────────────────────────────────────────────────

def get_fetchers(max_jobs: int) -> dict[str, object]:
    """
    All available fetchers.
    Adding a new source = add it here.
    """
    return {
        JobSource.HN.value:        HNFetcher(max_jobs=max_jobs),
        JobSource.REMOTEOK.value:  RemoteOKFetcher(max_jobs=max_jobs),
        JobSource.ARBEITNOW.value: ArbeitnowFetcher(max_jobs=max_jobs),
    }


# ─── Pipeline ─────────────────────────────────────────────────────────────────

async def run_pipeline(
    sources: list[str] | None = None,
    max_jobs_per_source: int | None = None,
) -> PipelineResult:
    """
    Run the full ingestion pipeline.

    Args:
        sources: Which sources to fetch from. None = all.
                 e.g. ["hackernews", "remoteok"]
        max_jobs_per_source: Override the .env setting for testing.

    Returns:
        PipelineResult with full stats.
    """
    settings = get_settings()
    max_jobs = max_jobs_per_source or settings.max_jobs_per_source
    db_path  = settings.db_path
    started_at = datetime.now(ZoneInfo("Asia/Kolkata"))
 

    result = PipelineResult(started_at=started_at, finished_at=started_at)

    # ── Init DB ──
    init_db(db_path)

    # ── Select fetchers ──
    all_fetchers = get_fetchers(max_jobs)
    if sources:
        selected = {k: v for k, v in all_fetchers.items() if k in sources}
    else:
        selected = all_fetchers

    if not selected:
        logger.error(f"No valid sources found. Available: {list(all_fetchers.keys())}")
        result.finished_at = datetime.now(ZoneInfo("Asia/Kolkata"))
        return result

    # ── Step 1: Fetch concurrently from all sources ──
    logger.info(f"Fetching from {list(selected.keys())} (max {max_jobs} per source)...")

    all_posts: list[RawJobPost] = []

    # Single shared aiohttp session for all fetchers (connection pool)
    async with aiohttp.ClientSession() as session:
        # asyncio.gather runs all fetch() coroutines in parallel
        fetch_tasks = [fetcher.fetch(session) for fetcher in selected.values()] # type: ignore
        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    for source_name, fetch_result in zip(selected.keys(), fetch_results):
        if isinstance(fetch_result, Exception):
            msg = f"Fetch failed for {source_name}: {fetch_result}"
            logger.error(msg)
            result.errors.append(msg)
            result.by_source[source_name] = 0
        else:
            result.by_source[source_name] = len(fetch_result) # type: ignore
            all_posts.extend(fetch_result) # type: ignore
            logger.info(f"  {source_name}: {len(fetch_result)} posts") # type: ignore

    result.total_fetched = len(all_posts)
    logger.info(f"Total fetched: {result.total_fetched} posts")

    if not all_posts:
        logger.warning("No posts fetched — aborting")
        result.finished_at = datetime.now(ZoneInfo("Asia/Kolkata"))
        return result

    # ── Step 2: Deduplicate by source_id ──
    seen_ids: set[str] = set()
    unique_posts: list[RawJobPost] = []
    for post in all_posts:
        key = f"{post.source.value}:{post.source_id}"
        if key not in seen_ids:
            seen_ids.add(key)
            unique_posts.append(post)

    if len(unique_posts) < len(all_posts):
        logger.info(f"Deduped: {len(all_posts)} → {len(unique_posts)} unique posts")
    all_posts = unique_posts

    # ── Step 3: LLM Skill Extraction ──
    logger.info("Extracting skills with LLM...")
    extractor = SkillExtractor()
    extraction_pairs = await extractor.extract_batch(all_posts)

    # ── Step 4: Build JobRecords ──
    fetched_at = datetime.now(ZoneInfo("Asia/Kolkata"))
    records: list[JobRecord] = []

    for raw, extracted in extraction_pairs:
        if extracted is None:
            result.extraction_failures += 1
            # Fallback: use pre-parsed tags if available
            if raw.raw_tags:
                extracted = extract_skills_from_tags(raw.raw_tags)
                logger.debug(f"Used tag fallback for: {raw.title}")
            else:
                logger.debug(f"Skipping (no extraction, no tags): {raw.title}")
                continue

        result.total_extracted += 1
        record = JobRecord.from_raw_and_extracted(raw, extracted, fetched_at)
        records.append(record)

    logger.info(f"Built {len(records)} job records ({result.extraction_failures} extraction failures)")

    # ── Step 5: Bulk Save ──
    logger.info("Saving to database...")
    new_count, dup_count = save_job_records_batch(db_path, records)
    result.new_jobs_saved = new_count
    result.duplicate_jobs = dup_count

    result.finished_at = datetime.now(ZoneInfo("Asia/Kolkata"))

    logger.info(
        f"Pipeline complete in {result.duration_seconds:.1f}s — "
        f"{new_count} new, {dup_count} duplicates"
    )
    return result
