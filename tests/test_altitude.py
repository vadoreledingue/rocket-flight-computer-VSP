import pytest
from flight.altitude import AltitudeCalculator

def test_altitude_at_baseline_is_zero():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    alt = calc.compute(1013.25, 20.0)
    assert alt == pytest.approx(0.0, abs=0.1)

def test_altitude_increases_with_lower_pressure():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    alt = calc.compute(1001.0, 18.0)
    assert alt > 50.0
    assert alt < 200.0

def test_vspeed_calculation():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    calc.update(1013.25, 20.0, timestamp=0.0)
    calc.update(1001.0, 18.0, timestamp=1.0)
    assert calc.vspeed > 50.0

def test_vspeed_zero_when_stationary():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    calc.update(1013.25, 20.0, timestamp=0.0)
    calc.update(1013.25, 20.0, timestamp=1.0)
    assert calc.vspeed == pytest.approx(0.0, abs=0.5)

def test_altitude_history():
    calc = AltitudeCalculator()
    calc.set_baseline(1013.25, 20.0)
    calc.update(1013.25, 20.0, timestamp=0.0)
    calc.update(1010.0, 19.0, timestamp=1.0)
    calc.update(1007.0, 18.0, timestamp=2.0)
    assert len(calc.history) == 3
