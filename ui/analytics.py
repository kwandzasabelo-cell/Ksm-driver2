# ui/analytics.py — Analytics page module
from __future__ import annotations
from utils.error_handler import safe_page
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from utils.exports import export_buttons
from core.config import (
    MAX_PAYLOAD_KG, FUEL_PRICE_DEFAULT, MAINTENANCE_PER_KM,
    HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD,
    FUEL_CONSUMPTION_BASE_L_PER_100KM,
)
from core.database import get_connection


def _risk_label(score) -> str:
    """Convert numeric risk score to plain English."""
    try:
        s = float(score)
        if s < 33:  return "● Low"
        if s < 66:  return "● Medium"
        return "● High"
    except Exception:
        return "—"


@safe_page
def advanced_analytics_module():
    st.subheader(" Advanced Fleet Analytics")
    conn = get_connection()

    try:
        # ── Date filter ──────────────────────────────────────────────────────
        st.markdown("#### Filter")
        f1, f2, f3 = st.columns([1, 1, 2])
        with f1:
            date_from = st.date_input("From", value=date.today() - timedelta(days=90), key="an_from")
        with f2:
            date_to = st.date_input("To", value=date.today(), key="an_to")
        with f3:
            truck_filter_df = pd.read_sql_query("SELECT registration FROM Truck", conn)
            truck_options = ["All Trucks"] + truck_filter_df['registration'].tolist()
            truck_filter = st.selectbox("Truck", truck_options, key="an_truck")

        truck_clause = ""
        truck_params: list = [str(date_from), str(date_to)]
        if truck_filter != "All Trucks":
            truck_clause = "AND T.registration = ?"
            truck_params.append(truck_filter)

        # ── Main aggregation — only trips with hard_braking_events recorded ──
        # risk_score is now written on every trip log; avg_braking uses real logged values
        analytics_df = pd.read_sql_query(f"""
            SELECT T.registration,
                   T.mileage, T.last_service_km, T.fuel_efficiency_baseline,
                   T.rolling_fuel_efficiency,
                   COUNT(TR.trip_id)                     as trip_count,
                   SUM(TR.distance)                      as total_km,
                   AVG(TR.actual_fuel_efficiency)        as avg_efficiency,
                   AVG(TR.predicted_fuel_efficiency)     as avg_predicted_efficiency,
                   AVG(NULLIF(TR.hard_braking_events,0)) as avg_braking,
                   AVG(TR.idle_time_minutes)             as avg_idle,
                   AVG(NULLIF(TR.risk_score,0))          as avg_risk,
                   SUM(TR.revenue)                       as total_revenue,
                   SUM(TR.actual_fuel_cost)              as total_fuel_cost,
                   SUM(TR.distance * ?)                  as total_maint_cost
            FROM Truck T
            LEFT JOIN Trip TR ON T.truck_id = TR.truck_id
                AND TR.date >= ? AND TR.date <= ?
                {truck_clause}
            GROUP BY T.registration
        """, conn, params=[MAINTENANCE_PER_KM] + truck_params).fillna(0)

        analytics_df = analytics_df[analytics_df['trip_count'] > 0]

        if analytics_df.empty:
            st.info("No trip data for the selected filters. Log trips to see analytics.")
            conn.close()
            return

        # ── Summary KPIs ─────────────────────────────────────────────────────
        st.divider()
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total Trips", int(analytics_df['trip_count'].sum()))
        k2.metric("Total Distance", f"{analytics_df['total_km'].sum():,.0f} km")
        k3.metric("Total Revenue", f"E {analytics_df['total_revenue'].sum():,.0f}")
        total_costs = analytics_df['total_fuel_cost'].sum() + analytics_df['total_maint_cost'].sum()
        k4.metric("Total Est. Costs", f"E {total_costs:,.0f}")
        net = analytics_df['total_revenue'].sum() - total_costs
        k5.metric("Net Profit (est.)", f"E {net:,.0f}", delta=f"E {net:,.0f}")

        st.divider()

        # ── Row 1: Efficiency + Risk ─────────────────────────────────────────
        c1, c2 = st.columns(2)
        with c1:
            eff_df = analytics_df[analytics_df['avg_efficiency'] > 0].copy()
            if not eff_df.empty:
                # Show both actual and baseline for comparison
                fig = go.Figure()
                fig.add_bar(x=eff_df['registration'], y=eff_df['avg_efficiency'],
                            name='Actual (avg)', marker_color='#10b981')
                fig.add_bar(x=eff_df['registration'], y=eff_df['fuel_efficiency_baseline'],
                            name='Baseline (registered)', marker_color='#93c5fd')
                if eff_df['rolling_fuel_efficiency'].sum() > 0:
                    fig.add_bar(x=eff_df['registration'], y=eff_df['rolling_fuel_efficiency'],
                                name='Rolling (full-tank pairs)', marker_color='#f59e0b')
                fig.update_layout(title='Fuel Efficiency by Truck (km/L)',
                                  barmode='group', legend=dict(orientation='h'))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No fuel efficiency data yet.")

        with c2:
            risk_df = analytics_df[analytics_df['avg_risk'] > 0].copy()
            if not risk_df.empty:
                fig2 = px.bar(risk_df, x='registration', y='avg_risk',
                              title='Average Risk Score by Truck (from logged trips)',
                              color='avg_risk', color_continuous_scale='Reds',
                              labels={'avg_risk': 'Avg Risk Score (0–100)'})
                fig2.add_hline(y=HIGH_RISK_THRESHOLD, line_dash='dash',
                               line_color='red', annotation_text='High risk threshold')
                fig2.add_hline(y=MEDIUM_RISK_THRESHOLD, line_dash='dot',
                               line_color='orange', annotation_text='Medium risk threshold')
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Risk scores will appear here once trips are logged (scores are now saved with each trip).")

        # ── Row 2: Predicted vs Actual fuel ─────────────────────────────────
        st.divider()
        st.markdown("#### ◉ Predicted vs Actual Fuel Efficiency")
        pa_df = analytics_df[
            (analytics_df['avg_efficiency'] > 0) &
            (analytics_df['avg_predicted_efficiency'] > 0)
        ].copy()
        if not pa_df.empty:
            pa_df['variance_pct'] = ((pa_df['avg_efficiency'] - pa_df['avg_predicted_efficiency'])
                                     / pa_df['avg_predicted_efficiency'] * 100).round(1)
            pa_fig = go.Figure()
            pa_fig.add_bar(x=pa_df['registration'], y=pa_df['avg_predicted_efficiency'],
                           name='Model Prediction', marker_color='#6366f1')
            pa_fig.add_bar(x=pa_df['registration'], y=pa_df['avg_efficiency'],
                           name='Actual Logged', marker_color='#10b981')
            pa_fig.update_layout(barmode='group',
                                 title='Predicted vs Actual km/L (model accuracy check)')
            st.plotly_chart(pa_fig, use_container_width=True)
            st.caption("Positive variance = truck performing better than model predicted. "
                       "Large negative variance = model overestimating efficiency (retrain recommended).")
            st.dataframe(pa_df[['registration', 'avg_predicted_efficiency',
                                 'avg_efficiency', 'variance_pct']].rename(columns={
                'registration': 'Truck',
                'avg_predicted_efficiency': 'Predicted km/L',
                'avg_efficiency': 'Actual km/L',
                'variance_pct': 'Variance %'
            }).round(2), use_container_width=True, hide_index=True)
        else:
            st.info("Predicted vs actual comparison requires trips with both predicted and actual efficiency recorded. "
                    "Ensure the ML model is trained before running job feasibility analyses.")

        # ── Row 3: Driver Behaviour ─────────────────────────────────────────
        st.divider()
        st.markdown("#### 🚚 Driver Behaviour Analysis")
        beh_df = analytics_df[analytics_df['avg_braking'].notna() &
                               (analytics_df['avg_braking'] > 0)].copy()
        if not beh_df.empty:
            fig3 = px.scatter(
                beh_df, x='avg_braking', y='avg_idle',
                size='trip_count', color='avg_efficiency',
                color_continuous_scale='RdYlGn',
                text='registration',
                title='Driver Behaviour: Hard Braking vs Idle Time (colour = fuel efficiency)',
                labels={'avg_braking': 'Avg Hard Braking Events / Trip',
                        'avg_idle': 'Avg Idle Time (min) / Trip',
                        'avg_efficiency': 'Fuel Efficiency (km/L)'}
            )
            fig3.update_traces(textposition='top center')
            st.plotly_chart(fig3, use_container_width=True)
            st.caption("Hard braking and excessive idling are the two biggest controllable fuel wasters. "
                       "Trucks in the top-right need driver coaching.")
        else:
            st.info("Driver behaviour data will appear here once hard braking events are logged with trips. "
                    "Use the '⛔ Hard Braking Events' field when logging completed trips.")

        # ── Row 4: Trip trend over time ─────────────────────────────────────
        st.divider()
        st.markdown("#### ↑ Trip Trends Over Time")
        trend_sql = f"""
            SELECT TR.date, TR.actual_fuel_efficiency, TR.risk_score,
                   TR.distance, TR.revenue, TR.actual_fuel_cost, T.registration
            FROM Trip TR JOIN Truck T ON TR.truck_id = T.truck_id
            WHERE TR.date >= ? AND TR.date <= ?
            {'AND T.registration = ?' if truck_filter != 'All Trucks' else ''}
            ORDER BY TR.date
        """
        trend_params = [str(date_from), str(date_to)]
        if truck_filter != "All Trucks":
            trend_params.append(truck_filter)
        trend_df = pd.read_sql_query(trend_sql, conn, params=trend_params)

        if not trend_df.empty and len(trend_df) >= 2:
            t1, t2 = st.columns(2)
            with t1:
                eff_trend = trend_df[trend_df['actual_fuel_efficiency'] > 0]
                if not eff_trend.empty:
                    fig_t1 = px.line(eff_trend, x='date', y='actual_fuel_efficiency',
                                     color='registration', markers=True,
                                     title='Fuel Efficiency Trend (km/L)',
                                     labels={'actual_fuel_efficiency': 'km/L', 'date': 'Date'})
                    st.plotly_chart(fig_t1, use_container_width=True)
            with t2:
                risk_trend = trend_df[trend_df['risk_score'] > 0]
                if not risk_trend.empty:
                    fig_t2 = px.line(risk_trend, x='date', y='risk_score',
                                     color='registration', markers=True,
                                     title='Risk Score Trend',
                                     labels={'risk_score': 'Risk Score', 'date': 'Date'})
                    fig_t2.add_hline(y=HIGH_RISK_THRESHOLD, line_dash='dash', line_color='red')
                    st.plotly_chart(fig_t2, use_container_width=True)
        else:
            st.info("Need at least 2 trips in the selected period to show trends.")

        # ── Raw summary table ────────────────────────────────────────────────
        with st.expander("📋 Full Data Table"):
            st.dataframe(analytics_df.round(2), use_container_width=True, hide_index=True)
            export_buttons(analytics_df, "ksm_analytics", "Analytics")

    except Exception as e:
        st.error(f"Analytics error: {str(e)}")
    conn.close()
