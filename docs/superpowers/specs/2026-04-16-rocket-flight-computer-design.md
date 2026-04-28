# Rocket Flight Computer – Design Spec

## Overview

Flight computer software for a model rocket based on a Raspberry Pi Zero. The system consists of two independent processes: a **Flight Controller** (sensor readout, data logging, flight logic, parachute deployment) and a **Dashboard Server** (web-based avionics-style monitoring and configuration UI).

## Hardware

| Component                 | Purpose                          | Interface      | Status             |
| ------------------------- | -------------------------------- | -------------- | ------------------ |
| Raspberry Pi Zero 2W      | Main computer                    | –              | Running            |
| Adafruit PowerBoost 1000C | Power supply                     | GPIO/I2C       | Connected          |
| 3.7V LiPo Battery         | Energy source                    | via PowerBoost | Connected          |
| BMP280                    | Pressure, temperature            | I2C (0x76)     | Connected, working |
| MPU-6050                  | Accelerometer + 3-axis gyroscope | I2C (0x68)     | Connected, working |

## Architecture

Two independent processes, communicating exclusively via SQLite:

```
Flight Controller (Daemon)  ──►  SQLite DB  ◄──  Dashboard Server (Flask)
```

- `rocket-flight.service` – starts on boot, always running
- `rocket-dashboard.service` – optional, manually started/stopped

## Flight Controller

### Main Loop

Runs at configurable frequency (1 Hz idle, 20 Hz in flight):

1. Read all sensors (BME280, BNO055, PowerBoost)
2. Compute barometric altitude from pressure
3. Update flight state machine
4. Write data to SQLite
5. Check for config changes (~1s interval)

### State Machine

```
IDLE ──► ARMED ──► ASCENT ──► APOGEE ──► DESCENT ──► LANDED
 │          │
 └──────────┘ (Disarm)
```

| State   | Trigger                                   | Action                                     |
| ------- | ----------------------------------------- | ------------------------------------------ |
| IDLE    | Default after boot                        | Sensors active, no logging                 |
| ARMED   | Manual via Dashboard                      | Logging starts, baseline pressure captured |
| ASCENT  | Acceleration + altitude increase detected | High-frequency logging (20 Hz)             |
| APOGEE  | Altitude decreasing over N samples        | GPIO pin fires (deployment)                |
| DESCENT | After deployment, altitude dropping       | Logging continues                          |
| LANDED  | Altitude stable near ground for ~10s      | Logging stops, flight saved                |

### Apogee Detection

- Primary: Barometric altitude via moving average – triggers when altitude drops over `apogee_samples` consecutive readings
- Secondary: BNO055 acceleration data as confirmation
- Safety: Minimum altitude (`min_deploy_altitude`) and minimum flight time (`min_flight_time`) must be met before deployment can trigger

### Deployment

- GPIO pin is set HIGH for `deploy_duration` seconds at apogee
- Hardware (e-match/relay/MOSFET) to be determined later
- Software prepares a generic GPIO signal

### Data Rates

| State                     | Sample Rate           |
| ------------------------- | --------------------- |
| IDLE / ARMED              | 1 Hz                  |
| ASCENT / APOGEE / DESCENT | 20 Hz                 |
| LANDED                    | 1 Hz, stops after 30s |

### Sensor Notes

