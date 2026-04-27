# =============================================================================
# analysis_agent.py v2 – Zyflex AI Demand Analysis
#
# Forbedringer i v2:
#   • Distance-decay event scoring (sigmoid – ikke hård 5km cut-off)
#   • Dag-i-ugen vægtning (weekend nat vs. hverdag morgen)
#   • Festival lookahead: events inden for 7 dage booster score
#   • Chauffør-feedback integration fra driver_feedback.json
#   • Earnings estimate pr. zone (DKK/time)
#   • Confidence-score (hvor sikker er vi på scoren)
#   • Næste rush-periode beregning (minutter til næste høje demand)
#   • Zoner kan nu "chainkøres" – bedste rækkefølge foreslås
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

try:
    from history import get_historical_modifiers
    HISTORY_AVAILABLE = True
except ImportError:
    HISTORY_AVAILABLE = False

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent

# ── Tidsmultiplikatorer (time 0-23) ──────────────────────────────────────────
# Basis er hverdage. Weekend tillæg håndteres separat.
TIME_BASE = {
    0: 0.55, 1: 0.45, 2: 0.45, 3: 0.35, 4: 0.35, 5: 0.50,
    6: 0.70, 7: 1.05, 8: 1.35, 9: 1.10, 10: 0.90, 11: 0.90,
    12: 1.00, 13: 1.00, 14: 0.90, 15: 1.05, 16: 1.25, 17: 1.45,
    18: 1.35, 19: 1.15, 20: 1.05, 21: 1.15, 22: 1.30, 23: 1.10,
}

# Weekend (lørdag=5, søndag=6) multiplier oven på TIME_BASE
WEEKEND_EXTRA = {
    22: 0.30, 23: 0.40, 0: 0.50, 1: 0.55, 2: 0.45,
}

# POI-type tidsbonus
POI_BONUS = {
    "transport_hub": {(7, 9): 0.35, (16, 18): 0.30},
    "venue":         {(18, 23): 0.45, (22, 2):  0.50},
    "hospital":      {},   # Altid stabil – ingen ekstra bonus
    "nightlife":     {(22, 3): 0.60},
}

WEIGHTS = {"weather": 22, "events": 32, "time": 24, "location": 22}

# Earnings estimater (DKK/time) baseret på score
EARN_TABLE = [
    (85, 620), (70, 490), (55, 380), (40, 260), (0, 160),
]


