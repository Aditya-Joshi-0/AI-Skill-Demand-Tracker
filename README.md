---
title: AI Skill Demand Tracker Dashboard
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# AI Skill Demand Tracker — Phase 1: Data Pipeline

> Fetch job posts from 3 live sources → LLM extracts skills → stored in SQLite time-series DB.

---

## Architecture

```
┌──────────────┐  ┌──────────────┐  ┌───────────────┐
│  HN Algolia  │  │  RemoteOK    │  │   Arbeitnow   │   ← 3 free APIs, no auth
└──────┬───────┘  └──────┬───────┘  └───────┬───────┘
       │                 │                  │
       └─────────────────┴──────────────────┘
                         │  asyncio.gather() — runs all 3 concurrently
                         ▼
               ┌──────────────────┐
               │  RawJobPost[]    │   Pydantic-validated, HTML-stripped
               └────────┬─────────┘
                        │
                        ▼
               ┌──────────────────────────────────┐
               │  SkillExtractor (LLM)             │
               │  gpt-4o-mini / claude-haiku       │
               │  Batches of 5 → structured output │
               └────────┬─────────────────────────┘
                        │  ExtractedSkills (Pydantic)
                        ▼
               ┌──────────────────┐
               │  SQLite DB       │
               │  jobs            │
               │  skills          │   ← normalised, deduplicated
               │  job_skills      │   ← join table for trend queries
               └──────────────────┘
```

---

## Setup

```bash
# 1. Create virtualenv
python -m venv venv
source venv/bin/activate       # Linux/Mac
# venv\Scripts\activate        # Windows

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env: add OPENAI_API_KEY (and/or ANTHROPIC_API_KEY)

# 4. Run
python ingest.py
```

---

## CLI Commands

```bash
# Fetch from all 3 sources
python ingest.py

# Single source (good for testing)
python ingest.py --source hackernews
python ingest.py --source remoteok
python ingest.py --source arbeitnow

# Limit jobs (cheap LLM testing)
python ingest.py --max-jobs 10

# Multiple sources
python ingest.py --source hackernews --source remoteok

# Check DB health
python ingest.py --stats

# See top trending skills (last 7 days)
python ingest.py --top-skills

# Top skills over last 30 days
python ingest.py --top-skills --days 30
```

---

## Project Structure

```
skill-tracker/
├── .env.example
├── requirements.txt
├── ingest.py              ← CLI entry point
│
└── src/
    ├── config.py          ← settings + get_llm() factory
    ├── models.py          ← all Pydantic models (RawJobPost, ExtractedSkills...)
    ├── database.py        ← SQLite schema + read/write operations
    ├── extractor.py       ← LLM skill extraction with structured output
    ├── pipeline.py        ← orchestrates everything
    └── fetchers/
        ├── base.py        ← abstract BaseFetcher
        ├── hn.py          ← Hacker News Algolia API
        ├── remoteok.py    ← RemoteOK public API
        └── arbeitnow.py   ← Arbeitnow public API
```

---

## Key Learning Points

| File | Concept |
|---|---|
| `pipeline.py` | `asyncio.gather()` — concurrent fetching |
| `extractor.py` | `with_structured_output()` — LLM → Pydantic |
| `database.py` | 3NF schema design for time-series queries |
| `models.py` | Pydantic validators + enums |
| `fetchers/base.py` | Abstract base class pattern |

---

## Phase 2 Preview: Analytics Engine

Once you have data, Phase 2 adds:
- Week-over-week trend detection (rising / falling / stable per skill)
- Skill co-occurrence graph (which skills always appear together)
- Saturation score (high demand but too many candidates)
- Segmentation: by seniority, role type, remote vs onsite

```bash
# Phase 2 CLI (coming soon)
python analyse.py --trending          # top rising skills this week
python analyse.py --skill "LangChain" # full trend history for one skill
python analyse.py --co-occurrence     # skill pairing graph
```

---

## Estimated LLM Cost

With `gpt-4o-mini` and default settings (50 jobs per source, batch size 5):
- ~150 jobs × ~500 tokens each = ~75k tokens input per run
- ~150 jobs × ~200 tokens output = ~30k tokens output
- Total: ~$0.03–0.05 per daily run

With `claude-haiku`: slightly cheaper, similar quality for extraction tasks.
