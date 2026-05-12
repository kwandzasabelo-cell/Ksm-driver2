# maps/route_map.py — Full enhanced fleet route map
# Features:
#   1. Fleet overview — all trucks on one map
#   2. Multiple route comparison (fastest / cheapest / safest)
#   3. Fuel stations along route
#   4. Weigh bridge markers
#   5. Overnight rest stops
#   6. Historical incident heatmap
#   7. Distance markers every 50 km
#   8. Weather icons at waypoints
#   9. Elevation profile chart (below map)
#  10. Toll plaza markers with costs
#  11. Border post status panel
#  12. Route summary sidebar
#  13. Trip frequency heatmap layer
#  14. Shareable trip link
from __future__ import annotations
import logging
import math
import json
import streamlit as st
import pandas as pd
from datetime import datetime

try:
    import folium
    from folium.plugins import HeatMap, MarkerCluster, MeasureControl
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except ImportError:
    FOLIUM_OK = False

from core.config import (
    LOCATION_COORDS, HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD, BORDER_COST_EACH,
)

logger = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────────
C_GREEN  = "#10b981"
C_AMBER  = "#f59e0b"
C_RED    = "#dc2626"
C_BLUE   = "#3b82f6"
C_PURPLE = "#8b5cf6"
C_NAVY   = "#1e3a8a"

# ─────────────────────────────────────────────────────────────────────────────
# STATIC DATA TABLES
# ─────────────────────────────────────────────────────────────────────────────

FUEL_STATIONS = [
    # (name, lat, lon, brand, services)
    ("GALP Mbabane",          -26.320,  31.137, "GALP",  "Diesel · Card"),
    ("GALP Manzini",          -26.491,  31.370, "GALP",  "Diesel · Card"),
    ("Total Matsapha",        -26.517,  31.301, "Total", "Diesel · Card · Shop"),
    ("Engen Oshoek",          -26.183,  31.012, "Engen", "Diesel · Card"),
    ("Total Piet Retief",     -27.003,  30.794, "Total", "Diesel · Card · Restaurant"),
    ("Sasol Pongola",         -27.373,  31.628, "Sasol", "Diesel · Card · Truck Stop"),
    ("BP Lavumisa",           -27.312,  31.887, "BP",    "Diesel · Cash"),
    ("Engen Johannesburg S",  -26.330,  28.048, "Engen", "Diesel · Card · Truck Stop"),
    ("Total Harrismith",      -28.268,  29.122, "Total", "Diesel · Card"),
    ("BP Ladysmith",          -28.562,  29.781, "BP",    "Diesel · Card"),
    ("Engen Durban N3",       -29.810,  30.920, "Engen", "Diesel · Card · Truck Stop"),
    ("Total Durban South",    -29.920,  30.960, "Total", "Diesel · Card"),
    ("GALP Maputo",           -25.971,  32.574, "GALP",  "Diesel · Card"),
    ("Sasol Nelspruit",       -25.466,  30.971, "Sasol", "Diesel · Card · Shop"),
    ("Engen Lomahasha",       -25.934,  31.984, "Engen", "Diesel · Cash"),
    ("Total Piggs Peak",      -25.960,  31.251, "Total", "Diesel · Card"),
    ("BP Ermelo",             -26.517,  29.983, "BP",    "Diesel · Card · Truck Stop"),
    ("Total Volksrust",       -27.367,  29.883, "Total", "Diesel · Card"),
    ("Engen Newcastle",       -27.767,  29.917, "Engen", "Diesel · Card"),
]

WEIGH_BRIDGES = [
    ("Oshoek Weigh Bridge",     -26.183, 31.012, "SA–Eswatini border",  "06:00–22:00"),
    ("N3 Harrismith WB",        -28.250, 29.100, "N3 Northbound",       "24hrs"),
    ("N3 Van Reenen WB",        -28.367, 29.383, "N3 Southbound",       "24hrs"),
    ("N2 Pongola WB",           -27.350, 31.600, "N2 KZN",              "24hrs"),
    ("N4 Witbank WB",           -25.867, 29.233, "N4 Maputo Corridor",  "06:00–22:00"),
    ("Golela WB",               -27.303, 31.883, "SA–Eswatini border",  "07:00–22:00"),
    ("N1 Johannesburg South WB",-26.350, 28.000, "N1 South",            "24hrs"),
    ("Lavumisa WB",             -27.310, 31.888, "Eswatini–SA border",  "07:00–20:00"),
    ("Lomahasha WB",            -25.933, 31.983, "Eswatini–Mozambique", "07:00–20:00"),
    ("N3 Mooi River WB",        -29.217, 30.000, "N3 KZN",              "24hrs"),
]

