#!/usr/bin/env python3
# =============================================================================
# main.py – Zyflex AI Command Center (FastAPI Server)
#
# Kør med:  python backend/main.py
# Dashboard: http://localhost:8000  (eller åbn dashboard/index.html direkte)
#
# API endpoints:
#   GET  /api/status       → agent-status (polling)
#   GET  /api/report       → seneste rapport
#   POST /api/run          → kør alle agenter { "city": "Horsens" }
#   GET  /health           → server-ping
# =============================================================================

import sys
import os
import json
import logging
import threading
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from agents.data_agent     import DataAgent
from agents.analysis_agent import AnalysisAgent
from agents.sales_agent    import SalesAgent
from agents.ops_agent      import OpsAgent

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Zyflex AI", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # Tillad dashboard at kalde API'en lokalt
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global state (delt mellem API og agent-tråde) ────────────────────────────
BASE_DIR = Path(__file__).parent.parent

AGENT_STATE = {
    "data_agent":     {"status": "idle", "message": "Venter...", "progress": 0},
    "analysis_agent": {"status": "idle", "message": "Venter...", "progress": 0},
    "sales_agent":    {"status": "idle", "message": "Venter...", "progress": 0},
    "ops_agent":      {"status": "idle", "message": "Venter...", "progress": 0},
}
STATE_LOCK   = threading.Lock()
LATEST_REPORT = {}
IS_RUNNING    = False


# ── API-endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/status")
def get_status():
    with STATE_LOCK:
        return {
            "agents":     AGENT_STATE.copy(),
            "is_running": IS_RUNNING,
            "city":       LATEST_REPORT.get("city", "–"),
            "generated":  LATEST_REPORT.get("generated_at", "–"),
        }


@app.get("/api/report")
def get_report():
    if not LATEST_REPORT:
        rp = BASE_DIR / "data" / "report.json"
        if rp.exists():
            with open(rp, encoding="utf-8") as f:
                return json.load(f)
        return {"error": "Ingen rapport fundet. Kør /api/run først."}
    return LATEST_REPORT


@app.get("/api/alerts")
def get_alerts():
    """Returnerer aktive alarmer – polles hurtigt af dashboard."""
    if not LATEST_REPORT:
        return {"alerts": [], "has_critical": False}
    alerts = _detect_alerts(LATEST_REPORT)
    return {
        "alerts":       alerts,
        "has_critical": any(a["level"] == "critical" for a in alerts),
        "count":        len(alerts),
    }


@app.post("/api/run")
def run_agents(body: dict = {}):
    global IS_RUNNING
    if IS_RUNNING:
        return {"status": "already_running", "message": "Agenter kører allerede"}

    city = body.get("city", "Horsens").strip() or "Horsens"
    thread = threading.Thread(target=_run_all_agents, args=(city,), daemon=True)
    thread.start()
    return {"status": "started", "city": city}


@app.post("/api/feedback")
def driver_feedback(body: dict = {}):
    """Chauffør rapporterer 'ingen kunder her' – gemmes til historisk læring."""
    zone    = body.get("zone", "ukendt")
    action  = body.get("action", "no_customers")   # no_customers | busy | good
    comment = body.get("comment", "")

    feedback_file = BASE_DIR / "data" / "driver_feedback.json"
    feedback_file.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if feedback_file.exists():
        try:
            existing = json.loads(feedback_file.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    entry = {
        "zone":      zone,
        "action":    action,
        "comment":   comment,
        "timestamp": datetime.now().isoformat(),
        "hour":      datetime.now().hour,
        "weekday":   datetime.now().weekday(),
    }
    existing.append(entry)
    # Behold kun de 500 nyeste
    existing = existing[-500:]
    feedback_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"[Feedback] {zone}: {action}")
    return {"status": "ok", "message": f"Feedback gemt for {zone}"}


# ── Agent-orchestrator (kører i baggrundstråd) ────────────────────────────────

