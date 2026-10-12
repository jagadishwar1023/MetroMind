import pandas as pd
import numpy as np
from .loader import load_trips, load_stop_times

def compute_headways(service_id='WK'):
    """
    Returns a DataFrame with columns:
    route_id, stop_id, hour, avg_headway_min, trains_per_hour
    """
    trips = load_trips()
    stop_times = load_stop_times()
    
    # Filter for service
    service_trips = trips[trips['service_id'] == service_id]['trip_id'].tolist()
    filtered = stop_times[stop_times['trip_id'].isin(service_trips)].copy()
    
    # Normalize stop_id to parent (strip trailing platform digits like 1,2,3,4)
    import re
    filtered['parent_stop'] = filtered['stop_id'].str.replace(r'\d+$', '', regex=True)
    
    # Parse hour from arrival_time (handles times > 24:00)
    def parse_hour(t):
        try:
            return int(str(t).split(':')[0]) % 24
        except:
            return 0
    filtered['hour'] = filtered['arrival_time'].apply(parse_hour)
    
    # Join route info
    trip_route = trips[['trip_id', 'route_id']].drop_duplicates()
    filtered = filtered.merge(trip_route, on='trip_id')
    
    records = []
    for (route_id, parent_stop, hour), group in filtered.groupby(['route_id', 'parent_stop', 'hour']):
        arr_times = sorted(group['arrival_time'].tolist())
        if len(arr_times) < 2:
            continue
        def to_minutes(t):
            parts = str(t).split(':')
            return int(parts[0]) * 60 + int(parts[1])
        headways = []
        for i in range(len(arr_times) - 1):
            delta = to_minutes(arr_times[i+1]) - to_minutes(arr_times[i])
            if 0 < delta < 60:
                headways.append(delta)
        if headways:
            avg_hw = round(np.mean(headways), 2)
            tph = round(60 / avg_hw, 1)
            records.append({'route_id': route_id, 'stop_id': parent_stop, 'hour': hour, 'avg_headway_min': avg_hw, 'trains_per_hour': tph})
    
    return pd.DataFrame(records)

def get_headway_dict(service_id='WK'):
    """Returns nested dict: {route_id: {stop_id: {hour: headway_min}}}"""
    df = compute_headways(service_id)
    result = {}
    for _, row in df.iterrows():
        r, s, h = row['route_id'], row['stop_id'], row['hour']
        if r not in result: result[r] = {}
        if s not in result[r]: result[r][s] = {}
        result[r][s][h] = row['avg_headway_min']
    return result
