# Architecture: Rocket Flight Computer

## System Design

The project is built around two separate processes that share a SQLite database:

```text
+---------------------+        +------------------+        +----------------------+
| Flight Controller   | -----> | SQLite (shared)  | <----- | Dashboard / Flask UI |
| flight/main.py      |        | db/rocket.db     |        | dashboard/app.py     |
+---------------------+        +------------------+        +----------------------+
         |
         +--> Camera thread and MJPEG frame output
```

This split gives the system a simple failure boundary:

- the flight controller can keep logging even if the dashboard is down
- the dashboard can restart without interrupting the main control loop

## Main Runtime Components

### Flight Controller

`flight/main.py` owns the real-time loop. Each tick:

1. reads the available sensors
2. computes altitude and vertical speed
3. computes total and net acceleration
4. updates the state machine
5. logs the new reading
6. reacts to dashboard commands stored in `config`
7. synchronizes camera state

The loop rate depends on the current state:

- `IDLE` and `ARMED`: `sample_rate_idle`
- `ASCENT`, `APOGEE`, `DESCENT`: `sample_rate_flight`

### State Machine

`flight/state_machine.py` models the flight lifecycle:

```text
IDLE -> ARMED -> ASCENT -> APOGEE -> DESCENT -> LANDED
```

Important rules from the current implementation:

- launch is detected only if altitude, vertical speed, and net acceleration all exceed thresholds
- apogee is confirmed after a configurable number of consecutive falling samples
- landing is confirmed after a configurable duration of stable altitude
- disarm is only allowed from `ARMED`

### Sensor Layer

The current flight stack uses two sensor drivers in `flight/sensors/`:

- `bmp280.py`: pressure and temperature over I2C
- `mpu6050.py`: IMU readings with a primary library path and an SMBus fallback

The IMU driver also derives `pitch` and `roll` using `flight/orientation.py`.

### Derived Data

Two helper modules compute values used elsewhere in the system:

- `flight/altitude.py`
  - initializes a pressure baseline automatically
  - computes altitude from barometric pressure
  - derives vertical speed from altitude deltas over time
- `flight/acceleration.py`
  - computes `total_accel` as vector magnitude
  - computes `net_accel` as `max(0, total_accel - 9.81)`

### Flight Logging

`flight/logger.py` writes telemetry to SQLite through `FlightDB`.

Logging starts when the controller enters `ARMED` and stops when the controller reaches `LANDED`. Flight summaries are written to the `flights` table when a flight completes.

### Camera Pipeline

`flight/camera.py` manages onboard video:

- records H.264 to disk
- exports the latest JPEG frame to a shared file
- allows the dashboard to serve an MJPEG stream without owning the camera

The dashboard reads the frame file from `/api/camera/stream`.

## Database Model

`flight/database.py` is a lightweight SQLite wrapper. The schema lives in `db/schema.sql`.

### `readings`

One row per telemetry sample:

```sql
id | flight_id | timestamp | pressure | temperature | humidity | altitude | vspeed |
roll | pitch | yaw | accel_x | accel_y | accel_z | total_accel | net_accel | state
```

Notes:

- `flight_id` links a sample to a recorded flight when one is active
- `state` stores the controller state at the moment of the sample

### `flights`

One row per flight:

```sql
id | started_at | ended_at | max_altitude | max_vspeed | duration | state
```

### `config`

Shared runtime configuration:

```sql
key | value | updated_at
```

The dashboard writes to this table, and the flight controller reloads it periodically.

## Dashboard Architecture

`dashboard/app.py` creates the Flask application and attaches:

- a shared `FlightDB`
- a shared `ConfigManager`
- the API blueprint from `dashboard/api.py`

### API Surface

Current endpoints:

- `GET /api/status`
- `GET /api/history`
- `GET /api/flights`
- `GET /api/config`
- `POST /api/config`
- `POST /api/arm`
- `POST /api/disarm`
- `POST /api/calibrate`
- `GET /api/hardware`
- `GET /api/camera/stream`

`/api/hardware` has two responsibilities:

- scan the I2C bus to detect the BMP280 and MPU6050
- report Raspberry Pi undervoltage status using `vcgencmd get_throttled`

## Communication Pattern

### Dashboard to Flight Controller

Commands are written into the `config` table:

- arm request
- disarm request
- altitude recalibration request
- updated sampling and state-machine parameters

The flight controller polls configuration roughly once per second and consumes those requests.

### Flight Controller to Dashboard

Telemetry flows through the `readings` table and flight summaries through `flights`.

This design keeps the dashboard read-only with respect to telemetry history and makes inspection easy with standard SQLite tools.

### Camera to Dashboard

The camera path is file-based rather than database-based:

1. the camera thread writes the latest JPEG frame to a known file
2. the dashboard reads that file when serving `/api/camera/stream`

This avoids bloating the database with binary image data.

## Error Handling

The codebase follows a graceful-degradation approach:

- sensor read failures return `None` rather than crashing the loop
- the main controller catches exceptions inside `run()`
- the dashboard can continue serving stale or partial information if some hardware probes fail
- missing Raspberry Pi tooling such as `i2cdetect` or `vcgencmd` degrades hardware-status reporting without taking down the app

## Current Constraints

Some architecture limits are worth calling out explicitly:

- command delivery from dashboard to controller is polling-based, not event-driven
- camera streaming depends on a shared frame file
- SQLite writes happen synchronously on each logged sample
- yaw is not estimated beyond the placeholder values emitted by the IMU path

## Future Improvements

Reasonable next architectural steps:

1. Introduce better IMU fusion for more reliable orientation estimation.
2. Add export tooling for logged flights.
3. Make command propagation event-driven instead of periodic polling.
4. Add stronger operational logging around camera and sensor failures.
5. Extend telemetry transport beyond local Wi-Fi if long-range ground testing is needed.
