# =============================================================================
# processor.py – Zyflex AI Demand Scoring Engine
#
# This is the brain of the system. It takes raw data from the fetchers
# and turns it into actionable demand scores and recommendations.
#
# Scoring formula (each component scores 0–100):
#   final_score = (
#       weather_score  * WEIGHT_WEATHER  +
#       event_score    * WEIGHT_EVENTS   +
#       time_score     * WEIGHT_TIME     +
#       location_score * WEIGHT_LOCATION
#   ) / 100  +  base_score_adjustment
#
# The output is a ranked list of zones with scores and human-readable reasons.
# =============================================================================

import math
import logging
from datetime import datetime
from typing import List, Dict

from config import ZONES, SCORING_WEIGHTS, TIME_MULTIPLIERS, WEATHER, OUTPUT

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCORING FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def score_zones(
    weather_data:   dict,
    events_data:    list,
    location_data:  dict,
    current_hour:   int = None,
) -> List[Dict]:
    """
    Score all zones and return them ranked by demand score.

    Args:
        weather_data:   Output from fetchers.fetch_weather()
        events_data:    Output from fetchers.fetch_events()
        location_data:  Output from fetchers.fetch_locations()
        current_hour:   Hour (0–23) to score for. Defaults to now.

    Returns:
        List of zone dicts sorted by score descending, each containing:
        {
            "id":           str,
            "name":         str,
            "score":        int,          # 0–100
            "grade":        str,          # "🔴 Høj", "🟡 Mellem", "🟢 Lav"
            "reasons":      list[str],    # Human-readable factors
            "weather":      dict,
            "events_near":  list,
            "recommendation": str,
        }
    """
    if current_hour is None:
        current_hour = datetime.now().hour

    scored = []

    for zone in ZONES:
        zone_id = zone["id"]

        # Calculate each component
        w_score, w_reasons = _weather_score(weather_data)
        e_score, e_reasons, near_events = _event_score(zone, events_data)
        t_score, t_reasons = _time_score(current_hour, zone)
        l_score, l_reasons = _location_score(zone, location_data.get(zone_id, {}))

        # Weighted combination
        weights = SCORING_WEIGHTS
        raw_score = (
            w_score * weights["weather"]  +
            e_score * weights["events"]   +
            t_score * weights["time"]     +
            l_score * weights["location"]
        ) / 100  # Normalise back to 0–100

        # Add the zone's base score as a bonus (max +10 pts)
        base_bonus = (zone["base_score"] - 30) / 20 * 10  # Map 30–50 base → 0–10 pts
        final_score = min(100, max(0, round(raw_score + base_bonus)))

        # Combine all reasons
        all_reasons = w_reasons + e_reasons + t_reasons + l_reasons

        scored.append({
            "id":             zone_id,
            "name":           zone["name"],
            "lat":            zone["lat"],
            "lon":            zone["lon"],
            "description":    zone["description"],
            "score":          final_score,
            "grade":          _grade(final_score),
            "reasons":        all_reasons,
            "events_near":    near_events,
            "weather":        weather_data,
            "recommendation": _build_recommendation(zone, final_score, all_reasons, near_events, current_hour),
            "component_scores": {
                "weather":  round(w_score),
                "events":   round(e_score),
                "time":     round(t_score),
                "location": round(l_score),
            },
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    logger.info(f"Scoring complete. Top zone: {scored[0]['name']} ({scored[0]['score']})")
    return scored


# ─────────────────────────────────────────────────────────────────────────────
# COMPONENT SCORERS
# Each returns (score: float 0–100, reasons: list[str])
# ─────────────────────────────────────────────────────────────────────────────

def _weather_score(weather: dict) -> tuple:
    """
    Rain and cold = people don't want to walk → more taxi demand.
    Score logic:
      - No rain, mild temp  → ~30 pts (baseline)
      - Light rain          → +30 pts
      - Heavy rain          → +50 pts
      - Cold (<5°C)         → +15 pts
      - Windy (>40 km/h)    → +10 pts
    """
    score = 30.0
    reasons = []

    precip   = weather.get("precipitation", 0)
    temp     = weather.get("temperature", 15)
    wind     = weather.get("windspeed", 0)
    is_rain  = weather.get("is_raining", False)
    is_heavy = weather.get("is_heavy_rain", False)
    is_cold  = weather.get("is_cold", False)

    if is_heavy:
        score += 50
        reasons.append(f"Kraftig regn ({precip:.1f} mm/t) – folk vil IKKE gå")
    elif is_rain:
        score += 30
        reasons.append(f"Let regn ({precip:.1f} mm/t) – taxi-efterspørgsel stiger")

    if is_cold:
        score += 15
        reasons.append(f"Koldt vejr ({temp:.0f}°C) – passagerer foretrækker taxa")

    if wind >= 40:
        score += 10
        reasons.append(f"Kraftig vind ({wind:.0f} km/t)")
    elif wind >= 25:
        score += 5
        reasons.append(f"Blæsende vejr ({wind:.0f} km/t)")

    if not reasons:
        reasons.append(f"Vejr OK: {temp:.0f}°C, ingen nedbør")

    return min(100, score), reasons


def _event_score(zone: dict, events: list) -> tuple:
    """
    Events near a zone dramatically increase demand.
    Score scales with attendance:
      - Small event (<500):   +20 pts
      - Medium (500–2000):    +40 pts
      - Large (>2000):        +70 pts
    Multiple events stack (capped at 100).
    """
    score = 0.0
    reasons = []
    near_events = []

    for event in events:
        distance_km = _haversine(
            zone["lat"], zone["lon"],
            event.get("lat", zone["lat"]),
            event.get("lon", zone["lon"]),
        )

        # Only count events within 5 km of the zone
        if distance_km <= 5.0:
            attendance = event.get("attendance", 500)
            name       = event.get("name", "Event")
            category   = event.get("category", "")

            if attendance > 5000:
                pts = 80
            elif attendance > 2000:
                pts = 60
            elif attendance > 500:
                pts = 40
            else:
                pts = 20

            # Events at the exact venue (within 0.5 km) get a bonus
            if distance_km <= 0.5:
                pts = min(100, pts + 15)

            score += pts
            near_events.append({**event, "distance_km": round(distance_km, 2)})
            reasons.append(
                f"Event nærhed: {name} ({attendance:,} gæster, {distance_km:.1f} km)"
            )

    if not near_events:
        score = 20  # Baseline – no events
        reasons.append("Ingen events i nærheden i dag")

    return min(100, score), reasons, near_events


def _time_score(hour: int, zone: dict) -> tuple:
    """
    Time-of-day multiplier applied to base score.
    Transport hubs get extra boost during rush hours.
    Venues get boost in evenings.
    """
    multiplier = TIME_MULTIPLIERS.get(hour, 1.0)
    base       = 50.0  # Neutral baseline

    # POI-type adjustments
    poi_type = zone.get("poi_type", "city_center")

    if poi_type == "transport_hub":
        # Stations: extra boost morning (7–9) and afternoon (16–18)
        if 7 <= hour <= 9 or 16 <= hour <= 18:
            multiplier = min(2.0, multiplier + 0.3)

    elif poi_type == "venue":
        # Arenas: only matter in evenings
        if 18 <= hour <= 23:
            multiplier = min(2.0, multiplier + 0.4)
        else:
            multiplier = max(0.3, multiplier - 0.3)

    elif poi_type == "hospital":
        # Hospitals: steady demand, slight boost early morning
        multiplier = max(0.8, multiplier)

    score = min(100, base * multiplier)

    # Build time label
    if 7 <= hour <= 9:
        time_label = f"Morgenrush ({hour}:00)"
    elif 16 <= hour <= 18:
        time_label = f"Eftermiddagsrush ({hour}:00)"
    elif 22 <= hour or hour <= 2:
        time_label = f"Natteliv ({hour}:00)"
    elif 12 <= hour <= 14:
        time_label = f"Frokosttid ({hour}:00)"
    else:
        time_label = f"Normaltid ({hour}:00)"

    reasons = [f"Tidspunkt: {time_label} (multiplikator {multiplier:.1f}x)"]
    return score, reasons


def _location_score(zone: dict, pois: dict) -> tuple:
    """
    More POIs (hotels, bars, restaurants) = more potential pickups/dropoffs.
    Score = weighted sum of POI counts, capped at 100.
    """
    if not pois:
        return 30.0, ["Ingen POI-data tilgængelig"]

    hotels      = pois.get("hotels", 0)
    bars        = pois.get("bars", 0)
    restaurants = pois.get("restaurants", 0)
    hospitals   = pois.get("hospitals", 0)
    stations    = pois.get("stations", 0)
    total       = pois.get("total_pois", 0)

    # Each POI type has a different weight
    score = (
        hotels      * 8 +
        bars        * 5 +
        restaurants * 3 +
        hospitals   * 10 +
        stations    * 12
    )

    score = min(100, score)
    reasons = []

    if hotels > 0:
        reasons.append(f"{hotels} hotel(er) i nærheden")
    if bars > 0:
        reasons.append(f"{bars} bar/pub(er) i nærheden")
    if hospitals > 0:
        reasons.append(f"{hospitals} sygehus/klinik i nærheden")
    if stations > 0:
        reasons.append(f"{stations} togstation(er) i nærheden")
    if not reasons:
        reasons.append(f"{total} POI'er i alt")

    return score, reasons


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two GPS coordinates."""
    R = 6371  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _grade(score: int) -> str:
    """Convert numeric score to a colour-coded grade."""
    if score >= 75:
        return "🔴 Høj efterspørgsel"
    elif score >= 55:
        return "🟡 Middel efterspørgsel"
    elif score >= 35:
        return "🟢 Lav efterspørgsel"
    else:
        return "⚪ Meget lav"


def _build_recommendation(
    zone: dict,
    score: int,
    reasons: list,
    near_events: list,
    hour: int,
) -> str:
    """
    Build a concrete, actionable driving recommendation for the driver.
    """
    name = zone["name"]

    if score >= 75:
        base = f"KØR TIL {name.upper()} – høj efterspørgsel lige nu!"
    elif score >= 55:
        base = f"Overvej {name} – god mulighed for ture"
    elif score >= 35:
        base = f"{name} – moderat aktivitet, passende som alternativ"
    else:
        base = f"{name} – lav aktivitet, undgå medmindre du er i nærheden"

    # Add specific event context
    if near_events:
        event_names = ", ".join(e["name"] for e in near_events[:2])
        base += f". Event: {event_names}."

    return base


# ─────────────────────────────────────────────────────────────────────────────
# DAILY REPORT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(scored_zones: list, weather: dict, events: list) -> dict:
    """
    Generate a structured daily report dict.
    This is saved as data/report.json and read by the dashboard.
    """
    top_zones    = scored_zones[:OUTPUT["top_zones_count"]]
    avoid_zones  = [z for z in scored_zones if z["score"] < 35]

    # Estimated earnings (rough model):
    # High demand zones → ~3 trips/hour @ avg 120 DKK = 360 DKK/hour
    top_score    = top_zones[0]["score"] if top_zones else 50
    est_trips_hr = round(1.5 + (top_score / 100) * 2.5, 1)
    est_earn_hr  = round(est_trips_hr * 120)

    return {
        "generated_at":   datetime.now().isoformat(),
        "date":           datetime.now().strftime("%Y-%m-%d"),
        "time":           datetime.now().strftime("%H:%M"),
        "weather_summary": {
            "temperature":   weather.get("temperature"),
            "precipitation": weather.get("precipitation"),
            "is_raining":    weather.get("is_raining"),
        },
        "events_today":   len(events),
        "top_zones":      top_zones,
        "avoid_zones":    [{"name": z["name"], "score": z["score"]} for z in avoid_zones],
        "all_zones":      scored_zones,
        "earnings_estimate": {
            "trips_per_hour":  est_trips_hr,
            "earn_per_hour_dkk": est_earn_hr,
            "daily_est_8h_dkk":  est_earn_hr * 8,
            "note": "Estimat baseret på demandsscore – faktisk indtjening varierer",
        },
        "partnership_leads": _find_partnership_leads(scored_zones),
    }


def _find_partnership_leads(scored_zones: list) -> list:
    """
    Identify zones worth approaching for B2B partnerships.
    High-scoring hotel and hospital zones = good leads.
    """
    leads = []
    for zone in scored_zones:
        poi_type = next(
            (z["poi_type"] for z in ZONES if z["id"] == zone["id"]), ""
        )
        if poi_type in ("transport_hub", "hospital") and zone["score"] >= 40:
            leads.append({
                "zone":        zone["name"],
                "score":       zone["score"],
                "lead_type":   "Fast transportaftale" if poi_type == "hospital" else "Stationspartner",
                "action":      f"Kontakt {zone['name']} om fast aftale – steady demand",
            })
    return leads[:3]  # Top 3 leads only
