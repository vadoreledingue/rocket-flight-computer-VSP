from typing import Optional
import math


class MPU6050Sensor:
    """MPU-6050 6-axis IMU sensor (accelerometer + gyroscope).

    Supports two initialization modes:
    1. Adafruit CircuitPython driver (preferred, handles I2C communication)
    2. SMBus fallback (direct register access if Adafruit fails)

    Provides raw accelerometer (±2g) and gyroscope (±250 dps) readings.
    Euler angles (pitch/roll) are computed from accelerometer via atan2.
    Yaw requires gyro integration (not implemented; always 0.0).
    """

    def __init__(self) -> None:
        # Try to initialize the Adafruit driver first. If it fails (e.g. unexpected
        # WHO_AM_I value for this device variant), fall back to a direct SMBus
        # implementation reading registers manually.
        try:
            import board
            import busio
            import adafruit_mpu6050
            i2c = busio.I2C(board.SCL, board.SDA)
            self._device = adafruit_mpu6050.MPU6050(i2c)
            self._fallback = False
            self._bus = None
        except Exception:
            # Fallback: use smbus2 to read registers directly
            from smbus2 import SMBus
            self._device = None
            self._fallback = True
            self._bus = SMBus(1)
            self._addr = 0x68

    def _compute_pitch_roll(self, accel: tuple) -> tuple:
        """Compute pitch and roll from accelerometer data.

        Args:
            accel: tuple of (x, y, z) acceleration values

        Returns:
            tuple of (pitch, roll) in degrees
        """
        x, y, z = accel
        pitch = math.degrees(math.atan2(x, math.sqrt(y**2 + z**2)))
        roll = math.degrees(math.atan2(y, math.sqrt(x**2 + z**2)))
        return pitch, roll

    def read(self) -> Optional[dict]:
        try:
            if not self._fallback and self._device is not None:
                accel = self._device.acceleration
                gyro = self._device.gyro
                if accel is None or gyro is None:
                    return None
                pitch, roll = self._compute_pitch_roll(accel)
                return {
                    "yaw": 0.0,
                    "roll": roll,
                    "pitch": pitch,
                    "accel_x": accel[0],
                    "accel_y": accel[1],
                    "accel_z": accel[2],
                    "gyro_x": gyro[0],
                    "gyro_y": gyro[1],
                    "gyro_z": gyro[2],
                }

            # SMBus fallback: read raw registers and convert
            if self._fallback and self._bus is not None:
                # Read 6 accel bytes starting at 0x3B and 6 gyro bytes at 0x43
                def read_word(reg):
                    hi = self._bus.read_byte_data(self._addr, reg)
                    lo = self._bus.read_byte_data(self._addr, reg + 1)
                    val = (hi << 8) | lo
                    if val & 0x8000:
                        val = -((val ^ 0xFFFF) + 1)
                    return val

                ax = read_word(0x3B)
                ay = read_word(0x3D)
                az = read_word(0x3F)
                gx = read_word(0x43)
                gy = read_word(0x45)
                gz = read_word(0x47)

                # Convert raw values to physical units.
                # Assuming default FS: accel +/-2g -> 16384 LSB/g; gyro +/-250 dps -> 131 LSB/(deg/s)
                accel_x = ax / 16384.0
                accel_y = ay / 16384.0
                accel_z = az / 16384.0
                gyro_x = gx / 131.0
                gyro_y = gy / 131.0
                gyro_z = gz / 131.0

                pitch, roll = self._compute_pitch_roll(
                    (accel_x, accel_y, accel_z))

                return {
                    "yaw": 0.0,
                    "roll": roll,
                    "pitch": pitch,
                    "accel_x": accel_x,
                    "accel_y": accel_y,
                    "accel_z": accel_z,
                    "gyro_x": gyro_x,
                    "gyro_y": gyro_y,
                    "gyro_z": gyro_z,
                }

            return None
        except (OSError, ValueError, Exception):
            return None
