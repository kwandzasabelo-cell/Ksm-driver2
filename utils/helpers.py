# utils/helpers.py — Shared utility functions
from __future__ import annotations
import os
import logging
import streamlit as st
import pandas as pd
import plotly.express as px


def save_uploaded_image(uploaded_file, truck_id) -> str | None:
    if uploaded_file:
        os.makedirs("truck_photos", exist_ok=True)
        path = f"truck_photos/truck_{truck_id}.png"
        with open(path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return path
    return None


def retrain_risk_model(ml_risk_predictor) -> None:
    from core.database import get_connection
    with st.spinner("Training risk model…"):
        conn = get_connection()
        success, result = ml_risk_predictor.train_from_database(conn)
        conn.close()
        if success:
            mae, r2, n, importances = result
            st.session_state["risk_model_metrics"] = (mae, r2, n, importances)
            st.success(f"✅ Risk model trained on **{n} trips** — MAE: {mae:.1f} · R²: {r2:.2f}")
            imp_df = (
                pd.DataFrame({
                    "feature":    ml_risk_predictor.feature_columns,
                    "importance": importances,
                })
                .sort_values("importance", ascending=False)
            )
            with st.expander("Risk Factor Importance"):
                fig = px.bar(
                    imp_df.head(8), x="importance", y="feature",
                    orientation="h", title="Top Risk Factors",
                    color="importance", color_continuous_scale="Reds",
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(
                f"⚠️ Risk model not trained: **{result}**\n\n"
                f"Run `python seed_training_data.py` from the `ksm_fixed` folder to populate "
                f"the database with 60 realistic training trips, then retrain."
            )


def retrain_fuel_model(fuel_model) -> None:
    from core.database import get_connection
    with st.spinner("Training fuel model…"):
        conn = get_connection()
        success, result = fuel_model.train_from_database(conn)
        conn.close()
        if success:
            mae, rmse, r2, n, importances = result
            st.session_state["fuel_model_metrics"] = (mae, r2, n, importances)
            st.success(
                f"✅ Fuel model trained on **{n} trips** — "
                f"MAE: {mae:.1f} L · RMSE: {rmse:.1f} L · R²: {r2:.2f} ({r2*100:.0f}% accuracy)"
            )
            imp_df = (
                pd.DataFrame({
                    "feature":    fuel_model.feature_columns,
                    "importance": importances,
                })
                .sort_values("importance", ascending=False)
            )
            with st.expander("Fuel Consumption Factors"):
                fig = px.bar(
                    imp_df.head(8), x="importance", y="feature",
                    orientation="h", title="Top Fuel Factors",
                    color="importance", color_continuous_scale="Blues",
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(
                f"⚠️ Fuel model not trained: **{result}**\n\n"
                f"Run `python seed_training_data.py` from the `ksm_fixed` folder to populate "
                f"the database with 60 realistic training trips, then retrain."
            )
