"""
spatial_temporal.py
───────────────────
Spatial-temporal cross-station feature engineering for HMR demand modelling.

Design philosophy
─────────────────
A full Spatial-Temporal Graph Neural Network (ST-GNN) would require PyTorch
Geometric (PyG) and heavy GPU infrastructure.  Instead, this module uses a
*LightGBM-style lagged-feature* approach that is mathematically equivalent for
the prediction use-case:

  1. For each station s at hour h, we look *upstream* in the corridor graph
     (BFS up to 3 hops) and retrieve demand observations from those upstream
     stations at earlier hours (h − travel_time_in_hours).

  2. The resulting "upstream load" features mimic the GNN message-passing step
     but are computed in plain Python/NumPy — no GPU required.

  3. A "passenger wave propagation" helper shifts demand downstream in time so
     that downstream stations implicitly inherit upstream crowding signals.

Adjacency graph
───────────────
Each station entry maps to a dict of ``{neighbor_station_id: travel_minutes}``.
Only *downstream* neighbours are stored (direction of increasing index in the
corridor order).  Upstream travel is inferred by reversing the graph.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Station adjacency graph
# Format: {station_id: {neighbor_id: travel_minutes}}
# Edges represent *downstream* direction (toward line terminus).
# ─────────────────────────────────────────────────────────────────────────────

STATION_ADJACENCY: Dict[str, Dict[str, int]] = {
    # ── RED LINE (Miyapur → LB Nagar) ────────────────────────────────────────
    "MYP": {"BKH": 3},
    "BKH": {"JNT": 3},
    "JNT": {"KUK": 3},
    "KUK": {"KUP": 3},
    "KUP": {"KLG": 3},
    "KLG": {"BOW": 3},
    "BOW": {"CHK": 3},
    "CHK": {"CHN": 3},
    "CHN": {"AME": 3},
    "AME": {"NAR": 3, "MGB": 3},   # AME is interchange with GREEN & BLUE
    "NAR": {"MGB": 3},
    "MGB": {"ASF": 3},
    "ASF": {"DAR": 3},
    "DAR": {"NSK": 3},
    "NSK": {"UPL": 3},
    "UPL": {"VRD": 3},
    "VRD": {"MDN": 3},
    "MDN": {"KPH": 3},
    "KPH": {"ADI": 3},
    "ADI": {"UCL": 3},
    "UCL": {"LBN": 3},
    "LBN": {},   # terminus

    # ── BLUE LINE (Nagole → Raidurg) ─────────────────────────────────────────
    "NAG": {"NGP": 3},
    "NGP": {"MET": 3},
    "MET": {"LBB": 3},
    "LBB": {"UAH": 3},
    "UAH": {"KMD": 3},
    "KMD": {"MUS": 3},
    "MUS": {"AME": 3},   # AME shared with RED
    # AME already defined above; BLUE continues from AME
    "AER": {"KHR": 3},
    "KHR": {"IRU": 3},
    "IRU": {"RTC": 3},
    "RTC": {"SBN": 3},
    "SBN": {"MAD": 3},
    "MAD": {"PED": 3},
    "PED": {"DGC": 3},
    "DGC": {"JCP": 3},
    "JCP": {"YUG": 3},
    "YUG": {"RDG": 3},
    "RDG": {},   # terminus

    # ── GREEN LINE (JBS → MGBS) ───────────────────────────────────────────────
    "JBS": {"PAR": 4},
    "PAR": {"GAB": 4},
    "GAB": {"MGB": 4},
    # MGB already defined above (RED/BLUE interchange)
}

# Corridor membership: station_id → corridor label
# Used to restrict BFS to within-corridor searches.
_CORRIDOR_STATIONS: Dict[str, str] = {
    **{s: "RED" for s in [
        "MYP", "BKH", "JNT", "KUK", "KUP", "KLG", "BOW", "CHK", "CHN",
        "AME", "NAR", "MGB", "ASF", "DAR", "NSK", "UPL", "VRD", "MDN",
        "KPH", "ADI", "UCL", "LBN",
    ]},
    **{s: "BLUE" for s in [
        "NAG", "NGP", "MET", "LBB", "UAH", "KMD", "MUS", "AME",
        "AER", "KHR", "IRU", "RTC", "SBN", "MAD", "PED", "DGC",
        "JCP", "YUG", "RDG",
    ]},
    **{s: "GREEN" for s in ["JBS", "PAR", "GAB", "MGB"]},
}


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass for enriched per-station/hour features
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CrossStationFeatures:
    """
    Spatial-temporal features derived from upstream / downstream station loads.

    Attributes
    ----------
    station_id : str
    hour : int
        Hour of day (0–23) for which features were computed.
    upstream_load_30min : float
        Average demand observed at upstream stations ~30 min ago
        (i.e. at ``hour - 0.5`` adjusted for travel time).
    upstream_load_45min : float
        Same as above for ~45 min lag.
    downstream_pressure : float
        Estimated load heading toward downstream neighbours in the current hour.
    local_demand : float
        Observed / forecast demand at this station at this hour.
    propagated_wave_demand : float
        Demand adjusted by the upstream passenger wave (smoothed).
    """

    station_id: str
    hour: int
    upstream_load_30min: float
    upstream_load_45min: float
    downstream_pressure: float
    local_demand: float
    propagated_wave_demand: float


# ─────────────────────────────────────────────────────────────────────────────
# Spatial-Temporal Feature Extractor
# ─────────────────────────────────────────────────────────────────────────────

class SpatialTemporalFeatureExtractor:
    """
    Computes cross-station lagged features for demand enrichment.

    The extractor works with a *demand_history* dict that stores observed or
    forecast passenger counts per station per hour:

        demand_history = {station_id: {hour: count}}

    All BFS traversals are bounded to ``max_hops`` to keep latency low.
    """

    def get_upstream_stations(
        self,
        station_id: str,
        corridor: str,
        max_hops: int = 3,
    ) -> List[Tuple[str, int]]:
        """
        BFS over the *reversed* adjacency graph to find upstream stations.

        Parameters
        ----------
        station_id : str
            Source station.
        corridor : str
            Restrict search to this corridor label.
        max_hops : int
            Maximum number of graph hops (edges) to traverse. Default 3.

        Returns
        -------
        list[tuple[str, int]]
            ``[(upstream_station_id, cumulative_travel_minutes), ...]``
            sorted by increasing travel time.
        """
        # Build reverse adjacency for the given corridor
        reverse_adj: Dict[str, Dict[str, int]] = {}
        for src, neighbours in STATION_ADJACENCY.items():
            if _CORRIDOR_STATIONS.get(src, "") != corridor and corridor not in ("", "ALL"):
                continue
            for dst, mins in neighbours.items():
                if _CORRIDOR_STATIONS.get(dst, "") != corridor and corridor not in ("", "ALL"):
                    continue
                reverse_adj.setdefault(dst, {})[src] = mins

        # BFS
        visited: Set[str] = {station_id}
        queue: deque[Tuple[str, int, int]] = deque([(station_id, 0, 0)])  # (node, depth, cum_mins)
        upstream: List[Tuple[str, int]] = []

        while queue:
            current, depth, cum_mins = queue.popleft()
            if depth >= max_hops:
                continue
            for neighbour, travel_mins in reverse_adj.get(current, {}).items():
                if neighbour not in visited:
                    visited.add(neighbour)
                    total_mins = cum_mins + travel_mins
                    upstream.append((neighbour, total_mins))
                    queue.append((neighbour, depth + 1, total_mins))

        return sorted(upstream, key=lambda x: x[1])

    def extract_upstream_features(
        self,
        station_id: str,
        hour: int,
        corridor: str,
        demand_history: Dict[str, Dict[int, float]],
    ) -> Dict[str, float]:
        """
        Extract lagged upstream demand features for a station-hour pair.

        Upstream stations within 30 and 45 minutes of travel time contribute
        to the lagged features.  Demand is attributed to the hour from which
        passengers departed (i.e. ``hour - travel_time_hours``).

        Parameters
        ----------
        station_id : str
        hour : int
            Current hour (0–23).
        corridor : str
        demand_history : dict
            ``{station_id: {hour: count}}``.

        Returns
        -------
        dict
            upstream_30min_load  – avg demand from stations ≤30 min upstream
            upstream_45min_load  – avg demand from stations ≤45 min upstream
            downstream_pressure  – estimated outgoing load from this station
        """
        upstream_stations = self.get_upstream_stations(station_id, corridor, max_hops=3)

        loads_30: List[float] = []
        loads_45: List[float] = []

        for up_station, travel_mins in upstream_stations:
            # Which hour were these passengers boarding upstream?
            departure_hour = max(0, hour - round(travel_mins / 60))
            station_history = demand_history.get(up_station, {})
            load = float(station_history.get(departure_hour, 0.0))

            if travel_mins <= 30:
                loads_30.append(load)
            if travel_mins <= 45:
                loads_45.append(load)

        upstream_30 = float(np.mean(loads_30)) if loads_30 else 0.0
        upstream_45 = float(np.mean(loads_45)) if loads_45 else 0.0

        # Downstream pressure: average demand at immediate downstream neighbours
        downstream_loads: List[float] = []
        for down_station in STATION_ADJACENCY.get(station_id, {}):
            if _CORRIDOR_STATIONS.get(down_station) == corridor:
                down_history = demand_history.get(down_station, {})
                downstream_loads.append(float(down_history.get(hour, 0.0)))

        downstream_pressure = float(np.mean(downstream_loads)) if downstream_loads else 0.0

        return {
            "upstream_30min_load": round(upstream_30, 2),
            "upstream_45min_load": round(upstream_45, 2),
            "downstream_pressure": round(downstream_pressure, 2),
        }

    def compute_wave_propagation(
        self,
        demand_by_station_hour: Dict[str, Dict[int, float]],
        corridor: str,
    ) -> Dict[str, Dict[int, float]]:
        """
        Propagate passenger demand waves along the corridor.

        Each station's demand at hour ``h`` is supplemented by an attenuated
        contribution from upstream stations at earlier hours, modelling the
        physical movement of passengers through the network.

        Parameters
        ----------
        demand_by_station_hour : dict
            ``{station_id: {hour: count}}``.
        corridor : str
            Corridor to process ('RED', 'BLUE', or 'GREEN').

        Returns
        -------
        dict
            Augmented ``{station_id: {hour: propagated_count}}``.
        """
        augmented: Dict[str, Dict[int, float]] = {}

        # Deep copy original values
        for station, hour_map in demand_by_station_hour.items():
            augmented[station] = {h: float(v) for h, v in hour_map.items()}

        # Process downstream edges: propagate a fraction of upstream load
        for src, neighbours in STATION_ADJACENCY.items():
            if _CORRIDOR_STATIONS.get(src, "") != corridor:
                continue
            src_history = demand_by_station_hour.get(src, {})
            for dst, travel_mins in neighbours.items():
                if _CORRIDOR_STATIONS.get(dst, "") != corridor:
                    continue
                travel_hours = travel_mins / 60.0
                for hour in range(24):
                    arrival_hour = min(23, hour + int(round(travel_hours)))
                    propagated_load = float(src_history.get(hour, 0.0)) * 0.85
                    # Add wave contribution (85 % carry-over, 15 % exits)
                    augmented.setdefault(dst, {})
                    augmented[dst][arrival_hour] = (
                        augmented[dst].get(arrival_hour, 0.0) + propagated_load
                    )

        return augmented


# ─────────────────────────────────────────────────────────────────────────────
# Network enrichment function
# ─────────────────────────────────────────────────────────────────────────────

def enrich_demand_with_spatial_features(
    demand_by_station_hour: Dict[str, Dict[int, float]],
    route_map: Dict[str, Dict],
) -> Dict[str, Dict[int, CrossStationFeatures]]:
    """
    Enrich per-station demand estimates with cross-station spatial features.

    For each station and each hour that has a demand observation, this function
    computes upstream lagged features and downstream pressure, then blends the
    local demand with the propagated passenger wave to produce a more accurate
    ``propagated_wave_demand`` estimate.

    Parameters
    ----------
    demand_by_station_hour : dict
        ``{station_id: {hour: count}}``.
    route_map : dict
        ``{station_id: {corridor: str, ...}}``.
        Must contain at least a ``'corridor'`` key per station.

    Returns
    -------
    dict
        ``{station_id: {hour: CrossStationFeatures}}``.
    """
    extractor = SpatialTemporalFeatureExtractor()
    results: Dict[str, Dict[int, CrossStationFeatures]] = {}

    # Pre-compute wave-propagated demand for each corridor
    corridors = set(
        v.get("corridor", "RED").upper() for v in route_map.values()
    )
    propagated_by_corridor: Dict[str, Dict[str, Dict[int, float]]] = {}
    for corridor in corridors:
        propagated_by_corridor[corridor] = extractor.compute_wave_propagation(
            demand_by_station_hour, corridor
        )

    for station_id, hour_map in demand_by_station_hour.items():
        corridor = route_map.get(station_id, {}).get("corridor", "RED").upper()
        propagated_demand = propagated_by_corridor.get(corridor, {})

        results[station_id] = {}
        for hour, local_demand in hour_map.items():
            try:
                upstream_features = extractor.extract_upstream_features(
                    station_id=station_id,
                    hour=hour,
                    corridor=corridor,
                    demand_history=demand_by_station_hour,
                )
                wave_demand = float(
                    propagated_demand.get(station_id, {}).get(hour, local_demand)
                )

                results[station_id][hour] = CrossStationFeatures(
                    station_id=station_id,
                    hour=hour,
                    upstream_load_30min=upstream_features["upstream_30min_load"],
                    upstream_load_45min=upstream_features["upstream_45min_load"],
                    downstream_pressure=upstream_features["downstream_pressure"],
                    local_demand=float(local_demand),
                    propagated_wave_demand=round(wave_demand, 2),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Spatial feature extraction failed for station %s hour %d: %s",
                    station_id, hour, exc,
                )

    return results
