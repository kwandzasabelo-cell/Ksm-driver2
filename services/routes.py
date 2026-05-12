# services/routes.py — Route database, route selection, travel-time and ML route advisor
from __future__ import annotations
import math
import logging
from datetime import datetime, timedelta
from core.config import (
    MAX_PAYLOAD_KG, FUEL_PRICE_DEFAULT, BORDER_COST_EACH,
    VEHICLE_SPEED_PROFILES, ROAD_CONDITION_SPEED, WEATHER_SPEED_PENALTY,
    LOCATION_COORDS, LOCATION_TERRAIN, SEASONAL_TEMP,
)

# =============================================================================
# 4. ROUTE DATABASE — Multi-route with road numbers & vehicle speed profiles
# =============================================================================

# VEHICLE_SPEED_PROFILES, ROAD_CONDITION_SPEED and WEATHER_SPEED_PENALTY
# are imported from core.config — do not redefine here.

# MULTI-ROUTE DATABASE
# Each route pair maps to a list of alternative routes.
# route_id, name, road_numbers, distance_km, terrain, gradient, road_quality,
# accident_risk, theft_risk, border_crossings, base_duration_car_hrs,
# waypoints (list of stop names), tolls_zar, description, is_preferred
MULTI_ROUTE_DB = {
    ("Mbabane", "Johannesburg"): [
        {
            "route_id": "MBB-JHB-N4",
            "name": "N4 / N17 via Oshoek-Badplaas (Recommended)",
            "road_numbers": ["N4 (Eswatini)", "MR3", "R38", "N17", "N12"],
            "distance": 368,
            "terrain": "Rolling",
            "gradient": 2.5,
            "road_quality": 0.82,
            "accident_risk": 0.25,
            "theft_risk": 0.18,
            "border_crossings": 1,
            "base_duration_car": 4.8,
            "tolls": 85,
            "waypoints": ["Ngwenya/Oshoek Border", "Badplaas", "Carolina", "Bethal", "Johannesburg"],
            "description": "Main HGV corridor. Good road surface, lower gradient, N17 is well-lit.",
            "is_preferred": True,
        },
        {
            "route_id": "MBB-JHB-N1",
            "name": "N1 via Machado / Waterval Boven",
            "road_numbers": ["MR1 (Eswatini)", "Jeppe's Reef Border", "N4", "N1"],
            "distance": 412,
            "terrain": "Mountainous",
            "gradient": 4.2,
            "road_quality": 0.75,
            "accident_risk": 0.35,
            "theft_risk": 0.20,
            "border_crossings": 1,
            "base_duration_car": 5.5,
            "tolls": 120,
            "waypoints": ["Piggs Peak", "Jeppe's Reef Border", "Waterval Boven", "Machadodorp", "Johannesburg"],
            "description": "Scenic but steep Drakensberg descent. NOT recommended for overloaded trucks. High gradient risk.",
            "is_preferred": False,
        },
        {
            "route_id": "MBB-JHB-N2S",
            "name": "N2 South via Piet Retief",
            "road_numbers": ["MR3", "Lavumisa Border", "N2", "N17"],
            "distance": 445,
            "terrain": "Rolling",
            "gradient": 1.8,
            "road_quality": 0.80,
            "accident_risk": 0.22,
            "theft_risk": 0.22,
            "border_crossings": 1,
            "base_duration_car": 5.8,
            "tolls": 60,
            "waypoints": ["Manzini", "Lavumisa/Golela Border", "Piet Retief", "Standerton", "Johannesburg"],
            "description": "Longest but flattest option. Good for overloaded/max GVM trucks. Low tolls.",
            "is_preferred": False,
        },
    ],
    ("Manzini", "Durban"): [
        {
            "route_id": "MNZ-DBN-N2",
            "name": "N2 via Lavumisa / Golela (Recommended)",
            "road_numbers": ["MR3 (Eswatini)", "Lavumisa Border", "N2"],
            "distance": 418,
            "terrain": "Rolling",
            "gradient": 1.8,
            "road_quality": 0.87,
            "accident_risk": 0.22,
            "theft_risk": 0.14,
            "border_crossings": 1,
            "base_duration_car": 5.5,
            "tolls": 95,
            "waypoints": ["Lavumisa/Golela Border", "Pongola", "Mkuze", "Richards Bay", "Durban"],
            "description": "Primary HGV route to Durban port. Well-maintained N2, familiar to SA trucks.",
            "is_preferred": True,
        },
        {
            "route_id": "MNZ-DBN-R66",
            "name": "R66 / N11 via Piet Retief",
            "road_numbers": ["MR8 (Eswatini)", "Mahamba Border", "R66", "N11", "N2"],
            "distance": 435,
            "terrain": "Mountainous",
            "gradient": 3.2,
            "road_quality": 0.72,
            "accident_risk": 0.30,
            "theft_risk": 0.16,
            "border_crossings": 1,
            "base_duration_car": 5.9,
            "tolls": 70,
            "waypoints": ["Mahamba Border", "Piet Retief", "Newcastle", "N11 Junction", "Durban"],
            "description": "Alternative via Mahamba border. R66 has patchy surface. Avoid for perishables.",
            "is_preferred": False,
        },
    ],
    ("Matsapha", "Maputo"): [
        {
            "route_id": "MTS-MPT-EN4",
            "name": "EN4 via Lomahasha / Namaacha (Recommended)",
            "road_numbers": ["MR3 (Eswatini)", "Lomahasha Border", "EN4 (Mozambique)"],
            "distance": 178,
            "terrain": "Flat",
            "gradient": 0.5,
            "road_quality": 0.72,
            "accident_risk": 0.32,
            "theft_risk": 0.28,
            "border_crossings": 2,
            "base_duration_car": 3.0,
            "tolls": 45,
            "waypoints": ["Lomahasha Border", "Namaacha", "Maputo"],
            "description": "Most direct to Maputo port. EN4 road quality variable – allow buffer time. High theft risk in Maputo suburbs.",
            "is_preferred": True,
        },
        {
            "route_id": "MTS-MPT-SA",
            "name": "Via South Africa / KM Border",
            "road_numbers": ["MR3", "Lavumisa Border", "N2", "N17 (SA)", "Lebombo Border", "EN4"],
            "distance": 390,
            "terrain": "Flat",
            "gradient": 0.8,
            "road_quality": 0.80,
            "accident_risk": 0.25,
            "theft_risk": 0.20,
            "border_crossings": 4,
            "base_duration_car": 6.0,
            "tolls": 110,
            "waypoints": ["Lavumisa Border", "Piet Retief", "Komatipoort/Lebombo", "EN4", "Maputo"],
            "description": "Much longer but better road quality. Only use if Lomahasha border is congested.",
            "is_preferred": False,
        },
    ],
    ("Piggs Peak", "Nelspruit"): [
        {
            "route_id": "PPK-NLS-N4",
            "name": "N4 via Jeppe's Reef (Recommended)",
            "road_numbers": ["MR4 (Eswatini)", "Jeppe's Reef Border", "N4"],
            "distance": 148,
            "terrain": "Mountainous",
            "gradient": 4.2,
            "road_quality": 0.68,
            "accident_risk": 0.38,
            "theft_risk": 0.16,
            "border_crossings": 1,
            "base_duration_car": 2.6,
            "tolls": 55,
            "waypoints": ["Jeppe's Reef Border", "Matsulu", "Nelspruit"],
            "description": "Fastest route but very steep descent. Ensure brakes checked. Slow speed mandatory on Drakensberg pass.",
            "is_preferred": True,
        },
    ],
    ("Mbabane", "Manzini"): [
        {
            "route_id": "MBB-MNZ-MR3",
            "name": "MR3 Motorway (Only Route)",
            "road_numbers": ["MR3 (Eswatini Motorway)"],
            "distance": 45,
            "terrain": "Rolling",
            "gradient": 1.5,
            "road_quality": 0.91,
            "accident_risk": 0.14,
            "theft_risk": 0.07,
            "border_crossings": 0,
            "base_duration_car": 0.55,
            "tolls": 0,
            "waypoints": ["Malkerns Junction", "Manzini"],
            "description": "Dual carriageway. Well-maintained. Congestion possible Mbabane CBD outbound 07:00–08:30.",
            "is_preferred": True,
        },
    ],
    ("Manzini", "Mbabane"): [
        {
            "route_id": "MNZ-MBB-MR3",
            "name": "MR3 Motorway (Only Route)",
            "road_numbers": ["MR3 (Eswatini Motorway)"],
            "distance": 45,
            "terrain": "Rolling",
            "gradient": 1.5,
            "road_quality": 0.91,
            "accident_risk": 0.14,
            "theft_risk": 0.07,
            "border_crossings": 0,
            "base_duration_car": 0.55,
            "tolls": 0,
            "waypoints": ["Malkerns Junction", "Mbabane"],
            "description": "Dual carriageway. Congestion possible Manzini CBD 07:30–08:30.",
            "is_preferred": True,
        },
    ],
    ("Manzini", "Lavumisa"): [
        {
            "route_id": "MNZ-LAV-MR8",
            "name": "MR8 via Big Bend",
            "road_numbers": ["MR8 (Eswatini)"],
            "distance": 90,
            "terrain": "Rolling",
            "gradient": 1.0,
            "road_quality": 0.80,
            "accident_risk": 0.18,
            "theft_risk": 0.10,
            "border_crossings": 0,
            "base_duration_car": 1.3,
            "tolls": 0,
            "waypoints": ["Big Bend", "Lavumisa"],
            "description": "Standard southern route. Road quality acceptable. Livestock crossing hazard near Big Bend.",
            "is_preferred": True,
        },
    ],
    ("Manzini", "Lomahasha"): [
        {
            "route_id": "MNZ-LOM-MR3",
            "name": "MR3 / MR13 via Simunye",
            "road_numbers": ["MR3 (Eswatini)", "MR13"],
            "distance": 130,
            "terrain": "Rolling",
            "gradient": 1.8,
            "road_quality": 0.76,
            "accident_risk": 0.21,
            "theft_risk": 0.12,
            "border_crossings": 0,
            "base_duration_car": 1.9,
            "tolls": 0,
            "waypoints": ["Simunye", "Tshaneni", "Lomahasha"],
            "description": "North-east corridor. Watch for sugar cane trucks on MR13 during harvest (Apr–Nov).",
            "is_preferred": True,
        },
    ],
    # ── Reverse / inbound route pairs ───────────────────────────────────────
    ("Johannesburg", "Mbabane"): [
        {
            "route_id": "JHB-MBB-N17",
            "name": "N17 / N4 via Oshoek-Badplaas (Recommended)",
            "road_numbers": ["N12", "N17", "R38", "MR3"],
            "distance": 368, "terrain": "Rolling", "gradient": 2.5,
            "road_quality": 0.82, "accident_risk": 0.25, "theft_risk": 0.18,
            "border_crossings": 1, "base_duration_car": 4.8, "tolls": 85,
            "waypoints": ["Bethal", "Carolina", "Badplaas", "Ngwenya/Oshoek Border", "Mbabane"],
            "description": "Standard inbound HGV corridor from Gauteng.",
            "is_preferred": True,
        },
        {
            "route_id": "JHB-MBB-N2S",
            "name": "N2 North via Piet Retief",
            "road_numbers": ["N17", "N2", "Golela/Lavumisa Border", "MR3"],
            "distance": 445, "terrain": "Rolling", "gradient": 1.8,
            "road_quality": 0.80, "accident_risk": 0.22, "theft_risk": 0.22,
            "border_crossings": 1, "base_duration_car": 5.8, "tolls": 60,
            "waypoints": ["Standerton", "Piet Retief", "Lavumisa/Golela Border", "Manzini", "Mbabane"],
            "description": "Flattest option. Suitable for overloaded/max GVM trucks.",
            "is_preferred": False,
        },
    ],
    ("Durban", "Manzini"): [
        {
            "route_id": "DBN-MNZ-N2",
            "name": "N2 via Golela / Lavumisa (Recommended)",
            "road_numbers": ["N2", "Golela/Lavumisa Border", "MR3 (Eswatini)"],
            "distance": 418, "terrain": "Rolling", "gradient": 1.8,
            "road_quality": 0.87, "accident_risk": 0.22, "theft_risk": 0.14,
            "border_crossings": 1, "base_duration_car": 5.5, "tolls": 95,
            "waypoints": ["Richards Bay", "Mkuze", "Pongola", "Golela/Lavumisa Border", "Manzini"],
            "description": "Primary inbound HGV route from Durban port. Well-maintained N2.",
            "is_preferred": True,
        },
    ],
    ("Maputo", "Matsapha"): [
        {
            "route_id": "MPT-MTS-EN4",
            "name": "EN4 via Namaacha / Lomahasha (Recommended)",
            "road_numbers": ["EN4 (Mozambique)", "Namaacha Border", "MR3 (Eswatini)"],
            "distance": 178, "terrain": "Flat", "gradient": 0.5,
            "road_quality": 0.72, "accident_risk": 0.32, "theft_risk": 0.28,
            "border_crossings": 2, "base_duration_car": 3.0, "tolls": 45,
            "waypoints": ["Namaacha Border", "Lomahasha", "Matsapha"],
            "description": "Most direct inbound from Maputo port. EN4 quality variable.",
            "is_preferred": True,
        },
    ],
    ("Nelspruit", "Piggs Peak"): [
        {
            "route_id": "NLS-PPK-N4",
            "name": "N4 via Jeppe's Reef (Recommended)",
            "road_numbers": ["N4", "Jeppe's Reef Border", "MR4 (Eswatini)"],
            "distance": 148, "terrain": "Mountainous", "gradient": 4.2,
            "road_quality": 0.68, "accident_risk": 0.38, "theft_risk": 0.16,
            "border_crossings": 1, "base_duration_car": 2.6, "tolls": 55,
            "waypoints": ["Matsulu", "Jeppe's Reef Border", "Piggs Peak"],
            "description": "Steep ascent inbound. Ensure brakes in good condition.",
            "is_preferred": True,
        },
    ],
    ("Lavumisa", "Manzini"): [
        {
            "route_id": "LAV-MNZ-MR8",
            "name": "MR8 via Big Bend",
            "road_numbers": ["MR8 (Eswatini)"],
            "distance": 90, "terrain": "Rolling", "gradient": 1.0,
            "road_quality": 0.80, "accident_risk": 0.18, "theft_risk": 0.10,
            "border_crossings": 0, "base_duration_car": 1.3, "tolls": 0,
            "waypoints": ["Big Bend", "Manzini"],
            "description": "Standard northbound return. Livestock crossing near Big Bend.",
            "is_preferred": True,
        },
    ],
    ("Lomahasha", "Manzini"): [
        {
            "route_id": "LOM-MNZ-MR13",
            "name": "MR13 / MR3 via Simunye",
            "road_numbers": ["MR13", "MR3 (Eswatini)"],
            "distance": 130, "terrain": "Rolling", "gradient": 1.8,
            "road_quality": 0.76, "accident_risk": 0.21, "theft_risk": 0.12,
            "border_crossings": 0, "base_duration_car": 1.9, "tolls": 0,
            "waypoints": ["Tshaneni", "Simunye", "Manzini"],
            "description": "South-west return from Lomahasha. Watch for sugar cane trucks during harvest.",
            "is_preferred": True,
        },
    ],
}

