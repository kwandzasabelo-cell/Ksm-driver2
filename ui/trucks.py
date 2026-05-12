# ui/trucks.py — Trucks page module
from __future__ import annotations
from utils.error_handler import safe_page
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import math
import logging
import os
import json
import base64
import io
from datetime import datetime, date, timedelta
from PIL import Image as PILImage
from core.hgv_profiles import get_hgv_types, get_profile
from core.config import (
    MAX_PAYLOAD_KG, FUEL_PRICE_DEFAULT, MAINTENANCE_PER_KM,
    BORDER_COST_EACH, SERVICE_INTERVAL_KM, TRUCK_TARE_KG,
    DRIVER_RATE_PER_HR, OPPORTUNITY_COST_HR, INSURANCE_BASE_COST,
    HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD,
    LOCATION_COORDS, VEHICLE_SPEED_PROFILES, SEASONAL_TEMP,
    FUEL_CONSUMPTION_BASE_L_PER_100KM, FUEL_EFFICIENCY_BASE,
)
from core.database import get_connection
from services.market_data import fetch_live_market_data, fetch_weather_for_location, fetch_ors_route
from services.routes import (
    get_route_characteristics, get_routes_for_pair,
    ml_route_advisor, calculate_truck_travel_time,
    estimate_distance, determine_terrain,
    ROUTE_DEFAULTS_LEGACY,
)
from maps.route_map import render_route_map
from utils.helpers import save_uploaded_image


# =============================================================================
# DOCUMENT VAULT — CONFIG & HELPERS
# =============================================================================

# All document types the vault handles.
# db_col = matching column in Truck table for the expiry date (None = stored in
#          TruckDocuments only, not mirrored to a Truck column).
DOC_TYPES: dict[str, dict] = {
    "roadworthy":    {"label": "Roadworthy Certificate",       "icon": "🔧",
                      "db_col": "roadworthy_expiry",      "required": True},
    "cross_border":  {"label": "Cross-Border Permit",          "icon": "🚧",
                      "db_col": "cross_border_permit_expiry", "required": True},
    "insurance":     {"label": "Insurance Disc / Policy",      "icon": "🛡️",
                      "db_col": None,                     "required": True},
    "pdp":           {"label": "PDP (Prof. Driving Permit)",   "icon": "🪪",
                      "db_col": "pdp_expiry",             "required": True},
    "licence_disc":  {"label": "Vehicle Licence Disc",         "icon": "📋",
                      "db_col": "licence_expiry",         "required": True},
    "operating_lic": {"label": "Operating Licence",            "icon": "📄",
                      "db_col": None,                     "required": False},
    "other":         {"label": "Other Document",               "icon": "📎",
                      "db_col": None,                     "required": False},
}

ALERT_DAYS = 30   # Warn this many days before expiry


