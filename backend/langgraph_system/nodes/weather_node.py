# =============================================================================
# nodes/weather_node.py
#
# Zyflex AI – WeatherNode (LangGraph)
#
# Ansvar:
#   Analyserer vejrdata fra data_node og beregner:
#   - En weather_score (0-100) der beskriver vejrets impact på taxi-efterspørgsel
#   - En weather_modifier (+/- point) der tilføjes til zone-scores
#   - Klare forklaringer til chaufføren
#
# Modtager: data_weather fra DataNode
# Sender:   weather_score, weather_reasons, weather_modifier til state
# =============================================================================

from __future__ import annotations
import logging
import time

from langgraph_system.state import ZyflexState

logger = logging.getLogger("zyflex.langgraph.weather_node")


def weather_node(state: ZyflexState) -> ZyflexState:
    """
    LangGraph Node: WeatherNode

    Analyserer vejrdata og beregner demand-impact.
    Input:  data_weather (dict fra DataAgent/Open-Meteo)
    Output: weather_score (0-100), weather_reasons (list), weather_modifier (float)
    """
    logger.info("[WeatherNode] Analyserer vejrdata")
    t_start = time.time()

    errors: list[str] = list(state.get("meta_errors", []))
    node_times: dict = dict(state.get("meta_node_times", {}))
    w = state.get("data_weather", {})

    try:
        score, reasons, modifier = _analyze_weather(w)

        elapsed = round((time.time() - t_start) * 1000)
        node_times["weather_node"] = elapsed
        logger.info(f"[WeatherNode] ✅ Score={score}, modifier={modifier:+.1f}, {elapsed}ms")

        return {
            **state,
            "weather_score":    score,
            "weather_reasons":  reasons,
            "weather_modifier": modifier,
            "meta_node_times":  node_times,
            "meta_errors":      errors,
        }

    except Exception as exc:
        elapsed = round((time.time() - t_start) * 1000)
        node_times["weather_node"] = elapsed
        err_msg = f"WeatherNode fejl: {exc}"
        logger.error(f"[WeatherNode] ❌ {err_msg}", exc_info=True)
        errors.append(err_msg)

        return {
            **state,
            "weather_score":    30.0,
            "weather_reasons":  ["Vejrdata utilgængelig – bruger neutral score"],
            "weather_modifier": 0.0,
            "meta_node_times":  node_times,
            "meta_errors":      errors,
        }


def _analyze_weather(w: dict) -> tuple[float, list[str], float]:
    """
    Beregn vejr-score og modifier baseret på Open-Meteo data.

    Scorer:
    - Tørt vejr:        score≈30, modifier=0
    - Let regn:         score≈60, modifier=+12
    - Kraftig regn:     score≈85, modifier=+25
    - Frost / storm:    bonus oven på regn
    - Varmt og solrigt: score≈20, modifier=-5 (folk går)

    Returns: (score: float, reasons: list[str], modifier: float)
    """
    score    = 30.0
    modifier = 0.0
    reasons  = []

    temp   = float(w.get("temperature",   12))
    precip = float(w.get("precipitation", 0))
    wind   = float(w.get("windspeed",     0))

    # ── Regn – den største single-driver for taxi-efterspørgsel ────────────
    if precip >= 10.0:
        score    += 55
        modifier += 30
        reasons.append(f"🌧 Skybrud {precip:.1f}mm/t – ALLE vil have taxa")
    elif precip >= 3.0:
        score    += 45
        modifier += 25
        reasons.append(f"🌧 Kraftig regn {precip:.1f}mm/t – meget høj efterspørgsel")
    elif precip >= 1.0:
        score    += 30
        modifier += 15
        reasons.append(f"🌦 Moderat regn {precip:.1f}mm/t – efterspørgsel stiger markant")
    elif precip >= 0.5:
        score    += 18
        modifier += 8
        reasons.append(f"🌦 Let regn {precip:.1f}mm/t – efterspørgsel stiger")
    elif precip > 0:
        score    += 5
        modifier += 3
        reasons.append(f"💧 Dryp ({precip:.1f}mm/t) – svagt boosted")

    # ── Temperatur ─────────────────────────────────────────────────────────
    if temp <= -5:
        score    += 22
        modifier += 15
        reasons.append(f"🥶 Hård frost {temp:.0f}°C – ingen vil gå udenfor")
    elif temp <= 0:
        score    += 18
        modifier += 12
        reasons.append(f"❄️ Frost {temp:.0f}°C – folk vil have taxa")
    elif temp <= 5:
        score    += 12
        modifier += 7
        reasons.append(f"🧊 Meget koldt {temp:.0f}°C – øget efterspørgsel")
    elif temp <= 10:
        score    += 6
        modifier += 3
        reasons.append(f"🧥 Koldt {temp:.0f}°C – let boost")
    elif temp >= 28:
        # Meget varmt – folk kører selv eller går
        score    -= 5
        modifier -= 5
        reasons.append(f"☀️ Varmt {temp:.0f}°C – folk går / kører selv")

    # ── Vind ───────────────────────────────────────────────────────────────
    if wind >= 60:
        score    += 18
        modifier += 12
        reasons.append(f"🌪 Orkan {wind:.0f}km/t – ekstremt vejr")
    elif wind >= 50:
        score    += 14
        modifier += 9
        reasons.append(f"💨 Storm {wind:.0f}km/t – få vil cykle/gå")
    elif wind >= 40:
        score    += 9
        modifier += 5
        reasons.append(f"💨 Stærk vind {wind:.0f}km/t")

    # ── Ingen negativ vejr-faktor ──────────────────────────────────────────
    if not reasons or (len(reasons) == 1 and "Varmt" in reasons[0]):
        reasons = [f"☀️ Fint vejr: {temp:.0f}°C, {precip:.1f}mm – neutral efterspørgsel"]

    # Score cap: 0-100
    score = max(0.0, min(100.0, score))

    return round(score, 1), reasons, round(modifier, 1)
