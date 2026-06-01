# =============================================================================
# langgraph_system/__init__.py
#
# Zyflex AI – LangGraph Multi-Agent System
# Eksponerer det centrale workflow og convenience-funktioner.
# =============================================================================

from .workflow import build_workflow, run_dispatch_workflow
from .state import ZyflexState

__all__ = ["build_workflow", "run_dispatch_workflow", "ZyflexState"]
