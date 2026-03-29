"""
src/api/main.py
────────────────
FastAPI application factory.

Key FastAPI concepts demonstrated here:

1. lifespan context manager (replaces deprecated @app.on_event)
   Code before `yield` runs on startup.
   Code after `yield` runs on shutdown.
   Used to: init DB, start scheduler, log config.

2. APIRouter
   Each route group (trends, skills, digest) is its own router module.
   We include them here with a prefix.
   This keeps route files focused and testable in isolation.

3. CORS middleware
   Allows the Streamlit dashboard (running on a different port)
   to call this API from the browser.

4. OpenAPI docs
   FastAPI auto-generates interactive docs at /docs (Swagger UI)
   and /redoc. Zero config needed — it reads your schemas + docstrings.
   This is massive for portfolio — interviewers can explore your API live.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings, setup_logging
from src.database import init_db
from src.api.routes import health, trends, skills, digest, ingest
from src.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown logic.
    Everything before yield = startup.
    Everything after yield = shutdown.
    """
    # ── Startup ──
    setup_logging()
    settings = get_settings()

    logger.info("Starting AI Skill Demand Tracker API...")
    logger.info(f"LLM provider: {settings.llm_provider} - Model: {settings.nvidia_model}")
    logger.info(f"Database: {(settings.db_path).split(':')[0]}")

    # Ensure DB and tables exist
    init_db(settings.db_path)

    # Start the APScheduler (daily pipeline runs)
    start_scheduler()
    logger.info("Scheduler started — pipeline will run daily at midnight IST")

    yield  # ← app runs here

    # ── Shutdown ──
    stop_scheduler()
    logger.info("Scheduler stopped. Goodbye.")


def create_app() -> FastAPI:
    """
    Application factory pattern.
    Returning the app from a function (vs module-level) makes it
    easier to test — you can create fresh app instances per test.
    """
    app = FastAPI(
        title="AI Skill Demand Tracker",
        description=(
            "Tracks real-time skill demand from job postings across HN, RemoteOK, and Arbeitnow. "
            "Provides trend analysis, co-occurrence graphs, segmentation, and LLM-generated digests."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ──
    # Allow any origin in development. Tighten this in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ──
    # Each router handles a logical group of endpoints.
    # prefix="/api/v1" means all routes become /api/v1/trends, etc.
    API_PREFIX = "/api/v1"

    app.include_router(health.router,  prefix=API_PREFIX)
    app.include_router(trends.router,  prefix=API_PREFIX)
    app.include_router(skills.router,  prefix=API_PREFIX)
    app.include_router(digest.router,  prefix=API_PREFIX)
    app.include_router(ingest.router,  prefix=API_PREFIX)

    # ── Root redirect to docs ──
    @app.get("/", include_in_schema=False)
    def root():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/docs")

    return app


# Module-level app instance — what uvicorn imports
app = create_app()
