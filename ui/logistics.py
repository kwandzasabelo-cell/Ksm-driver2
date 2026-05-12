# ui/logistics.py — Unified Logistics shell (thin router)
# ─────────────────────────────────────────────────────────────────────────────
# All logic lives in:
#   ui/trip_log.py        — Log Completed Trip tab
#   ui/job_feasibility.py — Analyse Job Feasibility tab
#   ui/service_history.py — Service History & Warnings tab
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
import streamlit as st

from core.database import get_connection
from core.constants import NAV_INTENT_KEY

from ui.trip_log        import render_trip_log_tab
from ui.job_feasibility import render_job_feasibility_tab
from ui.service_history import render_service_history_tab

logger = logging.getLogger(__name__)


def unified_logistics_module() -> None:
    st.subheader("▣ Unified Logistics & Trip Management")

    nav_intent = st.session_state.pop(NAV_INTENT_KEY, None)

    tab1, tab2, tab3 = st.tabs([
        "📋 Log Completed Trip",
        "▦ Analyse Job Feasibility",
        "🔧 Service History & Warnings",
    ])

    try:
        conn = get_connection()
    except Exception as e:
        logger.error("logistics: DB connection failed: %s", e)
        st.error(f"❌ Could not connect to database: {e}")
        return

    try:
        with tab1:
            render_trip_log_tab(conn)
        with tab2:
            render_job_feasibility_tab(conn)
        with tab3:
            render_service_history_tab(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass
