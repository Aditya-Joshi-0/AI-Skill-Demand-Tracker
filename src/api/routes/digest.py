"""
src/api/routes/digest.py
─────────────────────────
GET /digest → LLM-generated narrative summary of the week's skill trends.

This is the endpoint that makes the project feel like a real product.
Instead of raw numbers, it returns a readable market intelligence brief
that a hiring manager or developer could subscribe to weekly.

Key concept: using LLMs for narrative generation on top of structured data.
The LLM doesn't do the analysis — the analytics engine does.
The LLM only converts structured results into readable prose.
This is the right division of responsibility.
"""

import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from langchain_classic.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.api.schemas import DigestResponse
from src.analytics.trends import compute_trends, TrendDirection
from src.analytics.scoring import build_skill_report
from src.database import get_stats
from src.config import get_settings, get_llm

logger = logging.getLogger(__name__)
router = APIRouter()

DIGEST_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a senior tech talent market analyst. "
        "Write a concise, insightful weekly digest (3-4 paragraphs) about AI/tech skill demand trends. "
        "Be specific, mention actual skills and percentages. "
        "Tone: professional but readable, like a good industry newsletter. "
        "Focus on what developers should actually DO with this information."
    ),
    (
        "human",
        """Write this week's skill demand digest based on the following data:

RISING SKILLS (week-over-week):
{rising}

FALLING SKILLS:
{falling}

TOP SKILLS BY JOB COUNT:
{top_skills}

NEW SKILLS (appeared this week):
{new_skills}

Total jobs analysed: {total_jobs}
Period: {period}

Write a 3-4 paragraph narrative digest. End with one actionable recommendation."""
    ),
])


@router.get("/digest", response_model=DigestResponse, tags=["analytics"])
def get_weekly_digest():
    """
    LLM-generated weekly market intelligence digest.
    Summarises skill trends into readable narrative prose.
    """
    settings = get_settings()
    db_path = settings.db_path

    # Gather structured data
    trends = compute_trends(db_path)
    report = build_skill_report(db_path, top_n=10)
    stats  = get_stats(db_path)

    rising  = [t for t in trends if t.direction == TrendDirection.RISING and t.is_significant][:8]
    falling = [t for t in trends if t.direction == TrendDirection.FALLING and t.is_significant][:5]
    new     = [t for t in trends if t.direction == TrendDirection.NEW][:5]

    # Format for prompt
    def fmt_trend(t):
        return f"- {t.name} ({t.category}): {t.delta_pct:+.0f}% WoW, {t.current_count} jobs"

    rising_txt  = "\n".join(fmt_trend(t) for t in rising)  or "No significant rising skills this week."
    falling_txt = "\n".join(fmt_trend(t) for t in falling) or "No significant falling skills."
    new_txt     = "\n".join(f"- {t.name}" for t in new)    or "No new skills detected."
    top_txt     = "\n".join(
        f"- {s.name}: {s.total_jobs} jobs ({s.frequency:.1f}% of postings)"
        for s in report[:8]
    )

    period = f"Week of {datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%B %d, %Y')}"

    # Generate narrative with LLM
    try:
        chain = DIGEST_PROMPT | get_llm() | StrOutputParser()
        narrative = chain.invoke({
            "rising":     rising_txt,
            "falling":    falling_txt,
            "top_skills": top_txt,
            "new_skills": new_txt,
            "total_jobs": stats["total_jobs"],
            "period":     period,
        })
    except Exception as e:
        logger.error(f"LLM digest generation failed: {e}")
        narrative = (
            f"Digest generation unavailable. "
            f"Top skills this week: {', '.join(s.name for s in report[:5])}."
        )

    return DigestResponse(
        generated_at=datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        period=period,
        narrative=narrative,
        top_rising=[t.name for t in rising],
        top_falling=[t.name for t in falling],
        top_skills=[s.name for s in report[:10]],
        new_skills=[t.name for t in new],
        total_jobs_analysed=stats["total_jobs"],
    )
