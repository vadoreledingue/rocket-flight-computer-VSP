# Rocket Flight Computer

Avionics system for model rockets running on **Raspberry Pi Zero 2W**. Monitors flight in real-time, records sensor data, and streams live video from onboard camera.

## Overview

The system consists of **two independent processes** communicating through a shared SQLite database:

- **Flight Controller** (`flight/`) – Reads sensors at 1–20 Hz, tracks flight state, logs data, records video
- **Dashboard Server** (`dashboard/`) – Flask web UI (port 8080) showing live telemetry and configuration

Both can be restarted independently without losing flight data.

---

## Hardware

| Component | Purpose | Connection |
|-----------|---------|------------|
| **BMP280** | Pressure + Temperature | I2C 0x77 (altitude calculation) |
| **MPU-6050** | Accel (3-axis) + Gyro (3-axis) | I2C 0x68 (orientation, acceleration) |
| **PowerBoost 1000C** | Power delivery + LBO pin | GPIO 4 (battery low threshold ~3.2V) |
| **Raspberry Pi Camera Module 3** | Video capture | Camera port (1280×720, 24 fps, H.264 + MJPEG) |

---

## Project Structure

```
rocket-flight-computer-VSP/
├── flight/                          # Flight controller process
│   ├── main.py                      # FlightController class + main loop
│   ├── config.py                    # ConfigManager (DB-backed key-value store)
│   ├── database.py                  # FlightDB (SQLite wrapper)
│   ├── state_machine.py             # Flight state machine (6 states)
│   ├── altitude.py                  # AltitudeCalculator (barometric formula)
│   ├── logger.py                    # FlightLogger (data to DB)
│   ├── camera.py                    # CameraStreamer (picamera2 + MJPEG)
│   └── sensors/
│       ├── bmp280.py                # BMP280 driver (Adafruit)
│       ├── mpu6050.py               # MPU6050 driver (Adafruit + SMBus fallback)
│       ├── power.py                 # PowerSensor (GPIO LBO pin)
│       └── fake.py                  # Simulation sensors (RocketFlightProfile)
│
├── dashboard/                       # Dashboard web server
│   ├── app.py                       # Flask app factory + index route
│   ├── api.py                       # REST API (endpoints + MJPEG stream)
│   ├── static/                      # CSS, JS, fonts (to be added)
│   └── templates/
│       └── dashboard.html           # Main UI (to be added)
│
├── db/
│   └── schema.sql                   # SQLite schema (4 tables)
│
├── scripts/
│   ├── deploy.sh                    # Raspberry Pi deployment script
│   └── run_sim.py                   # Simulation runner (fake sensors)
│
├── tests/                           # pytest unit tests
│
├── config/                          # systemd service files
│   ├── rocket-flight.service        # Flight controller service
│   └── rocket-dashboard.service     # Dashboard service
│
└── docs/
    ├── specs/                       # Design specifications
    └── plans/                       # Implementation plans
```

---

## Flight State Machine

The rocket progresses through **6 states** based on altitude and vertical speed:

```
IDLE ──[arm]──> ARMED ──[launch]──> ASCENT ──[apogee]──> APOGEE ──[instant]──> DESCENT ──[landed]──> LANDED
```

| State | Trigger | Exit Condition |
|-------|---------|----------------|
| **IDLE** | Power-on | Arm command from dashboard |
| **ARMED** | Arm button | Altitude ≥ 5m + vertical speed > 5 m/s |
| **ASCENT** | Launch detected | Falling for ≥ 5 consecutive samples |
| **APOGEE** | Falling detected | Transition to DESCENT (instant) |
| **DESCENT** | Instant | Altitude stable within 1m for ≥ 10 seconds |
| **LANDED** | Landing detected | Flight ends, camera stops, data written |

### Configuration Parameters (in database, live-reloadable)

- `sample_rate_idle` – Hz during IDLE/ARMED (default: 1)
- `sample_rate_flight` – Hz during ASCENT/APOGEE/DESCENT (default: 20)
- `apogee_samples` – Consecutive falling samples to confirm apogee (default: 5)
- `landing_stable_time` – Seconds of stable altitude to confirm landing (default: 10)

---

## Data Storage

All data is stored in **SQLite** (`db/rocket.db`), using WAL mode for concurrent read/write:

### `readings` table
Every sensor sample from every flight:
```sql
flight_id | timestamp | pressure | temperature | altitude | vspeed | 
roll | pitch | yaw | accel_x | accel_y | accel_z | battery_pct | battery_v | state
```

### `flights` table
One row per flight:
```sql
id | started_at | ended_at | max_altitude | max_vspeed | duration | state
```

### `config` table
Live configuration (key-value pairs, reloaded every 1 second during flight):
```sql
key | value | updated_at
```

### `battery_tests` table
Battery capacity testing (optional feature):
```sql
id | started_at | low_at | ended_at | state
```

---

## Flight Controller Loop (`flight/main.py`)

The controller ticks **20 times per second** during flight (configurable):

```python
1. Read sensors (BMP280, MPU6050, battery pin)
2. Calculate altitude from pressure using barometric formula
3. Calculate vertical speed (dAlt / dt)
4. Update flight state machine with latest reading
5. Log all sensor data to database
6. If state changed: print state transition
7. Check for dashboard commands (arm/disarm/calibrate)
8. Sync camera: start recording if ARMED, stop if LANDED
9. Reload config every 1 second (sample rates, thresholds)
10. Sleep until next tick
```

---

## Camera System (`flight/camera.py`)

**CameraStreamer** runs in a dedicated background thread:

