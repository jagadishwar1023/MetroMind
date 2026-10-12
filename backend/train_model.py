import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

DATA_PATH = Path(__file__).parent / 'data' / 'historical_demand.csv'
MODEL_PATH = Path(__file__).parent / 'data' / 'demand_model.pkl'

def train():
    print('Loading data...')
    df = pd.read_csv(DATA_PATH)
    
    # Encode categoricals
    station_encoder = {sid: i for i, sid in enumerate(df['station_id'].unique())}
    corridor_encoder = {'RED': 0, 'BLUE': 1, 'GREEN': 2}
    
    df['station_encoded'] = df['station_id'].map(station_encoder)
    df['corridor_encoded'] = df['corridor'].map(corridor_encoder).fillna(0)
    
    features = ['hour', 'day_of_week', 'is_weekend', 'is_holiday', 'station_encoded',
                'corridor_encoded', 'trains_per_hour', 'nearby_it_density',
                'nearby_college_density', 'weather_code', 'temperature']
    target = 'passenger_count'
    
    X = df[features].values
    y = df[target].values
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
    
    print('Training XGBoost model...')
    model = xgb.XGBRegressor(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        n_jobs=-1, objective='reg:squarederror'
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=100)
    
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    print(f'\nTest MAE: {mae:.0f} passengers | R²: {r2:.4f}')
    
    joblib.dump({'model': model, 'station_encoder': station_encoder, 'corridor_encoder': corridor_encoder}, MODEL_PATH)
    print(f'Model saved to {MODEL_PATH}')

if __name__ == '__main__':
    train()
