# =============================================================================
# live_data/events/billetto_source.py
#
# Zyflex AI – Billetto Event Source (PRIMÆR)
#
# Billetto er Danmarks bedste event-platform med stærk lokal dækning.
# Bruger Billetto Public API v3:
#   https://billetto.dk/api/v3/public/events
#
# Features:
#   - 30-minutters in-memory cache pr. by
#   - Pagination (op til 3 sider)
#   - Postal code filtrering pr. by
#   - Event-deduplicering (titel + dato + venue)
#   - Timeout-beskyttelse (5 sekunder)
#   - Graceful failure (returnerer [] ved fejl)
#   - Unified Zyflex event format
#   - Detaljeret logging: svartid, event-antal, fejl, cache-hits
#
# Konfiguration:
#   BILLETTO_API_KEY=<dit_token>  (i .env)
#
# Zyflex unified event format:
#   {
#     "title":          str,
#     "venue":          str,
#     "city":           str,
#     "start_time":     str,        # ISO8601 eller "HH:MM"
#     "end_time":       str | null,
#     "lat":            float | null,
#     "lng":            float | null,
#     "expected_crowd": int | null,
#     "source":         "billetto",
#     "url":            str | null,
#     # Legacy felter (bruges af EventNode):
#     "name":           str,        # = title (alias)
#     "date":           str,        # YYYY-MM-DD
#     "time":           str,        # HH:MM
#     "attendance":     int,        # = expected_crowd
#     "category":       str,
#   }
# =============================================================================

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

# Sørg for at backend-mappen er i path
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

logger = logging.getLogger("zyflex.billetto")

# ---------------------------------------------------------------------------
# Konstanter
# ---------------------------------------------------------------------------

BILLETTO_API_URL = "https://billetto.dk/api/v3/public/events"
BILLETTO_API_KEY  = os.getenv("BILLETTO_API_KEY", "")

_REQUEST_TIMEOUT  = 5       # sekunder
_MAX_PAGES        = 3       # maks 3 sider pr. by (= 75 events)
_PAGE_SIZE        = 25
_CACHE_TTL_MIN    = 30      # minutter

# Postnummer-mapping pr. by
_CITY_POSTAL: dict[str, list[str]] = {
    "horsens":  ["8700"],
    "vejle":    ["7100"],
    "herning":  ["7400"],
    "ikast":    ["7430"],
    "aarhus":   ["8000", "8200", "8210", "8220", "8230", "8240"],
}

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

_cache: dict[str, dict] = {}
# Format: { city_lower: {"events": [...], "fetched_at": datetime, "count": int} }


def _is_cache_valid(city_lower: str) -> bool:
    entry = _cache.get(city_lower)
    if not entry:
        return False
    age = datetime.now() - entry["fetched_at"]
    return age < timedelta(minutes=_CACHE_TTL_MIN)


def _get_from_cache(city_lower: str) -> Optional[list[dict]]:
    if _is_cache_valid(city_lower):
        entry = _cache[city_lower]
        logger.info(
            f"[Billetto] Cache HIT for '{city_lower}' – "
            f"{entry['count']} events, alder: "
            f"{int((datetime.now() - entry['fetched_at']).total_seconds() / 60)} min"
        )
        return entry["events"]
    return None


def _set_cache(city_lower: str, events: list[dict]):
    _cache[city_lower] = {
        "events":     events,
        "fetched_at": datetime.now(),
        "count":      len(events),
    }
    logger.info(f"[Billetto] Cache SET for '{city_lower}' – {len(events)} events gemt")


def get_cache_status() -> dict:
    """Returnerer cache-status for alle byer – bruges af /ai/events/sources."""
    status = {}
    for city, entry in _cache.items():
        age_sec = int((datetime.now() - entry["fetched_at"]).total_seconds())
        status[city] = {
            "count":      entry["count"],
            "fetched_at": entry["fetched_at"].isoformat(),
            "age_sec":    age_sec,
            "valid":      age_sec < _CACHE_TTL_MIN * 60,
        }
    return status


# ---------------------------------------------------------------------------
# Hoved-fetch funktion
# ---------------------------------------------------------------------------

