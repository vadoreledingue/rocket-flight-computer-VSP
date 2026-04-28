from enum import Enum
from typing import Optional


class FlightState(Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    ASCENT = "ASCENT"
    APOGEE = "APOGEE"
    DESCENT = "DESCENT"
    LANDED = "LANDED"


class StateMachine:
    def __init__(self, apogee_samples: int = 5,
                 landing_stable_time: float = 10.0) -> None:
        self._state = FlightState.IDLE
        self._apogee_samples = apogee_samples
        self._landing_stable_time = landing_stable_time
        self._falling_count: int = 0
        self._max_altitude: float = 0.0
        self._armed_time: Optional[float] = None
        self._stable_since: Optional[float] = None
        self._last_altitude: Optional[float] = None

    @property
    def state(self) -> FlightState:
        return self._state

    @property
    def max_altitude(self) -> float:
        return self._max_altitude

    def arm(self) -> None:
        if self._state == FlightState.IDLE:
            self._state = FlightState.ARMED
            self._falling_count = 0
            self._max_altitude = 0.0
            self._armed_time = None
            self._stable_since = None
            self._last_altitude = None

    def disarm(self) -> None:
        if self._state == FlightState.ARMED:
            self._state = FlightState.IDLE

    def update(self, reading: dict) -> None:
        alt: float = reading["altitude"]
        vspeed: float = reading["vspeed"]
        ts: float = reading["timestamp"]

        if self._state == FlightState.ARMED:
            # Record arm time on first update
            if self._armed_time is None:
                self._armed_time = ts
            # Detect launch: meaningful altitude gain and upward speed
            if alt >= 5.0 and vspeed > 5.0:
                self._state = FlightState.ASCENT

        elif self._state == FlightState.ASCENT:
            self._max_altitude = max(self._max_altitude, alt)
            # Count consecutive falling samples to confirm apogee
            if vspeed < 0:
                self._falling_count += 1
            else:
                self._falling_count = 0
            if self._falling_count >= self._apogee_samples:
                self._state = FlightState.APOGEE

        elif self._state == FlightState.APOGEE:
            # Transition to descent and clear last altitude so the landing detector
            # starts fresh without comparing against an apogee-phase altitude
            self._state = FlightState.DESCENT
            self._last_altitude = None

        elif self._state == FlightState.DESCENT:
            # Detect landing by stable altitude over landing_stable_time seconds.
            # If no previous altitude is known (e.g. first sample after apogee),
            # begin the stability timer immediately.
            if self._last_altitude is None:
                self._stable_since = ts
            elif abs(alt - self._last_altitude) < 1.0:
                if self._stable_since is None:
                    self._stable_since = ts
                elif ts - self._stable_since >= self._landing_stable_time:
                    self._state = FlightState.LANDED
            else:
                self._stable_since = None

        self._last_altitude = alt
