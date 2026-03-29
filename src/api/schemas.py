"""
src/api/schemas.py
───────────────────
All FastAPI request and response schemas live here.

Why separate schemas from src/models.py?
  models.py = internal data shapes (pipeline, DB)
  schemas.py = external API contract (what clients see)

  These often differ:
    - API responses may flatten nested objects
    - API may expose fewer fields than the internal model
    - Versioning: internal models can change without breaking the API contract

Key FastAPI concept: response_model=
  FastAPI automatically validates AND serialises the return value
  against the response schema. If your function returns extra fields,
  they get stripped. If it returns wrong types, FastAPI raises a 500
  before the client sees broken data.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ─── Common ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    db_path: str
    total_jobs: int
    unique_skills: int
    latest_fetch: Optional[str]


# ─── Trends ───────────────────────────────────────────────────────────────────

class SkillTrendResponse(BaseModel):
    name: str
    category: str
    current_count: int
    previous_count: int
    current_freq: float
    previous_freq: float
    delta_pct: float
    direction: str           # "rising" | "falling" | "stable" | "new" | "disappeared"
    weeks_present: int
    momentum_label: str


class TrendsResponse(BaseModel):
    trends: list[SkillTrendResponse]
    total: int
    filters_applied: dict


# ─── Skills ───────────────────────────────────────────────────────────────────

class SkillHistoryPoint(BaseModel):
    week_start: str
    job_count: int
    frequency: float
    total_jobs: int


class SkillNeighbor(BaseModel):
    skill: str
    co_count: int
    confidence: float


class SkillDetailResponse(BaseModel):
    name: str
    history: list[SkillHistoryPoint]
    neighbors: list[SkillNeighbor]
    segments: dict


# ─── Report ───────────────────────────────────────────────────────────────────

class ScoredSkillResponse(BaseModel):
    rank: int
    name: str
    category: str
    total_jobs: int
    frequency: float
    trend_direction: str
    trend_delta: float
    investment_score: float
    investment_label: str


class ReportResponse(BaseModel):
    skills: list[ScoredSkillResponse]
    total: int
    category_filter: Optional[str]


# ─── Co-occurrence ────────────────────────────────────────────────────────────

class SkillPairResponse(BaseModel):
    skill_a: str
    skill_b: str
    co_occurrence_count: int
    support: float
    confidence_a_to_b: float
    confidence_b_to_a: float
    lift: float
    strength_label: str


class CooccurrenceResponse(BaseModel):
    pairs: list[SkillPairResponse]
    total: int


# ─── Segments ─────────────────────────────────────────────────────────────────

class SegmentSkillItem(BaseModel):
    skill: str
    category: str
    count: int
    frequency: float


class SegmentsResponse(BaseModel):
    segment_by: str
    data: dict[str, list[SegmentSkillItem]]


# ─── Digest ───────────────────────────────────────────────────────────────────

class DigestResponse(BaseModel):
    generated_at: str
    period: str
    narrative: str              # LLM-generated summary
    top_rising: list[str]
    top_falling: list[str]
    top_skills: list[str]
    new_skills: list[str]
    total_jobs_analysed: int


# ─── Ingest (trigger pipeline via API) ───────────────────────────────────────

class IngestRequest(BaseModel):
    sources: Optional[list[str]] = Field(
        default=None,
        description="Sources to fetch from. None = all. Options: hackernews, remoteok, arbeitnow"
    )
    max_jobs_per_source: Optional[int] = Field(
        default=None,
        description="Max jobs per source. Overrides env setting."
    )


class IngestResponse(BaseModel):
    status: str
    new_jobs_saved: int
    duplicate_jobs: int
    total_fetched: int
    extraction_failures: int
    duration_seconds: float
    by_source: dict[str, int]
    errors: list[str]
