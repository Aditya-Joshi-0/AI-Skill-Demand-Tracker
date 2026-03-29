"""
src/fetchers/base.py
─────────────────────
Abstract base class that every fetcher must implement.

Why an abstract base?
  - Enforces a consistent interface: fetch() always returns list[RawJobPost]
  - The pipeline doesn't need to know which source it's calling
  - Adding a new source later = just subclass BaseFetcher

Key async concepts here:
  aiohttp.ClientSession — a reusable HTTP connection pool
  async with session.get(...) — non-blocking HTTP request
  asyncio.gather() — runs multiple coroutines concurrently
"""

import asyncio
import logging
from abc import ABC, abstractmethod

import aiohttp

from src.models import RawJobPost

logger = logging.getLogger(__name__)

# Default headers — some APIs reject requests without a User-Agent
DEFAULT_HEADERS = {
    "User-Agent": "SkillTracker/1.0 (open-source research tool)",
    "Accept": "application/json",
}

# Total timeout per request (connect + read)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class BaseFetcher(ABC):
    """All job board fetchers extend this class."""

    source_name: str = "unknown"   # override in subclass

    def __init__(self, max_jobs: int = 50):
        self.max_jobs = max_jobs

    @abstractmethod
    async def fetch(self, session: aiohttp.ClientSession) -> list[RawJobPost]:
        """
        Fetch job posts from this source.

        Args:
            session: Shared aiohttp session (don't create one per fetcher)

        Returns:
            List of normalised RawJobPost objects
        """
        ...

    async def safe_get_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        params: dict | None = None,
    ) -> dict | list | None:
        """
        GET request that returns parsed JSON or None on failure.
        Logs errors but doesn't crash the pipeline if one source is down.
        """
        try:
            async with session.get(
                url,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                logger.warning(f"[{self.source_name}] HTTP {resp.status} for {url}")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"[{self.source_name}] Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"[{self.source_name}] Error fetching {url}: {e}")
            return None
