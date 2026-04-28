from typing import Optional
import math


class MPU6050Sensor:
    """MPU-6050 sensor (accelerometer + 3-axis gyroscope).

    Provides raw accelerometer and gyroscope readings.
    Euler angles (pitch/roll) are computed from accelerometer only.
    """

    def __init__(self) -> None:
        import board
        import busio
        import adafruit_mpu6050
        i2c = busio.I2C(board.SCL, board.SDA)
        self._device = adafruit_mpu6050.MPU6050(i2c)

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
            accel = self._device.acceleration
            gyro = self._device.gyro
            if accel is None or gyro is None:
                return None

            pitch, roll = self._compute_pitch_roll(accel)

            return {
                "yaw": 0.0,  # MPU-6050 cannot measure yaw without magnetometer
                "roll": roll,
                "pitch": pitch,
                "accel_x": accel[0],
                "accel_y": accel[1],
                "accel_z": accel[2],
                "gyro_x": gyro[0],
                "gyro_y": gyro[1],
                "gyro_z": gyro[2],
            }
        except (OSError, ValueError):
            return None
