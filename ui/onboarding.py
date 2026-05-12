# ui/onboarding.py — First-run setup wizard for new KSM installations
from __future__ import annotations
import streamlit as st
import pandas as pd
from core.database import get_connection
from core.auth import change_password_by_username


_STEPS = ["Welcome", "Add First Truck", "Add Drivers", "Alerts Setup", "Done"]


def _progress_bar(step: int) -> None:
    pct = int((step / (len(_STEPS) - 1)) * 100)
    st.markdown(
        f"<div style='background:rgba(255,255,255,.07);border-radius:8px;height:8px;margin-bottom:20px;'>"
        f"<div style='background:linear-gradient(90deg,#3b82f6,#8b5cf6);width:{pct}%;height:8px;border-radius:8px;'></div>"
        f"</div>"
        f"<div style='display:flex;justify-content:space-between;font-size:.65rem;color:#64748b;margin-bottom:24px;'>"
        + "".join(
            f"<span style='color:{'#3b82f6' if i <= step else '#475569'};font-weight:{'700' if i==step else '400'};'>{s}</span>"
            for i, s in enumerate(_STEPS)
        )
        + "</div>",
        unsafe_allow_html=True,
    )


def should_show_onboarding() -> bool:
    """Show onboarding if fleet has no trucks yet."""
    try:
        conn = get_connection()
        n = pd.read_sql_query("SELECT COUNT(*) as c FROM Truck", conn)["c"].iloc[0]
        conn.close()
        return int(n) == 0
    except Exception:
        return False


