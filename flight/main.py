import time
import signal
import sys
from typing import Optional
from flight.database import FlightDB
from flight.config import ConfigManager
from flight.state_machine import FlightState, StateMachine
from flight.altitude import AltitudeCalculator
from flight.acceleration import AccelerationCalculator
from flight.logger import FlightLogger
from flight.camera import CameraStreamer
from flight.reporting import FlightReportManager


class FlightController:
    def __init__(self, db_path: str = "/opt/rocket/db/rocket.db",
                 bmp280_sensor=None, mpu6050_sensor=None) -> None:
        self.db = FlightDB(db_path)
        self.config = ConfigManager(self.db)
        self.state_machine = StateMachine(
            apogee_samples=self.config.get("apogee_samples"),
            landing_stable_time=self.config.get("landing_stable_time"),
        )
        # Initialize flat test mode from configuration
        try:
            self.state_machine.set_flat_test(self.config.get("flat_test"))
        except Exception:
            # ignore if config missing or invalid
            pass
        self.altitude_calc = AltitudeCalculator()
        self.acceleration_calc = AccelerationCalculator()
        self.logger = FlightLogger(self.db)
        self.report_manager = FlightReportManager(self.db)
        self.camera = CameraStreamer()
        self._bmp280 = bmp280_sensor
        self._mpu6050 = mpu6050_sensor
        self._running = False
        self._last_config_check = 0.0
        self._flight_start_time: Optional[float] = None
        self._max_vspeed: float = 0.0
        self._max_net_accel: float = 0.0
        self._previous_state: Optional[FlightState] = None

    def _start_armed_flight(self, now: float, data: dict) -> None:
        self.logger.start_flight()
        self.altitude_calc.recalibrate(
            data["pressure"], data["temperature"], now)
        self._flight_start_time = now
        self._max_vspeed = 0.0
        self._max_net_accel = 0.0

    def _init_sensors(self) -> None:
        if self._bmp280 is None:
            from flight.sensors.bmp280 import BMP280Sensor
            self._bmp280 = BMP280Sensor()
        if self._mpu6050 is None:
            from flight.sensors.mpu6050 import MPU6050Sensor
            try:
                self._mpu6050 = MPU6050Sensor()
                if not self._mpu6050._initialized:
                    print(
                        f"[FLIGHT] WARNING: MPU6050 failed to initialize: {self._mpu6050._init_error}", file=sys.stderr)
            except Exception as e:
                print(
                    f"[FLIGHT] ERROR: Failed to create MPU6050 instance: {e}", file=sys.stderr)
                self._mpu6050 = None

    def tick(self) -> None:
        now = time.time()
        bmp280_data = self._bmp280.read() if self._bmp280 else None
        mpu6050_data = self._mpu6050.read() if self._mpu6050 else None

        data: dict = {
            "pressure": 0.0, "temperature": 0.0,
            "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 0.0,
        }
        if bmp280_data:
            data.update(bmp280_data)
        if mpu6050_data:
            data.update(mpu6050_data)

        if self.state_machine.state == FlightState.ARMED and self.logger.flight_id is None:
            self._start_armed_flight(now, data)

        self.altitude_calc.update(data["pressure"], data["temperature"], now)
        data["altitude"] = self.altitude_calc.altitude
        data["vspeed"] = self.altitude_calc.vspeed
        self._max_vspeed = max(self._max_vspeed, abs(data["vspeed"]))

        accel_data = self.acceleration_calc.update(
            data.get("accel_x", 0.0),
            data.get("accel_y", 0.0),
            data.get("accel_z", 0.0)
        )
        data.update(accel_data)
        self._max_net_accel = max(
            self._max_net_accel, data.get("net_accel", 0.0))

        state = self.state_machine.state
        if state not in (FlightState.IDLE,):
            reading = {"altitude": data["altitude"], "vspeed": data["vspeed"],
                       "accel_z": data["accel_z"], "net_accel": data.get("net_accel", 0.0),
                       "timestamp": now}
            self.state_machine.update(reading)

        current_state = self.state_machine.state
        ended_flight_id: Optional[int] = None

        self.logger.log(data, state=current_state.value, timestamp=now)

        if current_state == FlightState.LANDED and self.logger.flight_id is not None:
            duration = now - (self._flight_start_time or now)
            ended_flight_id = self.logger.flight_id
            self.logger.end_flight(max_altitude=self.state_machine.max_altitude,
                                   max_vspeed=self._max_vspeed,
                                   max_net_accel=self._max_net_accel,
                                   duration=duration)

        if self._previous_state != current_state:
            print(f"[STATE] {self._previous_state} -> {current_state}")
            self._previous_state = current_state

        self._sync_camera_state(now, current_state)

        if ended_flight_id is not None:
            try:
                print(
                    f"[REPORT] Generating report for flight {ended_flight_id}")
                self.report_manager.generate_for_flight(ended_flight_id)
            except Exception as exc:
                print(f"[REPORT] Failed to generate report for flight {ended_flight_id}: {exc}",
                      file=sys.stderr)

        if now - self._last_config_check >= 1.0:
            self.config.reload()
            self._last_config_check = now

            # Check for arm/disarm commands from dashboard
            if self.config.get("arm_requested") == "true":
                print("[DASHBOARD] ARM requested")
                self.state_machine.arm()
                self.config.set("arm_requested", "false")

            if self.config.get("disarm_requested") == "true":
                print("[DASHBOARD] DISARM requested")
                self.state_machine.disarm()
                self.config.set("disarm_requested", "false")

            # Check for calibration request from dashboard
            if self.config.get("calibrate_requested"):
                self.altitude_calc.recalibrate(
                    data["pressure"], data["temperature"], now)
                self.config.set("calibrate_requested", False)
            # Sync flat test mode if changed in config
            try:
                desired_flat = bool(self.config.get("flat_test"))
            except Exception:
                desired_flat = False
            self.state_machine.set_flat_test(desired_flat)

    def _sync_camera_state(self, now: float, current_state: FlightState) -> None:
        active_camera_states = {
            FlightState.ARMED,
            FlightState.ASCENT,
            FlightState.APOGEE,
            FlightState.DESCENT,
        }
        should_run = current_state in active_camera_states

        if should_run and not self.camera.is_running:
            flight_id = str(self.logger.flight_id or int(now))
            print(f"[CAMERA] Starting camera (flight_id={flight_id})")
            self.camera.start(flight_id)
        elif not should_run and self.camera.is_running:
            print("[CAMERA] Stopping camera")
            self.camera.stop()

    def get_sample_rate(self) -> float:
        state = self.state_machine.state
        if state in (FlightState.ASCENT, FlightState.APOGEE, FlightState.DESCENT):
            return self.config.get("sample_rate_flight")
        return self.config.get("sample_rate_idle")

    def run(self) -> None:
        self._init_sensors()
        print(
            f"[FLIGHT] Sensors initialized: BMP280={self._bmp280 is not None}, MPU6050={self._mpu6050 is not None and self._mpu6050._initialized}", file=sys.stderr)
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
