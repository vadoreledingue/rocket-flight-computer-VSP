from typing import Optional

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    GPIO = None


class PowerSensor:
    """Reads battery status from PowerBoost 1000C via LBO (Low Battery Output) pin.

    Hardware specs:
    - Input: 3.7V LiPo (nominal 3.0–4.2V)
    - Output: 5V USB regulated, up to 1A continuous
    - LBO pin: Active LOW when battery voltage < ~3.2V threshold
    - Provides binary low-battery indication only (no ADC voltage reading)

    Current implementation:
    - battery_v: Returns 3.8V (normal) or 3.2V (low)
    - battery_pct: Returns 80% (normal) or 10% (low)
    - battery_low: Boolean from GPIO pin state

    Limitations:
    - No precise voltage measurement (would require ADC)
    - Percentage is a crude estimate based on LBO threshold
    - Does not account for load variation or cell chemistry
    """

    def __init__(self, lbo_pin: int = 4) -> None:
        self._lbo_pin = lbo_pin
        if GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(lbo_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def _is_low_battery(self) -> bool:
        if not GPIO:
            return False
        return GPIO.input(self._lbo_pin) == GPIO.LOW

    def read(self) -> Optional[dict]:
        try:
            low = self._is_low_battery()
            # PowerBoost 1000 estimates based on LBO threshold (3.2V)
            # Full LiPo: ~4.2V, Empty: ~3.0V
            return {
                "battery_v": 3.2 if low else 3.8,
                "battery_pct": 10.0 if low else 80.0,
                "battery_low": low,
            }
        except (OSError, ValueError):
            return None

    def cleanup(self) -> None:
        if GPIO:
            GPIO.cleanup(self._lbo_pin)
