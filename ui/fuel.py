# ui/fuel.py — Fuel Management & Consumption Tracking
# Redesigned around real GALP receipt format:
#   • Pump number, product type (Diesel 50PPM), card type, driver ID
#   • Station name auto-matched from known network
#   • Odometer read directly from receipt
#   • Fleet card / account payment tracking
from __future__ import annotations
from utils.error_handler import safe_page
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, date, timedelta
from utils.exports import export_buttons

from core.config import (
    MAX_PAYLOAD_KG, FUEL_PRICE_DEFAULT, MAINTENANCE_PER_KM,
    FUEL_EFFICIENCY_BASE, FUEL_CONSUMPTION_BASE_L_PER_100KM,
)
from core.database import get_connection
from services.market_data import fetch_live_market_data

# ── Station network — common Eswatini / cross-border stations ──────────────────
KNOWN_STATIONS = [
    "GALP Manzini",
    "GALP Matsapha",
    "GALP Mbabane",
    "GALP Mhlambanyatsi",
    "Total Matsapha",
    "Total Mbabane",
    "Total Manzini",
    "BP Manzini",
    "BP Matsapha",
    "Engen Manzini",
    "Puma Matsapha",
    "Total Ermelo (ZA)",
    "Total Nelspruit (ZA)",
    "Total Maputo (MZ)",
    "Petromoc Maputo (MZ)",
    "Other / Enter manually",
]

FUEL_PRODUCTS = [
    "Diesel 50PPM",
    "Diesel 500PPM",
    "Petrol 93 ULP",
    "Petrol 95 ULP",
    "Diesel (Generic)",
    "Biofuel",
]

PAYMENT_METHODS = [
    "GALP Frota Card",
    "Fleet Card (generic)",
    "Company Credit Card",
    "EFT / Bank Transfer",
    "Cash",
    "Driver Account",
]


