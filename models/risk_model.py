# models/risk_model.py — ML risk prediction model
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from core.config import (
    MAX_PAYLOAD_KG, FAILURE_PROB_THRESHOLD,
    DRIVER_SCORE_THRESHOLD,
)

class MLRiskPredictor:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_columns = [
            'distance', 'load', 'road_quality',
            'driver_experience_years', 'hard_braking_events',
            'idle_time_minutes', 'truck_age_years',
            'border_crossings',
        ]

    def prepare_features(self, trip_data, truck_data=None):
        td = truck_data or {}
        features = {
            'distance':                trip_data.get('distance', 0),
            'load':                    trip_data.get('load', 0) / MAX_PAYLOAD_KG,
            'road_quality':            trip_data.get('road_quality', 0.75),
            'driver_experience_years': trip_data.get('driver_experience_years', 5),
            'hard_braking_events':     trip_data.get('hard_braking_events', 0),
            'idle_time_minutes':       trip_data.get('idle_time_minutes', 0),
            'truck_age_years':         td.get('truck_age_years', 0),
            'border_crossings':        trip_data.get('border_crossings', 0),
        }
        arr = np.array([features[c] for c in self.feature_columns])
        return arr.reshape(1, -1)

    def calculate_historical_risk(self, row):
        risk = 0
        if row['distance'] > 500: risk += 20
        elif row['distance'] > 300: risk += 10

        load_ratio = row['load'] / MAX_PAYLOAD_KG if row['load'] else 0
        if load_ratio > 0.9: risk += 15
        elif load_ratio > 0.7: risk += 8

        terrain_risk = {'Mountainous': 20, 'Rolling': 10, 'Flat': 5}
        risk += terrain_risk.get(row.get('terrain_type', 'Flat'), 5)

        rq = row.get('road_quality', 0.75)
        if rq < 0.6: risk += 15
        elif rq < 0.8: risk += 8

        weather_risk = {'Storm': 20, 'Rain': 10, 'Fog': 12, 'High Wind': 15, 'Clear': 0}
        risk += weather_risk.get(row.get('weather_condition', 'Clear'), 5)

        risk += min(20, row.get('hard_braking_events', 0) * 2)
        risk += min(15, row.get('idle_time_minutes', 0) / 10)
        risk += row.get('border_crossings', 0) * 5

        # NOTE: delivery_on_time is intentionally excluded — it is not captured
        # in the trip log form and would always be NULL, biasing the training target.

        return min(100, risk)

    def train_from_database(self, conn):
        try:
            query = """
            SELECT TR.distance, TR.load, TR.road_quality,
                   TR.driver_experience_years, TR.hard_braking_events,
                   TR.idle_time_minutes, TR.terrain_type, TR.weather_condition,
                   TR.delivery_on_time, TR.border_crossings,
                   T.truck_age_years
            FROM Trip TR
            LEFT JOIN Truck T ON TR.truck_id = T.truck_id
            WHERE TR.distance IS NOT NULL
            """
            data = pd.read_sql_query(query, conn)
            if len(data) < 3:
                return False, f"Need at least 3 trips to train risk model. Have {len(data)}. Run seed_training_data.py or log more trips."

            risk_scores = [self.calculate_historical_risk(row) for _, row in data.iterrows()]
            data['risk_score_target'] = risk_scores

            X = []
            for _, row in data.iterrows():
                features = {
                    'distance':                row['distance'],
                    'load':                    row['load'] / MAX_PAYLOAD_KG if row['load'] else 0,
                    'road_quality':            row['road_quality'] if pd.notna(row.get('road_quality')) else 0.75,
                    'driver_experience_years': row['driver_experience_years'] if pd.notna(row.get('driver_experience_years')) else 5,
                    'hard_braking_events':     row['hard_braking_events'] if pd.notna(row.get('hard_braking_events')) else 0,
                    'idle_time_minutes':       row['idle_time_minutes'] if pd.notna(row.get('idle_time_minutes')) else 0,
                    'truck_age_years':         row['truck_age_years'] if pd.notna(row.get('truck_age_years')) else 0,
                    'border_crossings':        row['border_crossings'] if pd.notna(row.get('border_crossings')) else 0,
                }
                X.append([features[c] for c in self.feature_columns])

            X = np.array(X)
            y = np.array(risk_scores)
            X_scaled = self.scaler.fit_transform(X)

            # For small datasets skip the split to avoid empty train/test sets
            if len(data) >= 15:
                X_train, X_test, y_train, y_test = train_test_split(
                    X_scaled, y, test_size=0.2, random_state=42
                )
            else:
                X_train, X_test, y_train, y_test = X_scaled, X_scaled, y, y

            # Relax tree constraints for small datasets
            min_split = max(2, min(5, len(X_train) // 4))
            min_leaf  = max(1, min(2, len(X_train) // 6))

            self.model = RandomForestRegressor(
                n_estimators=100, max_depth=10,
                min_samples_split=min_split, min_samples_leaf=min_leaf,
                random_state=42, n_jobs=-1
            )
            self.model.fit(X_train, y_train)
            self.is_trained = True

            # Persist to disk — survives app restarts
            try:
                from utils.model_store import save_model
                save_model('risk_model', self)
            except Exception:
                pass

            y_pred = self.model.predict(X_test)
            mae = mean_absolute_error(y_test, y_pred)
            r2  = r2_score(y_test, y_pred)

            return True, (mae, r2, len(data), self.model.feature_importances_)
        except Exception as e:
            logging.error(f"Risk model training error: {e}")
            return False, str(e)

    def predict_risk(self, trip_data, truck_data=None):
        if self.is_trained and self.model:
            try:
                feat = self.prepare_features(trip_data, truck_data)
                scaled = self.scaler.transform(feat)
                score = self.model.predict(scaled)[0]
                return min(100, max(0, score))
            except Exception as e:
                logging.warning(f"ML risk prediction failed, using rules: {e}")
        return self.calculate_rule_based_risk(trip_data, truck_data)

    def calculate_rule_based_risk(self, trip_data, truck_data=None):
        risk = 0
        distance = trip_data.get('distance', 300)
        risk += min(20, distance / 30)

        load_ratio = trip_data.get('weight', 5000) / MAX_PAYLOAD_KG
        risk += load_ratio * 15

        terrain = trip_data.get('terrain', 'Rolling')
        terrain_risk = {'Mountainous': 20, 'Rolling': 10, 'Flat': 5}
        risk += terrain_risk.get(terrain, 10)

        weather = trip_data.get('weather', 'Clear')
        weather_risk = {'Storm': 20, 'Rain': 12, 'Fog': 10, 'High Wind': 15, 'Clear': 0}
        risk += weather_risk.get(weather, 5)

        risk += trip_data.get('border_crossings', 0) * 5

        driver_exp = trip_data.get('driver_experience_years', 5)
        risk += max(0, 15 - driver_exp * 1.5)

        return min(100, risk)

    def get_risk_factors(self, trip_data, truck_data=None):
        if self.is_trained and self.model:
            try:
                feat = self.prepare_features(trip_data, truck_data)
                scaled = self.scaler.transform(feat)
                contributions = {f: self.model.feature_importances_[i] * feat[0][i]
                                 for i, f in enumerate(self.feature_columns)}
                sorted_c = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)
                return [{'factor': f.replace('_', ' ').title(), 'impact': v,
                         'severity': 'High' if abs(v) > 0.1 else 'Medium' if abs(v) > 0.05 else 'Low'}
                        for f, v in sorted_c[:5] if abs(v) > 0.01]
            except:
                pass
        return [{'factor': 'Insufficient data for detailed analysis', 'impact': 0, 'severity': 'Low'}]

# =============================================================================
