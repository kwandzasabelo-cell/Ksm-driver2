"""
KSM Smart Freight Solutions — Supabase DB Layer
core/supabase_db.py
"""
import json
import streamlit as st
from datetime import datetime

try:
    from supabase import create_client, Client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False

SUPABASE_URL = "https://vximcvocwubrnnscwfqs.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ4aW1jdm9jd3Vicm5uc2N3ZnFzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2MTU4MzcsImV4cCI6MjA5MjE5MTgzN30.n9OszM3fwG7bBvKEuwUmL0Lw5pbnWjeIUl0r18hnNG0"

@st.cache_resource
def _get_sb():
    if not _SUPABASE_AVAILABLE:
        raise ImportError("Run: pip install supabase")
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except Exception:
        url = SUPABASE_URL
        key = SUPABASE_KEY
    return create_client(url, key)

def db_ok():
    try:
        _get_sb().table("truck").select("truck_id").limit(1).execute()
        return True
    except Exception:
        return False

def ensure_schema():
    pass

def get_driver_by_id(did):
    try:
        sb = _get_sb()
        r = sb.table("truck").select(
            "truck_id,registration,driver,mileage,fuel_tank_capacity,"
            "driver_id,driver_license,driver_phone,driver_id_number,"
            "driver_experience_years,driver_routes,driver_certifications,"
            "truck_status,model"
        ).eq("driver_id", did).limit(1).execute()
        if not r.data:
            return None
        d = r.data[0]
        return (
            d.get("truck_id"), d.get("registration"), d.get("driver"),
            d.get("mileage"), d.get("fuel_tank_capacity"),
            d.get("driver_id"), d.get("driver_license"), d.get("driver_phone"),
            d.get("driver_id_number"), d.get("driver_experience_years"),
            d.get("driver_routes"), d.get("driver_certifications"),
            d.get("truck_status"), d.get("model"),
        )
    except Exception as e:
        st.error(f"Supabase error: {e}")
        return None

def get_last_fuel(tid):
    try:
        sb = _get_sb()
        r = sb.table("fuel_consumption").select(
            "fuel_added,odometer,date,cost_per_liter"
        ).eq("truck_id", tid).order("odometer", desc=True).limit(1).execute()
        if not r.data:
            return None
        d = r.data[0]
        return (d.get("fuel_added"), d.get("odometer"),
                d.get("date"), d.get("cost_per_liter"))
    except Exception:
        return None

def get_avg_eff(tid, window=10):
    try:
        sb = _get_sb()
        r = sb.table("trip").select(
            "actual_fuel_efficiency"
        ).eq("truck_id", tid).order("date", desc=True).limit(window).execute()
        vals = [row["actual_fuel_efficiency"] for row in r.data
                if (row.get("actual_fuel_efficiency") or 0) > 0]
        return round(sum(vals)/len(vals), 2) if vals else None
    except Exception:
        return None

def get_driver_jobs(tid, limit=25):
    try:
        sb = _get_sb()
        r = sb.table("trip").select(
            "trip_id,date,start_location,end_location,distance,load,"
            "fuel_consumed,actual_fuel_efficiency,trip_duration_hours,"
            "border_crossings,delivery_on_time,terrain_type,weather_condition"
        ).eq("truck_id", tid).order("date", desc=True).limit(limit).execute()
        return [
            (d.get("trip_id"), d.get("date"),
             d.get("start_location"), d.get("end_location"),
             d.get("distance"), d.get("load"),
             d.get("fuel_consumed"), d.get("actual_fuel_efficiency"),
             d.get("trip_duration_hours"), d.get("border_crossings"),
             d.get("delivery_on_time"), d.get("terrain_type"),
             d.get("weather_condition"))
            for d in r.data
        ]
    except Exception:
        return []

def get_driver_docs(tid, did, limit=30):
    try:
        sb = _get_sb()
        r = sb.table("driver_documents").select(
            "doc_id,upload_date,doc_type,filename,file_size,"
            "extracted,linked_trip,notes"
        ).or_(f"truck_id.eq.{tid},driver_id.eq.{did}").order(
            "upload_date", desc=True).limit(limit).execute()
        return [
            (d.get("doc_id"), d.get("upload_date"), d.get("doc_type"),
             d.get("filename"), d.get("file_size"), d.get("extracted"),
             d.get("linked_trip"), d.get("notes"))
            for d in r.data
        ]
    except Exception:
        return []

