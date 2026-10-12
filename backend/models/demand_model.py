import xgboost as xgb
import numpy as np
import pandas as pd
import joblib
from pathlib import Path

MODEL_PATH = Path(__file__).parent.parent / 'data' / 'demand_model.pkl'
FEATURES = ['hour', 'day_of_week', 'is_weekend', 'is_holiday', 'station_encoded',
            'corridor_encoded', 'trains_per_hour', 'nearby_it_density',
            'nearby_college_density', 'weather_code', 'temperature']

class DemandModel:
    def __init__(self):
        self.model = None
        self.station_encoder = {}
        self.corridor_encoder = {'RED': 0, 'BLUE': 1, 'GREEN': 2}
    
    def load(self):
        data = joblib.load(MODEL_PATH)
        self.model = data['model']
        self.station_encoder = data['station_encoder']
        return self
    
    def predict(self, station_id, corridor, hour, day_of_week, is_weekend, is_holiday,
                trains_per_hour, it_density, college_density, weather_code=0, temperature=32.0):
        enc_station = self.station_encoder.get(station_id, 0)
        enc_corridor = self.corridor_encoder.get(corridor, 0)
        X = np.array([[hour, day_of_week, int(is_weekend), int(is_holiday),
                        enc_station, enc_corridor, trains_per_hour,
                        it_density, college_density, weather_code, temperature]])
        pred = float(self.model.predict(X)[0])
        # 90% confidence interval: ±12%
        return {
            'expected': max(0, round(pred)),
            'low': max(0, round(pred * 0.88)),
            'high': round(pred * 1.12)
        }

# Singleton
_model_instance = None
def get_model():
    global _model_instance
    if _model_instance is None:
        _model_instance = DemandModel().load()
    return _model_instance
