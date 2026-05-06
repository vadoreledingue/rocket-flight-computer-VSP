import subprocess
import time
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app, Response
from flight.camera import DEFAULT_FRAME_FILE


def create_api_blueprint() -> Blueprint:
    bp = Blueprint("api", __name__)

    @bp.route("/api/status")
    def status():
        db = current_app.config["db"]
        rows = db.get_latest_readings(count=1)
        if rows:
            return jsonify(rows[0])
        return jsonify({"state": "IDLE"})

    @bp.route("/api/history")
    def history():
        db = current_app.config["db"]
        seconds = request.args.get("seconds", 60, type=int)
        since = time.time() - seconds
        rows = db.get_readings_since(since)
        return jsonify(rows)

    @bp.route("/api/config", methods=["GET"])
    def get_config():
        cfg = current_app.config["config_manager"]
        return jsonify(cfg.all())

    @bp.route("/api/config", methods=["POST"])
    def set_config():
        cfg = current_app.config["config_manager"]
        data = request.get_json()
        for key, value in data.items():
            cfg.set(key, value)
        return jsonify(cfg.all())

    @bp.route("/api/arm", methods=["POST"])
    def arm():
        try:
            cfg = current_app.config["config_manager"]
            cfg.set("arm_requested", "true")
            return jsonify({"status": "ok"})
        except Exception as e:
            print(f"[ARM] Error: {e}")
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/disarm", methods=["POST"])
    def disarm():
        try:
            cfg = current_app.config["config_manager"]
            cfg.set("disarm_requested", "true")
            return jsonify({"status": "ok"})
        except Exception as e:
            print(f"[DISARM] Error: {e}")
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/calibrate", methods=["POST"])
    def calibrate():
        cfg = current_app.config["config_manager"]
        cfg.set("calibrate_requested", True)
        return jsonify({"status": "calibration requested"})

    @bp.route("/api/flights")
    def flights():
        db = current_app.config["db"]
        return jsonify(db.get_flights())

    @bp.route("/api/battery-test", methods=["GET"])
    def battery_test_status():
        db = current_app.config["db"]
        test = db.get_active_battery_test()
        if test:
            test["elapsed"] = time.time() - test["started_at"]
        return jsonify(test)

    @bp.route("/api/battery-test/start", methods=["POST"])
    def battery_test_start():
        db = current_app.config["db"]
        existing = db.get_active_battery_test()
        if existing:
            return jsonify({"error": "Test already running", "id": existing["id"]}), 409
        test_id = db.start_battery_test(time.time())
        return jsonify({"id": test_id, "state": "RUNNING"})

    @bp.route("/api/battery-test/stop", methods=["POST"])
    def battery_test_stop():
        db = current_app.config["db"]
        test = db.get_active_battery_test()
        if not test:
            return jsonify({"error": "No test running"}), 404
        db.stop_battery_test(test["id"], time.time())
        return jsonify({"id": test["id"], "state": "COMPLETED"})

    @bp.route("/api/battery-tests")
    def battery_test_history():
        db = current_app.config["db"]
        return jsonify(db.get_battery_tests())

    @bp.route("/api/battery-tests/clear", methods=["POST"])
    def battery_test_clear():
        db = current_app.config["db"]
        deleted = db.delete_completed_battery_tests()
        return jsonify({"deleted": deleted})

    @bp.route("/api/hardware")
    def hardware_status():
        pins = [
            {"pin": 2, "gpio": "5V", "label": "PowerBoost 5V", "type": "power"},
            {"pin": 3, "gpio": "SDA", "label": "I2C Data", "type": "i2c"},
            {"pin": 5, "gpio": "SCL", "label": "I2C Clock", "type": "i2c"},
            {"pin": 6, "gpio": "GND", "label": "PowerBoost GND", "type": "power"},
            {"pin": 7, "gpio": "GPIO4", "label": "Battery LBO", "type": "input"},
        ]
        # Scan I2C bus for connected sensors
        i2c_devices = _scan_i2c()
        sensors = [
            {"name": "BMP280", "addr": "0x77", "connected": "0x77" in i2c_devices,
             "function": "Pressure/Temperature"},
            {"name": "MPU6050", "addr": "0x68", "connected": "0x68" in i2c_devices,
             "function": "IMU (Accel + Gyro)"},
        ]
        power = _get_power_status()
        return jsonify({"pins": pins, "sensors": sensors, "power": power})

    @bp.route("/api/camera/stream")
    def camera_stream():
        """MJPEG stream from flight controller camera."""
        frame_file = Path(current_app.config.get("camera_frame_file", DEFAULT_FRAME_FILE))
        print(f"[STREAM] Client connected, waiting for frames from {frame_file}")

        def generate():
            last_frame = None
            frame_count = 0
            last_log = time.time()

            while True:
                try:
                    if frame_file.exists():
                        try:
                            frame = frame_file.read_bytes()
                        except OSError:
                            time.sleep(0.01)
                            continue

                        if frame and len(frame) > 100 and frame != last_frame:
                            last_frame = frame
                            frame_count += 1

                            if time.time() - last_log >= 3.0:
                                print(f"[STREAM] {frame_count} frames sent, latest: {len(frame)} bytes")
                                last_log = time.time()

                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n'
                                   b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
                                   + frame + b'\r\n')
                    else:
                        if frame_count == 0 and time.time() - last_log >= 3.0:
                            print(f"[STREAM] Frame file not found at {frame_file}, waiting...")
                            last_log = time.time()

                    time.sleep(0.05)

                except GeneratorExit:
                    print(f"[STREAM] Client disconnected after {frame_count} frames")
                    break
                except Exception as e:
                    print(f"[STREAM] Error: {e}")
                    break

        resp = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
        resp.headers['Cache-Control'] = 'public, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Connection'] = 'close'
        return resp

    return bp


def _scan_i2c() -> list[str]:
    """Scan I2C bus 1 and return list of detected hex addresses."""
    try:
        result = subprocess.run(
            ["i2cdetect", "-y", "1"],
            capture_output=True, text=True, timeout=5,
        )
        devices = []
        for line in result.stdout.splitlines()[1:]:
            for token in line.split()[1:]:
                if token != "--" and len(token) == 2:
                    devices.append("0x" + token)
        return devices
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _get_power_status() -> dict:
    """Read Pi supply voltage status via vcgencmd.

    Returns dict with:
      - undervoltage: bool (currently under ~4.63V)
      - throttled_hex: str (raw throttled value)
    """
    try:
        result = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=5,
        )
        # Output: "throttled=0x0" or "throttled=0x50005" etc.
        raw = result.stdout.strip()
        hex_str = raw.split("=")[-1]
        flags = int(hex_str, 16)
        return {
            "undervoltage": bool(flags & 0x1),
            "throttled_hex": hex_str,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return {"undervoltage": None, "throttled_hex": None}
