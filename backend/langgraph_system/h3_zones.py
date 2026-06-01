# =============================================================================
# langgraph_system/h3_zones.py
#
# Zyflex AI – Uber H3 Hexagonal Zone System
#
# Bruger Uber's H3 library til at opdele Danmark i hexagonale celler.
# Hvert hex-felt får en demand-score baseret på:
#   - Nærhed til kendte POI-zoner
#   - Events inden for hexet
#   - Historisk aktivitet (trips.csv)
#
# H3 Resolution valg:
#   Res 8  ≈  0.46 km² pr. hex  (ca. 500m diameter)  ← Vi bruger dette
#   Res 9  ≈  0.10 km² pr. hex  (ca. 200m diameter)
#
# Horsens centrum dækkes af ~25 hex-felter på res 8.
# =============================================================================

from __future__ import annotations
import math
import logging
from typing import Optional
import h3

logger = logging.getLogger(__name__)

# ── H3 Konfiguration ─────────────────────────────────────────────────────────
H3_RESOLUTION = 8          # ~500m hex-størrelse – perfekt til taxi-hotspots
H3_SEARCH_RADIUS_KM = 8.0  # Generer hexes inden for denne radius fra centrum

# ── Kendte Horsens POI-koordinater med base-scores ───────────────────────────
HORSENS_POI_WEIGHTS = {
    "centrum":    {"lat": 55.8608, "lon": 9.8502, "weight": 55},
    "station":    {"lat": 55.8641, "lon": 9.8438, "weight": 50},
    "sygehus":    {"lat": 55.8739, "lon": 9.8344, "weight": 45},
    "casa_arena": {"lat": 55.8572, "lon": 9.8614, "weight": 38},
    "havn":       {"lat": 55.8576, "lon": 9.8664, "weight": 33},
    "scandic":    {"lat": 55.8534, "lon": 9.8423, "weight": 38},
}


def get_hex_for_location(lat: float, lon: float) -> str:
    """Returner H3 hex-index for en GPS-koordinat."""
    return h3.latlng_to_cell(lat, lon, H3_RESOLUTION)


def get_hex_center(hex_id: str) -> tuple[float, float]:
    """Returner (lat, lon) for midtpunktet af en H3 hex."""
    lat, lon = h3.cell_to_latlng(hex_id)
    return lat, lon


