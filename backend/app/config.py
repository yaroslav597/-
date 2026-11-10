import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    endpoint: str = 'udpin:127.0.0.1:14550'
    baud: int = 115200
    system_id: int = 1
    component_id: int = 1
    source_system: int = 255
    source_component: int = 190
    heartbeat_timeout: float = 5.0
    response_timeout: float = 1.5
    max_retries: int = 5
    home_tolerance: float = 20.0
    database: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1] / 'data' / 'bridge.sqlite3')
    # Vite tries the next port when another development server is already running.
    origins: tuple[str, ...] = tuple(
        f'http://{host}:{port}'
        for host in ('127.0.0.1', 'localhost')
        for port in (*range(5173, 5184), *range(4173, 4184))
    )

    @classmethod
    def from_env(cls):
        base = cls()
        return cls(
            endpoint=os.getenv('MAVLINK_ENDPOINT', base.endpoint),
            baud=int(os.getenv('MAVLINK_BAUD', base.baud)),
            system_id=int(os.getenv('MAVLINK_SYSTEM_ID', base.system_id)),
            component_id=int(os.getenv('MAVLINK_COMPONENT_ID', base.component_id)),
            database=Path(os.getenv('BRIDGE_DATABASE', str(base.database))),
            origins=tuple(os.getenv('BRIDGE_ORIGINS', ','.join(base.origins)).split(',')),
        )
