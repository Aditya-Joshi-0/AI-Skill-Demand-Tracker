# AI Skill Demand Tracker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An end-to-end data pipeline and analysis platform that tracks the demand for skills in the AI and tech job market. This project automatically ingests job postings from multiple sources, uses Large Language Models (LLMs) to extract key skills, and provides a dashboard and API for trend analysis.

## Features

- **Automated Data Ingestion**: Fetches job postings from Hacker News, RemoteOK, and Arbeitnow concurrently.
- **LLM-Powered Skill Extraction**: Uses ChatGPT or Claude to accurately extract skills from unstructured job descriptions.
- **Time-Series Database**: Stores skill data in a normalized PostGreSQL database for historical trend analysis.
- **Interactive Dashboard**: A Streamlit application to visualize skill trends, co-occurrence, and other insights.
- **REST API**: A FastAPI backend to programmatically access the skill trend data.
- **CLI Interface**: A command-line interface to control the ingestion process and get quick insights.

## Architecture

```
┌──────────────┐  ┌──────────────┐  ┌───────────────┐
│  HN Algolia  │  │  RemoteOK    │  │   Arbeitnow   │
└──────┬───────┘  └──────┬───────┘  └───────┬───────┘
       │                 │                  │
       └─────────────────┴──────────────────┘
                         │  asyncio.gather()
                         ▼
               ┌──────────────────┐
               │  RawJobPost[]    │
               └────────┬─────────┘
                        │
                        ▼
               ┌──────────────────────────────────┐
               │  SkillExtractor (LLM)             │
               │  (gpt-4o-mini / claude-haiku)     │
               └────────┬─────────────────────────┘
                        │  ExtractedSkills
                        ▼
               ┌──────────────────┐
               │  SQLite DB       │
               └──────────────────┘
```

## Technology Stack

- **Backend**: Python, FastAPI, Uvicorn
- **Database**: PostgreSQL
- **Data Processing**: Pandas
- **LLM Integration**: LangChain
- **Dashboard**: Streamlit
- **Visualization**: Plotly, NetworkX
- **CLI**: Typer, Rich
- **Containerization**: Docker

## Getting Started

### Prerequisites

- Python 3.11+
- An API key from OpenAI or Anthropic

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/AI-Skill-Demand-Tracker.git
    cd AI-Skill-Demand-Tracker
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Configure your API keys:**
    ```bash
    cp .env.example .env
    ```
    Now, edit the `.env` file to add your `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

## Usage

### Command-Line Interface

The CLI allows you to control the data ingestion pipeline and get quick insights from the database.

-   **Fetch jobs from all sources:**
    ```bash
    python ingest.py
    ```

-   **Fetch from a single source:**
    ```bash
    python ingest.py --source hackernews
    ```

-   **Limit the number of jobs to fetch:**
    ```bash
    python ingest.py --max-jobs 10
    ```

-   **Check database statistics:**
    ```bash
    python ingest.py --stats
    ```

-   **View top trending skills:**
    ```bash
    python ingest.py --top-skills --days 30
    ```

### API

The project includes a FastAPI server to expose the data through a REST API.

-   **Run the API server:**
    ```bash
    uvicorn src.api.main:app --reload
    ```
    The API will be available at `http://127.0.0.1:8000`.

-   **API Endpoints:**
    -   `GET /api/health`: Health check endpoint.
    -   `POST /api/ingest`: Trigger the data ingestion pipeline.
    -   `GET /api/skills`: Get a list of all skills.
    -   `GET /api/skills/{skill_id}`: Get details for a specific skill.
    -   `GET /api/trends/top`: Get the top trending skills.
    -   `GET /api/digest`: Get a summary digest of skill trends.

### Dashboard

The interactive dashboard provides a user-friendly way to explore the skill trend data.

-   **Run the Streamlit dashboard:**
    ```bash
    streamlit run dashboard/Home.py
    ```
    The dashboard will be available at `http://localhost:8501`.

## Project Structure

```
AI-Skill-Demand-Tracker/
├── .dockerignore
├── .env.example
├── .gitattributes
├── .gitignore
├── Dockerfile
├── README.md
├── analyze.py
├── dashboard/
├── ingest.py
├── requirements.txt
├── seed_test_data.py
└── src/
    ├── analytics/
    ├── api/
    ├── config.py
    ├── database.py
    ├── extractor.py
    ├── fetchers/
    ├── models.py
    ├── pipeline.py
    └── scheduler.py
```

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

## License

This project is licensed under the MIT License. See the [LICENSE](https://opensource.org/licenses/MIT) file for details.