# Architecture: Rocket Flight Computer

## System Design

The flight computer is a **real-time distributed system** with two processes sharing state through SQLite:

```
┌─────────────────────────────────────┐
│   Rocket (flight)                   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ FlightController (main loop)│   │
│  │ Ticks @ 1-20 Hz             │   │
│  └──┬─────────────────────────┬┘   │
│     │                         │     │
│  ┌──▼────────┐  ┌────────────▼──┐  │
│  │  Sensors  │  │ State Machine │  │
│  │ (BMP280,  │  │  (6 states)   │  │
│  │  MPU6050, │  └───────────────┘  │
│  │  Power)   │                     │
│  └───┬───────┘                     │
│      │                             │
│   ┌──▼──────────────────┐          │
│   │   FlightLogger      │          │
│   │ (writes to DB)      │          │
│   └──┬──────────────────┘          │
│      │                             │
│   ┌──▼──────────────────┐          │
│   │  CameraStreamer     │          │
│   │  (H.264 recording   │          │
│   │   + MJPEG frame)    │          │
│   └─────────────────────┘          │
└──────────┬──────────────────────────┘
           │
      ┌────▼─────┐
      │  SQLite  │
      │  (shared)│
      └────┬─────┘
           │
┌──────────▼────────────────────────┐
│   Dashboard (web server)           │
│   Port 8080                        │
│                                    │
│  ┌────────────────────────────┐   │
│  │   Flask App                │   │
│  │                            │   │
│  │  GET  /api/status          │   │
│  │  GET  /api/history         │   │
│  │  POST /api/arm             │   │
│  │  GET  /api/camera/stream   │   │
│  │  ...                       │   │
│  └────────────────────────────┘   │
│                                    │
└────────────────────────────────────┘
```

## Module Breakdown

### Flight Controller (`flight/main.py`)

**FlightController** is the core real-time loop. It runs continuously and:

1. **Reads all sensors** (BMP280, MPU6050, battery pin)
2. **Calculates derived values** (altitude from pressure, vertical speed from altitude)
3. **Updates state machine** (determines if launched, apogee, landed)
4. **Logs data** (inserts row into `readings` table)
5. **Responds to commands** (arm/disarm from dashboard via `config` table)
6. **Manages camera** (starts/stops recording based on flight state)
7. **Reload configuration** (sample rates, thresholds) once per second

```python
while True:
    tick()  # All steps above
    sleep(1.0 / sample_rate)  # Adaptive: 1 Hz idle, 20 Hz in flight
```

**Key properties:**
- Non-blocking: Every tick must complete within ~50 ms (20 Hz)
- Fault-tolerant: Sensor read failures return `None`, handled gracefully
- Stateful: Tracks flight start time, max altitude, max vertical speed

---

### State Machine (`flight/state_machine.py`)

**StateMachine** models the 6-state rocket lifecycle:

```
IDLE
  ↓ (arm)
ARMED
  ↓ (detect launch: alt ≥ 5m, vspeed > 5 m/s)
ASCENT
  ↓ (detect apogee: 5 consecutive samples with vspeed < 0)
APOGEE
  ↓ (instant transition)
DESCENT
  ↓ (detect landing: alt stable within 1m for 10 seconds)
LANDED
```

**State transitions are one-way** (except ARMED ↔ IDLE via disarm). Once `LANDED`, a new flight requires disarm + re-arm.

**Why 6 states?**
- **IDLE**: Safe, no sensors read, no logging
- **ARMED**: Sensors active, ready for launch, baseline calibration done
- **ASCENT**: Fast climb, high vertical speed, high sample rate (20 Hz)
- **APOGEE**: Transition point, camera and parachute deployment logic
- **DESCENT**: Falling, stable vertical speed, landing detection
- **LANDED**: Flight complete, archive data, safe state

Each tick, the state machine receives:
- `altitude` (meters)
- `vspeed` (m/s)
- `timestamp` (seconds)

It returns the new state (or same state if no transition).

---

### Altitude Calculator (`flight/altitude.py`)

**AltitudeCalculator** computes altitude from barometric pressure using the **hypsometric formula**:

```
altitude = (T / 0.0065) * (1 - (P / P_baseline)^0.190284)
```