- **Recording**: H.264 video file (`flight_YYYYMMDD_HHMMSS.h264`)
- **Streaming**: MJPEG over HTTP (6 fps to dashboard)
- **Frame file**: Single JPEG frame at `/dev/shm/rocket_camera_frame.jpg` (RAM disk, ~100 KB)

The dashboard's `/api/camera/stream` endpoint reads this frame file and serves MJPEG.

**Why split recording and streaming?**
- H.264 playback requires proper decode on desktop
- MJPEG works in any browser without plugins
- Low-bandwidth MJPEG stream doesn't affect recording quality

---

## Dashboard API

All endpoints return JSON. Base URL: `http://rocket.local:8080`

### Flight State & Telemetry

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/status` | GET | Latest sensor reading |
| `/api/history?seconds=60` | GET | Readings from last N seconds |
| `/api/flights` | GET | List all completed flights |

### Configuration

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/config` | GET | All config parameters as JSON |
| `/api/config` | POST | Update multiple config keys (JSON body) |

### Flight Control

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/arm` | POST | Arm rocket (transition to ARMED state) |
| `/api/disarm` | POST | Disarm rocket (return to IDLE) |
| `/api/calibrate` | POST | Recalibrate altitude (set baseline pressure) |

### Battery Testing (Optional)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/battery-test` | GET | Current battery test status |
| `/api/battery-test/start` | POST | Start capacity test |
| `/api/battery-test/stop` | POST | Stop and record test |
| `/api/battery-tests` | GET | History of all tests |
| `/api/battery-tests/clear` | POST | Delete completed tests |

### Hardware Status

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/hardware` | GET | Pin mapping, detected I2C devices, power status |

### Video Stream

| Endpoint | Method | MIME Type | Purpose |
|----------|--------|-----------|---------|
| `/api/camera/stream` | GET | `multipart/x-mixed-replace; boundary=frame` | Live MJPEG stream (6 fps) |

---

## Development

### Simulator

Test the flight controller locally without hardware:

```bash
python scripts/run_sim.py
```

This uses **fake sensors** (`flight/sensors/fake.py`) that simulate a realistic flight profile:
- Launch at 1.5 seconds
- Burn for 2 seconds (35 m/s² acceleration)
- Coast and descend under gravity
- Land when altitude reaches 0

### Tests

```bash
python -m pytest tests/ -v
```

### Local Dashboard

```bash
# Terminal 1: Start flight controller with simulation
python scripts/run_sim.py

# Terminal 2: Start dashboard server
python -m dashboard.app
```

Then open `http://localhost:8080`

---

## Raspberry Pi Deployment

### Prerequisites

```bash
# System-wide dependencies (outside venv)
sudo apt update
sudo apt install -y \
  libcamera-dev python3-libcamera python3-libcamera-binding \
  python3-pip python3-venv git \
  i2c-tools python3-smbus2 \
  python3-rpi.gpio
```

### First-Time Setup

```bash
# Clone and set up on Pi
git clone <repo-url> /opt/rocket
cd /opt/rocket

# Create venv WITH system packages (for libcamera, RPi.GPIO)
python3 -m venv venv --system-site-packages
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Deploy (creates database, systemd services, starts daemons)
bash scripts/deploy.sh
```

### Dashboard URL

```
http://rocket.local:8080
```

### Check Status

```bash
# Flight controller status
sudo systemctl status rocket-flight.service

# Dashboard status
sudo systemctl status rocket-dashboard.service

# View logs
sudo journalctl -u rocket-flight.service -f
sudo journalctl -u rocket-dashboard.service -f
```

### Manual Restart

```bash
sudo systemctl restart rocket-flight.service
sudo systemctl restart rocket-dashboard.service
```

---

## Configuration

All settings are stored in the `config` table and **reloaded every 1 second** during flight. You can:

1. **Via dashboard UI** (if UI exists)
2. **Via API**:
   ```bash
   curl -X POST http://rocket.local:8080/api/config \
     -H "Content-Type: application/json" \
     -d '{"sample_rate_flight": 30, "apogee_samples": 7}'
   ```
3. **Directly in DB** (advanced):
   ```bash
   sqlite3 /opt/rocket/db/rocket.db "UPDATE config SET value='30' WHERE key='sample_rate_flight';"
   ```

---

## Conventions

- **Code**: Python 3, PEP 8, type hints
- **Timestamps**: Unix epoch (seconds.milliseconds) for sensor data, ISO 8601 for flight metadata
- **Coordinates**: Altitude (meters), vertical speed (m/s), angles (degrees)
- **Comments**: English only, explain *why* not *what*
- **Commits**: Manual (no auto-commits without user confirmation)
- **Deployment**: Manual via SSH + deploy script

---

## Troubleshooting

### Camera not starting
```bash
# Check if I2C camera is detected
vcgencmd get_camera

# Ensure venv was created with --system-site-packages
python3 -c "import picamera2; print(picamera2.__version__)"
```

### No I2C devices detected
```bash
# Scan I2C bus
i2cdetect -y 1

# Expected: BMP280 at 0x77, MPU6050 at 0x68
```

### Flight data not saving
```bash
# Check database permissions
ls -la /opt/rocket/db/
# Should be owned by 'vld' user

# Verify database schema
sqlite3 /opt/rocket/db/rocket.db ".schema"
```

### Dashboard server won't start
```bash
# Check port 8080 is not in use
sudo lsof -i :8080

# Verify Flask installation in venv
source venv/bin/activate
python -c "import flask; print(flask.__version__)"
```

---

## Documentation

- **Architecture deep-dive**: See `ARCHITECTURE.md`
- **Design spec**: See `docs/superpowers/specs/2026-04-16-rocket-flight-computer-design.md`
- **API endpoints**: Full reference in `API.md`

---

## Authors & License

See CLAUDE.md for project guidelines.
