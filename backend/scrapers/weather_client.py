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

try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except Exception:
    pass

OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")
CITY_ID: int = 1269843          # OpenWeatherMap city ID for Hyderabad, IN
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
# Precipitation & Road Impact Classification
# ---------------------------------------------------------------------------

def classify_precipitation_and_impact(
    wmo_code: int = 0,
    precip_mm: float = 0.0,
    temp: float = 32.0,
    description: str = "",
) -> dict[str, Any]:
    """
    Scientifically accurate classification of rainfall impact on Hyderabad road traffic.
    
    Rule: Small precipitation (< 2.5 mm drizzle or brief passing showers) DOES NOT cause 
    road waterlogging in Hyderabad. Normal traffic flow continues.
    Waterlogging only occurs during severe convective thunderstorms or intense downpours (> 25 mm).
    """
    desc_lower = description.lower()

    # 1. Severe Thunderstorm / Cloudburst (> 25 mm)
    if wmo_code in [95, 96, 99] or precip_mm >= 25.0 or "thunderstorm" in desc_lower:
        return {
            "weather_code": 4,
            "description": "Severe Thunderstorm & Local Waterlogging at Low-Lying Underpasses",
            "is_rain": True,
            "rain_surge_multiplier": 1.25,
            "precip_mm": round(precip_mm, 1),
        }

    # 2. Heavy Rainfall (> 12 mm)
    if precip_mm >= 12.0 or wmo_code in [65, 81, 82] or "heavy rain" in desc_lower:
        return {
            "weather_code": 1,
            "description": "Heavy Rainfall, Arterial Road Traffic Slowdown",
            "is_rain": True,
            "rain_surge_multiplier": 1.15,
            "precip_mm": round(precip_mm, 1),
        }

    # 3. Moderate Steady Rain (2.5 mm – 12 mm)
    if precip_mm >= 2.5 or wmo_code in [61, 63, 80] or "moderate rain" in desc_lower:
        return {
            "weather_code": 1,
            "description": "Moderate Rain & Wet Roads, Slight Traffic Slowdown",
            "is_rain": True,
            "rain_surge_multiplier": 1.08,
            "precip_mm": round(precip_mm, 1),
        }

    # 4. Light Passing Drizzle / Trace Rain (< 2.5 mm) - NO WATERLOGGING
    if precip_mm > 0.0 or wmo_code in [51, 53, 55] or any(k in desc_lower for k in ["drizzle", "light rain"]):
        return {
            "weather_code": 0,
            "description": "Light Passing Drizzle, Normal Traffic Conditions (No Waterlogging)",
            "is_rain": False,
            "rain_surge_multiplier": 1.0,
            "precip_mm": round(precip_mm, 1),
        }

    # 5. Fog
    if wmo_code in [45, 48] or "fog" in desc_lower:
        return {
            "weather_code": 2,
            "description": "Dense Fog & Reduced Visibility",
            "is_rain": False,
            "rain_surge_multiplier": 1.0,
            "precip_mm": 0.0,
        }

    # 6. Partly Cloudy / Overcast
    if wmo_code in [2, 3] or any(k in desc_lower for k in ["cloud", "overcast"]):
        return {
            "weather_code": 0,
            "description": "Partly Cloudy, Dry Commute",
            "is_rain": False,
            "rain_surge_multiplier": 1.0,
            "precip_mm": 0.0,
        }

    # 7. Clear & Sunny
    return {
        "weather_code": 0,
        "description": "Clear & Sunny, Normal Commute",
        "is_rain": False,
        "rain_surge_multiplier": 1.0,
        "precip_mm": 0.0,
    }


# ---------------------------------------------------------------------------
# WeatherClient
# ---------------------------------------------------------------------------

