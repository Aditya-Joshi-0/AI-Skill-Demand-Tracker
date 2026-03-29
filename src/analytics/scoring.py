"""
src/analytics/scoring.py
─────────────────────────
Saturation score + ranked skill report.

Saturation Score (0–100):
  A skill can be in high demand but also massively oversupplied.
  e.g. "Python" is in almost every job AND every developer knows it.
  That means it's table stakes — not a differentiator.

  We estimate saturation using two signals:
    1. frequency_score: how often does it appear in job posts? (high = good)
    2. ubiquity_penalty: skills that appear in ALL categories are commoditised
                         skills that appear in niche categories are differentiators

  saturation_score = frequency_score × (1 - ubiquity_penalty)

  High saturation score = high demand AND still a differentiator
  Low saturation score  = either low demand OR totally commoditised

Investment Score:
  Combines trend momentum + saturation.
  "Should I learn this skill right now?"
    HIGH investment score = rising demand + not yet oversupplied
    LOW  investment score = falling demand OR completely commoditised
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.database import get_connection
from src.analytics.trends import compute_trends, SkillTrend, TrendDirection

logger = logging.getLogger(__name__)


@dataclass
class ScoredSkill:
    """A skill with all computed scores — used for the full report."""
    name: str
    category: str
    total_jobs: int
    frequency: float            # % of all jobs
    trend_direction: str
    trend_delta: float          # week-over-week change %
    saturation_score: float     # 0–100, higher = more unique/differentiating
    investment_score: float     # 0–100, higher = better to learn now

    @property
    def investment_label(self) -> str:
        if self.investment_score >= 70:
            return "🟢 high priority"
        if self.investment_score >= 40:
            return "🟡 worth learning"
        return "🔴 low priority"

    @property
    def summary(self) -> str:
        return (
            f"{self.name} | {self.frequency:.1f}% of jobs | "
            f"{self.trend_delta:+.0f}% WoW | "
            f"invest={self.investment_score:.0f}"
        )


def compute_saturation_scores(db_path: str) -> dict[str, float]:
    """
    Compute saturation score (0–100) for every skill in the DB.

    Algorithm:
      1. raw_freq    = skill_jobs / total_jobs  (how in-demand)
      2. n_categories = how many distinct categories this skill spans
                        (a skill in 5 categories = commoditised)
      3. ubiquity    = n_categories / total_categories
      4. saturation  = raw_freq * (1 - ubiquity * 0.5)
      5. Normalise to 0–100

    The 0.5 factor means ubiquity cuts saturation score in half at most.
    Pure frequency still matters — a totally ubiquitous skill that's
    ALSO everywhere is still worth knowing.
    """
    query = """SELECT
    s.name,
    s.category,
    COUNT(DISTINCT js.job_id)                        AS skill_jobs,
    (SELECT COUNT(DISTINCT id) FROM jobs)            AS total_jobs,
    COUNT(DISTINCT j.role_category)                  AS n_role_categories,
    (SELECT COUNT(DISTINCT role_category) FROM jobs) AS total_role_categories
    FROM skills s
    JOIN job_skills js ON js.skill_id = s.id
    JOIN jobs j        ON j.id = js.job_id
    GROUP BY s.name, s.category  -- <-- Fix #2: Added s.category here
    HAVING COUNT(DISTINCT js.job_id) >= 3  -- <-- Fix #1: Replaced alias
    """
    

    with get_connection(db_path) as conn:
        conn.execute(query)
        rows = conn.fetchall()

    scores: dict[str, float] = {}
    raw_scores: dict[str, float] = {}

    for row in rows:
        total = row["total_jobs"] or 1
        total_cats = row["total_role_categories"] or 1

        raw_freq = row["skill_jobs"] / total
        ubiquity = row["n_role_categories"] / total_cats
        raw_score = raw_freq * (1 - ubiquity * 0.5)
        raw_scores[row["name"]] = raw_score

    # Normalise to 0–100
    if raw_scores:
        max_score = max(raw_scores.values())
        if max_score > 0:
            scores = {k: round(v / max_score * 100, 1) for k, v in raw_scores.items()}

    return scores

from typing import Optional
# Make sure to import get_connection, compute_saturation_scores, compute_trends, etc.

def build_skill_report(
    dsn: str,  # Swapped db_path for dsn
    top_n: int = 30,
    category: Optional[str] = None,
) -> list[ScoredSkill]:
    """
    Full ranked skill report: frequency + trend + saturation + investment score.
    """
    # Pass DSN down to the other functions
    sat_scores = compute_saturation_scores(dsn)
    trends = compute_trends(dsn)
    trend_map: dict[str, SkillTrend] = {t.name: t for t in trends}

    # FIX 1: Use Postgres %s placeholder
    cat_filter = "AND s.category = %s" if category else ""
    params = [category] if category else []

    # FIX 2: Added s.category to GROUP BY
    # FIX 3: Replaced job_count alias in HAVING
    # FIX 4: Replaced LIMIT ? with LIMIT %s
    freq_query = f"""
        SELECT
            s.name,
            s.category,
            COUNT(DISTINCT js.job_id) AS job_count,
            COUNT(DISTINCT js.job_id) * 100.0 / (
                SELECT COUNT(DISTINCT id) FROM jobs
            ) AS frequency
        FROM skills s
        JOIN job_skills js ON js.skill_id = s.id
        WHERE 1=1 {cat_filter}
        GROUP BY s.name, s.category
        HAVING COUNT(DISTINCT js.job_id) >= 3
        ORDER BY COUNT(DISTINCT js.job_id) DESC
        LIMIT %s
    """

    # FIX 5: Split the cursor execution and convert params to a tuple
    with get_connection(dsn) as cursor:
        cursor.execute(freq_query, tuple(params + [top_n * 3]))
        rows = cursor.fetchall()

    scored: list[ScoredSkill] = []

    for row in rows:
        name = row["name"]
        trend = trend_map.get(name)

        sat_score = sat_scores.get(name, 0.0)

        # Trend momentum bonus: rising skills get investment bump
        if trend:
            direction = trend.direction
            delta = trend.delta_pct
            if direction == TrendDirection.RISING:
                momentum = min(delta / 100, 1.0)     # cap at 1.0
            elif direction == TrendDirection.FALLING:
                momentum = max(delta / 100, -1.0)    # floor at -1.0
            elif direction == TrendDirection.NEW:
                momentum = 0.5
            else:
                momentum = 0.0
        else:
            direction = TrendDirection.STABLE
            delta = 0.0
            momentum = 0.0

        # Investment score = saturation score adjusted by momentum
        investment_score = min(100, max(0, sat_score + momentum * 20))

        scored.append(ScoredSkill(
            name=name,
            category=row["category"],
            total_jobs=row["job_count"],
            frequency=round(row["frequency"], 1),
            trend_direction=direction.value,
            trend_delta=delta,
            saturation_score=sat_score,
            investment_score=round(investment_score, 1),
        ))

    # Sort by investment score
    scored.sort(key=lambda s: s.investment_score, reverse=True)
    return scored[:top_n]
