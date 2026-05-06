import time
import signal
import sys
from typing import Optional
from flight.database import FlightDB
from flight.config import ConfigManager
from flight.state_machine import FlightState, StateMachine
from flight.altitude import AltitudeCalculator
from flight.logger import FlightLogger
from flight.camera import CameraStreamer


class FlightController:
    def __init__(self, db_path: str = "/opt/rocket/db/rocket.db",
                 bmp280_sensor=None, mpu6050_sensor=None, power_sensor=None) -> None:
        self.db = FlightDB(db_path)
        self.config = ConfigManager(self.db)
        self.state_machine = StateMachine(
            apogee_samples=self.config.get("apogee_samples"),
            landing_stable_time=self.config.get("landing_stable_time"),
        )
        self.altitude_calc = AltitudeCalculator()
        self.logger = FlightLogger(self.db)
        self.camera = CameraStreamer()
        self._bmp280 = bmp280_sensor
        self._mpu6050 = mpu6050_sensor
        self._pwr = power_sensor
        self._running = False
        self._last_config_check = 0.0
        self._flight_start_time: Optional[float] = None
        self._max_vspeed: float = 0.0
        self._previous_state: Optional[FlightState] = None

    def _init_sensors(self) -> None:
        if self._bmp280 is None:
            from flight.sensors.bmp280 import BMP280Sensor
            self._bmp280 = BMP280Sensor()
        if self._mpu6050 is None:
            from flight.sensors.mpu6050 import MPU6050Sensor
            try:
                self._mpu6050 = MPU6050Sensor()
            except Exception:
                self._mpu6050 = None
        if self._pwr is None:
            from flight.sensors.power import PowerSensor
            self._pwr = PowerSensor()

    def tick(self) -> None:
        now = time.time()
        bmp280_data = self._bmp280.read() if self._bmp280 else None
        mpu6050_data = self._mpu6050.read() if self._mpu6050 else None
        pwr_data = self._pwr.read() if self._pwr else None

        data: dict = {
            "pressure": 0.0, "temperature": 0.0,
            "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 0.0,
            "battery_v": 0.0, "battery_pct": 0.0,
        }
        if bmp280_data:
            data.update(bmp280_data)
        if mpu6050_data:
            data.update(mpu6050_data)
        if pwr_data:
            data.update(pwr_data)

        self.altitude_calc.update(data["pressure"], data["temperature"], now)
        data["altitude"] = self.altitude_calc.altitude
        data["vspeed"] = self.altitude_calc.vspeed
        self._max_vspeed = max(self._max_vspeed, abs(data["vspeed"]))

        state = self.state_machine.state
        if state not in (FlightState.IDLE,):
            reading = {"altitude": data["altitude"], "vspeed": data["vspeed"],
                       "accel_z": data["accel_z"], "timestamp": now}
            self.state_machine.update(reading)

        current_state = self.state_machine.state

        if current_state == FlightState.ARMED and self.logger.flight_id is None:
            self.logger.start_flight()
            self.altitude_calc.set_baseline(
                data["pressure"], data["temperature"])
            self._flight_start_time = now
            self._max_vspeed = 0.0

        if current_state == FlightState.LANDED and self.logger.flight_id is not None:
            duration = now - (self._flight_start_time or now)
            self.logger.end_flight(max_altitude=self.state_machine.max_altitude,
                                   max_vspeed=self._max_vspeed, duration=duration)

        self.logger.log(data, state=current_state.value, timestamp=now)

        # Handle camera state transitions
        if self._previous_state != current_state:
            print(f"[STATE] {self._previous_state} → {current_state}")
            if current_state == FlightState.ARMED:
                flight_id = self.logger.flight_id or f"{int(now)}"
                print(f"[CAMERA] Starting camera (flight_id={flight_id})")
                self.camera.start(flight_id)
            elif current_state == FlightState.LANDED:
                print(f"[CAMERA] Stopping camera")
                self.camera.stop()
            self._previous_state = current_state

        if now - self._last_config_check >= 1.0:
            self.config.reload()
            self._last_config_check = now

            # Check for arm/disarm commands from dashboard
            if self.config.get("arm_requested"):
                print("[DASHBOARD] ARM requested")
                self.state_machine.arm()
                self.config.set("arm_requested", False)

            if self.config.get("disarm_requested"):
                print("[DASHBOARD] DISARM requested")
                self.state_machine.disarm()
                self.config.set("disarm_requested", False)

            # Check for calibration request from dashboard
            if self.config.get("calibrate_requested"):
                self.altitude_calc.set_baseline(
                    data["pressure"], data["temperature"])
                self.config.set("calibrate_requested", False)

            # Track battery LOW for active battery test
            if pwr_data and pwr_data.get("battery_low"):
                bat_test = self.db.get_active_battery_test()
                if bat_test and bat_test["low_at"] is None:
                    self.db.set_battery_test_low(bat_test["id"], now)

    def get_sample_rate(self) -> float:
        state = self.state_machine.state
        if state in (FlightState.ASCENT, FlightState.APOGEE, FlightState.DESCENT):
            return self.config.get("sample_rate_flight")
        return self.config.get("sample_rate_idle")

    def run(self) -> None:
        self._init_sensors()
        self._running = True

        def stop(sig, frame):
            self._running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        while self._running:
            try:
                self.tick()
            except Exception as e:
                print(f"Tick error: {e}", file=sys.stderr)
            rate = self.get_sample_rate()
            time.sleep(1.0 / rate)
        self.camera.stop()
        self.db.close()


def main() -> None:
    controller = FlightController()
    controller.run()


if __name__ == "__main__":
    main()
