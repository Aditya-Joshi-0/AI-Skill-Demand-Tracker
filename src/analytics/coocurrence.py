"""
src/analytics/cooccurrence.py
──────────────────────────────
Skill co-occurrence: which skills always appear together in the same job?

Why is this useful?
  Knowing Python is in demand is table stakes.
  Knowing "Python + FastAPI + Docker + AWS" is the dominant stack for
  AI backend roles — that's actionable. You know exactly what to learn next.

How it works:
  For every pair of skills (A, B) that appear in the same job:
    support(A,B)     = P(A and B)   = jobs_with_both / total_jobs
    confidence(A→B)  = P(B|A)       = jobs_with_both / jobs_with_A
    lift(A,B)        = P(A,B)/(P(A)*P(B))
                     = how much more likely they co-occur vs by chance

  These are standard Association Rule Mining metrics (Apriori algorithm).

  lift > 1    → positively correlated (appear together more than expected)
  lift = 1    → independent
  lift < 1    → negatively correlated (rarely together)

Concept you'll know for interviews:
  This is a simplified version of market basket analysis —
  "people who bought X also bought Y" applied to job requirements.
"""

import logging
from dataclasses import dataclass
from itertools import combinations
from typing import Optional

from src.database import get_connection

logger = logging.getLogger(__name__)


@dataclass
class SkillPair:
    """A co-occurring skill pair with association metrics."""
    skill_a: str
    skill_b: str
    co_occurrence_count: int    # jobs where both appear
    support: float              # % of all jobs where both appear
    confidence_a_to_b: float    # P(B | A): if job needs A, % also need B
    confidence_b_to_a: float    # P(A | B): if job needs B, % also need A
    lift: float                 # how much more likely vs random chance

    @property
    def strength_label(self) -> str:
        if self.lift >= 3.0:
            return "very strong"
        if self.lift >= 2.0:
            return "strong"
        if self.lift >= 1.5:
            return "moderate"
        return "weak"

    @property
    def pair_label(self) -> str:
        return f"{self.skill_a} + {self.skill_b}"


def compute_cooccurrence(
    db_path: str,
    min_support: float = 0.02,   # pair must appear in ≥2% of jobs
    min_lift: float = 1.2,       # must co-occur 20% more than random
    top_n: int = 50,
    category_filter: Optional[str] = None,
) -> list[SkillPair]:
    """
    Compute skill co-occurrence pairs.

    Args:
        db_path:        Path to SQLite DB
        min_support:    Minimum fraction of jobs where pair appears (noise filter)
        min_lift:       Minimum lift (correlation filter)
        top_n:          Return top N pairs by lift
        category_filter: Only include skills of this category

    Returns:
        List of SkillPair objects sorted by lift descending.
    """
    # Pull all (job_id, skill_name) pairs from DB
    cat_filter = "AND s.category = %s" if category_filter else ""
    params = [category_filter] if category_filter else []

    query = f"""
        SELECT j.id AS job_id, s.name AS skill_name
        FROM jobs j
        JOIN job_skills js ON js.job_id = j.id
        JOIN skills s      ON s.id = js.skill_id
        WHERE 1=1 {cat_filter}
        ORDER BY j.id
    """

    total_query = "SELECT COUNT(DISTINCT id) FROM jobs"

    with get_connection(db_path) as conn:
        conn.execute(query, params)
        rows = conn.fetchall()
        conn.execute(total_query)
        total_jobs = conn.fetchone()[0]

    if total_jobs == 0:
        return []

    # Build job → skills mapping
    job_skills: dict[int, set[str]] = {}
    for row in rows:
        job_id = row["job_id"]
        if job_id not in job_skills:
            job_skills[job_id] = set()
        job_skills[job_id].add(row["skill_name"])

    # Count individual skill occurrences
    skill_counts: dict[str, int] = {}
    for skills in job_skills.values():
        for skill in skills:
            skill_counts[skill] = skill_counts.get(skill, 0) + 1

    # Count pair occurrences
    pair_counts: dict[tuple[str, str], int] = {}
    for skills in job_skills.values():
        skill_list = sorted(skills)   # sort so (A,B) and (B,A) map to same key
        for a, b in combinations(skill_list, 2):
            pair = (a, b)
            pair_counts[pair] = pair_counts.get(pair, 0) + 1

    # Compute metrics and filter
    pairs: list[SkillPair] = []
    for (a, b), count in pair_counts.items():
        support = count / total_jobs
        if support < min_support:
            continue

        p_a = skill_counts.get(a, 0) / total_jobs
        p_b = skill_counts.get(b, 0) / total_jobs

        if p_a == 0 or p_b == 0:
            continue

        confidence_a_to_b = count / skill_counts[a]
        confidence_b_to_a = count / skill_counts[b]
        lift = support / (p_a * p_b)

        if lift < min_lift:
            continue

        pairs.append(SkillPair(
            skill_a=a,
            skill_b=b,
            co_occurrence_count=count,
            support=round(support * 100, 2),
            confidence_a_to_b=round(confidence_a_to_b * 100, 1),
            confidence_b_to_a=round(confidence_b_to_a * 100, 1),
            lift=round(lift, 2),
        ))

    pairs.sort(key=lambda p: p.lift, reverse=True)
    return pairs[:top_n]


def get_skill_neighbors(
    dsn: str,  # Swapped db_path for dsn
    skill_name: str,
    top_n: int = 10,
) -> list[dict]:
    """
    For a given skill, return its top co-occurring skills.
    Used in the dashboard: "skills that appear alongside Python".

    Returns list of {skill, count, confidence, lift} dicts.
    """
    with get_connection(dsn) as cursor: # Renamed conn to cursor
        # 1. FIX: Changed ? to %s
        cursor.execute(
            """
            SELECT DISTINCT j.id
            FROM jobs j
            JOIN job_skills js ON js.job_id = j.id
            JOIN skills s ON s.id = js.skill_id
            WHERE s.name = %s
            """,
            (skill_name,),
        )
        skill_jobs = cursor.fetchall()

        total_with_skill = len(skill_jobs)
        if total_with_skill == 0:
            return []

        # 2. FIX: Convert job_ids to a tuple so psycopg2 can adapt it cleanly
        job_ids = tuple(row["id"] for row in skill_jobs) 

        # 3. FIX: Removed string manipulation, used IN %s, and changed ? to %s
        cursor.execute(
            """
            SELECT s.name, COUNT(DISTINCT j.id) as co_count
            FROM jobs j
            JOIN job_skills js ON js.job_id = j.id
            JOIN skills s ON s.id = js.skill_id
            WHERE j.id IN %s
              AND s.name != %s
            GROUP BY s.name
            ORDER BY co_count DESC
            LIMIT %s
            """,
            (job_ids, skill_name, top_n), # Pass the tuple directly!
        )
        # 4. FIX: Standardized spelling to 'neighbors' to match the return loop
        neighbors = cursor.fetchall()

    return [
        {
            "skill": row["name"],
            "co_count": row["co_count"],
            "confidence": round(row["co_count"] / total_with_skill * 100, 1),
        }
        for row in neighbors
    ]

