"""
KSM Smart Freight — Supabase Database Layer
Replaces local SQLite with cloud PostgreSQL via Supabase REST API.
"""
import os
import json
import hashlib
from datetime import datetime
import streamlit as st

try:
    from supabase import create_client, Client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False

# =============================================================================
# SUPABASE CONFIG — loaded from Streamlit secrets
# =============================================================================
def _get_client():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        if not _SUPABASE_AVAILABLE:
            return None
        return create_client(url, key)
    except Exception:
        return None


def db_ok() -> bool:
    try:
        client = _get_client()
        if not client:
            return False
        client.table("Truck").select("truck_id").limit(1).execute()
        return True
    except Exception:
        return False


# =============================================================================
# SCHEMA SETUP — creates tables if they don't exist via SQL
# =============================================================================
def ensure_schema():
    """Tables must be created in Supabase SQL Editor. This just verifies connection."""
    return db_ok()


# =============================================================================
# AUTH HELPERS
# =============================================================================
def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_driver_login(driver_id: str, pin: str):
    """
    Returns (True, full_name, truck_id) or (False, error_message, None)
    Checks Users table first (DB auth), falls back to hardcoded DRIVER_PINS.
    """
    try:
        client = _get_client()
        if client:
            row = client.table("Users").select(
                "password_hash,full_name,truck_id,is_active"
            ).eq("username", driver_id).eq("role", "driver").execute()
            if row.data:
                u = row.data[0]
                if not u.get("is_active", 1):
                    return False, "Account is inactive. Contact your manager.", None
                if u["password_hash"] == _hash_pw(pin):
                    return True, (u.get("full_name") or driver_id), u.get("truck_id")
                return False, "Incorrect PIN.", None
    except Exception:
        pass
    return False, "Driver ID not found. Contact your manager.", None


def log_access(username: str, role: str, truck_id=None):
    try:
        client = _get_client()
        if not client:
            return
        client.table("AccessLog").insert({
            "username": username,
            "role": role,
            "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "truck_id": truck_id,
        }).execute()
        client.table("Users").update({
            "last_login": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }).eq("username", username).execute()
    except Exception:
        pass


# =============================================================================
# TRUCK / DRIVER QUERIES
# =============================================================================
def get_driver_by_id(driver_id: str):
    """Returns tuple: (truck_id, registration, driver, mileage, fuel_tank_capacity,
    driver_id, driver_license, driver_phone, driver_id_number,
    driver_experience_years, driver_routes, driver_certifications, truck_status, model)"""
    try:
        client = _get_client()
        if not client:
            return None

        # First get truck_id from Users table
        user_row = client.table("Users").select("truck_id").eq(
            "username", driver_id
        ).execute()
        if not user_row.data or not user_row.data[0].get("truck_id"):
            return None

        tid = user_row.data[0]["truck_id"]
        row = client.table("Truck").select(
            "truck_id,registration,driver,mileage,fuel_tank_capacity,"
            "driver_id,driver_license,driver_phone,driver_id_number,"
            "driver_experience_years,driver_routes,driver_certifications,"
            "truck_status,model"
        ).eq("truck_id", tid).execute()

        if not row.data:
            return None
        r = row.data[0]
        return (
            r.get("truck_id"), r.get("registration"), r.get("driver"),
            r.get("mileage", 0), r.get("fuel_tank_capacity", 300),
            r.get("driver_id"), r.get("driver_license"), r.get("driver_phone"),
            r.get("driver_id_number"), r.get("driver_experience_years", 0),
            r.get("driver_routes"), r.get("driver_certifications"),
            r.get("truck_status", "ACTIVE"), r.get("model"),
        )
    except Exception:
        return None


def get_last_fuel(truck_id):
    try:
        client = _get_client()
        if not client:
            return None
        row = client.table("FuelConsumption").select(
            "fuel_added,odometer,date,cost_per_liter"
        ).eq("truck_id", truck_id).order("odometer", desc=True).limit(1).execute()
        if row.data:
            r = row.data[0]
            return (r.get("fuel_added"), r.get("odometer"), r.get("date"), r.get("cost_per_liter"))
        return None
    except Exception:
        return None


def get_avg_eff(truck_id, window=10):
    try:
        client = _get_client()
        if not client:
            return None
        rows = client.table("Trip").select(
            "actual_fuel_efficiency"
        ).eq("truck_id", truck_id).gt(
            "actual_fuel_efficiency", 0
        ).order("date", desc=True).limit(window).execute()
        vals = [r["actual_fuel_efficiency"] for r in rows.data if r.get("actual_fuel_efficiency")]
        return round(sum(vals) / len(vals), 2) if vals else None
    except Exception:
        return None


def get_driver_jobs(truck_id, limit=25):
    try:
        client = _get_client()
        if not client:
            return []
        rows = client.table("Trip").select(
            "trip_id,date,start_location,end_location,distance,load,"
            "fuel_consumed,actual_fuel_efficiency,trip_duration_hours,"
            "border_crossings,delivery_on_time,terrain_type,weather_condition"
        ).eq("truck_id", truck_id).order("date", desc=True).limit(limit).execute()
        return [
            (r.get("trip_id"), r.get("date"), r.get("start_location"),
             r.get("end_location"), r.get("distance"), r.get("load"),
             r.get("fuel_consumed"), r.get("actual_fuel_efficiency"),
             r.get("trip_duration_hours"), r.get("border_crossings"),
             r.get("delivery_on_time"), r.get("terrain_type"), r.get("weather_condition"))
            for r in rows.data
        ]
    except Exception:
        return []


