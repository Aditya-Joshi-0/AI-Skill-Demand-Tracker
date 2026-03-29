"""
dashboard/pages/3_Co_Occurrence.py
────────────────────────────────────
Skill co-occurrence: association rule mining results as
an interactive scatter plot + table.
"""

import sys
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import networkx as nx

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.styles import apply_theme, PLOTLY_THEME, AMBER, TEAL, MUTED, PURPLE
from dashboard.api_client import get_cooccurrence

st.set_page_config(page_title="Co-occurrence · Skill Tracker", page_icon="🕸", layout="wide")
apply_theme()

st.markdown("# 🕸 Skill Co-occurrence")
st.caption("Which skills always appear together? Built using association rule mining (lift score).")
st.divider()

# ── Controls ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
with c1:
    min_lift = st.slider("Min lift score", 1.0, 5.0, 1.2, step=0.1,
                         help="Lift > 2.0 means skills co-occur 2× more than by chance")
with c2:
    category = st.selectbox("Filter category", ["all", "ml_concept", "framework", "language", "cloud", "database"])
with c3:
    limit = st.slider("Max pairs", 10, 80, 30)

pairs = get_cooccurrence(
    limit=limit,
    min_lift=min_lift,
    category=None if category == "all" else category,
)

if not pairs:
    st.info("No skill combinations meet the current lift threshold. Decrease the minimum lift score to view more results.")
    st.stop()

df = pd.DataFrame(pairs)

# ── Summary ───────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Pairs Found", len(df))
c2.metric("Strongest Lift", f"{df['lift'].max():.2f}" if not df.empty else "—")
c3.metric("Avg Confidence A→B", f"{df['confidence_a_to_b'].mean():.1f}%" if not df.empty else "—")

st.divider()

left, right = st.columns([1.2, 1], gap="large")

# ── Network graph ─────────────────────────────────────────────────────────────
with left:
    st.markdown("### Skill Relationship Network")
    st.caption("Node size = job count  ·  Edge thickness = lift score")

    G = nx.Graph()
    for _, row in df.iterrows():
        G.add_edge(row["skill_a"], row["skill_b"], weight=row["lift"], support=row["support"])

    # Spring layout
    pos = nx.spring_layout(G, k=2.5, seed=42)

    edge_traces = []
    for edge in G.edges(data=True):
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        lift = edge[2].get("weight", 1.0)
        opacity = min(0.9, 0.2 + lift * 0.15)
        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(width=max(0.5, lift * 0.8), color=f"rgba(46,196,182,{opacity:.2f})"),
            hoverinfo="none",
        ))

    node_x = [pos[n][0] for n in G.nodes()]
    node_y = [pos[n][1] for n in G.nodes()]
    node_labels = list(G.nodes())
    node_degrees = [G.degree(n) for n in G.nodes()]

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_labels,
        textposition="top center",
        textfont=dict(family="DM Mono", size=9, color="#96918a"),
        marker=dict(
            size=[8 + d * 4 for d in node_degrees],
            color=node_degrees,
            colorscale=[[0, "#1a1a2e"], [0.5, PURPLE], [1.0, AMBER]],
            line=dict(width=1, color="#1e1e2e"),
        ),
        hovertemplate="<b>%{text}</b><br>Connections: %{marker.size}<extra></extra>",
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    # fig.update_layout(
    #     **PLOTLY_THEME,
    #     height=420,
    #     showlegend=False,
    #     xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    #     yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    #     hovermode="closest",
    # )
    layout_config = {
        **PLOTLY_THEME,
        "height": 420,
        "showlegend": False,
        "hovermode": "closest",
    }
    layout_config["xaxis"] = dict(showgrid=False, zeroline=False, showticklabels=False)
    layout_config["yaxis"] = dict(showgrid=False, zeroline=False, showticklabels=False)
    fig.update_layout(**layout_config)
    st.plotly_chart(fig, use_container_width=True)

# ── Lift scatter ──────────────────────────────────────────────────────────────
with right:
    st.markdown("### Support vs Lift")
    st.caption("High lift + high support = strong, common pairing")

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df["support"],
        y=df["lift"],
        mode="markers+text",
        text=[f"{a}+{b}" for a, b in zip(df["skill_a"], df["skill_b"])],
        textposition="top center",
        textfont=dict(family="DM Mono", size=8, color=MUTED),
        marker=dict(
            size=df["co_occurrence_count"].clip(3, 30),
            color=df["lift"],
            colorscale=[[0, "#1a1a2e"], [0.5, TEAL], [1.0, AMBER]],
            showscale=True,
            colorbar=dict(title="Lift", tickfont=dict(size=9, color=MUTED)),
            line=dict(width=0),
        ),
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Support: %{x:.1f}%<br>"
            "Lift: %{y:.2f}<br>"
            "Co-occurrences: %{marker.size}<extra></extra>"
        ),
    ))
    # Reference line: lift = 1.0 (random)
    fig2.add_hline(y=1.0, line_dash="dot", line_color="#2a2a3e",
                   annotation_text="lift=1 (random)", annotation_font_size=9)
    # fig2.update_layout(
    #     **PLOTLY_THEME,
    #     height=420,
    #     xaxis=dict(**PLOTLY_THEME["xaxis"], title="Support (%)", ticksuffix="%"),
    #     yaxis=dict(**PLOTLY_THEME["yaxis"], title="Lift"),
    # )
    layout_config = {
        **PLOTLY_THEME,
        "height": 420,
    }
    layout_config["xaxis"] = dict(**PLOTLY_THEME["xaxis"], title="Support (%)", ticksuffix="%")
    layout_config["yaxis"] = dict(**PLOTLY_THEME["yaxis"], title="Lift")
    fig2.update_layout(**layout_config)
    st.plotly_chart(fig2, use_container_width=True)

# ── Table ─────────────────────────────────────────────────────────────────────
st.markdown("### Pair Detail Table")
display = df[["skill_a", "skill_b", "co_occurrence_count", "support",
              "confidence_a_to_b", "confidence_b_to_a", "lift", "strength_label"]].copy()
display.columns = ["Skill A", "Skill B", "Co-occurs", "Support %",
                   "A→B conf%", "B→A conf%", "Lift", "Strength"]
st.dataframe(display, use_container_width=True, hide_index=True, height=320)
