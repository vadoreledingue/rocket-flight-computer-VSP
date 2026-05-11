CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id INTEGER,
    timestamp REAL NOT NULL,
    pressure REAL,
    temperature REAL,
    humidity REAL,
    altitude REAL,
    vspeed REAL,
    roll REAL,
    pitch REAL,
    yaw REAL,
    accel_x REAL,
    accel_y REAL,
    accel_z REAL,
    total_accel REAL,
    net_accel REAL,
    battery_pct REAL,
    battery_v REAL,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    max_altitude REAL DEFAULT 0,
    max_vspeed REAL DEFAULT 0,
    duration REAL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'ACTIVE'
);
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS battery_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    low_at REAL,
    ended_at REAL,
    state TEXT NOT NULL DEFAULT 'RUNNING'
);