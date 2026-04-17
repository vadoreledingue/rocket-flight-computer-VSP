import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


class FlightDB:
    def __init__(self, db_path: str = "/opt/rocket/data/rocket.db") -> None:
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        schema = SCHEMA_PATH.read_text()
        self.conn.executescript(schema)

    def close(self) -> None:
        self.conn.close()

    def insert_reading(self, flight_id: Optional[int], timestamp: float,
                       pressure: float, temperature: float, humidity: float,
                       altitude: float, vspeed: float,
                       roll: float, pitch: float, yaw: float,
                       accel_x: float, accel_y: float, accel_z: float,
                       battery_pct: float, battery_v: float,
                       state: str) -> None:
        self.conn.execute(
            """INSERT INTO readings (flight_id, timestamp, pressure, temperature,
               humidity, altitude, vspeed, roll, pitch, yaw,
               accel_x, accel_y, accel_z, battery_pct, battery_v, state)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (flight_id, timestamp, pressure, temperature, humidity,
             altitude, vspeed, roll, pitch, yaw,
             accel_x, accel_y, accel_z, battery_pct, battery_v, state),
        )
        self.conn.commit()

    def get_latest_readings(self, count: int = 1) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (count,)
        )
        return [dict(row) for row in cur.fetchall()]

    def get_readings_since(self, since_timestamp: float) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM readings WHERE timestamp >= ? ORDER BY timestamp ASC",
            (since_timestamp,),
        )
        return [dict(row) for row in cur.fetchall()]

    def create_flight(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO flights (started_at, state) VALUES (?, 'ACTIVE')", (now,),
        )
        self.conn.commit()
        return cur.lastrowid

    def end_flight(self, flight_id: int, max_altitude: float,
                   max_vspeed: float, duration: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """UPDATE flights SET ended_at=?, max_altitude=?, max_vspeed=?,
               duration=?, state='COMPLETED' WHERE id=?""",
            (now, max_altitude, max_vspeed, duration, flight_id),
        )
        self.conn.commit()

    def get_flights(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM flights ORDER BY id DESC")
        return [dict(row) for row in cur.fetchall()]

    def set_config(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?""",
            (key, value, now, value, now),
        )
        self.conn.commit()

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        cur = self.conn.execute("SELECT value FROM config WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def get_all_config(self) -> dict[str, str]:
        cur = self.conn.execute("SELECT key, value FROM config")
        return {row["key"]: row["value"] for row in cur.fetchall()}

    # -- Battery tests --

    def start_battery_test(self, timestamp: float) -> int:
        cur = self.conn.execute(
            "INSERT INTO battery_tests (started_at, state) VALUES (?, 'RUNNING')",
            (timestamp,),
        )
        self.conn.commit()
        return cur.lastrowid

    def stop_battery_test(self, test_id: int, timestamp: float) -> None:
        self.conn.execute(
            "UPDATE battery_tests SET ended_at=?, state='COMPLETED' WHERE id=?",
            (timestamp, test_id),
        )
        self.conn.commit()

    def set_battery_test_low(self, test_id: int, timestamp: float) -> None:
        self.conn.execute(
            "UPDATE battery_tests SET low_at=? WHERE id=? AND low_at IS NULL",
            (timestamp, test_id),
        )
        self.conn.commit()

    def get_active_battery_test(self) -> Optional[dict]:
        cur = self.conn.execute(
            "SELECT * FROM battery_tests WHERE state='RUNNING' ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_battery_tests(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM battery_tests ORDER BY id DESC"
        )
        return [dict(row) for row in cur.fetchall()]

    def delete_completed_battery_tests(self) -> int:
        cur = self.conn.execute(
            "DELETE FROM battery_tests WHERE state='COMPLETED'"
        )
        self.conn.commit()
        return cur.rowcount
