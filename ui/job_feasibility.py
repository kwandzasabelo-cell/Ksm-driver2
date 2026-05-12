# ui/job_feasibility.py — Job Feasibility Engine (Phase 1 & 2)
from __future__ import annotations
import logging
import streamlit as st
import pandas as pd
from utils.error_handler import safe_page

from core.config import (
    FUEL_PRICE_DEFAULT, SERVICE_INTERVAL_KM, FUEL_EFFICIENCY_BASE,
    HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD,
    LOCATION_COORDS, VEHICLE_SPEED_PROFILES, TRUCK_TARE_KG,
    DRIVER_RATE_PER_HR, OPPORTUNITY_COST_HR,
)
from core.hgv_profiles import (
    HGV_PROFILES, BORDER_COSTS, CARGO_PROFILES, TOLL_COSTS,
    MIN_RATE_PER_KM, TARGET_MARGIN_PCT, MIN_MARGIN_PCT,
    get_profile, get_hgv_types, get_hgv_types_by_category,
    estimate_fuel_cost, estimate_total_cost,
    DRIVER_SUBSISTENCE_PER_NIGHT, DRIVER_CROSS_BORDER_ALLOWANCE,
)
from services.market_data import fetch_weather_for_location, fetch_ors_route
from services.routes import get_routes_for_pair, ml_route_advisor
from maps.route_map import render_route_map

logger = logging.getLogger(__name__)


def _lm():
    return st.session_state.get("logistics_manager")


def _flag(level: str, msg: str) -> None:
    if level == "error":   st.error(f"⛔ {msg}")
    elif level == "warning": st.warning(f"⚠️ {msg}")
    else:                  st.info(f"ℹ️ {msg}")


def _cost_row(label: str, amount: float, pct: float = 0) -> str:
    pct_str = f"&nbsp;&nbsp;<span style='color:#64748b;font-size:.75rem;'>({pct:.1f}%)</span>" if pct else ""
    return (
        f"<tr><td style='padding:4px 8px;color:#94a3b8;'>{label}</td>"
        f"<td style='padding:4px 8px;text-align:right;color:#e2e8f0;font-weight:600;'>"
        f"E {amount:,.0f}{pct_str}</td></tr>"
    )


