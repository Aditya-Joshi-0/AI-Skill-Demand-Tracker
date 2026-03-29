"""
analyse.py
───────────
Analytics CLI. Run after ingest.py has populated the database.

Commands:
  python analyse.py trending                  # rising/falling skills this week
  python analyse.py report                    # full ranked skill report
  python analyse.py skill "Python"            # deep-dive on one skill
  python analyse.py cooccurrence              # skill pairs that appear together
  python analyse.py segments --by seniority   # skills by seniority level
  python analyse.py segments --by role        # skills by role category
  python analyse.py segments --by source      # skills by job board
"""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box as rich_box

sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_settings, setup_logging

from src.analytics.scoring import build_skill_report
from src.analytics.trends import compute_trends, get_skill_history, TrendDirection
from src.analytics.coocurrence import compute_cooccurrence, get_skill_neighbors
from src.analytics.segments import (
    get_skills_by_seniority, get_skills_by_role_category, 
    get_skills_by_source, compare_skill_across_segments
)


app     = typer.Typer(name="analyse", help="AI Skill Demand Tracker — Analytics", pretty_exceptions_show_locals=False)
console = Console()

DIRECTION_COLORS = {
    TrendDirection.RISING.value:      "green",
    TrendDirection.FALLING.value:     "red",
    TrendDirection.STABLE.value:      "dim",
    TrendDirection.NEW.value:         "cyan",
    TrendDirection.DISAPPEARED.value: "yellow",
}

DIRECTION_ICONS = {
    TrendDirection.RISING.value:      "↑",
    TrendDirection.FALLING.value:     "↓",
    TrendDirection.STABLE.value:      "→",
    TrendDirection.NEW.value:         "✦",
    TrendDirection.DISAPPEARED.value: "✕",
}


# ─── trending ────────────────────────────────────────────────────────────────

@app.command()
def trending(
    direction: Optional[str] = typer.Option(
        None, "--direction", "-d",
        help="Filter: rising | falling | new | stable | disappeared"
    ),
    category: Optional[str] = typer.Option(
        None, "--category", "-c",
        help="Filter by category: language | framework | ml_concept | cloud | database | tool",
    ),
    seniority: Optional[str] = typer.Option(None, "--seniority"),
    limit: int = typer.Option(25, "--limit", "-n"),
):
    """Show week-over-week trending skills."""
    setup_logging()
    db_path = get_settings().db_path

    trends = compute_trends(db_path, seniority=seniority)

    if not trends:
        console.print("[yellow]Not enough data yet. Run ingest.py for at least 2 days to see trends.[/yellow]")
        console.print("[dim]Tip: you can test with synthetic data — see README.[/dim]")
        return

    # Filter
    if direction:
        trends = [t for t in trends if t.direction.value == direction]
    if category:
        trends = [t for t in trends if t.category == category]

    trends = [t for t in trends if t.is_significant][:limit]

    table = Table(
        show_header=True,
        header_style="bold",
        box=rich_box.SIMPLE,
        padding=(0, 1),
    )
    table.add_column("Skill",      style="cyan",  min_width=18)
    table.add_column("Category",   style="dim",   min_width=12)
    table.add_column("This week",  justify="right")
    table.add_column("Last week",  justify="right", style="dim")
    table.add_column("Δ WoW",      justify="right", min_width=8)
    table.add_column("Direction",  min_width=14)
    table.add_column("Weeks seen", justify="right", style="dim")

    for t in trends:
        dir_color = DIRECTION_COLORS.get(t.direction.value, "white")
        dir_icon  = DIRECTION_ICONS.get(t.direction.value, "?")
        delta_str = f"{t.delta_pct:+.1f}%"
        delta_color = "green" if t.delta_pct > 0 else "red" if t.delta_pct < 0 else "dim"

        table.add_row(
            t.name,
            t.category,
            f"{t.current_count} ({t.current_freq:.1f}%)",
            f"{t.previous_count} ({t.previous_freq:.1f}%)",
            f"[{delta_color}]{delta_str}[/{delta_color}]",
            f"[{dir_color}]{dir_icon} {t.direction.value}[/{dir_color}]",
            str(t.weeks_present),
        )

    title_parts = ["Skill Trends — Week over Week"]
    if direction:
        title_parts.append(f"direction={direction}")
    if seniority:
        title_parts.append(f"seniority={seniority}")

    console.print(Panel(table, title=f"[bold]{'  |  '.join(title_parts)}[/bold]", border_style="blue"))
    console.print(f"[dim]{len(trends)} skills shown. Run with --direction rising to focus on rising skills.[/dim]")