def _section(label: str) -> None:
    st.markdown(
        f"<div style='font-size:0.67rem;font-weight:800;letter-spacing:0.14em;"
        f"text-transform:uppercase;color:#60a5fa;margin:1.1rem 0 0.5rem 0;"
        f"border-bottom:1px solid rgba(96,165,250,0.2);padding-bottom:0.35rem;'>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


@safe_page
def fuel_tracking_module():
    from ui.command_bar import get_fuel_prefill, clear_fuel_prefill
    _pf = get_fuel_prefill() or {}

    st.subheader("◉ Fuel Management & Consumption Tracking")
    conn = get_connection()

    tab1, tab2, tab3, tab4 = st.tabs([
        "◉ Log Fill-Up", "▦ Fleet Dashboard",
        "↑ Efficiency Trends", "🔔 Fuel Alerts"
    ])

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1 — LOG FILL-UP  (redesigned around GALP receipt format)
    # ─────────────────────────────────────────────────────────────────────────
    with tab1:
        st.markdown("### ◉ Record Fuel Fill-Up")
        st.caption(
            "Mirrors GALP station receipts — pump number, product, card type, "
            "driver ID and odometer all captured from the slip."
        )

        try:
            trucks = pd.read_sql_query(
                "SELECT truck_id, registration, mileage, fuel_tank_capacity, driver, driver_id FROM Truck ORDER BY registration",
                conn
            )
            if trucks.empty:
                st.warning("No trucks registered. Add a truck first.")
                conn.close(); return
        except Exception as e:
            st.error(f"Could not load trucks: {e}")
            conn.close(); return

        if _pf:
            st.success(
                "✅ **Document pre-filled this form** — review values and press **Save Fill-Up**.",
                icon="📋",
            )

        # ── Truck selector ─────────────────────────────────────────────────
        _pf_truck = _pf.get("truck_registration")
        _truck_list = list(trucks["registration"])
        _truck_idx = _truck_list.index(_pf_truck) if _pf_truck and _pf_truck in _truck_list else 0

        col_ts1, col_ts2 = st.columns([2, 3])
        with col_ts1:
            sel_truck = st.selectbox("Truck Registration", _truck_list, index=_truck_idx, key="fuel_truck")
        truck_row   = trucks[trucks["registration"] == sel_truck].iloc[0]
        tid         = int(truck_row["truck_id"])
        tank_cap    = float(truck_row.get("fuel_tank_capacity") or 300)
        cur_mileage = float(truck_row.get("mileage") or 0)
        driver_name = truck_row.get("driver") or "—"
        driver_id   = truck_row.get("driver_id") or "—"

        with col_ts2:
            # Driver + odometer info strip
            st.markdown(
                f"<div style='background:rgba(15,23,42,0.55);border:1px solid rgba(96,165,250,0.2);"
                f"border-radius:10px;padding:10px 14px;display:flex;gap:20px;flex-wrap:wrap;margin-top:4px;'>"
                f"<div><div style='font-size:0.6rem;color:#94a3b8;text-transform:uppercase;'>Driver</div>"
                f"<div style='font-size:0.88rem;font-weight:700;color:#e2e8f0;'>{driver_name}</div>"
                f"<div style='font-size:0.67rem;color:#34d399;font-family:monospace;'>{driver_id}</div></div>"
                f"<div><div style='font-size:0.6rem;color:#94a3b8;text-transform:uppercase;'>Odometer (DB)</div>"
                f"<div style='font-size:0.88rem;font-weight:700;color:#60a5fa;font-family:monospace;'>"
                f"{cur_mileage:,.0f} km</div></div>"
                f"<div><div style='font-size:0.6rem;color:#94a3b8;text-transform:uppercase;'>Tank Capacity</div>"
                f"<div style='font-size:0.88rem;font-weight:700;color:#e2e8f0;'>{tank_cap:.0f} L</div></div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Last fill-up for km-since-fill
        try:
            last_fill = pd.read_sql_query(
                "SELECT odometer, fuel_added, date, station_location, cost_per_liter "
                "FROM FuelConsumption WHERE truck_id=? ORDER BY odometer DESC LIMIT 1",
                conn, params=(tid,)
            )
        except Exception:
            last_fill = pd.DataFrame()

        if not last_fill.empty:
            lf = last_fill.iloc[0]
            km_since = cur_mileage - float(lf["odometer"])
            st.markdown(
                f"<div style='background:rgba(5,150,105,0.12);border:1px solid rgba(52,211,153,0.25);"
                f"border-radius:8px;padding:8px 14px;font-size:0.78rem;color:#6ee7b7;margin-bottom:0.5rem;'>"
                f"📋 Last fill-up: <b>{lf['date']}</b> at <b>{lf['station_location'] or 'unknown station'}</b> — "
                f"<b>{lf['fuel_added']:.0f} L</b> @ E{lf['cost_per_liter']:.2f}/L — "
                f"<b>{km_since:,.0f} km</b> since last fill"
                f"</div>",
                unsafe_allow_html=True,
            )

        with st.form("fuel_log_form", clear_on_submit=True):

            # ── Station & receipt ──────────────────────────────────────────
            _section("🏢  Station & Receipt Details  ←  from the slip")
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                # Station dropdown — covers all known network + free entry
                _pf_station = _pf.get("station_name", "")
                _station_idx = next(
                    (i for i, s in enumerate(KNOWN_STATIONS) if _pf_station.lower() in s.lower()),
                    len(KNOWN_STATIONS) - 1
                ) if _pf_station else 0
                station_choice = st.selectbox("Station / Location", KNOWN_STATIONS, index=_station_idx)
                if station_choice == "Other / Enter manually":
                    station_name = st.text_input("Enter Station Name", value=_pf_station,
                                                 placeholder="e.g. Galp Simunye")
                else:
                    station_name = station_choice
            with col_s2:
                fill_date = st.date_input("Fill-Up Date", value=date.today())
            with col_s3:
                pass  # advanced fields moved below
            # Advanced receipt details
            with st.expander("🧾 Receipt Details (optional)"):
                _ac1, _ac2, _ac3 = st.columns(3)
                with _ac1:
                    receipt_number = st.text_input("Receipt / Transaction No.",
                        value=_pf.get("receipt_number", ""), placeholder="e.g. 998877665")
                    pump_number = st.text_input("Pump No.",
                        value=_pf.get("pump_number", ""), placeholder="e.g. 04")
                with _ac2:
                    fill_time = st.text_input("Time (from receipt)",
                        value=_pf.get("fill_time", ""), placeholder="e.g. 08:35")
                with _ac3:
                    pass

            # ── Product & quantities ───────────────────────────────────────
            _section("⛽  Product & Quantities")
            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            with col_p1:
                fuel_product = st.selectbox(
                    "Fuel Product",
                    FUEL_PRODUCTS,
                    index=0,  # Diesel 50PPM is default — most common
                )
            with col_p2:
                fuel_added = st.number_input(
                    "Volume Added (L)",
                    min_value=1.0, max_value=float(tank_cap + 100),
                    value=float(_pf.get("fuel_added_L", 150.0)), step=5.0,
                    help=f"Tank capacity: {tank_cap:.0f} L"
                )
            with col_p3:
                cost_per_L = st.number_input(
                    "Unit Price (E/L)",
                    min_value=5.0,
                    value=float(_pf.get("cost_per_litre_SZL", FUEL_PRICE_DEFAULT)),
                    step=0.05,
                    help="Price from the receipt slip"
                )
            with col_p4:
                full_tank = st.checkbox("Filled to full tank ✅", value=True,
                                        help="Required for accurate tank-to-tank efficiency calculation")

            # Live cost preview
            total_cost = fuel_added * cost_per_L
            fill_pct   = min(100, (fuel_added / tank_cap) * 100)
            range_est  = fuel_added * (1000 / FUEL_CONSUMPTION_BASE_L_PER_100KM)  # km
            col_prev1, col_prev2, col_prev3 = st.columns(3)
            col_prev1.metric("Total Cost", f"E {total_cost:,.2f}")
            col_prev2.metric("Tank Fill %", f"{fill_pct:.0f}%")
            col_prev3.metric("Est. Range", f"~{range_est:,.0f} km")

            # ── Odometer from receipt ──────────────────────────────────────
            _section("Odometer Reading")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                odometer = st.number_input(
                    "Odometer at Fill-Up (km)",
                    min_value=0.0,
                    value=float(_pf.get("odometer_km", cur_mileage)),
                    step=1.0,
                    help="Enter the odometer reading printed on the fuel receipt"
                )
            with col_o2:
                if not last_fill.empty and odometer > float(last_fill.iloc[0]["odometer"]):
                    km_this_interval = odometer - float(last_fill.iloc[0]["odometer"])
                    st.markdown(
                        f"<div style='background:rgba(30,58,138,0.4);border:1px solid rgba(96,165,250,0.25);"
                        f"border-radius:8px;padding:10px 14px;margin-top:28px;'>"
                        f"<div style='font-size:0.68rem;color:#93c5fd;'>Distance since last fill</div>"
                        f"<div style='font-size:1.3rem;font-weight:800;color:#fff;font-family:monospace;'>"
                        f"{km_this_interval:,.0f} km</div>"
                        f"<div style='font-size:0.72rem;color:#94a3b8;'>"
                        f"Implied: {km_this_interval/fuel_added:.2f} km/L</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            # ── Payment & driver — collapsed by default ────────────────────
            with st.expander("💳 Payment & Driver Details (optional)"):
              col_pay1, col_pay2, col_pay3 = st.columns(3)
              with col_pay1:
                payment_method = st.selectbox("Payment Method", PAYMENT_METHODS, index=0)
              with col_pay2:
                card_last4 = st.text_input("Card No. (last 4 digits)",
                    value=_pf.get("card_last4", ""), placeholder="e.g. 1234", max_chars=4)
              with col_pay3:
                receipt_driver_id = st.text_input(
                    "Driver ID on Receipt",
                    value=_pf.get("receipt_driver_id", driver_id),
                    placeholder="e.g. KSM-DRV-0001 or 5501",
                    help="Driver ID printed on fleet card receipt"
                )

            trip_ref = st.text_input(
                "Trip Reference (optional)",
                value=_pf.get("notes", ""),
                placeholder="e.g. Matsapha → Maputo run, 17 Apr 2026",
            )

            submitted = st.form_submit_button("◉ Save Fill-Up Record", type="primary",
                                              use_container_width=True)

        # ── Handle submission ─────────────────────────────────────────────────
        if submitted:
            errors = []
            if odometer < cur_mileage - 1:
                errors.append(f"Odometer ({odometer:,.0f} km) is below current DB reading ({cur_mileage:,.0f} km). Check the slip.")
            if fuel_added > tank_cap * 1.1:
                errors.append(f"{fuel_added:.0f} L exceeds tank capacity ({tank_cap:.0f} L) by more than 10%.")
            if errors:
                for e in errors: st.error(f"❌ {e}")
            else:
                try:
                    notes_full = " | ".join(filter(None, [
                        f"Pump: {pump_number}" if pump_number else "",
                        f"Receipt: {receipt_number}" if receipt_number else "",
                        f"Card: ****{card_last4}" if card_last4 else "",
                        f"Driver ID (receipt): {receipt_driver_id}" if receipt_driver_id else "",
                        f"Product: {fuel_product}",
                        f"Payment: {payment_method}",
                        f"Full tank: {'Yes' if full_tank else 'No'}",
                        trip_ref,
                    ]))

                    cursor = conn.cursor()
                    cursor.execute(
                        """INSERT INTO FuelConsumption
                           (truck_id, date, trip_id, fuel_added, odometer,
                            cost_per_liter, total_cost, fuel_type, station_location,
                            notes, is_full_tank)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (tid, str(fill_date), None, fuel_added, odometer,
                         cost_per_L, round(total_cost, 2), fuel_product,
                         station_name, notes_full, 1 if full_tank else 0),
                    )

                    if odometer > cur_mileage:
                        cursor.execute("UPDATE Truck SET mileage=? WHERE truck_id=?", (odometer, tid))

                    # Recompute rolling efficiency
                    valid_fills = pd.read_sql_query(
                        "SELECT odometer, fuel_added FROM FuelConsumption "
                        "WHERE truck_id=? AND is_full_tank=1 ORDER BY odometer ASC",
                        conn, params=(tid,)
                    )
                    if len(valid_fills) >= 2:
                        total_km   = float(valid_fills["odometer"].iloc[-1]) - float(valid_fills["odometer"].iloc[0])
                        total_fuel = valid_fills["fuel_added"].iloc[1:].sum()
                        if total_km > 0 and total_fuel > 0:
                            cursor.execute(
                                "UPDATE Truck SET rolling_fuel_efficiency=? WHERE truck_id=?",
                                (round(total_km / total_fuel, 3), tid)
                            )

                    conn.commit()
                    clear_fuel_prefill()

                    st.toast(f"◉ {fuel_added:.0f} L saved at {station_name}", icon="✅")
                    st.success(
                        f"✅ Fill-up saved — **{fuel_added:.0f} L** of **{fuel_product}** "
                        f"@ **E {cost_per_L:.2f}/L** = **E {total_cost:,.2f}** at {station_name}"
                    )

                    # Tank-to-tank efficiency
                    if not last_fill.empty and full_tank:
                        prev = last_fill.iloc[0]
                        km_driven  = odometer - float(prev["odometer"])
                        if km_driven > 0 and fuel_added > 0:
                            eff   = km_driven / fuel_added
                            l100  = (fuel_added / km_driven) * 100
                            delta = eff - float(FUEL_EFFICIENCY_BASE)
                            arrow = "↑" if delta > 0 else "↓"
                            c = "#34d399" if delta > 0 else "#f87171"
                            st.markdown(
                                f"<div style='background:rgba(5,150,105,0.15);border:1px solid rgba(52,211,153,0.3);"
                                f"border-radius:10px;padding:12px 16px;margin-top:8px;'>"
                                f"<div style='font-size:0.65rem;color:#94a3b8;text-transform:uppercase;margin-bottom:6px;'>Tank-to-Tank Efficiency</div>"
                                f"<div style='display:flex;gap:24px;flex-wrap:wrap;'>"
                                f"<div><div style='font-size:1.4rem;font-weight:800;color:{c};font-family:monospace;'>"
                                f"{arrow} {eff:.2f} km/L</div>"
                                f"<div style='font-size:0.72rem;color:#94a3b8;'>({l100:.1f} L/100km)</div></div>"
                                f"<div><div style='font-size:0.9rem;font-weight:700;color:#e2e8f0;'>{km_driven:,.0f} km</div>"
                                f"<div style='font-size:0.72rem;color:#94a3b8;'>driven since last fill</div></div>"
                                f"<div><div style='font-size:0.9rem;font-weight:700;color:#e2e8f0;'>E {total_cost/km_driven:.2f}/km</div>"
                                f"<div style='font-size:0.72rem;color:#94a3b8;'>fuel cost per km</div></div>"
                                f"</div></div>",
                                unsafe_allow_html=True,
                            )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving fill-up: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2 — FLEET DASHBOARD
    # ─────────────────────────────────────────────────────────────────────────
    with tab2:
        st.markdown("### ▦ Fleet Fuel Dashboard")
        try:
            summary = pd.read_sql_query("""
                SELECT T.registration, T.fuel_tank_capacity, T.driver,
                       T.rolling_fuel_efficiency,
                       COUNT(F.fuel_id)           AS fill_ups,
                       COALESCE(SUM(F.fuel_added),0)   AS total_litres,
                       COALESCE(SUM(F.total_cost),0)   AS total_spend,
                       COALESCE(AVG(F.cost_per_liter),0) AS avg_price,
                       COALESCE(MAX(F.odometer) - MIN(F.odometer),0) AS odometer_span,
                       MAX(F.date) AS last_fill_date
                FROM Truck T
                LEFT JOIN FuelConsumption F ON T.truck_id = F.truck_id
                GROUP BY T.truck_id, T.registration
                ORDER BY T.registration
            """, conn).fillna(0)

            if summary["total_litres"].sum() > 0:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Litres",    f"{summary['total_litres'].sum():,.0f} L")
                m2.metric("Total Spend",     f"E {summary['total_spend'].sum():,.2f}")
                avg_p = summary[summary["avg_price"] > 0]["avg_price"].mean()
                m3.metric("Avg Price/Litre", f"E {avg_p:.2f}/L" if avg_p > 0 else "—")
                m4.metric("Total Fill-Ups",  f"{int(summary['fill_ups'].sum())}")

                st.divider()

                # Efficiency table
                eff_rows = []
                for _, row in summary.iterrows():
                    rolling = float(row.get("rolling_fuel_efficiency") or 0)
                    calc    = (row["odometer_span"] / row["total_litres"]
                               if row["fill_ups"] >= 2 and row["total_litres"] > 0 else None)
                    eff     = rolling if rolling > 0 else calc
                    cost_km = row["total_spend"] / row["odometer_span"] if row["odometer_span"] > 0 else 0
                    eff_rows.append({
                        "Truck":          row["registration"],
                        "Driver":         row["driver"] or "—",
                        "km/L":           round(eff, 2) if eff else "—",
                        "L/100km":        round(100 / eff, 1) if eff and eff > 0 else "—",
                        "E/km":           round(cost_km, 2),
                        "Fill-Ups":       int(row["fill_ups"]),
                        "Total Litres":   round(row["total_litres"], 0),
                        "Total Spend (E)": round(row["total_spend"], 2),
                        "Last Fill":      row["last_fill_date"] or "never",
                    })

                if eff_rows:
                    eff_df = pd.DataFrame(eff_rows)
                    eff_num = eff_df[eff_df["km/L"] != "—"].copy()
                    if not eff_num.empty:
                        eff_num["km/L"] = eff_num["km/L"].astype(float)
                        c1, c2 = st.columns(2)
                        with c1:
                            fig = px.bar(eff_num, x="Truck", y="km/L",
                                         title="Fuel Efficiency by Truck (km/L)",
                                         color="km/L", color_continuous_scale="Greens",
                                         text="km/L")
                            fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                              font_color="#e2e8f0")
                            st.plotly_chart(fig, use_container_width=True)
                        with c2:
                            fig2 = px.bar(eff_num, x="Truck", y="E/km",
                                          title="Fuel Cost per km (E/km)",
                                          color="E/km", color_continuous_scale="Oranges",
                                          text="E/km")
                            fig2.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                               font_color="#e2e8f0")
                            st.plotly_chart(fig2, use_container_width=True)

                    st.dataframe(eff_df, use_container_width=True, hide_index=True)

                # Recent fill-ups
                st.divider()
                st.markdown("#### 📋 Recent Fill-Ups")
                recent = pd.read_sql_query("""
                    SELECT T.registration AS Truck, F.date AS Date,
                           F.odometer AS Odometer, F.fuel_added AS Litres,
                           F.fuel_type AS Product, F.cost_per_liter AS "E/L",
                           F.total_cost AS Total, F.station_location AS Station
                    FROM FuelConsumption F
                    JOIN Truck T ON F.truck_id = T.truck_id
                    ORDER BY F.date DESC, F.odometer DESC LIMIT 30
                """, conn)
                if not recent.empty:
                    st.dataframe(recent, use_container_width=True, hide_index=True)
                    export_buttons(recent, 'ksm_fuel_log', 'Fuel Log')
            else:
                st.info("No fuel data yet. Log your first fill-up in the **◉ Log Fill-Up** tab.")
        except Exception as e:
            st.error(f"Dashboard error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3 — EFFICIENCY TRENDS
    # ─────────────────────────────────────────────────────────────────────────
    with tab3:
        st.markdown("### ↑ Efficiency & Cost Trends")
        try:
            trucks_list = pd.read_sql_query("SELECT truck_id, registration FROM Truck ORDER BY registration", conn)
            if trucks_list.empty:
                st.info("No trucks registered.")
            else:
                sel = st.selectbox("Select Truck", trucks_list["registration"], key="trend_truck")
                tid_t = int(trucks_list[trucks_list["registration"] == sel]["truck_id"].iloc[0])

                fills = pd.read_sql_query(
                    """SELECT date, odometer, fuel_added, cost_per_liter, total_cost,
                              is_full_tank, station_location, fuel_type
                       FROM FuelConsumption WHERE truck_id=? ORDER BY odometer ASC""",
                    conn, params=(tid_t,)
                )

                if len(fills) >= 2:
                    fills["prev_full"]     = fills["is_full_tank"].shift(1).fillna(0).astype(int)
                    fills["km_since_last"] = fills["odometer"].diff()
                    fills["km_per_litre"]  = fills.apply(
                        lambda r: r["km_since_last"] / r["fuel_added"]
                        if (r["is_full_tank"] == 1 and r["prev_full"] == 1
                            and r["km_since_last"] > 0 and r["fuel_added"] > 0) else None,
                        axis=1,
                    )
                    fills["l_per_100km"]  = fills.apply(
                        lambda r: (r["fuel_added"] / r["km_since_last"]) * 100
                        if r["km_per_litre"] is not None and r["km_per_litre"] > 0 else None,
                        axis=1,
                    )
                    fills["cost_per_km"]  = fills["total_cost"] / fills["km_since_last"].replace(0, None)
                    valid = fills.dropna(subset=["km_per_litre"]).copy()

                    if not valid.empty:
                        avg_eff  = valid["km_per_litre"].mean()
                        avg_l100 = valid["l_per_100km"].mean()
                        avg_cpm  = valid["cost_per_km"].mean()
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Avg Efficiency",    f"{avg_eff:.2f} km/L")
                        m2.metric("Avg L/100km",       f"{avg_l100:.1f} L")
                        m3.metric("Avg Cost/km",       f"E {avg_cpm:.2f}")

                        c1, c2 = st.columns(2)
                        with c1:
                            fig1 = px.line(valid, x="date", y="km_per_litre",
                                           title="Fuel Efficiency Over Time (km/L)",
                                           markers=True,
                                           labels={"km_per_litre": "km/L", "date": "Date"})
                            fig1.add_hline(y=avg_eff, line_dash="dash",
                                           annotation_text=f"Avg {avg_eff:.2f}")
                            fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                                               plot_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0")
                            st.plotly_chart(fig1, use_container_width=True)
                        with c2:
                            fig2 = px.bar(fills, x="date", y="total_cost",
                                          title="Fuel Spend per Fill-Up (E)",
                                          color="cost_per_km", color_continuous_scale="RdYlGn_r",
                                          labels={"total_cost": "Spend (E)", "date": "Date"})
                            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                                               plot_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0")
                            st.plotly_chart(fig2, use_container_width=True)

                        fig3 = px.line(valid, x="date", y="l_per_100km",
                                       title="Litres per 100km — lower is better",
                                       markers=True, labels={"l_per_100km": "L/100km"})
                        fig3.add_hline(y=avg_l100, line_dash="dash",
                                       annotation_text=f"Avg {avg_l100:.1f}")
                        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                                           plot_bgcolor="rgba(0,0,0,0)", font_color="#e2e8f0")
                        st.plotly_chart(fig3, use_container_width=True)

                        with st.expander("📋 Raw Fill-Up Data"):
                            st.dataframe(
                                valid[["date", "odometer", "fuel_added", "km_since_last",
                                       "km_per_litre", "l_per_100km", "cost_per_km", "total_cost",
                                       "station_location"]].round(2),
                                use_container_width=True, hide_index=True,
                            )
                    else:
                        st.info("Valid full-tank pairs needed for efficiency calculation. Keep logging fill-ups!")
                else:
                    st.info(f"Need at least 2 fill-ups for **{sel}** to compute trends.")
        except Exception as e:
            st.error(f"Trend error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 4 — FUEL ALERTS
    # ─────────────────────────────────────────────────────────────────────────
    with tab4:
        st.markdown("### 🔔 Smart Fuel Alerts")
        try:
            alert_data = pd.read_sql_query("""
                SELECT T.registration, T.fuel_tank_capacity, T.mileage, T.driver,
                       T.fuel_efficiency_baseline, T.rolling_fuel_efficiency,
                       COALESCE(SUM(F.fuel_added),0) AS total_fuel,
                       COALESCE(MAX(F.odometer),0)   AS last_odometer,
                       MAX(F.date)                   AS last_fill_date,
                       COUNT(F.fuel_id)               AS fill_count,
                       COALESCE(AVG(F.cost_per_liter),0) AS avg_price,
                       MAX(F.station_location)        AS last_station
                FROM Truck T
                LEFT JOIN FuelConsumption F ON T.truck_id = F.truck_id
                GROUP BY T.truck_id
            """, conn).fillna(0)

            live = fetch_live_market_data()
            alerts = []
            for _, row in alert_data.iterrows():
                km_since  = float(row["mileage"]) - float(row["last_odometer"])
                rolling   = float(row.get("rolling_fuel_efficiency") or 0)
                baseline  = float(row["fuel_efficiency_baseline"]) or FUEL_EFFICIENCY_BASE
                eff       = rolling if rolling > 0 else baseline
                tank      = float(row["fuel_tank_capacity"]) or 300
                est_range = eff * tank * 0.80

                if km_since > est_range * 0.80:
                    alerts.append(("critical", row["registration"],
                                   f"Likely needs refuelling — {km_since:,.0f} km since last fill "
                                   f"(est. range {est_range:,.0f} km). Last at: {row['last_station'] or '?'}"))
                elif km_since > est_range * 0.60:
                    alerts.append(("warning", row["registration"],
                                   f"Plan refuelling soon — {km_since:,.0f} km since last fill"))

                avg_p = float(row["avg_price"])
                if avg_p > 0 and live["fuel_price"] > avg_p * 1.10:
                    alerts.append(("info", row["registration"],
                                   f"Fuel price up ~{((live['fuel_price']/avg_p)-1)*100:.0f}% "
                                   f"vs your avg (E{avg_p:.2f} → E{live['fuel_price']:.2f}/L)"))

                if row["fill_count"] < 2:
                    alerts.append(("info", row["registration"],
                                   "Log more fill-ups to enable efficiency tracking."))

            if alerts:
                for level, truck, msg in alerts:
                    if level == "critical":
                        st.error(f"● **{truck}**: {msg}")
                    elif level == "warning":
                        st.warning(f"● **{truck}**: {msg}")
                    else:
                        st.info(f"🔵 **{truck}**: {msg}")
            else:
                st.success("✅ No fuel alerts. All trucks appear adequately fuelled.")

            # Tank status gauges
            st.divider()
            st.markdown("#### ◉ Estimated Tank Status")
            gauge_cols = st.columns(min(len(alert_data), 4))
            for i, (_, row) in enumerate(alert_data.iterrows()):
                km_since = float(row["mileage"]) - float(row["last_odometer"])
                rolling  = float(row.get("rolling_fuel_efficiency") or 0)
                baseline = float(row["fuel_efficiency_baseline"]) or FUEL_EFFICIENCY_BASE
                eff      = rolling if rolling > 0 else baseline
                tank     = float(row["fuel_tank_capacity"]) or 300
                used     = km_since / eff if eff > 0 else 0
                remain   = max(0, tank - used)
                pct      = min(100, (remain / tank) * 100) if tank > 0 else 0
                bar_c    = "#10b981" if pct > 40 else "#f59e0b" if pct > 20 else "#dc2626"
                with gauge_cols[i % 4]:
                    st.markdown(
                        f"<div style='background:rgba(15,23,42,0.55);border:1px solid {bar_c}44;"
                        f"border-radius:10px;padding:12px 14px;margin-bottom:8px;'>"
                        f"<div style='font-size:0.75rem;font-weight:700;color:#e2e8f0;'>{row['registration']}</div>"
                        f"<div style='font-size:0.68rem;color:#94a3b8;'>{row['driver'] or '—'}</div>"
                        f"<div style='font-size:1.1rem;font-weight:800;color:{bar_c};margin:4px 0;'>"
                        f"{remain:.0f} L <span style='font-size:0.7rem;font-weight:400;'>/ {tank:.0f} L</span></div>"
                        f"<div style='background:rgba(30,41,59,0.8);border-radius:5px;height:10px;'>"
                        f"<div style='background:{bar_c};width:{pct:.0f}%;height:10px;border-radius:5px;'></div></div>"
                        f"<div style='font-size:0.65rem;color:#64748b;margin-top:4px;'>"
                        f"Last fill: {row['last_fill_date'] or 'never'}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        except Exception as e:
            st.error(f"Alerts error: {e}")

    conn.close()
