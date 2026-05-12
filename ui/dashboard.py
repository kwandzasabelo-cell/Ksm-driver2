# ui/dashboard.py — Enhanced Dashboard with KPI cards, alerts, quick actions & exports
from __future__ import annotations
from utils.error_handler import safe_page
import streamlit as st
import pandas as pd
from core.config import SERVICE_INTERVAL_KM
from core.database import get_connection
from core.constants import NAV_OVERRIDE_KEY, SIDEBAR_MENU_KEY
from services.market_data import fetch_live_market_data
from utils.exports import export_buttons


def _get_models():
    return (
        st.session_state.get("ml_risk_predictor"),
        st.session_state.get("fuel_model"),
    )


def _navigate(page: str):
    st.session_state[NAV_OVERRIDE_KEY] = page
    st.session_state[SIDEBAR_MENU_KEY] = page
    st.rerun()


def _kpi_card(label, value, sub="", color="#3b82f6", icon=""):
    return (
        f"<div style='background:linear-gradient(135deg,rgba(15,23,42,0.85),rgba(7,15,40,0.9));"
        f"border:1px solid {color}44;border-radius:14px;padding:16px 18px;"
        f"box-shadow:0 4px 20px rgba(0,0,0,0.3);'>"
        f"<div style='font-size:.63rem;font-weight:700;color:#64748b;letter-spacing:.12em;"
        f"text-transform:uppercase;margin-bottom:6px;'>{icon} {label}</div>"
        f"<div style='font-size:1.55rem;font-weight:900;color:#fff;line-height:1.1;'>{value}</div>"
        f"<div style='font-size:.7rem;color:{color};margin-top:4px;font-weight:600;'>{sub}</div>"
        f"</div>"
    )


def _alert_row(msg, level="warning"):
    cols  = {"error":"#f87171","warning":"#fbbf24","info":"#60a5fa","success":"#34d399"}
    icons = {"error":"🚨","warning":"⚠️","info":"ℹ️","success":"✅"}
    c = cols.get(level, "#fbbf24")
    i = icons.get(level, "⚠️")
    st.markdown(
        f"<div style='border:1px solid {c}44;border-radius:10px;padding:9px 14px;"
        f"margin-bottom:6px;font-size:.82rem;color:{c};background:{c}11;'>{i} {msg}</div>",
        unsafe_allow_html=True,
    )


