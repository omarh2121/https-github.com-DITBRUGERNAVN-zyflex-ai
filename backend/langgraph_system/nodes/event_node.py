# =============================================================================
# nodes/event_node.py
#
# Zyflex AI – EventNode (LangGraph)
#
# Ansvar:
#   Wrapper om den eksisterende EventAgent + beriget event-klassificering.
#   Analyserer events og kategoriserer dem efter taxi-relevans:
#   - Sluttidspunkt analyse (= folk skal hjem = taxa-peak)
#   - High-impact events (> 1000 gæster)
#   - Events i dag vs. kommende
#
# Modtager: data_events (allerede hentet af DataNode via DataAgent/EventAgent)
# Sender:   events_list, events_today, events_high_impact, events_count
# =============================================================================

from __future__ import annotations
import logging
import time
from datetime import datetime

from langgraph_system.state import ZyflexState

logger = logging.getLogger("zyflex.langgraph.event_node")


def event_node(state: ZyflexState) -> ZyflexState:
    """
    LangGraph Node: EventNode

    Beriger og kategoriserer events fra DataNode.
    Input:  data_events (rå liste fra DataAgent)
    Output: events_list, events_today, events_high_impact, events_count
    """
    logger.info("[EventNode] Analyserer events")
    t_start = time.time()

    errors: list[str] = list(state.get("meta_errors", []))
    node_times: dict = dict(state.get("meta_node_times", {}))

    raw_events = state.get("data_events", [])

    try:
        enriched      = _enrich_events(raw_events)
        today_events  = _filter_today(enriched)
        high_impact   = _filter_high_impact(enriched)

        elapsed = round((time.time() - t_start) * 1000)
        node_times["event_node"] = elapsed
        logger.info(
            f"[EventNode] ✅ {len(enriched)} total, {len(today_events)} i dag, "
            f"{len(high_impact)} high-impact, {elapsed}ms"
        )

        return {
            **state,
            "events_list":         enriched,
            "events_count":        len(enriched),
            "events_today":        today_events,
            "events_high_impact":  high_impact,
            "meta_node_times":     node_times,
            "meta_errors":         errors,
        }

    except Exception as exc:
        elapsed = round((time.time() - t_start) * 1000)
        node_times["event_node"] = elapsed
        err_msg = f"EventNode fejl: {exc}"
        logger.error(f"[EventNode] ❌ {err_msg}", exc_info=True)
        errors.append(err_msg)

        return {
            **state,
            "events_list":         raw_events,
            "events_count":        len(raw_events),
            "events_today":        [],
            "events_high_impact":  [],
            "meta_node_times":     node_times,
            "meta_errors":         errors,
        }


def _enrich_events(events: list[dict]) -> list[dict]:
    """
    Beriger events med taxi-relevante felter:
    - end_time_estimated: estimeret sluttidspunkt (= taxi-peak)
    - taxi_window:        hvornår taxa-efterspørgsel er højest
    - demand_level:       "critical" / "high" / "medium" / "low"
    - days_until:         antal dage til eventet
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    enriched = []

    for evt in events:
        e = dict(evt)  # Kopi – ændrer ikke originalen

        # ── Estimér sluttidspunkt ─────────────────────────────────────────
        start_time = e.get("time", "19:00")
        try:
            start_hour = int(start_time[:2])
        except (ValueError, TypeError):
            start_hour = 19

        att = e.get("attendance", 300)

        # Typisk varighed baseret på event-type
        category = (e.get("category") or "").lower()
        if "festival" in category:
            duration_hours = 8   # Festivaler: heldag
        elif "fodbold" in category or "sport" in category:
            duration_hours = 2   # Sport: ~2 timer
        elif "koncert" in category or "musik" in category:
            duration_hours = 3   # Koncert: ~3 timer
        else:
            duration_hours = 2   # Default

        end_hour = (start_hour + duration_hours) % 24
        e["end_time_estimated"] = f"{end_hour:02d}:00"

        # Taxi-peak er typisk 0-30 min efter sluttidspunkt
        taxi_peak_hour = end_hour
        e["taxi_window"] = f"{taxi_peak_hour:02d}:00 – {(taxi_peak_hour + 1) % 24:02d}:30"

        # ── Demand level ──────────────────────────────────────────────────
        if att >= 10000:
            e["demand_level"] = "critical"
        elif att >= 2000:
            e["demand_level"] = "high"
        elif att >= 500:
            e["demand_level"] = "medium"
        else:
            e["demand_level"] = "low"

        # ── Dage til eventet ──────────────────────────────────────────────
        event_date = e.get("date", today_str)
        try:
            d = datetime.strptime(event_date[:10], "%Y-%m-%d")
            e["days_until"] = max(0, (d.date() - now.date()).days)
        except Exception:
            e["days_until"] = 0

        # ── Taxi-relevans-note ────────────────────────────────────────────
        if e["days_until"] == 0:
            if start_hour <= now.hour <= end_hour:
                e["taxi_note"] = f"🔴 LIVE – event kører NU! Kør til {e.get('venue', 'venue')}"
            elif now.hour < start_hour:
                mins_to_start = (start_hour - now.hour) * 60
                e["taxi_note"] = f"⏰ Starter om ~{mins_to_start} min – positionér nu"
            else:
                e["taxi_note"] = f"✅ Sluttede – folk skal hjem (taxi-peak)"
        elif e["days_until"] == 1:
            e["taxi_note"] = f"📅 I morgen – forbered dig"
        else:
            e["taxi_note"] = f"📅 Om {e['days_until']} dage"

        enriched.append(e)

    # Sorter: events i dag og high-impact øverst
    enriched.sort(key=lambda x: (x.get("days_until", 99), -x.get("attendance", 0)))
    return enriched


def _filter_today(events: list[dict]) -> list[dict]:
    """Returner kun events der er i dag (days_until == 0)."""
    return [e for e in events if e.get("days_until", 99) == 0]


def _filter_high_impact(events: list[dict]) -> list[dict]:
    """Returner events med attendance > 1000 og inden for 3 dage."""
    return [
        e for e in events
        if e.get("attendance", 0) >= 1000 and e.get("days_until", 99) <= 3
    ]