def _ensure_truck_docs_table(conn: sqlite3.Connection):
    """Create TruckDocuments table if it doesn't exist (safe to call every time)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS TruckDocuments (
            doc_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            truck_id         INTEGER NOT NULL,
            doc_type         TEXT    NOT NULL,
            doc_label        TEXT,
            file_data        BLOB,
            file_name        TEXT,
            mime_type        TEXT,
            expiry_date      TEXT,
            issue_date       TEXT,
            issuing_authority TEXT,
            notes            TEXT,
            uploaded_date    TEXT,
            is_active        INTEGER DEFAULT 1
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tdocs_truck ON TruckDocuments(truck_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tdocs_type  ON TruckDocuments(truck_id, doc_type)")
    conn.commit()


def _doc_status(expiry_str: str | None) -> tuple[str, str, int | None]:
    """Return (hex_colour, status_label, days_remaining).
    days_remaining is None when no expiry date is set.
    """
    if not expiry_str:
        return "#64748b", "No expiry set", None
    try:
        exp = date.fromisoformat(str(expiry_str))
    except ValueError:
        return "#64748b", "Invalid date", None
    today = date.today()
    days  = (exp - today).days
    if days < 0:
        return "#dc2626", f"EXPIRED {abs(days)}d ago", days
    if days <= ALERT_DAYS:
        return "#f59e0b", f"Expires in {days}d", days
    return "#10b981", f"Valid · {days}d left", days


def _save_document(conn, truck_id: int, doc_type: str, doc_label: str,
                   file_bytes: bytes, file_name: str, mime_type: str,
                   expiry_date: str, issue_date: str,
                   issuing_authority: str, notes: str):
    """Deactivate old version and insert new document row."""
    conn.execute(
        "UPDATE TruckDocuments SET is_active=0 WHERE truck_id=? AND doc_type=?",
        (truck_id, doc_type))
    conn.execute("""
        INSERT INTO TruckDocuments
        (truck_id, doc_type, doc_label, file_data, file_name, mime_type,
         expiry_date, issue_date, issuing_authority, notes, uploaded_date, is_active)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,1)
    """, (truck_id, doc_type, doc_label, file_bytes, file_name, mime_type,
          expiry_date or None, issue_date or None,
          issuing_authority, notes, str(date.today())))

    # Mirror expiry to Truck table if a matching column exists
    db_col = DOC_TYPES.get(doc_type, {}).get("db_col")
    if db_col and expiry_date:
        try:
            conn.execute(f"UPDATE Truck SET {db_col}=? WHERE truck_id=?",
                         (expiry_date, truck_id))
        except Exception:
            pass
    conn.commit()


def _get_active_doc(conn, truck_id: int, doc_type: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM TruckDocuments WHERE truck_id=? AND doc_type=? AND is_active=1 "
        "ORDER BY doc_id DESC LIMIT 1",
        (truck_id, doc_type)).fetchone()


def _all_docs_for_truck(conn, truck_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM TruckDocuments WHERE truck_id=? AND is_active=1 ORDER BY doc_type",
        (truck_id,)).fetchall()


# =============================================================================
# COMPLIANCE ALERT BOARD  (shown in Tab 1 for selected truck)
# =============================================================================

def _compliance_alert_board(conn, truck_id: int, registration: str):
    """Render a compact traffic-light compliance panel for one truck."""
    _ensure_truck_docs_table(conn)

    truck_row = conn.execute("SELECT * FROM Truck WHERE truck_id=?", (truck_id,)).fetchone()
    if not truck_row:
        return

    expiring, expired, missing = [], [], []

    for key, meta in DOC_TYPES.items():
        if not meta["required"]:
            continue
        doc = _get_active_doc(conn, truck_id, key)

        # Prefer expiry from TruckDocuments; fall back to Truck column
        expiry_str = None
        if doc:
            expiry_str = doc["expiry_date"]
        if not expiry_str and meta["db_col"]:
            expiry_str = truck_row[meta["db_col"]] if meta["db_col"] in truck_row.keys() else None

        color, label, days = _doc_status(expiry_str)

        if days is None:
            missing.append((meta["icon"], meta["label"]))
        elif days < 0:
            expired.append((meta["icon"], meta["label"], abs(days), color))
        elif days <= ALERT_DAYS:
            expiring.append((meta["icon"], meta["label"], days, color))

    total_issues = len(expired) + len(expiring) + len(missing)
    if total_issues == 0:
        st.success(f"✅ All compliance documents valid for **{registration}**.")
        return

    st.markdown(f"""
    <div style="background:rgba(15,23,42,0.6);border:1px solid rgba(96,165,250,0.2);
                border-radius:14px;padding:16px 20px;margin-bottom:16px;">
        <div style="font-size:0.7rem;font-weight:800;letter-spacing:0.12em;
                    text-transform:uppercase;color:#f59e0b;margin-bottom:10px;">
            ⚠️ Compliance Alerts — {registration}
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;">
    """, unsafe_allow_html=True)

    for icon, lbl, days_ago, _ in expired:
        st.markdown(
            f'<span style="background:rgba(220,38,38,0.25);border:1px solid #dc2626;'
            f'color:#fca5a5;border-radius:20px;padding:4px 12px;font-size:0.75rem;">'
            f'{icon} {lbl} — EXPIRED {days_ago}d ago</span>',
            unsafe_allow_html=True)

    for icon, lbl, days_left, _ in expiring:
        st.markdown(
            f'<span style="background:rgba(245,158,11,0.25);border:1px solid #f59e0b;'
            f'color:#fde68a;border-radius:20px;padding:4px 12px;font-size:0.75rem;">'
            f'{icon} {lbl} — {days_left}d left</span>',
            unsafe_allow_html=True)

    for icon, lbl in missing:
        st.markdown(
            f'<span style="background:rgba(100,116,139,0.25);border:1px solid #64748b;'
            f'color:#cbd5e1;border-radius:20px;padding:4px 12px;font-size:0.75rem;">'
            f'{icon} {lbl} — not uploaded</span>',
            unsafe_allow_html=True)

    st.markdown("</div></div>", unsafe_allow_html=True)
    st.caption("Go to **📄 Document Vault** tab to upload or renew documents.")


# =============================================================================
# DOCUMENT VAULT TAB
# =============================================================================

def _document_vault_tab(conn, trucks_df: pd.DataFrame):
    st.markdown("### 📄 Document Vault")
    st.caption(
        "Store, scan, and manage compliance documents for each truck. "
        "Camera scanning works on any phone or laptop with a camera."
    )

    _ensure_truck_docs_table(conn)

    if trucks_df.empty:
        st.info("No trucks registered yet.")
        return

    # ── Fleet-wide compliance overview ────────────────────────────────────
    with st.expander("🚦 Fleet Compliance Overview", expanded=True):
        overview_rows = []
        for _, tr in trucks_df.iterrows():
            tid  = int(tr["truck_id"])
            reg  = tr["registration"]
            row_data = {"Truck": reg}
            for key, meta in DOC_TYPES.items():
                if not meta["required"]:
                    continue
                doc = _get_active_doc(conn, tid, key)
                expiry = doc["expiry_date"] if doc else (
                    tr.get(meta["db_col"]) if meta["db_col"] else None)
                color, label, _ = _doc_status(expiry)
                row_data[meta["label"]] = label
            overview_rows.append(row_data)

        if overview_rows:
            st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Per-truck document management ────────────────────────────────────
    sel_reg = st.selectbox(
        "🚛 Select Truck to Manage Documents",
        trucks_df["registration"].tolist(),
        key="vault_truck_sel",
    )
    truck_row = trucks_df[trucks_df["registration"] == sel_reg].iloc[0]
    tid       = int(truck_row["truck_id"])

    # One card per document type
    for doc_key, meta in DOC_TYPES.items():
        existing = _get_active_doc(conn, tid, doc_key)

        # Derive current expiry
        current_expiry = None
        if existing:
            current_expiry = existing["expiry_date"]
        if not current_expiry and meta["db_col"]:
            current_expiry = truck_row.get(meta["db_col"])

        color, status_label, days = _doc_status(current_expiry)
        required_badge = (
            '<span style="font-size:0.65rem;color:#f87171;'
            'border:1px solid #f87171;border-radius:8px;'
            'padding:1px 6px;margin-left:6px;">REQUIRED</span>'
            if meta["required"] else ""
        )

        with st.expander(
            f"{meta['icon']} {meta['label']}{' ✅' if days and days > ALERT_DAYS else ' ⚠️' if days is not None and days <= ALERT_DAYS else ' ❌' if days is not None and days < 0 else ' —'}",
            expanded=(days is not None and days <= ALERT_DAYS) or days is None and meta["required"],
        ):
            # Status strip
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">'
                f'<span style="background:{color}22;border:1px solid {color};color:{color};'
                f'border-radius:20px;padding:4px 14px;font-size:0.78rem;font-weight:700;">'
                f'{status_label}</span>'
                f'{required_badge}'
                f'{"<span style=\"font-size:0.75rem;color:#94a3b8;\">Uploaded: " + existing["uploaded_date"] + "</span>" if existing else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Current document preview
            if existing and existing["file_data"]:
                mime = existing["mime_type"] or ""
                if mime.startswith("image/"):
                    try:
                        img_data = base64.b64encode(existing["file_data"]).decode()
                        st.markdown(
                            f'<img src="data:{mime};base64,{img_data}" '
                            f'style="max-width:100%;max-height:320px;border-radius:10px;'
                            f'border:1px solid rgba(96,165,250,0.3);margin-bottom:8px;"/>',
                            unsafe_allow_html=True,
                        )
                    except Exception:
                        pass
                st.download_button(
                    f"⬇️ Download {existing['file_name'] or meta['label']}",
                    data=bytes(existing["file_data"]),
                    file_name=existing["file_name"] or f"{doc_key}_{sel_reg}.bin",
                    mime=mime or "application/octet-stream",
                    key=f"dl_{tid}_{doc_key}",
                )

            st.markdown("---")
            st.markdown("#### Upload New / Replace Document")

            # ── Input method toggle ───────────────────────────────────────
            input_method = st.radio(
                "How to add document",
                ["📁 Upload File", "📷 Scan with Camera"],
                horizontal=True,
                key=f"input_method_{tid}_{doc_key}",
            )

            uploaded_bytes = None
            uploaded_name  = None
            uploaded_mime  = None

            if input_method == "📁 Upload File":
                uploaded_file = st.file_uploader(
                    "Choose file (PDF, JPG, PNG)",
                    type=["pdf", "jpg", "jpeg", "png"],
                    key=f"upload_{tid}_{doc_key}",
                )
                if uploaded_file:
                    uploaded_bytes = uploaded_file.read()
                    uploaded_name  = uploaded_file.name
                    uploaded_mime  = uploaded_file.type

            else:  # Camera scan
                st.info(
                    "📱 **On phone:** tap the button and your rear camera will open. "
                    "Point at the document, take the photo, and press **Save**.\n\n"
                    "💻 **On laptop:** your webcam will open automatically."
                )
                cam_img = st.camera_input(
                    f"Point camera at document and capture",
                    key=f"cam_{tid}_{doc_key}",
                )
                if cam_img:
                    # Streamlit camera_input returns JPEG bytes
                    raw = cam_img.read()
                    # Straighten and compress the captured image
                    try:
                        pil = PILImage.open(io.BytesIO(raw))
                        buf = io.BytesIO()
                        pil.save(buf, format="JPEG", quality=85)
                        uploaded_bytes = buf.getvalue()
                    except Exception:
                        uploaded_bytes = raw
                    uploaded_name = f"{doc_key}_{sel_reg}_{date.today()}.jpg"
                    uploaded_mime = "image/jpeg"
                    # Show live preview of captured scan
                    b64_prev = base64.b64encode(uploaded_bytes).decode()
                    st.markdown(
                        f'<img src="data:image/jpeg;base64,{b64_prev}" '
                        f'style="max-width:100%;max-height:280px;border-radius:10px;'
                        f'border:2px solid #10b981;margin:6px 0;"/>',
                        unsafe_allow_html=True,
                    )
                    st.success("✅ Image captured. Fill in the details below and press Save.")

            # ── Document metadata ─────────────────────────────────────────
            m1, m2, m3 = st.columns(3)
            with m1:
                new_expiry = st.date_input(
                    "Expiry Date",
                    value=(date.fromisoformat(str(current_expiry))
                           if current_expiry else date.today() + timedelta(days=365)),
                    key=f"exp_{tid}_{doc_key}",
                )
            with m2:
                new_issue = st.date_input(
                    "Issue Date",
                    value=(date.fromisoformat(str(existing["issue_date"]))
                           if existing and existing["issue_date"] else date.today()),
                    key=f"iss_{tid}_{doc_key}",
                )
            with m3:
                new_authority = st.text_input(
                    "Issuing Authority",
                    value=existing["issuing_authority"] if existing else "",
                    placeholder="e.g. RTMSA, RSSA",
                    key=f"auth_{tid}_{doc_key}",
                )
            new_notes = st.text_input(
                "Notes (optional)",
                value=existing["notes"] if existing else "",
                placeholder="e.g. Renewed after inspection at Oshoek",
                key=f"notes_{tid}_{doc_key}",
            )

            # ── Save ─────────────────────────────────────────────────────
            save_col, _ = st.columns([1, 3])
            with save_col:
                if st.button(f"💾 Save {meta['label']}", key=f"save_{tid}_{doc_key}",
                              type="primary", use_container_width=True):
                    if uploaded_bytes is None and existing is None:
                        st.error("Please upload a file or scan a document first.")
                    else:
                        # If no new file provided, keep existing file bytes
                        file_bytes = uploaded_bytes if uploaded_bytes else bytes(existing["file_data"])
                        file_name  = uploaded_name  if uploaded_name  else (existing["file_name"] or f"{doc_key}.bin")
                        mime_type  = uploaded_mime  if uploaded_mime  else (existing["mime_type"]  or "application/octet-stream")
                        _save_document(
                            conn, tid, doc_key, meta["label"],
                            file_bytes, file_name, mime_type,
                            str(new_expiry), str(new_issue),
                            new_authority, new_notes,
                        )
                        st.success(f"✅ {meta['label']} saved! Expiry: **{new_expiry}**")
                        st.rerun()

            # History
            history = conn.execute(
                "SELECT uploaded_date, expiry_date, file_name, issuing_authority "
                "FROM TruckDocuments WHERE truck_id=? AND doc_type=? ORDER BY doc_id DESC LIMIT 5",
                (tid, doc_key)).fetchall()
            if history and len(history) > 1:
                with st.expander("📜 Version history"):
                    for h in history:
                        st.markdown(
                            f'<div style="font-size:0.75rem;color:#94a3b8;padding:2px 0;">'
                            f'Uploaded: <b style="color:#e2e8f0;">{h["uploaded_date"]}</b> &nbsp;|&nbsp; '
                            f'Expiry: <b style="color:#e2e8f0;">{h["expiry_date"] or "—"}</b> &nbsp;|&nbsp; '
                            f'{h["file_name"] or "—"} &nbsp;|&nbsp; {h["issuing_authority"] or "—"}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )


# =============================================================================
# MAIN MODULE
# =============================================================================

@safe_page
def truck_management_module():
    st.subheader("🚛 Fleet Registry & Information Control")
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 View & Edit Fleet",
        "➕ Register New Truck",
        "🪪 Driver Management",
        "📄 Document Vault",
    ])
    conn = get_connection()

    # ── TAB 1: VIEW & EDIT ────────────────────────────────────────────────
    with tab1:
        try:
            df = pd.read_sql_query("SELECT * FROM Truck", conn)
            if df.empty:
                st.info("No trucks registered yet.")
                conn.close()
                return

            truck_regs   = df["registration"].tolist()
            selected_reg = st.selectbox("🚛 Select Truck to View Full Record", truck_regs,
                                         key="fleet_view_selector")
            truck    = df[df["registration"] == selected_reg].iloc[0]
            tid_view = int(truck["truck_id"])

            # ── COMPLIANCE ALERT BOARD ────────────────────────────────────
            _compliance_alert_board(conn, tid_view, selected_reg)

            # ── Pull live aggregated stats ────────────────────────────────
            month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
            year_start  = datetime.now().replace(month=1, day=1).strftime("%Y-%m-%d")

            fuel_month = pd.read_sql_query(
                "SELECT COALESCE(SUM(fuel_added),0) as f, COALESCE(SUM(total_cost),0) as c FROM FuelConsumption WHERE truck_id=? AND date>=?",
                conn, params=(tid_view, month_start)).iloc[0]
            fuel_year = pd.read_sql_query(
                "SELECT COALESCE(SUM(fuel_added),0) as f, COALESCE(SUM(total_cost),0) as c FROM FuelConsumption WHERE truck_id=? AND date>=?",
                conn, params=(tid_view, year_start)).iloc[0]
            fuel_all = pd.read_sql_query(
                "SELECT COALESCE(SUM(fuel_added),0) as f, COALESCE(SUM(total_cost),0) as c FROM FuelConsumption WHERE truck_id=?",
                conn, params=(tid_view,)).iloc[0]
            trips_all = pd.read_sql_query(
                """SELECT COALESCE(COUNT(*),0) as n, COALESCE(SUM(distance),0) as d,
                          COALESCE(SUM(revenue - actual_fuel_cost - fuel_refill_cost),0) as p
                   FROM Trip WHERE truck_id=? AND revenue > 0""",
                conn, params=(tid_view,)).iloc[0]
            trips_year = pd.read_sql_query(
                """SELECT COALESCE(SUM(revenue - actual_fuel_cost - fuel_refill_cost),0) as p,
                          COALESCE(COUNT(*),0) as n
                   FROM Trip WHERE truck_id=? AND date>=? AND revenue > 0""",
                conn, params=(tid_view, year_start)).iloc[0]

            tables    = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)["name"].tolist()
            maint_all = pd.read_sql_query(
                "SELECT * FROM MaintenanceLog WHERE truck_id=? ORDER BY date DESC",
                conn, params=(tid_view,)) if "MaintenanceLog" in tables else pd.DataFrame()
            maint_spend = float(maint_all["cost"].sum()) if not maint_all.empty and "cost" in maint_all.columns else 0.0

            recent_fuel  = pd.read_sql_query(
                "SELECT date, odometer, fuel_added, total_cost, station_location FROM FuelConsumption WHERE truck_id=? ORDER BY date DESC LIMIT 5",
                conn, params=(tid_view,))
            recent_trips = pd.read_sql_query(
                "SELECT date, start_location, end_location, distance, fuel_consumed, weather_condition FROM Trip WHERE truck_id=? ORDER BY date DESC LIMIT 5",
                conn, params=(tid_view,))

            service_gap      = float(truck["mileage"]) - float(truck["last_service_km"])
            service_interval = float(truck.get("service_interval") or SERVICE_INTERVAL_KM)
            service_pct      = min(100, (service_gap / service_interval) * 100)
            service_color    = "#10b981" if service_pct < 60 else "#f59e0b" if service_pct < 90 else "#dc2626"

            truck_status  = str(truck.get("truck_status") or "ACTIVE").upper()
            status_colors = {"ACTIVE": "#22c55e", "MAINTENANCE": "#f59e0b", "OUT_OF_SERVICE": "#dc2626"}
            status_labels = {"ACTIVE": "● ACTIVE", "MAINTENANCE": "🔧 MAINTENANCE", "OUT_OF_SERVICE": "⛔ OUT OF SERVICE"}
            badge_color   = status_colors.get(truck_status, "#22c55e")
            badge_label   = status_labels.get(truck_status, "● ACTIVE")

            # Truck photo
            photo_display = ""
            if truck.get("photo_path") and os.path.exists(truck["photo_path"]):
                try:
                    img        = PILImage.open(truck["photo_path"]).resize((120, 120))
                    img_buffer = io.BytesIO()
                    img.save(img_buffer, format="PNG")
                    img_b64    = base64.b64encode(img_buffer.getvalue()).decode()
                    photo_display = f'<img src="data:image/png;base64,{img_b64}" style="width:120px;height:120px;border-radius:12px;object-fit:cover;border:3px solid rgba(255,255,255,0.3);"/>'
                except Exception as e:
                    logging.warning(f"Could not load truck photo: {e}")
                    photo_display = '<div style="background:rgba(255,255,255,0.15);border-radius:12px;width:120px;height:120px;display:flex;align-items:center;justify-content:center;"><span style="color:rgba(255,255,255,0.4);font-weight:600;">PHOTO</span></div>'
            else:
                photo_display = '<div style="background:rgba(255,255,255,0.15);border-radius:12px;width:120px;height:120px;display:flex;align-items:center;justify-content:center;"><span style="color:rgba(255,255,255,0.4);font-weight:600;">PHOTO</span></div>'

            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 50%,#1e40af 100%);
                        border-radius:18px;padding:28px;color:white;margin-bottom:18px;
                        box-shadow:0 8px 32px rgba(30,58,138,0.45);">
                <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
                    {photo_display}
                    <div>
                        <h2 style="margin:0;font-size:26px;letter-spacing:1px;">{truck["name"] or truck["registration"]}</h2>
                        <p style="margin:4px 0 0 0;font-size:15px;opacity:0.8;">Fleet Record · KSM Smart Freight Solutions</p>
                    </div>
                    <div style="margin-left:auto;text-align:right;">
                        <span style="background:{badge_color};border-radius:20px;padding:5px 14px;font-size:13px;font-weight:bold;">{badge_label}</span>
                    </div>
                </div>
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;">
                    <div style="background:rgba(255,255,255,0.1);border-radius:10px;padding:12px;">
                        <div style="font-size:11px;opacity:0.7;text-transform:uppercase;letter-spacing:1px;">Registration</div>
                        <div style="font-size:20px;font-weight:bold;">{truck["registration"]}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.1);border-radius:10px;padding:12px;">
                        <div style="font-size:11px;opacity:0.7;text-transform:uppercase;letter-spacing:1px;">Chassis Number</div>
                        <div style="font-size:16px;font-weight:bold;font-family:monospace;">{truck["chassis_number"] or "—"}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.1);border-radius:10px;padding:12px;">
                        <div style="font-size:11px;opacity:0.7;text-transform:uppercase;letter-spacing:1px;">Model</div>
                        <div style="font-size:16px;font-weight:bold;">{truck["model"] or "—"}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.1);border-radius:10px;padding:12px;">
                        <div style="font-size:11px;opacity:0.7;text-transform:uppercase;letter-spacing:1px;">Current Driver</div>
                        <div style="font-size:16px;font-weight:bold;">👤 {truck["driver"] or "Unassigned"}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.1);border-radius:10px;padding:12px;">
                        <div style="font-size:11px;opacity:0.7;text-transform:uppercase;letter-spacing:1px;">Odometer</div>
                        <div style="font-size:16px;font-weight:bold;">{float(truck["mileage"]):,.0f} km</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.1);border-radius:10px;padding:12px;">
                        <div style="font-size:11px;opacity:0.7;text-transform:uppercase;letter-spacing:1px;">Registered</div>
                        <div style="font-size:16px;font-weight:bold;">{truck["created_date"] or "—"}</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

            s1, s2, s3, s4, s5, s6 = st.columns(6)
            s1.metric("⛽ Fuel This Month",  f"{float(fuel_month['f']):,.0f} L",  help="Litres from fuel log this calendar month")
            s2.metric("💰 Fuel Cost Month",  f"E {float(fuel_month['c']):,.0f}")
            s3.metric("⛽ Fuel This Year",   f"{float(fuel_year['f']):,.0f} L")
            s4.metric("🗺️ Total Trips",      f"{int(trips_all['n'])}")
            s5.metric("🛣️ Total Distance",   f"{float(trips_all['d']):,.0f} km")
            s6.metric("📈 Total Profit",     f"E {float(trips_all['p']):,.0f}")

            st.divider()

            st.markdown("#### 🔧 Service Health")
            st.markdown(f"""
            <div style="margin:6px 0 12px 0;">
                <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                    <span><b>Last Service:</b> {float(truck['last_service_km']):,.0f} km
                    &nbsp;|&nbsp; <b>Current:</b> {float(truck['mileage']):,.0f} km
                    &nbsp;|&nbsp; <b>Since last service:</b> {service_gap:,.0f} km / {service_interval:,.0f} km interval</span>
                    <span style="color:{service_color};font-weight:bold;">{service_pct:.0f}% used</span>
                </div>
                <div style="background:#374151;border-radius:8px;height:18px;">
                    <div style="background:{service_color};width:{service_pct:.0f}%;height:18px;border-radius:8px;transition:width 0.4s;"></div>
                </div>
                {'<p style="color:#dc2626;font-weight:bold;margin-top:4px;">⚠️ SERVICE OVERDUE — schedule immediately</p>' if service_pct >= 100 else ''}
            </div>""", unsafe_allow_html=True)

            ma, mb = st.columns(2)
            with ma:
                st.markdown("#### 🔧 Maintenance History")
                st.metric("Total Spent on Maintenance", f"E {maint_spend:,.2f}")
                st.caption(f"Last maintenance: **{truck.get('last_maintenance_date') or '—'}**")
                if not maint_all.empty:
                    st.dataframe(
                        maint_all[["date","description","cost"] if "description" in maint_all.columns else maint_all.columns[:4]].head(10),
                        use_container_width=True, hide_index=True)
                else:
                    st.info("No maintenance records logged yet.")
            with mb:
                st.markdown("#### 📈 Profit Summary")
                profit_year = float(trips_year["p"])
                profit_all  = float(trips_all["p"])
                trips_yr_n  = int(trips_year["n"])
                st.metric("Profit This Year",  f"E {profit_year:,.0f}")
                st.metric("All-Time Profit",   f"E {profit_all:,.0f}")
                st.metric("Trips This Year",   f"{trips_yr_n}")
                st.metric("Avg Profit / Trip", f"E {profit_all / max(1, int(trips_all['n'])):,.0f}")

            st.divider()

            fh, th = st.columns(2)
            with fh:
                st.markdown("#### ⛽ Recent Fuel Fill-Ups")
                st.dataframe(recent_fuel,  use_container_width=True, hide_index=True) if not recent_fuel.empty  else st.info("No fuel records yet.")
            with th:
                st.markdown("#### 🗺️ Recent Trips")
                st.dataframe(recent_trips, use_container_width=True, hide_index=True) if not recent_trips.empty else st.info("No trips logged yet.")

            st.divider()
            if st.button(f"✏️ Edit {truck['registration']}", key=f"edit_{truck['truck_id']}"):
                st.session_state["editing_truck"] = truck["truck_id"]

        except Exception as e:
            st.error(f"Error loading fleet: {str(e)}")

        if "editing_truck" in st.session_state:
            try:
                tid  = st.session_state["editing_truck"]
                df_t = pd.read_sql_query("SELECT * FROM Truck WHERE truck_id = ?", conn, params=(tid,))
                if not df_t.empty:
                    truck = df_t.iloc[0]
                    st.markdown("### ✏️ Edit Truck")
                    with st.form("edit_truck_form"):
                        c1, c2 = st.columns(2)
                        with c1:
                            up_mileage = st.number_input("Current Odometer (km)",      value=float(truck["mileage"]))
                            up_service = st.number_input("Last Service Odometer (km)", value=float(truck["last_service_km"]))
                            up_driver  = st.text_input("Assigned Driver",              value=truck["driver"] if truck["driver"] else "")
                            up_status  = st.selectbox("Truck Status",
                                                       ["ACTIVE", "MAINTENANCE", "OUT_OF_SERVICE"],
                                                       index=["ACTIVE", "MAINTENANCE", "OUT_OF_SERVICE"].index(
                                                           str(truck.get("truck_status") or "ACTIVE").upper()
                                                           if str(truck.get("truck_status") or "ACTIVE").upper()
                                                           in ["ACTIVE", "MAINTENANCE", "OUT_OF_SERVICE"] else "ACTIVE"))
                            up_year = st.number_input("Year of Manufacture", min_value=1990, max_value=2030,
                                                       value=int(truck.get("year_of_manufacture") or 2015))
                        with c2:
                            engine_hours = st.number_input("Engine Hours",          value=float(truck.get("engine_hours", 0)))
                            up_fuel_eff  = st.number_input("Baseline Fuel Efficiency (km/L)", min_value=1.0,
                                                            value=float(truck.get("fuel_efficiency_baseline") or FUEL_EFFICIENCY_BASE))
                            up_tank      = st.number_input("Fuel Tank Capacity (L)", min_value=50.0,
                                                            value=float(truck.get("fuel_tank_capacity") or 300))
                            up_interval  = st.number_input("Service Interval (km)",  min_value=1000.0,
                                                            value=float(truck.get("service_interval") or SERVICE_INTERVAL_KM))
                            new_photo    = st.file_uploader("Upload Truck Photo", type=["png","jpg","jpeg"])
                        if st.form_submit_button("Save Changes"):
                            age_years = round((date.today().year - up_year) + (date.today().month - 1) / 12, 1)
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE Truck SET mileage=?, last_service_km=?, driver=?, engine_hours=?,
                                truck_status=?, year_of_manufacture=?, truck_age_years=?,
                                fuel_efficiency_baseline=?, fuel_tank_capacity=?, service_interval=?
                                WHERE truck_id=?
                            """, (up_mileage, up_service, up_driver, engine_hours,
                                  up_status, up_year, age_years,
                                  up_fuel_eff, up_tank, up_interval, tid))
                            if new_photo:
                                path = save_uploaded_image(new_photo, tid)
                                if path:
                                    cursor.execute("UPDATE Truck SET photo_path=? WHERE truck_id=?", (path, tid))
                            conn.commit()
                            st.success("✅ Truck updated!")
                            del st.session_state["editing_truck"]
                            st.rerun()
            except Exception as e:
                st.error(f"Error editing truck: {str(e)}")

    # ── TAB 2: REGISTER NEW TRUCK ─────────────────────────────────────────
    with tab2:
        with st.form("new_truck_form", clear_on_submit=True):
            st.markdown("#### Vehicle Identity")
            c1, c2, c3 = st.columns(3)
            with c1:
                t_reg       = st.text_input("Registration Plate *", placeholder="e.g. SD 123 EZ")
                t_name      = st.text_input("Truck Name / Fleet No.", placeholder="e.g. Unit 01")
                t_chassis   = st.text_input("Chassis Number")
                truck_model = st.text_input("Make & Model", placeholder="e.g. Volvo FH16")
            with c2:
                t_year   = st.number_input("Year of Manufacture", min_value=1990,
                                            max_value=date.today().year, value=2018)
                t_mile   = st.number_input("Opening Odometer (km)", min_value=0.0, step=1000.0)
                t_driver = st.text_input("Assigned Driver (optional)")
                truck_photo = st.file_uploader("Truck Photo", type=["png","jpg","jpeg"])
            with c3:
                hgv_types = get_hgv_types()
                hgv_type  = st.selectbox("HGV Type *", hgv_types,
                    index=hgv_types.index("Superlink — Tautliner") if "Superlink — Tautliner" in hgv_types else 0,
                    help="Selects realistic cost parameters automatically")
                profile = get_profile(hgv_type)

            st.markdown("---")
            st.markdown("**Auto-loaded Cost Profile** *(from HGV type — edit if needed)*")
            pa1, pa2, pa3, pa4 = st.columns(4)
            with pa1:
                fuel_base = st.number_input("Fuel Efficiency (km/L)", min_value=0.5,
                    value=round(100 / profile["fuel_l_per_100km_loaded"], 2), step=0.1)
                t_tank = st.number_input("Fuel Tank (L)", min_value=50.0,
                    value=float(profile.get("fuel_tank_capacity", 300) or 300), step=10.0)
            with pa2:
                t_interval  = st.number_input("Service Interval (km)", min_value=1000.0,
                    value=float(profile["service_interval_km"]), step=1000.0)
                max_payload = st.number_input("Max Payload (kg)", min_value=1000.0,
                    value=float(profile["max_payload_kg"]), step=500.0)
            with pa3:
                tare_kg   = st.number_input("Tare Weight (kg)", min_value=1000.0,
                    value=float(profile["tare_kg"]), step=500.0)
                num_tyres = st.number_input("Number of Tyres", min_value=4, max_value=40,
                    value=int(profile["num_tyres"]), step=2)
            with pa4:
                ins_monthly = st.number_input("Insurance (E/month)", min_value=0.0,
                    value=float(profile["insurance_per_month"]), step=500.0)
                depr_per_km = st.number_input("Depreciation (E/km)", min_value=0.0,
                    value=float(profile["depreciation_per_km"]), step=0.10)

            st.markdown("---")
            with st.expander("💼 Financial Details (optional but recommended)"):
                fb1, fb2, fb3 = st.columns(3)
                with fb1:
                    purchase_price  = st.number_input("Purchase Price (E)", min_value=0.0,
                        value=float(profile["typical_purchase_price"]), step=50000.0)
                    purchase_date   = st.date_input("Purchase Date", value=date.today())
                    finance_balance = st.number_input("Outstanding Finance (E)", min_value=0.0, value=0.0, step=10000.0)
                with fb2:
                    finance_monthly  = st.number_input("Monthly Finance Payment (E)", min_value=0.0, value=0.0, step=500.0)
                    tracker_monthly  = st.number_input("Tracker/Telematics (E/month)", min_value=0.0, value=850.0, step=50.0)
                    licensing_annual = st.number_input("Annual Licensing Cost (E)", min_value=0.0, value=3500.0, step=100.0)
                with fb3:
                    pdp_expiry          = st.date_input("PDP Expiry Date",           value=None)
                    roadworthy_expiry   = st.date_input("Roadworthy Expiry",          value=None)
                    cross_border_expiry = st.date_input("Cross-Border Permit Expiry", value=None)

            submitted = st.form_submit_button("Register Truck", type="primary", use_container_width=True)

        if submitted:
            if not t_reg.strip():
                st.error("Registration plate is required.")
            else:
                try:
                    age_years = round((date.today().year - t_year) + (date.today().month - 1) / 12, 1)
                    cursor    = conn.cursor()
                    cursor.execute("""
                        INSERT INTO Truck
                        (registration, name, chassis_number, starting_mileage, mileage,
                         last_service_km, driver, model, created_date, fuel_efficiency_baseline,
                         fuel_tank_capacity, service_interval, year_of_manufacture, truck_age_years,
                         truck_status, hgv_type, tare_weight_kg, max_payload, insurance_monthly,
                         purchase_price, purchase_date, finance_balance, finance_monthly,
                         tracker_monthly, licensing_annual, pdp_expiry, roadworthy_expiry,
                         cross_border_permit_expiry)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        t_reg.strip().upper(), t_name, t_chassis, t_mile, t_mile, t_mile,
                        t_driver, truck_model, str(date.today()), fuel_base,
                        t_tank, t_interval, t_year, age_years, "ACTIVE",
                        hgv_type, tare_kg, max_payload, ins_monthly,
                        purchase_price, str(purchase_date), finance_balance, finance_monthly,
                        tracker_monthly, licensing_annual,
                        str(pdp_expiry) if pdp_expiry else None,
                        str(roadworthy_expiry) if roadworthy_expiry else None,
                        str(cross_border_expiry) if cross_border_expiry else None,
                    ))
                    tid = cursor.lastrowid
                    if truck_photo:
                        path = save_uploaded_image(truck_photo, tid)
                        if path:
                            cursor.execute("UPDATE Truck SET photo_path=? WHERE truck_id=?", (path, tid))
                    conn.commit()
                    st.toast(f"✅ Truck {t_reg.upper()} registered!", icon="🚚")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Registration plate already exists.")
                except Exception as e:
                    st.error(f"Error registering truck: {e}")

    # ── TAB 3: DRIVER MANAGEMENT ──────────────────────────────────────────
    with tab3:
        st.markdown("### 🪪 Driver Identification & Management")
        st.caption("Manage driver IDs, credentials, assigned routes and certifications.")

        try:
            drivers_df = pd.read_sql_query(
                """SELECT truck_id, registration, driver, driver_id, driver_license,
                          driver_phone, driver_id_number, driver_experience_years,
                          driver_routes, driver_certifications, truck_status, model
                   FROM Truck ORDER BY driver_id""", conn)
        except Exception as e:
            st.error(f"Could not load driver data: {e}")
            conn.close()
            return

        if drivers_df.empty:
            st.info("No trucks/drivers registered yet.")
        else:
            st.markdown("#### Fleet Driver Overview")
            for _, row in drivers_df.iterrows():
                status_c = {"ACTIVE": "#34d399", "MAINTENANCE": "#fbbf24", "OUT_OF_SERVICE": "#f87171"}.get(
                    row.get("truck_status") or "ACTIVE", "#34d399")
                exp    = row.get("driver_experience_years") or 0
                drv_id = row.get("driver_id") or f"KSM-DRV-{int(row['truck_id']):04d}"
                with st.expander(
                    f"🪪 **{drv_id}** — {row.get('driver') or 'Unassigned'}  ·  {row.get('registration')}",
                    expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"""
                        <div style='background:rgba(15,23,42,0.6);border:1px solid rgba(96,165,250,0.2);
                            border-radius:12px;padding:14px 16px;'>
                        <div style='font-size:0.62rem;font-weight:800;letter-spacing:0.12em;
                                    color:#34d399;text-transform:uppercase;margin-bottom:10px;'>Driver ID Card</div>
                        <table style='width:100%;font-size:0.8rem;border-collapse:collapse;'>
                            <tr><td style='color:#94a3b8;padding:3px 0;width:40%;'>Full Name</td>
                                <td style='color:#e2e8f0;font-weight:600;'>{row.get('driver') or '—'}</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>Driver ID</td>
                                <td style='color:#6ee7b7;font-weight:700;font-family:monospace;'>{drv_id}</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>Truck Reg.</td>
                                <td style='color:#93c5fd;font-weight:600;'>{row.get('registration')} — {row.get('model') or ''}</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>Status</td>
                                <td style='color:{status_c};font-weight:700;'>{row.get('truck_status') or 'ACTIVE'}</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>License No.</td>
                                <td style='color:#e2e8f0;'>{row.get('driver_license') or '—'}</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>ID / Passport</td>
                                <td style='color:#e2e8f0;'>{row.get('driver_id_number') or '—'}</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>Phone</td>
                                <td style='color:#e2e8f0;'>{row.get('driver_phone') or '—'}</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>Experience</td>
                                <td style='color:#e2e8f0;'>{exp} yrs</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>Routes</td>
                                <td style='color:#e2e8f0;'>{row.get('driver_routes') or 'All routes'}</td></tr>
                            <tr><td style='color:#94a3b8;padding:3px 0;'>Certifications</td>
                                <td style='color:#e2e8f0;'>{row.get('driver_certifications') or 'Standard'}</td></tr>
                        </table></div>""", unsafe_allow_html=True)
                    with c2:
                        st.markdown("**Edit Driver Details**")
                        tid_edit = int(row["truck_id"])
                        with st.form(f"drv_edit_{tid_edit}", clear_on_submit=False):
                            new_name   = st.text_input("Full Name",                 value=row.get("driver") or "")
                            new_did    = st.text_input("Driver ID (auto-generated)", value=drv_id, disabled=True)
                            new_lic    = st.text_input("License Number",            value=row.get("driver_license") or "")
                            new_id     = st.text_input("National ID / Passport",    value=row.get("driver_id_number") or "")
                            new_ph     = st.text_input("Phone",                     value=row.get("driver_phone") or "", placeholder="+268 7xxx xxxx")
                            new_exp    = st.number_input("Experience (years)", min_value=0, max_value=50,
                                                          value=int(exp), step=1)
                            new_routes = st.text_input("Assigned Routes",          value=row.get("driver_routes") or "",
                                                        placeholder="e.g. Eswatini, South Africa")
                            new_certs  = st.text_input("Certifications",           value=row.get("driver_certifications") or "",
                                                        placeholder="e.g. Hazmat, Cross-border")
                            new_pin    = st.text_input("App PIN (4 digits)", value="", type="password",
                                                        placeholder="Leave blank to keep existing PIN")
                            save_drv   = st.form_submit_button("💾 Save Driver", use_container_width=True, type="primary")

                        if save_drv:
                            try:
                                conn.execute("""
                                    UPDATE Truck SET driver=?, driver_license=?, driver_id_number=?,
                                    driver_phone=?, driver_experience_years=?,
                                    driver_routes=?, driver_certifications=?
                                    WHERE truck_id=?
                                """, (new_name, new_lic, new_id, new_ph, new_exp,
                                      new_routes, new_certs, tid_edit))
                                conn.commit()
                                st.success(f"✅ Driver {drv_id} updated.")
                                if new_pin and len(new_pin) == 4 and new_pin.isdigit():
                                    st.info(f"🔐 PIN set to **{new_pin}** — update `DRIVER_PINS` in `driver_app.py` with `\"{drv_id}\": \"{new_pin}\"`")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error saving: {e}")

            st.markdown("---")
            st.markdown("#### 🔐 Driver Terminal Access Reference")
            st.caption("Share Driver IDs and PINs securely with each driver.")
            pin_data = []
            for _, row in drivers_df.iterrows():
                drv_id = row.get("driver_id") or f"KSM-DRV-{int(row['truck_id']):04d}"
                pin_data.append({
                    "Driver ID":    drv_id,
                    "Name":         row.get("driver") or "Unassigned",
                    "Truck":        row.get("registration") or "—",
                    "Terminal PIN": "Set in driver_app.py",
                })
            st.dataframe(pd.DataFrame(pin_data), use_container_width=True, hide_index=True)
            st.info(
                "**Note:** PINs are managed in `driver_app.py` under `DRIVER_PINS`. "
                "Format: `\"KSM-DRV-XXXX\": \"1234\"`. "
                "The fleet manager override is `FLEET-MGR / ksm2025`.",
                icon="🔐")

    # ── TAB 4: DOCUMENT VAULT ─────────────────────────────────────────────
    with tab4:
        try:
            df_all = pd.read_sql_query("SELECT * FROM Truck", conn)
            _document_vault_tab(conn, df_all)
        except Exception as e:
            st.error(f"Document Vault error: {e}")

    conn.close()