Where:
- T = baseline temperature (Kelvin)
- P = current pressure (hPa)
- P_baseline = sea-level calibration pressure (hPa)

**Baseline calibration** happens once when transitioning ARMED → ASCENT. This sets P_baseline and T_baseline from the first valid BMP280 reading.

**Vertical speed** is computed as:
```
vspeed = (altitude_now - altitude_prev) / (time_now - time_prev)
```

Stored in a rolling buffer (50 samples) for smoothing/analysis if needed.

---

### Sensor Drivers (`flight/sensors/`)

#### BMP280 (`flight/sensors/bmp280.py`)

Adafruit CircuitPython driver for pressure + temperature over I2C (0x77).

```python
read() → dict:
    pressure: float (hPa)
    temperature: float (°C)
```

Returns `None` on I2C error (gracefully ignored by FlightController).

#### MPU6050 (`flight/sensors/mpu6050.py`)

Dual-mode IMU driver:

**Primary**: Adafruit CircuitPython `MPU6050` class
**Fallback**: Direct SMBus register reads (if Adafruit fails with "WHO_AM_I mismatch")

```python
read() → dict:
    accel_x, accel_y, accel_z: float (g)
    gyro_x, gyro_y, gyro_z: float (deg/s)
    pitch, roll: float (degrees, computed from accel)
    yaw: float (0.0, not computed)
```

**Euler angles** (pitch, roll) are computed from accelerometer only:
```
pitch = atan2(accel_x, sqrt(accel_y² + accel_z²))
roll = atan2(accel_y, sqrt(accel_x² + accel_z²))
```

This provides a simple estimate of rocket orientation. True orientation requires gyro integration (not implemented).

#### Power Sensor (`flight/sensors/power.py`)

Reads **GPIO pin 4** (LBO from PowerBoost 1000C). LBO is pulled HIGH normally, goes LOW when battery voltage drops below ~3.2V.

```python
read() → dict:
    battery_v: float (3.2 if LOW, 3.8 otherwise)
    battery_pct: float (10 if LOW, 80 otherwise)
    battery_low: bool
```

⚠️ **Current implementation is crude**: just returns static values based on LBO pin state. A real implementation would:
- Use ADC to read actual voltage
- Estimate charge % from voltage curve (Li-Po discharge profile)

#### Fake Sensors (`flight/sensors/fake.py`)

**RocketFlightProfile** simulates a realistic flight:
- Launch delay: 1.5 seconds
- Motor burn: 2 seconds @ 35 m/s² acceleration
- Coasting + gravity descent
- Landing when altitude ≤ 0

`FakeBMP280Sensor`, `FakeMPU6050Sensor`, `FakePowerSensor` wrap the profile and return realistic data based on elapsed time.

---

### Flight Logger (`flight/logger.py`)

**FlightLogger** writes sensor data to the database:

1. `start_flight()` → creates a new row in `flights` table, returns `flight_id`
2. `log(sensor_data, state, timestamp)` → appends row to `readings` table
3. `end_flight(max_altitude, max_vspeed, duration)` → marks flight completed, stores summary

All timestamps are **Unix epoch** (seconds.milliseconds).

---

### Camera System (`flight/camera.py`)

**CameraStreamer** runs in a background thread and handles:

1. **H.264 Recording**: Full-quality video, written directly to disk
   - File: `/opt/rocket/data/videos/flight_YYYYMMDD_HHMMSS.h264`
   - Bitrate: 2 Mbps
   - Resolution: 1280×720 @ 24 fps

2. **MJPEG Frame Extraction**: Every ~167 ms (6 fps), extracts a JPEG frame
   - File: `/dev/shm/rocket_camera_frame.jpg` (RAM disk, fast I/O)
   - Size: ~100 KB per frame
   - Used for dashboard live preview

**Why two video outputs?**
- H.264 is efficient and records at full framerate (24 fps), but requires decoding
- MJPEG is browser-compatible, but would be bandwidth-heavy at 24 fps
- Solution: Record H.264 for post-flight analysis, stream MJPEG for live monitoring

**Thread safety:**
- Camera thread writes to `/dev/shm/rocket_camera_frame.jpg` atomically (write to `.tmp`, then `os.replace()`)
- Dashboard server reads the file, tolerates missing/corrupted frames gracefully

