import subprocess
import time
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app, Response


def create_api_blueprint() -> Blueprint:
    bp = Blueprint("api", __name__)

    @bp.route("/api/status")
    def status():
        db = current_app.config["db"]
        sm = current_app.config["state_machine"]
        rows = db.get_latest_readings(count=1)
        if rows:
            data = rows[0]
            data["state"] = sm.state.value
            return jsonify(data)
        return jsonify({"state": sm.state.value})

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
        cfg = current_app.config["config_manager"]
        cfg.set("arm_requested", "true")
        db = current_app.config["db"]
        rows = db.get_latest_readings(count=1)
        if rows:
            return jsonify({"status": "arm requested", "state": rows[0]["state"]})
        return jsonify({"status": "arm requested"})

    @bp.route("/api/disarm", methods=["POST"])
    def disarm():
        cfg = current_app.config["config_manager"]
        cfg.set("disarm_requested", "true")
        db = current_app.config["db"]
        rows = db.get_latest_readings(count=1)
        if rows:
            return jsonify({"status": "disarm requested", "state": rows[0]["state"]})
        return jsonify({"status": "disarm requested"})

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

    @bp.route("/api/camera/frame")
    def camera_frame():
        """Get current camera frame as JPEG."""
        frame_file = Path("/tmp/rocket_camera_frame.jpg")
        if frame_file.exists():
            try:
                frame_data = frame_file.read_bytes()
                if frame_data:
                    return Response(frame_data, mimetype='image/jpeg')
            except Exception as e:
                print(f"[CAMERA] Frame read error: {e}")
        return _generate_test_frame()

    def _generate_test_frame():
        """Generate a test JPEG frame for development."""
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.new('RGB', (1280, 720), color='black')
            draw = ImageDraw.Draw(img)
            draw.text((640, 360), "No camera feed", fill='cyan')
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=80)
            return Response(buffer.getvalue(), mimetype='image/jpeg')
        except Exception:
            return Response(b'', mimetype='image/jpeg', status=204)

    @bp.route("/api/camera/stream")
    def camera_stream():
        """MJPEG stream from flight controller camera."""
        frame_file = Path("/tmp/rocket_camera_frame.jpg")
        print(f"[STREAM] Starting MJPEG stream, frame_file exists: {frame_file.exists()}")

        def generate():
            last_frame = None
            frame_count = 0
            no_update_count = 0
            while True:
                try:
                    if frame_file.exists():
                        frame = frame_file.read_bytes()
                        if frame and frame != last_frame:
                            last_frame = frame
                            frame_count += 1
                            no_update_count = 0
                            if frame_count % 30 == 0:
                                print(f"[STREAM] Sent {frame_count} frames")
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n'
                                   b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
                                   + frame + b'\r\n')
                        else:
                            no_update_count += 1
                            if no_update_count >= 50:
                                print(f"[STREAM] No frame update for 5s, stream timeout")
                                break
                    else:
                        print(f"[STREAM] Frame file not found, waiting...")
                        time.sleep(0.5)
                except Exception as e:
                    print(f"[STREAM] Error: {e}")
                    break
                time.sleep(0.01)

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

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
