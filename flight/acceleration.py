import math


class AccelerationCalculator:
    """Calculate total and net acceleration from sensor data.

    Total acceleration: magnitude of acceleration vector including gravity.
    Net acceleration: magnitude minus 1g (gravity), represents actual thrust/motion.
    """

    def update(self, accel_x: float, accel_y: float, accel_z: float) -> dict:
        """Calculate acceleration metrics from IMU readings.

        Args:
            accel_x, accel_y, accel_z: Acceleration components in m/s²

        Returns:
            dict with:
              - total_accel: magnitude in m/s²
              - net_accel: magnitude - 9.81 m/s² (clamped to 0.0 minimum)
        """
        total = math.sqrt(accel_x**2 + accel_y**2 + accel_z**2)
        net = max(0.0, total - 9.81)
        return {
            "total_accel": total,
            "net_accel": net,
        }
