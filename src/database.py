"""
src/database.py
───────────────
All PostgreSQL operations in one place (Migrated for Supabase).

Schema design decisions worth understanding:

1. THREE tables, not one fat table
   jobs        → one row per job post (metadata)
   skills      → unique skill names (normalisation)
   job_skills  → join table (many-to-many)

2. (source, source_id) as natural unique key
   Prevents duplicate ingestion if we re-run the pipeline on the same day.

3. fetched_at vs posted_at
   posted_at = when the company posted the job (may be weeks ago)
   fetched_at = when OUR pipeline ran (always today)

4. No ORM (no SQLAlchemy)
   Using raw SQL via psycopg2 keeps things simple, fast, and transparent.
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Generator

import psycopg2
from psycopg2.extras import DictCursor

from src.models import JobRecord, ExtractedSkill

logger = logging.getLogger(__name__)


# ─── Schema ──────────────────────────────────────────────────────────────────

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,          -- "hackernews", "remoteok", "arbeitnow"
    source_id   TEXT NOT NULL,          -- original ID from the job board
    title       TEXT NOT NULL,
    company     TEXT,
    url         TEXT,
    location    TEXT,
    is_remote   BOOLEAN DEFAULT TRUE,   -- Postgres supports native booleans
    job_type    TEXT,                   -- "full_time", "contract", etc.
    seniority   TEXT,                   -- "junior", "senior", etc.
    role_category TEXT,                 -- "AI/ML Engineer", "Data Scientist", etc.
    posted_at   TIMESTAMPTZ,            -- timezone-aware timestamp
    fetched_at  TIMESTAMPTZ NOT NULL,   -- timezone-aware timestamp

    -- Natural unique key: same job from same source = same record
    UNIQUE(source, source_id)
);
"""

CREATE_SKILLS_TABLE = """
CREATE TABLE IF NOT EXISTS skills (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,      -- "Python", "LangChain", "RAG"
    category TEXT NOT NULL              -- "language", "framework", etc.
);
"""

CREATE_JOB_SKILLS_TABLE = """
CREATE TABLE IF NOT EXISTS job_skills (
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id    INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    is_required BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (job_id, skill_id)
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_jobs_fetched_at  ON jobs(fetched_at);
CREATE INDEX IF NOT EXISTS idx_jobs_source      ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_seniority   ON jobs(seniority);
CREATE INDEX IF NOT EXISTS idx_job_skills_skill ON job_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_skills_name      ON skills(name);
"""


# ─── Connection Manager ───────────────────────────────────────────────────────

@contextmanager
def get_connection(dsn: str) -> Generator[DictCursor, None, None]:
    """
    Context manager that yields a Postgres cursor directly.
    Automatically commits on success, rolls back on error, and closes the connection.
    
    Usage:
        with get_connection(dsn) as cursor:
            cursor.execute("SELECT * FROM jobs")
            results = cursor.fetchall()
    """
    conn = psycopg2.connect(dsn, cursor_factory=DictCursor)
    try:
        # Create the cursor using a with block to ensure it closes cleanly
        with conn.cursor() as cursor:
            yield cursor  # Yield the cursor to the caller, not the connection
            
        # If the yielded block finishes without crashing, commit the transaction
        conn.commit()
    except Exception:
        # If anything goes wrong, roll back
        conn.rollback()
        raise
    finally:
        # Always close the connection at the very end
        conn.close()


# ─── Init ────────────────────────────────────────────────────────────────────

def init_db(dsn: str) -> None:
    """
    Create all tables and indexes if they don't exist.
    Safe to call on every startup.
    """
    with get_connection(dsn) as cursor:
        cursor.execute(CREATE_JOBS_TABLE)
        cursor.execute(CREATE_SKILLS_TABLE)
        cursor.execute(CREATE_JOB_SKILLS_TABLE)
        cursor.execute(CREATE_INDEXES)
    logger.info("Supabase PostgreSQL database initialised")


# ─── Write Operations ─────────────────────────────────────────────────────────

