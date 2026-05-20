from enum import Enum
from typing import Optional


class FlightState(Enum):
    """Six-state rocket lifecycle model.

    IDLE → ARMED → ASCENT → APOGEE → DESCENT → LANDED

    - IDLE: Safe default, no logging
    - ARMED: Ready for launch, baseline pressure calibrated
    - ASCENT: Launch detected by net acceleration
    - APOGEE: Apex reached (falling for N samples)
    - DESCENT: Coasting down, landing detector active
    - LANDED: Flight complete, safe state
    """

    IDLE = "IDLE"
    ARMED = "ARMED"
    ASCENT = "ASCENT"
    APOGEE = "APOGEE"
    DESCENT = "DESCENT"
    LANDED = "LANDED"


class StateMachine:
    def __init__(self, apogee_samples: int = 5,
                 landing_stable_time: float = 10.0,
                 landing_accel_threshold: float = 1.0) -> None:
        self._state = FlightState.IDLE
        self._apogee_samples = apogee_samples
        self._landing_stable_time = landing_stable_time
        self._landing_accel_threshold = landing_accel_threshold
        self._flat_test = False
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
        net_accel: float = reading.get("net_accel", 0.0)

        if self._state == FlightState.ARMED:
            # Record arm time on first update
            if self._armed_time is None:
                self._armed_time = ts
            # Detect launch from net acceleration alone
            if net_accel > 2.0:
                # Normal transition to ASCENT
                self._state = FlightState.ASCENT
                # If flat-test mode is enabled, immediately treat as DESCENT
                # so we can record a flat roll test without real flight.
                if self._flat_test:
                    self._state = FlightState.DESCENT

    def set_flat_test(self, enabled: bool) -> None:
        self._flat_test = bool(enabled)

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
            # Detect landing by low net acceleration maintained for
            # landing_stable_time seconds. This replaces the previous
            # altitude-stability detector: when |net_accel| is below the
            # configured threshold for the required window, we consider the
            # vehicle landed.
            if abs(net_accel) < self._landing_accel_threshold:
                if self._stable_since is None:
                    self._stable_since = ts
                elif ts - self._stable_since >= self._landing_stable_time:
                    self._state = FlightState.LANDED
            else:
                self._stable_since = None

        self._last_altitude = alt
