# services/gps_routing.py — Real GPS geocoding + HGV road routing
# Stack:
#   1. Nominatim (OpenStreetMap) — free geocoding, no key needed
#   2. OpenRouteService (ORS)    — real HGV road routing with key
#   3. OSRM public server        — free fallback routing (car profile)
#   4. Haversine                 — last-resort straight-line × 1.35
#
# Usage:
#   coords = geocode("Mbabane CBD, Eswatini")          # → (-26.3054, 31.1367)
#   result = get_road_distance("Mbabane CBD", "Durban Baito Boxer Superstore")
#   # result = {"distance_km": 422.3, "duration_hrs": 6.1, "source": "ORS HGV", ...}

from __future__ import annotations
import logging
import math
import time
from typing import Optional
import requests

logger = logging.getLogger(__name__)

# ── Request settings ──────────────────────────────────────────────────────────
_HEADERS = {"User-Agent": "KSM-SmartFreight/1.0 (kwandzasabelo@gmail.com)"}
_TIMEOUT = 10

# ── Geocode cache (in-memory for session) ─────────────────────────────────────
_GEOCODE_CACHE: dict[str, Optional[tuple[float, float]]] = {}

# ── Known coordinate overrides (Eswatini specific locations) ─────────────────
# These ensure local landmarks resolve correctly even without internet
_KNOWN_COORDS: dict[str, tuple[float, float]] = {
    # Eswatini towns
    "mbabane":               (-26.3054, 31.1367),
    "mbabane cbd":           (-26.3200, 31.1367),
    "manzini":               (-26.4854, 31.3598),
    "manzini cbd":           (-26.4910, 31.3670),
    "matsapha":              (-26.5168, 31.3006),
    "matsapha industrial":   (-26.5168, 31.3006),
    "piggs peak":            (-25.9588, 31.2498),
    "nhlangano":             (-27.1167, 31.2000),
    "siteki":                (-26.4500, 31.9500),
    "big bend":              (-26.8333, 31.9167),
    "hlatikhulu":            (-26.9667, 31.3167),
    "mankayane":             (-26.6667, 31.0667),
    "lobamba":               (-26.4500, 31.2000),
    "ezulwini":              (-26.4333, 31.1833),
    "kwaluseni":             (-26.4500, 31.3333),
    "oshoek":                (-25.8833, 31.1500),
    "ngwenya":               (-26.1500, 31.0000),
    "lomahasha":             (-25.9333, 31.9833),
    "lavumisa":              (-27.3167, 31.8833),
    "mahamba":               (-27.1333, 31.2000),
    "lundzi":                (-26.5833, 31.2000),
    "sandlane":              (-26.2333, 31.0167),
    # South Africa
    "johannesburg":          (-26.2041, 28.0473),
    "johannesburg cbd":      (-26.2041, 28.0473),
    "sandton":               (-26.1070, 28.0567),
    "durban":                (-29.8587, 31.0218),
    "durban cbd":            (-29.8587, 31.0218),
    "durban harbour":        (-29.8700, 31.0300),
    "durban port":           (-29.8700, 31.0300),
    "pinetown":              (-29.8167, 30.8667),
    "westmead":              (-29.7833, 30.8833),
    "cornubia":              (-29.7000, 31.0333),
    "umhlanga":              (-29.7333, 31.0667),
    "nelspruit":             (-25.4653, 30.9706),
    "nelspruit cbd":         (-25.4653, 30.9706),
    "mbombela":              (-25.4653, 30.9706),
    "cape town":             (-33.9249, 18.4241),
    "pretoria":              (-25.7479, 28.2293),
    "richardsbay":           (-28.7833, 32.0833),
    "empangeni":             (-28.7500, 31.9000),
    "stanger":               (-29.3333, 31.2833),
    "ballito":               (-29.5333, 31.2167),
    "port elizabeth":        (-33.9608, 25.6022),
    "gqeberha":              (-33.9608, 25.6022),
    "east london":           (-33.0153, 27.9116),
    "bloemfontein":          (-29.1209, 26.2140),
    "kimberley":             (-28.7282, 24.7499),
    "polokwane":             (-23.9045, 29.4688),
    "rustenburg":            (-25.6667, 27.2500),
    "witbank":               (-25.8667, 29.2333),
    "emalahleni":            (-25.8667, 29.2333),
    "middelburg":            (-25.7833, 29.4667),
    "secunda":               (-26.5167, 29.1833),
    "ermelo":                (-26.5167, 29.9833),
    "piet retief":           (-27.0000, 30.8167),
    "volksrust":             (-27.3667, 29.8833),
    "newcastle":             (-27.7667, 29.9167),
    "ladysmith":             (-28.5667, 29.7833),
    "harrismith":            (-28.2667, 29.1333),
    # Mozambique
    "maputo":                (-25.9692, 32.5732),
    "maputo cbd":            (-25.9692, 32.5732),
    "matola":                (-25.9667, 32.4667),
    "xai-xai":               (-25.0500, 33.6333),
    "inhambane":             (-23.8667, 35.3833),
    "beira":                 (-19.8436, 34.8389),
    "tete":                  (-16.1500, 33.5833),
    "nampula":               (-15.1167, 39.2667),
    "pemba":                 (-13.3000, 40.5167),
    "nacala":                (-14.5500, 40.6833),
    # Zimbabwe
    "harare":                (-17.8252, 31.0335),
    "bulawayo":              (-20.1500, 28.5833),
    "mutare":                (-18.9667, 32.6500),
    "beitbridge":            (-22.2167, 30.0000),
    # Zambia
    "lusaka":                (-15.4167, 28.2833),
    "livingstone":           (-17.8500, 25.8667),
}


