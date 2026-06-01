"""
telemetry_router.py – Zyflex Demand Radar
Endpoints til driver telemetry og feedback.

Routes:
  POST /api/telemetry/view
  POST /api/telemetry/recommendation-shown
  POST /api/telemetry/action
  POST /api/telemetry/feedback
  GET  /api/telemetry/stats   → ejer-dashboard analytics
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from db import (
    insert_driver_event,
    insert_recommendation,
    insert_feedback,
    get_telemetry_stats,
    init_db,
)

logger = logging.getLogger("telemetry")
router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

# ── Gyldige event-typer ───────────────────────────────────────────────────────
VALID_ACTION_TYPES = {
    "view_dashboard",
    "click_drive_here",
    "click_wait_here",
    "click_good_later",
    "click_avoid",
    "mark_arrived",
    "mark_left_zone",
    "report_got_trip",
    "report_no_trip",
    "report_good_recommendation",
    "report_bad_recommendation",
    "click_sales_action",
}

# ── Pydantic modeller ─────────────────────────────────────────────────────────
class ViewPayload(BaseModel):
    driver_id:            Optional[str] = None
    anonymous_session_id: Optional[str] = None
    city:                 str           = "Horsens"
    top_zone:             Optional[str] = None
    top_zone_id:          Optional[str] = None
    top_score:            Optional[int] = None

class RecommendationShownPayload(BaseModel):
    recommendation_id:    Optional[str] = None   # client-side ID (kan overskrives)
    driver_id:            Optional[str] = None
    anonymous_session_id: Optional[str] = None
    zone_id:              str
    zone_name:            str
    score:                int
    action_text:          str
    reason:               Optional[str] = ""

class ActionPayload(BaseModel):
    driver_id:            Optional[str] = None
    anonymous_session_id: Optional[str] = None
    action_type:          str
    zone_id:              Optional[str] = None
    recommendation_id:    Optional[str] = None
    metadata:             Optional[dict] = Field(default_factory=dict)

class FeedbackPayload(BaseModel):
    driver_id:            Optional[str] = None
    anonymous_session_id: Optional[str] = None
    recommendation_id:    Optional[str] = None
    rating:               Optional[str] = None   # good, bad
    got_trip:             Optional[bool] = None
    comment:              Optional[str] = ""

# ── Helper ────────────────────────────────────────────────────────────────────
def _session(payload) -> tuple[Optional[str], Optional[str]]:
    """Returnerer (driver_id, anon_id). Mindst ét skal være sat."""
    return payload.driver_id or None, payload.anonymous_session_id or None

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/view")
async def track_view(payload: ViewPayload):
    """Log at chauffør åbnede /driver-event."""
    try:
        driver_id, anon_id = _session(payload)
        if not driver_id and not anon_id:
            return JSONResponse({"error": "driver_id eller anonymous_session_id krævet"}, status_code=400)

        event_id = insert_driver_event(
            event_type           = "view_dashboard",
            driver_id            = driver_id,
            anonymous_session_id = anon_id,
            zone_id              = payload.top_zone_id,
            metadata             = {
                "city":      payload.city,
                "top_zone":  payload.top_zone,
                "top_score": payload.top_score,
            },
        )
        logger.info(f"[view] session={anon_id or driver_id} zone={payload.top_zone} score={payload.top_score}")
        return {"status": "ok", "event_id": event_id}
    except Exception as e:
        logger.error(f"view fejl: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/recommendation-shown")
async def track_recommendation_shown(payload: RecommendationShownPayload):
    """Log at en anbefaling blev vist til chauffør."""
    try:
        driver_id, anon_id = _session(payload)
        rec_id = insert_recommendation(
            zone_id              = payload.zone_id,
            score                = payload.score,
            action_text          = payload.action_text,
            reason               = payload.reason or "",
            driver_id            = driver_id,
            anonymous_session_id = anon_id,
        )
        logger.info(f"[rec-shown] zone={payload.zone_name} score={payload.score}")
        return {"status": "ok", "recommendation_id": rec_id}
    except Exception as e:
        logger.error(f"recommendation-shown fejl: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/action")
async def track_action(payload: ActionPayload):
    """Log en chauffør-handling (knapklik, ankomst, etc.)."""
    if payload.action_type not in VALID_ACTION_TYPES:
        return JSONResponse(
            {"error": f"Ugyldig action_type. Gyldige: {sorted(VALID_ACTION_TYPES)}"},
            status_code=400,
        )
    try:
        driver_id, anon_id = _session(payload)
        if not driver_id and not anon_id:
            return JSONResponse({"error": "driver_id eller anonymous_session_id krævet"}, status_code=400)

        event_id = insert_driver_event(
            event_type           = payload.action_type,
            driver_id            = driver_id,
            anonymous_session_id = anon_id,
            zone_id              = payload.zone_id,
            recommendation_id    = payload.recommendation_id,
            metadata             = payload.metadata or {},
        )
        logger.info(f"[action] type={payload.action_type} zone={payload.zone_id} session={anon_id or driver_id}")
        return {"status": "ok", "event_id": event_id}
    except Exception as e:
        logger.error(f"action fejl: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/feedback")
async def track_feedback(payload: FeedbackPayload):
    """Log feedback fra chauffør (fik tur / ingen tur / god/dårlig anbefaling)."""
    if payload.rating and payload.rating not in ("good", "bad"):
        return JSONResponse({"error": "rating skal være 'good' eller 'bad'"}, status_code=400)
    try:
        driver_id, anon_id = _session(payload)
        if not driver_id and not anon_id:
            return JSONResponse({"error": "driver_id eller anonymous_session_id krævet"}, status_code=400)

        feedback_id = insert_feedback(
            rating               = payload.rating,
            got_trip             = payload.got_trip,
            driver_id            = driver_id,
            anonymous_session_id = anon_id,
            recommendation_id    = payload.recommendation_id,
            comment              = payload.comment or "",
        )

        # Log også som driver_event for enkel aggregering
        action = "report_got_trip" if payload.got_trip else (
                 "report_no_trip" if payload.got_trip is False else (
                 "report_good_recommendation" if payload.rating == "good" else
                 "report_bad_recommendation"))
        insert_driver_event(
            event_type           = action,
            driver_id            = driver_id,
            anonymous_session_id = anon_id,
            recommendation_id    = payload.recommendation_id,
            metadata             = {"rating": payload.rating, "got_trip": payload.got_trip},
        )

        logger.info(f"[feedback] rating={payload.rating} got_trip={payload.got_trip} session={anon_id or driver_id}")
        return {"status": "ok", "feedback_id": feedback_id}
    except Exception as e:
        logger.error(f"feedback fejl: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/stats")
async def get_stats():
    """Aggregerede telemetri-stats til ejer-dashboard."""
    try:
        stats = get_telemetry_stats()
        return stats
    except Exception as e:
        logger.error(f"stats fejl: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
