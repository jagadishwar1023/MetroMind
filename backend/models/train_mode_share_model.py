"""
models/train_mode_share_model.py
--------------------------------
Generates realistic historical transit behavior data, trains a RandomForestRegressor
to predict Metro Mode Share (0.01 to 0.60), evaluates feature importance, renders
the feature importance chart, and saves the trained model to models/mode_share_rf.pkl.
"""

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
DATA_FILE = DATA_DIR / "historical_mode_share.csv"
MODEL_FILE = MODELS_DIR / "mode_share_rf.pkl"
CHART_FILE = MODELS_DIR / "mode_share_feature_importance.png"

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

    # 1. Distance to nearest metro station in km (0.2 km up to 8.0 km)
    distance_to_nearest_metro_km = np.random.exponential(scale=1.8, size=num_samples) + 0.2
    distance_to_nearest_metro_km = np.clip(distance_to_nearest_metro_km, 0.2, 8.5)

    # 2. Venue parking capacity ratio (parking spots / venue capacity, 0.02 to 0.45)
    venue_parking_capacity_ratio = np.random.uniform(0.02, 0.40, size=num_samples)

    # 3. Event end hour (11:00 AM to 23:30 PM, metro closes at 23:00 / 23:30)
    event_end_hour = np.random.choice([13, 17, 18, 19, 21, 22, 23], size=num_samples,
                                      p=[0.05, 0.10, 0.15, 0.15, 0.25, 0.20, 0.10])

    # 4. Event type
    event_types = np.random.choice(list(EVENT_TYPE_ENCODING.keys()), size=num_samples)
    event_type_encoded = np.array([EVENT_TYPE_ENCODING[t] for t in event_types])

    # Ground truth relationship modeling real-world transit behavior in Indian metros:
    # - In Hyderabad, metro mode share for major events typically ranges between 3% and 22%.
    # - Even adjacent to the stadium (e.g. Uppal), mode share is ~14-18% (due to bikes, autos, cabs, cars).
    # - Beyond walking distance (> 1.5 km), mode share drops steeply below 10%.
    
    dist_factor = np.exp(-0.75 * distance_to_nearest_metro_km)  # steep drop beyond walking distance
    parking_penalty = 0.05 * venue_parking_capacity_ratio       # lower parking -> slightly higher metro
    
    # Hour effect: events ending right at peak or closing hours
    hour_factor = np.where(event_end_hour >= 23, -0.03,
                  np.where(event_end_hour >= 21, 0.02, 0.0))

    type_factor = np.where(event_types == "Conference", 0.02,
                  np.where(event_types == "Sports", 0.02,
                  np.where(event_types == "Concert", 0.02,
                  np.where(event_types == "Rally", -0.04, 0.0))))

    noise = np.random.normal(0, 0.012, size=num_samples)

    raw_mode_share = 0.02 + (0.16 * dist_factor) - parking_penalty + hour_factor + type_factor + noise
    metro_mode_share_pct = np.clip(raw_mode_share, 0.02, 0.22)

    df = pd.DataFrame({
        "distance_to_nearest_metro_km": np.round(distance_to_nearest_metro_km, 2),
        "venue_parking_capacity_ratio": np.round(venue_parking_capacity_ratio, 3),
        "event_end_hour": event_end_hour,
        "event_type_encoded": event_type_encoded,
        "event_type": event_types,
        "metro_mode_share_pct": np.round(metro_mode_share_pct, 4)
    })
    return df

def train_model():
    print("=" * 65)
    print("PHASE 3: TRAINING METRO MODE SHARE MODEL (Random Forest)")
    print("=" * 65)

    if not DATA_FILE.exists():
        print(f"Generating synthetic mode share data -> {DATA_FILE}")
        df = generate_synthetic_data(1500)
        df.to_csv(DATA_FILE, index=False)
    else:
        print(f"Loading existing mode share dataset from {DATA_FILE}")
        df = pd.read_csv(DATA_FILE)

    features = [
        "distance_to_nearest_metro_km",
        "venue_parking_capacity_ratio",
        "event_end_hour",
        "event_type_encoded"
    ]
    target = "metro_mode_share_pct"

    X = df[features]
    y = df[target]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42)

    rf = RandomForestRegressor(
        n_estimators=150,
        max_depth=10,
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
        print(f"  {i+1}. {feat:<32}: {score*100:6.2f}%")

    # Plot & Save Feature Importance
    plt.figure(figsize=(8, 4.5))
    plt.barh([features[i] for i in indices[::-1]], [importances[i] for i in indices[::-1]], color="#009846")
    plt.xlabel("Relative Importance")
    plt.title("Metro Mode Share - Feature Importance (Random Forest)")
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
