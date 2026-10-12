"""
Train the Directional Demand Model for HMR.
Augments historical_demand.csv with directional inbound/outbound splits
and fits separate XGBoost regressors for each direction.

Run with:
    python train_directional_model.py
"""
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

DATA_PATH = Path(__file__).parent / 'data' / 'historical_demand.csv'
MODEL_PATH = Path(__file__).parent / 'data' / 'directional_demand_model.pkl'

# ── Direction split rules ─────────────────────────────────────────────────────
# Inbound fraction by corridor and time-of-day window
# "Inbound" = toward major IT corridors / city centre
DIRECTION_RULES = {
    'RED': {
        'morning_peak': (0.72, 0.28),   # 06-10h: heavy inbound toward LBN/AME from suburbs
        'midday':       (0.50, 0.50),
        'evening_peak': (0.32, 0.68),   # 17-21h: reverse commute
        'off_peak':     (0.50, 0.50),
    },
    'BLUE': {
        'morning_peak': (0.30, 0.70),   # 06-10h: toward HITEC City / Raidurg (Outbound NAG->RDG)
        'midday':       (0.50, 0.50),
        'evening_peak': (0.70, 0.30),   # 16-21h: leaving HITEC City / Raidurg (Inbound RDG->NAG)
        'off_peak':     (0.50, 0.50),
    },
    'GREEN': {
        'morning_peak': (0.55, 0.45),
        'midday':       (0.50, 0.50),
        'evening_peak': (0.45, 0.55),
        'off_peak':     (0.50, 0.50),
    },
}

def get_period(hour: int) -> str:
    if 6 <= hour <= 10:
        return 'morning_peak'
    elif 11 <= hour <= 15:
        return 'midday'
    elif 16 <= hour <= 21:
        return 'evening_peak'
    else:
        return 'off_peak'

def augment_with_directions(df: pd.DataFrame) -> pd.DataFrame:
    """Add inbound/outbound columns based on direction rules."""
    inbound_vals, outbound_vals = [], []
    for _, row in df.iterrows():
        corridor = row.get('corridor', 'RED')
        hour = int(row.get('hour', 8))
        total = float(row.get('passenger_count', 0))
        period = get_period(hour)
        rules = DIRECTION_RULES.get(corridor, DIRECTION_RULES['RED'])
        in_frac, out_frac = rules.get(period, (0.5, 0.5))
        # Add ±5% noise to make the model generalise
        noise = np.random.uniform(-0.05, 0.05)
        in_frac_noisy = max(0.1, min(0.9, in_frac + noise))
        out_frac_noisy = 1.0 - in_frac_noisy
        inbound_vals.append(round(total * in_frac_noisy))
        outbound_vals.append(round(total * out_frac_noisy))
    df = df.copy()
    df['inbound_count'] = inbound_vals
    df['outbound_count'] = outbound_vals
    return df


def train():
    print('Loading historical demand data...')
    df = pd.read_csv(DATA_PATH)
    print(f'  {len(df):,} rows loaded.')

    # Encode categoricals
    station_encoder = {sid: i for i, sid in enumerate(df['station_id'].unique())}
    corridor_encoder = {'RED': 0, 'BLUE': 1, 'GREEN': 2}

    df['station_encoded'] = df['station_id'].map(station_encoder)
    df['corridor_encoded'] = df['corridor'].map(corridor_encoder).fillna(0)
    df['period_encoded'] = df['hour'].apply(get_period).map(
        {'morning_peak': 0, 'midday': 1, 'evening_peak': 2, 'off_peak': 3}
    )

    # Augment with directional splits
    print('Augmenting dataset with directional splits...')
    df = augment_with_directions(df)

    FEATURES = [
        'hour', 'day_of_week', 'is_weekend', 'is_holiday',
        'station_encoded', 'corridor_encoded', 'period_encoded',
        'trains_per_hour', 'nearby_it_density', 'nearby_college_density',
        'weather_code', 'temperature'
    ]

    X = df[FEATURES].values
    y_inbound = df['inbound_count'].values
    y_outbound = df['outbound_count'].values

    X_tr, X_te, yi_tr, yi_te, yo_tr, yo_te = train_test_split(
        X, y_inbound, y_outbound, test_size=0.15, random_state=42
    )

    xgb_params = dict(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        n_jobs=-1, objective='reg:squarederror'
    )

    print('Training inbound model...')
    model_inbound = xgb.XGBRegressor(**xgb_params)
    model_inbound.fit(X_tr, yi_tr, eval_set=[(X_te, yi_te)], verbose=100)
    mae_in = mean_absolute_error(yi_te, model_inbound.predict(X_te))
    r2_in = r2_score(yi_te, model_inbound.predict(X_te))
    print(f'  Inbound  MAE={mae_in:.0f} | R²={r2_in:.4f}')

    print('Training outbound model...')
    model_outbound = xgb.XGBRegressor(**xgb_params)
    model_outbound.fit(X_tr, yo_tr, eval_set=[(X_te, yo_te)], verbose=100)
    mae_out = mean_absolute_error(yo_te, model_outbound.predict(X_te))
    r2_out = r2_score(yo_te, model_outbound.predict(X_te))
    print(f'  Outbound MAE={mae_out:.0f} | R²={r2_out:.4f}')

    payload = {
        'model_inbound': model_inbound,
        'model_outbound': model_outbound,
        'station_encoder': station_encoder,
        'corridor_encoder': corridor_encoder,
        'features': FEATURES,
        'direction_rules': DIRECTION_RULES,
    }
    joblib.dump(payload, MODEL_PATH)
    print(f'\nDirectional model saved to {MODEL_PATH}')


if __name__ == '__main__':
    train()
