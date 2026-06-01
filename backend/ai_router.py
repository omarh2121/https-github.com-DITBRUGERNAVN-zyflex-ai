# =============================================================================
# ai_router.py – Zyflex AI LangGraph Endpoints
#
# NYE endpoints der bruger det nye LangGraph multi-agent system.
# Eksisterende endpoints i main.py røres IKKE.
#
# Endpoints:
#   GET /ai/recommendation  → Bedste zone + årsag (til chauffør)
#   GET /ai/hotspots        → Top 5 hotspot-zoner
#   GET /ai/heatmap         → H3 hex heatmap data (til kort)
#   GET /ai/leads           → B2B contract leads (kører separat workflow)
#   GET /ai/pipeline/status → Pipeline metadata (timing, fejl)
# =============================================================================

import logging
import asyncio
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, BackgroundTasks
from fastapi.responses import JSONResponse

# ── Anbefalings-logger ────────────────────────────────────────────────────────
_LOG_DIR  = Path(__file__).parent.parent / "data"
_LOG_FILE = _LOG_DIR / "ai_recommendations.jsonl"

def _log_recommendation(rec: dict, city: str, cached: bool):
    """
    Gemmer hver AI-anbefaling til data/ai_recommendations.jsonl.
    Ét JSON-objekt pr. linje – nem import til Pandas/Excel efterfølgende.

    Felter gemt:
      ts, city, zone, score, go_now, earn_dkk, weather_temp, weather_rain,
      events_today, pipeline_errors, cached
    """
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts":              datetime.now().isoformat(timespec="seconds"),
            "city":            city,
            "zone":            rec.get("recommended_zone", ""),
            "score":           rec.get("score", 0),
            "grade":           rec.get("grade", ""),
            "go_now":          rec.get("go_now", False),
            "earn_dkk":        rec.get("earn_dkk_per_hour", 0),
            "weather_temp":    rec.get("weather", {}).get("temp_c", None),
            "weather_rain_mm": rec.get("weather", {}).get("precip_mm", None),
            "weather_wind":    rec.get("weather", {}).get("wind_kmh", None),
            "is_raining":      rec.get("weather", {}).get("is_raining", False),
            "events_today":    len(rec.get("events_today", [])),
            "top_zone_2":      rec.get("top_zones", [{}])[1].get("zone", "") if len(rec.get("top_zones", [])) > 1 else "",
            "top_zone_2_score":rec.get("top_zones", [{}])[1].get("score", 0)  if len(rec.get("top_zones", [])) > 1 else 0,
            "errors":          len(rec.get("pipeline_errors", [])),
            "cached":          cached,
        }
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[Logger] Kunne ikke skrive til log: {e}")

# Importer LangGraph workflow
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Billetto source (soft-import)
try:
    from live_data.events.billetto_source import get_source_status as _billetto_status
    _BILLETTO_IMPORT_OK = True
except ImportError:
    _billetto_status    = None
    _BILLETTO_IMPORT_OK = False

from langgraph_system.workflow import run_dispatch_workflow, run_leads_workflow

logger = logging.getLogger("zyflex.ai_router")

# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/ai", tags=["AI LangGraph"])

# ── Simple in-memory cache (TTL: 5 minutter) ─────────────────────────────────
# Undgår at køre hele pipelinen ved hvert request.
# Pipelinen tager ~2-4 sek – caching giver <50ms response.
_cache: dict = {}
_CACHE_TTL_SEC = 300   # 5 minutter


