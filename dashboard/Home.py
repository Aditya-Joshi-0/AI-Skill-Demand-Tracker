"""
dashboard/Home.py
──────────────────
Landing page. Streamlit uses the filename as the page title in the sidebar.
Pages in the `pages/` subfolder auto-appear in the sidebar nav.

This page shows:
  - DB health metrics (total jobs, skills, last fetch)
  - Top 10 rising skills this week (bar chart)
  - Top 20 skills by job count (horizontal bar)
  - Quick skill search → navigate to Skill Deep-Dive
"""

import sys
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# Make dashboard/ importable from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.styles import apply_theme, PLOTLY_THEME, AMBER, TEAL, RED, MUTED, PURPLE
from dashboard.api_client import get_health, get_trends, get_report

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Skill Demand Tracker",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📡 Skill Tracker")
    st.caption("Real-time AI/tech skill demand from job postings")
    st.divider()

    health = get_health()
    if health:
        st.caption("DATABASE")
        st.markdown(f"`{health.get('total_jobs', 0):,}` jobs indexed")
        st.markdown(f"`{health.get('unique_skills', 0):,}` unique skills")
        if health.get("latest_fetch"):
            st.caption(f"Last fetch: {health['latest_fetch'][:10]}")
    st.divider()
    st.caption("PAGES")


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("# 📡 AI Skill Demand Tracker")
st.caption("Live skill frequency data from Hacker News · RemoteOK · Arbeitnow")
st.divider()

# ── Health metrics ────────────────────────────────────────────────────────────
if health:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Jobs Indexed", f"{health.get('total_jobs', 0):,}")
    with col2:
        st.metric("Unique Skills Tracked", f"{health.get('unique_skills', 0):,}")
    with col3:
        st.metric("API Status", "🟢 Online" if health.get("status") == "ok" else "🔴 Degraded")
    with col4:
        last = health.get("latest_fetch", "—")
        st.metric("Last Ingestion", last[:10] if last else "—")
else:
    st.warning("Cannot connect to API. Start the backend.")
    st.stop()

st.divider()

# ── Two-column layout ─────────────────────────────────────────────────────────
left, right = st.columns([1.1, 1], gap="large")

# ── LEFT: Rising Skills ───────────────────────────────────────────────────────
with left:
    st.markdown("### 🔥 Rising This Week")
    st.caption("Skills with the largest week-over-week frequency increase")

    rising = get_trends(direction="rising", limit=12)

    if rising:
        df_rising = pd.DataFrame(rising)
        df_rising = df_rising.sort_values("delta_pct", ascending=True)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_rising["delta_pct"],
            y=df_rising["name"],
            orientation="h",
            marker=dict(
                color=df_rising["delta_pct"],
                colorscale=[[0, "#1a3322"], [0.5, "#1d7a52"], [1.0, TEAL]],
                line=dict(width=0),
            ),
            text=[f"+{v:.0f}%" for v in df_rising["delta_pct"]],
            textposition="outside",
            textfont=dict(family="DM Mono", size=10, color="#96918a"),
            hovertemplate="<b>%{y}</b><br>Δ WoW: +%{x:.1f}%<br>%{customdata} jobs this week<extra></extra>",
            customdata=df_rising["current_count"],
        ))
        # fig.update_layout(
        #     **PLOTLY_THEME,
        #     height=380,
        #     xaxis_title="Week-over-week change (%)",
        #     yaxis_title="",
        #     showlegend=False,
        #     xaxis=dict(**PLOTLY_THEME["xaxis"], ticksuffix="%"),
        # )
        layout_config = {
            **PLOTLY_THEME,
            "height": 380,
            "xaxis_title": "Week-over-week change (%)",
            "yaxis_title": "",
            "showlegend": False,
        }
        layout_config["xaxis"] = dict(**PLOTLY_THEME["xaxis"], ticksuffix="%")
        fig.update_layout(**layout_config)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("📊 Trend data will appear after running the data ingestion pipeline for 2+ days. "
                   "Or, load sample data now to explore the dashboard."
        )
    if st.button("📥 Load Sample Data", key="load_sample"):
        # Call seed function
        pass
    st.caption("💡 Once you start the ingestion pipeline, this message will disappear as data accumulates.")


# ── RIGHT: Top Skills by Job Count ────────────────────────────────────────────
with right:
    st.markdown("### 📊 Top Skills by Demand")
    st.caption("% of all job postings mentioning each skill")

    report = get_report(limit=20)

    if report:
        df_report = pd.DataFrame(report)

        # Colour by category
        cat_colors = {
            "ml_concept": TEAL,
            "framework":  AMBER,
            "language":   PURPLE if True else AMBER,
            "cloud":      "#5b8ff9",
            "database":   "#e05252",
            "tool":       MUTED,
            "domain":     "#b87aff",
            "other":      MUTED,
        }
        
        colors = [cat_colors.get(row["category"], MUTED) for _, row in df_report.iterrows()]

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_report["frequency"],
            y=df_report["name"],
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            text=[f"{v:.1f}%" for v in df_report["frequency"]],
            textposition="outside",
            textfont=dict(family="DM Mono", size=10, color="#96918a"),
            hovertemplate="<b>%{y}</b><br>%{x:.1f}% of jobs<br>%{customdata} postings<extra></extra>",
            customdata=df_report["total_jobs"],
        ))
        # fig2.update_layout(
        #     **PLOTLY_THEME,
        #     height=380,
        #     xaxis_title="% of job postings",
        #     yaxis=dict(**PLOTLY_THEME["yaxis"], autorange="reversed"),
        #     showlegend=False,
        #     xaxis=dict(**PLOTLY_THEME["xaxis"], ticksuffix="%"),
        # )
        layout_config = {
            **PLOTLY_THEME,
            "height": 380,
            "xaxis_title": "% of job postings",
            "showlegend": False,
        }
        layout_config["yaxis"] = dict(**PLOTLY_THEME["yaxis"], autorange="reversed")
        layout_config["xaxis"] = dict(**PLOTLY_THEME["xaxis"], ticksuffix="%")
        fig2.update_layout(**layout_config)
        st.plotly_chart(fig2, use_container_width=True)

        # Category legend
        st.caption("■ ml_concept  ■ framework  ■ language  ■ cloud  ■ database")

# ── Quick Search ──────────────────────────────────────────────────────────────
st.divider()
st.markdown("### 🔍 Quick Skill Lookup")

search_col, _ = st.columns([1, 2])
with search_col:
    skill_name = st.text_input(
        "Skill name",
        placeholder="e.g. Python, LangChain, RAG...",
        label_visibility="collapsed",
    )

if skill_name:
    st.info(f"Navigate to **Skill Deep-Dive** in the sidebar and search for `{skill_name}`")
