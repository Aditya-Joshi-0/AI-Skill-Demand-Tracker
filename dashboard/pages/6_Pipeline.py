"""
dashboard/pages/6_Pipeline.py
───────────────────────────────
Trigger the ingestion pipeline from the UI.
Shows live status and results.
"""

import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.styles import apply_theme
from dashboard.api_client import get_health, trigger_ingest

st.set_page_config(page_title="Pipeline · Skill Tracker", page_icon="⚙️", layout="wide")
apply_theme()

st.markdown("# ⚙️ Pipeline Control")
st.caption("Manually trigger ingestion or check scheduler status")
st.divider()

# ── Current status ────────────────────────────────────────────────────────────
health = get_health()
if health:
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Jobs", f"{health.get('total_jobs', 0):,}")
    c2.metric("Unique Skills", f"{health.get('unique_skills', 0):,}")
    c3.metric("Last Fetch", health.get("latest_fetch", "—")[:10] if health.get("latest_fetch") else "Never")

st.divider()

# ── Manual trigger ────────────────────────────────────────────────────────────
st.markdown("### Run Pipeline Now")

col1, col2 = st.columns(2)
with col1:
    sources = st.multiselect(
        "Sources to fetch from",
        ["hackernews", "remoteok", "arbeitnow"],
        default=["hackernews", "remoteok", "arbeitnow"],
    )
with col2:
    max_jobs = st.slider("Max jobs per source", 5, 100, 25)

st.caption("⚠️ This will make live API calls and consume LLM tokens.")

if st.button("▶ Run Ingestion Now", type="primary"):
    with st.spinner("Pipeline running... (this takes 30-90 seconds)"):
        result = trigger_ingest(sources=sources or None, max_jobs=max_jobs)

    if result:
        st.success("Pipeline complete!")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Fetched",      result.get("total_fetched", 0))
        c2.metric("New Jobs",     result.get("new_jobs_saved", 0))
        c3.metric("Duplicates",   result.get("duplicate_jobs", 0))
        c4.metric("Duration",     f"{result.get('duration_seconds', 0):.1f}s")

        if result.get("by_source"):
            st.markdown("**By source:**")
            for src, count in result["by_source"].items():
                st.markdown(f"- `{src}`: {count} jobs")

        if result.get("errors"):
            st.warning("Some errors occurred:")
            for err in result["errors"]:
                st.code(err)

        # Clear cache so dashboard reflects new data
        st.cache_data.clear()
        st.info("Cache cleared — navigate to any page to see updated data.")

st.divider()
st.markdown("### Scheduler")
st.info("The data pipeline runs automatically each day at midnight IST. Check back tomorrow for fresh insights.")
