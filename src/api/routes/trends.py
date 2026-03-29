"""
src/api/routes/trends.py
─────────────────────────
Trend endpoints.

GET /trends                        → all skill trends (WoW)
GET /trends?direction=rising       → filter by direction
GET /trends?category=ml_concept    → filter by category
GET /trends?seniority=senior       → filter by seniority

FastAPI concepts demonstrated here:
  - Query parameters with defaults (no URL path required)
  - Optional parameters (Optional[str] = None)
  - response_model enforces output schema automatically
  - Enum for query param validation
"""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from src.api.schemas import TrendsResponse, SkillTrendResponse
from src.analytics.trends import compute_trends, TrendDirection
from src.config import get_settings

router = APIRouter()


@router.get("/trends", response_model=TrendsResponse, tags=["analytics"])
def get_trends(
    direction: Optional[str] = Query(
        default=None,
        description="Filter by direction: rising | falling | stable | new | disappeared"
    ),
    category: Optional[str] = Query(
        default=None,
        description="Filter by skill category: language | framework | ml_concept | cloud | database | tool"
    ),
    seniority: Optional[str] = Query(
        default=None,
        description="Filter by seniority: junior | mid | senior | lead"
    ),
    min_jobs: int = Query(default=3, description="Minimum job count to include"),
    limit: int = Query(default=50, le=200),
):
    """
    Week-over-week skill trends.
    Requires at least 2 weeks of ingested data to show deltas.
    """
    settings = get_settings()

    # Validate direction if provided
    valid_directions = {d.value for d in TrendDirection}
    if direction and direction not in valid_directions:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid direction '{direction}'. Valid: {sorted(valid_directions)}"
        )

    trends = compute_trends(
        settings.db_path,
        min_jobs=min_jobs,
        seniority=seniority,
    )

    # Apply filters
    if direction:
        trends = [t for t in trends if t.direction.value == direction]
    if category:
        trends = [t for t in trends if t.category == category]

    # Keep only significant trends
    trends = [t for t in trends if t.is_significant][:limit]

    return TrendsResponse(
        trends=[
            SkillTrendResponse(
                name=t.name,
                category=t.category,
                current_count=t.current_count,
                previous_count=t.previous_count,
                current_freq=t.current_freq,
                previous_freq=t.previous_freq,
                delta_pct=t.delta_pct,
                direction=t.direction.value,
                weeks_present=t.weeks_present,
                momentum_label=t.momentum_label,
            )
            for t in trends
        ],
        total=len(trends),
        filters_applied={
            k: v for k, v in {
                "direction": direction,
                "category": category,
                "seniority": seniority,
            }.items() if v is not None
        },
    )
