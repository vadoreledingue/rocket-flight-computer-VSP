from typing import Optional


class BMP280Sensor:
    """BMP280 sensor (pressure, temperature). No humidity sensor in BMP280."""

    def __init__(self) -> None:
        import board
        import busio
        import adafruit_bmp280
        i2c = busio.I2C(board.SCL, board.SDA)
        self._device = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=0x77)
        # Set sea level pressure for altitude calculation (typically 1013.25 hPa)
        self._device.sea_level_pressure = 1013.25

    def read(self) -> Optional[dict]:
        try:
            return {
                "pressure": self._device.pressure,
                "temperature": self._device.temperature,
                "humidity": None,  # BMP280 doesn't measure humidity
            }
        except (OSError, ValueError):
            return None