def _run_all_agents(city: str):
    global IS_RUNNING, LATEST_REPORT
    IS_RUNNING = True
    _reset_agents()

    try:
        logger.info(f"🚀 Starter alle agenter for '{city}'")

        # ── Agent 1: Data ────────────────────────────────────────────────────
        _set_agent("data_agent", "running", "Starter...", 5)
        data_agent = DataAgent(status_callback=lambda m: _set_agent("data_agent", "running", m))
        data_result = data_agent.run(city)
        _set_agent("data_agent", "done", f"✅ {data_result.get('city')} · {len(data_result.get('events',[]))} events · {len(data_result.get('zones',[]))} zoner", 100)

        # ── Agent 2: Analyse ─────────────────────────────────────────────────
        _set_agent("analysis_agent", "running", "Starter...", 5)
        analysis_agent = AnalysisAgent(status_callback=lambda m: _set_agent("analysis_agent", "running", m))
        analysis_result = analysis_agent.run(data_result)
        top = analysis_result.get("top_zones", [{}])[0]
        _set_agent("analysis_agent", "done", f"✅ Top zone: {top.get('name','?')} ({top.get('score','?')}/100)", 100)

        # ── Agent 3: Sales ───────────────────────────────────────────────────
        _set_agent("sales_agent", "running", "Starter...", 5)
        sales_agent = SalesAgent(status_callback=lambda m: _set_agent("sales_agent", "running", m))
        sales_result = sales_agent.run(data_result, analysis_result)
        _set_agent("sales_agent", "done", f"✅ {sales_result.get('total_leads', 0)} leads fundet", 100)

        # Sørg for konsistente felter til dashboardet
        earnings = sales_result.get("earnings", {})
        if "earn_per_hour" in earnings and "earn_per_hour_dkk" not in earnings:
            earnings["earn_per_hour_dkk"] = earnings["earn_per_hour"]
        sales_result["earnings"] = earnings

        # ── Agent 4: Ops ─────────────────────────────────────────────────────
        _set_agent("ops_agent", "running", "Starter...", 5)
        ops_agent = OpsAgent(status_callback=lambda m: _set_agent("ops_agent", "running", m))
        ops_result = ops_agent.run(data_result, analysis_result)
        est = ops_result.get("earnings", {}).get("daily_est_dkk", 0)
        _set_agent("ops_agent", "done", f"✅ Estimeret dagsindt: {est:,} DKK", 100)

        # ── Byg samlet rapport ───────────────────────────────────────────────
        report = {
            "city":         data_result["city"],
            "generated_at": datetime.now().isoformat(),
            "date":         datetime.now().strftime("%Y-%m-%d"),
            "time":         datetime.now().strftime("%H:%M"),
            "weather":      data_result["weather"],
            "events":       data_result["events"],
            "top_zones":    analysis_result["top_zones"],
            "all_zones":    analysis_result["scored_zones"],
            "hotspots":     analysis_result["hotspots"],
            "avoid_zones":  analysis_result["avoid_zones"],
            "sales":        sales_result,
            "ops":          ops_result,
        }
        report["alerts"] = _detect_alerts(report)
        LATEST_REPORT = report
        _save_report(LATEST_REPORT)

        # Push notifikation hvis score >= 80
        top = analysis_result.get("top_zones", [{}])[0]
        if top.get("score", 0) >= 80:
            _send_push(
                title=f"GO NOW - {top.get('name', 'Hotspot')}",
                message=f"Score {top.get('score')}/100 - Kør hertil nu! {top.get('reason', '')}",
                priority="urgent",
            )

        logger.info(f"✅ Alle agenter færdige for '{city}'")

    except Exception as e:
        logger.error(f"Agent-fejl: {e}", exc_info=True)
        for agent in AGENT_STATE:
            if AGENT_STATE[agent]["status"] == "running":
                _set_agent(agent, "error", f"Fejl: {str(e)[:80]}")
    finally:
        IS_RUNNING = False


# ── Hjælpere ──────────────────────────────────────────────────────────────────

def _set_agent(name: str, status: str, message: str = "", progress: int = None):
    with STATE_LOCK:
        AGENT_STATE[name]["status"]  = status
        AGENT_STATE[name]["message"] = message
        if progress is not None:
            AGENT_STATE[name]["progress"] = progress
        elif status == "running":
            # Auto-increment progress
            AGENT_STATE[name]["progress"] = min(90, AGENT_STATE[name]["progress"] + 10)
        elif status == "done":
            AGENT_STATE[name]["progress"] = 100


def _reset_agents():
    with STATE_LOCK:
        for name in AGENT_STATE:
            AGENT_STATE[name] = {"status": "idle", "message": "Venter...", "progress": 0}


