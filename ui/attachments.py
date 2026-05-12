# ui/attachments.py — Document Attachment Portal for KSM Smart Freight
# ─────────────────────────────────────────────────────────────────────────────
# Renders an attachment panel next to the command bar.
# Accepts: Receipts, Proof of Payments, Job Orders, Invoices
# Calls Gemini Vision to extract structured data automatically.
# Stores files + extracted JSON in DocumentAttachments SQLite table.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import base64
import io
import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from core.database import get_connection

logger = logging.getLogger(__name__)

# ── Doc type config ────────────────────────────────────────────────────────────
DOC_TYPES = {
    "Job Order":        {"icon": "📋", "color": "rgba(37,99,235,0.18)",  "border": "rgba(96,165,250,0.4)"},
    "Receipt":          {"icon": "🧾", "color": "rgba(5,150,105,0.18)",  "border": "rgba(52,211,153,0.4)"},
    "Proof of Payment": {"icon": "💳", "color": "rgba(124,58,237,0.18)", "border": "rgba(167,139,250,0.4)"},
    "Invoice":          {"icon": "📄", "color": "rgba(217,119,6,0.18)",  "border": "rgba(251,191,36,0.4)"},
}

ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"]

# ── AI extraction prompts per doc type ────────────────────────────────────────
_EXTRACT_PROMPTS = {
    "Job Order": """Extract all data from this job order document. Return ONLY valid JSON with these keys (use null if not found):
{
  "job_number": "...",
  "date": "YYYY-MM-DD",
  "client_name": "...",
  "client_contact": "...",
  "truck_registration": "...",
  "driver": "...",
  "origin": "...",
  "destination": "...",
  "cargo_description": "...",
  "weight_kg": number_or_null,
  "distance_km": number_or_null,
  "rate_per_km": number_or_null,
  "total_amount_SZL": number_or_null,
  "special_instructions": "...",
  "delivery_date": "YYYY-MM-DD or null"
}""",

    "Receipt": """Extract all data from this receipt. Return ONLY valid JSON:
{
  "receipt_number": "...",
  "date": "YYYY-MM-DD",
  "vendor": "...",
  "items": [{"description": "...", "quantity": number, "unit_price": number, "total": number}],
  "subtotal": number_or_null,
  "tax": number_or_null,
  "total_SZL": number_or_null,
  "payment_method": "...",
  "truck_registration": "...",
  "category": "fuel | maintenance | toll | other"
}""",

    "Proof of Payment": """Extract all data from this proof of payment. Return ONLY valid JSON:
{
  "reference_number": "...",
  "date": "YYYY-MM-DD",
  "payer": "...",
  "payee": "...",
  "bank": "...",
  "amount_SZL": number_or_null,
  "currency": "SZL",
  "payment_method": "EFT | cash | card | ...",
  "description": "...",
  "account_number_last4": "..."
}""",

    "Invoice": """Extract all data from this invoice. Return ONLY valid JSON:
{
  "invoice_number": "...",
  "date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD or null",
  "from_company": "...",
  "to_company": "...",
  "to_contact": "...",
  "line_items": [{"description": "...", "quantity": number, "unit_price": number, "total": number}],
  "subtotal": number_or_null,
  "vat": number_or_null,
  "total_SZL": number_or_null,
  "truck_registration": "...",
  "trip_reference": "...",
  "payment_terms": "..."
}""",
}


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Vision extractor
# ─────────────────────────────────────────────────────────────────────────────

