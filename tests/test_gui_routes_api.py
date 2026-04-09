"""REST endpoint integration tests for the GUI server.

Uses FastAPI's TestClient. No real solver, no real browser.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from engine_simulator.gui.server import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestConfigsEndpoint:
    def test_list_configs_returns_cbr600rr(self, client):
        response = client.get("/api/configs")
        assert response.status_code == 200
        configs = response.json()
        assert any(c["name"] == "cbr600rr.json" for c in configs)

    def test_get_config_returns_json(self, client):
        response = client.get("/api/configs/cbr600rr.json")
        assert response.status_code == 200
        data = response.json()
        # Should have at least the n_cylinders and cylinder fields
        assert "n_cylinders" in data or "cylinder" in data

    def test_get_config_not_found(self, client):
        response = client.get("/api/configs/nonexistent.json")
        assert response.status_code == 404


class TestSweepsListEndpoint:
    def test_empty_sweeps_returns_empty_list(self, client, monkeypatch, tmp_path):
        from engine_simulator.gui import routes_api as ra
        monkeypatch.setattr(ra, "get_sweeps_dir", lambda: str(tmp_path))
        response = client.get("/api/sweeps")
        assert response.status_code == 200
        assert response.json() == []


class TestSweepStartStop:
    def test_start_sweep_with_invalid_body_returns_422(self, client):
        # Missing required fields
        response = client.post("/api/sweep/start", json={})
        assert response.status_code == 422

    def test_stop_sweep_when_idle_returns_200(self, client):
        response = client.post("/api/sweep/stop")
        assert response.status_code == 200

    def test_start_sweep_validation_rejects_negative_rpm(self, client):
        response = client.post("/api/sweep/start", json={
            "rpm_start": -1, "rpm_end": 8000, "rpm_step": 1000,
            "n_cycles": 4, "n_workers": 1, "config_name": "cbr600rr.json",
        })
        assert response.status_code == 422

    def test_start_sweep_validation_rejects_zero_workers(self, client):
        response = client.post("/api/sweep/start", json={
            "rpm_start": 8000, "rpm_end": 8000, "rpm_step": 1000,
            "n_cycles": 4, "n_workers": 0, "config_name": "cbr600rr.json",
        })
        assert response.status_code == 422
