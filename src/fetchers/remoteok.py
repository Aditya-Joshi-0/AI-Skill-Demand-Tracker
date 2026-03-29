"""
src/fetchers/remoteok.py
─────────────────────────
Fetches from RemoteOK's free public API.

Why RemoteOK?
  - 100% free, no API key, no rate limits documented
  - Already has tech tags per job (e.g. ["python", "fastapi", "aws"])
  - We use these pre-parsed tags AS WELL AS running LLM extraction
    on the description — the tags are a cross-validation signal

API docs: https://remoteok.com/api
Returns an array — the first element is a metadata object, skip it.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp

from src.models import RawJobPost, JobSource, JobType
from src.fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

REMOTEOK_URL = "https://remoteok.com/api"


class RemoteOKFetcher(BaseFetcher):
    source_name = "remoteok"

    # Tags we care about — filter to AI/ML/engineering jobs
    # (RemoteOK has a lot of non-tech jobs)
    RELEVANT_TAGS = {
        "python", "machine learning", "ai", "llm", "data science",
        "backend", "golang", "typescript", "javascript", "rust",
        "devops", "cloud", "aws", "gcp", "azure", "fullstack",
        "react", "nodejs", "fastapi", "django", "kubernetes", "docker",
    }

    async def fetch(self, session: aiohttp.ClientSession) -> list[RawJobPost]:
        logger.info("[RemoteOK] Starting fetch...")

        data = await self.safe_get_json(session, REMOTEOK_URL)
        if not data or not isinstance(data, list):
            logger.error("[RemoteOK] Unexpected response format")
            return []

        # First element is metadata — skip it
        jobs_raw = [item for item in data[1:] if isinstance(item, dict)]

        posts = []
        for job in jobs_raw:
            # Filter to relevant tech/AI roles
            tags = [t.lower() for t in job.get("tags", [])]
            if not any(t in self.RELEVANT_TAGS for t in tags):
                continue

            post = self._parse_job(job)
            if post:
                posts.append(post)

            if len(posts) >= self.max_jobs:
                break

        logger.info(f"[RemoteOK] Fetched {len(posts)} relevant job posts")
        return posts

    def _parse_job(self, job: dict) -> RawJobPost | None:
        try:
            # RemoteOK epoch is Unix timestamp
            epoch = job.get("epoch", 0)
            try:
                posted_at = datetime.fromtimestamp(int(epoch), tz=ZoneInfo("Asia/Kolkata"))
            except Exception:
                posted_at = datetime.now(ZoneInfo("Asia/Kolkata"))

            # Build description from available fields
            description_parts = []
            if job.get("position"):
                description_parts.append(f"Role: {job['position']}")
            if job.get("company"):
                description_parts.append(f"Company: {job['company']}")
            if job.get("description"):
                description_parts.append(job["description"])
            if job.get("tags"):
                description_parts.append(f"Tags: {', '.join(job['tags'])}")

            description = "\n".join(description_parts)

            return RawJobPost(
                source=JobSource.REMOTEOK,
                source_id=f"rok_{job.get('id', '')}",
                title=job.get("position", "Engineer"),
                company=job.get("company", "Unknown"),
                description=description,
                url=job.get("url", ""),
                location="Remote",
                is_remote=True,            # RemoteOK is remote-only by definition
                job_type=JobType.FULL_TIME,
                posted_at=posted_at,
                raw_tags=job.get("tags", []),
            )
        except Exception as e:
            logger.debug(f"[RemoteOK] Failed to parse job {job.get('id')}: {e}")
            return None
