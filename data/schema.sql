-- =============================================================================
-- Zyflex Demand Radar – Database Schema
-- SQLite for local dev, Supabase/Postgres for production
-- =============================================================================

-- ── Drivers ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS drivers (
    id          TEXT PRIMARY KEY,           -- UUID
    name        TEXT NOT NULL DEFAULT '',
    company_id  TEXT,
    car_id      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Taxi Zones ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS taxi_zones (
    id             TEXT PRIMARY KEY,        -- UUID
    name           TEXT NOT NULL,
    type           TEXT NOT NULL,           -- centrum, hotel, arena, station, hospital, nightlife, industrial
    city           TEXT NOT NULL DEFAULT 'Horsens',
    lat            REAL,
    lng            REAL,
    radius_meters  INTEGER DEFAULT 500,
    base_score     INTEGER DEFAULT 50,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Recommendations ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recommendations (
    id                   TEXT PRIMARY KEY,  -- UUID
    driver_id            TEXT,              -- nullable → anonym
    anonymous_session_id TEXT,
    zone_id              TEXT NOT NULL,
    score                INTEGER NOT NULL,
    action_text          TEXT NOT NULL,
    reason               TEXT,
    shown_at             TEXT NOT NULL DEFAULT (datetime('now')),
    status               TEXT DEFAULT 'shown',  -- shown, accepted, rejected, expired
    FOREIGN KEY (zone_id) REFERENCES taxi_zones(id)
);

-- ── Driver Events ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS driver_events (
    id                   TEXT PRIMARY KEY,  -- UUID
    driver_id            TEXT,
    anonymous_session_id TEXT,
    event_type           TEXT NOT NULL,     -- se action_types
    zone_id              TEXT,
    recommendation_id    TEXT,
    metadata_json        TEXT DEFAULT '{}',
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Driver Feedback ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS driver_feedback (
    id                   TEXT PRIMARY KEY,  -- UUID
    driver_id            TEXT,
    anonymous_session_id TEXT,
    recommendation_id    TEXT,
    rating               TEXT,             -- good, bad
    got_trip             INTEGER,           -- 1=ja, 0=nej, NULL=ukendt
    comment              TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_driver_events_type       ON driver_events(event_type);
CREATE INDEX IF NOT EXISTS idx_driver_events_created    ON driver_events(created_at);
CREATE INDEX IF NOT EXISTS idx_driver_events_zone       ON driver_events(zone_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_shown    ON recommendations(shown_at);
CREATE INDEX IF NOT EXISTS idx_feedback_rating          ON driver_feedback(rating);

-- ── Seed: Horsens Zoner ───────────────────────────────────────────────────────
INSERT OR IGNORE INTO taxi_zones (id, name, type, city, lat, lng, radius_meters, base_score) VALUES
('zone-001', 'Horsens Centrum',       'centrum',    'Horsens', 55.8612, 9.8498, 600, 65),
('zone-002', 'CASA Arena',            'arena',      'Horsens', 55.8557, 9.8396, 400, 70),
('zone-003', 'Hotel Opus',            'hotel',      'Horsens', 55.8598, 9.8512, 200, 60),
('zone-004', 'Horsens Banegård',      'station',    'Horsens', 55.8580, 9.8430, 300, 58),
('zone-005', 'Regionshospitalet',     'hospital',   'Horsens', 55.8700, 9.8350, 500, 48),
('zone-006', 'Natteliv Søndergade',   'nightlife',  'Horsens', 55.8608, 9.8505, 350, 55),
('zone-007', 'Restaurantkvarteret',   'restaurant', 'Horsens', 55.8615, 9.8490, 300, 52),
('zone-008', 'Industriområde Nord',   'industrial', 'Horsens', 55.8750, 9.8300, 800, 20),
('zone-009', 'Horsens Arena',         'arena',      'Horsens', 55.8560, 9.8400, 500, 68);
