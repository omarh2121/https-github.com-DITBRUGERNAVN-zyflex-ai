# =============================================================================
# config.py – Zyflex AI Configuration
# All zones, API settings, and scoring weights live here.
# Edit this file to add new zones or tune the scoring system.
# =============================================================================

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# API KEYS (loaded from .env file)
# ---------------------------------------------------------------------------
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "")

# ---------------------------------------------------------------------------
# GEOGRAPHIC SETTINGS
# Primary operating area: Horsens + surrounding municipalities
# Coordinates: (latitude, longitude)
# ---------------------------------------------------------------------------
ZONES = [
    {
        "id": "horsens_centrum",
        "name": "Horsens Centrum",
        "lat": 55.8615,
        "lon": 9.8506,
        "base_score": 50,          # Starting demand score before modifiers
        "poi_type": "city_center",  # Point-of-interest type
        "description": "Bymidten – høj basisaktivitet hele dagen",
    },
    {
        "id": "horsens_station",
        "name": "Horsens Station",
        "lat": 55.8591,
        "lon": 9.8441,
        "base_score": 45,
        "poi_type": "transport_hub",
        "description": "Tog- og busstation – rush hour spidser",
    },
    {
        "id": "horsens_sygehus",
        "name": "Horsens Sygehus",
        "lat": 55.8711,
        "lon": 9.8395,
        "base_score": 40,
        "poi_type": "hospital",
        "description": "Sygehus – stabil efterspørgsel hele dagen",
    },
    {
        "id": "horsens_sportscenter",
        "name": "Horsens Sportscenter / CASA Arena",
        "lat": 55.8517,
        "lon": 9.8625,
        "base_score": 30,
        "poi_type": "venue",
        "description": "Arena – eksploderer ved events og kampe",
    },
    {
        "id": "ikast_centrum",
        "name": "Ikast Centrum",
        "lat": 56.1389,
        "lon": 9.1578,
        "base_score": 35,
        "poi_type": "city_center",
        "description": "Ikast bymidte – sekundær zone",
    },
    {
        "id": "skanderborg_centrum",
        "name": "Skanderborg Centrum",
        "lat": 56.0431,
        "lon": 9.9270,
        "base_score": 35,
        "poi_type": "city_center",
        "description": "Skanderborg – god ved Smukfest og events",
    },
    {
        "id": "hedensted_centrum",
        "name": "Hedensted Centrum",
        "lat": 55.7731,
        "lon": 9.7047,
        "base_score": 28,
        "poi_type": "city_center",
        "description": "Hedensted – lokalmarked",
    },
    {
        "id": "braedstrup_centrum",
        "name": "Brædstrup Centrum",
        "lat": 55.9706,
        "lon": 9.6042,
        "base_score": 25,
        "poi_type": "city_center",
        "description": "Brædstrup – pendlerzone",
    },
]

# ---------------------------------------------------------------------------
# SCORING WEIGHTS
# These control how much each factor impacts the final demand score.
# Total weights should add up to 100 for a clean 0–100 scale.
# ---------------------------------------------------------------------------
SCORING_WEIGHTS = {
    "weather":   25,   # Rain and cold push demand up significantly
    "events":    30,   # Concerts, sports, festivals are the biggest driver
    "time":      25,   # Rush hours, weekends, nights
    "location":  20,   # POI density (hotels, bars, transport hubs nearby)
}

# ---------------------------------------------------------------------------
# WEATHER THRESHOLDS
# ---------------------------------------------------------------------------
WEATHER = {
    "rain_threshold_mm": 0.5,    # mm/hour – above this = rainy
    "heavy_rain_mm":     3.0,    # mm/hour – above this = heavy rain
    "cold_threshold_c":  5.0,    # °C – below this = cold bonus
    "hot_threshold_c":   28.0,   # °C – above this = slight demand drop
}

# ---------------------------------------------------------------------------
# TIME-OF-DAY MULTIPLIERS (hour 0–23)
# Values above 1.0 = high demand period
# ---------------------------------------------------------------------------
TIME_MULTIPLIERS = {
    0:  0.6,   # Midnight
    1:  0.5,
    2:  0.5,
    3:  0.4,
    4:  0.4,
    5:  0.5,
    6:  0.7,   # Early morning
    7:  1.0,   # Morning rush starts
    8:  1.3,   # Morning rush peak
    9:  1.1,
    10: 0.9,
    11: 0.9,
    12: 1.0,   # Lunch
    13: 1.0,
    14: 0.9,
    15: 1.0,
    16: 1.2,   # Afternoon rush
    17: 1.4,   # Afternoon rush peak
    18: 1.3,
    19: 1.1,
    20: 1.0,
    21: 1.1,   # Evening out
    22: 1.2,   # Late evening – bars/restaurants
    23: 1.0,
}

# ---------------------------------------------------------------------------
# OUTPUT SETTINGS
# ---------------------------------------------------------------------------
OUTPUT = {
    "top_zones_count":   5,       # How many top zones to display
    "report_file":       "data/report.json",
    "trips_file":        "data/trips.csv",
    "log_file":          "data/zyflex.log",
}

# ---------------------------------------------------------------------------
# OPEN-METEO API (free – no key needed)
# ---------------------------------------------------------------------------
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# ---------------------------------------------------------------------------
# TICKETMASTER API (optional – falls back to mock data if no key)
# ---------------------------------------------------------------------------
TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
TICKETMASTER_SEARCH_RADIUS = "50"   # km radius around Horsens
TICKETMASTER_CITY = "Horsens"
TICKETMASTER_COUNTRY = "DK"

# ---------------------------------------------------------------------------
# OVERPASS API (OpenStreetMap – free)
# ---------------------------------------------------------------------------
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_RADIUS_M = 1000            # Search radius in meters around each zone
