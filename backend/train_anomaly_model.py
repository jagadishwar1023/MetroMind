"""
Train the Anomaly Detection model for HMR.
Uses Isolation Forest on historical demand ratios (actual/expected).

Run AFTER train_model.py so that demand_model.pkl exists.

    python train_anomaly_model.py
"""
import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

DATA_PATH  = Path(__file__).parent / 'data' / 'historical_demand.csv'
MODEL_PATH = Path(__file__).parent / 'data' / 'anomaly_model.pkl'
DEMAND_MODEL_PATH = Path(__file__).parent / 'data' / 'demand_model.pkl'


def get_period(hour: int) -> str:
    if 6 <= hour <= 10:   return 'morning_peak'
    if 17 <= hour <= 21:  return 'evening_peak'
    if 11 <= hour <= 16:  return 'midday'
    return 'off_peak'


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build anomaly detection feature matrix from historical demand."""
    # Load demand model to compute expected counts
    expected_col = []
    try:
        demand_data = joblib.load(DEMAND_MODEL_PATH)
        model = demand_data['model']
        station_enc = demand_data['station_encoder']
        corridor_enc = {'RED': 0, 'BLUE': 1, 'GREEN': 2}

        for _, row in df.iterrows():
            X = np.array([[
                row['hour'], row['day_of_week'], row['is_weekend'], row['is_holiday'],
                station_enc.get(row['station_id'], 0),
                corridor_enc.get(row.get('corridor', 'RED'), 0),
                row.get('trains_per_hour', 6.0),
                row.get('nearby_it_density', 0.1),
                row.get('nearby_college_density', 0.1),
                row.get('weather_code', 0),
                row.get('temperature', 30.0),
            ]])
            expected_col.append(float(model.predict(X)[0]))
    except Exception:
        # Fallback: use rolling mean as expected
        expected_col = df['passenger_count'].rolling(window=7, min_periods=1).mean().tolist()

    df = df.copy()
    df['expected_count'] = expected_col
    df['ratio'] = df['passenger_count'] / df['expected_count'].clip(lower=1.0)
    df['deviation_pct'] = (df['passenger_count'] - df['expected_count']) / df['expected_count'].clip(lower=1.0) * 100
    df['is_peak_hour'] = df['hour'].apply(lambda h: 1 if (6 <= h <= 10 or 17 <= h <= 21) else 0)
    df['period_encoded'] = df['hour'].apply(get_period).map(
        {'morning_peak': 0, 'midday': 1, 'evening_peak': 2, 'off_peak': 3}
    )
    return df


ANOMALY_FEATURES = [
    'ratio', 'deviation_pct', 'weather_code', 'temperature',
    'is_peak_hour', 'hour', 'day_of_week', 'period_encoded'
]


def train():
    print('Loading data...')
    df = pd.read_csv(DATA_PATH)
    print(f'  {len(df):,} rows')

    print('Computing expected demands and building feature matrix...')
    df = build_features(df)

    X = df[ANOMALY_FEATURES].fillna(0).values

    # Normalise
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print('Training Isolation Forest (contamination=0.05)...')
    iso = IsolationForest(
        n_estimators=200,
        contamination=0.05,   # ~5% of historical data treated as anomalies
        random_state=42,
        n_jobs=-1
    )
    iso.fit(X_scaled)

    # Quick self-evaluation
    labels = iso.predict(X_scaled)
    anomaly_count = (labels == -1).sum()
    print(f'  Flagged {anomaly_count} anomalies ({anomaly_count/len(df)*100:.1f}%) in training set')
    print(f'  Score range: [{iso.score_samples(X_scaled).min():.3f}, {iso.score_samples(X_scaled).max():.3f}]')

    payload = {
        'model': iso,
        'scaler': scaler,
        'features': ANOMALY_FEATURES,
        'threshold_scores': {
            'low':      -0.1,
            'medium':   -0.2,
            'high':     -0.35,
            'critical': -0.5,
        }
    }
    joblib.dump(payload, MODEL_PATH)
    print(f'\nAnomaly model saved to {MODEL_PATH}')


if __name__ == '__main__':
    train()
