import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
try:
    import thranw_router
    print("[OK] thranw_router importeret")
    from agents.thranw_agent import ThranwAgent
    print("[OK] ThranwAgent importeret")
    print("[OK] Alt klar")
except Exception as e:
    print("[FEJL]", type(e).__name__, e)
    traceback.print_exc()