# Fallback for pairs not in MULTI_ROUTE_DB — use legacy single-route dict
ROUTE_DEFAULTS_LEGACY = {
    'Mbabane-Matsapha':  {'distance': 40,  'terrain': 'Rolling',      'gradient': 1.2, 'road_quality': 0.90, 'accident_risk': 0.12, 'theft_risk': 0.07, 'border_crossings': 0, 'duration': 0.6,  'tolls': 0},
    'Matsapha-Mbabane':  {'distance': 40,  'terrain': 'Rolling',      'gradient': 1.2, 'road_quality': 0.90, 'accident_risk': 0.12, 'theft_risk': 0.07, 'border_crossings': 0, 'duration': 0.6,  'tolls': 0},
    'Mbabane-Piggs Peak':{'distance': 55,  'terrain': 'Mountainous',  'gradient': 3.8, 'road_quality': 0.70, 'accident_risk': 0.30, 'theft_risk': 0.10, 'border_crossings': 0, 'duration': 1.2,  'tolls': 0},
    'Manzini-Matsapha':  {'distance': 10,  'terrain': 'Flat',         'gradient': 0.3, 'road_quality': 0.92, 'accident_risk': 0.10, 'theft_risk': 0.05, 'border_crossings': 0, 'duration': 0.2,  'tolls': 0},
}