class WeatherClient:
    """
    Hyderabad meteorological client combining real-time Open-Meteo WMO ground
    truth telemetry with OpenWeatherMap observation.
    """

    def __init__(self, api_key: str = OPENWEATHER_API_KEY) -> None:
        self._api_key = api_key

    def fetch_current(self) -> dict[str, Any]:
        """Fetch real-time current conditions for Hyderabad."""
        # 1. Primary: High-accuracy Open-Meteo WMO live station
        try:
            url = "https://api.open-meteo.com/v1/forecast?latitude=17.3850&longitude=78.4867&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m&timezone=Asia%2FKolkata"
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                c = resp.json().get("current", {})
                temp = float(c.get("temperature_2m", 33.0))
                precip = float(c.get("precipitation", 0.0))
                wmo = int(c.get("weather_code", 0))
                classified = classify_precipitation_and_impact(wmo, precip, temp)
                return {
                    "temperature": round(temp, 1),
                    "weather_code": classified["weather_code"],
                    "description": classified["description"],
                    "humidity": int(c.get("relative_humidity_2m", 35)),
                    "wind_speed": float(c.get("wind_speed_10m", 5.0)),
                    "is_rain": classified["is_rain"],
                    "rain_surge_multiplier": classified["rain_surge_multiplier"],
                    "precipitation_mm": precip,
                    "source": "live_open_meteo",
                }
        except Exception as exc:
            logger.warning("Open-Meteo current fetch failed: %s", exc)

        # 2. Secondary fallback: OpenWeatherMap
        if self._api_key:
            try:
                url = f"{BASE_URL}/weather"
                params = {"q": "Hyderabad,IN", "appid": self._api_key, "units": "metric"}
                resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    return self._parse_current(resp.json())
            except Exception as exc:
                logger.warning("OpenWeather current fallback failed: %s", exc)

        return self._mock_weather()

    def fetch_forecast(self, hours: int = 24) -> list[dict[str, Any]]:
        """
        Fetch an hourly or 3-hourly forecast for Hyderabad.
        Primary: High-accuracy Open-Meteo hourly telemetry.
        Secondary: OpenWeatherMap 3-hourly forecast.
        Fallback: Climatological dry profile (zero fake rain).
        """
        # 1. Primary: High-accuracy Open-Meteo hourly telemetry
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude=17.3850&longitude=78.4867&hourly=temperature_2m,precipitation_probability,precipitation,weather_code&timezone=Asia%2FKolkata&forecast_hours={max(hours, 24)}"
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json().get("hourly", {})
                times = data.get("time", [])
                temps = data.get("temperature_2m", [])
                precips = data.get("precipitation", [])
                codes = data.get("weather_code", [])
                probs = data.get("precipitation_probability", [])

                try:
                    import pytz
                    now_ist = datetime.now(pytz.timezone("Asia/Kolkata"))
                except Exception:
                    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))

                slots: list[dict[str, Any]] = []
                for i in range(len(times)):
                    t_str = times[i]
                    try:
                        t_dt = datetime.fromisoformat(t_str)
                        if t_dt.tzinfo is None:
                            try:
                                import pytz
                                t_dt = pytz.timezone("Asia/Kolkata").localize(t_dt)
                            except Exception:
                                t_dt = t_dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                        offset = round((t_dt - now_ist).total_seconds() / 3600.0, 1)
                    except Exception:
                        offset = float(i)
                    if offset < -1.0:
                        continue
                    if offset > hours:
                        break
                    precip_val = float(precips[i]) if i < len(precips) else 0.0
                    temp_val = float(temps[i]) if i < len(temps) else 30.0
                    wmo_val = int(codes[i]) if i < len(codes) else 0
                    prob_val = float(probs[i]) / 100.0 if i < len(probs) else 0.0

                    classified = classify_precipitation_and_impact(wmo_val, precip_val, temp_val)
                    slots.append({
                        "hour_offset": max(0.0, offset),
                        "hour": t_dt.hour,
                        "weather_code": classified["weather_code"],
                        "temperature": round(temp_val, 1),
                        "description": classified["description"],
                        "rain_probability": round(prob_val, 2),
                    })
                if slots:
                    return slots
        except Exception as exc:
            logger.warning("Open-Meteo hourly forecast failed: %s", exc)

        # 2. Secondary: OpenWeatherMap
        if self._api_key:
            try:
                cnt = hours // 3 + 4   # extra slots for safety
                url = f"{BASE_URL}/forecast"
                params = {"q": "Hyderabad,IN", "appid": self._api_key, "units": "metric", "cnt": cnt}
                resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
                resp.raise_for_status()
                return self._parse_forecast(resp.json(), hours)
            except Exception as exc:  # noqa: BLE001
                logger.warning("fetch_forecast OWM failed (%s); returning mock data.", exc)

        return self._mock_forecast()

    def get_forecast_for_date(self, target_date: Any) -> Optional[dict[str, Any]]:
        """
        Return the summarized weather forecast for a specific date.
        Primary: Open-Meteo 7-day daily forecast (free, live, high-precision).
        Secondary: OpenWeatherMap 5-day forecast.
        Fallback: Climatological dry autumn profile (no fake rain or waterlogging).
        """
        if hasattr(target_date, "strftime"):
            date_str = target_date.strftime("%Y-%m-%d")
        else:
            date_str = str(target_date)

        # 1. Primary: Open-Meteo 7-day daily forecast
        try:
            url = "https://api.open-meteo.com/v1/forecast?latitude=17.3850&longitude=78.4867&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=Asia%2FKolkata"
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                daily = resp.json().get("daily", {})
                times = daily.get("time", [])
                if date_str in times:
                    idx = times.index(date_str)
                    wmo = int(daily.get("weather_code", [0])[idx])
                    precip = float(daily.get("precipitation_sum", [0.0])[idx])
                    t_max = float(daily.get("temperature_2m_max", [32.0])[idx])
                    t_min = float(daily.get("temperature_2m_min", [24.0])[idx])
                    avg_temp = round((t_max + t_min) / 2.0, 1)

                    classified = classify_precipitation_and_impact(wmo, precip, avg_temp)
                    return {
                        "weather_code": classified["weather_code"],
                        "temperature": avg_temp,
                        "description": classified["description"],
                        "source": "live_open_meteo_forecast",
                        "is_rain": classified["is_rain"],
                        "rain_surge_multiplier": classified["rain_surge_multiplier"],
                        "precipitation_mm": precip,
                    }
        except Exception as exc:
            logger.warning("Open-Meteo daily forecast lookup failed: %s", exc)

        # 2. Secondary: OpenWeather 5-day forecast
        if self._api_key:
            try:
                url = f"{BASE_URL}/forecast"
                params = {"q": "Hyderabad,IN", "appid": self._api_key, "units": "metric"}
                resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("list", [])

                    # Match items starting with date_str
                    matching = [it for it in items if it.get("dt_txt", "").startswith(date_str)]
                    if matching:
                        temps = [it.get("main", {}).get("temp", 30.0) for it in matching]
                        avg_temp = round(sum(temps) / len(temps), 1)

                        # Check for rain / storms
                        rain_item = next((it for it in matching if any(w.get("main", "").lower() in ["rain", "thunderstorm", "drizzle"] for w in it.get("weather", []))), None)
                        if rain_item:
                            w_info = rain_item.get("weather", [{}])[0]
                            desc = w_info.get("description", "Showers").capitalize()
                            code = self._map_condition_to_code(w_info.get("main", "Rain"))
                            rain_mm = float(rain_item.get("rain", {}).get("3h", 0.0))
                            classified = classify_precipitation_and_impact(code, rain_mm, avg_temp, desc)
                            return {
                                "weather_code": classified["weather_code"],
                                "temperature": avg_temp,
                                "description": classified["description"],
                                "source": "live_openweather_forecast",
                                "is_rain": classified["is_rain"],
                                "rain_surge_multiplier": classified["rain_surge_multiplier"],
                                "precipitation_mm": rain_mm,
                            }
                        else:
                            mid = matching[len(matching) // 2]
                            w_info = mid.get("weather", [{}])[0]
                            desc = w_info.get("description", "Clear sky").capitalize()
                            code = self._map_condition_to_code(w_info.get("main", "Clear"))
                            return {
                                "weather_code": code,
                                "temperature": avg_temp,
                                "description": desc,
                                "source": "live_openweather_forecast",
                                "is_rain": False,
                                "rain_surge_multiplier": 1.0,
                                "precipitation_mm": 0.0,
                            }
            except Exception as exc:
                logger.warning("OpenWeather get_forecast_for_date failed: %s", exc)

        # 3. Beyond 7-day forecast window or offline: return standard Hyderabad autumn climate
        return {
            "weather_code": 0,
            "temperature": 32.5,
            "description": "Clear & Sunny, Normal Commute",
            "source": "climatology_autumn",
            "is_rain": False,
            "rain_surge_multiplier": 1.0,
            "precipitation_mm": 0.0,
        }

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
            "temperature": 32.5,
            "weather_code": 0,
            "description": "Clear & Sunny, Normal Commute",
            "humidity": 45,
            "wind_speed": 4.5,
            "raw_condition": "Clear",
            "is_rain": False,
            "rain_surge_multiplier": 1.0,
            "precipitation_mm": 0.0,
        }

    @staticmethod
    def _mock_forecast() -> list[dict[str, Any]]:
        """8 realistic forecast slots spanning the next 24 hours."""
        now = datetime.now(tz=timezone.utc)
        slots = []
        conditions = [
            (0, "Partly cloudy",     30.5, 0.05),
            (0, "Clear sky",         32.0, 0.02),
            (0, "Sunny",             33.5, 0.00),
            (0, "Partly cloudy",     31.0, 0.05),
            (0, "Clear sky",         29.0, 0.00),
            (0, "Clear sky",         27.5, 0.00),
            (0, "Sunny",             28.5, 0.00),
            (0, "Few clouds",        31.5, 0.05),
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
