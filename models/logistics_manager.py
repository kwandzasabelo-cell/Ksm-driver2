# models/logistics_manager.py — Job feasibility scoring and cost analysis
from __future__ import annotations
import logging
from datetime import datetime
from core.config import (
    MAX_PAYLOAD_KG, FUEL_PRICE_DEFAULT, MAINTENANCE_PER_KM,
    DRIVER_RATE_PER_HR, BORDER_COST_EACH, INSURANCE_BASE_COST,
    OPPORTUNITY_COST_HR, PROFIT_SCALE_FACTOR,
    FAILURE_PROB_THRESHOLD, DRIVER_SCORE_THRESHOLD,
)
from services.routes import get_route_characteristics, get_season_temp
from models.maintenance import PredictiveMaintenanceEngine
from models.driver import DriverBehaviorAnalyzer

class UnifiedLogisticsManager:
    def __init__(self):
        self.maintenance_engine = PredictiveMaintenanceEngine()
        self.driver_analyzer = DriverBehaviorAnalyzer()
        self.ml_risk_predictor = None  # set via set_models()
        self.fuel_model = None  # set via set_models()


    def set_models(self, ml_risk_predictor, fuel_model):
        """Inject trained model instances from the main app."""
        self.ml_risk_predictor = ml_risk_predictor
        self.fuel_model = fuel_model

    def evaluate_job_feasibility(self, job_data, truck_data, driver_data, live_weather=None):
        origin = job_data['origin']
        destination = job_data['destination']

        # Use ORS route if provided (without mutating truck_data)
        ors_route = truck_data.get('_ors_route')
        if ors_route and isinstance(ors_route, dict) and "error" not in ors_route:
            route = ors_route.copy()
            route['border_crossings'] = job_data.get('border_crossings', 0)
            route_source = "ORS HGV (live)"
        else:
            route = get_route_characteristics(origin, destination)
            if job_data.get('border_crossings') is not None:
                route['border_crossings'] = job_data['border_crossings']
            route_source = "Route defaults"

        if live_weather:
            weather_condition = live_weather.get("weather_condition", "Clear")
            ambient_temp = live_weather.get("temperature", 25.0)
            wind_speed = live_weather.get("wind_speed", 15.0)
            rainfall = live_weather.get("rainfall", 0.0)
            weather_source = live_weather.get("source", "unknown")
        else:
            weather_condition = job_data.get('weather', 'Clear')
            ambient_temp = get_season_temp()
            wind_speed = 15.0
            rainfall = 0.0
            weather_source = "seasonal default"

        trip_data_for_risk = {
            'distance':                route['distance'],
            'load':                    job_data.get('weight', 5000),
            'road_quality':            route.get('road_quality', 0.75),
            'driver_experience_years': driver_data.get('experience_years', 5),
            'hard_braking_events':     driver_data.get('hard_braking_events', 0),
            'idle_time_minutes':       driver_data.get('idle_time_minutes', 0),
            'border_crossings':        route['border_crossings'],
            'terrain':                 route.get('terrain', 'Rolling'),
            'weather':                 weather_condition,
            'wind_speed':              wind_speed,
            'rainfall_mm':             rainfall,
        }

        risk_score = self.ml_risk_predictor.predict_risk(trip_data_for_risk, truck_data)
        risk_factors = self.ml_risk_predictor.get_risk_factors(trip_data_for_risk, truck_data)

        trip_data_for_fuel = {
            'distance':         route['distance'],
            'weight':           job_data.get('weight', 5000),
            'avg_gradient':     route.get('gradient', 0),
            'road_quality':     route.get('road_quality', 0.75),
            'terrain':          route.get('terrain', 'Rolling'),
            'weather':          weather_condition,
            'border_crossings': route['border_crossings'],
        }

        predicted_fuel = self.fuel_model.predict_fuel_consumption(trip_data_for_fuel, truck_data, driver_data)
        fuel_efficiency = self.fuel_model.calculate_fuel_efficiency(route['distance'], predicted_fuel)
        eff_rating, eff_color, eff_icon = self.fuel_model.get_fuel_efficiency_rating(fuel_efficiency)

        total_costs = self._calculate_total_costs(route, predicted_fuel, job_data, truck_data, driver_data)
        opportunity_cost = self._get_opportunity_cost(route, job_data)
        revenue = job_data.get('revenue', predicted_fuel * FUEL_PRICE_DEFAULT * 2.5)
        profit = revenue - total_costs

        failure_prob = risk_score / 100
        driver_behavior_score = self.driver_analyzer.analyze_behavior(driver_data)
        feasibility_score = self._calculate_feasibility_score(profit, failure_prob, driver_behavior_score, route)

        return {
            'route': route,
            'route_source': route_source,
            'weather_source': weather_source,
            'live_weather': live_weather,
            'fuel_needed': predicted_fuel,
            'fuel_efficiency': fuel_efficiency,
            'efficiency_rating': eff_rating,
            'efficiency_color': eff_color,
            'efficiency_icon': eff_icon,
            'total_costs': total_costs,
            'opportunity_cost': opportunity_cost,
            'revenue': revenue,
            'profit': profit,
            'failure_probability': failure_prob,
            'risk_score': risk_score,
            'risk_factors': risk_factors,
            'driver_behavior_score': driver_behavior_score,
            'feasibility_score': feasibility_score,
            'recommendations': self._generate_recommendations(profit, failure_prob, driver_behavior_score, route),
            'detailed_metrics': self._get_detailed_metrics(route, truck_data, driver_data),
            'ambient_temp': ambient_temp,
            'wind_speed': wind_speed,
            'rainfall': rainfall,
            'weather_condition': weather_condition,
        }

    def _calculate_total_costs(self, route, fuel_needed, job_data, truck_data, driver_data):
        """Returns only real cash outflows. Opportunity cost is excluded — it is a
        decision-support concept, not an actual expense, and including it distorts profit."""
        fuel_cost        = fuel_needed * job_data.get('fuel_price', FUEL_PRICE_DEFAULT)
        maintenance_cost = route['distance'] * MAINTENANCE_PER_KM * (1 + truck_data.get('truck_age_years', 0) * 0.05)
        driver_cost      = route.get('duration', 0) * driver_data.get('hourly_rate', DRIVER_RATE_PER_HR)
        toll_cost        = route.get('tolls', 0)
        border_cost      = route.get('border_crossings', 0) * BORDER_COST_EACH
        # Insurance scales with cargo value (0.1% of cargo value) capped at base
        cargo_value      = truck_data.get('cargo_value', 0) or job_data.get('cargo_value', 0)
        insurance_cost   = max(
            route.get('accident_risk', 0.3) * INSURANCE_BASE_COST,
            cargo_value * 0.001,
        )
        return fuel_cost + maintenance_cost + driver_cost + toll_cost + border_cost + insurance_cost

    def _get_opportunity_cost(self, route, job_data):
        """Opportunity cost for reference display only — not included in profit."""
        return route.get('duration', 0) * job_data.get('opportunity_cost_rate', OPPORTUNITY_COST_HR)

    def _calculate_feasibility_score(self, profit, failure_prob, driver_score, route):
        profit_score = min(100, max(0, profit / PROFIT_SCALE_FACTOR)) if profit > 0 else 0
        risk_score = (1 - failure_prob) * 100
        road_score = route.get('road_quality', 0.75) * 100
        feasibility = (profit_score * 0.45 + risk_score * 0.35 + driver_score * 0.10 + road_score * 0.10)
        return min(100, max(0, feasibility))

    def _generate_recommendations(self, profit, failure_prob, driver_score, route):
        recs = []
        if profit <= 0:
            recs.append({'type': 'CRITICAL', 'message': 'Negative profit projection – renegotiate rates or reject job', 'action': 'Increase rate by 15–20% or seek alternative cargo'})
        if failure_prob > FAILURE_PROB_THRESHOLD:
            recs.append({'type': 'WARNING', 'message': f'High failure probability ({failure_prob:.0%})', 'action': 'Schedule preventive maintenance before trip'})
        if driver_score < DRIVER_SCORE_THRESHOLD:
            recs.append({'type': 'IMPROVEMENT', 'message': f'Driver behaviour score low ({driver_score:.0f})', 'action': 'Provide eco-driving training'})
        if route.get('road_quality', 1) < 0.7:
            recs.append({'type': 'ROUTE', 'message': 'Poor road quality on this route', 'action': 'Consider alternative route or reduce speed'})
        return recs

    def _get_detailed_metrics(self, route, truck_data, driver_data):
        return {
            'route_metrics': {
                'Distance': f"{route['distance']:.1f} km",
                'Duration': f"{route.get('duration', 0):.1f} hours",
                'Terrain': route.get('terrain', 'Unknown'),
                'Road Quality': f"{route.get('road_quality', 0)*100:.0f}%",
                'Accident Risk': f"{route.get('accident_risk', 0)*100:.0f}%",
                'Border Crossings': route.get('border_crossings', 0),
            },
            'truck_metrics': {
                'Service Gap': f"{truck_data['mileage'] - truck_data['last_service_km']:.0f} km",
                'Truck Age': f"{truck_data.get('truck_age_years', 0):.1f} years",
            },
            'driver_metrics': {
                'Experience': f"{driver_data.get('experience_years', 5)} years",
                'Hard Braking': driver_data.get('hard_braking_events', 0),
                'Idle Time': f"{driver_data.get('idle_time_minutes', 0)} min",
            },
        }

# =============================================================================
