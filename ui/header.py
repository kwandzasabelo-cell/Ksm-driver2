# ui/header.py — Simplified sidebar navigation and header
from __future__ import annotations
import os
import streamlit as st
from datetime import datetime


def render_header() -> None:
    BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(BASE_DIR, "..", "image_2ff50a.png")
    h1, h2, h3 = st.columns([1, 3, 1])
    with h1:
        if os.path.exists(logo_path):
            try:
                st.image(logo_path, width=150)
            except Exception:
                st.markdown("**KSM**")
    with h2:
        st.markdown(
            "<h1 style='text-align:center;color:#1E3A8A;margin-bottom:0;'>"
            "KSM SMART FREIGHT SOLUTIONS</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center;color:#475569;font-weight:bold;'>"
            "Intelligent Fleet Management · Fuel & Route Optimisation</p>",
            unsafe_allow_html=True,
        )
    with h3:
        now = datetime.now()
        st.markdown(
            f"<div style='text-align:right;'>"
            f"<b>{now.strftime('%d %b %Y')}</b><br>"
            f"<b>⏰ {now.strftime('%H:%M')}</b></div>",
            unsafe_allow_html=True,
        )
        if st.button("↺ Refresh", use_container_width=True):
            st.rerun()
    st.divider()


# ── AI status badge helper ─────────────────────────────────────────────────────
def _ai_badge(ml_risk, fuel_model, trip_count: int) -> None:
    """Single-line AI status — no technical details."""
    risk_ok = ml_risk and getattr(ml_risk, "is_trained", False)
    fuel_ok = fuel_model and getattr(fuel_model, "is_trained", False)

    if risk_ok and fuel_ok:
        st.sidebar.success("◈ AI Predictions: Active")
    else:
        need_risk = max(0, 10 - trip_count)
        need_fuel = max(0, 20 - trip_count)
        need      = max(need_risk, need_fuel)
        if need > 0:
            st.sidebar.info(f"◈ AI activates after {need} more trip(s)")
        else:
            st.sidebar.warning("◈ AI ready — log a trip to activate")


