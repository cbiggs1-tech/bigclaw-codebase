#!/usr/bin/env python3
"""Weather for BigClaw. Uses Open-Meteo (free, no API key).

Usage:
    python3 weather.py                          # Default: Alvarado, TX
    python3 weather.py --lat 32.41 --lon -97.21
    python3 weather.py --json
"""

import argparse
import json
import requests

# Alvarado, TX
DEFAULT_LAT = 32.41
DEFAULT_LON = -97.21
DEFAULT_LOCATION = "Alvarado, TX"

WMO_CODES = {
    0: "☀️ Clear", 1: "🌤️ Mostly clear", 2: "⛅ Partly cloudy", 3: "☁️ Overcast",
    45: "🌫️ Fog", 48: "🌫️ Icy fog",
    51: "🌦️ Light drizzle", 53: "🌦️ Drizzle", 55: "🌧️ Heavy drizzle",
    61: "🌧️ Light rain", 63: "🌧️ Rain", 65: "🌧️ Heavy rain",
    71: "🌨️ Light snow", 73: "🌨️ Snow", 75: "🌨️ Heavy snow",
    80: "🌧️ Rain showers", 81: "🌧️ Moderate showers", 82: "⛈️ Heavy showers",
    85: "🌨️ Snow showers", 86: "🌨️ Heavy snow showers",
    95: "⛈️ Thunderstorm", 96: "⛈️ Thunderstorm + hail", 99: "⛈️ Severe thunderstorm",
}

WIND_DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def get_wind_direction(degrees):
    idx = round(degrees / 22.5) % 16
    return WIND_DIRS[idx]


def get_weather(lat=DEFAULT_LAT, lon=DEFAULT_LON):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
        "temperature_unit": "fahrenheit",
        "windspeed_unit": "mph",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
        "forecast_days": 3,
        "timezone": "America/Chicago",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def format_weather(data, location=DEFAULT_LOCATION):
    cw = data["current_weather"]
    temp = cw["temperature"]
    wind = cw["windspeed"]
    wind_dir = get_wind_direction(cw["winddirection"])
    code = cw["weathercode"]
    condition = WMO_CODES.get(code, f"Code {code}")
    is_day = "☀️" if cw["is_day"] else "🌙"

    lines = [
        f"🌡️ **Weather — {location}**",
        f"{condition} {temp:.0f}°F | Wind: {wind:.0f} mph {wind_dir}",
    ]

    # Daily forecast
    daily = data.get("daily", {})
    if daily:
        lines.append("")
        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_probability_max", [])
        codes = daily.get("weathercode", [])

        for i in range(min(3, len(dates))):
            d = dates[i]
            hi = highs[i] if i < len(highs) else "?"
            lo = lows[i] if i < len(lows) else "?"
            p = precip[i] if i < len(precip) else 0
            c = WMO_CODES.get(codes[i], "") if i < len(codes) else ""
            label = "Today" if i == 0 else "Tomorrow" if i == 1 else d
            rain = f" | 🌧️ {p}%" if p and p > 0 else ""
            lines.append(f"  {label}: {c} {hi:.0f}°/{lo:.0f}°F{rain}")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weather forecast")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--location", type=str, default=DEFAULT_LOCATION)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        data = get_weather(args.lat, args.lon)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(format_weather(data, args.location))
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
