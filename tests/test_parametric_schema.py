"""Pydantic request-schema validation tests."""

import pytest
from pydantic import ValidationError

from engine_simulator.gui.parametric.schema import (
    ParametricStudyStartRequest,
    resolve_parameter_values,
)


def _valid_body():
    return {
        "name": "IRL sweep",
        "config_name": "cbr600rr.json",
        "parameter_path": "intake_pipes[*].length",
        "value_start": 0.15,
        "value_end": 0.35,
        "value_step": 0.05,
        "sweep_rpm_start": 3000,
        "sweep_rpm_end": 15000,
        "sweep_rpm_step": 500,
        "sweep_n_cycles": 8,
        "n_workers": 8,
    }


def test_valid_body_parses():
    req = ParametricStudyStartRequest(**_valid_body())
    assert req.parameter_path == "intake_pipes[*].length"
    assert req.sweep_n_cycles == 8


def test_rejects_unknown_parameter_path():
    body = _valid_body()
    body["parameter_path"] = "cylinder.bore"
    with pytest.raises(ValidationError, match="not in whitelist"):
        ParametricStudyStartRequest(**body)


def test_rejects_rpm_end_lte_rpm_start():
    body = _valid_body()
    body["sweep_rpm_end"] = 3000
    with pytest.raises(ValidationError):
        ParametricStudyStartRequest(**body)


def test_rejects_value_end_lte_value_start():
    body = _valid_body()
    body["value_end"] = 0.10
    with pytest.raises(ValidationError):
        ParametricStudyStartRequest(**body)


def test_rejects_nonpositive_value_step():
    body = _valid_body()
    body["value_step"] = 0.0
    with pytest.raises(ValidationError):
        ParametricStudyStartRequest(**body)


def test_rejects_value_start_below_min_allowed():
    body = _valid_body()
    body["parameter_path"] = "plenum.volume"
    body["value_start"] = 0.00001  # below min_allowed=0.0001
    body["value_end"] = 0.002
    body["value_step"] = 0.0005
    with pytest.raises(ValidationError, match="min_allowed|bound"):
        ParametricStudyStartRequest(**body)


def test_resolve_parameter_values_from_range():
    values = resolve_parameter_values(0.15, 0.30, 0.05)
    assert values == pytest.approx([0.15, 0.20, 0.25, 0.30])


def test_resolve_parameter_values_handles_fp_roundoff():
    values = resolve_parameter_values(0.15, 0.35, 0.05)
    assert len(values) == 5
    assert values[0] == pytest.approx(0.15)
    assert values[-1] == pytest.approx(0.35)
