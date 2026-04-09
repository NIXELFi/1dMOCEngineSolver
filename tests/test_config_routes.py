"""REST endpoint tests for config save/save-as.

Uses FastAPI's TestClient. monkeypatch get_configs_dir() to a tmp_path
so the real cbr600rr.json is never touched.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REAL_CBR = (
    Path(__file__).resolve().parents[1]
    / "engine_simulator"
    / "config"
    / "cbr600rr.json"
)


@pytest.fixture
def configs_dir(tmp_path, monkeypatch):
    """Isolated configs directory seeded with a copy of cbr600rr.json."""
    shutil.copy(REAL_CBR, tmp_path / "cbr600rr.json")
    from engine_simulator.gui import routes_api
    monkeypatch.setattr(routes_api, "get_configs_dir", lambda: str(tmp_path))
    return tmp_path


@pytest.fixture
def client(configs_dir):
    from engine_simulator.gui.server import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


def _valid_payload(configs_dir):
    with open(configs_dir / "cbr600rr.json") as f:
        return json.load(f)


class TestSaveInPlace:
    def test_put_with_valid_payload_writes_file(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["intake_valve"]["open_angle"] = 339.5
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 200
        # Re-read from disk and check the change persisted
        with open(configs_dir / "cbr600rr.json") as f:
            on_disk = json.load(f)
        assert on_disk["intake_valve"]["open_angle"] == 339.5

    def test_put_to_nonexistent_returns_404(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        response = client.put("/api/configs/missing.json", json=payload)
        assert response.status_code == 404

    def test_put_with_negative_bore_returns_422(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["cylinder"]["bore"] = -1
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 422
        details = response.json()["detail"]
        # Pydantic 422 detail is a list of {loc, msg, type, ...}
        assert any("bore" in entry["loc"] for entry in details)

    def test_put_with_compression_ratio_below_one_returns_422(
        self, client, configs_dir
    ):
        payload = _valid_payload(configs_dir)
        payload["cylinder"]["compression_ratio"] = 0.5
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 422

    def test_put_with_dc_above_one_returns_422(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["restrictor"]["discharge_coefficient"] = 1.5
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 422

    def test_put_with_close_before_open_returns_422(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["intake_valve"]["close_angle"] = (
            payload["intake_valve"]["open_angle"] - 1
        )
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 422


class TestSaveAs:
    def test_post_creates_new_file(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "tweaked.json", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 200
        assert (configs_dir / "tweaked.json").exists()

    def test_post_lists_via_get_configs(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "tweaked.json", "payload": payload}
        client.post("/api/configs", json=body)
        listing = client.get("/api/configs").json()
        names = [c["name"] for c in listing]
        assert "tweaked.json" in names

    def test_post_rejects_existing_name(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "cbr600rr.json", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 409

    def test_post_with_invalid_payload_returns_422(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["cylinder"]["bore"] = -1
        body = {"name": "broken.json", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 422
        # And the file must NOT have been written
        assert not (configs_dir / "broken.json").exists()
