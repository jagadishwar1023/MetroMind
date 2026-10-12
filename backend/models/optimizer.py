import numpy as np
from typing import Dict

# HMR operational constants
MIN_HEADWAY = 2.0      # minutes
MAX_HEADWAY = 15.0     # minutes
TRAIN_CAPACITY = 975   # passengers per train
FLEET_SIZE = 57        # total train sets
CAPACITY_BUFFER = 1.1  # 10% buffer

# Approximate round-trip times per corridor (minutes)
ROUND_TRIP_TIMES = {
    'RED': 72,    # Miyapur ↔ LB Nagar
    'BLUE': 66,   # Nagole ↔ Raidurg
    'GREEN': 26   # JBS ↔ MGBS
}

def trains_needed(headway_min, corridor):
    """Number of trains to maintain given headway on a corridor."""
    rt = ROUND_TRIP_TIMES.get(corridor, 60)
    return max(1, rt / headway_min)

def optimal_headway(max_demand_pax, baseline_headway=6.0, baseline_demand=None):
    """
    Computes optimal headway considering passenger demand, baseline GTFS schedule, and capacity buffer.
    """
    # 1. Capacity requirement: how many trains needed to serve max station demand
    trains_for_capacity = (max_demand_pax * CAPACITY_BUFFER) / TRAIN_CAPACITY if max_demand_pax > 0 else 4.0
    capacity_hw = 60.0 / max(1.0, trains_for_capacity)
    
    # 2. Surge-based compression: if demand surged above baseline, tighten headway proportionally
    if baseline_demand and baseline_demand > 0 and max_demand_pax > baseline_demand:
        surge_ratio = max_demand_pax / baseline_demand
        surge_hw = baseline_headway / surge_ratio
        target_hw = min(baseline_headway, min(capacity_hw, surge_hw))
    else:
        # Default to baseline headway if capacity is already satisfied, or capacity_hw if higher frequency needed
        target_hw = min(baseline_headway, capacity_hw)
    
    # Bound between MIN_HEADWAY (2.0 min safety headway) and MAX_HEADWAY (15.0 min)
    return round(max(MIN_HEADWAY, min(MAX_HEADWAY, target_hw)), 1)

def optimize_schedule(demand_by_station_hour: Dict, corridors=['RED', 'BLUE', 'GREEN'],
                      corridor_stations: Dict = None, baseline_headways: Dict = None,
                      base_demand_by_station_hour: Dict = None):
    """
    demand_by_station_hour: {station_id: {hour: passenger_count}}
    corridors: list of corridors to optimize
    corridor_stations: {corridor: [station_ids]}
    baseline_headways: {corridor: {station_id: {hour: headway_min}}} or {corridor: {hour: headway_min}}
    base_demand_by_station_hour: base demand without event
    """
    from gtfs.loader import get_station_route_map
    if corridor_stations is None:
        route_map = get_station_route_map()
        corridor_stations = {'RED': [], 'BLUE': [], 'GREEN': []}
        for sid, routes in route_map.items():
            for r in routes:
                if r in corridor_stations and sid not in corridor_stations[r]:
                    corridor_stations[r].append(sid)

    result = {}
    for corridor in corridors:
        stations = corridor_stations.get(corridor, [])
        corridor_result = {}
        
        for hour in range(5, 24):
            # Max demand across all stations in this corridor at this hour
            demands = [demand_by_station_hour.get(s, {}).get(hour, 0) for s in stations]
            max_demand = max(demands) if demands else 0
            
            base_demands = [base_demand_by_station_hour.get(s, {}).get(hour, 0) for s in stations] if base_demand_by_station_hour else []
            max_base_demand = max(base_demands) if base_demands else max_demand
            
            # Extract baseline headway for this corridor & hour
            base_hw = 6.0
            if baseline_headways and corridor in baseline_headways:
                c_hw = baseline_headways[corridor]
                if hour in c_hw:
                    base_hw = c_hw[hour]
                elif isinstance(c_hw, dict):
                    # Station-level dict: average across corridor stations
                    hw_vals = [c_hw[s][hour] for s in stations if s in c_hw and hour in c_hw[s]]
                    if hw_vals:
                        base_hw = float(np.mean(hw_vals))
            
            # 1. Compute station-level optimal headways across the corridor
            st_headways = []
            for s in stations:
                st_dem = demand_by_station_hour.get(s, {}).get(hour, 0)
                st_base = base_demand_by_station_hour.get(s, {}).get(hour, st_dem) if base_demand_by_station_hour else st_dem
                
                st_base_hw = base_hw
                if baseline_headways and corridor in baseline_headways and isinstance(baseline_headways[corridor], dict):
                    if s in baseline_headways[corridor] and hour in baseline_headways[corridor][s]:
                        st_base_hw = baseline_headways[corridor][s][hour]
                
                st_hw = optimal_headway(st_dem, baseline_headway=st_base_hw, baseline_demand=st_base)
                st_headways.append(st_hw)

            # 2. Corridor headway must satisfy the highest-surged station on the line
            corr_hw = optimal_headway(max_demand, baseline_headway=base_hw, baseline_demand=max_base_demand)
            hw = min(corr_hw, min(st_headways)) if st_headways else corr_hw
            tph = round(60 / hw, 1)
            
            corridor_result[hour] = {
                'headway_min': hw,
                'trains_per_hour': tph,
                'max_station_demand': round(max_demand),
                'fleet_trains': round(trains_needed(hw, corridor), 1),
                'baseline_headway_min': round(base_hw, 1),
                'fleet_constrained': False
            }
        
        result[corridor] = corridor_result
    
    # Pure demand-driven optimization without artificial fleet throttling
    return result

def _apply_fleet_constraint(schedule):
    """Deprecated: Fleet throttling removed to allow uncompromised headway optimization."""
    return schedule

