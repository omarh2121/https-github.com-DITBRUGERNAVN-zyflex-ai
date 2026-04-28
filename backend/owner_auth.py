# =============================================================================
# owner_auth.py – Privat PIN-login til ejer-dashboard
# PIN sættes via env var ADMIN_PIN (default: 2121)
# =============================================================================
import os, json, secrets
from pathlib import Path
from datetime import datetime

OWNER_PIN       = os.environ.get("ADMIN_PIN", "2121")
SESSIONS_FILE   = Path(__file__).parent.parent / "data" / "owner_sessions.json"


def verify_pin(pin: str) -> str | None:
    """Verificer PIN og returner session-token hvis korrekt."""
    if str(pin).strip() == OWNER_PIN:
        token = secrets.token_hex(32)
        _save_token(token)
        return token
    return None


def verify_token(token: str) -> bool:
    """Tjek om token er gyldig."""
    if not token:
        return False
    return token in _load_tokens()


def revoke_token(token: str):
    tokens = _load_tokens()
    tokens = [t for t in tokens if t != token]
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
