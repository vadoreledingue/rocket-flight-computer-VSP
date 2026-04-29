from flask import Flask
from dashboard.api import create_api_blueprint
from flight.database import FlightDB
from flight.config import ConfigManager
from flight.state_machine import StateMachine
import os
from pathlib import Path


def create_app(db_path: str | None = None) -> Flask:
    """Create Flask app. Use `ROCKET_DB` env var or local `db/rocket.db` by default."""
    if db_path is None:
        db_path = os.environ.get(
            "ROCKET_DB",
            str(Path(__file__).resolve().parents[1] / "db" / "rocket.db"),
        )
    # Ensure parent directory exists so sqlite can create the file
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__, static_folder="static", template_folder="templates")
    db = FlightDB(db_path)
    config = ConfigManager(db)
    state_machine = StateMachine()
    app.config["db"] = db
    app.config["config_manager"] = config
    app.config["state_machine"] = state_machine
    api_bp = create_api_blueprint()
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("dashboard.html")

    return app


def main() -> None:
    app = create_app()
    app.run(host="0.0.0.0", port=8080, debug=False)


if __name__ == "__main__":
    main()