def get_driver_docs(truck_id, driver_id, limit=30):
    try:
        client = _get_client()
        if not client:
            return []
        rows = client.table("DriverDocuments").select(
            "doc_id,upload_date,doc_type,filename,file_size,extracted,linked_trip,notes"
        ).eq("truck_id", truck_id).order("upload_date", desc=True).limit(limit).execute()
        return [
            (r.get("doc_id"), r.get("upload_date"), r.get("doc_type"),
             r.get("filename"), r.get("file_size"), r.get("extracted"),
             r.get("linked_trip"), r.get("notes"))
            for r in rows.data
        ]
    except Exception:
        return []


# =============================================================================
# SAVE OPERATIONS
# =============================================================================
def save_trip(d: dict) -> bool:
    try:
        client = _get_client()
        if not client:
            return False
        dist = d["distance"]
        fuel = d["fuel_consumed"]
        eff = dist / fuel if (dist > 0 and fuel > 0) else 0
        client.table("Trip").insert({
            "truck_id": d["truck_id"],
            "start_location": d["origin"],
            "end_location": d["destination"],
            "distance": dist,
            "load": d.get("load_kg", 0),
            "date": d["date"],
            "fuel_consumed": fuel,
            "actual_fuel_efficiency": eff,
            "trip_duration_hours": d.get("duration_h", 0),
            "border_crossings": d.get("border_crossings", 0),
            "terrain_type": d.get("terrain", "Rolling"),
            "weather_condition": "Clear",
            "road_quality": 0.75,
            "predicted_fuel_efficiency": eff,
            "risk_score": 0.15,
            "delivery_on_time": True if d.get("on_time", True) else False,
            "revenue": 0,
            "profit_margin": 0,
            "driver_experience_years": d.get("driver_exp", 5),
            "hard_braking_events": 0,
            "idle_time_minutes": 0,
        }).execute()
        odo = d.get("odometer", 0)
        if odo > 0:
            client.table("Truck").update({"mileage": odo}).eq("truck_id", d["truck_id"]).execute()
        return True
    except Exception as e:
        st.error(f"Save trip error: {e}")
        return False


def save_fuel(d: dict) -> bool:
    try:
        client = _get_client()
        if not client:
            return False
        client.table("FuelConsumption").insert({
            "truck_id": d["truck_id"],
            "date": d["date"],
            "fuel_added": d["fuel_added"],
            "odometer": d["odometer"],
            "cost_per_liter": d["cost_per_liter"],
            "total_cost": round(d["fuel_added"] * d["cost_per_liter"], 2),
            "fuel_type": "Diesel",
            "station_location": d.get("station", ""),
            "notes": d.get("notes", ""),
        }).execute()
        if d.get("odometer", 0) > 0:
            client.table("Truck").update(
                {"mileage": d["odometer"]}
            ).eq("truck_id", d["truck_id"]).execute()
        return True
    except Exception as e:
        st.error(f"Save fuel error: {e}")
        return False


def save_event(d: dict) -> bool:
    try:
        client = _get_client()
        if not client:
            return False
        client.table("MaintenanceLog").insert({
            "truck_id": d["truck_id"],
            "date": d["date"],
            "description": f"[DRIVER EVENT] {d['event_type']}",
            "cost": 0,
            "odometer": d.get("odometer", 0),
            "service_type": "DriverEvent",
            "notes": f"Severity: {d['severity']} | Location: {d.get('location','')} | {d.get('description','')}",
        }).execute()
        return True
    except Exception as e:
        st.error(f"Save event error: {e}")
        return False


def save_doc(d: dict) -> bool:
    try:
        client = _get_client()
        if not client:
            return False
        client.table("DriverDocuments").insert({
            "truck_id": d.get("truck_id"),
            "driver_id": d.get("driver_id"),
            "upload_date": d.get("upload_date", datetime.now().strftime("%Y-%m-%d")),
            "doc_type": d.get("doc_type", "Other"),
            "filename": d.get("filename", ""),
            "file_size": d.get("file_size", 0),
            "mime_type": d.get("mime_type", ""),
            "extracted": d.get("extracted", ""),
            "linked_trip": d.get("linked_trip"),
            "notes": d.get("notes", ""),
        }).execute()
        return True
    except Exception as e:
        st.error(f"Save doc error: {e}")
        return False


def update_driver_profile(driver_id: str, data: dict) -> bool:
    try:
        client = _get_client()
        if not client:
            return False
        client.table("Truck").update(data).eq("driver_id", driver_id).execute()
        return True
    except Exception:
        return False


# =============================================================================
# OFFLINE QUEUE
# =============================================================================
def enqueue(record: dict, kind: str = "trip"):
    key = f"offline_{kind}"
    if key not in st.session_state:
        st.session_state[key] = []
    st.session_state[key].append(record)


def qcount(kind: str) -> int:
    return len(st.session_state.get(f"offline_{kind}", []))


def sync_all() -> dict:
    results = {"trips": 0, "fuel": 0, "events": 0, "failed": 0}
    for rec in list(st.session_state.get("offline_trip", [])):
        if save_trip(rec):
            st.session_state["offline_trip"].remove(rec)
            results["trips"] += 1
        else:
            results["failed"] += 1
    for rec in list(st.session_state.get("offline_fuel", [])):
        if save_fuel(rec):
            st.session_state["offline_fuel"].remove(rec)
            results["fuel"] += 1
        else:
            results["failed"] += 1
    for rec in list(st.session_state.get("offline_event", [])):
        if save_event(rec):
            st.session_state["offline_event"].remove(rec)
            results["events"] += 1
        else:
            results["failed"] += 1
    return results
