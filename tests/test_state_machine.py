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
        sm = StateMachine(min_deploy_altitude=10, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=5.0, vspeed=20.0, accel_z=30.0, timestamp=1.0))
        assert sm.state == FlightState.ASCENT

    def test_apogee_detected_after_n_falling_samples(self):
        sm = StateMachine(apogee_samples=3, min_deploy_altitude=5, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        assert sm.state == FlightState.ASCENT
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=48.0, vspeed=-1.0, timestamp=3.0))
        sm.update(make_reading(altitude=47.0, vspeed=-1.0, timestamp=4.0))
        assert sm.state == FlightState.APOGEE

    def test_no_deploy_below_min_altitude(self):
        sm = StateMachine(apogee_samples=2, min_deploy_altitude=100, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=20.0, vspeed=10.0, timestamp=1.0))
        sm.update(make_reading(altitude=19.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=18.0, vspeed=-1.0, timestamp=3.0))
        assert sm.state != FlightState.APOGEE

    def test_no_deploy_before_min_flight_time(self):
        sm = StateMachine(apogee_samples=2, min_deploy_altitude=5, min_flight_time=10)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=48.0, vspeed=-1.0, timestamp=3.0))
        assert sm.state != FlightState.APOGEE

    def test_descent_after_apogee(self):
        sm = StateMachine(apogee_samples=1, min_deploy_altitude=5, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        assert sm.state == FlightState.APOGEE
        sm.update(make_reading(altitude=40.0, vspeed=-5.0, timestamp=3.0))
        assert sm.state == FlightState.DESCENT

    def test_landed_after_stable_altitude(self):
        sm = StateMachine(apogee_samples=1, min_deploy_altitude=5,
                          min_flight_time=0, landing_stable_time=2)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        sm.update(make_reading(altitude=40.0, vspeed=-5.0, timestamp=3.0))
        sm.update(make_reading(altitude=1.0, vspeed=0.0, timestamp=10.0))
        sm.update(make_reading(altitude=1.0, vspeed=0.0, timestamp=13.0))
        assert sm.state == FlightState.LANDED

    def test_deploy_triggered_flag(self):
        sm = StateMachine(apogee_samples=1, min_deploy_altitude=5, min_flight_time=0)
        sm.arm()
        sm.update(make_reading(altitude=50.0, vspeed=20.0, timestamp=1.0))
        result = sm.update(make_reading(altitude=49.0, vspeed=-1.0, timestamp=2.0))
        assert result.deploy_triggered is True

    def test_no_deploy_in_other_states(self):
        sm = StateMachine()
        sm.arm()
        result = sm.update(make_reading(altitude=0.0, vspeed=0.0, timestamp=1.0))
        assert result.deploy_triggered is False
