"""End-to-end parametric study test with the real orchestrator.

Runs a minimal study (2 parameter values, 2 RPM points, 1 cycle each)
to catch wiring bugs the mocked unit tests miss. Slow but bounded.
"""

import asyncio

import pytest

from engine_simulator.gui.parametric.study_manager import (
    ParametricStudyManager,
    ParametricStudyDef,
)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_end_to_end_tiny_study(tmp_path):
    messages = []

    async def broadcast(msg):
        messages.append(msg)

    loop = asyncio.get_running_loop()
    mgr = ParametricStudyManager(
        loop=loop,
        studies_dir=str(tmp_path),
        broadcast_fn=broadcast,
    )

    definition = ParametricStudyDef(
        study_id="param_integration",
        name="integration test",
        config_name="cbr600rr.json",
        parameter_path="plenum.volume",
        parameter_values=[0.0015, 0.0020],
        sweep_rpm_start=8000.0,
        sweep_rpm_end=9000.0,
        sweep_rpm_step=1000.0,
        sweep_n_cycles=1,
        n_workers=1,
        created_at="2026-04-10T12:00:00Z",
    )

    await mgr.start_study(definition)
    await mgr._study_task

    current = mgr.get_current()
    assert current.status == "complete", f"study failed: {current.error}"
    assert len(current.runs) == 2

    for i, run in enumerate(current.runs):
        assert run.status == "done", f"run {i} failed: {run.error}"
        assert len(run.sweep_results) == 2
        for perf in run.sweep_results:
            assert perf["brake_power_hp"] > 0, f"run {i} non-positive power: {perf}"
            assert perf["brake_torque_Nm"] > 0

    # Persisted file exists
    assert (tmp_path / "param_integration.json").exists()

    # At least one parametric message was broadcast
    parametric_msgs = [m for m in messages if m.get("channel") == "parametric"]
    assert len(parametric_msgs) > 0
    assert any(m["type"] == "parametric_study_complete" for m in parametric_msgs)
