from typing import Optional
import math
import sys


class MPU6050Sensor:
    """MPU-6050 6-axis IMU sensor (accelerometer + gyroscope).

    Uses simple mpu6050 library. Falls back to smbus2 direct register access
    if mpu6050 library is unavailable.

    Provides raw accelerometer (±2g) and gyroscope (±250 dps) readings.
    Euler angles (pitch/roll) are computed from accelerometer via atan2.
    Yaw requires gyro integration (not implemented; always 0.0).
    """

    def __init__(self) -> None:
        self._device = None
        self._fallback = False
        self._bus = None
        self._addr = 0x68
        self._initialized = False
        self._init_error: Optional[str] = None

        try:
            from mpu6050 import mpu6050
            self._device = mpu6050(0x68)
            self._fallback = False
            self._initialized = True
            print("[MPU6050] Initialized via mpu6050 library", file=sys.stderr)
        except Exception as e:
            mpu6050_error = str(e)
            try:
                from smbus2 import SMBus
                self._bus = SMBus(1)
                self._device = None
                self._fallback = True
                self._initialized = True
                print(f"[MPU6050] mpu6050 library failed ({mpu6050_error}), using SMBus fallback", file=sys.stderr)
            except Exception as smbus_err:
                self._device = None
                self._bus = None
                self._initialized = False
                self._init_error = f"mpu6050: {mpu6050_error}; SMBus: {str(smbus_err)}"
                print(f"[MPU6050] ERROR: Failed to initialize sensor: {self._init_error}", file=sys.stderr)

    def _compute_pitch_roll(self, accel: tuple) -> tuple:
        """Compute pitch and roll from accelerometer data.

        Args:
            accel: tuple of (x, y, z) acceleration values in m/s²

        Returns:
            tuple of (pitch, roll) in degrees
        """
        x, y, z = accel
        x_g = x / 9.81
        z_g = z / 9.81
        y_g = y / 9.81
        pitch = math.degrees(math.atan2(x_g, math.sqrt(y_g**2 + z_g**2)))
        roll = math.degrees(math.atan2(y_g, math.sqrt(x_g**2 + z_g**2)))
        return pitch, roll

    def read(self) -> Optional[dict]:
        if not self._initialized:
            if self._init_error and not hasattr(self, '_logged_init_error'):
                print(f"[MPU6050] Cannot read: {self._init_error}", file=sys.stderr)
                self._logged_init_error = True
            return None

        try:
            if not self._fallback and self._device is not None:
                accel_data = self._device.get_accel_data()
                gyro_data = self._device.get_gyro_data()

                accel_x = accel_data.get('x', 0.0)
                accel_y = accel_data.get('y', 0.0)
                accel_z = accel_data.get('z', 0.0)
                gyro_x = gyro_data.get('x', 0.0)
                gyro_y = gyro_data.get('y', 0.0)
                gyro_z = gyro_data.get('z', 0.0)

                pitch, roll = self._compute_pitch_roll((accel_x, accel_y, accel_z))
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

            if self._fallback and self._bus is not None:
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

                accel_x = ax / 16384.0
                accel_y = ay / 16384.0
                accel_z = az / 16384.0
                gyro_x = gx / 131.0
                gyro_y = gy / 131.0
                gyro_z = gz / 131.0

                pitch, roll = self._compute_pitch_roll(
                    (accel_x, accel_y, accel_z))

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

            print("[MPU6050] ERROR: Sensor not properly initialized (no device or bus)", file=sys.stderr)
            return None
        except OSError as e:
            print(f"[MPU6050] I2C OSError during read: {e}", file=sys.stderr)
            return None
        except ValueError as e:
            print(f"[MPU6050] ValueError during read: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"[MPU6050] Unexpected error during read: {type(e).__name__}: {e}", file=sys.stderr)
            return None
