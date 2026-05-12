# models/driver.py — Driver behaviour analyser
from __future__ import annotations

class DriverBehaviorAnalyzer:
    def analyze_behavior(self, driver_data):
        score = 100
        if driver_data.get('hard_braking_events', 0) > 5:
            score -= min(20, driver_data['hard_braking_events'] * 2)
        if driver_data.get('hard_acceleration_events', 0) > 5:
            score -= min(20, driver_data['hard_acceleration_events'] * 2)
        idle = driver_data.get('idle_time_minutes', 0)
        if idle > 30:
            score -= min(15, idle / 10)
        return max(0, score)

    def get_fuel_efficiency_impact(self, score):
        if score >= 90: return 0.95
        if score >= 70: return 1.00
        if score >= 50: return 1.08
        return 1.15

# =============================================================================
