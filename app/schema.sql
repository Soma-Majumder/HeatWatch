-- HeatWatch data model (BUILD_PLAN.md section 3)

-- Cached copy of the public 311 / HPD complaints (source of priors and address history)
CREATE TABLE IF NOT EXISTS hpd_complaints (
    unique_key                     TEXT PRIMARY KEY,
    created_date                   TEXT NOT NULL,
    closed_date                    TEXT,
    status                         TEXT,
    descriptor                     TEXT,   -- ENTIRE BUILDING | APARTMENT ONLY
    incident_address               TEXT,
    incident_zip                   TEXT,
    community_board                TEXT,
    borough                        TEXT,
    resolution_description         TEXT,
    resolution_action_updated_date TEXT,
    latitude                       REAL,
    longitude                      REAL,
    loaded_at                      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_hpd_created ON hpd_complaints(created_date);
CREATE INDEX IF NOT EXISTS ix_hpd_address ON hpd_complaints(incident_address);

-- HeatWatch's own tickets
CREATE TABLE IF NOT EXISTS tickets (
    id             TEXT PRIMARY KEY,        -- HW-XXXXXX, non-sequential
    created_at     TEXT NOT NULL,
    address_norm   TEXT,
    address_raw    TEXT,
    zip            TEXT,
    scope          TEXT CHECK (scope IN ('building','apartment')),
    problem        TEXT CHECK (problem IN ('heat','hot_water','both')),
    duration_hours REAL,
    vulnerable     INTEGER NOT NULL DEFAULT 0,
    safety_flag    INTEGER NOT NULL DEFAULT 0,
    description    TEXT,
    priority       TEXT CHECK (priority IN ('critical','high','normal','low')),
    score          REAL,
    score_reasons  TEXT,                    -- JSON
    stage          TEXT NOT NULL DEFAULT 'received',
    eta_hours      REAL,
    linked_311_key TEXT,
    duplicate_of   TEXT,
    lang           TEXT NOT NULL DEFAULT 'en'
);
CREATE INDEX IF NOT EXISTS ix_tickets_address ON tickets(address_norm);
CREATE INDEX IF NOT EXISTS ix_tickets_stage ON tickets(stage);

CREATE TABLE IF NOT EXISTS ticket_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL REFERENCES tickets(id),
    at        TEXT NOT NULL,
    stage     TEXT NOT NULL,
    actor     TEXT NOT NULL CHECK (actor IN ('agent','tenant','reviewer','system')),
    note      TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_ticket ON ticket_events(ticket_id);

CREATE TABLE IF NOT EXISTS escalations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL REFERENCES tickets(id),
    rule      TEXT NOT NULL,
    reason    TEXT,
    at        TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','ack','closed')),
    reviewer  TEXT
);

-- Derived tables, rebuilt from hpd_complaints in phase 1
CREATE TABLE IF NOT EXISTS address_stats (
    address_norm      TEXT PRIMARY KEY,
    complaints_2y     INTEGER NOT NULL,
    last_complaint_at TEXT,
    repeat_flag       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS priors (
    key         TEXT PRIMARY KEY,           -- scope|month|hour_bucket
    n           INTEGER NOT NULL,
    p50_close_h REAL,
    p75_close_h REAL,
    p90_close_h REAL,
    dup_rate    REAL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
