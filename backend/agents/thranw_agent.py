#!/usr/bin/env python3
# =============================================================================
# thranw_agent.py – Zyflex Hovedagent (Thranw)
#
# Thranw er beslutningslaget OVENPÅ dine eksisterende agenter:
#   - data_agent.DataAgent       → vejr + events + zoner + POIs
#   - analysis_agent.AnalysisAgent → zone-scoring 0-100 (inkl. historik)
#   - ops_agent.OpsAgent         → earnings + briefing
#   - history.get_summary        → personlig insight fra trips.csv
#
# Thranw reimplementerer IKKE scoring – den orkestrerer dine agenter,
# vægter top-zonen mod chauffør-position og pakker det i ÉT klart svar.
#
# CLI test:
#   python thranw_agent.py --lat 55.86 --lng 9.85
#   python thranw_agent.py --lat 55.86 --lng 9.85 --json
#   python thranw_agent.py --health
#   python thranw_agent.py --all-zones
# =============================================================================

from __future__ import annotations

import os
import sys
import json
import math
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Sørg for at parent-mapper er på path uanset hvordan filen kaldes
_THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
_BACKEND   = os.path.dirname(_THIS_DIR)
for p in (_THIS_DIR, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger("thranw")

# ── Imports af eksisterende agenter (med graceful fallback) ──────────────────
try:
    from agents.data_agent     import DataAgent
except Exception:
    from data_agent     import DataAgent          # type: ignore
try:
    from agents.analysis_agent import AnalysisAgent
except Exception:
    from analysis_agent import AnalysisAgent      # type: ignore
try:
    from agents.ops_agent      import OpsAgent
except Exception:
    from ops_agent      import OpsAgent           # type: ignore

try:
    from history import get_summary as _history_summary
except Exception:
    _history_summary = lambda: {"status": "no_data"}  # noqa: E731


# =============================================================================
# KONFIGURATION
# =============================================================================

GO_NOW_THRESHOLD       = 85
HIGH_SCORE_THRESHOLD   = 70
MEDIUM_SCORE_THRESHOLD = 55
CACHE_TTL_SECONDS      = 300   # 5 min cache på den tunge pipeline
DEFAULT_CITY           = "Horsens"

# Hvor meget afstand-fra-chauffør må trække fra zonens score (max-straf i pt)
DISTANCE_PENALTY_MAX   = 18
# Over denne afstand (km) gives fuld straf
DISTANCE_FULL_PENALTY  = 12.0


# =============================================================================
# OUTPUT-MODEL
# =============================================================================

@dataclass
class Recommendation:
    """Thranw's output – ét klart svar til chaufføren."""
    recommendation_text: str = ""
    zone_score:          int = 0
    zone_name:           str = ""
    reason:              str = ""
    expected_earnings_per_hour: int = 0
    expected_trips_per_hour:    float = 0.0
    go_now:              bool = False
    distance_km:         float = 0.0
    map_link:            str = ""
    weather_note:        str = ""
    event_note:          str = ""
    history_note:        str = ""
    confidence:          float = 0.0
    alternatives:        List[Dict[str, Any]] = field(default_factory=list)
    timestamp:           str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# =============================================================================
# HJÆLPERE
# =============================================================================

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Afstand i km mellem to GPS-punkter (Haversine)."""
    R = 6371.0
    dl = math.radians(lat2 - lat1)
    dg = math.radians(lon2 - lon1)
    a  = (math.sin(dl/2) ** 2
          + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
          * math.sin(dg/2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _distance_penalty(km: float) -> float:
    """Lineær straf 0..DISTANCE_PENALTY_MAX over 0..DISTANCE_FULL_PENALTY km."""
    if km <= 0:
        return 0.0
    if km >= DISTANCE_FULL_PENALTY:
        return DISTANCE_PENALTY_MAX
    return (km / DISTANCE_FULL_PENALTY) * DISTANCE_PENALTY_MAX


def _maps_link(orig_lat: float, orig_lng: float,
               dest_lat: float, dest_lng: float) -> str:
    return (f"https://www.google.com/maps/dir/?api=1"
            f"&origin={orig_lat},{orig_lng}"
            f"&destination={dest_lat},{dest_lng}"
            f"&travelmode=driving")


def _parse_iso(ts: Optional[str]) -> datetime:
    if not ts:
        return datetime.now()
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


# =============================================================================
# THRANW HOVEDAGENT
# =============================================================================

class ThranwAgent:
    """Orkestrerer dine eksisterende agenter og bygger ét klart svar."""

    def __init__(self, city: str = DEFAULT_CITY):
        self.city = city
        self._cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()

    # ── Pipeline med cache ────────────────────────────────────────────────────

    def _pipeline(self, city: str) -> Dict[str, Any]:
        """
        Kør DataAgent → AnalysisAgent → OpsAgent.
        Cache resultatet i CACHE_TTL_SECONDS for at skåne Render free tier.
        """
        now = datetime.now().timestamp()
        with self._cache_lock:
            cached = self._cache.get(city)
            if cached and (now - cached["t"]) < CACHE_TTL_SECONDS:
                return cached["data"]

        result: Dict[str, Any] = {"city": city, "ok": False}
        try:
            data = DataAgent().run(city)
        except Exception as e:
            logger.warning(f"[Thranw] DataAgent fejlede: {e}")
            data = {"city": city, "weather": {}, "events": [], "zones": [], "locations": {}}

        try:
            analysis = AnalysisAgent().run(data)
        except Exception as e:
            logger.warning(f"[Thranw] AnalysisAgent fejlede: {e}")
            analysis = {"scored_zones": [], "top_zones": [], "hotspots": [],
                        "history": {"status": "error"}}

        try:
            ops = OpsAgent().run(data, analysis)
        except Exception as e:
            logger.warning(f"[Thranw] OpsAgent fejlede: {e}")
            ops = {"earnings": {}, "driver_briefing": {}, "kpi": {}}

        result.update({
            "ok":       True,
            "data":     data,
            "analysis": analysis,
            "ops":      ops,
        })
        with self._cache_lock:
            self._cache[city] = {"t": now, "data": result}
        return result

    def invalidate_cache(self):
        with self._cache_lock:
            self._cache.clear()

    # ── HOVEDMETODE: anbefaling til chauffør ─────────────────────────────────

    def recommend(self, lat: float, lng: float,
                  current_time: Optional[str] = None,
                  city: Optional[str] = None) -> Recommendation:
        """Returnér ét klart svar baseret på chauffør-position."""
        when = _parse_iso(current_time)
        city = city or self.city

        pipe = self._pipeline(city)
        analysis = pipe.get("analysis", {})
        data     = pipe.get("data", {})
        ops      = pipe.get("ops", {})
        weather  = data.get("weather", {})
        events   = data.get("events", [])

        scored: List[Dict[str, Any]] = analysis.get("scored_zones", []) or []
        if not scored:
            return self._fallback(lat, lng, city, weather)

        # Re-rangér zoner ud fra (zone_score - distance_penalty)
        ranked: List[Tuple[Dict[str, Any], float, float]] = []
        for z in scored:
            zlat = z.get("lat", 0.0)
            zlon = z.get("lon", 0.0)
            dist = _haversine_km(lat, lng, zlat, zlon)
            adj  = z.get("score", 0) - _distance_penalty(dist)
            ranked.append((z, dist, adj))

        ranked.sort(key=lambda x: x[2], reverse=True)
        top_zone, top_dist, _ = ranked[0]

        # Earnings: brug zonens egen earn_dkk_hr (fra AnalysisAgent), ellers ops
        earn_per_hour = int(top_zone.get("earn_dkk_hr") or
                            ops.get("earnings", {}).get("earn_per_hour", 0) or 0)
        trips_per_hour = float(ops.get("earnings", {}).get("trips_per_hour", 0.0) or 0.0)

        score   = int(top_zone.get("score", 0))
        go_now  = score >= GO_NOW_THRESHOLD

        # Anbefalingstekst
        zone_up = top_zone.get("name", "Centrum").upper()
        if go_now:
            rec_text = f"⚡ KØR TIL {zone_up} NU"
        elif score >= HIGH_SCORE_THRESHOLD:
            rec_text = f"🔥 Kør mod {top_zone.get('name')} – høj efterspørgsel"
        elif score >= MEDIUM_SCORE_THRESHOLD:
            rec_text = f"📈 {top_zone.get('name')} – god mulighed"
        else:
            rec_text = f"📍 {top_zone.get('name')} – stabil/lav efterspørgsel"

        # Begrundelse: brug analysens reasons (top 3) + afstand
        reasons = top_zone.get("reasons", []) or []
        reasons_short = " · ".join(r for r in reasons[:3] if r)
        if top_dist > 0.3:
            reasons_short = (f"{top_dist:.1f} km væk · " + reasons_short).strip(" ·")

        # Vejrnote
        if weather.get("is_heavy_rain"):
            weather_note = f"Kraftig regn ({weather.get('precipitation', 0):.1f} mm/t) – maks efterspørgsel"
        elif weather.get("is_raining"):
            weather_note = f"Let regn ({weather.get('precipitation', 0):.1f} mm/t) – flere taxa-kunder"
        else:
            t = weather.get("temperature")
            weather_note = f"{t:.0f}°C, ingen regn" if isinstance(t, (int, float)) else "Vejrdata utilgængelig"

        # Eventnote
        near_events = top_zone.get("events_near", []) or []
        if near_events:
            ev = near_events[0]
            event_note = (f"{ev.get('name', 'Event')} – "
                          f"{ev.get('attendance', 0):,} gæster "
                          f"({ev.get('distance_km', 0):.1f} km)")
        elif events:
            event_note = f"{len(events)} event(s) i regionen i dag"
        else:
            event_note = "Ingen events i nærheden"

        # Historie-note
        hist = analysis.get("history", {}) or {}
        if hist.get("status") == "ok":
            history_note = (f"{hist.get('total_runs', 0)} kørsler i historik · "
                            f"regn-boost {hist.get('rain_boost', 0)} pt · "
                            f"bedste zone: {hist.get('best_zone', '?')}")
        else:
            history_note = "Ingen historik endnu – systemet lærer mens du kører"

        # Confidence (zone-niveau)
        conf_label = top_zone.get("confidence", "Lav")
        conf_score = {"Høj": 0.9, "Middel": 0.6, "Lav": 0.35}.get(conf_label, 0.5)

        # Alternativer (næste 3 zoner)
        alternatives = []
        for z, d, _adj in ranked[1:4]:
            alternatives.append({
                "zone":     z.get("name"),
                "score":    int(z.get("score", 0)),
                "distance_km": round(d, 1),
                "earn_dkk_hr": int(z.get("earn_dkk_hr", 0) or 0),
            })

        return Recommendation(
            recommendation_text=rec_text,
            zone_score=score,
            zone_name=top_zone.get("name", ""),
            reason=reasons_short or "Samlet analyse af zone, vejr, events og historik",
            expected_earnings_per_hour=earn_per_hour,
            expected_trips_per_hour=trips_per_hour,
            go_now=go_now,
            distance_km=round(top_dist, 2),
            map_link=_maps_link(lat, lng, top_zone.get("lat", lat), top_zone.get("lon", lng)),
            weather_note=weather_note,
            event_note=event_note,
            history_note=history_note,
            confidence=conf_score,
            alternatives=alternatives,
            timestamp=when.isoformat(),
        )

    # ── Alle zoner (til ejer-dashboard) ──────────────────────────────────────

    def score_all_zones(self, city: Optional[str] = None) -> Dict[str, Any]:
        city = city or self.city
        pipe = self._pipeline(city)
        analysis = pipe.get("analysis", {})
        zones = analysis.get("scored_zones", []) or []

        compact = []
        for z in zones:
            compact.append({
                "id":            z.get("id"),
                "name":          z.get("name"),
                "lat":           z.get("lat"),
                "lon":           z.get("lon"),
                "score":         int(z.get("score", 0)),
                "grade":         z.get("grade", ""),
                "is_hotspot":    bool(z.get("is_hotspot", False)),
                "earn_dkk_hr":   int(z.get("earn_dkk_hr", 0) or 0),
                "events_near":   len(z.get("events_near", []) or []),
                "recommendation": z.get("recommendation", ""),
                "confidence":    z.get("confidence", "Lav"),
            })
        compact.sort(key=lambda x: x["score"], reverse=True)

        top = compact[0] if compact else None
        return {
            "city":      city,
            "zones":     compact,
            "top_zone":  top["name"] if top else None,
            "top_score": top["score"] if top else 0,
            "history":   analysis.get("history", {}),
            "timestamp": datetime.now().isoformat(),
        }

    # ── Health ───────────────────────────────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        from pathlib import Path
        trips_csv = Path(_BACKEND).parent / "data" / "trips.csv"
        try:
            n_lines = sum(1 for _ in open(trips_csv, encoding="utf-8")) - 1 if trips_csv.exists() else 0
        except Exception:
            n_lines = 0

        try:
            hist = _history_summary()
        except Exception:
            hist = {"status": "error"}

        with self._cache_lock:
            cache_keys = list(self._cache.keys())

        return {
            "status":          "ok",
            "agent":           "thranw",
            "ready":           True,
            "city":            self.city,
            "trips_csv_rows":  n_lines,
            "history_status":  hist.get("status", "unknown"),
            "cache_cities":    cache_keys,
            "cache_ttl_sec":   CACHE_TTL_SECONDS,
            "go_now_threshold": GO_NOW_THRESHOLD,
            "timestamp":       datetime.now().isoformat(),
        }

    # ── Fallback hvis pipeline fejler totalt ─────────────────────────────────

    def _fallback(self, lat: float, lng: float, city: str, weather: dict) -> Recommendation:
        return Recommendation(
            recommendation_text=f"Kør mod {city} centrum – begrænset data lige nu",
            zone_score=50,
            zone_name=f"{city} Centrum",
            reason="Ingen scored zoner tilgængelige – systemet bruger fallback",
            expected_earnings_per_hour=200,
            expected_trips_per_hour=1.5,
            go_now=False,
            distance_km=0.0,
            map_link=f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
            weather_note="Vejrdata utilgængelig" if not weather else f"{weather.get('temperature','?')}°C",
            event_note="Ingen event-data",
            history_note="Ingen historik tilgængelig",
            confidence=0.3,
            alternatives=[],
        )


# =============================================================================
# CLI
# =============================================================================

def _cli():
    import argparse
    parser = argparse.ArgumentParser(
        description="Thranw – Zyflex Hovedagent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("Eksempler:\n"
                "  python thranw_agent.py --lat 55.86 --lng 9.85\n"
                "  python thranw_agent.py --lat 55.86 --lng 9.85 --json\n"
                "  python thranw_agent.py --health\n"
                "  python thranw_agent.py --all-zones\n")
    )
    parser.add_argument("--lat",  type=float, default=55.86)
    parser.add_argument("--lng",  type=float, default=9.85)
    parser.add_argument("--time", type=str,   default=None,
                        help="ISO-tidspunkt, fx 2026-05-06T19:45:00")
    parser.add_argument("--city", type=str,   default=DEFAULT_CITY)
    parser.add_argument("--json", action="store_true", help="Output som JSON")
    parser.add_argument("--health",    action="store_true")
    parser.add_argument("--all-zones", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    thranw = ThranwAgent(city=args.city)

    if args.health:
        print(json.dumps(thranw.health(), ensure_ascii=False, indent=2))
        return

    if args.all_zones:
        out = thranw.score_all_zones()
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return

    rec = thranw.recommend(args.lat, args.lng, args.time, city=args.city)

    if args.json:
        print(rec.to_json())
        return

    # Pæn dansk CLI-output
    print()
    print("=" * 64)
    print("  THRANW – ZYFLEX")
    print("=" * 64)
    print(f"  📍 {rec.recommendation_text}")
    print()
    print(f"  Zone:        {rec.zone_name}")
    print(f"  Score:       {rec.zone_score}/100")
    print(f"  Forventet:   {rec.expected_earnings_per_hour} kr/time "
          f"({rec.expected_trips_per_hour:.1f} ture/t)")
    print(f"  Afstand:     {rec.distance_km:.1f} km")
    print(f"  GO NOW:      {'JA ⚡' if rec.go_now else 'nej'}")
    print()
    print(f"  Begrundelse: {rec.reason}")
    print(f"  🌤️  {rec.weather_note}")
    print(f"  🎉 {rec.event_note}")
    print(f"  📊 {rec.history_note}")
    print(f"  Konfidens:   {rec.confidence * 100:.0f}%")
    if rec.alternatives:
        print()
        print("  Alternativer:")
        for a in rec.alternatives:
            print(f"    • {a['zone']:<30}  {a['score']:>3}/100  "
                  f"{a['distance_km']:>4.1f} km  ~{a['earn_dkk_hr']} kr/t")
    print()
    print(f"  Rute: {rec.map_link}")
    print(f"  Tid:  {rec.timestamp}")
    print("=" * 64)


if __name__ == "__main__":
    _cli()
