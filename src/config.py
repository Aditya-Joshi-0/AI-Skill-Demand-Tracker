"""
config.py
─────────
Centralised settings loaded from .env.
get_llm() returns the right LangChain model based on LLM_PROVIDER.

We use gpt-4o-mini / claude-haiku here (not the big models) because:
  - Skill extraction is a simple structured task, not complex reasoning
  - We'll call this hundreds of times per run — cost matters
  - Haiku / mini are fast enough to not bottleneck the pipeline
"""

import os
import logging
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger(__name__)


class Settings(BaseModel):
    llm_provider: str = ""  # "openai", "anthropic", or "nvidia"
    nvidia_api_key: str = ""
    nvidia_model: str = ""

    openai_api_key: str = ""
    openai_model: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = ""

    db_path: str = ""
    max_jobs_per_source: int = 25 
    extraction_batch_size: int = 5
    log_level: str = "INFO"

    model_config = {"extra": "ignore"}

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", ""),
            nvidia_api_key=os.getenv("NVIDIA_API_KEY", ""),
            nvidia_model=os.getenv("NVIDIA_MODEL", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", ""),
            db_path=os.getenv("DB_PATH", ""),
            max_jobs_per_source=int(os.getenv("MAX_JOBS_PER_SOURCE", "25")),
            extraction_batch_size=int(os.getenv("EXTRACTION_BATCH_SIZE", "5")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def get_llm():
    """
    Factory: returns the right LangChain chat model.
    Swap LLM_PROVIDER in .env to switch providers instantly.
    """
    s = get_settings()
    if s.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=s.anthropic_model,
            api_key=s.anthropic_api_key,
            temperature=0,
            max_tokens=1024,
        )
    elif s.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=s.openai_model,
            api_key=s.openai_api_key,
            temperature=0,
            max_tokens=1024,
        )
    else:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        return ChatNVIDIA(
            model=s.nvidia_model,
            api_key=s.nvidia_api_key,
            temperature=0,
            max_tokens=1024,
        )


def setup_logging():
    s = get_settings()
    logging.basicConfig(
        level=getattr(logging, s.log_level, logging.INFO),
        format="%(asctime)s | %(name)-20s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