---

### Configuration Manager (`flight/config.py`)

**ConfigManager** provides a simple key-value store backed by SQLite:

```python
cfg.get(key) → Any          # Read from cache (or defaults)
cfg.set(key, value) → None  # Write to DB and cache
cfg.reload() → None         # Refresh cache from DB
cfg.all() → dict            # All keys as dict
```

**Design pattern:**
- In-memory cache (dict) for fast reads during tight loop
- Every 1 second, reload from DB to pick up dashboard changes
- All values are stored as JSON strings in DB

**Default values** (initialized once if not in DB):
```python
DEFAULTS = {
    "sample_rate_idle": 1,           # Hz when IDLE/ARMED
    "sample_rate_flight": 20,        # Hz when ASCENT/APOGEE/DESCENT
    "apogee_samples": 5,             # Falling samples to confirm apogee
    "landing_stable_time": 10,       # Seconds of stable alt to confirm landing
}
```

Dashboard can POST to `/api/config` to update any parameter without restarting flight controller.

---

### Database (`flight/database.py` + `db/schema.sql`)

**FlightDB** is a thin wrapper around SQLite, using WAL mode for concurrent access.

#### Tables

**readings** – Sensor data, one row per sample
```sql
id | flight_id | timestamp | pressure | temperature | humidity | altitude | vspeed |
roll | pitch | yaw | accel_x | accel_y | accel_z | battery_pct | battery_v | state
```
- 100,000+ rows per long flight (20 Hz × 3600 seconds)
- Indexed by flight_id for fast queries per-flight

**flights** – One row per completed flight
```sql
id | started_at | ended_at | max_altitude | max_vspeed | duration | state
```
- started_at, ended_at: ISO 8601 timestamps
- state: "ACTIVE" or "COMPLETED"

**config** – Live configuration (key-value pairs)
```sql
key | value | updated_at
```
- Every write includes current timestamp
- FlightController reloads every 1 second

**battery_tests** – Optional battery capacity testing
```sql
id | started_at | low_at | ended_at | state
```
- Tracks when battery hits LBO threshold during a test

---

### Dashboard API (`dashboard/api.py`)

**create_api_blueprint()** returns a Flask Blueprint with endpoints:

#### Status & History
- `GET /api/status` – Latest reading (single row)
- `GET /api/history?seconds=60` – Recent readings (N seconds)
- `GET /api/flights` – All completed flights

#### Configuration
- `GET /api/config` – All config as JSON
- `POST /api/config` – Update config (body: JSON dict)

#### Flight Control
- `POST /api/arm` – Set `arm_requested=true` in config (flight controller will respond)
- `POST /api/disarm` – Set `disarm_requested=true` in config
- `POST /api/calibrate` – Trigger altitude recalibration

#### Hardware Status
- `GET /api/hardware` – Scans I2C, checks power status, returns pin mapping

#### Battery Testing
- `GET /api/battery-test` – Current test status
- `POST /api/battery-test/start` – Begin test
- `POST /api/battery-test/stop` – End test
- `GET /api/battery-tests` – All tests
- `POST /api/battery-tests/clear` – Delete completed tests

#### Video Stream
- `GET /api/camera/stream` – **MJPEG stream** (multipart/x-mixed-replace)

---

### Dashboard Server (`dashboard/app.py`)

**create_app()** sets up Flask with:

1. Shared database and configuration managers
2. API blueprint
3. Index route (`GET /` → `dashboard.html`)

```python
app.config["db"] = FlightDB(...)
app.config["config_manager"] = ConfigManager(...)
app.config["camera_frame_file"] = Path(...)
```

Entry point: `python -m dashboard.app` (runs on `0.0.0.0:8080`)

---

## Data Flow Example: Launch to Landing

### Timeline

**T=0.0 (startup)**
1. Flight controller initializes: reads config, calibrates baseline pressure
2. State: IDLE
3. Dashboard shows status, receives 1 Hz sensor updates

**T=10.0 (arm via dashboard)**
1. Dashboard POST `/api/arm` → sets `arm_requested=true` in config
2. Flight controller's next reload (1 sec check) picks up the flag
3. Calls `state_machine.arm()`
4. State: ARMED
5. Camera thread starts (begins H.264 recording)