def fetch(city: str = "Horsens") -> list[dict]:
    """
    Henter events for en by fra Billetto API.

    Args:
        city: By-navn (case-insensitiv) – se _CITY_POSTAL for understøttede byer.

    Returns:
        Liste af events i Zyflex unified format.
        Returnerer [] ved fejl (graceful failure).
    """
    city_lower = city.lower().strip()
    t_start    = time.time()

    # ── Ingen API-nøgle? ─────────────────────────────────────────────────────
    if not BILLETTO_API_KEY:
        logger.warning("[Billetto] BILLETTO_API_KEY mangler i .env – springer over")
        return []

    # ── Cache hit? ────────────────────────────────────────────────────────────
    cached = _get_from_cache(city_lower)
    if cached is not None:
        return cached

    # ── Hent postal codes ─────────────────────────────────────────────────────
    postal_codes = _CITY_POSTAL.get(city_lower)
    if not postal_codes:
        # Prøv alligevel med by-navn som søgning
        logger.warning(f"[Billetto] Ingen postal codes for '{city}' – bruger by-søgning")
        postal_codes = None

    # ── Hent fra API ──────────────────────────────────────────────────────────
    all_events: list[dict] = []
    headers    = {"Authorization": f"Bearer {BILLETTO_API_KEY}",
                  "Accept":        "application/json"}

    try:
        for postal in (postal_codes or [None]):
            page_events = _fetch_for_postal(postal, city, headers)
            all_events.extend(page_events)

        # Deduplicering
        before_dedup = len(all_events)
        all_events   = _deduplicate(all_events)
        dupes_removed = before_dedup - len(all_events)

        elapsed_ms = int((time.time() - t_start) * 1000)
        logger.info(
            f"[Billetto] ✅ {city}: {len(all_events)} events "
            f"({dupes_removed} duplikater fjernet), {elapsed_ms}ms"
        )

        _set_cache(city_lower, all_events)
        return all_events

    except Exception as exc:
        elapsed_ms = int((time.time() - t_start) * 1000)
        logger.error(f"[Billetto] ❌ Fejl for '{city}' efter {elapsed_ms}ms: {exc}", exc_info=True)
        return []


