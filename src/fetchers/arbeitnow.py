"""
src/fetchers/arbeitnow.py
──────────────────────────
Fetches from Arbeitnow's free public job board API.

Why Arbeitnow?
  - Free, no auth, returns paginated clean JSON
  - Good global coverage (not just US-centric like HN)
  - Has tags + remote flag + full job descriptions
  - Provides diversity in the dataset

API docs: https://arbeitnow.com/api/job-board-api
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp

from src.models import RawJobPost, JobSource, JobType
from src.fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"

# Keywords to filter relevant tech/AI roles
RELEVANT_KEYWORDS = {
    "python", "machine learning", "ai", "data", "engineer",
    "backend", "developer", "llm", "cloud", "devops", "ml",
    "software", "fullstack", "data scientist", "nlp",
}


class ArbeitnowFetcher(BaseFetcher):
    source_name = "arbeitnow"

    async def fetch(self, session: aiohttp.ClientSession) -> list[RawJobPost]:
        logger.info("[Arbeitnow] Starting fetch...")

        posts = []
        page = 1

        # Paginate until we have enough jobs or run out of pages
        while len(posts) < self.max_jobs:
            data = await self.safe_get_json(
                session,
                ARBEITNOW_URL,
                params={"page": page},
            )

            if not data or not data.get("data"): # type: ignore
                break

            jobs_raw = data.get("data") # type: ignore
            if not jobs_raw:
                break

            for job in jobs_raw:
                if not self._is_relevant(job):
                    continue
                post = self._parse_job(job)
                if post:
                    posts.append(post)
                if len(posts) >= self.max_jobs:
                    break

            # Check if there are more pages
            if not data.get("links", {}).get("next"): # type: ignore
                break
            page += 1

        logger.info(f"[Arbeitnow] Fetched {len(posts)} relevant job posts")
        return posts

    def _is_relevant(self, job: dict) -> bool:
        """Check if this job is in a relevant tech category."""
        text = " ".join([
            job.get("title", ""),
            job.get("description", ""),
            " ".join(job.get("tags", [])),
        ]).lower()
        return any(kw in text for kw in RELEVANT_KEYWORDS)

    def _parse_job(self, job: dict) -> RawJobPost | None:
        try:
            # Arbeitnow gives Unix timestamp
            created = job.get("created_at", 0)
            try:
                posted_at = datetime.fromtimestamp(int(created), tz=ZoneInfo("Asia/Kolkata"))
            except Exception:
                posted_at = datetime.now(ZoneInfo("Asia/Kolkata"))

            is_remote = job.get("remote", False)
            location = "Remote" if is_remote else job.get("location", "Unknown")

            # Build rich description
            description_parts = [
                f"Title: {job.get('title', '')}",
                f"Company: {job.get('company_name', '')}",
                f"Location: {location}",
            ]
            if job.get("tags"):
                description_parts.append(f"Tags: {', '.join(job['tags'])}")
            if job.get("description"):
                description_parts.append(job["description"])

            return RawJobPost(
                source=JobSource.ARBEITNOW,
                source_id=f"arb_{job.get('slug', job.get('title', '')[:50])}",
                title=job.get("title", "Engineer"),
                company=job.get("company_name", "Unknown"),
                description="\n".join(description_parts),
                url=job.get("url", ""),
                location=location,
                is_remote=is_remote,
                job_type=JobType.FULL_TIME,
                posted_at=posted_at,
                raw_tags=job.get("tags", []),
            )
        except Exception as e:
            logger.debug(f"[Arbeitnow] Failed to parse job: {e}")
            return None