def get_routes_for_pair(origin: str, destination: str) -> list:
    """Return list of route option dicts for an origin-destination pair."""
    routes = MULTI_ROUTE_DB.get((origin, destination))
    if routes:
        return routes
    # Try reverse lookup (sometimes bidirectional)
    rev = MULTI_ROUTE_DB.get((destination, origin))
    if rev:
        flipped = []
        for r in rev:
            rc = r.copy()
            rc["name"] = rc["name"] + " (reversed)"
            rc["waypoints"] = list(reversed(rc.get("waypoints", [])))
            flipped.append(rc)
        return flipped
    # Fall back to legacy single-route
    key = f"{origin}-{destination}"
    if key in ROUTE_DEFAULTS_LEGACY:
        d = ROUTE_DEFAULTS_LEGACY[key]
        return [{
            "route_id": key,
            "name": f"Standard Route ({origin} → {destination})",
            "road_numbers": ["MR (Eswatini)"],
            "distance": d["distance"],
            "terrain": d["terrain"],
            "gradient": d["gradient"],
            "road_quality": d["road_quality"],
            "accident_risk": d["accident_risk"],
            "theft_risk": d["theft_risk"],
            "border_crossings": d["border_crossings"],
            "base_duration_car": d["duration"],
            "tolls": d["tolls"],
            "waypoints": [destination],
            "description": "Auto-generated from route defaults.",
            "is_preferred": True,
        }]
    return []