class AnalysisAgent:
    """Agent 2 v2 – analyserer efterspørgsel og scorer zoner 0–100."""

    def __init__(self, status_callback=None):
        self.status_callback = status_callback or (lambda msg: None)
        self.result = {}
        self._feedback_cache = None

    # ── Hoved-metode ─────────────────────────────────────────────────────────

    def run(self, data: dict) -> dict:
        city    = data.get("city", "Horsens")
        zones   = data.get("zones", [])
        weather = data.get("weather", {})
        events  = data.get("events", [])
        locs    = data.get("locations", {})
        now     = datetime.now()
        hour    = now.hour
        weekday = now.weekday()   # 0=man … 6=søn

        self._update(f"Analyserer {city} – {len(zones)} zoner, {len(events)} events...")

        # Vejr-score (global – samme for alle zoner)
        self._update("Beregner vejrpåvirkning...")
        w_score, w_reasons = self._weather_score(weather)

        # Historiske modifikatorer
        hist_mods = {}
        if HISTORY_AVAILABLE:
            self._update("Læser historiske data...")
            hist_mods = get_historical_modifiers(city)

        # Chauffør-feedback (seneste 2 timer)
        self._update("Indlæser chauffør-feedback...")
        feedback_mods = self._load_feedback_modifiers(hour, weekday)

        scored_zones = []
        for zone in zones:
            self._update(f"Scorer {zone['name']}...")

            e_score, e_reasons, near_events = self._event_score(zone, events, now)
            t_score, t_reasons              = self._time_score(hour, weekday, zone)
            l_score, l_reasons              = self._location_score(zone, locs.get(zone["id"], {}))

            raw = (
                w_score * WEIGHTS["weather"] +
                e_score * WEIGHTS["events"]  +
                t_score * WEIGHTS["time"]    +
                l_score * WEIGHTS["location"]
            ) / 100

            base_bonus = (zone.get("base_score", 35) - 30) / 20 * 10

            # Historisk modifier
            hist_mod, hist_reasons = self._apply_history(zone["id"], hist_mods)

            # Feedback modifier (chauffør har rapporteret ingen kunder)
            fb_mod, fb_reasons = feedback_mods.get(zone["id"], (0, []))

            final = min(100, max(0, round(raw + base_bonus + hist_mod + fb_mod)))

            # Earnings estimate
            earn_dkk = self._earn_estimate(final)

            # Confidence
            confidence = self._confidence(len(near_events), bool(hist_mods.get(zone["id"])))

            # Næste rush
            next_rush_min, next_rush_label = self._next_rush(hour, weekday, zone)

            all_reasons = w_reasons + e_reasons + t_reasons + l_reasons + hist_reasons + fb_reasons

            scored_zones.append({
                "id":           zone["id"],
                "name":         zone["name"],
                "lat":          zone["lat"],
                "lon":          zone["lon"],
                "score":        final,
                "grade":        self._grade(final),
                "is_hotspot":   final >= 70,
                "reasons":      all_reasons,
                "events_near":  near_events,
                "earn_dkk_hr":  earn_dkk,
                "confidence":   confidence,
                "next_rush_min": next_rush_min,
                "next_rush_lbl": next_rush_label,
                "component_scores": {
                    "weather":  round(w_score),
                    "events":   round(e_score),
                    "time":     round(t_score),
                    "location": round(l_score),
                },
                "recommendation": self._recommendation(zone["name"], final, near_events, earn_dkk),
                "chain_value":    self._chain_value(zone, final),
            })

        scored_zones.sort(key=lambda x: x["score"], reverse=True)
        hotspots = [z for z in scored_zones if z["is_hotspot"]]

        # Foreslå zone-kæde (bedste rækkefølge at køre igennem)
        chain = self._suggest_chain(scored_zones[:4])

        self._update(f"✅ {len(hotspots)} hotspots · top: {scored_zones[0]['name'] if scored_zones else '–'} ({scored_zones[0]['score'] if scored_zones else 0}/100)")

        hist_summary = {}
        if HISTORY_AVAILABLE:
            from history import get_summary
            hist_summary = get_summary()

        self.result = {
            "city":           city,
            "scored_zones":   scored_zones,
            "top_zones":      scored_zones[:5],
            "hotspots":       hotspots,
            "avoid_zones":    [z for z in scored_zones if z["score"] < 35],
            "hour_analyzed":  hour,
            "weekday":        weekday,
            "weather_impact": "HØJ" if weather.get("is_raining") else "LAV",
            "history":        hist_summary,
            "zone_chain":     chain,
            "top_earn_dkk":   scored_zones[0]["earn_dkk_hr"] if scored_zones else 0,
        }
        return self.result

    # ── Scoring-komponenter ───────────────────────────────────────────────────

    def _weather_score(self, w):
        score, reasons = 30.0, []
        temp   = w.get("temperature", 12)
        precip = w.get("precipitation", 0)
        wind   = w.get("windspeed", 0)

        if w.get("is_heavy_rain"):
            score += 52
            reasons.append(f"🌧 Kraftig regn {precip:.1f}mm/t – folk vil IKKE gå")
        elif w.get("is_raining"):
            score += 32
            reasons.append(f"🌦 Let regn {precip:.1f}mm/t – efterspørgsel stiger")

        if temp <= 0:
            score += 20; reasons.append(f"🥶 Frost ({temp:.0f}°C) – ingen vil gå")
        elif temp <= 5:
            score += 15; reasons.append(f"❄️ Meget koldt ({temp:.0f}°C)")
        elif temp <= 10:
            score += 8;  reasons.append(f"🧥 Koldt ({temp:.0f}°C)")

        if wind >= 50:
            score += 15; reasons.append(f"💨 Storm {wind:.0f} km/t")
        elif wind >= 40:
            score += 10; reasons.append(f"💨 Stærk vind {wind:.0f} km/t")

        if not reasons:
            reasons.append(f"☀️ Fint vejr: {temp:.0f}°C, ingen nedbør")

        return min(100, score), reasons

    def _event_score(self, zone, events, now: datetime):
        """Distance-decay scoring – events tættere på = meget højere score."""
        score, reasons, near = 0.0, [], []

        for e in events:
            d = self._dist(zone["lat"], zone["lon"],
                           e.get("lat", zone["lat"]), e.get("lon", zone["lon"]))
            if d > 60:
                continue   # Irrelevant

            att = e.get("attendance", 300)

            # Basis-score fra størrelse
            if att > 20000:  base = 95
            elif att > 5000: base = 80
            elif att > 2000: base = 65
            elif att > 500:  base = 45
            elif att > 100:  base = 25
            else:            base = 12

            # Distance decay: sigmoid-funktion
            # 0.0 km → 1.0x, 1.0 km → 0.82x, 3.0 km → 0.50x, 8.0 km → 0.18x
            decay = 1 / (1 + math.exp(0.5 * (d - 2)))

            # Festival-lookahead bo