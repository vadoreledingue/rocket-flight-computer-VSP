"""Orientation calculations from accelerometer data.

Provides pitch and roll Euler angles computed from 3-axis accelerometer readings
using inverse tangent of normalized acceleration components. Yaw calculation
requires gyroscope integration (not implemented; always 0.0 without magnetometer).
"""

import math


def compute_pitch_roll(accel_x: float, accel_y: float, accel_z: float) -> tuple[float, float]:
    """Compute pitch and roll from accelerometer data.

    Assumes accelerometer is mounted with:
    - X-axis pointing forward (aircraft nose)
    - Y-axis pointing right (starboard)
    - Z-axis pointing down (nadir)

    Normalizes by gravity (9.81 m/s²) and applies inverse tangent to get
    rotation angles around the Y and X axes respectively.

    Args:
        accel_x: Forward acceleration in m/s²
        accel_y: Right-wing acceleration in m/s²
        accel_z: Downward acceleration in m/s²

    Returns:
        tuple of (pitch, roll) in degrees:
        - pitch: Rotation around Y-axis (right wing), range ±90°
        - roll: Rotation around X-axis (forward), range ±180°
    """
    x_g = accel_x / 9.81
    y_g = accel_y / 9.81
    z_g = accel_z / 9.81

    pitch = math.degrees(math.atan2(x_g, math.sqrt(y_g**2 + z_g**2)))
    roll = math.degrees(math.atan2(y_g, math.sqrt(x_g**2 + z_g**2)))

    return pitch, roll
