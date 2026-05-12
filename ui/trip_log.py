# ui/trip_log.py — Unified Logistics: Log Completed Trip
# Redesigned around real KSM document workflows:
#   • CONCO-style Job Orders  (carrier, truck+trailer, cargo, seal, compliance)
#   • Weighbridge tickets     (gross/tare/net, quality %, field/section)
#   • Standard transport runs (origin→destination, duration, expenses)
from __future__ import annotations
from utils.error_handler import safe_page
import logging
import streamlit as st
import pandas as pd
from datetime import date, datetime
from utils.exports import export_buttons

from core.config import (
    MAX_PAYLOAD_KG, FUEL_PRICE_DEFAULT, MAINTENANCE_PER_KM,
    BORDER_COST_EACH, SERVICE_INTERVAL_KM, LOCATION_COORDS,
)
from core.database import get_connection
from core.constants import TRIP_PREFILL_KEY
from services.market_data import fetch_weather_for_location
from services.routes import get_route_characteristics

logger = logging.getLogger(__name__)

# ── Cargo types derived from real document types seen in the fleet ─────────────
CARGO_TYPES = [
    "General Cargo",
    "Beverage Concentrate",
    "Sugar Cane",
    "Building Materials",
    "Palletized Goods",
    "Bulk Agricultural",
    "Refrigerated / Perishable",
    "Hazardous Materials",
    "Machinery / Equipment",
    "Fuel / Liquid Bulk",
    "Other",
]

PAYMENT_TYPES = [
    "Invoice (30-day)",
    "Cash on Delivery",
    "EFT / Bank Transfer",
    "Fleet Card (e.g. Galp Frota)",
    "Credit Account",
]

COMPLIANCE_ITEMS = [
    "Driver licence & PDP verified",
    "PPE on board",
    "Vehicle roadworthy",
    "Cargo insurance active",
    "Customs / export docs ready",
    "Seal number recorded",
    "Weighbridge ticket obtained",
]


def _get_logistics_manager():
    return st.session_state.get("logistics_manager")


def get_trip_prefill() -> dict | None:
    return st.session_state.get(TRIP_PREFILL_KEY)


def clear_trip_prefill() -> None:
    st.session_state.pop(TRIP_PREFILL_KEY, None)


