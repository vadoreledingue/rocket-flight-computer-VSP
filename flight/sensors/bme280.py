from typing import Optional


class BME280Sensor:
    def __init__(self) -> None:
        import board
        import busio
        import adafruit_bme280.advanced as adafruit_bme280
        i2c = busio.I2C(board.SCL, board.SDA)
        self._device = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)

    def read(self) -> Optional[dict]:
        try:
            return {
                "pressure": self._device.pressure,
                "temperature": self._device.temperature,
                "humidity": self._device.relative_humidity,
            }
        except (OSError, ValueError):
            return None