def _fetch_for_postal(
    postal_code: Optional[str],
    city: str,
    headers: dict,
) -> list[dict]:
    """Henter events for ét postnummer (med pagination)."""
    raw_events: list[dict] = []

    for page in range(1, _MAX_PAGES + 1):
        params: dict = {
            "per_page": _PAGE_SIZE,
            "page":     page,
            "status":   "published",
        }

        if postal_code:
            params["postal_code"] = postal_code
        else:
            # Fallback: søg på by-navn
            params["q"] = city

        try:
            t0  = time.time()
            resp = requests.get(
                BILLETTO_API_URL,
                headers=headers,
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            ms = int((time.time() - t0) * 1000)

            if resp.status_code == 401:
                logger.error("[Billetto] 401 Unauthorized – tjek BILLETTO_API_KEY")
                break

            if resp.status_code == 404:
                logger.debug(f"[Billetto] 404 for postal={postal_code}, side={page} – stopper")
                break

            if resp.status_code != 200:
                logger.warning(f"[Billetto] HTTP {resp.status_code} for side {page}, postal={postal_code}")
                break

            data = resp.json()
            logger.debug(
                f"[Billetto] Side {page}/{_MAX_PAGES}, postal={postal_code}: "
                f"{ms}ms, {len(data.get('data', []))} events"
            )

            events_on_page = data.get("data", [])
            if not events_on_page:
                break  # Ingen flere events

            for raw in events_on_page:
                unified = _to_zyflex_format(raw, city)
                if unified:
                    raw_events.append(unified)

            # Ingen næste side hvis vi fik færre end forventet
            if len(events_on_page) < _PAGE_SIZE:
                break

        except requests.Timeout:
            logger.warning(f"[Billetto] Timeout på side {page} for postal={postal_code} (>{_REQUEST_TIMEOUT}s)")
            break
        except requests.RequestException as exc:
            logger.error(f"[Billetto] Request-fejl på side {page}: {exc}")
            break

    return raw_events


# ---------------------------------------------------------------------------
# Format-konvertering
# ---------------------------------------------------------------------------

def _to_zyflex_format(raw: dict, city: str) -> Optional[dict]:
    """
    Konverterer Billetto API-event til Zyflex unified format.
    Returnerer None hvis eventet er ubrugeligt (ingen titel/dato).
    """
    try:
        title = raw.get("title") or raw.get("name") or ""
        if not title:
            return None

        # Dato og tidspunkt
        start_raw = raw.get("start_at") or raw.get("starts_at") or raw.get("date") or ""
        end_raw   = raw.get("end_at")   or raw.get("ends_at")   or raw.get("end_date") or None

        date_str, time_str = _parse_datetime(start_raw)
        end_str            = _parse_end_time(end_raw)

        if not date_str:
            return None  # Springer over events uden dato

        # Venue
        venue_obj = raw.get("venue") or {}
        if isinstance(venue_obj, dict):
            venue_name = venue_obj.get("name") or venue_obj.get("title") or ""
        else:
            venue_name = str(venue_obj)

        # Koordinater
        lat = lng = None
        if isinstance(venue_obj, dict):
            lat = _safe_float(venue_obj.get("lat") or venue_obj.get("latitude"))
            lng = _safe_float(venue_obj.get("lng") or venue_obj.get("longitude"))

        # By – brug venue-by hvis tilgængelig, ellers fallback til input-by
        venue_city = ""
        if isinstance(venue_obj, dict):
            venue_city = venue_obj.get("city") or venue_obj.get("address_city") or ""
        event_city = venue_city or city

        # Forventet deltagere
        capacity      = _safe_int(raw.get("capacity") or raw.get("max_attendees"))
        tickets_sold  = _safe_int(raw.get("tickets_sold") or raw.get("sold_count"))
        expected      = capacity or tickets_sold or _guess_crowd(raw)

        # Kategori
        category_obj = raw.get("category") or {}
        if isinstance(category_obj, dict):
            category = category_obj.get("name") or ""
        else:
            category = str(category_obj) if category_obj else ""

        # URL
        slug  = raw.get("slug") or raw.get("id") or ""
        url   = raw.get("url") or (f"https://billetto.dk/e/{slug}" if slug else None)

        return {
            # Zyflex unified format
            "title":          title,
            "venue":          venue_name or f"{event_city} venue",
            "city":           event_city,
            "start_time":     f"{date_str}T{time_str}" if time_str else date_str,
            "end_time":       end_str,
            "lat":            lat,
            "lng":            lng,
            "expected_crowd": expected,
            "source":         "billetto",
            "url":            url,
            # Legacy felter (bruges af EventNode downstream)
            "name":           title,
            "date":           date_str,
            "time":           time_str or "19:00",
            "attendance":     expected or 300,
            "category":       category,
        }

    except Exception as exc:
        logger.debug(f"[Billetto] Kunne ikke konvertere event: {exc} – {raw.get('title', '?')}")
        return None


def _parse_datetime(raw: str) -> tuple[str, str]:
    """Parser ISO8601 streng til (YYYY-MM-DD, HH:MM). Returnerer ('', '') ved fejl."""
    if not raw:
        return ("", "")
    try:
        # Prøv ISO8601 med T
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return (dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"))
        # Prøv dato-only
        if len(raw) >= 10:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d")
            return (dt.strftime("%Y-%m-%d"), "")
    except Exception:
        pass
    return ("", "")


def _parse_end_time(raw: Optional[str]) -> Optional[str]:
    """Parser sluttidspunkt. Returnerer ISO8601 string eller None."""
    if not raw:
        return None
    date_str, time_str = _parse_datetime(raw)
    if date_str:
        return f"{date_str}T{time_str}" if time_str else date_str
    return None


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _guess_crowd(raw: dict) -> int:
    """Gæt deltagerantal baseret på event-type hvis kapacitet mangler."""
    category_raw = raw.get("category") or {}
    cat = ""
    if isinstance(category_raw, dict):
        cat = (category_raw.get("name") or "").lower()
    elif isinstance(category_raw, str):
        cat = category_raw.lower()

    title = (raw.get("title") or "").lower()

    if any(w in cat or w in title for w in ["festival", "musik festival"]):
        return 2000
    if any(w in cat or w in title for w in ["koncert", "concert", "musik", "music"]):
        return 500
    if any(w in cat or w in title for w in ["sport", "fodbold", "håndbold"]):
        return 800
    if any(w in cat or w in title for w in ["teater", "standup", "comedy"]):
        return 300
    return 150  # Default


# ---------------------------------------------------------------------------
# Deduplicering
# ---------------------------------------------------------------------------

def _deduplicate(events: list[dict]) -> list[dict]:
    """
    Fjerner duplikater baseret på (title, date, venue).
    Beholder første forekomst.
    """
    seen: set[tuple] = set()
    unique: list[dict] = []

    for evt in events:
        key = (
            (evt.get("title") or "").lower().strip(),
            evt.get("date", ""),
            (evt.get("venue") or "").lower().strip(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(evt)

    return unique


# ---------------------------------------------------------------------------
# Status-funktion (til /ai/events/sources endpoint)
# ---------------------------------------------------------------------------

def get_source_status() -> dict:
    """
    Returnerer Billetto source-status til /ai/events/sources endpoint.
    """
    has_key    = bool(BILLETTO_API_KEY)
    cache_info = get_cache_status()
    total_events = sum(v["count"] for v in cache_info.values())

    # Find seneste opdatering
    last_update = None
    if cache_info:
        latest = max(cache_info.values(), key=lambda x: x["fetched_at"])
        last_update = latest["fetched_at"]

    return {
        "source":       "billetto",
        "status":       "ok" if has_key else "no_key",
        "has_key":      has_key,
        "event_count":  total_events,
        "last_update":  last_update,
        "cache":        cache_info,
        "api_url":      BILLETTO_API_URL,
        "note":         "Primær dansk event-kilde" if has_key else "Tilføj BILLETTO_API_KEY i .env",
    }
