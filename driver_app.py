"""
KSM Smart Freight Solutions — Driver Terminal v5.0
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
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(_APP_DIR, "fleet.db")
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
ROUTE_DATA = {
    ("Manzini","Johannesburg"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Vehicle Licence Disc","Driver Licence","PDP","Cross-border permit","Company letter"],
        "est_wait":"1–3 hrs","dangers":["Van Reenen Pass (fog/ice Jun–Aug)","N3 truck stops (theft risk at night)","Standerton weigh bridge"],"overnight":"Standerton or Heidelberg"},
    ("Manzini","Durban"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Vehicle Licence Disc","Driver Licence","PDP","Cross-border permit"],
        "est_wait":"1–2 hrs","dangers":["Van Reenen Pass (steep descent — brake check required)","N3 Mooi River bend","Durban port congestion"],"overnight":"Harrismith or Mooi River"},
    ("Manzini","Nelspruit"):{"border":"Matsamo / Jeppe's Reef","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Driver Licence","PDP","Cross-border permit"],
        "est_wait":"30min–2 hrs","dangers":["R40 mountain passes","Hazyview pedestrian traffic"],"overnight":"Hazyview or White River"},
    ("Manzini","Pretoria"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Vehicle Licence Disc","Driver Licence","PDP","Cross-border permit","Company letter"],
        "est_wait":"1–3 hrs","dangers":["N3/N1 junction heavy traffic","Johannesburg bypass congestion","N1 weigh bridges"],"overnight":"Middelburg or Witbank"},
    ("Mbabane","Johannesburg"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Vehicle Licence Disc","Driver Licence","PDP","Cross-border permit"],
        "est_wait":"1–3 hrs","dangers":["Van Reenen Pass","N3 long-vehicle restrictions peak hours"],"overnight":"Standerton"},
    ("Mbabane","Durban"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Driver Licence","PDP","Cross-border permit"],
        "est_wait":"1–2 hrs","dangers":["Van Reenen Pass","N3 Mooi River"],"overnight":"Harrismith"},
    ("Matsapha","Johannesburg"):{"border":"Oshoek / Ngwenya","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Vehicle Licence Disc","Driver Licence","PDP","Cross-border permit"],
        "est_wait":"1–3 hrs","dangers":["Van Reenen Pass","N3 truck stops"],"overnight":"Standerton"},
    ("Lavumisa","Durban"):{"border":"Lavumisa / Golela","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Driver Licence","PDP","Cross-border permit"],
        "est_wait":"30min–2 hrs","dangers":["N2 Pongola bridge (weight limit)","Sugar cane trucks on N2"],"overnight":"Pongola or Mkuze"},
    ("Lavumisa","Johannesburg"):{"border":"Lavumisa / Golela","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Driver Licence","PDP","Cross-border permit","Company letter"],
        "est_wait":"30min–2 hrs","dangers":["N2 to N3 Durban bypass","Van Reenen Pass","N3 Johannesburg congestion"],"overnight":"Harrismith or Heidelberg"},
    ("Piggs Peak","Johannesburg"):{"border":"Matsamo / Jeppe's Reef","border_hours":"06:00–22:00",
        "border_docs":["CMR/Waybill","Driver Licence","PDP","Cross-border permit"],
        "est_wait":"30min–1.5 hrs","dangers":["R40 narrow road sections","Hazyview pedestrian traffic"],"overnight":"Nelspruit or Middelburg"},
    ("Manzini","Maputo"):{"border":"Lomahasha / Namaacha","border_hours":"07:00–22:00",
        "border_docs":["CMR/Waybill","Mozambican transit permit","SADC certificate of origin","Driver Licence","PDP","Carbon tax certificate"],
        "est_wait":"2–5 hrs","dangers":["EN4 road quality (potholes)","Fuel availability in MZ — carry extra","Border fraud risk — use official lanes only","Speeding fines — cameras on EN4"],"overnight":"Maputo (arrive before 17:00)"},
    ("Mbabane","Maputo"):{"border":"Lomahasha / Namaacha","border_hours":"07:00–22:00",
        "border_docs":["CMR/Waybill","Mozambican transit permit","SADC certificate of origin","Driver Licence","PDP"],
        "est_wait":"2–5 hrs","dangers":["EN4 road quality","Fuel scarcity outside Maputo","Night driving not recommended in MZ"],"overnight":"Maputo"},
    ("Lomahasha","Maputo"):{"border":"Lomahasha / Namaacha","border_hours":"07:00–22:00",
        "border_docs":["CMR/Waybill","Mozambican transit permit","Driver Licence","PDP"],
        "est_wait":"1–4 hrs","dangers":["EN4 road quality","Police checkpoints every 50km in MZ"],"overnight":"Maputo"},
    ("Johannesburg","Durban"):{"border":None,"border_hours":None,"border_docs":[],"est_wait":None,
        "dangers":["Van Reenen Pass (fog/ice/steep)","N3 Mooi River accident zone","Durban port congestion","Pietermaritzburg N3 upgrade delays"],"overnight":"Harrismith or Mooi River"},
    ("Johannesburg","Nelspruit"):{"border":None,"border_hours":None,"border_docs":[],"est_wait":None,
        "dangers":["N4 Middelburg toll","N4 Machadodorp mountain section","Nelspruit R40 pedestrian traffic"],"overnight":"Middelburg or Belfast"},
    ("Nelspruit","Maputo"):{"border":"Lebombo / Ressano Garcia","border_hours":"06:00–24:00",
        "border_docs":["CMR/Waybill","Mozambican transit permit","SADC certificate of origin","Driver Licence","PDP","Carbon tax certificate"],
        "est_wait":"1–4 hrs","dangers":["EN4 potholes after Ressano Garcia","Speeding cameras on EN4","Night driving risk"],"overnight":"Maputo"},
    ("Durban","Maputo"):{"border":"Lebombo / Ressano Garcia","border_hours":"06:00–24:00",
        "border_docs":["CMR/Waybill","Mozambican transit permit","SADC CoO","Driver Licence","PDP"],
        "est_wait":"1–3 hrs","dangers":["N2 Pongola bridge","EN4 road quality","Long route — fatigue risk (850km+)"],"overnight":"Nelspruit outbound / Pongola inbound"},
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
                        ("driver_routes","TEXT"),("driver_certifications","TEXT"),
                        ("pdp_expiry","TEXT"),("roadworthy_expiry","TEXT"),
                        ("cross_border_permit_expiry","TEXT"),("driver_pin","TEXT")]:
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
        conn.commit(); conn.close()
     except Exception as e:
        try: conn.close()
        except: pass

def get_driver_by_id(did):
    if not db_ok(): return None
    try:
        conn = get_conn()
        row = conn.execute("""SELECT truck_id,registration,driver,mileage,fuel_tank_capacity,
            driver_id,driver_license,driver_phone,driver_id_number,driver_experience_years,
            driver_routes,driver_certifications,truck_status,model,
            pdp_expiry,roadworthy_expiry,cross_border_permit_expiry,driver_pin
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

