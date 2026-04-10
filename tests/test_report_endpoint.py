"""Tests for the PDF report download endpoint."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Create a test client with routes patched to use tmp dirs."""
    from engine_simulator.gui.routes_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    import shutil
    sweep_src = os.path.join(
        os.path.dirname(__file__), "..", "sweeps",
        "2026-04-10T03-47-56_2500-15000_step1000_12cyc.json",
    )
    shutil.copy(sweep_src, tmp_path / "2026-04-10T03-47-56_2500-15000_step1000_12cyc.json")

    with patch("engine_simulator.gui.routes_api.get_sweeps_dir", return_value=str(tmp_path)):
        yield TestClient(app)


def test_report_endpoint_returns_pdf(client):
    resp = client.get("/api/sweeps/2026-04-10T03-47-56_2500-15000_step1000_12cyc/report")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


def test_report_endpoint_404_for_missing_sweep(client):
    resp = client.get("/api/sweeps/nonexistent-sweep/report")
    assert resp.status_code == 404
