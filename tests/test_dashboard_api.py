import os
import json
import tempfile
import time
from pathlib import Path
import pytest
from flight.database import FlightDB
from flight.config import ConfigManager
from dashboard.app import create_app


def seed_completed_flight(db: FlightDB) -> int:
    now = time.time()
    flight_id = db.create_flight()
    for index in range(5):
        db.insert_reading(
            flight_id=flight_id,
            timestamp=now + index,
            pressure=1013.25 - index * 0.3,
            temperature=21.0 + index * 0.2,
            altitude=index * 12.5,
            vspeed=5.0 + index,
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
            accel_x=0.0,
            accel_y=0.0,
            accel_z=9.81 + index * 0.4,
            total_accel=9.81 + index * 0.4,
            net_accel=index * 0.4,
            state="ASCENT" if index < 4 else "LANDED",
        )
    db.end_flight(
        flight_id,
        max_altitude=50.0,
        max_vspeed=9.0,
        max_net_accel=1.6,
        duration=4.0,
    )
    return flight_id


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
        temperature=21.0, altitude=0.0, vspeed=0.0,
        roll=0.0, pitch=0.0, yaw=0.0, accel_x=0.0, accel_y=0.0, accel_z=9.81,
        total_accel=9.81, net_accel=0.0, state="IDLE",
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


def test_reports_page_returns_html(client):
    resp = client.get("/reports")
    assert resp.status_code == 200
    assert b"FLIGHT REPORT" in resp.data


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
    assert data["status"] == "ok"
    assert client.application.config["config_manager"].get(
        "arm_requested") == "true"


def test_api_disarm(client):
    client.post("/api/arm")
    resp = client.post("/api/disarm")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "ok"
    assert client.application.config["config_manager"].get(
        "disarm_requested") == "true"


def test_api_hardware_status(client):
    resp = client.get("/api/hardware")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "pins" in data
    assert "sensors" in data
    assert len(data["pins"]) == 4
    assert len(data["sensors"]) == 2
    # On dev machine, i2cdetect not available, so sensors show not connected
    for sensor in data["sensors"]:
        assert "name" in sensor
        assert "connected" in sensor


def test_api_camera_stream_reads_shared_frame_file(client, tmp_path):
    frame_file = tmp_path / "rocket_camera_frame.jpg"
    frame_file.write_bytes(b"\xff\xd8" + b"\x00" * 256 + b"\xff\xd9")
    client.application.config["camera_frame_file"] = Path(frame_file)

    resp = client.get("/api/camera/stream")

    assert resp.status_code == 200
    assert resp.mimetype == "multipart/x-mixed-replace"
    first_chunk = next(resp.response)
    assert b"Content-Type: image/jpeg" in first_chunk


def test_api_reports_generates_detail_assets(db_path, tmp_path):
    db = FlightDB(db_path)
    ConfigManager(db)
    flight_id = seed_completed_flight(db)
    db.close()

    app = create_app(
        db_path=db_path,
        report_dir=str(tmp_path / "reports"),
        video_dir=str(tmp_path / "videos"),
    )
    app.config["TESTING"] = True

    with app.test_client() as client:
        list_resp = client.get("/api/reports")
        assert list_resp.status_code == 200
        reports = json.loads(list_resp.data)
        assert len(reports) == 1
        assert reports[0]["flight_id"] == flight_id

        detail_resp = client.get(f"/api/reports/{flight_id}")
        assert detail_resp.status_code == 200
        report = json.loads(detail_resp.data)
        assert report["report_available"] is True
        assert len(report["images"]) == 4
        assert len(report["smoothed_images"]) == 4
        assert report["raw_summary"]["max_altitude"] == 50.0
        assert report["smoothed_summary"] is not None
        assert report["smoothing"]["window_size"] == 5
        assert report["video"]["available"] is False

        asset_resp = client.get(report["images"][0]["url"])
        assert asset_resp.status_code == 200
        assert asset_resp.mimetype == "image/png"

    app.config["db"].close()
