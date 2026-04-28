# Rocket Flight Computer – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-process flight computer system (Flight Controller + Dashboard) for a model rocket on Raspberry Pi Zero.

**Architecture:** Flight Controller daemon reads sensors, logs data, runs flight state machine, and triggers deployment GPIO. Dashboard Server (Flask) reads from shared SQLite DB to display avionics-style UI and accept configuration. Both run as independent systemd services.

**Tech Stack:** Python 3, Flask, SQLite, plain HTML/CSS/JS, RPi.GPIO, Adafruit CircuitPython libraries.

**Spec:** `docs/superpowers/specs/2026-04-16-rocket-flight-computer-design.md`

---

## Task 1: Database Schema and Access Layer

**Files:**

- Create: `db/schema.sql`
- Create: `flight/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write the schema file**

```sql
-- db/schema.sql
CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id   INTEGER,
    timestamp   REAL NOT NULL,
    pressure    REAL,
    temperature REAL,
    humidity    REAL,
    altitude    REAL,
    vspeed      REAL,
    roll        REAL,
    pitch       REAL,
    yaw         REAL,
    accel_x     REAL,
    accel_y     REAL,
    accel_z     REAL,
    battery_pct REAL,
    battery_v   REAL,
    state       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flights (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    max_altitude  REAL DEFAULT 0,
    max_vspeed    REAL DEFAULT 0,
    duration      REAL DEFAULT 0,
    state         TEXT NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE IF NOT EXISTS config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

- [ ] **Step 2: Write failing tests for database layer**

```python
# tests/test_database.py
import os
import tempfile
import time
import pytest
from flight.database import FlightDB

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = FlightDB(path)
    yield database
    database.close()
    os.unlink(path)

def test_insert_and_read_reading(db: FlightDB):
    db.insert_reading(
        flight_id=None,
        timestamp=time.time(),
        pressure=1013.25,
        temperature=21.0,
        humidity=45.0,
        altitude=0.0,
        vspeed=0.0,
        roll=0.0, pitch=0.0, yaw=0.0,
        accel_x=0.0, accel_y=0.0, accel_z=9.81,
        battery_pct=85.0,
        battery_v=3.9,
        state="IDLE",
    )
    rows = db.get_latest_readings(count=1)
    assert len(rows) == 1
    assert rows[0]["pressure"] == pytest.approx(1013.25)
    assert rows[0]["state"] == "IDLE"

def test_create_and_end_flight(db: FlightDB):
    flight_id = db.create_flight()
    assert flight_id == 1
    db.end_flight(flight_id, max_altitude=150.0, max_vspeed=45.0, duration=12.5)
    flights = db.get_flights()
    assert len(flights) == 1
    assert flights[0]["max_altitude"] == pytest.approx(150.0)
    assert flights[0]["state"] == "COMPLETED"

def test_config_set_and_get(db: FlightDB):
    db.set_config("deploy_pin", "17")
    val = db.get_config("deploy_pin")
    assert val == "17"

def test_config_get_default(db: FlightDB):
    val = db.get_config("nonexistent", default="42")
    assert val == "42"

def test_get_all_config(db: FlightDB):
    db.set_config("key_a", "1")
    db.set_config("key_b", "2")
    all_cfg = db.get_all_config()
    assert all_cfg["key_a"] == "1"
    assert all_cfg["key_b"] == "2"

def test_get_readings_since(db: FlightDB):
    now = time.time()
    db.insert_reading(flight_id=None, timestamp=now - 10, pressure=1013.0,
        temperature=20.0, humidity=40.0, altitude=0.0, vspeed=0.0,
        roll=0.0, pitch=0.0, yaw=0.0, accel_x=0.0, accel_y=0.0, accel_z=9.81,
        battery_pct=80.0, battery_v=3.8, state="IDLE")
    db.insert_reading(flight_id=None, timestamp=now - 2, pressure=1010.0,
        temperature=20.5, humidity=41.0, altitude=30.0, vspeed=5.0,
        roll=1.0, pitch=2.0, yaw=3.0, accel_x=0.1, accel_y=0.2, accel_z=10.0,
        battery_pct=79.0, battery_v=3.7, state="ASCENT")
    rows = db.get_readings_since(now - 5)
    assert len(rows) == 1
    assert rows[0]["altitude"] == pytest.approx(30.0)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd C:/Users/hartm/Desktop/Claude/Projects/rocket && python -m pytest tests/test_database.py -v`
Expected: FAIL – `ModuleNotFoundError: No module named 'flight.database'`

- [ ] **Step 4: Implement database layer**

```python
# flight/database.py
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"

class FlightDB:
    def __init__(self, db_path: str = "/opt/rocket/data/rocket.db") -> None:
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        schema = SCHEMA_PATH.read_text()
        self.conn.executescript(schema)

    def close(self) -> None:
        self.conn.close()

    def insert_reading(self, flight_id: Optional[int], timestamp: float,
                       pressure: float, temperature: float, humidity: float,
                       altitude: float, vspeed: float,
                       roll: float, pitch: float, yaw: float,
                       accel_x: float, accel_y: float, accel_z: float,
                       battery_pct: float, battery_v: float,
                       state: str) -> None:
        self.conn.execute(
            """INSERT INTO readings (flight_id, timestamp, pressure, temperature,
               humidity, altitude, vspeed, roll, pitch, yaw,
               accel_x, accel_y, accel_z, battery_pct, battery_v, state)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (flight_id, timestamp, pressure, temperature, humidity,
             altitude, vspeed, roll, pitch, yaw,
             accel_x, accel_y, accel_z, battery_pct, battery_v, state),
        )
        self.conn.commit()

    def get_latest_readings(self, count: int = 1) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (count,)
        )
        return [dict(row) for row in cur.fetchall()]

    def get_readings_since(self, since_timestamp: float) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM readings WHERE timestamp >= ? ORDER BY timestamp ASC",
            (since_timestamp,),
        )
        return [dict(row) for row in cur.fetchall()]

    def create_flight(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO flights (started_at, state) VALUES (?, 'ACTIVE')",
            (now,),
        )
        self.conn.commit()
        return cur.lastrowid

    def end_flight(self, flight_id: int, max_altitude: float,
                   max_vspeed: float, duration: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """UPDATE flights SET ended_at=?, max_altitude=?, max_vspeed=?,
               duration=?, state='COMPLETED' WHERE id=?""",
            (now, max_altitude, max_vspeed, duration, flight_id),
        )
        self.conn.commit()

    def get_flights(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM flights ORDER BY id DESC"
        )
        return [dict(row) for row in cur.fetchall()]

    def set_config(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?""",
            (key, value, now, value, now),
        )
        self.conn.commit()

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        cur = self.conn.execute(
            "SELECT value FROM config WHERE key=?", (key,)
        )
        row = cur.fetchone()
        return row["value"] if row else default

    def get_all_config(self) -> dict[str, str]:
        cur = self.conn.execute("SELECT key, value FROM config")
        return {row["key"]: row["value"] for row in cur.fetchall()}
```

- [ ] **Step 5: Create `flight/__init__.py`**

```python
# flight/__init__.py
```

(Empty init file to make flight a package.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd C:/Users/hartm/Desktop/Claude/Projects/rocket && python -m pytest tests/test_database.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add db/schema.sql flight/__init__.py flight/database.py tests/test_database.py
git commit -m "feat: add SQLite database schema and access layer"
```

---

## Task 2: Configuration Manager

**Files:**

- Create: `flight/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
import os
import tempfile
import pytest
from flight.database import FlightDB
from flight.config import ConfigManager, DEFAULTS

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = FlightDB(path)
    yield database
    database.close()
    os.unlink(path)

def test_defaults_loaded_on_init(db: FlightDB):
    cfg = ConfigManager(db)
    assert cfg.get("deploy_pin") == 17
    assert cfg.get("sample_rate_flight") == 20

def test_get_returns_typed_value(db: FlightDB):
    cfg = ConfigManager(db)
    assert isinstance(cfg.get("deploy_duration"), float)
    assert isinstance(cfg.get("deploy_pin"), int)

def test_set_and_get(db: FlightDB):
    cfg = ConfigManager(db)
    cfg.set("deploy_pin", 27)
    assert cfg.get("deploy_pin") == 27

def test_reload_picks_up_db_changes(db: FlightDB):
    cfg = ConfigManager(db)
    db.set_config("deploy_pin", "27")
    cfg.reload()
    assert cfg.get("deploy_pin") == 27

def test_all_returns_dict(db: FlightDB):
    cfg = ConfigManager(db)
    all_cfg = cfg.all()
    assert "deploy_pin" in all_cfg
    assert "sample_rate_idle" in all_cfg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL – `ModuleNotFoundError: No module named 'flight.config'`

- [ ] **Step 3: Implement ConfigManager**

```python
# flight/config.py
import json
from typing import Any
from flight.database import FlightDB

DEFAULTS: dict[str, Any] = {
    "sample_rate_idle": 1,
    "sample_rate_flight": 20,
    "min_deploy_altitude": 30,
    "min_flight_time": 2,
    "apogee_samples": 5,
    "deploy_pin": 17,
    "deploy_duration": 1.0,
    "landing_stable_time": 10,
}

class ConfigManager:
    def __init__(self, db: FlightDB) -> None:
        self._db = db
        self._cache: dict[str, Any] = {}
        self._init_defaults()
        self.reload()

    def _init_defaults(self) -> None:
        for key, value in DEFAULTS.items():
            existing = self._db.get_config(key)
            if existing is None:
                self._db.set_config(key, json.dumps(value))

    def reload(self) -> None:
        raw = self._db.get_all_config()
        self._cache = {k: json.loads(v) for k, v in raw.items()}

    def get(self, key: str) -> Any:
        return self._cache.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._db.set_config(key, json.dumps(value))
        self._cache[key] = value

    def all(self) -> dict[str, Any]:
        return dict(self._cache)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add flight/config.py tests/test_config.py
git commit -m "feat: add configuration manager with defaults and DB persistence"
```

---

## Task 3: Altitude Calculator

**Files:**

- Create: `flight/altitude.py`
- Create: `tests/test_altitude.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_altitude.py
import pytest
from flight.altitude import AltitudeCalculator

def test_altitude_at_baseline_is_zero():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    alt = calc.compute(1013.25, 20.0)
    assert alt == pytest.approx(0.0, abs=0.1)

def test_altitude_increases_with_lower_pressure():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    alt = calc.compute(1001.0, 18.0)
    assert alt > 50.0
    assert alt < 200.0

def test_vspeed_calculation():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    calc.update(1013.25, 20.0, timestamp=0.0)
    calc.update(1001.0, 18.0, timestamp=1.0)
    assert calc.vspeed > 50.0  # climbed ~100m in 1s

def test_vspeed_zero_when_stationary():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    calc.update(1013.25, 20.0, timestamp=0.0)
    calc.update(1013.25, 20.0, timestamp=1.0)
    assert calc.vspeed == pytest.approx(0.0, abs=0.5)

def test_altitude_history():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    calc.update(1013.25, 20.0, timestamp=0.0)
    calc.update(1010.0, 19.0, timestamp=1.0)
    calc.update(1007.0, 18.0, timestamp=2.0)
    assert len(calc.history) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_altitude.py -v`
Expected: FAIL – `ModuleNotFoundError: No module named 'flight.altitude'`

- [ ] **Step 3: Implement AltitudeCalculator**

```python
# flight/altitude.py
from collections import deque
from typing import Optional

class AltitudeCalculator:
    """Computes altitude from barometric pressure using the hypsometric formula."""

    def __init__(self, history_size: int = 50) -> None:
        self._baseline_pressure: Optional[float] = None
        self._baseline_temp: Optional[float] = None
        self._last_altitude: float = 0.0
        self._last_timestamp: Optional[float] = None
        self.altitude: float = 0.0
        self.vspeed: float = 0.0
        self.history: deque[tuple[float, float]] = deque(maxlen=history_size)

    def set_baseline(self, pressure: float, temperature: float) -> None:
        self._baseline_pressure = pressure
        self._baseline_temp = temperature

    def compute(self, pressure: float, temperature: float) -> float:
        if self._baseline_pressure is None:
            return 0.0
        temp_k = temperature + 273.15
        altitude = temp_k / 0.0065 * (
            1.0 - (pressure / self._baseline_pressure) ** 0.190284
        )
        return altitude

    def update(self, pressure: float, temperature: float,
               timestamp: float) -> None:
        self.altitude = self.compute(pressure, temperature)
        if self._last_timestamp is not None:
            dt = timestamp - self._last_timestamp
            if dt > 0:
                self.vspeed = (self.altitude - self._last_altitude) / dt
        self._last_altitude = self.altitude
        self._last_timestamp = timestamp
        self.history.append((timestamp, self.altitude))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_altitude.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add flight/altitude.py tests/test_altitude.py
git commit -m "feat: add barometric altitude calculator with vertical speed"
```

---

## Task 4: Sensor Abstractions (BME280, BNO055, PowerBoost)

**Files:**

- Create: `flight/sensors/__init__.py`
- Create: `flight/sensors/bme280.py`
- Create: `flight/sensors/bno055.py`
- Create: `flight/sensors/power.py`
- Create: `tests/test_sensors.py`

- [ ] **Step 1: Write failing tests with mock hardware**

```python
# tests/test_sensors.py
import pytest
from unittest.mock import MagicMock, patch
from flight.sensors.bmp280 import BMP280Sensor
from flight.sensors.mpu6050 import MPU6050Sensor
from flight.sensors.power import PowerSensor

class TestBMP280:
    def test_read_returns_dict_with_required_keys(self):
        with patch("flight.sensors.bmp280.board"), \
             patch("flight.sensors.bme280.busio"), \
             patch("flight.sensors.bme280.adafruit_bme280"):
            sensor = BME280Sensor.__new__(BME280Sensor)
            sensor._device = MagicMock()
            sensor._device.pressure = 1013.25
            sensor._device.temperature = 21.0
            sensor._device.relative_humidity = 45.0
            data = sensor.read()
            assert "pressure" in data
            assert "temperature" in data
            assert "humidity" in data
            assert data["pressure"] == pytest.approx(1013.25)

    def test_read_returns_none_on_error(self):
        sensor = BME280Sensor.__new__(BME280Sensor)
        sensor._device = MagicMock()
        type(sensor._device).pressure = property(
            lambda s: (_ for _ in ()).throw(OSError("I2C"))
        )
        data = sensor.read()
        assert data is None

class TestBNO055:
    def test_read_returns_orientation_and_accel(self):
        with patch("flight.sensors.bno055.board"), \
             patch("flight.sensors.bno055.busio"), \
             patch("flight.sensors.bno055.adafruit_bno055"):
            sensor = BNO055Sensor.__new__(BNO055Sensor)
            sensor._device = MagicMock()
            sensor._device.euler = (10.0, 20.0, 30.0)
            sensor._device.linear_acceleration = (0.1, 0.2, 9.8)
            data = sensor.read()
            assert data["yaw"] == pytest.approx(10.0)
            assert data["roll"] == pytest.approx(20.0)
            assert data["pitch"] == pytest.approx(30.0)
            assert data["accel_x"] == pytest.approx(0.1)

    def test_read_returns_none_on_error(self):
        sensor = BNO055Sensor.__new__(BNO055Sensor)
        sensor._device = MagicMock()
        type(sensor._device).euler = property(
            lambda s: (_ for _ in ()).throw(OSError("I2C"))
        )
        data = sensor.read()
        assert data is None

class TestPowerSensor:
    def test_read_returns_battery_info(self):
        sensor = PowerSensor.__new__(PowerSensor)
        sensor._read_voltage = MagicMock(return_value=3.9)
        data = sensor.read()
        assert "battery_v" in data
        assert "battery_pct" in data
        assert data["battery_v"] == pytest.approx(3.9)
        assert 0 <= data["battery_pct"] <= 100

    def test_voltage_to_percent_mapping(self):
        sensor = PowerSensor.__new__(PowerSensor)
        assert sensor._voltage_to_percent(4.2) == pytest.approx(100.0)
        assert sensor._voltage_to_percent(3.0) == pytest.approx(0.0)
        assert 0 < sensor._voltage_to_percent(3.7) < 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sensors.py -v`
Expected: FAIL – `ModuleNotFoundError`

- [ ] **Step 3: Implement BME280 sensor wrapper**

```python
# flight/sensors/__init__.py
from typing import Optional, Protocol

class Sensor(Protocol):
    def read(self) -> Optional[dict]:
        ...
```

```python
# flight/sensors/bme280.py
from typing import Optional

class BME280Sensor:
    def __init__(self) -> None:
        import board
        import busio
        import adafruit_bme280.advanced as adafruit_bme280
        i2c = busio.I2C(board.SCL, board.SDA)
        self._device = adafruit_bme280.Adafruit_BME280_I2C(i2c)

    def read(self) -> Optional[dict]:
        try:
            return {
                "pressure": self._device.pressure,
                "temperature": self._device.temperature,
                "humidity": self._device.relative_humidity,
            }
        except (OSError, ValueError):
            return None
```

- [ ] **Step 4: Implement BNO055 sensor wrapper**

```python
# flight/sensors/bno055.py
from typing import Optional

class BNO055Sensor:
    def __init__(self) -> None:
        import board
        import busio
        import adafruit_bno055
        i2c = busio.I2C(board.SCL, board.SDA)
        self._device = adafruit_bno055.BNO055_I2C(i2c)

    def read(self) -> Optional[dict]:
        try:
            euler = self._device.euler
            accel = self._device.linear_acceleration
            if euler is None or accel is None:
                return None
            return {
                "yaw": euler[0] or 0.0,
                "roll": euler[1] or 0.0,
                "pitch": euler[2] or 0.0,
                "accel_x": accel[0] or 0.0,
                "accel_y": accel[1] or 0.0,
                "accel_z": accel[2] or 0.0,
            }
        except (OSError, ValueError):
            return None
```

- [ ] **Step 5: Implement PowerBoost sensor**

```python
# flight/sensors/power.py
from typing import Optional

class PowerSensor:
    """Reads battery voltage from PowerBoost 500 via ADC or GPIO."""

    VOLTAGE_MIN = 3.0
    VOLTAGE_MAX = 4.2

    def __init__(self, adc_pin: int = 0) -> None:
        self._adc_pin = adc_pin
        try:
            import board
            import analogio
            self._adc = analogio.AnalogIn(board.A0)
        except (ImportError, RuntimeError):
            self._adc = None

    def _read_voltage(self) -> float:
        if self._adc is None:
            return 0.0
        raw = self._adc.value
        return (raw / 65535) * 3.3 * 2  # Voltage divider factor

    def _voltage_to_percent(self, voltage: float) -> float:
        pct = (voltage - self.VOLTAGE_MIN) / (self.VOLTAGE_MAX - self.VOLTAGE_MIN) * 100
        return max(0.0, min(100.0, pct))

    def read(self) -> Optional[dict]:
        try:
            voltage = self._read_voltage()
            return {
                "battery_v": round(voltage, 2),
                "battery_pct": round(self._voltage_to_percent(voltage), 1),
            }
        except (OSError, ValueError):
            return None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_sensors.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add flight/sensors/ tests/test_sensors.py
git commit -m "feat: add sensor abstractions for BME280, BNO055, PowerBoost"
```

---

## Task 5: Flight State Machine

**Files:**

- Create: `flight/state_machine.py`
- Create: `tests/test_state_machine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_state_machine.py
import pytest
from flight.state_machine import FlightState, StateMachine

def make_reading(altitude: float = 0.0, vspeed: float = 0.0,
                 accel_z: float = 9.81, timestamp: float = 0.0) -> dict:
    return {
        "altitude": altitude, "vspeed": vspeed, "accel_z": accel_z,
        "timestamp": timestamp,
    }

class TestStateMachine:
    def test_initial_state_is_idle(self):
        sm = StateMachine()
        assert sm.state == FlightState.IDLE

    def test_arm_transitions_to_armed(self):
        sm = StateMachine()
        sm.arm()
        assert sm.state == FlightState.ARMED

    def test_disarm_transitions_to_idle(self):
        sm = StateMachine()
        sm.arm()
        sm.disarm()
        assert sm.state == FlightState.IDLE

    def test_cannot_arm_from_ascent(self):
        sm = StateMachine()
        sm.arm()
        sm._state = FlightState.ASCENT
        sm.arm()
        assert sm.state == FlightState.ASCENT

    def test_ascent_detected_on_altitude_increase(self):
        sm = StateMachine(min_deploy_altitude=10, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=5.0, vspeed=20.0, accel_z=30.0, timestamp=1.0))
        assert sm.state == FlightState.ASCENT

    def test_apogee_detected_after_n_falling_samples(self):
        sm = StateMachine(apogee_samples=3, min_deploy_altitude=5, min_flight_time=0)
        sm.arm()
        # Ascent
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        assert sm.state == FlightState.ASCENT
        # Falling samples
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=48.0, vspeed=-1.0, timestamp=3.0))
        sm.update(make_reading(altitude=47.0, vspeed=-1.0, timestamp=4.0))
        assert sm.state == FlightState.APOGEE

    def test_no_deploy_below_min_altitude(self):
        sm = StateMachine(apogee_samples=2, min_deploy_altitude=100, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=20.0, vspeed=10.0, timestamp=1.0))
        sm.update(make_reading(altitude=19.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=18.0, vspeed=-1.0, timestamp=3.0))
        assert sm.state != FlightState.APOGEE

    def test_no_deploy_before_min_flight_time(self):
        sm = StateMachine(apogee_samples=2, min_deploy_altitude=5, min_flight_time=10)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=48.0, vspeed=-1.0, timestamp=3.0))
        assert sm.state != FlightState.APOGEE  # only 3s, need 10

    def test_descent_after_apogee(self):
        sm = StateMachine(apogee_samples=1, min_deploy_altitude=5, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        assert sm.state == FlightState.APOGEE
        sm.update(make_reading(altitude=40.0, vspeed=-5.0, timestamp=3.0))
        assert sm.state == FlightState.DESCENT

    def test_landed_after_stable_altitude(self):
        sm = StateMachine(apogee_samples=1, min_deploy_altitude=5,
                          min_flight_time=0, landing_stable_time=2)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=40.0, vspeed=-5.0, timestamp=3.0))
        # Stable on ground
        sm.update(make_reading(altitude=1.0, vspeed=0.0, timestamp=10.0))
        sm.update(make_reading(altitude=1.0, vspeed=0.0, timestamp=13.0))
        assert sm.state == FlightState.LANDED

    def test_deploy_triggered_flag(self):
        sm = StateMachine(apogee_samples=1, min_deploy_altitude=5, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        result = sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        assert result.deploy_triggered is True

    def test_no_deploy_in_other_states(self):
        sm = StateMachine()
        sm.arm()
        result = sm.update(make_reading(altitude=0.0, vspeed=0.0, timestamp=1.0))
        assert result.deploy_triggered is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_state_machine.py -v`
Expected: FAIL – `ModuleNotFoundError`

- [ ] **Step 3: Implement state machine**

```python
# flight/state_machine.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class FlightState(Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    ASCENT = "ASCENT"
    APOGEE = "APOGEE"
    DESCENT = "DESCENT"
    LANDED = "LANDED"

@dataclass
class UpdateResult:
    deploy_triggered: bool = False

class StateMachine:
    def __init__(
        self,
        apogee_samples: int = 5,
        min_deploy_altitude: float = 30.0,
        min_flight_time: float = 2.0,
        landing_stable_time: float = 10.0,
    ) -> None:
        self._state = FlightState.IDLE
        self._apogee_samples = apogee_samples
        self._min_deploy_altitude = min_deploy_altitude
        self._min_flight_time = min_flight_time
        self._landing_stable_time = landing_stable_time

        self._falling_count: int = 0
        self._max_altitude: float = 0.0
        self._armed_time: Optional[float] = None
        self._stable_since: Optional[float] = None
        self._last_altitude: Optional[float] = None

    @property
    def state(self) -> FlightState:
        return self._state

    @property
    def max_altitude(self) -> float:
        return self._max_altitude

    def arm(self) -> None:
        if self._state == FlightState.IDLE:
            self._state = FlightState.ARMED
            self._falling_count = 0
            self._max_altitude = 0.0
            self._stable_since = None
            self._last_altitude = None

    def disarm(self) -> None:
        if self._state == FlightState.ARMED:
            self._state = FlightState.IDLE

    def update(self, reading: dict) -> UpdateResult:
        result = UpdateResult()
        alt = reading["altitude"]
        vspeed = reading["vspeed"]
        ts = reading["timestamp"]

        if self._state == FlightState.ARMED:
            self._armed_time = self._armed_time or ts
            if alt > 5.0 and vspeed > 5.0:
                self._state = FlightState.ASCENT

        elif self._state == FlightState.ASCENT:
            self._max_altitude = max(self._max_altitude, alt)
            flight_time = ts - (self._armed_time or ts)

            if vspeed < 0:
                self._falling_count += 1
            else:
                self._falling_count = 0

            if (self._falling_count >= self._apogee_samples
                    and alt >= self._min_deploy_altitude
                    and flight_time >= self._min_flight_time):
                self._state = FlightState.APOGEE
                result.deploy_triggered = True

        elif self._state == FlightState.APOGEE:
            self._state = FlightState.DESCENT

        elif self._state == FlightState.DESCENT:
            if self._last_altitude is not None:
                if abs(alt - self._last_altitude) < 1.0:
                    if self._stable_since is None:
                        self._stable_since = ts
                    elif ts - self._stable_since >= self._landing_stable_time:
                        self._state = FlightState.LANDED
                else:
                    self._stable_since = None

        self._last_altitude = alt
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_state_machine.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add flight/state_machine.py tests/test_state_machine.py
git commit -m "feat: add flight state machine with apogee detection and safety checks"
```

---

## Task 6: Deployment Controller (GPIO)

**Files:**

- Create: `flight/deployment.py`
- Create: `tests/test_deployment.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_deployment.py
import pytest
from unittest.mock import MagicMock, patch, call
from flight.deployment import DeploymentController

@pytest.fixture
def mock_gpio():
    gpio = MagicMock()
    with patch("flight.deployment.GPIO", gpio):
        yield gpio

def test_init_sets_up_gpio(mock_gpio):
    ctrl = DeploymentController(pin=17)
    mock_gpio.setmode.assert_called_once_with(mock_gpio.BCM)
    mock_gpio.setup.assert_called_once_with(17, mock_gpio.OUT, initial=mock_gpio.LOW)

def test_fire_sets_pin_high(mock_gpio):
    ctrl = DeploymentController(pin=17)
    ctrl.fire(duration=0.01)
    mock_gpio.output.assert_any_call(17, mock_gpio.HIGH)

def test_fire_sets_pin_low_after_duration(mock_gpio):
    with patch("flight.deployment.time") as mock_time:
        ctrl = DeploymentController(pin=17)
        ctrl.fire(duration=1.0)
        mock_time.sleep.assert_called_once_with(1.0)
        calls = mock_gpio.output.call_args_list
        assert calls[-1] == call(17, mock_gpio.LOW)

def test_fire_only_once(mock_gpio):
    ctrl = DeploymentController(pin=17)
    ctrl.fire(duration=0.01)
    ctrl.fire(duration=0.01)  # second call should be ignored
    assert mock_gpio.output.call_count == 2  # HIGH + LOW from first fire only

def test_cleanup(mock_gpio):
    ctrl = DeploymentController(pin=17)
    ctrl.cleanup()
    mock_gpio.cleanup.assert_called_once_with(17)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deployment.py -v`
Expected: FAIL – `ModuleNotFoundError`

- [ ] **Step 3: Implement DeploymentController**

```python
# flight/deployment.py
import time
import threading
from typing import Optional

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    GPIO = None  # type: ignore

class DeploymentController:
    def __init__(self, pin: int = 17) -> None:
        self._pin = pin
        self._fired = False
        if GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    def fire(self, duration: float = 1.0) -> None:
        if self._fired or not GPIO:
            return
        self._fired = True
        GPIO.output(self._pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(self._pin, GPIO.LOW)

    def fire_async(self, duration: float = 1.0) -> None:
        thread = threading.Thread(target=self.fire, args=(duration,), daemon=True)
        thread.start()

    @property
    def has_fired(self) -> bool:
        return self._fired

    def reset(self) -> None:
        self._fired = False

    def cleanup(self) -> None:
        if GPIO:
            GPIO.cleanup(self._pin)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deployment.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add flight/deployment.py tests/test_deployment.py
git commit -m "feat: add GPIO deployment controller for parachute release"
```

---

## Task 7: Data Logger

**Files:**

- Create: `flight/logger.py`
- Create: `tests/test_logger.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_logger.py
import os
import tempfile
import time
import pytest
from flight.database import FlightDB
from flight.logger import FlightLogger

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = FlightDB(path)
    yield database
    database.close()
    os.unlink(path)

def make_sensor_data() -> dict:
    return {
        "pressure": 1013.25, "temperature": 21.0, "humidity": 45.0,
        "altitude": 100.0, "vspeed": 10.0,
        "roll": 1.0, "pitch": 2.0, "yaw": 3.0,
        "accel_x": 0.1, "accel_y": 0.2, "accel_z": 9.8,
        "battery_pct": 85.0, "battery_v": 3.9,
    }

def test_start_flight_creates_record(db: FlightDB):
    logger = FlightLogger(db)
    logger.start_flight()
    assert logger.flight_id is not None
    flights = db.get_flights()
    assert len(flights) == 1

def test_log_reading_writes_to_db(db: FlightDB):
    logger = FlightLogger(db)
    logger.start_flight()
    logger.log(make_sensor_data(), state="ASCENT", timestamp=time.time())
    rows = db.get_latest_readings(count=1)
    assert len(rows) == 1
    assert rows[0]["state"] == "ASCENT"
    assert rows[0]["flight_id"] == logger.flight_id

def test_end_flight_updates_record(db: FlightDB):
    logger = FlightLogger(db)
    logger.start_flight()
    logger.log(make_sensor_data(), state="ASCENT", timestamp=time.time())
    logger.end_flight(max_altitude=150.0, max_vspeed=40.0, duration=12.0)
    flights = db.get_flights()
    assert flights[0]["state"] == "COMPLETED"
    assert flights[0]["max_altitude"] == pytest.approx(150.0)

def test_log_without_flight_uses_none(db: FlightDB):
    logger = FlightLogger(db)
    logger.log(make_sensor_data(), state="IDLE", timestamp=time.time())
    rows = db.get_latest_readings(count=1)
    assert rows[0]["flight_id"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_logger.py -v`
Expected: FAIL – `ModuleNotFoundError`

- [ ] **Step 3: Implement FlightLogger**

```python
# flight/logger.py
from typing import Optional
from flight.database import FlightDB

class FlightLogger:
    def __init__(self, db: FlightDB) -> None:
        self._db = db
        self.flight_id: Optional[int] = None

    def start_flight(self) -> int:
        self.flight_id = self._db.create_flight()
        return self.flight_id

    def log(self, sensor_data: dict, state: str, timestamp: float) -> None:
        self._db.insert_reading(
            flight_id=self.flight_id,
            timestamp=timestamp,
            pressure=sensor_data.get("pressure", 0.0),
            temperature=sensor_data.get("temperature", 0.0),
            humidity=sensor_data.get("humidity", 0.0),
            altitude=sensor_data.get("altitude", 0.0),
            vspeed=sensor_data.get("vspeed", 0.0),
            roll=sensor_data.get("roll", 0.0),
            pitch=sensor_data.get("pitch", 0.0),
            yaw=sensor_data.get("yaw", 0.0),
            accel_x=sensor_data.get("accel_x", 0.0),
            accel_y=sensor_data.get("accel_y", 0.0),
            accel_z=sensor_data.get("accel_z", 0.0),
            battery_pct=sensor_data.get("battery_pct", 0.0),
            battery_v=sensor_data.get("battery_v", 0.0),
            state=state,
        )

    def end_flight(self, max_altitude: float, max_vspeed: float,
                   duration: float) -> None:
        if self.flight_id is not None:
            self._db.end_flight(self.flight_id, max_altitude, max_vspeed, duration)
            self.flight_id = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_logger.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add flight/logger.py tests/test_logger.py
git commit -m "feat: add flight data logger with flight lifecycle management"
```

---

## Task 8: Flight Controller Main Loop

**Files:**

- Create: `flight/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_main.py
import os
import tempfile
import time
import pytest
from unittest.mock import MagicMock, patch
from flight.main import FlightController

@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)

@pytest.fixture
def mock_sensors():
    bme = MagicMock()
    bme.read.return_value = {
        "pressure": 1013.25, "temperature": 21.0, "humidity": 45.0,
    }
    bno = MagicMock()
    bno.read.return_value = {
        "yaw": 0.0, "roll": 0.0, "pitch": 0.0,
        "accel_x": 0.0, "accel_y": 0.0, "accel_z": 9.81,
    }
    pwr = MagicMock()
    pwr.read.return_value = {"battery_v": 3.9, "battery_pct": 85.0}
    return bmp280, mpu6050, pwr

def test_controller_initializes(db_path, mock_sensors):
    bmp280, mpu6050, pwr = mock_sensors
    ctrl = FlightController(db_path=db_path, bmp280_sensor=bmp280,
                            mpu6050_sensor=mpu6050, power_sensor=pwr)
    assert ctrl.state_machine.state.value == "IDLE"

def test_single_tick_reads_sensors(db_path, mock_sensors):
    bmp280, mpu6050, pwr = mock_sensors
    ctrl = FlightController(db_path=db_path, bmp280_sensor=bmp280,
                            mpu6050_sensor=mpu6050, power_sensor=pwr)
    ctrl.tick()
    bmp280.read.assert_called_once()
    mpu6050.read.assert_called_once()
    pwr.read.assert_called_once()

def test_tick_logs_data_when_armed(db_path, mock_sensors):
    bmp280, mpu6050, pwr = mock_sensors
    ctrl = FlightController(db_path=db_path, bmp280_sensor=bmp280,
                            mpu6050_sensor=mpu6050, power_sensor=pwr)
    ctrl.state_machine.arm()
    ctrl.tick()
    rows = ctrl.db.get_latest_readings(count=1)
    assert len(rows) == 1
    assert rows[0]["state"] == "ARMED"

def test_tick_handles_sensor_failure_gracefully(db_path, mock_sensors):
    bmp280, mpu6050, pwr = mock_sensors
    bmp280.read.return_value = None  # sensor error
    ctrl = FlightController(db_path=db_path, bmp280_sensor=bmp280,
                            mpu6050_sensor=mpu6050, power_sensor=pwr)
    ctrl.state_machine.arm()
    ctrl.tick()  # should not crash
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL – `ModuleNotFoundError`

- [ ] **Step 3: Implement FlightController**

```python
# flight/main.py
import time
import signal
import sys
from typing import Optional
from flight.database import FlightDB
from flight.config import ConfigManager
from flight.state_machine import FlightState, StateMachine
from flight.altitude import AltitudeCalculator
from flight.logger import FlightLogger
from flight.deployment import DeploymentController

class FlightController:
    def __init__(
        self,
        db_path: str = "/opt/rocket/data/rocket.db",
        bmp280_sensor=None,
        mpu6050_sensor=None,
        power_sensor=None,
    ) -> None:
        self.db = FlightDB(db_path)
        self.config = ConfigManager(self.db)
        self.state_machine = StateMachine(
            apogee_samples=self.config.get("apogee_samples"),
            min_deploy_altitude=self.config.get("min_deploy_altitude"),
            min_flight_time=self.config.get("min_flight_time"),
            landing_stable_time=self.config.get("landing_stable_time"),
        )
        self.altitude_calc = AltitudeCalculator()
        self.logger = FlightLogger(self.db)
        self.deployer = DeploymentController(pin=self.config.get("deploy_pin"))

        self._bmp280 = bmp280_sensor
        self._mpu6050 = mpu6050_sensor
        self._pwr = power_sensor
        self._running = False
        self._last_config_check = 0.0
        self._flight_start_time: Optional[float] = None
        self._max_vspeed: float = 0.0

    def _init_sensors(self) -> None:
        if self._bme is None:
            from flight.sensors.bmp280 import BMP280Sensor
            self._bme = BMP280Sensor()
        if self._bno is None:
            from flight.sensors.mpu6050 import MPU6050Sensor
            try:
                self._bno = MPU6050Sensor()
            except Exception:
                self._bno = None
        if self._pwr is None:
            from flight.sensors.power import PowerSensor
            self._pwr = PowerSensor()

    def tick(self) -> None:
        now = time.time()

        # Read sensors
        bme_data = self._bme.read() if self._bme else None
        bno_data = self._bno.read() if self._bno else None
        pwr_data = self._pwr.read() if self._pwr else None

        # Merge sensor data with defaults for missing values
        data = {
            "pressure": 0.0, "temperature": 0.0, "humidity": 0.0,
            "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 0.0,
            "battery_v": 0.0, "battery_pct": 0.0,
        }
        if bme_data:
            data.update(bme_data)
        if bno_data:
            data.update(bno_data)
        if pwr_data:
            data.update(pwr_data)

        # Compute altitude
        self.altitude_calc.update(data["pressure"], data["temperature"], now)
        data["altitude"] = self.altitude_calc.altitude
        data["vspeed"] = self.altitude_calc.vspeed
        self._max_vspeed = max(self._max_vspeed, abs(data["vspeed"]))

        # Update state machine
        state = self.state_machine.state
        if state not in (FlightState.IDLE,):
            reading = {
                "altitude": data["altitude"],
                "vspeed": data["vspeed"],
                "accel_z": data["accel_z"],
                "timestamp": now,
            }
            result = self.state_machine.update(reading)

            if result.deploy_triggered:
                duration = self.config.get("deploy_duration")
                self.deployer.fire_async(duration=duration)

        # Handle state transitions for logging
        current_state = self.state_machine.state
        if current_state == FlightState.ARMED and self.logger.flight_id is None:
            self.logger.start_flight()
            self.altitude_calc.set_baseline(data["pressure"], data["temperature"])
            self._flight_start_time = now
            self._max_vspeed = 0.0

        if current_state == FlightState.LANDED and self.logger.flight_id is not None:
            duration = now - (self._flight_start_time or now)
            self.logger.end_flight(
                max_altitude=self.state_machine.max_altitude,
                max_vspeed=self._max_vspeed,
                duration=duration,
            )

        # Log data (always when not IDLE, also in IDLE for dashboard display)
        self.logger.log(data, state=current_state.value, timestamp=now)

        # Periodic config reload
        if now - self._last_config_check >= 1.0:
            self.config.reload()
            self._last_config_check = now

    def get_sample_rate(self) -> float:
        state = self.state_machine.state
        if state in (FlightState.ASCENT, FlightState.APOGEE, FlightState.DESCENT):
            return self.config.get("sample_rate_flight")
        return self.config.get("sample_rate_idle")

    def run(self) -> None:
        self._init_sensors()
        self._running = True

        def stop(sig, frame):
            self._running = False
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

        while self._running:
            try:
                self.tick()
            except Exception as e:
                print(f"Tick error: {e}", file=sys.stderr)
            rate = self.get_sample_rate()
            time.sleep(1.0 / rate)

        self.deployer.cleanup()
        self.db.close()

def main() -> None:
    controller = FlightController()
    controller.run()

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add flight/main.py tests/test_main.py
git commit -m "feat: add flight controller main loop with sensor integration"
```

---

## Task 9: Dashboard Flask Backend

**Files:**

- Create: `dashboard/__init__.py`
- Create: `dashboard/app.py`
- Create: `dashboard/api.py`
- Create: `tests/test_dashboard_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dashboard_api.py
import os
import json
import tempfile
import time
import pytest
from flight.database import FlightDB
from flight.config import ConfigManager
from dashboard.app import create_app

@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)

@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def seeded_client(db_path):
    db = FlightDB(db_path)
    ConfigManager(db)  # init defaults
    now = time.time()
    db.insert_reading(
        flight_id=None, timestamp=now, pressure=1013.25,
        temperature=21.0, humidity=45.0, altitude=0.0, vspeed=0.0,
        roll=0.0, pitch=0.0, yaw=0.0, accel_x=0.0, accel_y=0.0, accel_z=9.81,
        battery_pct=85.0, battery_v=3.9, state="IDLE",
    )
    db.close()
    app = create_app(db_path=db_path)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data

def test_api_status_returns_json(seeded_client):
    resp = seeded_client.get("/api/status")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "state" in data
    assert "pressure" in data

def test_api_config_get(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "deploy_pin" in data

def test_api_config_post(client):
    resp = client.post("/api/config",
                       data=json.dumps({"deploy_pin": 27}),
                       content_type="application/json")
    assert resp.status_code == 200
    resp2 = client.get("/api/config")
    data = json.loads(resp2.data)
    assert data["deploy_pin"] == 27

def test_api_history(seeded_client):
    resp = seeded_client.get("/api/history?seconds=60")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)

def test_api_flights(client):
    resp = client.get("/api/flights")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)

