# =============================================================================
# ops_agent.py – Agent 4: Operations & Route Optimization
#
# Ansvar: Oversæt analyse til konkrete chauffør-handlinger.
# - Anbefal præcis where og hvornår chaufføren skal køre
# - Estimer daglig og månedlig indtjening
# - Identificér tomkørsel og reducer den
# - Giv time-for-time køreplan
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Gennemsnitlig tur-pris i DKK (baseret på Horsens-markedet)
AVG_FARE_DKK       = 130
TARGET_MONTHLY_DKK = 85_000
WORKING_DAYS_PM    = 22
TARGET_DAILY_DKK   = TARGET_MONTHLY_DKK // WORKING_DAYS_PM


class OpsAgent:
    """
    Agent 4 – genererer driftsanbefalinger og køreplan.
    Kald .run(data_result, analysis_result) for at starte.
    """

    def __init__(self, status_callback=None):
        self.status_callback = status_callback or (lambda msg: None)
        self.result = {}

    def run(self, data: dict, analysis: dict) -> dict:
        city       = data.get("city", "Horsens")
        weather    = data.get("weather", {})
        top_zones  = analysis.get("top_zones", [])
        all_zones  = analysis.get("scored_zones", [])
        hour       = datetime.now().hour

        self._update(f"Beregner optimal køreplan for {city}...")
        plan = self._build_hourly_plan(top_zones, hour)

        self._update("Estimerer indtjening baseret på demand...")
        earnings = self._estimate_earnings(top_zones, weather)

        self._update("Analyserer tomkørsel...")
        empty_drive = self._empty_drive_analysis(top_zones, all_zones)

        self._update("Genererer chauffør-briefing...")
        briefing = self._driver_briefing(city, top_zones, weather, hour)

        self._update(f"✅ Driftsplan klar – estimeret {earnings['daily_est_dkk']:,} kr i dag")

        self.result = {
            "city":              city,
            "current_action":    briefing["now"],
            "hourly_plan":       plan,
            "earnings":          earnings,
            "empty_drive":       empty_drive,
            "driver_briefing":   briefing,
            "kpi": {
                "target_monthly":  TARGET_MONTHLY_DKK,
                "target_daily":    TARGET_DAILY_DKK,
                "est_daily":       earnings["daily_est_dkk"],
                "gap_to_target":   max(0, TARGET_DAILY_DKK - earnings["daily_est_dkk"]),
                "on_track":        earnings["daily_est_dkk"] >= TARGET_DAILY_DKK * 0.8,
            },
        }
        return self.result

    # ── Køreplan (time-for-time) ──────────────────────────────────────────────

    def _build_hourly_plan(self, top_zones: list, current_hour: int) -> list:
        """Lav en køreplan for de næste 8 timer."""
        plan = []
        top_name = top_zones[0]["name"] if top_zones else "Centrum"

        for offset in range(8):
            h = (current_hour + offset) % 24
            zone = self._best_zone_for_hour(top_zones, h)
            demand = self._hour_demand_label(h)
            plan.append({
                "hour":       f"{h:02d}:00",
                "zone":       zone,
                "demand":     demand,
                "action":     self._hour_action(h, zone, demand),
                "is_current": offset == 0,
            })
        return plan

    def _best_zone_for_hour(self, zones: list, hour: int) -> str:
        if not zones:
            return "Centrum"
        # Morgen/aften: station; Nat: centrum; events: venue
        if 7 <= hour <= 9 or 16 <= hour <= 18:
            station = next((z["name"] for z in zones if "station" in z["id"].lower()), None)
            if station: return station
        if 22 <= hour or hour <= 3:
            centrum = next((z["name"] for z in zones if "centrum" in z["id"].lower()), None)
            if centrum: return centrum
        return zones[0]["name"]

    def _hour_demand_label(self, h: int) -> str:
        if 7 <= h <= 9 or 16 <= h <= 18: return "⚡ Rush"
        if 22 <= h or h <= 2:            return "🌙 Natteliv"
        if 12 <= h <= 14:                return "🍽 Frokost"
        if 6 <= h <= 7 or 18 <= h <= 20: return "📈 Stigende"
        return "📊 Normal"

    def _hour_action(self, h: int, zone: str, demand: str) -> str:
        if "Rush" in demand:
            return f"Positionér dig ved {zone} – rush hour"
        if "Natteliv" in demand:
            return f"Kør centrum – folk hjem fra barer og restauranter"
        if "Frokost" in demand:
            return f"Hold ved {zone} – frokosttransport"
        return f"Kør {zone} – stabil efterspørgsel"

    # ── Indtjeningsestimering ─────────────────────────────────────────────────

    def _estimate_earnings(self, top_zones: list, weather: dict) -> dict:
        top_score    = top_zones[0]["score"] if top_zones else 50
        base_trips_h = 1.5 + (top_score / 100) * 2.5

        # Vejrbonus
        rain_bonus   = 0.4 if weather.get("is_heavy_rain") else 0.2 if weather.get("is_raining") else 0

        trips_h   = round(base_trips_h + rain_bonus, 1)
        earn_h    = round(trips_h * AVG_FARE_DKK)
        earn_8h   = round(earn_h * 8)
        earn_pm   = round(earn_8h * WORKING_DAYS_PM)

        return {
            "avg_fare_dkk":    AVG_FARE_DKK,
            "trips_per_hour":  trips_h,
            "earn_per_hour":   earn_h,
            "daily_est_dkk":   earn_8h,
            "monthly_est_dkk": earn_pm,
            "target_monthly":  TARGET_MONTHLY_DKK,
            "rain_bonus":      rain_bonus > 0,
            "note":            "Estimat – faktisk resultat afhænger af tilgængelighed og konkurrence",
        }

    # ── Tomkørsel-analyse ─────────────────────────────────────────────────────

    def _empty_drive_analysis(self, top_zones: list, all_zones: list) -> dict:
        high_zones = [z["name"] for z in all_zones if z["score"] >= 60]
        low_zones  = [z["name"] for z in all_zones if z["score"] < 35]

        tips = []
        if len(high_zones) >= 2:
            tips.append(f"Kør mellem {high_zones[0]} og {high_zones[1]} – begge høj score")
        if low_zones:
            tips.append(f"Undgå: {', '.join(low_zones[:2])} – lav efterspørgsel")
        tips.append("Slå 'Del tur' til i perioder med lav demand")
        tips.append("Positionér dig 5 min FØR rush hour – ikke under")

        empty_pct   = max(5, 30 - len(high_zones) * 5)
        optimized   = max(5, empty_pct - 12)

        return {
            "current_empty_pct":   empty_pct,
            "optimized_empty_pct": optimized,
            "saved_km_daily":      round((empty_pct - optimized) / 100 * 150),
            "saved_dkk_daily":     round((empty_pct - optimized) / 100 * 150 * 2.5),
            "tips":                tips,
        }

    # ── Chauffør-briefing ─────────────────────────────────────────────────────

    def _driver_briefing(self, city, top_zones, weather, hour) -> dict:
        top = top_zones[0]["name"] if top_zones else city + " Centrum"
        score = top_zones[0]["score"] if top_zones else 50

        now_msg = f"KØR TIL {top.upper()} – Score {score}/100"
        if weather.get("is_raining"):
            now_msg += " · Regn booster efterspørgsel"

        return {
            "now":     now_msg,
            "morning": f"Positionér ved station i {city} 07:00–09:00",
            "middag":  f"Hold centrum kl 12–13 – frokosttransport",
            "aften":   f"Rush hour ved {top} kl 16–18",
            "nat":     f"Centrum og barer efter kl 22",
            "tip":     "Hav altid laderen i bilen og hold telefonen synlig",
        }

    def _update(self, msg):
        logger.info(f"[OpsAgent] {msg}")
        self.status_callback(msg)
