import pytest
from unittest.mock import MagicMock, patch
from flight.sensors.bme280 import BME280Sensor
from flight.sensors.bno055 import BNO055Sensor
from flight.sensors.power import PowerSensor


class TestBME280:
    def test_read_returns_dict_with_required_keys(self):
        sensor = BME280Sensor.__new__(BME280Sensor)
        sensor._device = MagicMock()
        sensor._device.pressure = 1013.25
        sensor._device.temperature = 21.0
        data = sensor.read()
        assert "pressure" in data
        assert "temperature" in data
        assert "humidity" in data
        assert data["humidity"] is None  # BMP280 has no humidity sensor
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
        sensor = BNO055Sensor.__new__(BNO055Sensor)
        sensor._device = MagicMock()
        sensor._device.acceleration = (0.1, 0.2, 9.8)
        sensor._device.gyro = (0.01, 0.02, 0.03)
        data = sensor.read()
        # MPU-6050 cannot measure yaw without magnetometer
        assert data["yaw"] == pytest.approx(0.0)
        assert "roll" in data
        assert "pitch" in data
        assert data["accel_x"] == pytest.approx(0.1)
        assert data["accel_z"] == pytest.approx(9.8)
        assert data["gyro_x"] == pytest.approx(0.01)
        assert data["gyro_z"] == pytest.approx(0.03)

    def test_read_returns_none_on_error(self):
        sensor = BNO055Sensor.__new__(BNO055Sensor)
        sensor._device = MagicMock()
        type(sensor._device).acceleration = property(
            lambda s: (_ for _ in ()).throw(OSError("I2C"))
        )
        data = sensor.read()
        assert data is None


class TestPowerSensor:
    def test_read_returns_ok_when_battery_not_low(self):
        sensor = PowerSensor.__new__(PowerSensor)
        sensor._is_low_battery = MagicMock(return_value=False)
        data = sensor.read()
        assert "battery_v" in data
        assert "battery_pct" in data
        assert "battery_low" in data
        assert data["battery_low"] is False
        assert data["battery_pct"] == pytest.approx(80.0)

    def test_read_returns_low_when_battery_low(self):
        sensor = PowerSensor.__new__(PowerSensor)
        sensor._is_low_battery = MagicMock(return_value=True)
        data = sensor.read()
        assert data["battery_low"] is True
        assert data["battery_pct"] == pytest.approx(10.0)
        assert data["battery_v"] == pytest.approx(3.2)