def test_api_arm(client):
    resp = client.post("/api/arm")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["state"] == "ARMED"

def test_api_disarm(client):
    client.post("/api/arm")
    resp = client.post("/api/disarm")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["state"] == "IDLE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dashboard_api.py -v`
Expected: FAIL – `ModuleNotFoundError`

- [ ] **Step 3: Implement Flask app and API**

```python
# dashboard/__init__.py
```

```python
# dashboard/app.py
from flask import Flask
from dashboard.api import create_api_blueprint
from flight.database import FlightDB
from flight.config import ConfigManager
from flight.state_machine import StateMachine

def create_app(db_path: str = "/opt/rocket/data/rocket.db") -> Flask:
    app = Flask(__name__,
                static_folder="static",
                template_folder="templates")

    db = FlightDB(db_path)
    config = ConfigManager(db)
    state_machine = StateMachine()

    app.config["db"] = db
    app.config["config_manager"] = config
    app.config["state_machine"] = state_machine

    api_bp = create_api_blueprint()
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("dashboard.html")

    return app

def main() -> None:
    app = create_app()
    app.run(host="0.0.0.0", port=8080, debug=False)

if __name__ == "__main__":
    main()
```

```python
# dashboard/api.py
import time
from flask import Blueprint, request, jsonify, current_app

def create_api_blueprint() -> Blueprint:
    bp = Blueprint("api", __name__)

    @bp.route("/api/status")
    def status():
        db = current_app.config["db"]
        sm = current_app.config["state_machine"]
        rows = db.get_latest_readings(count=1)
        if rows:
            data = rows[0]
            data["state"] = sm.state.value
            return jsonify(data)
        return jsonify({"state": sm.state.value})

    @bp.route("/api/history")
    def history():
        db = current_app.config["db"]
        seconds = request.args.get("seconds", 60, type=int)
        since = time.time() - seconds
        rows = db.get_readings_since(since)
        return jsonify(rows)

    @bp.route("/api/config", methods=["GET"])
    def get_config():
        cfg = current_app.config["config_manager"]
        return jsonify(cfg.all())

    @bp.route("/api/config", methods=["POST"])
    def set_config():
        cfg = current_app.config["config_manager"]
        data = request.get_json()
        for key, value in data.items():
            cfg.set(key, value)
        return jsonify(cfg.all())

    @bp.route("/api/arm", methods=["POST"])
    def arm():
        sm = current_app.config["state_machine"]
        sm.arm()
        return jsonify({"state": sm.state.value})

    @bp.route("/api/disarm", methods=["POST"])
    def disarm():
        sm = current_app.config["state_machine"]
        sm.disarm()
        return jsonify({"state": sm.state.value})

    @bp.route("/api/flights")
    def flights():
        db = current_app.config["db"]
        return jsonify(db.get_flights())

    return bp
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dashboard_api.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/__init__.py dashboard/app.py dashboard/api.py tests/test_dashboard_api.py
git commit -m "feat: add Flask dashboard backend with REST API"
```

