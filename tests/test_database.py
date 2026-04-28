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
        flight_id=None, timestamp=time.time(), pressure=1013.25,
        temperature=21.0, humidity=45.0, altitude=0.0, vspeed=0.0,
        roll=0.0, pitch=0.0, yaw=0.0, accel_x=0.0, accel_y=0.0, accel_z=9.81,
        battery_pct=85.0, battery_v=3.9, state="IDLE",
    )
    rows = db.get_latest_readings(count=1)
    assert len(rows) == 1
    assert rows[0]["pressure"] == pytest.approx(1013.25)
    assert rows[0]["state"] == "IDLE"


def test_create_and_end_flight(db: FlightDB):
    flight_id = db.create_flight()
    assert flight_id == 1
    db.end_flight(flight_id, max_altitude=150.0,
                  max_vspeed=45.0, duration=12.5)
    flights = db.get_flights()
    assert len(flights) == 1
    assert flights[0]["max_altitude"] == pytest.approx(150.0)
    assert flights[0]["state"] == "COMPLETED"


def test_config_set_and_get(db: FlightDB):
    db.set_config("sample_rate_idle", "17")
    val = db.get_config("sample_rate_idle")
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


def test_battery_test_lifecycle(db: FlightDB):
    now = time.time()
    test_id = db.start_battery_test(now)
    assert test_id == 1

    active = db.get_active_battery_test()
    assert active is not None
    assert active["state"] == "RUNNING"
    assert active["low_at"] is None

    db.set_battery_test_low(test_id, now + 3600)
    active = db.get_active_battery_test()
    assert active["low_at"] == pytest.approx(now + 3600)

    # Second low call should not overwrite
    db.set_battery_test_low(test_id, now + 7200)
    active = db.get_active_battery_test()
    assert active["low_at"] == pytest.approx(now + 3600)

    db.stop_battery_test(test_id, now + 7200)
    assert db.get_active_battery_test() is None

    history = db.get_battery_tests()
    assert len(history) == 1
    assert history[0]["state"] == "COMPLETED"

    # Clear completed tests
    deleted = db.delete_completed_battery_tests()
    assert deleted == 1
    assert db.get_battery_tests() == []


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
