"""
Comprehensive Telangana & National Public Holidays Calendar and
Dynamic Long Weekend Detection Engine for Hyderabad Metro (HMR).

Models:
1. Morning Exodus Rush at Intercity Bus Terminals & Highway Outbound Hubs:
   - MGBS (Mahatma Gandhi Bus Station - Red & Green interchange)
   - JBS Parade Ground (Jubilee Bus Station - Green Line)
   - L.B. Nagar (Highway bus hub towards Vijayawada / South AP & Telangana - Red Line)
   - Miyapur (Private intercity bus depot & NH65 towards Mumbai/Nizamabad - Red Line)
   - Secunderabad Junction (Interstate rail terminal - Blue & Green Lines)
   - Nampally (Hyderabad Deccan rail terminal - Red Line)

2. Daytime & Evening Surge at Tourist, Cultural & Recreation Destinations:
   - Khairatabad (Tank Bund, Hussain Sagar Lake Promenade, Lumbini Park, People's Plaza)
   - Durgam Cheruvu (Freshwater lake waterfront, iconic Cable-Stayed Bridge, Inorbit)
   - Assembly (Public Gardens, Telangana State Museum)
   - Lakdikapul (Birla Mandir & Birla Science Planetarium)
   - Hitec City (Shilparamam Arts & Crafts Cultural Village)
   - Peddamma Gudi (Jubilee Hills Temple)
"""

from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import calendar

