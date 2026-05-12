# ui/command_bar.py — Natural language command bar for KSM Smart Freight
# ─────────────────────────────────────────────────────────────────────────────
# Drop this above every page: it gives the operator a plain-English interface
# that can query the database, pre-fill forms, run feasibility checks, and
# filter trip data — all without navigating through tabs.
#
# KEY IMPROVEMENTS over v3:
#   • trip_log  → auto-navigates to Unified Logistics AND injects prefill values
#                 directly into session_state so the form fields are pre-filled
#                 on arrival (no manual re-entry required).
#   • fuel_log  → auto-navigates to Fuel Tracking AND injects truck + odometer
#                 + litres prefill values into session_state.
#   • query     → results rendered inline (table + text); no navigation needed.
#   • Branding  → Gemini 2.5 Flash command bar (was Claude).
#
# Dependencies: google-generativeai (pip install -U google-generativeai)
# The Gemini API key is read from st.session_state["gemini_api_key"]
# or from the GOOGLE_API_KEY environment variable.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

try:
    from google import genai as _genai_new
    _USE_NEW_SDK = True
except ImportError:
    import google.generativeai as genai  # type: ignore
    _USE_NEW_SDK = False
import pandas as pd
import streamlit as st

from core.database import get_connection

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
from core.constants import (
    TRIP_PREFILL_KEY   as _LOGISTICS_PREFILL_KEY,
    FUEL_PREFILL_KEY   as _FUEL_PREFILL_KEY,
    CMD_HISTORY_KEY    as _HISTORY_KEY,
    CMD_KEY_PREFIX     as _KEY_PREFIX,
    NAV_OVERRIDE_KEY,
    SIDEBAR_MENU_KEY,
    NAV_INTENT_KEY,
    NAV_MENU           as _VALID_PAGES_LIST,
)
_VALID_PAGES = set(_VALID_PAGES_LIST)

# Session-state keys used to prefill Unified Logistics form fields
# These must match the widget keys used in ui/logistics.py

# Session-state keys used to prefill Fuel Tracking form fields


# ─────────────────────────────────────────────────────────────────────────────
# Schema + live-context builder
# ─────────────────────────────────────────────────────────────────────────────

def _get_live_context() -> str:
    """Query the database and return a compact JSON snapshot for the prompt."""
    try:
        conn = get_connection()

        trucks_df = pd.read_sql_query(
            "SELECT registration, driver, mileage, last_service_km, "
            "service_interval, truck_status, truck_age_years "
            "FROM Truck ORDER BY registration",
            conn,
        )

        recent_trips = pd.read_sql_query(
            """SELECT t.date, tr.registration, t.start_location, t.end_location,
                      t.distance, t.load, t.fuel_consumed, t.revenue, t.risk_score
               FROM Trip t
               JOIN Truck tr ON tr.truck_id = t.truck_id
               ORDER BY t.date DESC LIMIT 10""",
            conn,
        )

        fuel_summary = pd.read_sql_query(
            """SELECT tr.registration,
                      ROUND(SUM(f.total_cost),2)  AS total_fuel_spend_SZL,
                      ROUND(SUM(f.fuel_added),1)  AS total_litres,
                      COUNT(*)                     AS fill_ups
               FROM FuelConsumption f
               JOIN Truck tr ON tr.truck_id = f.truck_id
               GROUP BY tr.registration""",
            conn,
        )

        conn.close()

        ctx = {
            "fleet": trucks_df.to_dict(orient="records"),
            "recent_trips": recent_trips.to_dict(orient="records"),
            "fuel_summary_by_truck": fuel_summary.to_dict(orient="records"),
        }
        return json.dumps(ctx, default=str, indent=2)

    except Exception as exc:
        logger.warning("command_bar: could not fetch live context: %s", exc)
        return "{}"