def render_sidebar(ml_risk_predictor, fuel_model) -> str:
    from core.constants import (
        MGR_AUTH_KEY, MGR_USERNAME_KEY, MGR_FULLNAME_KEY,
        AUTH_NAME_KEY, AUTH_USERNAME_KEY, AUTH_STATUS_KEY,
        SIDEBAR_MENU_KEY,
    )

    # ── Manager info + logout ─────────────────────────────────────────────────
    if st.session_state.get(MGR_AUTH_KEY):
        auth_name = st.session_state.get(MGR_FULLNAME_KEY, "Manager")
        auth_user = st.session_state.get(MGR_USERNAME_KEY, "")
        auth_keys = [MGR_AUTH_KEY, MGR_USERNAME_KEY, MGR_FULLNAME_KEY]
    else:
        auth_name = st.session_state.get(AUTH_NAME_KEY, "User")
        auth_user = st.session_state.get(AUTH_USERNAME_KEY, "")
        auth_keys = [AUTH_STATUS_KEY, AUTH_NAME_KEY, AUTH_USERNAME_KEY]

    st.sidebar.markdown(
        f"""<div style="background:rgba(37,99,235,0.2);border:1px solid rgba(96,165,250,0.3);
                border-radius:10px;padding:10px 14px;margin-bottom:8px;">
            <div style="color:#93c5fd;font-size:11px;text-transform:uppercase;letter-spacing:1px;">
                Fleet Manager</div>
            <div style="color:#e0f2fe;font-weight:700;font-size:15px;">🔧 {auth_name}</div>
            <div style="color:#64748b;font-size:11px;">@{auth_user}</div>
        </div>""",
        unsafe_allow_html=True,
    )
    if st.sidebar.button("🔓 Sign Out", use_container_width=True, key="logout_btn"):
        for k in auth_keys:
            st.session_state.pop(k, None)
        st.rerun()

    st.sidebar.divider()

    # ── Simplified navigation ─────────────────────────────────────────────────
    st.sidebar.markdown("**Menu**")

    # Main actions — always visible
    main_pages = {
        "◈ Dashboard":      "Dashboard",
        "↗ Log Trip":       "Unified Logistics",
        "◉ Log Fuel":       "Fuel Tracking",
        "▣ My Fleet":       "Truck Management",
        "▦ Reports":        "Advanced Analytics",
        "◎ Statement":      "Statement of Account",
    }

    # Settings — collapsed by default
    settings_pages = {
        "◫ User Management":  "User Management",
        "↑ Market Intel":     "Market Intel",
    }

    # Determine current choice
    current = st.session_state.get(SIDEBAR_MENU_KEY, "Dashboard")

    # Map display labels back to page names
    all_display = {**main_pages, **settings_pages}
    display_to_page = all_display
    page_to_display = {v: k for k, v in all_display.items()}

    # Render main nav buttons
    for label, page in main_pages.items():
        is_active = current == page
        btn_type  = "primary" if is_active else "secondary"
        if st.sidebar.button(label, key=f"nav_{page}", use_container_width=True,
                             type=btn_type):
            st.session_state[SIDEBAR_MENU_KEY] = page
            st.rerun()

    # Settings expander
    with st.sidebar.expander("⊙ Settings & Admin"):
        for label, page in settings_pages.items():
            is_active = current == page
            if st.sidebar.button(label, key=f"nav_{page}", use_container_width=True,
                                 type="primary" if is_active else "secondary"):
                st.session_state[SIDEBAR_MENU_KEY] = page
                st.rerun()

        # ORS key — tucked away in settings
        st.markdown("Route API Key")
        ors_key = st.text_input(
            "OpenRouteService Key",
            value=st.session_state.get("ors_api_key", ""),
            type="password",
            help="Free at openrouteservice.org — enables live HGV routing.",
            label_visibility="collapsed",
            placeholder="ORS API key (optional)",
        )
        if ors_key:
            st.session_state["ors_api_key"] = ors_key

        # Gemini key
        st.markdown("Gemini AI Key")
        from core.constants import GEMINI_API_KEY
        from core.secrets import gemini_api_key
        gem_val = st.session_state.get(GEMINI_API_KEY) or gemini_api_key() or ""
        gem_key = st.text_input(
            "Gemini Key",
            value=gem_val,
            type="password",
            label_visibility="collapsed",
            placeholder="Gemini API key (optional)",
        )
        if gem_key:
            st.session_state[GEMINI_API_KEY] = gem_key

    st.sidebar.divider()

    # ── AI status + silent auto-train ─────────────────────────────────────────
    try:
        from core.database import get_connection
        import pandas as pd
        conn       = get_connection()
        trip_count = int(pd.read_sql_query(
            "SELECT COUNT(*) as c FROM Trip WHERE fuel_consumed > 0", conn
        ).iloc[0]["c"])
        conn.close()
    except Exception:
        trip_count = 0

    # Silent auto-train when thresholds are met
    _auto_done = st.session_state.get("_models_auto_trained", False)
    if not _auto_done:
        from utils.helpers import retrain_risk_model, retrain_fuel_model
        trained_any = False
        if trip_count >= 10 and not getattr(ml_risk_predictor, "is_trained", False):
            retrain_risk_model(ml_risk_predictor)
            trained_any = True
        if trip_count >= 20 and not getattr(fuel_model, "is_trained", False):
            retrain_fuel_model(fuel_model)
            trained_any = True
        if trained_any:
            st.session_state["_models_auto_trained"] = True
            st.toast("◈ AI predictions are now active!", icon="✅")

    _ai_badge(ml_risk_predictor, fuel_model, trip_count)

    return st.session_state.get(SIDEBAR_MENU_KEY, "Dashboard")
