"""WebSocket protocol tests using FastAPI's TestClient WebSocket support."""

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from engine_simulator.gui.server import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestWebSocketSnapshot:
    def test_initial_snapshot_received_on_connect(self, client):
        with client.websocket_connect("/ws/events") as ws:
            data = ws.receive_json()
        assert data["type"] == "snapshot"
        assert "sweep" in data
        assert "available_sweeps" in data

    def test_snapshot_when_no_sweep_running_has_null_sweep(self, client):
        with client.websocket_connect("/ws/events") as ws:
            data = ws.receive_json()
        assert data["sweep"] is None

    def test_ping_pong_heartbeat(self, client):
        with client.websocket_connect("/ws/events") as ws:
            ws.receive_json()   # initial snapshot
            ws.send_json({"type": "ping"})
            response = ws.receive_json()
        assert response == {"type": "pong"}
