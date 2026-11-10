from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Config
from backend.app.main import create_app
from .fakes import FakeTransport


@pytest.fixture
def plan():
    return dict(version=3, settings=dict(speed=12, takeoff=True, takeoffAlt=80, ending='rtl', home=dict(lat=55.755, lng=37.59),
                                      landing=dict(lat=55.745, lng=37.63, alt=80)),
                waypoints=[dict(id='first', lat=55.755, lng=37.59, alt=80, delay=0, actions=[])])


@pytest.fixture
def setup(tmp_path):
    peer = FakeTransport()
    config = replace(Config(), database=tmp_path / 'test.sqlite3', response_timeout=0.1, max_retries=2, heartbeat_timeout=2)
    app = create_app(config, lambda _: peer)
    with TestClient(app) as client:
        yield client, peer, app
    assert peer.closed