# Convenience: return the single preferred/default route characteristics dict
def get_route_characteristics(origin: str, destination: str) -> dict:
    routes = get_routes_for_pair(origin, destination)
    if not routes:
        # Estimate from coordinates
        distance = estimate_distance(origin, destination)
        terrain  = determine_terrain(origin, destination)
        gmap     = {'Mountainous': 3.5, 'Rolling': 2.0, 'Flat': 0.5}
        rqmap    = {'Mountainous': 0.68, 'Rolling': 0.78, 'Flat': 0.82}
        rskmap   = {'Mountainous': 0.35, 'Rolling': 0.25, 'Flat': 0.18}
        return {
            'distance': distance, 'terrain': terrain,
            'gradient': gmap.get(terrain, 2.0),
            'road_quality': rqmap.get(terrain, 0.75),
            'accident_risk': rskmap.get(terrain, 0.25),
            'theft_risk': 0.15,
            'border_crossings': 1 if origin != destination else 0,
            'duration': distance / 70,
            'tolls': distance * 0.3,
        }
    preferred = next((r for r in routes if r.get("is_preferred")), routes[0])
    return _route_to_characteristics(preferred)

def _route_to_characteristics(r: dict) -> dict:
    return {
        'distance':        r['distance'],
        'terrain':         r['terrain'],
        'gradient':        r['gradient'],
        'road_quality':    r['road_quality'],
        'accident_risk':   r['accident_risk'],
        'theft_risk':      r['theft_risk'],
        'border_crossings':r['border_crossings'],
        'duration':        r['base_duration_car'],
        'tolls':           r['tolls'],
        'road_numbers':    r.get('road_numbers', []),
        'waypoints':       r.get('waypoints', []),
        'route_name':      r.get('name', ''),
    }

