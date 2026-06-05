from typing import Optional
import sys
from flight.orientation import compute_pitch_roll


class MPU6050Sensor:
    """MPU-6050 6-axis IMU sensor (accelerometer + gyroscope).

    Uses simple mpu6050 library.

    Provides raw accelerometer (±2g) and gyroscope (±250 dps) readings.
    Euler angles (pitch/roll) are computed from accelerometer via atan2.
    Yaw requires gyro integration (not implemented; always 0.0).
    """

    def __init__(self) -> None:
        self._device = None
        self._initialized = False
        self._init_error: Optional[str] = None

        try:
            from mpu6050 import mpu6050
            self._device = mpu6050(0x68)
            self._initialized = True
            print("[MPU6050] Initialized via mpu6050 library", file=sys.stderr)
        except Exception as e:
            self._device = None
            self._initialized = False
            self._init_error = f"mpu6050: {str(e)}"
            print(
                f"[MPU6050] ERROR: Failed to initialize sensor: {self._init_error}", file=sys.stderr)

    def read(self) -> Optional[dict]:
        if not self._initialized:
            if self._init_error and not hasattr(self, '_logged_init_error'):
                print(
                    f"[MPU6050] Cannot read: {self._init_error}", file=sys.stderr)
                self._logged_init_error = True
            return None

        try:
            if self._device is not None:
                accel_data = self._device.get_accel_data()
                gyro_data = self._device.get_gyro_data()

                accel_x = accel_data.get('x', 0.0)
                accel_y = accel_data.get('y', 0.0)
                accel_z = accel_data.get('z', 0.0)
                gyro_x = gyro_data.get('x', 0.0)
                gyro_y = gyro_data.get('y', 0.0)
                gyro_z = gyro_data.get('z', 0.0)

                pitch, roll = compute_pitch_roll(accel_x, accel_y, accel_z)
                return {
                    "roll": roll,
                    "pitch": pitch,
                    "accel_x": accel_x,
                    "accel_y": accel_y,
                    "accel_z": accel_z,
                    "gyro_x": gyro_x,
                    "gyro_y": gyro_y,
                    "gyro_z": gyro_z,
                }

            print(
                "[MPU6050] ERROR: Sensor not properly initialized (no device)", file=sys.stderr)
            return None
        except OSError as e:
            print(f"[MPU6050] I2C OSError during read: {e}", file=sys.stderr)
            return None
        except ValueError as e:
            print(f"[MPU6050] ValueError during read: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(
                f"[MPU6050] Unexpected error during read: {type(e).__name__}: {e}", file=sys.stderr)
            return None
