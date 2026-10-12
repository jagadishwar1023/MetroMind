"""
scrapers/weather_client.py
--------------------------
OpenWeatherMap API client for the HMR (Hyderabad Metro Rail) demand
optimization system.

Provides current weather and 24-hour forecast data mapped to the internal
weather-code schema used by the multiplier tables:

    0 = clear / sunny
    1 = rain / drizzle
    2 = fog
    3 = haze / mist
    4 = thunderstorm / severe

All network errors are caught and fall back to mock data so the pipeline
never crashes when the API key is absent or the network is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")
CITY_ID: int = 1265782          # OpenWeatherMap city ID for Hyderabad, IN
BASE_URL: str = "https://api.openweathermap.org/data/2.5"
HTTP_TIMEOUT: int = 10          # seconds

# ---------------------------------------------------------------------------
# Condition → internal weather-code mapping
# ---------------------------------------------------------------------------
_CONDITION_CODE_MAP: dict[str, int] = {
    "thunderstorm": 4,
    "squall": 4,
    "tornado": 4,
    "drizzle": 1,
    "rain": 1,
    "snow": 1,           # unlikely in Hyderabad but handled for completeness
    "sleet": 1,
    "fog": 2,
    "sand": 3,
    "dust": 3,
    "ash": 3,
    "haze": 3,
    "mist": 3,
    "smoke": 3,
    "clouds": 0,
    "clear": 0,
}


# ---------------------------------------------------------------------------
# WeatherClient
# ---------------------------------------------------------------------------

class WeatherClient:
    """
    Thin wrapper around the OpenWeatherMap ``/weather`` and ``/forecast``
    endpoints for Hyderabad.

    Instantiate once via ``get_weather_client()`` (module-level singleton)
    rather than creating instances directly.
    """

    def __init__(self, api_key: str = OPENWEATHER_API_KEY) -> None:
        self._api_key = api_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_current(self) -> dict[str, Any]:
        """
        Fetch current weather conditions for Hyderabad.

        Returns
        -------
        dict with keys:
            temperature (float), weather_code (int 0-4), description (str),
            humidity (int), wind_speed (float), raw_condition (str)
        """
        if not self._api_key:
            logger.debug("No API key; returning mock current weather.")
            return self._mock_weather()

        try:
            url = f"{BASE_URL}/weather"
            params = {"id": CITY_ID, "appid": self._api_key, "units": "metric"}
            resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            return self._parse_current(resp.json())
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch_current failed (%s); returning mock data.", exc)
            return self._mock_weather()

    def fetch_forecast(self, hours: int = 24) -> list[dict[str, Any]]:
        """
        Fetch a 3-hourly forecast for Hyderabad.

        Parameters
        ----------
        hours : int
            How many hours ahead to fetch (rounded up to the nearest 3-hour slot).

        Returns
        -------
        list of dicts, each with keys:
            hour_offset (int), hour (int 0-23), weather_code (int 0-4),
            temperature (float), description (str), rain_probability (float 0-1)
        """
        if not self._api_key:
            logger.debug("No API key; returning mock forecast.")
            return self._mock_forecast()

        try:
            cnt = hours // 3 + 4   # extra slots for safety
            url = f"{BASE_URL}/forecast"
            params = {"id": CITY_ID, "appid": self._api_key, "units": "metric", "cnt": cnt}
            resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            return self._parse_forecast(resp.json(), hours)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch_forecast failed (%s); returning mock data.", exc)
            return self._mock_forecast()

    def get_weather_for_hour(
        self,
        target_hour: int,
        target_date: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Return the forecast slot closest to ``target_hour`` on ``target_date``.

        Parameters
        ----------
        target_hour : int
            Hour of day (0-23) in local IST time.
        target_date : datetime or None
            Date to match.  Defaults to today in UTC (approx IST).

        Returns
        -------
        dict — same schema as ``fetch_forecast`` list elements.
        """
        forecast = self.fetch_forecast(hours=48)
        if not forecast:
            return self._mock_forecast()[0]

        if target_date is None:
            target_date = datetime.now(tz=timezone.utc)

        best: dict[str, Any] | None = None
        best_diff = float("inf")

        for slot in forecast:
            slot_hour = slot.get("hour", 0)
            slot_offset = slot.get("hour_offset", 0)
            slot_dt = datetime.now(tz=timezone.utc) + timedelta(hours=slot_offset)

            # Filter to the right calendar date (UTC date approximation)
            if slot_dt.date() != target_date.date():
                continue

            diff = abs(slot_hour - target_hour)
            if diff < best_diff:
                best_diff = diff
                best = slot

        return best or forecast[0]

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_current(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract and normalise fields from OWM /weather response."""
        main = data.get("main", {})
        weather_list = data.get("weather", [{}])
        weather_item = weather_list[0] if weather_list else {}

        raw_condition = weather_item.get("main", "Clear")
        code = self._map_condition_to_code(raw_condition)

        return {
            "temperature": float(main.get("temp", 28.5)),
            "weather_code": code,
            "description": weather_item.get("description", "").capitalize(),
            "humidity": int(main.get("humidity", 60)),
            "wind_speed": float(data.get("wind", {}).get("speed", 0.0)),
            "raw_condition": raw_condition,
        }

    def _parse_forecast(self, data: dict[str, Any], hours: int) -> list[dict[str, Any]]:
        """Extract and normalise fields from OWM /forecast response."""
        items = data.get("list", [])
        now = datetime.now(tz=timezone.utc)
        slots: list[dict[str, Any]] = []

        for item in items:
            dt_unix = item.get("dt", 0)
            slot_dt = datetime.fromtimestamp(dt_unix, tz=timezone.utc)
            hour_offset = (slot_dt - now).total_seconds() / 3600
            if hour_offset > hours + 3:
                break

            weather_list = item.get("weather", [{}])
            weather_item = weather_list[0] if weather_list else {}
            raw_condition = weather_item.get("main", "Clear")
            code = self._map_condition_to_code(raw_condition)

            main = item.get("main", {})
            pop = float(item.get("pop", 0.0))       # probability of precipitation

            slots.append({
                "hour_offset": round(hour_offset, 1),
                "hour": slot_dt.hour,
                "weather_code": code,
                "temperature": float(main.get("temp", 28.0)),
                "description": weather_item.get("description", "").capitalize(),
                "rain_probability": round(pop, 2),
            })

        return slots if slots else self._mock_forecast()

    # ------------------------------------------------------------------
    # Condition mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_condition_to_code(condition_str: str) -> int:
        """
        Map an OWM ``weather.main`` string to the internal weather code.

        ============  =====================  =====
        Code          Meaning                OWM conditions
        ============  =====================  =====
        0             Clear / cloudy         Clear, Clouds
        1             Rain / drizzle         Rain, Drizzle, Snow
        2             Fog                    Fog
        3             Haze / mist / dust     Haze, Mist, Smoke, Sand, Dust, Ash
        4             Storm / severe         Thunderstorm, Squall, Tornado
        ============  =====================  =====
        """
        lower = condition_str.lower().strip()
        for keyword, code in _CONDITION_CODE_MAP.items():
            if keyword in lower:
                return code
        return 0    # default: clear

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_weather() -> dict[str, Any]:
        """Realistic fallback current-weather dict for Hyderabad."""
        return {
            "temperature": 28.5,
            "weather_code": 0,
            "description": "Partly cloudy",
            "humidity": 65,
            "wind_speed": 3.2,
            "raw_condition": "Clouds",
        }

    @staticmethod
    def _mock_forecast() -> list[dict[str, Any]]:
        """8 realistic forecast slots spanning the next 24 hours."""
        now = datetime.now(tz=timezone.utc)
        slots = []
        conditions = [
            (0, "Partly cloudy",     28.5, 0.05),
            (0, "Clear sky",         29.0, 0.02),
            (1, "Light rain",        26.5, 0.75),
            (1, "Moderate rain",     25.0, 0.85),
            (0, "Scattered clouds", 27.0, 0.20),
            (3, "Haze",             30.0, 0.10),
            (0, "Clear sky",         31.5, 0.02),
            (0, "Few clouds",        29.5, 0.05),
        ]
        for i, (code, desc, temp, pop) in enumerate(conditions):
            offset_hours = i * 3
            slot_dt = now + timedelta(hours=offset_hours)
            slots.append({
                "hour_offset": float(offset_hours),
                "hour": slot_dt.hour,
                "weather_code": code,
                "temperature": temp,
                "description": desc,
                "rain_probability": pop,
            })
        return slots


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client_instance: WeatherClient | None = None


def get_weather_client() -> WeatherClient:
    """
    Return the module-level ``WeatherClient`` singleton.

    Creates a new instance on first call using ``OPENWEATHER_API_KEY``
    from the environment.
    """
    global _client_instance  # noqa: PLW0603
    if _client_instance is None:
        _client_instance = WeatherClient(api_key=OPENWEATHER_API_KEY)
    return _client_instance


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def get_live_weather_code_and_temp(target_hour: int | None = None) -> tuple[int, float]:
    """
    Return ``(weather_code, temperature)`` for a given hour of the day.

    Parameters
    ----------
    target_hour : int or None
        Hour of day (0-23).  If ``None``, returns current conditions.

    Returns
    -------
    tuple[int, float]
        ``(weather_code, temperature_celsius)``

    Notes
    -----
    Falls back to mock data when the API key is not configured or a network
    error occurs.
    """
    client = get_weather_client()

    if target_hour is None:
        current = client.fetch_current()
        return current["weather_code"], current["temperature"]

    slot = client.get_weather_for_hour(target_hour=target_hour)
    return slot["weather_code"], slot["temperature"]


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    client = get_weather_client()

    print("\n=== Current Weather (Hyderabad) ===")
    current = client.fetch_current()
    for k, v in current.items():
        print(f"  {k:20s}: {v}")

    print("\n=== 24-Hour Forecast ===")
    forecast = client.fetch_forecast(hours=24)
    for slot in forecast:
        bar = "🌧️" if slot["weather_code"] == 1 else ("⛈️" if slot["weather_code"] == 4 else "☀️")
        print(
            f"  +{slot['hour_offset']:4.1f}h  "
            f"hour={slot['hour']:02d}  "
            f"code={slot['weather_code']}  "
            f"temp={slot['temperature']:5.1f}°C  "
            f"rain_prob={slot['rain_probability']:.0%}  "
            f"{bar} {slot['description']}"
        )

    print("\n=== Convenience function ===")
    for h in [6, 9, 12, 18, 21]:
        code, temp = get_live_weather_code_and_temp(target_hour=h)
        print(f"  Hour {h:02d}:00  weather_code={code}  temp={temp:.1f}°C")