- **BMP280** : Mesure pression et température uniquement (pas d'humidité)
- **MPU-6050** : Fournit accélération + vitesse angulaire (gyro), pas de magnétomètre
  - Yaw toujours 0 (pas de fusion 9-DOF)
  - Pitch/Roll calculés à partir de l'accéléromètre
  - Données gyro disponibles : `gyro_x`, `gyro_y`, `gyro_z`

## Dashboard Server

### Technology

- Backend: Flask (Python)
- Frontend: Plain HTML/CSS/JavaScript, no framework
- Data updates: `fetch()` polling every 500ms against JSON API

### API

| Method | Endpoint                  | Description                                      |
| ------ | ------------------------- | ------------------------------------------------ |
| GET    | `/`                       | Serve dashboard page                             |
| GET    | `/api/status`             | Current flight state + latest sensor values      |
| GET    | `/api/history?seconds=60` | Time series of last N seconds                    |
| GET    | `/api/config`             | Read current configuration                       |
| POST   | `/api/config`             | Update configuration (thresholds etc.)           |
| POST   | `/api/arm`                | Arm rocket (IDLE → ARMED)                        |
| POST   | `/api/disarm`             | Disarm rocket (ARMED → IDLE)                     |
| GET    | `/api/flights`            | List of past flights (for future replay feature) |

### Dashboard Layout – Avionics Glass Cockpit Style

```
┌──────────────────────────────────────────────────────────┐
│  ROCKET FLIGHT COMPUTER          State: ARMED    12:34:05│
├────────────┬─────────────────────────┬───────────────────┤
│            │                         │                   │
│  ALTITUDE  │    ATTITUDE INDICATOR   │   VERTICAL SPEED  │
│  (tape)    │    (artificial horizon) │   (tape)          │
│            │                         │                   │
├────────────┴──────────┬──────────────┴───────────────────┤
│  ENVIRONMENT          │  SYSTEM                          │
│  Pressure, Temp, Hum  │  Battery %, Voltage, Flight Time │
├───────────────────────┴──────────────────────────────────┤
│  [ ARM ] [ DISARM ] [ CONFIG ]              ● Connected  │
└──────────────────────────────────────────────────────────┘
```

### Color Scheme

| Element                 | Color             | Hex                              |
| ----------------------- | ----------------- | -------------------------------- |
| Background              | Dark blue         | `#0a1628` to `#1a2a4a`           |
| Primary text            | White             | `#ffffff`                        |
| Secondary text          | Dimmed blue-white | `#8899bb`                        |
| Accents / active values | Cyan              | `#00ccff`                        |
| Warnings                | Amber             | `#ffaa00`                        |
| Critical                | Red               | `#ff3344`                        |
| OK status               | Green             | `#00ff88`                        |
| Font                    | Monospace         | `JetBrains Mono` / `Courier New` |

## Database (SQLite)

### Tables

**readings** – one row per sensor tick:

- `id`, `flight_id`, `timestamp`, `pressure`, `temperature`, `humidity`, `altitude`, `vspeed`, `roll`, `pitch`, `yaw`, `accel_x`, `accel_y`, `accel_z`, `battery_pct`, `battery_v`, `state`

**flights** – one row per flight:

- `id`, `started_at`, `ended_at`, `max_altitude`, `max_vspeed`, `duration`, `state` (COMPLETED/ABORTED)

**config** – key/value store:

- `key`, `value` (JSON-encoded), `updated_at`

### Default Configuration

| Key                   | Default | Description                                     |
| --------------------- | ------- | ----------------------------------------------- |
| `sample_rate_idle`    | `1`     | Hz in IDLE/ARMED                                |
| `sample_rate_flight`  | `20`    | Hz in flight                                    |
| `min_deploy_altitude` | `30`    | Meters – no deployment below this               |
| `min_flight_time`     | `2`     | Seconds – minimum flight time before deployment |
| `apogee_samples`      | `5`     | Consecutive falling readings to confirm apogee  |
| `deploy_pin`          | `17`    | GPIO pin for deployment                         |
| `deploy_duration`     | `1.0`   | Seconds the pin stays HIGH                      |
| `landing_stable_time` | `10`    | Seconds of stable altitude → LANDED             |

## Deployment

Manual deployment via SSH. No automatic triggers.

```bash
# On developer PC:
git push origin main

# SSH into Pi:
ssh pi@rocket.local
cd /opt/rocket
git pull
pip install -r requirements.txt
sudo systemctl restart rocket-flight rocket-dashboard
```

A `deploy.sh` script wraps these steps for convenience, but is always run manually.

## Project Structure

```
rocket/
├── flight/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── state_machine.py
│   ├── sensors/
│   │   ├── __init__.py
│   │   ├── bme280.py
│   │   ├── bno055.py
│   │   └── power.py
│   ├── deployment.py
│   ├── altitude.py
│   └── logger.py
├── dashboard/
│   ├── __init__.py
│   ├── app.py
│   ├── api.py
│   ├── static/
│   │   ├── css/
│   │   │   └── cockpit.css
│   │   └── js/
│   │       ├── main.js
│   │       └── gauges.js
│   └── templates/
│       └── dashboard.html
├── db/
│   └── schema.sql
├── config/
│   ├── rocket-flight.service
│   └── rocket-dashboard.service
├── scripts/
│   └── deploy.sh
├── requirements.txt
├── setup.py
├── README.md
└── .gitignore
```

## Future Features (Out of Scope for MVP)

- **Live telemetry** – streaming sensor data over WiFi during flight
- **Flight replay** – play back recorded flights in the dashboard
- All sensors fully operational (BMP280, MPU-6050, PowerBoost 1000C) – GitHub Actions / webhook-based deploy

## User Constraints

- Languages: Python, HTML, CSS, basic JavaScript
- No frontend frameworks
- Manual deployment only
- BME280 and PowerBoost already operational
- BNO055 not yet connected
