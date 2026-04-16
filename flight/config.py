import json
from typing import Any
from flight.database import FlightDB

DEFAULTS: dict[str, Any] = {
    "sample_rate_idle": 1,
    "sample_rate_flight": 20,
    "min_deploy_altitude": 30,
    "min_flight_time": 2,
    "apogee_samples": 5,
    "deploy_pin": 17,
    "deploy_duration": 1.0,
    "landing_stable_time": 10,
}


class ConfigManager:
    def __init__(self, db: FlightDB) -> None:
        self._db = db
        self._cache: dict[str, Any] = {}
        self._init_defaults()
        self.reload()

    def _init_defaults(self) -> None:
        # Write each default only when the key does not yet exist in the DB
        for key, value in DEFAULTS.items():
            existing = self._db.get_config(key)
            if existing is None:
                self._db.set_config(key, json.dumps(value))

    def reload(self) -> None:
        # Rebuild the in-memory cache from the current DB state
        raw = self._db.get_all_config()
        self._cache = {k: json.loads(v) for k, v in raw.items()}

    def get(self, key: str) -> Any:
        return self._cache.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._db.set_config(key, json.dumps(value))
        self._cache[key] = value

    def all(self) -> dict[str, Any]:
        return dict(self._cache)
