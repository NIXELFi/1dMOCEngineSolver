"""Pydantic schema round-trip tests.

Critical: the parallel Pydantic schema in engine_simulator/gui/config_schema.py
must remain in lockstep with the dataclass schema in engine_simulator/config/
engine_config.py. These tests catch drift by loading the canonical
cbr600rr.json through both paths and comparing results field-by-field.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

import pytest

from engine_simulator.config.engine_config import (
    EngineConfig,
    PipeConfig,
    load_config,
)
from engine_simulator.gui.config_schema import EnginePayload, PipeModel


CBR_PATH = (
    Path(__file__).resolve().parents[1]
    / "engine_simulator"
    / "config"
    / "cbr600rr.json"
)


def _normalize(obj):
    """Recursively normalize lists/tuples for comparison."""
    if is_dataclass(obj):
        return _normalize(asdict(obj))
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(x) for x in obj]
    return obj


class TestExistingConfigParsesIntoPydantic:
    def test_cbr600rr_json_loads_into_pydantic(self):
        with open(CBR_PATH) as f:
            data = json.load(f)
        # Should not raise
        payload = EnginePayload.model_validate(data)
        assert payload.name == data["name"]
        assert payload.cylinder.bore == data["cylinder"]["bore"]


class TestPydanticRoundTripVsLoadConfig:
    def test_pydantic_dump_loads_via_load_config(self, tmp_path):
        # 1. Original dataclass via load_config()
        original_cfg = load_config(CBR_PATH)

        # 2. Same JSON through pydantic
        with open(CBR_PATH) as f:
            data = json.load(f)
        payload = EnginePayload.model_validate(data)

        # 3. Dump pydantic to a temp file, load with load_config()
        dumped = payload.model_dump(mode="json")
        tmp_file = tmp_path / "round_trip.json"
        tmp_file.write_text(json.dumps(dumped))
        round_tripped = load_config(tmp_file)

        # 4. Compare every nested field via asdict normalization
        assert _normalize(round_tripped) == _normalize(original_cfg)


class TestCdTableRoundTrip:
    def test_pydantic_preserves_cd_table_pairs(self):
        with open(CBR_PATH) as f:
            data = json.load(f)
        payload = EnginePayload.model_validate(data)
        # cd_table should be a list of (float, float) tuples
        assert len(payload.intake_valve.cd_table) >= 1
        first = payload.intake_valve.cd_table[0]
        assert len(first) == 2
        assert isinstance(first[0], float)
        assert isinstance(first[1], float)


class TestOptionalDiameterOutRoundTrip:
    def test_pipe_without_diameter_out_round_trips_to_none(self):
        # Existing intake_runner_1 has no diameter_out in the JSON
        with open(CBR_PATH) as f:
            data = json.load(f)
        payload = EnginePayload.model_validate(data)
        assert payload.intake_pipes[0].diameter_out is None
        # And round-tripping a pipe with diameter_out=None preserves it
        dumped = payload.intake_pipes[0].model_dump(mode="json")
        reparsed = PipeModel.model_validate(dumped)
        assert reparsed.diameter_out is None

    def test_pipe_with_diameter_out_round_trips(self):
        m = PipeModel(
            name="taper",
            length=0.4,
            diameter=0.0381,
            diameter_out=0.0508,
            n_points=20,
            wall_temperature=500.0,
            roughness=4.6e-05,
        )
        dumped = m.model_dump(mode="json")
        reparsed = PipeModel.model_validate(dumped)
        assert reparsed.diameter_out == pytest.approx(0.0508)
