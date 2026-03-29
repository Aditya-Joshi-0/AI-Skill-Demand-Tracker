"""
ingest.py
──────────
CLI entry point. Run this to trigger the pipeline.

Usage:
  python ingest.py                          # fetch from all sources
  python ingest.py --source hackernews      # single source
  python ingest.py --source hackernews --source remoteok   # two sources
  python ingest.py --max-jobs 10            # small run for testing
  python ingest.py --stats                  # just show DB stats, no fetch
  python ingest.py --top-skills            # show top skills from last 7 days
"""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich import print as rprint

# Make src/ importable when running from project root
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_settings, setup_logging
from src.pipeline import run_pipeline
from src.database import get_stats, get_top_skills

app = typer.Typer(
    name="skill-tracker",
    help="AI Skill Demand Tracker — fetch job posts, extract skills, track trends.",
    pretty_exceptions_show_locals=False,
)
console = Console()

VALID_SOURCES = ["hackernews", "remoteok", "arbeitnow"]


@app.command()
def ingest(
    source: list[str] = typer.Option(
        None,
        "--source", "-s",
        help=f"Source(s) to fetch from. Options: {', '.join(VALID_SOURCES)}. Default: all.",
    ),
    max_jobs: int = typer.Option(
        None,
        "--max-jobs", "-n",
        help="Max jobs per source (overrides .env MAX_JOBS_PER_SOURCE).",
    ),
    stats: bool = typer.Option(
        False,
        "--stats",
        help="Show database stats and exit (no fetching).",
    ),
    top_skills: bool = typer.Option(
        False,
        "--top-skills",
        help="Show top skills from the last 7 days and exit.",
    ),
    days: int = typer.Option(
        7,
        "--days",
        help="Days lookback for --top-skills.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Fetch and extract but don't write to database.",
    ),
):
    """
    Run the skill ingestion pipeline.

    Examples:\n
      python ingest.py\n
      python ingest.py --source hackernews --max-jobs 20\n
      python ingest.py --stats\n
      python ingest.py --top-skills --days 14
    """
    setup_logging()
    settings = get_settings()

    # ── Stats only ──
    if stats:
        _show_stats(settings.db_path)
        return

    if top_skills:
        _show_top_skills(settings.db_path, days)
        return

    # ── Validate sources ──
    if source:
        invalid = [s for s in source if s not in VALID_SOURCES]
        if invalid:
            console.print(f"[red]Unknown source(s): {', '.join(invalid)}[/red]")
            console.print(f"Valid sources: {', '.join(VALID_SOURCES)}")
            raise typer.Exit(1)

    # ── Print run config ──
    console.print()
    console.print(Panel.fit(
        f"[bold]AI Skill Demand Tracker[/bold]\n"
        f"Sources:  [cyan]{', '.join(source) if source else 'all'}[/cyan]\n"
        f"Max jobs: [cyan]{max_jobs or settings.max_jobs_per_source} per source[/cyan]\n"
        f"LLM:      [cyan]{settings.llm_provider} / "
        f"{'gpt-4o-mini' if settings.llm_provider == 'openai' else ('claude-haiku' if settings.llm_provider == 'claude' else settings.nvidia_model)}[/cyan] \n"
        f"DB:       [cyan]{settings.db_path}[/cyan]"
        + (" [yellow](DRY RUN — not saving)[/yellow]" if dry_run else ""),
        title="[bold blue]Pipeline Config[/bold blue]",
        border_style="blue",
    ))
    console.print()

    # ── Run pipeline ──
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Running pipeline...", total=None)

        async def _run():
            return await run_pipeline(
                sources=list(source) if source else None,
                max_jobs_per_source=max_jobs,
            )

        result = asyncio.run(_run())
        progress.update(task, description="Pipeline complete ✓")

    # ── Print results ──
    console.print()

    # Source breakdown table
    source_table = Table(show_header=True, header_style="bold", box=None)
    source_table.add_column("Source", style="cyan")
    source_table.add_column("Fetched", justify="right")
    for src, count in result.by_source.items():
        source_table.add_row(src, str(count))
    source_table.add_row("─────────────", "───────")
    source_table.add_row("[bold]Total[/bold]", f"[bold]{result.total_fetched}[/bold]")

    console.print(source_table)
    console.print()

    # Summary panel
    console.print(Panel(
        f"  Fetched:              [cyan]{result.total_fetched}[/cyan] posts\n"
        f"  Extracted (LLM):      [cyan]{result.total_extracted}[/cyan]\n"
        f"  Extraction failures:  [{'red' if result.extraction_failures else 'dim'}]{result.extraction_failures}[/{'red' if result.extraction_failures else 'dim'}]\n"
        f"  New jobs saved:       [green]{result.new_jobs_saved}[/green]\n"
        f"  Duplicates skipped:   [dim]{result.duplicate_jobs}[/dim]\n"
        f"  Duration:             [cyan]{result.duration_seconds:.1f}s[/cyan]",
        title="[bold green]Run Complete[/bold green]",
        border_style="green",
    ))

    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in result.errors:
            console.print(f"  [red]• {err}[/red]")

    # Show top skills if we saved anything new
    if result.new_jobs_saved > 0:
        console.print()
        _show_top_skills(settings.db_path, days=1, limit=15, title="Top Skills from This Run")


def _show_stats(db_path: str):
    """Print database health stats."""
    try:
        stats = get_stats(db_path)
    except Exception as e:
        console.print(f"[red]Could not read DB: {e}[/red]")
        console.print("Have you run the pipeline yet? Try: python ingest.py")
        return

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value", style="cyan")
    table.add_row("Total jobs",     str(stats["total_jobs"]))
    table.add_row("Unique skills",  str(stats["unique_skills"]))
    table.add_row("Skill links",    str(stats["skill_links"]))
    table.add_row("Latest fetch",   str(stats["latest_fetch"] or "—"))
    table.add_section()
    for source, count in (stats.get("by_source") or {}).items():
        table.add_row(f"  {source}", str(count))

    console.print(Panel(table, title="[bold]Database Stats[/bold]", border_style="blue"))


def _show_top_skills(
    db_path: str,
    days: int = 7,
    limit: int = 20,
    title: str | None = None,
):
    """Print top skills table."""
    try:
        skills = get_top_skills(db_path, limit=limit, days=days)
    except Exception as e:
        console.print(f"[red]Could not read skills: {e}[/red]")
        return

    if not skills:
        console.print(f"[dim]No skills found for last {days} days.[/dim]")
        return

    title = title or f"Top {limit} Skills — Last {days} Days"
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("#",        style="dim",  width=4)
    table.add_column("Skill",    style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Jobs",     justify="right")

    max_count = skills[0]["job_count"] if skills else 1
    for i, row in enumerate(skills, 1):
        bar_len = int(row["job_count"] / max_count * 20)
        bar = "█" * bar_len
        table.add_row(
            str(i),
            row["name"],
            row["category"],
            f"{row['job_count']}  [dim]{bar}[/dim]",
        )

    console.print(Panel(table, title=f"[bold]{title}[/bold]", border_style="cyan"))


if __name__ == "__main__":
    app()
