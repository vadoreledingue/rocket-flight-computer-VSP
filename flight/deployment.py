import time
import threading

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    GPIO = None


class DeploymentController:
    def __init__(self, pin: int = 17) -> None:
        self._pin = pin
        self._fired = False
        if GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    def fire(self, duration: float = 1.0) -> None:
        if self._fired or not GPIO:
            return
        self._fired = True
        GPIO.output(self._pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(self._pin, GPIO.LOW)

    def fire_async(self, duration: float = 1.0) -> None:
        thread = threading.Thread(target=self.fire, args=(duration,), daemon=True)
        thread.start()

    @property
    def has_fired(self) -> bool:
        return self._fired

    def reset(self) -> None:
        self._fired = False

    def cleanup(self) -> None:
        if GPIO:
            GPIO.cleanup(self._pin)
