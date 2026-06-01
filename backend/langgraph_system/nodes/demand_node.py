# =============================================================================
# nodes/demand_node.py
#
# Zyflex AI – DemandNode (LangGraph)
#
# Ansvar:
#   Kombinerer output fra WeatherNode + EventNode med den eksisterende
#   AnalysisAgent for at producere:
#   - Scorede zoner (0-100)
#   - H3 hex-baseret heatmap
#   - Top 5 zoner
#   - Hotspots (score >= 70)
#   - Optimal zone-kæde (rækkefølge at besøge)
#
# VIGTIGT: Kalder eksisterende AnalysisAgent for zone-scoring (uændret logik).
#          H3 heatmap er NYT – tilføjer hex-level granularitet.
# =============================================================================

from __future__ import annotations
import logging
import sys
import os
import time

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agents.analysis_agent import AnalysisAgent
from langgraph_system.state import ZyflexState
from langgraph_system.h3_zones import build_h3_heatmap

logger = logging.getLogger("zyflex.langgraph.demand_node")


def demand_node(state: ZyflexState) -> ZyflexState:
    """
    LangGraph Node: DemandNode

    Orkestrerer zone-scoring:
    1. Kald eksisterende AnalysisAgent med data fra state
    2. Byg H3 heatmap oven på zone-resultaterne
    3. Gem alt i state

    Input fra state:
        data_weather, data_events, data_zones, data_locations
        weather_modifier (fra WeatherNode)
        events_list (fra EventNode – berigede events)

    Output til state:
        demand_scored_zones, demand_top_zones, demand_hotspots,
        demand_avoid_zones, demand_h3_hexes, demand_zone_chain
    """
    logger.info("[DemandNode] Starter zone-scoring")
    t_start = time.time()

    errors: list[str] = list(state.get("meta_errors", []))
    node_times: dict = dict(state.get("meta_node_times", {}))

    try:
        # ── Forbered data-pakke til AnalysisAgent (eksisterende format) ──────
        data_package = {
            "city":      state.get("input_city", "Horsens"),
            "weather":   state.get("data_weather", {}),
            # Brug de berigede events fra EventNode (har mere info)
            "events":    state.get("events_list") or state.get("data_events", []),
            "zones":     state.get("data_zones", []),
            "locations": state.get("data_locations", {}),
        }

        # ── Kald eksisterende AnalysisAgent (UÆNDRET) ─────────────────────
        analysis = AnalysisAgent()
        result = analysis.run(data_package)

        scored_zones  = result.get("scored_zones", [])
        top_zones     = result.get("top_zones", [])
        hotspots      = result.get("hotspots", [])
        avoid_zones   = result.get("avoid_zones", [])
        zone_chain    = result.get("zone_chain", [])

        # ── Byg H3 heatmap ─────────────────────────────────────────────────
        # Brug zone-scorer som input til H3-scoring
        zone_scores_dict = {z["id"]: z["score"] for z in scored_zones}
        weather_mod = float(state.get("weather_modifier", 0.0))

        city_lat = state.get("input_lat", 55.8615)
        city_lon = state.get("input_lon", 9.8506)

        h3_heatmap = build_h3_heatmap(
            city_lat=city_lat,
            city_lon=city_lon,
            events=state.get("events_list") or state.get("data_events", []),
            zone_scores=zone_scores_dict,
            weather_modifier=weather_mod,
            radius_km=6.0,  # Dæk hele Horsens + omegn
        )

        elapsed = round((time.time() - t_start) * 1000)
        node_times["demand_node"] = elapsed
        logger.info(
            f"[DemandNode] ✅ {len(scored_zones)} zoner scoret, "
            f"{len(hotspots)} hotspots, "
            f"{len(h3_heatmap)} H3 hexes, "
            f"top: {top_zones[0]['name'] if top_zones else '?'} "
            f"({top_zones[0]['score'] if top_zones else 0}/100), "
            f"{elapsed}ms"
        )

        return {
            **state,
            "demand_scored_zones": scored_zones,
            "demand_top_zones":    top_zones,
            "demand_hotspots":     hotspots,
            "demand_avoid_zones":  avoid_zones,
            "demand_h3_hexes":     h3_heatmap,
            "demand_zone_chain":   zone_chain,
            "meta_node_times":     node_times,
            "meta_errors":         errors,
        }

    except Exception as exc:
        elapsed = round((time.time() - t_start) * 1000)
        node_times["demand_node"] = elapsed
        err_msg = f"DemandNode fejl: {exc}"
        logger.error(f"[DemandNode] ❌ {err_msg}", exc_info=True)
        errors.append(err_msg)

        return {
            **state,
            "demand_scored_zones": [],
            "demand_top_zones":    [],
            "demand_hotspots":     [],
            "demand_avoid_zones":  [],
            "demand_h3_hexes":     [],
            "demand_zone_chain":   [],
            "meta_node_times":     node_times,
            "meta_errors":         errors,
        }
