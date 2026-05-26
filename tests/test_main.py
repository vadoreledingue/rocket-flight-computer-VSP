import os
import tempfile
import pytest
from unittest.mock import MagicMock
from flight.main import FlightController
from flight.state_machine import FlightState


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except PermissionError:
        pass  # Windows: SQLite may still hold the file


@pytest.fixture
def mock_sensors():
    bmp280 = MagicMock()
    bmp280.read.return_value = {"pressure": 1013.25,
                                "temperature": 21.0}
    mpu6050 = MagicMock()
    mpu6050.read.return_value = {"yaw": 0.0, "roll": 0.0, "pitch": 0.0, "accel_x": 0.0,
                                 "accel_y": 0.0, "accel_z": 10.81, "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0}
    return bmp280, mpu6050


def test_controller_initializes(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    assert ctrl.state_machine.state.value == "IDLE"


def test_single_tick_reads_sensors(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    ctrl.tick()
    bmp280.read.assert_called_once()
    mpu6050.read.assert_called_once()
    assert ctrl._max_net_accel == pytest.approx(1.0)


def test_tick_logs_data_when_armed(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    ctrl.state_machine.arm()
    ctrl.tick()
    rows = ctrl.db.get_latest_readings(count=1)
    assert len(rows) == 1
    assert rows[0]["state"] == "ARMED"


def test_tick_handles_sensor_failure_gracefully(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    bmp280.read.return_value = None
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    ctrl.state_machine.arm()
    ctrl.tick()  # should not crash


def test_camera_starts_when_flight_is_armed(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    ctrl.camera = MagicMock()
    ctrl.camera.is_running = False

    ctrl.state_machine.arm()
    ctrl.tick()

    ctrl.camera.start.assert_called_once()


def test_camera_stops_when_state_is_no_longer_active(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    ctrl.camera = MagicMock()
    ctrl.camera.is_running = True
    ctrl.state_machine._state = FlightState.LANDED

    ctrl.tick()

    ctrl.camera.stop.assert_called_once()


def test_report_generation_runs_once_after_landing(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    ctrl.camera = MagicMock()
    ctrl.camera.is_running = True
    ctrl.report_manager = MagicMock()

    ctrl.state_machine.arm()
    ctrl.tick()
    active_flight_id = ctrl.logger.flight_id

    ctrl.state_machine._state = FlightState.LANDED
    ctrl.tick()

    ctrl.report_manager.generate_for_flight.assert_called_once_with(active_flight_id)
    assert ctrl.state_machine.state == FlightState.IDLE


def test_controller_returns_to_idle_even_if_report_generation_fails(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    ctrl.camera = MagicMock()
    ctrl.camera.is_running = True
    ctrl.report_manager = MagicMock()
    ctrl.report_manager.generate_for_flight.side_effect = RuntimeError("boom")

    ctrl.state_machine.arm()
    ctrl.tick()

    ctrl.state_machine._state = FlightState.LANDED
    ctrl.tick()

    assert ctrl.state_machine.state == FlightState.IDLE


def test_camera_restarts_in_active_flight_with_same_flight_id(db_path, mock_sensors):
    bmp280, mpu6050 = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050)
    ctrl.camera = MagicMock()
    ctrl.camera.is_running = False

    ctrl.state_machine.arm()
    ctrl.tick()
    active_flight_id = ctrl.logger.flight_id

    ctrl.camera.start.reset_mock()
    ctrl.camera.is_running = False
    ctrl.state_machine._state = FlightState.ASCENT
    ctrl.tick()

    ctrl.camera.start.assert_called_once_with(str(active_flight_id))