# ─── ML Route Advisor ─────────────────────────────────────────────────────────

def calculate_truck_travel_time(route: dict, vehicle_type: str, cargo_kg: float,
                                 weather: str = "Clear", departure_hour: int = 7) -> dict:
    """
    Calculate realistic truck travel time factoring:
    - Vehicle type speed profile
    - Load ratio (heavier = slower on grades)
    - Terrain gradient penalty
    - Road quality penalty
    - Weather speed penalty
    - Border crossing queue time
    - Driver rest stops (legal requirement: 30 min break per 4.5 hrs driving)
    - Departure time congestion
    """
    profile = VEHICLE_SPEED_PROFILES.get(vehicle_type, VEHICLE_SPEED_PROFILES["Rigid Truck (8–15t)"])
    base_speed = profile["base_speed"]
    hgv_factor = profile["hgv_factor"]

    # Load ratio effect on speed
    max_payload = MAX_PAYLOAD_KG
    load_ratio = min(1.0, cargo_kg / max_payload) if max_payload > 0 else 0.5
    load_speed_penalty = 1.0 - (load_ratio * 0.12)  # fully laden = 12% slower

    # Gradient penalty on speed (steep grades slow HGVs significantly)
    gradient = route.get('gradient', 2.0)
    gradient_penalty = 1.0 - min(0.30, gradient * 0.05)  # up to 30% slower on steep

    # Road quality penalty
    road_quality = route.get('road_quality', 0.75)
    road_penalty = 0.70 + (road_quality * 0.30)  # poor road = 70% speed

    # Weather
    weather_factor = WEATHER_SPEED_PENALTY.get(weather, 1.0)

    # Effective speed for this truck on this route
    effective_speed = base_speed * hgv_factor * load_speed_penalty * gradient_penalty * road_penalty * weather_factor
    effective_speed = max(25, effective_speed)  # floor at 25 km/h (mountain crawl)

    # Driving time (pure movement)
    distance = route.get('distance', 300)
    driving_hours = distance / effective_speed

    # Border crossing time (queue + processing, 45–90 min each for HGV)
    border_count = route.get('border_crossings', 0)
    border_hours = border_count * 1.25  # 75 min average per border for HGV

    # Mandatory rest stops (SA/Eswatini regulation: 30 min after 4.5 hrs continuous driving)
    rest_stops = int(driving_hours / 4.5)
    rest_hours = rest_stops * 0.5

    # Departure time congestion (peak hour penalty)
    congestion_hours = 0.0
    if 7 <= departure_hour <= 9:
        congestion_hours = 0.4  # CBD/border morning rush
    elif 15 <= departure_hour <= 18:
        congestion_hours = 0.3

    total_hours = driving_hours + border_hours + rest_hours + congestion_hours

    # ETA
    eta_dt = datetime.now().replace(hour=departure_hour, minute=0, second=0) + timedelta(hours=total_hours)

    return {
        "effective_speed_kmh":  round(effective_speed, 1),
        "driving_hours":        round(driving_hours, 2),
        "border_hours":         round(border_hours, 2),
        "rest_stops":           rest_stops,
        "rest_hours":           round(rest_hours, 2),
        "congestion_hours":     round(congestion_hours, 2),
        "total_hours":          round(total_hours, 2),
        "total_hours_hhmm":     f"{int(total_hours)}h {int((total_hours % 1) * 60):02d}m",
        "eta_str":              eta_dt.strftime("%H:%M on %a %d %b"),
        "breakdown": {
            "Driving time":     f"{driving_hours:.2f} hrs @ {effective_speed:.0f} km/h",
            "Border queues":    f"{border_hours:.2f} hrs ({border_count} crossing{'s' if border_count != 1 else ''})",
            "Mandatory rest":   f"{rest_hours:.2f} hrs ({rest_stops} stop{'s' if rest_stops != 1 else ''})",
            "Congestion":       f"{congestion_hours:.2f} hrs",
        }
    }

