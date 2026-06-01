# =============================================================================
# langgraph_system/state.py
#
# Zyflex AI – Delt tilstand (State) for LangGraph workflow
#
# ZyflexState flyder igennem alle nodes i pipelinen:
#   DataNode → WeatherNode → EventNode → DemandNode → DispatchNode
#
# Hvert node tilføjer sine resultater til state-dicten.
# LangGraph sender den opdaterede state videre til næste node.
# =============================================================================

from __future__ import annotations
from typing import TypedDict, Optional, Any


class ZyflexState(TypedDict, total=False):
    """
    Komplet delt tilstand for Zyflex AI dispatch-pipeline.

    Feltnavne er gruppereret logisk:
    - input_*     : Input-parametre til pipelinen
    - data_*      : Rå data fra DataNode
    - weather_*   : Vejr-analyse fra WeatherNode
    - events_*    : Event-data fra EventNode
    - demand_*    : Zone-scoring fra DemandNode (inkl. H3)
    - dispatch_*  : Final anbefaling fra DispatchNode
    - leads_*     : B2B leads fra ContractHunterNode
    - meta_*      : Pipeline-metadata (tidsstempler, fejl, etc.)
    """

    # ── Input ──────────────────────────────────────────────────────────────
    input_city: str                    # By der analyseres (default: "Horsens")
    input_lat: float                   # Breddegrad for byen
    input_lon: float                   # Længdegrad for byen

    # ── Data (fra DataNode / eksisterende DataAgent) ──────────────────────
    data_weather: dict[str, Any]       # Rå vejrdata fra Open-Meteo
    data_events: list[dict]            # Events fra alle kilder (local + TM + live)
    data_zones: list[dict]             # Geografiske zoner for byen
    data_locations: dict[str, Any]     # POI-data pr. zone

    # ── Vejr (fra WeatherNode) ────────────────────────────────────────────
    weather_score: float               # 0-100 vejr-impact score
    weather_reasons: list[str]         # Forklaringer (fx "🌧 Kraftig regn")
    weather_modifier: float            # Samlet score-modifier til zone-scoring

    # ── Events (fra EventNode) ────────────────────────────────────────────
    events_list: list[dict]            # Alle relevante events (berigede)
    events_count: int                  # Antal events
    events_today: list[dict]           # Kun events i dag
    events_high_impact: list[dict]     # Events med attendance > 1000

    # ── Demand / Zone-scoring (fra DemandNode) ────────────────────────────
    demand_scored_zones: list[dict]    # Alle zoner med scores
    demand_top_zones: list[dict]       # Top 5 zoner
    demand_hotspots: list[dict]        # Zoner med score >= 70
    demand_avoid_zones: list[dict]     # Zoner med score < 35
    demand_h3_hexes: list[dict]        # H3 hex-celler med scores (heatmap)
    demand_zone_chain: list[str]       # Optimal rækkefølge at besøge zoner

    # ── Dispatch / Final anbefaling (fra DispatchNode) ────────────────────
    dispatch_zone: str                 # Bedste zone (navn)
    dispatch_score: int                # Score 0-100
    dispatch_reason: str               # Forklaring i ét klart sætning
    dispatch_grade: str                # "⚡ Ekstrem" / "🔥 Høj" / "📈 Middel" etc.
    dispatch_earn_dkk: int             # Estimeret DKK/time
    dispatch_h3_hex: Optional[str]     # H3 hex-index for bedste zone

    # ── Leads (fra ContractHunterNode – køres separat) ───────────────────
    leads_all: list[dict]              # Alle fundne leads
    leads_top: list[dict]              # Top 10 højst scorede leads
    leads_monthly_pot_dkk: int         # Potentiel månedlig omsætning fra leads

    # ── Pipeline Metadata ─────────────────────────────────────────────────
    meta_started_at: str               # ISO timestamp da pipeline startede
    meta_completed_at: str             # ISO timestamp da pipeline sluttede
    meta_errors: list[str]             # Eventuelle fejl (non-fatal)
    meta_node_times: dict[str, float]  # Millisekunder pr. node (performance)
    meta_version: str                  # Pipeline version