def _section(label: str) -> None:
    st.markdown(
        f"<div style='font-size:0.67rem;font-weight:800;letter-spacing:0.14em;"
        f"text-transform:uppercase;color:#60a5fa;margin:1.2rem 0 0.5rem 0;"
        f"border-bottom:1px solid rgba(96,165,250,0.2);padding-bottom:0.35rem;'>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


def _info_pill(text: str, color: str = "#60a5fa") -> None:
    st.markdown(
        f"<div style='background:rgba(15,23,42,0.55);border:1px solid {color}33;"
        f"border-radius:8px;padding:7px 12px;font-size:0.78rem;color:{color};"
        f"margin-bottom:0.4rem;'>{text}</div>",
        unsafe_allow_html=True,
    )


def render_trip_log_tab(conn) -> None:
    """Redesigned trip log — mirrors real CONCO job order + weighbridge workflow."""
    _pf = get_trip_prefill() or {}

    st.markdown("### 📋 Log Completed Trip")
    st.caption("Built around CONCO job orders, weighbridge tickets and standard transport runs.")

    if _pf:
        st.success(
            "✅ **Document pre-filled this form** — review the values and press **Log Trip**.",
            icon="📋",
        )

    # ── Truck & trailer ───────────────────────────────────────────────────────
    try:
        trucks_df = pd.read_sql_query(
            "SELECT truck_id, registration, driver, mileage, model, driver_id FROM Truck ORDER BY registration",
            conn,
        )
        if trucks_df.empty:
            st.warning("⚠️ No trucks registered. Please add a truck first.")
            return
    except Exception as e:
        st.error(f"❌ Could not load truck list: {e}")
        return

    _section("▣  Truck & Driver")

    # Auto-match truck from prefill (job order may have a registration)
    _pf_truck = _pf.get("truck_registration")
    _truck_list = list(trucks_df["registration"])
    _truck_idx = _truck_list.index(_pf_truck) if _pf_truck and _pf_truck in _truck_list else 0

    col_t1, col_t2, col_t3 = st.columns([2, 2, 2])
    with col_t1:
        sel_truck = st.selectbox("Truck Registration", _truck_list, index=_truck_idx, key="log_truck_sel")
    with col_t2:
        trailer_reg = st.text_input(
            "Trailer Registration (if any)",
            value=_pf.get("trailer_registration", ""),
            placeholder="e.g. TSD 456 DEF",
        )
    with col_t3:
        job_number = st.text_input(
            "Job / Document Reference",
            value=_pf.get("job_number", ""),
            placeholder="e.g. CONCO-2026-0416-01",
        )

    truck_row = trucks_df[trucks_df["registration"] == sel_truck].iloc[0]
    tid_log = int(truck_row["truck_id"])
    current_odometer_km = float(truck_row["mileage"] or 0)
    driver_name = truck_row.get("driver") or "Unassigned"
    driver_id   = truck_row.get("driver_id") or "—"

    # ── Auto-pull last odometer & fuel ────────────────────────────────────────
    try:
        last_fuel_row = pd.read_sql_query(
            "SELECT fuel_added, odometer, date, cost_per_liter FROM FuelConsumption "
            "WHERE truck_id=? ORDER BY odometer DESC LIMIT 1",
            conn, params=(tid_log,),
        )
        prev_fuel_row = pd.read_sql_query(
            "SELECT odometer FROM FuelConsumption "
            "WHERE truck_id=? ORDER BY odometer DESC LIMIT 1 OFFSET 1",
            conn, params=(tid_log,),
        )
    except Exception:
        last_fuel_row = pd.DataFrame()
        prev_fuel_row = pd.DataFrame()

    auto_odometer   = float(last_fuel_row["odometer"].iloc[0]) if not last_fuel_row.empty else current_odometer_km
    auto_fuel       = float(last_fuel_row["fuel_added"].iloc[0]) if not last_fuel_row.empty else 0.0
    prev_odometer   = float(prev_fuel_row["odometer"].iloc[0]) if not prev_fuel_row.empty else (auto_odometer - 300)
    auto_distance   = max(0.0, auto_odometer - prev_odometer)
    last_fuel_price = float(last_fuel_row["cost_per_liter"].iloc[0]) if not last_fuel_row.empty else FUEL_PRICE_DEFAULT

    # Driver + odometer banner
    st.markdown(
        f"<div style='background:linear-gradient(135deg,rgba(30,58,138,0.6),rgba(15,23,42,0.7));"
        f"border:1px solid rgba(96,165,250,0.25);border-radius:12px;"
        f"padding:12px 18px;margin-bottom:0.8rem;display:flex;gap:24px;flex-wrap:wrap;'>"
        f"<div><div style='font-size:0.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em;'>Driver</div>"
        f"<div style='font-size:0.95rem;font-weight:700;color:#e2e8f0;'>{driver_name}</div>"
        f"<div style='font-size:0.68rem;color:#34d399;font-family:monospace;'>{driver_id}</div></div>"
        f"<div><div style='font-size:0.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em;'>Odometer (DB)</div>"
        f"<div style='font-size:0.95rem;font-weight:700;color:#60a5fa;font-family:monospace;'>{current_odometer_km:,.0f} km</div></div>"
        f"<div><div style='font-size:0.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em;'>Last Fill-Up</div>"
        f"<div style='font-size:0.95rem;font-weight:700;color:#e2e8f0;'>"
        f"{f'{auto_fuel:.0f} L @ E{last_fuel_price:.2f}/L' if not last_fuel_row.empty else 'No fuel records'}</div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── GPS Route Lookup (OUTSIDE form — buttons not allowed inside forms) ──────
    st.markdown("**Route Details**")
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        origin = st.text_input(
            "Origin / Loading Point",
            value=st.session_state.get("_trip_origin", _pf.get("start_location", "")),
            placeholder="e.g. Mbabane CBD, Eswatini",
            key="origin_input",
            help="Type any address, business name or town.",
        )
        st.session_state["_trip_origin"] = origin
    with col_r2:
        destination = st.text_input(
            "Destination",
            value=st.session_state.get("_trip_dest", _pf.get("end_location", "")),
            placeholder="e.g. Durban Baito Boxer Superstore, KZN",
            key="dest_input",
            help="Enter full destination address including city for best accuracy.",
        )
        st.session_state["_trip_dest"] = destination

    _gps_key    = f"_gps_{origin}_{destination}"
    _gps_result = st.session_state.get(_gps_key, {})
    _gps_dist   = float(_pf.get("distance_km", auto_distance))

    col_btn, col_result = st.columns([1, 3])
    with col_btn:
        if st.button("📍 Get Road Distance",
                     key="gps_calc_btn",
                     use_container_width=True,
                     disabled=not (origin.strip() and destination.strip())):
            with st.spinner("Calculating road distance..."):
                try:
                    from services.gps_routing import get_road_distance
                    _ors_key    = st.session_state.get("ors_api_key", "")
                    _gps_result = get_road_distance(origin, destination, _ors_key)
                    st.session_state[_gps_key] = _gps_result
                except Exception as _e:
                    _gps_result = {"error": str(_e)}
                    st.session_state[_gps_key] = _gps_result

    with col_result:
        if _gps_result:
            if "error" in _gps_result:
                st.warning(f"⚠️ {_gps_result['error']}")
            else:
                _gps_dist = _gps_result["distance_km"]
                _gps_dur  = _gps_result["duration_hrs"]
                _gps_src  = _gps_result["source"]
                st.success(
                    f"📍 **{_gps_dist:.1f} km** road distance · "
                    f"Est. drive time: **{_gps_dur:.1f} hrs** (HGV) · "
                    f"*{_gps_src}*"
                )
                # Infer terrain from GPS coords
                try:
                    from services.gps_routing import infer_terrain
                    _gps_terrain = infer_terrain(
                        _gps_result["origin_coords"],
                        _gps_result["dest_coords"]
                    )
                    st.session_state["_gps_terrain"] = _gps_terrain
                except Exception:
                    pass

    st.divider()

    with st.form("trip_log_form", clear_on_submit=True):

        # Read GPS values already captured above
        _section("Route Details")
        col_gps2, col_gps3, col_gps4 = st.columns(3)
        with col_gps2:
            distance = st.number_input("Distance (km)", min_value=0.0,
                value=_gps_dist,
                help="Auto-filled by GPS above. Edit manually if needed.")
        with col_gps3:
            border_crossings = st.number_input("Borders Crossed", min_value=0,
                value=int(_pf.get("border_crossings", 0)), step=1)
        with col_gps4:
            _gps_terrain_val = st.session_state.get("_gps_terrain", "")
            if _gps_terrain_val:
                st.info(f"Terrain: **{_gps_terrain_val}**")

        col_r5, col_r6, col_r7 = st.columns(3)
        with col_r5:
            trip_date = st.date_input("Trip Date", value=date.today())
        with col_r6:
            loading_time = st.text_input(
                "Loading Time / Schedule",
                value=_pf.get("loading_time", ""),
                placeholder="e.g. 08:00 AM, 17 Apr 2026",
            )
        with col_r7:
            expected_delivery = st.text_input(
                "Expected Delivery",
                value=_pf.get("expected_delivery", ""),
                placeholder="e.g. 18 Apr 2026",
            )

        # ── Cargo & weighbridge ───────────────────────────────────────────────
        _section("📦  Cargo & Weighbridge Details")
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            cargo_type = st.selectbox("Cargo Type / Description", CARGO_TYPES,
                                      index=CARGO_TYPES.index(_pf.get("cargo_type", "General Cargo"))
                                      if _pf.get("cargo_type") in CARGO_TYPES else 0)
            cargo_desc = st.text_input("Cargo Details / Client",
                                       value=_pf.get("cargo_description", ""),
                                       placeholder="e.g. Beverage Concentrate — CONCO Ltd")
        with col_c2:
            # Weighbridge-aware load entry
            gross_weight = st.number_input(
                "Gross Weight (kg)  ← Weighbridge",
                min_value=0.0,
                value=float(_pf.get("gross_weight_kg", _pf.get("load_kg", 0.0))),
                help="Gross weight from weighbridge ticket (truck + cargo)"
            )
            tare_weight = st.number_input(
                "Tare Weight / Empty Truck (kg)",
                min_value=0.0,
                value=float(_pf.get("tare_weight_kg", 15000.0)),
                help="Empty truck weight — from weighbridge ticket or truck specs"
            )
            net_weight = max(0.0, gross_weight - tare_weight)
        with col_c3:
            seal_number = st.text_input(
                "Seal Number",
                value=_pf.get("seal_number", ""),
                placeholder="e.g. CO-998877",
            )
            weighbridge_ticket = st.text_input(
                "Weighbridge Ticket No.",
                value=_pf.get("weighbridge_ticket", ""),
                placeholder="e.g. #ESW-2026-99045",
            )
            quality_pct = st.number_input(
                "Quality / Trash % (if applicable)",
                min_value=0.0, max_value=100.0,
                value=float(_pf.get("quality_pct", 0.0)),
                step=0.1,
                help="From weighbridge quality report e.g. sugar cane trash %"
            )

        # Auto net weight display
        if gross_weight > 0 and tare_weight > 0:
            w_pct = (net_weight / MAX_PAYLOAD_KG * 100)
            w_col = "#34d399" if w_pct <= 85 else ("#fbbf24" if w_pct <= 100 else "#f87171")
            st.markdown(
                f"<div style='background:rgba(15,23,42,0.5);border:1px solid {w_col}44;"
                f"border-radius:8px;padding:8px 14px;font-size:0.79rem;color:{w_col};margin-bottom:0.3rem;'>"
                f"⚖️ Net Cargo Weight: <b>{net_weight:,.0f} kg</b>"
                f" &nbsp;|&nbsp; Payload utilisation: <b>{w_pct:.0f}%</b> of {MAX_PAYLOAD_KG:,} kg max"
                f"{'&nbsp;|&nbsp; ⚠️ <b>OVERLOADED</b>' if w_pct > 100 else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )
        if net_weight > MAX_PAYLOAD_KG:
            st.warning(f"⚠️ Net weight {net_weight:,.0f} kg exceeds maximum payload of {MAX_PAYLOAD_KG:,} kg.")

        # ── Fuel & performance ────────────────────────────────────────────────
        _section("◉  Fuel & Performance")
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            fuel_consumed = st.number_input("Fuel Consumed (L)", min_value=0.0,
                                            value=float(_pf.get("fuel_consumed_L", auto_fuel)), step=5.0)
        with col_f2:
            odometer_end = st.number_input("Odometer at Trip End (km)", min_value=0.0,
                                           value=float(auto_odometer), step=1.0)
        with col_f3:
            trip_duration = st.number_input("Trip Duration (hours)", min_value=0.0,
                                            value=float(_pf.get("trip_duration_hours", 5.0)), step=0.25)
        with col_f4:
            idle_time = st.number_input("Idle Time (min)", min_value=0, value=0, step=5)

        with st.expander("🔧 Advanced Performance Details (optional)"):
            col_f5, col_f6, col_f7 = st.columns(3)
            with col_f5:
                hard_braking = st.number_input("Hard Braking Events", min_value=0, value=0, step=1,
                    help="Number of sudden braking incidents recorded during the trip")
            with col_f6:
                driver_exp = st.number_input("Driver Experience (years)", min_value=0, max_value=50,
                                             value=5, step=1)
            with col_f7:
                idle_time = st.number_input("Idle Time (min)", min_value=0, value=0, step=5,
                    help="Total engine-on time while stationary")

        # ── Revenue & payment ─────────────────────────────────────────────────
        _section("◎  Revenue & Payment")
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            billing_method = st.selectbox("Billing Method",
                ["Per km (one way)", "Per km (both ways)", "Per ton-km", "Flat rate"])
            rate_per_km = st.number_input("Rate (E/km)", min_value=0.0, value=30.0, step=0.50,
                help="Minimum E22/km for local, E24/km cross-border")
        with col_v2:
            # Auto-calculate revenue from rate × distance
            if billing_method == "Per km (one way)":
                _auto_rev = rate_per_km * distance if distance > 0 else 0.0
            elif billing_method == "Per km (both ways)":
                _auto_rev = rate_per_km * distance * 2 if distance > 0 else 0.0
            elif billing_method == "Per ton-km":
                _net_wt = max(0.0, float(_pf.get("net_weight", 0.0)))
                _auto_rev = rate_per_km * distance * (_net_wt / 1000) if distance > 0 else 0.0
            else:
                _auto_rev = 0.0
            revenue = st.number_input("Total Revenue (E)", min_value=0.0,
                                      value=max(float(_pf.get("revenue_SZL", 0.0)), _auto_rev),
                                      step=100.0,
                                      help="Auto-calculated from rate × distance — edit if flat rate")
            payment_type = st.selectbox("Payment Terms", PAYMENT_TYPES)
        with col_v3:
            client_name = st.text_input("Client / Customer",
                                        value=_pf.get("client_name", ""),
                                        placeholder="e.g. CONCO Ltd")
            return_load = st.radio("Return Load",
                ["Return load secured", "Empty return"],
                help="Empty return doubles effective cost per km")
            return_empty = return_load == "Empty return"
            if return_empty:
                st.warning("Empty return — seek a backhaul to reduce cost per km.")

        # ── Trip expenses ─────────────────────────────────────────────────────
        _section("Trip Expenses")
        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            toll_cost  = st.number_input("Toll Fees (E)", min_value=0.0,
                                         value=float(_pf.get("toll_cost_SZL", 0.0)), step=10.0)
            toll_notes = st.text_input("Toll Notes", placeholder="e.g. N2 Oshoek border toll",
                                       key="toll_notes_log")
        with col_e2:
            fuel_refill_L   = st.number_input("En-Route Refill (L)", min_value=0.0, value=0.0, step=5.0)
            fuel_refill_ppl = st.number_input("Refill Price/L (E)", min_value=0.0,
                                              value=FUEL_PRICE_DEFAULT, step=0.05)
            fuel_refill_loc = st.text_input("Refill Station", placeholder="e.g. Total Ermelo",
                                            key="refill_loc_log")
        with col_e3:
            other_exp  = st.number_input("Other Expenses (E)", min_value=0.0, value=0.0, step=10.0)
            other_desc = st.text_input("Other Description",
                                       placeholder="e.g. Overnight parking, port fees",
                                       key="other_desc_log")

        # ── Compliance checklist ──────────────────────────────────────────────
        _section("Compliance & Safety Checklist")
        st.caption("Tick all that were verified before departure — mirrors CONCO job order checklist.")
        comp_cols = st.columns(3)
        compliance_checked = []
        for i, item in enumerate(COMPLIANCE_ITEMS):
            with comp_cols[i % 3]:
                if st.checkbox(item, value=True, key=f"comp_{i}"):
                    compliance_checked.append(item)

        on_time = st.selectbox("Delivered On Time?", ["Yes", "No", "Partial delay"], index=0)

        # ── Time & delays ─────────────────────────────────────────────────────
        _section("Time & Delays")
        td1, td2, td3 = st.columns(3)
        with td1:
            departure_time = st.text_input("Actual Departure Time",
                placeholder="e.g. 06:30", key="dep_time_log")
            arrival_time   = st.text_input("Actual Arrival Time",
                placeholder="e.g. 14:45", key="arr_time_log")
        with td2:
            border_wait_hrs = st.number_input("Border Waiting Time (hrs)",
                min_value=0.0, value=0.0, step=0.5,
                help="Total time spent waiting at all border posts")
            breakdown_hrs   = st.number_input("Breakdown Time (hrs)",
                min_value=0.0, value=0.0, step=0.5)
        with td3:
            delay_reason = st.selectbox("Delay Reason (if any)",
                ["None", "Border delays", "Traffic", "Breakdown",
                 "Weather", "Client not ready", "Road closure", "Other"])
            nights_away = st.number_input("Nights Away from Base",
                min_value=0, value=0, step=1)

        # ── Incidents ─────────────────────────────────────────────────────────
        _section("Incident Reporting")
        inc1, inc2, inc3 = st.columns(3)
        with inc1:
            incident_occurred = st.checkbox("Incident occurred on this trip", value=False)
        with inc2:
            incident_type = "None"
            if incident_occurred:
                incident_type = st.selectbox("Incident Type",
                    ["Near miss", "Minor damage", "Accident",
                     "Theft / Pilferage", "Hijacking", "Overloading fine",
                     "Traffic fine", "Other"])
        with inc3:
            incident_cost = 0.0
            if incident_occurred:
                incident_cost = st.number_input("Incident Cost (E)",
                    min_value=0.0, value=0.0, step=500.0)

        notes   = st.text_area("Additional Notes / Remarks",
            placeholder="Delays, incidents, special instructions…", height=70)

        submit_trip = st.form_submit_button("✅ Log Trip", type="primary", use_container_width=True)

    # ── Handle submission ─────────────────────────────────────────────────────
    if not submit_trip:
        return

    # Validation
    if distance <= 0 and (odometer_end - current_odometer_km) <= 0:
        st.error("❌ Distance must be greater than 0.")
        return
    effective_distance = distance if distance > 0 else max(0.0, odometer_end - current_odometer_km)
    load_kg = net_weight if gross_weight > 0 else 0.0

    # Auto weather + terrain
    # Read origin/destination from session_state (set outside form)
    origin      = st.session_state.get("_trip_origin", origin) if not origin else origin
    destination = st.session_state.get("_trip_dest",   destination) if not destination else destination

    # Resolve origin coordinates via GPS geocoding
    try:
        from services.gps_routing import geocode as _geocode
        origin_coords = _geocode(origin) or (-26.485, 31.360)
    except Exception:
        origin_coords = LOCATION_COORDS.get(origin, (-26.485, 31.360))
    with st.spinner("🌤️ Auto-detecting weather…"):
        try:
            live_w = fetch_weather_for_location(origin_coords[0], origin_coords[1], origin)
        except Exception:
            live_w = {}
    auto_weather = live_w.get("weather_condition", "Clear")

    try:
        route_defaults = get_route_characteristics(origin, destination)
    except Exception:
        route_defaults = {}
    auto_terrain = route_defaults.get("terrain", "Rolling")
    road_quality = route_defaults.get("road_quality", 0.75)

    fuel_eff          = effective_distance / fuel_consumed if fuel_consumed > 0 else 0
    actual_fuel_cost  = fuel_consumed * last_fuel_price
    fuel_refill_cost  = fuel_refill_L * fuel_refill_ppl
    maint_cost        = effective_distance * MAINTENANCE_PER_KM
    total_expenses    = toll_cost + fuel_refill_cost + other_exp + (border_crossings * BORDER_COST_EACH)
    profit_trip       = revenue - actual_fuel_cost - maint_cost - total_expenses
    pm                = (profit_trip / revenue * 100) if revenue > 0 else 0.0

    # Risk prediction
    lm = _get_logistics_manager()
    try:
        risk_score = lm.ml_risk_predictor.predict_risk(
            {"distance": effective_distance, "load": load_kg, "road_quality": road_quality,
             "driver_experience_years": driver_exp, "hard_braking_events": hard_braking,
             "idle_time_minutes": idle_time, "border_crossings": border_crossings,
             "terrain": auto_terrain, "weather": auto_weather},
            {"truck_age_years": 0, "mileage": current_odometer_km, "last_service_km": current_odometer_km},
        ) if lm and lm.ml_risk_predictor else 0
    except Exception:
        risk_score = 0

    # ── Pre-trip profitability check ─────────────────────────────────────────
    from core.hgv_profiles import MIN_RATE_PER_KM
    _route_type = "Cross-border (SA↔SWZ)" if border_crossings > 0 else "Local (within Eswatini)"
    _min_rate   = MIN_RATE_PER_KM.get(_route_type, 22.0)
    if rate_per_km > 0 and rate_per_km < _min_rate:
        st.warning(f"⚠️ Rate of E{rate_per_km:.2f}/km is below the minimum of E{_min_rate:.2f}/km for this route type.")
    if return_empty:
        _effective_cost_km = (actual_fuel_cost + maint_cost) / max(effective_distance, 1) * 2
        st.info(f"Empty return doubles effective cost. Seek a backhaul above E{_effective_cost_km:.2f}/km.")

    # Build notes string with all extra metadata
    full_notes = " | ".join(filter(None, [
        f"Job: {job_number}" if job_number else "",
        f"Trailer: {trailer_reg}" if trailer_reg else "",
        f"Seal: {seal_number}" if seal_number else "",
        f"WB Ticket: {weighbridge_ticket}" if weighbridge_ticket else "",
        f"Client: {client_name}" if client_name else "",
        f"Cargo: {cargo_desc}" if cargo_desc else "",
        f"Payment: {payment_type}",
        f"Billing: {billing_method} @ E{rate_per_km:.2f}/km",
        f"Return: {return_load}",
        f"Quality: {quality_pct:.1f}%" if quality_pct > 0 else "",
        f"Depart: {departure_time}" if departure_time else "",
        f"Arrive: {arrival_time}" if arrival_time else "",
        f"Border wait: {border_wait_hrs:.1f}hrs" if border_wait_hrs > 0 else "",
        f"Breakdown: {breakdown_hrs:.1f}hrs" if breakdown_hrs > 0 else "",
        f"Delay: {delay_reason}" if delay_reason != "None" else "",
        f"Nights: {nights_away}" if nights_away > 0 else "",
        f"Incident: {incident_type} E{incident_cost:,.0f}" if incident_occurred else "",
        f"Compliance: {len(compliance_checked)}/{len(COMPLIANCE_ITEMS)} items checked",
        notes,
    ]))

    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO Trip
               (truck_id, start_location, end_location, distance, load, date,
                terrain_type, weather_condition, road_quality, border_crossings,
                fuel_consumed, actual_fuel_efficiency, trip_duration_hours,
                toll_cost, hard_braking_events, idle_time_minutes,
                driver_experience_years, profit_margin, revenue,
                fuel_refill_cost, fuel_refill_litres, actual_fuel_cost, risk_score,
                delivery_on_time, rate_per_km, billing_method, return_empty,
                departure_time, arrival_time, border_wait_hrs, breakdown_hrs,
                delay_reason, nights_away, incident_occurred, incident_type,
                incident_cost, client_name)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                tid_log, origin, destination, effective_distance, load_kg, str(trip_date),
                auto_terrain, auto_weather, road_quality, border_crossings,
                fuel_consumed, fuel_eff, trip_duration,
                toll_cost, hard_braking, idle_time, driver_exp, round(pm, 2), revenue,
                fuel_refill_cost, fuel_refill_L, actual_fuel_cost, risk_score,
                1 if on_time == "Yes" else 0,
                rate_per_km, billing_method, 1 if return_empty else 0,
                departure_time, arrival_time, border_wait_hrs, breakdown_hrs,
                delay_reason, nights_away,
                1 if incident_occurred else 0, incident_type if incident_occurred else None,
                incident_cost if incident_occurred else 0.0,
                client_name,
            ),
        )
        trip_id = cursor.lastrowid

        if toll_cost > 0 or fuel_refill_cost > 0 or other_exp > 0:
            cursor.execute(
                """INSERT INTO TripExpenses
                   (trip_id, truck_id, date, toll_fees, fuel_refill_cost,
                    fuel_refill_litres, fuel_refill_location, other_expenses, other_description)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (trip_id, tid_log, str(trip_date), toll_cost, fuel_refill_cost,
                 fuel_refill_L, fuel_refill_loc, other_exp, other_desc),
            )

        if odometer_end > current_odometer_km:
            cursor.execute("UPDATE Truck SET mileage=? WHERE truck_id=?", (odometer_end, tid_log))

        # Service warning check
        try:
            svc_row = pd.read_sql_query(
                "SELECT last_service_km, service_interval, service_warning_active FROM Truck WHERE truck_id=?",
                conn, params=(tid_log,),
            ).iloc[0]
            svc_gap = odometer_end - float(svc_row["last_service_km"] or 0)
            svc_int = float(svc_row.get("service_interval") or SERVICE_INTERVAL_KM)
            if svc_gap >= svc_int * 0.90 and not int(svc_row.get("service_warning_active") or 0):
                cursor.execute(
                    "UPDATE Truck SET service_warning_active=1, service_warning_date=? WHERE truck_id=?",
                    (str(trip_date), tid_log),
                )
                cursor.execute(
                    "INSERT INTO ServiceWarning (truck_id, warning_type, triggered_date, triggered_km) VALUES (?,?,?,?)",
                    (tid_log, "Service Due", str(trip_date), odometer_end),
                )
                st.warning(f"⚠️ **SERVICE WARNING** — {svc_gap:,.0f} km since last service (interval: {svc_int:,.0f} km)")
        except Exception as e:
            logger.warning("trip_log: service check failed: %s", e)

        conn.commit()
        clear_trip_prefill()

        # ── Success summary ────────────────────────────────────────────────────
        st.toast(f"Trip logged: {origin} → {destination}", icon="↗")
        st.success(
            f"✅ Trip logged! **{origin} → {destination}** | "
            f"Terrain: **{auto_terrain}** | Weather: **{auto_weather}**"
        )
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Distance",     f"{effective_distance:.0f} km")
        c2.metric("Net Weight",   f"{load_kg:,.0f} kg")
        c3.metric("Rate",         f"E{rate_per_km:.2f}/km")
        c4.metric("Efficiency",   f"{fuel_eff:.2f} km/L" if fuel_eff > 0 else "—")
        _risk_label = ("● Low Risk" if risk_score < 33
                       else "● Medium Risk" if risk_score < 66
                       else "● High Risk")
        c5.metric("Trip Risk", _risk_label)

        if revenue > 0:
            _margin = (profit_trip / revenue * 100) if revenue > 0 else 0
            _colour = "normal" if profit_trip > 0 else "inverse"
            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("Revenue",  f"E {revenue:,.0f}")
            col_p2.metric("Total Cost", f"E {total_expenses + actual_fuel_cost + maint_cost:,.0f}")
            col_p3.metric("Profit",   f"E {profit_trip:,.0f}",
                delta=f"{_margin:.1f}% margin", delta_color=_colour)

        if incident_occurred:
            st.warning(f"⚠️ Incident recorded: {incident_type} — E{incident_cost:,.0f}. Ensure fleet manager is notified.")
        if len(compliance_checked) < len(COMPLIANCE_ITEMS):
            missing = len(COMPLIANCE_ITEMS) - len(compliance_checked)
            st.warning(f"⚠️ {missing} compliance item(s) were not checked — review before next run.")

        # ── Route map for logged trip ─────────────────────────────────────────
        if origin and destination:
            try:
                from maps.route_map import (
                    render_route_map, render_route_summary,
                    render_border_status, render_elevation_profile,
                )
                st.divider()
                st.markdown("**Trip Route Map**")
                _mc, _sc = st.columns([3, 1])
                with _mc:
                    render_route_map(
                        origin=origin, destination=destination,
                        risk_score=risk_score,
                        weather_condition=auto_weather,
                        distance_km=effective_distance,
                        duration_hrs=trip_duration,
                    )
                with _sc:
                    render_route_summary(
                        origin=origin, destination=destination,
                        distance_km=effective_distance,
                        duration_hrs=trip_duration,
                        risk_score=risk_score,
                        border_crossings=border_crossings,
                        payload_kg=load_kg,
                    )
                    render_border_status(origin, destination)
                render_elevation_profile(origin, destination)
            except Exception as _me:
                pass

    except Exception as e:
        logger.error("trip_log: DB insert failed: %s", e)
        st.error(f"❌ Error logging trip: {e}")
