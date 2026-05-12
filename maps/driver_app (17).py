"""
KSM Smart Freight Solutions — Driver Terminal v6.1
Redesigned for speed — drivers log a trip in under 60 seconds.
• Trip log: 5 fields only (no revenue, no behaviour tracking)
• Document scanner: camera/upload → AI reads → auto-fills forms
• My Jobs: all trips for this driver (no revenue shown)
• Fuel receipts: scan → auto-fill → one tap save
"""
import streamlit as st
import sqlite3
import math
import os
import json
import base64
from datetime import datetime, date
try:
    from core.auth import verify_driver_login as _db_verify_driver, log_access as _log_access
    _AUTH_DB = True
except Exception:
    _AUTH_DB = False

st.set_page_config(page_title="KSM Driver Terminal", page_icon="▣",
                   layout="centered", initial_sidebar_state="collapsed")

DB_PATH             = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fleet.db")
FUEL_PRICE_DEFAULT  = 19.85
MAX_PAYLOAD_KG      = 25_000
FUEL_BASE_L_PER_100 = 28.0
SERVICE_INTERVAL_KM = 15_000
LOCATIONS = ["Mbabane","Manzini","Matsapha","Piggs Peak","Lomahasha","Lavumisa",
             "Johannesburg","Durban","Maputo","Nelspruit"]
LOCATION_COORDS = {
    "Mbabane":(-26.318,31.135),"Manzini":(-26.485,31.360),"Matsapha":(-26.516,31.300),
    "Piggs Peak":(-25.959,31.250),"Lomahasha":(-25.933,31.983),"Lavumisa":(-27.310,31.888),
    "Johannesburg":(-26.204,28.047),"Durban":(-29.858,31.021),
    "Maputo":(-25.969,32.573),"Nelspruit":(-25.466,30.970),
}
EVENT_TYPES = ["Near miss","Vehicle breakdown","Tyre blowout / puncture","Engine overheating",
               "Cargo damage","Border / weigh-bridge delay","Road closure / accident scene",
               "Speeding warning","Fatigue stop","Theft or security incident","Other"]
KNOWN_STATIONS = ["GALP Manzini","GALP Matsapha","GALP Mbabane","Total Matsapha","Total Mbabane",
                  "Total Manzini","BP Manzini","BP Matsapha","Engen Manzini","Puma Matsapha",
                  "Total Ermelo (ZA)","Total Nelspruit (ZA)","Total Maputo (MZ)","Petromoc Maputo (MZ)",
                  "Other / Enter manually"]
