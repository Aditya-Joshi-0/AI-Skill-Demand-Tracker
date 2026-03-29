"""
src/api/routes/health.py
─────────────────────────
Health check endpoint. Always implement this — it's how:
  - Docker healthchecks know the container is ready
  - Load balancers know to send traffic
  - Monitoring systems know the service is alive

GET /health → HealthResponse
"""

from fastapi import APIRouter
from src.api.schemas import HealthResponse
from src.database import get_stats
from src.config import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health_check():
    """Service health check. Returns DB stats."""
    settings = get_settings()
    try:
        stats = get_stats(settings.db_path)
        return HealthResponse(
            status="ok",
            db_path=settings.db_path,
            total_jobs=stats["total_jobs"],
            unique_skills=stats["unique_skills"],
            latest_fetch=stats.get("latest_fetch"),
        )
    except Exception as e:
        return HealthResponse(
            status=f"degraded: {e}",
            db_path=settings.db_path,
            total_jobs=0,
            unique_skills=0,
            latest_fetch=None,
        )
