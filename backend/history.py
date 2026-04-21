# =============================================================================
# history.py – Zyflex AI Historical Pattern Analyser
#
# Læser trips.csv og finder mønstre i dine egne data.
# Jo mere du kører systemet, desto klogere bliver det.
#
# Mønstre det lærer:
#   - Regn + tidspunkt → hvilke zoner stiger mest?
#   - Hvilke timer giver højest score historisk?
#   - Events → hvilke zoner drager mest fordel?
# =============================================================================

import csv
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

# Stien til CSV-filen (relativt til projektrod)
TRIPS_CSV = Path(__file__).parent.parent / "data" / "trips.csv"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FUNCTION – kaldes af AnalysisAgent
# ─────────────────────────────────────────────────────────────────────────────

def get_historical_modifiers(city: str = "Horsens") -> dict:
    """
    Analyser trips.csv og returnér score-modifikatorer pr. zone.

    Returner:
        {
            "zone_id": {
                "modifier":     float,   # +/- point der lægges til raw score
                "confidence":   str,     # "høj" / "middel" / "lav"
                "insight":      str,     # Menneskelæsbar forklaring
                "runs":         int,     # Antal datapunkter bag indsigten
            },
            ...
        }
    """
    rows = _load_csv()
    if not rows:
        logger.info("Ingen historisk data – bruger neutrale modifikatorer")
        return {}

    modifiers = {}
    zone_data  = _group_by_zone(rows)
    hour_now   = datetime.now().hour
    is_weekend = datetime.now().weekday() >= 5

    for zone_id, zone_rows in zone_data.items():
        if len(zone_rows) < 2:
            continue  # For få datapunkter

        # Gennemsnitlig score for denne zone
        avg_score    = sum(r["score"] for r in zone_rows) / len(zone_rows)

        # Regn-effekt: sammenlign regn vs. tørt
        rain_scores = [r["score"] for r in zone_rows if "regn" in r["top_reason"].lower()]
        dry_scores  = [r["score"] for r in zone_rows if "regn" not in r["top_reason"].lower() and r["score"] > 0]

        rain_effect = 0.0
        if rain_scores and dry_scores:
            rain_effect = (sum(rain_scores)/len(rain_scores)) - (sum(dry_scores)/len(dry_scores))

        # Time-effekt: score på nuværende tidspunkt vs. gennemsnit
        hour_scores = [r["score"] for r in zone_rows if r["hour"] == hour_now]
        hour_effect = 0.0
        if hour_scores:
            hour_avg    = sum(hour_scores) / len(hour_scores)
            hour_effect = hour_avg - avg_score

        # Event-effekt
        event_scores = [r["score"] for r in zone_rows if r["events_nearby"] > 0]
        no_evt_scores= [r["score"] for r in zone_rows if r["events_nearby"] == 0]
        event_effect = 0.0
        if event_scores and no_evt_scores:
            event_effect = (sum(event_scores)/len(event_scores)) - (sum(no_evt_scores)/len(no_evt_scores))

        # Samlet modifikator (vægtet sum)
        modifier = round(
            hour_effect  * 0.4 +
            event_effect * 0.4 +
            rain_effect  * 0.2,   # Regn håndteres allerede i weather_score
            1
        )

        # Confidence baseret på antal datapunkter
        confidence = "høj" if len(zone_rows) >= 10 else "middel" if len(zone_rows) >= 4 else "lav"

        # Byg indsigt-tekst
        insights = []
        if abs(rain_effect) >= 3:
            direction = "stiger" if rain_effect > 0 else "falder"
            insights.append(f"Regn: score {direction} med {abs(rain_effect):.0f} pt historisk")
        if abs(event_effect) >= 5:
            insights.append(f"Events: +{event_effect:.0f} pt når events i nærheden")
        if abs(hour_effect) >= 3:
            direction = "bedre" if hour_effect > 0 else "svagere"
            insights.append(f"Kl. {hour_now}:00 historisk {direction} end gennemsnit")
        if not insights:
            insights.append(f"Gns. score: {avg_score:.0f} baseret på {len(zone_rows)} kørsler")

        modifiers[zone_id] = {
            "modifier":   modifier,
            "confidence": confidence,
            "insight":    " · ".join(insights),
            "runs":       len(zone_rows),
            "avg_score":  round(avg_score, 1),
        }

    logger.info(f"Historisk analyse: {len(modifiers)} zoner analyseret, "
                f"{len(rows)} datapunkter i alt")
    return modifiers


def get_summary() -> dict:
    """
    Giv et hurtigt overblik over hvad historien viser.
    Bruges til dashboard og terminal-output.
    """
    rows = _load_csv()
    if not rows:
        return {"status": "no_data", "message": "Ingen historisk data endnu"}

    total_runs   = len(set(r["timestamp"][:19] for r in rows))  # Unikke kørselstider
    total_rows   = len(rows)
    best_zone    = max(set(r["zone_name"] for r in rows),
                       key=lambda z: sum(r["score"] for r in rows if r["zone_name"] == z) /
                                     max(1, sum(1 for r in rows if r["zone_name"] == z)))
    rain_rows    = [r for r in rows if "regn" in r["top_reason"].lower()]
    dry_rows     = [r for r in rows if "regn" not in r["top_reason"].lower()]
    rain_avg     = round(sum(r["score"] for r in rain_rows) / max(1, len(rain_rows)), 1)
    dry_avg      = round(sum(r["score"] for r in dry_rows)  / max(1, len(dry_rows)),  1)
    event_rows   = [r for r in rows if r["events_nearby"] > 0]
    event_avg    = round(sum(r["score"] for r in event_rows) / max(1, len(event_rows)), 1)

    return {
        "status":           "ok",
        "total_runs":       total_runs,
        "total_datapoints": total_rows,
        "best_zone":        best_zone,
        "rain_avg_score":   rain_avg,
        "dry_avg_score":    dry_avg,
        "event_avg_score":  event_avg,
        "rain_boost":       round(rain_avg - dry_avg, 1),
        "insights": [
            f"Systemet har kørt {total_runs} gange og indsamlet {total_rows} datapunkter",
            f"Bedste zone historisk: {best_zone}",
            f"Regn booster gennemscore med {round(rain_avg - dry_avg, 1)} point",
            f"Events giver gennemsnit {event_avg}/100 vs {dry_avg}/100 uden events",
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# INTERNE HJÆLPERE
# ─────────────────────────────────────────────────────────────────────────────

def _load_csv() -> list:
    """Læs trips.csv og returner liste af dicts."""
    if not TRIPS_CSV.exists():
        return []
    rows = []
    try:
        with open(TRIPS_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    ts = row.get("timestamp", "")
                    rows.append({
                        "timestamp":     ts,
                        "hour":          _parse_hour(ts),
                        "zone_id":       row.get("zone_id", ""),
                        "zone_name":     row.get("zone_name", ""),
                        "score":         int(row.get("score", 0)),
                        "top_reason":    row.get("top_reason", ""),
                        "events_nearby": int(row.get("events_nearby", 0)),
                    })
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        logger.warning(f"Kunne ikke læse trips.csv: {e}")
    return rows


def _parse_hour(ts: str) -> int:
    """Udtræk time fra timestamp-streng."""
    try:
        return int(ts[11:13])
    except Exception:
        return datetime.now().hour


def _group_by_zone(rows: list) -> dict:
    """Gruppér rækker efter zone_id."""
    groups = defaultdict(list)
    for r in rows:
        if r["zone_id"]:
            groups[r["zone_id"]].append(r)
    return dict(groups)