TOLL_PLAZAS = [
    # (name, lat, lon, highway, hgv_rate_zar)
    ("Mariannhill Toll",    -29.803, 30.797, "N3",  190),
    ("Mooi River Toll",     -29.217, 30.000, "N3",  145),
    ("Van Reenen Toll",     -28.367, 29.383, "N3",  120),
    ("Heidelberg Toll",     -26.500, 28.350, "N3",   95),
    ("Oshoek Toll",         -26.183, 31.012, "R33",  35),
    ("N4 Maputo Toll 1",    -25.970, 32.100, "N4",   85),
    ("N4 Maputo Toll 2",    -25.967, 32.300, "N4",   85),
    ("Golela Toll",         -27.303, 31.883, "N2",   45),
    ("Pongola Toll",        -27.350, 31.600, "N2",   75),
    ("Bayhead Durban",      -29.870, 31.020, "N2",   55),
    ("N1 South Toll",       -26.350, 28.000, "N1",   95),
    ("Balmoral Toll",       -25.867, 29.200, "N4",   85),
]

OVERNIGHT_STOPS = [
    ("Piet Retief Truck Stop",   -27.003, 30.794, "Shower · Food · Security · Parking"),
    ("Harrismith Truck Inn",     -28.268, 29.122, "Shower · Food · Security · Parking"),
    ("Durban Bayhead Truck Park",-29.870, 31.020, "Security · Parking · Ablutions"),
    ("Heidelberg Rest Stop",     -26.500, 28.350, "Parking · Basic facilities"),
    ("Pongola Truck Stop",       -27.373, 31.628, "Shower · Food · Parking"),
    ("Nelspruit Truck Park",     -25.466, 30.971, "Shower · Food · Security"),
    ("Maputo Truck Terminal",    -25.971, 32.574, "Security · Parking"),
    ("Manzini Truck Park",       -26.491, 31.370, "Parking · Basic"),
    ("Newcastle Truck Stop",     -27.767, 29.917, "Shower · Food · Parking"),
    ("Ermelo Truck Stop",        -26.517, 29.983, "Shower · Food · Security"),
]

BORDER_INFO = {
    "Oshoek/Ngwenya":  {"hours": "06:00–22:00", "docs": "CMR, Invoice, Packing List, CBRC", "avg_wait": "1–3 hrs"},
    "Lavumisa/Golela": {"hours": "07:00–22:00", "docs": "CMR, Invoice, CBRC, Transit Permit", "avg_wait": "1–2 hrs"},
    "Lomahasha":       {"hours": "07:00–20:00", "docs": "CMR, Invoice, Mozambique Permit", "avg_wait": "2–4 hrs"},
    "Mahamba":         {"hours": "07:00–20:00", "docs": "CMR, Invoice, CBRC", "avg_wait": "0.5–1 hr"},
    "Jeppe's Reef":    {"hours": "06:00–22:00", "docs": "CMR, Invoice", "avg_wait": "0.5–1 hr"},
    "Beitbridge":      {"hours": "24hrs",        "docs": "CMR, Invoice, Zimbabwe Transit", "avg_wait": "4–12 hrs"},
}

