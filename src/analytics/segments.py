"""
src/analytics/segments.py
──────────────────────────
Segmented skill analysis: break down skill demand by
  - Seniority level (junior vs senior requirements differ a lot)
  - Role category (AI Engineer vs Data Scientist vs DevOps)
  - Job source (HN vs RemoteOK vs Arbeitnow)
  - Remote vs onsite

Key insight this enables:
  "Python is required by 80% of all jobs"
  vs
  "Python is required by 95% of Senior AI Engineer roles but only 40% of junior roles"

The second statement is far more useful for career decisions.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.database import get_connection

logger = logging.getLogger(__name__)


@dataclass
class SegmentRow:
    """A single segment → skill → count record."""
    segment_value: str    # e.g. "senior", "AI/ML Engineer", "hackernews"
    skill_name: str
    skill_category: str
    job_count: int
    frequency: float      # % of jobs in this segment mentioning this skill

def get_skills_by_seniority(
    dsn: str,  # Swapped db_path for dsn
    top_n: int = 15,
) -> dict[str, list[dict]]:
    """
    Top skills per seniority level.

    Returns: {seniority_level: [{skill, count, frequency}, ...]}
    """
    query = """
        SELECT
            j.seniority,
            s.name         AS skill_name,
            s.category,
            COUNT(DISTINCT j.id) AS job_count,
            COUNT(DISTINCT j.id) * 100.0 / (
                SELECT COUNT(DISTINCT id)
                FROM jobs j2
                WHERE j2.seniority = j.seniority
            ) AS frequency
        FROM jobs j
        JOIN job_skills js ON js.job_id = j.id
        JOIN skills s      ON s.id = js.skill_id
        WHERE j.seniority != 'unknown'
        GROUP BY j.seniority, s.name, s.category          -- FIX 1: Added s.category
        ORDER BY j.seniority, COUNT(DISTINCT j.id) DESC   -- FIX 2: Replaced alias
    """
    
    # FIX 3: Renamed conn to cursor
    with get_connection(dsn) as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    result: dict[str, list[dict]] = {}
    for row in rows:
        seg = row["seniority"]
        if seg not in result:
            result[seg] = []
        if len(result[seg]) < top_n:
            result[seg].append({
                "skill": row["skill_name"],
                "category": row["category"],
                "count": row["job_count"],
                "frequency": round(row["frequency"], 1),
            })

    return result


def get_skills_by_role_category(
    dsn: str,  # Swapped db_path for dsn
    top_n: int = 15,
) -> dict[str, list[dict]]:
    """
    Top skills per role category (AI/ML Engineer, Data Scientist, etc.)
    """
    query = """
        SELECT
            j.role_category,
            s.name         AS skill_name,
            s.category,
            COUNT(DISTINCT j.id) AS job_count,
            COUNT(DISTINCT j.id) * 100.0 / (
                SELECT COUNT(DISTINCT id)
                FROM jobs j2
                WHERE j2.role_category = j.role_category
            ) AS frequency
        FROM jobs j
        JOIN job_skills js ON js.job_id = j.id
        JOIN skills s      ON s.id = js.skill_id
        WHERE j.role_category IS NOT NULL AND j.role_category != ''
        GROUP BY j.role_category, s.name, s.category        -- FIX 1: Added s.category
        ORDER BY j.role_category, COUNT(DISTINCT j.id) DESC -- FIX 2: Replaced alias
    """
    
    # FIX 3: Renamed conn to cursor
    with get_connection(dsn) as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    result: dict[str, list[dict]] = {}
    for row in rows:
        seg = row["role_category"]
        if seg not in result:
            result[seg] = []
        if len(result[seg]) < top_n:
            result[seg].append({
                "skill": row["skill_name"],
                "category": row["category"],
                "count": row["job_count"],
                "frequency": round(row["frequency"], 1),
            })

    return result

def get_skills_by_source(
    dsn: str,  # Swapped db_path for dsn
    top_n: int = 15,
) -> dict[str, list[dict]]:
    """
    Compare which skills each job board emphasises.
    HN tends to be AI-heavy; RemoteOK has more full-stack.
    """
    query = """
        SELECT
            j.source,
            s.name AS skill_name,
            s.category,
            COUNT(DISTINCT j.id) AS job_count,
            COUNT(DISTINCT j.id) * 100.0 / (
                SELECT COUNT(DISTINCT id)
                FROM jobs j2
                WHERE j2.source = j.source
            ) AS frequency
        FROM jobs j
        JOIN job_skills js ON js.job_id = j.id
        JOIN skills s ON s.id = js.skill_id
        GROUP BY j.source, s.name, s.category       -- FIX 1: Added s.category
        ORDER BY j.source, COUNT(DISTINCT j.id) DESC -- FIX 2: Replaced alias in ORDER BY
    """
    
    # FIX 3: Split execution and fetchall
    with get_connection(dsn) as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    result: dict[str, list[dict]] = {}
    for row in rows:
        seg = row["source"]
        if seg not in result:
            result[seg] = []
        if len(result[seg]) < top_n:
            result[seg].append({
                "skill": row["skill_name"],
                "category": row["category"],
                "count": row["job_count"],
                "frequency": round(row["frequency"], 1),
            })

    return result

def compare_skill_across_segments(
    db_path: str,
    skill_name: str,
) -> dict:
    """
    Deep-dive on a single skill: how does its demand vary across segments?
    Used by: python analyse.py --skill "Python"

    Returns breakdown by seniority, role, source, and remote flag.
    """
    base_query = """
        SELECT
            {segment_col} AS segment,
            COUNT(DISTINCT j.id) AS skill_jobs,
            (SELECT COUNT(DISTINCT id) FROM jobs j2
             WHERE {segment_col} = {segment_col_alias}) AS total_in_segment
        FROM jobs j
        JOIN job_skills js ON js.job_id = j.id
        JOIN skills s ON s.id = js.skill_id
        WHERE s.name = %s
        GROUP BY {segment_col}
        ORDER BY skill_jobs DESC
    """

    results = {}

    segments = {
        "seniority": ("j.seniority", "j2.seniority = j.seniority"),
        "role_category": ("j.role_category", "j2.role_category = j.role_category"),
        "source": ("j.source", "j2.source = j.source"),
    }

    with get_connection(db_path) as conn:
        for seg_name, (col, alias) in segments.items():
            query = f"""
                SELECT
                    {col} AS segment,
                    COUNT(DISTINCT j.id) AS skill_jobs,
                    (SELECT COUNT(DISTINCT id) FROM jobs j2
                     WHERE {alias}) AS total_in_segment
                FROM jobs j
                JOIN job_skills js ON js.job_id = j.id
                JOIN skills s ON s.id = js.skill_id
                WHERE s.name = %s
                GROUP BY {col}
                ORDER BY skill_jobs DESC
            """
            conn.execute(query, (skill_name,))
            rows = conn.fetchall()
            results[seg_name] = [
                {
                    "segment": row["segment"],
                    "count": row["skill_jobs"],
                    "frequency": round(
                        row["skill_jobs"] / row["total_in_segment"] * 100, 1
                    ) if row["total_in_segment"] else 0,
                }
                for row in rows
                if row["segment"]
            ]

    return results
