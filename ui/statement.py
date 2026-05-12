# ui/statement.py — Statement of Account module
from __future__ import annotations
from utils.error_handler import safe_page
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from core.config import (
    MAINTENANCE_PER_KM, BORDER_COST_EACH, SERVICE_INTERVAL_KM,
    DRIVER_RATE_PER_HR,
)
from core.database import get_connection


@safe_page
def statement_of_account_module():
    st.subheader(" Statement of Account — Comprehensive Cost & Productivity Report")
    conn = get_connection()

    # ── Date filter ───────────────────────────────────────────────────────────
    today = date.today()
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    with col_f1:
        date_from = st.date_input("From Date", value=today.replace(day=1), key="soa_from")
    with col_f2:
        date_to = st.date_input("To Date", value=today, key="soa_to")
    with col_f3:
        quick = st.selectbox(
            "Quick Period",
            ["Custom", "This Month", "Last Month", "This Year", "All Time"],
            key="soa_quick",
        )

    if quick == "This Month":
        date_from = today.replace(day=1)
        date_to = today
    elif quick == "Last Month":
        first_this = today.replace(day=1)
        last_last = first_this - timedelta(days=1)
        date_from = last_last.replace(day=1)
        date_to = last_last
    elif quick == "This Year":
        date_from = today.replace(month=1, day=1)
        date_to = today
    elif quick == "All Time":
        date_from = date(2000, 1, 1)
        date_to = today

    d_from = str(date_from)
    d_to = str(date_to)
    st.markdown(f"**Period:** {d_from}  →  {d_to}")
    st.divider()

    try:
        trucks_all = pd.read_sql_query("SELECT * FROM Truck", conn)
        if trucks_all.empty:
            st.info("No trucks registered. Register trucks and log trips to generate statements.")
            conn.close()
            return

        # ── Fetch all data for the period ────────────────────────────────────
        # Use actual_fuel_cost (real price paid) not profit_margin (used default price)
        trips_df = pd.read_sql_query(f"""
            SELECT truck_id, date, distance, load, fuel_consumed,
                   actual_fuel_cost, toll_cost, revenue,
                   fuel_refill_cost, fuel_refill_litres,
                   border_crossings, trip_duration_hours,
                   actual_fuel_efficiency, driver_experience_years
            FROM Trip
            WHERE date >= '{d_from}' AND date <= '{d_to}'
        """, conn).fillna(0)

        fuel_df = pd.read_sql_query(f"""
            SELECT truck_id, date, fuel_added, total_cost, cost_per_liter
            FROM FuelConsumption
            WHERE date >= '{d_from}' AND date <= '{d_to}'
        """, conn).fillna(0)

        expenses_df = pd.read_sql_query(f"""
            SELECT truck_id, date, toll_fees, fuel_refill_cost,
                   fuel_refill_litres, other_expenses, other_description
            FROM TripExpenses
            WHERE date >= '{d_from}' AND date <= '{d_to}'
        """, conn).fillna(0)

        maint_df = pd.read_sql_query(f"""
            SELECT truck_id, date, cost, service_type, description
            FROM MaintenanceLog
            WHERE date >= '{d_from}' AND date <= '{d_to}'
        """, conn).fillna(0)

        # ── Helper: compute per-truck costs consistently ──────────────────────
        def _truck_costs(t_trips, t_fuel, t_maint, t_exp):
            """All cash costs for a truck in the period. Returns dict of line items."""
            t_km       = float(t_trips['distance'].sum())
            # Base fuel: prefer actual_fuel_cost (real price); fall back to fuel_df total
            t_fuel_actual = float(t_trips['actual_fuel_cost'].sum())
            t_fuel_log    = float(t_fuel['total_cost'].sum())
            # Use whichever is higher/more complete — logged fill-ups are ground truth
            t_fuel_cost   = t_fuel_log if t_fuel_log > 0 else t_fuel_actual
            t_refill      = float(t_trips['fuel_refill_cost'].sum())
            t_toll        = float(t_trips['toll_cost'].sum()) + (
                float(t_exp['toll_fees'].sum()) if not t_exp.empty else 0)
            t_other       = float(t_exp['other_expenses'].sum()) if not t_exp.empty else 0
            t_maint_log   = float(t_maint['cost'].sum())
            t_border      = float(t_trips['border_crossings'].sum()) * BORDER_COST_EACH
            t_run         = t_km * MAINTENANCE_PER_KM
            t_total       = t_fuel_cost + t_refill + t_toll + t_other + t_maint_log + t_border + t_run
            return {
                'fuel_cost': t_fuel_cost,
                'refill': t_refill,
                'toll': t_toll,
                'other': t_other,
                'maint_log': t_maint_log,
                'border': t_border,
                'running': t_run,
                'total': t_total,
                'km': t_km,
            }

        # ── COMPANY-WIDE EXECUTIVE SUMMARY ───────────────────────────────────
        st.markdown("## 🏢 Company-Wide Executive Summary")

        total_revenue   = float(trips_df['revenue'].sum())
        total_km        = float(trips_df['distance'].sum())
        total_trips_n   = len(trips_df)
        total_fuel_L    = float(trips_df['fuel_consumed'].sum())
        total_hours     = float(trips_df['trip_duration_hours'].sum())

        # Build company-wide costs via the same helper logic
        all_costs = _truck_costs(trips_df, fuel_df, maint_df, expenses_df)
        total_expenses   = all_costs['total']
        net_profit       = total_revenue - total_expenses
        profit_margin_pct = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        fleet_efficiency = total_km / max(1, total_fuel_L) if total_fuel_L > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric(" Total Revenue",  f"E {total_revenue:,.2f}")
        k2.metric("▦ Total Expenses", f"E {total_expenses:,.2f}")
        k3.metric("↑ Net Profit",
                  f"E {net_profit:,.2f}",
                  delta=f"{profit_margin_pct:.1f}% margin",
                  delta_color="normal" if net_profit >= 0 else "inverse")
        k4.metric("▣ Total Trips", f"{total_trips_n}")

        k5, k6, k7, k8 = st.columns(4)
        k5.metric("🗺 Total Distance",      f"{total_km:,.0f} km")
        k6.metric("◉ Fleet Fuel Used",     f"{total_fuel_L:,.0f} L")
        k7.metric("▶ Fleet Efficiency",    f"{fleet_efficiency:.2f} km/L" if fleet_efficiency > 0 else "—")
        k8.metric("⏱️ Operating Hours",     f"{total_hours:,.1f} hrs")

        # Cost breakdown pie + monthly trend
        cost_pairs = [
            ("Base Fuel (paid)", all_costs['fuel_cost']),
            ("En-Route Refill",  all_costs['refill']),
            ("Tolls",            all_costs['toll']),
            ("Other Trip Costs", all_costs['other']),
            ("Maintenance",      all_costs['maint_log']),
            ("Border Fees",      all_costs['border']),
            ("Running (E/km)",   all_costs['running']),
        ]
        nonzero = [(l, v) for l, v in cost_pairs if v > 0]

        if nonzero:
            fig_pie = px.pie(
                names=[x[0] for x in nonzero],
                values=[x[1] for x in nonzero],
                title="Company Expense Breakdown",
                color_discrete_sequence=px.colors.sequential.Blues_r,
                hole=0.4,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")

            # Monthly revenue & profit trend using actual cost data
            if not trips_df.empty:
                trips_ts = trips_df.copy()
                trips_ts['date'] = pd.to_datetime(trips_ts['date'])
                trips_ts['month'] = trips_ts['date'].dt.to_period('M').astype(str)
                # Compute actual profit per trip: revenue - actual_fuel_cost - refill - toll
                trips_ts['trip_actual_cost'] = (
                    trips_ts['actual_fuel_cost'] +
                    trips_ts['fuel_refill_cost'] +
                    trips_ts['toll_cost'] +
                    trips_ts['distance'] * MAINTENANCE_PER_KM +
                    trips_ts['border_crossings'] * BORDER_COST_EACH
                )
                trips_ts['trip_profit'] = trips_ts['revenue'] - trips_ts['trip_actual_cost']
                monthly = trips_ts.groupby('month').agg(
                    Revenue=('revenue', 'sum'),
                    Profit=('trip_profit', 'sum'),
                    Trips=('revenue', 'count'),
                ).reset_index()
                if len(monthly) > 1:
                    fig_trend = px.bar(
                        monthly, x='month', y=['Revenue', 'Profit'],
                        title='Monthly Revenue vs Profit (actual costs)',
                        barmode='group',
                        color_discrete_map={'Revenue': '#3b82f6', 'Profit': '#10b981'},
                    )
                    ch1, ch2 = st.columns(2)
                    with ch1:
                        st.plotly_chart(fig_pie, use_container_width=True)
                    with ch2:
                        st.plotly_chart(fig_trend, use_container_width=True)
                else:
                    st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()

        # ── DETAILED COST TABLE ───────────────────────────────────────────────
        st.markdown("### 📋 Company Cost Summary Table")
        st.caption(
            "ℹ️ **Fuel Cost** uses actual fill-up records where available. "
            "**Running Cost** is a per-km estimate (E{}/km) for wear not captured in service logs. "
            "Opportunity cost is excluded — it is not a cash expense.".format(MAINTENANCE_PER_KM)
        )
        summary_rows = [
            {"Cost Category": "◉ Base Fuel (actual paid)",    "Amount (E)": round(all_costs['fuel_cost'], 2),
             "Notes": f"{fuel_df['fuel_added'].sum():,.0f} L · from fill-up records"},
            {"Cost Category": "◉ En-Route Fuel Refills",      "Amount (E)": round(all_costs['refill'], 2),
             "Notes": f"{trips_df['fuel_refill_litres'].sum():,.0f} L refilled during trips"},
            {"Cost Category": "🗺 Toll Fees",                  "Amount (E)": round(all_costs['toll'], 2),
             "Notes": "All toll gates across all trucks"},
            {"Cost Category": " Other Trip Expenses",         "Amount (E)": round(all_costs['other'], 2),
             "Notes": "Parking, permits, accommodation etc."},
            {"Cost Category": "🔧 Maintenance (Logged)",       "Amount (E)": round(all_costs['maint_log'], 2),
             "Notes": f"{len(maint_df)} maintenance records"},
            {"Cost Category": "🔧 Running Cost (E/km est.)",   "Amount (E)": round(all_costs['running'], 2),
             "Notes": f"E{MAINTENANCE_PER_KM}/km × {total_km:,.0f} km"},
            {"Cost Category": "⚠ Border Fees",                "Amount (E)": round(all_costs['border'], 2),
             "Notes": f"{int(trips_df['border_crossings'].sum())} crossings × E{BORDER_COST_EACH}"},
            {"Cost Category": "▦ TOTAL EXPENSES",             "Amount (E)": round(total_expenses, 2),
             "Notes": ""},
            {"Cost Category": " TOTAL REVENUE",              "Amount (E)": round(total_revenue, 2),
             "Notes": "Revenue logged on all trips"},
            {"Cost Category": "↑ NET PROFIT / (LOSS)",        "Amount (E)": round(net_profit, 2),
             "Notes": f"Margin: {profit_margin_pct:.1f}%"},
        ]
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        st.divider()

        # ── PER-TRUCK STATEMENTS ──────────────────────────────────────────────
        st.markdown("## ▣ Per-Truck Statement of Account")
        truck_tabs = st.tabs([f"▣ {r['registration']}" for _, r in trucks_all.iterrows()])

        for i, (_, truck) in enumerate(trucks_all.iterrows()):
            with truck_tabs[i]:
                tid = int(truck['truck_id'])
                reg = truck['registration']

                t_trips = trips_df[trips_df['truck_id'] == tid].copy()
                t_fuel  = fuel_df[fuel_df['truck_id'] == tid]
                t_maint = maint_df[maint_df['truck_id'] == tid]
                t_exp   = expenses_df[expenses_df['truck_id'] == tid] if not expenses_df.empty else pd.DataFrame()

                c = _truck_costs(t_trips, t_fuel, t_maint, t_exp)
                t_revenue    = float(t_trips['revenue'].sum())
                t_km         = c['km']
                t_total_exp  = c['total']
                t_net        = t_revenue - t_total_exp
                t_margin_pct = (t_net / t_revenue * 100) if t_revenue > 0 else 0
                t_trips_n    = len(t_trips)
                t_fuel_L     = float(t_trips['fuel_consumed'].sum())
                t_hours      = float(t_trips['trip_duration_hours'].sum())
                t_eff        = t_km / max(1, t_fuel_L) if t_fuel_L > 0 else 0
                t_cost_per_km    = t_total_exp / max(1, t_km)
                t_revenue_per_km = t_revenue / max(1, t_km)

                svc_gap   = float(truck['mileage']) - float(truck['last_service_km'])
                svc_int   = float(truck.get('service_interval') or SERVICE_INTERVAL_KM)
                svc_pct   = min(100, (svc_gap / svc_int) * 100)
                svc_color = "#10b981" if svc_pct < 60 else "#f59e0b" if svc_pct < 90 else "#dc2626"
                warn_active = int(truck.get('service_warning_active') or 0)
                truck_status = str(truck.get('truck_status') or 'ACTIVE').upper()

                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#0f172a,#1e3a8a);color:white;
                            border-radius:14px;padding:20px;margin-bottom:16px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <h2 style="margin:0;font-size:22px;">▣ {reg}</h2>
                            <p style="margin:4px 0 0 0;opacity:0.75;font-size:13px;">
                                {truck['name'] or '—'} · Driver: {truck['driver'] or 'Unassigned'} ·
                                Odometer: {float(truck['mileage']):,.0f} km · Status: {truck_status}
                            </p>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:11px;opacity:0.7;">Statement Period</div>
                            <div style="font-weight:bold;">{d_from} → {d_to}</div>
                            {'<div style="background:#dc2626;border-radius:8px;padding:3px 10px;font-size:12px;margin-top:4px;">⚠️ SERVICE DUE</div>' if warn_active else ''}
                        </div>
                    </div>
                </div>""", unsafe_allow_html=True)

                tk1, tk2, tk3, tk4, tk5 = st.columns(5)
                tk1.metric(" Revenue",    f"E {t_revenue:,.2f}")
                tk2.metric("▦ Expenses",   f"E {t_total_exp:,.2f}")
                tk3.metric("↑ Net Profit", f"E {t_net:,.2f}",
                           delta=f"{t_margin_pct:.1f}%",
                           delta_color="normal" if t_net >= 0 else "inverse")
                tk4.metric("▣ Trips",      f"{t_trips_n}")
                tk5.metric("🗺 Distance",   f"{t_km:,.0f} km")

                tk6, tk7, tk8, tk9, tk10 = st.columns(5)
                tk6.metric("◉ Fuel Used",    f"{t_fuel_L:,.0f} L")
                tk7.metric("▶ Efficiency",   f"{t_eff:.2f} km/L" if t_eff > 0 else "—")
                tk8.metric(" Cost/km",       f"E {t_cost_per_km:.2f}")
                tk9.metric(" Revenue/km",    f"E {t_revenue_per_km:.2f}")
                tk10.metric("⏱️ Hours",       f"{t_hours:,.1f} hrs")

                st.markdown("#### 📋 Detailed Cost Statement")
                st.caption("Fuel cost uses actual fill-up records (ground truth). "
                           "Running cost is a per-km wear estimate.")
                truck_rows = [
                    {"Item": "◉ Fuel Cost (actual paid)",
                     "Amount (E)": round(c['fuel_cost'], 2),
                     "Detail": (f"{t_fuel['fuel_added'].sum():,.0f} L @ avg "
                                f"E{t_fuel['cost_per_liter'].mean():.2f}/L"
                                if not t_fuel.empty else "No fill-up records in period")},
                    {"Item": "◉ En-Route Fuel Refill",
                     "Amount (E)": round(c['refill'], 2),
                     "Detail": f"{t_trips['fuel_refill_litres'].sum():,.0f} L refilled during trips"},
                    {"Item": "🗺 Toll Fees",
                     "Amount (E)": round(c['toll'], 2),
                     "Detail": "All toll fees on logged trips"},
                    {"Item": " Other Trip Expenses",
                     "Amount (E)": round(c['other'], 2),
                     "Detail": "Parking, permits, accommodation etc."},
                    {"Item": "🔧 Maintenance (logged)",
                     "Amount (E)": round(c['maint_log'], 2),
                     "Detail": f"{len(t_maint)} service records" if not t_maint.empty else "No records"},
                    {"Item": "🔧 Running Cost (E/km est.)",
                     "Amount (E)": round(c['running'], 2),
                     "Detail": f"E{MAINTENANCE_PER_KM}/km × {t_km:,.0f} km"},
                    {"Item": "⚠ Border Fees",
                     "Amount (E)": round(c['border'], 2),
                     "Detail": f"{int(t_trips['border_crossings'].sum())} crossings × E{BORDER_COST_EACH}"},
                    {"Item": "▦ TOTAL EXPENSES",  "Amount (E)": round(t_total_exp, 2), "Detail": ""},
                    {"Item": " REVENUE",          "Amount (E)": round(t_revenue, 2),   "Detail": f"Across {t_trips_n} trips"},
                    {"Item": "↑ NET PROFIT / (LOSS)", "Amount (E)": round(t_net, 2),  "Detail": f"Margin: {t_margin_pct:.1f}%"},
                ]
                st.dataframe(pd.DataFrame(truck_rows), use_container_width=True, hide_index=True)

                st.markdown("#### 🔧 Service Status")
                st.markdown(f"""
                <div style="margin:6px 0 12px 0;">
                    <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                        <span>Last Service: <b>{float(truck['last_service_km']):,.0f} km</b> |
                        Current: <b>{float(truck['mileage']):,.0f} km</b> |
                        Since last service: <b>{svc_gap:,.0f} km</b></span>
                        <span style="color:{svc_color};font-weight:bold;">{svc_pct:.0f}% of {svc_int:,.0f} km interval</span>
                    </div>
                    <div style="background:#374151;border-radius:8px;height:14px;">
                        <div style="background:{svc_color};width:{svc_pct:.0f}%;height:14px;border-radius:8px;"></div>
                    </div>
                    <div style="font-size:12px;color:#94a3b8;margin-top:4px;">
                        Maintenance cost this period: <b>E {c['maint_log']:,.2f}</b> ·
                        Running cost estimate: <b>E {c['running']:,.2f}</b>
                    </div>
                </div>""", unsafe_allow_html=True)

                st.markdown("#### ▦ Productivity Metrics")
                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Revenue per Trip",  f"E {t_revenue/max(1,t_trips_n):,.2f}")
                p2.metric("Profit per Trip",   f"E {t_net/max(1,t_trips_n):,.2f}")
                p3.metric("Cost per Trip",     f"E {t_total_exp/max(1,t_trips_n):,.2f}")
                p4.metric("Avg Trip Distance", f"{t_km/max(1,t_trips_n):,.0f} km")

                # Per-trip profit chart using actual costs
                if not t_trips.empty and t_revenue > 0:
                    t_trips = t_trips.copy()
                    t_trips['trip_actual_cost'] = (
                        t_trips['actual_fuel_cost'] +
                        t_trips['fuel_refill_cost'] +
                        t_trips['toll_cost'] +
                        t_trips['distance'] * MAINTENANCE_PER_KM +
                        t_trips['border_crossings'] * BORDER_COST_EACH
                    )
                    t_trips['trip_profit'] = t_trips['revenue'] - t_trips['trip_actual_cost']
                    t_trips['Trip #'] = range(1, len(t_trips) + 1)
                    t_trips['route'] = t_trips.get('start_location', '') + '→' + t_trips.get('end_location', '')
                    fig_tp = px.bar(
                        t_trips, x='Trip #', y='trip_profit',
                        title=f'Actual Profit per Trip — {reg}',
                        color='trip_profit',
                        color_continuous_scale=['#dc2626', '#f59e0b', '#10b981'],
                        labels={'trip_profit': 'Profit (E)'},
                        hover_data=['date', 'route', 'revenue', 'actual_fuel_cost'] if 'start_location' in t_trips.columns else ['date', 'revenue'],
                    )
                    fig_tp.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
                    st.plotly_chart(fig_tp, use_container_width=True)

                if not t_maint.empty:
                    with st.expander(f"🔧 Maintenance Records for {reg} ({len(t_maint)} records)"):
                        st.dataframe(
                            t_maint[['date', 'service_type', 'description', 'cost']],
                            use_container_width=True, hide_index=True,
                        )

                if not t_trips.empty:
                    with st.expander(f"📋️ Trip Log for {reg} ({t_trips_n} trips)"):
                        show_cols = [c for c in [
                            'date', 'start_location', 'end_location', 'distance',
                            'revenue', 'fuel_consumed', 'actual_fuel_cost',
                            'toll_cost', 'fuel_refill_cost', 'border_crossings', 'trip_profit',
                        ] if c in t_trips.columns]
                        st.dataframe(t_trips[show_cols].round(2), use_container_width=True, hide_index=True)

        st.divider()

        # ── FLEET PRODUCTIVITY COMPARISON ─────────────────────────────────────
        st.markdown("## ▦ Fleet Productivity Comparison")
        productivity_rows = []
        for _, truck in trucks_all.iterrows():
            tid   = int(truck['truck_id'])
            tt    = trips_df[trips_df['truck_id'] == tid]
            tf    = fuel_df[fuel_df['truck_id'] == tid]
            tm    = maint_df[maint_df['truck_id'] == tid]
            te    = expenses_df[expenses_df['truck_id'] == tid] if not expenses_df.empty else pd.DataFrame()
            c2    = _truck_costs(tt, tf, tm, te)
            t_rev = float(tt['revenue'].sum())
            t_net = t_rev - c2['total']
            t_fl  = float(tt['fuel_consumed'].sum())
            t_eff = c2['km'] / max(1, t_fl) if t_fl > 0 else 0
            productivity_rows.append({
                "Truck":              truck['registration'],
                "Driver":             truck['driver'] or "—",
                "Status":             str(truck.get('truck_status') or 'ACTIVE'),
                "Trips":              len(tt),
                "Distance (km)":      round(c2['km'], 0),
                "Revenue (E)":        round(t_rev, 2),
                "Total Expenses (E)": round(c2['total'], 2),
                "Net Profit (E)":     round(t_net, 2),
                "Margin %":           round((t_net / t_rev * 100) if t_rev > 0 else 0, 1),
                "Fuel Used (L)":      round(t_fl, 0),
                "Efficiency (km/L)":  round(t_eff, 2) if t_eff > 0 else 0,
                "Cost/km (E)":        round(c2['total'] / max(1, c2['km']), 2),
                "Rev/km (E)":         round(t_rev / max(1, c2['km']), 2),
                "Odometer (km)":      round(float(truck['mileage']), 0),
            })

        if productivity_rows:
            prod_df = pd.DataFrame(productivity_rows)
            st.dataframe(prod_df, use_container_width=True, hide_index=True)

            if len(prod_df) > 0 and prod_df['Revenue (E)'].sum() > 0:
                pc1, pc2 = st.columns(2)
                with pc1:
                    fig_rev = px.bar(
                        prod_df, x='Truck', y='Revenue (E)',
                        title='Revenue by Truck',
                        color='Revenue (E)', color_continuous_scale='Blues', text='Revenue (E)',
                    )
                    fig_rev.update_traces(texttemplate='E%{text:,.0f}', textposition='outside')
                    st.plotly_chart(fig_rev, use_container_width=True)
                with pc2:
                    fig_net = px.bar(
                        prod_df, x='Truck', y='Net Profit (E)',
                        title='Net Profit by Truck (actual costs)',
                        color='Net Profit (E)',
                        color_continuous_scale=['#dc2626', '#f59e0b', '#10b981'],
                        text='Net Profit (E)',
                    )
                    fig_net.update_traces(texttemplate='E%{text:,.0f}', textposition='outside')
                    st.plotly_chart(fig_net, use_container_width=True)

                pc3, pc4 = st.columns(2)
                with pc3:
                    if prod_df['Efficiency (km/L)'].sum() > 0:
                        fig_eff = px.bar(
                            prod_df, x='Truck', y='Efficiency (km/L)',
                            title='Fuel Efficiency by Truck (km/L)',
                            color='Efficiency (km/L)', color_continuous_scale='Greens', text='Efficiency (km/L)',
                        )
                        fig_eff.update_traces(texttemplate='%{text:.2f}', textposition='outside')
                        st.plotly_chart(fig_eff, use_container_width=True)
                with pc4:
                    fig_margin = px.bar(
                        prod_df, x='Truck', y='Margin %',
                        title='Profit Margin % by Truck (actual costs)',
                        color='Margin %',
                        color_continuous_scale=['#dc2626', '#f59e0b', '#10b981'],
                        text='Margin %',
                    )
                    fig_margin.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                    st.plotly_chart(fig_margin, use_container_width=True)

            if len(prod_df) > 1:
                st.markdown("#### ★ Performance Rankings")
                ranked = prod_df.sort_values('Net Profit (E)', ascending=False).reset_index(drop=True)
                ranked.index = ranked.index + 1
                for idx, row in ranked.iterrows():
                    medal = "1." if idx == 1 else "2." if idx == 2 else "3." if idx == 3 else f"#{idx}"
                    profit_color = "#10b981" if row['Net Profit (E)'] >= 0 else "#dc2626"
                    st.markdown(f"""
                    <div style="background:rgba(255,255,255,0.04);border-radius:10px;padding:10px 16px;
                                margin:6px 0;border:1px solid rgba(255,255,255,0.08);
                                display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:18px;">{medal}</span>
                        <span style="font-weight:bold;min-width:120px;">{row['Truck']}</span>
                        <span style="color:#93c5fd;">{row['Trips']} trips · {row['Distance (km)']:,.0f} km</span>
                        <span style="color:#fbbf24;">Revenue: E {row['Revenue (E)']:,.2f}</span>
                        <span style="color:{profit_color};font-weight:bold;">
                            Profit: E {row['Net Profit (E)']:,.2f} ({row['Margin %']:.1f}%)
                        </span>
                    </div>""", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Statement of Account error: {e}")
        import traceback; st.code(traceback.format_exc())
    finally:
        conn.close()