@safe_page
def dashboard_module():
    st.subheader("◈ Fleet Intelligence Dashboard")
    conn = get_connection()

    # ── Live Market Snapshot ──────────────────────────────────────────────────
    with st.expander("◉ Live Market Snapshot", expanded=False):
        mkt = fetch_live_market_data()
        src_tag = "● Live" if "fallback" not in mkt["source"] else "● Offline"
        st.caption(f"{src_tag} · {mkt['source']} · {mkt['timestamp']}")
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("◉ Fuel Price (est.)", f"E {mkt['fuel_price']:.2f}/L")
        mc2.metric("↔ USD/SZL",          f"{mkt['usd_szl']:.2f}")
        mc3.metric("⛽ WTI Crude Oil",    f"${mkt['crude_usd']:.2f}/bbl")

    # ── Pull data ─────────────────────────────────────────────────────────────
    try:
        fleet_df = pd.read_sql_query("SELECT * FROM Truck", conn)
    except Exception:
        fleet_df = pd.DataFrame()

    try:
        trip_df = pd.read_sql_query("SELECT * FROM Trip ORDER BY date DESC LIMIT 50", conn)
    except Exception:
        trip_df = pd.DataFrame()

    try:
        fq = pd.read_sql_query(
            "SELECT COALESCE(SUM(fuel_added),0) as tf, COALESCE(SUM(total_cost),0) as tc "
            "FROM FuelConsumption", conn)
        total_fuel_l    = float(fq["tf"].iloc[0])
        total_fuel_cost = float(fq["tc"].iloc[0])
    except Exception:
        total_fuel_l = total_fuel_cost = 0.0

    try:
        total_trips = int(pd.read_sql_query("SELECT COUNT(*) as c FROM Trip", conn)["c"].iloc[0])
    except Exception:
        total_trips = 0

    try:
        total_revenue = float(pd.read_sql_query(
            "SELECT COALESCE(SUM(revenue),0) as r FROM Trip WHERE revenue > 0", conn)["r"].iloc[0])
    except Exception:
        total_revenue = 0.0

    active_trucks = len(fleet_df)
    if not fleet_df.empty and "truck_status" in fleet_df.columns:
        try:
            active_trucks = int((fleet_df["truck_status"].str.upper() == "ACTIVE").sum())
        except Exception:
            pass

    ml_risk, fuel_model = _get_models()

    # ── KPI CARDS ─────────────────────────────────────────────────────────────
    st.markdown("### ▦ Fleet Overview")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(_kpi_card("Active Trucks", str(active_trucks),
            f"{len(fleet_df)} total in fleet", "#22c55e", "▣"), unsafe_allow_html=True)
    with k2:
        st.markdown(_kpi_card("Total Trips", f"{total_trips:,}",
            "All time", "#3b82f6", "↗"), unsafe_allow_html=True)
    with k3:
        st.markdown(_kpi_card("Fuel Purchased", f"{total_fuel_l:,.0f} L",
            f"E {total_fuel_cost:,.0f} spend", "#f59e0b", "◉"), unsafe_allow_html=True)
    with k4:
        st.markdown(_kpi_card("Total Revenue", f"E {total_revenue:,.0f}",
            "From completed trips", "#a78bfa", "◎"), unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── QUICK ACTIONS ─────────────────────────────────────────────────────────
    st.markdown("### ▶ Quick Actions")
    qa1, qa2, qa3, qa4 = st.columns(4)
    with qa1:
        if st.button("↗ Log New Trip",    use_container_width=True, type="primary"):
            _navigate("Unified Logistics")
    with qa2:
        if st.button("◉ Log Fuel Fill-Up", use_container_width=True):
            _navigate("Fuel Tracking")
    with qa3:
        if st.button("▣ Manage Fleet",     use_container_width=True):
            _navigate("Truck Management")
    with qa4:
        if st.button("▦ View Analytics",   use_container_width=True):
            _navigate("Advanced Analytics")

    st.divider()

    # ── ALERTS PANEL ──────────────────────────────────────────────────────────
    alerts = []

    if not fleet_df.empty:
        for _, tr in fleet_df.iterrows():
            try:
                svc_gap = float(tr["mileage"]) - float(tr["last_service_km"])
                svc_int = float(tr.get("service_interval") or SERVICE_INTERVAL_KM)
                svc_pct = min(100, (svc_gap / svc_int) * 100) if svc_int > 0 else 0
                reg = tr["registration"]
                if svc_pct >= 100:
                    alerts.append(("error",   f"**{reg}** — SERVICE OVERDUE ({svc_gap:,.0f} km since last service)"))
                elif svc_pct >= 80:
                    alerts.append(("warning", f"**{reg}** — Service due soon ({svc_pct:.0f}% of interval used)"))
                status = str(tr.get("truck_status") or "ACTIVE").upper()
                if status == "MAINTENANCE":
                    alerts.append(("warning", f"**{reg}** is currently in MAINTENANCE"))
                elif status == "OUT_OF_SERVICE":
                    alerts.append(("error",   f"**{reg}** is OUT OF SERVICE"))
            except Exception:
                pass

    try:
        sw = pd.read_sql_query(
            "SELECT sw.*, t.registration FROM ServiceWarning sw "
            "LEFT JOIN Truck t ON sw.truck_id = t.truck_id "
            "WHERE (sw.resolved = 0 OR sw.resolved IS NULL) "
            "ORDER BY sw.triggered_date DESC LIMIT 5", conn)
        for _, w in sw.iterrows():
            alerts.append(("warning",
                f"Service warning: **{w.get('registration','Unknown')}** — "
                f"{w.get('warning_type','')} on {w.get('triggered_date','')}"))
    except Exception:
        pass

    # ── Compliance expiry alerts ───────────────────────────────────────────────
    try:
        from datetime import date, timedelta
        today      = date.today()
        warn_days  = 30
        critical_days = 7
        expiry_checks = [
            ("pdp_expiry",                 "PDP"),
            ("roadworthy_expiry",          "Roadworthy Certificate"),
            ("cross_border_permit_expiry", "Cross-Border Permit"),
        ]
        for col, label in expiry_checks:
            if col not in fleet_df.columns:
                continue
            for _, tr in fleet_df.iterrows():
                val = tr.get(col)
                if not val or str(val) in ("None", "nan", ""):
                    continue
                try:
                    exp_date = date.fromisoformat(str(val)[:10])
                    days_left = (exp_date - today).days
                    reg = tr.get("registration", "Unknown")
                    if days_left < 0:
                        alerts.append(("error",
                            f"**{reg}** — {label} EXPIRED {abs(days_left)} day(s) ago. "
                            f"Do not dispatch until renewed."))
                    elif days_left <= critical_days:
                        alerts.append(("error",
                            f"**{reg}** — {label} expires in {days_left} day(s) ({exp_date})."))
                    elif days_left <= warn_days:
                        alerts.append(("warning",
                            f"**{reg}** — {label} expires in {days_left} day(s) ({exp_date})."))
                except Exception:
                    pass
    except Exception:
        pass

    if not (ml_risk and getattr(ml_risk, "is_trained", False)):
        need = max(0, 10 - total_trips)
        alerts.append(("info", f"Risk ML model inactive — log {need} more trip(s) to enable" if need > 0
                       else "Risk ML model ready to train — click **Train Models** in sidebar"))
    if not (fuel_model and getattr(fuel_model, "is_trained", False)):
        need = max(0, 20 - total_trips)
        alerts.append(("info", f"Fuel ML model inactive — log {need} more trip(s) to enable" if need > 0
                       else "Fuel ML model ready to train — click **Train Models** in sidebar"))

    if alerts:
        st.markdown("### Alerts & Notifications")
        for level, msg in alerts:
            _alert_row(msg, level)
        # Fire external notifications for critical alerts (email/WhatsApp)
        critical = [m for l, m in alerts if l == "error"]
        if critical:
            try:
                from services.notifications import send_alert
                for msg in critical[:2]:  # cap at 2 to avoid spam
                    send_alert("Fleet Alert", msg)
            except Exception:
                pass
        st.divider()

    # ── FLEET STATUS GRID ─────────────────────────────────────────────────────
    if not fleet_df.empty:
        st.markdown("### ▣ Fleet Status")
        cols_per_row = min(len(fleet_df), 4)
        grid_cols = st.columns(cols_per_row)
        for i, (_, tr) in enumerate(fleet_df.iterrows()):
            with grid_cols[i % cols_per_row]:
                status  = str(tr.get("truck_status") or "ACTIVE").upper()
                s_color = {"ACTIVE":"#22c55e","MAINTENANCE":"#f59e0b","OUT_OF_SERVICE":"#f87171"}.get(status,"#22c55e")
                s_label = {"ACTIVE":"● ACTIVE","MAINTENANCE":"🔧 MAINT.","OUT_OF_SERVICE":"⛔ OUT SVC"}.get(status,"● ACTIVE")
                try:
                    svc_gap = float(tr["mileage"]) - float(tr["last_service_km"])
                    svc_int = float(tr.get("service_interval") or SERVICE_INTERVAL_KM)
                    svc_pct = min(100, (svc_gap / svc_int) * 100)
                    bar_c   = "#22c55e" if svc_pct < 60 else ("#f59e0b" if svc_pct < 90 else "#f87171")
                except Exception:
                    svc_pct = 0; bar_c = "#22c55e"

                st.markdown(
                    f"<div style='background:rgba(15,23,42,.8);border:1px solid {s_color}33;"
                    f"border-radius:12px;padding:12px 14px;margin-bottom:8px;'>"
                    f"<div style='font-size:.85rem;font-weight:800;color:#e2e8f0;margin-bottom:3px;'>"
                    f"▣ {tr['registration']}</div>"
                    f"<div style='font-size:.68rem;font-weight:700;color:{s_color};margin-bottom:6px;'>{s_label}</div>"
                    f"<div style='font-size:.65rem;color:#64748b;margin-bottom:2px;'>"
                    f"📍 {float(tr.get('mileage',0)):,.0f} km · {tr.get('driver','—') or '—'}</div>"
                    f"<div style='font-size:.6rem;color:#475569;margin-bottom:3px;'>Service interval</div>"
                    f"<div style='background:rgba(255,255,255,.08);border-radius:4px;height:5px;'>"
                    f"<div style='background:{bar_c};width:{svc_pct:.0f}%;height:5px;border-radius:4px;'></div></div>"
                    f"<div style='font-size:.6rem;color:{bar_c};margin-top:2px;'>{svc_pct:.0f}% used</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        st.divider()

    # ── AI STATUS — simple one liner ──────────────────────────────────────────
    risk_ok = ml_risk and getattr(ml_risk, "is_trained", False)
    fuel_ok = fuel_model and getattr(fuel_model, "is_trained", False)
    if risk_ok and fuel_ok:
        st.success("◈ **AI Predictions Active** — fuel efficiency and risk scoring are live on all trips.")
    else:
        need = max(max(0, 10 - total_trips), max(0, 20 - total_trips))
        if need > 0:
            st.info(f"◈ **AI Predictions** will activate after **{need} more trip(s)** are logged.")
        else:
            st.info("◈ **AI Predictions** are ready — training will start automatically on your next trip.")
    st.divider()

    # ── RECENT TRIPS ──────────────────────────────────────────────────────────
    # ── FLEET OVERVIEW MAP ────────────────────────────────────────────────────
    st.markdown("### Fleet Map")
    try:
        from maps.route_map import render_fleet_overview_map
        with st.expander("View Live Fleet Positions — click to expand", expanded=False):
            render_fleet_overview_map()
    except Exception:
        pass
    st.divider()

    st.markdown("### Recent Trips")
    if not trip_df.empty:
        display_cols = [c for c in ["date","start_location","end_location","distance",
                                     "load","actual_fuel_efficiency","risk_score","revenue"]
                        if c in trip_df.columns]
        st.dataframe(trip_df[display_cols].head(10), use_container_width=True, hide_index=True)
        export_buttons(trip_df[display_cols], "ksm_trips", "Trips")
    else:
        st.info("No trips logged yet. Use **Unified Logistics** to log your first trip.")

    conn.close()
