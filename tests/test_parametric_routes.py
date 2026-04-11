"""FastAPI route tests for the parametric study endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from engine_simulator.gui.server import create_app
from engine_simulator.gui import server as server_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = create_app()

    # Inject a fake parametric manager that tests can control
    fake = MagicMock()
    fake.start_study = AsyncMock(return_value="param_test")
    fake.stop_study = AsyncMock(return_value=None)
    fake.get_current = MagicMock(return_value=None)
    fake.list_studies = MagicMock(return_value=[])
    fake.load_study = MagicMock()
    fake.get_study_readonly = MagicMock()
    fake.delete_study = MagicMock()
    fake._studies_dir = str(tmp_path)

    server_module.parametric_manager = fake
    yield TestClient(app), fake
    server_module.parametric_manager = None


def test_list_parameters(client):
    tc, _ = client
    resp = tc.get("/api/parametric/parameters")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "path" in data[0]
    assert "label" in data[0]
    assert "default_range" in data[0]


def test_start_study_success(client):
    tc, fake = client
    body = {
        "name": "plenum sweep",
        "config_name": "cbr600rr.json",
        "parameter_path": "plenum.volume",
        "value_start": 0.001,
        "value_end": 0.003,
        "value_step": 0.001,
        "sweep_rpm_start": 6000,
        "sweep_rpm_end": 8000,
        "sweep_rpm_step": 1000,
        "sweep_n_cycles": 2,
        "n_workers": 1,
    }
    resp = tc.post("/api/parametric/study/start", json=body)
    assert resp.status_code == 200
    assert resp.json()["study_id"] == "param_test"
    fake.start_study.assert_called_once()


def test_start_study_rejects_unknown_parameter(client):
    tc, _ = client
    body = {
        "name": "bad sweep",
        "config_name": "cbr600rr.json",
        "parameter_path": "cylinder.bore",
        "value_start": 0.06,
        "value_end": 0.08,
        "value_step": 0.005,
        "sweep_rpm_start": 6000,
        "sweep_rpm_end": 8000,
        "sweep_rpm_step": 1000,
        "sweep_n_cycles": 2,
        "n_workers": 1,
    }
    resp = tc.post("/api/parametric/study/start", json=body)
    assert resp.status_code == 422


def test_stop_study(client):
    tc, fake = client
    resp = tc.post("/api/parametric/study/stop")
    assert resp.status_code == 200
    fake.stop_study.assert_awaited_once()


def test_list_studies_empty(client):
    tc, _ = client
    resp = tc.get("/api/parametric/studies")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_study_not_found(client):
    tc, fake = client
    fake.get_study_readonly.side_effect = FileNotFoundError("nope")
    resp = tc.get("/api/parametric/studies/missing")
    assert resp.status_code == 404


def test_delete_study_not_found(client):
    tc, fake = client
    fake.delete_study.side_effect = FileNotFoundError("nope")
    resp = tc.delete("/api/parametric/studies/missing")
    assert resp.status_code == 404


def test_delete_running_study_is_rejected(client):
    tc, fake = client
    fake.delete_study.side_effect = RuntimeError("cannot delete running study")
    resp = tc.delete("/api/parametric/studies/param_running")
    assert resp.status_code == 409
