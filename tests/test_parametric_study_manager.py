"""Unit tests for ParametricStudyManager with a mocked orchestrator."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from engine_simulator.gui.parametric.study_manager import (
    ParametricStudyManager,
    ParametricStudyDef,
)


def _def(parameter_values=None):
    return ParametricStudyDef(
        study_id="param_test",
        name="test",
        config_name="cbr600rr.json",
        parameter_path="plenum.volume",
        parameter_values=parameter_values or [0.001, 0.002],
        sweep_rpm_start=6000.0,
        sweep_rpm_end=8000.0,
        sweep_rpm_step=1000.0,
        sweep_n_cycles=1,
        n_workers=1,
        created_at="2026-04-10T12:00:00Z",
    )


class _FakeOrchestrator:
    """Returns fixed perf dicts keyed by the plenum volume it was built with."""

    last_volumes_seen = []

    def __init__(self, config):
        # Record the mutated plenum volume so the test can assert the config
        # was actually changed for each iteration.
        _FakeOrchestrator.last_volumes_seen.append(config.plenum.volume)
        self._volume = config.plenum.volume
        self.results_by_rpm = {}

    def run_rpm_sweep(
        self, rpm_start, rpm_end, rpm_step, n_cycles,
        verbose=False, n_workers=None, consumer=None,
    ):
        # Emit one fake perf dict per RPM, scaling power with volume so
        # the test can tell runs apart.
        rpms = [6000.0, 7000.0, 8000.0]
        return [
            {
                "rpm": r,
                "brake_power_hp": 40.0 + r / 1000 + self._volume * 10000,
                "brake_torque_Nm": 50.0,
            }
            for r in rpms
        ]


@pytest.fixture(autouse=True)
def _reset_fake():
    _FakeOrchestrator.last_volumes_seen = []
    yield


@pytest.mark.asyncio
async def test_happy_path_runs_all_parameter_values(tmp_path):
    broadcast = MagicMock()
    loop = asyncio.get_running_loop()

    async def async_broadcast(msg):
        broadcast(msg)

    mgr = ParametricStudyManager(
        loop=loop,
        studies_dir=str(tmp_path),
        broadcast_fn=async_broadcast,
    )

    with patch(
        "engine_simulator.gui.parametric.study_manager.SimulationOrchestrator",
        _FakeOrchestrator,
    ), patch(
        "engine_simulator.gui.parametric.study_manager._load_config_dict",
        return_value=_minimal_config_dict(),
    ), patch(
        "engine_simulator.gui.parametric.study_manager._config_from_dict",
        side_effect=_fake_config_from_dict,
    ):
        study_id = await mgr.start_study(_def([0.001, 0.002]))

        # Wait for the study task to complete
        await mgr._study_task

    assert study_id == "param_test"
    # Both volumes were seen by the orchestrator (proves config mutation)
    assert _FakeOrchestrator.last_volumes_seen == [0.001, 0.002]
    current = mgr.get_current()
    assert current.status == "complete"
    assert len(current.runs) == 2
    assert all(r.status == "done" for r in current.runs)
    # Different volumes produced different power values
    assert current.runs[0].sweep_results[0]["brake_power_hp"] != \
           current.runs[1].sweep_results[0]["brake_power_hp"]
    # Persisted file exists
    assert (tmp_path / "param_test.json").exists()


@pytest.mark.asyncio
async def test_error_isolation(tmp_path):
    """If one parameter value raises, the study continues with the others."""
    calls = []

    class _FlakyOrchestrator:
        def __init__(self, config):
            calls.append(config.plenum.volume)
            self._volume = config.plenum.volume
            self.results_by_rpm = {}

        def run_rpm_sweep(self, **kwargs):
            if self._volume == 0.002:
                raise RuntimeError("boom")
            return [{"rpm": 6000.0, "brake_power_hp": 50.0, "brake_torque_Nm": 50.0}]

    broadcast = MagicMock()
    loop = asyncio.get_running_loop()

    async def async_broadcast(msg):
        broadcast(msg)

    mgr = ParametricStudyManager(
        loop=loop,
        studies_dir=str(tmp_path),
        broadcast_fn=async_broadcast,
    )

    with patch(
        "engine_simulator.gui.parametric.study_manager.SimulationOrchestrator",
        _FlakyOrchestrator,
    ), patch(
        "engine_simulator.gui.parametric.study_manager._load_config_dict",
        return_value=_minimal_config_dict(),
    ), patch(
        "engine_simulator.gui.parametric.study_manager._config_from_dict",
        side_effect=_fake_config_from_dict,
    ):
        await mgr.start_study(_def([0.001, 0.002, 0.003]))
        await mgr._study_task

    current = mgr.get_current()
    assert len(current.runs) == 3
    statuses = [r.status for r in current.runs]
    assert statuses == ["done", "error", "done"]
    assert current.runs[1].error is not None
    assert "boom" in current.runs[1].error
    # Study overall status is complete — error was isolated
    assert current.status == "complete"


@pytest.mark.asyncio
async def test_stop_study_sets_flag(tmp_path):
    broadcast = MagicMock()
    loop = asyncio.get_running_loop()

    async def async_broadcast(msg):
        broadcast(msg)

    mgr = ParametricStudyManager(
        loop=loop,
        studies_dir=str(tmp_path),
        broadcast_fn=async_broadcast,
    )
    # No study running: stop is a no-op
    await mgr.stop_study()
    assert mgr.get_current() is None


# ---------- helpers ----------

def _minimal_config_dict():
    return {
        "name": "cbr600rr",
        "n_cylinders": 4,
        "firing_order": [1, 2, 4, 3],
        "firing_interval": 180.0,
        "cylinder": {
            "bore": 0.067, "stroke": 0.0425,
            "con_rod_length": 0.0963, "compression_ratio": 12.2,
            "n_intake_valves": 2, "n_exhaust_valves": 2,
        },
        "plenum": {
            "volume": 0.0015,
            "initial_pressure": 101325.0,
            "initial_temperature": 300.0,
        },
        "intake_pipes": [],
    }


def _fake_config_from_dict(d):
    """Return a Mock-like object with attribute access matching the dict."""
    class _Cfg:
        pass
    cfg = _Cfg()
    cfg.plenum = _Cfg()
    cfg.plenum.volume = d["plenum"]["volume"]
    return cfg
