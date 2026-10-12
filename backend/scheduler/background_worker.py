"""
scheduler/background_worker.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
APScheduler-based background worker for the HMR Demand Optimisation system.

Scheduled jobs
--------------
* job_scrape_events   - daily at 06:00 IST
* job_fetch_weather   - every 3 hours
* job_detect_anomalies - every 30 minutes

On first launch all three jobs are also queued to run 10 seconds after
startup so the application is immediately populated with live data.

Caches
------
* WeatherCache  - reads/writes backend/data/weather_cache.json
* EventCache    - reads backend/data/live_events.json (written by EventAggregator)

Dependencies (installed separately):
    apscheduler>=3.10
    pandas (for historical demand rolling window)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path bootstrap - ensure backend package is importable from anywhere
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ---------------------------------------------------------------------------
# APScheduler imports
# ---------------------------------------------------------------------------
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DATA_DIR = _BACKEND_DIR / "data"
_WEATHER_STALE_HOURS = 3          # hours before cache is considered stale
_ANOMALY_ROLLING_ROWS = 500       # rows from historical_demand.csv for detection
_STARTUP_DELAY_SECONDS = 5        # seconds before startup jobs fire

# ---------------------------------------------------------------------------
# Pre-import scraper and model classes synchronously to prevent thread deadlock
# ---------------------------------------------------------------------------
try:
    from scrapers.weather_client import WeatherClient
except Exception as _e:
    WeatherClient = None
    logger.debug("WeatherClient pre-import: %s", _e)

try:
    from scrapers.event_scraper import EventAggregator, save_live_events
except Exception as _e:
    EventAggregator = None
    save_live_events = None
    logger.debug("EventAggregator pre-import: %s", _e)

try:
    from models.anomaly_detector import AnomalyDetector
except Exception as _e:
    AnomalyDetector = None
    logger.debug("AnomalyDetector pre-import: %s", _e)

# ============================================================================
# WeatherCache
# ============================================================================

class WeatherCache:
    """
    Persist and retrieve weather data from a JSON file on disk.

    Schema
    ------
    {
        "weather_code": int,
        "temperature":  float,
        "forecast":     [{"hour": int, "weather_code": int, "temperature": float}, ...],
        "timestamp":    "ISO-8601 string"
    }
    """

    CACHE_PATH: Path = _DATA_DIR / "weather_cache.json"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    @classmethod
    def save(
        cls,
        weather_code: int,
        temperature: float,
        forecast_list: List[Dict[str, Any]],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Persist current conditions and 24-hour forecast to disk."""
        if timestamp is None:
            timestamp = datetime.now()
        payload = {
            "weather_code": weather_code,
            "temperature": temperature,
            "forecast": forecast_list,
            "timestamp": timestamp.isoformat(),
        }
        cls.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with cls.CACHE_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        logger.debug("WeatherCache: saved (code=%s, temp=%.1f-C)", weather_code, temperature)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> Dict[str, Any]:
        """
        Load cached weather data.

        Returns
        -------
        dict with keys:
            weather_code (int), temperature (float), forecast (list),
            timestamp (str | None), is_stale (bool)
        """
        defaults: Dict[str, Any] = {
            "weather_code": 0,
            "temperature": 30.0,
            "forecast": [],
            "timestamp": None,
            "is_stale": True,
        }
        if not cls.CACHE_PATH.exists():
            return defaults
        try:
            with cls.CACHE_PATH.open(encoding="utf-8") as fh:
                data = json.load(fh)
            ts_str = data.get("timestamp")
            is_stale = True
            if ts_str:
                cached_at = datetime.fromisoformat(ts_str)
                age = datetime.now() - cached_at
                is_stale = age > timedelta(hours=_WEATHER_STALE_HOURS)
            return {
                "weather_code": int(data.get("weather_code", 0)),
                "temperature": float(data.get("temperature", 30.0)),
                "forecast": data.get("forecast", []),
                "timestamp": ts_str,
                "is_stale": is_stale,
            }
        except Exception as exc:
            logger.warning("WeatherCache.load failed: %s", exc)
            return defaults

    # ------------------------------------------------------------------
    # Forecast helper
    # ------------------------------------------------------------------
    @classmethod
    def get_weather_for_hour(cls, hour: int) -> Tuple[int, float]:
        """
        Find the closest forecast slot for a given hour (0-23).

        Returns
        -------
        (weather_code, temperature) - falls back to current conditions if no
        matching forecast slot is found.
        """
        cached = cls.load()
        forecast = cached.get("forecast", [])
        # Exact match first
        for slot in forecast:
            if slot.get("hour") == hour:
                return int(slot.get("weather_code", 0)), float(slot.get("temperature", 30.0))
        # Nearest slot
        if forecast:
            nearest = min(forecast, key=lambda s: abs(s.get("hour", 0) - hour))
            return int(nearest.get("weather_code", 0)), float(nearest.get("temperature", 30.0))
        return cached["weather_code"], cached["temperature"]


