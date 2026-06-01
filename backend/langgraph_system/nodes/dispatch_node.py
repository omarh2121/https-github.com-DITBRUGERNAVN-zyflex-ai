# =============================================================================
# nodes/dispatch_node.py
#
# Zyflex AI – DispatchNode (LangGraph)
#
# Ansvar:
#   Det finale trin i pipelinen.
#   Kombinerer ALLE scores og producerer ét klart svar:
#
#   {
#     "zone": "Horsens Centrum",
#     "score": 92,
#     "reason": "CASA Arena koncert slutter om 20 min + kraftig regn"
#   }
#
# Dette er hvad chaufføren ser på skærmen.
# Score >= 85 → GO NOW (rød overlay + alarm)
# =============================================================================

from __future__ import annotations
import logging
import time
from datetime import datetime

from langgraph_system.state import ZyflexState
from langgraph_system.h3_zones import get_best_hex

logger = logging.getLogger("zyflex.langgraph.dispatch_node")


def dispatch_node(state: ZyflexState) -> ZyflexState:
    """
    LangGraph Node: DispatchNode

    Producerer den finale dispatch-anbefaling til chaufføren.

    Input fra state (alle foregående nodes):
        demand_top_zones, demand_h3_hexes, demand_hotspots
        weather_score, weather_reasons
        events_today, events_high_impact

    Output til state:
        dispatch_zone, dispatch_score, dispatch_reason,
        dispatch_grade, dispatch_earn_dkk, dispatch_h3_hex
        meta_completed_at
    """
    logger.info("[DispatchNode] Beregner final dispatch-anbefaling")
    t_start = time.time()

    errors: list[str] = list(state.get("meta_errors", []))
    node_times: dict = dict(state.get("meta_node_times", {}))

    try:
        top_zones       = state.get("demand_top_zones", [])
        h3_heatmap      = state.get("demand_h3_hexes", [])
        weather_score   = float(state.get("weather_score", 30))
        weather_reasons = state.get("weather_reasons", [])
        today_events    = state.get("events_today", [])
        high_events     = state.get("events_high_impact", [])

        # ── Vælg bedste zone ────────────────────────────────────────────────
        best_zone = top_zones[0] if top_zones else None
        zone_name = best_zone["name"] if best_zone else "Horsens Centrum"
        zone_score = best_zone["score"] if best_zone else 50

        # ── Beregn kombineret final score ───────────────────────────────────
        # Zone score er allerede kombineret. Vi kan lave en lille vejr-boost
        # oven på hvis vejret er ekstremt.
        final_score = zone_score
        if weather_score >= 80 and final_score < 90:
            final_score = min(100, final_score + 5)
        elif weather_score >= 60 and final_score < 80:
            final_score = min(100, final_score + 3)

        # ── Byg årsags-sætning ─────────────────────────────────────────────
        reason_parts = []

        # Tilføj events der sker nu/snart
        for evt in (today_events + high_events)[:2]:
            days = evt.get("days_until", 0)
            att  = evt.get("attendance", 0)
            name = evt.get("name", "")[:35]
            if days == 0:
                note = evt.get("taxi_note", "")
                if note:
                    reason_parts.append(f"{name} ({att:,} gæster)")
            elif days <= 1:
                reason_parts.append(f"{name} i morgen")

        # Tilføj vejr-årsag hvis relevant
        for wr in weather_reasons[:1]:
            if any(kw in wr for kw in ["regn", "frost", "Frost", "Regn", "Storm", "storm"]):
                # Kort version af vejr-årsagen
                short_weather = wr.split("–")[0].strip() if "–" in wr else wr[:40]
                reason_parts.append(short_weather)

        # Tilføj zone-egne årsager
        if best_zone:
            zone_reasons = best_zone.get("reasons", [])
            for r in zone_reasons[:1]:
                if r and len(r) < 60 and r not in reason_parts:
                    reason_parts.append(r)

        if reason_parts:
            reason = " · ".join(reason_parts[:3])
        else:
            grade = best_zone.get("grade", "") if best_zone else ""
            reason = f"{grade} – positionér nu"

        # ── Find bedste H3 hex ─────────────────────────────────────────────
        best_hex = get_best_hex(h3_heatmap)
        best_hex_id = best_hex["hex_id"] if best_hex else None

        # ── Earnings estimate ──────────────────────────────────────────────
        earn_dkk = best_zone.get("earn_dkk_hr", 0) if best_zone else 350

        # ── Grade ──────────────────────────────────────────────────────────
        grade = _score_grade(final_score)

        elapsed = round((time.time() - t_start) * 1000)
        node_times["dispatch_node"] = elapsed

        logger.info(
            f"[DispatchNode] ✅ → '{zone_name}' score={final_score} "
            f"grade='{grade}' earn={earn_dkk}kr/t, {elapsed}ms"
        )

        return {
            **state,
            "dispatch_zone":    zone_name,
            "dispatch_score":   int(final_score),
            "dispatch_reason":  reason,
            "dispatch_grade":   grade,
            "dispatch_earn_dkk": earn_dkk,
            "dispatch_h3_hex":  best_hex_id,
            "meta_completed_at": datetime.now().isoformat(),
            "meta_node_times":   node_times,
            "meta_errors":       errors,
        }

    except Exception as exc:
        elapsed = round((time.time() - t_start) * 1000)
        node_times["dispatch_node"] = elapsed
        err_msg = f"DispatchNode fejl: {exc}"
        logger.error(f"[DispatchNode] ❌ {err_msg}", exc_info=True)
        errors.append(err_msg)

        # Graceful fallback – returner noget brugbart
        return {
            **state,
            "dispatch_zone":     "Horsens Centrum",
            "dispatch_score":    50,
            "dispatch_reason":   "Fejl i pipeline – bruger standard anbefaling",
            "dispatch_grade":    "📍 Lav efterspørgsel",
            "dispatch_earn_dkk": 300,
            "dispatch_h3_hex":   None,
            "meta_completed_at": datetime.now().isoformat(),
            "meta_node_times":   node_times,
            "meta_errors":       errors,
        }


def _score_grade(score: int) -> str:
    if score >= 85: return "⚡ Ekstrem efterspørgsel"
    if score >= 70: return "🔥 Høj efterspørgsel"
    if score >= 55: return "📈 Middel efterspørgsel"
    if score >= 35: return "📍 Lav efterspørgsel"
    return "⚪ Meget lav"
