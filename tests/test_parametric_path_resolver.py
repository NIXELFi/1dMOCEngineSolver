"""Tests for the dotted-path config resolver."""

import copy
import json
from pathlib import Path

import pytest

from engine_simulator.gui.parametric.path_resolver import (
    get_parameter,
    set_parameter,
    PathError,
    BoundsError,
)


@pytest.fixture
def config():
    """Load the default cbr600rr config as a dict."""
    config_path = (
        Path(__file__).resolve().parents[1]
        / "engine_simulator" / "config" / "cbr600rr.json"
    )
    with open(config_path) as f:
        return json.load(f)


# ---------- get_parameter ----------

def test_get_simple_dotted_path(config):
    assert get_parameter(config, "plenum.volume") == pytest.approx(0.0015)


def test_get_nested_dotted_path(config):
    assert get_parameter(config, "combustion.spark_advance") == 25.0


def test_get_indexed_path(config):
    assert get_parameter(config, "intake_pipes[0].length") == 0.245


def test_get_wildcard_returns_list(config):
    values = get_parameter(config, "intake_pipes[*].length")
    assert isinstance(values, list)
    assert len(values) == 4
    assert all(v == 0.245 for v in values)


def test_get_missing_path_raises(config):
    with pytest.raises(PathError):
        get_parameter(config, "nonexistent.field")


def test_get_out_of_range_index_raises(config):
    with pytest.raises(PathError):
        get_parameter(config, "intake_pipes[99].length")


# ---------- set_parameter ----------

def test_set_simple_path_returns_new_dict(config):
    result = set_parameter(config, "plenum.volume", 0.002)
    assert result["plenum"]["volume"] == 0.002
    # Original dict is unchanged
    assert config["plenum"]["volume"] == pytest.approx(0.0015)


def test_set_nested_path(config):
    result = set_parameter(config, "combustion.spark_advance", 30.0)
    assert result["combustion"]["spark_advance"] == 30.0


def test_set_indexed_path(config):
    result = set_parameter(config, "intake_pipes[0].length", 0.30)
    assert result["intake_pipes"][0]["length"] == 0.30
    # Other pipes untouched
    assert result["intake_pipes"][1]["length"] == 0.245


def test_set_wildcard_updates_all_elements(config):
    result = set_parameter(config, "intake_pipes[*].length", 0.30)
    for pipe in result["intake_pipes"]:
        assert pipe["length"] == 0.30


def test_set_does_not_mutate_input(config):
    original = copy.deepcopy(config)
    set_parameter(config, "plenum.volume", 0.003)
    assert config == original


def test_set_missing_path_raises(config):
    with pytest.raises(PathError):
        set_parameter(config, "nonexistent.field", 1.0)


def test_set_below_min_allowed_raises(config):
    with pytest.raises(BoundsError):
        set_parameter(
            config, "plenum.volume", 0.00001,
            min_allowed=0.0001, max_allowed=0.02,
        )


def test_set_above_max_allowed_raises(config):
    with pytest.raises(BoundsError):
        set_parameter(
            config, "plenum.volume", 0.5,
            min_allowed=0.0001, max_allowed=0.02,
        )


def test_set_within_bounds_succeeds(config):
    result = set_parameter(
        config, "plenum.volume", 0.002,
        min_allowed=0.0001, max_allowed=0.02,
    )
    assert result["plenum"]["volume"] == 0.002