DRIVER_PINS = {
    "KSM-DRV-0001":"1234","KSM-DRV-0002":"5678","KSM-DRV-0003":"9012",
    "KSM-DRV-0004":"3456","KSM-DRV-0005":"7890","KSM-DRV-0006":"1234",
    "KSM-DRV-0007":"1234","FLEET-MGR":"ksm2025",
}
DOC_TYPES = ["Job Order","Fuel Receipt","Weighbridge Ticket","Delivery Note","Other Document"]

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
.stApp{background:linear-gradient(135deg,rgba(10,15,40,.97) 0%,rgba(15,30,70,.95) 35%,rgba(20,50,100,.93) 65%,rgba(10,20,55,.97) 100%),url('https://images.unsplash.com/photo-1519003722824-194d4455a60c?ixlib=rb-4.0.3&auto=format&fit=crop&w=2000&q=80');background-size:cover;background-attachment:fixed;font-family:'Sora',sans-serif;}
.main .block-container{background:rgba(255,255,255,.04);backdrop-filter:blur(12px);border-radius:16px;border:1px solid rgba(255,255,255,.08);padding:1.2rem 1.5rem;max-width:840px;}
.stApp,.stApp p,.stApp label,.stApp div,.stApp span,.stApp h1,.stApp h2,.stApp h3{color:#e2e8f0 !important;font-family:'Sora',sans-serif !important;}
h1{color:#60a5fa !important;}h2{color:#93c5fd !important;}h3{color:#bfdbfe !important;}
[data-testid="stMetric"]{background:linear-gradient(135deg,rgba(30,58,138,.7),rgba(37,99,235,.5));padding:14px;border-radius:12px;border:1px solid rgba(96,165,250,.35);}
[data-testid="stMetricLabel"]{color:#93c5fd !important;font-weight:700 !important;font-size:.72rem !important;}
[data-testid="stMetricValue"]{color:#fff !important;font-size:1.35rem !important;font-weight:800 !important;}
.stTextInput>div>div>input,.stNumberInput>div>div>input,.stTextArea>div>textarea,.stSelectbox>div>div{background:rgba(15,23,42,.75) !important;border:1px solid rgba(96,165,250,.4) !important;border-radius:8px !important;color:#e2e8f0 !important;font-family:'Sora',sans-serif !important;font-size:.88rem !important;}
.stSelectbox>div>div>div{color:#e2e8f0 !important;}
.stButton>button{background:linear-gradient(135deg,#1d4ed8,#2563eb) !important;color:white !important;border:1px solid rgba(96,165,250,.4) !important;border-radius:10px !important;font-weight:700 !important;font-family:'Sora',sans-serif !important;font-size:.85rem !important;box-shadow:0 4px 12px rgba(37,99,235,.4);width:100%;padding:.55rem 1rem !important;}
.stButton>button:hover{background:linear-gradient(135deg,#2563eb,#3b82f6) !important;transform:translateY(-1px);}
[data-testid="stFormSubmitButton"]>button{background:linear-gradient(135deg,#059669,#10b981) !important;box-shadow:0 4px 14px rgba(16,185,129,.45) !important;width:100%;font-size:.9rem !important;padding:.65rem 1rem !important;}
[data-testid="stFormSubmitButton"]>button:hover{background:linear-gradient(135deg,#10b981,#34d399) !important;transform:translateY(-1px);}
.stTabs [data-baseweb="tab-list"]{background:rgba(15,23,42,.6) !important;border-radius:10px !important;padding:4px !important;border:1px solid rgba(96,165,250,.2);gap:2px;}
.stTabs [data-baseweb="tab"]{color:#94a3b8 !important;border-radius:8px !important;font-weight:600 !important;font-size:.78rem !important;font-family:'Sora',sans-serif !important;padding:6px 10px !important;}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#1e3a8a,#2563eb) !important;color:white !important;}
.stSuccess{background:rgba(6,78,59,.6) !important;border-color:#10b981 !important;color:#a7f3d0 !important;border-radius:10px !important;}
.stWarning{background:rgba(78,54,6,.6) !important;border-color:#f59e0b !important;color:#fde68a !important;border-radius:10px !important;}
.stError{background:rgba(78,6,6,.6) !important;border-color:#dc2626 !important;color:#fca5a5 !important;border-radius:10px !important;}
.stInfo{background:rgba(6,42,78,.6) !important;border-color:#3b82f6 !important;color:#bfdbfe !important;border-radius:10px !important;}
hr{border-color:rgba(96,165,250,.15) !important;}
::-webkit-scrollbar{width:6px;}::-webkit-scrollbar-track{background:rgba(15,23,42,.4);}::-webkit-scrollbar-thumb{background:rgba(96,165,250,.4);border-radius:3px;}
.sec{font-size:.65rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#60a5fa;margin:1rem 0 .45rem;border-bottom:1px solid rgba(96,165,250,.2);padding-bottom:.3rem;}
.info-strip{background:rgba(30,58,138,.3);border:1px solid rgba(96,165,250,.2);border-radius:8px;padding:7px 12px;font-size:.77rem;color:#93c5fd;margin-bottom:.4rem;}
.conn-badge{display:inline-flex;align-items:center;gap:7px;padding:5px 14px;border-radius:20px;font-size:.73rem;font-weight:700;}
.conn-live{background:rgba(6,78,59,.5);border:1px solid #10b981;color:#34d399;}
.conn-pending{background:rgba(78,54,6,.5);border:1px solid #f59e0b;color:#fbbf24;}
.conn-offline{background:rgba(78,6,6,.5);border:1px solid #dc2626;color:#f87171;}
.job-card{background:linear-gradient(135deg,rgba(30,58,138,.25),rgba(15,23,42,.4));border:1px solid rgba(96,165,250,.18);border-radius:12px;padding:12px 16px;margin-bottom:8px;}
.job-route{font-size:.95rem;font-weight:700;color:#e2e8f0;}
.job-meta{font-size:.73rem;color:#94a3b8;margin-top:5px;display:flex;flex-wrap:wrap;gap:10px;}
.doc-card{background:rgba(15,23,42,.55);border:1px solid rgba(96,165,250,.2);border-radius:10px;padding:10px 14px;margin-bottom:8px;}
.scan-box{background:linear-gradient(135deg,rgba(5,150,105,.15),rgba(6,78,59,.25));border:2px dashed rgba(52,211,153,.4);border-radius:14px;padding:20px;text-align:center;margin-bottom:1rem;}
.ext-banner{background:linear-gradient(135deg,rgba(5,150,105,.2),rgba(6,78,59,.35));border:1px solid rgba(52,211,153,.4);border-radius:12px;padding:14px 18px;margin-bottom:1rem;}
.queue-item{background:rgba(78,54,6,.25);border:1px solid rgba(245,158,11,.3);border-radius:8px;padding:.6rem .9rem;margin-bottom:.4rem;font-size:.79rem;}
.id-card{background:linear-gradient(135deg,rgba(5,150,105,.2),rgba(6,78,59,.35));border:1px solid rgba(52,211,153,.35);border-radius:14px;padding:14px 18px;margin-bottom:.8rem;}
.prof-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.prof-label{font-size:.62rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em;}
.odo-box{background:linear-gradient(135deg,#1e3a8a,#2563eb);border-radius:12px;padding:12px 18px;margin-bottom:.8rem;border:1px solid rgba(96,165,250,.35);}
.link-banner{background:linear-gradient(135deg,rgba(5,150,105,.2),rgba(6,78,59,.3));border:1px solid rgba(52,211,153,.35);border-radius:10px;padding:8px 14px;margin:.3rem 0 .8rem;font-size:.76rem;color:#6ee7b7;}
.pf-banner{background:rgba(5,150,105,.15);border:1px solid rgba(52,211,153,.3);border-radius:10px;padding:10px 14px;margin-bottom:.8rem;font-size:.79rem;color:#6ee7b7;}
</style>
""", unsafe_allow_html=True)

# ── DB Helpers ─────────────────────────────────────────────────────────────────
def db_ok(): return os.path.exists(DB_PATH)
def get_conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL"); return c

def ensure_schema():
    if not db_ok(): return
    try:
        conn = get_conn()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(Truck)").fetchall()]
        for col,typ in [("driver_id","TEXT"),("driver_license","TEXT"),("driver_phone","TEXT"),
                        ("driver_id_number","TEXT"),("driver_experience_years","INTEGER DEFAULT 0"),
                        ("driver_routes","TEXT"),("driver_certifications","TEXT")]:
            if col not in cols: conn.execute(f"ALTER TABLE Truck ADD COLUMN {col} {typ}")
        for (tid,) in conn.execute("SELECT truck_id FROM Truck WHERE driver_id IS NULL OR driver_id=''").fetchall():
            conn.execute("UPDATE Truck SET driver_id=? WHERE truck_id=?",(f"KSM-DRV-{tid:04d}",tid))
        conn.execute("""CREATE TABLE IF NOT EXISTS DriverDocuments (
            doc_id INTEGER PRIMARY KEY AUTOINCREMENT, truck_id INTEGER, driver_id TEXT,
            upload_date TEXT, doc_type TEXT, filename TEXT, file_data BLOB,
            file_size INTEGER, mime_type TEXT, extracted TEXT, linked_trip INTEGER, notes TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dd_drv ON DriverDocuments(driver_id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS DriverNotifications (
            notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id TEXT, truck_id INTEGER,
            sent_date TEXT, subject TEXT, message TEXT,
            priority TEXT DEFAULT 'Normal',
            read_at TEXT DEFAULT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dn_drv ON DriverNotifications(driver_id)")

        # Expiry tracking columns on Truck table
        truck_cols = [r[1] for r in conn.execute("PRAGMA table_info(Truck)").fetchall()]
        for col, typ in [
            ("pdp_expiry",                 "TEXT"),
            ("roadworthy_expiry",          "TEXT"),
            ("cross_border_permit_expiry", "TEXT"),
            ("service_warning_active",     "INTEGER DEFAULT 0"),
            ("service_warning_date",       "TEXT"),
            ("truck_status",               "TEXT DEFAULT 'ACTIVE'"),
        ]:
            if col not in truck_cols:
                conn.execute(f"ALTER TABLE Truck ADD COLUMN {col} {typ}")

        # Pre-trip check log table
        conn.execute("""CREATE TABLE IF NOT EXISTS PreTripCheck (
            check_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            truck_id    INTEGER,
            driver_id   TEXT,
            check_date  TEXT,
            items_checked TEXT,
            odometer    REAL,
            notes       TEXT)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ptc_drv ON PreTripCheck(driver_id)")

        conn.commit(); conn.close()
    except Exception: pass

def get_driver_by_id(did):
    if not db_ok(): return None
    try:
        conn = get_conn()
        row = conn.execute("""SELECT truck_id,registration,driver,mileage,fuel_tank_capacity,
            driver_id,driver_license,driver_phone,driver_id_number,driver_experience_years,
            driver_routes,driver_certifications,truck_status,model,
            pdp_expiry,roadworthy_expiry,cross_border_permit_expiry,
            last_service_km,service_interval
            FROM Truck WHERE driver_id=?""",(did,)).fetchone()
        conn.close(); return row
    except: return None

def get_notifications(did, tid, limit=20):
    """Fetch notifications for this driver (unread first, then recent read)."""
    if not db_ok(): return []
    try:
        conn = get_conn()
        rows = conn.execute("""SELECT notif_id,sent_date,subject,message,priority,read_at
            FROM DriverNotifications
            WHERE driver_id=? OR (truck_id=? AND driver_id IS NULL)
            ORDER BY read_at IS NOT NULL ASC, sent_date DESC LIMIT ?""",
            (did, tid, limit)).fetchall()
        conn.close(); return rows
    except: return []

def get_unread_count(did, tid):
    if not db_ok(): return 0
    try:
        conn = get_conn()
        n = conn.execute("SELECT COUNT(*) FROM DriverNotifications WHERE (driver_id=? OR truck_id=?) AND read_at IS NULL",
                         (did, tid)).fetchone()[0]
        conn.close(); return n
    except: return 0

def mark_notification_read(notif_id):
    if not db_ok(): return
    try:
        conn = get_conn()
        conn.execute("UPDATE DriverNotifications SET read_at=? WHERE notif_id=?",
                     (datetime.now().strftime("%Y-%m-%d %H:%M"), notif_id))
        conn.commit(); conn.close()
    except: pass

def mark_all_read(did, tid):
    if not db_ok(): return
    try:
        conn = get_conn()
        conn.execute("UPDATE DriverNotifications SET read_at=? WHERE (driver_id=? OR truck_id=?) AND read_at IS NULL",
                     (datetime.now().strftime("%Y-%m-%d %H:%M"), did, tid))
        conn.commit(); conn.close()
    except: pass

def save_sos(d):
    """Log SOS as a Critical incident in MaintenanceLog."""
    if not db_ok(): return False
    try:
        conn = get_conn()
        conn.execute("""INSERT INTO MaintenanceLog
            (truck_id,date,description,cost,odometer,service_type,notes) VALUES(?,?,?,?,?,?,?)""",
            (d["truck_id"], d["date"],
             f"[SOS] EMERGENCY — {d['driver_id']}",
             0, d.get("odometer", 0), "SOS",
             f"Location: {d.get('location','Unknown')} | Driver: {d['driver_id']} | Truck: {d.get('reg','?')}"))
        conn.commit(); conn.close(); return True
    except: return False

def get_last_fuel(tid):
    if not db_ok(): return None
    try:
        conn = get_conn()
        r = conn.execute("SELECT fuel_added,odometer,date,cost_per_liter FROM FuelConsumption "
                         "WHERE truck_id=? ORDER BY odometer DESC LIMIT 1",(tid,)).fetchone()
        conn.close(); return r
    except: return None

def get_avg_eff(tid,window=10):
    if not db_ok(): return None
    try:
        conn = get_conn()
        rows = conn.execute("SELECT actual_fuel_efficiency FROM Trip WHERE truck_id=? "
                            "AND actual_fuel_efficiency>0 ORDER BY date DESC LIMIT ?",(tid,window)).fetchall()
        conn.close()
        vals=[r[0] for r in rows if r[0]]
        return round(sum(vals)/len(vals),2) if vals else None
    except: return None

def get_driver_jobs(tid,limit=25):
    if not db_ok(): return []
    try:
        conn = get_conn()
        rows = conn.execute("""SELECT trip_id,date,start_location,end_location,distance,load,
            fuel_consumed,actual_fuel_efficiency,trip_duration_hours,border_crossings,
            delivery_on_time,terrain_type,weather_condition FROM Trip
            WHERE truck_id=? ORDER BY date DESC,trip_id DESC LIMIT ?""",(tid,limit)).fetchall()
        conn.close(); return rows
    except: return []

def get_driver_docs(tid,did,limit=30):
    if not db_ok(): return []
    try:
        conn = get_conn()
        rows = conn.execute("""SELECT doc_id,upload_date,doc_type,filename,file_size,
            extracted,linked_trip,notes FROM DriverDocuments
            WHERE truck_id=? OR driver_id=? ORDER BY upload_date DESC LIMIT ?""",(tid,did,limit)).fetchall()
        conn.close(); return rows
    except: return []

def save_trip(d):
    if not db_ok(): return False
    try:
        conn = get_conn(); cur = conn.cursor()
        dist = d["distance"]; fuel = d["fuel_consumed"]
        eff  = dist/fuel if (dist>0 and fuel>0) else 0
        cur.execute("""INSERT INTO Trip
            (truck_id,start_location,end_location,distance,load,date,fuel_consumed,
             actual_fuel_efficiency,trip_duration_hours,border_crossings,terrain_type,
             weather_condition,road_quality,predicted_fuel_efficiency,risk_score,
             delivery_on_time,revenue,profit_margin,driver_experience_years,
             hard_braking_events,idle_time_minutes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["truck_id"],d["origin"],d["destination"],dist,d.get("load_kg",0),d["date"],
             fuel,eff,d.get("duration_h",0.0),d.get("border_crossings",0),
             d.get("terrain","Rolling"),"Clear",0.75,eff,0.15,
             1 if d.get("on_time",True) else 0,
             0,0,d.get("driver_exp",5),0,0))
        odo = d.get("odometer",0)
        if odo>0: cur.execute("UPDATE Truck SET mileage=? WHERE truck_id=?",(odo,d["truck_id"]))
        svc = conn.execute("SELECT last_service_km,service_interval,service_warning_active FROM Truck WHERE truck_id=?",
                           (d["truck_id"],)).fetchone()
        if svc and odo>0:
            ls,iv,ac = svc; iv=iv or SERVICE_INTERVAL_KM
            if (odo-(ls or 0))>=iv*0.90 and not ac:
                cur.execute("UPDATE Truck SET service_warning_active=1,service_warning_date=? WHERE truck_id=?",(d["date"],d["truck_id"]))
                try: cur.execute("INSERT INTO ServiceWarning(truck_id,warning_type,triggered_date,triggered_km) VALUES(?,?,?,?)",
                                 (d["truck_id"],"Service Due",d["date"],odo))
                except: pass
                st.warning("⚠️ Service warning triggered. Fleet manager notified.")
        conn.commit(); conn.close(); return True
    except Exception as e: st.error(f"DB error: {e}"); return False

def save_fuel(d):
    if not db_ok(): return False
    try:
        conn = get_conn()
        conn.execute("""INSERT INTO FuelConsumption
            (truck_id,date,fuel_added,odometer,cost_per_liter,total_cost,
             fuel_type,station_location,notes,is_full_tank)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (d["truck_id"],d["date"],d["fuel_added"],d["odometer"],d["cost_per_liter"],
             round(d["fuel_added"]*d["cost_per_liter"],2),
             d.get("fuel_type","Diesel 50PPM"),d.get("station",""),d.get("notes",""),
             1 if d.get("full_tank",True) else 0))
        if d["odometer"]>0:
            conn.execute("UPDATE Truck SET mileage=? WHERE truck_id=?",(d["odometer"],d["truck_id"]))
        conn.commit(); conn.close(); return True
    except Exception as e: st.error(f"DB error: {e}"); return False

def save_event(d):
    if not db_ok(): return False
    try:
        conn = get_conn()
        conn.execute("""INSERT INTO MaintenanceLog
            (truck_id,date,description,cost,odometer,service_type,notes) VALUES(?,?,?,?,?,?,?)""",
            (d["truck_id"],d["date"],f"[DRIVER EVENT] {d['event_type']}",0,
             d.get("odometer",0),"DriverEvent",
             f"Severity: {d['severity']} | Location: {d['location']} | {d['description']}"))
        conn.commit(); conn.close(); return True
    except Exception as e: st.error(f"DB error: {e}"); return False

def save_doc(tid,did,dtype,fname,fbytes,mime,extracted,notes="",linked_trip=None):
    if not db_ok(): return None
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""INSERT INTO DriverDocuments
            (truck_id,driver_id,upload_date,doc_type,filename,file_data,file_size,
             mime_type,extracted,linked_trip,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (tid,did,datetime.now().strftime("%Y-%m-%d %H:%M"),dtype,fname,fbytes,
             len(fbytes) if fbytes else 0,mime,
             json.dumps(extracted,ensure_ascii=False) if extracted else "{}",
             linked_trip,notes))
        doc_id = cur.lastrowid; conn.commit(); conn.close(); return doc_id
    except Exception as e: st.error(f"Save error: {e}"); return None

# ── Pre-trip checklist items ──────────────────────────────────────────────────
CHECKLIST_ITEMS = [
    ("tyres",       "🛞", "Tyres",          "All tyres inflated and no visible damage"),
    ("lights",      "💡", "Lights",          "Headlights, indicators and brake lights working"),
    ("brakes",      "🛑", "Brakes",          "Brake feel normal, no warning lights"),
    ("fluids",      "🛢️", "Fluids",          "Oil, coolant and windscreen washer checked"),
    ("load",        "📦", "Load secured",    "Cargo strapped, sealed and within limits"),
    ("docs",        "📋", "Documents on board","Job order, licence and cross-border docs present"),
    ("cab",         "🪟", "Cab & mirrors",   "Mirrors adjusted, cab tidy, no obstructions"),
    ("fire_ext",    "🧯", "Fire extinguisher","Present and not expired"),
]

DSR_REASONS_UNFIT = ["Fatigue / insufficient rest","Illness","Medication affecting alertness",
                      "Personal emergency","Injury","Other"]

def save_dsr(d):
    """Save Daily Status Report into MaintenanceLog with service_type='DSR'."""
    if not db_ok(): return False
    try:
        conn = get_conn()
        notes = (f"Fit: {d['fit']} | Start ODO: {d['odometer']} | "
                 f"Checklist: {d['checklist_score']}/8 | "
                 f"Issues: {d.get('issues','none') or 'none'} | "
                 f"Unfit reason: {d.get('unfit_reason','') or ''}")
        conn.execute("""INSERT INTO MaintenanceLog
            (truck_id,date,description,cost,odometer,service_type,notes) VALUES(?,?,?,?,?,?,?)""",
            (d["truck_id"], d["date"],
             f"[DSR] {'FIT' if d['fit'] else 'UNFIT'} — {d['driver_id']}",
             0, d["odometer"], "DSR", notes))
        conn.commit(); conn.close(); return True
    except Exception as e: st.error(f"DSR save error: {e}"); return False

def save_pretripcheck(tid, did, items_checked, odometer, notes=""):
    if not db_ok(): return
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO PreTripCheck(truck_id,driver_id,check_date,items_checked,odometer,notes) "
            "VALUES(?,?,?,?,?,?)",
            (tid, did, date.today().isoformat(), json.dumps(items_checked), odometer, notes)
        )
        conn.commit(); conn.close()
    except Exception: pass

def days_until_expiry(date_str):
    if not date_str or str(date_str) in ("None", "nan", ""):
        return None
    try:
        exp = date.fromisoformat(str(date_str)[:10])
        return (exp - date.today()).days
    except: return None

def expiry_badge(days):
    if days is None: return "— not set", "#64748b"
    if days < 0:     return f"EXPIRED {abs(days)}d ago", "#dc2626"
    if days <= 7:    return f"⚠️ {days}d left", "#dc2626"
    if days <= 30:   return f"⚠️ {days}d left", "#f59e0b"
    return f"✅ {days}d left", "#10b981"

def get_todays_dsr(tid, did):
    """Return today's DSR row if already submitted."""
    if not db_ok(): return None
    try:
        conn = get_conn()
        today = date.today().strftime("%Y-%m-%d")
        row = conn.execute(
            """SELECT notes FROM MaintenanceLog
               WHERE truck_id=? AND service_type='DSR' AND date=?
               ORDER BY id DESC LIMIT 1""", (tid, today)).fetchone()
        conn.close(); return row
    except: return None

# ── Offline queue ──────────────────────────────────────────────────────────────
def enqueue(rec,kind="trip"): st.session_state.setdefault(f"offline_{kind}",[]).append(rec)
def qcount(kind): return len(st.session_state.get(f"offline_{kind}",[]))
def sync_all():
    r={"trips":0,"fuel":0,"events":0,"failed":0}
    for lst,fn,key in [(st.session_state.get("offline_trip",[]),save_trip,"trips"),
                       (st.session_state.get("offline_fuel",[]),save_fuel,"fuel"),
                       (st.session_state.get("offline_event",[]),save_event,"events")]:
        for rec in list(lst):
            if fn(rec): lst.remove(rec); r[key]+=1
            else: r["failed"]+=1
    return r

# ── Geometry helpers ─────────────────────────────────────────────────────────
def est_dist(o,d):
    if o in LOCATION_COORDS and d in LOCATION_COORDS:
        p1,p2=LOCATION_COORDS[o],LOCATION_COORDS[d]
        return round(math.sqrt((p2[0]-p1[0])**2+(p2[1]-p1[1])**2)*111*1.2,1)
    return 0.0

def det_terrain(o,d):
    M={"Mbabane","Piggs Peak","Nelspruit"}; F={"Lomahasha","Lavumisa","Maputo"}
    if o in M or d in M: return "Mountainous"
    if o in F and d in F: return "Flat"
    return "Rolling"

def fmt_size(n):
    if n<1024: return f"{n} B"
    if n<1048576: return f"{n/1024:.1f} KB"
    return f"{n/1048576:.1f} MB"

# ── AI extraction ──────────────────────────────────────────────────────────────
DOC_PROMPTS = {
"Job Order": """Extract all data from this transport job order. Return ONLY valid JSON:
{"job_number":"...","date":"YYYY-MM-DD","client_name":"...","origin":"...","destination":"...","truck_registration":"...","driver":"...","trailer_registration":"...","weight_kg":null,"cargo_description":"...","seal_number":"...","loading_time":"...","expected_delivery":"...","border_crossings":null,"distance_km":null}""",
"Fuel Receipt": """Extract all data from this fuel receipt. Return ONLY valid JSON:
{"receipt_number":"...","date":"YYYY-MM-DD","time":"HH:MM","station_name":"...","pump_number":"...","fuel_type":"...","volume_litres":null,"unit_price":null,"total_amount":null,"odometer_km":null,"vehicle_registration":"...","driver_id":"...","payment_method":"...","card_last4":"..."}""",
"Weighbridge Ticket": """Extract all data. Return ONLY valid JSON:
{"ticket_number":"...","date":"YYYY-MM-DD","truck_registration":"...","driver":"...","gross_weight_kg":null,"tare_weight_kg":null,"net_weight_kg":null,"cargo_type":"...","quality_pct":null,"field_section":"..."}""",
"Delivery Note": """Extract all data. Return ONLY valid JSON:
{"delivery_number":"...","date":"YYYY-MM-DD","client_name":"...","origin":"...","destination":"...","cargo_description":"...","weight_kg":null,"received_by":"...","remarks":"..."}""",
"Other Document": """Extract all visible data. Return ONLY valid JSON with all key fields found.""",
}

def extract_with_ai(fbytes,mime,dtype,api_key):
    try:
        prompt = DOC_PROMPTS.get(dtype, DOC_PROMPTS["Other Document"])
        try:
            from google import genai as _g
            client = _g.Client(api_key=api_key)
            resp = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=[_g.types.Part.from_bytes(data=fbytes,mime_type=mime), prompt])
        except ImportError:
            import google.generativeai as gl
            gl.configure(api_key=api_key)
            m = gl.GenerativeModel("gemini-2.5-flash-lite")
            b64 = base64.b64encode(fbytes).decode()
            resp = m.generate_content([{"mime_type":mime,"data":b64},prompt])
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"): text=text[4:]
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        return {"_error":f"Could not parse AI response: {e}"}
    except Exception as e:
        return {"_error":str(e)}

def apply_extraction(dtype,ext):
    if not ext or "_error" in ext: return
    if dtype == "Job Order":
        st.session_state["pf_trip"] = {
            "origin": ext.get("origin",""), "destination": ext.get("destination",""),
            "load_kg": ext.get("weight_kg"), "border": ext.get("border_crossings",0),
            "job_ref": ext.get("job_number",""), "truck_reg": ext.get("truck_registration",""),
            "cargo_desc": ext.get("cargo_description",""),
        }
        st.toast("📋 Job Order extracted — Trip Log pre-filled!", icon="✅")
    elif dtype == "Fuel Receipt":
        st.session_state["pf_fuel"] = {
            "fuel_added": ext.get("volume_litres"), "cost_per_L": ext.get("unit_price"),
            "odometer": ext.get("odometer_km"), "station": ext.get("station_name",""),
            "receipt_no": ext.get("receipt_number",""), "fuel_type": ext.get("fuel_type","Diesel 50PPM"),
            "pump": ext.get("pump_number",""),
        }
        st.toast("◉ Fuel receipt extracted — Fuel tab pre-filled!", icon="✅")
    elif dtype == "Weighbridge Ticket":
        pf = st.session_state.get("pf_trip",{})
        pf.update({"load_kg": ext.get("net_weight_kg") or ext.get("gross_weight_kg"),
                   "wb_ticket": ext.get("ticket_number",""), "quality_pct": ext.get("quality_pct",0)})
        st.session_state["pf_trip"] = pf
        st.toast("Weighbridge ticket extracted!", icon="✅")

# ── Session state defaults ────────────────────────────────────────────────────
ensure_schema()
for k,v in [("drv_authenticated",False),("drv_driver_id",None),("drv_driver_row",None),
             ("selected_truck_id",None),("selected_truck_label",""),("current_odo",0.0),
             ("offline_trip",[]),("offline_fuel",[]),("offline_event",[]),
             ("pf_trip",{}),("pf_fuel",{}),("scan_extracted",None),("scan_doc_type",None),
             ("checklist_done",False),("checklist_data",{}),("dsr_done",False),("sos_fired",False)]:
    if k not in st.session_state: st.session_state[k]=v

# ── Performance stats helper ──────────────────────────────────────────────────
def get_perf_stats(tid, did):
    """Return driver performance stats for current month and all-time."""
    if not db_ok(): return {}
    try:
        conn = get_conn()
        month_start = date.today().strftime("%Y-%m-01")
        # This month
        m = conn.execute("""SELECT COUNT(*),SUM(distance),AVG(actual_fuel_efficiency),
            SUM(delivery_on_time),COUNT(*) FROM Trip
            WHERE truck_id=? AND date>=?""",(tid,month_start)).fetchone()
        # All time
        a = conn.execute("""SELECT COUNT(*),SUM(distance),AVG(actual_fuel_efficiency),
            SUM(delivery_on_time),COUNT(*) FROM Trip WHERE truck_id=?""",(tid,)).fetchone()
        # Incidents this month
        inc = conn.execute("""SELECT COUNT(*) FROM MaintenanceLog
            WHERE truck_id=? AND service_type='DriverEvent' AND date>=?""",(tid,month_start)).fetchone()
        # Fleet avg efficiency
        fleet_avg = conn.execute("""SELECT AVG(actual_fuel_efficiency) FROM Trip
            WHERE actual_fuel_efficiency>0""").fetchone()
        conn.close()
        trips_m, dist_m, eff_m, ontime_m, total_m = m
        trips_a, dist_a, eff_a, ontime_a, total_a = a
        return {
            "trips_month": trips_m or 0,
            "dist_month":  round(dist_m or 0, 0),
            "eff_month":   round(eff_m or 0, 2),
            "ontime_month": int(ontime_m or 0),
            "total_month":  int(total_m or 0),
            "trips_all":   trips_a or 0,
            "dist_all":    round(dist_a or 0, 0),
            "eff_all":     round(eff_a or 0, 2),
            "incidents_month": inc[0] if inc else 0,
            "fleet_avg_eff": round(fleet_avg[0] or 0, 2) if fleet_avg else 0,
        }
    except: return {}

# ── Login ─────────────────────────────────────────────────────────────────────
def _render_login():
    BASE_DIR=os.path.dirname(os.path.abspath(__file__))
    logo=os.path.join(BASE_DIR,"image_2ff50a.png")
    hA,hB=st.columns([1,3])
    with hA:
        if os.path.exists(logo): st.image(logo,width=85)
    with hB:
        st.markdown("<div style='padding-top:10px;'><div style='font-size:1.3rem;font-weight:900;color:#60a5fa;'>KSM DRIVER TERMINAL</div>"
                    "<div style='font-size:.72rem;font-weight:700;color:#34d399;letter-spacing:.1em;margin-top:3px;'>SMART FREIGHT SOLUTIONS · SECURE ACCESS</div></div>",
                    unsafe_allow_html=True)
    st.markdown("<div style='background:rgba(15,23,42,.88);backdrop-filter:blur(20px);border:1px solid rgba(96,165,250,.25);border-radius:16px;padding:28px 24px;margin-top:20px;'>"
                "<div style='color:#93c5fd;font-size:.68rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;margin-bottom:16px;text-align:center;border-bottom:1px solid rgba(96,165,250,.15);padding-bottom:12px;'>🔐 Driver Authentication Required</div>",
                unsafe_allow_html=True)
    with st.form("drv_login"):
        did=st.text_input("Driver ID",placeholder="e.g. KSM-DRV-0001")
        pin=st.text_input("PIN",type="password",placeholder="Enter your PIN")
        ok =st.form_submit_button("🔐 Sign In",type="primary",use_container_width=True)
    if ok:
        drv_id=did.strip().upper()
        if _AUTH_DB:
            auth_ok, auth_result, truck_id_db = _db_verify_driver(drv_id, pin)
        else:
            exp=DRIVER_PINS.get(drv_id)
            auth_ok = bool(exp and pin==exp)
            auth_result = drv_id
            truck_id_db = None
        if auth_ok:
            row=get_driver_by_id(drv_id)
            if _AUTH_DB: _log_access(drv_id, "driver", truck_id_db)
            st.session_state.update({"drv_authenticated":True,"drv_driver_id":drv_id,"drv_driver_row":row,
                                      "selected_truck_id":row[0] if row else None,
                                      "selected_truck_label":row[1] if row else "",
                                      "current_odo":float(row[3] or 0) if row else 0.0})
            st.rerun()
        else:
            st.error(f"❌ {auth_result if _AUTH_DB else 'Invalid Driver ID or PIN.'}")
    st.markdown("<div style='text-align:center;margin-top:14px;color:#475569;font-size:.67rem;border-top:1px solid rgba(96,165,250,.1);padding-top:12px;'>"
                "Demo — KSM-DRV-0001 / PIN: 1234 &nbsp;·&nbsp; Credentials managed in User Management</div></div>",unsafe_allow_html=True)

if not st.session_state.get("drv_authenticated"): _render_login(); st.stop()

# ── Post-login setup ──────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
logo_path  = os.path.join(BASE_DIR,"image_2ff50a.png")
drv_id     = st.session_state["drv_driver_id"]
drv_row    = st.session_state["drv_driver_row"]
connected  = db_ok()
_drv_row_fresh = get_driver_by_id(drv_id) if drv_id else None
trucks     = [_drv_row_fresh] if _drv_row_fresh else []
total_pend = qcount("trip")+qcount("fuel")+qcount("event")

# Resolve assigned truck
if drv_row and trucks:
    assigned = next((r for r in trucks if r[0]==drv_row[0]), None)
    if assigned:
        st.session_state.selected_truck_id    = assigned[0]
        st.session_state.selected_truck_label = assigned[1]
        st.session_state.current_odo          = float(assigned[3] or 0)
        tank_cap = float(assigned[4] or 300)
    else:
        assigned = None; tank_cap = 300.0
else:
    assigned = None; tank_cap = 300.0

tid     = st.session_state.selected_truck_id
cur_odo = st.session_state.current_odo
sel_row = next((r for r in trucks if r[0]==tid), None) if tid else None

# Sidebar: Gemini key only
with st.sidebar:
    st.markdown("#### ◈ AI Document Scanner")
    gemini_key=st.text_input("Gemini API Key",type="password",
        value=st.session_state.get("gemini_key",""),
        help="Free at aistudio.google.com — enables AI document scanning")
    if gemini_key: st.session_state["gemini_key"]=gemini_key; st.success("✅ AI scanning enabled")
    else: st.info("Add Gemini key to enable scanning")

# ── Header ────────────────────────────────────────────────────────────────────
if connected and not total_pend: chtml='<span class="conn-badge conn-live">● LIVE</span>'
elif connected: chtml=f'<span class="conn-badge conn-pending">◑ {total_pend} pending</span>'
else: chtml='<span class="conn-badge conn-offline">○ OFFLINE</span>'

dname = drv_row[2] if drv_row else "Driver"
treg  = drv_row[1] if drv_row else "—"
now   = datetime.now()

hA,hB,hC = st.columns([1,4,1])
with hA:
    if os.path.exists(logo_path): st.image(logo_path,width=68)
with hB:
    st.markdown(f"<div style='padding-top:4px;'>"
        f"<div style='font-size:.72rem;font-weight:800;color:#60a5fa;letter-spacing:.1em;'>KSM DRIVER TERMINAL v6.1</div>"
        f"<div style='font-size:1rem;font-weight:700;color:#fff;margin-top:2px;'>{dname}</div>"
        f"<div style='font-size:.68rem;color:#64748b;margin-top:2px;'>"
        f"ID: <span style='color:#34d399;font-weight:700;font-family:monospace;'>{drv_id}</span>"
        f" · Truck: <span style='color:#93c5fd;font-weight:700;'>{treg}</span>"
        f" · {now.strftime('%d %b %Y %H:%M')}</div></div>",unsafe_allow_html=True)
with hC:
    st.markdown("<div style='height:4px'></div>",unsafe_allow_html=True)
    _unread = get_unread_count(drv_id, tid or 0) if connected else 0
    if _unread:
        st.markdown(f"<div style='text-align:center;font-size:.68rem;font-weight:800;color:#fbbf24;"
                    f"background:rgba(78,54,6,.5);border:1px solid #f59e0b;border-radius:20px;"
                    f"padding:2px 10px;margin-bottom:4px;'>{_unread} new</div>",unsafe_allow_html=True)
    if st.button("🆘 SOS",use_container_width=True,help="Emergency — tap to alert fleet manager immediately"):
        _sos_rec={"truck_id":tid or 0,"driver_id":drv_id,"date":now.strftime("%Y-%m-%d"),
                  "odometer":cur_odo,"location":"GPS unavailable — contact driver","reg":treg}
        if connected and save_sos(_sos_rec): st.session_state["sos_fired"]=True
        else: st.session_state["sos_fired"]=False
        st.rerun()
    if st.session_state.get("sos_fired"):
        st.markdown("<div style='text-align:center;font-size:.68rem;font-weight:800;color:#f87171;"
                    "background:rgba(78,6,6,.5);border:1px solid #dc2626;border-radius:6px;"
                    "padding:3px 6px;margin-top:2px;'>🚨 SOS SENT</div>",unsafe_allow_html=True)
    st.markdown("<div style='height:2px'></div>",unsafe_allow_html=True)
    if st.button("Sign Out",use_container_width=True):
        for k in list(st.session_state.keys()):
            st.session_state.pop(k,None)
        st.rerun()

st.divider()

# ── Truck status strip ────────────────────────────────────────────────────────
if not assigned:
    st.warning("⚠️ No truck assigned to your account. Contact your fleet manager.")
else:
    (t_id,t_reg,t_driver,t_mile,t_tank,t_did,t_lic,t_phone,t_idn,t_exp,t_routes,t_certs,t_stat,t_model,t_pdp_exp,t_rbw_exp,t_cbp_exp,t_last_svc,t_svc_int) = assigned
    st.markdown(
        f"<div style='background:rgba(15,23,42,.6);border:1px solid rgba(96,165,250,.25);"
        f"border-radius:9px;padding:9px 16px;display:flex;align-items:center;gap:12px;margin-bottom:.5rem;'>"
        f"<span style='font-size:.85rem;font-weight:700;color:#e2e8f0;'>"
        f"▣ <span style='color:#93c5fd;'>{t_reg}</span>"
        f"<span style='font-size:.72rem;color:#64748b;font-weight:400;margin-left:8px;'>{t_model or ''} · {cur_odo:,.0f} km</span>"
        f"</span><span style='margin-left:auto;'>{chtml}</span></div>",
        unsafe_allow_html=True)

# =============================================================================
# 3-TAB NAVIGATION: Now  |  Log  |  Me
# =============================================================================
tab_now, tab_log, tab_me = st.tabs(["🏠 Now","📋 Log","👤 Me"])

# ═══════════════════════════════════════════════════════════════════════════════
# NOW TAB — Today Screen: Job card, SOS, checklist gate, route briefing, DSR
# ═══════════════════════════════════════════════════════════════════════════════
with tab_now:
    if not tid:
        st.warning("⚠️ No truck assigned. Contact your fleet manager.")
        st.stop()

    # ── TODAY CARD ─────────────────────────────────────────────────────────────
    pf_now   = st.session_state.get("pf_trip", {})
    hour_now = datetime.now().hour
    greeting = "Good morning" if hour_now < 12 else ("Good afternoon" if hour_now < 17 else "Good evening")
    today_job_origin = pf_now.get("origin", "—")
    today_job_dest   = pf_now.get("destination", "—")
    job_loaded       = bool(pf_now.get("origin") and pf_now.get("destination"))
    checklist_done_now = st.session_state.get("checklist_done", False)

    # Determine route alert from corridor warnings
    _cw_alerts = []
    if job_loaded:
        _cw_map = {
            ("Manzini","Johannesburg"): "N3 Van Reenen — fog risk. Depart before 07:00.",
            ("Manzini","Durban"):       "N2 Empangeni — high accident zone. Reduce speed.",
            ("Mbabane","Johannesburg"): "Malagwane Hill — engage low gear before descent.",
            ("Mbabane","Durban"):       "Lavumisa border closes 22:00. Plan arrival by 20:00.",
            ("Manzini","Maputo"):       "Lomahasha border closes 20:00. Carry MZN cash.",
            ("Manzini","Beira"):        "EN6 Mozambique — fill up at Chimoio, long stretch no fuel.",
            ("Manzini","Harare"):       "Beitbridge — 4–12hr wait. Carry food and water.",
        }
        for (o, d), alert in _cw_map.items():
            if (o in today_job_origin or today_job_origin in o) and                (d in today_job_dest or today_job_dest in d):
                _cw_alerts.append(alert)
                break

    # Build status color
    _status_c = "#22c55e" if checklist_done_now else "#f59e0b"
    _status_l = "✅ Ready to depart" if checklist_done_now else "⚠️ Checklist required"

    # Build today card HTML in parts to avoid f-string nesting issues
    _job_html = (
        f"<div style='font-size:.85rem;font-weight:700;color:#e2e8f0;margin-bottom:6px;'>"
        f"Today's Job: <span style='color:#fbbf24;'>{today_job_origin} &rarr; {today_job_dest}</span></div>"
        if job_loaded else
        "<div style='font-size:.8rem;color:#64748b;margin-bottom:6px;'>No job loaded — scan a Job Order in Log &rarr; Scan.</div>"
    )
    _alert_html = "".join(
        f"<div style='background:rgba(249,115,22,.15);border:1px solid rgba(249,115,22,.25);"
        f"border-radius:8px;padding:6px 12px;font-size:.78rem;color:#fde68a;margin-bottom:5px;'>"
        f"&#9888; {a}</div>"
        for a in _cw_alerts
    )
    _dot_html = (
        f"<div style='width:8px;height:8px;background:{_status_c};"
        f"border-radius:50%;display:inline-block;margin-right:6px;'></div>"
        f"<span style='font-size:.72rem;color:{_status_c};font-weight:700;'>{_status_l}</span>"
    )
    _today_card = (
        "<div style='background:linear-gradient(135deg,rgba(15,23,42,.92),rgba(30,58,138,.45));"
        "border:1px solid rgba(96,165,250,.3);border-radius:16px;padding:18px 20px;margin-bottom:12px;'>"
        "<div style='font-size:.7rem;font-weight:800;letter-spacing:.14em;"
        "text-transform:uppercase;color:#34d399;margin-bottom:10px;'>Today</div>"
        f"<div style='font-size:1.1rem;font-weight:800;color:#e2e8f0;margin-bottom:4px;'>{greeting}, {dname.split()[0]}</div>"
        f"<div style='font-size:.82rem;color:#93c5fd;margin-bottom:10px;'>Truck: <b>{treg}</b> &nbsp;&middot;&nbsp; Odometer: <b>{cur_odo:,.0f} km</b></div>"
        + _job_html
        + _alert_html
        + f"<div style='margin-top:10px;'>{_dot_html}</div>"
        "</div>"
    )
    st.markdown(_today_card, unsafe_allow_html=True)

    # ── Start Pre-Trip Check button (gates LOG tab) ────────────────────────────
    if not checklist_done_now:
        if st.button("✅ Start Pre-Trip Safety Check", use_container_width=True, type="primary",
                     help="Complete the 8-point safety check to unlock trip logging"):
            st.session_state["_goto_checklist"] = True
            st.session_state["checklist_done"]  = False
            st.rerun()
        st.info("Complete the pre-trip checklist before logging a trip. Tap above to begin.")
    else:
        chk = st.session_state.get("checklist_data", {})
        st.success(f"✅ Pre-trip check complete — {chk.get('score',8)}/8 items · "
                   f"{'No issues' if not chk.get('issues') else chk['issues'][:50]}")
        if st.button("↩ Redo Pre-Trip Check", key="redo_chk_now"):
            st.session_state["checklist_done"] = False
            st.rerun()

    st.divider()

    # ── GPS auto-location ─────────────────────────────────────────────────────
    st.markdown('<div class="sec">📍 My Location</div>', unsafe_allow_html=True)
    gps_html = """
    <div id="gps-wrap" style="margin-bottom:8px;">
      <button onclick="getGPS()" style="background:linear-gradient(135deg,#059669,#10b981);color:white;
        border:none;border-radius:8px;padding:8px 18px;font-weight:700;font-size:.82rem;cursor:pointer;width:100%;">
        📍 Get My GPS Location
      </button>
      <div id="gps-result" style="margin-top:6px;font-size:.78rem;color:#6ee7b7;font-family:monospace;"></div>
    </div>
    <script>
    function getGPS(){
      document.getElementById('gps-result').innerText='⏳ Getting location...';
      if(!navigator.geolocation){
        document.getElementById('gps-result').innerText='❌ GPS not available on this device';
        return;
      }
      navigator.geolocation.getCurrentPosition(function(p){
        var lat=p.coords.latitude.toFixed(5), lon=p.coords.longitude.toFixed(5);
        var acc=Math.round(p.coords.accuracy);
        document.getElementById('gps-result').innerText=
          '✅ '+lat+', '+lon+' (±'+acc+'m) — copied to clipboard';
        navigator.clipboard&&navigator.clipboard.writeText(lat+', '+lon);
        // store in sessionStorage for driver to reference
        sessionStorage.setItem('ksm_lat',lat);
        sessionStorage.setItem('ksm_lon',lon);
      }, function(e){
        document.getElementById('gps-result').innerText='⚠️ '+e.message;
      },{enableHighAccuracy:true,timeout:10000});
    }
    </script>
    """
    st.components.v1.html(gps_html, height=90)
    st.caption("GPS coordinates are captured for SOS and incident logging. Location is not tracked continuously.")

    st.divider()

    # ── Today's Job Card (detail section) ────────────────────────────────────
    st.markdown('<div class="sec">📋 Job Details</div>', unsafe_allow_html=True)
    pf = pf_now  # already set above
    last_fuel = get_last_fuel(tid)
    avg_eff   = get_avg_eff(tid)

    if pf.get("origin") and pf.get("destination"):
        jc_origin = pf["origin"]; jc_dest = pf["destination"]
        jc_load   = pf.get("load_kg") or 0
        jc_ref    = pf.get("job_ref","")
        jc_cargo  = pf.get("cargo_desc","")
        jc_dist   = est_dist(jc_origin, jc_dest)
        jc_fuel_e = round(jc_dist * FUEL_BASE_L_PER_100 / 100, 0)
        jc_terrain= det_terrain(jc_origin, jc_dest)
        st.markdown(f"""<div class="job-card" style="border-color:rgba(52,211,153,.35);">
        <div style="font-size:.6rem;font-weight:800;letter-spacing:.12em;color:#34d399;text-transform:uppercase;margin-bottom:8px;">📋 Active Job — Pre-filled from Scan</div>
        <div class="job-route">{jc_origin} → {jc_dest}</div>
        <div class="job-meta">
            {'<span>📦 '+f"{jc_load:,.0f} kg"+'</span>' if jc_load else ''}
            {'<span>'+jc_ref+'</span>' if jc_ref else ''}
            {'<span>'+jc_cargo[:40]+'</span>' if jc_cargo else ''}
            <span>~{jc_dist:.0f} km</span>
            <span>◉ ~{jc_fuel_e:.0f} L est.</span>
            <span>{jc_terrain}</span>
        </div></div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-strip">📋 No job loaded. Scan a Job Order in <b>📝 Log → Scan</b> to auto-fill your job details here.</div>',
                    unsafe_allow_html=True)

    # ── Fuel Calculator ───────────────────────────────────────────────────────
    st.markdown('<div class="sec">⛽ Fuel Calculator</div>', unsafe_allow_html=True)
    fc1, fc2 = st.columns(2)
    with fc1:
        fc_origin = st.text_input("From", key="fc_orig_txt",
            value=st.session_state.get("_fc_origin", pf_now.get("origin", "Manzini")),
            placeholder="e.g. Manzini CBD")
        st.session_state["_fc_origin"] = fc_origin
    with fc2:
        fc_dest = st.text_input("To", key="fc_dest_txt",
            value=st.session_state.get("_fc_dest", pf_now.get("destination", "")),
            placeholder="e.g. Johannesburg")
        st.session_state["_fc_dest"] = fc_dest

    # GPS distance for fuel calc
    _fc_gps_key = f"_fc_gps_{fc_origin}_{fc_dest}"
    _fc_gps = st.session_state.get(_fc_gps_key, {})
    _fg1, _fg2 = st.columns([1, 3])
    with _fg1:
        if st.button("📍 Get Distance", key="fc_gps_btn", use_container_width=True,
                     disabled=not (fc_origin.strip() and fc_dest.strip())):
            with st.spinner("Calculating..."):
                try:
                    from services.gps_routing import get_road_distance
                    _ors = st.session_state.get("ors_api_key", "")
                    _fc_gps = get_road_distance(fc_origin, fc_dest, _ors)
                    st.session_state[_fc_gps_key] = _fc_gps
                except Exception as _fe:
                    _fc_gps = {"error": str(_fe)}
                    st.session_state[_fc_gps_key] = _fc_gps
    with _fg2:
        if _fc_gps and "error" not in _fc_gps:
            st.success(f"📍 **{_fc_gps['distance_km']:.0f} km** road distance")
        elif _fc_gps and "error" in _fc_gps:
            st.warning(f"⚠️ {_fc_gps['error']}")

    if _fc_gps and "distance_km" in _fc_gps:
        fc_dist = _fc_gps["distance_km"]
    else:
        fc_dist  = est_dist(fc_origin, fc_dest)
    fc_rate  = avg_eff if avg_eff and avg_eff > 0 else (100/FUEL_BASE_L_PER_100)
    fc_need  = round(fc_dist / fc_rate, 0) if fc_rate > 0 else round(fc_dist * FUEL_BASE_L_PER_100 / 100, 0)
    fc_tank  = cur_odo  # current odo as proxy; actual tank level from last fill
    # Estimate remaining fuel from last fill
    lf_liters = float(last_fuel[0]) if last_fuel else 0
    lf_odo    = float(last_fuel[1]) if last_fuel else cur_odo
    km_since  = max(0, cur_odo - lf_odo)
    fc_consumed_since = round(km_since / fc_rate, 0) if (fc_rate > 0 and km_since > 0) else 0
    fc_est_remaining  = max(0, lf_liters - fc_consumed_since) if last_fuel else 0
    fc_after_trip     = fc_est_remaining - fc_need
    fc_pct_after      = round(fc_after_trip / tank_cap * 100, 0) if tank_cap > 0 else 0

    fa1,fa2,fa3,fa4 = st.columns(4)
    fa1.metric("📏 Distance", f"{fc_dist:.0f} km")
    fa2.metric("⛽ Est. Fuel Needed", f"{fc_need:.0f} L")
    fa3.metric("🪣 Est. in Tank", f"{fc_est_remaining:.0f} L" if last_fuel else "—")
    fa4.metric("📉 Tank After Trip", f"{fc_after_trip:.0f} L" if last_fuel else "—",
               delta=f"{fc_pct_after:.0f}%" if last_fuel else None,
               delta_color="normal" if fc_pct_after > 20 else "inverse")

    if last_fuel and fc_after_trip < tank_cap * 0.15:
        # Find midpoint city for refuel suggestion
        refuel_suggestions = {"Johannesburg":"Nelspruit","Durban":"Pongola / Mkuze",
                               "Maputo":"Lomahasha / Namaacha","Nelspruit":"Ermelo"}
        refuel_tip = refuel_suggestions.get(fc_dest, "before destination")
        st.markdown(f'<div class="info-strip" style="border-color:#f59e0b40;color:#fbbf24;">⛽ <b>Low fuel warning</b> — estimated {fc_after_trip:.0f} L remaining after trip '
                    f'({fc_pct_after:.0f}% of tank). Consider refuelling at <b>{refuel_tip}</b>.</div>',
                    unsafe_allow_html=True)
    elif last_fuel:
        st.markdown(f'<div class="info-strip">✅ Sufficient fuel for this trip — ~{fc_pct_after:.0f}% remaining on arrival.</div>',
                    unsafe_allow_html=True)

    # ── Route Briefing ────────────────────────────────────────────────────────
    ROUTE_DATA = {
        ("Manzini","Johannesburg"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
            "border_docs":["CMR/Waybill","Vehicle Licence Disc","Driver Licence","PDP","Cross-border permit","Company letter"],
            "est_wait":"1–3 hrs","dangers":["Van Reenen Pass (fog/ice Jun–Aug)","N3 truck stops (theft risk at night)","Standerton weigh bridge"],"overnight":"Standerton or Heidelberg"},
        ("Manzini","Durban"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
            "border_docs":["CMR/Waybill","Vehicle Licence Disc","Driver Licence","PDP","Cross-border permit"],
            "est_wait":"1–2 hrs","dangers":["Van Reenen Pass (steep descent — brake check required)","N3 Mooi River bend","Durban port congestion"],"overnight":"Harrismith or Mooi River"},
        ("Manzini","Maputo"):{"border":"Lomahasha / Namaacha","border_hours":"07:00–22:00",
            "border_docs":["CMR/Waybill","Mozambican transit permit","SADC certificate of origin","Driver Licence","PDP"],
            "est_wait":"2–5 hrs","dangers":["EN4 road quality","Fuel availability in MZ — carry extra","Border fraud risk — use official lanes only"],"overnight":"Maputo (plan to arrive before 17:00)"},
        ("Mbabane","Johannesburg"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
            "border_docs":["CMR/Waybill","Vehicle Licence Disc","Driver Licence","PDP","Cross-border permit"],
            "est_wait":"1–3 hrs","dangers":["Van Reenen Pass","N3 long-vehicle restrictions peak hours"],"overnight":"Standerton"},
    }

    # Extended corridor warnings
    CORRIDOR_WARNINGS = {
        ("Manzini","Johannesburg"): ["N3 Van Reenen — fog and ice Jun–Aug, depart before 07:00",
                                     "Ermelo area — hijacking hotspot, travel in daylight only",
                                     "Oshoek border — closes 22:00, plan arrival by 20:00"],
        ("Manzini","Durban"):       ["Lavumisa border — closes 22:00",
                                     "N2 Empangeni — high accident zone, reduce speed",
                                     "Mariannhill toll — heavy congestion after 15:00 Friday"],
        ("Mbabane","Johannesburg"): ["Oshoek border — peak wait 08:00–11:00",
                                     "Carolina N17 — severe potholes, reduce to 60km/h at night",
                                     "Malagwane Hill descent — engage low gear before descent"],
        ("Mbabane","Durban"):       ["Malagwane Hill — check brakes before descent",
                                     "Lavumisa border — closes 22:00, plan arrival by 20:00",
                                     "N2 Pongola area — livestock on road after dark"],
        ("Manzini","Maputo"):       ["Lomahasha border — closes 20:00",
                                     "Mozambique roads — potholes worsen after rainy season",
                                     "Carry MZN/USD cash — card machines often offline in MZ"],
        ("Manzini","Nelspruit"):    ["Jeppe's Reef border — closes 22:00",
                                     "R40 after border — steep curves, reduce speed significantly"],
        ("Manzini","Beira"):        ["Lomahasha border — closes 20:00, strict document checks",
                                     "EN6 Mozambique — fill up at Chimoio, long stretches without fuel",
                                     "Beira port — congestion Monday morning, arrive before 07:00"],
        ("Manzini","Harare"):       ["Beitbridge border — 4–12hr wait, carry food and water",
                                     "Zimbabwe roads — severe potholes, maximum 50km/h at night",
                                     "USD cash required for Zimbabwe fuel and toll roads"],
        ("Mbabane","Richards Bay"): ["Lavumisa border — closes 22:00",
                                     "N2 coastal — allow minimum 8 hours driving time",
                                     "Empangeni area — avoid parking roadside at night"],
    }
    extra_warnings = []
    _ck1 = (fc_origin, fc_dest)
    _ck2 = (fc_dest, fc_origin)
    for (o, d), warns in CORRIDOR_WARNINGS.items():
        if o in fc_origin or fc_origin in o:
            if d in fc_dest or fc_dest in d:
                extra_warnings = warns
                break
    if not extra_warnings:
        for (o, d), warns in CORRIDOR_WARNINGS.items():
            if o == fc_origin.split()[0] or d == fc_dest.split()[0]:
                extra_warnings = warns[:2]
                break

    if extra_warnings:
        with st.expander("⚠️ Additional Route Warnings", expanded=False):
            for w in extra_warnings:
                st.markdown(
                    f"<div style='background:rgba(78,40,6,.35);border:1px solid #f97316;border-radius:8px;"
                    f"padding:7px 12px;margin-bottom:5px;font-size:.8rem;color:#fde68a;'>⚠️ {w}</div>",
                    unsafe_allow_html=True,
                )

    route_key  = (fc_origin, fc_dest)
    route_key2 = (fc_dest, fc_origin)
    rd = ROUTE_DATA.get(route_key) or ROUTE_DATA.get(route_key2)
    is_cross_border = any(loc in [fc_origin, fc_dest] for loc in ["Johannesburg","Durban","Maputo","Nelspruit"])

    if rd or is_cross_border:
        with st.expander("🗺️ Route Briefing — tap to expand", expanded=False):
            if rd:
                st.markdown(f"""<div style='margin-bottom:.6rem;'>
                <div style='font-size:.62rem;font-weight:800;letter-spacing:.12em;color:#60a5fa;text-transform:uppercase;margin-bottom:8px;'>🛂 Border Information</div>
                <div style='font-size:.82rem;color:#e2e8f0;margin-bottom:4px;'>
                  <b>Post:</b> {rd['border']} &nbsp;·&nbsp; <b>Hours:</b> {rd['border_hours']} &nbsp;·&nbsp; <b>Est. wait:</b> {rd['est_wait']}
                </div>
                <div style='font-size:.75rem;color:#94a3b8;'>Documents required at border: {', '.join(rd['border_docs'])}</div>
                </div>""", unsafe_allow_html=True)
                st.markdown('<div style="font-size:.62rem;font-weight:800;letter-spacing:.12em;color:#f97316;text-transform:uppercase;margin-bottom:6px;">⚠️ Route Hazards</div>', unsafe_allow_html=True)
                for danger in rd["dangers"]:
                    st.markdown(f"<div style='font-size:.79rem;color:#fde68a;margin-bottom:3px;'>• {danger}</div>", unsafe_allow_html=True)
                if rd.get("overnight"):
                    st.markdown(f'<div style="font-size:.79rem;color:#6ee7b7;margin-top:8px;">🛏️ <b>🛏️ Overnight stop if trip &gt;8h:</b> {rd["overnight"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="info-strip">Cross-border route — ensure all transit documents are on board before departure.</div>', unsafe_allow_html=True)

    # ── DSR ───────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="sec">📋 Daily Status Report</div>', unsafe_allow_html=True)
    today_dsr = get_todays_dsr(tid, drv_id) if connected else None
    if today_dsr:
        notes_str = today_dsr[0] or ""
        fit_status = "FIT" if "Fit: True" in notes_str else "UNFIT"
        color = "#34d399" if fit_status=="FIT" else "#f87171"
        st.markdown(f'<div class="ext-banner" style="border-color:{color}40;">'
                    f'<span style="font-size:.72rem;font-weight:800;letter-spacing:.1em;color:{color};">● DSR SUBMITTED TODAY — {fit_status}</span><br>'
                    f'<span style="font-size:.8rem;color:#94a3b8;">{notes_str[:140]}</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-strip">⏰ Submit your Daily Status Report before departing.</div>', unsafe_allow_html=True)
        with st.form("dsr_form", clear_on_submit=True):
            fit = st.radio("Fit to drive today?", ["✅ Yes — I am fit","❌ No — I am not fit"], index=0, horizontal=True)
            is_fit = fit.startswith("✅")
            unfit_reason = ""
            if not is_fit:
                unfit_reason = st.selectbox("Reason", DSR_REASONS_UNFIT)
                st.warning("⚠️ Fleet manager will be notified. Do not drive today.")
            truck_condition = st.radio("Truck condition",
                ["✅ Roadworthy","⚠️ Minor issues — noted below","Unroadworthy"],index=0)
            condition_notes = st.text_area("Condition notes",height=50,placeholder="e.g. Windscreen crack")
            dsr_odo = st.number_input("Starting odometer (km)",min_value=0.0,value=float(cur_odo),step=1.0)
            dsr_date = st.date_input("Date",value=date.today(),key="dsr_date")
            dsr_sub = st.form_submit_button("📋 Submit DSR",type="primary",use_container_width=True)
        if dsr_sub:
            all_notes = f"{truck_condition} | {condition_notes}" if condition_notes.strip() else truck_condition
            dsr_rec={"truck_id":tid,"driver_id":drv_id,"date":dsr_date.strftime("%Y-%m-%d"),
                     "fit":is_fit,"odometer":dsr_odo,
                     "checklist_score":st.session_state.get("checklist_data",{}).get("score",0),
                     "issues":all_notes,"unfit_reason":unfit_reason if not is_fit else ""}
            if connected and save_dsr(dsr_rec):
                st.success("✅ DSR submitted — have a safe trip!" if is_fit else f"UNFIT logged: {unfit_reason}")
                st.session_state["dsr_done"]=True; st.rerun()
            else: st.warning("📶 Could not save DSR — check DB connection.")

    # ── Document Expiry Alerts ───────────────────────────────────────────────
    if connected and tid:
        try:
            _conn2 = get_conn()
            _erow2 = _conn2.execute(
                "SELECT pdp_expiry, roadworthy_expiry, cross_border_permit_expiry "
                "FROM Truck WHERE truck_id=?", (tid,)
            ).fetchone()
            _conn2.close()
            if _erow2:
                _exp_alerts = [
                    ("PDP",                    _erow2[0]),
                    ("Roadworthy Certificate", _erow2[1]),
                    ("Cross-Border Permit",    _erow2[2]),
                ]
                _shown_any = False
                for _ea_label, _ea_val in _exp_alerts:
                    _ea_days = days_until_expiry(_ea_val)
                    if _ea_days is not None and _ea_days <= 30:
                        if not _shown_any:
                            st.divider()
                            st.markdown('<div class="sec">⚠️ Document Expiry Alerts</div>', unsafe_allow_html=True)
                            _shown_any = True
                        _ea_badge, _ea_col = expiry_badge(_ea_days)
                        level = "error" if _ea_days <= 7 else "warning"
                        if level == "error":
                            st.error(f"🚨 {_ea_label}: {_ea_badge} — Do not cross borders until renewed.")
                        else:
                            st.warning(f"⚠️ {_ea_label}: {_ea_badge} — Renew before your next cross-border trip.")
        except Exception:
            pass

    # ── Notification inbox ────────────────────────────────────────────────────
    st.divider()
    notifs = get_notifications(drv_id, tid) if connected else []
    unread_n = sum(1 for n in notifs if not n[5])
    st.markdown(f'<div class="sec">Messages{" · "+str(unread_n)+" unread" if unread_n else ""}</div>', unsafe_allow_html=True)
    if not notifs:
        st.markdown('<div class="info-strip">📭 No messages from fleet manager.</div>', unsafe_allow_html=True)
    else:
        if unread_n and st.button("✅ Mark all read", key="mark_all_now"):
            mark_all_read(drv_id, tid); st.rerun()
        _pc={"Urgent":"#f87171","High":"#f97316","Normal":"#93c5fd","Info":"#6ee7b7"}
        _pb={"Urgent":"rgba(78,6,6,.35)","High":"rgba(78,40,6,.35)","Normal":"rgba(30,58,138,.25)","Info":"rgba(6,78,59,.25)"}
        for notif in notifs:
            nid,ndate,subject,message,priority,read_at=notif
            pc=_pc.get(priority,"#93c5fd"); pb=_pb.get(priority,"rgba(30,58,138,.25)")
            dot="" if read_at else f"<span style='display:inline-block;width:7px;height:7px;background:{pc};border-radius:50%;margin-right:5px;'></span>"
            st.markdown(f"<div style='background:{pb};border:1px solid {pc}30;border-radius:10px;padding:10px 14px;margin-bottom:6px;opacity:{'1' if not read_at else '.6'};'>"
                        f"<div style='display:flex;justify-content:space-between;margin-bottom:3px;'>"
                        f"<span style='font-size:.82rem;font-weight:700;color:#e2e8f0;'>{dot}{subject or '(no subject)'}</span>"
                        f"<span style='font-size:.65rem;color:#64748b;'>{(ndate or '')[:16]} · <span style='color:{pc};font-weight:700;'>{priority}</span></span></div>"
                        f"<div style='font-size:.78rem;color:#cbd5e1;'>{message or ''}</div></div>", unsafe_allow_html=True)
            if not read_at:
                if st.button("Mark read", key=f"rd_{nid}"): mark_notification_read(nid); st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# LOG TAB — Scan, Trip, Fuel, Incident, Sync
# ═══════════════════════════════════════════════════════════════════════════════
with tab_log:
    if not tid:
        st.warning("⚠️ No truck assigned.")
    else:
        # If driver came from "Start Pre-Trip Check" button, show notice
        if st.session_state.pop("_goto_checklist", False):
            st.info("Complete the pre-trip checklist below to unlock the trip form.")

        log_scan, log_trip, log_fuel, log_evt, log_sync = st.tabs([
            "📷 Scan","▣ Trip","◉ Fuel","🚨 Incident","Sync"])

        # ── SCAN ──────────────────────────────────────────────────────────────
        with log_scan:
            st.markdown("### 📷 Scan Documents")
            st.caption("Photograph any document — AI reads and fills the form for you.")
            api_key = st.session_state.get("gemini_key","")
            dtype = st.selectbox("Document Type", DOC_TYPES, key="scan_dtype_sel")
            st.markdown('<div class="scan-box"><div style="font-size:1rem;font-weight:700;color:#34d399;margin-bottom:4px;">📷 Camera · Upload · PDF</div>'
                        '<div style="font-size:.74rem;color:#6ee7b7;">Take a photo or upload from your device</div></div>', unsafe_allow_html=True)
            uploaded = st.file_uploader("Photograph or choose file", type=["jpg","jpeg","png","webp","pdf"],
                                         key="scan_uploader", label_visibility="collapsed")
            if uploaded:
                fbytes=uploaded.read(); mime=uploaded.type or "image/jpeg"
                if mime.startswith("image/"): st.image(fbytes,width=340,caption=uploaded.name)
                else: st.info(f"📄 **{uploaded.name}** ({fmt_size(len(fbytes))})")
                if not api_key:
                    st.warning("⚠️ Add your Gemini API key in the sidebar to enable AI extraction.")
                else:
                    if st.button("🤖 Extract with AI", use_container_width=True, key="scan_extract_btn"):
                        with st.spinner("Reading document..."):
                            ext = extract_with_ai(fbytes, mime, dtype, api_key)
                        if "_error" in ext:
                            st.error(f"AI error: {ext['_error']}")
                        else:
                            st.session_state["scan_extracted"]=ext; st.session_state["scan_doc_type"]=dtype
                            apply_extraction(dtype, ext)
                            icons={"Job Order":"📋","Fuel Receipt":"◉","Weighbridge Ticket":"⚖️","Delivery Note":"📦","Other Document":"📄"}
                            st.markdown(f'<div class="ext-banner">{icons.get(dtype,"📄")} Extracted from {dtype} — form auto-filled ✅</div>',unsafe_allow_html=True)
                            for k,v in list(ext.items())[:10]:
                                if v and not k.startswith("_"):
                                    st.markdown(f"<div style='font-size:.77rem;color:#e2e8f0;'><span style='color:#64748b;'>{k.replace('_',' ').title()}:</span> {v}</div>",unsafe_allow_html=True)
                    if st.button("💾 Save Document", use_container_width=True, key="scan_save_btn"):
                        ext = st.session_state.get("scan_extracted") or {}
                        doc_id = save_doc(tid, drv_id, dtype, uploaded.name, fbytes, mime, ext)
                        if doc_id: st.success(f"✅ Saved as document #{doc_id}")

        # ── TRIP ──────────────────────────────────────────────────────────────
        with log_trip:
            st.markdown("### 🚚 Log Trip")
            st.caption("Complete checklist first — then log your trip.")

            # Pre-trip checklist gate
            checklist_done = st.session_state.get("checklist_done", False)
            if not checklist_done:
                st.markdown('<div class="sec">✅ Pre-Trip Safety Checklist</div>', unsafe_allow_html=True)
                st.markdown('<div class="info-strip">Tick all 8 items to unlock the trip form.</div>', unsafe_allow_html=True)
                checks={}
                for key,icon,label,hint in CHECKLIST_ITEMS:
                    ca,cb=st.columns([5,1])
                    with ca: st.markdown(f"<div style='font-size:.85rem;color:#e2e8f0;padding:4px 0;'>{icon} <b>{label}</b> <span style='color:#64748b;font-size:.75rem;'>— {hint}</span></div>",unsafe_allow_html=True)
                    with cb: checks[key]=st.checkbox("OK",key=f"chk_{key}",label_visibility="collapsed")
                passed=sum(checks.values())
                st.markdown(f"<div style='margin:.5rem 0;font-size:.82rem;color:{'#34d399' if passed==8 else '#f59e0b'};font-weight:700;'>{'✅ All checks passed — ready to depart.' if passed==8 else f'⚠️ {passed}/8 confirmed.'}</div>",unsafe_allow_html=True)
                issues_text=st.text_area("Note any faults (optional)",placeholder="e.g. Minor oil seep noted",height=55,key="chk_issues")
                if st.button("✅ Confirm Checklist & Unlock Trip Form", use_container_width=True, disabled=(passed<8)):
                    st.session_state["checklist_done"] = True
                    st.session_state["checklist_data"] = {"score": passed, "issues": issues_text, "items": checks}
                    # Save to DB
                    try:
                        _ptc_odo = float(cur_odo)
                        save_pretripcheck(tid, drv_id, [k for k,v in checks.items() if v], _ptc_odo, issues_text)
                    except Exception:
                        pass
                    st.rerun()
            else:
                chk_data=st.session_state.get("checklist_data",{})
                st.markdown(f'<div class="pf-banner">✅ <b>Checklist passed</b> — {chk_data.get("score",8)}/8 items · '
                            f'{"No issues" if not chk_data.get("issues") else chk_data["issues"][:50]}</div>',unsafe_allow_html=True)
                if st.button("↩ Redo Checklist",key="redo_chk"): st.session_state["checklist_done"]=False; st.rerun()

                pf=st.session_state.get("pf_trip",{})
                last_fuel=get_last_fuel(tid)
                avg_eff=get_avg_eff(tid)
                auto_odo=float(last_fuel[1]) if last_fuel else cur_odo
                auto_fuel=float(last_fuel[0]) if last_fuel else 0.0
                if pf: st.markdown('<div class="pf-banner">📋 <b>Pre-filled from scanned document</b></div>',unsafe_allow_html=True)

                # ── GPS Route Search (outside form — buttons not allowed in st.form) ────
                st.markdown('<div class="sec">📍 Route</div>', unsafe_allow_html=True)
                _tr1, _tr2 = st.columns(2)
                with _tr1:
                    origin = st.text_input("From",
                        value=st.session_state.get("_tl_origin", pf.get("origin", "")),
                        placeholder="e.g. Manzini CBD, Eswatini",
                        key="tl_origin_gps")
                    st.session_state["_tl_origin"] = origin
                with _tr2:
                    destination = st.text_input("To",
                        value=st.session_state.get("_tl_dest", pf.get("destination", "")),
                        placeholder="e.g. Durban Boxer Superstore, KZN",
                        key="tl_dest_gps")
                    st.session_state["_tl_dest"] = destination

                _tl_gps_key = f"_tl_gps_{origin}_{destination}"
                _tl_gps = st.session_state.get(_tl_gps_key, {})
                _tg1, _tg2 = st.columns([1, 3])
                with _tg1:
                    if st.button("📍 Road Distance", key="tl_gps_btn", use_container_width=True,
                                 disabled=not (origin.strip() and destination.strip())):
                        with st.spinner("Calculating..."):
                            try:
                                from services.gps_routing import get_road_distance
                                _ors = st.session_state.get("ors_api_key", "")
                                _tl_gps = get_road_distance(origin, destination, _ors)
                                st.session_state[_tl_gps_key] = _tl_gps
                            except Exception as _ge:
                                _tl_gps = {"error": str(_ge)}
                                st.session_state[_tl_gps_key] = _tl_gps
                with _tg2:
                    if _tl_gps and "error" not in _tl_gps:
                        st.success(f"📍 **{_tl_gps['distance_km']:.0f} km** · Est. **{_tl_gps['duration_hrs']:.1f} hrs** HGV · *{_tl_gps['source']}*")
                    elif _tl_gps and "error" in _tl_gps:
                        st.warning(f"⚠️ {_tl_gps['error']}")

                if _tl_gps and "distance_km" in _tl_gps:
                    auto_d = _tl_gps["distance_km"]
                else:
                    auto_d = est_dist(origin, destination)
                auto_t = det_terrain(origin, destination)

                with st.form("trip_v6", clear_on_submit=True):
                    st.markdown(f'<div class="info-strip"><b>{auto_d:.0f} km</b> · <b>{auto_t}</b> · ◉ Est. <b>~{auto_d*FUEL_BASE_L_PER_100/100:.0f} L</b>'
                                +(f' · Your avg <b>{avg_eff:.2f} km/L</b>' if avg_eff else '')+'</div>', unsafe_allow_html=True)

                    st.markdown('<div class="sec">🔢 Odometer & Fuel</div>',unsafe_allow_html=True)
                    o1,o2=st.columns(2)
                    with o1:
                        odometer=st.number_input("Odometer at Trip End (km)",min_value=0.0,
                            value=float(pf.get("odometer",auto_odo if auto_odo>0 else cur_odo)),step=1.0)
                    with o2:
                        fuel_cons=st.number_input("Fuel Used (L)",min_value=0.0,
                            value=float(pf.get("fuel_consumed",auto_fuel)),step=5.0)
                    odo_photo=st.file_uploader("📷 Odometer photo (optional)",type=["jpg","jpeg","png","webp"],key="odo_photo_upload")

                    st.markdown('<div class="sec">⏱️ Timing</div>',unsafe_allow_html=True)
                    tc1,tc2,tc3=st.columns(3)
                    with tc1: trip_date=st.date_input("Date",value=date.today())
                    with tc2: depart_time=st.time_input("Departure",value=datetime.now().replace(hour=6,minute=0,second=0,microsecond=0).time(),step=300)
                    with tc3: arrive_time=st.time_input("Arrival",value=datetime.now().replace(second=0,microsecond=0).time(),step=300)
                    _depart_dt=datetime.combine(trip_date,depart_time)
                    _arrive_dt=datetime.combine(trip_date,arrive_time)
                    _dur_h=max(0.0,round((_arrive_dt-_depart_dt).total_seconds()/3600,2))
                    if _dur_h>0:
                        st.markdown(f'<div class="info-strip">⏱️ <b>{int(_dur_h)}h {int((_dur_h%1)*60)}m</b>'
                                    +(f' · Avg <b>{auto_d/_dur_h:.0f} km/h</b>' if auto_d>0 else '')+'</div>',unsafe_allow_html=True)

                    st.markdown('<div class="sec">📦 Cargo & Delivery</div>',unsafe_allow_html=True)
                    c5,c6,c7=st.columns(3)
                    with c5: load_kg=st.number_input("Load (kg)",min_value=0.0,value=float(pf.get("load_kg") or 0),step=100.0)
                    with c6: borders=st.number_input("Border crossings",min_value=0,value=int(pf.get("border",0)),step=1)
                    with c7: on_time=st.selectbox("Delivered?",["Yes","No","Partial"],index=0)

                    # Voice input for notes
                    st.markdown('<div class="sec">📝 Notes</div>',unsafe_allow_html=True)
                    voice_html="""
                    <div style="margin-bottom:6px;">
                    <button id="voice-btn" onclick="startVoice()" style="background:rgba(30,58,138,.7);color:#93c5fd;border:1px solid rgba(96,165,250,.4);
                      border-radius:8px;padding:6px 14px;font-size:.78rem;font-weight:700;cursor:pointer;">Tap to speak</button>
                    <span id="voice-status" style="font-size:.72rem;color:#64748b;margin-left:8px;"></span>
                    </div>
                    <script>
                    var recog=null;
                    function startVoice(){
                      if(!('webkitSpeechRecognition' in window||'SpeechRecognition' in window)){
                        document.getElementById('voice-status').innerText='❌ Not supported on this browser';return;}
                      var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
                      recog=new SR(); recog.lang='en-ZA'; recog.interimResults=false;
                      document.getElementById('voice-status').innerText='Listening...';
                      document.getElementById('voice-btn').innerText='⏹ Stop';
                      recog.onresult=function(e){
                        var txt=e.results[0][0].transcript;
                        document.getElementById('voice-status').innerText='✅ '+txt;
                        // Try to find the textarea in the parent frame and append
                        try{var ta=window.parent.document.querySelector('textarea[data-testid]');
                          if(ta){ta.value+=(ta.value?' ':'')+txt;ta.dispatchEvent(new Event('input',{bubbles:true}));}}catch(e){}
                      };
                      recog.onerror=function(e){document.getElementById('voice-status').innerText='❌ '+e.error;};
                      recog.onend=function(){document.getElementById('voice-btn').innerText='Tap to speak';};
                      recog.start();
                    }
                    </script>
                    """
                    st.components.v1.html(voice_html, height=52)
                    trip_notes=st.text_area("Trip notes",placeholder="Any notes about this trip...",height=60,key="trip_notes_txt")

                    # Border crossing details
                    BORDER_POINTS=["Oshoek / Ngwenya (SZ↔ZA)","Lomahasha / Namaacha (SZ↔MZ)",
                                   "Lavumisa / Golela (SZ↔ZA)","Mahamba (SZ↔ZA)",
                                   "Matsamo / Jeppe's Reef (SZ↔ZA)","Lebombo / Ressano Garcia (ZA↔MZ)","Other"]
                    border_logs=[]
                    if borders>0:
                        st.markdown('<div class="sec">🛂 Border Crossing Details</div>',unsafe_allow_html=True)
                        for b_idx in range(int(borders)):
                            st.markdown(f"<div style='font-size:.75rem;color:#93c5fd;font-weight:700;margin:.3rem 0 .2rem;'>Crossing {b_idx+1}</div>",unsafe_allow_html=True)
                            bb1,bb2,bb3=st.columns(3)
                            with bb1: bp=st.selectbox("Border post",BORDER_POINTS,key=f"bp_{b_idx}")
                            with bb2: bw=st.number_input("Wait (hrs)",min_value=0.0,max_value=24.0,value=0.5,step=0.25,key=f"bw_{b_idx}")
                            with bb3: bi=st.selectbox("Issue?",["None","Documents queried","Overweight","Cargo inspection","Long queue","Other"],key=f"bi_{b_idx}")
                            border_logs.append({"post":bp,"wait_h":bw,"issue":bi})
                        st.markdown(f'<div class="info-strip">🛂 Total border wait: <b>{sum(b["wait_h"] for b in border_logs):.1f} hrs</b></div>',unsafe_allow_html=True)

                    # Cargo condition
                    st.markdown('<div class="sec">📦 Cargo Condition at Delivery</div>',unsafe_allow_html=True)
                    cargo_condition=st.selectbox("Condition on arrival",
                        ["✅ Intact — no issues","⚠️ Minor damage","Significant damage","📦 Partial delivery"],index=0,key="cargo_cond")
                    cargo_ok=cargo_condition.startswith("✅")
                    cargo_photo=None; cargo_notes=""
                    if not cargo_ok:
                        cn1,cn2=st.columns([3,2])
                        with cn1: cargo_notes=st.text_area("Damage description",height=60,placeholder="Describe damage or shortage")
                        with cn2: cargo_photo=st.file_uploader("📷 Damage photo",type=["jpg","jpeg","png","webp"],key="cargo_photo_upload")
                        st.markdown(f"<div style='font-size:.78rem;color:#fbbf24;'>Fleet manager will be notified.</div>",unsafe_allow_html=True)

                    job_ref=st.text_input("Job Reference (optional)",value=pf.get("job_ref",""),placeholder="e.g. CONCO-2026-0416-01")
                    sub=st.form_submit_button("✅ Log Trip",type="primary",use_container_width=True)

                if sub:
                    if odometer<=0 and fuel_cons<=0:
                        st.error("Enter at least the odometer reading or fuel used.")
                    else:
                        odo_dist=max(0.0,odometer-cur_odo)
                        dist=max(auto_d,odo_dist)
                        eff=dist/fuel_cons if (dist>0 and fuel_cons>0) else 0
                        drv_exp=int(sel_row[9] or 5) if sel_row else 5
                        deviation_pct=((odo_dist-auto_d)/auto_d*100) if (auto_d>0 and odo_dist>0) else 0
                        if deviation_pct>20 and odo_dist>0:
                            st.warning(f"⚠️ Route deviation — odometer suggests {odo_dist:.0f} km vs expected {auto_d:.0f} km ({deviation_pct:+.0f}%).")
                        border_note=""
                        if border_logs:
                            border_note=" | Borders: "+"; ".join(
                                f"{b['post']} wait {b['wait_h']}h{' ['+b['issue']+']' if b['issue']!='None' else ''}"
                                for b in border_logs)
                        rec={"truck_id":tid,"origin":origin,"destination":destination,"distance":dist,
                             "load_kg":load_kg,"date":trip_date.strftime("%Y-%m-%d"),"fuel_consumed":fuel_cons,
                             "fuel_efficiency":eff,"duration_h":_dur_h,"border_crossings":borders,"terrain":auto_t,
                             "odometer":odometer,"on_time":on_time=="Yes","driver_exp":drv_exp,
                             "deviation_pct":round(deviation_pct,1),"border_note":border_note}
                        if connected and save_trip(rec):
                            dur_str=f" · ⏱️ {int(_dur_h)}h {int((_dur_h%1)*60)}m" if _dur_h>0 else ""
                            st.success(f"✅ Trip saved — **{origin} → {destination}** · {dist:.0f} km{dur_str}"+(f" · {eff:.2f} km/L" if eff>0 else ""))
                            if eff>0 and avg_eff:
                                d_pct=(eff-avg_eff)/avg_eff*100
                                col="#34d399" if d_pct>=0 else "#f87171"; arr="↑" if d_pct>=0 else "↓"
                                st.markdown(f"<div style='font-size:.82rem;color:{col};'>Efficiency {arr} {abs(d_pct):.0f}% vs your average</div>",unsafe_allow_html=True)
                            # Save odometer photo
                            if odo_photo:
                                try:
                                    _ob=odo_photo.read(); _om=odo_photo.type or "image/jpeg"
                                    save_doc(tid,drv_id,"Other Document",
                                        f"odo_{trip_date.strftime('%Y%m%d')}.{odo_photo.name.split('.')[-1]}",
                                        _ob,_om,{"type":"odometer_photo","km":odometer},notes=f"Odo {odometer:.0f}km — {origin}→{destination}")
                                    st.toast("📷 Odometer photo saved",icon="✅")
                                except: pass
                            # Save cargo damage photo
                            if not cargo_ok and cargo_photo:
                                try:
                                    _cb=cargo_photo.read(); _cm=cargo_photo.type or "image/jpeg"
                                    save_doc(tid,drv_id,"Other Document",
                                        f"cargo_dmg_{trip_date.strftime('%Y%m%d')}.{cargo_photo.name.split('.')[-1]}",
                                        _cb,_cm,{"type":"cargo_damage","condition":cargo_condition,"notes":cargo_notes},
                                        notes=f"Cargo: {cargo_condition} | {cargo_notes[:60]}")
                                    st.toast("📷 Damage photo saved",icon="⚠️")
                                except: pass
                            if not cargo_ok:
                                st.warning(f"⚠️ Cargo issue logged: {cargo_condition}")
                            # WhatsApp share
                            eff_str=f"{eff:.2f} km/L" if eff>0 else "—"
                            wa_text=(f"✅ KSM Trip Complete%0A"
                                     f"Driver: {drv_id}%0A"
                                     f"Route: {origin} → {destination} ({dist:.0f}km)%0A"
                                     f"Delivered: {'✅ On time' if on_time=='Yes' else '⚠️ '+on_time}%0A"
                                     f"{'Load: '+str(int(load_kg))+'kg%0A' if load_kg else ''}"
                                     f"Fuel: {fuel_cons:.0f}L · {eff_str}%0A"
                                     f"Odometer: {odometer:,.0f}km%0A"
                                     f"{'Cargo: '+cargo_condition[:30]+'%0A' if not cargo_ok else ''}"
                                     f"Ref: {job_ref or '—'}")
                            st.markdown(f'<a href="https://wa.me/?text={wa_text}" target="_blank" style="display:block;background:linear-gradient(135deg,#065f46,#059669);color:white;text-align:center;padding:10px;border-radius:10px;font-weight:700;font-size:.85rem;text-decoration:none;margin-top:8px;">Share via WhatsApp</a>', unsafe_allow_html=True)
                            # Show route map for completed trip
                            if origin and destination:
                                try:
                                    from maps.route_map import render_route_map
                                    st.markdown("**Trip Route**")
                                    render_route_map(
                                        origin=origin,
                                        destination=destination,
                                        distance_km=dist,
                                        duration_hrs=_dur_h,
                                        risk_score=15,
                                    )
                                except Exception:
                                    pass
                            st.session_state["pf_trip"] = {}
                        else:
                            enqueue(rec, "trip"); st.warning("📶 Offline — trip queued.")
                        st.rerun()

        # ── FUEL ──────────────────────────────────────────────────────────────
        with log_fuel:
            st.markdown("### ◉ Log Fuel Fill-Up")
            st.caption("Scan your receipt in 📷 Scan — values auto-fill here.")
            pff=st.session_state.get("pf_fuel",{})
            last_fill=get_last_fuel(tid)
            if pff: st.markdown('<div class="pf-banner">◉ <b>Pre-filled from scanned receipt</b> — review and save</div>',unsafe_allow_html=True)
            if last_fill:
                ks=cur_odo-float(last_fill[1])
                st.markdown(f'<div class="info-strip">Last fill: <b>{last_fill[2]}</b> · <b>{last_fill[0]:.0f} L</b> · <b>{ks:,.0f} km</b> since</div>',unsafe_allow_html=True)
            with st.form("fuel_v6",clear_on_submit=True):
                st.markdown('<div class="sec">🏢 Station</div>',unsafe_allow_html=True)
                pf_st=pff.get("station","")
                st_idx=next((i for i,s in enumerate(KNOWN_STATIONS) if pf_st.lower() in s.lower()),len(KNOWN_STATIONS)-1) if pf_st else 0
                st_choice=st.selectbox("Station",KNOWN_STATIONS,index=st_idx)
                station_name=st.text_input("Enter Station Name",value=pf_st) if st_choice=="Other / Enter manually" else st_choice
                rec_no=st.text_input("Receipt Number",value=pff.get("receipt_no",""),placeholder="e.g. 998877665")
                st.markdown('<div class="sec">⛽ Fuel Details</div>',unsafe_allow_html=True)
                f1,f2,f3=st.columns(3)
                with f1: fa=st.number_input("Litres Added",min_value=1.0,max_value=float(tank_cap+50),value=float(pff.get("fuel_added") or 150.0),step=5.0)
                with f2: cpl=st.number_input("Price/Litre (E)",min_value=5.0,value=float(pff.get("cost_per_L") or FUEL_PRICE_DEFAULT),step=0.05)
                with f3: ft=st.selectbox("Product",["Diesel 50PPM","Diesel 500PPM","Petrol 93","Petrol 95","Diesel (Generic)"],index=0)
                tc2=fa*cpl; fp=min(100,fa/tank_cap*100)
                p1,p2,p3=st.columns(3)
                p1.metric("Total Cost",f"E {tc2:,.2f}"); p2.metric("Tank Fill",f"{fp:.0f}%"); p3.metric("Est. Range",f"~{fa/(FUEL_BASE_L_PER_100/100):.0f} km")
                st.markdown('<div class="sec">Odometer</div>',unsafe_allow_html=True)
                odo_f=st.number_input("Odometer at Fill-Up",min_value=0.0,value=float(pff.get("odometer") or cur_odo),step=1.0)
                full_t=st.checkbox("Filled to full tank",value=True)
                fd=st.date_input("Date",value=date.today(),key="fuel_date")
                fs=st.form_submit_button("◉ Save Fill-Up",type="primary",use_container_width=True)
            if fs:
                frec={"truck_id":tid,"date":fd.strftime("%Y-%m-%d"),"fuel_added":fa,"odometer":odo_f,
                     "cost_per_liter":cpl,"station":station_name,"fuel_type":ft,"full_tank":full_t,
                     "notes":f"Receipt: {rec_no}" if rec_no else ""}
                if connected and save_fuel(frec):
                    st.success(f"✅ Fill-up saved — **{fa:.0f} L** @ E{cpl:.2f}/L = **E {tc2:,.2f}**")
                    if last_fill and full_t:
                        km2=odo_f-float(last_fill[1])
                        if km2>0 and fa>0:
                            ef2=km2/fa; col="#34d399" if ef2>=3.0 else "#fbbf24"
                            st.markdown(f"<div style='color:{col};font-size:.84rem;'>Tank-to-tank: <b>{ef2:.2f} km/L</b> over {km2:,.0f} km · E {tc2/km2:.2f}/km</div>",unsafe_allow_html=True)
                    st.session_state["pf_fuel"]={}
                else: enqueue(frec,"fuel"); st.warning("📶 Queued offline.")
                st.rerun()

        # ── INCIDENT ──────────────────────────────────────────────────────────
        with log_evt:
            st.markdown("### 🚨 Report Incident")
            st.caption("Fleet manager notified immediately for High / Critical events.")
            with st.form("evt_v6",clear_on_submit=True):
                e1,e2=st.columns(2)
                with e1: etype=st.selectbox("Event Type",EVENT_TYPES)
                with e2: sev=st.selectbox("Severity",["Low","Medium","High","Critical"])
                sc={"Low":"#60a5fa","Medium":"#fbbf24","High":"#f97316","Critical":"#f87171"}.get(sev,"#60a5fa")
                si={"Low":"ℹ️","Medium":"⚠️","High":"🔶","Critical":"🚨"}.get(sev,"ℹ️")
                st.markdown(f'<div style="background:rgba(15,23,42,.5);border:1px solid {sc}40;border-radius:8px;padding:6px 12px;font-size:.76rem;color:{sc};">'
                            f'{si} <b>{sev}</b> — {"Fleet manager alerted immediately." if sev in ("High","Critical") else "Logged for fleet manager."}</div>',unsafe_allow_html=True)
                eloc=st.text_input("Location",placeholder="e.g. N2 near Oshoek border")

                # Voice input for incident description
                st.components.v1.html("""
                <button onclick="startIncVoice()" style="background:rgba(30,58,138,.7);color:#93c5fd;border:1px solid rgba(96,165,250,.4);
                  border-radius:8px;padding:5px 12px;font-size:.76rem;font-weight:700;cursor:pointer;margin-bottom:4px;">
                  Speak incident description</button>
                <span id="inc-v-status" style="font-size:.7rem;color:#64748b;margin-left:6px;"></span>
                <script>
                function startIncVoice(){
                  if(!('webkitSpeechRecognition' in window||'SpeechRecognition' in window)){
                    document.getElementById('inc-v-status').innerText='❌ Not supported';return;}
                  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
                  var r=new SR(); r.lang='en-ZA'; r.interimResults=false;
                  document.getElementById('inc-v-status').innerText='Listening...';
                  r.onresult=function(e){
                    var t=e.results[0][0].transcript;
                    document.getElementById('inc-v-status').innerText='✅ '+t;
                    try{var ta=window.parent.document.querySelectorAll('textarea')[0];
                      if(ta){ta.value+=(ta.value?' ':'')+t;ta.dispatchEvent(new Event('input',{bubbles:true}));}}catch(e){}
                  };
                  r.onerror=function(e){document.getElementById('inc-v-status').innerText='❌ '+e.error;};
                  r.start();
                }
                </script>""", height=46)
                edesc=st.text_area("What happened?",placeholder="Describe event, action taken, current status.",height=80)
                edate=st.date_input("Date",value=date.today(),key="evt_date")
                esub=st.form_submit_button("🚨 Submit Report",type="primary",use_container_width=True)
            # Incident photo — outside form (buttons not allowed in forms)
            st.markdown("**📷 Attach Photo (optional)**")
            incident_photo = st.file_uploader(
                "Photograph damage, accident scene or police notice",
                type=["jpg","jpeg","png","webp"],
                key="incident_photo_upload",
                label_visibility="collapsed",
                help="On mobile: tap Camera to take a photo directly"
            )
            if incident_photo:
                st.image(incident_photo, caption="Incident photo attached", width=300)

            if esub:
                if not edesc.strip(): st.error("Please describe what happened.")
                else:
                    erec={"truck_id":tid,"date":edate.strftime("%Y-%m-%d"),"event_type":etype,"severity":sev,
                          "location":eloc,"description":edesc,"odometer":cur_odo}
                    if connected and save_event(erec):
                        st.success("✅ Incident reported.")
                        # Save incident photo if attached
                        _inc_p = st.session_state.get("incident_photo_upload")
                        if _inc_p and connected:
                            try:
                                _ib = _inc_p.read()
                                save_doc(tid, drv_id, "Other Document", _inc_p.name, _ib,
                                         _inc_p.type, {"event_type": etype, "severity": sev, "location": eloc},
                                         f"Incident photo — {etype}")
                                st.toast("📷 Incident photo saved", icon="✅")
                            except Exception:
                                pass
                        if sev in ("High","Critical"):
                            st.error(f"🚨 {sev.upper()} incident recorded. Fleet manager has been notified.")
                    else:
                        enqueue(erec,"event"); st.warning("📶 Queued offline.")

        # ── SYNC ──────────────────────────────────────────────────────────────
        with log_sync:
            st.markdown("### Sync & Status")
            tp=qcount("trip")+qcount("fuel")+qcount("event")
            s1,s2,s3,s4=st.columns(4)
            s1.metric("DB","● Live" if connected else "● Offline")
            s2.metric("Trips",qcount("trip")); s3.metric("Fuel",qcount("fuel")); s4.metric("Events",qcount("event"))
            if tp==0: st.success("✅ All records synced.")
            elif not connected: st.error("⚠️ Database not reachable.")
            else:
                if st.button("🔄 Sync Now",use_container_width=True):
                    r=sync_all(); synced=r["trips"]+r["fuel"]+r["events"]
                    if synced: st.success(f"✅ Synced: {r['trips']} trips · {r['fuel']} fuel · {r['events']} events")
                    if r["failed"]: st.warning(f"⚠️ {r['failed']} failed.")
                    elif synced: st.balloons()
            if tp:
                st.markdown("---")
                for rec in st.session_state.get("offline_trip",[]):
                    st.markdown(f'<div class="queue-item"><b style="color:#fbbf24;">TRIP</b> {rec.get("origin","?")} → {rec.get("destination","?")} · {rec.get("date","")}</div>',unsafe_allow_html=True)
                for rec in st.session_state.get("offline_fuel",[]):
                    st.markdown(f'<div class="queue-item"><b style="color:#fbbf24;">FUEL</b> {rec.get("fuel_added",0):.0f}L @ {rec.get("station","?")} · {rec.get("date","")}</div>',unsafe_allow_html=True)
                for rec in st.session_state.get("offline_event",[]):
                    st.markdown(f'<div class="queue-item"><b style="color:#fbbf24;">EVENT</b> {rec.get("event_type","?")} · {rec.get("severity","")} · {rec.get("date","")}</div>',unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# ME TAB — Performance, Jobs, Docs, Profile
# ═══════════════════════════════════════════════════════════════════════════════
with tab_me:
    me_perf, me_jobs, me_docs, me_prof = st.tabs(["📊 Performance", "🗺️ My Jobs", "📁 Documents", "👤 Profile"])

    # ── PERFORMANCE ───────────────────────────────────────────────────────────
    with me_perf:
        st.markdown("### 📊 Driver Performance")
        st.caption(f"Month to date — {date.today().strftime('%B %Y')}")
        if not tid: st.info("No truck assigned.")
        elif not connected: st.warning("⚠️ Database not reachable.")
        else:
            ps = get_perf_stats(tid, drv_id)
            if not ps: st.info("No trip data yet.")
            else:
                # Month metrics
                p1,p2,p3,p4 = st.columns(4)
                p1.metric("Trips This Month", ps["trips_month"])
                p2.metric("📏 Distance", f"{ps['dist_month']:,.0f} km")
                ontime_pct = round(ps["ontime_month"]/ps["total_month"]*100) if ps["total_month"] else 0
                p3.metric("On-Time Rate", f"{ontime_pct}%",
                           delta=f"{ontime_pct-90:.0f}% vs 90% target" if ps["total_month"]>2 else None,
                           delta_color="normal" if ontime_pct>=90 else "inverse")
                p4.metric("Incidents", ps["incidents_month"],
                           delta="this month",delta_color="inverse" if ps["incidents_month"]>0 else "off")

                st.markdown('<div class="sec">⛽ Fuel Efficiency</div>',unsafe_allow_html=True)
                eff_m = ps["eff_month"]; eff_a = ps["eff_all"]; fleet_a = ps["fleet_avg_eff"]
                fe1,fe2,fe3 = st.columns(3)
                fe1.metric("This Month", f"{eff_m:.2f} km/L" if eff_m else "—")
                fe2.metric("All-Time Avg", f"{eff_a:.2f} km/L" if eff_a else "—")
                fe3.metric("Fleet Average", f"{fleet_a:.2f} km/L" if fleet_a else "—",
                            delta=f"{((eff_m-fleet_a)/fleet_a*100):+.0f}% vs fleet" if (eff_m and fleet_a) else None,
                            delta_color="normal" if eff_m>=fleet_a else "inverse")

                # Efficiency bar vs fleet
                if eff_m and fleet_a:
                    ratio = min(eff_m/fleet_a, 2.0)
                    bar_w = min(int(ratio*50), 100)
                    bar_col = "#34d399" if ratio>=1 else "#f87171"
                    st.markdown(f"<div style='margin:.6rem 0;'>"
                                f"<div style='font-size:.68rem;color:#64748b;margin-bottom:4px;'>Your efficiency vs fleet average</div>"
                                f"<div style='background:rgba(15,23,42,.5);border-radius:20px;height:10px;overflow:hidden;'>"
                                f"<div style='width:{bar_w}%;background:{bar_col};height:100%;border-radius:20px;transition:width .5s;'></div></div>"
                                f"<div style='font-size:.7rem;color:{bar_col};margin-top:3px;font-weight:700;'>"
                                f"{'Above' if ratio>=1 else 'Below'} fleet average by {abs(eff_m-fleet_a):.2f} km/L</div></div>",
                                unsafe_allow_html=True)

                st.markdown('<div class="sec">📊 All-Time Summary</div>',unsafe_allow_html=True)
                at1,at2 = st.columns(2)
                at1.metric("Total Trips", ps["trips_all"])
                at2.metric("Total Distance", f"{ps['dist_all']:,.0f} km")

    # ── MY JOBS ───────────────────────────────────────────────────────────────
    with me_jobs:
        st.markdown("### 🗺️ Trip History")
        st.caption("All trips logged for this truck.")
        if not tid: st.info("No truck assigned.")
        elif not connected: st.warning("⚠️ Database not reachable.")
        else:
            avg_eff=get_avg_eff(tid); jobs=get_driver_jobs(tid)
            if jobs:
                m1,m2,m3,m4=st.columns(4)
                m1.metric("Total",len(jobs))
                m2.metric("📏 Distance",f"{sum(r[4] or 0 for r in jobs):,.0f} km")
                effs=[r[7] for r in jobs if r[7] and r[7]>0]
                m3.metric("Avg Eff",f"{sum(effs)/len(effs):.2f} km/L" if effs else "—")
                m4.metric("10-Trip Avg",f"{avg_eff:.2f} km/L" if avg_eff else "—")
                st.markdown("")
            if not jobs: st.info("No jobs logged yet.")
            else:
                for row in jobs:
                    (trip_id,tdate,orig,dest,dist,load,fuel,eff,dur,bords,ontime,terrain,weather)=row
                    ec,arr="#94a3b8",""
                    if eff and avg_eff:
                        dd=(eff-avg_eff)/avg_eff
                        ec="#34d399" if dd>=.05 else ("#f87171" if dd<-.15 else "#fbbf24")
                        arr="↑" if dd>=.05 else ("↓" if dd<-.10 else "→")
                    otb="✅" if ontime==1 else ("⚠️" if ontime==0 else "")
                    st.markdown(f"""<div class="job-card">
                        <div class="job-route">{orig} → {dest}<span style="float:right;font-size:.71rem;color:#64748b;">{tdate} #{trip_id}</span></div>
                        <div class="job-meta">
                            {'<span>'+f"{dist:.0f} km"+'</span>' if dist else ''}
                            {'<span>◉ '+f"{fuel:.0f} L"+'</span>' if fuel else ''}
                            {'<span style="color:'+ec+';font-weight:700;">'+arr+' '+f"{eff:.2f} km/L"+'</span>' if eff else ''}
                            {'<span>📦 '+f"{load:,.0f} kg"+'</span>' if load else ''}
                            {'<span>🛂 '+str(bords)+' border(s)</span>' if bords else ''}
                            {'<span>'+otb+' On time</span>' if otb else ''}
                        </div></div>""",unsafe_allow_html=True)

    # ── MY DOCS ───────────────────────────────────────────────────────────────
    with me_docs:
        st.markdown("### 📁 My Documents")
        if not connected: st.warning("⚠️ Database not reachable.")
        else:
            docs=get_driver_docs(tid or 0,drv_id)
            if not docs: st.info("No documents yet. Use 📷 Scan to save documents.")
            else:
                dtypes={}
                for d in docs: dtypes[d[2]]=dtypes.get(d[2],0)+1
                st.markdown("<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:1rem;'>"
                            +"".join(f"<div style='background:rgba(30,58,138,.4);border:1px solid rgba(96,165,250,.25);border-radius:20px;padding:3px 12px;font-size:.73rem;color:#93c5fd;'>{t}: {n}</div>" for t,n in dtypes.items())
                            +"</div>",unsafe_allow_html=True)
                icons={"Job Order":"📋","Fuel Receipt":"◉","Weighbridge Ticket":"⚖️","Delivery Note":"📦","Other Document":"📄"}
                for doc in docs:
                    doc_id,udate,dtype,fname,fsize,ext_str,linked,notes=doc
                    icon=icons.get(dtype,"📄")
                    with st.expander(f"{icon} **{dtype}** — {fname or 'document'} · {udate[:16] if udate else ''}"):
                        ci,ce=st.columns([3,2])
                        with ci:
                            st.markdown(f'<div class="doc-card"><b>Type:</b> {dtype}<br><b>Saved:</b> {udate}'
                                        +(f'<br><b>Size:</b> {fmt_size(fsize)}' if fsize else '')
                                        +(f'<br><b>Notes:</b> {notes}' if notes else '')+'</div>',unsafe_allow_html=True)
                        with ce:
                            if ext_str and ext_str!="{}":
                                try:
                                    ext=json.loads(ext_str)
                                    if ext and "_error" not in ext:
                                        for k,v in list(ext.items())[:8]:
                                            if v and not k.startswith("_"):
                                                st.markdown(f"<div style='font-size:.75rem;color:#e2e8f0;'><span style='color:#64748b;'>{k.replace('_',' ').title()}:</span> {v}</div>",unsafe_allow_html=True)
                                except: pass

    # ── PROFILE ───────────────────────────────────────────────────────────────
    with me_prof:
        st.markdown("### 👤 My Profile")
        if not tid or not sel_row: st.info("No truck assigned.")
        else:
            (t_id,t_reg,t_driver,t_mile,t_tank,t_did,t_lic,t_phone,t_idn,t_exp,t_routes,t_certs,t_stat,t_model,t_pdp_exp,t_rbw_exp,t_cbp_exp,t_last_svc,t_svc_int)=sel_row
            st.markdown(f"""<div class="id-card" style="margin-bottom:1.2rem;">
            <div style="font-size:.62rem;font-weight:800;letter-spacing:.14em;color:#34d399;text-transform:uppercase;margin-bottom:12px;border-bottom:1px solid rgba(52,211,153,.2);padding-bottom:8px;">🪪 Official Driver ID — KSM Smart Freight Solutions</div>
            <div class="prof-grid">
                <div><div class="prof-label">Full Name</div><div style="font-size:1rem;font-weight:700;color:#fff;">{t_driver or "—"}</div></div>
                <div><div class="prof-label">Driver ID</div><div style="color:#6ee7b7;font-family:monospace;font-size:1rem;font-weight:700;">{t_did or "—"}</div></div>
                <div><div class="prof-label">Truck</div><div style="color:#93c5fd;">{t_reg} — {t_model or ""}</div></div>
                <div><div class="prof-label">Status</div><div style="color:#34d399;font-weight:700;">{t_stat or "ACTIVE"}</div></div>
                <div><div class="prof-label">License</div><div style="color:#e2e8f0;">{t_lic or "—"}</div></div>
                <div><div class="prof-label">ID / Passport</div><div style="color:#e2e8f0;">{t_idn or "—"}</div></div>
                <div><div class="prof-label">Phone</div><div style="color:#e2e8f0;">{t_phone or "—"}</div></div>
                <div><div class="prof-label">Experience</div><div style="color:#e2e8f0;">{t_exp or 0} years</div></div>
                <div><div class="prof-label">Routes</div><div style="color:#e2e8f0;">{t_routes or "All routes"}</div></div>
                <div><div class="prof-label">Certifications</div><div style="color:#e2e8f0;">{t_certs or "Standard"}</div></div>
            </div></div>""",unsafe_allow_html=True)
            # ── Document Expiry Wallet ─────────────────────────────────────────────
            st.markdown('<div class="sec">📄 Document Expiry Status</div>', unsafe_allow_html=True)
            # Fetch fresh expiry data
            _pdp_exp = _rbw_exp = _cbp_exp = None
            if connected and tid:
                try:
                    _conn = get_conn()
                    _erow = _conn.execute(
                        "SELECT pdp_expiry, roadworthy_expiry, cross_border_permit_expiry "
                        "FROM Truck WHERE truck_id=?", (tid,)
                    ).fetchone()
                    _conn.close()
                    if _erow:
                        _pdp_exp, _rbw_exp, _cbp_exp = _erow
                except Exception:
                    pass

            _exp_items = [
                ("PDP",                      _pdp_exp),
                ("Roadworthy Certificate",   _rbw_exp),
                ("Cross-Border Permit",      _cbp_exp),
            ]
            for _exp_label, _exp_val in _exp_items:
                _days = days_until_expiry(_exp_val)
                _badge, _bc = expiry_badge(_days)
                st.markdown(
                    f"<div style='background:rgba(15,23,42,.55);border:1px solid {_bc}44;"
                    f"border-radius:8px;padding:8px 14px;margin-bottom:5px;"
                    f"display:flex;justify-content:space-between;align-items:center;'>"
                    f"<span style='font-size:.82rem;color:#e2e8f0;font-weight:600;'>{_exp_label}</span>"
                    f"<span style='font-size:.78rem;color:{_bc};font-weight:700;'>{_badge}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="sec">📞 Contact Details</div>', unsafe_allow_html=True)
            with st.form("prof_v6", clear_on_submit=False):
                np2=st.text_input("Phone", value=t_phone or "", placeholder="+268 7xxx xxxx")
                nl2=st.text_input("License Number", value=t_lic or "")
                ni2=st.text_input("National ID / Passport", value=t_idn or "")
                nc2=st.text_input("Certifications", value=t_certs or "", placeholder="e.g. Hazmat, Refrigerated")
                nr2=st.text_input("Assigned Routes", value=t_routes or "", placeholder="e.g. Eswatini, South Africa")
                sp2=st.form_submit_button("💾 Save", type="primary", use_container_width=True)
            if sp2 and connected:
                try:
                    conn=get_conn()
                    conn.execute("UPDATE Truck SET driver_phone=?,driver_license=?,driver_id_number=?,driver_certifications=?,driver_routes=? WHERE truck_id=?",
                                 (np2,nl2,ni2,nc2,nr2,tid))
                    conn.commit(); conn.close(); st.success("✅ Profile updated."); st.rerun()
                except Exception as e: st.error(f"Error: {e}")

            # ── Change PIN ─────────────────────────────────────────────────────────
            st.markdown('<div class="sec">🔑 Change PIN</div>', unsafe_allow_html=True)
            with st.form("pin_change_drv", clear_on_submit=True):
                _op = st.text_input("Current PIN", type="password", placeholder="Enter current PIN")
                _np1 = st.text_input("New PIN", type="password", placeholder="Minimum 4 digits")
                _np2 = st.text_input("Confirm New PIN", type="password")
                _pb = st.form_submit_button("Change PIN", use_container_width=True)
            if _pb:
                if len(_np1) < 4:
                    st.error("PIN must be at least 4 digits.")
                elif _np1 != _np2:
                    st.error("PINs do not match.")
                elif not _op:
                    st.error("Enter your current PIN to confirm.")
                else:
                    try:
                        from core.auth import (
                            verify_driver_login as _vdl,
                            change_password_by_username as _cpbu,
                        )
                        _vok, _vmsg, _ = _vdl(drv_id, _op)
                        if not _vok:
                            st.error(f"Current PIN incorrect — {_vmsg}")
                        else:
                            _rok, _rmsg = _cpbu(drv_id, _np1)
                            if _rok:
                                st.success("✅ PIN changed. Use your new PIN next time you log in.")
                            else:
                                st.error(f"Error: {_rmsg}")
                    except ImportError:
                        st.warning("PIN change requires the manager portal auth module. Contact your fleet manager.")
                    except Exception as _pe:
                        st.error(f"PIN change failed: {_pe}")

st.divider()
st.markdown(f"<div style='text-align:center;font-size:.7rem;color:#475569;'>KSM Smart Freight · Driver Terminal v6.1 · {drv_id}</div>",unsafe_allow_html=True)
