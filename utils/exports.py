# utils/exports.py — CSV / Excel export helpers for KSM tables
from __future__ import annotations
import io
import pandas as pd
import streamlit as st


def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Data") -> bytes:
    """Return an Excel (.xlsx) file as bytes from a DataFrame."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buf.getvalue()


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Return a UTF-8 CSV file as bytes from a DataFrame."""
    return df.to_csv(index=False).encode("utf-8")


def export_buttons(df: pd.DataFrame, filename_stem: str, sheet_name: str = "Data") -> None:
    """Render side-by-side CSV and Excel download buttons for a DataFrame."""
    if df is None or df.empty:
        return
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            label="⬇️ Export CSV",
            data=df_to_csv_bytes(df),
            file_name=f"{filename_stem}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            label="⬇️ Export Excel",
            data=df_to_excel_bytes(df, sheet_name),
            file_name=f"{filename_stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