# ── 1. Geocoding via Nominatim ────────────────────────────────────────────────

def geocode(address: str) -> Optional[tuple[float, float]]:
    """
    Convert a free-text address to (lat, lon).
    Tries known coords first, then Nominatim API.
    Returns None if not found.
    """
    key = address.strip().lower()

    # Check known coords
    if key in _KNOWN_COORDS:
        return _KNOWN_COORDS[key]

    # Partial match on known coords
    for known_key, coords in _KNOWN_COORDS.items():
        if known_key in key or key in known_key:
            return coords

    # Check cache
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]

    # Try Nominatim
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q":              address,
                "format":         "json",
                "limit":          1,
                "countrycodes":   "sz,za,mz,zw,zm",   # Prioritise regional results
                "addressdetails": 0,
            },
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            _GEOCODE_CACHE[key] = (lat, lon)
            logger.info("Geocoded '%s' → (%f, %f)", address, lat, lon)
            return (lat, lon)
    except Exception as e:
        logger.warning("Nominatim geocode failed for '%s': %s", address, e)

    # Broader search (drop country restriction)
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            _GEOCODE_CACHE[key] = (lat, lon)
            return (lat, lon)
    except Exception as e:
        logger.warning("Nominatim broad geocode failed: %s", e)

    _GEOCODE_CACHE[key] = None
    return None


def geocode_suggestions(partial: str, limit: int = 8) -> list[dict]:
    """
    Return a list of address suggestions for a partial query.
    Used for the autocomplete search in the trip form.
    """
    if len(partial.strip()) < 3:
        return []
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q":            partial,
                "format":       "json",
                "limit":        limit,
                "countrycodes": "sz,za,mz,zw,zm",
                "addressdetails": 1,
            },
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        results = []
        for r in resp.json():
            addr = r.get("display_name", "")
            lat  = float(r["lat"])
            lon  = float(r["lon"])
            results.append({
                "label": addr,
                "short": _short_label(addr),
                "lat":   lat,
                "lon":   lon,
            })
        return results
    except Exception as e:
        logger.warning("geocode_suggestions failed: %s", e)
        return []


def _short_label(display_name: str) -> str:
    """Shorten 'Boxer Superstore, 123 Main Rd, Durban, KZN, South Africa' to
    'Boxer Superstore, Durban'"""
    parts = [p.strip() for p in display_name.split(",")]
    if len(parts) >= 2:
        return f"{parts[0]}, {parts[-3] if len(parts) >= 3 else parts[-1]}"
    return display_name[:60]


# ── 2. Haversine straight-line distance ───────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── 3. ORS HGV routing ────────────────────────────────────────────────────────

