import time
from flask import Blueprint, request, jsonify, current_app


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
        sm = current_app.config["state_machine"]
        sm.arm()
        return jsonify({"state": sm.state.value})

    @bp.route("/api/disarm", methods=["POST"])
    def disarm():
        sm = current_app.config["state_machine"]
        sm.disarm()
        return jsonify({"state": sm.state.value})

    @bp.route("/api/calibrate", methods=["POST"])
    def calibrate():
        cfg = current_app.config["config_manager"]
        cfg.set("calibrate_requested", True)
        return jsonify({"status": "calibration requested"})

    @bp.route("/api/flights")
    def flights():
        db = current_app.config["db"]
        return jsonify(db.get_flights())

    return bp