# ─── report ──────────────────────────────────────────────────────────────────

@app.command()
def report(
    limit: int = typer.Option(25, "--limit", "-n"),
    category: Optional[str] = typer.Option(None, "--category", "-c"),
):
    """Full ranked skill report: frequency + trend + investment score."""
    setup_logging()
    db_path = get_settings().db_path

    skills = build_skill_report(db_path, top_n=limit, category=category)

    if not skills:
        console.print("[yellow]No data found. Run: python ingest.py[/yellow]")
        return

    table = Table(show_header=True, header_style="bold", box=rich_box.SIMPLE, padding=(0, 1))
    table.add_column("#",           style="dim",  width=4)
    table.add_column("Skill",       style="cyan", min_width=18)
    table.add_column("Category",    style="dim",  min_width=12)
    table.add_column("Jobs",        justify="right")
    table.add_column("Frequency",   justify="right")
    table.add_column("Trend",       justify="right", min_width=8)
    table.add_column("Invest score",justify="right")
    table.add_column("Priority",    min_width=16)

    for i, s in enumerate(skills, 1):
        dir_color = DIRECTION_COLORS.get(s.trend_direction, "dim")
        dir_icon  = DIRECTION_ICONS.get(s.trend_direction, "→")
        delta_str = f"{s.trend_delta:+.0f}%" if s.trend_delta != 0 else "—"

        # Colour the investment score
        inv = s.investment_score
        inv_color = "green" if inv >= 70 else "yellow" if inv >= 40 else "red"

        table.add_row(
            str(i),
            s.name,
            s.category,
            str(s.total_jobs),
            f"{s.frequency:.1f}%",
            f"[{dir_color}]{dir_icon} {delta_str}[/{dir_color}]",
            f"[{inv_color}]{inv:.0f}[/{inv_color}]",
            s.investment_label,
        )

    subtitle = f"category={category}" if category else "all categories"
    console.print(Panel(
        table,
        title=f"[bold]Skill Investment Report — {subtitle}[/bold]",
        border_style="cyan",
    ))
    console.print("[dim]Investment score: frequency × trend momentum × differentiation value[/dim]")


# ─── skill ───────────────────────────────────────────────────────────────────

@app.command()
def skill(
    name: str = typer.Argument(..., help="Skill name to deep-dive, e.g. 'Python'"),
):
    """Deep-dive on a single skill: history, segments, and neighbours."""
    setup_logging()
    db_path = get_settings().db_path

    console.print(f"\n[bold cyan]Deep-dive: {name}[/bold cyan]\n")

    # ── Trend history ──
    history = get_skill_history(db_path, name, n_weeks=8)
    if not history:
        console.print(f"[yellow]Skill '{name}' not found in database.[/yellow]")
        return

    hist_table = Table(show_header=True, header_style="bold", box=rich_box.SIMPLE)
    hist_table.add_column("Week")
    hist_table.add_column("Jobs", justify="right")
    hist_table.add_column("Freq", justify="right")
    hist_table.add_column("Sparkline")

    max_count = max((h["job_count"] for h in history), default=1)
    for h in history:
        bar_len = int(h["job_count"] / max_count * 20) if max_count else 0
        bar = "█" * bar_len
        hist_table.add_row(
            h["week_start"],
            str(h["job_count"]),
            f"{h['frequency']:.1f}%",
            f"[cyan]{bar}[/cyan]",
        )
    console.print(Panel(hist_table, title="Weekly Trend History", border_style="blue"))

    # ── Segment breakdown ──
    segments = compare_skill_across_segments(db_path, name)

    seg_panels = []
    for seg_name, rows in segments.items():
        if not rows:
            continue
        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column("Segment", style="dim")
        t.add_column("Freq", justify="right", style="cyan")
        for r in rows[:6]:
            t.add_row(r["segment"] or "—", f"{r['frequency']:.0f}%")
        seg_panels.append(Panel(t, title=f"[dim]{seg_name}[/dim]", border_style="dim"))

    if seg_panels:
        console.print(Columns(seg_panels))

    # ── Co-occurring skills ──
    neighbors = get_skill_neighbors(db_path, name, top_n=10)
    if neighbors:
        n_table = Table(show_header=True, header_style="bold", box=rich_box.SIMPLE)
        n_table.add_column("Skill that appears alongside", style="cyan")
        n_table.add_column("Co-occurrences", justify="right")
        n_table.add_column("Confidence", justify="right")
        for n in neighbors:
            n_table.add_row(n["skill"], str(n["co_count"]), f"{n['confidence']:.0f}%")
        console.print(Panel(n_table, title=f"Skills That Appear Alongside '{name}'", border_style="green"))