---

## Task 10: Dashboard Frontend – HTML Structure

**Files:**

- Create: `dashboard/templates/dashboard.html`
- Create: `dashboard/static/css/cockpit.css`

- [ ] **Step 1: Create the HTML template**

```html
<!-- dashboard/templates/dashboard.html -->
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Rocket Flight Computer</title>
    <link
      rel="stylesheet"
      href="{{ url_for('static', filename='css/cockpit.css') }}"
    />
  </head>
  <body>
    <header id="top-bar">
      <span class="title">ROCKET FLIGHT COMPUTER</span>
      <span id="flight-state" class="state">IDLE</span>
      <span id="clock" class="clock">00:00:00</span>
    </header>

    <main id="instruments">
      <section id="altitude-tape" class="instrument-panel">
        <h2>ALTITUDE</h2>
        <div class="tape-container">
          <div id="alt-tape" class="tape"></div>
          <div id="alt-value" class="tape-value">0 m</div>
        </div>
      </section>

      <section id="attitude-indicator" class="instrument-panel center-panel">
        <h2>ATTITUDE</h2>
        <div id="attitude-container">
          <canvas id="attitude-canvas" width="300" height="300"></canvas>
        </div>
      </section>

      <section id="vspeed-tape" class="instrument-panel">
        <h2>VERTICAL SPEED</h2>
        <div class="tape-container">
          <div id="vs-tape" class="tape"></div>
          <div id="vs-value" class="tape-value">0.0 m/s</div>
        </div>
      </section>
    </main>

    <div id="readouts">
      <section id="environment" class="readout-panel">
        <h2>ENVIRONMENT</h2>
        <div class="readout-row">
          <span class="label">Pressure</span>
          <span id="pressure" class="value">---- hPa</span>
        </div>
        <div class="readout-row">
          <span class="label">Temperature</span>
          <span id="temperature" class="value">-- &deg;C</span>
        </div>
        <div class="readout-row">
          <span class="label">Humidity</span>
          <span id="humidity" class="value">-- %</span>
        </div>
      </section>

      <section id="system" class="readout-panel">
        <h2>SYSTEM</h2>
        <div class="readout-row">
          <span class="label">Battery</span>
          <div id="battery-bar" class="bar-container">
            <div id="battery-fill" class="bar-fill"></div>
            <span id="battery-pct" class="bar-text">--%</span>
          </div>
        </div>
        <div class="readout-row">
          <span class="label">Voltage</span>
          <span id="voltage" class="value">-- V</span>
        </div>
        <div class="readout-row">
          <span class="label">Flight Time</span>
          <span id="flight-time" class="value">00:00:00</span>
        </div>
        <div class="readout-row">
          <span class="label">Logging</span>
          <span id="logging-status" class="value status-inactive"
            >INACTIVE</span
          >
        </div>
      </section>
    </div>

    <footer id="controls">
      <button id="btn-arm" class="ctrl-btn">ARM</button>
      <button id="btn-disarm" class="ctrl-btn" disabled>DISARM</button>
      <button id="btn-config" class="ctrl-btn">CONFIG</button>
      <span id="connection-status" class="conn-status">Connecting...</span>
    </footer>

    <div id="config-modal" class="modal hidden">
      <div class="modal-content">
        <h2>CONFIGURATION</h2>
        <div id="config-fields"></div>
        <div class="modal-actions">
          <button id="btn-config-save" class="ctrl-btn">SAVE</button>
          <button id="btn-config-close" class="ctrl-btn">CLOSE</button>
        </div>
      </div>
    </div>

    <script src="{{ url_for('static', filename='js/gauges.js') }}"></script>
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
  </body>
</html>
```

