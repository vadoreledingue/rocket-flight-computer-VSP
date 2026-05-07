from collections import deque
from typing import Optional


class AltitudeCalculator:
    """Computes altitude from barometric pressure using the hypsometric formula.

    Altitude is computed relative to a baseline pressure set via set_baseline().
    Vertical speed (m/s) is derived from altitude rate of change over time.
    History is maintained in a rolling buffer for post-flight analysis.
    """

    def __init__(self, history_size: int = 50) -> None:
        self._baseline_pressure: Optional[float] = None
        self._baseline_temp: Optional[float] = None
        self._last_altitude: float = 0.0
        self._last_timestamp: Optional[float] = None
        self.altitude: float = 0.0
        self.vspeed: float = 0.0
        self.history: deque[tuple[float, float]] = deque(maxlen=history_size)

    def set_baseline(self, pressure: float, temperature: float) -> None:
        self._baseline_pressure = pressure
        self._baseline_temp = temperature

    def compute(self, pressure: float, temperature: float) -> float:
        if self._baseline_pressure is None:
            return 0.0
        temp_k = temperature + 273.15
        altitude = temp_k / 0.0065 * (
            1.0 - (pressure / self._baseline_pressure) ** 0.190284
        )
        return altitude

    def update(self, pressure: float, temperature: float, timestamp: float) -> None:
        if self._baseline_pressure is None and pressure > 0:
            self.set_baseline(pressure, temperature)
        self.altitude = self.compute(pressure, temperature)
        if self._last_timestamp is not None:
            dt = timestamp - self._last_timestamp
            if dt > 0:
                self.vspeed = (self.altitude - self._last_altitude) / dt
        self._last_altitude = self.altitude
        self._last_timestamp = timestamp
        self.history.append((timestamp, self.altitude))