def _cache_key(city: str) -> str:
    # Ny cache-nøgle hvert 5. minut pr. by
    bucket = int(datetime.now().timestamp() // _CACHE_TTL_SEC)
    return f"{city.lower()}:{bucket}"


def _get_cached(city: str) -> Optional[dict]:
    key = _cache_key(city)
    entry = _cache.get(key)
    if entry:
        logger.debug(f"[Cache] HIT for '{city}'")
        return entry
    return None


def _set_cache(city: str, data: dict):
    # Ryd gamle entries (simpel GC)
    current_key = _cache_key(city)
    stale_keys = [k for k in list(_cache.keys()) if k != current_key]
    for k in stale_keys:
        _cache.pop(k, None)
    _cache[current_key] = data
    logger.debug(f"[Cache] SET for '{city}'")


# =============================================================================
# GET /ai/recommendation
# =============================================================================

@router.get("/recommendation")
async def get_ai_recommendation(
    city: str = Query(default="Horsens", description="By at analysere"),
    fresh: bool = Query(default=False,   description="Ignorer cache og kør ny pipeline"),
):
    """
    Returnerer AI's bedste dispatch-anbefaling til chaufføren.

    Kører LangGraph pipeline: Data → Vejr → Events → Demand → Dispatch

    Response:
    {
      "recommended_zone": "Horsens Centrum",
      "score": 92,
      "reason": "CASA Arena koncert slutter om 20 min + kraftig regn",
      "grade": "⚡ Ekstrem efterspørgsel",
      "earn_dkk_per_hour": 620,
      "go_now": true,
      "h3_hex": "881f1d4a09fffff",
      "top_zones": [...],
      "timestamp": "2026-05-25T14:32:00"
    }
    """
    logger.info(f"[/ai/recommendation] city='{city}' fresh={fresh}")

    # Tjek cache (medmindre fresh=true)
    if not fresh:
        cached_data = _get_cached(city)
        if cached_data:
            _log_recommendation(cached_data, city, cached=True)
            return {**cached_data, "cached": True}

    try:
        # Kør LangGraph pipeline (synkront i thread-pool for ikke at blokere event loop)
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(None, run_dispatch_workflow, city)

        response = _build_recommendation_response(state)
        _set_cache(city, response)
        _log_recommendation(response, city, cached=False)
        return {**response, "cached": False}

    except Exception as exc:
        logger.error(f"[/ai/recommendation] Fejl: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error":   "Pipeline fejlede",
                "detail":  str(exc),
                "fallback": {
                    "recommended_zone": f"{city} Centrum",
                    "score":  50,
                    "reason": "Fejl i AI-pipeline – bruger standard anbefaling",
                    "grade":  "⚠️ Pipeline fejl",
                    "go_now": False,
                    "timestamp": datetime.now().isoformat(),
                }
            }
        )


def _build_recommendation_response(state: dict) -> dict:
    """Byg det endelige /ai/recommendation response fra pipeline state."""
    score = state.get("dispatch_score", 50)

    return {
        "recommended_zone":  state.get("dispatch_zone", "Horsens Centrum"),
        "score":             score,
        "reason":            state.get("dispatch_reason", ""),
        "grade":             state.get("dispatch_grade", ""),
        "earn_dkk_per_hour": state.get("dispatch_earn_dkk", 0),
        "go_now":            score >= 85,          # GO NOW trigger
        "h3_hex":            state.get("dispatch_h3_hex"),
        "top_zones":         _format_top_zones(state.get("demand_top_zones", [])[:5]),
        "weather":           _format_weather(state.get("data_weather", {})),
        "events_today":      _format_events(state.get("events_today", [])[:3]),
        "pipeline_errors":   state.get("meta_errors", []),
        "timestamp":         state.get("meta_completed_at", datetime.now().isoformat()),
    }


# =============================================================================
# GET /ai/hotspots
# =============================================================================