- [ ] **Step 2: Create the cockpit CSS**

```css
/* dashboard/static/css/cockpit.css */

/* === Reset & Base === */
*,
*::before,
*::after {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  --bg-dark: #0a1628;
  --bg-panel: #111d35;
  --bg-instrument: #0d1829;
  --text-primary: #ffffff;
  --text-secondary: #8899bb;
  --accent: #00ccff;
  --warning: #ffaa00;
  --critical: #ff3344;
  --ok: #00ff88;
  --border: #1e3a5f;
  --font-mono: "Courier New", "Consolas", monospace;
}

body {
  background: var(--bg-dark);
  color: var(--text-primary);
  font-family: var(--font-mono);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* === Header === */
#top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
}

.title {
  font-size: 16px;
  letter-spacing: 3px;
  color: var(--accent);
  font-weight: bold;
}

.state {
  font-size: 18px;
  padding: 4px 16px;
  border: 1px solid var(--accent);
  border-radius: 4px;
  letter-spacing: 2px;
}

.state.armed {
  border-color: var(--warning);
  color: var(--warning);
}
.state.ascent {
  border-color: var(--ok);
  color: var(--ok);
}
.state.apogee {
  border-color: var(--critical);
  color: var(--critical);
}
.state.descent {
  border-color: var(--warning);
  color: var(--warning);
}
.state.landed {
  border-color: var(--ok);
  color: var(--ok);
}

.clock {
  font-size: 16px;
  color: var(--text-secondary);
}

/* === Instruments === */
#instruments {
  display: grid;
  grid-template-columns: 1fr 2fr 1fr;
  gap: 8px;
  padding: 8px;
  flex: 1;
  min-height: 300px;
}

.instrument-panel {
  background: var(--bg-instrument);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.instrument-panel h2 {
  font-size: 11px;
  letter-spacing: 2px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.tape-container {
  flex: 1;
  width: 80px;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 2px;
  background: var(--bg-dark);
}

.tape-value {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  background: var(--bg-panel);
  border: 1px solid var(--accent);
  padding: 4px 8px;
  font-size: 16px;
  font-weight: bold;
  color: var(--accent);
  z-index: 2;
  white-space: nowrap;
}

.center-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

#attitude-canvas {
  border-radius: 50%;
  border: 2px solid var(--border);
}

/* === Readouts === */
#readouts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 0 8px 8px;
}

.readout-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px;
}

.readout-panel h2 {
  font-size: 11px;
  letter-spacing: 2px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
}

.readout-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
}

.label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.value {
  font-size: 16px;
  font-weight: bold;
  color: var(--text-primary);
}

/* Battery bar */
.bar-container {
  width: 120px;
  height: 20px;
  background: var(--bg-dark);
  border: 1px solid var(--border);
  border-radius: 2px;
  position: relative;
}

.bar-fill {
  height: 100%;
  background: var(--ok);
  border-radius: 1px;
  transition: width 0.3s ease;
}

.bar-fill.warning {
  background: var(--warning);
}
.bar-fill.critical {
  background: var(--critical);
}

.bar-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 11px;
  font-weight: bold;
}

.status-active {
  color: var(--ok);
}
.status-inactive {
  color: var(--text-secondary);
}

/* === Controls === */
#controls {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  background: var(--bg-panel);
  border-top: 1px solid var(--border);
}

.ctrl-btn {
  background: var(--bg-instrument);
  color: var(--text-primary);
  border: 1px solid var(--border);
  padding: 8px 24px;
  font-family: var(--font-mono);
  font-size: 13px;
  letter-spacing: 2px;
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.15s ease;
}

.ctrl-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.ctrl-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.conn-status {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary);
}

.conn-status.connected {
  color: var(--ok);
}
.conn-status.disconnected {
  color: var(--critical);
}

/* === Config Modal === */
.modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal.hidden {
  display: none;
}

.modal-content {
  background: var(--bg-panel);
  border: 1px solid var(--accent);
  border-radius: 6px;
  padding: 24px;
  min-width: 400px;
  max-width: 500px;
}

.modal-content h2 {
  font-size: 14px;
  letter-spacing: 2px;
  color: var(--accent);
  margin-bottom: 16px;
}

.modal-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  justify-content: flex-end;
}

.config-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
}

.config-row label {
  font-size: 12px;
  color: var(--text-secondary);
}

.config-row input {
  background: var(--bg-dark);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-family: var(--font-mono);
  padding: 4px 8px;
  width: 100px;
  text-align: right;
  border-radius: 2px;
}

.config-row input:focus {
  outline: none;
  border-color: var(--accent);
}
```

