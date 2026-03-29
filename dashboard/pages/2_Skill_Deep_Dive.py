"""
dashboard/pages/2_Skill_Deep_Dive.py
──────────────────────────────────────
Deep-dive on any single skill:
  - Weekly trend sparkline (8 weeks)
  - Segment breakdown: seniority / role / source
  - Co-occurring skills network
"""

import sys
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from styles import hex_to_rgba

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.styles import apply_theme, PLOTLY_THEME, AMBER, TEAL, MUTED
from dashboard.api_client import get_skill_detail, get_report

st.set_page_config(page_title="Skill Deep-Dive · Skill Tracker", page_icon="🔬", layout="wide")
apply_theme()

st.markdown("# 🔬 Skill Deep-Dive")
st.caption("8-week trend history, segment analysis, and skill network")
st.divider()

# ── Skill selector ────────────────────────────────────────────────────────────
report = get_report(limit=50)
skill_names = [s["name"] for s in report] if report else []

col_sel, col_weeks, _ = st.columns([1.5, 0.8, 2])
with col_sel:
    skill_name = st.selectbox("Select skill", skill_names, index=0 if skill_names else None)
with col_weeks:
    n_weeks = st.selectbox("History (weeks)", [4, 8, 12], index=1)

if not skill_name:
    st.info("No skills data available yet. Please ingest job postings first to populate the database.")
    st.stop()

detail = get_skill_detail(skill_name)
if not detail:
    st.warning(f"No data found for '{skill_name}'")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────
history = detail.get("history", [])
if history:
    latest = history[-1]
    previous = history[-2] if len(history) >= 2 else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Skill", skill_name)
    c2.metric("Jobs This Week", latest["job_count"])
    c3.metric("Frequency", f"{latest['frequency']:.1f}%",
              delta=f"{latest['frequency'] - previous['frequency']:+.1f}%" if previous else None)
    c4.metric("Total Jobs Indexed", latest["total_jobs"])

st.divider()

# ── Trend sparkline ───────────────────────────────────────────────────────────
left, right = st.columns([1.3, 1], gap="large")

with left:
    st.markdown(f"### Weekly Demand — {skill_name}")
    if history:
        df_hist = pd.DataFrame(history)

        fig = go.Figure()
        # Area fill
        fig.add_trace(go.Scatter(
            x=df_hist["week_start"],
            y=df_hist["frequency"],
            mode="lines+markers",
            line=dict(color=TEAL, width=2.5),
            marker=dict(color=TEAL, size=6),
            fill="tozeroy",
            fillcolor=hex_to_rgba(TEAL, 0.08),
            name="Frequency (%)",
            hovertemplate="%{x}<br><b>%{y:.1f}%</b> of jobs<extra></extra>",
        ))
        # Job count as secondary
        fig.add_trace(go.Bar(
            x=df_hist["week_start"],
            y=df_hist["job_count"],
            name="Job count",
            marker=dict(color="#1e1e2e"),
            yaxis="y2",
            hovertemplate="%{x}<br><b>%{y}</b> jobs<extra></extra>",
            opacity=0.7,
        ))
        # fig.update_layout(
        #     **PLOTLY_THEME,
        #     height=280,
        #     yaxis=dict(**PLOTLY_THEME["yaxis"], title="% of all jobs", ticksuffix="%"),
        #     yaxis2=dict(
        #         title="Job count", overlaying="y", side="right",
        #         gridcolor="#1e1e2e", tickfont=dict(color=MUTED, size=9),
        #     ),
        #     legend=dict(orientation="h", y=-0.2, font=dict(size=10)),
        #     hovermode="x unified",
        # )
        layout_config = {
            **PLOTLY_THEME,
            "height": 280,
            "legend": dict(orientation="h", y=-0.2, font=dict(size=10)),
            "hovermode": "x unified",
        }
        layout_config["yaxis"] = dict(**PLOTLY_THEME["yaxis"], title="% of all jobs", ticksuffix="%")
        layout_config["yaxis2"] = dict(
            title="Job count", overlaying="y", side="right",
            gridcolor="#1e1e2e", tickfont=dict(color=MUTED, size=9),
        )
        fig.update_layout(**layout_config)
        st.plotly_chart(fig, use_container_width=True)

# ── Co-occurring skills ───────────────────────────────────────────────────────
with right:
    st.markdown(f"### Skills That Appear Alongside")
    neighbors = detail.get("neighbors", [])
    if neighbors:
        df_n = pd.DataFrame(neighbors).head(10)
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_n["confidence"],
            y=df_n["skill"],
            orientation="h",
            marker=dict(
                color=df_n["confidence"],
                colorscale=[[0, "#1a1a2e"], [1.0, AMBER]],
                line=dict(width=0),
            ),
            text=[f"{v:.0f}%" for v in df_n["confidence"]],
            textposition="outside",
            textfont=dict(family="DM Mono", size=10, color=MUTED),
            hovertemplate="<b>%{y}</b><br>%{x:.0f}% of '%{customdata}' jobs also need this<extra></extra>",
            customdata=[skill_name] * len(df_n),
        ))
        # fig2.update_layout(
        #     **PLOTLY_THEME,
        #     height=280,
        #     xaxis=dict(**PLOTLY_THEME["xaxis"], ticksuffix="%", title="Co-occurrence confidence"),
        #     yaxis=dict(**PLOTLY_THEME["yaxis"], autorange="reversed"),
        # )
        layout_config = {
            **PLOTLY_THEME,
            "height": 280,
        }
        layout_config["xaxis"] = dict(**PLOTLY_THEME["xaxis"], ticksuffix="%", title="Co-occurrence confidence")
        layout_config["yaxis"] = dict(**PLOTLY_THEME["yaxis"], autorange="reversed")
        fig2.update_layout(**layout_config)
        st.plotly_chart(fig2, use_container_width=True)

# ── Segment breakdown ─────────────────────────────────────────────────────────
st.markdown("### Demand by Segment")
segments = detail.get("segments", {})

if segments:
    tabs = st.tabs(["By Seniority", "By Role", "By Source"])

    for tab, seg_key in zip(tabs, ["seniority", "role_category", "source"]):
        with tab:
            seg_data = segments.get(seg_key, [])
            if not seg_data:
                st.caption("No data for this segment.")
                continue

            df_seg = pd.DataFrame(seg_data)
            if df_seg.empty:
                continue

            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=df_seg["segment"],
                y=df_seg["frequency"],
                marker=dict(color=TEAL, line=dict(width=0)),
                text=[f"{v:.0f}%" for v in df_seg["frequency"]],
                textposition="outside",
                textfont=dict(family="DM Mono", size=10, color=MUTED),
                hovertemplate="<b>%{x}</b><br>%{y:.1f}% of jobs in segment<extra></extra>",
            ))
            # fig3.update_layout(
            #     **PLOTLY_THEME,
            #     height=220,
            #     yaxis=dict(**PLOTLY_THEME["yaxis"], ticksuffix="%"),
            #     showlegend=False,
            #     margin=dict(l=20, r=20, t=20, b=60),
            # )
            layout_config = {
                **PLOTLY_THEME,
                "height": 220,
                "showlegend": False,
                "margin": dict(l=20, r=20, t=20, b=60),
            }
            layout_config["yaxis"] = dict(**PLOTLY_THEME["yaxis"], ticksuffix="%")
            fig3.update_layout(**layout_config)
            st.plotly_chart(fig3, use_container_width=True)