def change_pin(tid, current_pin, new_pin, driver_id):
    """Verify current PIN then update to new PIN."""
    if not db_ok(): return False, "Database not available"
    try:
        conn = get_conn()
        row = conn.execute("SELECT driver_pin FROM Truck WHERE truck_id=?", (tid,)).fetchone()
        stored = (row[0] if row and row[0] else None)
        # Fallback: check DRIVER_PINS dict if no DB pin set
        fallback = DRIVER_PINS.get(driver_id)
        valid = (stored and current_pin == stored) or (not stored and current_pin == fallback)
        if not valid:
            conn.close(); return False, "Current PIN is incorrect"
        if len(new_pin) < 4:
            conn.close(); return False, "New PIN must be at least 4 digits"
        conn.execute("UPDATE Truck SET driver_pin=? WHERE truck_id=?", (new_pin, tid))
        conn.commit(); conn.close()
        # Also update in-memory fallback
        DRIVER_PINS[driver_id] = new_pin
        return True, "PIN changed successfully"
    except Exception as e:
        return False, str(e)

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
        st.toast("⚖️ Weighbridge ticket extracted!", icon="✅")

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
        f"<div style='font-size:.72rem;font-weight:800;color:#60a5fa;letter-spacing:.1em;'>KSM DRIVER TERMINAL v6.0</div>"
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
                    f"padding:2px 10px;margin-bottom:4px;'>🔔 {_unread} new</div>",unsafe_allow_html=True)
    # SOS: inject GPS-capture HTML alongside the Streamlit button
    sos_gps_html = """
    <div id="sos-gps-wrap" style="margin-bottom:4px;">
      <div id="sos-gps-loc" style="font-size:.62rem;color:#f87171;font-family:monospace;
        min-height:14px;text-align:center;"></div>
    </div>
    <script>
    (function(){
      var el=document.getElementById('sos-gps-loc');
      if(!navigator.geolocation){el.innerText='GPS not available';return;}
      navigator.geolocation.getCurrentPosition(function(p){
        var lat=p.coords.latitude.toFixed(5),lon=p.coords.longitude.toFixed(5);
        var acc=Math.round(p.coords.accuracy);
        el.innerText='📍 '+lat+', '+lon+' (±'+acc+'m)';
        sessionStorage.setItem('ksm_sos_lat',lat);
        sessionStorage.setItem('ksm_sos_lon',lon);
        sessionStorage.setItem('ksm_sos_loc','GPS: '+lat+','+lon+' ±'+acc+'m');
      },function(e){el.innerText='⚠️ '+e.message;},{enableHighAccuracy:true,timeout:8000});
    })();
    </script>
    """
    st.components.v1.html(sos_gps_html, height=22)
    if st.button("🆘 SOS",use_container_width=True,help="Emergency — tap to alert fleet manager immediately"):
        _sos_loc = st.session_state.get("_sos_gps_loc","GPS capture — see browser") 
        _sos_rec={"truck_id":tid or 0,"driver_id":drv_id,"date":now.strftime("%Y-%m-%d"),
                  "odometer":cur_odo,"location":_sos_loc,"reg":treg}
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
    (t_id,t_reg,t_driver,t_mile,t_tank,t_did,t_lic,t_phone,t_idn,t_exp,
     t_routes,t_certs,t_stat,t_model,*_) = assigned
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
tab_now, tab_log, tab_me = st.tabs(["🏠 Now","📝 Log","👤 Me"])

