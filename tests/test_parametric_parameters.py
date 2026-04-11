"""Whitelist integrity tests for sweepable parameters."""

import pytest

from engine_simulator.gui.parametric.parameters import (
    Param,
    SWEEPABLE_PARAMETERS,
    find_parameter,
)


def test_whitelist_is_non_empty():
    assert len(SWEEPABLE_PARAMETERS) > 0


def test_every_param_has_required_fields():
    for param in SWEEPABLE_PARAMETERS:
        assert isinstance(param, Param)
        assert param.path
        assert param.label
        assert param.unit is not None  # may be ""
        start, end, step = param.default_range
        assert start < end
        assert step > 0


def test_paths_are_unique():
    paths = [p.path for p in SWEEPABLE_PARAMETERS]
    assert len(paths) == len(set(paths))


def test_find_parameter_returns_matching_param():
    p = find_parameter("plenum.volume")
    assert p is not None
    assert p.label == "Plenum Volume"


def test_find_parameter_returns_none_for_unknown():
    assert find_parameter("cylinder.bore") is None


@pytest.mark.xfail(reason="path_resolver implemented in Task 2")
def test_all_whitelisted_paths_resolve_against_default_config():
    """Every whitelisted path must be a valid path into the default config."""
    from engine_simulator.gui.parametric.path_resolver import get_parameter
    from pathlib import Path
    import json

    config_path = (
        Path(__file__).resolve().parents[1]
        / "engine_simulator" / "config" / "cbr600rr.json"
    )
    with open(config_path) as f:
        config_dict = json.load(f)

    for param in SWEEPABLE_PARAMETERS:
        value = get_parameter(config_dict, param.path)
        assert value is not None, f"Path {param.path} resolved to None"


def test_excluded_fundamental_parameters_not_in_whitelist():
    """Fundamental engine geometry must not be sweepable."""
    excluded = {
        "cylinder.bore",
        "cylinder.stroke",
        "cylinder.con_rod_length",
        "cylinder.compression_ratio",
        "n_cylinders",
        "firing_order",
        "simulation.cfl_number",
        "simulation.convergence_tolerance",
    }
    paths = {p.path for p in SWEEPABLE_PARAMETERS}
    assert not (excluded & paths), f"Excluded params found: {excluded & paths}"
