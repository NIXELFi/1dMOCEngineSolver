"""Snapshot builder tests.

snapshot.build_snapshot translates a LiveSweepState (or None) into the
JSON-serializable dict that gets sent to a freshly connected WebSocket
client.
"""

import pytest
from unittest.mock import MagicMock


def test_snapshot_with_no_sweep(tmp_path):
    from engine_simulator.gui.snapshot import build_snapshot
    snap = build_snapshot(current=None, sweeps_dir=str(tmp_path))
    assert snap["type"] == "snapshot"
    assert snap["sweep"] is None
    assert snap["available_sweeps"] == []


def test_snapshot_with_running_sweep(tmp_path):
    from engine_simulator.gui.snapshot import build_snapshot
    from engine_simulator.gui.sweep_manager import LiveSweepState
    state = LiveSweepState(
        sweep_id="test_sweep",
        status="running",
        config=MagicMock(),
        config_name="cbr600rr.json",
        rpm_points=[8000.0, 10000.0],
        n_cycles=4,
        n_workers=2,
        started_at="2026-04-08T18:00:00Z",
        rpms={
            8000.0: {"status": "running", "rpm_index": 0, "current_cycle": 2,
                     "delta": 0.05, "delta_history": [0.1, 0.05],
                     "step_count": 1000, "elapsed": 5.0,
                     "p_ivc_history": [[95000.0]*4, [95100.0]*4]},
            10000.0: {"status": "queued", "rpm_index": 1},
        },
    )
    snap = build_snapshot(current=state, sweeps_dir=str(tmp_path))
    assert snap["sweep"] is not None
    assert snap["sweep"]["status"] == "running"
    assert snap["sweep"]["sweep_id"] == "test_sweep"
    assert snap["sweep"]["rpm_points"] == [8000.0, 10000.0]
    assert "8000.0" in snap["sweep"]["rpms"] or 8000.0 in snap["sweep"]["rpms"]
    assert snap["sweep"]["config_summary"]["n_cycles"] == 4


def test_snapshot_lists_available_sweeps_from_disk(tmp_path):
    from engine_simulator.gui.snapshot import build_snapshot
    from engine_simulator.gui.persistence import save_sweep
    from engine_simulator.gui.sweep_manager import LiveSweepState
    from engine_simulator.config.engine_config import EngineConfig

    state = LiveSweepState(
        sweep_id="2026-04-08T18-00-00_8000-8000_step1000_4cyc",
        status="complete",
        config=EngineConfig(),
        config_name="cbr600rr.json",
        rpm_points=[8000.0],
        n_cycles=4,
        n_workers=1,
        started_at="2026-04-08T18:00:00Z",
        completed_at="2026-04-08T18:01:00Z",
        sweep_results=[{"rpm": 8000.0, "brake_power_hp": 72.2}],
    )
    save_sweep(state, str(tmp_path))

    snap = build_snapshot(current=None, sweeps_dir=str(tmp_path))
    assert len(snap["available_sweeps"]) == 1
    assert snap["available_sweeps"][0]["id"] == state.sweep_id
