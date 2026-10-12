"""
directional_model.py
────────────────────
Extends the base XGBoost demand model with directional (inbound / outbound)
passenger-flow splitting for each HMR corridor.

Rationale – IT corridor asymmetry
──────────────────────────────────
Hyderabad's metro demand is heavily asymmetric during peak hours due to the
concentration of software-engineering campuses around HITEC City, Raidurg
(RDG), Madhapur, and Ameerpet (AME).

  • Morning peak (06:00–10:00):  ~70 % of passengers travel *toward* these
    tech-park clusters (inbound direction).  The flow reverses in the evening.
  • Evening peak (17:00–21:00):  ~65 % travel *away* from the tech-park
    cluster (outbound direction).
  • Off-peak hours maintain a near-balanced 50/50 split.

This asymmetry directly impacts:
  - Train deployment strategy (more coaches needed in the inbound direction
    during morning peak).
  - Platform crowd-management at interchange stations (Ameerpet).
  - Revenue attribution between inbound/outbound services.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Terminal direction labels per corridor
# Format: 'ORIGIN_TERMINAL -> DESTINATION_TERMINAL'
# ─────────────────────────────────────────────────────────────────────────────

INBOUND_TERMINAL: Dict[str, str] = {
    # LB Nagar → Miyapur (toward HITEC City / Ameerpet end)
    "RED": "LBN->MYP",
    # Raidurg → Nagole (toward Nagole residential end)
    "BLUE": "RDG->NAG",
    # Mahatma Gandhi Bus Station → Jubilee Bus Station
    "GREEN": "MGB->JBS",
}

OUTBOUND_TERMINAL: Dict[str, str] = {
    "RED": "MYP->LBN",
    "BLUE": "NAG->RDG",
    "GREEN": "JBS->MGB",
}

# ─────────────────────────────────────────────────────────────────────────────
# Direction split rules
# Key  : (corridor, peak_type)
# Value: (inbound_fraction, outbound_fraction)
#
# morning_peak : 06–10 h
# evening_peak : 17–21 h
# off_peak     : all other hours
# ─────────────────────────────────────────────────────────────────────────────

DIRECTION_SPLIT_RULES: Dict[Tuple[str, str], Tuple[float, float]] = {
    # RED corridor (LB Nagar ↔ Miyapur)
    # Inbound = toward IT hubs (HTC, RDG, AME)
    ("RED", "morning_peak"): (0.72, 0.28),
    ("RED", "evening_peak"): (0.35, 0.65),
    ("RED", "off_peak"):     (0.50, 0.50),

    # BLUE corridor (Nagole ↔ Raidurg)
    # Inbound = RDG->NAG (Raidurg to Nagole, heading away from IT corridor)
    # Outbound = NAG->RDG (Nagole to Raidurg, heading into IT corridor)
    # Morning: heavy commute into IT corridor (Outbound: NAG->RDG)
    # Evening: heavy commute leaving IT corridor (Inbound: RDG->NAG)
    ("BLUE", "morning_peak"): (0.28, 0.72),
    ("BLUE", "evening_peak"): (0.72, 0.28),
    ("BLUE", "off_peak"):     (0.50, 0.50),

    # GREEN corridor (JBS ↔ MGBS) – less IT-driven, more balanced
    ("GREEN", "morning_peak"): (0.55, 0.45),
    ("GREEN", "evening_peak"): (0.45, 0.55),
    ("GREEN", "off_peak"):     (0.50, 0.50),
}

# Hour boundaries for peak classification
_MORNING_PEAK_HOURS = range(6, 11)   # 06:00 – 10:59
_EVENING_PEAK_HOURS = range(16, 22)  # 16:00 – 21:59 (4 PM – 10 PM)


def _classify_peak(hour: int) -> str:
    """Return the peak classification string for a given hour (0–23)."""
    if hour in _MORNING_PEAK_HOURS:
        return "morning_peak"
    if hour in _EVENING_PEAK_HOURS:
        return "evening_peak"
    return "off_peak"


class DirectionalDemandModel:
    """
    Wraps the base XGBoost DemandModel to provide directional demand splits.

    Usage
    -----
    >>> from models.demand_model import get_model
    >>> from models.directional_model import DirectionalDemandModel
    >>> base = get_model()
    >>> ddm = DirectionalDemandModel()
    >>> result = ddm.predict_directional(
    ...     station_id='AME', corridor='RED', hour=8, day_of_week=1,
    ...     is_weekend=False, is_holiday=False, trains_per_hour=12,
    ...     it_density=0.9, college_density=0.3, base_model=base
    ... )
    """

    def get_split_fractions(
        self, corridor: str, hour: int
    ) -> Tuple[float, float, str]:
        """
        Return (inbound_fraction, outbound_fraction, peak_type) for a
        corridor / hour combination.

        Falls back to 50/50 split for unknown corridors.

        Parameters
        ----------
        corridor : str
            One of 'RED', 'BLUE', 'GREEN'.
        hour : int
            Hour of day in 24-h format (0–23).

        Returns
        -------
        Tuple[float, float, str]
            (inbound_fraction, outbound_fraction, peak_type)
        """
        peak_type = _classify_peak(hour)
        key = (corridor.upper(), peak_type)
        inbound_frac, outbound_frac = DIRECTION_SPLIT_RULES.get(key, (0.50, 0.50))
        return inbound_frac, outbound_frac, peak_type

    def predict_directional(
        self,
        station_id: str,
        corridor: str,
        hour: int,
        day_of_week: int,
        is_weekend: bool,
        is_holiday: bool,
        trains_per_hour: int,
        it_density: float,
        college_density: float,
        weather_code: int = 0,
        temperature: float = 32.0,
        base_model=None,
    ) -> Dict:
        """
        Predict total demand and split it into directional components.

        If *base_model* is supplied the total demand is obtained from the
        XGBoost model; otherwise a simple heuristic estimate is used (useful
        for testing without a trained model artefact).

        Parameters
        ----------
        station_id : str
            Station code, e.g. 'AME'.
        corridor : str
            'RED', 'BLUE', or 'GREEN'.
        hour : int
            Hour of day (0–23).
        day_of_week : int
            0 = Monday … 6 = Sunday.
        is_weekend : bool
        is_holiday : bool
        trains_per_hour : int
            Scheduled trains per hour at this station.
        it_density : float
            Nearby IT-office density score (0–1).
        college_density : float
            Nearby college density score (0–1).
        weather_code : int, optional
            Encoded weather condition (0 = clear). Default 0.
        temperature : float, optional
            Temperature in °C. Default 32.0.
        base_model : DemandModel, optional
            Fitted DemandModel instance from demand_model.py.

        Returns
        -------
        dict with keys:
            total            – int, total predicted passengers
            inbound          – int, passengers in inbound direction
            outbound         – int, passengers in outbound direction
            inbound_direction  – str, human-readable terminal label
            outbound_direction – str, human-readable terminal label
            inbound_fraction   – float
            outbound_fraction  – float
            peak_type          – 'morning_peak' | 'evening_peak' | 'off_peak'
        """
        corridor = corridor.upper()

        # ── 1. Obtain total demand ───────────────────────────────────────────
        if base_model is not None:
            prediction = base_model.predict(
                station_id=station_id,
                corridor=corridor,
                hour=hour,
                day_of_week=day_of_week,
                is_weekend=is_weekend,
                is_holiday=is_holiday,
                trains_per_hour=trains_per_hour,
                it_density=it_density,
                college_density=college_density,
                weather_code=weather_code,
                temperature=temperature,
            )
            total = int(prediction["expected"])
        else:
            # Heuristic fallback: base load scaled by time-of-day curve
            base_load = 300 + it_density * 400 + college_density * 200
            peak_multiplier = (
                1.8 if _classify_peak(hour) == "morning_peak"
                else 1.6 if _classify_peak(hour) == "evening_peak"
                else 1.0
            )
            weekend_factor = 0.65 if (is_weekend or is_holiday) else 1.0
            total = max(0, int(base_load * peak_multiplier * weekend_factor))
            logger.warning(
                "No base_model provided for station %s; using heuristic total=%d",
                station_id, total,
            )

        # ── 2. Apply directional split ───────────────────────────────────────
        inbound_frac, outbound_frac, peak_type = self.get_split_fractions(
            corridor, hour
        )

        inbound = int(round(total * inbound_frac))
        outbound = total - inbound  # ensure integer totals add up exactly

        return {
            "total": total,
            "inbound": inbound,
            "outbound": outbound,
            "inbound_direction": INBOUND_TERMINAL.get(corridor, "UNKNOWN"),
            "outbound_direction": OUTBOUND_TERMINAL.get(corridor, "UNKNOWN"),
            "inbound_fraction": inbound_frac,
            "outbound_fraction": outbound_frac,
            "peak_type": peak_type,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Network-level prediction helper
# ─────────────────────────────────────────────────────────────────────────────

def predict_network_directional_load(
    stops_df: pd.DataFrame,
    route_map: Dict[str, Dict],
    hour: int,
    day_of_week: int,
    base_model=None,
    weather_code: int = 0,
    temperature: float = 32.0,
) -> List[Dict]:
    """
    Compute directional demand for every station in *stops_df*.

    Parameters
    ----------
    stops_df : pd.DataFrame
        Must contain columns: station_id, corridor, trains_per_hour,
        nearby_it_density, nearby_college_density.
    route_map : dict
        Mapping of ``{station_id: {is_weekend: bool, is_holiday: bool, ...}}``.
        Provides per-station contextual flags.
    hour : int
        Hour of day (0–23) for which to run predictions.
    day_of_week : int
        0 = Monday … 6 = Sunday.
    base_model : DemandModel, optional
        Fitted DemandModel instance.  If None, heuristic mode is used.
    weather_code : int, optional
        Network-wide weather code. Default 0.
    temperature : float, optional
        Ambient temperature in °C. Default 32.0.

    Returns
    -------
    list[dict]
        One entry per station containing directional demand breakdown plus
        station metadata (station_id, corridor).
    """
    model = DirectionalDemandModel()
    results: List[Dict] = []

    required_cols = {"station_id", "corridor", "trains_per_hour",
                     "nearby_it_density", "nearby_college_density"}
    missing = required_cols - set(stops_df.columns)
    if missing:
        raise ValueError(f"stops_df is missing required columns: {missing}")

    is_weekend = day_of_week >= 5  # Saturday or Sunday

    for _, row in stops_df.iterrows():
        station_id = str(row["station_id"])
        corridor = str(row["corridor"]).upper()

        # Per-station overrides from route_map (e.g. special holiday flag)
        ctx = route_map.get(station_id, {})
        station_is_weekend = ctx.get("is_weekend", is_weekend)
        station_is_holiday = ctx.get("is_holiday", False)

        try:
            prediction = model.predict_directional(
                station_id=station_id,
                corridor=corridor,
                hour=hour,
                day_of_week=day_of_week,
                is_weekend=station_is_weekend,
                is_holiday=station_is_holiday,
                trains_per_hour=int(row["trains_per_hour"]),
                it_density=float(row["nearby_it_density"]),
                college_density=float(row["nearby_college_density"]),
                weather_code=weather_code,
                temperature=temperature,
                base_model=base_model,
            )
            prediction["station_id"] = station_id
            prediction["corridor"] = corridor
            results.append(prediction)

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Directional prediction failed for station %s: %s", station_id, exc
            )
            results.append({
                "station_id": station_id,
                "corridor": corridor,
                "error": str(exc),
            })

    return results