# ============================================================================
# EventCache
# ============================================================================

class EventCache:
    """
    Read-only access to live events stored by the EventAggregator scraper.

    The underlying JSON file is a list of event objects, each expected to have
    at least the following fields:
        name, start_time (ISO-8601), end_time (ISO-8601), venue_lat, venue_lon
    """

    CACHE_PATH: Path = _DATA_DIR / "live_events.json"

    # ------------------------------------------------------------------
    # Raw load
    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> List[Dict[str, Any]]:
        """Return the full event list; returns [] if the file is missing."""
        if not cls.CACHE_PATH.exists():
            return []
        try:
            with cls.CACHE_PATH.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
            # Some scrapers wrap the list in a dict
            if isinstance(data, dict):
                return data.get("events", [])
            return []
        except Exception as exc:
            logger.warning("EventCache.load failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Filtered views
    # ------------------------------------------------------------------
    @classmethod
    def _parse_iso(cls, dt_str: str) -> datetime:
        """Parse ISO string handling 'Z' suffix and normalizing to naive local time."""
        if not dt_str:
            return datetime.now()
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt
        except Exception:
            return datetime.now()

    @classmethod
    def get_upcoming(cls, within_hours: int = 48) -> List[Dict[str, Any]]:
        """
        Return events whose start_time falls within the next *within_hours* hours,
        sorted chronologically.
        """
        now = datetime.now()
        cutoff = now + timedelta(hours=within_hours)
        results = []
        for ev in cls.load():
            try:
                start = cls._parse_iso(ev.get("start_time", ""))
                if now <= start <= cutoff:
                    results.append(ev)
            except Exception:
                continue
        return sorted(results, key=lambda e: e.get("start_time", ""))

    @classmethod
    def get_active_now(cls, buffer_minutes: int = 60) -> List[Dict[str, Any]]:
        """
        Return events that are currently ongoing **or** starting within the next
        *buffer_minutes* minutes.
        """
        now = datetime.now()
        buffer_start = now - timedelta(minutes=buffer_minutes)
        buffer_end = now + timedelta(minutes=buffer_minutes)
        results = []
        for ev in cls.load():
            try:
                start = cls._parse_iso(ev.get("start_time", ""))
                end = cls._parse_iso(ev.get("end_time", ""))
                ongoing = start <= now <= end
                imminent = buffer_start <= start <= buffer_end
                if ongoing or imminent:
                    results.append(ev)
            except Exception:
                continue
        return sorted(results, key=lambda e: e.get("start_time", ""))

    @classmethod
    def get_events_for_date(cls, target_date: Any) -> List[Dict[str, Any]]:
        """
        Return all events scheduled on the given calendar date (YYYY-MM-DD or date object).
        """
        if isinstance(target_date, str):
            try:
                target_date = datetime.fromisoformat(target_date).date()
            except Exception:
                target_date = datetime.now().date()
        elif isinstance(target_date, datetime):
            target_date = target_date.date()

        matched = []
        for ev in cls.load():
            try:
                start = cls._parse_iso(ev.get("start_time", ""))
                if start.date() == target_date:
                    matched.append(ev)
            except Exception:
                continue
        return sorted(matched, key=lambda e: e.get("start_time", ""))


# ============================================================================
# Scheduled Jobs
# ============================================================================

def job_scrape_events() -> None:
    """
    Scheduled job: scrape live events from all configured sources.

    Runs daily at 06:00 IST.  Uses EventAggregator from
    ``scrapers.event_scraper``.  Results are persisted via
    ``save_live_events()``.
    """
    try:
        if EventAggregator is None:
            from scrapers.event_scraper import EventAggregator as _EA, save_live_events as _SLE
            _agg_cls = _EA
            _save_fn = _SLE
        else:
            _agg_cls = EventAggregator
            _save_fn = save_live_events

        logger.info("[job_scrape_events] Starting event scrape -")
        aggregator = _agg_cls()
        events = aggregator.fetch_all_events()
        _save_fn(events)
        logger.info("[job_scrape_events] Done - %d event(s) saved.", len(events))
    except Exception as exc:
        logger.error("[job_scrape_events] Unexpected error: %s", exc, exc_info=True)


def job_fetch_weather() -> None:
    """
    Scheduled job: fetch current weather and 24-hour forecast.

    Runs every 3 hours.  Uses ``WeatherClient`` from
    ``scrapers.weather_client``.  Results are persisted via
    :class:`WeatherCache`.
    """
    try:
        if WeatherClient is None:
            from scrapers.weather_client import WeatherClient as _WC
            _client_cls = _WC
        else:
            _client_cls = WeatherClient

        logger.info("[job_fetch_weather] Fetching weather -")
        client = _client_cls()

        # Current conditions
        if hasattr(client, "fetch_current"):
            curr = client.fetch_current()
            weather_code = curr.get("weather_code", 0)
            temperature = curr.get("temperature", 30.0)
        elif hasattr(client, "get_live_weather_code_and_temp"):
            weather_code, temperature = client.get_live_weather_code_and_temp()
        else:
            weather_code, temperature = 0, 30.0

        # 24-hour forecast
        forecast_list: List[Dict[str, Any]] = []
        if hasattr(client, "fetch_forecast"):
            forecast_list = client.fetch_forecast(hours=24) or []
        elif hasattr(client, "get_forecast"):
            forecast_list = client.get_forecast() or []

        WeatherCache.save(
            weather_code=weather_code,
            temperature=temperature,
            forecast_list=forecast_list,
        )
        logger.info(
            "[job_fetch_weather] Done - code=%s, temp=%.1f-C, %d forecast slots.",
            weather_code,
            temperature,
            len(forecast_list),
        )
    except ImportError as exc:
        logger.warning("[job_fetch_weather] WeatherClient not available: %s", exc)
    except Exception as exc:
        logger.error("[job_fetch_weather] Unexpected error: %s", exc, exc_info=True)


def job_detect_anomalies() -> None:
    """
    Scheduled job: run batch anomaly detection over recent demand data.

    Runs every 30 minutes.  Loads a rolling window from
    ``historical_demand.csv`` (or ``live_demand_buffer.json`` if it exists),
    passes each row through :class:`~models.anomaly_detector.AnomalyDetector`,
    and persists CRITICAL / HIGH severity alerts to
    ``backend/data/active_alerts.json``.
    """
    try:
        from models.anomaly_detector import AnomalyDetector  # type: ignore[import]

        logger.info("[job_detect_anomalies] Running anomaly detection -")

        # -- Load rolling demand window ------------------------------------
        live_buffer_path = _DATA_DIR / "live_demand_buffer.json"
        hist_csv_path = _DATA_DIR / "historical_demand.csv"

        rows: List[Dict[str, Any]] = []

        if live_buffer_path.exists():
            try:
                with live_buffer_path.open(encoding="utf-8") as fh:
                    rows = json.load(fh)
                logger.debug("[job_detect_anomalies] Loaded %d rows from live buffer.", len(rows))
            except Exception as exc:
                logger.warning("[job_detect_anomalies] Could not read live buffer: %s", exc)

        if not rows and hist_csv_path.exists():
            try:
                import pandas as pd  # noqa: PLC0415

                df = pd.read_csv(hist_csv_path)
                tail = df.tail(_ANOMALY_ROLLING_ROWS)
                rows = tail.to_dict("records")
                logger.debug(
                    "[job_detect_anomalies] Loaded %d rows from historical CSV.", len(rows)
                )
            except Exception as exc:
                logger.warning("[job_detect_anomalies] Could not read historical CSV: %s", exc)

        if not rows:
            logger.info("[job_detect_anomalies] No demand data available; skipping.")
            return

        # -- Run detection -------------------------------------------------
        detector = AnomalyDetector()
        alerts: List[Dict[str, Any]] = []

        for row in rows:
            try:
                result = detector.detect(
                    station_id=str(row.get("station_id", "")),
                    corridor=str(row.get("corridor", "RED")),
                    hour=int(row.get("hour", 12)),
                    observed_count=int(row.get("passenger_count", row.get("observed_count", 0))),
                    expected_count=row.get("expected_count"),
                    date=row.get("date"),
                )
                if result and result.get("severity") in ("CRITICAL", "HIGH"):
                    alerts.append(result)
            except Exception:
                continue  # never let one bad row crash the job

        # -- Persist alerts ------------------------------------------------
        alerts_path = _DATA_DIR / "active_alerts.json"
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Merge with existing alerts to avoid losing history within the same window
        existing: List[Dict[str, Any]] = []
        if alerts_path.exists():
            try:
                with alerts_path.open(encoding="utf-8") as fh:
                    existing = json.load(fh)
            except Exception:
                existing = []

        # De-duplicate by station_id + hour + date; new results win
        existing_keys = {
            (a.get("station_id"), a.get("hour"), a.get("date")) for a in alerts
        }
        merged = [
            a
            for a in existing
            if (a.get("station_id"), a.get("hour"), a.get("date")) not in existing_keys
        ]
        merged.extend(alerts)
        # Keep at most 1 000 alerts in the file
        merged = merged[-1000:]

        with alerts_path.open("w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)

        critical = sum(1 for a in alerts if a.get("severity") == "CRITICAL")
        high = sum(1 for a in alerts if a.get("severity") == "HIGH")
        logger.info(
            "[job_detect_anomalies] Done - %d new alert(s) (CRITICAL=%d, HIGH=%d).",
            len(alerts),
            critical,
            high,
        )
    except ImportError as exc:
        logger.warning("[job_detect_anomalies] AnomalyDetector not available: %s", exc)
    except Exception as exc:
        logger.error("[job_detect_anomalies] Unexpected error: %s", exc, exc_info=True)


# ============================================================================
# Scheduler lifecycle
# ============================================================================

_scheduler_instance: Optional[BackgroundScheduler] = None


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Return the singleton :class:`BackgroundScheduler` instance (or None)."""
    return _scheduler_instance


def start_scheduler() -> BackgroundScheduler:
    """
    Create, configure, and start the APScheduler ``BackgroundScheduler``.

    Jobs
    ----
    * ``scrape_events``   - CronTrigger, daily 06:00 IST
    * ``fetch_weather``   - IntervalTrigger, every 3 hours
    * ``detect_anomalies``- IntervalTrigger, every 30 minutes
    * ``startup_events``  - DateTrigger, now + 10 s (one-shot)
    * ``startup_weather`` - DateTrigger, now + 10 s (one-shot)
    * ``startup_anomalies``- DateTrigger, now + 10 s (one-shot)

    Returns
    -------
    The started :class:`BackgroundScheduler` instance.
    """
    global _scheduler_instance

    if _scheduler_instance is not None and _scheduler_instance.running:
        logger.info("Scheduler already running; reusing existing instance.")
        return _scheduler_instance

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # -- Recurring jobs ----------------------------------------------------
    scheduler.add_job(
        job_scrape_events,
        trigger=CronTrigger(hour=6, minute=0, timezone="Asia/Kolkata"),
        id="scrape_events",
        name="Daily event scrape (06:00 IST)",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        job_fetch_weather,
        trigger=IntervalTrigger(hours=3),
        id="fetch_weather",
        name="Weather refresh (3h interval)",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.add_job(
        job_detect_anomalies,
        trigger=IntervalTrigger(minutes=30),
        id="detect_anomalies",
        name="Anomaly detection (30m interval)",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # -- One-shot startup jobs (staggered to prevent race conditions) -----
    now = datetime.now()

    scheduler.add_job(
        job_fetch_weather,
        trigger=DateTrigger(run_date=now + timedelta(seconds=2)),
        id="startup_weather",
        name="Startup: weather fetch",
        replace_existing=True,
    )

    scheduler.add_job(
        job_scrape_events,
        trigger=DateTrigger(run_date=now + timedelta(seconds=10)),
        id="startup_events",
        name="Startup: event scrape",
        replace_existing=True,
    )

    scheduler.add_job(
        job_detect_anomalies,
        trigger=DateTrigger(run_date=now + timedelta(seconds=20)),
        id="startup_anomalies",
        name="Startup: anomaly detection",
        replace_existing=True,
    )

    scheduler.start()
    _scheduler_instance = scheduler

    logger.info(
        "Background scheduler started (timezone=Asia/Kolkata). Jobs: %s",
        [job.id for job in scheduler.get_jobs()],
    )
    return scheduler


def stop_scheduler(scheduler: Optional[BackgroundScheduler] = None) -> None:
    """
    Gracefully shut down the scheduler.

    Parameters
    ----------
    scheduler:
        The scheduler instance to stop.  Falls back to the module-level
        singleton if *None* is passed.
    """
    global _scheduler_instance

    target = scheduler or _scheduler_instance
    if target is None:
        logger.info("stop_scheduler called but no scheduler is running.")
        return
    try:
        if target.running:
            target.shutdown(wait=False)
            logger.info("Background scheduler stopped.")
    except Exception as exc:
        logger.warning("Error stopping scheduler: %s", exc)
    finally:
        if target is _scheduler_instance:
            _scheduler_instance = None