def onboarding_wizard() -> None:
    step = st.session_state.get("_onboard_step", 0)

    st.markdown("## ▣ Welcome to KSM Smart Freight Solutions")
    _progress_bar(step)

    # ── Step 0: Welcome ───────────────────────────────────────────────────────
    if step == 0:
        st.markdown("""
        ### Let's get your fleet set up in 3 minutes.

        This quick setup will help you:
        - ✅ Add your first truck to the system
        - ✅ Create driver accounts
        - ✅ Configure alert notifications
        - ✅ Start tracking trips and fuel

        **Your data stays on your machine** — no cloud account required to get started.
        """)
        if st.button("Get Started →", type="primary", use_container_width=True):
            st.session_state["_onboard_step"] = 1
            st.rerun()

        if st.button("Skip Setup — I'll configure later", use_container_width=True):
            st.session_state["_onboard_done"] = True
            st.rerun()

    # ── Step 1: Add First Truck ───────────────────────────────────────────────
    elif step == 1:
        st.markdown("### Step 1: Add Your First Truck")
        st.caption("You can add more trucks later in Truck Management.")

        with st.form("onboard_truck"):
            reg   = st.text_input("Registration / Number Plate *", placeholder="e.g. SD 123 EZ")
            model = st.text_input("Make & Model", placeholder="e.g. Volvo FH16")
            year  = st.number_input("Year of Manufacture", min_value=1990, max_value=2026, value=2018)
            km    = st.number_input("Current Odometer (km)", min_value=0.0, value=0.0, step=1000.0)
            tank  = st.number_input("Fuel Tank Capacity (L)", min_value=100.0, value=300.0, step=10.0)
            payload = st.number_input("Max Payload (kg)", min_value=1000.0, value=25000.0, step=500.0)
            submitted = st.form_submit_button("Add Truck & Continue →", type="primary",
                                              use_container_width=True)

        if submitted:
            if not reg.strip():
                st.error("❌ Registration is required.")
            else:
                try:
                    from datetime import date
                    conn = get_connection()
                    conn.execute(
                        "INSERT INTO Truck (registration, model, mileage, starting_mileage, "
                        "fuel_tank_capacity, max_payload, year_of_manufacture, created_date, "
                        "last_service_km, truck_status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (reg.strip().upper(), model.strip(), km, km,
                         tank, payload, year, date.today().isoformat(), km, "ACTIVE")
                    )
                    conn.commit(); conn.close()
                    st.toast(f"✅ Truck {reg.upper()} added!", icon="▣")
                    st.session_state["_onboard_step"] = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")

        if st.button("← Back"):
            st.session_state["_onboard_step"] = 0
            st.rerun()

    # ── Step 2: Add Drivers ───────────────────────────────────────────────────
    elif step == 2:
        st.markdown("### Step 2: Add Your Drivers")
        st.caption("Drivers will log in to the Driver Terminal using their ID and PIN.")

        added = st.session_state.get("_onboard_drivers_added", [])
        if added:
            st.success(f"✅ {len(added)} driver(s) added: {', '.join(added)}")

        with st.form("onboard_driver"):
            col1, col2 = st.columns(2)
            with col1:
                drv_id   = st.text_input("Driver ID", placeholder="e.g. KSM-DRV-0001")
                drv_name = st.text_input("Full Name", placeholder="e.g. John Dube")
            with col2:
                drv_pin  = st.text_input("PIN (4–6 digits)", type="password", placeholder="e.g. 1234")
                drv_pin2 = st.text_input("Confirm PIN", type="password")
            add_btn = st.form_submit_button("➕ Add Driver", use_container_width=True)

        if add_btn:
            from core.auth import create_user
            if not drv_id.strip() or not drv_name.strip():
                st.error("❌ Driver ID and name are required.")
            elif len(drv_pin) < 4:
                st.error("❌ PIN must be at least 4 digits.")
            elif drv_pin != drv_pin2:
                st.error("❌ PINs do not match.")
            else:
                ok, msg = create_user(drv_id.strip().upper(), drv_pin,
                                      "driver", drv_name.strip())
                if ok:
                    added.append(drv_id.upper())
                    st.session_state["_onboard_drivers_added"] = added
                    st.toast(f"✅ Driver {drv_id.upper()} added!", icon="👤")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Back", use_container_width=True):
                st.session_state["_onboard_step"] = 1
                st.rerun()
        with c2:
            lbl = "Continue →" if added else "Skip — Add Drivers Later →"
            if st.button(lbl, type="primary", use_container_width=True):
                st.session_state["_onboard_step"] = 3
                st.rerun()

    # ── Step 3: Alerts Setup ──────────────────────────────────────────────────
    elif step == 3:
        st.markdown("### Step 3: Alert Notifications")
        st.caption(
            "Get notified when trucks are overdue for service or when high-risk trips are logged. "
            "This is optional — you can configure it later in your `.env` file."
        )

        st.info(
            "📋 **To set up alerts:**\n\n"
            "1. Find the `.env.example` file in your project folder\n"
            "2. Copy it to `.env`\n"
            "3. Fill in your email (SMTP) or WhatsApp (Twilio) details\n"
            "4. Restart the app\n\n"
            "Alerts will then be sent automatically when service is overdue or risk scores are high."
        )

        try:
            from core.secrets import smtp_host, twilio_sid
            if smtp_host():
                st.success("✅ Email alerts are configured.")
            if twilio_sid():
                st.success("✅ WhatsApp alerts are configured.")
        except Exception:
            pass

        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Back", use_container_width=True):
                st.session_state["_onboard_step"] = 2
                st.rerun()
        with c2:
            if st.button("Finish Setup →", type="primary", use_container_width=True):
                st.session_state["_onboard_step"] = 4
                st.rerun()

    # ── Step 4: Done ──────────────────────────────────────────────────────────
    elif step == 4:
        st.success("### ◆ You're all set!")
        st.markdown("""
        Your KSM Fleet Management system is ready to use.

        **What to do next:**
        - ↗ Log your first trip in **Unified Logistics**
        - ◉ Record a fuel fill-up in **Fuel Tracking**
        - ▦ Train your AI models once you have 10+ trips
        - ◫ Add more drivers and trucks in **User Management**

        The AI risk and fuel models will activate automatically as your data grows.
        """)
        if st.button("▣ Open Fleet Dashboard →", type="primary", use_container_width=True):
            st.session_state["_onboard_done"] = True
            st.session_state.pop("_onboard_step", None)
            st.session_state.pop("_onboard_drivers_added", None)
            st.rerun()