def _ors_route(
    origin_coords: tuple[float, float],
    dest_coords:   tuple[float, float],
    api_key:       str,
) -> Optional[dict]:
    """Call ORS directions API with driving-hgv profile."""
    try:
        url  = "https://api.openrouteservice.org/v2/directions/driving-hgv"
        body = {
            "coordinates": [
                [origin_coords[1], origin_coords[0]],   # ORS uses [lon, lat]
                [dest_coords[1],   dest_coords[0]],
            ],
            "units": "km",
            "geometry": False,
        }
        resp = requests.post(
            url,
            json=body,
            headers={**_HEADERS, "Authorization": api_key,
                     "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            seg = resp.json()["routes"][0]["summary"]
            return {
                "distance_km":  round(seg["distance"], 1),
                "duration_hrs": round(seg["duration"] / 3600, 2),
                "source":       "ORS HGV (actual road distance)",
            }
        else:
            logger.warning("ORS returned %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("ORS routing failed: %s", e)
    return None


# ── 4. OSRM fallback routing ─────────────────────────────────────────────────

def _osrm_route(
    origin_coords: tuple[float, float],
    dest_coords:   tuple[float, float],
) -> Optional[dict]:
    """Call public OSRM API — car profile, free, no key."""
    try:
        url = (
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{origin_coords[1]},{origin_coords[0]};"
            f"{dest_coords[1]},{dest_coords[0]}"
            f"?overview=false&geometries=geojson"
        )
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code == 200:
            route = resp.json()["routes"][0]
            dist_km  = round(route["distance"] / 1000, 1)
            # Add 8% to car distance for HGV (longer route due to weight restrictions)
            dist_km  = round(dist_km * 1.08, 1)
            dur_hrs  = round(route["duration"] / 3600 * 1.25, 2)  # HGV slower than car
            return {
                "distance_km":  dist_km,
                "duration_hrs": dur_hrs,
                "source":       "OSRM road routing (HGV-adjusted)",
            }
    except Exception as e:
        logger.warning("OSRM routing failed: %s", e)
    return None


# ── 5. Main routing function ──────────────────────────────────────────────────

def get_road_distance(
    origin:      str,
    destination: str,
    ors_api_key: str = "",
) -> dict:
    """
    Get real road distance between two free-text locations.
    Returns dict with distance_km, duration_hrs, source, origin_coords, dest_coords.

    Priority:
    1. ORS HGV profile (most accurate for heavy trucks) — requires API key
    2. OSRM public (good road routing, car profile + HGV adjustment)
    3. Haversine × 1.35 (straight-line fallback)
    """

    # Step 1: Geocode both ends
    origin_coords = geocode(origin)
    dest_coords   = geocode(destination)

    if not origin_coords:
        return {"error": f"Could not find location: '{origin}'. Try adding city/country."}
    if not dest_coords:
        return {"error": f"Could not find location: '{destination}'. Try adding city/country."}

    # Step 2: ORS HGV routing (best accuracy)
    if ors_api_key:
        result = _ors_route(origin_coords, dest_coords, ors_api_key)
        if result:
            result["origin_coords"] = origin_coords
            result["dest_coords"]   = dest_coords
            return result

    # Step 3: OSRM fallback
    result = _osrm_route(origin_coords, dest_coords)
    if result:
        result["origin_coords"] = origin_coords
        result["dest_coords"]   = dest_coords
        return result

    # Step 4: Haversine last resort
    straight = haversine_km(*origin_coords, *dest_coords)
    road_est = round(straight * 1.35, 1)
    speed_kph = 70.0
    return {
        "distance_km":  road_est,
        "duration_hrs": round(road_est / speed_kph, 2),
        "source":       "Estimated (no internet — straight-line × 1.35)",
        "origin_coords": origin_coords,
        "dest_coords":   dest_coords,
    }


# ── 6. Backwards-compatible wrapper for existing code ─────────────────────────

def estimate_distance(origin: str, destination: str, ors_key: str = "") -> float:
    """
    Drop-in replacement for the old estimate_distance() in routes.py.
    Returns distance in km as a float.
    """
    result = get_road_distance(origin, destination, ors_key)
    if "error" in result:
        logger.warning("estimate_distance: %s", result["error"])
        return 300.0
    return result["distance_km"]


# ── 7. Terrain inference from coordinates ────────────────────────────────────

def infer_terrain(
    origin_coords: tuple[float, float],
    dest_coords:   tuple[float, float],
) -> str:
    """
    Infer terrain type from latitude/longitude context.
    Uses known Eswatini/SA elevation zones.
    """
    lats = [origin_coords[0], dest_coords[0]]
    lons = [origin_coords[1], dest_coords[1]]

    # Eswatini Highveld (mountainous)
    highveld_zones = [
        (-26.40, -26.20, 30.90, 31.30),   # Mbabane / Ngwenya
        (-25.90, -25.70, 31.10, 31.40),   # Piggs Peak
    ]
    for lat1, lat2, lon1, lon2 in highveld_zones:
        for lat, lon in zip(lats, lons):
            if lat1 <= lat <= lat2 and lon1 <= lon <= lon2:
                return "Mountainous"

    # Drakensberg escarpment zone
    if any(-30.0 <= lat <= -25.0 and 29.0 <= lon <= 32.0
           for lat, lon in zip(lats, lons)):
        straight = haversine_km(*origin_coords, *dest_coords)
        if straight > 200:
            return "Rolling"

    # Coastal flat (Durban, Maputo, Richards Bay)
    if any(lat <= -27.0 and lon >= 30.5 for lat, lon in zip(lats, lons)):
        return "Flat"

    return "Rolling"
