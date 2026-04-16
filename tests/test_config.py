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
    assert cfg.get("deploy_pin") == 17
    assert cfg.get("sample_rate_flight") == 20

def test_get_returns_typed_value(db: FlightDB):
    cfg = ConfigManager(db)
    assert isinstance(cfg.get("deploy_duration"), float)
    assert isinstance(cfg.get("deploy_pin"), int)

def test_set_and_get(db: FlightDB):
    cfg = ConfigManager(db)
    cfg.set("deploy_pin", 27)
    assert cfg.get("deploy_pin") == 27

def test_reload_picks_up_db_changes(db: FlightDB):
    cfg = ConfigManager(db)
    db.set_config("deploy_pin", "27")
    cfg.reload()
    assert cfg.get("deploy_pin") == 27

def test_all_returns_dict(db: FlightDB):
    cfg = ConfigManager(db)
    all_cfg = cfg.all()
    assert "deploy_pin" in all_cfg
    assert "sample_rate_idle" in all_cfg