def ml_route_advisor(routes: list, vehicle_type: str, cargo_kg: float,
                     weather: str = "Clear", departure_hour: int = 7,
                     priority: str = "Fastest") -> dict:
    """
    Score all available routes and recommend the best one.
    Priority modes: Fastest | Safest | Most Economical | Lowest Risk
    Returns scored routes list + recommendation.
    """
    if not routes:
        return {"error": "No routes available"}

    scored = []
    for r in routes:
        travel = calculate_truck_travel_time(r, vehicle_type, cargo_kg, weather, departure_hour)

        # Risk score (0–100, lower = better)
        terrain_risk = {'Mountainous': 25, 'Rolling': 12, 'Flat': 5}
        risk = (r.get('accident_risk', 0.25) * 40 +
                r.get('theft_risk', 0.15) * 20 +
                terrain_risk.get(r.get('terrain', 'Rolling'), 12) * 0.5 +
                r.get('border_crossings', 0) * 8)

        # Fuel estimate (physics model)
        profile = VEHICLE_SPEED_PROFILES.get(vehicle_type, VEHICLE_SPEED_PROFILES["Rigid Truck (8–15t)"])
        base_l100 = profile["fuel_base_l100"]
        load_ratio = min(1.0, cargo_kg / MAX_PAYLOAD_KG)
        fuel_l100 = base_l100 * (1 + load_ratio * 0.40) * (1 + max(0, r.get('gradient', 2.0)) * 0.045) * (1 + (1 - r.get('road_quality', 0.75)) * 0.25)
        fuel_litres = (fuel_l100 * r['distance']) / 100
        fuel_cost   = fuel_litres * FUEL_PRICE_DEFAULT

        total_cost  = fuel_cost + r.get('tolls', 0) + r.get('border_crossings', 0) * BORDER_COST_EACH

        # Composite score per priority (lower = better for all raw values)
        if priority == "Fastest":
            score = travel["total_hours"] * 10 + risk * 0.1
        elif priority == "Safest":
            score = risk * 1.5 + travel["total_hours"] * 2
        elif priority == "Most Economical":
            score = total_cost * 0.01 + travel["total_hours"] * 2
        else:  # Lowest Risk
            score = risk * 2 + r.get('border_crossings', 0) * 10

        scored.append({
            "route":         r,
            "travel":        travel,
            "risk_score":    round(risk, 1),
            "fuel_litres":   round(fuel_litres, 1),
            "fuel_cost":     round(fuel_cost, 2),
            "total_cost":    round(total_cost, 2),
            "advisor_score": round(score, 2),
        })

    scored.sort(key=lambda x: x["advisor_score"])
    best = scored[0]

    # Build AI narrative
    reasons = []
    if best["route"].get("is_preferred"):
        reasons.append("✅ This is the established HGV preferred corridor")
    if best["travel"]["total_hours"] == min(s["travel"]["total_hours"] for s in scored):
        reasons.append("▶ Fastest arrival time")
    if best["risk_score"] == min(s["risk_score"] for s in scored):
        reasons.append("️ Lowest accident & theft risk")
    if best["total_cost"] == min(s["total_cost"] for s in scored):
        reasons.append(" Most economical (fuel + tolls + border)")
    if best["route"].get("terrain") != "Mountainous":
        reasons.append(" Avoids steep gradients — safer for laden HGV")

    return {
        "ranked": scored,
        "best":   best,
        "reasons": reasons,
        "priority_used": priority,
    }

