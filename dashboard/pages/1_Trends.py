"""
dashboard/pages/1_Trends.py
────────────────────────────
Full trend table with direction/category/seniority filters.
The "1_" prefix controls sidebar sort order.
"""

import sys
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.styles import apply_theme, PLOTLY_THEME, AMBER, TEAL, RED, MUTED
from dashboard.api_client import get_trends

st.set_page_config(page_title="Trends · Skill Tracker", page_icon="📈", layout="wide")
apply_theme()

st.markdown("# 📈 Skill Trends")
st.caption("Week-over-week frequency change across all tracked skills")
st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────
f1, f2, f3, f4 = st.columns(4)
with f1:
    direction = st.selectbox("Direction", ["all", "rising", "falling", "stable", "new", "disappeared"])
with f2:
    category = st.selectbox("Category", ["all", "ml_concept", "framework", "language", "cloud", "database", "tool"])
with f3:
    seniority = st.selectbox("Seniority", ["all", "junior", "mid", "senior", "lead"])
with f4:
    limit = st.slider("Max results", 10, 100, 40)

direction_val = None if direction == "all" else direction
category_val  = None if category  == "all" else category
seniority_val = None if seniority == "all" else seniority

trends = get_trends(
    direction=direction_val,
    category=category_val,
    seniority=seniority_val,
    limit=limit,
)

if not trends:
    st.info("Insufficient data for trends. Need at least 2 days of job postings to calculate meaningful trends.")
    st.stop()

df = pd.DataFrame(trends)

# ── Summary metrics ───────────────────────────────────────────────────────────
rising_n    = len(df[df["direction"] == "rising"])
falling_n   = len(df[df["direction"] == "falling"])
new_n       = len(df[df["direction"] == "new"])
stable_n    = len(df[df["direction"] == "stable"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Rising ↑", rising_n,  delta=f"skills gaining demand")
c2.metric("Falling ↓", falling_n, delta=f"skills losing demand", delta_color="inverse")
c3.metric("New ✦",  new_n,  delta="appeared this week")
c4.metric("Stable →", stable_n)

st.divider()

# ── Diverging bar chart ───────────────────────────────────────────────────────
st.markdown("### Δ Week-over-Week Change")

df_sorted = df.sort_values("delta_pct", ascending=False).head(30)
colors = [TEAL if d > 0 else RED for d in df_sorted["delta_pct"]]

fig = go.Figure()
fig.add_trace(go.Bar(
    x=df_sorted["name"],
    y=df_sorted["delta_pct"],
    marker=dict(color=colors, line=dict(width=0)),
    text=[f"{v:+.0f}%" for v in df_sorted["delta_pct"]],
    textposition="outside",
    textfont=dict(family="DM Mono", size=9, color="#96918a"),
    hovertemplate="<b>%{x}</b><br>Δ: %{y:+.1f}%<extra></extra>",
))
fig.update_layout(
    **PLOTLY_THEME,
    height=340,
    yaxis_title="WoW Δ (%)",
    xaxis_tickangle=-35,
    shapes=[dict(
        type="line", x0=-0.5, x1=len(df_sorted)-0.5, y0=0, y1=0,
        line=dict(color="#2a2a3e", width=1, dash="dot"),
    )],
)
st.plotly_chart(fig, use_container_width=True)

# ── Detail table ──────────────────────────────────────────────────────────────
st.markdown("### Full Trend Table")

DIR_ICONS = {
    "rising": "↑", "falling": "↓",
    "stable": "→", "new": "✦", "disappeared": "✕",
}

display_df = df[[
    "name", "category", "direction",
    "current_count", "current_freq",
    "previous_count", "previous_freq",
    "delta_pct", "weeks_present",
]].copy()

display_df["direction"] = display_df["direction"].map(lambda d: f"{DIR_ICONS.get(d,'')} {d}")
display_df["current_freq"]  = display_df["current_freq"].map(lambda x: f"{x:.1f}%")
display_df["previous_freq"] = display_df["previous_freq"].map(lambda x: f"{x:.1f}%")
display_df["delta_pct"]     = display_df["delta_pct"].map(lambda x: f"{x:+.1f}%")

display_df.columns = ["Skill", "Category", "Direction", "This Week", "Freq", "Last Week", "Prev Freq", "Δ WoW", "Weeks Seen"]

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=420,
)
