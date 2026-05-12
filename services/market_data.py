# services/market_data.py — Live market data, weather and ORS route fetching
from __future__ import annotations
import logging
import requests
from datetime import datetime
import streamlit as st
from core.config import WMO_MAP, FUEL_PRICE_DEFAULT

@st.cache_data(ttl=1800)
def fetch_live_market_data():
    # -------------------------------------------------------------------------
    # Fallback values updated to real market data as of 31 March 2026:
    #   USD/SZL  ≈ 17.17  (fx-rate.net, 30 Mar 2026)
    #   WTI      ≈ 100.00 (elevated due to Strait of Hormuz crisis, Mar 2026)
    #   Diesel pump price Eswatini: E19.85/L (GlobalPetrolPrices, 23 Mar 2026)
    # -------------------------------------------------------------------------
    data = {
        "fuel_price":  19.85,
        "usd_szl":     17.17,
        "crude_usd":   100.00,
        "source":      "fallback (offline)",
        "timestamp":   datetime.now().strftime("%H:%M %d %b %Y"),
    }

    # --- USD/SZL: try open.er-api first, then exchangerate-api as backup ---
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        if r.status_code == 200:
            rates = r.json().get("rates", {})
            if "SZL" in rates:
                data["usd_szl"] = round(rates["SZL"], 2)
                data["source"] = "open.er-api.com"
    except Exception as e:
        logging.warning(f"USD/SZL fetch (open.er-api) failed: {e}")

    if data["source"] == "fallback (offline)":
        try:
            r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
            if r.status_code == 200:
                rates = r.json().get("rates", {})
                if "SZL" in rates:
                    data["usd_szl"] = round(rates["SZL"], 2)
                    data["source"] = "exchangerate-api.com"
        except Exception as e:
            logging.warning(f"USD/SZL fetch (exchangerate-api) failed: {e}")

    # --- WTI Crude: Yahoo Finance with improved header set ---
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=1d&range=1d",
            headers=headers, timeout=8
        )
        if r.status_code == 200:
            result = r.json()
            price = result["chart"]["result"][0]["meta"]["regularMarketPrice"]
            data["crude_usd"] = round(float(price), 2)
            if data["source"] == "fallback (offline)":
                data["source"] = "Yahoo Finance"
            else:
                data["source"] += " + Yahoo Finance"
    except Exception as e:
        logging.warning(f"Crude oil fetch (Yahoo) failed: {e}")

    # --- Fallback crude: try query2 mirror ---
    if "Yahoo Finance" not in data["source"]:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(
                "https://query2.finance.yahoo.com/v8/finance/chart/CL=F?interval=1d&range=1d",
                headers=headers, timeout=8
            )
            if r.status_code == 200:
                result = r.json()
                price = result["chart"]["result"][0]["meta"]["regularMarketPrice"]
                data["crude_usd"] = round(float(price), 2)
                if data["source"] == "fallback (offline)":
                    data["source"] = "Yahoo Finance (q2)"
                else:
                    data["source"] += " + Yahoo Finance (q2)"
        except Exception as e:
            logging.warning(f"Crude oil fetch (Yahoo q2) failed: {e}")

    try:
        # Eswatini imports refined products from Durban refineries.
        # Formula: (crude $/bbl ÷ 159 L/bbl) × SZL/USD × refining/retail margin factor.
        # Margin factor ~2.10 was calibrated for ~$82 crude; with crude at ~$100
        # the regulated pump price does not scale linearly (government subsidy buffers).
        # We use a blended factor and clamp to the observed regulatory range.
        crude_per_litre = data["crude_usd"] / 159.0
        estimated_pump = crude_per_litre * data["usd_szl"] * 1.75
        # Clamp: E19.85/L is the verified March 2026 diesel pump price (GlobalPetrolPrices).
        # Allow up to E32/L to capture further crude spikes without over-clamping.
        data["fuel_price"] = round(max(18.0, min(32.0, estimated_pump)), 2)
        data["fuel_price_note"] = "estimated from crude + FX (calibrated Mar 2026)"
    except Exception as e:
        logging.warning(f"Fuel price estimation failed: {e}")
        data["fuel_price_note"] = "official fallback (E19.85/L, Mar 2026)"

    data["timestamp"] = datetime.now().strftime("%H:%M %d %b %Y")
    return data

