import os
import tempfile
import pytest
from flight.database import FlightDB
from flight.config import ConfigManager, DEFAULTS


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = FlightDB(path)
    yield database
    database.close()
    os.unlink(path)


def test_defaults_loaded_on_init(db: FlightDB):
    cfg = ConfigManager(db)
    assert cfg.get("sample_rate_flight") == 20


def test_get_returns_typed_value(db: FlightDB):
    cfg = ConfigManager(db)
    assert isinstance(cfg.get("sample_rate_idle"), int)
    assert isinstance(cfg.get("landing_stable_time"), int)


def test_set_and_get(db: FlightDB):
    cfg = ConfigManager(db)
    cfg.set("sample_rate_idle", 5)
    assert cfg.get("sample_rate_idle") == 5


def test_reload_picks_up_db_changes(db: FlightDB):
    cfg = ConfigManager(db)
    db.set_config("sample_rate_idle", "5")
    cfg.reload()
    assert cfg.get("sample_rate_idle") == 5


def test_all_returns_dict(db: FlightDB):
    cfg = ConfigManager(db)
    all_cfg = cfg.all()
    assert "sample_rate_idle" in all_cfg
