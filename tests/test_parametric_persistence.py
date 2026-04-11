"""Round-trip tests for parametric study persistence."""

import json
from pathlib import Path

import pytest

from engine_simulator.gui.parametric.persistence import (
    save_study,
    load_study,
    list_studies,
)
from engine_simulator.gui.parametric.study_manager import (
    LiveParametricStudy,
    ParametricRun,
    ParametricStudyDef,
)


def _make_study(study_id="param_test") -> LiveParametricStudy:
    definition = ParametricStudyDef(
        study_id=study_id,
        name="test",
        config_name="cbr600rr.json",
        parameter_path="plenum.volume",
        parameter_values=[0.001, 0.002, 0.003],
        sweep_rpm_start=6000.0,
        sweep_rpm_end=8000.0,
        sweep_rpm_step=1000.0,
        sweep_n_cycles=2,
        n_workers=1,
        created_at="2026-04-10T12:00:00.000000Z",
    )
    runs = [
        ParametricRun(
            parameter_value=0.001,
            status="done",
            sweep_results=[
                {"rpm": 6000.0, "brake_power_hp": 40.0, "brake_torque_Nm": 50.0},
                {"rpm": 7000.0, "brake_power_hp": 55.0, "brake_torque_Nm": 56.0},
                {"rpm": 8000.0, "brake_power_hp": 65.0, "brake_torque_Nm": 58.0},
            ],
            per_rpm_delta={6000.0: 0.002, 7000.0: 0.0015, 8000.0: 0.001},
            elapsed_seconds=12.3,
            error=None,
        ),
        ParametricRun(
            parameter_value=0.002,
            status="done",
            sweep_results=[
                {"rpm": 6000.0, "brake_power_hp": 42.0, "brake_torque_Nm": 52.0},
                {"rpm": 7000.0, "brake_power_hp": 58.0, "brake_torque_Nm": 59.0},
                {"rpm": 8000.0, "brake_power_hp": 68.0, "brake_torque_Nm": 61.0},
            ],
            per_rpm_delta={},
            elapsed_seconds=11.8,
            error=None,
        ),
    ]
    return LiveParametricStudy(
        definition=definition,
        status="complete",
        started_at="2026-04-10T12:00:00Z",
        completed_at="2026-04-10T12:05:00Z",
        runs=runs,
        error=None,
    )


def test_save_and_load_round_trip(tmp_path):
    study = _make_study()
    filename = save_study(study, str(tmp_path))
    assert filename.endswith(".json")

    loaded = load_study(str(tmp_path / filename))
    assert loaded.definition.study_id == study.definition.study_id
    assert loaded.status == "complete"
    assert len(loaded.runs) == 2
    assert loaded.runs[0].parameter_value == 0.001
    assert loaded.runs[0].sweep_results[1]["brake_power_hp"] == 55.0


def test_nonfinite_values_coerced_to_none(tmp_path):
    study = _make_study()
    study.runs[0].sweep_results[0]["brake_power_hp"] = float("inf")
    filename = save_study(study, str(tmp_path))
    # Raw JSON must not contain Infinity/NaN literals
    raw = (tmp_path / filename).read_text()
    assert "Infinity" not in raw
    assert "NaN" not in raw
    loaded = load_study(str(tmp_path / filename))
    assert loaded.runs[0].sweep_results[0]["brake_power_hp"] is None


def test_list_studies_returns_metadata(tmp_path):
    save_study(_make_study("param_a"), str(tmp_path))
    save_study(_make_study("param_b"), str(tmp_path))
    items = list_studies(str(tmp_path))
    assert len(items) == 2
    assert all("study_id" in it for it in items)
    assert all("parameter_path" in it for it in items)
    assert all("status" in it for it in items)


def test_list_studies_returns_empty_for_missing_dir(tmp_path):
    assert list_studies(str(tmp_path / "nonexistent")) == []
