# models/maintenance.py — Predictive maintenance engine
from __future__ import annotations
from core.config import SERVICE_INTERVAL_KM


class PredictiveMaintenanceEngine:
    def __init__(self):
        self.component_lifespan = {
            'engine_oil':   15000,
            'air_filter':   20000,
            'fuel_filter':  25000,
            'brake_pads':   50000,
            'tires':        60000,
            'transmission': 100000,
        }
        # Realistic estimated replacement cost (E) per component for HGV
        self.component_cost = {
            'engine_oil':   850,
            'air_filter':   450,
            'fuel_filter':  600,
            'brake_pads':  3200,
            'tires':       8500,   # per set of 4 steer tyres
            'transmission': 25000,
        }

    def predict_failure_probability(self, truck_data, trip_data):
        risk = 0.0
        service_gap      = truck_data['mileage'] - truck_data['last_service_km']
        service_interval = truck_data.get('service_interval', SERVICE_INTERVAL_KM)
        if service_gap > service_interval:
            risk += min(0.4, service_gap / 50000)
        if trip_data.get('terrain_type') == 'Mountainous':
            risk += 0.10
        if trip_data.get('road_quality', 1) < 0.7:
            risk += 0.15
        breakdown_count = truck_data.get('breakdown_count', 0)
        if breakdown_count > 2:
            risk += 0.1 * breakdown_count
        return min(0.95, risk)

    def get_maintenance_recommendations(self, truck_data):
        recommendations = []
        service_gap = truck_data['mileage'] - truck_data['last_service_km']
        service_interval = truck_data.get('service_interval', SERVICE_INTERVAL_KM)
        for component, lifespan in self.component_lifespan.items():
            if service_gap > lifespan * 0.8:
                recommendations.append({
                    'component':      component,
                    'urgency':        'HIGH' if service_gap > lifespan else 'MEDIUM',
                    'action':         f'Replace {component.replace("_", " ")}',
                    'estimated_cost': self.component_cost.get(component, 1500),
                })
        return recommendations
