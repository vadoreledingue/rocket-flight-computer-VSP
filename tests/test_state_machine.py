import pytest
from flight.state_machine import FlightState, StateMachine


def make_reading(altitude: float = 0.0, vspeed: float = 0.0,
                 accel_z: float = 9.81, timestamp: float = 0.0) -> dict:
    return {"altitude": altitude, "vspeed": vspeed, "accel_z": accel_z, "timestamp": timestamp}


class TestStateMachine:
    def test_initial_state_is_idle(self):
        sm = StateMachine()
        assert sm.state == FlightState.IDLE

    def test_arm_transitions_to_armed(self):
        sm = StateMachine()
        sm.arm()
        assert sm.state == FlightState.ARMED

    def test_disarm_transitions_to_idle(self):
        sm = StateMachine()
        sm.arm()
        sm.disarm()
        assert sm.state == FlightState.IDLE

    def test_cannot_arm_from_ascent(self):
        sm = StateMachine()
        sm.arm()
        sm._state = FlightState.ASCENT
        sm.arm()
        assert sm.state == FlightState.ASCENT

    def test_ascent_detected_on_altitude_increase(self):
        sm = StateMachine()
        sm.arm()
        sm.update(make_reading(altitude=5.0, vspeed=20.0,
                  accel_z=30.0, timestamp=1.0))
        assert sm.state == FlightState.ASCENT

    def test_apogee_detected_after_n_falling_samples(self):
        sm = StateMachine(apogee_samples=3)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        assert sm.state == FlightState.ASCENT
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=48.0, vspeed=-1.0, timestamp=3.0))
        sm.update(make_reading(altitude=47.0, vspeed=-1.0, timestamp=4.0))
        assert sm.state == FlightState.APOGEE

    def test_apogee_detected_without_deploy_thresholds(self):
        sm = StateMachine(apogee_samples=2)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=48.0, vspeed=-1.0, timestamp=3.0))
        assert sm.state == FlightState.APOGEE

    def test_descent_after_apogee(self):
        sm = StateMachine(apogee_samples=1)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        assert sm.state == FlightState.APOGEE
        sm.update(make_reading(altitude=40.0, vspeed=-5.0, timestamp=3.0))
        assert sm.state == FlightState.DESCENT

    def test_landed_after_stable_altitude(self):
        sm = StateMachine(apogee_samples=1, landing_stable_time=2)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=40.0, vspeed=-5.0, timestamp=3.0))
        sm.update(make_reading(altitude=1.0, vspeed=0.0, timestamp=10.0))
        sm.update(make_reading(altitude=1.0, vspeed=0.0, timestamp=13.0))
        assert sm.state == FlightState.LANDED
