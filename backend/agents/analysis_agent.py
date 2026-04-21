# =============================================================================
# analysis_agent.py – Agent 2: Demand Analysis
#
# Ansvar: Tag rådata fra DataAgent og beregn efterspørgselsscore for alle zoner.
# Output: Ranket liste af zoner med score, begrundelse og hotspot-status.
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import logging
from datetime import datetime

try:
    from history import get_historical_modifiers
    HISTORY_AVAILABLE = True
except ImportError:
    HISTORY_AVAILABLE = False

logger = logging.getLogger(__name__)

TIME_MULTIPLIERS = {
    0: 0.6, 1: 0.5, 2: 0.5, 3: 0.4, 4: 0.4, 5: 0.5,
    6: 0.7, 7: 1.0, 8: 1.3, 9: 1.1, 10: 0.9, 11: 0.9,
    12: 1.0, 13: 1.0, 14: 0.9, 15: 1.0, 16: 1.2, 17: 1.4,
    18: 1.3, 19: 1.1, 20: 1.0, 21: 1.1, 22: 1.2, 23: 1.0,
}

WEIGHTS = {"weather": 25, "events": 30, "time": 25, "location": 20}


class AnalysisAgent:
    """
    Agent 2 – analyserer efterspørgsel og scorer zoner 0–100.
    Kald .run(data_agent_result) for at starte.
    """

    def __init__(self, status_callback=None):
        self.status_callback = status_callback or (lambda msg: None)
        self.result = {}

    def run(self, data: dict) -> dict:
        city    = data.get("city", "Horsens")
        zones   = data.get("zones", [])
        weather = data.get("weather", {})
        events  = data.get("events", [])
        locs    = data.get("locations", {})
        hour    = datetime.now().hour

        self._update(f"Analyserer vejrpåvirkning for {city}...")
        w_score, w_reasons = self._weather_score(weather)

        # Hent historiske modifikatorer fra trips.csv
        hist_mods = {}
        if HISTORY_AVAILABLE:
            self._update("Læser historiske mønstre fra trips.csv...")
            hist_mods = get_historical_modifiers(city)
            if hist_mods:
                self._update(f"Historik: {len(hist_mods)} zoner med data")

        self._update(f"Scanner {len(events)} events i nærheden...")
        scored_zones = []

        for zone in zones:
            self._update(f"Scorer zone: {zone['name']}...")
            e_score, e_reasons, near_events = self._event_score(zone, events)
            t_score, t_reasons = self._time_score(hour, zone)
            l_score, l_reasons = self._location_score(zone, locs.get(zone["id"], {}))

            raw = (
                w_score * WEIGHTS["weather"] +
                e_score * WEIGHTS["events"] +
                t_score * WEIGHTS["time"] +
                l_score * WEIGHTS["location"]
            ) / 100

            base_bonus = (zone.get("base_score", 35) - 30) / 20 * 10

            # Historisk modifikator (maks ±8 point – undgå over-fitting)
            hist_mod    = 0.0
            hist_reason = []
            zone_hist   = hist_mods.get(zone["id"], {})
            if zone_hist:
                hist_mod = max(-8, min(8, zone_hist.get("modifier", 0)))
                if abs(hist_mod) >= 1.5:
                    direction = "↑" if hist_mod > 0 else "↓"
                    hist_reason = [f"📊 Historik {direction}{abs(hist_mod):.0f}pt: {zone_hist.get('insight','')}"
                                   + f" ({zone_hist.get('confidence','?')} confidence, {zone_hist.get('runs',0)} kørsler)"]

            final = min(100, max(0, round(raw + base_bonus + hist_mod)))

            all_reasons = w_reasons + e_reasons + t_reasons + l_reasons + hist_reason

            scored_zones.append({
                "id":          zone["id"],
                "name":        zone["name"],
                "lat":         zone["lat"],
                "lon":         zone["lon"],
                "score":       final,
                "grade":       self._grade(final),
                "is_hotspot":  final >= 70,
                "reasons":     all_reasons,
                "events_near": near_events,
                "component_scores": {
                    "weather":  round(w_score),
                    "events":   round(e_score),
                    "time":     round(t_score),
                    "location": round(l_score),
                },
                "recommendation": self._recommendation(zone["name"], final, near_events),
            })

        scored_zones.sort(key=lambda x: x["score"], reverse=True)

        hotspots = [z for z in scored_zones if z["is_hotspot"]]
        self._update(f"✅ Analyse færdig – {len(hotspots)} hotspots fundet i {city}")

        # Historisk overblik til dashboard
        hist_summary = {}
        if HISTORY_AVAILABLE:
            from history import get_summary
            hist_summary = get_summary()

        self.result = {
            "city":          city,
            "scored_zones":  scored_zones,
            "top_zones":     scored_zones[:5],
            "hotspots":      hotspots,
            "avoid_zones":   [z for z in scored_zones if z["score"] < 35],
            "hour_analyzed": hour,
            "weather_impact": "HØJ" if weather.get("is_raining") else "LAV",
            "history":       hist_summary,
        }
        return self.result

    # ── Scoring-komponenter ───────────────────────────────────────────────────

    def _weather_score(self, w):
        score, reasons = 30.0, []
        if w.get("is_heavy_rain"):
            score += 50; reasons.append(f"Kraftig regn ({w.get('precipitation',0):.1f}mm/t) – folk vil IKKE gå")
        elif w.get("is_raining"):
            score += 30; reasons.append(f"Let regn ({w.get('precipitation',0):.1f}mm/t) – taxi-efterspørgsel stiger")
        if w.get("is_cold"):
            score += 15; reasons.append(f"Koldt ({w.get('temperature',12):.0f}°C) – passagerer foretrækker taxa")
        if w.get("windspeed", 0) >= 40:
            score += 10; reasons.append("Kraftig vind")
        if not reasons:
            reasons.append(f"Vejr OK: {w.get('temperature',12):.0f}°C, ingen nedbør")
        return min(100, score), reasons

    def _event_score(self, zone, events):
        score, reasons, near = 0.0, [], []
        for e in events:
            d = self._dist(zone["lat"], zone["lon"], e.get("lat", zone["lat"]), e.get("lon", zone["lon"]))
            if d <= 5.0:
                att = e.get("attendance", 500)
                pts = 80 if att > 5000 else 60 if att > 2000 else 40 if att > 500 else 20
                if d <= 0.5: pts = min(100, pts + 15)
                score += pts
                near.append({**e, "distance_km": round(d, 2)})
                reasons.append(f"Event: {e['name']} ({att:,} gæster, {d:.1f} km)")
        if not near:
            score = 20; reasons.append("Ingen events i nærheden")
        return min(100, score), reasons, near

    def _time_score(self, hour, zone):
        m = TIME_MULTIPLIERS.get(hour, 1.0)
        poi = zone.get("poi_type", "city_center")
        if poi == "transport_hub" and (7 <= hour <= 9 or 16 <= hour <= 18):
            m = min(2.0, m + 0.3)
        elif poi == "venue" and 18 <= hour <= 23:
            m = min(2.0, m + 0.4)
        elif poi == "hospital":
            m = max(0.8, m)
        score = min(100, 50 * m)
        label = ("Morgenrush" if 7 <= hour <= 9 else "Eftermiddagsrush" if 16 <= hour <= 18
                 else "Natteliv" if hour >= 22 or hour <= 2 else "Frokost" if 12 <= hour <= 14 else "Normal")
        return score, [f"Tidspunkt: {label} ({hour}:00) – {m:.1f}x multiplikator"]

    def _location_score(self, zone, pois):
        if not pois:
            return 30.0, ["Ingen POI-data"]
        score = min(100,
            pois.get("hotels", 0) * 8 + pois.get("bars", 0) * 5 +
            pois.get("restaurants", 0) * 3 + pois.get("hospitals", 0) * 10 +
            pois.get("stations", 0) * 12
        )
        reasons = []
        if pois.get("hotels"):    reasons.append(f"{pois['hotels']} hotel(er)")
        if pois.get("bars"):      reasons.append(f"{pois['bars']} bar/pub(er)")
        if pois.get("hospitals"): reasons.append(f"{pois['hospitals']} sygehus")
        if pois.get("stations"):  reasons.append(f"{pois['stations']} togstation(er)")
        return score, reasons or [f"{pois.get('total_pois',0)} POI'er"]

    # ── Hjælpere ─────────────────────────────────────────────────────────────

    def _dist(self, lat1, lon1, lat2, lon2):
        R = 6371
        dl = math.radians(lat2 - lat1); dg = math.radians(lon2 - lon1)
        a = math.sin(dl/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dg/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _grade(self, score):
        if score >= 75: return "🔴 Høj efterspørgsel"
        if score >= 55: return "🟡 Middel efterspørgsel"
        if score >= 35: return "🟢 Lav efterspørgsel"
        return "⚪ Meget lav"

    def _recommendation(self, name, score, events):
        if score >= 75:   base = f"KØR TIL {name.upper()} – høj efterspørgsel!"
        elif score >= 55: base = f"Overvej {name} – god mulighed"
        elif score >= 35: base = f"{name} – moderat aktivitet"
        else:             base = f"{name} – undgå for nu"
        if events:
            base += f" · Event: {events[0]['name']}"
        return base

    def _update(self, msg):
        logger.info(f"[AnalysisAgent] {msg}")
        self.status_callback(msg)