def _detect_alerts(report: dict) -> list:
    """
    Analysér rapporten og generer actionable alarmer til chaufføren.
    Level: critical (rød+lyd) | warning (gul) | info (blå)
    """
    alerts = []
    top_zones = report.get("top_zones", [])
    weather   = report.get("weather",   {})
    events    = report.get("events",    [])
    ops       = report.get("ops",       {})
    hour      = datetime.now().hour

    # ── Kritisk: score 80+ ────────────────────────────────────────────────────
    if top_zones and top_zones[0].get("score", 0) >= 80:
        z = top_zones[0]
        alerts.append({
            "level":   "critical",
            "type":    "HIGH_DEMAND",
            "title":   "⚡ HØJ EFTERSPØRGSEL",
            "message": f"KØR TIL {z['name'].upper()}",
            "sub":     f"Score {z['score']}/100 · {z.get('grade','')}",
            "zone":    z["name"],
            "sound":   True,
        })

    # ── Kritisk: kraftig regn ─────────────────────────────────────────────────
    if weather.get("is_heavy_rain"):
        precip = weather.get("precipitation", 0)
        alerts.append({
            "level":   "critical",
            "type":    "HEAVY_RAIN",
            "title":   "🌧 KRAFTIG REGN",
            "message": f"{precip:.1f} mm/t – Maksimal taxi-efterspørgsel",
            "sub":     "Folk vil IKKE gå – alle vil have taxa",
            "sound":   True,
        })
    elif weather.get("is_raining"):
        alerts.append({
            "level":   "warning",
            "type":    "RAIN",
            "title":   "🌦 LET REGN",
            "message": "Taxi-efterspørgsel stiger",
            "sub":     f"{weather.get('precipitation',0):.1f} mm/t nedbør",
            "sound":   False,
        })

    # ── Warning: events i nærheden ────────────────────────────────────────────
    for evt in events[:2]:
        att = evt.get("attendance", 0)
        if att >= 1000:
            alerts.append({
                "level":   "warning",
                "type":    "EVENT",
                "title":   f"🎉 {evt['name']}",
                "message": f"KØR TIL {evt.get('venue', evt.get('city',''))}",
                "sub":     f"{att:,} gæster · {evt.get('category','')}",
                "sound":   False,
            })

    # ── Info: rush hour ───────────────────────────────────────────────────────
    if 7 <= hour <= 9:
        alerts.append({
            "level":   "info",
            "type":    "RUSH",
            "title":   "⏰ MORGENRUSH",
            "message": f"Hold ved {top_zones[0]['name'] if top_zones else 'stationen'}",
            "sub":     f"Kl. {hour}:00 – rush hour i gang",
            "sound":   False,
        })
    elif 16 <= hour <= 18:
        alerts.append({
            "level":   "info",
            "type":    "RUSH",
            "title":   "⏰ EFTERMIDDAGSRUSH",
            "message": f"Hold ved {top_zones[0]['name'] if top_zones else 'centrum'}",
            "sub":     f"Kl. {hour}:00 – rush hour i gang",
            "sound":   False,
        })

    # ── Info: nuværende anbefaling ────────────────────────────────────────────
    now_action = ops.get("driver_briefing", {}).get("now", "")
    if now_action and not alerts:
        alerts.append({
            "level":   "info",
            "type":    "ACTION",
            "title":   "🚕 ANBEFALING",
            "message": now_action,
            "sub":     f"Opdateret kl. {datetime.now().strftime('%H:%M')}",
            "sound":   False,
        })

    return alerts


def _save_report(report: dict):
    p = BASE_DIR / "data" / "report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)


def _send_push(title: str, message: str, priority: str = "high"):
    """Send push-notifikation via ntfy.sh – gratis, ingen konto nødvendig."""
    try:
        import urllib.request as ur
        channel = os.environ.get("NTFY_CHANNEL", "zyflex-horsens-42x9")
        req = ur.Request(
            f"https://ntfy.sh/{channel}",
            data=message.encode("utf-8"),
            headers={
                "Title":    title,
                "Priority": priority,
                "Tags":     "taxi,denmark",
            },
            method="POST",
        )
        ur.urlopen(req, timeout=5)
        logger.info(f"[Push] Sendt: {title}")
    except Exception as e:
        logger.warning(f"[Push] Fejlede: {e}")


def _auto_refresh_loop():
    """Kør agenter automatisk hver 30. minut."""
    time.sleep(60)   # Vent 1 min efter opstart
    while True:
        try:
            if not IS_RUNNING:
                logger.info("[AutoRefresh] Opdaterer data...")
                _run_all_agents("Horsens")
        except Exception as e:
            logger.error(f"[AutoRefresh] Fejl: {e}")
        time.sleep(30 * 60)   # 30 minutter


# ── Serve dashboard statisk (valgfrit) ───────────────────────────────────────
dashboard_dir = BASE_DIR / "dashboard"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

    @app.get("/")
    def root():
        return FileResponse(str(dashboard_dir / "index.html"))


# ── Start server ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  🚕  ZYFLEX AI – COMMAND CENTER")
    print(f"  📅  {datetime.now().strftime('%A %d. %B %Y, kl. %H:%M')}")
    print("=" * 60)
    print("  🌐  Server:    http://localhost:8000")
    print("  📊  Dashboard: http://localhost:8000")
    print("  🔌  API:       http://localhost:8000/api/status")
    print("=" * 60)
    print("  Åbn http://localhost:8000 i din browser")
    print("  Tryk Ctrl+C for at stoppe\n")

    # Kør automatisk ved opstart for Horsens
    threading.Thread(target=_run_all_agents, args=("Horsens",), daemon=True).start()
    # Auto-refresh hver 30. minut
    threading.Thread(target=_auto_refresh_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
