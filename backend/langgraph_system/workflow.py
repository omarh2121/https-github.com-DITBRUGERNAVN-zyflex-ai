# =============================================================================
# langgraph_system/workflow.py
#
# Zyflex AI – LangGraph Dispatch Workflow
#
# Definerer den officielle multi-agent pipeline:
#
#   DataNode
#     ↓
#   WeatherNode   (parallelt med EventNode i teorien, men sequential her)
#     ↓
#   EventNode
#     ↓
#   DemandNode    (zone-scoring + H3 heatmap)
#     ↓
#   DispatchNode  (final anbefaling)
#
# Separat pipeline:
#   ContractHunterNode  (køres via /ai/leads – ikke del af hoved-pipeline)
#
# Brug:
#   from langgraph_system import run_dispatch_workflow
#   result = run_dispatch_workflow("Horsens")
# =============================================================================

from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import Optional

from langgraph.graph import StateGraph, END

from langgraph_system.state import ZyflexState
from langgraph_system.nodes import (
    data_node,
    weather_node,
    event_node,
    demand_node,
    dispatch_node,
    contract_hunter_node,
)

logger = logging.getLogger("zyflex.langgraph.workflow")

# ── Pipeline version ──────────────────────────────────────────────────────────
PIPELINE_VERSION = "2.0.0-langgraph"


def build_workflow() -> StateGraph:
    """
    Byg og kompilér LangGraph dispatch-workflow.

    Returnerer et kompileret graph-objekt klar til at køre.
    Kald én gang ved opstart og genbrug det.
    """
    graph = StateGraph(ZyflexState)

    # ── Registrer nodes ───────────────────────────────────────────────────
    graph.add_node("data",     data_node)
    graph.add_node("weather",  weather_node)
    graph.add_node("events",   event_node)
    graph.add_node("demand",   demand_node)
    graph.add_node("dispatch", dispatch_node)

    # ── Definer pipeline-flow ─────────────────────────────────────────────
    # DataNode → WeatherNode → EventNode → DemandNode → DispatchNode → END
    graph.set_entry_point("data")
    graph.add_edge("data",     "weather")
    graph.add_edge("weather",  "events")
    graph.add_edge("events",   "demand")
    graph.add_edge("demand",   "dispatch")
    graph.add_edge("dispatch", END)

    compiled = graph.compile()
    logger.info(f"[Workflow] LangGraph dispatch-pipeline bygget (v{PIPELINE_VERSION})")
    return compiled


def build_leads_workflow() -> StateGraph:
    """
    Separat workflow kun til lead-generering.
    Kør via /ai/leads endpoint.
    """
    graph = StateGraph(ZyflexState)
    graph.add_node("contract_hunter", contract_hunter_node)
    graph.set_entry_point("contract_hunter")
    graph.add_edge("contract_hunter", END)
    return graph.compile()


# ── Singleton workflow-instanser (opret én gang, genbrug) ─────────────────────
_dispatch_workflow: Optional[StateGraph] = None
_leads_workflow: Optional[StateGraph]    = None


def _get_dispatch_workflow() -> StateGraph:
    global _dispatch_workflow
    if _dispatch_workflow is None:
        _dispatch_workflow = build_workflow()
    return _dispatch_workflow


def _get_leads_workflow() -> StateGraph:
    global _leads_workflow
    if _leads_workflow is None:
        _leads_workflow = build_leads_workflow()
    return _leads_workflow


def run_dispatch_workflow(city: str = "Horsens") -> dict:
    """
    Kør den komplette dispatch-pipeline for en by.

    Returnerer det endelige ZyflexState som dict.
    Bruges af /ai/recommendation og /ai/hotspots endpoints.

    Args:
        city: Bynavn (default: "Horsens")

    Returns:
        Komplet state dict med alle pipeline-resultater.
    """
    logger.info(f"[Workflow] Kører dispatch-pipeline for '{city}'")
    t_start = time.time()

    # Initialisér state
    initial_state: ZyflexState = {
        "input_city":      city,
        "input_lat":       55.8615,   # Horsens fallback
        "input_lon":       9.8506,
        "meta_started_at": datetime.now().isoformat(),
        "meta_errors":     [],
        "meta_node_times": {},
        "meta_version":    PIPELINE_VERSION,
    }

    try:
        workflow = _get_dispatch_workflow()
        final_state = workflow.invoke(initial_state)

        elapsed_total = round((time.time() - t_start) * 1000)
        logger.info(
            f"[Workflow] ✅ Pipeline færdig på {elapsed_total}ms – "
            f"zone='{final_state.get('dispatch_zone')}' "
            f"score={final_state.get('dispatch_score')}"
        )

        # Tilføj total pipeline-tid
        if "meta_node_times" in final_state:
            final_state["meta_node_times"]["total"] = elapsed_total

        return final_state

    except Exception as exc:
        elapsed_total = round((time.time() - t_start) * 1000)
        logger.error(f"[Workflow] ❌ Pipeline fejlede på {elapsed_total}ms: {exc}", exc_info=True)

        # Returner en minimal fallback-state
        return {
            **initial_state,
            "dispatch_zone":     "Horsens Centrum",
            "dispatch_score":    50,
            "dispatch_reason":   f"Pipeline fejl: {str(exc)[:80]}",
            "dispatch_grade":    "⚠️ Fejl – fallback",
            "dispatch_earn_dkk": 300,
            "demand_top_zones":  [],
            "demand_hotspots":   [],
            "demand_h3_hexes":   [],
            "meta_errors":       [str(exc)],
            "meta_completed_at": datetime.now().isoformat(),
            "meta_node_times":   {"total": elapsed_total},
        }


def run_leads_workflow(city: str = "Horsens") -> dict:
    """
    Kør lead-generering workflow.
    Bruges af /ai/leads endpoint.
    """
    logger.info(f"[Workflow] Kører leads-pipeline for '{city}'")

    initial_state: ZyflexState = {
        "input_city":      city,
        "meta_started_at": datetime.now().isoformat(),
        "meta_errors":     [],
        "meta_node_times": {},
        "meta_version":    PIPELINE_VERSION,
    }

    try:
        workflow = _get_leads_workflow()
        return workflow.invoke(initial_state)
    except Exception as exc:
        logger.error(f"[Workflow] Leads-pipeline fejl: {exc}", exc_info=True)
        return {
            **initial_state,
            "leads_all":             [],
            "leads_top":             [],
            "leads_monthly_pot_dkk": 0,
            "meta_errors":           [str(exc)],
        }