def _extract_with_gemini(file_bytes: bytes, mime_type: str, doc_type: str, api_key: str) -> dict:
    """Send document image to Gemini Vision and return extracted structured data."""
    try:
        try:
            from google import genai as _genai
            client = _genai.Client(api_key=api_key)
            b64 = base64.b64encode(file_bytes).decode()
            prompt = _EXTRACT_PROMPTS.get(doc_type, "Extract all data from this document as JSON.")
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=[
                    _genai.types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    prompt,
                ],
            )
            text = response.text.strip()
        except ImportError:
            import google.generativeai as genai_legacy  # type: ignore
            genai_legacy.configure(api_key=api_key)
            model = genai_legacy.GenerativeModel("gemini-2.5-flash-lite")
            b64 = base64.b64encode(file_bytes).decode()
            prompt = _EXTRACT_PROMPTS.get(doc_type, "Extract all data from this document as JSON.")
            response = model.generate_content([
                {"mime_type": mime_type, "data": b64},
                prompt,
            ])
            text = response.text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        return json.loads(text)

    except json.JSONDecodeError:
        return {"_raw": text, "_error": "Could not parse JSON from AI response"}
    except Exception as exc:
        logger.warning("Gemini extraction failed: %s", exc)
        return {"_error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Database helpers
# ─────────────────────────────────────────────────────────────────────────────

def _save_document(
    doc_type: str,
    filename: str,
    file_bytes: bytes,
    mime_type: str,
    extracted: dict,
    notes: str = "",
    linked_entity: str = "",
    linked_id: int | None = None,
) -> int:
    """Insert a document record and return its doc_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO DocumentAttachments
           (upload_date, doc_type, filename, file_data, file_size,
            mime_type, linked_entity, linked_id, extracted_data, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            doc_type,
            filename,
            file_bytes,
            len(file_bytes),
            mime_type,
            linked_entity or "",
            linked_id,
            json.dumps(extracted, ensure_ascii=False),
            notes,
        ),
    )
    doc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def _load_documents(doc_type: str | None = None, limit: int = 50) -> pd.DataFrame:
    conn = get_connection()
    if doc_type:
        df = pd.read_sql_query(
            "SELECT doc_id, upload_date, doc_type, filename, file_size, mime_type, "
            "linked_entity, extracted_data, notes FROM DocumentAttachments "
            "WHERE doc_type=? ORDER BY upload_date DESC LIMIT ?",
            conn, params=(doc_type, limit),
        )
    else:
        df = pd.read_sql_query(
            "SELECT doc_id, upload_date, doc_type, filename, file_size, mime_type, "
            "linked_entity, extracted_data, notes FROM DocumentAttachments "
            "ORDER BY upload_date DESC LIMIT ?",
            conn, params=(limit,),
        )
    conn.close()
    return df


def _get_file_bytes(doc_id: int) -> bytes | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT file_data FROM DocumentAttachments WHERE doc_id=?", (doc_id,)
    ).fetchone()
    conn.close()
    return bytes(row[0]) if row else None


def _delete_document(doc_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM DocumentAttachments WHERE doc_id=?", (doc_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


def _render_extracted_card(data: dict, doc_type: str) -> None:
    """Render extracted fields in a tidy card."""
    cfg = DOC_TYPES.get(doc_type, {"color": "rgba(30,41,59,0.6)", "border": "rgba(148,163,184,0.3)", "icon": "📄"})
    if "_error" in data:
        st.warning(f"⚠️ Extraction issue: {data['_error']}")
        return

    st.markdown(
        f"""<div style='background:{cfg["color"]};border:1px solid {cfg["border"]};
            border-radius:10px;padding:12px 16px;margin-top:6px;'>
            <div style='color:#94a3b8;font-size:11px;font-weight:600;
                text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;'>
            {cfg["icon"]} Extracted Fields</div>""",
        unsafe_allow_html=True,
    )
    pairs = []
    for k, v in data.items():
        if v is None or k.startswith("_"):
            continue
        if isinstance(v, list):
            v = f"{len(v)} item(s)"
        label = k.replace("_", " ").title()
        pairs.append(f"**{label}:** {v}")

    cols = st.columns(2)
    for i, p in enumerate(pairs):
        cols[i % 2].markdown(p, unsafe_allow_html=False)
    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Auto-route extracted data to rightful modules
# ─────────────────────────────────────────────────────────────────────────────

def _auto_route_to_module(doc_type: str, extracted: dict) -> None:
    """
    After AI extraction, inject extracted values into the appropriate module
    via session_state prefill keys (same mechanism as command bar), then
    navigate there so the operator lands on a pre-filled form.

    Routing rules:
      Job Order  → Unified Logistics  (trip log prefill)
      Receipt    → Fuel Tracking if fuel category, else inline summary
      Invoice / Proof of Payment → Statement of Account
    """
    from core.constants import TRIP_PREFILL_KEY, FUEL_PREFILL_KEY, NAV_OVERRIDE_KEY

    if doc_type == "Job Order":
        prefill = {k: v for k, v in {
            "truck_registration": extracted.get("truck_registration"),
            "date":               extracted.get("date") or extracted.get("delivery_date"),
            "start_location":     extracted.get("origin"),
            "end_location":       extracted.get("destination"),
            "distance_km":        extracted.get("distance_km"),
            "load_kg":            extracted.get("weight_kg"),
            "revenue_SZL":        extracted.get("total_amount_SZL"),
        }.items() if v is not None}
        if prefill:
            if "truck_registration" in prefill:
                st.session_state["log_truck_sel"] = prefill["truck_registration"]
            st.session_state[TRIP_PREFILL_KEY] = prefill
            st.session_state[NAV_OVERRIDE_KEY] = "Unified Logistics"
            # NAV_OVERRIDE_KEY only — yizo.py router sets SIDEBAR_MENU_KEY safely before widget creation
            st.info(
                "→ **Job Order extracted** — navigating to **Unified Logistics** with pre-filled trip form. "
                "Review the values and press **Log Trip**.",
                icon="📋",
            )
            st.rerun()

    elif doc_type == "Receipt":
        category = (extracted.get("category") or "").lower()
        if "fuel" in category:
            prefill: dict = {k: v for k, v in {
                "truck_registration": extracted.get("truck_registration"),
                "date":               extracted.get("date"),
                "station_name":       extracted.get("vendor"),
                "notes":              f"Receipt #{extracted.get('receipt_number', '')}",
            }.items() if v is not None}
            # Try to parse litres/price from line items
            for item in extracted.get("items", []):
                desc = (item.get("description") or "").lower()
                if any(w in desc for w in ("litre", "liter", "diesel", "fuel", "petrol")):
                    if item.get("quantity"):
                        prefill["fuel_added_L"] = item["quantity"]
                    if item.get("unit_price"):
                        prefill["cost_per_litre_SZL"] = item["unit_price"]
            if prefill:
                if "truck_registration" in prefill:
                    st.session_state["fuel_truck"] = prefill["truck_registration"]
                st.session_state[FUEL_PREFILL_KEY] = prefill
                st.session_state[NAV_OVERRIDE_KEY] = "Fuel Tracking"
                # NAV_OVERRIDE_KEY only — yizo.py router sets SIDEBAR_MENU_KEY safely before widget creation
                st.info("→ **Fuel receipt extracted** — navigating to **Fuel Tracking** with pre-filled fill-up form.", icon="◉")
                st.rerun()
            else:
                total = extracted.get("total_SZL") or extracted.get("subtotal")
                st.info(f"◉ Fuel receipt saved{f' — Total: E {total:,.2f}' if total else ''}. Open **Fuel Tracking** to log manually.")
        else:
            total = extracted.get("total_SZL") or extracted.get("subtotal")
            vendor = extracted.get("vendor", "?")
            if total:
                st.info(f"🧾 Receipt saved — **E {total:,.2f}** from **{vendor}**")

    elif doc_type in ("Invoice", "Proof of Payment"):
        st.session_state[NAV_OVERRIDE_KEY] = "Statement of Account"
        # NAV_OVERRIDE_KEY only — yizo.py router sets SIDEBAR_MENU_KEY safely before widget creation
        ref   = extracted.get("invoice_number") or extracted.get("reference_number", "")
        total = extracted.get("total_SZL") or extracted.get("amount_SZL")
        msg   = f"📄 **{doc_type}** saved"
        if ref:
            msg += f" · Ref: **{ref}**"
        if total:
            msg += f" · Amount: **E {total:,.2f}**"
        msg += " — opening **Statement of Account**."
        st.info(msg, icon="💳")
        st.rerun()


# Main render function
# ─────────────────────────────────────────────────────────────────────────────

def render_attachment_portal() -> None:
    """
    Render the document attachment portal.
    Call this immediately after render_command_bar() in yizo.py.
    """
    api_key = st.session_state.get("gemini_api_key", "")

    # ── Header ─────────────────────────────────────────────────────────────
    st.markdown(
        """<div style='background:linear-gradient(135deg,rgba(124,58,237,0.55),rgba(217,119,6,0.4));
            border:1px solid rgba(167,139,250,0.25);border-radius:14px;
            padding:14px 20px 10px 20px;margin-bottom:4px;'>
            <div style='display:flex;align-items:center;gap:10px;'>
              <span style='font-size:22px;'>📄</span>
              <div>
                <div style='color:#e0f2fe;font-weight:700;font-size:15px;'>
                  Document Portal
                  <span style='font-size:11px;font-weight:400;color:#94a3b8;margin-left:8px;'>
                    AI auto-extract · job orders · receipts · invoices
                  </span>
                </div>
                <div style='color:#94a3b8;font-size:12px;'>
                  Upload documents — AI reads and auto-fills the data
                </div>
              </div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    tab_upload, tab_library = st.tabs(["⬆ Upload & Extract", "🗂️ Document Library"])

    # ── UPLOAD TAB ──────────────────────────────────────────────────────────
    with tab_upload:
        col_type, col_link = st.columns([2, 2])
        with col_type:
            doc_type = st.selectbox(
                "Document Type",
                list(DOC_TYPES.keys()),
                key="att_doc_type",
                format_func=lambda t: f"{DOC_TYPES[t]['icon']} {t}",
            )
        with col_link:
            linked_entity = st.selectbox(
                "Link to (optional)",
                ["— none —", "Trip", "Truck", "Maintenance", "Fuel Fill-Up"],
                key="att_link_entity",
            )
            if linked_entity != "— none —":
                linked_id = st.number_input(
                    f"{linked_entity} ID", min_value=1, step=1, key="att_link_id"
                )
            else:
                linked_id = None

        uploaded = st.file_uploader(
            f"Drop your {doc_type} here",
            type=["jpg", "jpeg", "png", "webp", "pdf"],
            key="att_uploader",
            help="JPEG, PNG, WEBP, or PDF · max 10 MB",
        )

        notes = st.text_input("Notes (optional)", key="att_notes", placeholder="e.g. Maputo run, April 2026")

        if uploaded:
            file_bytes = uploaded.read()
            mime = uploaded.type or "image/jpeg"

            # Preview
            if mime.startswith("image/"):
                st.image(file_bytes, width=320, caption=uploaded.name)
            else:
                st.info(f"📄 PDF uploaded: **{uploaded.name}** ({_fmt_size(len(file_bytes))})")

            st.markdown("---")

            # Auto-extract button
            col_ext, col_save = st.columns(2)

            with col_ext:
                if st.button(
                    "◈ AI Extract Data",
                    key="att_extract_btn",
                    use_container_width=True,
                    disabled=not api_key,
                    help="Uses Gemini Vision to read and parse the document" if api_key else "Add Gemini API key in sidebar",
                ):
                    with st.spinner(f"Reading {doc_type}…"):
                        extracted = _extract_with_gemini(file_bytes, mime, doc_type, api_key)
                    st.session_state["att_extracted"] = extracted
                    st.success("✅ Extraction complete!")
                    st.rerun()

            if not api_key:
                st.caption("⬆️ Add Gemini API key in sidebar to enable AI extraction.")

            extracted = st.session_state.get("att_extracted", {})
            if extracted:
                _render_extracted_card(extracted, doc_type)

            with col_save:
                if st.button(
                    "💾 Save & Auto-Upload",
                    key="att_save_btn",
                    use_container_width=True,
                    type="primary",
                ):
                    with st.spinner("Saving and routing to modules…"):
                        final_extracted = st.session_state.get("att_extracted", {})
                        doc_id = _save_document(
                            doc_type=doc_type,
                            filename=uploaded.name,
                            file_bytes=file_bytes,
                            mime_type=mime,
                            extracted=final_extracted,
                            notes=notes,
                            linked_entity=linked_entity if linked_entity != "— none —" else "",
                            linked_id=linked_id,
                        )
                    st.success(f"✅ Saved as Document #{doc_id}")

                    # ── AUTO-UPLOAD extracted data to the rightful module ──────
                    if final_extracted and "_error" not in final_extracted:
                        _auto_route_to_module(doc_type, final_extracted)

                    st.session_state.pop("att_extracted", None)
                    st.rerun()

    # ── LIBRARY TAB ─────────────────────────────────────────────────────────
    with tab_library:
        filter_type = st.selectbox(
            "Filter by type",
            ["All"] + list(DOC_TYPES.keys()),
            key="att_lib_filter",
            format_func=lambda t: f"{DOC_TYPES[t]['icon']} {t}" if t in DOC_TYPES else t,
        )

        df = _load_documents(filter_type if filter_type != "All" else None, limit=100)

        if df.empty:
            st.info("No documents saved yet. Upload your first document above.")
        else:
            st.caption(f"Showing {len(df)} document(s)")
            for _, row in df.iterrows():
                doc_id   = int(row["doc_id"])
                dtype    = row["doc_type"]
                cfg      = DOC_TYPES.get(dtype, {"icon": "📄", "color": "rgba(30,41,59,0.6)", "border": "rgba(148,163,184,0.3)"})
                fname    = row["filename"]
                fsize    = _fmt_size(int(row["file_size"])) if row["file_size"] else "?"
                udate    = row["upload_date"][:16] if row["upload_date"] else ""
                link     = row["linked_entity"] or ""

                with st.expander(
                    f"{cfg['icon']} **{dtype}** — {fname}  ·  {udate}  ·  {fsize}",
                    expanded=False,
                ):
                    col_info, col_actions = st.columns([3, 1])
                    with col_info:
                        if link:
                            st.caption(f"🔗 Linked to: {link} #{int(row['linked_id']) if row['linked_id'] else '?'}")
                        if row["notes"]:
                            st.caption(f"📝 {row['notes']}")

                        raw_extracted = row.get("extracted_data", "{}")
                        try:
                            extracted = json.loads(raw_extracted) if raw_extracted else {}
                        except Exception:
                            extracted = {}

                        if extracted and "_error" not in extracted:
                            _render_extracted_card(extracted, dtype)
                        elif extracted.get("_error"):
                            st.warning(f"Extraction error: {extracted['_error']}")

                    with col_actions:
                        # Download button
                        file_bytes = _get_file_bytes(doc_id)
                        if file_bytes:
                            st.download_button(
                                "⬇️ Download",
                                data=file_bytes,
                                file_name=fname,
                                mime=row["mime_type"] or "application/octet-stream",
                                key=f"att_dl_{doc_id}",
                                use_container_width=True,
                            )

                        # Re-extract with AI
                        if api_key and file_bytes:
                            if st.button(
                                "◈ Re-extract",
                                key=f"att_reext_{doc_id}",
                                use_container_width=True,
                            ):
                                with st.spinner("Re-extracting…"):
                                    mime = row["mime_type"] or "image/jpeg"
                                    new_extracted = _extract_with_gemini(file_bytes, mime, dtype, api_key)
                                    conn = get_connection()
                                    conn.execute(
                                        "UPDATE DocumentAttachments SET extracted_data=? WHERE doc_id=?",
                                        (json.dumps(new_extracted, ensure_ascii=False), doc_id),
                                    )
                                    conn.commit()
                                    conn.close()
                                st.success("Re-extracted!")
                                st.rerun()

                        # Delete
                        if st.button(
                            "✕️ Delete",
                            key=f"att_del_{doc_id}",
                            use_container_width=True,
                        ):
                            _delete_document(doc_id)
                            st.rerun()

    st.markdown("---")
