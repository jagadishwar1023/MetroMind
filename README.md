# 🚇 MetroMind — Autonomous Metro Rail Frequency & Demand Optimization System

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/Frontend-React%2018%20%2B%20Vite-61DAFB?style=flat-square&logo=react)](https://reactjs.org)
[![TailwindCSS](https://img.shields.io/badge/Styling-TailwindCSS%203-38B2AC?style=flat-square&logo=tailwind-css)](https://tailwindcss.com)
[![Python](https://img.shields.io/badge/ML-Python%203.11%20%7C%20Scikit--Learn-3776AB?style=flat-square&logo=python)](https://python.org)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-success?style=flat-square)]()

**MetroMind** is an enterprise transit optimization platform built for **Hyderabad Metro Rail (HMR)**. It continuously balances train frequencies and headways across all three corridors (Red, Blue, Green) by synthesizing real-time verified city events (cricket matches, concerts, tech summits), live weather conditions, public holidays, and bidirectional commuter flow dynamics.

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                   MetroMind React 18 Dashboard                         │
│  Control Center  │  Network Map  │  Schedule View  │  Trends & Surges  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Axios REST API (Port 8000)
┌───────────────────────────────────▼────────────────────────────────────┐
│                      FastAPI Autonomous Backend                        │
│  /auto-optimize  /predict/directional  /events/live  /weather/live     │
└─────────┬─────────────────────────┬──────────────────────────┬─────────┘
          │                         │                          │
┌─────────▼─────────────┐ ┌─────────▼─────────────┐ ┌──────────▼─────────┐
│  Multi-Source Scraper │ │  ML Demand & Surge    │ │  Bidirectional     │
│  BMS / Insider / Govt │ │  Attendance & Share   │ │  Headway Engine    │
│  Live Open-Meteo      │ │  Random Forest Models │ │  Inbound/Outbound  │
└───────────────────────┘ └───────────────────────┘ └────────────────────┘
```

---

## ✨ Core Features

### 1. 🤖 AI AutoPilot Dashboard (`Control Center`)
- **Autonomous Headway Calibration**: Continuously ingests live city events, weather forecasts, and calendar patterns to compute optimal train dispatch schedules.
- **Dynamic Event Ingress/Egress Surges**: Accurately differentiates crowd arrivals before an event and departure exit rushes after an event.
- **Operator Overrides**: Transit operators can manually exclude verified events or add ad-hoc gatherings with instant schedule recalculation.

### 2. ⇄ Bidirectional Schedule Optimization (`Schedule View`)
- **Directional Flow Disaggregation**: Metro lines are inherently bidirectional. MetroMind calculates distinct Inbound and Outbound headways calibrated against static GTFS baselines:
  - **Red Line (Corridor I)**: `Miyapur ➔ LB Nagar` vs `LB Nagar ➔ Miyapur`
  - **Blue Line (Corridor III)**: `Raidurg ➔ Nagole` (Evening IT Exit) vs `Nagole ➔ Raidurg` (Morning IT Inflow)
  - **Green Line (Corridor II)**: `JBS Parade Ground ➔ MGBS` vs `MGBS ➔ JBS Parade Ground`
- **Trains-per-Hour (TPH) Scheduling**: Granular hourly table mapping headway minutes, frequency (TPH), directional split percentage, and compression deltas.

### 3. 📍 Event & Metro Proximity Map
- **Leaflet Interactive Map**: Zero-API-key tile layers (Dark Canvas via Esri ArcGIS, Dark OSM with isolated CSS filter, and Standard OpenStreetMap).
- **Venue Proximity Vectors**: Dynamic connector lines between event venues and nearest metro stations with walking distances and travel times.
- **Network Polylines**: Complete coordinates for Red (29 km), Blue (27 km), and Green (11 km) corridors covering all 57 stations.

### 4. 📈 ML Trends & Demand Surges
- **Stacked Surge Visualizations**: Diurnal passenger load breakdown disaggregated into baseline commuters vs. event surge riders.
- **Hourly Slider Analysis**: Interactive 24-hour drill-down across every station in the network.

### 5. 🌦️ Weather & Holiday Surge Modeling
- **Rain Commuter Divergence**: Live precipitation detection modeling private vehicle diversion to metro (+22% ridership surge during downpours).
- **Public Holiday & Long Weekend Exoduses**: Intercity bus hub rushes at MGBS, JBS Parade Ground, LB Nagar, and Miyapur (06:00 - 11:00 AM).
- **Leisure & Waterfront Rushes**: Tank Bund / Hussain Sagar, Durgam Cheruvu Cable Bridge, and Shilparamam afternoon surges.

---

## 📁 Repository Structure

```
metro/
├── .gitignore                   # Production gitignore (excludes node_modules, dist, __pycache__, .env)
├── README.md                    # Project documentation
│
├── backend/                     # FastAPI Python Server
│   ├── main.py                  # API routes & optimization pipeline (/auto-optimize)
│   ├── requirements.txt         # Python dependencies
│   ├── data/                    # GTFS, metadata, and cache files
│   │   ├── station_meta.json    # 57 station coordinates & connectivity
│   │   ├── venues.json          # Stadium & convention venue registry
│   │   ├── holidays.json        # Holiday calendar
│   │   └── live_events.json     # Cached verified events
│   ├── models/                  # ML models & optimizer engines
│   │   ├── optimizer.py         # Headway & fleet calculation engine
│   │   ├── event_impact.py      # Spatial-temporal decay models
│   │   ├── directional_model.py # Inbound vs Outbound flow classifier
│   │   └── anomaly_detector.py  # Statistical load anomaly detector
│   ├── scheduler/               # Background task workers (weather, cache refresh)
│   ├── scrapers/                # Live event and weather clients
│   └── utils/                   # Calendar, holiday, and geo helper functions
│
└── frontend/                    # React 18 + Vite Web Application
    ├── index.html
    ├── package.json
    ├── tailwind.config.js       # Modern dark slate theme configuration
    ├── vite.config.js
    └── src/
        ├── App.jsx              # Main router & layout shell
        ├── index.css            # Dark theme styles & Leaflet tile filters
        ├── api/
        │   └── client.js        # Axios API client
        ├── components/
        │   ├── AutoPilotPanel.jsx    # Executive AI schedule optimizer dashboard
        │   ├── DemandChart.jsx       # Recharts baseline vs surge chart
        │   ├── EventProximityMap.jsx # Interactive Leaflet event proximity modal
        │   ├── FrequencyTable.jsx    # Bidirectional hourly transit dispatch table
        │   ├── LoadingSpinner.jsx    # Accessible loading indicator
        │   └── Sidebar.jsx           # Modern glassmorphic navigation sidebar
        ├── data/
        │   └── corridorCoordinates.js # High-resolution line polylines
        ├── pages/
        │   ├── ControlCenter.jsx     # Autonomous Control Room
        │   ├── NetworkMap.jsx        # Interactive 57-station GIS network map
        │   ├── ScheduleView.jsx      # Bidirectional headway optimization view
        │   └── Trends.jsx            # Event-augmented demand forecasting
        └── utils/
            └── dateUtils.js          # Timezone-accurate date utilities
```

---

## 🚀 Getting Started

### Prerequisites
- **Python**: 3.10 or higher
- **Node.js**: 18.0 or higher
- **npm**: 9.0 or higher

### 1. Backend Setup
```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment (optional but recommended)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI development server
uvicorn main:app --reload --port 8000
```
- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start Vite dev server
npm run dev
```
- Web Application: [http://localhost:5173](http://localhost:5173)

---

## 📦 Pushing to Git

This repository is pre-configured with a clean `.gitignore` that safely excludes all build artifacts (`dist/`), dependencies (`node_modules/`), Python bytecodes (`__pycache__/`), and environment configurations (`.env`).

To push this codebase to your Git repository:

```bash
# 1. Initialize Git (if not already initialized)
git init

# 2. Stage all project files
git add .

# 3. Commit your clean project
git commit -m "feat: complete MetroMind autonomous transit optimization platform"

# 4. Link to your GitHub repository
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git branch -M main

# 5. Push code
git push -u origin main
```

---

## 📄 License
This project is developed for Hyderabad Metro Rail optimization research.