def save_trip(d):
    try:
        sb = _get_sb()
        dist = d["distance"]; fuel = d["fuel_consumed"]
        eff = dist/fuel if (dist > 0 and fuel > 0) else 0
        sb.table("trip").insert({
            "truck_id": d["truck_id"],
            "start_location": d["origin"],
            "end_location": d["destination"],
            "distance": dist, "load": d.get("load_kg", 0),
            "date": d["date"], "fuel_consumed": fuel,
            "actual_fuel_efficiency": eff,
            "trip_duration_hours": d.get("duration_h", 0),
            "border_crossings": d.get("border_crossings", 0),
            "terrain_type": d.get("terrain", "Rolling"),
            "weather_condition": "Clear", "road_quality": 0.75,
            "predicted_fuel_efficiency": eff, "risk_score": 0.15,
            "delivery_on_time": 1 if d.get("on_time", True) else 0,
            "revenue": 0, "profit_margin": 0,
            "driver_experience_years": d.get("driver_exp", 5),
            "hard_braking_events": 0, "idle_time_minutes": 0,
        }).execute()
        odo = d.get("odometer", 0)
        if odo > 0:
            sb.table("truck").update({"mileage": odo}).eq("truck_id", d["truck_id"]).execute()
        return True
    except Exception as e:
        st.error(f"DB error: {e}"); return False

def save_fuel(d):
    try:
        sb = _get_sb()
        sb.table("fuel_consumption").insert({
            "truck_id": d["truck_id"], "date": d["date"],
            "fuel_added": d["fuel_added"], "odometer": d["odometer"],
            "cost_per_liter": d["cost_per_liter"],
            "total_cost": round(d["fuel_added"]*d["cost_per_liter"], 2),
            "fuel_type": d.get("fuel_type", "Diesel 50PPM"),
            "station_location": d.get("station", ""),
            "notes": d.get("notes", ""),
            "is_full_tank": 1 if d.get("full_tank", True) else 0,
        }).execute()
        if d["odometer"] > 0:
            sb.table("truck").update(
                {"mileage": d["odometer"]}
            ).eq("truck_id", d["truck_id"]).execute()
        return True
    except Exception as e:
        st.error(f"DB error: {e}"); return False

def save_event(d):
    try:
        sb = _get_sb()
        sb.table("maintenance_log").insert({
            "truck_id": d["truck_id"], "date": d["date"],
            "description": f"[DRIVER EVENT] {d['event_type']}",
            "cost": 0, "odometer": d.get("odometer", 0),
            "service_type": "DriverEvent",
            "notes": f"Severity: {d['severity']} | Location: {d['location']} | {d['description']}",
        }).execute()
        return True
    except Exception as e:
        st.error(f"DB error: {e}"); return False

def save_doc(tid, did, dtype, fname, fbytes, mime, extracted, notes="", linked_trip=None):
    try:
        sb = _get_sb()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"{did}/{ts}_{fname}"
        sb.storage.from_("driver-docs").upload(
            file_path, fbytes, {"content-type": mime, "x-upsert": "true"})
        r = sb.table("driver_documents").insert({
            "truck_id": tid, "driver_id": did,
            "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "doc_type": dtype, "filename": fname, "file_path": file_path,
            "file_size": len(fbytes) if fbytes else 0, "mime_type": mime,
            "extracted": json.dumps(extracted, ensure_ascii=False) if extracted else "{}",
            "linked_trip": linked_trip, "notes": notes,
        }).execute()
        return r.data[0]["doc_id"] if r.data else None
    except Exception as e:
        st.error(f"Save error: {e}"); return None

def update_driver_profile(tid, phone, license_no, id_number, certs, routes):
    try:
        sb = _get_sb()
        sb.table("truck").update({
            "driver_phone": phone, "driver_license": license_no,
            "driver_id_number": id_number, "driver_certifications": certs,
            "driver_routes": routes,
        }).eq("truck_id", tid).execute()
        return True
    except Exception as e:
        st.error(f"Error: {e}"); return False

def enqueue(rec, kind="trip"):
    st.session_state.setdefault(f"offline_{kind}", []).append(rec)

def qcount(kind):
    return len(st.session_state.get(f"offline_{kind}", []))

def sync_all():
    r = {"trips": 0, "fuel": 0, "events": 0, "failed": 0}
    for lst, fn, key in [
        (st.session_state.get("offline_trip", []), save_trip, "trips"),
        (st.session_state.get("offline_fuel", []), save_fuel, "fuel"),
        (st.session_state.get("offline_event", []), save_event, "events"),
    ]:
        for rec in list(lst):
            if fn(rec): lst.remove(rec); r[key] += 1
            else: r["failed"] += 1
    return r
