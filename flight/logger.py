from typing import Optional
from flight.database import FlightDB


class FlightLogger:
    def __init__(self, db: FlightDB) -> None:
        self._db = db
        self.flight_id: Optional[int] = None

    def start_flight(self) -> int:
        self.flight_id = self._db.create_flight()
        return self.flight_id

    def log(self, sensor_data: dict, state: str, timestamp: float) -> None:
        self._db.insert_reading(
            flight_id=self.flight_id,
            timestamp=timestamp,
            pressure=sensor_data.get("pressure", 0.0),
            temperature=sensor_data.get("temperature", 0.0),
            humidity=sensor_data.get("humidity", 0.0),
            altitude=sensor_data.get("altitude", 0.0),
            vspeed=sensor_data.get("vspeed", 0.0),
            roll=sensor_data.get("roll", 0.0),
            pitch=sensor_data.get("pitch", 0.0),
            yaw=sensor_data.get("yaw", 0.0),
            accel_x=sensor_data.get("accel_x", 0.0),
            accel_y=sensor_data.get("accel_y", 0.0),
            accel_z=sensor_data.get("accel_z", 0.0),
            battery_pct=sensor_data.get("battery_pct", 0.0),
            battery_v=sensor_data.get("battery_v", 0.0),
            state=state,
        )

    def end_flight(self, max_altitude: float, max_vspeed: float, duration: float) -> None:
        if self.flight_id is not None:
            self._db.end_flight(
                self.flight_id, max_altitude, max_vspeed, duration)
            self.flight_id = None
