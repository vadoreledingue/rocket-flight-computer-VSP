import json
from typing import Any
from flight.database import FlightDB

DEFAULTS: dict[str, Any] = {
    "sample_rate_idle": 1,
    "sample_rate_flight": 20,
    "apogee_samples": 5,
    "landing_stable_time": 10,
}


class ConfigManager:
    """Live configuration store backed by SQLite.

    Provides caching layer for fast reads during tight flight loop.
    Reloaded from database every 1 second to pick up dashboard changes.
    All values stored as JSON strings in DB, cached as Python objects.

    Configuration is mutable at runtime without restarting flight controller.
    Default values are initialized once on first startup.
    """
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