# ─── cooccurrence ────────────────────────────────────────────────────────────

@app.command()
def cooccurrence(
    limit: int = typer.Option(20, "--limit", "-n"),
    category: Optional[str] = typer.Option(
        None, "--category", "-c",
        help="Filter pairs to a skill category"
    ),
    min_lift: float = typer.Option(1.2, "--min-lift"),
):
    """Show skill pairs that frequently appear together (association rules)."""
    setup_logging()
    db_path = get_settings().db_path

    pairs = compute_cooccurrence(
        db_path,
        top_n=limit,
        category_filter=category,
        min_lift=min_lift,
    )

    if not pairs:
        console.print("[yellow]No co-occurrence pairs found. Try lowering --min-lift.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold", box=rich_box.SIMPLE, padding=(0, 1))
    table.add_column("Skill A",     style="cyan",  min_width=16)
    table.add_column("Skill B",     style="green", min_width=16)
    table.add_column("Co-occurs",   justify="right")
    table.add_column("Support",     justify="right")
    table.add_column("A→B conf",    justify="right")
    table.add_column("B→A conf",    justify="right")
    table.add_column("Lift",        justify="right")
    table.add_column("Strength",    min_width=12)

    for p in pairs:
        lift_color = "green" if p.lift >= 2.0 else "yellow" if p.lift >= 1.5 else "dim"
        table.add_row(
            p.skill_a,
            p.skill_b,
            str(p.co_occurrence_count),
            f"{p.support:.1f}%",
            f"{p.confidence_a_to_b:.0f}%",
            f"{p.confidence_b_to_a:.0f}%",
            f"[{lift_color}]{p.lift:.2f}[/{lift_color}]",
            p.strength_label,
        )

    console.print(Panel(
        table,
        title=f"[bold]Skill Co-occurrence Pairs (lift ≥ {min_lift})[/bold]",
        border_style="green",
    ))
    console.print("[dim]Lift > 2.0 = skills appear together 2× more than expected by chance.[/dim]")


# ─── segments ────────────────────────────────────────────────────────────────

@app.command()
def segments(
    by: str = typer.Option(
        "seniority",
        "--by", "-b",
        help="Segment by: seniority | role | source"
    ),
    limit: int = typer.Option(10, "--limit", "-n"),
):
    """Break down skill demand by seniority, role type, or job source."""
    setup_logging()
    db_path = get_settings().db_path

    if by == "seniority":
        data = get_skills_by_seniority(db_path, top_n=limit)
        title = "Top Skills by Seniority Level"
    elif by == "role":
        data = get_skills_by_role_category(db_path, top_n=limit)
        title = "Top Skills by Role Category"
    elif by == "source":
        data = get_skills_by_source(db_path, top_n=limit)
        title = "Top Skills by Job Source"
    else:
        console.print(f"[red]Unknown segment: {by}. Use: seniority | role | source[/red]")
        raise typer.Exit(1)

    if not data:
        console.print("[yellow]No segment data found. Run: python ingest.py[/yellow]")
        return

    panels = []
    for segment, skills in sorted(data.items()):
        if not skills:
            continue
        t = Table(show_header=False, box=None, padding=(0, 1))
        t.add_column("Skill", style="cyan")
        t.add_column("Freq",  justify="right", style="dim")
        for s in skills:
            t.add_row(s["skill"], f"{s['frequency']:.0f}%")
        panels.append(Panel(t, title=f"[bold]{segment}[/bold]", border_style="blue"))

    console.print(f"\n[bold]{title}[/bold]\n")
    # Print panels in rows of 3
    for i in range(0, len(panels), 3):
        console.print(Columns(panels[i:i+3]))


if __name__ == "__main__":
    app()
