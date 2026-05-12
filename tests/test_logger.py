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
        "pressure": 1013.25, "temperature": 21.0,
        "altitude": 100.0, "vspeed": 10.0,
        "roll": 1.0, "pitch": 2.0, "yaw": 3.0,
        "accel_x": 0.1, "accel_y": 0.2, "accel_z": 9.8,
        "net_accel": 0.2,
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
    logger.end_flight(max_altitude=150.0, max_vspeed=40.0,
                      max_net_accel=0.2, duration=12.0)
    flights = db.get_flights()
    assert flights[0]["state"] == "COMPLETED"
    assert flights[0]["max_altitude"] == pytest.approx(150.0)


def test_log_without_flight_uses_none(db: FlightDB):
    logger = FlightLogger(db)
    logger.log(make_sensor_data(), state="IDLE", timestamp=time.time())
    rows = db.get_latest_readings(count=1)
    assert rows[0]["flight_id"] is None