def get_nearby_hexes(lat: float, lon: float, radius_km: float = H3_SEARCH_RADIUS_KM) -> list[str]:
    """
    Returner alle H3 hex-indexes inden for radius_km fra et punkt.
    Bruges til at generere heatmap-data for et by-område.
    """
    center_hex = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
    # Konverter km til H3 k-ring steps (approx 0.5km pr. step på res 8)
    k_steps = max(1, int(radius_km / 0.5))
    k_steps = min(k_steps, 20)  # Cap for performance
    nearby = h3.grid_disk(center_hex, k_steps)
    return list(nearby)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Beregn afstand i km mellem to GPS-punkter."""
    R = 6371.0
    dl = math.radians(lat2 - lat1)
    dg = math.radians(lon2 - lon1)
    a = (math.sin(dl / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dg / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def score_hex(
    hex_id: str,
    events: list[dict],
    zone_scores: dict[str, int],
    weather_modifier: float = 0.0,
) -> dict:
    """
    Beregn demand-score for ét H3 hex-felt.

    Scoring-logik:
    1. POI proximity score (baseret på kendte Horsens lokationer)
    2. Event proximity score (events inden for hexet eller nær det)
    3. Zone overlap score (fra eksisterende zone-scorer)
    4. Vejr-modifier (global – samme for alle hexes)

    Returns dict med hex-id, score, lat/lon og årsager.
    """
    hex_lat, hex_lon = get_hex_center(hex_id)
    reasons = []
    score = 0.0

    # ── 1. POI Proximity Score ──────────────────────────────────────────────
    poi_score = 0.0
    for poi_name, poi in HORSENS_POI_WEIGHTS.items():
        dist = haversine_km(hex_lat, hex_lon, poi["lat"], poi["lon"])
        if dist < 0.3:
            # Hex INDEHOLDER dette POI
            poi_score += poi["weight"]
            reasons.append(f"📍 {poi_name.replace('_', ' ').title()} ({poi['weight']}pt)")
        elif dist < 1.0:
            # Tæt på POI – distance-decay
            decay = 1.0 - (dist / 1.0)
            poi_score += poi["weight"] * decay * 0.6
        elif dist < 2.0:
            # Inden for 2km – svag effekt
            decay = 1.0 - (dist / 2.0)
            poi_score += poi["weight"] * decay * 0.2

    score += min(60, poi_score)

    # ── 2. Event Proximity Score ────────────────────────────────────────────
    event_score = 0.0
    for evt in events:
        evt_lat = evt.get("lat", hex_lat)
        evt_lon = evt.get("lon", hex_lon)
        dist = haversine_km(hex_lat, hex_lon, evt_lat, evt_lon)

        if dist > 5.0:
            continue

        att = evt.get("attendance", 300)
        base = min(40, att / 500 * 15)
        decay = max(0, 1.0 - dist / 3.0)
        pts = base * decay
        event_score += pts

        if pts > 2:
            reasons.append(f"🎉 {evt.get('name', 'Event')[:30]} ({dist:.1f}km)")

    score += min(35, event_score)

    # ── 3. Zone Overlap Score ───────────────────────────────────────────────
    best_zone_score = 0
    for zone_id, z_score in zone_scores.items():
        zone_poi = HORSENS_POI_WEIGHTS.get(zone_id)
        if not zone_poi:
            continue
        dist = haversine_km(hex_lat, hex_lon, zone_poi["lat"], zone_poi["lon"])
        if dist < 0.8:
            overlap = z_score * (1.0 - dist / 0.8) * 0.15
            best_zone_score = max(best_zone_score, overlap)

    score += min(20, best_zone_score)

    # ── 4. Vejr-modifier (global) ───────────────────────────────────────────
    if weather_modifier > 0:
        score += weather_modifier * 0.1
        if weather_modifier > 10:
            reasons.append(f"🌧 Vejr booster score")

    final_score = min(100, max(0, round(score)))

    return {
        "hex_id":   hex_id,
        "lat":      round(hex_lat, 6),
        "lon":      round(hex_lon, 6),
        "score":    final_score,
        "is_hot":   final_score >= 70,
        "grade":    _hex_grade(final_score),
        "reasons":  reasons[:3],  # Max 3 årsager for performance
    }


def build_h3_heatmap(
    city_lat: float,
    city_lon: float,
    events: list[dict],
    zone_scores: dict[str, int],
    weather_modifier: float = 0.0,
    radius_km: float = H3_SEARCH_RADIUS_KM,
) -> list[dict]:
    """
    Byg et komplet H3 heatmap for et byområde.

    Returns liste af hex-dicts sorteret efter score (højest først).
    Bruges til:
    - /ai/hotspots endpoint (top 5)
    - Frontend heatmap overlay
    - Demand prediction
    """
    logger.info(f"[H3] Genererer heatmap – radius {radius_km}km, res {H3_RESOLUTION}")

    hexes = get_nearby_hexes(city_lat, city_lon, radius_km)
    logger.info(f"[H3] {len(hexes)} hex-felter genereret")

    scored = []
    for hex_id in hexes:
        try:
            result = score_hex(hex_id, events, zone_scores, weather_modifier)
            scored.append(result)
        except Exception as e:
            logger.debug(f"[H3] Fejl på hex {hex_id}: {e}")
            continue

    # Sorter: hotspots øverst
    scored.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"[H3] Top hex: score={scored[0]['score'] if scored else 0}")

    return scored


def get_best_hex(heatmap: list[dict]) -> Optional[dict]:
    """Returner hex-feltet med højeste score."""
    if not heatmap:
        return None
    return heatmap[0]


def _hex_grade(score: int) -> str:
    if score >= 85: return "⚡ Ekstrem"
    if score >= 70: return "🔥 Høj"
    if score >= 55: return "📈 Middel"
    if score >= 35: return "📍 Lav"
    return "⚪ Meget lav"
