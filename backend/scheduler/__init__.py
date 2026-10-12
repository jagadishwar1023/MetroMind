"""
scheduler/__init__.py
~~~~~~~~~~~~~~~~~~~~~
Public API for the HMR background scheduler package.
Exports the scheduler lifecycle functions and cache utilities.
"""

from .background_worker import (
    start_scheduler,
    stop_scheduler,
    get_scheduler,
    WeatherCache,
    EventCache,
)

__all__ = [
    "start_scheduler",
    "stop_scheduler",
    "get_scheduler",
    "WeatherCache",
    "EventCache",
]
