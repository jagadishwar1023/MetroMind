import pandas as pd
import numpy as np
from datetime import date

IT_STATIONS = {'HTC', 'RDG', 'MAD', 'DGC', 'PED', 'JCP', 'YUG'}
COLLEGE_STATIONS = {'JNT', 'KUK', 'OMC', 'RTC', 'NAR', 'SCR', 'MET'}
INTERCHANGE_STATIONS = {'AME', 'MGB', 'JBS'}

def station_it_density(stop_id):
    return 0.9 if stop_id in IT_STATIONS else (0.2 if stop_id in INTERCHANGE_STATIONS else 0.1)

def station_college_density(stop_id):
    return 0.85 if stop_id in COLLEGE_STATIONS else 0.1

def is_holiday(dt):
    """Check if a date is a public holiday in Telangana."""
    # Key Telangana/national holidays
    holidays_2026 = [
        date(2026, 1, 1), date(2026, 1, 26), date(2026, 3, 25),
        date(2026, 4, 6), date(2026, 4, 14), date(2026, 5, 1),
        date(2026, 6, 2), date(2026, 8, 15), date(2026, 10, 2),
        date(2026, 10, 13), date(2026, 10, 20), date(2026, 11, 1),
        date(2026, 12, 25)
    ]
    holidays_2027 = [
        date(2027, 1, 1), date(2027, 1, 26), date(2027, 3, 14),
        date(2027, 4, 26), date(2027, 8, 15), date(2027, 10, 2),
        date(2027, 12, 25)
    ]
    all_holidays = set(holidays_2026 + holidays_2027)
    if isinstance(dt, str):
        dt = date.fromisoformat(dt)
    return 1 if dt in all_holidays else 0
