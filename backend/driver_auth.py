# =============================================================================
# driver_auth.py – PIN-login til chauffør-side
# PIN sættes via env var DRIVER_PIN (default: 2121)
# =============================================================================
import os, json, secrets
from pathlib import Path

DRIVER_PIN     = os.environ.get("DRIVER_PIN", "2121")
SESSIONS_FILE  = Path(__file__).parent.parent / "data" / "driver_sessions.json"


def verify_pin(pin: str) -> str | None:
    """Verificer PIN og returner session-token hvis korrekt."""
    if str(pin).strip() == DRIVER_PIN:
        token = secrets.token_hex(32)
        _save_token(token)
        return token
    return None


def verify_token(token: str) -> bool:
    if not token:
        return False
    return token in _load_tokens()


def revoke_token(token: str):
    tokens = [t for t in _load_tokens() if t != token]
    _write_tokens(tokens)


def _load_tokens() -> list:
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_token(token: str):
    tokens = _load_tokens()
    tokens.append(token)
    tokens = tokens[-200:]
    _write_tokens(tokens)


def _write_tokens(tokens: list):
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSIONS_FILE.write_text(json.dumps(tokens), encoding="utf-8")
