from typing import Optional, Protocol


class Sensor(Protocol):
    def read(self) -> Optional[dict]:
        ...