# ---------------------------------------------------------------------------
# Telangana State & National Public Holidays Directory (2025 - 2027)
# ---------------------------------------------------------------------------
HOLIDAY_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ── 2025 ──────────────────────────────────────────────────────────────
    '2025-01-01': {'name': "New Year's Day", 'type': 'long_weekend_leisure', 'significance': 'state'},
    '2025-01-14': {'name': 'Bhogi', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2025-01-15': {'name': 'Makar Sankranti', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2025-01-16': {'name': 'Kanuma', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2025-01-26': {'name': 'Republic Day', 'type': 'national_civic', 'significance': 'national'},
    '2025-02-26': {'name': 'Maha Shivaratri', 'type': 'religious_festival', 'significance': 'telangana_major'},
    '2025-03-14': {'name': 'Holi', 'type': 'festival_holiday', 'significance': 'state'},
    '2025-03-30': {'name': 'Ugadi (Telugu New Year)', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2025-03-31': {'name': 'Eid ul-Fitr (Ramzan)', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2025-04-05': {'name': 'Babu Jagjivan Ram Jayanti', 'type': 'national_civic', 'significance': 'state'},
    '2025-04-14': {'name': 'Dr. B.R. Ambedkar Jayanti', 'type': 'national_civic', 'significance': 'national'},
    '2025-04-18': {'name': 'Good Friday', 'type': 'long_weekend_leisure', 'significance': 'national'},
    '2025-05-01': {'name': 'May Day (Labour Day)', 'type': 'national_civic', 'significance': 'state'},
    '2025-06-02': {'name': 'Telangana State Formation Day', 'type': 'state_civic', 'significance': 'telangana_major'},
    '2025-06-07': {'name': 'Bakrid (Eid ul-Adha)', 'type': 'festival_holiday', 'significance': 'telangana_major'},
    '2025-07-21': {'name': 'Bonalu Festival', 'type': 'state_cultural_festival', 'significance': 'telangana_major'},
    '2025-08-15': {'name': 'Independence Day', 'type': 'national_civic', 'significance': 'national'},
    '2025-08-27': {'name': 'Vinayaka Chaturthi (Ganesh Festival)', 'type': 'state_cultural_festival', 'significance': 'telangana_major'},
    '2025-09-06': {'name': 'Ganesh Immersion (Tank Bund/Khairatabad)', 'type': 'state_cultural_festival', 'significance': 'telangana_major'},
    '2025-10-02': {'name': 'Mahatma Gandhi Jayanti', 'type': 'national_civic', 'significance': 'national'},
    '2025-10-02': {'name': 'Vijayadashami (Dussehra)', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2025-10-20': {'name': 'Deepavali (Diwali)', 'type': 'festival_mass_exodus', 'significance': 'national'},
    '2025-12-25': {'name': 'Christmas', 'type': 'festival_holiday', 'significance': 'national'},

    # ── 2026 ──────────────────────────────────────────────────────────────
    '2026-01-01': {'name': "New Year's Day", 'type': 'long_weekend_leisure', 'significance': 'state'},
    '2026-01-14': {'name': 'Bhogi', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2026-01-15': {'name': 'Makara Sankranti', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2026-01-16': {'name': 'Kanuma', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2026-01-26': {'name': 'Republic Day', 'type': 'national_civic', 'significance': 'national'},
    '2026-02-15': {'name': 'Maha Shivaratri', 'type': 'religious_festival', 'significance': 'telangana_major'},
    '2026-03-03': {'name': 'Holi', 'type': 'festival_holiday', 'significance': 'state'},
    '2026-03-19': {'name': 'Ugadi (Telugu New Year)', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2026-03-20': {'name': 'Eid ul-Fitr (Ramzan)', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2026-04-03': {'name': 'Good Friday', 'type': 'long_weekend_leisure', 'significance': 'national'},
    '2026-04-05': {'name': 'Babu Jagjivan Ram Jayanti', 'type': 'national_civic', 'significance': 'state'},
    '2026-04-14': {'name': 'Dr. B.R. Ambedkar Jayanti', 'type': 'national_civic', 'significance': 'national'},
    '2026-05-01': {'name': 'May Day (Workers Day)', 'type': 'national_civic', 'significance': 'state'},
    '2026-05-27': {'name': 'Eid ul-Adha (Bakrid)', 'type': 'festival_holiday', 'significance': 'telangana_major'},
    '2026-06-02': {'name': 'Telangana State Formation Day', 'type': 'state_civic', 'significance': 'telangana_major'},
    '2026-06-25': {'name': 'Moharram', 'type': 'religious_festival', 'significance': 'state'},
    '2026-07-20': {'name': 'Bonalu Festival (Secunderabad/Golconda)', 'type': 'state_cultural_festival', 'significance': 'telangana_major'},
    '2026-08-15': {'name': 'Independence Day', 'type': 'national_civic', 'significance': 'national'},
    '2026-08-25': {'name': 'Milad-un-Nabi', 'type': 'religious_festival', 'significance': 'state'},
    '2026-09-04': {'name': 'Sri Krishna Janmashtami', 'type': 'religious_festival', 'significance': 'state'},
    '2026-09-14': {'name': 'Vinayaka Chaturthi', 'type': 'state_cultural_festival', 'significance': 'telangana_major'},
    '2026-09-24': {'name': 'Ganesh Nimajjanam (Hussain Sagar Immersion)', 'type': 'state_cultural_festival', 'significance': 'telangana_major'},
    '2026-10-02': {'name': 'Mahatma Gandhi Jayanti', 'type': 'national_civic', 'significance': 'national'},
    '2026-10-18': {'name': 'Bathukamma Festival Starting', 'type': 'state_cultural_festival', 'significance': 'telangana_major'},
    '2026-10-19': {'name': 'Durgashtami / Maha Navami', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2026-10-20': {'name': 'Vijayadashami (Dussehra)', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2026-11-08': {'name': 'Deepavali (Diwali)', 'type': 'festival_mass_exodus', 'significance': 'national'},
    '2026-11-24': {'name': 'Kartika Purnima', 'type': 'religious_festival', 'significance': 'state'},
    '2026-12-25': {'name': 'Christmas', 'type': 'festival_holiday', 'significance': 'national'},

    # ── 2027 ──────────────────────────────────────────────────────────────
    '2027-01-01': {'name': "New Year's Day", 'type': 'long_weekend_leisure', 'significance': 'state'},
    '2027-01-14': {'name': 'Bhogi', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2027-01-15': {'name': 'Makara Sankranti', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2027-01-26': {'name': 'Republic Day', 'type': 'national_civic', 'significance': 'national'},
    '2027-03-23': {'name': 'Holi', 'type': 'festival_holiday', 'significance': 'state'},
    '2027-04-07': {'name': 'Ugadi (Telugu New Year)', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2027-04-14': {'name': 'Dr. B.R. Ambedkar Jayanti', 'type': 'national_civic', 'significance': 'national'},
    '2027-05-01': {'name': 'May Day', 'type': 'national_civic', 'significance': 'state'},
    '2027-06-02': {'name': 'Telangana State Formation Day', 'type': 'state_civic', 'significance': 'telangana_major'},
    '2027-08-15': {'name': 'Independence Day', 'type': 'national_civic', 'significance': 'national'},
    '2027-10-02': {'name': 'Mahatma Gandhi Jayanti', 'type': 'national_civic', 'significance': 'national'},
    '2027-10-10': {'name': 'Vijayadashami (Dussehra)', 'type': 'festival_mass_exodus', 'significance': 'telangana_major'},
    '2027-10-29': {'name': 'Deepavali (Diwali)', 'type': 'festival_mass_exodus', 'significance': 'national'},
    '2027-12-25': {'name': 'Christmas', 'type': 'festival_holiday', 'significance': 'national'},
}

# ---------------------------------------------------------------------------
# Station Transit Profiles for Holidays
# ---------------------------------------------------------------------------
INTERCITY_BUS_AND_RAIL_STATIONS = {
    'MGB': {
        'name': 'MGBS (Mahatma Gandhi Bus Station)',
        'category': 'intercity_bus_terminal',
        'corridors': ['RED', 'GREEN'],
        'description': 'Largest intercity bus terminal in Asia (TSRTC, APSRTC, interstate routes)',
    },
    'JBS': {
        'name': 'JBS Parade Ground',
        'category': 'intercity_bus_terminal',
        'corridors': ['GREEN', 'BLUE'],
        'description': 'North Telangana major bus terminal (Karimnagar, Nizamabad, Adilabad routes)',
    },
    'LBN': {
        'name': 'L. B. Nagar',
        'category': 'highway_outbound_hub',
        'corridors': ['RED'],
        'description': 'Main highway passenger pickup point towards Vijayawada / South AP & Telangana (NH65)',
    },
    'MYP': {
        'name': 'Miyapur',
        'category': 'highway_outbound_hub',
        'corridors': ['RED'],
        'description': 'Major intercity private bus terminal & NH65 highway hub towards Mumbai/Pune/Nizamabad',
    },
    'SCR': {
        'name': 'Secunderabad Junction (West/East)',
        'category': 'railway_junction',
        'corridors': ['BLUE', 'GREEN'],
        'description': 'Primary interstate railway junction connecting all long-distance trains',
    },
    'NAM': {
        'name': 'Nampally (Hyderabad Deccan)',
        'category': 'railway_junction',
        'corridors': ['RED'],
        'description': 'Hyderabad Deccan railway terminus for intercity express trains',
    },
}

TOURIST_RECREATION_STATIONS = {
    'KHA': {
        'name': 'Khairatabad',
        'attraction': 'Hussain Sagar Lake, Tank Bund Promenade, Lumbini Park, People’s Plaza',
        'corridors': ['RED'],
        'peak_hours': [14, 15, 16, 17, 18, 19, 20, 21],
    },
    'DGC': {
        'name': 'Durgam Cheruvu',
        'attraction': 'Freshwater Lake Waterfront, Iconic Cable-Stayed Bridge, Inorbit Waterfront',
        'corridors': ['BLUE'],
        'peak_hours': [15, 16, 17, 18, 19, 20, 21],
    },
    'ASM': {
        'name': 'Assembly',
        'attraction': 'Public Gardens, Telangana State Archaeological Museum, Indira Park',
        'corridors': ['RED'],
        'peak_hours': [11, 12, 13, 14, 15, 16, 17],
    },
    'LKP': {
        'name': 'Lakdikapul',
        'attraction': 'Birla Mandir, B.M. Birla Science Planetarium, Tank Bund access',
        'corridors': ['RED'],
        'peak_hours': [15, 16, 17, 18, 19, 20],
    },
    'HTC': {
        'name': 'Hitec City',
        'attraction': 'Shilparamam Arts & Cultural Village (Handicrafts, cultural fairs, food stalls)',
        'corridors': ['BLUE'],
        'peak_hours': [14, 15, 16, 17, 18, 19, 20],
    },
    'PED': {
        'name': 'Peddamma Gudi',
        'attraction': 'Sri Peddamma Temple, Jubilee Hills (High weekend/holiday temple visits)',
        'corridors': ['BLUE'],
        'peak_hours': [8, 9, 10, 11, 17, 18, 19, 20],
    },
}


def is_public_holiday(dt: date | str) -> bool:
    """Return True if the date is a registered public holiday in Telangana."""
    if isinstance(dt, str):
      dt = date.fromisoformat(dt)
    dt_str = dt.strftime('%Y-%m-%d')
    return dt_str in HOLIDAY_REGISTRY


def get_holiday_and_weekend_details(dt: date | str) -> Dict[str, Any]:
    """
    Analyzes target date for public holiday status, long weekend continuity,
    and returns tailored crowd profiles for intercity bus terminals & tourist hubs.
    """
    if isinstance(dt, str):
      dt = date.fromisoformat(dt)

    dt_str = dt.strftime('%Y-%m-%d')
    dow = dt.weekday()  # 0=Mon, ..., 5=Sat, 6=Sun
    is_weekend = dow >= 5

    # 1. Holiday lookup
    holiday_meta = HOLIDAY_REGISTRY.get(dt_str)
    is_holiday = holiday_meta is not None
    holiday_name = holiday_meta['name'] if holiday_meta else None
    holiday_type = holiday_meta['type'] if holiday_meta else None

    # 2. Dynamic Long Weekend Scanner:
    # Check window [dt - 3 days to dt + 3 days] for contiguous non-working days
    # (weekends + holidays)
    def is_off_day(d: date) -> bool:
      return (d.weekday() >= 5) or (d.strftime('%Y-%m-%d') in HOLIDAY_REGISTRY)

    # Walk backward to find start of block
    block_start = dt
    while is_off_day(block_start - timedelta(days=1)):
      block_start -= timedelta(days=1)

    # Walk forward to find end of block
    block_end = dt
    while is_off_day(block_end + timedelta(days=1)):
      block_end += timedelta(days=1)

    block_length = (block_end - block_start).days + 1
    is_long_weekend = block_length >= 3 and (is_holiday or is_weekend)

    # Determine position within long weekend
    day_pos_in_block = (dt - block_start).days
    if day_pos_in_block == 0 or (day_pos_in_block == 1 and block_length >= 4):
      lw_position = 'start'  # Morning exodus rush!
    elif day_pos_in_block == block_length - 1:
      lw_position = 'end'    # Return rush!
    else:
      lw_position = 'mid'    # Full tourist & leisure day!

    # Format long weekend span string
    start_fmt = f"{calendar.month_abbr[block_start.month]} {block_start.day} ({calendar.day_abbr[block_start.weekday()]})"
    end_fmt = f"{calendar.month_abbr[block_end.month]} {block_end.day} ({calendar.day_abbr[block_end.weekday()]})"
    span_str = f"{start_fmt} – {end_fmt}" if is_long_weekend else None

    # If it's a regular weekend or holiday, synthesize holiday_name if none
    if not holiday_name:
      if is_long_weekend:
        # Find which day caused the holiday in the block
        curr = block_start
        found_name = None
        while curr <= block_end:
          c_str = curr.strftime('%Y-%m-%d')
          if c_str in HOLIDAY_REGISTRY:
            found_name = HOLIDAY_REGISTRY[c_str]['name']
            holiday_type = HOLIDAY_REGISTRY[c_str]['type']
            break
          curr += timedelta(days=1)
        holiday_name = f"Long Weekend ({found_name})" if found_name else "Extended Weekend"
      elif is_weekend:
        holiday_name = "Sunday Regular Weekend" if dow == 6 else "Saturday Weekend"
        holiday_type = "weekend"

    # 3. Crowd Surge Multipliers based on holiday nature
    # Major festival exodus gives highest bus hub boost
    if holiday_type == 'festival_mass_exodus':
      bus_surge_pct = 55
      tourist_surge_pct = 35
      summary_desc = (
          f"Massive Festive Period ({holiday_name}). High morning departures at MGBS, JBS, "
          f"LB Nagar, and Miyapur as passengers travel across Telangana & AP."
      )
    elif holiday_type == 'national_civic':
      bus_surge_pct = 35
      tourist_surge_pct = 50
      summary_desc = (
          f"National Holiday ({holiday_name}). High civic ceremonies at Secunderabad Parade Grounds, "
          f"Assembly, and massive family leisure crowds at Tank Bund and lakes."
      )
    elif is_long_weekend:
      bus_surge_pct = 45 if lw_position == 'start' else (30 if lw_position == 'mid' else 40)
      tourist_surge_pct = 40
      pos_text = "Morning exodus rush towards bus terminals" if lw_position == 'start' else ("Return traveler surge" if lw_position == 'end' else "Peak tourist & lake leisure")
      summary_desc = f"Long Weekend ({span_str}). {pos_text} across city transit hubs."
    elif is_weekend:
      bus_surge_pct = 20
      tourist_surge_pct = 35
      summary_desc = "Regular weekend transit profile with high afternoon recreational travel."
    else:
      bus_surge_pct = 0
      tourist_surge_pct = 0
      summary_desc = "Standard weekday commuter transit profile."

    return {
        'date': dt_str,
        'day_of_week': dow,
        'day_name': calendar.day_name[dow],
        'is_weekend': is_weekend,
        'is_holiday': is_holiday or (is_long_weekend and holiday_type != 'weekend'),
        'holiday_name': holiday_name,
        'holiday_type': holiday_type or 'regular',
        'is_long_weekend': is_long_weekend,
        'long_weekend_span': span_str,
        'long_weekend_days': block_length if is_long_weekend else 1,
        'long_weekend_position': lw_position if is_long_weekend else 'normal',
        'summary': summary_desc,
        'bus_terminal_surge': {
            'active': (is_holiday or is_long_weekend or is_weekend) and bus_surge_pct > 0,
            'surge_pct': bus_surge_pct,
            'station_ids': list(INTERCITY_BUS_AND_RAIL_STATIONS.keys()),
            'stations': [s['name'] for s in INTERCITY_BUS_AND_RAIL_STATIONS.values()],
            'peak_morning_hours': [6, 7, 8, 9, 10, 11],
            'peak_evening_hours': [17, 18, 19, 20, 21, 22] if lw_position == 'end' else [],
            'reason': 'Morning intercity passenger rush for TSRTC/APSRTC and private highway buses.',
        },
        'tourist_recreation_surge': {
            'active': (is_holiday or is_long_weekend or is_weekend) and tourist_surge_pct > 0,
            'surge_pct': tourist_surge_pct,
            'station_ids': list(TOURIST_RECREATION_STATIONS.keys()),
            'stations': [f"{s['name']} ({s['attraction'].split(',')[0]})" for s in TOURIST_RECREATION_STATIONS.values()],
            'peak_hours': [14, 15, 16, 17, 18, 19, 20, 21],
            'reason': 'Afternoon & evening leisure, lakefront promenades, cable bridge, and temple visits.',
        },
        'it_corridor_reduction': {
            'active': is_holiday and not is_weekend,
            'reduction_pct': 45,
            'stations': ['Raidurg', 'Hitec City', 'Madhapur'],
            'reason': 'Corporate IT corridor offices and universities closed for public holiday.',
        },
    }
