import pandas as pd
import os

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_GTFS_DIR = BASE_DIR / "data" / "gtfs"

GTFS_DIR = Path(os.environ.get("GTFS_DIR", str(DEFAULT_GTFS_DIR)))
if not GTFS_DIR.exists():
    fallback = Path(r"C:\Users\jagad\Downloads\metrodata")
    if fallback.exists():
        GTFS_DIR = fallback

def load_stops():
    df = pd.read_csv(os.path.join(str(GTFS_DIR), "stops.txt"))
    # Filter for parent stations (location_type==1) if applicable
    if 'location_type' in df.columns:
        df = df[df['location_type'] == 1]
    return df

def load_trips():
    return pd.read_csv(os.path.join(GTFS_DIR, "trips.txt"))

def load_stop_times():
    return pd.read_csv(os.path.join(GTFS_DIR, "stop_times.txt"))

def load_routes():
    return pd.read_csv(os.path.join(GTFS_DIR, "routes.txt"))

def get_station_route_map():
    stop_times = load_stop_times()
    trips = load_trips()
    
    # Normalize stop_id to parent by stripping trailing digits
    stop_times['parent_stop'] = stop_times['stop_id'].str.replace(r'\d+$', '', regex=True)
    
    merged = stop_times.merge(trips[['trip_id', 'route_id']], on='trip_id')
    
    # map parent stop_id to list of unique route_ids
    route_map = {}
    grouped = merged.groupby('parent_stop')['route_id'].unique()
    for stop_id, routes in grouped.items():
        route_map[stop_id] = list(routes)
        
    return route_map
