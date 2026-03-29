"""
dashboard/pages/5_Digest.py
────────────────────────────
Weekly market intelligence digest — LLM-generated narrative.
"""

import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.styles import apply_theme, AMBER, TEAL
from dashboard.api_client import get_digest

st.set_page_config(page_title="Digest · Skill Tracker", page_icon="📰", layout="wide")
apply_theme()

st.markdown("# 📰 Weekly Intelligence Digest")
st.caption("LLM-generated market analysis based on this week's skill demand data")
st.divider()

with st.spinner("Generating digest with LLM..."):
    digest = get_digest()

if not digest:
    st.warning("Digest unavailable. Ensure the API is running with valid LLM keys.")
    st.stop()

# ── Metadata strip ────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Period", digest.get("period", "—"))
c2.metric("Jobs Analysed", f"{digest.get('total_jobs_analysed', 0):,}")
c3.metric("Generated", digest.get("generated_at", "—")[:16].replace("T", " ") + " IST")

st.divider()

# ── Narrative ─────────────────────────────────────────────────────────────────
left, right = st.columns([1.6, 1], gap="large")

with left:
    st.markdown("### Market Intelligence Brief")
    narrative = digest.get("narrative", "")
    if narrative:
        # Render each paragraph with spacing
        for para in narrative.split("\n\n"):
            if para.strip():
                st.markdown(para.strip())
                st.markdown("")

with right:
    st.markdown("### This Week's Signals")

    rising = digest.get("top_rising", [])
    if rising:
        st.markdown("**🔥 Rising**")
        for s in rising[:6]:
            st.markdown(f"- `{s}`")
        st.markdown("")

    falling = digest.get("top_falling", [])
    if falling:
        st.markdown("**↓ Falling**")
        for s in falling[:5]:
            st.markdown(f"- `{s}`")
        st.markdown("")

    new_skills = digest.get("new_skills", [])
    if new_skills:
        st.markdown("**✦ New This Week**")
        for s in new_skills:
            st.markdown(f"- `{s}`")
        st.markdown("")

    top = digest.get("top_skills", [])
    if top:
        st.markdown("**📊 Most In-Demand**")
        for s in top[:8]:
            st.markdown(f"- `{s}`")

st.divider()
st.caption(f"Digest generated at {digest.get('generated_at', '')[:19].replace('T',' ')} IST · "
           "Powered by your configured LLM provider (GPT-4o-mini / Claude Haiku)")
