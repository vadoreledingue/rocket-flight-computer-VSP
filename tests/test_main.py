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
    try:
        os.unlink(path)
    except PermissionError:
        pass  # Windows: SQLite may still hold the file


@pytest.fixture
def mock_sensors():
    bmp280 = MagicMock()
    bmp280.read.return_value = {"pressure": 1013.25,
                                "temperature": 21.0, "humidity": None}
    mpu6050 = MagicMock()
    mpu6050.read.return_value = {"yaw": 0.0, "roll": 0.0, "pitch": 0.0, "accel_x": 0.0,
                                 "accel_y": 0.0, "accel_z": 9.81, "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0}
    pwr = MagicMock()
    pwr.read.return_value = {"battery_v": 3.9, "battery_pct": 85.0}
    return bmp280, mpu6050, pwr


def test_controller_initializes(db_path, mock_sensors):
    bmp280, mpu6050, pwr = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050, power_sensor=pwr)
    assert ctrl.state_machine.state.value == "IDLE"


def test_single_tick_reads_sensors(db_path, mock_sensors):
    bmp280, mpu6050, pwr = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050, power_sensor=pwr)
    ctrl.tick()
    bmp280.read.assert_called_once()
    mpu6050.read.assert_called_once()
    pwr.read.assert_called_once()


def test_tick_logs_data_when_armed(db_path, mock_sensors):
    bmp280, mpu6050, pwr = mock_sensors
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050, power_sensor=pwr)
    ctrl.state_machine.arm()
    ctrl.tick()
    rows = ctrl.db.get_latest_readings(count=1)
    assert len(rows) == 1
    assert rows[0]["state"] == "ARMED"


def test_tick_handles_sensor_failure_gracefully(db_path, mock_sensors):
    bmp280, mpu6050, pwr = mock_sensors
    bmp280.read.return_value = None
    ctrl = FlightController(
        db_path=db_path, bmp280_sensor=bmp280, mpu6050_sensor=mpu6050, power_sensor=pwr)
    ctrl.state_machine.arm()
    ctrl.tick()  # should not crash
