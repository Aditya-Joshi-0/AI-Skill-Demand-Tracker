"""
seed_test_data.py
──────────────────
Injects synthetic job data spanning 3 weeks into the DB so you can
test ALL analytics commands immediately — without waiting weeks for
real data to accumulate.

This is NOT cheating. It's good engineering practice:
  - Lets you validate your analytics logic against known data
  - You know exactly what trends SHOULD appear → easy to verify correctness
  - Standard practice for testing time-series pipelines

Run with:
    python seed_test_data.py
    python analyse.py trending
    python analyse.py report
    python analyse.py skill "Python"
    python analyse.py cooccurrence
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import random

sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_settings, setup_logging
from src.database import init_db, get_connection
from rich.console import Console
from rich.progress import track

console = Console()

# ─── Synthetic skill profiles ─────────────────────────────────────────────────
# Format: (skill_name, category, base_weight, trend)
# trend: "rising" | "falling" | "stable" | "new"
# base_weight = probability of appearing in a job (0–1)

SKILL_PROFILES = [
    # Languages
    ("Python",       "language",   0.85, "stable"),
    ("TypeScript",   "language",   0.45, "rising"),
    ("Go",           "language",   0.30, "rising"),
    ("Rust",         "language",   0.15, "rising"),
    ("Java",         "language",   0.35, "falling"),
    ("Scala",        "language",   0.10, "falling"),
    ("R",            "language",   0.12, "falling"),

    # Frameworks
    ("FastAPI",      "framework",  0.50, "rising"),
    ("LangChain",    "framework",  0.45, "rising"),
    ("LangGraph",    "framework",  0.20, "rising"),
    ("PyTorch",      "framework",  0.55, "stable"),
    ("TensorFlow",   "framework",  0.30, "falling"),
    ("Django",       "framework",  0.25, "stable"),
    ("React",        "framework",  0.35, "stable"),
    ("Hugging Face", "framework",  0.40, "rising"),

    # ML Concepts
    ("RAG",              "ml_concept", 0.55, "rising"),
    ("Fine-tuning",      "ml_concept", 0.40, "rising"),
    ("LLM",              "ml_concept", 0.70, "rising"),
    ("Transformers",     "ml_concept", 0.45, "stable"),
    ("Embeddings",       "ml_concept", 0.50, "rising"),
    ("RLHF",             "ml_concept", 0.20, "rising"),
    ("Computer Vision",  "ml_concept", 0.25, "stable"),
    ("NLP",              "ml_concept", 0.35, "stable"),
    ("Prompt Engineering","ml_concept",0.40, "rising"),
    ("MLOps",            "ml_concept", 0.30, "stable"),
    ("MCP",              "ml_concept", 0.05, "new"),    # new this week

    # Cloud
    ("AWS",          "cloud",      0.60, "stable"),
    ("GCP",          "cloud",      0.35, "stable"),
    ("Azure",        "cloud",      0.30, "stable"),
    ("Kubernetes",   "cloud",      0.40, "stable"),
    ("Docker",       "cloud",      0.65, "stable"),
    ("Terraform",    "cloud",      0.20, "rising"),

    # Databases
    ("PostgreSQL",   "database",   0.55, "stable"),
    ("ChromaDB",     "database",   0.30, "rising"),
    ("Pinecone",     "database",   0.25, "rising"),
    ("Redis",        "database",   0.30, "stable"),
    ("MongoDB",      "database",   0.20, "falling"),
    ("Weaviate",     "database",   0.15, "rising"),
]

# Role categories and their seniority distributions
ROLE_CONFIGS = [
    ("AI/ML Engineer",     {"junior": 0.1, "mid": 0.35, "senior": 0.45, "lead": 0.1}),
    ("Data Scientist",     {"junior": 0.15, "mid": 0.40, "senior": 0.35, "lead": 0.1}),
    ("Backend Engineer",   {"junior": 0.2, "mid": 0.45, "senior": 0.30, "lead": 0.05}),
    ("DevOps Engineer",    {"junior": 0.1, "mid": 0.40, "senior": 0.40, "lead": 0.1}),
    ("Full Stack Engineer",{"junior": 0.25, "mid": 0.45, "senior": 0.25, "lead": 0.05}),
]

SOURCES = ["hackernews", "remoteok", "arbeitnow"]

COMPANIES = [
    "Anthropic", "OpenAI", "Mistral AI", "Cohere", "Hugging Face",
    "Stripe", "Linear", "Notion", "Figma", "Vercel", "Fly.io",
    "Scale AI", "Weights & Biases", "Modal", "Replicate",
    "DataBricks", "Snowflake", "dbt Labs", "Airbyte", "Fivetran",
    "Cloudflare", "Supabase", "PlanetScale", "Neon", "TurboRepo",
]


def _week_ago(n_weeks: int) -> datetime:
    """Return a datetime n_weeks ago, with some random day offset within the week."""
    base = datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(weeks=n_weeks)
    return base + timedelta(days=random.randint(0, 6), hours=random.randint(0, 23))


def _weighted_choice(items, weights):
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0
    for item, weight in zip(items, weights):
        cumulative += weight
        if r <= cumulative:
            return item
    return items[-1]


def _get_skill_weight(profile: tuple, week: int, n_weeks: int = 3) -> float:
    """
    Adjust skill weight based on trend direction and week.
    week=0 is oldest, week=n_weeks-1 is most recent.
    """
    name, cat, base_weight, trend = profile
    progress = week / max(n_weeks - 1, 1)   # 0.0 → 1.0

    if trend == "rising":
        return base_weight * (0.6 + 0.7 * progress)
    elif trend == "falling":
        return base_weight * (1.4 - 0.7 * progress)
    elif trend == "new":
        return base_weight if week == n_weeks - 1 else 0.0
    else:
        return base_weight


def _pick_skills_for_job(week: int, n_weeks: int, role: str) -> list[tuple[str, str, bool]]:
    """
    Pick a realistic set of skills for a job, weighted by trend.
    Returns list of (skill_name, category, is_required).
    """
    skills = []
    # Each job gets 5-12 skills
    for profile in SKILL_PROFILES:
        w = _get_skill_weight(profile, week, n_weeks)
        if random.random() < w * 0.7:   # scale down to get realistic counts
            is_required = random.random() > 0.2  # 80% required
            skills.append((profile[0], profile[1], is_required))
    return skills[:15]  # cap at 15


def seed_data(n_weeks: int = 3, jobs_per_week: int = 60):
    """
    Inject synthetic jobs across n_weeks.
    """
    settings = get_settings()
    db_path = settings.db_path
    init_db(db_path)

    total_jobs = n_weeks * jobs_per_week
    console.print(f"\n[bold]Seeding {total_jobs} synthetic jobs across {n_weeks} weeks...[/bold]")
    console.print(f"[dim]DB: {db_path}[/dim]\n")

    inserted = 0
    skipped = 0

    with get_connection(db_path) as conn:
        for week_idx in track(range(n_weeks), description="Generating weeks..."):
            for job_i in range(jobs_per_week):
                # Pick role and seniority
                role_name, seniority_dist = random.choice(ROLE_CONFIGS)
                seniority = _weighted_choice(
                    list(seniority_dist.keys()),
                    list(seniority_dist.values()),
                )
                source = random.choice(SOURCES)
                company = random.choice(COMPANIES)
                posted_at = _week_ago(n_weeks - week_idx - 1)
                source_id = f"seed_{week_idx}_{job_i}_{random.randint(10000, 99999)}"

                # Insert job
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs
                        (source, source_id, title, company, url, location,
                         is_remote, job_type, seniority, role_category, posted_at, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source,
                        source_id,
                        f"{seniority.title()} {role_name}",
                        company,
                        f"https://example.com/jobs/{source_id}",
                        "Remote",
                        1,
                        "full_time",
                        seniority,
                        role_name,
                        posted_at.isoformat(),
                        posted_at.isoformat(),   # fetched_at = posted_at for seed data
                    ),
                )

                if cursor.rowcount == 0:
                    skipped += 1
                    continue

                job_db_id = cursor.lastrowid
                inserted += 1

                # Insert skills
                for skill_name, skill_cat, is_required in _pick_skills_for_job(
                    week_idx, n_weeks, role_name
                ):
                    conn.execute(
                        "INSERT OR IGNORE INTO skills (name, category) VALUES (%s, %s)",
                        (skill_name, skill_cat),
                    )
                    skill_row = conn.execute(
                        "SELECT id FROM skills WHERE name = %s", (skill_name,)
                    ).fetchone()
                    if skill_row:
                        conn.execute(
                            "INSERT OR IGNORE INTO job_skills (job_id, skill_id, is_required) VALUES (%s, %s, %s)",
                            (job_db_id, skill_row["id"], 1 if is_required else 0),
                        )

    console.print(f"\n[green]✓ Seeded {inserted} new jobs ({skipped} skipped as duplicates)[/green]")
    console.print("\nYou can now run:")
    console.print("  [cyan]python analyse.py trending[/cyan]")
    console.print("  [cyan]python analyse.py report[/cyan]")
    console.print("  [cyan]python analyse.py skill Python[/cyan]")
    console.print("  [cyan]python analyse.py cooccurrence[/cyan]")
    console.print("  [cyan]python analyse.py segments --by seniority[/cyan]")


if __name__ == "__main__":
    setup_logging()
    seed_data(n_weeks=3, jobs_per_week=60)