# ═══════════════════════════════════════════════════════════════════════════════
# NOW TAB — Greeting · SOS · Job Card · DSR gate · Checklist gate · Fuel · Briefing · Inbox
# ═══════════════════════════════════════════════════════════════════════════════
with tab_now:
    if not tid:
        st.warning("⚠️ No truck assigned. Contact your fleet manager.")
    else:
        pf        = st.session_state.get("pf_trip", {})
        last_fuel = get_last_fuel(tid)
        avg_eff   = get_avg_eff(tid)

        # ── GREETING BANNER ───────────────────────────────────────────────────
        _hour = now.hour
        _greet = "Good morning" if _hour < 12 else ("Good afternoon" if _hour < 17 else "Good evening")
        _greet_icon = "🌅" if _hour < 12 else ("☀️" if _hour < 17 else "🌙")
        _first_name = (drv_row[2] or drv_id).split()[0] if drv_row else drv_id

        if pf.get("origin") and pf.get("destination"):
            _job_line = f'<div style="font-size:.85rem;color:#93c5fd;margin-top:6px;">Today\'s job: <b>{pf["origin"]} → {pf["destination"]}</b></div>'
            _rk = (pf["origin"], pf["destination"])
            _rk2 = (pf["destination"], pf["origin"])
            _rd_a = ROUTE_DATA.get(_rk) or ROUTE_DATA.get(_rk2)
            _alert_html = (
                f'<div style="margin-top:8px;background:rgba(245,158,11,.12);border:1px solid #f59e0b40;'
                f'border-radius:8px;padding:8px 12px;font-size:.78rem;color:#fde68a;">'
                f'⚠️ <b>Route alert:</b> {_rd_a["dangers"][0]}</div>'
            ) if (_rd_a and _rd_a.get("dangers")) else ""
        else:
            _job_line = '<div style="font-size:.78rem;color:#475569;margin-top:6px;">No job loaded — scan a Job Order in 📝 Log → Scan</div>'
            _alert_html = ""

        st.markdown(
            f'<div style="background:linear-gradient(135deg,rgba(15,23,42,.95),rgba(30,41,59,.9));'
            f'border:1px solid rgba(96,165,250,.3);border-radius:16px;padding:20px 22px;margin-bottom:1rem;">'
            f'<div style="font-size:1.15rem;font-weight:800;color:#fff;">{_greet_icon} {_greet}, {_first_name}</div>'
            f'<div style="font-size:.75rem;color:#64748b;margin-top:3px;">'
            f'Truck: <span style="color:#93c5fd;font-weight:700;">{treg}</span>'
            f' · ODO: <span style="color:#e2e8f0;">{cur_odo:,.0f} km</span>'
            f' · {now.strftime("%a %d %b %Y")}</div>'
            f'{_job_line}{_alert_html}'
            f'</div>',
            unsafe_allow_html=True)

        # ── PROMINENT SOS ─────────────────────────────────────────────────────
        st.components.v1.html("""
        <div id="sos-gps-badge" style="font-size:.62rem;color:#f87171;font-family:monospace;
          text-align:center;min-height:14px;margin-bottom:4px;"></div>
        <script>
        (function(){
          var el=document.getElementById('sos-gps-badge');
          if(!navigator.geolocation){el.innerText='GPS unavailable';return;}
          navigator.geolocation.getCurrentPosition(function(p){
            var lat=p.coords.latitude.toFixed(5),lon=p.coords.longitude.toFixed(5),acc=Math.round(p.coords.accuracy);
            el.innerText='📍 '+lat+', '+lon+' (±'+acc+'m)';
            sessionStorage.setItem('ksm_sos_lat',lat);
            sessionStorage.setItem('ksm_sos_lon',lon);
          },function(e){el.innerText='⚠️ '+e.message;},{enableHighAccuracy:true,timeout:8000});
        })();
        </script>""", height=20)

        if st.button("🆘 SOS — EMERGENCY", use_container_width=True, type="primary",
                     help="One tap — logs your location and alerts fleet manager immediately"):
            _sos_rec = {"truck_id": tid, "driver_id": drv_id, "date": now.strftime("%Y-%m-%d"),
                        "odometer": cur_odo, "location": "GPS auto-captured — see DB log", "reg": treg}
            if connected and save_sos(_sos_rec):
                st.session_state["sos_fired"] = True
            st.rerun()
        if st.session_state.get("sos_fired"):
            st.markdown(
                '<div style="text-align:center;font-size:.9rem;font-weight:800;color:#f87171;'
                'background:rgba(78,6,6,.6);border:2px solid #dc2626;border-radius:10px;'
                'padding:10px;margin-top:4px;">🚨 SOS SENT — Fleet manager alerted</div>',
                unsafe_allow_html=True)
            st.markdown(
                '<div style="text-align:center;font-size:.78rem;color:#fde68a;margin-top:6px;">'
                'Emergency numbers: 🚔 Police <b>999</b> · 🚑 Ambulance <b>977</b> · 🔥 Fire <b>933</b></div>',
                unsafe_allow_html=True)

        st.divider()

        # ── STEP 1: DSR GATE ─────────────────────────────────────────────────
        today_dsr = get_todays_dsr(tid, drv_id) if connected else None
        dsr_passed = bool(today_dsr)
        _dsr_label = "✅ Daily Status Report" if dsr_passed else '① Daily Status Report <span style="color:#f59e0b;font-size:.72rem;">(required before checklist)</span>'
        st.markdown(f'<div class="sec">{_dsr_label}</div>', unsafe_allow_html=True)

        if dsr_passed:
            _notes_str = today_dsr[0] or ""
            _fit_status = "FIT" if "Fit: True" in _notes_str else "UNFIT"
            _dsr_col = "#34d399" if _fit_status == "FIT" else "#f87171"
            st.markdown(
                f'<div class="ext-banner" style="border-color:{_dsr_col}40;">'
                f'<span style="font-size:.72rem;font-weight:800;color:{_dsr_col};">● DSR — {_fit_status} TO DRIVE TODAY</span><br>'
                f'<span style="font-size:.78rem;color:#94a3b8;">{_notes_str[:120]}</span></div>',
                unsafe_allow_html=True)
        else:
            with st.form("dsr_form", clear_on_submit=True):
                _fit = st.radio("Fit to drive today?", ["✅ Yes — I am fit", "❌ No — I am not fit"], index=0, horizontal=True)
                _is_fit = _fit.startswith("✅")
                _unfit_reason = ""
                if not _is_fit:
                    _unfit_reason = st.selectbox("Reason", DSR_REASONS_UNFIT)
                    st.warning("⚠️ Fleet manager will be notified. Do not drive today.")
                _tc_sel = st.radio("Truck condition", ["✅ Roadworthy", "⚠️ Minor issues", "🔴 Unroadworthy"], index=0, horizontal=True)
                _tc_notes = st.text_area("Condition notes (if issues)", height=50, placeholder="e.g. Windscreen crack noted")
                _dsr_odo = st.number_input("Starting odometer (km)", min_value=0.0, value=float(cur_odo), step=1.0)
                _dsr_date = st.date_input("Date", value=date.today(), key="dsr_date")
                _dsr_sub = st.form_submit_button("📋 Submit DSR & Continue", type="primary", use_container_width=True)
            if _dsr_sub:
                _all_notes = f"{_tc_sel} | {_tc_notes}" if _tc_notes.strip() else _tc_sel
                _dsr_rec = {"truck_id": tid, "driver_id": drv_id, "date": _dsr_date.strftime("%Y-%m-%d"),
                            "fit": _is_fit, "odometer": _dsr_odo,
                            "checklist_score": st.session_state.get("checklist_data", {}).get("score", 0),
                            "issues": _all_notes, "unfit_reason": _unfit_reason if not _is_fit else ""}
                if connected and save_dsr(_dsr_rec):
                    st.success("✅ DSR submitted!" if _is_fit else f"🔴 UNFIT status logged.")
                    st.session_state["dsr_done"] = True
                    st.rerun()
                else:
                    st.warning("📶 Could not save DSR.")
            st.info("ℹ️ Complete your Daily Status Report above to continue.")

        if dsr_passed:
            st.divider()

            # ── STEP 2: PRE-TRIP CHECKLIST GATE ──────────────────────────────
            _checklist_done = st.session_state.get("checklist_done", False)
            _chk_label = "✅ Pre-Trip Safety Checklist" if _checklist_done else '② Pre-Trip Safety Checklist <span style="color:#f59e0b;font-size:.72rem;">(required before Log Trip unlocks)</span>'
            st.markdown(f'<div class="sec">{_chk_label}</div>', unsafe_allow_html=True)

            if _checklist_done:
                _chk_data = st.session_state.get("checklist_data", {})
                _chk_issues_html = f'<br><span style="font-size:.76rem;color:#94a3b8;">Issues: {_chk_data["issues"][:80]}</span>' if _chk_data.get("issues") else ""
                st.markdown(
                    f'<div class="ext-banner" style="border-color:#34d39940;">'
                    f'<span style="font-size:.72rem;font-weight:800;color:#34d399;">✅ CHECKLIST PASSED — {_chk_data.get("score", 8)}/8 items</span>'
                    f'{_chk_issues_html}</div>',
                    unsafe_allow_html=True)
                if st.button("↩ Redo Checklist", key="redo_chk_now"):
                    st.session_state["checklist_done"] = False
                    st.rerun()
            else:
                st.markdown('<div class="info-strip">Complete all 8 checks — the <b>📝 Log → Trip</b> form unlocks when done.</div>', unsafe_allow_html=True)
                _checks = {}
                for _key, _icon, _label, _hint in CHECKLIST_ITEMS:
                    _ca, _cb = st.columns([5, 1])
                    with _ca:
                        st.markdown(f"<div style='font-size:.85rem;color:#e2e8f0;padding:5px 0;'>{_icon} <b>{_label}</b> "
                                    f"<span style='color:#475569;font-size:.74rem;'>— {_hint}</span></div>",
                                    unsafe_allow_html=True)
                    with _cb:
                        _checks[_key] = st.checkbox("✓", key=f"chk_now_{_key}", label_visibility="collapsed")
                _passed = sum(_checks.values())
                _pass_color = "#34d399" if _passed == 8 else "#f59e0b"
                _pass_msg = "✅ All checks passed — ready to depart!" if _passed == 8 else f"⚠️ {_passed}/8 confirmed — tick all to unlock trip logging."
                st.markdown(f"<div style='margin:.5rem 0;font-size:.84rem;font-weight:700;color:{_pass_color};'>{_pass_msg}</div>", unsafe_allow_html=True)
                _issues_txt = st.text_area("Faults / notes (optional)", placeholder="e.g. Minor oil seep — reported to workshop", height=55, key="chk_now_issues")
                _btn_label = "✅ Confirm Checklist — Unlock Log Trip" if _passed == 8 else f"⚠️ {_passed}/8 — tick all boxes first"
                if st.button(_btn_label, use_container_width=True, disabled=(_passed < 8)):
                    st.session_state["checklist_done"] = True
                    st.session_state["checklist_data"] = {"score": _passed, "issues": _issues_txt, "items": _checks}
                    st.rerun()

            st.divider()

            # ── GPS LOCATION ──────────────────────────────────────────────────
            st.markdown('<div class="sec">📍 My Location</div>', unsafe_allow_html=True)
            st.components.v1.html("""
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
              if(!navigator.geolocation){document.getElementById('gps-result').innerText='❌ GPS not available';return;}
              navigator.geolocation.getCurrentPosition(function(p){
                var lat=p.coords.latitude.toFixed(5),lon=p.coords.longitude.toFixed(5),acc=Math.round(p.coords.accuracy);
                document.getElementById('gps-result').innerText='✅ '+lat+', '+lon+' (±'+acc+'m) — copied';
                navigator.clipboard&&navigator.clipboard.writeText(lat+', '+lon);
                sessionStorage.setItem('ksm_lat',lat); sessionStorage.setItem('ksm_lon',lon);
              },function(e){document.getElementById('gps-result').innerText='⚠️ '+e.message;},{enableHighAccuracy:true,timeout:10000});
            }
            </script>""", height=80)
            st.caption("Coordinates stored locally for SOS and incident logging. Not tracked continuously.")

            st.divider()

            # ── FUEL CALCULATOR ───────────────────────────────────────────────
            st.markdown('<div class="sec">⛽ Pre-Departure Fuel Calculator</div>', unsafe_allow_html=True)
            _fc1, _fc2 = st.columns(2)
            with _fc1:
                _fc_orig_txt = st.text_input("From (type to search)", value=pf.get("origin", "Manzini"), key="fc_orig_txt", placeholder="e.g. Manzini, Mbabane")
                _fc_orig_m = [l for l in LOCATIONS if _fc_orig_txt.lower() in l.lower()] if _fc_orig_txt else LOCATIONS
                _fc_origin = _fc_orig_m[0] if _fc_orig_m else (_fc_orig_txt or LOCATIONS[0])
                if len(_fc_orig_m) > 1:
                    _fc_origin = st.selectbox("", _fc_orig_m, key="fc_orig_sel", label_visibility="collapsed")
            with _fc2:
                _fc_dest_txt = st.text_input("To (type to search)", value=pf.get("destination", "Johannesburg"), key="fc_dest_txt", placeholder="e.g. Durban, Maputo")
                _fc_dest_m = [l for l in LOCATIONS if _fc_dest_txt.lower() in l.lower() and l != _fc_origin] if _fc_dest_txt else [l for l in LOCATIONS if l != _fc_origin]
                _fc_dest = _fc_dest_m[0] if _fc_dest_m else (_fc_dest_txt or LOCATIONS[1])
                if len(_fc_dest_m) > 1:
                    _fc_dest = st.selectbox("", _fc_dest_m, key="fc_dest_sel", label_visibility="collapsed")

            _fc_dist = est_dist(_fc_origin, _fc_dest)
            _fc_rate = avg_eff if avg_eff and avg_eff > 0 else (100 / FUEL_BASE_L_PER_100)
            _fc_need = round(_fc_dist / _fc_rate, 0) if _fc_rate > 0 else round(_fc_dist * FUEL_BASE_L_PER_100 / 100, 0)
            _lf_liters = float(last_fuel[0]) if last_fuel else 0
            _lf_odo = float(last_fuel[1]) if last_fuel else cur_odo
            _km_since = max(0, cur_odo - _lf_odo)
            _fc_consumed = round(_km_since / _fc_rate, 0) if (_fc_rate > 0 and _km_since > 0) else 0
            _fc_remaining = max(0, _lf_liters - _fc_consumed) if last_fuel else 0
            _fc_after = _fc_remaining - _fc_need
            _fc_pct = round(_fc_after / tank_cap * 100, 0) if tank_cap > 0 else 0

            _fca, _fcb, _fcc, _fcd = st.columns(4)
            _fca.metric("Distance", f"{_fc_dist:.0f} km")
            _fcb.metric("Est. Fuel Needed", f"{_fc_need:.0f} L")
            _fcc.metric("Est. in Tank", f"{_fc_remaining:.0f} L" if last_fuel else "—")
            _fcd.metric("Tank After Trip", f"{_fc_after:.0f} L" if last_fuel else "—",
                        delta=f"{_fc_pct:.0f}%" if last_fuel else None,
                        delta_color="normal" if _fc_pct > 20 else "inverse")
            if last_fuel and _fc_after < tank_cap * 0.15:
                _refuel_tips = {"Johannesburg": "Nelspruit", "Durban": "Pongola / Mkuze",
                                "Maputo": "Lomahasha / Namaacha", "Nelspruit": "Ermelo / Middelburg"}
                _refuel_tip = _refuel_tips.get(_fc_dest, "before destination")
                st.markdown(f'<div class="info-strip" style="border-color:#f59e0b40;color:#fbbf24;">⛽ <b>Low fuel warning</b> — ~{_fc_after:.0f} L remaining after trip. Refuel at <b>{_refuel_tip}</b>.</div>', unsafe_allow_html=True)
            elif last_fuel:
                st.markdown(f'<div class="info-strip">✅ Sufficient fuel — ~{_fc_pct:.0f}% remaining on arrival.</div>', unsafe_allow_html=True)

            # ── ROUTE BRIEFING ────────────────────────────────────────────────
            _rd = ROUTE_DATA.get((_fc_origin, _fc_dest)) or ROUTE_DATA.get((_fc_dest, _fc_origin))
            _is_cross = any(l in [_fc_origin, _fc_dest] for l in ["Johannesburg", "Durban", "Maputo", "Nelspruit", "Pretoria"])
            if _rd or _is_cross:
                with st.expander("🗺️ Route Briefing — tap to expand", expanded=False):
                    if _rd:
                        if _rd.get("border"):
                            st.markdown(
                                f'<div style="margin-bottom:.6rem;">'
                                f'<div style="font-size:.62rem;font-weight:800;letter-spacing:.12em;color:#60a5fa;text-transform:uppercase;margin-bottom:8px;">🛂 Border Information</div>'
                                f'<div style="font-size:.82rem;color:#e2e8f0;margin-bottom:4px;">'
                                f'<b>Post:</b> {_rd["border"]} · <b>Hours:</b> {_rd["border_hours"]} · <b>Est. wait:</b> {_rd["est_wait"]}</div>'
                                f'<div style="font-size:.75rem;color:#94a3b8;">Documents: {", ".join(_rd["border_docs"])}</div>'
                                f'</div>', unsafe_allow_html=True)
                        st.markdown('<div style="font-size:.62rem;font-weight:800;letter-spacing:.12em;color:#f97316;text-transform:uppercase;margin-bottom:6px;">⚠️ Route Hazards</div>', unsafe_allow_html=True)
                        for _danger in _rd["dangers"]:
                            st.markdown(f"<div style='font-size:.79rem;color:#fde68a;margin-bottom:3px;'>• {_danger}</div>", unsafe_allow_html=True)
                        if _rd.get("overnight"):
                            st.markdown(f'<div style="font-size:.79rem;color:#6ee7b7;margin-top:8px;">🛏️ <b>Overnight stop if trip &gt;8h:</b> {_rd["overnight"]}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="info-strip">Cross-border route — ensure all transit documents are on board.</div>', unsafe_allow_html=True)

            st.divider()

            # ── NOTIFICATION INBOX ────────────────────────────────────────────
            _notifs = get_notifications(drv_id, tid) if connected else []
            _unread_n = sum(1 for n in _notifs if not n[5])
            st.markdown(f'<div class="sec">🔔 Messages{" · " + str(_unread_n) + " unread" if _unread_n else ""}</div>', unsafe_allow_html=True)
            if not _notifs:
                st.markdown('<div class="info-strip">📭 No messages from fleet manager.</div>', unsafe_allow_html=True)
            else:
                if _unread_n and st.button("✅ Mark all read", key="mark_all_now"):
                    mark_all_read(drv_id, tid); st.rerun()
                _pc = {"Urgent": "#f87171", "High": "#f97316", "Normal": "#93c5fd", "Info": "#6ee7b7"}
                _pb = {"Urgent": "rgba(78,6,6,.35)", "High": "rgba(78,40,6,.35)", "Normal": "rgba(30,58,138,.25)", "Info": "rgba(6,78,59,.25)"}
                for _notif in _notifs:
                    _nid, _ndate, _subject, _message, _priority, _read_at = _notif
                    _nc = _pc.get(_priority, "#93c5fd"); _nb = _pb.get(_priority, "rgba(30,58,138,.25)")
                    _dot = "" if _read_at else f"<span style='display:inline-block;width:7px;height:7px;background:{_nc};border-radius:50%;margin-right:5px;'></span>"
                    st.markdown(
                        f"<div style='background:{_nb};border:1px solid {_nc}30;border-radius:10px;padding:10px 14px;margin-bottom:6px;opacity:{'1' if not _read_at else '.6'};'>"
                        f"<div style='display:flex;justify-content:space-between;margin-bottom:3px;'>"
                        f"<span style='font-size:.82rem;font-weight:700;color:#e2e8f0;'>{_dot}{_subject or '(no subject)'}</span>"
                        f"<span style='font-size:.65rem;color:#64748b;'>{(_ndate or '')[:16]} · <span style='color:{_nc};font-weight:700;'>{_priority}</span></span></div>"
                        f"<div style='font-size:.78rem;color:#cbd5e1;'>{_message or ''}</div></div>",
                        unsafe_allow_html=True)
                    if not _read_at:
                        if st.button("Mark read", key=f"rd_{_nid}"):
                            mark_notification_read(_nid); st.rerun()



