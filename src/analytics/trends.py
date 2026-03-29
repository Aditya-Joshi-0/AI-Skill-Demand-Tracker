"""
src/analytics/trends.py
────────────────────────
Core trend engine: computes week-over-week skill frequency changes.

Key concepts:
  - We split fetched_at into weekly buckets
  - For each skill, count how many jobs required it per week
  - Compare current week vs previous week → delta %
  - Classify as RISING / FALLING / STABLE / NEW / DISAPPEARED

Why fetched_at and not posted_at?
  posted_at is noisy — a company might post a job in week 1 but we
  fetch it in week 3. fetched_at is our consistent, reliable time axis.

Why relative frequency (% of jobs) not raw count?
  If we fetched 100 jobs one week and 200 the next, raw counts would
  make everything look like it doubled. Relative frequency normalises
  for volume differences between runs.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from enum import Enum
from typing import Optional

from src.database import get_connection
from src.config import get_settings

logger = logging.getLogger(__name__)


# ─── Trend Direction ──────────────────────────────────────────────────────────

class TrendDirection(str, Enum):
    RISING      = "rising"       # up > 10% week-over-week
    FALLING     = "falling"      # down > 10% week-over-week
    STABLE      = "stable"       # within ±10%
    NEW         = "new"          # appeared this week, absent last week
    DISAPPEARED = "disappeared"  # was there last week, gone this week


@dataclass
class SkillTrend:
    """Trend data for a single skill."""
    name: str
    category: str
    current_count: int          # jobs mentioning this skill this week
    previous_count: int         # jobs mentioning this skill last week
    current_freq: float         # % of this week's jobs mentioning it
    previous_freq: float        # % of last week's jobs mentioning it
    delta_pct: float            # (current_freq - previous_freq) / previous_freq * 100
    direction: TrendDirection
    weeks_present: int          # how many consecutive weeks it's appeared

    @property
    def is_significant(self) -> bool:
        """Only show trends with enough data points to be meaningful."""
        return self.current_count >= 3

    @property
    def momentum_label(self) -> str:
        if self.direction == TrendDirection.RISING:
            if self.delta_pct > 50:
                return "🔥 surging"
            return "↑ rising"
        if self.direction == TrendDirection.FALLING:
            if self.delta_pct < -50:
                return "↓↓ dropping fast"
            return "↓ falling"
        if self.direction == TrendDirection.NEW:
            return "✨ new"
        if self.direction == TrendDirection.DISAPPEARED:
            return "— gone"
        return "→ stable"


@dataclass
class WeeklySnapshot:
    """Aggregated skill counts for a single week."""
    week_start: datetime        # Monday of the week
    total_jobs: int
    skill_counts: dict[str, int]   # skill_name → job count

    def frequency(self, skill_name: str) -> float:
        """Relative frequency: what % of this week's jobs mention this skill."""
        if self.total_jobs == 0:
            return 0.0
        return self.skill_counts.get(skill_name, 0) / self.total_jobs * 100


# ─── Data Fetching ────────────────────────────────────────────────────────────

from datetime import datetime, timezone
from typing import Optional
import logging

# Assuming WeeklySnapshot and get_connection are imported at the top of the file
# from src.models import WeeklySnapshot
# from src.database import get_connection

logger = logging.getLogger(__name__)

