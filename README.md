# Rocket Flight Computer

Avionics software for a model rocket based on Raspberry Pi Zero 2 W. The project combines a flight controller, a web dashboard, onboard video streaming, and SQLite-based telemetry logging.

## Overview

The system is split into two independent processes that share a single SQLite database:

- `flight/`: reads sensors, computes derived flight data, updates the state machine, logs telemetry, and controls the camera
- `dashboard/`: serves a Flask web UI and REST API for live monitoring and commands

Because both processes communicate through the database, they can be restarted independently without losing flight history.

## Hardware

| Component                    | Purpose                            | Connection           |
| ---------------------------- | ---------------------------------- | -------------------- |
| `BMP280`                     | Pressure and temperature           | I2C `0x77`           |
| `MPU-6050`                   | IMU: acceleration and gyroscope    | I2C `0x68`           |
| Raspberry Pi Camera Module 3 | Video recording and preview stream | CSI camera connector |

The dashboard also exposes Raspberry Pi supply-voltage status through `vcgencmd get_throttled`.

## Project Structure

```text
rocket-flight-computer-VSP/
|-- flight/
|   |-- main.py
|   |-- state_machine.py
|   |-- altitude.py
|   |-- acceleration.py
|   |-- logger.py
|   |-- database.py
|   |-- config.py
|   |-- camera.py
|   |-- orientation.py
|   `-- sensors/
|       |-- bmp280.py
|       `-- mpu6050.py
|-- dashboard/
|   |-- app.py
|   |-- api.py
|   |-- templates/
|   `-- static/
|-- db/
|   `-- schema.sql
|-- config/
|   |-- rocket-flight.service
|   `-- rocket-dashboard.service
|-- scripts/
|   `-- deploy.sh
`-- tests/
```

## Flight State Machine

The rocket progresses through six states:

```text
IDLE -> ARMED -> ASCENT -> APOGEE -> DESCENT -> LANDED
```

Main transition logic:

- `IDLE -> ARMED`: dashboard arm command
- `ARMED -> ASCENT`: altitude >= 5 m, vertical speed > 5 m/s, and net acceleration >= 5 m/s^2
- `ASCENT -> APOGEE`: falling detected for `apogee_samples` consecutive samples
- `APOGEE -> DESCENT`: immediate transition on next update
- `DESCENT -> LANDED`: altitude remains stable within 1 m for `landing_stable_time` seconds

Runtime-tunable parameters stored in the database:

- `sample_rate_idle`
- `sample_rate_flight`
- `apogee_samples`
- `landing_stable_time`

## Data Storage

All telemetry is stored in SQLite with WAL mode enabled.

### `readings`

One row per sample:

```sql
id | flight_id | timestamp | pressure | temperature | altitude | vspeed |
roll | pitch | yaw | accel_x | accel_y | accel_z | total_accel | net_accel | state
```

### `flights`

One row per recorded flight:

```sql
id | started_at | ended_at | max_altitude | max_vspeed | max_net_accel | duration | state
```

### `config`

Live configuration store:

```sql
key | value | updated_at
```

## Flight Controller Loop

`flight/main.py` performs this cycle continuously:

1. Read `BMP280` and `MPU6050`
2. Compute altitude and vertical speed
3. Compute total and net acceleration
4. Update the state machine
5. Start or stop the camera depending on flight state
6. Log the sample to SQLite
7. Reload configuration periodically and consume dashboard commands

Sampling is adaptive:

- idle or armed: `sample_rate_idle`
- ascent, apogee, descent: `sample_rate_flight`

## Dashboard API

Base URL: `http://rocket.local:8080`

### Telemetry

| Endpoint                  | Method | Purpose                    |
| ------------------------- | ------ | -------------------------- |
| `/api/status`             | `GET`  | Latest reading             |
| `/api/history?seconds=60` | `GET`  | Recent readings            |
| `/api/flights`            | `GET`  | Completed flight summaries |

### Configuration

| Endpoint      | Method | Purpose                     |
| ------------- | ------ | --------------------------- |
| `/api/config` | `GET`  | Current configuration       |
| `/api/config` | `POST` | Update configuration values |

### Commands

| Endpoint         | Method | Purpose                       |
| ---------------- | ------ | ----------------------------- |
| `/api/arm`       | `POST` | Request arm                   |
| `/api/disarm`    | `POST` | Request disarm                |
| `/api/calibrate` | `POST` | Recalibrate altitude baseline |

### Hardware and Video

| Endpoint             | Method | Purpose                                     |
| -------------------- | ------ | ------------------------------------------- |
| `/api/hardware`      | `GET`  | I2C scan, pin mapping, and Pi supply status |
| `/api/camera/stream` | `GET`  | Live MJPEG stream                           |

## Local Development

Start the flight controller:

```bash
python -m flight.main
```

Start the dashboard:

```bash
python -m dashboard.app
```

Run tests:

```bash
python -m pytest tests -v
```

## Raspberry Pi Deployment

Install system dependencies:

```bash
sudo apt update
sudo apt install -y \
  libcamera-dev python3-libcamera python3-libcamera-binding \
  python3-pip python3-venv git \
  i2c-tools python3-smbus2 \
  python3-rpi.gpio
```

Set up the project:

```bash
git clone <repo-url> /opt/rocket
cd /opt/rocket
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt
bash scripts/deploy.sh
```

Systemd service files are provided in `config/`.

## Configuration Notes

The dashboard and flight controller share configuration through the `config` table. Values are stored as JSON in SQLite and reloaded by the flight controller roughly once per second.

Useful environment variables:

- `ROCKET_DB`: override the SQLite database path
- `ROCKET_CAMERA_FRAME_FILE`: override the MJPEG frame file path used by the dashboard

## Documentation

- Architecture details: `ARCHITECTURE.md`
- Design spec: `docs/superpowers/specs/2026-04-16-rocket-flight-computer-design.md`

## License

See `CLAUDE.md` for project guidance and repository conventions.
