# ui/market_intel.py — Market Intel page module
from __future__ import annotations
from utils.error_handler import safe_page
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from core.config import (
    FUEL_PRICE_DEFAULT, BORDER_COST_EACH, MAINTENANCE_PER_KM,
)
from core.database import get_connection
from services.market_data import fetch_live_market_data


@safe_page
def market_intel_module():
    st.subheader("🧠 Market Intelligence")

    m_data = fetch_live_market_data()
    src_badge = "● Live" if "fallback" not in m_data["source"] else " Offline (using verified defaults)"
    st.caption(f"**Data source:** {m_data['source']} &nbsp;|&nbsp; **Last updated:** {m_data['timestamp']} &nbsp;|&nbsp; {src_badge}")

    c1, c2, c3 = st.columns(3)
    c1.metric(" Fuel Price (est.)", f"E {m_data['fuel_price']:.2f}/L",
              help=m_data.get("fuel_price_note", ""))
    c2.metric(" USD/SZL", f"{m_data['usd_szl']:.2f}")
    c3.metric("️ WTI Crude Oil", f"${m_data['crude_usd']:.2f}/bbl")

    st.divider()

    # ── Fuel price note ──────────────────────────────────────────────────────
    st.info(
        "ℹ️ **About this fuel price:** Eswatini diesel prices are set monthly by the "
        "Energy Regulatory Authority (ESERA) and do not float freely with crude oil. "
        "The estimate above is derived from crude + USD/SZL and is an *indicator only*. "
        "Always confirm the current regulated pump price with your fuel supplier before budgeting."
    )

    # ── Market pressure narrative ─────────────────────────────────────────────
    st.markdown("### Market Conditions")
    crude = m_data['crude_usd']
    if crude > 100:
        pressure = " Critical — crude above $100. Government subsidy buffers may delay pump price impact, but expect upward revision at next ESERA announcement."
    elif crude > 85:
        pressure = " Elevated — crude above $85. Monitor ESERA monthly announcements for price increases."
    elif crude > 70:
        pressure = "● Moderate — crude in a normal range. No immediate price pressure expected."
    else:
        pressure = "● Low — crude below $70. Favourable conditions for locking in long-haul contracts."

    szl = m_data['usd_szl']
    if szl > 20:
        fx_note = " SZL weak against USD — imported components and tyres cost more. Factor into maintenance budgets."
    elif szl > 18:
        fx_note = "● SZL moderate. Watch for further weakening before major parts purchases."
    else:
        fx_note = "● SZL relatively strong. Good time for imported parts procurement."

    # Dynamic season note based on actual current month
    month = datetime.now().month
    if month in [6, 7, 8, 9]:
        season_note = "📅 **Current season:** Winter (Jun–Sep) — dry roads, lower accident risk. Typically higher freight demand for agricultural exports."
    elif month in [11, 12, 1, 2]:
        season_note = "📅 **Current season:** Summer rains (Nov–Feb) — wet roads increase risk scores. Allow extra travel time and review route road quality ratings."
    elif month in [3, 4, 5]:
        season_note = "📅 **Current season:** Autumn harvest (Mar–May) — sugar cane and citrus harvests active. Expect HGV congestion on MR13 corridor and at Lavumisa border."
    else:
        season_note = "📅 **Current season:** Spring (Sep–Oct) — transitional weather. Monitor Open-Meteo alerts before long-haul departures."

    st.markdown(f"""
    - **Fuel Pressure:** {pressure}
    - **FX Pressure:** {fx_note}
    - {season_note}
    - Cross-border routes: factor E {BORDER_COST_EACH:.0f} per border crossing in job pricing
    """)

    # ── Crude sensitivity chart ──────────────────────────────────────────────
    st.markdown("### ◉ Fuel Price Sensitivity to Crude Oil")
    st.caption(
        "Illustrative relationship between WTI crude and estimated Eswatini pump price at the "
        f"current exchange rate of USD/SZL = {szl:.2f}. Actual price is government-regulated."
    )
    szl_val = m_data['usd_szl']
    crude_range = list(range(60, 126, 5))
    pump_est = [round((c / 159) * szl_val * 1.75, 2) for c in crude_range]
    chart_df = pd.DataFrame({'Crude ($/bbl)': crude_range, 'Est. Pump Price (E/L)': pump_est})
    fig = px.line(chart_df, x='Crude ($/bbl)', y='Est. Pump Price (E/L)',
                  title=f'Estimated Pump Price Sensitivity (USD/SZL = {szl_val:.2f})')
    fig.add_vline(x=crude, line_dash="dash", line_color="red",
                  annotation_text=f"Current: ${crude:.0f}/bbl")
    fig.add_hline(y=m_data['fuel_price'], line_dash="dot", line_color="orange",
                  annotation_text=f"Est. pump: E{m_data['fuel_price']:.2f}/L")
    st.plotly_chart(fig, use_container_width=True)

    # ── Your fleet in context ────────────────────────────────────────────────
    st.divider()
    st.markdown("### ▣ Your Fleet in Market Context")
    conn = get_connection()
    try:
        fleet_fuel = pd.read_sql_query("""
            SELECT AVG(F.cost_per_liter) as avg_price_paid,
                   SUM(F.fuel_added)     as total_litres,
                   SUM(F.total_cost)     as total_spend,
                   COUNT(F.fuel_id)      as fill_count
            FROM FuelConsumption F
        """, conn).iloc[0]

        route_costs = pd.read_sql_query("""
            SELECT TR.start_location, TR.end_location,
                   COUNT(*)                      as trip_count,
                   AVG(TR.actual_fuel_cost)      as avg_fuel_cost,
                   AVG(TR.distance)              as avg_distance,
                   AVG(TR.actual_fuel_efficiency) as avg_efficiency
            FROM Trip TR
            WHERE TR.revenue > 0
            GROUP BY TR.start_location, TR.end_location
            ORDER BY trip_count DESC
            LIMIT 10
        """, conn)

        if float(fleet_fuel['fill_count'] or 0) > 0:
            avg_paid = float(fleet_fuel['avg_price_paid'] or 0)
            price_delta = m_data['fuel_price'] - avg_paid
            delta_dir = "⬆️ above" if price_delta > 0 else "⬇️ below"

            mx1, mx2, mx3 = st.columns(3)
            mx1.metric("Your Avg Price Paid", f"E {avg_paid:.2f}/L",
                       delta=f"E {abs(price_delta):.2f} {delta_dir} current estimate",
                       delta_color="inverse")
            mx2.metric("Total Fuel Purchased", f"{float(fleet_fuel['total_litres'] or 0):,.0f} L")
            mx3.metric("Total Fuel Spend", f"E {float(fleet_fuel['total_spend'] or 0):,.2f}")

            # Impact of current price on your common routes
            if not route_costs.empty and avg_paid > 0:
                st.markdown("#### Impact of Current Price on Your Routes")
                route_costs['price_impact_E'] = route_costs.apply(
                    lambda r: round(
                        (m_data['fuel_price'] - avg_paid) *
                        (r['avg_distance'] / max(r['avg_efficiency'], 0.1)),
                        2) if r['avg_efficiency'] > 0 else 0,
                    axis=1)
                route_costs['route'] = route_costs['start_location'] + " → " + route_costs['end_location']
                display_cols = ['route', 'trip_count', 'avg_distance',
                                'avg_efficiency', 'avg_fuel_cost', 'price_impact_E']
                st.dataframe(
                    route_costs[display_cols].rename(columns={
                        'route': 'Route', 'trip_count': 'Trips',
                        'avg_distance': 'Avg km', 'avg_efficiency': 'Avg km/L',
                        'avg_fuel_cost': 'Avg Fuel Cost (E)',
                        'price_impact_E': 'Extra Cost at Current Price (E)'
                    }).round(2),
                    use_container_width=True, hide_index=True
                )
                st.caption(
                    "Extra Cost = difference between your historical avg price paid and "
                    "today's estimated price, applied to the average fuel needed per trip. "
                    "Positive = today's fuel costs more than your historical average."
                )
        else:
            st.info("Log fuel fill-ups to see how market prices compare to what you actually pay.")
    except Exception as e:
        st.warning(f"Could not load fleet context data: {e}")
    finally:
        conn.close()
