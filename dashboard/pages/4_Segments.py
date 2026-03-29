"""
dashboard/pages/4_Segments.py
───────────────────────────────
Compare skill demand across segments: seniority / role / source.
"""

import sys
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.styles import apply_theme, PLOTLY_THEME, AMBER, TEAL, MUTED
from dashboard.api_client import get_segments

st.set_page_config(page_title="Segments · Skill Tracker", page_icon="🎯", layout="wide")
apply_theme()

st.markdown("# 🎯 Skill Demand by Segment")
st.caption("How skill requirements differ by seniority level, role type, and job source")
st.divider()

# ── Segment selector ──────────────────────────────────────────────────────────
seg_tab1, seg_tab2, seg_tab3 = st.tabs(["👤 By Seniority", "🧪 By Role", "📡 By Source"])

COLORS = [TEAL, AMBER, "#9b8fe8", "#e05252", "#5b8ff9", "#2ec4b6"]


def _render_grouped_bars(data: dict, title: str):
    """Render overlapping bar charts, one per segment."""
    if not data:
        st.info("No segments available yet. Job posting data needs to be ingested before segments can be generated")
        return

    fig = go.Figure()
    for i, (segment, skills) in enumerate(sorted(data.items())):
        if not skills:
            continue
        df_seg = pd.DataFrame(skills).head(12)
        fig.add_trace(go.Bar(
            name=segment,
            x=df_seg["skill"],
            y=df_seg["frequency"],
            marker=dict(color=COLORS[i % len(COLORS)], line=dict(width=0), opacity=0.85),
            hovertemplate=f"<b>%{{x}}</b><br>{segment}: %{{y:.1f}}%<extra></extra>",
        ))

    # fig.update_layout(
    #     **PLOTLY_THEME,
    #     height=380,
    #     barmode="group",
    #     yaxis=dict(**PLOTLY_THEME["yaxis"], title="% of jobs in segment", ticksuffix="%"),
    #     xaxis=dict(**PLOTLY_THEME["xaxis"], tickangle=-35),
    #     legend=dict(orientation="h", y=-0.25, font=dict(size=11, color="#96918a")),
    # )
    layout_config = {
        **PLOTLY_THEME,
        "height": 380,
        "barmode": "group",
        "legend": dict(orientation="h", y=-0.25, font=dict(size=11, color="#96918a")),
    }
    layout_config["yaxis"] = dict(**PLOTLY_THEME["yaxis"], title="% of jobs in segment", ticksuffix="%")
    layout_config["xaxis"] = dict(**PLOTLY_THEME["xaxis"], tickangle=-35)
    fig.update_layout(**layout_config)
    st.plotly_chart(fig, use_container_width=True)

    # Heatmap view
    st.markdown("#### Heatmap View")
    all_skills = []
    for skills in data.values():
        all_skills.extend([s["skill"] for s in skills])
    top_skills = list(dict.fromkeys(all_skills))[:20]

    segments = sorted(data.keys())
    z_matrix = []
    for seg in segments:
        skill_map = {s["skill"]: s["frequency"] for s in data[seg]}
        row = [skill_map.get(sk, 0.0) for sk in top_skills]
        z_matrix.append(row)

    fig2 = go.Figure(go.Heatmap(
        z=z_matrix,
        x=top_skills,
        y=segments,
        colorscale=[[0, "#0d0d14"], [0.3, "#1a3322"], [0.7, TEAL], [1.0, AMBER]],
        text=[[f"{v:.0f}%" for v in row] for row in z_matrix],
        texttemplate="%{text}",
        textfont=dict(size=9, family="DM Mono"),
        hovertemplate="<b>%{x}</b> in <b>%{y}</b><br>%{z:.1f}% of jobs<extra></extra>",
        # colorbar=dict(
        #     title="Frequency %",
        #     tickfont=dict(size=9, color=MUTED),
        #     titlefont=dict(size=10, color=MUTED),
        # ),
        colorbar=dict(
            title=dict(text="Frequency %", font=dict(size=10, color=MUTED)),
            tickfont=dict(size=9, color=MUTED),
        )
    ))
    # fig2.update_layout(
    #     **PLOTLY_THEME,
    #     height=max(180, len(segments) * 60),
    #     xaxis=dict(**PLOTLY_THEME["xaxis"], tickangle=-35),
    #     margin=dict(l=80, r=20, t=20, b=80),
    # )
    layout_config = {
        **PLOTLY_THEME,
        "height": max(180, len(segments) * 60),
        "margin": dict(l=80, r=20, t=20, b=80),
    }
    layout_config["xaxis"] = dict(**PLOTLY_THEME["xaxis"], tickangle=-35)
    fig2.update_layout(**layout_config)
    st.plotly_chart(fig2, use_container_width=True)


with seg_tab1:
    st.markdown("### Junior vs Mid vs Senior vs Lead")
    st.caption("Same skills, very different frequency by level — shows what actually matters at each stage")
    data = get_segments(by="seniority", limit=12)
    _render_grouped_bars(data, "Seniority")

with seg_tab2:
    st.markdown("### AI Engineer vs Data Scientist vs Backend vs DevOps")
    st.caption("What each role type actually requires — useful for career targeting")
    data = get_segments(by="role", limit=12)
    _render_grouped_bars(data, "Role")

with seg_tab3:
    st.markdown("### HN vs RemoteOK vs Arbeitnow")
    st.caption("Each job board has a different audience — HN skews AI-heavy, RemoteOK is full-stack")
    data = get_segments(by="source", limit=12)
    _render_grouped_bars(data, "Source")