def insert_job(cursor: DictCursor, record: JobRecord) -> int | None:
    """
    Insert a job record. Returns the new row's id, or None if duplicate.
    Uses Postgres ON CONFLICT DO NOTHING combined with RETURNING id.
    """
    cursor.execute(
        """
        INSERT INTO jobs
            (source, source_id, title, company, url, location,
             is_remote, job_type, seniority, role_category, posted_at, fetched_at)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source, source_id) DO NOTHING
        RETURNING id
        """,
        (
            record.source,
            record.source_id,
            record.title,
            record.company,
            record.url,
            record.location,
            record.is_remote,      # Postgres accepts raw booleans
            record.job_type,
            record.seniority,
            record.role_category,
            record.posted_at,
            record.fetched_at,
        ),
    )
    result = cursor.fetchone()
    return result["id"] if result else None


def upsert_skill(cursor: DictCursor, skill: ExtractedSkill) -> int:
    """
    Insert a skill if it doesn't exist, return its id either way.
    """
    cursor.execute(
        "INSERT INTO skills (name, category) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
        (skill.name, skill.category.value),
    )
    cursor.execute(
        "SELECT id FROM skills WHERE name = %s", 
        (skill.name,)
    )
    return cursor.fetchone()["id"]


def link_job_skill(
    cursor: DictCursor,
    job_id: int,
    skill_id: int,
    is_required: bool,
) -> None:
    """Link a job to a skill in the join table. Ignore if already linked."""
    cursor.execute(
        "INSERT INTO job_skills (job_id, skill_id, is_required) VALUES (%s, %s, %s) ON CONFLICT (job_id, skill_id) DO NOTHING",
        (job_id, skill_id, is_required),
    )


def save_job_record(dsn: str, record: JobRecord) -> bool:
    """
    Top-level write: insert a job + all its skills atomically.
    Returns True if the job was new, False if it was a duplicate.
    """
    with get_connection(dsn) as conn:
        job_id = insert_job(conn, record)
        if job_id is None:
            return False  # duplicate

        for skill in record.skills:
            skill_id = upsert_skill(conn, skill)
            link_job_skill(conn, job_id, skill_id, skill.is_required)

    return True


def save_job_records_batch(dsn: str, records: list[JobRecord]) -> tuple[int, int]:
    """
    Bulk save for efficiency. Returns (new_count, duplicate_count).
    Uses a single connection and transaction for the whole batch.
    """
    new_count = 0
    dup_count = 0

    with get_connection(dsn) as conn:
        for record in records:
            job_id = insert_job(conn, record)
            if job_id is None:
                dup_count += 1
                continue
            
            new_count += 1
            for skill in record.skills:
                skill_id = upsert_skill(conn, skill)
                link_job_skill(conn, job_id, skill_id, skill.is_required)

    return new_count, dup_count


# ─── Read Operations ──────────────────────────────────────────────────────────

def get_stats(dsn: str) -> dict:
    """Summary stats — used by the CLI to show DB health."""
    with get_connection(dsn) as cursor:
        cursor.execute("SELECT COUNT(*) FROM jobs")
        job_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM skills")
        skill_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM job_skills")
        link_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT source, COUNT(*) as n FROM jobs GROUP BY source")
        sources = cursor.fetchall()
        
        cursor.execute("SELECT MAX(fetched_at) FROM jobs")
        latest = cursor.fetchone()[0]
    
    return {
        "total_jobs": job_count,
        "unique_skills": skill_count,
        "skill_links": link_count,
        "by_source": {row["source"]: row["n"] for row in sources},
        "latest_fetch": latest.isoformat() if latest else None,
    }

def get_top_skills(dsn: str, limit: int = 20, days: int = 7) -> list[dict]:
    """
    Top N skills by job count in the last `days` days.
    """
    # Calculate the exact timestamp cutoff in Python to keep the SQL clean
    cutoff_time = datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(days=days)
    
    with get_connection(dsn) as cursor:
        cursor.execute(
            """
            SELECT
                s.name,
                s.category,
                COUNT(DISTINCT js.job_id) as job_count
            FROM skills s
            JOIN job_skills js ON js.skill_id = s.id
            JOIN jobs j ON j.id = js.job_id
            WHERE j.fetched_at >= %s
            GROUP BY s.id
            ORDER BY job_count DESC
            LIMIT %s
            """,
            (cutoff_time, limit),
        )
        rows = cursor.fetchall()
            
    return [dict(row) for row in rows]