# LOCATION_COORDS, LOCATION_TERRAIN and SEASONAL_TEMP are imported from core.config.

def get_season_temp():
    """Return seasonal ambient temperature based on Southern Hemisphere calendar."""
    month = datetime.now().month
    return SEASONAL_TEMP['Summer'] if month in [10, 11, 12, 1, 2, 3] else SEASONAL_TEMP['Winter']

def estimate_distance(origin: str, destination: str, ors_key: str = "") -> float:
    """Real road distance via GPS routing — falls back to OSRM then haversine."""
    try:
        import streamlit as st
        _ors = ors_key or st.session_state.get("ors_api_key", "")
    except Exception:
        _ors = ors_key
    try:
        from services.gps_routing import get_road_distance
        result = get_road_distance(origin, destination, _ors)
        if "error" not in result:
            return result["distance_km"]
    except Exception as e:
        logging.warning("GPS routing failed, using haversine: %s", e)
    # Legacy haversine fallback
    if origin in LOCATION_COORDS and destination in LOCATION_COORDS:
        p1, p2 = LOCATION_COORDS[origin], LOCATION_COORDS[destination]
        dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2) * 111
        return round(dist * 1.3, 1)
    return 300.0

def determine_terrain(origin, destination):
    if LOCATION_TERRAIN.get(origin) == 'Mountainous' or LOCATION_TERRAIN.get(destination) == 'Mountainous':
        return 'Mountainous'
    elif LOCATION_TERRAIN.get(origin) == 'Flat' and LOCATION_TERRAIN.get(destination) == 'Flat':
        return 'Flat'
    return 'Rolling'
