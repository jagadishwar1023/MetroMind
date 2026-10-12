"""
anomaly_detector.py
───────────────────
Anomaly-detection engine for HMR (Hyderabad Metro Rail) passenger demand.

Two detection modes
───────────────────
1. **IsolationForest** (sklearn) – used when a trained model artefact is
   available at ``backend/data/anomaly_model.pkl``.
2. **Statistical z-score fallback** – when no model artefact exists the
   detector falls back to a simple absolute-deviation threshold so that the
   service never crashes on a cold start.

Severity scale
──────────────
| Deviation from expected |  Severity  | Recommended action       |
|-------------------------|------------|--------------------------|
| < 20 %                  | normal     | monitor                  |
| 20 – 40 %               | low        | monitor / alert           |
| 40 – 70 %               | medium     | alert_operations          |
| 70 – 120 %              | high       | deploy_extra_trains       |
| > 120 %                 | critical   | emergency_response        |
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

# Absolute path to the persisted model artefact
MODEL_PATH = Path(__file__).parent.parent / "data" / "anomaly_model.pkl"

# Features used during training / inference
_FEATURE_COLS = [
    "ratio",
    "weather_code",
    "temperature",
    "is_peak_hour",
    "hour",
    "day_of_week",
]

# Severity thresholds (absolute deviation %)
_SEVERITY_THRESHOLDS = {
    "critical": 120.0,
    "high": 70.0,
    "medium": 40.0,
    "low": 20.0,
}

_ACTION_MAP = {
    "critical": "emergency_response",
    "high": "deploy_extra_trains",
    "medium": "alert_operations",
    "low": "monitor",
    "normal": "monitor",
}


# ─────────────────────────────────────────────────────────────────────────────
# TypedDict for input features
# ─────────────────────────────────────────────────────────────────────────────

class AnomalyFeatures(TypedDict):
    """Typed input contract for a single station-hour observation."""

    station_id: str
    corridor: str
    hour: int
    day_of_week: int
    passenger_count: int      # Observed count
    expected_count: int       # Model-predicted count
    ratio: float              # passenger_count / expected_count
    weather_code: int
    temperature: float
    is_peak_hour: int         # 1 if peak hour, 0 otherwise


# ─────────────────────────────────────────────────────────────────────────────
# Alert dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AnomalyAlert:
    """Structured alert emitted when an anomaly is detected."""

    station_id: str
    station_name: str
    corridor: str
    hour: int
    severity: str                   # 'normal' | 'low' | 'medium' | 'high' | 'critical'
    deviation_pct: float            # signed percentage; positive = overcrowding
    alert_message: str
    recommended_action: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    def to_dict(self) -> Dict:
        return {
            "station_id": self.station_id,
            "station_name": self.station_name,
            "corridor": self.corridor,
            "hour": self.hour,
            "severity": self.severity,
            "deviation_pct": round(self.deviation_pct, 2),
            "alert_message": self.alert_message,
            "recommended_action": self.recommended_action,
            "timestamp": self.timestamp.isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def _classify_severity(deviation_pct: float) -> str:
    """Map an absolute deviation percentage to a severity label."""
    abs_dev = abs(deviation_pct)
    if abs_dev >= _SEVERITY_THRESHOLDS["critical"]:
        return "critical"
    if abs_dev >= _SEVERITY_THRESHOLDS["high"]:
        return "high"
    if abs_dev >= _SEVERITY_THRESHOLDS["medium"]:
        return "medium"
    if abs_dev >= _SEVERITY_THRESHOLDS["low"]:
        return "low"
    return "normal"


def _build_alert_message(
    station_id: str,
    corridor: str,
    hour: int,
    deviation_pct: float,
    severity: str,
) -> str:
    direction = "overcrowding" if deviation_pct > 0 else "under-utilisation"
    return (
        f"[{severity.upper()}] Station {station_id} ({corridor} line) at "
        f"{hour:02d}:00 – {direction} detected. "
        f"Observed demand deviates {deviation_pct:+.1f}% from forecast."
    )


def _is_peak_hour(hour: int) -> int:
    return int(hour in range(6, 10) or hour in range(17, 21))


# ─────────────────────────────────────────────────────────────────────────────
# Core detector class
# ─────────────────────────────────────────────────────────────────────────────

class AnomalyDetector:
    """
    Detects anomalous passenger counts using IsolationForest.

    Falls back to a statistical deviation threshold if no trained model
    artefact is present (cold-start safe).

    Parameters
    ----------
    contamination : float
        Expected proportion of anomalies in training data.  Passed directly
        to ``IsolationForest``. Default 0.05.
    n_estimators : int
        Number of base estimators in the ensemble. Default 100.
    """

    MODEL_PATH = MODEL_PATH

    def __init__(self, contamination: float = 0.05, n_estimators: int = 100) -> None:
        self.contamination = contamination
        self.n_estimators = n_estimators
        self._model: Optional[IsolationForest] = None
        self._fitted: bool = False

    # ── Training ──────────────────────────────────────────────────────────────

    def fit(self, historical_df: pd.DataFrame) -> "AnomalyDetector":
        """
        Train the IsolationForest on historical station-hour data.

        Parameters
        ----------
        historical_df : pd.DataFrame
            Must contain columns matching ``_FEATURE_COLS``:
            ratio, weather_code, temperature, is_peak_hour, hour, day_of_week.

        Returns
        -------
        self
        """
        missing = set(_FEATURE_COLS) - set(historical_df.columns)
        if missing:
            raise ValueError(f"historical_df missing columns: {missing}")

        X = historical_df[_FEATURE_COLS].values

        self._model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X)
        self._fitted = True

        # Persist the model artefact
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self._model,
                "contamination": self.contamination,
                "n_estimators": self.n_estimators,
            },
            MODEL_PATH,
        )
        logger.info("AnomalyDetector: model saved to %s", MODEL_PATH)
        return self

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(self) -> "AnomalyDetector":
        """
        Load a previously persisted IsolationForest from ``MODEL_PATH``.

        Returns
        -------
        self
        """
        if not MODEL_PATH.exists():
            logger.warning(
                "AnomalyDetector: no model artefact found at %s. "
                "Falling back to z-score detection.",
                MODEL_PATH,
            )
            return self

        data = joblib.load(MODEL_PATH)
        self._model = data.get("model", data)
        self._scaler = data.get("scaler")
        self._features = data.get("features", _FEATURE_COLS)
        self._fitted = True
        logger.info("AnomalyDetector: loaded model from %s", MODEL_PATH)
        return self

    # ── Inference ─────────────────────────────────────────────────────────────

    def detect(
        self,
        station_id: str,
        corridor: str,
        hour: int,
        day_of_week: int,
        observed_count: int,
        expected_count: int,
        weather_code: int = 0,
        temperature: float = 32.0,
    ) -> Dict:
        """
        Detect whether a single observation is anomalous.
        """
        # ── Compute ratio & deviation ───────────────────────────────────────
        safe_expected = max(expected_count, 1)
        ratio = observed_count / safe_expected
        deviation_pct = (observed_count - expected_count) / safe_expected * 100.0

        severity = _classify_severity(deviation_pct)
        is_anomaly = severity != "normal"

        # ── IsolationForest score (if model fitted) ─────────────────────────
        if self._fitted and self._model is not None:
            n_in = getattr(self._model, "n_features_in_", 6)
            if n_in == 8:
                # 8-feature format from train_anomaly_model.py
                period_encoded = 0 if (6 <= hour <= 10) else (2 if 17 <= hour <= 21 else (1 if 11 <= hour <= 16 else 3))
                feature_vec = np.array([[
                    ratio,
                    deviation_pct,
                    weather_code,
                    temperature,
                    _is_peak_hour(hour),
                    hour,
                    day_of_week,
                    period_encoded
                ]])
            else:
                feature_vec = np.array([[
                    ratio,
                    weather_code,
                    temperature,
                    _is_peak_hour(hour),
                    hour,
                    day_of_week,
                ]])

            if hasattr(self, "_scaler") and self._scaler is not None:
                try:
                    feature_vec = self._scaler.transform(feature_vec)
                except Exception:
                    pass

            raw_score = float(self._model.score_samples(feature_vec)[0])
            anomaly_score = -raw_score  # positive, higher = more anomalous
            model_prediction = self._model.predict(feature_vec)[0]  # +1 normal, -1 anomaly
            is_anomaly = model_prediction == -1 or is_anomaly
        else:
            # Fallback: use deviation_pct as proxy score
            anomaly_score = abs(deviation_pct)

        alert_message = _build_alert_message(
            station_id, corridor, hour, deviation_pct, severity
        )

        return {
            "is_anomaly": bool(is_anomaly),
            "anomaly_score": float(round(anomaly_score, 4)),
            "severity": str(severity),
            "deviation_pct": float(round(deviation_pct, 2)),
            "alert_message": alert_message,
            "recommended_action": _ACTION_MAP[severity],
        }

    # ── Batch detection ───────────────────────────────────────────────────────

    def detect_network_anomalies(
        self,
        station_hour_counts: Dict[str, Dict[int, int]],
        expected_counts: Dict[str, Dict[int, int]],
        corridor_map: Optional[Dict[str, str]] = None,
        day_of_week: int = 0,
        weather_code: int = 0,
        temperature: float = 32.0,
    ) -> List[Dict]:
        """
        Run anomaly detection across all stations and hours in the network.

        Parameters
        ----------
        station_hour_counts : dict
            ``{station_id: {hour: observed_count}}``.
        expected_counts : dict
            ``{station_id: {hour: expected_count}}``.
        corridor_map : dict, optional
            ``{station_id: corridor_label}``. If None, corridor is 'UNKNOWN'.
        day_of_week : int
        weather_code : int
        temperature : float

        Returns
        -------
        list[dict]
            All detection results; anomalies are flagged by ``is_anomaly=True``.
        """
        corridor_map = corridor_map or {}
        results: List[Dict] = []

        for station_id, hour_counts in station_hour_counts.items():
            corridor = corridor_map.get(station_id, "UNKNOWN")
            for hour, observed in hour_counts.items():
                expected = expected_counts.get(station_id, {}).get(hour, observed)
                result = self.detect(
                    station_id=station_id,
                    corridor=corridor,
                    hour=hour,
                    day_of_week=day_of_week,
                    observed_count=observed,
                    expected_count=expected,
                    weather_code=weather_code,
                    temperature=temperature,
                )
                result["station_id"] = station_id
                result["corridor"] = corridor
                result["hour"] = hour
                results.append(result)

        return results


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_anomaly_report(alerts: List[AnomalyAlert]) -> Dict:
    """
    Aggregate a list of ``AnomalyAlert`` instances into a structured summary.

    Parameters
    ----------
    alerts : list[AnomalyAlert]

    Returns
    -------
    dict
        Keys: total_alerts, by_severity (grouped lists), critical_stations,
        generated_at (ISO timestamp).
    """
    severity_groups: Dict[str, List[Dict]] = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
        "normal": [],
    }

    for alert in alerts:
        severity_groups.setdefault(alert.severity, []).append(alert.to_dict())

    critical_stations = [
        a["station_id"] for a in severity_groups["critical"]
    ]

    return {
        "total_alerts": len(alerts),
        "by_severity": severity_groups,
        "critical_stations": critical_stations,
        "summary": {
            sev: len(items) for sev, items in severity_groups.items() if items
        },
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

_detector_instance: Optional[AnomalyDetector] = None


def get_detector() -> AnomalyDetector:
    """
    Return the module-level AnomalyDetector singleton.

    Attempts to load a persisted model from ``MODEL_PATH``.  If the artefact
    does not exist, returns an unfitted detector that operates in statistical
    fallback mode (no crash on cold start).
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = AnomalyDetector().load()
    return _detector_instance