@safe_page
def render_job_feasibility_tab(conn) -> None:
    st.markdown("### Job Feasibility Analysis")
    st.caption("Enter job details below to get a full cost breakdown, profit estimate, and go/no-go decision.")

    try:
        trucks_df = pd.read_sql_query("SELECT * FROM Truck", conn)
        if trucks_df.empty:
            st.warning("No trucks registered. Add trucks in Fleet Management first.")
            return
    except Exception as e:
        st.error(f"Could not load fleet: {e}")
        return

    # ── Live fuel price ────────────────────────────────────────────────────────
    try:
        from services.market_data import fetch_live_market_data
        mkt = fetch_live_market_data()
        live_fuel = float(mkt.get("fuel_price", FUEL_PRICE_DEFAULT))
    except Exception:
        live_fuel = float(FUEL_PRICE_DEFAULT)

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — TRUCK & HGV CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("#### 1. Truck & Vehicle Configuration")
    fc1, fc2, fc3 = st.columns(3)

    with fc1:
        sel_truck  = st.selectbox("Select Truck", trucks_df["registration"].tolist())
        truck_row  = trucks_df[trucks_df["registration"] == sel_truck].iloc[0]
        # Use stored HGV type or default
        stored_hgv = truck_row.get("hgv_type") or "Superlink — Tautliner"
        hgv_types  = get_hgv_types()
        hgv_idx    = hgv_types.index(stored_hgv) if stored_hgv in hgv_types else 0
        hgv_type   = st.selectbox("HGV Configuration", hgv_types, index=hgv_idx)

    profile = get_profile(hgv_type)

    with fc2:
        st.markdown("**Auto-loaded from HGV profile:**")
        st.markdown(f"- Max payload: **{profile['max_payload_kg']:,} kg**")
        st.markdown(f"- Fuel (loaded): **{profile['fuel_l_per_100km_loaded']} L/100km**")
        st.markdown(f"- Tyres: **{profile['num_tyres']} tyres**")
        if profile["requires_reefer"]:
            st.info("❄️ Refrigerated unit — reefer fuel cost included")
        if profile["abnormal_permit"]:
            st.warning("⚠️ Abnormal load — permit cost included")
        if profile["hazmat_capable"]:
            st.info("☣️ Hazmat capable — verify cargo permit")

    with fc3:
        st.markdown("**Truck Status:**")
        svc_gap = float(truck_row.get("mileage", 0)) - float(truck_row.get("last_service_km", 0))
        svc_int = float(truck_row.get("service_interval") or SERVICE_INTERVAL_KM)
        svc_pct = min(100, (svc_gap / svc_int) * 100) if svc_int > 0 else 0
        svc_label = "🟢 Good" if svc_pct < 60 else ("🟡 Due soon" if svc_pct < 90 else "🔴 OVERDUE")
        st.markdown(f"- Service: **{svc_label}** ({svc_pct:.0f}% of interval)")
        st.markdown(f"- Odometer: **{float(truck_row.get('mileage',0)):,.0f} km**")
        age = truck_row.get("truck_age_years") or 0
        st.markdown(f"- Age: **{age:.1f} years**")
        ins_month = float(truck_row.get("insurance_monthly") or profile["insurance_per_month"])
        st.markdown(f"- Insurance: **E {ins_month:,.0f}/month**")

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — ROUTE & CARGO
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("#### 2. Route & Cargo")
    rc1, rc2, rc3 = st.columns(3)

    with rc1:
        col_fa, col_fb = st.columns(2)
        with col_fa:
            origin = st.text_input("Origin",
                placeholder="e.g. Manzini CBD, Eswatini",
                value=st.session_state.get("_feas_origin", "Manzini"),
                key="feas_origin")
        with col_fb:
            destination = st.text_input("Destination",
                placeholder="e.g. Johannesburg Kaserne, Gauteng",
                value=st.session_state.get("_feas_dest", "Johannesburg"),
                key="feas_dest")
        st.session_state["_feas_origin"] = origin
        st.session_state["_feas_dest"]   = destination
        border_list= list(BORDER_COSTS.keys())
        borders_selected = st.multiselect(
            "Border Crossings",
            border_list,
            default=["None (domestic)"],
            help="Select each border crossing on this route"
        )
        num_borders = len([b for b in borders_selected if b != "None (domestic)"])

    with rc2:
        cargo_types = list(CARGO_PROFILES.keys())
        cargo_type  = st.selectbox("Cargo Type", cargo_types)
        cargo_profile = CARGO_PROFILES[cargo_type]
        payload_kg  = st.number_input(
            "Payload (kg)", min_value=0.0,
            max_value=float(profile["max_payload_kg"]),
            value=min(20000.0, float(profile["max_payload_kg"])),
            step=500.0,
            help=f"Max for this HGV: {profile['max_payload_kg']:,} kg"
        )
        payload_tons = payload_kg / 1000
        cargo_value  = st.number_input("Cargo Value (E)", min_value=0.0, value=80000.0, step=5000.0)
        if cargo_profile["reefer_required"] and not profile["requires_reefer"]:
            st.warning("⚠️ This cargo requires refrigeration but selected HGV is not a reefer unit.")
        if cargo_profile["requires_permit"]:
            st.warning("⚠️ This cargo requires a special transport permit.")

    with rc3:
        return_load = st.radio(
            "Return Load",
            ["✅ Return load secured", "❌ No return load (empty run)"],
            help="Empty return doubles your effective cost per km"
        )
        return_empty = "❌" in return_load
        if return_empty:
            st.warning("Empty return doubles effective cost/km. Seek a backhaul.")

        route_dist_km = st.number_input(
            "Route Distance (km)", min_value=1.0, value=420.0, step=10.0,
            help="One-way distance. Return leg calculated automatically."
        )
        trip_duration_days = st.number_input(
            "Estimated Trip Duration (days)", min_value=0.5, value=2.0, step=0.5,
            help="Total days truck is away including loading/offloading"
        )
        nights_away = max(0, trip_duration_days - 1)

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — PRICING
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("#### 3. Pricing & Revenue")
    pr1, pr2, pr3 = st.columns(3)

    with pr1:
        billing_method = st.selectbox(
            "Billing Method",
            ["Per km (one way)", "Per km (both ways)", "Per ton-km", "Flat rate"]
        )
        quoted_rate = st.number_input(
            "Quoted Rate (E/km)" if "Per km" in billing_method or "ton" in billing_method else "Flat Rate (E)",
            min_value=0.0, value=30.0 if "km" in billing_method else 12600.0,
            step=0.50
        )
        # Calculate gross revenue
        if billing_method == "Per km (one way)":
            gross_revenue = quoted_rate * route_dist_km
        elif billing_method == "Per km (both ways)":
            gross_revenue = quoted_rate * route_dist_km * 2
        elif billing_method == "Per ton-km":
            gross_revenue = quoted_rate * route_dist_km * payload_tons
        else:
            gross_revenue = quoted_rate
        st.metric("Gross Revenue", f"E {gross_revenue:,.0f}")

    with pr2:
        fuel_price = st.number_input(
            "Fuel Price (E/L)", min_value=10.0, value=live_fuel, step=0.10,
            help="Current pump price — auto-filled from live market data"
        )
        payment_terms = st.selectbox(
            "Payment Terms",
            ["COD (Cash on Delivery)", "7 Days", "30 Days", "60 Days"],
        )
        client_credit = st.selectbox(
            "Client Credit Risk",
            ["✅ Good — reliable payer", "🟡 Average — occasional delays", "🔴 Poor — payment risk"]
        )

    with pr3:
        fuel_escalation = st.checkbox(
            "Fuel escalation clause",
            value=True,
            help="Rate adjusts if fuel moves more than E1.50/L from today"
        )
        vat_applicable = st.checkbox("VAT Applicable (15%)", value=False)
        currency = st.selectbox("Invoice Currency", ["SZL (E)", "ZAR (R)", "USD ($)", "MZN"])

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTION 4 — DRIVER & OPERATING COSTS
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("#### 4. Driver & Operating Costs")
    dr1, dr2, dr3 = st.columns(3)

    with dr1:
        driver_salary = st.number_input(
            "Driver Salary (E/month)", min_value=0.0, value=12000.0, step=500.0
        )
        driver_exp = st.slider("Driver Experience (years)", 0, 30, 5)
        monthly_km = st.number_input(
            "Truck Monthly Distance (km)", min_value=1000.0, value=10000.0, step=500.0,
            help="Used to allocate fixed costs per km"
        )

    with dr2:
        toll_cost  = st.number_input(
            "Toll Fees (E)", min_value=0.0,
            value=float(TOLL_COSTS.get(f"{origin} → {destination}", TOLL_COSTS["Default"])),
            step=50.0
        )
        other_expenses = st.number_input(
            "Other Trip Expenses (E)", min_value=0.0, value=0.0, step=100.0,
            help="Parking, port fees, handling charges, etc."
        )
        departure_hour = st.slider("Planned Departure Hour", 0, 23, 6,
            help="Night driving increases risk score")

    with dr3:
        ins_override = st.number_input(
            "Insurance (E/month) — override",
            min_value=0.0,
            value=float(truck_row.get("insurance_monthly") or profile["insurance_per_month"]),
            step=500.0
        )
        fin_monthly = float(truck_row.get("finance_monthly") or 0)
        tracker_m   = float(truck_row.get("tracker_monthly") or 850)
        st.markdown(f"Finance payment: **E {fin_monthly:,.0f}/month**")
        st.markdown(f"Tracker/telematics: **E {tracker_m:,.0f}/month**")

    # ═══════════════════════════════════════════════════════════════════════════
    # RUN ANALYSIS BUTTON
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    run_btn = st.button("▶  Run Full Analysis", type="primary", use_container_width=True)

    if not run_btn:
        # Show live break-even preview even before full analysis
        preview_cost = estimate_total_cost(
            hgv_type=hgv_type,
            distance_km=route_dist_km,
            payload_kg=payload_kg,
            fuel_price_per_l=fuel_price,
            driver_salary_month=driver_salary,
            monthly_km=monthly_km,
            num_borders=num_borders,
            border_names=borders_selected,
            cargo_type=cargo_type,
            cargo_value=cargo_value,
            num_nights=nights_away,
            toll_cost=toll_cost + other_expenses,
            return_empty=return_empty,
            trip_duration_days=trip_duration_days,
        )
        breakeven = preview_cost["total"] / route_dist_km if route_dist_km > 0 else 0
        pv1, pv2, pv3 = st.columns(3)
        pv1.metric("Estimated Cost", f"E {preview_cost['total']:,.0f}")
        pv2.metric("Break-Even Rate", f"E {breakeven:.2f}/km")
        margin = ((gross_revenue - preview_cost["total"]) / gross_revenue * 100) if gross_revenue > 0 else 0
        pv3.metric("Estimated Margin", f"{margin:.1f}%",
                   delta="▲ Profitable" if margin >= MIN_MARGIN_PCT else "▼ Review pricing")
        return

    # ═══════════════════════════════════════════════════════════════════════════
    # FULL ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    # Live weather
    try:
        from services.gps_routing import geocode as _gc, get_road_distance as _grd
        origin_coords = _gc(origin) or (-26.485, 31.360)
    except Exception:
        origin_coords = LOCATION_COORDS.get(origin, (-26.485, 31.360))
    with st.spinner("Fetching live weather…"):
        try:
            live_weather = fetch_weather_for_location(origin_coords[0], origin_coords[1], origin)
        except Exception:
            live_weather = {"weather_condition": "Clear", "source": "default", "timestamp": "—"}

    # ORS routing
    ors_route = None
    ors_key = st.session_state.get("ors_api_key", "")
    if ors_key:
        try:
            dest_coords = _gc(destination) or (-26.204, 28.047)
        except Exception:
            dest_coords = LOCATION_COORDS.get(destination, (-26.204, 28.047))
        with st.spinner("Fetching HGV route…"):
            try:
                total_weight = int(payload_kg + profile["tare_kg"])
                ors_route    = fetch_ors_route(origin_coords, dest_coords, total_weight, ors_key)
                if ors_route and "error" not in ors_route:
                    route_dist_km = ors_route.get("distance_km", route_dist_km)
            except Exception as e:
                logger.warning("ORS failed: %s", e)

    # Full cost breakdown
    costs = estimate_total_cost(
        hgv_type=hgv_type,
        distance_km=route_dist_km,
        payload_kg=payload_kg,
        fuel_price_per_l=fuel_price,
        driver_salary_month=driver_salary,
        monthly_km=monthly_km,
        num_borders=num_borders,
        border_names=borders_selected,
        cargo_type=cargo_type,
        cargo_value=cargo_value,
        num_nights=nights_away,
        toll_cost=toll_cost + other_expenses,
        return_empty=return_empty,
        trip_duration_days=trip_duration_days,
    )

    total_cost     = costs["total"]
    profit         = gross_revenue - total_cost
    margin_pct     = (profit / gross_revenue * 100) if gross_revenue > 0 else -100
    breakeven_rate = total_cost / route_dist_km if route_dist_km > 0 else 0
    rev_per_tonkm  = gross_revenue / (route_dist_km * payload_tons) if payload_tons > 0 else 0
    cost_per_km    = total_cost / route_dist_km if route_dist_km > 0 else 0
    eff_dist       = costs["effective_distance"]

    # ── Decision flags ────────────────────────────────────────────────────────
    flags = []
    if profit < 0:
        flags.append(("error", f"This job runs at a LOSS of E {abs(profit):,.0f}"))
    if margin_pct < MIN_MARGIN_PCT and profit >= 0:
        flags.append(("warning", f"Margin of {margin_pct:.1f}% is below the {MIN_MARGIN_PCT:.0f}% minimum target"))
    if billing_method == "Per km (one way)" and quoted_rate < breakeven_rate:
        flags.append(("error", f"Quoted rate E {quoted_rate:.2f}/km is below break-even of E {breakeven_rate:.2f}/km"))
    # Check minimum rate
    route_type = "Local (within Eswatini)" if num_borders == 0 else "Cross-border (SA↔SWZ)"
    min_rate = MIN_RATE_PER_KM.get(route_type, 22.0)
    if "Per km" in billing_method and quoted_rate < min_rate:
        flags.append(("warning", f"Rate E {quoted_rate:.2f}/km is below market minimum of E {min_rate:.2f}/km for this route type"))
    if return_empty:
        flags.append(("warning", f"Empty return adds E {costs['fuel_cost'] * 0.5:,.0f} in unrecovered fuel cost"))
    if payload_kg > profile["max_payload_kg"] * 0.95:
        flags.append(("warning", f"Payload is at {(payload_kg/profile['max_payload_kg']*100):.0f}% of GCM limit — verify at weigh bridge"))
    if svc_pct >= 100:
        flags.append(("error", f"Truck {sel_truck} is OVERDUE for service — do not dispatch"))
    elif svc_pct >= 80:
        flags.append(("warning", f"Truck {sel_truck} is {svc_pct:.0f}% through service interval — schedule service soon"))
    if "🔴" in client_credit:
        flags.append(("warning", "Client has poor credit rating — consider requiring upfront payment or deposit"))
    if departure_hour >= 22 or departure_hour <= 4:
        flags.append(("warning", "Night departure (22:00–04:00) increases fatigue risk and accident probability"))
    if cargo_profile["reefer_required"] and not profile["requires_reefer"]:
        flags.append(("error", "Selected HGV cannot handle this cargo — reefer unit required"))
    if profile["abnormal_permit"]:
        flags.append(("warning", "Abnormal load permit required — allow 5–10 working days for approval"))
    if num_borders >= 2:
        flags.append(("warning", f"{num_borders} border crossings — allow extra time for documentation and delays"))

    # ═══════════════════════════════════════════════════════════════════════════
    # RESULTS DISPLAY
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("### Analysis Results")

    # Decision banner
    if profit > 0 and margin_pct >= TARGET_MARGIN_PCT:
        decision_color = "#166534"; decision_bg = "#dcfce7"; decision = "✅  ACCEPT JOB"
        decision_sub   = f"Profitable at {margin_pct:.1f}% margin — above {TARGET_MARGIN_PCT:.0f}% target"
    elif profit > 0 and margin_pct >= MIN_MARGIN_PCT:
        decision_color = "#854d0e"; decision_bg = "#fef9c3"; decision = "⚠️  PROCEED WITH CAUTION"
        decision_sub   = f"Margin of {margin_pct:.1f}% is acceptable but below the {TARGET_MARGIN_PCT:.0f}% target"
    elif profit > 0:
        decision_color = "#7c2d12"; decision_bg = "#ffedd5"; decision = "⚠️  MARGINAL — REVIEW PRICING"
        decision_sub   = f"Only {margin_pct:.1f}% margin — negotiate a higher rate or reduce costs"
    else:
        decision_color = "#7f1d1d"; decision_bg = "#fee2e2"; decision = "⛔  REJECT — LOSS-MAKING"
        decision_sub   = f"Job loses E {abs(profit):,.0f} — rate too low or costs too high"

    st.markdown(
        f"<div style='background:{decision_bg};border-left:6px solid {decision_color};"
        f"border-radius:10px;padding:18px 24px;margin-bottom:16px;'>"
        f"<div style='font-size:1.3rem;font-weight:900;color:{decision_color};'>{decision}</div>"
        f"<div style='font-size:.9rem;color:{decision_color};margin-top:4px;'>{decision_sub}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Flags
    if flags:
        for level, msg in flags:
            _flag(level, msg)
        st.markdown("")

    # KPI row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Gross Revenue",   f"E {gross_revenue:,.0f}")
    k2.metric("Total Cost",      f"E {total_cost:,.0f}")
    k3.metric("Profit",          f"E {profit:,.0f}",
              delta=f"{margin_pct:.1f}% margin")
    k4.metric("Break-even Rate", f"E {breakeven_rate:.2f}/km")
    k5.metric("Rev per Ton-km",  f"E {rev_per_tonkm:.3f}")

    st.divider()

    # Cost breakdown table + route summary side by side
    col_cost, col_route = st.columns([1, 1])

    with col_cost:
        st.markdown("**Cost Breakdown**")
        rows_html = "".join([
            _cost_row("Fuel",              costs["fuel_cost"],        costs["fuel_cost"]/total_cost*100),
            _cost_row("Tyres (wear)",       costs["tyre_cost"],        costs["tyre_cost"]/total_cost*100),
            _cost_row("Maintenance",        costs["maintenance_cost"], costs["maintenance_cost"]/total_cost*100),
            _cost_row("Depreciation",       costs["depreciation"],     costs["depreciation"]/total_cost*100),
            _cost_row("Insurance",          costs["insurance_trip"],   costs["insurance_trip"]/total_cost*100),
            _cost_row("Driver (salary+all)",costs["driver_cost"]+costs["subsistence"]+costs["border_allowance"],
                      (costs["driver_cost"]+costs["subsistence"]+costs["border_allowance"])/total_cost*100),
            _cost_row("Border fees",        costs["border_fees"],      costs["border_fees"]/total_cost*100),
            _cost_row("Tolls & other",      costs["toll_cost"],        costs["toll_cost"]/total_cost*100),
            _cost_row("Cargo insurance",    costs["cargo_insurance"],  costs["cargo_insurance"]/total_cost*100),
            _cost_row("Permits (haz/abn)",  costs["hazmat_permit"]+costs["abnormal_permit"], 0),
        ])
        st.markdown(
            f"<table style='width:100%;border-collapse:collapse;font-size:.82rem;'>"
            f"{rows_html}"
            f"<tr style='border-top:1px solid #334155;'>"
            f"<td style='padding:6px 8px;font-weight:800;color:#e2e8f0;'>TOTAL</td>"
            f"<td style='padding:6px 8px;text-align:right;font-weight:900;color:#60a5fa;font-size:1rem;'>"
            f"E {total_cost:,.0f}</td></tr>"
            f"</table>",
            unsafe_allow_html=True,
        )
        if return_empty:
            st.caption(f"⚠️ Includes empty return leg ({route_dist_km:.0f} km both ways = {eff_dist:.0f} km effective)")

    with col_route:
        st.markdown("**Route Summary**")
        # Border waiting cost
        total_border_wait = sum(
            BORDER_COSTS.get(b, {}).get("avg_wait_hrs", 0)
            for b in borders_selected if b != "None (domestic)"
        )
        idling_fuel_cost = total_border_wait * (profile["fuel_l_per_100km_loaded"]/100 * 10) * fuel_price

        st.markdown(
            f"<div style='background:rgba(15,23,42,.8);border-radius:10px;padding:14px;"
            f"border-left:4px solid #3b82f6;font-size:.83rem;line-height:2.0;color:#e2e8f0;'>"
            f"<b>Origin:</b> {origin}<br>"
            f"<b>Destination:</b> {destination}<br>"
            f"<b>Distance:</b> {route_dist_km:,.0f} km (one way)<br>"
            f"<b>Effective km:</b> {eff_dist:,.0f} km {'(incl. empty return)' if return_empty else ''}<br>"
            f"<b>HGV Type:</b> {hgv_type}<br>"
            f"<b>Payload:</b> {payload_tons:.1f} tons ({payload_kg:,.0f} kg)<br>"
            f"<b>Cargo:</b> {cargo_type}<br>"
            f"<b>Borders:</b> {num_borders} crossing(s)<br>"
            f"<b>Border wait:</b> ~{total_border_wait:.1f} hrs (est. idling E {idling_fuel_cost:,.0f})<br>"
            f"<b>Nights away:</b> {nights_away:.0f}<br>"
            f"<b>Weather:</b> {live_weather.get('weather_condition','—')}<br>"
            f"<b>Cost/km:</b> E {cost_per_km:.2f}<br>"
            f"<b>Break-even rate:</b> E {breakeven_rate:.2f}/km<br>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Profitability bar
    st.divider()
    bar_pct = min(100, max(0, margin_pct))
    bar_col = "#22c55e" if margin_pct >= TARGET_MARGIN_PCT else ("#f59e0b" if margin_pct >= MIN_MARGIN_PCT else "#ef4444")
    st.markdown(
        f"<div style='margin-bottom:4px;font-size:.8rem;color:#94a3b8;'>Profit Margin: {margin_pct:.1f}%"
        f" &nbsp;|&nbsp; Target: {TARGET_MARGIN_PCT:.0f}%</div>"
        f"<div style='background:rgba(255,255,255,.08);border-radius:6px;height:12px;'>"
        f"<div style='background:{bar_col};width:{bar_pct:.0f}%;height:12px;border-radius:6px;"
        f"transition:width 0.5s;'></div></div>",
        unsafe_allow_html=True,
    )

    # Route map
    st.divider()
    st.markdown("**Route Map & Analysis**")
    try:
        risk_score = 50 - (driver_exp * 2) + (num_borders * 10) + (20 if return_empty else 0)
        risk_score = max(5, min(95, risk_score))

        # Side-by-side: map + summary
        map_col, sum_col = st.columns([3, 1])
        with map_col:
            render_route_map(
                origin=origin, destination=destination,
                ors_route=ors_route, risk_score=risk_score,
                weather_condition=live_weather.get("weather_condition", "Clear"),
                distance_km=route_dist_km,
                duration_hrs=route_dist_km / 70.0,
            )
        with sum_col:
            from maps.route_map import render_route_summary, render_border_status
            render_route_summary(
                origin=origin, destination=destination,
                distance_km=route_dist_km,
                duration_hrs=route_dist_km / 70.0,
                risk_score=risk_score,
                border_crossings=num_borders,
                payload_kg=payload_kg,
            )
            render_border_status(origin, destination)

        # Elevation profile below map
        from maps.route_map import render_elevation_profile
        render_elevation_profile(origin, destination)

    except Exception as e:
        st.info(f"Map unavailable: {e}")

    # AI Route Advisor
    try:
        available_routes = get_routes_for_pair(origin, destination)
        if available_routes:
            st.divider()
            st.markdown("**AI Route Recommendation**")
            advice = ml_route_advisor(
                routes=available_routes,
                vehicle_type=hgv_type,
                cargo_kg=payload_kg,
                weather=live_weather.get("weather_condition", "Clear"),
                departure_hour=departure_hour,
                priority="Most Economical",
            )
            best_r = advice["best"]
            r_cost = best_r.get("total_cost", 0)
            st.success(
                f"✅ **Best route: {best_r['route']['name']}** — "
                f"ETA {best_r['travel']['eta_str']} · "
                f"Fuel {best_r['fuel_litres']:.0f} L · "
                f"Route cost E {r_cost:,.0f}"
            )
            for reason in advice.get("reasons", [])[:3]:
                st.markdown(f"  {reason}")
    except Exception as e:
        logger.debug("Route advisor: %s", e)

    # Export cost breakdown
    st.divider()
    from utils.exports import export_buttons
    cost_df = pd.DataFrame([
        {"Item": "Fuel",              "Cost (E)": costs["fuel_cost"]},
        {"Item": "Tyres",             "Cost (E)": costs["tyre_cost"]},
        {"Item": "Maintenance",       "Cost (E)": costs["maintenance_cost"]},
        {"Item": "Depreciation",      "Cost (E)": costs["depreciation"]},
        {"Item": "Insurance",         "Cost (E)": costs["insurance_trip"]},
        {"Item": "Driver salary",     "Cost (E)": costs["driver_cost"]},
        {"Item": "Subsistence",       "Cost (E)": costs["subsistence"]},
        {"Item": "Border allowance",  "Cost (E)": costs["border_allowance"]},
        {"Item": "Border fees",       "Cost (E)": costs["border_fees"]},
        {"Item": "Tolls & expenses",  "Cost (E)": costs["toll_cost"]},
        {"Item": "Cargo insurance",   "Cost (E)": costs["cargo_insurance"]},
        {"Item": "Permits",           "Cost (E)": costs["hazmat_permit"] + costs["abnormal_permit"]},
        {"Item": "TOTAL COST",        "Cost (E)": total_cost},
        {"Item": "Gross Revenue",     "Cost (E)": gross_revenue},
        {"Item": "Profit",            "Cost (E)": profit},
        {"Item": "Margin %",          "Cost (E)": round(margin_pct, 2)},
    ])
    export_buttons(cost_df, f"ksm_feasibility_{origin.lower()}_{destination.lower()}", "Feasibility")
