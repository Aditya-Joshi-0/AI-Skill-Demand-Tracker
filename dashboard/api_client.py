"""
dashboard/api_client.py
────────────────────────
HTTP client for the Streamlit dashboard → FastAPI backend.

Why a separate client module?
  - All API calls go through one place — easy to swap base URL
  - st.cache_data decorators live here — cache results across reruns
  - Error handling in one place — dashboard pages just call functions

st.cache_data:
  Streamlit reruns the whole script on every interaction.
  @st.cache_data(ttl=300) means: cache this result for 5 minutes.
  Without it, every sidebar click would re-hit the API.
  TTL (time-to-live) = seconds before cache expires.
"""

import os
import requests
import streamlit as st

# Base URL: env var in Docker, localhost in dev
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")


def _get(endpoint: str, params: dict = None) -> dict | list | None:
    """
    Raw GET request. Returns parsed JSON or None on failure.
    Shows a Streamlit error if the API is unreachable.
    """
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=300)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        st.error(
            f"Cannot reach API at {API_BASE}. "
            "Make sure the backend is running: `uvicorn src.api.main:app --reload`"
        )
        return None
    except requests.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return None


def _post(endpoint: str, body: dict = None) -> dict | None:
    try:
        resp = requests.post(f"{API_BASE}{endpoint}", json=body or {}, timeout=300)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


# ─── Cached API calls ─────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_health() -> dict | None:
    return _get("/health")


@st.cache_data(ttl=300)
def get_trends(
    direction: str = None,
    category: str = None,
    seniority: str = None,
    limit: int = 50,
) -> list[dict]:
    params = {"limit": limit}
    if direction:  params["direction"] = direction
    if category:   params["category"]  = category
    if seniority:  params["seniority"] = seniority
    data = _get("/trends", params=params)
    return data.get("trends", []) if data else []


@st.cache_data(ttl=300)
def get_report(limit: int = 30, category: str = None) -> list[dict]:
    params = {"limit": limit}
    if category: params["category"] = category
    data = _get("/report", params=params)
    return data.get("skills", []) if data else []


@st.cache_data(ttl=300)
def get_skill_detail(name: str) -> dict | None:
    return _get(f"/skills/{name}")


@st.cache_data(ttl=300)
def get_skill_history(name: str, weeks: int = 8) -> list[dict]:
    data = _get(f"/skills/{name}/history", params={"weeks": weeks})
    return data if isinstance(data, list) else []


@st.cache_data(ttl=300)
def get_cooccurrence(limit: int = 30, min_lift: float = 1.2, category: str = None) -> list[dict]:
    params = {"limit": limit, "min_lift": min_lift}
    if category: params["category"] = category
    data = _get("/cooccurrence", params=params)
    return data.get("pairs", []) if data else []


@st.cache_data(ttl=300)
def get_segments(by: str = "seniority", limit: int = 12) -> dict:
    data = _get("/segments", params={"by": by, "limit": limit})
    return data.get("data", {}) if data else {}


@st.cache_data(ttl=600)
def get_digest() -> dict | None:
    return _get("/digest")


def trigger_ingest(sources: list[str] = None, max_jobs: int = None) -> dict | None:
    """Trigger pipeline — not cached, always fresh."""
    body = {}
    if sources:   body["sources"] = sources
    if max_jobs:  body["max_jobs_per_source"] = max_jobs
    return _post("/ingest", body)
