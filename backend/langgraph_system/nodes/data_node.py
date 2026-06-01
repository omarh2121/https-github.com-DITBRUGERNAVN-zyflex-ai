# =============================================================================
# nodes/data_node.py
#
# Zyflex AI – DataNode (LangGraph)
#
# Ansvar:
#   Wrapper om den eksisterende DataAgent.
#   Henter geocoding, vejr, events og zoner for en by.
#   Putter resultatet i ZyflexState så næste nodes kan bruge det.
#
# VIGTIGT: Ændrer INTET i DataAgent – kun wraps dens output.
#
# [2026-05-26] Billetto-patch:
#   Efter DataAgent.run(), hentes Billetto-events og merges ind i data_events.
#   Alt eksisterende røres IKKE. Deduplicering sker på (title, date, venue).
# =============================================================================

from __future__ import annotations
import logging
import sys
import os
import time
from datetime import datetime

# Gør backend-mappen tilgængelig for imports
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agents.data_agent import DataAgent
from langgraph_system.state import ZyflexState

# ── Billetto – primær dansk event-kilde ──────────────────────────────────────
# Soft-import: pipeline fortsætter normalt selv om Billetto ikke er tilgængeligt.
try:
    from live_data.events.billetto_source import fetch as _billetto_fetch
    _BILLETTO_AVAILABLE = True
except ImportError:
    _billetto_fetch      = None
    _BILLETTO_AVAILABLE  = False

logger = logging.getLogger("zyflex.langgraph.data_node")


def data_node(state: ZyflexState) -> ZyflexState:
    """
    LangGraph Node: DataNode

    Input fra state:
        input_city (str) – By der skal analyseres (default: "Horsens")

    Output til state:
        data_weather, data_events, data_zones, data_locations
        input_lat, input_lon (opdateret med faktisk geocodet position)

    Bruger eksisterende DataAgent internt – ingen ny logik.
    Billetto-events merges ind EFTER DataAgent uden at ændre DataAgent.
    """
    city = state.get("input_city", "Horsens")
    logger.info(f"[DataNode] Starter for '{city}'")
    t_start = time.time()

    errors: list[str] = list(state.get("meta_errors", []))
    node_times: dict = dict(state.get("meta_node_times", {}))

    try:
        # ── Kald den eksisterende DataAgent (UÆNDRET) ─────────────────────
        agent  = DataAgent()
        result = agent.run(city)

        base_events = result.get("events", [])

        # ── Billetto injection (MINIMAL PATCH) ────────────────────────────
        # Henter Billetto-events og merger med eksisterende events.
        # Deduplicering sker på (title, date, venue).
        billetto_events: list[dict] = []
        if _BILLETTO_AVAILABLE and _billetto_fetch:
            try:
                t_b = time.time()
                billetto_events = _billetto_fetch(city) or []
                b_ms = int((time.time() - t_b) * 1000)
                logger.info(
                    f"[DataNode] Billetto: {len(billetto_events)} events for '{city}' ({b_ms}ms)"
                )
            except Exception as b_exc:
                logger.warning(f"[DataNode] Billetto fejlede (ikke kritisk): {b_exc}")
                billetto_events = []

        merged_events = _merge_events(base_events, billetto_events)

        elapsed = round((time.time() - t_start) * 1000)
        node_times["data_node"] = elapsed

        sources = []
        if base_events:     sources.append(f"{len(base_events)} base")
        if billetto_events: sources.append(f"{len(billetto_events)} billetto")
        logger.info(
            f"[DataNode] ✅ Færdig på {elapsed}ms – "
            f"{len(merged_events)} events samlet ({', '.join(sources) or 'ingen'}), "
            f"{len(result.get('zones', []))} zoner"
        )

        return {
            **state,
            # Opdater input-koordinater med faktisk geocoded position
            "input_lat":       result.get("lat", state.get("input_lat", 55.8615)),
            "input_lon":       result.get("lon", state.get("input_lon", 9.8506)),
            # Data-output (events = merged base + billetto)
            "data_weather":    result.get("weather", {}),
            "data_events":     merged_events,
            "data_zones":      result.get("zones", []),
            "data_locations":  result.get("locations", {}),
            # Metadata
            "meta_node_times": node_times,
            "meta_errors":     errors,
        }

    except Exception as exc:
        elapsed = round((time.time() - t_start) * 1000)
        node_times["data_node"] = elapsed
        err_msg = f"DataNode fejl: {exc}"
        logger.error(f"[DataNode] ❌ {err_msg}", exc_info=True)
        errors.append(err_msg)

        # Returner state med tomme felter – pipeline fortsætter (graceful degradation)
        return {
            **state,
            "data_weather":    {},
            "data_events":     [],
            "data_zones":      [],
            "data_locations":  {},
            "meta_node_times": node_times,
            "meta_errors":     errors,
        }


def _merge_events(base: list[dict], billetto: list[dict]) -> list[dict]:
    """
    Merger base-events med Billetto-events.
    Deduplicerer på (title_lower, date, venue_lower).
    Base-events har prioritet (beholdes ved konflikt).
    """
    if not billetto:
        return base

    seen: set[tuple] = set()
    merged: list[dict] = []

    for evt in base:
        key = _event_key(evt)
        if key not in seen:
            seen.add(key)
            merged.append(evt)

    added = 0
    for evt in billetto:
        key = _event_key(evt)
        if key not in seen:
            seen.add(key)
            merged.append(evt)
            added += 1

    if added:
        logger.debug(f"[DataNode] Merge: {len(base)} base + {added} nye billetto = {len(merged)} total")

    return merged


def _event_key(evt: dict) -> tuple:
    """Lav en dedup-nøgle for et event."""
    title = (evt.get("title") or evt.get("name") or "").lower().strip()
    date  = evt.get("date", "")[:10]  # Kun YYYY-MM-DD
    venue = (evt.get("venue", "")).lower().strip()
    return (title, date, venue)
