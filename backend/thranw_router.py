# =============================================================================
# thranw_router.py – FastAPI router for Thranw
#
# Endpoints:
#   POST /api/thranw/recommend  – chauffør får ét klart svar
#   GET  /api/thranw/zones      – alle zoner (til ejer-dashboard)
#   GET  /api/thranw/health     – system health
#
# Inkluderes i main.py med:
#   from thranw_router import router as thranw_router
#   app.include_router(thranw_router)
# =============================================================================

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.thranw_agent import ThranwAgent

logger = logging.getLogger("thranw.router")

router = APIRouter(prefix="/api/thranw", tags=["Thranw"])

# Singleton – ÉN agent-instans deles, så cachen bevares
_agent: Optional[ThranwAgent] = None


def _get_agent() -> ThranwAgent:
    global _agent
    if _agent is None:
        _agent = ThranwAgent()
    return _agent


# ── Pydantic-modeller ────────────────────────────────────────────────────────

class RecommendRequest(BaseModel):
    lat: float = Field(..., ge=-90,  le=90,  description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")
    current_time: Optional[str] = Field(
        default=None,
        description="ISO-8601 tidspunkt – fx 2026-05-06T19:45:00",
    )
    city: Optional[str] = Field(default=None, description="By (default: Horsens)")


class AlternativeZone(BaseModel):
    zone: str
    score: int
    distance_km: float
    earn_dkk_hr: int


class RecommendResponse(BaseModel):
    recommendation_text: str
    zone_score: int
    zone_name: str
    reason: str
    expected_earnings_per_hour: int
    expected_trips_per_hour: float
    go_now: bool
    distance_km: float
    map_link: str
    weather_note: str
    event_note: str
    history_note: str
    confidence: float
    alternatives: List[AlternativeZone]
    timestamp: str


class ZoneInfo(BaseModel):
    id:             Optional[str] = None
    name:           Optional[str] = None
    lat:            Optional[float] = None
    lon:            Optional[float] = None
    score:          int = 0
    grade:          str = ""
    is_hotspot:     bool = False
    earn_dkk_hr:    int = 0
    events_near:    int = 0
    recommendation: str = ""
    confidence:     str = "Lav"


class AllZonesResponse(BaseModel):
    city:      str
    zones:     List[ZoneInfo]
    top_zone:  Optional[str]
    top_score: int
    history:   Dict[str, Any] = {}
    timestamp: str


class HealthResponse(BaseModel):
    status:            str
    agent:             str
    ready:             bool
    city:              str
    trips_csv_rows:    int
    history_status:    str
    cache_cities:      List[str]
    cache_ttl_sec:     int
    go_now_threshold:  int
    timestamp:         str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/recommend", response_model=RecommendResponse,
             summary="Hent anbefaling: hvor skal chaufføren køre nu?")
async def recommend(body: RecommendRequest) -> RecommendResponse:
    try:
        agent = _get_agent()
        rec = agent.recommend(
            lat=body.lat,
            lng=body.lng,
            current_time=body.current_time,
            city=body.city or agent.city,
        )
        return RecommendResponse(
            recommendation_text=rec.recommendation_text,
            zone_score=rec.zone_score,
            zone_name=rec.zone_name,
            reason=rec.reason,
            expected_earnings_per_hour=rec.expected_earnings_per_hour,
            expected_trips_per_hour=rec.expected_trips_per_hour,
            go_now=rec.go_now,
            distance_km=rec.distance_km,
            map_link=rec.map_link,
            weather_note=rec.weather_note,
            event_note=rec.event_note,
            history_note=rec.history_note,
            confidence=rec.confidence,
            alternatives=[AlternativeZone(**a) for a in rec.alternatives],
            timestamp=rec.timestamp,
        )
    except Exception as e:
        logger.exception("Thranw recommend fejl")
        raise HTTPException(status_code=500, detail=f"Thranw fejl: {e}")


@router.get("/zones", response_model=AllZonesResponse,
            summary="Score for alle zoner – til ejer-dashboard")
async def all_zones(city: Optional[str] = None) -> AllZonesResponse:
    try:
        agent = _get_agent()
        out = agent.score_all_zones(city=city)
        return AllZonesResponse(
            city=out.get("city", "Horsens"),
            zones=[ZoneInfo(**z) for z in out.get("zones", [])],
            top_zone=out.get("top_zone"),
            top_score=int(out.get("top_score", 0)),
            history=out.get("history", {}) or {},
            timestamp=out.get("timestamp", datetime.now().isoformat()),
        )
    except Exception as e:
        logger.exception("Thranw zones fejl")
        raise HTTPException(status_code=500, detail=f"Thranw fejl: {e}")


@router.get("/health", response_model=HealthResponse,
            summary="Health check – tjek at Thranw er klar")
async def health() -> HealthResponse:
    try:
        agent = _get_agent()
        return HealthResponse(**agent.health())
    except Exception as e:
        logger.exception("Thranw health fejl")
        raise HTTPException(status_code=500, detail=f"Health fejl: {e}")


@router.post("/cache/invalidate", summary="Tøm Thranw cache (manuel refresh)")
async def invalidate_cache() -> Dict[str, str]:
    _get_agent().invalidate_cache()
    return {"status": "ok", "message": "Cache tømt"}