@router.get("/hotspots")
async def get_ai_hotspots(
    city: str  = Query(default="Horsens", description="By at analysere"),
    limit: int = Query(default=5,         description="Antal hotspots (max 10)", ge=1, le=10),
    fresh: bool = Query(default=False,    description="Ignorer cache"),
):
    """
    Returnerer top N hotspot-zoner med score og årsag.

    Response:
    {
      "hotspots": [
        {
          "rank": 1,
          "zone": "Horsens Centrum",
          "score": 88,
          "grade": "⚡ Ekstrem efterspørgsel",
          "reason": "...",
          "earn_dkk_per_hour": 620,
          "lat": 55.8608,
          "lon": 9.8502
        },
        ...
      ],
      "total_hotspots": 3,
      "h3_top_hexes": [...],
      "timestamp": "..."
    }
    """
    logger.info(f"[/ai/hotspots] city='{city}' limit={limit}")

    # Brug cached pipeline-resultat hvis muligt
    cached = _get_cached(city) if not fresh else None
    if cached and "top_zones" in cached:
        return _build_hotspots_response(cached, limit, from_cache=True)

    try:
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(None, run_dispatch_workflow, city)

        rec_response = _build_recommendation_response(state)
        _set_cache(city, rec_response)

        return _build_hotspots_response_from_state(state, limit)

    except Exception as exc:
        logger.error(f"[/ai/hotspots] Fejl: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(exc)})


def _build_hotspots_response(cached_rec: dict, limit: int, from_cache: bool) -> dict:
    """Byg hotspots response fra cached recommendation data."""
    top = cached_rec.get("top_zones", [])[:limit]
    return {
        "hotspots":       top,
        "total_hotspots": len(top),
        "h3_top_hexes":   [],   # Ikke cached – kræv fresh for H3 data
        "cached":         from_cache,
        "timestamp":      datetime.now().isoformat(),
    }


def _build_hotspots_response_from_state(state: dict, limit: int) -> dict:
    """Byg komplet hotspots response direkte fra pipeline state."""
    top_zones    = state.get("demand_top_zones", [])[:limit]
    all_hotspots = state.get("demand_hotspots", [])
    h3_hexes     = state.get("demand_h3_hexes", [])[:20]  # Top 20 hexes

    formatted = []
    for i, z in enumerate(top_zones, 1):
        formatted.append({
            "rank":             i,
            "zone":             z.get("name", ""),
            "score":            z.get("score", 0),
            "grade":            z.get("grade", ""),
            "reason":           " · ".join(z.get("reasons", [])[:2]),
            "earn_dkk_per_hour": z.get("earn_dkk_hr", 0),
            "confidence":       z.get("confidence", "Lav"),
            "events_near":      len(z.get("events_near", [])),
            "next_rush":        z.get("next_rush_lbl", ""),
            "lat":              z.get("lat", 0),
            "lon":              z.get("lon", 0),
            "is_hotspot":       z.get("is_hotspot", False),
        })

    # H3 hotspot hexes (score >= 70)
    h3_hotspots = [h for h in h3_hexes if h.get("score", 0) >= 70]

    return {
        "hotspots":          formatted,
        "total_hotspots":    len(all_hotspots),
        "h3_top_hexes":      h3_hotspots[:10],
        "avoid_zones":       _format_avoid(state.get("demand_avoid_zones", [])[:3]),
        "zone_chain":        state.get("demand_zone_chain", []),
        "cached":            False,
        "timestamp":         state.get("meta_completed_at", datetime.now().isoformat()),
    }


# =============================================================================
# GET /ai/heatmap
# =============================================================================

@router.get("/heatmap")
async def get_ai_heatmap(
    city: str  = Query(default="Horsens", description="By at generere heatmap for"),
    fresh: bool = Query(default=False,    description="Ignorer cache"),
):
    """
    Returnerer H3 hex heatmap data til kortvisning.
    Alle hexes inden for ~6km af bycentrum med demand-scores.

    Bruges til:
    - Frontend heatmap overlay (Leaflet / MapboxGL)
    - Driver View kort
    - Ejerdashboard analyse

    Response:
    {
      "hexes": [
        {"hex_id": "881f1d...", "lat": 55.86, "lon": 9.85, "score": 88, "grade": "⚡"},
        ...
      ],
      "total": 87,
      "timestamp": "..."
    }
    """
    logger.info(f"[/ai/heatmap] city='{city}'")

    try:
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(None, run_dispatch_workflow, city)
        h3_data = state.get("demand_h3_hexes", [])

        return {
            "hexes":     h3_data,
            "total":     len(h3_data),
            "hot_count": sum(1 for h in h3_data if h.get("is_hot")),
            "city":      city,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as exc:
        logger.error(f"[/ai/heatmap] Fejl: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(exc)})


# =============================================================================
# GET /ai/leads  (kører separat ContractHunter workflow)
# =============================================================================

@router.get("/leads")
async def get_ai_leads(
    city: str = Query(default="Horsens", description="By at søge leads i"),
):
    """
    Kører ContractHunterAgent via LangGraph og returnerer B2B leads.

    OBS: Denne er tung (~5-10 sek) og bør kun kaldes fra owner dashboard.

    Response:
    {
      "leads": [...],
      "top_leads": [...],
      "monthly_potential_dkk": 145000,
      "timestamp": "..."
    }
    """
    logger.info(f"[/ai/leads] city='{city}'")

    try:
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(None, run_leads_workflow, city)

        return {
            "leads":                   state.get("leads_all", []),
            "top_leads":               state.get("leads_top", []),
            "monthly_potential_dkk":   state.get("leads_monthly_pot_dkk", 0),
            "errors":                  state.get("meta_errors", []),
            "timestamp":               datetime.now().isoformat(),
        }

    except Exception as exc:
        logger.error(f"[/ai/leads] Fejl: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(exc)})


# =============================================================================
# GET /ai/pipeline/status
# =============================================================================

@router.get("/pipeline/status")
async def get_pipeline_status():
    """
    Returnerer status på LangGraph pipeline og cache.
    Bruges til debugging og monitoring.
    """
    return {
        "pipeline_version":   "2.0.0-langgraph",
        "cached_cities":      list({k.split(":")[0] for k in _cache.keys()}),
        "cache_entries":      len(_cache),
        "cache_ttl_sec":      _CACHE_TTL_SEC,
        "nodes": [
            "DataNode → WeatherNode → EventNode → DemandNode → DispatchNode"
        ],
        "endpoints": [
            "GET /ai/recommendation?city=Horsens",
            "GET /ai/hotspots?city=Horsens&limit=5",
            "GET /ai/heatmap?city=Horsens",
            "GET /ai/leads?city=Horsens",
            "GET /ai/pipeline/status",
        ],
        "timestamp": datetime.now().isoformat(),
    }


# =============================================================================
# Hjælpefunktioner til response-formatering
# =============================================================================

def _format_top_zones(zones: list) -> list:
    """Formater top-zones til API response (fjern intern data)."""
    out = []
    for i, z in enumerate(zones, 1):
        out.append({
            "rank":             i,
            "zone":             z.get("name", ""),
            "score":            z.get("score", 0),
            "grade":            z.get("grade", ""),
            "reason":           " · ".join(z.get("reasons", [])[:2]),
            "earn_dkk_per_hour": z.get("earn_dkk_hr", 0),
            "lat":              z.get("lat", 0),
            "lon":              z.get("lon", 0),
        })
    return out


def _format_events(events: list) -> list:
    """Formater events til API response."""
    return [
        {
            "name":       e.get("name", ""),
            "venue":      e.get("venue", ""),
            "time":       e.get("time", ""),
            "attendance": e.get("attendance", 0),
            "demand":     e.get("demand_level", ""),
            "taxi_note":  e.get("taxi_note", ""),
        }
        for e in events
    ]


def _format_weather(w: dict) -> dict:
    """Formater vejrdata til API response."""
    return {
        "temp_c":       w.get("temperature", 0),
        "precip_mm":    w.get("precipitation", 0),
        "wind_kmh":     w.get("windspeed", 0),
        "is_raining":   w.get("is_raining", False),
        "summary":      w.get("summary", ""),
    }


def _format_avoid(zones: list) -> list:
    """Formater undgå-zoner til API response."""
    return [
        {"zone": z.get("name", ""), "score": z.get("score", 0)}
        for z in zones
    ]


# =============================================================================
# GET /ai/events/sources
# =============================================================================

@router.get("/events/sources")
async def get_event_sources():
    """
    Returnerer status for alle event-datakilder i Zyflex.

    Viser:
    - Billetto (primær)
    - Lokal events.json (altid tilgængelig)
    - Ticketmaster (valgfri fallback)
    - Cache-status pr. kilde
    """
    import os
    from pathlib import Path

    sources = []

    # ── Billetto ──────────────────────────────────────────────────────────────
    if _BILLETTO_IMPORT_OK and _billetto_status:
        try:
            b_status = _billetto_status()
            sources.append({
                "name":         "Billetto",
                "role":         "primær",
                "status":       b_status.get("status", "unknown"),
                "event_count":  b_status.get("event_count", 0),
                "last_update":  b_status.get("last_update"),
                "has_key":      b_status.get("has_key", False),
                "note":         b_status.get("note", ""),
                "cache":        b_status.get("cache", {}),
            })
        except Exception as e:
            sources.append({
                "name":   "Billetto",
                "role":   "primær",
                "status": "error",
                "error":  str(e),
            })
    else:
        sources.append({
            "name":   "Billetto",
            "role":   "primær",
            "status": "not_loaded",
            "note":   "Modul ikke indlæst",
        })

    # ── Lokal events.json ─────────────────────────────────────────────────────
    events_json_path = Path(__file__).parent.parent / "data" / "events.json"
    if events_json_path.exists():
        try:
            with open(events_json_path, encoding="utf-8") as f:
                local_events = json.load(f)
            local_count = len(local_events)
        except Exception:
            local_count = 0
        sources.append({
            "name":        "Lokal events.json",
            "role":        "fallback",
            "status":      "ok",
            "event_count": local_count,
            "last_update": datetime.fromtimestamp(events_json_path.stat().st_mtime).isoformat(),
            "note":        "Manuelt tilføjede events (CASA Arena fodbold etc.)",
        })
    else:
        sources.append({
            "name":   "Lokal events.json",
            "role":   "fallback",
            "status": "missing",
            "note":   f"Fil ikke fundet: {events_json_path}",
        })

    # ── Ticketmaster ──────────────────────────────────────────────────────────
    tm_key = os.getenv("TICKETMASTER_API_KEY", "")
    sources.append({
        "name":    "Ticketmaster",
        "role":    "valgfri fallback",
        "status":  "ok" if tm_key else "no_key",
        "has_key": bool(tm_key),
        "note":    "Aktiv" if tm_key else "Tilføj TICKETMASTER_API_KEY i .env (svag dansk dækning)",
    })

    return {
        "sources":    sources,
        "primary":    "Billetto",
        "timestamp":  datetime.now().isoformat(),
    }


# =============================================================================
# GET /ai/system-overview
# =============================================================================

@router.get("/system-overview")
async def get_system_overview():
    """
    Samlet overblik over hele Zyflex AI-systemet.

    Inkluderer:
    - Pipeline health
    - Weather status
    - Event source status
    - Cache status
    - Aktive zoner
    - Recommendation engine status
    - Response times
    """
    import os
    from pathlib import Path

    # ── Cache-status ──────────────────────────────────────────────────────────
    cache_cities = list({k.split(":")[0] for k in _cache.keys()})
    cache_entries = len(_cache)

    # ── Log-fil status ────────────────────────────────────────────────────────
    log_count = 0
    last_log  = None
    try:
        if _LOG_FILE.exists():
            lines = _LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
            log_count = len(lines)
            if lines:
                last_entry = json.loads(lines[-1])
                last_log   = last_entry.get("ts")
    except Exception:
        pass

    # ── Billetto status ───────────────────────────────────────────────────────
    billetto_ok = False
    billetto_events = 0
    if _BILLETTO_IMPORT_OK and _billetto_status:
        try:
            b = _billetto_status()
            billetto_ok     = b.get("status") == "ok"
            billetto_events = b.get("event_count", 0)
        except Exception:
            pass

    # ── .env nøgler til stede? ────────────────────────────────────────────────
    keys_status = {
        "BILLETTO_API_KEY":     bool(os.getenv("BILLETTO_API_KEY")),
        "TICKETMASTER_API_KEY": bool(os.getenv("TICKETMASTER_API_KEY")),
        "NTFY_CHANNEL":         bool(os.getenv("NTFY_CHANNEL")),
    }

    # ── Data-filer ────────────────────────────────────────────────────────────
    data_dir = Path(__file__).parent.parent / "data"
    files_status = {}
    for fname in ["events.json", "trips.csv", "ai_recommendations.jsonl", "poi_cache.json"]:
        fpath = data_dir / fname
        files_status[fname] = {
            "exists": fpath.exists(),
            "size_kb": round(fpath.stat().st_size / 1024, 1) if fpath.exists() else 0,
        }

    return {
        "system":    "Zyflex AI – Palantir for Taxi",
        "version":   "2.1.0-billetto",
        "status":    "operational",

        "pipeline": {
            "version":   "LangGraph 2.0",
            "nodes":     ["DataNode", "WeatherNode", "EventNode", "DemandNode", "DispatchNode"],
            "health":    "ok",
        },

        "cache": {
            "entries":      cache_entries,
            "cities":       cache_cities,
            "ttl_sec":      _CACHE_TTL_SEC,
            "status":       "ok",
        },

        "event_sources": {
            "primary":          "Billetto",
            "billetto_active":  billetto_ok,
            "billetto_events":  billetto_events,
            "ticketmaster":     keys_status["TICKETMASTER_API_KEY"],
            "local_json":       files_status.get("events.json", {}).get("exists", False),
        },

        "logging": {
            "recommendations_logged": log_count,
            "last_log":               last_log,
            "file":                   "data/ai_recommendations.jsonl",
        },

        "api_keys": keys_status,
        "data_files": files_status,

        "endpoints": {
            "recommendation":   "GET /ai/recommendation?city=Horsens",
            "hotspots":         "GET /ai/hotspots?city=Horsens&limit=5",
            "heatmap":          "GET /ai/heatmap?city=Horsens",
            "leads":            "GET /ai/leads?city=Horsens",
            "event_sources":    "GET /ai/events/sources",
            "system_overview":  "GET /ai/system-overview",
            "pipeline_status":  "GET /ai/pipeline/status",
        },

        "dashboard": {
            "owner":  "http://localhost:8000/dashboard/owner",
            "driver": "http://localhost:8000/dashboard/driver",
        },

        "timestamp": datetime.now().isoformat(),
    }
