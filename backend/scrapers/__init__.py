"""
scrapers/__init__.py
--------------------
Public surface of the ``scrapers`` package for the HMR demand optimization
system.  Import the key symbols from here so the rest of the backend never
needs to know the internal module layout.

Usage
-----
    from scrapers import EventAggregator, load_live_events, save_live_events
    from scrapers import WeatherClient, get_live_weather_code_and_temp
"""

from scrapers.event_scraper import (
    EventAggregator,
    load_live_events,
    save_live_events,
)
from scrapers.weather_client import (
    WeatherClient,
    get_live_weather_code_and_temp,
)

__all__ = [
    "EventAggregator",
    "load_live_events",
    "save_live_events",
    "WeatherClient",
    "get_live_weather_code_and_temp",
]