def _get_weekly_snapshots(
    dsn: str,  # Swapped db_path for dsn
    n_weeks: int = 4,
    seniority: Optional[str] = None,
    role_category: Optional[str] = None,
    source: Optional[str] = None,
) -> list[WeeklySnapshot]:
    """
    Pull skill counts grouped by week from the Postgres DB.

    Returns the last n_weeks weeks in chronological order (oldest first).
    Applies optional filters for segmentation.
    """
    filters = []
    params: list = []

    # 1. FIX: Changed ? to %s
    if seniority:
        filters.append("j.seniority = %s")
        params.append(seniority)
    if role_category:
        filters.append("j.role_category LIKE %s")
        params.append(f"%{role_category}%")
    if source:
        filters.append("j.source = %s")
        params.append(source)

    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

    # 2. FIX: Replaced SQLite DATE() math with Postgres date_trunc('week', ...)
    # 3. FIX: Added s.category to the GROUP BY clause
    query = f"""
        SELECT
            DATE(date_trunc('week', j.fetched_at))       AS week_start,
            s.name                                       AS skill_name,
            s.category                                   AS skill_category,
            COUNT(DISTINCT j.id)                         AS job_count
        FROM jobs j
        JOIN job_skills js ON js.job_id = j.id
        JOIN skills s      ON s.id      = js.skill_id
        {where_clause}
        GROUP BY DATE(date_trunc('week', j.fetched_at)), s.name, s.category
        ORDER BY week_start ASC
    """

    total_query = f"""
        SELECT
            DATE(date_trunc('week', j.fetched_at))       AS week_start,
            COUNT(DISTINCT j.id)                         AS total_jobs
        FROM jobs j
        {where_clause}
        GROUP BY DATE(date_trunc('week', j.fetched_at))
        ORDER BY week_start ASC
    """

    # 4. FIX: Use the cursor yielded by the context manager, and split execute/fetchall
    with get_connection(dsn) as cursor:
        cursor.execute(query, tuple(params)) # Psycopg2 prefers tuples for params
        skill_rows = cursor.fetchall()
        
        cursor.execute(total_query, tuple(params))
        total_rows = cursor.fetchall()

    if not total_rows:
        return []

    # Build total jobs per week dict (converting the date object to a string for the dict key)
    totals: dict[str, int] = {str(row["week_start"]): row["total_jobs"] for row in total_rows}

    # Group skill counts by week
    weeks: dict[str, dict[str, int]] = {}
    for row in skill_rows:
        week = str(row["week_start"])
        if week not in weeks:
            weeks[week] = {}
        weeks[week][row["skill_name"]] = row["job_count"]

    # Build WeeklySnapshot objects, sorted by date, take last n_weeks
    snapshots = []
    for week_str in sorted(totals.keys()):
        try:
            week_dt = datetime.strptime(week_str, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        except Exception as e:
            logger.warning(f"Could not parse week_str {week_str}: {e}")
            continue
        
        snapshots.append(WeeklySnapshot(
            week_start=week_dt,
            total_jobs=totals[week_str],
            skill_counts=weeks.get(week_str, {}),
        ))

    return snapshots[-n_weeks:]

# ─── Trend Calculation ────────────────────────────────────────────────────────

def _classify_direction(
    current_freq: float,
    previous_freq: float,
    delta_pct: float,
) -> TrendDirection:
    if previous_freq == 0 and current_freq > 0:
        return TrendDirection.NEW
    if current_freq == 0 and previous_freq > 0:
        return TrendDirection.DISAPPEARED
    if delta_pct > 10:
        return TrendDirection.RISING
    if delta_pct < -10:
        return TrendDirection.FALLING
    return TrendDirection.STABLE


def compute_trends(
    db_path: str,
    min_jobs: int = 3,
    seniority: Optional[str] = None,
    role_category: Optional[str] = None,
    source: Optional[str] = None,
) -> list[SkillTrend]:
    """
    Compute week-over-week trends for all skills.

    Args:
        db_path:       Path to SQLite DB
        min_jobs:      Minimum job count to include (filters noise)
        seniority:     Filter to a seniority level
        role_category: Filter by role type substring
        source:        Filter to a specific job board

    Returns:
        List of SkillTrend objects, sorted by |delta_pct| descending.
    """
    snapshots = _get_weekly_snapshots(
        db_path, n_weeks=4,
        seniority=seniority,
        role_category=role_category,
        source=source,
    )

    if len(snapshots) < 1:
        logger.warning("Not enough weekly data for trend analysis. Run ingest.py more days.")
        return []

    current  = snapshots[-1]
    previous = snapshots[-2] if len(snapshots) >= 2 else None

    # All skills seen in current week
    all_skills = set(current.skill_counts.keys())
    if previous:
        all_skills |= set(previous.skill_counts.keys())

    trends: list[SkillTrend] = []

    for skill_name in all_skills:
        curr_count = current.skill_counts.get(skill_name, 0)
        prev_count = previous.skill_counts.get(skill_name, 0) if previous else 0

        # Skip low-signal skills
        if curr_count < min_jobs and prev_count < min_jobs:
            continue

        curr_freq = current.frequency(skill_name)
        prev_freq = previous.frequency(skill_name) if previous else 0.0

        # Calculate delta %
        if prev_freq > 0:
            delta_pct = (curr_freq - prev_freq) / prev_freq * 100
        elif curr_freq > 0:
            delta_pct = 100.0   # new skill → treat as 100% increase
        else:
            delta_pct = 0.0

        direction = _classify_direction(curr_freq, prev_freq, delta_pct)

        # Count how many of the last 4 weeks this skill appeared
        weeks_present = sum(
            1 for snap in snapshots
            if skill_name in snap.skill_counts
        )

        # Get category from DB (we need it for display)
        category = _get_skill_category(db_path, skill_name)

        trends.append(SkillTrend(
            name=skill_name,
            category=category,
            current_count=curr_count,
            previous_count=prev_count,
            current_freq=round(curr_freq, 2),
            previous_freq=round(prev_freq, 2),
            delta_pct=round(delta_pct, 1),
            direction=direction,
            weeks_present=weeks_present,
        ))

    # Sort by absolute delta descending (most movement at top)
    trends.sort(key=lambda t: abs(t.delta_pct), reverse=True)
    return trends


def _get_skill_category(db_path: str, skill_name: str) -> str:
    with get_connection(db_path) as conn:
        conn.execute(
            "SELECT category FROM skills WHERE name = %s", (skill_name,)
        )
        row = conn.fetchone()
    return row["category"] if row else "other"


# ─── Single Skill History ─────────────────────────────────────────────────────

def get_skill_history(db_path: str, skill_name: str, n_weeks: int = 8) -> list[dict]:
    """
    Full weekly history for a single skill.
    Used by the dashboard to draw a sparkline.

    Returns list of {week_start, job_count, frequency} dicts.
    """
    snapshots = _get_weekly_snapshots(db_path, n_weeks=n_weeks)
    history = []
    for snap in snapshots:
        history.append({
            "week_start": snap.week_start.strftime("%Y-%m-%d"),
            "job_count": snap.skill_counts.get(skill_name, 0),
            "frequency": round(snap.frequency(skill_name), 2),
            "total_jobs": snap.total_jobs,
        })
    return history
