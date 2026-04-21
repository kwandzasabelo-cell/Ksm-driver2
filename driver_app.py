"""
KSM Smart Freight Solutions — Driver Terminal v5.0
Redesigned for speed — drivers log a trip in under 60 seconds.
• Trip log: 5 fields only (no revenue, no behaviour tracking)
• Document scanner: camera/upload → AI reads → auto-fills forms
• My Jobs: all trips for this driver (no revenue shown)
• Fuel receipts: scan → auto-fill → one tap save
"""
import streamlit as st
import math
import os
import json
import base64
from datetime import datetime, date
_AUTH_DB = False

st.set_page_config(page_title="KSM Driver Terminal", page_icon="🚛",
                   layout="centered", initial_sidebar_state="collapsed")

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

from core.supabase_db import (
    db_ok, ensure_schema, get_driver_by_id, get_last_fuel,
    get_avg_eff, get_driver_jobs, get_driver_docs,
    save_trip, save_fuel, save_event, save_doc,
    update_driver_profile, enqueue, qcount, sync_all,
)
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
        st.toast("⛽ Fuel receipt extracted — Fuel tab pre-filled!", icon="✅")
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
             ("pf_trip",{}),("pf_fuel",{}),("scan_extracted",None),("scan_doc_type",None)]:
    if k not in st.session_state: st.session_state[k]=v

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
            # Fallback to hardcoded PINs if DB not available
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

# ── Post-login setup ─────────────────────────────────────────────────────────
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
logo_path=os.path.join(BASE_DIR,"image_2ff50a.png")
drv_id   =st.session_state["drv_driver_id"]
drv_row  =st.session_state["drv_driver_row"]
connected=db_ok()
# SECURITY: after login, only load THIS driver's assigned truck
# load_trucks() would return all — we use get_driver_by_id() result instead
_drv_row_fresh = get_driver_by_id(drv_id) if drv_id else None
trucks = [_drv_row_fresh] if _drv_row_fresh else []
total_pend=qcount("trip")+qcount("fuel")+qcount("event")

with st.sidebar:
    st.markdown("#### 🤖 AI Document Scanner")
    gemini_key=st.text_input("Gemini API Key",type="password",
        value=st.session_state.get("gemini_key",""),
        help="Free at aistudio.google.com — enables AI document scanning")
    if gemini_key: st.session_state["gemini_key"]=gemini_key; st.success("✅ AI scanning enabled")
    else: st.info("Add Gemini key to enable scanning")

# ── Slim header ───────────────────────────────────────────────────────────────
hA,hB,hC=st.columns([1,4,1])
with hA:
    if os.path.exists(logo_path): st.image(logo_path,width=68)
with hB:
    dname=drv_row[2] if drv_row else "Driver"
    treg =drv_row[1] if drv_row else "—"
    now  =datetime.now()
    st.markdown(f"<div style='padding-top:4px;'>"
        f"<div style='font-size:.72rem;font-weight:800;color:#60a5fa;letter-spacing:.1em;'>KSM DRIVER TERMINAL v5.0</div>"
        f"<div style='font-size:1rem;font-weight:700;color:#fff;margin-top:2px;'>{dname}</div>"
        f"<div style='font-size:.68rem;color:#64748b;margin-top:2px;'>"
        f"ID: <span style='color:#34d399;font-weight:700;font-family:monospace;'>{drv_id}</span>"
        f" · Truck: <span style='color:#93c5fd;font-weight:700;'>{treg}</span>"
        f" · {now.strftime('%d %b %Y %H:%M')}</div></div>",unsafe_allow_html=True)
with hC:
    st.markdown("<div style='height:10px'></div>",unsafe_allow_html=True)
    if st.button("Sign Out",use_container_width=True):
        for k in ["drv_authenticated","drv_driver_id","drv_driver_row","selected_truck_id",
                  "selected_truck_label","current_odo","pf_trip","pf_fuel","scan_extracted","scan_doc_type"]:
            st.session_state.pop(k,None)
        st.rerun()

st.divider()

# ── Truck selector + status ───────────────────────────────────────────────────
if connected and not total_pend: chtml='<span class="conn-badge conn-live">● LIVE</span>'
elif connected: chtml=f'<span class="conn-badge conn-pending">◑ {total_pend} pending</span>'
else: chtml='<span class="conn-badge conn-offline">○ OFFLINE</span>'

