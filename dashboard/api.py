import subprocess
import time
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app, Response, send_file, url_for
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

    @bp.route("/api/reports")
    def reports():
        report_manager = current_app.config["report_manager"]
        reports = report_manager.list_reports()
        return jsonify([_serialize_report(report) for report in reports])

    @bp.route("/api/reports/<int:flight_id>")
    def report_detail(flight_id: int):
        report_manager = current_app.config["report_manager"]
        report = report_manager.get_report(flight_id, generate_missing=True)
        if report is None:
            return jsonify({"error": "Flight not found"}), 404
        return jsonify(_serialize_report(report))

    @bp.route("/api/reports/<int:flight_id>/assets/<path:filename>")
    def report_asset(flight_id: int, filename: str):
        report_manager = current_app.config["report_manager"]
        try:
            asset_path = report_manager.get_asset_path(flight_id, filename)
        except ValueError:
            return jsonify({"error": "Invalid asset path"}), 400

        if not asset_path.exists() or not asset_path.is_file():
            return jsonify({"error": "Asset not found"}), 404
        return send_file(asset_path)

    @bp.route("/api/hardware")
    def hardware_status():
        pins = [
            {"pin": 2, "gpio": "5V", "label": "PowerBoost 5V", "type": "power"},
            {"pin": 3, "gpio": "SDA", "label": "I2C Data", "type": "i2c"},
            {"pin": 5, "gpio": "SCL", "label": "I2C Clock", "type": "i2c"},
            {"pin": 6, "gpio": "GND", "label": "PowerBoost GND", "type": "power"},
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


def _serialize_report(report: dict) -> dict:
    serialized = dict(report)
    flight_id = report["flight_id"]
    serialized["detail_url"] = url_for("api.report_detail", flight_id=flight_id)
    serialized["images"] = _serialize_report_images(
        flight_id, report.get("images", []))
    serialized["smoothed_images"] = _serialize_report_images(
        flight_id, report.get("smoothed_images", []))

    video = dict(report.get("video") or {})
    filename = video.get("filename")
    if filename:
        video["url"] = url_for("api.report_asset", flight_id=flight_id, filename=filename)
    serialized["video"] = video
    return serialized


def _serialize_report_images(flight_id: int, images: list[dict]) -> list[dict]:
    return [
        {
            **image,
            "url": url_for("api.report_asset", flight_id=flight_id, filename=image["filename"]),
        }
        for image in images
    ]