- [ ] **Step 3: Verify template renders**

Run: `python -m pytest tests/test_dashboard_api.py::test_index_returns_html -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add dashboard/templates/dashboard.html dashboard/static/css/cockpit.css
git commit -m "feat: add avionics cockpit dashboard HTML and CSS"
```

---

## Task 11: Dashboard Frontend – JavaScript (Polling & Gauges)

**Files:**

- Create: `dashboard/static/js/main.js`
- Create: `dashboard/static/js/gauges.js`

- [ ] **Step 1: Implement the attitude indicator (gauges.js)**

```javascript
// dashboard/static/js/gauges.js

class AttitudeIndicator {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext("2d");
    this.cx = this.canvas.width / 2;
    this.cy = this.canvas.height / 2;
    this.r = Math.min(this.cx, this.cy) - 4;
    this.roll = 0;
    this.pitch = 0;
    this.draw();
  }

  update(roll, pitch) {
    this.roll = roll || 0;
    this.pitch = pitch || 0;
    this.draw();
  }

  draw() {
    const ctx = this.ctx;
    const cx = this.cx;
    const cy = this.cy;
    const r = this.r;

    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.clip();

    ctx.translate(cx, cy);
    ctx.rotate((-this.roll * Math.PI) / 180);

    // Pitch offset: 2px per degree
    const pitchOffset = this.pitch * 2;

    // Sky
    ctx.fillStyle = "#1a3a6a";
    ctx.fillRect(-r, -r + pitchOffset, r * 2, r);

    // Ground
    ctx.fillStyle = "#4a2a0a";
    ctx.fillRect(-r, pitchOffset, r * 2, r);

    // Horizon line
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(-r, pitchOffset);
    ctx.lineTo(r, pitchOffset);
    ctx.stroke();

    // Pitch ladder
    ctx.strokeStyle = "#ffffff";
    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Courier New";
    ctx.textAlign = "center";
    ctx.lineWidth = 1;
    for (let deg = -30; deg <= 30; deg += 10) {
      if (deg === 0) continue;
      const y = pitchOffset - deg * 2;
      const w = Math.abs(deg) >= 20 ? 30 : 20;
      ctx.beginPath();
      ctx.moveTo(-w, y);
      ctx.lineTo(w, y);
      ctx.stroke();
      ctx.fillText(Math.abs(deg).toString(), w + 14, y + 3);
    }

    ctx.restore();

    // Fixed aircraft symbol
    ctx.strokeStyle = "#00ccff";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(cx - 40, cy);
    ctx.lineTo(cx - 15, cy);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + 15, cy);
    ctx.lineTo(cx + 40, cy);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.stroke();

    // Outer ring
    ctx.strokeStyle = "#1e3a5f";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  }
}
```