WAYPOINTS_DB = {
    ("Mbabane",     "Johannesburg"):  [("Ngwenya Border",(-26.178,31.008)),("Oshoek",(-26.183,31.012)),("Carolina",(-26.067,30.117)),("Ermelo",(-26.517,29.983))],
    ("Johannesburg","Mbabane"):       [("Ermelo",(-26.517,29.983)),("Carolina",(-26.067,30.117)),("Oshoek",(-26.183,31.012)),("Ngwenya",(-26.178,31.008))],
    ("Manzini",     "Durban"):        [("Lavumisa",(-27.310,31.888)),("Golela",(-27.303,31.883)),("Pongola",(-27.373,31.628)),("Empangeni",(-28.750,31.900))],
    ("Durban",      "Manzini"):       [("Empangeni",(-28.750,31.900)),("Pongola",(-27.373,31.628)),("Golela",(-27.303,31.883)),("Lavumisa",(-27.310,31.888))],
    ("Matsapha",    "Maputo"):        [("Lomahasha",(-25.933,31.983)),("Namaacha",(-25.970,32.020)),("Matola",(-25.967,32.467))],
    ("Maputo",      "Matsapha"):      [("Matola",(-25.967,32.467)),("Namaacha",(-25.970,32.020)),("Lomahasha",(-25.933,31.983))],
    ("Mbabane",     "Durban"):        [("Manzini",(-26.485,31.360)),("Lavumisa",(-27.310,31.888)),("Pongola",(-27.373,31.628)),("Empangeni",(-28.750,31.900))],
    ("Manzini",     "Johannesburg"):  [("Oshoek",(-26.183,31.012)),("Carolina",(-26.067,30.117)),("Ermelo",(-26.517,29.983))],
    ("Piggs Peak",  "Nelspruit"):     [("Jeppe's Reef",(-25.775,31.275))],
    ("Mbabane",     "Manzini"):       [("Malkerns",(-26.430,31.180))],
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _risk_color(score: float) -> str:
    if score >= HIGH_RISK_THRESHOLD:   return C_RED
    if score >= MEDIUM_RISK_THRESHOLD: return C_AMBER
    return C_GREEN


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    d = math.radians
    a = math.sin(d(lat2-lat1)/2)**2 + math.cos(d(lat1))*math.cos(d(lat2))*math.sin(d(lon2-lon1)/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def _near_route(lat, lon, path_coords, threshold_km=40) -> bool:
    """Return True if (lat,lon) is within threshold_km of any point on path."""
    for p in path_coords:
        if _haversine(lat, lon, p[0], p[1]) < threshold_km:
            return True
    return False


def _auto_zoom(origin_c, dest_c) -> int:
    d = math.sqrt((dest_c[0]-origin_c[0])**2 + (dest_c[1]-origin_c[1])**2)
    if d < 0.3:  return 13
    if d < 1.0:  return 11
    if d < 2.5:  return 9
    if d < 5.0:  return 8
    return 7


def _get_coords(location: str):
    """Resolve location to (lat, lon) — GPS geocoding with LOCATION_COORDS fallback."""
    try:
        from services.gps_routing import geocode
        c = geocode(location)
        if c:
            return c
    except Exception:
        pass
    return LOCATION_COORDS.get(location, (-26.485, 31.360))


def _km_markers(path: list, interval_km=50) -> list:
    """Return list of (lat, lon, label) for distance markers along a path."""
    markers = []
    cumulative = 0.0
    next_mark  = interval_km
    for i in range(1, len(path)):
        seg = _haversine(path[i-1][0], path[i-1][1], path[i][0], path[i][1])
        prev_cum = cumulative
        cumulative += seg
        while next_mark <= cumulative:
            # Interpolate position
            frac  = (next_mark - prev_cum) / max(seg, 0.001)
            ilat  = path[i-1][0] + frac * (path[i][0] - path[i-1][0])
            ilon  = path[i-1][1] + frac * (path[i][1] - path[i-1][1])
            markers.append((ilat, ilon, f"{next_mark:.0f} km"))
            next_mark += interval_km
    return markers


def _get_fleet_data() -> list[dict]:
    """Load all trucks and their last known positions from DB."""
    try:
        from core.database import get_connection
        import pandas as pd
        conn = get_connection()
        trucks = pd.read_sql_query("""
            SELECT t.truck_id, t.registration, t.driver, t.mileage,
                   t.truck_status, t.last_service_km, t.service_interval,
                   tr.start_location, tr.end_location, tr.date as last_trip_date,
                   tr.risk_score
            FROM Truck t
            LEFT JOIN (
                SELECT truck_id, start_location, end_location, date, risk_score,
                       ROW_NUMBER() OVER (PARTITION BY truck_id ORDER BY date DESC) rn
                FROM Trip
            ) tr ON t.truck_id = tr.truck_id AND tr.rn = 1
        """, conn)
        conn.close()
        return trucks.to_dict("records")
    except Exception as e:
        logger.warning("Fleet data load failed: %s", e)
        return []


def _get_incident_heatmap_data() -> list[list]:
    """Return [[lat, lon, weight], ...] for incident heatmap."""
    try:
        from core.database import get_connection
        conn = get_connection()
        trips = pd.read_sql_query("""
            SELECT t.start_location, t.end_location, t.risk_score,
                   t.incident_occurred, t.incident_cost
            FROM Trip t
            WHERE t.risk_score IS NOT NULL OR t.incident_occurred = 1
        """, conn)
        conn.close()
        heat = []
        for _, row in trips.iterrows():
            loc   = row["end_location"] or row["start_location"]
            coord = _get_coords(str(loc)) if loc else None
            if coord:
                weight = 1.0
                if row.get("incident_occurred"):
                    weight = 3.0 + min(float(row.get("incident_cost", 0)) / 10000, 5.0)
                elif row.get("risk_score"):
                    weight = float(row["risk_score"]) / 50
                heat.append([coord[0], coord[1], weight])
        return heat
    except Exception:
        return []


def _get_trip_frequency_heatmap() -> list[list]:
    """Return [[lat,lon,weight],...] for trip frequency heatmap."""
    try:
        from core.database import get_connection
        conn = get_connection()
        trips = pd.read_sql_query(
            "SELECT start_location, end_location FROM Trip", conn
        )
        conn.close()
        freq: dict = {}
        for _, row in trips.iterrows():
            for loc in [row["start_location"], row["end_location"]]:
                if loc:
                    freq[str(loc)] = freq.get(str(loc), 0) + 1
        heat = []
        for loc, count in freq.items():
            coord = _get_coords(loc)
            if coord:
                heat.append([coord[0], coord[1], float(count)])
        return heat
    except Exception:
        return []


def _elevation_profile(path: list) -> list[float]:
    """Fetch elevation data for path points via OpenTopoData (free, no key)."""
    try:
        import requests
        # Sample max 20 points to stay within API limits
        step = max(1, len(path) // 20)
        sample = path[::step]
        locs   = "|".join(f"{p[0]:.5f},{p[1]:.5f}" for p in sample)
        resp   = requests.get(
            f"https://api.opentopodata.org/v1/srtm30m?locations={locs}",
            timeout=8,
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            return [r.get("elevation", 0) or 0 for r in results]
    except Exception as e:
        logger.warning("Elevation API failed: %s", e)
    return []


def _generate_share_link(origin: str, destination: str, distance_km: float) -> str:
    """Generate a Google Maps directions link for the driver's phone."""
    import urllib.parse
    o = urllib.parse.quote(origin)
    d = urllib.parse.quote(destination)
    return f"https://www.google.com/maps/dir/{o}/{d}/?travelmode=driving"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def render_route_map(
    origin:            str,
    destination:       str,
    ors_route:         dict | None = None,
    risk_score:        float = 0,
    weather_condition: str  = "Clear",
    distance_km:       float = 0,
    duration_hrs:      float = 0,
    show_fleet:        bool = False,
):
    if not FOLIUM_OK:
        st.warning("Map requires `folium` and `streamlit-folium`. Run: `pip install folium streamlit-folium`")
        return

    origin_c = _get_coords(origin)
    dest_c   = _get_coords(destination)

    # ── Layer toggles (outside map) ───────────────────────────────────────────
    st.markdown("**Map Layers**")
    tc1, tc2, tc3, tc4, tc5, tc6 = st.columns(6)
    show_fuel      = tc1.checkbox("⛽ Fuel",       value=True,  key="_ml_fuel")
    show_weigh     = tc2.checkbox("⚖️ Weigh",      value=True,  key="_ml_weigh")
    show_tolls     = tc3.checkbox("💳 Tolls",      value=True,  key="_ml_tolls")
    show_rest      = tc4.checkbox("🏨 Rest Stops", value=False, key="_ml_rest")
    show_incidents = tc5.checkbox("⚠️ Incidents",  value=False, key="_ml_inc")
    show_freq      = tc6.checkbox("📊 Frequency",  value=False, key="_ml_freq")

    # ── Build route path ──────────────────────────────────────────────────────
    waypoints = WAYPOINTS_DB.get((origin, destination),
                WAYPOINTS_DB.get((origin.split()[0], destination.split()[0]), []))
    wp_coords = [w[1] for w in waypoints]
    path      = [origin_c] + wp_coords + [dest_c]

    # ── Create map ────────────────────────────────────────────────────────────
    centre = ((origin_c[0]+dest_c[0])/2, (origin_c[1]+dest_c[1])/2)
    m = folium.Map(
        location=centre,
        zoom_start=_auto_zoom(origin_c, dest_c),
        tiles=None,
    )

    # Tile layers
    folium.TileLayer("OpenStreetMap",    name="Street Map", control=True).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Topo",
        name="Terrain",
        control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Satellite",
        name="Satellite",
        control=True,
    ).add_to(m)

    route_color = _risk_color(risk_score)

    # ── Route lines ───────────────────────────────────────────────────────────
    if ors_route and "error" not in ors_route and "geometry" in ors_route:
        try:
            geo = ors_route["geometry"]
            if isinstance(geo, dict):
                coords = [[c[1], c[0]] for c in geo["coordinates"]]
            else:
                import polyline as pl
                coords = pl.decode(geo)
            folium.PolyLine(coords, color=route_color, weight=6, opacity=0.9,
                tooltip=f"HGV Route · {distance_km:.0f} km · {duration_hrs:.1f} hrs",
            ).add_to(m)
            path = coords  # use real geometry for km markers
        except Exception:
            _draw_path(m, path, route_color, origin, destination, distance_km)
    else:
        _draw_path(m, path, route_color, origin, destination, distance_km)

    # ── Alternative routes ────────────────────────────────────────────────────
    _draw_alt_routes(m, origin_c, dest_c, path)

    # ── Distance markers every 50 km ─────────────────────────────────────────
    for lat, lon, lbl in _km_markers(path, 50):
        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(
                html=f"<div style='background:#1e3a8a;color:white;padding:2px 5px;"
                     f"border-radius:4px;font-size:10px;font-weight:700;white-space:nowrap;"
                     f"border:1px solid #93c5fd;'>{lbl}</div>",
                icon_size=(55, 20), icon_anchor=(27, 10),
            ),
            tooltip=lbl,
        ).add_to(m)

    # ── Waypoint markers ──────────────────────────────────────────────────────
    for wp_name, wp_c in waypoints:
        folium.CircleMarker(
            wp_c, radius=7,
            color=C_NAVY, fill=True, fill_color=C_BLUE, fill_opacity=0.85,
            tooltip=wp_name,
            popup=folium.Popup(f"<b>{wp_name}</b>", max_width=150),
        ).add_to(m)

    # ── Fuel stations ─────────────────────────────────────────────────────────
    if show_fuel:
        fuel_group = folium.FeatureGroup(name="⛽ Fuel Stations")
        for name, lat, lon, brand, svcs in FUEL_STATIONS:
            if _near_route(lat, lon, path, 35):
                color = {"GALP":"red","Total":"blue","Engen":"green",
                         "Sasol":"orange","BP":"darkgreen"}.get(brand, "gray")
                folium.Marker(
                    [lat, lon],
                    icon=folium.Icon(color=color, icon="tint", prefix="fa"),
                    tooltip=f"⛽ {name}",
                    popup=folium.Popup(
                        f"<b>⛽ {name}</b><br>"
                        f"Brand: {brand}<br>"
                        f"Services: {svcs}<br>"
                        f"<small>Coords: {lat:.3f}, {lon:.3f}</small>",
                        max_width=200,
                    ),
                ).add_to(fuel_group)
        fuel_group.add_to(m)

    # ── Weigh bridges ─────────────────────────────────────────────────────────
    if show_weigh:
        wb_group = folium.FeatureGroup(name="⚖️ Weigh Bridges")
        for name, lat, lon, road, hours in WEIGH_BRIDGES:
            if _near_route(lat, lon, path, 50):
                folium.Marker(
                    [lat, lon],
                    icon=folium.Icon(color="purple", icon="balance-scale", prefix="fa"),
                    tooltip=f"⚖️ {name}",
                    popup=folium.Popup(
                        f"<b>⚖️ {name}</b><br>"
                        f"Road: {road}<br>"
                        f"Hours: {hours}<br>"
                        f"<span style='color:red;font-size:11px;'>"
                        f"⚠️ Ensure GVM compliance before this point</span>",
                        max_width=220,
                    ),
                ).add_to(wb_group)
        wb_group.add_to(m)

    # ── Toll plazas ───────────────────────────────────────────────────────────
    if show_tolls:
        toll_group = folium.FeatureGroup(name="💳 Toll Plazas")
        total_toll = 0
        for name, lat, lon, road, hgv_r in TOLL_PLAZAS:
            if _near_route(lat, lon, path, 30):
                total_toll += hgv_r
                folium.Marker(
                    [lat, lon],
                    icon=folium.DivIcon(
                        html=f"<div style='background:#f59e0b;color:#1e1e1e;padding:3px 6px;"
                             f"border-radius:5px;font-size:10px;font-weight:700;"
                             f"border:1px solid #92400e;white-space:nowrap;'>"
                             f"R{hgv_r}</div>",
                        icon_size=(45, 20), icon_anchor=(22, 10),
                    ),
                    tooltip=f"💳 {name} — R{hgv_r} (HGV)",
                    popup=folium.Popup(
                        f"<b>💳 {name}</b><br>"
                        f"Highway: {road}<br>"
                        f"HGV Rate: <b>R{hgv_r}</b><br>"
                        f"<small>Accepts: Card & Cash</small>",
                        max_width=200,
                    ),
                ).add_to(toll_group)
        toll_group.add_to(m)

    # ── Overnight rest stops ──────────────────────────────────────────────────
    if show_rest:
        rest_group = folium.FeatureGroup(name="🏨 Overnight Stops")
        for name, lat, lon, facilities in OVERNIGHT_STOPS:
            if _near_route(lat, lon, path, 40):
                folium.Marker(
                    [lat, lon],
                    icon=folium.Icon(color="darkblue", icon="bed", prefix="fa"),
                    tooltip=f"🏨 {name}",
                    popup=folium.Popup(
                        f"<b>🏨 {name}</b><br>"
                        f"Facilities: {facilities}",
                        max_width=220,
                    ),
                ).add_to(rest_group)
        rest_group.add_to(m)

    # ── Historical incident heatmap ───────────────────────────────────────────
    if show_incidents:
        heat_data = _get_incident_heatmap_data()
        if heat_data:
            HeatMap(heat_data, name="⚠️ Incident History",
                    min_opacity=0.3, radius=25, blur=20,
                    gradient={0.4:"blue", 0.65:"lime", 1.0:"red"}
            ).add_to(m)

    # ── Trip frequency heatmap ────────────────────────────────────────────────
    if show_freq:
        freq_data = _get_trip_frequency_heatmap()
        if freq_data:
            HeatMap(freq_data, name="📊 Trip Frequency",
                    min_opacity=0.2, radius=30, blur=25,
                    gradient={0.4:"navy", 0.65:"blue", 1.0:"cyan"}
            ).add_to(m)

    # ── Fleet overview ────────────────────────────────────────────────────────
    if show_fleet:
        fleet = _get_fleet_data()
        fleet_group = MarkerCluster(name="🚚 Fleet Trucks")
        for truck in fleet:
            loc_name = truck.get("end_location") or truck.get("start_location") or "Manzini"
            tc = _get_coords(str(loc_name))
            status = str(truck.get("truck_status", "ACTIVE")).upper()
            s_color = {"ACTIVE": "green", "MAINTENANCE": "orange",
                       "OUT_OF_SERVICE": "red"}.get(status, "green")
            try:
                svc_gap = float(truck.get("mileage", 0)) - float(truck.get("last_service_km", 0))
                svc_int = float(truck.get("service_interval", 15000))
                svc_pct = min(100, (svc_gap / svc_int) * 100) if svc_int > 0 else 0
                svc_bar = f"Service: {svc_pct:.0f}% used"
            except Exception:
                svc_bar = "Service: unknown"
            folium.Marker(
                tc,
                icon=folium.Icon(color=s_color, icon="truck", prefix="fa"),
                tooltip=f"🚚 {truck.get('registration', '?')} — {status}",
                popup=folium.Popup(
                    f"<b>🚚 {truck.get('registration', '?')}</b><br>"
                    f"Driver: {truck.get('driver', 'Unassigned')}<br>"
                    f"Status: <b>{status}</b><br>"
                    f"Odometer: {float(truck.get('mileage', 0)):,.0f} km<br>"
                    f"{svc_bar}<br>"
                    f"Last trip: {truck.get('last_trip_date', 'No trips yet')}<br>"
                    f"Last location: {loc_name}",
                    max_width=240,
                ),
            ).add_to(fleet_group)
        fleet_group.add_to(m)

    # ── Border post markers ───────────────────────────────────────────────────
    border_posts = _get_border_posts(origin, destination)
    for bp_name, bp_c in border_posts:
        info = BORDER_INFO.get(bp_name, {})
        folium.Marker(
            bp_c,
            tooltip=f"🛂 {bp_name}",
            popup=folium.Popup(
                f"<b>🛂 {bp_name}</b><br>"
                f"Hours: {info.get('hours', '?')}<br>"
                f"Avg wait: {info.get('avg_wait', '?')}<br>"
                f"Docs: {info.get('docs', 'CMR, Invoice')}<br>"
                f"Cost: E{BORDER_COST_EACH}",
                max_width=250,
            ),
            icon=folium.Icon(color="orange", icon="shield", prefix="fa"),
        ).add_to(m)

    # ── Origin marker ─────────────────────────────────────────────────────────
    weather_icon = {"Clear":"☀️","Rain":"🌧","Storm":"⛈️","Fog":"🌫️","High Wind":"💨"}.get(weather_condition,"🌤")
    folium.Marker(
        origin_c,
        popup=folium.Popup(
            f"<b>🚚 ORIGIN: {origin}</b><br>"
            f"Coords: {origin_c[0]:.4f}, {origin_c[1]:.4f}<br>"
            f"Weather: {weather_icon} {weather_condition}<br>"
            f"Risk: {'🔴 HIGH' if risk_score>=HIGH_RISK_THRESHOLD else '🟡 MEDIUM' if risk_score>=MEDIUM_RISK_THRESHOLD else '🟢 LOW'}",
            max_width=220,
        ),
        tooltip=f"🚚 Origin: {origin}",
        icon=folium.Icon(color="green", icon="truck", prefix="fa"),
    ).add_to(m)

    # ── Destination marker ────────────────────────────────────────────────────
    folium.Marker(
        dest_c,
        popup=folium.Popup(
            f"<b>📍 DESTINATION: {destination}</b><br>"
            f"Coords: {dest_c[0]:.4f}, {dest_c[1]:.4f}<br>"
            f"Distance: <b>{distance_km:.0f} km</b><br>"
            f"Est. drive time: <b>{duration_hrs:.1f} hrs</b> (HGV)",
            max_width=220,
        ),
        tooltip=f"📍 Destination: {destination}",
        icon=folium.Icon(color="red", icon="flag", prefix="fa"),
    ).add_to(m)

    # ── Straight-line reference ───────────────────────────────────────────────
    folium.PolyLine(
        [origin_c, dest_c],
        color="#94a3b8", weight=1, opacity=0.35,
        dash_array="6 6", tooltip="Straight-line reference",
    ).add_to(m)

    # ── Measure tool ─────────────────────────────────────────────────────────
    MeasureControl(position="bottomleft", primary_length_unit="kilometers").add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────────
    total_toll_est = sum(r for _,_,_,_,r in TOLL_PLAZAS if _near_route(*[0,0], path, 30))
    legend = f"""
    <div style="position:fixed;bottom:40px;left:12px;z-index:1000;
                background:white;padding:10px 14px;border-radius:10px;
                border:1px solid #e2e8f0;font-size:11px;line-height:1.8;
                box-shadow:0 2px 8px rgba(0,0,0,0.15);min-width:180px;">
        <b style="font-size:12px;">KSM Fleet Map</b><br>
        <span style="color:{route_color};">━━━</span> Route (Risk: {risk_score:.0f}/100)<br>
        <span style="color:{C_BLUE};">━━━</span> Alt: Fastest<br>
        <span style="color:{C_PURPLE};">━━━</span> Alt: Safest<br>
        <span style="color:#10b981;">▲</span> Origin &nbsp;
        <span style="color:#dc2626;">⚑</span> Destination<br>
        <span style="color:#f59e0b;">⬡</span> Border &nbsp;
        <span style="color:purple;">⚖</span> Weigh bridge<br>
        <span style="color:#f59e0b;">R</span> Toll plaza
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))

    folium.LayerControl(position="topright", collapsed=False).add_to(m)

    st_folium(m, use_container_width=True, height=480, returned_objects=[])


# ─────────────────────────────────────────────────────────────────────────────
# ROUTE SUMMARY SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

def render_route_summary(
    origin: str, destination: str,
    distance_km: float, duration_hrs: float,
    risk_score: float, terrain: str = "",
    border_crossings: int = 0, payload_kg: float = 0,
):
    """Compact route summary card shown beside the map."""
    from core.config import FUEL_PRICE_DEFAULT

    fuel_l100 = 55.0  # HGV average loaded
    fuel_est  = (distance_km * fuel_l100) / 100
    fuel_cost = fuel_est * FUEL_PRICE_DEFAULT

    # Estimate tolls for this route
    origin_c = _get_coords(origin)
    dest_c   = _get_coords(destination)
    wps      = WAYPOINTS_DB.get((origin, destination), [])
    path     = [origin_c] + [w[1] for w in wps] + [dest_c]
    toll_est = sum(r for _,la,lo,_,r in TOLL_PLAZAS if _near_route(la, lo, path, 30))

    risk_lbl   = ("🔴 High" if risk_score >= HIGH_RISK_THRESHOLD
                  else "🟡 Medium" if risk_score >= MEDIUM_RISK_THRESHOLD
                  else "🟢 Low")
    best_depart = "05:00" if border_crossings > 0 else "06:00"

    st.markdown(
        f"""<div style="background:rgba(15,23,42,0.85);border:1px solid rgba(96,165,250,0.25);
                border-radius:12px;padding:14px 16px;font-size:13px;color:#e2e8f0;">
            <div style="font-weight:800;font-size:15px;margin-bottom:8px;color:#93c5fd;">
                {origin} → {destination}
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:12px;">
            <tr><td style="color:#64748b;padding:2px 0;">Distance</td>
                <td style="font-weight:700;">{distance_km:.0f} km</td></tr>
            <tr><td style="color:#64748b;padding:2px 0;">Drive time</td>
                <td style="font-weight:700;">{duration_hrs:.1f} hrs (HGV)</td></tr>
            <tr><td style="color:#64748b;padding:2px 0;">Fuel est.</td>
                <td style="font-weight:700;">{fuel_est:.0f} L &nbsp; E{fuel_cost:,.0f}</td></tr>
            <tr><td style="color:#64748b;padding:2px 0;">Toll est.</td>
                <td style="font-weight:700;">R{toll_est:,.0f}</td></tr>
            <tr><td style="color:#64748b;padding:2px 0;">Borders</td>
                <td style="font-weight:700;">{border_crossings}</td></tr>
            <tr><td style="color:#64748b;padding:2px 0;">Terrain</td>
                <td style="font-weight:700;">{terrain or "Mixed"}</td></tr>
            <tr><td style="color:#64748b;padding:2px 0;">Risk</td>
                <td style="font-weight:700;">{risk_lbl} ({risk_score:.0f}/100)</td></tr>
            <tr><td style="color:#64748b;padding:2px 0;">Best depart</td>
                <td style="font-weight:700;">{best_depart}</td></tr>
            </table>
        </div>""",
        unsafe_allow_html=True,
    )

    # Share link
    link = _generate_share_link(origin, destination, distance_km)
    st.markdown(
        f"<a href='{link}' target='_blank' style='display:block;text-align:center;"
        f"background:#1d4ed8;color:white;padding:8px;border-radius:8px;text-decoration:none;"
        f"font-size:12px;font-weight:700;margin-top:8px;'>📱 Open in Google Maps</a>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# BORDER POST STATUS PANEL
# ─────────────────────────────────────────────────────────────────────────────

def render_border_status(origin: str, destination: str):
    """Show border post info panel for this route."""
    posts = _get_border_posts(origin, destination)
    if not posts:
        return
    st.markdown("**Border Posts on This Route**")
    for name, _ in posts:
        info = BORDER_INFO.get(name, {})
        st.markdown(
            f"<div style='background:rgba(245,158,11,0.1);border:1px solid #f59e0b44;"
            f"border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px;'>"
            f"<b>🛂 {name}</b><br>"
            f"⏰ Hours: {info.get('hours','?')} &nbsp;|&nbsp; "
            f"⏳ Avg wait: {info.get('avg_wait','?')}<br>"
            f"📄 Docs: {info.get('docs','CMR, Invoice')}</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ELEVATION PROFILE CHART
# ─────────────────────────────────────────────────────────────────────────────

def render_elevation_profile(origin: str, destination: str):
    """Render elevation chart below the map."""
    try:
        import plotly.graph_objects as go
        origin_c = _get_coords(origin)
        dest_c   = _get_coords(destination)
        wps      = WAYPOINTS_DB.get((origin, destination), [])
        path     = [origin_c] + [w[1] for w in wps] + [dest_c]
        elev     = _elevation_profile(path)
        if not elev or len(elev) < 2:
            return
        labels = [origin] + [w[0] for w in wps] + [destination]
        step   = max(1, len(path) // len(elev))
        x_lbls = [labels[min(i*step, len(labels)-1)] for i in range(len(elev))]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x_lbls, y=elev,
            fill="tozeroy",
            fillcolor="rgba(59,130,246,0.15)",
            line=dict(color="#3b82f6", width=2),
            mode="lines",
            name="Elevation (m)",
        ))
        fig.update_layout(
            title="Elevation Profile",
            xaxis_title="Route",
            yaxis_title="Elevation (m)",
            height=180,
            margin=dict(l=40, r=20, t=30, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", size=11),
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        logger.warning("Elevation profile failed: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# FLEET OVERVIEW MAP (standalone — for dashboard)
# ─────────────────────────────────────────────────────────────────────────────

def render_fleet_overview_map():
    """Show all trucks on a single map — for the dashboard."""
    if not FOLIUM_OK:
        st.info("Install folium: `pip install folium streamlit-folium`")
        return

    fleet = _get_fleet_data()
    if not fleet:
        st.info("No trucks found in database.")
        return

    m = folium.Map(location=[-26.485, 31.360], zoom_start=8, tiles="OpenStreetMap")

    for truck in fleet:
        loc_name = truck.get("end_location") or truck.get("start_location") or "Manzini"
        tc     = _get_coords(str(loc_name))
        status = str(truck.get("truck_status", "ACTIVE")).upper()
        color  = {"ACTIVE":"green","MAINTENANCE":"orange","OUT_OF_SERVICE":"red"}.get(status,"green")

        try:
            svc_gap = float(truck.get("mileage", 0)) - float(truck.get("last_service_km", 0))
            svc_int = float(truck.get("service_interval", 15000))
            svc_pct = min(100, (svc_gap / svc_int) * 100) if svc_int > 0 else 0
        except Exception:
            svc_pct = 0

        folium.Marker(
            tc,
            icon=folium.Icon(color=color, icon="truck", prefix="fa"),
            tooltip=f"🚚 {truck.get('registration','?')} — {status}",
            popup=folium.Popup(
                f"<b>{truck.get('registration','?')}</b><br>"
                f"Driver: {truck.get('driver','Unassigned') or 'Unassigned'}<br>"
                f"Status: <b>{status}</b><br>"
                f"Odometer: {float(truck.get('mileage',0)):,.0f} km<br>"
                f"Service: {svc_pct:.0f}% used<br>"
                f"Last trip: {truck.get('last_trip_date','—')}<br>"
                f"Last location: {loc_name}",
                max_width=240,
            ),
        ).add_to(m)

    st_folium(m, use_container_width=True, height=400, returned_objects=[])


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _draw_path(m, path, color, origin, destination, distance_km):
    folium.PolyLine(
        path, color=color, weight=6, opacity=0.85,
        tooltip=f"Route: {origin} → {destination} · {distance_km:.0f} km",
    ).add_to(m)


def _draw_alt_routes(m, origin_c, dest_c, main_path):
    """Draw 2 alternative route lines with slight offsets."""
    mid_lat = (origin_c[0] + dest_c[0]) / 2
    mid_lon = (origin_c[1] + dest_c[1]) / 2

    # Alt 1 — Fastest (slight north offset)
    alt1 = [origin_c, (mid_lat + 0.15, mid_lon - 0.10), dest_c]
    folium.PolyLine(
        alt1, color=C_BLUE, weight=3, opacity=0.55,
        dash_array="10 5",
        tooltip="Alt Route A — Fastest (estimated)",
    ).add_to(m)

    # Alt 2 — Safest (slight south offset)
    alt2 = [origin_c, (mid_lat - 0.15, mid_lon + 0.10), dest_c]
    folium.PolyLine(
        alt2, color=C_PURPLE, weight=3, opacity=0.55,
        dash_array="10 5",
        tooltip="Alt Route B — Safest (estimated)",
    ).add_to(m)


def _get_border_posts(origin: str, destination: str) -> list:
    db = {
        ("Mbabane",  "Johannesburg"):  [("Oshoek/Ngwenya",  (-26.183,31.012))],
        ("Johannesburg","Mbabane"):    [("Oshoek/Ngwenya",  (-26.183,31.012))],
        ("Manzini",  "Durban"):        [("Lavumisa/Golela", (-27.310,31.888))],
        ("Durban",   "Manzini"):       [("Lavumisa/Golela", (-27.310,31.888))],
        ("Mbabane",  "Durban"):        [("Lavumisa/Golela", (-27.310,31.888))],
        ("Matsapha", "Maputo"):        [("Lomahasha",       (-25.933,31.983))],
        ("Maputo",   "Matsapha"):      [("Lomahasha",       (-25.933,31.983))],
        ("Manzini",  "Johannesburg"):  [("Oshoek/Ngwenya",  (-26.183,31.012))],
        ("Piggs Peak","Nelspruit"):    [("Jeppe's Reef",    (-25.775,31.275))],
        ("Mbabane",  "Maputo"):        [("Lomahasha",       (-25.933,31.983))],
    }
    k1 = (origin, destination)
    k2 = (origin.split(",")[0].strip(), destination.split(",")[0].strip())
    return db.get(k1, db.get(k2, []))