**T=12.0 (launch)**
1. Rocket accelerates (vertical_speed goes from 0 → 5 m/s, altitude 0 → 5m)
2. Flight controller detects: `alt ≥ 5.0 and vspeed > 5.0`
3. State: ASCENT
4. Sample rate increases to 20 Hz (tighter loop)
5. Max altitude tracking begins

**T=14.0 (apogee)**
1. Vertical speed becomes negative (starts falling)
2. FlightController counts falling samples: 1, 2, 3, 4, 5 consecutive ticks
3. After 5 samples: State APOGEE
4. Instant transition to DESCENT

**T=14.5 (descent)**
1. State: DESCENT
2. Altitude still decreasing, but now looking for **stable** descent
3. Baseline altitude recorded; if next sample is within 1m, timer starts

**T=26.0 (landing, 10 seconds stable)**
1. Altitude ≈ 0, stable for 10 seconds
2. State: LANDED
3. Flight controller logs: `max_altitude=150m, max_vspeed=45m/s, duration=16sec`
4. Camera thread stops, H.264 file closed
5. MJPEG frame file deleted

**T=26.1 (post-landing)**
1. State remains LANDED (stays safe until disarm)
2. Dashboard shows flight summary
3. User can download H.264 video, inspect telemetry

---

## Communication Patterns

### Flight Controller → Dashboard

**Unidirectional write** (via DB):
- Every tick: `readings` table gets new row
- Flight summary: `flights` table updated on LANDED

**Latency**: ~0 ms (same machine, local SQLite)

### Dashboard → Flight Controller

**Bidirectional via `config` table**:
1. Dashboard POSTs `/api/arm` → sets flag in DB
2. Flight controller reloads config (1 sec poll)
3. Detects flag, calls `state_machine.arm()`
4. Clears flag for next command

**Latency**: Up to 1 second (reactive polling)

### Camera Frame Sharing

**Shared file** (`/dev/shm/rocket_camera_frame.jpg`):
1. Camera thread writes atomically (`.tmp` → replace)
2. Dashboard reads when client connects to `/api/camera/stream`
3. No database round-trip, just filesystem I/O

---

## Error Handling Philosophy

**Graceful degradation:**
- Sensor read fails → return `None` → FlightController uses last known value or default
- Camera fails → logs error, continues flight logging
- Dashboard server crashes → flight controller unaffected
- Config reload fails → uses cached config (safe defaults apply)

**No exceptions escape the main loop** – all errors logged to stdout/stderr.

---

## Performance Considerations

### Real-Time Loop (Flight Controller)

- **Target**: 20 Hz during flight = 50 ms per tick
- **Sensor reads**: ~5 ms (I2C @ 100 kHz)
- **Calculations**: ~2 ms (altitude, vspeed, state machine)
- **DB insert**: ~10 ms (SQLite commit)
- **Config reload** (1× per second): ~5 ms
- **Camera frame** (6 fps = 6× per 20 ticks): ~5 ms

Total: ~27 ms / 50 ms = 54% utilization. ✓ Safe margin.

### Database

- **WAL mode**: Readers don't block writers
- **~100 readings/sec during flight**: Grows DB by ~5 MB per hour
- **Typical flight**: 15–30 minutes = 50–150 MB

### Network

- **MJPEG stream**: 6 fps × 100 KB = 600 KB/s (2.5 Mbps) – requires decent WiFi
- **API queries**: Negligible (<1 KB/request)

---

## Future Improvements

1. **True IMU fusion**: Use gyro integration + accelerometer for better pitch/roll/yaw
2. **Parachute deployment logic**: In APOGEE state, trigger servo/pyro release
3. **Telemetry radio**: Send live data over LoRa / XBee for range testing
4. **Web UI**: Currently `/dashboard/static/` and `/dashboard/templates/` are empty
5. **Data export**: CSV / JSON download of flights
6. **Battery voltage monitoring**: Use ADC instead of just LBO pin
7. **GNSS integration**: GPS coordinates (requires u-Blox or similar)
8. **Persistent logs**: Flight controller should log to file (not just print)
