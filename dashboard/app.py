from flask import Flask
from dashboard.api import create_api_blueprint
from flight.database import FlightDB
from flight.config import ConfigManager
from flight.state_machine import StateMachine


def create_app(db_path: str = "/opt/rocket/data/rocket.db") -> Flask:
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
