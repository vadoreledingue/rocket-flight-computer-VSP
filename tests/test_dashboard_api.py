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
    # Close DB connection so Windows can delete the temp file in teardown
    app.config["db"].close()


@pytest.fixture
def seeded_client(db_path):
    db = FlightDB(db_path)
    ConfigManager(db)
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
    # Close DB connection so Windows can delete the temp file in teardown
    app.config["db"].close()


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
    assert "sample_rate_idle" in data


def test_api_config_post(client):
    resp = client.post("/api/config",
                       data=json.dumps({"sample_rate_idle": 5}),
                       content_type="application/json")
    assert resp.status_code == 200
    resp2 = client.get("/api/config")
    data = json.loads(resp2.data)
    assert data["sample_rate_idle"] == 5


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


def test_api_battery_test_lifecycle(client):
    # No active test initially
    resp = client.get("/api/battery-test")
    assert resp.status_code == 200
    assert json.loads(resp.data) is None

    # Start test
    resp = client.post("/api/battery-test/start")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["state"] == "RUNNING"

    # Cannot start while running
    resp = client.post("/api/battery-test/start")
    assert resp.status_code == 409

    # Active test exists
    resp = client.get("/api/battery-test")
    data = json.loads(resp.data)
    assert data["state"] == "RUNNING"
    assert "elapsed" in data

    # Stop test
    resp = client.post("/api/battery-test/stop")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["state"] == "COMPLETED"

    # Cannot stop when none running
    resp = client.post("/api/battery-test/stop")
    assert resp.status_code == 404

    # History shows completed test
    resp = client.get("/api/battery-tests")
    data = json.loads(resp.data)
    assert len(data) == 1
    assert data[0]["state"] == "COMPLETED"

    # Clear history
    resp = client.post("/api/battery-tests/clear")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["deleted"] == 1

    resp = client.get("/api/battery-tests")
    assert json.loads(resp.data) == []


def test_api_hardware_status(client):
    resp = client.get("/api/hardware")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "pins" in data
    assert "sensors" in data
    assert len(data["pins"]) == 6
    assert len(data["sensors"]) == 2
    # On dev machine, i2cdetect not available, so sensors show not connected
    for sensor in data["sensors"]:
        assert "name" in sensor
        assert "connected" in sensor
