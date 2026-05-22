"""
Weather service for Lightworks Pro.

Uses Open-Meteo (open-meteo.com) — free, no API key required.
Location is auto-detected from IP on first use via ip-api.com (also free),
then cached in the app config so subsequent calls are instant.

All network calls are synchronous — run from a thread-pool executor.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

_IP_API_URL     = "http://ip-api.com/json/?fields=lat,lon,city,country"
_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CODES: dict[int, str] = {
    0:  "clear sky",
    1:  "mainly clear",   2: "partly cloudy",  3: "overcast",
    45: "foggy",          48: "icy fog",
    51: "light drizzle",  53: "drizzle",        55: "heavy drizzle",
    61: "light rain",     63: "rain",           65: "heavy rain",
    71: "light snow",     73: "snow",           75: "heavy snow",
    77: "snow grains",
    80: "light showers",  81: "showers",        82: "violent showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorm",   96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}


def _wmo_description(code: int) -> str:
    return _WMO_CODES.get(code, f"weather code {code}")


def _detect_location() -> dict | None:
    """Return {'lat', 'lon', 'city'} from ip-api.com, or None on failure."""
    try:
        resp = requests.get(_IP_API_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if "lat" in data and "lon" in data:
            return {"lat": data["lat"], "lon": data["lon"], "city": data.get("city", "")}
    except Exception as e:
        log.warning("Location detection failed: %s", e)
    return None


def _celsius_to_fahrenheit(c: float) -> int:
    return round(c * 9 / 5 + 32)


class WeatherService:
    """
    Fetches current weather conditions and a daily high/low.
    Location is resolved once and cached; pass `config` dict to persist it.
    """

    def __init__(self, config: dict) -> None:
        self._config = config

    def get_weather_spoken(self) -> str:
        """Return a one-sentence spoken weather summary. Safe to call from executor."""
        lat, lon, city = self._resolve_location()
        if lat is None:
            return "Could not determine your location for weather. Please check your internet connection."

        try:
            resp = requests.get(
                _OPEN_METEO_URL,
                params={
                    "latitude":         lat,
                    "longitude":        lon,
                    "current":          "temperature_2m,weathercode,windspeed_10m",
                    "daily":            "temperature_2m_max,temperature_2m_min,weathercode",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit":  "mph",
                    "forecast_days":    1,
                    "timezone":         "auto",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("Weather fetch failed: %s", e)
            return "Could not fetch weather data. Please check your internet connection."

        current = data.get("current", {})
        daily   = data.get("daily", {})

        temp    = round(current.get("temperature_2m", 0))
        code    = current.get("weathercode", 0)
        wind    = round(current.get("windspeed_10m", 0))
        hi      = round((daily.get("temperature_2m_max") or [temp])[0])
        lo      = round((daily.get("temperature_2m_min") or [temp])[0])
        desc    = _wmo_description(code)

        location_label = f"in {city}" if city else ""
        wind_part = f" Wind at {wind} miles per hour." if wind > 5 else ""
        return (
            f"Currently {temp} degrees {location_label}, {desc}. "
            f"Today's high is {hi}, low is {lo}.{wind_part}"
        )

    def _resolve_location(self) -> tuple[Optional[float], Optional[float], str]:
        """Return (lat, lon, city) from config cache or live IP lookup."""
        lat  = self._config.get("weather_lat")
        lon  = self._config.get("weather_lon")
        city = self._config.get("weather_city", "")

        if lat is not None and lon is not None:
            return lat, lon, city

        loc = _detect_location()
        if loc:
            self._config["weather_lat"]  = loc["lat"]
            self._config["weather_lon"]  = loc["lon"]
            self._config["weather_city"] = loc.get("city", "")
            _save_config(self._config)
            return loc["lat"], loc["lon"], loc.get("city", "")

        return None, None, ""


def _save_config(config: dict) -> None:
    """Persist config dict to the standard config path."""
    import json
    import os
    path = os.path.join(os.environ.get("APPDATA", ""), "LightworksPro", "config.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        log.warning("Could not save config: %s", e)
