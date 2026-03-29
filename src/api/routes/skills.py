"""
src/api/routes/skills.py
─────────────────────────
Skill-level endpoints.

GET /skills/{name}              → full detail for one skill
GET /skills/{name}/history      → weekly frequency history
GET /skills/{name}/neighbors    → co-occurring skills
GET /report                     → full ranked investment report
GET /cooccurrence               → skill pairs by lift score
GET /segments                   → skills broken down by seniority/role/source

FastAPI concept: Path parameters
  /skills/{name} — `name` is captured from the URL path.
  Contrast with query params: /trends?direction=rising
  Use path params for resource IDs, query params for filters.
"""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from src.api.schemas import (
    SkillDetailResponse, SkillHistoryPoint, SkillNeighbor,
    ReportResponse, ScoredSkillResponse,
    CooccurrenceResponse, SkillPairResponse,
    SegmentsResponse, SegmentSkillItem,
)

from src.analytics.scoring import build_skill_report
from src.analytics.trends import get_skill_history
from src.analytics.coocurrence import compute_cooccurrence, get_skill_neighbors
from src.analytics.segments import (
    get_skills_by_seniority, get_skills_by_role_category, 
    get_skills_by_source
)

from src.config import get_settings

router = APIRouter()


@router.get("/skills/{name}", response_model=SkillDetailResponse, tags=["skills"])
def get_skill_detail(
    name: str,
    history_weeks: int = Query(default=8, le=52),
    neighbor_count: int = Query(default=10, le=30),
):
    """
    Full detail for a single skill: weekly trend history, co-occurring
    skills, and breakdown by seniority/role/source.
    """
    settings = get_settings()

    history_raw = get_skill_history(settings.db_path, name, n_weeks=history_weeks)
    if not history_raw:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found in database.")

    neighbors_raw = get_skill_neighbors(settings.db_path, name, top_n=neighbor_count)

    from src.analytics.segments import compare_skill_across_segments
    segments = compare_skill_across_segments(settings.db_path, name)

    return SkillDetailResponse(
        name=name,
        history=[SkillHistoryPoint(**h) for h in history_raw],
        neighbors=[SkillNeighbor(**n) for n in neighbors_raw],
        segments=segments,
    )


@router.get("/skills/{name}/history", response_model=list[SkillHistoryPoint], tags=["skills"])
def get_skill_trend_history(
    name: str,
    weeks: int = Query(default=8, le=52),
):
    """Weekly job count and frequency for a single skill."""
    settings = get_settings()
    history = get_skill_history(settings.db_path, name, n_weeks=weeks)
    if not history:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found.")
    return [SkillHistoryPoint(**h) for h in history]


@router.get("/skills/{name}/neighbors", response_model=list[SkillNeighbor], tags=["skills"])
def get_skill_cooccurring(name: str, top_n: int = Query(default=10, le=30)):
    """Skills that most frequently appear alongside this skill."""
    settings = get_settings()
    neighbors = get_skill_neighbors(settings.db_path, name, top_n=top_n)
    if not neighbors:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found or has no neighbors.")
    return [SkillNeighbor(**n) for n in neighbors]


@router.get("/report", response_model=ReportResponse, tags=["analytics"])
def get_skill_report(
    limit: int = Query(default=30, le=100),
    category: Optional[str] = Query(default=None),
):
    """
    Full ranked skill investment report.
    Combines frequency + trend momentum + saturation into one investment score.
    """
    settings = get_settings()
    skills = build_skill_report(settings.db_path, top_n=limit, category=category)

    return ReportResponse(
        skills=[
            ScoredSkillResponse(
                rank=i + 1,
                name=s.name,
                category=s.category,
                total_jobs=s.total_jobs,
                frequency=s.frequency,
                trend_direction=s.trend_direction,
                trend_delta=s.trend_delta,
                investment_score=s.investment_score,
                investment_label=s.investment_label,
            )
            for i, s in enumerate(skills)
        ],
        total=len(skills),
        category_filter=category,
    )


@router.get("/cooccurrence", response_model=CooccurrenceResponse, tags=["analytics"])
def get_cooccurrence(
    limit: int = Query(default=30, le=100),
    min_lift: float = Query(default=1.2),
    category: Optional[str] = Query(default=None),
):
    """
    Skill pairs that co-occur more than expected by chance.
    Lift > 2.0 = strong association (appear together 2× more than random).
    """
    settings = get_settings()
    pairs = compute_cooccurrence(
        settings.db_path,
        top_n=limit,
        min_lift=min_lift,
        category_filter=category,
    )

    return CooccurrenceResponse(
        pairs=[
            SkillPairResponse(
                skill_a=p.skill_a,
                skill_b=p.skill_b,
                co_occurrence_count=p.co_occurrence_count,
                support=p.support,
                confidence_a_to_b=p.confidence_a_to_b,
                confidence_b_to_a=p.confidence_b_to_a,
                lift=p.lift,
                strength_label=p.strength_label,
            )
            for p in pairs
        ],
        total=len(pairs),
    )


@router.get("/segments", response_model=SegmentsResponse, tags=["analytics"])
def get_segments(
    by: str = Query(
        default="seniority",
        description="Segment dimension: seniority | role | source"
    ),
    limit: int = Query(default=10, le=30),
):
    """
    Break down skill demand by a dimension.
    by=seniority → junior vs mid vs senior requirements
    by=role      → AI Engineer vs Data Scientist vs Backend
    by=source    → HN vs RemoteOK vs Arbeitnow
    """
    settings = get_settings()

    valid_bys = {"seniority", "role", "source"}
    if by not in valid_bys:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid 'by' value '{by}'. Valid: {sorted(valid_bys)}"
        )

    if by == "seniority":
        raw = get_skills_by_seniority(settings.db_path, top_n=limit)
    elif by == "role":
        raw = get_skills_by_role_category(settings.db_path, top_n=limit)
    else:
        raw = get_skills_by_source(settings.db_path, top_n=limit)

    return SegmentsResponse(
        segment_by=by,
        data={
            seg: [SegmentSkillItem(**item) for item in items]
            for seg, items in raw.items()
        },
    )
