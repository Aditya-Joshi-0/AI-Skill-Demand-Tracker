"""
dashboard/styles.py
────────────────────
Centralised Streamlit CSS injection.
All pages call apply_theme() once at the top.

Design direction: editorial / data-intelligence
  - Dark background (#0d0d14) with sharp amber/teal accent system
  - Monospace numerics, clean sans-serif labels
  - Feels like a Bloomberg terminal crossed with a modern SaaS tool
"""

import streamlit as st

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Outfit:wght@300;400;500;600&display=swap');

/* ── Root ── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0d0d14 !important;
    color: #e2ddd4 !important;
    font-family: 'Outfit', sans-serif !important;
}

[data-testid="stSidebar"] {
    background-color: #0a0a10 !important;
    border-right: 1px solid #1e1e2e !important;
}

/* ── Headings ── */
h1 { font-family: 'Outfit', sans-serif !important; font-weight: 600 !important;
     font-size: 1.8rem !important; color: #f0ebe3 !important; letter-spacing: -0.03em !important; }
h2 { font-family: 'Outfit', sans-serif !important; font-weight: 500 !important;
     font-size: 1.2rem !important; color: #c8c0b4 !important; }
h3 { font-family: 'Outfit', sans-serif !important; font-weight: 400 !important;
     font-size: 1rem !important; color: #96918a !important; }

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: #13131f !important;
    border: 1px solid #1e1e2e !important;
    border-radius: 10px !important;
    padding: 1rem 1.25rem !important;
}
[data-testid="stMetricLabel"] { font-size: 11px !important; color: #5a5670 !important;
    text-transform: uppercase !important; letter-spacing: 0.08em !important; font-family: 'DM Mono', monospace !important; }
[data-testid="stMetricValue"] { font-family: 'DM Mono', monospace !important; font-size: 1.6rem !important; color: #f0ebe3 !important; }
[data-testid="stMetricDelta"] { font-family: 'DM Mono', monospace !important; font-size: 0.8rem !important; }

/* ── Tabs ── */
[data-testid="stTabs"] button {
    font-family: 'Outfit', sans-serif !important;
    font-size: 13px !important;
    color: #5a5670 !important;
    border-bottom: 2px solid transparent !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #e8a830 !important;
    border-bottom: 2px solid #e8a830 !important;
}

/* ── Selectbox / Input ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] > div > div > input {
    background: #13131f !important;
    border: 1px solid #1e1e2e !important;
    color: #e2ddd4 !important;
    border-radius: 8px !important;
    font-family: 'Outfit', sans-serif !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border: 1px solid #1e1e2e !important; border-radius: 10px !important; }
[data-testid="stDataFrame"] th { background: #13131f !important; color: #5a5670 !important;
    font-family: 'DM Mono', monospace !important; font-size: 11px !important; text-transform: uppercase !important; }
[data-testid="stDataFrame"] td { color: #e2ddd4 !important; font-family: 'DM Mono', monospace !important; font-size: 12px !important; }

/* ── Info / Warning boxes ── */
[data-testid="stInfo"] { background: #0f1a2e !important; border: 1px solid #1a3060 !important; color: #7ab0f0 !important; }
[data-testid="stWarning"] { background: #1a1400 !important; border: 1px solid #3a2e00 !important; }

/* ── Sidebar nav ── */
[data-testid="stSidebarNav"] a { color: #5a5670 !important; font-family: 'Outfit', sans-serif !important; font-size: 14px !important; }
[data-testid="stSidebarNav"] a:hover { color: #e8a830 !important; }

/* ── Divider ── */
hr { border-color: #1e1e2e !important; }

/* ── Spinner ── */
[data-testid="stSpinner"] { color: #e8a830 !important; }

/* ── Plotly chart bg ── */
.js-plotly-plot { border-radius: 10px !important; border: 1px solid #1e1e2e !important; }
</style>
"""

# Plotly theme matching the dark dashboard
PLOTLY_THEME = dict(
    paper_bgcolor="#0d0d14",
    plot_bgcolor="#0d0d14",
    font=dict(family="DM Mono, monospace", color="#96918a", size=11),
    xaxis=dict(gridcolor="#1e1e2e", linecolor="#1e1e2e", zerolinecolor="#1e1e2e"),
    yaxis=dict(gridcolor="#1e1e2e", linecolor="#1e1e2e", zerolinecolor="#1e1e2e"),
    margin=dict(l=40, r=20, t=40, b=40),
)

# Accent colours
AMBER  = "#e8a830"
TEAL   = "#2ec4b6"
RED    = "#e05252"
PURPLE = "#9b8fe8"
MUTED  = "#5a5670"
PURPLE = "#9b8fe8"

def hex_to_rgba(hex_color, alpha=1.0):
    """Convert hex color to rgba format."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"

def apply_theme():
    """Inject CSS theme. Call once at the top of every page."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def stat_card(label: str, value: str, delta: str = "", delta_color: str = "normal"):
    """Render a single metric card."""
    st.metric(label=label, value=value, delta=delta if delta else None, delta_color=delta_color)


def section_header(title: str, subtitle: str = ""):
    """Styled section header with optional subtitle."""
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)