- [ ] **Step 2: Implement polling and DOM updates (main.js)**

```javascript
// dashboard/static/js/main.js

let attitude;
let pollInterval;
const POLL_MS = 500;

document.addEventListener("DOMContentLoaded", function () {
  attitude = new AttitudeIndicator("attitude-canvas");
  startPolling();
  setupControls();
  updateClock();
  setInterval(updateClock, 1000);
});

function startPolling() {
  poll();
  pollInterval = setInterval(poll, POLL_MS);
}

async function poll() {
  try {
    const resp = await fetch("/api/status");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    updateDashboard(data);
    setConnectionStatus(true);
  } catch (e) {
    setConnectionStatus(false);
  }
}

function updateDashboard(d) {
  // State
  const stateEl = document.getElementById("flight-state");
  stateEl.textContent = d.state || "IDLE";
  stateEl.className = "state " + (d.state || "idle").toLowerCase();

  // Altitude
  document.getElementById("alt-value").textContent =
    (d.altitude != null ? d.altitude.toFixed(1) : "0") + " m";

  // Vertical speed
  const vs = d.vspeed || 0;
  const vsStr = (vs >= 0 ? "+" : "") + vs.toFixed(1) + " m/s";
  document.getElementById("vs-value").textContent = vsStr;

  // Attitude
  attitude.update(d.roll || 0, d.pitch || 0);

  // Environment
  document.getElementById("pressure").textContent =
    (d.pressure != null ? d.pressure.toFixed(1) : "----") + " hPa";
  document.getElementById("temperature").textContent =
    (d.temperature != null ? d.temperature.toFixed(1) : "--") + " \u00B0C";
  document.getElementById("humidity").textContent =
    (d.humidity != null ? d.humidity.toFixed(0) : "--") + " %";

  // Battery
  const pct = d.battery_pct || 0;
  const fill = document.getElementById("battery-fill");
  fill.style.width = pct + "%";
  fill.className =
    "bar-fill" + (pct < 15 ? " critical" : pct < 30 ? " warning" : "");
  document.getElementById("battery-pct").textContent = pct.toFixed(0) + "%";
  document.getElementById("voltage").textContent =
    (d.battery_v != null ? d.battery_v.toFixed(2) : "--") + " V";

  // Logging
  const logEl = document.getElementById("logging-status");
  const isActive = d.state && d.state !== "IDLE";
  logEl.textContent = isActive ? "ACTIVE" : "INACTIVE";
  logEl.className = "value " + (isActive ? "status-active" : "status-inactive");

  // Buttons
  const isIdle = !d.state || d.state === "IDLE";
  const isArmed = d.state === "ARMED";
  document.getElementById("btn-arm").disabled = !isIdle;
  document.getElementById("btn-disarm").disabled = !isArmed;
}

function setConnectionStatus(connected) {
  const el = document.getElementById("connection-status");
  el.textContent = connected ? "Connected" : "Disconnected";
  el.className = "conn-status " + (connected ? "connected" : "disconnected");
}

function updateClock() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, "0");
  const m = String(now.getMinutes()).padStart(2, "0");
  const s = String(now.getSeconds()).padStart(2, "0");
  document.getElementById("clock").textContent = h + ":" + m + ":" + s;
}

function setupControls() {
  document
    .getElementById("btn-arm")
    .addEventListener("click", async function () {
      await fetch("/api/arm", { method: "POST" });
    });

  document
    .getElementById("btn-disarm")
    .addEventListener("click", async function () {
      await fetch("/api/disarm", { method: "POST" });
    });

  document.getElementById("btn-config").addEventListener("click", openConfig);
  document
    .getElementById("btn-config-close")
    .addEventListener("click", closeConfig);
  document
    .getElementById("btn-config-save")
    .addEventListener("click", saveConfig);
}

async function openConfig() {
  const resp = await fetch("/api/config");
  const cfg = await resp.json();
  const container = document.getElementById("config-fields");

  // Clear existing fields using safe DOM method
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }

  for (const [key, value] of Object.entries(cfg)) {
    const row = document.createElement("div");
    row.className = "config-row";

    const label = document.createElement("label");
    label.textContent = key;

    const input = document.createElement("input");
    input.type = "text";
    input.dataset.key = key;
    input.value = value;

    row.appendChild(label);
    row.appendChild(input);
    container.appendChild(row);
  }

  document.getElementById("config-modal").classList.remove("hidden");
}

function closeConfig() {
  document.getElementById("config-modal").classList.add("hidden");
}

async function saveConfig() {
  const inputs = document.querySelectorAll("#config-fields input");
  const cfg = {};
  inputs.forEach(function (input) {
    const val = input.value;
    const num = Number(val);
    cfg[input.dataset.key] = isNaN(num) ? val : num;
  });

  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });

  closeConfig();
}
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/js/main.js dashboard/static/js/gauges.js
git commit -m "feat: add dashboard JavaScript with polling, attitude indicator, and config modal"
```

