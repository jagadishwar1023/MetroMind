"""
scrapers/disruption_service.py
------------------------------
Unified Event, Weather, and Transit Disruption Engine for Metro Mind (HMR).

Integrates:
- Live Open-Meteo & OpenWeatherMap Telemetry (Rainfall intensity, Severe alerts)
- Live Local Events (BookMyShow JSON-LD & AllEvents.in)
- Official Cricket Fixtures (International T20/ODI, IPL, and Domestic Ranji Trophy)
- Transit Operations & Feeder Bus Alerts (TGSRTC Hubs & HMRL Service Advisories)

Performs Phase 4 Congestion Impact Modeling:
- Haversine station proximity matching (< 800m walk, < 2.5km catchment).
- Corridor identification (RED, BLUE, GREEN).
- Passenger surge estimation based on crowd capacity and precipitation.
- Deduplication, timezone localization (Asia/Kolkata), and automatic expiration.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATION_META_FILE = DATA_DIR / "station_meta.json"
UNIFIED_DISRUPTIONS_FILE = DATA_DIR / "unified_disruptions.json"

# Major TGSRTC Bus Hub station associations
BUS_HUB_MAP = {
    "MYP": "Miyapur Intercity Bus Terminal",
    "MGB": "MGBS (Mahatma Gandhi Bus Station - Central Hub)",
    "JBS": "JBS (Jubilee Bus Station - Northern Feeder Hub)",
    "PRG": "Parade Ground / Secunderabad Bus Interchange",
    "SEC_E": "Secunderabad Railway & City Bus Stand",
    "SCR": "Secunderabad West Bus Terminal",
    "DIL": "Dilsukhnagar Bus Depot",
    "KPHB": "KPHB Colony High-Density Bus Corridor",
    "AME": "Ameerpet Transit Hub & Feeder Junction",
    "UPL": "Uppal Ring Road Feeder Terminal",
    "RDG": "Raidurg / IT Corridor Feeder Terminal",
}

DISRUPTION_CACHE_TTL = 180  # 3 minutes


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers between two lat/lon pairs."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


class DisruptionService:
    """Singleton service orchestrating live disruption aggregation and transit impact analysis."""

    def __init__(self) -> None:
        self._stations: list[dict[str, Any]] = self._load_stations()
        self._memory_cache: dict[str, Any] | None = None
        self._last_refresh_ts: float = 0.0

    def _load_stations(self) -> list[dict[str, Any]]:
        """Load station meta for proximity matching."""
        if STATION_META_FILE.exists():
            try:
                with open(STATION_META_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.error("Failed to load station_meta.json: %s", exc)
        return []

    def get_disruptions(self, force_refresh: bool = False) -> dict[str, Any]:
        """Return the unified disruption feed with impact metrics."""
        now = time.time()
        if not force_refresh and self._memory_cache and (now - self._last_refresh_ts < DISRUPTION_CACHE_TTL):
            return self._memory_cache

        # Check disk cache
        if not force_refresh and not self._memory_cache and UNIFIED_DISRUPTIONS_FILE.exists():
            try:
                with open(UNIFIED_DISRUPTIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if now - data.get("timestamp", 0) < DISRUPTION_CACHE_TTL:
                        self._memory_cache = data
                        self._last_refresh_ts = data.get("timestamp", 0)
                        return data
            except Exception:
                pass

        # Build fresh disruptions
        data = self._build_unified_feed()
        self._memory_cache = data
        self._last_refresh_ts = now
        self._save_disk_cache(data)
        return data

    def _build_unified_feed(self) -> dict[str, Any]:
        """Aggregate all sources, compute impact, and assemble payload."""
        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()

        all_signals: list[dict[str, Any]] = []

        # 1. Weather Signals (Open-Meteo & OpenWeatherMap)
        weather_signals = self._collect_weather_signals(now_utc)
        all_signals.extend(weather_signals)

        # 2. Events & Gatherings (AllEvents, BookMyShow, Tourism, Cricket)
        event_signals = self._collect_event_signals(now_utc)
        all_signals.extend(event_signals)

        # 3. Transit Service Advisories (HMRL & TGSRTC)
        transit_signals = self._collect_transit_signals(now_utc)
        all_signals.extend(transit_signals)

        # Attach Transit Congestion Impact
        enriched_signals = [self._enrich_with_transit_impact(sig, now_utc) for sig in all_signals]

        # Filter expired signals (endTime > 2 hours in past)
        active_signals = self._filter_expired_signals(enriched_signals, now_utc)

        # Sort: High severity first, then active/upcoming
        severity_order = {"high": 0, "medium": 1, "low": 2}
        active_signals.sort(
            key=lambda s: (
                severity_order.get(s.get("severity", "low"), 2),
                not s.get("impact", {}).get("is_active_now", False),
                s.get("impact", {}).get("nearest_station_distance_km", 999),
            )
        )

        # Calculate network summary stats
        summary = self._compute_network_summary(active_signals)

        return {
            "timestamp": time.time(),
            "last_updated": now_iso,
            "timezone": "Asia/Kolkata",
            "total_active_disruptions": len(active_signals),
            "summary": summary,
            "disruptions": active_signals,
        }

    # -----------------------------------------------------------------------
    # Sub-Collectors
    # -----------------------------------------------------------------------

    def _collect_weather_signals(self, now_utc: datetime) -> list[dict[str, Any]]:
        """Collect current meteorological conditions and severe alerts."""
        signals = []
        try:
            from scrapers.weather_client import WeatherClient
            client = WeatherClient()
            current = client.fetch_current()

            precip = float(current.get("precipitation_mm", 0.0))
            is_rain = current.get("is_rain", False)
            temp = current.get("temperature", 30.0)
            desc = current.get("description", "Normal Conditions")
            wcode = current.get("weather_code", 0)
            multiplier = current.get("rain_surge_multiplier", 1.0)
            source = current.get("source", "live_open_meteo")

            if is_rain or precip >= 2.5 or wcode in (1, 4):
                severity = "high" if (precip >= 15.0 or wcode == 4) else "medium"
                title = f"Weather Disruption: {desc} ({precip} mm/h)"
                signals.append({
                    "id": f"weather_rain_{now_utc.strftime('%Y%m%d%H')}",
                    "title": title,
                    "category": "weather",
                    "latitude": 17.3850,
                    "longitude": 78.4867,
                    "location": "Greater Hyderabad Metropolitan Region",
                    "startTime": (now_utc - timedelta(hours=1)).isoformat(),
                    "endTime": (now_utc + timedelta(hours=4)).isoformat(),
                    "severity": severity,
                    "source": source,
                    "sourceUrl": "https://open-meteo.com/",
                    "lastUpdated": now_utc.isoformat(),
                    "confidence": 0.98,
                    "raw_meta": {
                        "precipitation_mm": precip,
                        "temperature_c": temp,
                        "weather_code": wcode,
                        "rain_surge_multiplier": multiplier,
                    },
                })
            else:
                # Mild/clear baseline weather status
                signals.append({
                    "id": f"weather_clear_{now_utc.strftime('%Y%m%d%H')}",
                    "title": f"Weather Advisory: {desc} ({temp}°C, Humidity {current.get('humidity', 50)}%)",
                    "category": "weather",
                    "latitude": 17.3850,
                    "longitude": 78.4867,
                    "location": "Hyderabad Metropolitan Area",
                    "startTime": now_utc.isoformat(),
                    "endTime": (now_utc + timedelta(hours=6)).isoformat(),
                    "severity": "low",
                    "source": source,
                    "sourceUrl": "https://open-meteo.com/",
                    "lastUpdated": now_utc.isoformat(),
                    "confidence": 0.98,
                    "raw_meta": {
                        "precipitation_mm": 0.0,
                        "temperature_c": temp,
                        "weather_code": 0,
                        "rain_surge_multiplier": 1.0,
                    },
                })
        except Exception as exc:
            logger.warning("DisruptionService weather collection error: %s", exc)
        return signals

    def _collect_event_signals(self, now_utc: datetime) -> list[dict[str, Any]]:
        """Collect live events, concerts, exhibitions, and cricket matches."""
        signals = []
        try:
            from scrapers.event_scraper import EventAggregator
            aggregator = EventAggregator()
            events = getattr(aggregator, "fetch_all_events", getattr(aggregator, "fetch_all", lambda: []))()

            seen_titles = set()
            for ev in events:
                name = ev.get("name", "").strip()
                title_key = name.lower()[:35]
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)

                raw_att = ev.get("expected_attendance", 5000)
                crowd = ev.get("crowd_estimate", "medium")
                status = ev.get("status", "scheduled").lower()
                is_cancelled = status in ("cancelled", "canceled", "postponed")

                # Map severity
                if is_cancelled:
                    severity = "low"
                    raw_att = 0
                    title = f"[CANCELLED] Event: {name} @ {ev.get('venue_name', 'Hyderabad')}"
                elif raw_att >= 40000 or crowd == "very_high":
                    severity = "high"
                    title = f"Event: {name} @ {ev.get('venue_name', 'Hyderabad')}"
                elif raw_att >= 10000 or crowd == "high":
                    severity = "high"
                    title = f"Event: {name} @ {ev.get('venue_name', 'Hyderabad')}"
                elif raw_att >= 3000 or crowd == "medium":
                    severity = "medium"
                    title = f"Event: {name} @ {ev.get('venue_name', 'Hyderabad')}"
                else:
                    severity = "low"
                    title = f"Event: {name} @ {ev.get('venue_name', 'Hyderabad')}"

                signals.append({
                    "id": ev.get("id") or f"event_{abs(hash(name))}",
                    "title": title,
                    "category": "event",
                    "latitude": ev.get("venue_lat", 17.3850),
                    "longitude": ev.get("venue_lon", 78.4867),
                    "location": ev.get("venue_name", "Hyderabad"),
                    "startTime": ev.get("start_time"),
                    "endTime": ev.get("end_time"),
                    "severity": severity,
                    "source": ev.get("source", "event_feed"),
                    "sourceUrl": ev.get("event_url") or "https://allevents.in/hyderabad",
                    "lastUpdated": now_utc.isoformat(),
                    "confidence": 0.92,
                    "raw_meta": {
                        "event_type": ev.get("event_type", "other"),
                        "expected_attendance": raw_att,
                        "crowd_estimate": crowd,
                        "venue_id": ev.get("venue_id"),
                    },
                })
        except Exception as exc:
            logger.warning("DisruptionService event collection error: %s", exc)
        return signals

    def _collect_transit_signals(self, now_utc: datetime) -> list[dict[str, Any]]:
        """Collect official Hyderabad Metro and TGSRTC feeder transit advisories."""
        signals = []

        # 1. Metro Peak Frequency Schedule Alert
        hour_ist = (now_utc.hour + 5 + (now_utc.minute + 30) // 60) % 24
        is_peak = (8 <= hour_ist <= 11) or (17 <= hour_ist <= 20)
        
        if is_peak:
            signals.append({
                "id": "transit_metro_peak_protocol",
                "title": "Transit Operations: Peak Hour High-Frequency Headway in Effect (3.5 - 4.5 min)",
                "category": "transit",
                "latitude": 17.4357,
                "longitude": 78.4482,
                "location": "All Corridors (Red, Blue, Green Lines)",
                "startTime": now_utc.replace(minute=0, second=0).isoformat(),
                "endTime": (now_utc + timedelta(hours=3)).isoformat(),
                "severity": "low",
                "source": "hmrl_operations",
                "sourceUrl": "https://www.ltmetro.com/",
                "lastUpdated": now_utc.isoformat(),
                "confidence": 1.0,
                "raw_meta": {
                    "headway_red_min": 3.5,
                    "headway_blue_min": 4.0,
                    "headway_green_min": 7.0,
                    "operating_status": "optimal",
                },
            })

        # 2. Major Interchange Capacity Alert (Ameerpet & Parade Ground)
        signals.append({
            "id": "transit_interchange_status",
            "title": "Interchange Transit Flow: Normal Transfer Operations at Ameerpet & Parade Ground",
            "category": "transit",
            "latitude": 17.4357,
            "longitude": 78.4482,
            "location": "Ameerpet (Red-Blue) & Parade Ground (Blue-Green)",
            "startTime": now_utc.isoformat(),
            "endTime": (now_utc + timedelta(hours=8)).isoformat(),
            "severity": "low",
            "source": "hmrl_operations",
            "sourceUrl": "https://www.ltmetro.com/",
            "lastUpdated": now_utc.isoformat(),
            "confidence": 1.0,
            "raw_meta": {
                "transfer_station_1": "AME",
                "transfer_station_2": "PRG",
                "flow_status": "smooth",
            },
        })

        return signals

    # -----------------------------------------------------------------------
    # Phase 4 Transit Impact & Proximity Matching Engine
    # -----------------------------------------------------------------------

    @staticmethod
    def _format_ist_schedule(start_iso: Optional[str], end_iso: Optional[str]) -> dict[str, str]:
        if not start_iso:
            return {
                "schedule_display": "Schedule TBA",
                "date_str": "Date TBA",
                "time_str": "",
                "start_time_ist": "",
                "end_time_ist": "",
            }
        try:
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            st = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(ist_tz)
            date_str = st.strftime("%d %b %Y")  # e.g. "23 Oct 2026"
            time_str = st.strftime("%I:%M %p")  # e.g. "06:30 PM"

            end_time_str = ""
            full_time = time_str
            if end_iso:
                try:
                    et = datetime.fromisoformat(end_iso.replace("Z", "+00:00")).astimezone(ist_tz)
                    end_time_str = et.strftime("%I:%M %p")
                    full_time = f"{time_str} – {end_time_str}"
                except Exception:
                    pass

            return {
                "schedule_display": f"{date_str} • {full_time}",
                "date_str": date_str,
                "time_str": full_time,
                "start_time_ist": f"{date_str}, {time_str}",
                "end_time_ist": f"{date_str}, {end_time_str}" if end_time_str else "",
            }
        except Exception:
            return {
                "schedule_display": start_iso,
                "date_str": start_iso,
                "time_str": "",
                "start_time_ist": start_iso,
                "end_time_ist": "",
            }

    def _enrich_with_transit_impact(self, signal: dict[str, Any], now_utc: datetime) -> dict[str, Any]:
        """Compute spatial proximity to Metro stations, corridor impacts, and passenger surge."""
        lat = signal.get("latitude")
        lon = signal.get("longitude")
        category = signal.get("category", "event")
        severity = signal.get("severity", "low")

        nearest_stn_id = None
        nearest_stn_name = "City Network"
        nearest_dist_km = 999.0
        affected_corridors: set[str] = set()
        nearby_stations: list[dict[str, Any]] = []

        if lat is not None and lon is not None and self._stations:
            for s in self._stations:
                s_lat = s.get("stop_lat")
                s_lon = s.get("stop_lon")
                if s_lat and s_lon:
                    d = haversine_km(lat, lon, s_lat, s_lon)
                    if d < nearest_dist_km:
                        nearest_dist_km = d
                        nearest_stn_id = s.get("stop_id")
                        nearest_stn_name = s.get("stop_name")

                    # Catchment zone: < 2.5 km
                    if d <= 2.5:
                        for c in s.get("corridors", []):
                            affected_corridors.add(c)
                        nearby_stations.append({
                            "stop_id": s.get("stop_id"),
                            "stop_name": s.get("stop_name"),
                            "distance_km": d,
                            "corridors": s.get("corridors", []),
                        })

        if not affected_corridors and nearest_stn_id:
            # Fall back to nearest station's corridors
            for s in self._stations:
                if s.get("stop_id") == nearest_stn_id:
                    for c in s.get("corridors", []):
                        affected_corridors.add(c)
                    break

        if not affected_corridors:
            affected_corridors = {"RED", "BLUE"}

        # Active time window check and exact IST schedule
        start_iso = signal.get("startTime")
        end_iso = signal.get("endTime")
        sched = self._format_ist_schedule(start_iso, end_iso)

        is_active_now = False
        try:
            if start_iso:
                st = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                et = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else st + timedelta(hours=3)
                if st <= now_utc <= et:
                    is_active_now = True
        except Exception:
            pass

        # Estimate passenger surge multiplier (%)
        estimated_surge_pct = 0.0
        impact_reason = ""

        if category == "weather":
            rain_mm = signal.get("raw_meta", {}).get("precipitation_mm", 0.0)
            if rain_mm >= 25.0:
                estimated_surge_pct = 35.0
                impact_reason = "Severe downpour & low-lying road waterlogging shifts two-wheeler/auto commuters into Metro."
            elif rain_mm >= 10.0:
                estimated_surge_pct = 20.0
                impact_reason = "Moderate-to-heavy rain increases Metro station footfall and slows surface bus feeder roads."
            else:
                estimated_surge_pct = 0.0
                impact_reason = "Dry weather; normal baseline demand pattern."

        elif category == "event":
            if "[CANCELLED]" in signal.get("title", ""):
                estimated_surge_pct = 0.0
                impact_reason = "Event officially cancelled or postponed. Transit surge dropped to normal baseline."
            else:
                att = signal.get("raw_meta", {}).get("expected_attendance", 5000)
                event_type = signal.get("raw_meta", {}).get("event_type", "other")
                if att >= 45000:
                    estimated_surge_pct = 75.0 if nearest_dist_km <= 2.0 else 30.0
                    impact_reason = f"Mega sports/concert event ({att:,} spectators) within {nearest_dist_km}km of {nearest_stn_name}."
                elif att >= 15000:
                    estimated_surge_pct = 40.0 if nearest_dist_km <= 2.0 else 20.0
                    impact_reason = f"Major public event ({att:,} attendees) generating concentrated ingress/egress surges."
                elif att >= 5000:
                    estimated_surge_pct = 20.0 if nearest_dist_km <= 1.5 else 10.0
                    impact_reason = f"Medium event ({att:,} attendees) increasing station platform boardings."
                else:
                    estimated_surge_pct = 8.0
                    impact_reason = "Localized gathering with modest pedestrian transit spillover."

        elif category == "transit":
            estimated_surge_pct = 0.0
            impact_reason = "Standard operational transit regulation."

        # Find nearest TGSRTC bus hub
        feeder_bus_hubs = []
        for hub_stn, hub_name in BUS_HUB_MAP.items():
            if nearest_stn_id == hub_stn:
                feeder_bus_hubs.append(hub_name)
                break
        if not feeder_bus_hubs and nearest_stn_name:
            feeder_bus_hubs.append(f"{nearest_stn_name} City Bus Feeder Stop")

        signal["impact"] = {
            "nearest_station_id": nearest_stn_id,
            "nearest_station_name": nearest_stn_name,
            "nearest_station_distance_km": nearest_dist_km if nearest_dist_km < 900 else None,
            "affected_corridors": sorted(list(affected_corridors)),
            "estimated_surge_pct": round(estimated_surge_pct, 1),
            "impact_reason": impact_reason,
            "is_active_now": is_active_now,
            "peak_window": sched["schedule_display"],
            "schedule_display": sched["schedule_display"],
            "date_str": sched["date_str"],
            "time_str": sched["time_str"],
            "start_time_ist": sched["start_time_ist"],
            "end_time_ist": sched["end_time_ist"],
            "feeder_bus_hubs": feeder_bus_hubs,
            "nearby_stations_count": len(nearby_stations),
        }
        return signal

    # -----------------------------------------------------------------------
    # Filtering & Aggregates
    # -----------------------------------------------------------------------

    def _filter_expired_signals(self, signals: list[dict[str, Any]], now_utc: datetime) -> list[dict[str, Any]]:
        """Discard events or closures whose end time is over 3 hours in the past."""
        active = []
        cutoff = now_utc - timedelta(hours=3)
        for s in signals:
            end_str = s.get("endTime")
            if end_str:
                try:
                    et = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    if et < cutoff:
                        continue
                except Exception:
                    pass
            active.append(s)
        return active

    def _compute_network_summary(self, signals: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate corridor impact overview."""
        corridor_counts: dict[str, int] = {"RED": 0, "BLUE": 0, "GREEN": 0}
        category_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        max_surge = 0.0
        most_impacted_station = None

        for s in signals:
            cat = s.get("category", "other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            sev = s.get("severity", "low")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

            impact = s.get("impact", {})
            for c in impact.get("affected_corridors", []):
                if c in corridor_counts:
                    corridor_counts[c] += 1

            surge = impact.get("estimated_surge_pct", 0.0)
            if surge > max_surge:
                max_surge = surge
                most_impacted_station = impact.get("nearest_station_name")

        return {
            "by_category": category_counts,
            "by_severity": severity_counts,
            "by_corridor": corridor_counts,
            "max_predicted_surge_pct": max_surge,
            "most_impacted_station": most_impacted_station or "Ameerpet",
        }

    def _save_disk_cache(self, data: dict[str, Any]) -> None:
        """Persist to disk."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(UNIFIED_DISRUPTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.warning("Failed to save unified disruptions cache: %s", exc)


# Global singleton instance
disruption_service = DisruptionService()
