"""
models/train_attendance_model.py
--------------------------------
Generates synthetic historical event attendance data, trains a RandomForestRegressor
to predict the venue occupancy rate (0.1 to 1.0), evaluates feature importance,
renders a feature importance chart, and saves the trained model to models/attendance_rf.pkl.
"""

import os
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
DATA_FILE = DATA_DIR / "historical_attendance.csv"
MODEL_FILE = MODELS_DIR / "attendance_rf.pkl"
CHART_FILE = MODELS_DIR / "attendance_feature_importance.png"

EVENT_TYPE_ENCODING = {
    "Sports": 0,
    "Concert": 1,
    "Conference": 2,
    "Comedy": 3,
    "Exhibition": 4,
    "Cultural": 5,
    "Rally": 6,
    "Other": 7,
}

def generate_synthetic_data(num_samples: int = 1500) -> pd.DataFrame:
    np.random.seed(42)
    capacities = np.random.choice([3500, 8000, 12000, 20000, 25000, 30000, 40000, 55000], size=num_samples)
    
    event_types = np.random.choice(list(EVENT_TYPE_ENCODING.keys()), size=num_samples, 
                                  p=[0.25, 0.25, 0.15, 0.10, 0.10, 0.05, 0.05, 0.05])
    event_type_encoded = np.array([EVENT_TYPE_ENCODING[t] for t in event_types])
    
    is_weekend = np.random.binomial(1, 0.40, size=num_samples)
    
    # Interest hearts (viral events get up to 60k, niche get 2k-10k)
    user_interest_hearts = np.random.gamma(shape=3.0, scale=6000, size=num_samples).astype(int) + 1500
    user_interest_hearts = np.clip(user_interest_hearts, 1000, 65000)
    
    # Average ticket price
    ticket_price_avg = np.random.uniform(150, 4500, size=num_samples)
    # Rallies/Free events
    free_mask = (event_types == "Rally") | (np.random.rand(num_samples) < 0.05)
    ticket_price_avg[free_mask] = 0.0

    # True latent relationship for occupancy rate (0.08 to 0.85)
    # Turnout reflects realistic event attendance (30% to 65% for typical events)
    interest_signal = np.clip(user_interest_hearts / (capacities * 1.5), 0.05, 1.0)
    weekend_boost = is_weekend * 0.08
    type_bonus = np.where(event_types == "Sports", 0.08,
                 np.where(event_types == "Concert", 0.06,
                 np.where(event_types == "Rally", 0.10, -0.02)))
    price_friction = np.clip(ticket_price_avg / 4000.0, 0.0, 0.18)
    noise = np.random.normal(0, 0.03, size=num_samples)

    raw_occupancy = 0.12 + (0.35 * interest_signal) + weekend_boost + type_bonus - price_friction + noise
    occupancy_rate = np.clip(raw_occupancy, 0.08, 0.85)

    df = pd.DataFrame({
        "venue_capacity": capacities,
        "ticket_price_avg": np.round(ticket_price_avg, 2),
        "user_interest_hearts": user_interest_hearts,
        "is_weekend": is_weekend,
        "event_type_encoded": event_type_encoded,
        "event_type": event_types,
        "occupancy_rate": np.round(occupancy_rate, 4)
    })
    return df

def train_model():
    print("=" * 65)
    print("PHASE 2: TRAINING ATTENDANCE PREDICTOR MODEL (Random Forest)")
    print("=" * 65)

    if not DATA_FILE.exists():
        print(f"Generating synthetic attendance data -> {DATA_FILE}")
        df = generate_synthetic_data(1500)
        df.to_csv(DATA_FILE, index=False)
    else:
        print(f"Loading existing training dataset from {DATA_FILE}")
        df = pd.read_csv(DATA_FILE)

    features = [
        "venue_capacity",
        "ticket_price_avg",
        "user_interest_hearts",
        "is_weekend",
        "event_type_encoded"
    ]
    target = "occupancy_rate"

    X = df[features]
    y = df[target]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42)

    rf = RandomForestRegressor(
        n_estimators=150,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train, y_train)

    y_pred = rf.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    print(f"\nModel Performance on Test Set (20% holdout):")
    print(f"  - RMSE: {rmse:.4f}")
    print(f"  - R-squared (R²): {r2:.4f}")

    # Feature Importance
    importances = rf.feature_importances_
    indices = np.argsort(importances)[::-1]

    print("\nFeature Importance (Mean Decrease in Impurity):")
    for i in range(len(features)):
        feat = features[indices[i]]
        score = importances[indices[i]]
        print(f"  {i+1}. {feat:<24}: {score*100:6.2f}%")

    # Plot & Save Feature Importance
    plt.figure(figsize=(8, 4.5))
    plt.barh([features[i] for i in indices[::-1]], [importances[i] for i in indices[::-1]], color="#007ABB")
    plt.xlabel("Relative Importance")
    plt.title("Attendance Predictor - Feature Importance (Random Forest)")
    plt.tight_layout()
    plt.savefig(CHART_FILE, dpi=150)
    plt.close()
    print(f"\nSaved feature importance chart -> {CHART_FILE}")

    # Save model artifacts
    artifact = {
        "model": rf,
        "features": features,
        "event_type_encoding": EVENT_TYPE_ENCODING,
        "metrics": {"rmse": rmse, "r2": r2}
    }
    joblib.dump(artifact, MODEL_FILE)
    print(f"Saved trained model -> {MODEL_FILE}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    train_model()
