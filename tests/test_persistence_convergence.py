"""Tests for convergence data round-trip in sweep persistence."""

import json
import os
import tempfile

from engine_simulator.gui.sweep_manager import LiveSweepState
from engine_simulator.gui.persistence import save_sweep, load_sweep


def _make_state_with_convergence() -> LiveSweepState:
    """Build a minimal LiveSweepState that includes convergence data."""
    return LiveSweepState(
        sweep_id="test-conv-001",
        status="complete",
        config={"name": "test", "n_cylinders": 4},
        config_name="test.json",
        rpm_points=[5000.0, 6000.0],
        n_cycles=10,
        n_workers=2,
        started_at="2026-04-09T00:00:00Z",
        completed_at="2026-04-09T00:05:00Z",
        rpms={
            5000.0: {
                "status": "done",
                "rpm_index": 0,
                "delta_history": [None, 0.15, 0.03, 0.004],
                "p_ivc_history": [
                    [101000.0, 101100.0, 101050.0, 101075.0],
                    [101200.0, 101300.0, 101250.0, 101275.0],
                    [101250.0, 101340.0, 101290.0, 101310.0],
                    [101252.0, 101342.0, 101291.0, 101312.0],
                ],
                "converged": True,
                "converged_at_cycle": 4,
                "perf": {"rpm": 5000.0, "indicated_power_hp": 30.0},
            },
            6000.0: {
                "status": "done",
                "rpm_index": 1,
                "delta_history": [None, 0.20, 0.08, 0.02, 0.003],
                "p_ivc_history": [
                    [102000.0, 102100.0, 102050.0, 102075.0],
                    [102400.0, 102500.0, 102450.0, 102475.0],
                    [102500.0, 102580.0, 102540.0, 102560.0],
                    [102520.0, 102595.0, 102555.0, 102575.0],
                    [102522.0, 102597.0, 102556.0, 102576.0],
                ],
                "converged": True,
                "converged_at_cycle": 5,
                "perf": {"rpm": 6000.0, "indicated_power_hp": 40.0},
            },
        },
        results_by_rpm={},
        sweep_results=[
            {"rpm": 5000.0, "indicated_power_hp": 30.0},
            {"rpm": 6000.0, "indicated_power_hp": 40.0},
        ],
    )


def test_convergence_data_round_trips():
    """Save a sweep with convergence data, load it, verify convergence is intact."""
    state = _make_state_with_convergence()
    with tempfile.TemporaryDirectory() as tmpdir:
        save_sweep(state, tmpdir)
        filepath = os.path.join(tmpdir, f"{state.sweep_id}.json")
        loaded = load_sweep(filepath)

    for rpm in [5000.0, 6000.0]:
        rpm_state = loaded.rpms[rpm]
        original = state.rpms[rpm]
        assert rpm_state.get("delta_history") == original["delta_history"]
        assert rpm_state.get("p_ivc_history") == original["p_ivc_history"]
        assert rpm_state.get("converged") == original["converged"]
        assert rpm_state.get("converged_at_cycle") == original["converged_at_cycle"]


def test_load_sweep_without_convergence_key():
    """Loading a legacy sweep file (no convergence key) should still work."""
    state = _make_state_with_convergence()
    with tempfile.TemporaryDirectory() as tmpdir:
        save_sweep(state, tmpdir)
        filepath = os.path.join(tmpdir, f"{state.sweep_id}.json")

        with open(filepath) as f:
            data = json.load(f)
        data.pop("convergence", None)
        with open(filepath, "w") as f:
            json.dump(data, f)

        loaded = load_sweep(filepath)

    assert loaded.rpms[5000.0]["status"] == "done"
    assert loaded.rpms[5000.0].get("delta_history") in (None, [])