---

## Task 12: Systemd Services and Deploy Script

**Files:**

- Create: `config/rocket-flight.service`
- Create: `config/rocket-dashboard.service`
- Create: `scripts/deploy.sh`

- [ ] **Step 1: Create flight controller service**

```ini
# config/rocket-flight.service
[Unit]
Description=Rocket Flight Controller
After=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/rocket
ExecStart=/opt/rocket/venv/bin/python -m flight.main
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create dashboard service**

```ini
# config/rocket-dashboard.service
[Unit]
Description=Rocket Dashboard Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/rocket
ExecStart=/opt/rocket/venv/bin/python -m dashboard.app
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Create deploy script**

```bash
#!/usr/bin/env bash
# scripts/deploy.sh
# Manual deployment script - run on the Raspberry Pi via SSH.
set -euo pipefail

ROCKET_DIR="/opt/rocket"
VENV_DIR="${ROCKET_DIR}/venv"
DATA_DIR="${ROCKET_DIR}/data"

echo "=== Rocket Flight Computer - Deploy ==="

# Pull latest code
cd "$ROCKET_DIR"
echo "[1/5] Pulling latest code..."
git pull

# Ensure venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "[2/5] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "[2/5] Virtual environment exists."
fi

# Install dependencies
echo "[3/5] Installing dependencies..."
"$VENV_DIR/bin/pip" install -r requirements.txt --quiet

# Ensure data directory exists
mkdir -p "$DATA_DIR"

# Install/update systemd services
echo "[4/5] Updating systemd services..."
sudo cp config/rocket-flight.service /etc/systemd/system/
sudo cp config/rocket-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rocket-flight.service

# Restart services
echo "[5/5] Restarting services..."
sudo systemctl restart rocket-flight.service
sudo systemctl restart rocket-dashboard.service

echo ""
echo "=== Deploy complete ==="
echo "Flight Controller: $(sudo systemctl is-active rocket-flight.service)"
echo "Dashboard:         $(sudo systemctl is-active rocket-dashboard.service)"
echo "Dashboard URL:     http://$(hostname).local:8080"
```

