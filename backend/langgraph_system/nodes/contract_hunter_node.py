# =============================================================================
# nodes/contract_hunter_node.py
#
# Zyflex AI – ContractHunterNode (LangGraph)
#
# Ansvar:
#   Wrapper om den eksisterende ContractHunterAgent.
#   Finder og scorer potentielle B2B leads:
#   - Hoteller uden faste transportaftaler
#   - Hospitaler og klinikker
#   - Kommunale institutioner
#   - Event-arrangører (CASA Arena, Billetto-promotors)
#   - Flextrafik-kontrakter
#
# VIGTIGT:
#   Denne node køres SEPARAT fra hoved-pipelinen (den er tung).
#   Kaldes fra /ai/leads endpoint – ikke fra /ai/recommendation.
#
# Input fra state:  input_city
# Output til state: leads_all, leads_top, leads_monthly_pot_dkk
# =============================================================================

from __future__ import annotations
import logging
import sys
import os
import time

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agents.contract_hunter import ContractHunterAgent
from langgraph_system.state import ZyflexState

logger = logging.getLogger("zyflex.langgraph.contract_hunter_node")


def contract_hunter_node(state: ZyflexState) -> ZyflexState:
    """
    LangGraph Node: ContractHunterNode

    Finder B2B leads via eksisterende ContractHunterAgent.
    Kræver internet-adgang for at hente OSM-data.

    Input:  input_city (str)
    Output: leads_all, leads_top, leads_monthly_pot_dkk
    """
    city = state.get("input_city", "alle")
    logger.info(f"[ContractHunterNode] Søger leads for '{city}'")
    t_start = time.time()

    errors: list[str] = list(state.get("meta_errors", []))
    node_times: dict = dict(state.get("meta_node_times", {}))

    try:
        # Kald eksisterende ContractHunterAgent (UÆNDRET)
        agent = ContractHunterAgent()
        result = agent.run(city)

        all_leads = result.get("alle_leads", [])
        # Top 10 leads sorteret efter score
        top_leads = sorted(all_leads, key=lambda x: x.get("score", 0), reverse=True)[:10]
        # Månedligt potentiale fra leads med score >= 75
        monthly_pot = sum(l.get("maanedlig_dkk", 0) for l in all_leads if l.get("score", 0) >= 75)

        elapsed = round((time.time() - t_start) * 1000)
        node_times["contract_hunter_node"] = elapsed
        logger.info(
            f"[ContractHunterNode] ✅ {len(all_leads)} leads fundet, "
            f"månedlig potentiale: {monthly_pot:,} DKK, {elapsed}ms"
        )

        return {
            **state,
            "leads_all":              all_leads,
            "leads_top":              top_leads,
            "leads_monthly_pot_dkk":  monthly_pot,
            "meta_node_times":        node_times,
            "meta_errors":            errors,
        }

    except Exception as exc:
        elapsed = round((time.time() - t_start) * 1000)
        node_times["contract_hunter_node"] = elapsed
        err_msg = f"ContractHunterNode fejl: {exc}"
        logger.error(f"[ContractHunterNode] ❌ {err_msg}", exc_info=True)
        errors.append(err_msg)

        return {
            **state,
            "leads_all":              [],
            "leads_top":              [],
            "leads_monthly_pot_dkk":  0,
            "meta_node_times":        node_times,
            "meta_errors":            errors,
        }
