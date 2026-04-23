# =============================================================================
# auth.py - Google OAuth + Session Management
# =============================================================================

import os, json, secrets, time, logging
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
ADMIN_EMAIL          = "omarhajimohamed62@gmail.com"

BASE_DIR       = Path(__file__).parent.parent
COMPANIES_FILE = BASE_DIR / "data" / "companies.json"
INVOICES_FILE  = BASE_DIR / "data" / "invoices.json"
SESSIONS_FILE  = BASE_DIR / "data" / "sessions.json"

SESSION_TTL = 60 * 60 * 24 * 30  # 30 dage


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _read(path: Path, default):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Google token verifikation ─────────────────────────────────────────────────

def verify_google_token(credential: str) -> dict | None:
    """Verificer Google ID-token via Googles tokeninfo API."""
    try:
        resp = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
            timeout=8
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Verificer at token er til vores app
        if GOOGLE_CLIENT_ID and data.get("aud") != GOOGLE_CLIENT_ID:
            logger.warning(f"Token audience mismatch: {data.get('aud')}")
            # Tillad under udvikling uden client_id sat
            if GOOGLE_CLIENT_ID:
                return None
        return {
            "email":   data.get("email", ""),
            "name":    data.get("name", ""),
            "picture": data.get("picture", ""),
            "sub":     data.get("sub", ""),
        }
    except Exception as e:
        logger.error(f"Google token fejl: {e}")
        return None


# ── Sessions ──────────────────────────────────────────────────────────────────

def create_session(user: dict) -> str:
    token = secrets.token_urlsafe(32)
    sessions = _read(SESSIONS_FILE, {})
    sessions[token] = {
        "email":   user["email"],
        "name":    user["name"],
        "picture": user.get("picture", ""),
        "created": time.time(),
        "expires": time.time() + SESSION_TTL,
    }
    # Ryd udløbne sessioner
    sessions = {k: v for k, v in sessions.items() if v["expires"] > time.time()}
    _write(SESSIONS_FILE, sessions)
    return token

def get_session(token: str) -> dict | None:
    if not token:
        return None
    sessions = _read(SESSIONS_FILE, {})
    s = sessions.get(token)
    if not s:
        return None
    if s["expires"] < time.time():
        return None
    return s

def delete_session(token: str):
    sessions = _read(SESSIONS_FILE, {})
    sessions.pop(token, None)
    _write(SESSIONS_FILE, sessions)


# ── Companies (multi-tenant) ──────────────────────────────────────────────────

def get_company(email: str) -> dict | None:
    companies = _read(COMPANIES_FILE, {})
    return companies.get(email)

def create_company(email: str, name: str, company: str, city: str) -> dict:
    companies = _read(COMPANIES_FILE, {})
    if email in companies:
        return companies[email]
    entry = {
        "email":      email,
        "name":       name,
        "company":    company,
        "city":       city,
        "created_at": time.strftime("%Y-%m-%d"),
        "status":     "active",   # active | suspended
        "plan":       "trial",    # trial | paid
    }
    companies[email] = entry
    _write(COMPANIES_FILE, companies)
    logger.info(f"Ny virksomhed oprettet: {company} ({email})")
    return entry

def update_company_status(email: str, status: str):
    companies = _read(COMPANIES_FILE, {})
    if email in companies:
        companies[email]["status"] = status
        _write(COMPANIES_FILE, companies)

def get_all_companies() -> list:
    companies = _read(COMPANIES_FILE, {})
    return list(companies.values())


# ── Invoices ──────────────────────────────────────────────────────────────────

def get_invoices(email: str = None) -> list:
    invoices = _read(INVOICES_FILE, [])
    if email:
        return [i for i in invoices if i["email"] == email]
    return invoices

def create_invoice(email: str, company: str, amount: int, month: str) -> dict:
    invoices = _read(INVOICES_FILE, [])
    inv = {
        "id":       f"ZYF-{int(time.time())}",
        "email":    email,
        "company":  company,
        "amount":   amount,
        "month":    month,
        "sent_at":  time.strftime("%Y-%m-%d"),
        "paid":     False,
        "paid_at":  None,
    }
    invoices.append(inv)
    _write(INVOICES_FILE, invoices)
    return inv

def mark_invoice_paid(invoice_id: str):
    invoices = _read(INVOICES_FILE, [])
    for inv in invoices:
        if inv["id"] == invoice_id:
            inv["paid"]    = True
            inv["paid_at"] = time.strftime("%Y-%m-%d")
    _write(INVOICES_FILE, invoices)

def is_admin(email: str) -> bool:
    return email == ADMIN_EMAIL
