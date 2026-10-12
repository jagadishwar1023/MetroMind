import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path
from datetime import date, timedelta

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gtfs.headway import get_headway_dict
from utils.features import is_holiday, station_it_density, station_college_density

def generate():
    STATIONS = {
        'AME': 35000, 'HTC': 32000, 'MGB': 28000, 'JBS': 22000,
        'UPL': 18000, 'RDG': 20000, 'MYP': 15000, 'LBN': 15000, 'NAG': 12000
    }
    
    # Load stops for others
    from gtfs.loader import load_stops, get_station_route_map
    stops = load_stops()
    route_map = get_station_route_map()
    
    station_meta = []
    station_data = []
    
    for _, row in stops.iterrows():
        sid = row['stop_id']
        sname = row['stop_name']
        slat = row['stop_lat']
        slon = row['stop_lon']
        base = STATIONS.get(sid, np.random.randint(5000, 12000))
        corridors = route_map.get(sid, ['RED'])
        
        station_meta.append({
            "stop_id": sid, "stop_name": sname, "stop_lat": slat, "stop_lon": slon,
            "corridors": corridors, "base_daily_passengers": base,
            "it_density": station_it_density(sid), "college_density": station_college_density(sid)
        })
        
        for c in corridors:
            station_data.append({
                "station_id": sid, "station_name": sname, "corridor": c, "base": base,
                "it_density": station_it_density(sid), "college_density": station_college_density(sid)
            })
            
    # Save meta
    meta_path = Path(__file__).parent / 'station_meta.json'
    with open(meta_path, 'w') as f:
        json.dump(station_meta, f, indent=2)
        
    # Generate 365 days
    start_date = date(2025, 1, 1)
    
    hw_wk = get_headway_dict('WK')
    hw_sa = get_headway_dict('SA')
    hw_su = get_headway_dict('SU')
    
    hour_mult = {
        5: 0.01, 6: 0.03, 7: 0.06, 8: 0.12, 9: 0.11, 10: 0.07,
        11: 0.05, 12: 0.05, 13: 0.05, 14: 0.04, 15: 0.04, 16: 0.06,
        17: 0.09, 18: 0.11, 19: 0.10, 20: 0.07, 21: 0.04, 22: 0.02, 23: 0.01
    }
    
    records = []
    
    for i in range(365):
        dt = start_date + timedelta(days=i)
        dow = dt.weekday()
        is_wknd = 1 if dow >= 5 else 0
        ishol = is_holiday(dt)
        
        service_id = 'WK'
        day_mult = 1.0
        if dow == 5:
            service_id = 'SA'
            day_mult = 0.72
        elif dow == 6:
            service_id = 'SU'
            day_mult = 0.60
            
        hw_dict = hw_wk if service_id == 'WK' else (hw_sa if service_id == 'SA' else hw_su)
        
        # Weather
        r = np.random.rand()
        weather = 0
        if r > 0.9: weather = 2
        elif r > 0.7: weather = 1
        temp = np.clip(np.random.normal(32, 5), 18, 45)
        
        for sd in station_data:
            sid = sd['station_id']
            corridor = sd['corridor']
            
            for h in range(5, 24):
                base_pass = sd['base'] * hour_mult.get(h, 0.0) * day_mult
                noise = np.random.uniform(0.85, 1.15)
                pax = int(base_pass * noise)
                
                hw = hw_dict.get(corridor, {}).get(sid, {}).get(h, None)
                if hw is None:
                    tph = 6.0
                else:
                    tph = round(60.0 / hw, 1)
                    
                records.append({
                    'date': str(dt),
                    'day_of_week': dow,
                    'service_id': service_id,
                    'is_weekend': is_wknd,
                    'is_holiday': ishol,
                    'station_id': sid,
                    'station_name': sd['station_name'],
                    'corridor': corridor,
                    'hour': h,
                    'trains_per_hour': tph,
                    'nearby_it_density': sd['it_density'],
                    'nearby_college_density': sd['college_density'],
                    'weather_code': weather,
                    'temperature': temp,
                    'passenger_count': pax
                })
                
    df = pd.DataFrame(records)
    out_path = Path(__file__).parent / 'historical_demand.csv'
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} records to {out_path}")

if __name__ == '__main__':
    generate()