# ═══════════════════════════════════════════════════════════════════════════════
# LOG TAB — Scan, Trip, Fuel, Incident, Sync
# ═══════════════════════════════════════════════════════════════════════════════
with tab_log:
    if not tid:
        st.warning("⚠️ No truck assigned.")
    else:
        log_scan, log_trip, log_fuel, log_evt, log_sync = st.tabs([
            "📷 Scan","▣ Trip","◉ Fuel","🚨 Incident","🔄 Sync"])

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
            st.markdown("### ▣ Log Trip")
            if not st.session_state.get("checklist_done", False):
                st.info("ℹ️ Complete the pre-trip safety checklist to unlock the trip form.")
                st.markdown('<div class="sec">✅ Pre-Trip Safety Checklist</div>', unsafe_allow_html=True)
                _lt_checks = {}
                for _key, _icon, _label, _hint in CHECKLIST_ITEMS:
                    _ca, _cb = st.columns([5, 1])
                    with _ca:
                        st.markdown(f"<div style='font-size:.85rem;color:#e2e8f0;padding:5px 0;'>{_icon} <b>{_label}</b> "
                                    f"<span style='color:#475569;font-size:.74rem;'>— {_hint}</span></div>",
                                    unsafe_allow_html=True)
                    with _cb:
                        _lt_checks[_key] = st.checkbox("✓", key=f"chk_log_{_key}", label_visibility="collapsed")
                _lt_passed = sum(_lt_checks.values())
                _lt_color = "#34d399" if _lt_passed == 8 else "#f59e0b"
                st.markdown(f"<div style='margin:.5rem 0;font-size:.84rem;font-weight:700;color:{_lt_color};'>"
                            f"{'✅ All checks passed.' if _lt_passed==8 else f'⚠️ {_lt_passed}/8 — tick all to continue.'}</div>",
                            unsafe_allow_html=True)
                _lt_issues = st.text_area("Faults / notes (optional)", height=55, key="chk_log_issues",
                                          placeholder="e.g. Minor oil seep — reported to workshop")
                if st.button("🔓 Confirm & Unlock Trip Form", use_container_width=True, disabled=(_lt_passed < 8)):
                    st.session_state["checklist_done"] = True
                    st.session_state["checklist_data"] = {"score": _lt_passed, "issues": _lt_issues, "items": _lt_checks}
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

                with st.form("trip_v6",clear_on_submit=True):
                    st.markdown('<div class="sec">📍 Route</div>',unsafe_allow_html=True)
                    r1,r2=st.columns(2)
                    with r1:
                        _orig_txt=st.text_input("From (type to search)",value=pf.get("origin","Manzini"),key="trip_orig_txt",placeholder="e.g. Manzini, Mbabane")
                        _orig_m=[l for l in LOCATIONS if _orig_txt.lower() in l.lower()] if _orig_txt else LOCATIONS
                        origin=_orig_m[0] if _orig_m else (_orig_txt or LOCATIONS[0])
                        if len(_orig_m)>1: origin=st.selectbox("",_orig_m,key="trip_orig_sel",label_visibility="collapsed")
                    with r2:
                        _dest_txt=st.text_input("To (type to search)",value=pf.get("destination","Johannesburg"),key="trip_dest_txt",placeholder="e.g. Durban, Maputo")
                        _dest_m=[l for l in LOCATIONS if _dest_txt.lower() in l.lower() and l!=origin] if _dest_txt else [l for l in LOCATIONS if l!=origin]
                        destination=_dest_m[0] if _dest_m else (_dest_txt or LOCATIONS[1])
                        if len(_dest_m)>1: destination=st.selectbox("",_dest_m,key="trip_dest_sel",label_visibility="collapsed")
                    auto_d=est_dist(origin,destination); auto_t=det_terrain(origin,destination)
                    st.markdown(f'<div class="info-strip">📏 <b>{auto_d:.0f} km</b> · ⛰️ <b>{auto_t}</b> · ◉ Est. <b>~{auto_d*FUEL_BASE_L_PER_100/100:.0f} L</b>'
                                +(f' · Your avg <b>{avg_eff:.2f} km/L</b>' if avg_eff else '')+'</div>',unsafe_allow_html=True)

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
                                    +(f' · 🚀 Avg <b>{auto_d/_dur_h:.0f} km/h</b>' if auto_d>0 else '')+'</div>',unsafe_allow_html=True)

                    st.markdown('<div class="sec">📦 Cargo & Delivery</div>',unsafe_allow_html=True)
                    c5,c6,c7=st.columns(3)
                    with c5: load_kg=st.number_input("Load (kg)",min_value=0.0,value=float(pf.get("load_kg") or 0),step=100.0)
                    with c6: borders=st.number_input("Border crossings",min_value=0,value=int(pf.get("border",0)),step=1)
                    with c7: on_time=st.selectbox("Delivered?",["Yes","No","Partial"],index=0)

                    # Voice input for notes
                    st.markdown('<div class="sec">🎙️ Notes (voice or type)</div>',unsafe_allow_html=True)
                    voice_html="""
                    <div style="margin-bottom:6px;">
                    <button id="voice-btn" onclick="startVoice()" style="background:rgba(30,58,138,.7);color:#93c5fd;border:1px solid rgba(96,165,250,.4);
                      border-radius:8px;padding:6px 14px;font-size:.78rem;font-weight:700;cursor:pointer;">🎙️ Tap to speak</button>
                    <span id="voice-status" style="font-size:.72rem;color:#64748b;margin-left:8px;"></span>
                    </div>
                    <script>
                    var recog=null;
                    function startVoice(){
                      if(!('webkitSpeechRecognition' in window||'SpeechRecognition' in window)){
                        document.getElementById('voice-status').innerText='❌ Not supported on this browser';return;}
                      var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
                      recog=new SR(); recog.lang='en-ZA'; recog.interimResults=false;
                      document.getElementById('voice-status').innerText='🔴 Listening...';
                      document.getElementById('voice-btn').innerText='⏹ Stop';
                      recog.onresult=function(e){
                        var txt=e.results[0][0].transcript;
                        document.getElementById('voice-status').innerText='✅ '+txt;
                        // Try to find the textarea in the parent frame and append
                        try{var ta=window.parent.document.querySelector('textarea[data-testid]');
                          if(ta){ta.value+=(ta.value?' ':'')+txt;ta.dispatchEvent(new Event('input',{bubbles:true}));}}catch(e){}
                      };
                      recog.onerror=function(e){document.getElementById('voice-status').innerText='❌ '+e.error;};
                      recog.onend=function(){document.getElementById('voice-btn').innerText='🎙️ Tap to speak';};
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
                        ["✅ Intact — no issues","⚠️ Minor damage","🔴 Significant damage","📦 Partial delivery"],index=0,key="cargo_cond")
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
                            st.markdown(f'<a href="https://wa.me/?text={wa_text}" target="_blank" style="display:block;background:linear-gradient(135deg,#065f46,#059669);color:white;text-align:center;padding:10px;border-radius:10px;font-weight:700;font-size:.85rem;text-decoration:none;margin-top:8px;">📲 Share via WhatsApp</a>',unsafe_allow_html=True)
                            # Route map — Google Maps directions link
                            _o_enc=origin.replace(" ","+"); _d_enc=destination.replace(" ","+")
                            _maps_url=f"https://www.google.com/maps/dir/{_o_enc}/{_d_enc}"
                            st.markdown(f'<a href="{_maps_url}" target="_blank" style="display:block;background:linear-gradient(135deg,#1e3a8a,#2563eb);color:white;text-align:center;padding:10px;border-radius:10px;font-weight:700;font-size:.85rem;text-decoration:none;margin-top:6px;">🗺️ View Route on Map</a>',unsafe_allow_html=True)
                            st.session_state["pf_trip"]={}
                        else:
                            enqueue(rec,"trip"); st.warning("📶 Offline — trip queued.")
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
                st.markdown('<div class="sec">🔢 Odometer</div>',unsafe_allow_html=True)
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
                  🎙️ Speak incident description</button>
                <span id="inc-v-status" style="font-size:.7rem;color:#64748b;margin-left:6px;"></span>
                <script>
                function startIncVoice(){
                  if(!('webkitSpeechRecognition' in window||'SpeechRecognition' in window)){
                    document.getElementById('inc-v-status').innerText='❌ Not supported';return;}
                  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
                  var r=new SR(); r.lang='en-ZA'; r.interimResults=false;
                  document.getElementById('inc-v-status').innerText='🔴 Listening...';
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
                evt_photo=st.file_uploader("📷 Incident photo (optional)",type=["jpg","jpeg","png","webp"],key="evt_photo_upload",
                    help="Photograph the scene, damage, or anything relevant")
                edate=st.date_input("Date",value=date.today(),key="evt_date")
                esub=st.form_submit_button("🚨 Submit Report",type="primary",use_container_width=True)
            if esub:
                if not edesc.strip(): st.error("Please describe what happened.")
                else:
                    erec={"truck_id":tid,"date":edate.strftime("%Y-%m-%d"),"event_type":etype,"severity":sev,
                          "location":eloc,"description":edesc,"odometer":cur_odo}
                    if connected and save_event(erec):
                        st.success("✅ Incident reported.")
                        if evt_photo:
                            try:
                                _eb=evt_photo.read(); _em=evt_photo.type or "image/jpeg"
                                save_doc(tid,drv_id,"Other Document",
                                    f"incident_{edate.strftime('%Y%m%d')}_{etype[:12].replace(' ','_')}.{evt_photo.name.split('.')[-1]}",
                                    _eb,_em,{"type":"incident_photo","event_type":etype,"severity":sev,"location":eloc},
                                    notes=f"Incident photo — {etype} [{sev}] at {eloc}")
                                st.toast("📷 Incident photo saved",icon="📷")
                            except Exception as _pe: st.warning(f"Photo save failed: {_pe}")
                    else: enqueue(erec,"event"); st.warning("📶 Queued offline.")

        # ── SYNC ──────────────────────────────────────────────────────────────
        with log_sync:
            st.markdown("### 🔄 Sync & Status")
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
    me_perf, me_jobs, me_docs, me_prof = st.tabs(["📊 Performance","📋 My Jobs","🗂️ My Docs","👤 Profile"])

    # ── PERFORMANCE ───────────────────────────────────────────────────────────
    with me_perf:
        st.markdown("### 📊 My Performance")
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
                p2.metric("Distance", f"{ps['dist_month']:,.0f} km")
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

                st.markdown('<div class="sec">📈 All-Time Summary</div>',unsafe_allow_html=True)
                at1,at2 = st.columns(2)
                at1.metric("Total Trips", ps["trips_all"])
                at2.metric("Total Distance", f"{ps['dist_all']:,.0f} km")

    # ── MY JOBS ───────────────────────────────────────────────────────────────
    with me_jobs:
        st.markdown("### 📋 My Jobs")
        st.caption("All trips logged for your truck.")
        if not tid: st.info("No truck assigned.")
        elif not connected: st.warning("⚠️ Database not reachable.")
        else:
            avg_eff=get_avg_eff(tid); jobs=get_driver_jobs(tid)
            if jobs:
                m1,m2,m3,m4=st.columns(4)
                m1.metric("Total",len(jobs))
                m2.metric("Distance",f"{sum(r[4] or 0 for r in jobs):,.0f} km")
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
                    _s_dist  = f'<span>📏 {dist:.0f} km</span>' if dist else ''
                    _s_fuel  = f'<span>◉ {fuel:.0f} L</span>' if fuel else ''
                    _s_eff   = f'<span style="color:{ec};font-weight:700;">{arr} {eff:.2f} km/L</span>' if eff else ''
                    _s_load  = f'<span>📦 {load:,.0f} kg</span>' if load else ''
                    _s_bords = f'<span>🛂 {bords} border(s)</span>' if bords else ''
                    _s_ontime= f'<span>{otb} On time</span>' if otb else ''
                    st.markdown(
                        f'<div class="job-card">'
                        f'<div class="job-route">{orig} → {dest}'
                        f'<span style="float:right;font-size:.71rem;color:#64748b;">{tdate} #{trip_id}</span></div>'
                        f'<div class="job-meta">{_s_dist}{_s_fuel}{_s_eff}{_s_load}{_s_bords}{_s_ontime}</div>'
                        f'</div>',
                        unsafe_allow_html=True)

    # ── MY DOCS ───────────────────────────────────────────────────────────────
    with me_docs:
        st.markdown("### 🗂️ My Documents")
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
            # sel_row now has 18 columns including expiry fields
            (t_id,t_reg,t_driver,t_mile,t_tank,t_did,t_lic,t_phone,t_idn,t_exp,
             t_routes,t_certs,t_stat,t_model,t_pdp_exp,t_rw_exp,t_cbp_exp,t_pin) = (sel_row + (None,)*18)[:18]

            # ── Expiry status helper ───────────────────────────────────────────
            def _exp_badge(label, exp_date_str):
                if not exp_date_str: return f"<div><div class='prof-label'>{label}</div><div style='color:#64748b;'>Not set</div></div>"
                try:
                    exp_d = date.fromisoformat(exp_date_str)
                    days  = (exp_d - date.today()).days
                    if days < 0:   col,tag = "#f87171","🔴 EXPIRED"
                    elif days < 30: col,tag = "#f97316",f"⚠️ {days}d left"
                    elif days < 90: col,tag = "#fbbf24",f"⚠️ {days}d left"
                    else:           col,tag = "#34d399",f"✅ {exp_d.strftime('%d %b %Y')}"
                    return f"<div><div class='prof-label'>{label}</div><div style='color:{col};font-weight:700;font-size:.8rem;'>{tag}</div></div>"
                except: return f"<div><div class='prof-label'>{label}</div><div style='color:#64748b;'>{exp_date_str}</div></div>"

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
            </div>
            <div style="margin-top:12px;border-top:1px solid rgba(52,211,153,.2);padding-top:10px;">
            <div style="font-size:.62rem;font-weight:800;letter-spacing:.1em;color:#60a5fa;text-transform:uppercase;margin-bottom:8px;">📋 Document Expiry Status</div>
            <div class="prof-grid">
                {_exp_badge("PDP Expiry", t_pdp_exp)}
                {_exp_badge("Roadworthy Expiry", t_rw_exp)}
                {_exp_badge("Cross-Border Permit", t_cbp_exp)}
            </div></div></div>""", unsafe_allow_html=True)

            # ── Update contact details ─────────────────────────────────────────
            st.markdown("#### ✏️ Update Details")
            with st.form("prof_v6", clear_on_submit=False):
                pp1, pp2 = st.columns(2)
                with pp1:
                    np2 = st.text_input("Phone", value=t_phone or "", placeholder="+268 7xxx xxxx")
                    nl2 = st.text_input("License Number", value=t_lic or "")
                    ni2 = st.text_input("National ID / Passport", value=t_idn or "")
                with pp2:
                    nc2 = st.text_input("Certifications", value=t_certs or "", placeholder="e.g. Hazmat, Refrigerated")
                    nr2 = st.text_input("Assigned Routes", value=t_routes or "", placeholder="e.g. Eswatini, ZA, MZ")
                    pass
                st.markdown('<div class="sec">📋 Document Expiry Dates</div>', unsafe_allow_html=True)
                ex1, ex2, ex3 = st.columns(3)
                with ex1: pdp_e  = st.date_input("PDP Expiry", value=date.fromisoformat(t_pdp_exp) if t_pdp_exp else date.today(), key="pdp_exp_in")
                with ex2: rw_e   = st.date_input("Roadworthy Expiry", value=date.fromisoformat(t_rw_exp) if t_rw_exp else date.today(), key="rw_exp_in")
                with ex3: cbp_e  = st.date_input("Cross-Border Permit Expiry", value=date.fromisoformat(t_cbp_exp) if t_cbp_exp else date.today(), key="cbp_exp_in")
                sp2 = st.form_submit_button("💾 Save Details", type="primary", use_container_width=True)
            if sp2 and connected:
                try:
                    conn = get_conn()
                    conn.execute("""UPDATE Truck SET driver_phone=?,driver_license=?,driver_id_number=?,
                        driver_certifications=?,driver_routes=?,pdp_expiry=?,roadworthy_expiry=?,
                        cross_border_permit_expiry=? WHERE truck_id=?""",
                        (np2,nl2,ni2,nc2,nr2,
                         pdp_e.isoformat(), rw_e.isoformat(), cbp_e.isoformat(), tid))
                    conn.commit(); conn.close()
                    st.success("✅ Profile updated."); st.rerun()
                except Exception as e: st.error(f"Error: {e}")

            # ── Change PIN ─────────────────────────────────────────────────────
            st.markdown("#### 🔐 Change PIN")
            with st.form("pin_change_v6", clear_on_submit=True):
                pc1, pc2, pc3 = st.columns(3)
                with pc1: cur_pin = st.text_input("Current PIN", type="password", max_chars=8)
                with pc2: new_pin = st.text_input("New PIN (min 4 digits)", type="password", max_chars=8)
                with pc3: cnf_pin = st.text_input("Confirm New PIN", type="password", max_chars=8)
                pin_sub = st.form_submit_button("🔐 Change PIN", use_container_width=True)
            if pin_sub:
                if not cur_pin or not new_pin:
                    st.error("Fill in all PIN fields.")
                elif new_pin != cnf_pin:
                    st.error("New PIN and confirmation do not match.")
                elif not new_pin.isdigit():
                    st.error("PIN must contain digits only.")
                else:
                    ok, msg = change_pin(tid, cur_pin, new_pin, drv_id)
                    if ok: st.success(f"✅ {msg}")
                    else:  st.error(f"❌ {msg}")

st.divider()
st.markdown(f"<div style='text-align:center;font-size:.7rem;color:#475569;'>KSM Smart Freight · Driver Terminal v6.0 · {drv_id}</div>",unsafe_allow_html=True)

