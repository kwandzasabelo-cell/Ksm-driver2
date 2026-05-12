# ui/user_management.py — User Management Module (managers only)
from __future__ import annotations
from utils.error_handler import safe_page
import pandas as pd
import streamlit as st

from core.auth import (
    get_all_users, create_user, set_user_active,
    change_password, get_access_log,
)
from core.database import get_connection
from utils.exports import export_buttons


@safe_page
def user_management_module() -> None:
    """Full user management — only accessible to authenticated managers."""
    st.subheader("◫ User Management")
    st.caption("Create and manage driver and manager accounts. Only managers can access this module.")

    tab_all, tab_add, tab_pwd, tab_log = st.tabs([
        "👤 All Users",
        "➕ Add New User",
        "🔑 Change Password",
        "📋 Access Log",
    ])

    # ── TAB 1 — ALL USERS ─────────────────────────────────────────────────────
    with tab_all:
        st.markdown("#### All Users")
        users = get_all_users()
        if not users:
            st.info("No users found. Add users in the **➕ Add New User** tab.")
            return

        m1, m2, m3 = st.columns(3)
        total    = len(users)
        managers = sum(1 for u in users if u["role"] == "manager")
        active   = sum(1 for u in users if u["is_active"])
        m1.metric("Total Users", total)
        m2.metric("Managers",    managers)
        m3.metric("Active",      active)
        st.divider()

        for role_group in ["manager", "driver"]:
            group = [u for u in users if u["role"] == role_group]
            if not group:
                continue
            role_label = "Managers" if role_group == "manager" else "▣ Drivers"
            st.markdown(f"**{role_label}** ({len(group)})")

            for u in group:
                is_active  = bool(u["is_active"])
                status_c   = "#34d399" if is_active else "#f87171"
                status_lbl = "Active" if is_active else "Inactive"
                truck_info = f"Truck: {u['truck_reg']}" if u.get("truck_reg") else "No truck assigned"
                last_login = u.get("last_login") or "Never"
                uid        = u.get("user_id") or u.get("username")

                with st.container():
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(
                            f"<div style='background:rgba(15,23,42,0.55);border:1px solid rgba(96,165,250,0.18);"
                            f"border-radius:10px;padding:10px 14px;margin-bottom:6px;'>"
                            f"<div style='display:flex;align-items:center;gap:10px;'>"
                            f"<div style='font-size:.9rem;font-weight:700;color:#e2e8f0;'>"
                            f"{u.get('full_name') or u['username']}</div>"
                            f"<div style='font-size:.68rem;color:#64748b;font-family:monospace;'>@{u['username']}</div>"
                            f"<div style='margin-left:auto;font-size:.68rem;font-weight:700;"
                            f"color:{status_c};background:{status_c}22;border:1px solid {status_c}44;"
                            f"border-radius:20px;padding:2px 10px;'>{status_lbl}</div>"
                            f"</div>"
                            f"<div style='font-size:.72rem;color:#94a3b8;margin-top:4px;'>"
                            f"{truck_info} &nbsp;·&nbsp; Last login: "
                            f"{last_login[:16] if last_login != 'Never' else 'Never'}"
                            f"</div></div>",
                            unsafe_allow_html=True,
                        )
                    with col_btn:
                        confirm_key = f"confirm_{uid}"
                        if st.session_state.get(confirm_key):
                            # Show confirm/cancel pair
                            c1, c2 = st.columns(2)
                            with c1:
                                action_label = "Deactivate" if is_active else "Reactivate"
                                if st.button("✅ Yes", key=f"yes_{uid}", use_container_width=True,
                                             type="primary"):
                                    set_user_active(uid, not is_active)
                                    action_word = "deactivated" if is_active else "reactivated"
                                    st.toast(f"✅ {u['username']} {action_word}.", icon="✅")
                                    st.session_state.pop(confirm_key, None)
                                    st.rerun()
                            with c2:
                                if st.button("❌ No", key=f"no_{uid}", use_container_width=True):
                                    st.session_state.pop(confirm_key, None)
                                    st.rerun()
                        else:
                            if is_active:
                                if st.button("Deactivate", key=f"deact_{uid}",
                                             use_container_width=True):
                                    st.session_state[confirm_key] = True
                                    st.rerun()
                            else:
                                if st.button("Reactivate", key=f"react_{uid}",
                                             use_container_width=True, type="primary"):
                                    st.session_state[confirm_key] = True
                                    st.rerun()

                    # Show confirmation warning below card when pending
                    if st.session_state.get(confirm_key):
                        action_label = "deactivate" if is_active else "reactivate"
                        st.warning(f"⚠️ Are you sure you want to **{action_label}** `{u['username']}`?")

            st.markdown("")

        with st.expander("📋 Full User Table"):
            df = pd.DataFrame(users)
            df = df.drop(columns=["password_hash"], errors="ignore")
            df["is_active"] = df["is_active"].map({1: "✅ Active", 0: "❌ Inactive"})
            st.dataframe(df, use_container_width=True, hide_index=True)
            export_buttons(df, "ksm_users", "Users")

    # ── TAB 2 — ADD NEW USER ──────────────────────────────────────────────────
    with tab_add:
        st.markdown("#### Add New User")
        try:
            conn = get_connection()
            trucks_df = pd.read_sql_query(
                "SELECT truck_id, registration, driver FROM Truck ORDER BY registration", conn)
            conn.close()
        except Exception:
            trucks_df = pd.DataFrame(columns=["truck_id","registration","driver"])

        with st.form("add_user_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("Username / Driver ID",
                    placeholder="e.g. KSM-DRV-0008 or john.smith",
                    help="For drivers use KSM-DRV-XXXX format")
                new_fullname = st.text_input("Full Name", placeholder="e.g. John Smith")
                new_role     = st.selectbox("Role", ["driver","manager"],
                    format_func=lambda r: "▣ Driver" if r == "driver" else "Manager")
            with col2:
                new_password = st.text_input("Password / PIN", type="password",
                    placeholder="Minimum 4 characters")
                new_confirm  = st.text_input("Confirm Password", type="password")
                truck_options = {"— No truck assigned —": None}
                for _, tr in trucks_df.iterrows():
                    label = f"{tr['registration']} ({tr['driver'] or 'unassigned'})"
                    truck_options[label] = int(tr["truck_id"])
                assigned_label    = st.selectbox("Assign Truck (driver only)",
                    list(truck_options.keys()))
                assigned_truck_id = truck_options[assigned_label]

            submit_user = st.form_submit_button("➕ Create User", type="primary",
                use_container_width=True)

        if submit_user:
            errors = []
            if not new_username.strip():  errors.append("Username is required.")
            if not new_fullname.strip():  errors.append("Full name is required.")
            if len(new_password) < 4:     errors.append("Password must be at least 4 characters.")
            if new_password != new_confirm: errors.append("Passwords do not match.")
            if errors:
                for e in errors:
                    st.error(f"❌ {e}")
            else:
                uname = (new_username.strip().upper() if new_role == "driver"
                         else new_username.strip().lower())
                ok, msg = create_user(uname, new_password, new_role,
                                      new_fullname.strip(), assigned_truck_id)
                if ok:
                    st.toast(f"✅ User {uname} created!", icon="✅")
                    st.success(f"✅ User **{uname}** created as "
                               f"{'Driver' if new_role == 'driver' else 'Manager'}.")
                    if assigned_truck_id:
                        st.info(f"▣ Assigned to truck ID {assigned_truck_id}.")
                else:
                    st.error(f"❌ {msg}")

        st.markdown("---")
        st.markdown("""
        **Username conventions**
        - Drivers: `KSM-DRV-XXXX` (auto-uppercased)
        - Managers: any lowercase username

        **Default driver PINs** (must be changed on first login)
        - `1234` for trucks 1, 6, 7 · `5678` for truck 2 · `9012` for truck 3
        """)

    # ── TAB 3 — CHANGE PASSWORD ───────────────────────────────────────────────
    with tab_pwd:
        st.markdown("#### Change Password")
        users = get_all_users()
        if not users:
            st.info("No users yet.")
        else:
            user_options = {
                f"{u.get('full_name') or u['username']} (@{u['username']}) [{u['role']}]": u.get("user_id") or u["username"]
                for u in users
            }
            selected_label = st.selectbox("Select User", list(user_options.keys()))
            selected_uid   = user_options[selected_label]

            with st.form("change_pwd_form", clear_on_submit=True):
                new_pwd1 = st.text_input("New Password", type="password",
                    placeholder="Minimum 4 characters")
                new_pwd2 = st.text_input("Confirm New Password", type="password")
                change_btn = st.form_submit_button("🔑 Update Password", type="primary",
                    use_container_width=True)

            if change_btn:
                if len(new_pwd1) < 4:
                    st.error("❌ Password must be at least 4 characters.")
                elif new_pwd1 != new_pwd2:
                    st.error("❌ Passwords do not match.")
                else:
                    ok, msg = change_password(selected_uid, new_pwd1)
                    if ok:
                        st.toast("✅ Password updated!", icon="🔑")
                        st.success(f"✅ Password updated for **{selected_label}**.")
                    else:
                        st.error(f"❌ {msg}")

    # ── TAB 4 — ACCESS LOG ────────────────────────────────────────────────────
    with tab_log:
        st.markdown("#### Access Log")
        st.caption("Last 200 login events.")
        logs = get_access_log(200)
        if not logs:
            st.info("No login events recorded yet.")
        else:
            df = pd.DataFrame(logs)
            df = df.rename(columns={
                "log_id":     "Log #",
                "username":   "Username",
                "role":       "Role",
                "login_time": "Login Time",
                "truck_id":   "Truck ID",
                "truck_reg":  "Truck Reg.",
            })
            df["Role"] = df["Role"].map(
                {"manager":"Manager","driver":"▣ Driver"}).fillna(df["Role"])

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Logins",   len(df))
            m2.metric("Manager Logins", int((df["Role"] == "Manager").sum()))
            m3.metric("Driver Logins",  int((df["Role"] == "▣ Driver").sum()))

            show_cols = [c for c in ["Log #","Username","Role","Login Time","Truck Reg."]
                         if c in df.columns]
            st.dataframe(df[show_cols], use_container_width=True, hide_index=True)
            export_buttons(df[show_cols], "ksm_access_log", "Access Log")
