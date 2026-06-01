"""
db.py – Zyflex database lag
Bruger SQLite lokalt. Klar til Supabase/Postgres via DATABASE_URL env-var.

Skift til Postgres:
  DATABASE_URL=postgresql://user:pass@host:5432/zyflex
"""

import os
import sqlite3
import uuid
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

logger = logging.getLogger("db")

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
BASE_DIR     = Path(__file__).parent.parent
SQLITE_PATH  = BASE_DIR / "data" / "zyflex.db"

_USE_POSTGRES = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")

# ── SQLite ────────────────────────────────────────────────────────────────────
def _get_sqlite_conn():
    conn = sqlite3.connect(str(SQLITE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL kan fejle på visse netværks/NTFS mounts – brug DELETE journal i stedet
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
    except Exception:
        pass
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

# ── Postgres (Supabase-klar) ──────────────────────────────────────────────────
def _get_pg_conn():
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    except ImportError:
        raise RuntimeError("psycopg2 ikke installeret. Kør: pip install psycopg2-binary")

@contextmanager
def get_conn():
    if _USE_POSTGRES:
        conn = _get_pg_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = _get_sqlite_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

# ── Init database ─────────────────────────────────────────────────────────────
def init_db():
    """Opret tabeller og seed Horsens-zoner. Fejler aldrig – kun advarsler."""
    schema_path = BASE_DIR / "data" / "schema.sql"
    if not schema_path.exists():
        logger.warning("schema.sql ikke fundet – springer init over")
        return
    try:
        _do_init_db(schema_path)
    except Exception as e:
        logger.warning(f"⚠️  DB init fejlede ({e}) – telemetry kører med fallback mock-data")

def _do_init_db(schema_path: Path):

    sql = schema_path.read_text(encoding="utf-8")

    # Kør statement-for-statement (virker på SQLite, Postgres og NTFS-mounts)
    stmts = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]

    if _USE_POSTGRES:
        with get_conn() as conn:
            cur = conn.cursor()
            for stmt in stmts:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.warning(f"Schema stmt fejl: {e}")
    else:
        # SQLite: åbn direkte (ikke via context manager) for at undgå nesting
        conn = sqlite3.connect(str(SQLITE_PATH), check_same_thread=False)
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            for stmt in stmts:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as e:
                    if "already exists" not in str(e).lower():
                        logger.warning(f"Schema stmt advarsel: {e}")
            conn.commit()
        finally:
            conn.close()

    logger.info(f"✅ Database initialiseret ({'Postgres' if _USE_POSTGRES else 'SQLite'}): {SQLITE_PATH if not _USE_POSTGRES else DATABASE_URL[:30]}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def new_id() -> str:
    return str(uuid.uuid4())

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ── Writers ───────────────────────────────────────────────────────────────────
def insert_driver_event(
    event_type: str,
    driver_id: str | None = None,
    anonymous_session_id: str | None = None,
    zone_id: str | None = None,
    recommendation_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    row_id = new_id()
    meta   = json.dumps(metadata or {}, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO driver_events
               (id, driver_id, anonymous_session_id, event_type, zone_id, recommendation_id, metadata_json, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (row_id, driver_id, anonymous_session_id, event_type, zone_id, recommendation_id, meta, now_iso())
        )
    return row_id

def insert_recommendation(
    zone_id: str,
    score: int,
    action_text: str,
    reason: str = "",
    driver_id: str | None = None,
    anonymous_session_id: str | None = None,
) -> str:
    row_id = new_id()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO recommendations
               (id, driver_id, anonymous_session_id, zone_id, score, action_text, reason, shown_at, status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (row_id, driver_id, anonymous_session_id, zone_id, score, action_text, reason, now_iso(), "shown")
        )
    return row_id

def insert_feedback(
    rating: str,
    got_trip: bool | None = None,
    driver_id: str | None = None,
    anonymous_session_id: str | None = None,
    recommendation_id: str | None = None,
    comment: str = "",
) -> str:
    row_id   = new_id()
    got_trip_int = None if got_trip is None else (1 if got_trip else 0)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO driver_feedback
               (id, driver_id, anonymous_session_id, recommendation_id, rating, got_trip, comment, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (row_id, driver_id, anonymous_session_id, recommendation_id, rating, got_trip_int, comment, now_iso())
        )
    return row_id

# ── Analytics ─────────────────────────────────────────────────────────────────
def get_telemetry_stats() -> dict:
    """Henter aggregerede stats til ejer-dashboard."""
    try:
        with get_conn() as conn:
            def scalar(sql, params=()):
                cur = conn.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row else 0

            total_views    = scalar("SELECT COUNT(*) FROM driver_events WHERE event_type='view_dashboard'")
            total_actions  = scalar("SELECT COUNT(*) FROM driver_events WHERE event_type != 'view_dashboard'")
            accepted       = scalar("SELECT COUNT(*) FROM driver_events WHERE event_type='click_drive_here'")
            good_feedback  = scalar("SELECT COUNT(*) FROM driver_feedback WHERE rating='good'")
            bad_feedback   = scalar("SELECT COUNT(*) FROM driver_feedback WHERE rating='bad'")
            reported_trips = scalar("SELECT COUNT(*) FROM driver_feedback WHERE got_trip=1")

            # Top zoner baseret på driver_events
            cur = conn.execute("""
                SELECT z.name, COUNT(*) as cnt
                FROM driver_events de
                JOIN taxi_zones z ON z.id = de.zone_id
                WHERE de.event_type IN ('click_drive_here','report_got_trip','mark_arrived')
                GROUP BY z.id
                ORDER BY cnt DESC
                LIMIT 5
            """)
            top_zones = [{"name": r[0], "count": r[1]} for r in cur.fetchall()]

        return {
            "total_views":    total_views,
            "total_actions":  total_actions,
            "accepted":       accepted,
            "good_feedback":  good_feedback,
            "bad_feedback":   bad_feedback,
            "reported_trips": reported_trips,
            "top_zones":      top_zones,
        }
    except Exception as e:
        logger.warning(f"Telemetry stats fejl: {e}")
        # Fallback mock-data hvis DB ikke er klar
        return {
            "total_views":    142,
            "total_actions":  87,
            "accepted":       61,
            "good_feedback":  44,
            "bad_feedback":   9,
            "reported_trips": 38,
            "top_zones": [
                {"name": "Horsens Centrum",  "count": 28},
                {"name": "CASA Arena",       "count": 19},
                {"name": "Hotel Opus",       "count": 12},
                {"name": "Banegården",       "count": 9},
                {"name": "Regionshospitalet","count": 6},
            ],
            "_mock": True,
        }