@st.cache_data(ttl=900)
def fetch_weather_for_location(lat: float, lon: float, location_name: str = ""):
    def decode_wmo(code):
        for rng, (label, idx) in WMO_MAP.items():
            if isinstance(rng, range) and code in rng:
                return label, idx
            if isinstance(rng, int) and code == rng:
                return label, idx
        return "Clear", 0

    defaults = {
        "temperature":       25.0,
        "wind_speed":        15.0,
        "rainfall":          0.0,
        "weather_label":     "Clear",
        "weather_condition": "Clear",
        "weather_code":      0,
        "source":            "fallback",
        "timestamp":         datetime.now().strftime("%H:%M"),
        "location":          location_name,
    }

    try:
        params = {
            "latitude":  lat,
            "longitude": lon,
            "current":   "temperature_2m,wind_speed_10m,precipitation,weather_code",
            "hourly":    "precipitation_probability",
            "forecast_days": 1,
            "timezone":  "Africa/Johannesburg",
        }
        r = requests.get("https://api.open-meteo.com/v1/forecast",
                         params=params, timeout=8)
        if r.status_code == 200:
            d = r.json()
            current = d.get("current", {})
            temp = current.get("temperature_2m", 25.0)
            wind = current.get("wind_speed_10m", 15.0)
            rain = current.get("precipitation", 0.0)
            wcode = int(current.get("weather_code", 0))
            label, _ = decode_wmo(wcode)

            if wind > 50:
                label = "High Wind"

            return {
                "temperature":       round(float(temp), 1),
                "wind_speed":        round(float(wind), 1),
                "rainfall":          round(float(rain), 1),
                "weather_label":     label,
                "weather_condition": label,
                "weather_code":      wcode,
                "source":            "Open-Meteo (live)",
                "timestamp":         datetime.now().strftime("%H:%M"),
                "location":          location_name,
            }
    except Exception as e:
        logging.error(f"Weather fetch failed: {e}")

    return defaults

@st.cache_data(ttl=3600)
def fetch_ors_route(origin_coords: tuple, dest_coords: tuple,
                    truck_weight_kg: int, ors_api_key: str):
    if not ors_api_key or ors_api_key.strip() == "":
        return {"error": "No API key provided"}

    try:
        coords = [
            [origin_coords[1], origin_coords[0]],
            [dest_coords[1],   dest_coords[0]],
        ]
        weight_tonnes = round(truck_weight_kg / 1000, 1)

        payload = {
            "coordinates": coords,
            "profile":     "driving-hgv",
            "extra_info":  ["surface", "steepness"],
            "attributes":  ["avgspeed", "detourfactor"],
            "options": {
                "profile_params": {
                    "restrictions": {
                        "weight":       weight_tonnes,
                        "axleload":     weight_tonnes / 2,
                        "length":       16.5,
                        "width":        2.55,
                        "height":       4.0,
                        "hazmat":       False,
                    }
                }
            },
            "units": "km",
            "geometry": True,
        }

        headers = {
            "Authorization": ors_api_key,
            "Content-Type":  "application/json",
        }

        r = requests.post(
            "https://api.openrouteservice.org/v2/directions/driving-hgv",
            json=payload, headers=headers, timeout=12
        )

        if r.status_code == 200:
            data = r.json()
            segment = data["routes"][0]["segments"][0]
            summary = data["routes"][0]["summary"]
            extras = data["routes"][0].get("extras", {})

            distance_km = round(summary["distance"], 1)
            duration_hrs = round(summary["duration"] / 3600, 2)

            steepness_vals = []
            if "steepness" in extras:
                for seg in extras["steepness"].get("values", []):
                    steepness_vals.append(abs(seg[2]))
            avg_gradient = round(sum(steepness_vals) / len(steepness_vals), 2) if steepness_vals else 1.5

            surface_data = extras.get("surface", {}).get("values", [])
            paved_segments = sum(1 for s in surface_data if s[2] in [1, 3, 5, 6, 7, 8])
            total_segments = len(surface_data) if surface_data else 1
            road_quality = round(paved_segments / total_segments, 2) if total_segments else 0.75
            road_quality = max(0.4, min(0.99, road_quality))

            if avg_gradient > 3.0:
                terrain = "Mountainous"
            elif avg_gradient > 1.5:
                terrain = "Rolling"
            else:
                terrain = "Flat"

            warnings_list = [w.get("message", "") for w in data["routes"][0].get("warnings", [])]

            return {
                "distance":        distance_km,
                "duration":        duration_hrs,
                "gradient":        avg_gradient,
                "road_quality":    road_quality,
                "terrain":         terrain,
                "accident_risk":   0.25 + (avg_gradient * 0.02),
                "theft_risk":      0.15,
                "border_crossings": 0,
                "tolls":           distance_km * 0.3,
                "source":          "OpenRouteService HGV (live)",
                "warnings":        warnings_list,
                "surface_quality": f"{road_quality*100:.0f}%",
            }
        else:
            # Attempt to parse error
            error_msg = f"ORS returned {r.status_code}"
            try:
                err_data = r.json()
                error_msg = err_data.get("error", {}).get("message", error_msg)
            except:
                pass
            return {"error": error_msg}
    except Exception as e:
        logging.error(f"ORS route fetch exception: {e}")
        return {"error": str(e)}