_SYSTEM_PROMPT = """You are the operations intelligence assistant for KSM Smart Freight Solutions,
a small fleet operator running heavy goods vehicles in Eswatini (Swaziland) and cross-border
routes to South Africa, Mozambique, and Zimbabwe.

The operator speaks to you in plain English. You must respond in a structured JSON object — never
plain prose at the top level. Your JSON must always have these keys:

  "response"    — the answer in clear, concise plain English (markdown allowed, keep it tight)
  "intent"      — one of: "query", "trip_log", "fuel_log", "feasibility", "filter", "navigate", "general"
  "sql"         — a valid SQLite SELECT query if data needs to be fetched, else null
  "prefill"     — a dict of suggested form values if the user wants to log a trip or fuel, else null
  "navigate_to" — ALWAYS set this whenever the user wants to go to a page, log something, or open a module.
                  Must be one of: "Dashboard", "Truck Management", "Unified Logistics",
                  "Fuel Tracking", "Advanced Analytics", "Market Intel", "Statement of Account".
                  Rules:
                    • intent "trip_log"  → ALWAYS "Unified Logistics"
                    • intent "fuel_log"  → ALWAYS "Fuel Tracking"
                    • intent "navigate"  → whichever page the user asked to open
                    • intent "query" or "filter" → null (data shown inline)
                    • intent "feasibility" → null (shown inline)
                    • intent "general" → null
  "table_title" — a short title for the data table if sql is provided, else null

NAVIGATION INTENT RULES — use intent "navigate" whenever the user says things like:
  "open X", "go to X", "take me to X", "show me X page", "switch to X"
  where X matches one of the page names above (even partial matches like "logistics", "fuel", "trucks").

DATABASE SCHEMA (SQLite, file: fleet.db):

  Truck(truck_id PK, registration, name, model, driver, load_type,
        starting_mileage, mileage, last_service_km, service_interval,
        chassis_number, photo_path, engine_hours, last_maintenance_date,
        truck_age_years, fuel_tank_capacity, max_payload, created_date,
        fuel_efficiency_baseline, tare_weight_kg,
        service_warning_active, service_warning_date, truck_status,
        year_of_manufacture, rolling_fuel_efficiency)

  Trip(trip_id PK, truck_id FK, start_location, end_location, distance,
       load, date, fuel_consumed, actual_fuel_efficiency,
       predicted_fuel_efficiency, terrain_type, weather_condition,
       road_quality, border_crossings, trip_duration_hours, toll_cost,
       hard_braking_events, idle_time_minutes, driver_experience_years,
       delivery_on_time, profit_margin, risk_score, revenue,
       fuel_refill_cost, fuel_refill_litres, actual_fuel_cost)

  FuelConsumption(fuel_id PK, truck_id FK, date, trip_id FK,
                  fuel_added, odometer, cost_per_liter, total_cost,
                  fuel_type, station_location, notes, is_full_tank)

  MaintenanceLog(maint_id PK, truck_id FK, date, description, cost,
                 odometer, service_type, technician, notes)

  TripExpenses(expense_id PK, trip_id FK, truck_id FK, date,
               toll_fees, fuel_refill_cost, fuel_refill_litres,
               fuel_refill_location, other_expenses, other_description, notes)

KNOWN LOCATIONS: Mbabane, Manzini, Matsapha, Piggs Peak, Lomahasha,
                 Lavumisa, Johannesburg, Durban, Maputo, Nelspruit

CURRENCY: Eswatini Lilangeni (E / SZL). On cross-border trips, ZAR ≈ SZL.

RULES:
- Revenue and costs are in SZL unless the user says otherwise.
- "Profit" = revenue − fuel_cost − maintenance − tolls − border fees.
  Rough border fee: E200 per crossing.
- Service interval default: 15,000 km.
- For trip_log prefill, include these keys (used to autofill the form):
    truck_registration, date (ISO YYYY-MM-DD), start_location, end_location,
    distance_km, load_kg, fuel_consumed_L, revenue_SZL,
    toll_cost_SZL (optional), trip_duration_hours (optional)
- For fuel_log prefill, include these keys (used to autofill the form):
    truck_registration, date (ISO YYYY-MM-DD), odometer_km,
    fuel_added_L, cost_per_litre_SZL (optional), station_name (optional),
    notes (optional)
- Keep SQL simple; avoid JOINs unless necessary. Always use LIMIT 100 max.
- Never write INSERT/UPDATE/DELETE SQL.
- If the user asks for "yesterday" compute relative to today's date.
- When responding about financial figures always include the currency symbol E.

TODAY: {today}

LIVE FLEET SNAPSHOT:
{context}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Gemini API caller
# ─────────────────────────────────────────────────────────────────────────────

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "response":    {"type": "string"},
        "intent":      {"type": "string", "enum": ["query", "trip_log", "fuel_log", "feasibility", "filter", "navigate", "general"]},
        "sql":         {"type": "string",  "nullable": True},
        "prefill":     {"type": "object",  "nullable": True},
        "navigate_to": {"type": "string",  "nullable": True},
        "table_title": {"type": "string",  "nullable": True},
    },
    "required": ["response", "intent"],
}


def _call_gemini(user_message: str, api_key: str) -> dict[str, Any]:
    """Send the user message to Gemini and return the parsed JSON response.

    Uses the model selected in the sidebar (default: gemini-2.5-flash-lite).
    If a 429 quota error is hit, automatically retries once with the lighter
    flash-lite model and surfaces a warning to the user.
    """
    import time

    today   = datetime.now().strftime("%Y-%m-%d (%A)")
    context = _get_live_context()
    system_instruction = _SYSTEM_PROMPT.format(today=today, context=context)

    model_name = st.session_state.get("cmd_bar_model", "gemini-2.5-flash-lite")

    def _try(name: str):
        if _USE_NEW_SDK:
            client = _genai_new.Client(api_key=api_key)
            response = client.models.generate_content(
                model=name,
                contents=user_message,
                config=_genai_new.types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                    max_output_tokens=1500,
                    temperature=0.1,
                ),
            )
            return response
        else:
            genai.configure(api_key=api_key)
            m = genai.GenerativeModel(model_name=name, system_instruction=system_instruction)
            return m.generate_content(
                user_message,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                    max_output_tokens=1500,
                    temperature=0.1,
                ),
            )

    try:
        response = _try(model_name)
    except Exception as exc:
        err = str(exc)
        # 429 quota exceeded — wait briefly then retry with flash-lite
        if "429" in err and model_name != "gemini-2.5-flash-lite":
            st.toast("▶ Quota limit hit — retrying with Gemini 2.5 Flash-Lite…", icon="⚠️")
            time.sleep(5)
            response = _try("gemini-2.5-flash-lite")
        else:
            raise

    try:
        return json.loads(response.text)
    except Exception:
        return {
            "response": response.text,
            "intent": "general",
            "sql": None,
            "prefill": None,
            "navigate_to": None,
            "table_title": None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SQL executor (SELECT only, hard-limited to 100 rows)
# ─────────────────────────────────────────────────────────────────────────────

def _run_sql(sql: str) -> pd.DataFrame | None:
    """Execute a read-only SELECT and return a DataFrame, or None on error."""
    if not sql:
        return None
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return None
    try:
        conn = get_connection()
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return df
    except Exception as exc:
        logger.warning("command_bar SQL error: %s | query: %s", exc, sql)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Navigation + autofill injection
# ─────────────────────────────────────────────────────────────────────────────

_VALID_PAGES = {
    "Dashboard", "Truck Management", "Unified Logistics",
    "Fuel Tracking", "Advanced Analytics", "Market Intel",
    "Statement of Account",
}


def _inject_trip_prefill(prefill: dict) -> None:
    """
    Write prefill values into session_state keys that ui/logistics.py reads
    when it renders the trip log form.

    The logistics form uses:
      - "log_truck_sel"  → selectbox key (truck registration)
      - "_trip_pf"       → dict picked up inside the form to set default values

    Since Streamlit selectbox/number_input widgets cannot be programmatically
    set via session_state after they are created, we store the prefill dict
    under a dedicated key.  unified_logistics_module() must call
    _apply_trip_prefill() at the TOP of its form render to consume it.
    """
    if prefill:
        # Store truck selection so the selectbox outside the form pre-selects it
        if "truck_registration" in prefill:
            st.session_state["log_truck_sel"] = prefill["truck_registration"]
        # Store the full prefill for the form fields
        st.session_state[_LOGISTICS_PREFILL_KEY] = prefill


def _inject_fuel_prefill(prefill: dict) -> None:
    """
    Write prefill values into session_state so ui/fuel.py can pre-fill the
    fuel log form.  fuel_tracking_module() must call _apply_fuel_prefill()
    at the top of its form render.
    """
    if prefill:
        if "truck_registration" in prefill:
            st.session_state["fuel_truck"] = prefill["truck_registration"]
        st.session_state[_FUEL_PREFILL_KEY] = prefill


def _navigate(page: str, prefill: dict | None, intent: str) -> None:
    """Inject prefill and trigger navigation to the given page in one rerun.

    Sets ``st.session_state["_sidebar_override"]`` (the key the main router
    reads) AND stores it under ``"current_page"`` as a secondary fallback so
    the router has two chances to pick it up regardless of which key name the
    host app uses.
    """
    if page not in _VALID_PAGES:
        logger.warning("command_bar: unknown navigate_to value %r — skipping", page)
        return
    if intent == "trip_log" and prefill:
        _inject_trip_prefill(prefill)
    elif intent == "fuel_log" and prefill:
        _inject_fuel_prefill(prefill)

    # Write only to NAV_OVERRIDE_KEY — NOT to SIDEBAR_MENU_KEY.
    # SIDEBAR_MENU_KEY is the key of a live st.selectbox widget; writing to it
    # after the widget is rendered raises StreamlitAPIException.
    # The yizo.py router reads NAV_OVERRIDE_KEY at the very top of each run
    # (before any widget is instantiated) and safely propagates it into the
    # selectbox default.
    st.session_state[NAV_OVERRIDE_KEY] = page
    st.session_state[NAV_INTENT_KEY] = intent
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers — call these from ui/logistics.py and ui/fuel.py
# ─────────────────────────────────────────────────────────────────────────────

def get_trip_prefill() -> dict | None:
    """
    Called by unified_logistics_module() to retrieve any AI-generated prefill
    values.  Uses .get() (NOT .pop()) so the data survives multiple reruns
    caused by widget interactions inside the form.

    Call clear_trip_prefill() explicitly AFTER the form is submitted so the
    values don't re-appear on the next fresh navigation.

    Usage in logistics.py (add near the top of the trip log tab):

        from ui.command_bar import get_trip_prefill, clear_trip_prefill
        pf = get_trip_prefill() or {}
        # use pf.get("start_location"), pf.get("distance_km") etc.
        # as the value= argument for each form widget.
        # After successful form submission:  clear_trip_prefill()
    """
    return st.session_state.get(_LOGISTICS_PREFILL_KEY)


def clear_trip_prefill() -> None:
    """Call this after the trip log form is successfully submitted."""
    st.session_state.pop(_LOGISTICS_PREFILL_KEY, None)
    st.session_state.pop("log_truck_sel_pf", None)


def get_fuel_prefill() -> dict | None:
    """
    Called by fuel_tracking_module() to retrieve any AI-generated prefill
    values.  Uses .get() (NOT .pop()) so the data survives multiple reruns.

    Call clear_fuel_prefill() explicitly AFTER the form is submitted.

    Usage in fuel.py (add near the top of the fill-up form):

        from ui.command_bar import get_fuel_prefill, clear_fuel_prefill
        pf = get_fuel_prefill() or {}
        # use pf.get("fuel_added_L"), pf.get("odometer_km") etc.
        # After successful form submission:  clear_fuel_prefill()
    """
    return st.session_state.get(_FUEL_PREFILL_KEY)


def clear_fuel_prefill() -> None:
    """Call this after the fuel log form is successfully submitted."""
    st.session_state.pop(_FUEL_PREFILL_KEY, None)
    st.session_state.pop("fuel_truck_pf", None)


# ─────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _render_prefill_summary(prefill: dict, intent: str) -> None:
    """Show a compact confirmation card of what values were injected."""
    color   = "rgba(37,99,235,0.12)"  if intent == "trip_log" else "rgba(5,150,105,0.12)"
    border  = "rgba(96,165,250,0.35)" if intent == "trip_log" else "rgba(52,211,153,0.35)"
    icon    = "📋" if intent == "trip_log" else "◉"
    title   = "Trip values injected — form is pre-filled" if intent == "trip_log" \
              else "Fuel values injected — form is pre-filled"

    st.markdown(
        f"""<div style='background:{color};border:1px solid {border};
           border-radius:10px;padding:14px 18px;margin-top:8px;'>
           <div style='color:#93c5fd;font-size:12px;font-weight:600;
                text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;'>
           {icon} {title}</div>""",
        unsafe_allow_html=True,
    )
    labels_trip = {
        "truck_registration": "Truck",
        "date": "Date",
        "start_location": "From",
        "end_location": "To",
        "distance_km": "Distance (km)",
        "load_kg": "Load (kg)",
        "fuel_consumed_L": "Fuel consumed (L)",
        "revenue_SZL": "Revenue (E)",
        "toll_cost_SZL": "Toll (E)",
        "trip_duration_hours": "Duration (hrs)",
    }
    labels_fuel = {
        "truck_registration": "Truck",
        "date": "Date",
        "odometer_km": "Odometer (km)",
        "fuel_added_L": "Litres added",
        "cost_per_litre_SZL": "Price/litre (E)",
        "station_name": "Station",
        "notes": "Notes",
    }
    labels = labels_trip if intent == "trip_log" else labels_fuel
    pairs = []
    for key, label in labels.items():
        if key in prefill:
            pairs.append(f"**{label}:** {prefill[key]}")
    for key, val in prefill.items():
        if key not in labels:
            pairs.append(f"**{key}:** {val}")

    cols = st.columns(2)
    for i, pair in enumerate(pairs):
        cols[i % 2].markdown(pair)

    st.markdown("</div>", unsafe_allow_html=True)


def _intent_icon(intent: str) -> str:
    return {
        "query":       "🔍",
        "trip_log":    "📋",
        "fuel_log":    "◉",
        "feasibility": "▦",
        "filter":      "🔍",
        "navigate":    "📍",
        "general":     "📝",
    }.get(intent, "📝")


# ─────────────────────────────────────────────────────────────────────────────
# Example prompts shown in the UI
# ─────────────────────────────────────────────────────────────────────────────

_EXAMPLES = [
    "Which truck is costing me the most per km this month?",
    "Log yesterday's trip: Manzini → Durban, 418 km, 14 200 kg, fuel E2 340, revenue E8 500",
    "Log a fuel fill-up: SDS 452 GP, 180 L at E18.40/L, odometer 87 500",
    "Is it worth taking a job to Maputo tomorrow? Client paying E12 000 for 18 tonnes",
    "Show all trips where actual fuel was more than 15% above predicted",
    "How much profit did I make last week?",
]


# ─────────────────────────────────────────────────────────────────────────────
# Main render function — call this once in yizo.py after render_header()
# ─────────────────────────────────────────────────────────────────────────────

def render_command_bar() -> None:
    """Render the conversational command bar. Call once per page, after render_header()."""

    # ── Sidebar: API key + model selector ────────────────────────────────────
    with st.sidebar:
        st.markdown("### ◇ AI Command Bar")
        api_key = st.text_input(
            "Gemini API Key",
            value=st.session_state.get("gemini_api_key", os.getenv("GOOGLE_API_KEY", "")),
            type="password",
            key=f"{_KEY_PREFIX}_api_key_input",
            help="Get a free key at aistudio.google.com — enables the natural language command bar.",
        )
        if api_key:
            st.session_state["gemini_api_key"] = api_key
            st.sidebar.success("✅ Command bar active")
        else:
            st.sidebar.info("ℹ️ Add Gemini key to enable command bar")

        _MODEL_OPTIONS = {
            "gemini-2.5-flash-lite": "2.5 Flash-Lite  (free · 30 rpm)",
            "gemini-2.5-flash":      "2.5 Flash       (free · 5 rpm)",
        }
        selected_model = st.selectbox(
            "Model",
            options=list(_MODEL_OPTIONS.keys()),
            format_func=lambda k: _MODEL_OPTIONS[k],
            index=0,
            key=f"{_KEY_PREFIX}_model_select",
            help="Flash-Lite is recommended for free-tier keys (30 req/min). "
                 "Flash gives higher quality but hits quota fast on free tier.",
        )
        st.session_state["cmd_bar_model"] = selected_model

    api_key = st.session_state.get("gemini_api_key", "")

    # ── Header bar ───────────────────────────────────────────────────────────
    st.markdown(
        """<div style='background:linear-gradient(135deg,rgba(30,58,138,0.7),rgba(5,150,105,0.5));
            border:1px solid rgba(96,165,250,0.25);border-radius:14px;
            padding:14px 20px 10px 20px;margin-bottom:4px;'>
            <div style='display:flex;align-items:center;gap:10px;'>
              <span style='font-size:22px;'>◇</span>
              <div>
                <div style='color:#e0f2fe;font-weight:700;font-size:15px;'>
                  Operations Command Bar
                  <span style='font-size:11px;font-weight:400;color:#94a3b8;margin-left:8px;'>
                    powered by Gemini 2.5
                  </span>
                </div>
                <div style='color:#94a3b8;font-size:12px;'>
                  Ask anything — log trips, record fuel, query data, check feasibility
                </div>
              </div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Input row (wrapped in a form so Enter key submits) ───────────────────
    # FIX 3: st.form captures Enter-key press.  Without it, only the ↩ button
    # worked; typing and pressing Enter did nothing.
    with st.form(key=f"{_KEY_PREFIX}_form", clear_on_submit=True):
        col_input, col_btn = st.columns([11, 1])
        with col_input:
            user_input = st.text_input(
                "command_bar_input",
                placeholder='e.g. "Log Manzini → Durban 418 km, 14 t, E8 500" or "Which truck costs most per km?"',
                label_visibility="collapsed",
                key=f"{_KEY_PREFIX}_input",
                disabled=not api_key,
            )
        with col_btn:
            submit = st.form_submit_button(
                "↩",
                help="Send  (or press Enter)",
                use_container_width=True,
                disabled=not api_key,
            )

    # ── Example chips ────────────────────────────────────────────────────────
    if not api_key:
        st.caption("⬆️ Add your Gemini API key in the sidebar to activate the command bar.")
    else:
        with st.expander("◉ Example queries", expanded=False):
            for ex in _EXAMPLES:
                if st.button(ex, key=f"{_KEY_PREFIX}_ex_{hash(ex)}", use_container_width=True):
                    st.session_state[f"{_KEY_PREFIX}_pending"] = ex
                    st.rerun()

    # ── Handle pending (from example chips) ──────────────────────────────────
    pending = st.session_state.pop(f"{_KEY_PREFIX}_pending", None)
    query   = pending or (user_input.strip() if submit and user_input else None)

    # FIX 3b: Prevent the same query from being re-processed on unrelated reruns
    # (e.g. a sidebar widget change).  Only process when we have a *new* query.
    if query and query == st.session_state.get(f"{_KEY_PREFIX}_last_query"):
        query = None   # already processed; skip
    if query:
        st.session_state[f"{_KEY_PREFIX}_last_query"] = query

    # ── Process query ────────────────────────────────────────────────────────
    if query and api_key:
        if _HISTORY_KEY not in st.session_state:
            st.session_state[_HISTORY_KEY] = []

        with st.spinner("Thinking…"):
            try:
                result = _call_gemini(query, api_key)
            except Exception as exc:
                st.error(f"Gemini API error: {exc}")
                result = None

        if result:
            entry = {"query": query, "result": result}
            st.session_state[_HISTORY_KEY].insert(0, entry)   # newest first

            # ── AUTO-NAVIGATE ─────────────────────────────────────────────────
            # Fire navigation whenever:
            #   (a) intent maps directly to a destination (trip_log / fuel_log)
            #   (b) OR Gemini explicitly set navigate_to (covers "navigate" intent
            #       and any "open X / go to X" phrasing regardless of intent label)
            intent  = result.get("intent", "general")
            nav     = result.get("navigate_to")
            prefill = result.get("prefill")

            _INTENT_DEST = {
                "trip_log": "Unified Logistics",
                "fuel_log": "Fuel Tracking",
            }
            dest = _INTENT_DEST.get(intent) or (nav if nav in _VALID_PAGES else None)
            if dest:
                _navigate(dest, prefill, intent)
                # st.rerun() is called inside _navigate; nothing below runs

    # ── Render history ───────────────────────────────────────────────────────
    history: list[dict] = st.session_state.get(_HISTORY_KEY, [])
    if history:
        st.markdown("---")
        for entry in history[:5]:
            q = entry["query"]
            r = entry["result"]

            icon   = _intent_icon(r.get("intent", "general"))
            intent = r.get("intent", "general")

            # User bubble
            st.markdown(
                f"<div style='background:rgba(37,99,235,0.18);border-radius:10px;"
                f"padding:8px 14px;margin-bottom:4px;color:#e2e8f0;font-size:14px;'>"
                f"<b>You:</b> {q}</div>",
                unsafe_allow_html=True,
            )

            # Assistant bubble
            response_md = r.get("response", "")
            st.markdown(
                f"<div style='background:rgba(5,150,105,0.12);border:1px solid "
                f"rgba(52,211,153,0.2);border-radius:10px;padding:10px 16px;"
                f"margin-bottom:8px;'>",
                unsafe_allow_html=True,
            )
            st.markdown(f"{icon} {response_md}")

            # ── INLINE query / filter results ─────────────────────────────────
            if intent in ("query", "filter", "feasibility"):
                sql = r.get("sql")
                if sql:
                    df = _run_sql(sql)
                    if df is not None and not df.empty:
                        title = r.get("table_title") or "Results"
                        st.caption(f"▦ {title} ({len(df)} row{'s' if len(df) != 1 else ''})")
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    elif df is not None:
                        st.caption("No records found for that query.")

            # ── trip_log / fuel_log: show injected-prefill summary card ───────
            elif intent in ("trip_log", "fuel_log"):
                prefill = r.get("prefill")
                if prefill and isinstance(prefill, dict):
                    _render_prefill_summary(prefill, intent)
                    nav = r.get("navigate_to", "")
                    dest = "Unified Logistics" if intent == "trip_log" else "Fuel Tracking"
                    st.info(
                        f"✅ Form pre-filled and page switched to **{dest}**. "
                        "Review the values and press **Log Trip** / **Save Fill-Up**.",
                        icon="→",
                    )

            st.markdown("</div>", unsafe_allow_html=True)

        # Clear history button
        if st.button("✕️ Clear command history", key=f"{_KEY_PREFIX}_clear"):
            st.session_state[_HISTORY_KEY] = []
            st.rerun()

    st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# ── HOW TO WIRE UP AUTOFILL IN ui/logistics.py ────────────────────────────────