# SECURITY: driver sees ONLY their assigned truck — no dropdown, no other trucks visible
if drv_row and trucks:
    assigned = next((r for r in trucks if r[0] == drv_row[0]), None)
    if assigned:
        st.session_state.selected_truck_id    = assigned[0]
        st.session_state.selected_truck_label = assigned[1]
        st.session_state.current_odo          = float(assigned[3] or 0)
        tank_cap = float(assigned[4] or 300)
        # Read-only truck display with inline status badge
        st.markdown(
            f"<div style='background:rgba(15,23,42,.6);border:1px solid rgba(96,165,250,.25);"
            f"border-radius:9px;padding:9px 16px;display:flex;align-items:center;gap:12px;'>"
            f"<span style='font-size:.85rem;font-weight:700;color:#e2e8f0;'>"
            f"🚛 <span style='color:#93c5fd;'>{assigned[1]}</span>"
            f"<span style='font-size:.72rem;color:#64748b;font-weight:400;margin-left:8px;'>Your assigned vehicle</span>"
            f"</span>"
            f"<span style='margin-left:auto;'>{chtml}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.warning("⚠️ No truck assigned to your account. Contact your fleet manager.")
        st.session_state.selected_truck_id = None; tank_cap = 300.0
else:
    st.warning("⚠️ No truck assignment found. Contact your fleet manager.")
    st.session_state.selected_truck_id = None; tank_cap = 300.0

tid        =st.session_state.selected_truck_id
cur_odo    =st.session_state.current_odo
sel_row    =next((r for r in trucks if r[0]==tid),None) if tid else None

# Driver ID card
if tid and sel_row:
    (t_id,t_reg,t_driver,t_mile,t_tank,t_did,t_lic,t_phone,t_idn,t_exp,t_routes,t_certs,t_stat,t_model)=sel_row
    s_c={"ACTIVE":"#34d399","MAINTENANCE":"#fbbf24","OUT_OF_SERVICE":"#f87171"}.get(t_stat or "ACTIVE","#34d399")
    items="".join(f'<div style="background:rgba(15,23,42,.5);border:1px solid rgba(96,165,250,.2);border-radius:7px;padding:4px 10px;font-size:.72rem;color:#cbd5e1;"><b style="color:#93c5fd;display:block;font-size:.6rem;text-transform:uppercase;">{lb}</b>{v}</div>'
                  for lb,v in [("License",t_lic or "—"),("Exp.",f"{t_exp or 0} yrs"),("Phone",t_phone or "—"),("Routes",t_routes or "All")])
    st.markdown(f"""<div class="id-card">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
        <div style="background:linear-gradient(135deg,#059669,#10b981);width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.2rem;">🪪</div>
        <div>
            <div style="font-size:.6rem;font-weight:800;letter-spacing:.14em;color:#34d399;text-transform:uppercase;">Driver ID</div>
            <div style="font-size:1rem;font-weight:800;color:#fff;">{t_driver or "Unassigned"}</div>
            <div style="font-size:.7rem;color:#94a3b8;">
                <span style="color:#6ee7b7;font-weight:700;font-family:monospace;">{t_did or "—"}</span>
                &nbsp;·&nbsp; {t_reg} {t_model or ""} &nbsp;·&nbsp;
                <span style="color:{s_c};font-weight:700;">{t_stat or "ACTIVE"}</span></div>
        </div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">{items}</div></div>""",unsafe_allow_html=True)

if tid:
    st.markdown(f'<div class="odo-box"><span style="font-size:.62rem;font-weight:800;letter-spacing:.14em;color:#93c5fd;text-transform:uppercase;">Current Odometer</span><br>'
        f'<span style="font-size:1.7rem;font-weight:800;color:#fff;font-family:monospace;">{cur_odo:,.0f} km</span>'
        f'&nbsp;&nbsp;<span style="font-size:.74rem;color:#60a5fa;">{st.session_state.selected_truck_label}</span></div>',unsafe_allow_html=True)

st.divider()

# =============================================================================
# TABS
# =============================================================================
tab_scan,tab_trip,tab_fuel,tab_evt,tab_jobs,tab_docs,tab_prof,tab_sync=st.tabs([
    "📷 Scan Docs","🚛 Log Trip","⛽ Fuel","🚨 Incident","📋 My Jobs","🗂️ My Docs","👤 Profile","🔄 Sync"])

# ── TAB 1: DOCUMENT SCANNER ────────────────────────────────────────────────────
with tab_scan:
    st.markdown("### 📷 Scan & Upload Documents")
    st.caption("Take a photo or upload any company document — AI reads it and fills the right form for you.")
    api_key=st.session_state.get("gemini_key","")
    dtype=st.selectbox("Document Type",DOC_TYPES,key="scan_dtype_sel",
                        help="Select what you're scanning so AI knows what to extract")
    st.markdown('<div class="scan-box"><div style="font-size:1rem;font-weight:700;color:#34d399;margin-bottom:4px;">📷 Camera · Upload · PDF</div>'
                '<div style="font-size:.74rem;color:#6ee7b7;">Take a photo with your phone or upload from your device<br>Supported: JPG · PNG · WEBP · PDF</div></div>',unsafe_allow_html=True)
    uploaded=st.file_uploader("Tap to photograph or choose file",type=["jpg","jpeg","png","webp","pdf"],
                               key="scan_uploader",label_visibility="collapsed",
                               help="On mobile tap 'Camera' to photograph directly")
    if uploaded:
        fbytes=uploaded.read(); mime=uploaded.type or "image/jpeg"
        if mime.startswith("image/"): st.image(fbytes,width=340,caption=uploaded.name)
        else: st.info(f"📄 **{uploaded.name}** ({fmt_size(len(fbytes))})")
        c1,c2=st.columns(2)
        with c1:
            if not api_key: st.warning("⬆️ Add Gemini API key in sidebar to enable AI extraction")
            elif st.button("🤖 Extract with AI",use_container_width=True,type="primary"):
                with st.spinner(f"Reading {dtype}…"):
                    result=extract_with_ai(fbytes,mime,dtype,api_key)
                st.session_state["scan_extracted"]=result; st.session_state["scan_doc_type"]=dtype
                if "_error" not in result: apply_extraction(dtype,result)
                st.rerun()
        with c2:
            notes=st.text_input("Notes",placeholder="e.g. Maputo run Apr 2026",key="scan_notes")
            if st.button("💾 Save Document",use_container_width=True):
                ext=st.session_state.get("scan_extracted") or {}
                doc_id=save_doc(tid or 0,drv_id,dtype,uploaded.name,fbytes,mime,ext,notes)
                if doc_id:
                    st.success(f"✅ Document #{doc_id} saved — see **My Docs** tab")
                    st.session_state["scan_extracted"]=None

    ext=st.session_state.get("scan_extracted")
    if ext:
        if "_error" in ext:
            st.error(f"❌ Extraction failed: {ext['_error']}")
        else:
            stype=st.session_state.get("scan_doc_type",dtype)
            icons={"Job Order":"📋","Fuel Receipt":"⛽","Weighbridge Ticket":"⚖️","Delivery Note":"📦","Other Document":"📄"}
            key_lbl={"job_number":"Job #","date":"Date","client_name":"Client","origin":"From","destination":"To",
                      "truck_registration":"Truck","weight_kg":"Weight (kg)","cargo_description":"Cargo",
                      "seal_number":"Seal","volume_litres":"Litres","unit_price":"Price/L","total_amount":"Total",
                      "station_name":"Station","odometer_km":"Odometer","fuel_type":"Product",
                      "gross_weight_kg":"Gross (kg)","tare_weight_kg":"Tare (kg)","net_weight_kg":"Net (kg)",
                      "quality_pct":"Quality %","ticket_number":"Ticket #","driver":"Driver"}
            st.markdown(f'<div class="ext-banner"><div style="font-size:.62rem;font-weight:800;letter-spacing:.14em;color:#34d399;text-transform:uppercase;margin-bottom:10px;">'
                        f'{icons.get(stype,"📄")} Extracted from {stype} — form auto-filled ✅</div>'
                        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">',unsafe_allow_html=True)
            for k,v in [(key_lbl.get(k,k.replace("_"," ").title()),v) for k,v in ext.items()
                         if v is not None and not k.startswith("_")][:16]:
                st.markdown(f"<div style='background:rgba(15,23,42,.4);border-radius:7px;padding:6px 10px;'>"
                            f"<div style='font-size:.6rem;color:#64748b;text-transform:uppercase;'>{k}</div>"
                            f"<div style='font-size:.84rem;color:#e2e8f0;font-weight:600;'>{v}</div></div>",unsafe_allow_html=True)
            st.markdown("</div></div>",unsafe_allow_html=True)
            dest={"Job Order":"🚛 Trip Log","Fuel Receipt":"⛽ Fuel","Weighbridge Ticket":"🚛 Trip Log"}.get(stype)
            if dest: st.info(f"✅ Values ready in **{dest}** tab — go there to review and submit.")

# ── TAB 2: TRIP LOG (5 fields, fast) ──────────────────────────────────────────
with tab_trip:
    st.markdown("### 🚛 Log Trip")
    st.caption("5 fields · under 60 seconds · revenue & behaviour not required")
    if not tid:
        st.info("Select a truck above.")
    else:
        pf=st.session_state.get("pf_trip",{})
        last_fuel=get_last_fuel(tid)
        avg_eff  =get_avg_eff(tid)
        auto_odo =float(last_fuel[1]) if last_fuel else cur_odo
        auto_fuel=float(last_fuel[0]) if last_fuel else 0.0
        if pf: st.markdown('<div class="pf-banner">📋 <b>Pre-filled from scanned document</b> — review values below then submit</div>',unsafe_allow_html=True)

        with st.form("trip_v5",clear_on_submit=True):
            st.markdown('<div class="sec">📍 Route</div>',unsafe_allow_html=True)
            c1,c2=st.columns(2)
            with c1:
                orig_idx=LOCATIONS.index(pf["origin"]) if pf.get("origin") in LOCATIONS else 0
                origin=st.selectbox("From",LOCATIONS,index=orig_idx)
            with c2:
                dopts=[l for l in LOCATIONS if l!=origin]
                didx=dopts.index(pf["destination"]) if pf.get("destination") in dopts else 0
                destination=st.selectbox("To",dopts,index=didx)
            auto_d=est_dist(origin,destination); auto_t=det_terrain(origin,destination)
            st.markdown(f'<div class="info-strip">📏 <b>{auto_d:.0f} km</b> auto · 🏔️ <b>{auto_t}</b> · ⛽ Expected <b>~{auto_d*(28/100):.0f} L</b>'
                        +(f' · Avg <b>{avg_eff:.2f} km/L</b>' if avg_eff else '')+'</div>',unsafe_allow_html=True)

            st.markdown('<div class="sec">🔢 Odometer & Fuel</div>',unsafe_allow_html=True)
            c3,c4=st.columns(2)
            with c3:
                odometer=st.number_input("Odometer at Trip End (km)",min_value=0.0,
                    value=float(pf.get("odometer",auto_odo if auto_odo>0 else cur_odo)),step=1.0,
                    help="Most important — read from your dashboard")
            with c4:
                fuel_cons=st.number_input("Fuel Used (L)",min_value=0.0,
                    value=float(pf.get("fuel_consumed",auto_fuel)),step=5.0,
                    help="From receipt or consumption estimate")

            st.markdown('<div class="sec">📦 Cargo (optional)</div>',unsafe_allow_html=True)
            c5,c6,c7=st.columns(3)
            with c5: load_kg=st.number_input("Load (kg)",min_value=0.0,value=float(pf.get("load_kg") or 0),step=100.0)
            with c6: borders=st.number_input("Borders",min_value=0,value=int(pf.get("border",0)),step=1)
            with c7: on_time=st.selectbox("Delivered?",["Yes","No","Partial"],index=0)
            job_ref=st.text_input("Job Reference (optional)",value=pf.get("job_ref",""),
                                   placeholder="e.g. CONCO-2026-0416-01")
            trip_date=st.date_input("Date",value=date.today())
            sub=st.form_submit_button("✅ Log Trip",type="primary",use_container_width=True)

        if sub:
            if odometer<=0 and fuel_cons<=0: st.error("Enter at least the odometer reading or fuel used.")
            else:
                dist=max(auto_d,max(0.0,odometer-cur_odo))
                eff =dist/fuel_cons if (dist>0 and fuel_cons>0) else 0
                drv_exp=int(sel_row[9] or 5) if sel_row else 5
                rec={"truck_id":tid,"origin":origin,"destination":destination,"distance":dist,
                     "load_kg":load_kg,"date":trip_date.strftime("%Y-%m-%d"),"fuel_consumed":fuel_cons,
                     "fuel_efficiency":eff,"duration_h":0,"border_crossings":borders,"terrain":auto_t,
                     "odometer":odometer,"on_time":on_time=="Yes","driver_exp":drv_exp}
                if connected and save_trip(rec):
                    st.success(f"✅ Trip saved — **{origin} → {destination}** · {dist:.0f} km"+(f" · {eff:.2f} km/L" if eff>0 else ""))
                    if eff>0 and avg_eff:
                        d=(eff-avg_eff)/avg_eff*100
                        col="#34d399" if d>=0 else "#f87171"; arr="↑" if d>=0 else "↓"
                        st.markdown(f"<div style='font-size:.82rem;color:{col};'>Efficiency: <b>{eff:.2f} km/L</b> {arr} {abs(d):.0f}% vs your average</div>",unsafe_allow_html=True)
                    st.session_state["pf_trip"]={}
                else:
                    enqueue(rec,"trip"); st.warning("📶 Offline — trip queued.")
                st.rerun()

# ── TAB 3: FUEL (scan → pre-fill → save) ───────────────────────────────────────
with tab_fuel:
    st.markdown("### ⛽ Log Fuel Fill-Up")
    st.caption("Scan your receipt in the 📷 Scan tab — values auto-fill here.")
    if not tid: st.info("Select a truck above.")
    else:
        pff=st.session_state.get("pf_fuel",{})
        last_fill=get_last_fuel(tid)
        if pff: st.markdown('<div class="pf-banner">⛽ <b>Pre-filled from scanned receipt</b> — review and save</div>',unsafe_allow_html=True)
        if last_fill:
            ks=cur_odo-float(last_fill[1])
            st.markdown(f'<div class="info-strip">Last fill: <b>{last_fill[2]}</b> · <b>{last_fill[0]:.0f} L</b> · <b>{ks:,.0f} km</b> since</div>',unsafe_allow_html=True)
        with st.form("fuel_v5",clear_on_submit=True):
            st.markdown('<div class="sec">🏪 Station</div>',unsafe_allow_html=True)
            pf_st=pff.get("station","")
            st_idx=next((i for i,s in enumerate(KNOWN_STATIONS) if pf_st.lower() in s.lower()),len(KNOWN_STATIONS)-1) if pf_st else 0
            st_choice=st.selectbox("Station",KNOWN_STATIONS,index=st_idx)
            station_name=st.text_input("Enter Station Name",value=pf_st) if st_choice=="Other / Enter manually" else st_choice
            rec_no=st.text_input("Receipt Number",value=pff.get("receipt_no",""),placeholder="e.g. 998877665")
            st.markdown('<div class="sec">🛢️ Fuel Details</div>',unsafe_allow_html=True)
            c1,c2,c3=st.columns(3)
            with c1: fa=st.number_input("Litres Added",min_value=1.0,max_value=float(tank_cap+50),value=float(pff.get("fuel_added") or 150.0),step=5.0)
            with c2: cpl=st.number_input("Price/Litre (E)",min_value=5.0,value=float(pff.get("cost_per_L") or FUEL_PRICE_DEFAULT),step=0.05)
            with c3: ft=st.selectbox("Product",["Diesel 50PPM","Diesel 500PPM","Petrol 93","Petrol 95","Diesel (Generic)"],index=0)
            tc=fa*cpl; fp=min(100,fa/tank_cap*100)
            p1,p2,p3=st.columns(3)
            p1.metric("Total Cost",f"E {tc:,.2f}"); p2.metric("Tank Fill",f"{fp:.0f}%"); p3.metric("Est. Range",f"~{fa/(28/100):.0f} km")
            st.markdown('<div class="sec">🔢 Odometer (from receipt)</div>',unsafe_allow_html=True)
            odo_f=st.number_input("Odometer at Fill-Up",min_value=0.0,value=float(pff.get("odometer") or cur_odo),step=1.0)
            full_t=st.checkbox("Filled to full tank",value=True)
            fd=st.date_input("Date",value=date.today(),key="fuel_date")
            fs=st.form_submit_button("⛽ Save Fill-Up",type="primary",use_container_width=True)
        if fs:
            rec={"truck_id":tid,"date":fd.strftime("%Y-%m-%d"),"fuel_added":fa,"odometer":odo_f,
                 "cost_per_liter":cpl,"station":station_name,"fuel_type":ft,"full_tank":full_t,
                 "notes":f"Receipt: {rec_no}" if rec_no else ""}
            if connected and save_fuel(rec):
                st.success(f"✅ Fill-up saved — **{fa:.0f} L** @ E{cpl:.2f}/L = **E {tc:,.2f}**")
                if last_fill and full_t:
                    km=odo_f-float(last_fill[1])
                    if km>0 and fa>0:
                        ef=km/fa; col="#34d399" if ef>=3.0 else "#fbbf24"
                        st.markdown(f"<div style='color:{col};font-size:.84rem;'>Tank-to-tank: <b>{ef:.2f} km/L</b> over {km:,.0f} km · E {tc/km:.2f}/km</div>",unsafe_allow_html=True)
                st.session_state["pf_fuel"]={}
            else: enqueue(rec,"fuel"); st.warning("📶 Queued offline.")
            st.rerun()

# ── TAB 4: INCIDENT ───────────────────────────────────────────────────────────
with tab_evt:
    st.markdown("### 🚨 Report Incident")
    st.caption("Fleet manager notified immediately for High / Critical events.")
    if not tid: st.info("Select a truck above.")
    else:
        with st.form("evt_v5",clear_on_submit=True):
            c1,c2=st.columns(2)
            with c1: etype=st.selectbox("Event Type",EVENT_TYPES)
            with c2: sev=st.selectbox("Severity",["Low","Medium","High","Critical"])
            sc={"Low":"#60a5fa","Medium":"#fbbf24","High":"#f97316","Critical":"#f87171"}.get(sev,"#60a5fa")
            si={"Low":"ℹ️","Medium":"⚠️","High":"🔶","Critical":"🚨"}.get(sev,"ℹ️")
            st.markdown(f'<div style="background:rgba(15,23,42,.5);border:1px solid {sc}40;border-radius:8px;padding:6px 12px;font-size:.76rem;color:{sc};">'
                        f'{si} <b>{sev}</b> — {"Fleet manager alerted immediately." if sev in ("High","Critical") else "Logged for fleet manager."}</div>',unsafe_allow_html=True)
            eloc =st.text_input("Location",placeholder="e.g. N2 near Oshoek border")
            edesc=st.text_area("What happened?",placeholder="Describe event, action taken, current status.",height=80)
            edate=st.date_input("Date",value=date.today(),key="evt_date")
            esub =st.form_submit_button("🚨 Submit Report",type="primary",use_container_width=True)
        if esub:
            if not edesc.strip(): st.error("Please describe what happened.")
            else:
                rec={"truck_id":tid,"date":edate.strftime("%Y-%m-%d"),"event_type":etype,"severity":sev,
                     "location":eloc,"description":edesc,"odometer":cur_odo}
                if connected and save_event(rec):
                    st.success("✅ Incident reported.")
                    if sev in ("High","Critical"): st.error(f"🚨 {sev.upper()} incident recorded.")
                else: enqueue(rec,"event"); st.warning("📶 Queued offline.")

# ── TAB 5: MY JOBS (no revenue) ───────────────────────────────────────────────
with tab_jobs:
    st.markdown("### 📋 My Jobs")
    st.caption("All trips logged for your truck. Revenue is managed by the fleet manager.")
    if not tid: st.info("Select a truck above.")
    elif not connected: st.warning("⚠️ Database not reachable.")
    else:
        avg_eff=get_avg_eff(tid); jobs=get_driver_jobs(tid)
        if jobs:
            m1,m2,m3,m4=st.columns(4)
            m1.metric("Total Jobs",len(jobs))
            m2.metric("Total Distance",f"{sum(r[4] or 0 for r in jobs):,.0f} km")
            effs=[r[7] for r in jobs if r[7] and r[7]>0]
            m3.metric("Avg Efficiency",f"{sum(effs)/len(effs):.2f} km/L" if effs else "—")
            m4.metric("10-Trip Avg",f"{avg_eff:.2f} km/L" if avg_eff else "—")
            st.markdown("")
        if not jobs: st.info("No jobs logged yet. Use **🚛 Log Trip** to record your first trip.")
        else:
            for row in jobs:
                (trip_id,tdate,orig,dest,dist,load,fuel,eff,dur,bords,ontime,terrain,weather)=row
                ec,arr="#94a3b8",""
                if eff and avg_eff:
                    d=(eff-avg_eff)/avg_eff
                    ec="#34d399" if d>=.05 else ("#f87171" if d<-.15 else "#fbbf24")
                    arr="↑" if d>=.05 else ("↓" if d<-.10 else "→")
                otb="✅" if ontime==1 else ("⚠️" if ontime==0 else "")
                st.markdown(f"""<div class="job-card">
                    <div class="job-route">{orig} → {dest}<span style="float:right;font-size:.71rem;color:#64748b;">{tdate} #{trip_id}</span></div>
                    <div class="job-meta">
                        {'<span>📏 '+f"{dist:.0f} km"+'</span>' if dist else ''}
                        {'<span>⛽ '+f"{fuel:.0f} L"+'</span>' if fuel else ''}
                        {'<span style="color:'+ec+';font-weight:700;">'+arr+' '+f"{eff:.2f} km/L"+'</span>' if eff else ''}
                        {'<span>📦 '+f"{load:,.0f} kg"+'</span>' if load else ''}
                        {'<span>🛂 '+str(bords)+' border(s)</span>' if bords else ''}
                        {'<span>'+otb+' On time</span>' if otb else ''}
                        {'<span>🌤️ '+weather+'</span>' if weather else ''}
                    </div></div>""",unsafe_allow_html=True)

# ── TAB 6: MY DOCUMENTS ────────────────────────────────────────────────────────
with tab_docs:
    st.markdown("### 🗂️ My Documents")
    st.caption("All receipts, job orders and other documents you've scanned and saved.")
    if not connected: st.warning("⚠️ Database not reachable.")
    else:
        docs=get_driver_docs(tid or 0,drv_id)
        if not docs: st.info("No documents saved yet. Use **📷 Scan Docs** to photograph and save documents.")
        else:
            dtypes={}
            for d in docs: dtypes[d[2]]=dtypes.get(d[2],0)+1
            st.markdown("<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:1rem;'>"
                        +"".join(f"<div style='background:rgba(30,58,138,.4);border:1px solid rgba(96,165,250,.25);border-radius:20px;padding:3px 12px;font-size:.73rem;color:#93c5fd;'>{t}: {n}</div>" for t,n in dtypes.items())
                        +"</div>",unsafe_allow_html=True)
            icons={"Job Order":"📋","Fuel Receipt":"⛽","Weighbridge Ticket":"⚖️","Delivery Note":"📦","Other Document":"📄"}
            for doc in docs:
                doc_id,udate,dtype,fname,fsize,ext_str,linked,notes=doc
                icon=icons.get(dtype,"📄")
                with st.expander(f"{icon} **{dtype}** — {fname or 'document'} · {udate[:16] if udate else ''}"):
                    ci,ce=st.columns([3,2])
                    with ci:
                        st.markdown(f'<div class="doc-card"><div style="font-size:.62rem;color:#94a3b8;text-transform:uppercase;margin-bottom:6px;">Document Info</div>'
                                    f'<div style="font-size:.82rem;color:#e2e8f0;"><b>Type:</b> {dtype}</div>'
                                    f'<div style="font-size:.82rem;color:#e2e8f0;"><b>Saved:</b> {udate}</div>'
                                    +(f'<div style="font-size:.82rem;color:#e2e8f0;"><b>Size:</b> {fmt_size(fsize)}</div>' if fsize else '')
                                    +(f'<div style="font-size:.82rem;color:#6ee7b7;"><b>Notes:</b> {notes}</div>' if notes else '')
                                    +'</div>',unsafe_allow_html=True)
                    with ce:
                        if ext_str and ext_str!="{}":
                            try:
                                ext=json.loads(ext_str)
                                if ext and "_error" not in ext:
                                    st.markdown('<div style="font-size:.62rem;color:#94a3b8;text-transform:uppercase;margin-bottom:6px;">Extracted Data</div>',unsafe_allow_html=True)
                                    for k,v in list(ext.items())[:8]:
                                        if v and not k.startswith("_"):
                                            st.markdown(f"<div style='font-size:.75rem;color:#e2e8f0;margin-bottom:2px;'><span style='color:#64748b;'>{k.replace('_',' ').title()}:</span> {v}</div>",unsafe_allow_html=True)
                            except: pass

# ── TAB 7: PROFILE ────────────────────────────────────────────────────────────
with tab_prof:
    st.markdown("### 👤 My Profile")
    if not tid or not sel_row: st.info("Select a truck above.")
    else:
        (t_id,t_reg,t_driver,t_mile,t_tank,t_did,t_lic,t_phone,t_idn,t_exp,t_routes,t_certs,t_stat,t_model)=sel_row
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
        st.markdown("#### Update Contact Details")
        with st.form("prof_v5",clear_on_submit=False):
            np=st.text_input("Phone",value=t_phone or "",placeholder="+268 7xxx xxxx")
            nl=st.text_input("License Number",value=t_lic or "")
            ni=st.text_input("National ID / Passport",value=t_idn or "")
            nc=st.text_input("Certifications",value=t_certs or "",placeholder="e.g. Hazmat, Refrigerated")
            nr=st.text_input("Assigned Routes",value=t_routes or "",placeholder="e.g. Eswatini, South Africa")
            sp=st.form_submit_button("💾 Save",type="primary",use_container_width=True)
        if sp and connected:
            if update_driver_profile(tid, np, nl, ni, nc, nr):
                st.success("✅ Profile updated.")
                st.rerun()

# ── TAB 8: SYNC ───────────────────────────────────────────────────────────────
with tab_sync:
    st.markdown("### 🔄 Sync & Status")
    tp=qcount("trip")+qcount("fuel")+qcount("event")
    s1,s2,s3,s4=st.columns(4)
    s1.metric("DB Status","🟢 Live" if connected else "🔴 Offline")
    s2.metric("Trips",qcount("trip")); s3.metric("Fuel",qcount("fuel")); s4.metric("Events",qcount("event"))
    if tp==0: st.success("✅ All records synced.")
    elif not connected: st.error("⚠️ Database not reachable.")
    else:
        if st.button("🔄 Sync Now",use_container_width=True):
            r=sync_all(); synced=r["trips"]+r["fuel"]+r["events"]
            if synced: st.success(f"✅ Synced: {r['trips']} trip(s) · {r['fuel']} fuel · {r['events']} event(s)")
            if r["failed"]: st.warning(f"⚠️ {r['failed']} could not sync.")
            elif synced: st.balloons()
    if tp:
        st.markdown("---")
        for rec in st.session_state.get("offline_trip",[]):
            st.markdown(f'<div class="queue-item"><b style="color:#fbbf24;">TRIP</b> {rec.get("origin","?")} → {rec.get("destination","?")} · {rec.get("date","")}</div>',unsafe_allow_html=True)
        for rec in st.session_state.get("offline_fuel",[]):
            st.markdown(f'<div class="queue-item"><b style="color:#fbbf24;">FUEL</b> {rec.get("fuel_added",0):.0f} L @ {rec.get("station","?")} · {rec.get("date","")}</div>',unsafe_allow_html=True)
        for rec in st.session_state.get("offline_event",[]):
            st.markdown(f'<div class="queue-item"><b style="color:#fbbf24;">EVENT</b> {rec.get("event_type","?")} · {rec.get("severity","")} · {rec.get("date","")}</div>',unsafe_allow_html=True)

st.divider()
st.markdown(f"<div style='text-align:center;font-size:.7rem;color:#475569;'>KSM Smart Freight · Driver Terminal v5.0 · {drv_id}</div>",unsafe_allow_html=True)