- [ ] **Step 4: Commit**

```bash
git add config/rocket-flight.service config/rocket-dashboard.service scripts/deploy.sh
git commit -m "feat: add systemd services and manual deploy script"
```

---

## Task 13: Setup and README

**Files:**

- Create: `setup.py`
- Create: `README.md`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create setup.py**

```python
# setup.py
from setuptools import setup, find_packages

setup(
    name="rocket-flight-computer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "flask",
    ],
    extras_require={
        "pi": [
            "adafruit-circuitpython-bme280",
            "adafruit-circuitpython-bno055",
            "RPi.GPIO",
        ],
    },
    entry_points={
        "console_scripts": [
            "rocket-flight=flight.main:main",
            "rocket-dashboard=dashboard.app:main",
        ],
    },
)
```

- [ ] **Step 2: Create README**

```markdown
# Rocket Flight Computer

Flight computer software for a model rocket on Raspberry Pi Zero.

## Components

- **Flight Controller** - Sensor readout, data logging, flight state machine, parachute deployment
- **Dashboard** - Web-based avionics cockpit UI for monitoring and configuration

## Hardware

- Raspberry Pi Zero
- Adafruit PowerBoost 500 + 3.7V LiPo
- BME280 (pressure, temperature, humidity)
- BNO055 (9-DOF orientation)

## Quick Start (Raspberry Pi)

    git clone <your-repo-url> /opt/rocket
    cd /opt/rocket
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    bash scripts/deploy.sh

Dashboard: http://<pi-hostname>.local:8080

## Development (PC)

    pip install -r requirements.txt
    python -m pytest tests/ -v

## Deploy

    # On your PC:
    git push origin main

    # SSH into Pi:
    ssh pi@rocket.local
    cd /opt/rocket && bash scripts/deploy.sh
```

- [ ] **Step 3: Create test init file**

```python
# tests/__init__.py
```

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add setup.py README.md tests/__init__.py
git commit -m "feat: add setup.py, README, and test infrastructure"
```

---

## Summary

| Task      | Component                                        | Tests  |
| --------- | ------------------------------------------------ | ------ |
| 1         | Database schema + access layer                   | 6      |
| 2         | Configuration manager                            | 5      |
| 3         | Altitude calculator                              | 5      |
| 4         | Sensor abstractions (BME280, BNO055, PowerBoost) | 6      |
| 5         | Flight state machine                             | 12     |
| 6         | Deployment controller (GPIO)                     | 5      |
| 7         | Data logger                                      | 4      |
| 8         | Flight controller main loop                      | 4      |
| 9         | Dashboard Flask backend + API                    | 8      |
| 10        | Dashboard HTML + CSS                             | 1      |
| 11        | Dashboard JavaScript (polling, gauges)           | –      |
| 12        | Systemd services + deploy script                 | –      |
| 13        | Setup + README                                   | –      |
| **Total** |                                                  | **56** |
