# ui/service_history.py — Service History & Warnings tab
from __future__ import annotations
import logging
import streamlit as st
import pandas as pd
from datetime import date

from core.config import SERVICE_INTERVAL_KM
from core.database import get_connection

logger = logging.getLogger(__name__)


def render_service_history_tab(conn) -> None:
    """Render the Service History & Warnings tab."""
    st.markdown("### 🔧 Service History & Warnings")

    try:
        trucks_svc = pd.read_sql_query(
            """SELECT truck_id, registration, mileage, last_service_km,
                      service_interval, service_warning_active,
                      service_warning_date, last_maintenance_date
               FROM Truck""",
            conn,
        )
    except Exception as e:
        logger.error("service_history: failed to load trucks: %s", e)
        st.error(f"❌ Could not load fleet data: {e}")
        return

    if trucks_svc.empty:
        st.info("No trucks registered.")
        return

    # ── Active service warnings ───────────────────────────────────────────────
    active_warnings = trucks_svc[trucks_svc["service_warning_active"].fillna(0).astype(int) == 1]
    if not active_warnings.empty:
        st.markdown("#### ⚠️ Active Service Warnings")
        for _, tw in active_warnings.iterrows():
            svc_gap = float(tw["mileage"]) - float(tw["last_service_km"])
            svc_int = float(tw.get("service_interval") or SERVICE_INTERVAL_KM)
            st.markdown(
                f"""<div style="background:rgba(127,29,29,0.25);border-left:5px solid #dc2626;
                            border-radius:10px;padding:14px;margin-bottom:10px;">
                    <span style="font-size:18px;">⚠️</span>
                    <b style="font-size:16px;color:#fca5a5;"> SERVICE DUE — {tw['registration']}</b><br>
                    <span style="color:#fcd34d;">Driven {svc_gap:,.0f} km since last service
                    · Interval: {svc_int:,.0f} km</span><br>
                    <span style="color:#94a3b8;font-size:12px;">
                    Warning triggered: {tw.get('service_warning_date') or '—'}
                    · Current odometer: {float(tw['mileage']):,.0f} km</span>
                </div>""",
                unsafe_allow_html=True,
            )

            if st.button(f"✅ Clear Warning — {tw['registration']}",
                         key=f"clr_warn_{tw['truck_id']}", type="primary"):
                st.session_state[f"clearing_{tw['truck_id']}"] = True

            if st.session_state.get(f"clearing_{tw['truck_id']}"):
                st.markdown(f"**Confirm service completion for {tw['registration']}:**")
                with st.form(f"clear_svc_form_{tw['truck_id']}"):
                    cl1, cl2 = st.columns(2)
                    with cl1:
                        svc_date     = st.date_input("Service Date", value=date.today(),
                                                     key=f"svc_date_{tw['truck_id']}")
                        svc_odometer = st.number_input("Odometer at Service (km)", min_value=0.0,
                                                       value=float(tw["mileage"]),
                                                       key=f"svc_odo_{tw['truck_id']}")
                        svc_cost     = st.number_input("Service Cost (E)", min_value=0.0, value=0.0,
                                                       key=f"svc_cost_{tw['truck_id']}")
                    with cl2:
                        svc_type = st.selectbox(
                            "Service Type",
                            ["Full Service", "Oil Change", "Tyre Rotation",
                             "Brake Service", "Major Overhaul", "Other"],
                            key=f"svc_type_{tw['truck_id']}",
                        )
                        svc_tech = st.text_input("Technician / Workshop",
                                                 key=f"svc_tech_{tw['truck_id']}")
                        svc_desc = st.text_area("Work Performed",
                                                key=f"svc_desc_{tw['truck_id']}", height=80)
                    if st.form_submit_button("✅ Confirm Service Done & Clear Warning", type="primary"):
                        try:
                            cursor = conn.cursor()
                            cursor.execute(
                                """UPDATE Truck SET service_warning_active=0,
                                   last_service_km=?, last_maintenance_date=?
                                   WHERE truck_id=?""",
                                (svc_odometer, str(svc_date), tw["truck_id"]),
                            )
                            cursor.execute(
                                """UPDATE ServiceWarning
                                   SET cleared=1, cleared_date=?, cleared_by=?, notes=?
                                   WHERE truck_id=? AND cleared=0""",
                                (str(svc_date), svc_tech or "Logged by user", svc_desc, tw["truck_id"]),
                            )
                            cursor.execute(
                                """INSERT INTO MaintenanceLog
                                   (truck_id, date, description, cost, odometer,
                                    service_type, technician, notes)
                                   VALUES (?,?,?,?,?,?,?,?)""",
                                (
                                    tw["truck_id"], str(svc_date), svc_desc or svc_type,
                                    svc_cost, svc_odometer, svc_type, svc_tech,
                                    "Service warning cleared",
                                ),
                            )
                            conn.commit()
                            del st.session_state[f"clearing_{tw['truck_id']}"]
                            st.success(f"✅ Service warning cleared for **{tw['registration']}**.")
                            st.rerun()
                        except Exception as e:
                            logger.error("service_history: clear warning failed: %s", e)
                            st.error(f"❌ Could not clear warning: {e}")
    else:
        st.success("✅ No active service warnings. All trucks are up to date.")

    st.divider()

    # ── Fleet service health bars ─────────────────────────────────────────────
    st.markdown("#### ▣ Fleet Service Health")
    for _, tr in trucks_svc.iterrows():
        svc_gap = float(tr["mileage"]) - float(tr["last_service_km"])
        svc_int = float(tr.get("service_interval") or SERVICE_INTERVAL_KM)
        svc_pct = min(100, (svc_gap / svc_int) * 100) if svc_int > 0 else 0
        bar_col   = "#10b981" if svc_pct < 60 else "#f59e0b" if svc_pct < 90 else "#dc2626"
        warn_icon = "⚠️" if svc_pct >= 90 else "●" if svc_pct >= 60 else "●"
        st.markdown(
            f"""<div style="margin:8px 0;padding:12px;background:rgba(255,255,255,0.04);
                    border-radius:10px;border:1px solid rgba(255,255,255,0.08);">
                <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                    <b>{warn_icon} {tr['registration']}</b>
                    <span style="color:{bar_col};font-weight:bold;">{svc_pct:.0f}% of interval used</span>
                </div>
                <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">
                    Last service: {float(tr['last_service_km']):,.0f} km ·
                    Current: {float(tr['mileage']):,.0f} km ·
                    Since last: {svc_gap:,.0f} km · Interval: {svc_int:,.0f} km ·
                    Last maintenance: {tr.get('last_maintenance_date') or '—'}
                </div>
                <div style="background:#374151;border-radius:6px;height:12px;">
                    <div style="background:{bar_col};width:{svc_pct:.0f}%;
                                height:12px;border-radius:6px;"></div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Log manual service record ─────────────────────────────────────────────
    st.markdown("#### ➕ Log Service / Maintenance Record")
    with st.form("manual_maint_form"):
        m1, m2 = st.columns(2)
        with m1:
            mnt_truck = st.selectbox("Truck", trucks_svc["registration"], key="mnt_truck_sel")
            mnt_tid   = int(trucks_svc[trucks_svc["registration"] == mnt_truck]["truck_id"].iloc[0])
            mnt_date  = st.date_input("Service Date", value=date.today())
            mnt_odo   = st.number_input(
                "Odometer (km)", min_value=0.0,
                value=float(trucks_svc[trucks_svc["registration"] == mnt_truck]["mileage"].iloc[0]),
            )
            mnt_cost  = st.number_input("Cost (E)", min_value=0.0, value=0.0)
        with m2:
            mnt_type = st.selectbox(
                "Service Type",
                ["Full Service", "Oil Change", "Tyre Rotation", "Brake Service",
                 "Major Overhaul", "Tyre Replacement", "Electrical", "Body Work", "Other"],
            )
            mnt_tech = st.text_input("Technician / Workshop")
            mnt_desc = st.text_area("Description of Work", height=80)
            update_svc_km = st.checkbox("Update truck's last service odometer", value=True)

        if st.form_submit_button("💾 Save Maintenance Record", type="primary"):
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO MaintenanceLog
                       (truck_id, date, description, cost, odometer, service_type, technician)
                       VALUES (?,?,?,?,?,?,?)""",
                    (mnt_tid, str(mnt_date), mnt_desc or mnt_type, mnt_cost, mnt_odo, mnt_type, mnt_tech),
                )
                if update_svc_km:
                    cursor.execute(
                        """UPDATE Truck SET last_service_km=?, last_maintenance_date=?,
                           service_warning_active=0 WHERE truck_id=?""",
                        (mnt_odo, str(mnt_date), mnt_tid),
                    )
                    cursor.execute(
                        "UPDATE ServiceWarning SET cleared=1, cleared_date=? WHERE truck_id=? AND cleared=0",
                        (str(mnt_date), mnt_tid),
                    )
                conn.commit()
                st.success(f"✅ Maintenance record saved for **{mnt_truck}**.")
                st.rerun()
            except Exception as e:
                logger.error("service_history: save maintenance failed: %s", e)
                st.error(f"❌ Could not save maintenance record: {e}")

    st.divider()

    # ── Full maintenance history ──────────────────────────────────────────────
    st.markdown("#### 📋 Maintenance History Log")
    try:
        all_maint = pd.read_sql_query(
            """SELECT T.registration, M.date, M.service_type, M.description,
                      M.odometer, M.cost, M.technician
               FROM MaintenanceLog M
               JOIN Truck T ON M.truck_id = T.truck_id
               ORDER BY M.date DESC, M.maint_id DESC""",
            conn,
        )
        if not all_maint.empty:
            st.dataframe(all_maint, use_container_width=True, hide_index=True)
            st.metric("Total Maintenance Spend (All Trucks)", f"E {all_maint['cost'].sum():,.2f}")
        else:
            st.info("No maintenance records logged yet.")
    except Exception as e:
        logger.error("service_history: load history failed: %s", e)
        st.error(f"❌ Could not load maintenance history: {e}")

    # ── Warning audit log ─────────────────────────────────────────────────────
    with st.expander("📋 Service Warning Audit Log"):
        try:
            warn_log = pd.read_sql_query(
                """SELECT T.registration, W.warning_type, W.triggered_date,
                          W.triggered_km, W.cleared, W.cleared_date, W.cleared_by
                   FROM ServiceWarning W
                   JOIN Truck T ON W.truck_id = T.truck_id
                   ORDER BY W.triggered_date DESC""",
                conn,
            )
            if not warn_log.empty:
                warn_log["Status"] = warn_log["cleared"].apply(
                    lambda x: "✅ Cleared" if x else "⚠️ Active"
                )
                st.dataframe(warn_log.drop(columns=["cleared"]), use_container_width=True, hide_index=True)
            else:
                st.info("No service warnings have been triggered yet.")
        except Exception as e:
            logger.warning("service_history: warning log query failed: %s", e)
            st.info(f"Warning log unavailable: {e}")
