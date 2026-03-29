"""
src/models.py
─────────────
Pydantic models are the single source of truth for data shapes.
They're used for:
  - Validating raw API responses from job boards
  - Defining the LLM's structured output schema (ExtractedSkills)
  - Type hints throughout the codebase

Key concept: Pydantic v2 with `model_validator` lets us normalise
incoming data (e.g. strip HTML, trim whitespace) at the boundary,
so the rest of the code only ever sees clean data.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field, model_validator, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────

class JobSource(str, Enum):
    HN         = "hackernews"
    REMOTEOK   = "remoteok"
    ARBEITNOW  = "arbeitnow"


class SeniorityLevel(str, Enum):
    JUNIOR    = "junior"
    MID       = "mid"
    SENIOR    = "senior"
    LEAD      = "lead"
    UNKNOWN   = "unknown"


class JobType(str, Enum):
    FULL_TIME  = "full_time"
    PART_TIME  = "part_time"
    CONTRACT   = "contract"
    UNKNOWN    = "unknown"


# ─── Raw Job Post ─────────────────────────────────────────────────────────────

class RawJobPost(BaseModel):
    """
    Normalised job post from any source.
    All fetchers produce this same shape.

    The `source_id` is the original ID from the job board.
    Together with `source`, it forms a unique key for deduplication.
    """
    source: JobSource
    source_id: str                          # e.g. "hn_12345678"
    title: str
    company: str = "Unknown"
    description: str                        # raw text, may contain HTML
    url: str = ""
    location: str = "Remote"
    is_remote: bool = True
    job_type: JobType = JobType.UNKNOWN
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    posted_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Kolkata")))
    raw_tags: list[str] = Field(default_factory=list)  # pre-parsed tags from source

    @field_validator("description", mode="before")
    @classmethod
    def strip_html(cls, v: str) -> str:
        """Remove HTML tags — descriptions from HN often have <p>, <a> etc."""
        if not v:
            return ""
        clean = re.sub(r"<[^>]+>", " ", str(v))
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:4000]  # cap length to avoid huge LLM prompts

    @field_validator("title", "company", mode="before")
    @classmethod
    def clean_string(cls, v) -> str:
        return str(v).strip()[:200] if v else ""

    @model_validator(mode="after")
    def infer_seniority_from_title(self) -> "RawJobPost":
        """
        If seniority wasn't set by the fetcher, guess from the title.
        This is a heuristic — good enough for trend analysis.
        """
        if self.seniority != SeniorityLevel.UNKNOWN:
            return self
        title_lower = self.title.lower()
        if any(w in title_lower for w in ["junior", "entry", "graduate", "intern"]):
            self.seniority = SeniorityLevel.JUNIOR
        elif any(w in title_lower for w in ["senior", "sr.", "sr ", "staff", "principal"]):
            self.seniority = SeniorityLevel.SENIOR
        elif any(w in title_lower for w in ["lead", "manager", "head of", "director"]):
            self.seniority = SeniorityLevel.LEAD
        elif any(w in title_lower for w in ["mid", "intermediate"]):
            self.seniority = SeniorityLevel.MID
        return self


# ─── LLM Extraction Output ───────────────────────────────────────────────────

class SkillCategory(str, Enum):
    """
    We categorise skills so we can analyse them separately.
    e.g. "Is Python demand up?" vs "Is agent framework demand up?"
    """
    LANGUAGE      = "language"        # Python, TypeScript, Go
    FRAMEWORK     = "framework"       # LangChain, FastAPI, React
    ML_CONCEPT    = "ml_concept"      # RAG, fine-tuning, RLHF, transformers
    CLOUD         = "cloud"           # AWS, GCP, Azure, Kubernetes
    DATABASE      = "database"        # PostgreSQL, ChromaDB, Redis
    TOOL          = "tool"            # Docker, Git, Terraform
    DOMAIN        = "domain"          # NLP, computer vision, recommendation systems
    OTHER         = "other"


class ExtractedSkill(BaseModel):
    """A single skill extracted from a job description."""
    name: str = Field(
        description="Canonical skill name, e.g. 'Python', 'LangChain', 'RAG'. "
                    "Normalise: 'python3' → 'Python', 'lang chain' → 'LangChain'."
    )
    category: SkillCategory = Field(
        description="Best-fit category for this skill."
    )
    is_required: bool = Field(
        default=True,
        description="True if listed as required/must-have, False if nice-to-have/preferred."
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: str) -> str:
        return str(v).strip()[:100]


class ExtractedSkills(BaseModel):
    """
    Structured output schema for the LLM extractor.

    This is what we tell the LLM to return.
    LangChain's .with_structured_output() enforces this schema,
    so we always get valid, typed data back — no parsing needed.
    """
    skills: list[ExtractedSkill] = Field(
        description="All technical skills mentioned in this job posting.",
        max_length=30,   # cap at 30 to prevent hallucination
    )
    role_category: str = Field(
        description="High-level role type: e.g. 'AI/ML Engineer', "
                    "'Data Scientist', 'Backend Engineer', 'DevOps'."
    )


# ─── Stored Records (what goes into SQLite) ──────────────────────────────────

class JobRecord(BaseModel):
    """A fully processed job post, ready to be written to the DB."""
    source: str
    source_id: str
    title: str
    company: str
    url: str
    location: str
    is_remote: bool
    job_type: str
    seniority: str
    role_category: str
    posted_at: str          # ISO8601 string for SQLite
    fetched_at: str         # when our pipeline ran
    skills: list[ExtractedSkill]

    @classmethod
    def from_raw_and_extracted(
        cls,
        raw: RawJobPost,
        extracted: ExtractedSkills,
        fetched_at: datetime,
    ) -> "JobRecord":
        return cls(
            source=raw.source.value,
            source_id=raw.source_id,
            title=raw.title,
            company=raw.company,
            url=raw.url,
            location=raw.location,
            is_remote=raw.is_remote,
            job_type=raw.job_type.value,
            seniority=raw.seniority.value,
            role_category=extracted.role_category,
            posted_at=raw.posted_at.isoformat(),
            fetched_at=fetched_at.isoformat(),
            skills=extracted.skills,
        )
