"""Tests for orientation calculation module."""

import pytest
import math
from flight.orientation import compute_pitch_roll


def test_pitch_roll_at_rest_level():
    """When accelerometer only measures gravity (rocket level), pitch and roll should be near zero."""
    pitch, roll = compute_pitch_roll(0.0, 0.0, 9.81)
    assert pitch == pytest.approx(0.0, abs=0.1)
    assert roll == pytest.approx(0.0, abs=0.1)


def test_pitch_45_degrees():
    """When tilted forward 45 degrees, pitch should be ±45."""
    accel_magnitude = 9.81
    forward_accel = accel_magnitude * math.sin(math.radians(45))
    vertical_accel = accel_magnitude * math.cos(math.radians(45))
    pitch, roll = compute_pitch_roll(forward_accel, 0.0, vertical_accel)
    assert pitch == pytest.approx(45.0, abs=1.0)
    assert roll == pytest.approx(0.0, abs=0.5)


def test_roll_45_degrees():
    """When tilted right 45 degrees, roll should be ±45."""
    accel_magnitude = 9.81
    right_accel = accel_magnitude * math.sin(math.radians(45))
    vertical_accel = accel_magnitude * math.cos(math.radians(45))
    pitch, roll = compute_pitch_roll(0.0, right_accel, vertical_accel)
    assert pitch == pytest.approx(0.0, abs=0.5)
    assert roll == pytest.approx(45.0, abs=1.0)


def test_pitch_90_degrees_nose_down():
    """When vertical acceleration dominates forward, pitch should approach 90."""
    pitch, roll = compute_pitch_roll(9.81, 0.0, 0.1)
    assert pitch > 80.0


def test_roll_90_degrees_right_wing_down():
    """When vertical acceleration dominates right, roll should approach 90."""
    pitch, roll = compute_pitch_roll(0.0, 9.81, 0.1)
    assert roll > 80.0


def test_combined_pitch_roll():
    """Combined pitch and roll rotations should compute independently."""
    accel_x = 7.0
    accel_y = 7.0
    accel_z = 5.0
    pitch, roll = compute_pitch_roll(accel_x, accel_y, accel_z)
    assert pitch > 0.0
    assert roll > 0.0
    assert pitch < 90.0
    assert roll < 90.0


def test_negative_pitch():
    """Negative forward acceleration gives negative pitch (nose up)."""
    pitch, roll = compute_pitch_roll(-7.0, 0.0, 7.0)
    assert pitch < 0.0


def test_negative_roll():
    """Negative right acceleration gives negative roll (left wing down)."""
    pitch, roll = compute_pitch_roll(0.0, -7.0, 7.0)
    assert roll < 0.0


def test_symmetry():
    """Positive and negative accelerations should give opposite angle signs."""
    pitch_pos, roll_pos = compute_pitch_roll(5.0, 5.0, 9.81)
    pitch_neg, roll_neg = compute_pitch_roll(-5.0, -5.0, 9.81)
    assert pitch_pos == pytest.approx(-pitch_neg, abs=0.1)
    assert roll_pos == pytest.approx(-roll_neg, abs=0.1)
