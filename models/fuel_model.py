# models/fuel_model.py — Fuel consumption ML model and physics estimator
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from core.config import (
    MAX_PAYLOAD_KG, FUEL_PRICE_DEFAULT,
    FUEL_CONSUMPTION_BASE_L_PER_100KM,
    WEIGHT_FACTOR_COEFF, GRADIENT_FACTOR_COEFF, ROAD_FACTOR_COEFF,
)

class FuelConsumptionModel:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_columns = [
            'distance', 'load_ratio', 'avg_gradient', 'road_quality',
            'terrain_type_encoded', 'weather_condition_encoded',
            'hard_braking_events', 'idle_time_minutes',
            'driver_experience_years', 'truck_age_years',
            'border_crossings',
        ]
        self.terrain_mapping = {'Flat': 0, 'Rolling': 1, 'Mountainous': 2}
        self.weather_mapping = {'Clear': 0, 'Rain': 1, 'Storm': 2, 'Fog': 3, 'High Wind': 4}

    def prepare_features(self, trip_data, truck_data, driver_data):
        features = {
            'distance':                trip_data.get('distance', 0),
            'load_ratio':              trip_data.get('weight', 0) / MAX_PAYLOAD_KG,
            'avg_gradient':            trip_data.get('avg_gradient', 0),
            'road_quality':            trip_data.get('road_quality', 0.75),
            'terrain_type_encoded':    self.terrain_mapping.get(trip_data.get('terrain', 'Rolling'), 1),
            'weather_condition_encoded': self.weather_mapping.get(trip_data.get('weather', 'Clear'), 0),
            'hard_braking_events':     driver_data.get('hard_braking_events', 0),
            'idle_time_minutes':       driver_data.get('idle_time_minutes', 0),
            'driver_experience_years': driver_data.get('experience_years', 5),
            'truck_age_years':         truck_data.get('truck_age_years', 0),
            'border_crossings':        trip_data.get('border_crossings', 0),
        }
        arr = np.array([features[c] for c in self.feature_columns])
        return arr.reshape(1, -1)

    def calculate_theoretical_fuel_consumption(self, distance, weight, gradient,
                                               road_quality, weather: str = "Clear"):
        """Physics-based fuel estimate used when the ML model is not yet trained.
        Factors: weight, gradient, road quality, and weather (speed penalty → more fuel).
        """
        # Weather speed penalties from config — slower speed = more fuel per km
        weather_fuel_penalty = {
            "Clear": 1.00, "Rain": 1.08, "Storm": 1.18,
            "Fog": 1.10, "High Wind": 1.12,
        }
        base = FUEL_CONSUMPTION_BASE_L_PER_100KM
        weight_factor   = 1 + (weight / MAX_PAYLOAD_KG) * WEIGHT_FACTOR_COEFF
        gradient_factor = 1 + max(0, gradient) * GRADIENT_FACTOR_COEFF
        road_factor     = 1 + (1 - road_quality) * ROAD_FACTOR_COEFF
        weather_factor  = weather_fuel_penalty.get(weather, 1.0)
        per_100 = base * weight_factor * gradient_factor * road_factor * weather_factor
        return (per_100 * distance) / 100

    def train_from_database(self, conn):
        try:
            query = """
            SELECT TR.distance, TR.load, TR.road_quality, TR.terrain_type,
                   TR.weather_condition, TR.hard_braking_events, TR.idle_time_minutes,
                   TR.driver_experience_years, TR.border_crossings,
                   TR.fuel_consumed, T.truck_age_years, T.fuel_efficiency_baseline
            FROM Trip TR
            LEFT JOIN Truck T ON TR.truck_id = T.truck_id
            WHERE TR.fuel_consumed IS NOT NULL AND TR.fuel_consumed > 0
            """
            data = pd.read_sql_query(query, conn)
            if len(data) < 5:
                return False, f"Need at least 5 trip records to train fuel model. Have {len(data)}. Run seed_training_data.py or log more trips."

            # Gradient lookup from terrain when direct value not stored in trip log
            terrain_gradient_defaults = {'Flat': 0.5, 'Rolling': 2.0, 'Mountainous': 4.0}
            X, y = [], []
            for _, row in data.iterrows():
                road_q   = row['road_quality'] if pd.notna(row.get('road_quality')) else 0.75
                terrain  = row.get('terrain_type', 'Rolling') or 'Rolling'
                gradient = terrain_gradient_defaults.get(terrain, 2.0)
                features = {
                    'distance':                row['distance'],
                    'load_ratio':              row['load'] / MAX_PAYLOAD_KG if row['load'] else 0,
                    'avg_gradient':            gradient,
                    'road_quality':            road_q,
                    'terrain_type_encoded':    self.terrain_mapping.get(terrain, 1),
                    'weather_condition_encoded': self.weather_mapping.get(row.get('weather_condition'), 0),
                    'hard_braking_events':     row['hard_braking_events'] if pd.notna(row.get('hard_braking_events')) else 0,
                    'idle_time_minutes':       row['idle_time_minutes'] if pd.notna(row.get('idle_time_minutes')) else 0,
                    'driver_experience_years': row['driver_experience_years'] if pd.notna(row.get('driver_experience_years')) else 5,
                    'truck_age_years':         row['truck_age_years'] if pd.notna(row.get('truck_age_years')) else 0,
                    'border_crossings':        row['border_crossings'] if pd.notna(row.get('border_crossings')) else 0,
                }
                X.append([features[c] for c in self.feature_columns])
                y.append(row['fuel_consumed'])

            X = np.array(X)
            y = np.array(y)
            X_scaled = self.scaler.fit_transform(X)

            # For small datasets skip the split to avoid empty train/test sets
            if len(data) >= 25:
                X_train, X_test, y_train, y_test = train_test_split(
                    X_scaled, y, test_size=0.2, random_state=42
                )
            else:
                # Train on all data; evaluate on same data (small dataset mode)
                X_train, X_test, y_train, y_test = X_scaled, X_scaled, y, y

            # Relax tree constraints for small datasets so the model can actually fit
            min_split = max(2, min(5, len(X_train) // 4))
            min_leaf  = max(1, min(3, len(X_train) // 6))

            self.model = RandomForestRegressor(
                n_estimators=150, max_depth=12,
                min_samples_split=min_split, min_samples_leaf=min_leaf,
                random_state=42, n_jobs=-1
            )
            self.model.fit(X_train, y_train)
            self.is_trained = True

            # Persist to disk — survives app restarts
            try:
                from utils.model_store import save_model
                save_model('fuel_model', self)
            except Exception:
                pass

            y_pred = self.model.predict(X_test)
            mae  = mean_absolute_error(y_test, y_pred)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            r2   = r2_score(y_test, y_pred)

            return True, (mae, rmse, r2, len(data), self.model.feature_importances_)
        except Exception as e:
            logging.error(f"Fuel model training error: {e}")
            return False, str(e)

    def predict_fuel_consumption(self, trip_data, truck_data, driver_data):
        if self.is_trained and self.model:
            try:
                feat = self.prepare_features(trip_data, truck_data, driver_data)
                scaled = self.scaler.transform(feat)
                return max(0, self.model.predict(scaled)[0])
            except Exception as e:
                logging.warning(f"ML prediction failed, using physics estimate: {e}")
        return self.calculate_theoretical_fuel_consumption(
            trip_data.get('distance', 0),
            trip_data.get('weight', 0),
            trip_data.get('avg_gradient', 0),
            trip_data.get('road_quality', 0.75),
            trip_data.get('weather', 'Clear'),
        )

    def calculate_fuel_efficiency(self, distance, fuel_consumed):
        return distance / fuel_consumed if fuel_consumed > 0 else 0

    def get_fuel_cost_savings_recommendations(self, predicted, actual):
        recommendations = []
        diff = actual - predicted
        if diff > 0:
            savings = diff * FUEL_PRICE_DEFAULT
            recommendations.append({
                'type': 'SAVINGS_OPPORTUNITY',
                'message': f'Potential savings of E {savings:.2f} per trip',
                'action': 'Review driving behaviour and route optimisation',
                'impact': 'High'
            })
        return recommendations

    def get_fuel_efficiency_rating(self, eff):
        if eff >= 4.0: return "Excellent", "green", ""
        if eff >= 3.0: return "Good", "lightgreen", "✅"
        if eff >= 2.5: return "Average", "orange", "⚠️"
        if eff >= 2.0: return "Below Average", "red", "❌"
        return "Poor", "darkred", ""

# =============================================================================
