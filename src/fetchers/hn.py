"""
src/fetchers/hn.py
───────────────────
Fetches jobs from Hacker News "Who is Hiring" threads via the Algolia HN API.

Why HN?
  - Monthly "Ask HN: Who is Hiring?" threads are legendary in the industry
  - Extremely signal-rich for AI/ML/engineering roles
  - Algolia's HN search API is free, no auth, returns clean JSON
  - Direct from hiring managers/founders — very little noise

How it works:
  1. Search for the most recent "Ask HN: Who is Hiring?" post
  2. Fetch all top-level comments (each = one job post)
  3. Parse free-text comment into structured RawJobPost

The tricky part: HN job posts are free-form text comments like:
  "Anthropic | AI Safety Engineer | SF or Remote | $200k | https://..."
  We parse these with heuristics + pass the full text to the LLM extractor.
"""

import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp

from src.models import RawJobPost, JobSource, JobType, SeniorityLevel
from src.fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)

# Algolia HN search API — no auth required
HN_SEARCH_URL   = "https://hn.algolia.com/api/v1/search"
HN_ITEMS_URL    = "https://hn.algolia.com/api/v1/items"


class HNFetcher(BaseFetcher):
    """Fetches from HN 'Who is Hiring' threads via Algolia."""

    source_name = "hackernews"

    async def fetch(self, session: aiohttp.ClientSession) -> list[RawJobPost]:
        logger.info("[HN] Starting fetch...")

        # ── Step 1: Find the latest "Who is Hiring?" thread ──
        thread_id = await self._find_latest_hiring_thread(session)
        if not thread_id:
            logger.error("[HN] Could not find a 'Who is Hiring' thread")
            return []

        logger.info(f"[HN] Found hiring thread: https://news.ycombinator.com/item?id={thread_id}")

        # ── Step 2: Fetch all comments from the thread ──
        posts = await self._fetch_thread_comments(session, thread_id)
        logger.info(f"[HN] Fetched {len(posts)} job posts")
        return posts

    async def _find_latest_hiring_thread(
        self, session: aiohttp.ClientSession
    ) -> str | None:
        """Search Algolia for the most recent 'Ask HN: Who is Hiring?' post."""
        data = await self.safe_get_json(
            session,
            HN_SEARCH_URL,
            params={
                "query": "Ask HN: Who is Hiring",
                "tags": "story,ask_hn",
                "hitsPerPage": 5,
            },
        )
        if not data or "hits" not in data:
            return None

        # The hits are sorted by relevance — find the most recent one
        hits = data["hits"] # type: ignore
        if not hits:
            return None

        # Sort by creation time descending and take the first
        hits_sorted = sorted(
            hits,
            key=lambda h: h.get("created_at_i", 0),
            reverse=True,
        )
        return str(hits_sorted[0]["objectID"])

    async def _fetch_thread_comments(
        self, session: aiohttp.ClientSession, thread_id: str
    ) -> list[RawJobPost]:
        """Fetch all top-level comments (job posts) from the thread."""
        data = await self.safe_get_json(session, f"{HN_ITEMS_URL}/{thread_id}")
        if not data or "children" not in data:
            return []

        posts = []
        for child in data["children"][: self.max_jobs]: # type: ignore
            # Skip deleted / dead comments
            if child.get("deleted") or child.get("dead"):
                continue
            text = child.get("text", "").strip()
            if not text or len(text) < 50:
                continue

            post = self._parse_comment(child)
            if post:
                posts.append(post)

        return posts

    def _parse_comment(self, comment: dict) -> RawJobPost | None:
        """
        Parse a single HN comment into a RawJobPost.

        HN comments often follow this loose format:
          "Company | Role | Location | Salary | URL"
        But it's free text so we do best-effort parsing.
        """
        try:
            text = comment.get("text", "")
            comment_id = str(comment.get("id", ""))
            created = comment.get("created_at", "")

            # Parse the first line for structured fields
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            first_line = lines[0] if lines else ""

            # Split on | to extract fields
            parts = [p.strip() for p in first_line.split("|")]

            company = parts[0] if len(parts) > 0 else "Unknown"
            title   = parts[1] if len(parts) > 1 else "Software Engineer"
            location = parts[2] if len(parts) > 2 else "Remote"

            # Extract URL from anywhere in the text
            urls = re.findall(r'https?://\S+', text)
            url = urls[0].rstrip(".,)>\"'") if urls else f"https://news.ycombinator.com/item?id={comment_id}"

            # Detect remote
            is_remote = any(
                w in text.lower()
                for w in ["remote", "wfh", "work from home", "distributed"]
            )

            # Parse datetime
            try:
                posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                posted_at = datetime.now(ZoneInfo("Asia/Kolkata"))

            # Infer job type
            job_type = JobType.UNKNOWN
            text_lower = text.lower()
            if "contract" in text_lower or "freelance" in text_lower:
                job_type = JobType.CONTRACT
            elif "part-time" in text_lower or "part time" in text_lower:
                job_type = JobType.PART_TIME
            elif "full-time" in text_lower or "full time" in text_lower:
                job_type = JobType.FULL_TIME

            return RawJobPost(
                source=JobSource.HN,
                source_id=f"hn_{comment_id}",
                title=title[:200],
                company=company[:200],
                description=text,       # full text → LLM will extract skills
                url=url,
                location=location,
                is_remote=is_remote,
                job_type=job_type,
                posted_at=posted_at,
            )

        except Exception as e:
            logger.debug(f"[HN] Failed to parse comment {comment.get('id')}: {e}")
            return None