#
# In unified_logistics_module(), BEFORE st.form("trip_log_form"), add:
#
#   from ui.command_bar import get_trip_prefill, clear_trip_prefill
#   _pf = get_trip_prefill() or {}          # .get() — survives widget reruns
#
# Then use _pf.get("start_location", default) as the `index=` for selectboxes
# and `value=` for number_input / text_input widgets.  Example:
#
#   LOCS = list(LOCATION_COORDS.keys())
#   _pf_origin = _pf.get("start_location", LOCS[0])
#   origin = st.selectbox("Origin", LOCS,
#                         index=LOCS.index(_pf_origin) if _pf_origin in LOCS else 0)
#
#   distance = st.number_input("Distance (km)", value=float(_pf.get("distance_km", auto_distance)))
#   load_kg  = st.number_input("Cargo Load (kg)", value=float(_pf.get("load_kg", 5000)))
#   revenue  = st.number_input("Revenue (E)", value=float(_pf.get("revenue_SZL", 0)))
#
# IMPORTANT: After the form submits successfully, call:
#   clear_trip_prefill()
# This prevents the same prefill from reappearing next time the page loads.
#
# ── HOW TO WIRE UP AUTOFILL IN ui/fuel.py ────────────────────────────────────
#
# In fuel_tracking_module(), BEFORE st.form("fuel_log_form"), add:
#
#   from ui.command_bar import get_fuel_prefill, clear_fuel_prefill
#   _pf = get_fuel_prefill() or {}          # .get() — survives widget reruns
#
# Then use _pf values as widget defaults:
#
#   odometer   = st.number_input("Odometer (km)", value=float(_pf.get("odometer_km", cur_mileage)))
#   fuel_added = st.number_input("Litres Added",  value=float(_pf.get("fuel_added_L", 150)))
#   cost_per_L = st.number_input("Price/L (E)",   value=float(_pf.get("cost_per_litre_SZL", FUEL_PRICE_DEFAULT)))
#   station    = st.text_input("Station",         value=_pf.get("station_name", ""))
#
# IMPORTANT: After the form submits successfully, call:
#   clear_fuel_prefill()
#
# ── HOW TO WIRE UP NAVIGATION IN yizo.py (or your main router) ───────────────
#
# The command bar writes to TWO session-state keys on navigation so your router
# only needs to check ONE of them (whichever you already use):
#
#   st.session_state["_sidebar_override"]  ← primary   (original key)
#   st.session_state["current_page"]       ← secondary fallback
#
# In your router / page-selector, add something like:
#
#   override = (
#       st.session_state.pop("_sidebar_override", None)
#       or st.session_state.pop("current_page", None)
#   )
#   if override:
#       selected_page = override
#
# ─────────────────────────────────────────────────────────────────────────────
