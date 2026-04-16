import pytest
from unittest.mock import MagicMock, patch, call
from flight.deployment import DeploymentController

@pytest.fixture
def mock_gpio():
    gpio = MagicMock()
    with patch("flight.deployment.GPIO", gpio):
        yield gpio

def test_init_sets_up_gpio(mock_gpio):
    ctrl = DeploymentController(pin=17)
    mock_gpio.setmode.assert_called_once_with(mock_gpio.BCM)
    mock_gpio.setup.assert_called_once_with(17, mock_gpio.OUT, initial=mock_gpio.LOW)

def test_fire_sets_pin_high(mock_gpio):
    ctrl = DeploymentController(pin=17)
    ctrl.fire(duration=0.01)
    mock_gpio.output.assert_any_call(17, mock_gpio.HIGH)

def test_fire_sets_pin_low_after_duration(mock_gpio):
    with patch("flight.deployment.time") as mock_time:
        ctrl = DeploymentController(pin=17)
        ctrl.fire(duration=1.0)
        mock_time.sleep.assert_called_once_with(1.0)
        calls = mock_gpio.output.call_args_list
        assert calls[-1] == call(17, mock_gpio.LOW)

def test_fire_only_once(mock_gpio):
    ctrl = DeploymentController(pin=17)
    ctrl.fire(duration=0.01)
    ctrl.fire(duration=0.01)
    assert mock_gpio.output.call_count == 2  # HIGH + LOW from first fire only

def test_cleanup(mock_gpio):
    ctrl = DeploymentController(pin=17)
    ctrl.cleanup()
    mock_gpio.cleanup.assert_called_once_with(17)
