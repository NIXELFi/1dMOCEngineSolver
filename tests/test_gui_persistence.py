"""Sweep persistence round-trip tests.

Layer 2: a LiveSweepState saved to JSON and loaded back must produce
the same data. Catches schema bugs, dtype loss, and key-mismatch errors.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


def _build_sample_state(tmp_path):
    """Build a sample LiveSweepState resembling a real completed sweep."""
    from engine_simulator.gui.sweep_manager import LiveSweepState
    from engine_simulator.config.engine_config import EngineConfig
    from engine_simulator.postprocessing.results import SimulationResults, ProbeData

    cfg = EngineConfig()

    sample_results = SimulationResults()
    sample_results.theta_history = [0.0, 0.5, 1.0, 1.5]
    sample_results.dt_history = [0.0001, 0.0001, 0.0001, 0.0001]
    sample_results.plenum_pressure = [101325.0, 101300.0, 101280.0, 101290.0]
    sample_results.plenum_temperature = [300.0, 300.1, 300.2, 300.3]
    sample_results.restrictor_mdot = [0.012, 0.014, 0.013, 0.015]
    sample_results.restrictor_choked = [False, False, False, False]
    pd = ProbeData()
    pd.theta = [0.0, 0.5, 1.0, 1.5]
    pd.pressure = [101325.0, 101400.0, 101500.0, 101600.0]
    pd.temperature = [300.0, 300.1, 300.2, 300.3]
    pd.velocity = [0.0, 0.0, 0.0, 0.0]
    pd.density = [1.177, 1.179, 1.180, 1.181]
    sample_results.cylinder_data[0] = pd
    sample_results.pipe_probes["intake_runner_1_mid"] = pd

    state = LiveSweepState(
        sweep_id="2026-04-08T18-23-04_8000-8000_step1000_4cyc",
        status="complete",
        config=cfg,
        config_name="cbr600rr.json",
        rpm_points=[8000.0],
        n_cycles=4,
        n_workers=1,
        started_at="2026-04-08T18:23:04.123Z",
        completed_at="2026-04-08T18:24:11.847Z",
        rpms={
            8000.0: {
                "status": "done",
                "rpm_index": 0,
                "perf": {
                    "rpm": 8000.0,
                    "indicated_power_hp": 89.9,
                    "brake_power_hp": 72.2,
                    "brake_torque_Nm": 64.2,
                    "volumetric_efficiency_atm": 1.07,
                    "imep_bar": 16.78,
                    "bmep_bar": 13.47,
                    "wheel_power_hp": 72.2,
                    "wheel_torque_Nm": 64.2,
                    "drivetrain_efficiency": 1.0,
                    "indicated_power_kW": 67.05,
                    "indicated_torque_Nm": 80.04,
                    "brake_power_kW": 53.82,
                    "fmep_bar": 3.31,
                    "volumetric_efficiency_plenum": 1.28,
                    "volumetric_efficiency": 1.28,
                    "intake_mass_per_cycle_g": 0.756,
                    "restrictor_choked": False,
                    "restrictor_mdot": 0.054,
                    "plenum_pressure_bar": 0.85,
                },
                "elapsed": 11.2,
                "step_count": 4523,
                "converged": True,
            }
        },
        results_by_rpm={8000.0: sample_results},
        sweep_results=[
            {
                "rpm": 8000.0,
                "indicated_power_hp": 89.9,
                "brake_power_hp": 72.2,
                "brake_torque_Nm": 64.2,
                "volumetric_efficiency_atm": 1.07,
                "imep_bar": 16.78,
                "bmep_bar": 13.47,
                "wheel_power_hp": 72.2,
                "wheel_torque_Nm": 64.2,
                "drivetrain_efficiency": 1.0,
                "indicated_power_kW": 67.05,
                "indicated_torque_Nm": 80.04,
                "brake_power_kW": 53.82,
                "fmep_bar": 3.31,
                "volumetric_efficiency_plenum": 1.28,
                "volumetric_efficiency": 1.28,
                "intake_mass_per_cycle_g": 0.756,
                "restrictor_choked": False,
                "restrictor_mdot": 0.054,
                "plenum_pressure_bar": 0.85,
            }
        ],
    )
    return state


class TestSavePerfDicts:
    def test_save_creates_file(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        path = Path(tmp_path) / filename
        assert path.exists()

    def test_save_filename_matches_schema(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        assert filename.endswith(".json")
        assert "_8000-8000_step1000_4cyc" in filename

    def test_saved_file_has_schema_version(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        with open(Path(tmp_path) / filename) as f:
            data = json.load(f)
        assert data["schema_version"] == 1

    def test_saved_file_has_metadata(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        with open(Path(tmp_path) / filename) as f:
            data = json.load(f)
        assert data["metadata"]["config_name"] == "cbr600rr.json"
        assert data["metadata"]["n_workers_requested"] == 1
        assert "started_at" in data["metadata"]

    def test_saved_perf_dict_matches_input(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        with open(Path(tmp_path) / filename) as f:
            data = json.load(f)
        assert data["perf"][0]["brake_power_hp"] == 72.2
        assert data["perf"][0]["rpm"] == 8000.0

    def test_atomic_write_no_temp_file_left_behind(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep
        state = _build_sample_state(tmp_path)
        save_sweep(state, str(tmp_path))
        tmp_files = list(Path(tmp_path).glob("*.tmp"))
        assert tmp_files == [], f"Stale .tmp file: {tmp_files}"


class TestLoadSweep:
    def test_load_returns_loaded_sweep_state(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, load_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        loaded = load_sweep(str(Path(tmp_path) / filename))
        assert loaded.sweep_id == state.sweep_id
        assert len(loaded.sweep_results) == 1

    def test_save_load_roundtrip_perf_dicts_bit_identical(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, load_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        loaded = load_sweep(str(Path(tmp_path) / filename))
        assert len(loaded.sweep_results) == len(state.sweep_results)
        for orig, lod in zip(state.sweep_results, loaded.sweep_results):
            for k in orig:
                assert orig[k] == lod[k], f"Mismatch on {k}"

    def test_save_load_roundtrip_results_arrays_match(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, load_sweep
        state = _build_sample_state(tmp_path)
        filename = save_sweep(state, str(tmp_path))
        loaded = load_sweep(str(Path(tmp_path) / filename))
        for rpm in state.results_by_rpm:
            orig_r = state.results_by_rpm[rpm]
            lod_r = loaded.results_by_rpm[rpm]
            np.testing.assert_array_equal(
                np.asarray(orig_r.theta_history),
                np.asarray(lod_r.theta_history),
            )
            np.testing.assert_array_equal(
                np.asarray(orig_r.plenum_pressure),
                np.asarray(lod_r.plenum_pressure),
            )
            assert set(orig_r.cylinder_data.keys()) == set(
                lod_r.cylinder_data.keys()
            )
            for cid in orig_r.cylinder_data:
                np.testing.assert_array_equal(
                    np.asarray(orig_r.cylinder_data[cid].pressure),
                    np.asarray(lod_r.cylinder_data[cid].pressure),
                )

    def test_load_unknown_schema_version_raises(self, tmp_path):
        from engine_simulator.gui.persistence import load_sweep
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({
            "schema_version": 999,
            "sweep_id": "x", "metadata": {}, "sweep_params": {},
            "engine_config": {}, "perf": [], "results_by_rpm": {},
        }))
        with pytest.raises(ValueError, match="schema version"):
            load_sweep(str(bad))

    def test_load_corrupt_json_raises_clear_error(self, tmp_path):
        from engine_simulator.gui.persistence import load_sweep
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("{not valid json")
        with pytest.raises(ValueError, match="Could not parse"):
            load_sweep(str(corrupt))


class TestListSweeps:
    def test_list_sweeps_returns_summaries(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, list_sweeps
        state = _build_sample_state(tmp_path)
        save_sweep(state, str(tmp_path))
        summaries = list_sweeps(str(tmp_path))
        assert len(summaries) == 1
        assert summaries[0]["id"] == state.sweep_id

    def test_list_sweeps_empty_directory(self, tmp_path):
        from engine_simulator.gui.persistence import list_sweeps
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert list_sweeps(str(empty_dir)) == []

    def test_list_sweeps_skips_non_json_files(self, tmp_path):
        from engine_simulator.gui.persistence import save_sweep, list_sweeps
        state = _build_sample_state(tmp_path)
        save_sweep(state, str(tmp_path))
        (tmp_path / "readme.txt").write_text("not a sweep")
        (tmp_path / "junk.tmp").write_text("not a sweep")
        summaries = list_sweeps(str(tmp_path))
        assert len(summaries) == 1
