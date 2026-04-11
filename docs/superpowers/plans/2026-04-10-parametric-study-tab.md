# Parametric Study Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new GUI tab for exhaustive single-parameter sensitivity studies (intake runner length, plenum volume, valve timing, etc.) with ranked comparison charts, summary table, and heatmap.

**Architecture:** New `ParametricStudyManager` owns study lifecycle and reuses the existing `SimulationOrchestrator` unchanged. Each study mutates one whitelisted config field across a user-defined range, runs a full RPM sweep per value, and computes derived optimization metrics on the frontend. Runs independently alongside the existing sweep flow — no modifications to `SweepManager` or existing tabs.

**Tech Stack:** Python 3 + FastAPI + pytest on the backend; React 18 + TypeScript + Zustand + Recharts on the frontend.

**Note on frontend testing:** The project currently has no frontend test framework. This plan relies on TypeScript strict compilation and manual browser verification for the UI layer. All derived logic (metric computation, ranking) is kept in pure-function modules so a test harness can be added later without refactoring.

**Spec reference:** `docs/superpowers/specs/2026-04-10-parametric-study-tab-design.md`

---

## File Structure

**Backend (new files):**
- `engine_simulator/gui/parametric/__init__.py`
- `engine_simulator/gui/parametric/parameters.py` — `Param` dataclass, `SWEEPABLE_PARAMETERS` whitelist
- `engine_simulator/gui/parametric/path_resolver.py` — dotted/bracketed/wildcard get+set
- `engine_simulator/gui/parametric/schema.py` — Pydantic request models
- `engine_simulator/gui/parametric/persistence.py` — save/load studies
- `engine_simulator/gui/parametric/event_consumer.py` — `ParametricEventConsumer` bridge
- `engine_simulator/gui/parametric/study_manager.py` — `ParametricStudyManager`, `LiveParametricStudy`, `ParametricRun`, `ParametricStudyDef`
- `engine_simulator/gui/routes_parametric.py` — REST router under `/api/parametric`

**Backend (modified):**
- `engine_simulator/gui/server.py` — wire `ParametricStudyManager` into lifespan + include router

**Backend tests (new):**
- `tests/test_parametric_parameters.py`
- `tests/test_parametric_path_resolver.py`
- `tests/test_parametric_schema.py`
- `tests/test_parametric_persistence.py`
- `tests/test_parametric_event_consumer.py`
- `tests/test_parametric_study_manager.py`
- `tests/test_parametric_routes.py`
- `tests/test_parametric_integration.py`

**Frontend (new files):**
- `gui-frontend/src/types/parametric.ts` — types for Param, ParametricStudyDef, ParametricRun, LiveParametricStudy
- `gui-frontend/src/state/parametricStore.ts` — Zustand store
- `gui-frontend/src/state/parametricSelectors.ts` — pure derived-data functions
- `gui-frontend/src/components/parametric/ParametricView.tsx` — mode router
- `gui-frontend/src/components/parametric/ParametricSetupForm.tsx` — Mode A
- `gui-frontend/src/components/parametric/ParametricRunGrid.tsx` — Mode B
- `gui-frontend/src/components/parametric/ParametricResultsView.tsx` — Mode C shell + controls
- `gui-frontend/src/components/parametric/ParametricOverlayCharts.tsx`
- `gui-frontend/src/components/parametric/ParametricComparisonTable.tsx`
- `gui-frontend/src/components/parametric/ParametricHeatmap.tsx`
- `gui-frontend/src/components/parametric/ParametricStudyListSidebar.tsx`

**Frontend (modified):**
- `gui-frontend/src/api/client.ts` — add parametric methods
- `gui-frontend/src/state/configStore.ts` — add `"parametric"` to `ActiveTab`
- `gui-frontend/src/state/eventReducer.ts` — route channel-tagged messages
- `gui-frontend/src/components/TabBar.tsx` — add 4th tab
- `gui-frontend/src/App.tsx` — render `ParametricView` when active

---

## Phase 1 — Backend Foundation

### Task 1: `Param` dataclass and `SWEEPABLE_PARAMETERS` whitelist

**Files:**
- Create: `engine_simulator/gui/parametric/__init__.py`
- Create: `engine_simulator/gui/parametric/parameters.py`
- Test: `tests/test_parametric_parameters.py`

- [ ] **Step 1.1: Create package `__init__.py`**

Create `engine_simulator/gui/parametric/__init__.py` with a single-line docstring:

```python
"""Parametric study feature: sweep one engine-design parameter across a range."""
```

- [ ] **Step 1.2: Write failing test for whitelist integrity**

Create `tests/test_parametric_parameters.py`:

```python
"""Whitelist integrity tests for sweepable parameters."""

from engine_simulator.config.engine_config import load_config
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
```

- [ ] **Step 1.3: Run test to verify failure**

Run: `pytest tests/test_parametric_parameters.py -v`
Expected: ImportError on `engine_simulator.gui.parametric.parameters`.

- [ ] **Step 1.4: Implement `parameters.py`**

Create `engine_simulator/gui/parametric/parameters.py`:

```python
"""Whitelist of sweepable engine-design parameters.

Parameters listed here can be the subject of a parametric study. Paths use
dotted notation into the JSON dict representation of an EngineConfig.

- Dotted:   "plenum.volume"
- Indexed:  "intake_pipes[0].length"
- Wildcard: "intake_pipes[*].length" (applies to all list elements)

`default_range` and all API I/O use storage units (SI). `display_scale` is
a multiplier applied ONLY at the UI boundary — e.g. display_scale=1000 for
a length in meters shows mm to the user. The backend never sees scaled
values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Param:
    path: str                                  # dotted path into config dict
    label: str                                 # human-readable name
    unit: str                                  # display unit label (e.g. "mm", "deg CA")
    default_range: tuple[float, float, float]  # (start, end, step) in storage units
    display_scale: float = 1.0                 # e.g. 1000 to display meters as mm
    min_allowed: Optional[float] = None        # hard safety bound (storage units)
    max_allowed: Optional[float] = None
    category: str = "Other"                    # for UI grouping


SWEEPABLE_PARAMETERS: list[Param] = [
    # ---- Intake pipes (all 4 runners swept together by default) ----
    Param(
        path="intake_pipes[*].length",
        label="Intake Runner Length",
        unit="mm",
        default_range=(0.10, 0.40, 0.025),
        display_scale=1000,
        min_allowed=0.02,
        max_allowed=1.0,
        category="Intake",
    ),
    Param(
        path="intake_pipes[*].diameter",
        label="Intake Runner Diameter",
        unit="mm",
        default_range=(0.030, 0.050, 0.0025),
        display_scale=1000,
        min_allowed=0.015,
        max_allowed=0.080,
        category="Intake",
    ),

    # ---- Exhaust ----
    Param(
        path="exhaust_primaries[*].length",
        label="Exhaust Primary Length",
        unit="mm",
        default_range=(0.25, 0.60, 0.05),
        display_scale=1000,
        min_allowed=0.05,
        max_allowed=1.5,
        category="Exhaust",
    ),
    Param(
        path="exhaust_primaries[*].diameter",
        label="Exhaust Primary Diameter",
        unit="mm",
        default_range=(0.028, 0.045, 0.002),
        display_scale=1000,
        min_allowed=0.015,
        max_allowed=0.080,
        category="Exhaust",
    ),
    Param(
        path="exhaust_secondaries[*].length",
        label="Exhaust Secondary Length",
        unit="mm",
        default_range=(0.20, 0.50, 0.05),
        display_scale=1000,
        min_allowed=0.05,
        max_allowed=1.5,
        category="Exhaust",
    ),
    Param(
        path="exhaust_secondaries[*].diameter",
        label="Exhaust Secondary Diameter",
        unit="mm",
        default_range=(0.035, 0.055, 0.0025),
        display_scale=1000,
        min_allowed=0.020,
        max_allowed=0.100,
        category="Exhaust",
    ),

    # ---- Plenum ----
    Param(
        path="plenum.volume",
        label="Plenum Volume",
        unit="L",
        default_range=(0.0005, 0.004, 0.00025),  # 0.5 L to 4 L in 0.25 L steps
        display_scale=1000,  # m^3 -> L
        min_allowed=0.0001,
        max_allowed=0.02,
        category="Plenum",
    ),

    # ---- Restrictor ----
    Param(
        path="restrictor.discharge_coefficient",
        label="Restrictor Cd",
        unit="",
        default_range=(0.85, 0.98, 0.01),
        display_scale=1.0,
        min_allowed=0.5,
        max_allowed=1.0,
        category="Restrictor",
    ),

    # ---- Valve timing (all in degrees crank angle) ----
    Param(
        path="intake_valve.open_angle",
        label="IVO (BTDC)",
        unit="deg CA",
        default_range=(-20, 30, 5),
        display_scale=1.0,
        min_allowed=-40,
        max_allowed=60,
        category="Valve Timing",
    ),
    Param(
        path="intake_valve.close_angle",
        label="IVC (ABDC)",
        unit="deg CA",
        default_range=(30, 80, 5),
        display_scale=1.0,
        min_allowed=0,
        max_allowed=120,
        category="Valve Timing",
    ),
    Param(
        path="exhaust_valve.open_angle",
        label="EVO (BBDC)",
        unit="deg CA",
        default_range=(30, 80, 5),
        display_scale=1.0,
        min_allowed=0,
        max_allowed=120,
        category="Valve Timing",
    ),
    Param(
        path="exhaust_valve.close_angle",
        label="EVC (ATDC)",
        unit="deg CA",
        default_range=(-20, 30, 5),
        display_scale=1.0,
        min_allowed=-40,
        max_allowed=60,
        category="Valve Timing",
    ),
    Param(
        path="intake_valve.max_lift",
        label="Intake Max Lift",
        unit="mm",
        default_range=(0.006, 0.012, 0.0005),
        display_scale=1000,
        min_allowed=0.002,
        max_allowed=0.020,
        category="Valve Timing",
    ),
    Param(
        path="exhaust_valve.max_lift",
        label="Exhaust Max Lift",
        unit="mm",
        default_range=(0.006, 0.012, 0.0005),
        display_scale=1000,
        min_allowed=0.002,
        max_allowed=0.020,
        category="Valve Timing",
    ),

    # ---- Combustion ----
    Param(
        path="combustion.spark_advance",
        label="Spark Advance",
        unit="deg BTDC",
        default_range=(10, 40, 2),
        display_scale=1.0,
        min_allowed=0,
        max_allowed=60,
        category="Combustion",
    ),
    Param(
        path="combustion.combustion_duration",
        label="Burn Duration",
        unit="deg CA",
        default_range=(30, 70, 5),
        display_scale=1.0,
        min_allowed=10,
        max_allowed=120,
        category="Combustion",
    ),
    Param(
        path="combustion.afr_target",
        label="Target AFR",
        unit="",
        default_range=(11.5, 14.7, 0.25),
        display_scale=1.0,
        min_allowed=8.0,
        max_allowed=18.0,
        category="Combustion",
    ),
]


def find_parameter(path: str) -> Optional[Param]:
    """Return the Param with the given path, or None if not whitelisted."""
    for p in SWEEPABLE_PARAMETERS:
        if p.path == path:
            return p
    return None


def to_api_dict(param: Param) -> dict:
    """Serialize a Param to a JSON-friendly dict for the API."""
    return {
        "path": param.path,
        "label": param.label,
        "unit": param.unit,
        "default_range": list(param.default_range),
        "display_scale": param.display_scale,
        "min_allowed": param.min_allowed,
        "max_allowed": param.max_allowed,
        "category": param.category,
    }
```

- [ ] **Step 1.5: Run tests to verify passing**

Run: `pytest tests/test_parametric_parameters.py -v`
Expected: All tests pass. (Note: the `test_all_whitelisted_paths_resolve_against_default_config` test still fails because `path_resolver` doesn't exist — that's Task 2. Mark it with xfail for now.)

- [ ] **Step 1.6: Add xfail marker for the path resolver test**

Edit `tests/test_parametric_parameters.py`, add `@pytest.mark.xfail(reason="path_resolver implemented in Task 2")` above `test_all_whitelisted_paths_resolve_against_default_config` and add `import pytest` at the top.

Run: `pytest tests/test_parametric_parameters.py -v`
Expected: All tests pass (one xfail).

- [ ] **Step 1.7: Commit**

```bash
git add engine_simulator/gui/parametric/__init__.py \
        engine_simulator/gui/parametric/parameters.py \
        tests/test_parametric_parameters.py
git commit -m "feat(parametric): add sweepable parameter whitelist

Introduces the Param dataclass and SWEEPABLE_PARAMETERS whitelist that
defines which engine-design fields can be the subject of a parametric
study. Fundamental geometry (bore, stroke, compression ratio) is
intentionally excluded."
```

---

### Task 2: Path resolver (dotted/indexed/wildcard get+set)

**Files:**
- Create: `engine_simulator/gui/parametric/path_resolver.py`
- Test: `tests/test_parametric_path_resolver.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_parametric_path_resolver.py`:

```python
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
```

- [ ] **Step 2.2: Run tests to verify failure**

Run: `pytest tests/test_parametric_path_resolver.py -v`
Expected: ImportError.

- [ ] **Step 2.3: Implement `path_resolver.py`**

Create `engine_simulator/gui/parametric/path_resolver.py`:

```python
"""Dotted/indexed/wildcard path resolver for the engine config dict.

Supports three path syntaxes:
- "plenum.volume"           — dotted
- "intake_pipes[0].length"  — indexed list access
- "intake_pipes[*].length"  — wildcard (applies to all list elements)

get_parameter() returns the value(s). set_parameter() returns a deep copy
with the mutation applied — the input dict is never touched.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Optional


class PathError(ValueError):
    """Raised when a path is malformed or does not resolve."""


class BoundsError(ValueError):
    """Raised when a value is outside the allowed bounds for a parameter."""


# Matches a path segment like "foo", "foo[0]", or "foo[*]".
_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+|\*)\])?$")


def _parse_path(path: str) -> list[tuple[str, Optional[str]]]:
    """Parse 'a.b[0].c' into [('a', None), ('b', '0'), ('c', None)]."""
    if not path:
        raise PathError("empty path")
    segments = []
    for raw in path.split("."):
        match = _SEGMENT_RE.match(raw)
        if not match:
            raise PathError(f"invalid path segment: {raw!r}")
        name, index = match.group(1), match.group(2)
        segments.append((name, index))
    return segments


def _descend(obj: Any, segments: list[tuple[str, Optional[str]]]) -> Any:
    """Walk `segments` into `obj`, returning the resolved value or list
    of values (for wildcard). Read-only."""
    if not segments:
        return obj
    name, index = segments[0]
    rest = segments[1:]

    if not isinstance(obj, dict) or name not in obj:
        raise PathError(f"missing key: {name}")

    child = obj[name]

    if index is None:
        return _descend(child, rest)

    if not isinstance(child, list):
        raise PathError(f"expected list at {name}, got {type(child).__name__}")

    if index == "*":
        return [_descend(item, rest) for item in child]

    idx = int(index)
    if idx < 0 or idx >= len(child):
        raise PathError(f"index {idx} out of range for {name}")

    return _descend(child[idx], rest)


def _apply(obj: Any, segments: list[tuple[str, Optional[str]]], value: float) -> None:
    """Write `value` at the location indicated by `segments`. Mutates `obj`
    in place — the caller provides a deep copy."""
    if not segments:
        raise PathError("empty path for set")

    name, index = segments[0]
    rest = segments[1:]

    if not isinstance(obj, dict) or name not in obj:
        raise PathError(f"missing key: {name}")

    if index is None:
        if not rest:
            obj[name] = value
            return
        _apply(obj[name], rest, value)
        return

    child = obj[name]
    if not isinstance(child, list):
        raise PathError(f"expected list at {name}, got {type(child).__name__}")

    if index == "*":
        for item in child:
            if not rest:
                raise PathError(f"wildcard requires a trailing field: {name}[*]")
            _apply(item, rest, value)
        return

    idx = int(index)
    if idx < 0 or idx >= len(child):
        raise PathError(f"index {idx} out of range for {name}")

    if not rest:
        child[idx] = value
        return
    _apply(child[idx], rest, value)


def get_parameter(config: dict, path: str) -> Any:
    """Read the value at `path`. For wildcard paths, returns a list."""
    segments = _parse_path(path)
    return _descend(config, segments)


def set_parameter(
    config: dict,
    path: str,
    value: float,
    min_allowed: Optional[float] = None,
    max_allowed: Optional[float] = None,
) -> dict:
    """Return a deep copy of `config` with `value` written at `path`.

    If `min_allowed` / `max_allowed` are provided, raises BoundsError when
    `value` is out of range. The input `config` is never mutated.
    """
    if min_allowed is not None and value < min_allowed:
        raise BoundsError(f"{value} below min_allowed={min_allowed}")
    if max_allowed is not None and value > max_allowed:
        raise BoundsError(f"{value} above max_allowed={max_allowed}")

    segments = _parse_path(path)
    new_config = copy.deepcopy(config)
    _apply(new_config, segments, value)
    return new_config
```

- [ ] **Step 2.4: Run tests to verify passing**

Run: `pytest tests/test_parametric_path_resolver.py tests/test_parametric_parameters.py -v`
Expected: All path_resolver tests pass; remove the xfail marker from `test_all_whitelisted_paths_resolve_against_default_config` and rerun — it should now pass.

- [ ] **Step 2.5: Remove xfail marker**

Edit `tests/test_parametric_parameters.py`, remove the `@pytest.mark.xfail(...)` decorator added in Task 1 Step 1.6.

Run: `pytest tests/test_parametric_parameters.py tests/test_parametric_path_resolver.py -v`
Expected: All tests pass, no xfails.

- [ ] **Step 2.6: Commit**

```bash
git add engine_simulator/gui/parametric/path_resolver.py \
        tests/test_parametric_path_resolver.py \
        tests/test_parametric_parameters.py
git commit -m "feat(parametric): add dotted/wildcard path resolver

Get/set values in the engine config dict via paths like
'intake_pipes[*].length'. set_parameter is non-mutating (returns a deep
copy) and validates bounds when given."
```

---

## Phase 2 — Backend Study Execution

### Task 3: Pydantic request schema

**Files:**
- Create: `engine_simulator/gui/parametric/schema.py`
- Test: `tests/test_parametric_schema.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_parametric_schema.py`:

```python
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
```

- [ ] **Step 3.2: Run to verify failure**

Run: `pytest tests/test_parametric_schema.py -v`
Expected: ImportError.

- [ ] **Step 3.3: Implement `schema.py`**

Create `engine_simulator/gui/parametric/schema.py`:

```python
"""Pydantic request models for parametric study endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from engine_simulator.gui.parametric.parameters import find_parameter


def resolve_parameter_values(
    start: float, end: float, step: float
) -> list[float]:
    """Generate parameter values from (start, end, step), inclusive of end.

    Uses integer arithmetic on a scaled step to avoid floating-point drift
    at the endpoint.
    """
    if step <= 0:
        raise ValueError("step must be positive")
    if end < start:
        raise ValueError("end must be >= start")
    # Add a half-step tolerance to make sure the endpoint is included when
    # the range divides cleanly, without overshooting when it doesn't.
    n_steps = int(round((end - start) / step))
    return [start + i * step for i in range(n_steps + 1)]


class ParametricStudyStartRequest(BaseModel):
    """Request body for POST /api/parametric/study/start."""

    name: str = Field(..., min_length=1, max_length=200)
    config_name: str = Field(..., min_length=1)
    parameter_path: str = Field(..., min_length=1)

    value_start: float
    value_end: float
    value_step: float = Field(..., gt=0)

    sweep_rpm_start: float = Field(..., gt=0)
    sweep_rpm_end: float = Field(..., gt=0)
    sweep_rpm_step: float = Field(..., gt=0)
    sweep_n_cycles: int = Field(..., gt=0, le=100)
    n_workers: int = Field(..., gt=0, le=64)

    @field_validator("parameter_path")
    @classmethod
    def _path_in_whitelist(cls, v: str) -> str:
        if find_parameter(v) is None:
            raise ValueError(f"parameter_path {v!r} not in whitelist")
        return v

    @model_validator(mode="after")
    def _check_ranges(self):
        if self.sweep_rpm_end <= self.sweep_rpm_start:
            raise ValueError("sweep_rpm_end must be > sweep_rpm_start")
        if self.value_end <= self.value_start:
            raise ValueError("value_end must be > value_start")
        param = find_parameter(self.parameter_path)
        if param is None:
            return self  # already caught by field_validator
        if param.min_allowed is not None and self.value_start < param.min_allowed:
            raise ValueError(
                f"value_start={self.value_start} below min_allowed={param.min_allowed} "
                f"for {self.parameter_path}"
            )
        if param.max_allowed is not None and self.value_end > param.max_allowed:
            raise ValueError(
                f"value_end={self.value_end} above max_allowed={param.max_allowed} "
                f"for {self.parameter_path}"
            )
        return self

    def parameter_values(self) -> list[float]:
        return resolve_parameter_values(
            self.value_start, self.value_end, self.value_step
        )
```

- [ ] **Step 3.4: Run tests to verify passing**

Run: `pytest tests/test_parametric_schema.py -v`
Expected: All pass.

- [ ] **Step 3.5: Commit**

```bash
git add engine_simulator/gui/parametric/schema.py \
        tests/test_parametric_schema.py
git commit -m "feat(parametric): add Pydantic request schema

Validates parametric-study start requests: parameter path is in the
whitelist, RPM and value ranges are sane, values fall within the
parameter's safety bounds."
```

---

### Task 4: Study data model + persistence

**Files:**
- Create: `engine_simulator/gui/parametric/study_manager.py` (data classes only; manager in Task 6)
- Create: `engine_simulator/gui/parametric/persistence.py`
- Test: `tests/test_parametric_persistence.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_parametric_persistence.py`:

```python
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
```

- [ ] **Step 4.2: Run to verify failure**

Run: `pytest tests/test_parametric_persistence.py -v`
Expected: ImportError.

- [ ] **Step 4.3: Implement the study data classes**

Create `engine_simulator/gui/parametric/study_manager.py`:

```python
"""ParametricStudyManager — lifecycle owner for parametric studies.

This module holds the data classes only. The manager class itself is
added in a later task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class ParametricStudyDef:
    """User-submitted definition of a parametric study."""
    study_id: str
    name: str
    config_name: str
    parameter_path: str
    parameter_values: list[float]
    sweep_rpm_start: float
    sweep_rpm_end: float
    sweep_rpm_step: float
    sweep_n_cycles: int
    n_workers: int
    created_at: str


@dataclass
class ParametricRun:
    """Result of running the RPM sweep for a single parameter value."""
    parameter_value: float
    status: Literal["queued", "running", "done", "error"] = "queued"
    sweep_results: list[dict] = field(default_factory=list)
    per_rpm_delta: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


@dataclass
class LiveParametricStudy:
    """In-memory + persisted study state.

    Serializes directly to the on-disk JSON format.
    """
    definition: ParametricStudyDef
    status: Literal["running", "complete", "error", "stopped"] = "running"
    started_at: str = ""
    completed_at: Optional[str] = None
    runs: list[ParametricRun] = field(default_factory=list)
    error: Optional[str] = None
```

- [ ] **Step 4.4: Implement persistence**

Create `engine_simulator/gui/parametric/persistence.py`:

```python
"""Save/load LiveParametricStudy as JSON files under sweeps/parametric/.

Studies are stored separately from regular sweeps so the UI can list and
load them independently.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine_simulator.gui.parametric.study_manager import (
    LiveParametricStudy,
    ParametricRun,
    ParametricStudyDef,
)


SCHEMA_VERSION = 1


def _coerce_jsonable(obj: Any) -> Any:
    """Recursively coerce numpy scalars/arrays to plain Python and replace
    non-finite floats with None so the result is JSON.parse-safe in the
    browser.
    """
    import numpy as np
    if isinstance(obj, dict):
        return {str(k): _coerce_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_coerce_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _coerce_jsonable(obj.tolist())
    if isinstance(obj, np.floating):
        v = float(obj.item())
        return v if math.isfinite(v) else None
    if isinstance(obj, (np.integer, np.bool_)):
        return obj.item()
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


def save_study(study: LiveParametricStudy, studies_dir: str) -> str:
    """Save a study to `<studies_dir>/<study_id>.json`. Returns the filename."""
    Path(studies_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{study.definition.study_id}.json"
    path = Path(studies_dir) / filename

    payload = {
        "schema_version": SCHEMA_VERSION,
        "definition": asdict(study.definition),
        "status": study.status,
        "started_at": study.started_at,
        "completed_at": study.completed_at,
        "error": study.error,
        "runs": [asdict(run) for run in study.runs],
    }
    safe = _coerce_jsonable(payload)
    path.write_text(json.dumps(safe, indent=2))
    return filename


def load_study(path: str) -> LiveParametricStudy:
    """Load a study from the given JSON file path."""
    with open(path) as f:
        payload = json.load(f)

    def_data = payload["definition"]
    definition = ParametricStudyDef(**def_data)

    runs = [ParametricRun(**r) for r in payload.get("runs", [])]

    return LiveParametricStudy(
        definition=definition,
        status=payload.get("status", "complete"),
        started_at=payload.get("started_at", ""),
        completed_at=payload.get("completed_at"),
        runs=runs,
        error=payload.get("error"),
    )


def list_studies(studies_dir: str) -> list[dict]:
    """Return metadata for every saved study, newest first.

    Each entry:
    - study_id, name, parameter_path, created_at, status, run_count,
      parameter_values (count only)
    """
    dir_path = Path(studies_dir)
    if not dir_path.exists():
        return []

    items = []
    for path in sorted(dir_path.glob("*.json"), reverse=True):
        try:
            with open(path) as f:
                payload = json.load(f)
            def_ = payload.get("definition", {})
            items.append({
                "study_id": def_.get("study_id", path.stem),
                "name": def_.get("name", ""),
                "parameter_path": def_.get("parameter_path", ""),
                "n_values": len(def_.get("parameter_values", [])),
                "created_at": def_.get("created_at", ""),
                "status": payload.get("status", "unknown"),
                "run_count": len(payload.get("runs", [])),
            })
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    return items
```

- [ ] **Step 4.5: Run tests to verify passing**

Run: `pytest tests/test_parametric_persistence.py -v`
Expected: All pass.

- [ ] **Step 4.6: Commit**

```bash
git add engine_simulator/gui/parametric/study_manager.py \
        engine_simulator/gui/parametric/persistence.py \
        tests/test_parametric_persistence.py
git commit -m "feat(parametric): add study data model and persistence

LiveParametricStudy serializes to JSON under sweeps/parametric/. Uses
the same non-finite coercion pattern as the existing sweep persistence
so the browser can JSON.parse the result safely."
```

---

### Task 5: Event consumer bridge

**Files:**
- Create: `engine_simulator/gui/parametric/event_consumer.py`
- Test: `tests/test_parametric_event_consumer.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_parametric_event_consumer.py`:

```python
"""Tests for the ParametricEventConsumer bridge."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from engine_simulator.gui.parametric.event_consumer import (
    ParametricEventConsumer,
)
from engine_simulator.simulation.parallel_sweep import (
    CycleDoneEvent,
    RPMDoneEvent,
    RPMStartEvent,
)


@pytest.mark.asyncio
async def test_rpm_start_is_rebroadcast_on_parametric_channel():
    broadcast = AsyncMock()
    loop = asyncio.get_event_loop()
    consumer = ParametricEventConsumer(
        loop=loop,
        broadcast_fn=broadcast,
        study_id="param_test",
        parameter_value=0.25,
    )
    consumer.handle(RPMStartEvent(
        rpm=8000.0, rpm_index=2, n_cycles_target=4, ts=1.0,
    ))
    # Give the loop a chance to run the scheduled coroutine
    await asyncio.sleep(0.05)

    broadcast.assert_called_once()
    msg = broadcast.call_args[0][0]
    assert msg["channel"] == "parametric"
    assert msg["type"] == "parametric_rpm_start"
    assert msg["study_id"] == "param_test"
    assert msg["parameter_value"] == 0.25
    assert msg["rpm"] == 8000.0


@pytest.mark.asyncio
async def test_rpm_done_tagged_with_parameter_value():
    broadcast = AsyncMock()
    loop = asyncio.get_event_loop()
    consumer = ParametricEventConsumer(
        loop=loop,
        broadcast_fn=broadcast,
        study_id="param_test",
        parameter_value=0.30,
    )
    consumer.handle(RPMDoneEvent(
        rpm=9000.0,
        perf={"brake_power_hp": 70.0, "brake_torque_Nm": 60.0},
        elapsed=12.5, step_count=4500, converged=True, ts=2.0,
    ))
    await asyncio.sleep(0.05)

    broadcast.assert_called_once()
    msg = broadcast.call_args[0][0]
    assert msg["type"] == "parametric_rpm_done"
    assert msg["parameter_value"] == 0.30
    assert msg["perf"]["brake_power_hp"] == 70.0


@pytest.mark.asyncio
async def test_nonfinite_delta_coerced_to_none():
    broadcast = AsyncMock()
    loop = asyncio.get_event_loop()
    consumer = ParametricEventConsumer(
        loop=loop,
        broadcast_fn=broadcast,
        study_id="param_test",
        parameter_value=0.20,
    )
    consumer.handle(CycleDoneEvent(
        rpm=8000.0, cycle=1, delta=float("inf"),
        p_ivc=(90000.0, 91000.0, 90500.0, 91200.0),
        step_count=100, elapsed=1.5, ts=3.0,
    ))
    await asyncio.sleep(0.05)

    msg = broadcast.call_args[0][0]
    assert msg["delta"] is None
```

- [ ] **Step 5.2: Run to verify failure**

Run: `pytest tests/test_parametric_event_consumer.py -v`
Expected: ImportError.

- [ ] **Step 5.3: Implement `event_consumer.py`**

Create `engine_simulator/gui/parametric/event_consumer.py`:

```python
"""ParametricEventConsumer — bridges inner-sweep events onto the parametric channel.

Wraps the event stream from the underlying ParallelSweepRunner and
re-emits each event as a parametric_* WebSocket message tagged with the
current parameter_value. The inner sweep stays completely unaware it's
running inside a parametric study.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any, Callable

from engine_simulator.simulation.parallel_sweep import (
    ConvergedEvent,
    CycleDoneEvent,
    EventConsumer,
    ProgressEvent,
    RPMDoneEvent,
    RPMErrorEvent,
    RPMStartEvent,
)


def _safe_float(v):
    """Coerce non-finite floats to None so JSON stays valid."""
    if v is None:
        return None
    try:
        return v if math.isfinite(v) else None
    except TypeError:
        return None


def _coerce_perf(perf: dict) -> dict:
    """Replace non-finite floats in a perf dict with None."""
    import numpy as np
    out = {}
    for k, v in perf.items():
        if isinstance(v, (int, bool)):
            out[k] = v
        elif isinstance(v, float):
            out[k] = v if math.isfinite(v) else None
        elif isinstance(v, np.floating):
            f = float(v)
            out[k] = f if math.isfinite(f) else None
        elif isinstance(v, np.integer):
            out[k] = int(v)
        else:
            out[k] = v
    return out


class ParametricEventConsumer(EventConsumer):
    """Implements the EventConsumer protocol and re-broadcasts events
    onto the parametric WebSocket channel.

    Call sites run in the parallel-sweep pump thread (not the asyncio
    loop), so we use `asyncio.run_coroutine_threadsafe` to schedule the
    broadcast back onto the event loop.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        broadcast_fn: Callable,
        study_id: str,
        parameter_value: float,
    ):
        self._loop = loop
        self._broadcast = broadcast_fn
        self._study_id = study_id
        self._parameter_value = parameter_value

    def _dispatch(self, msg: dict) -> None:
        """Schedule an async broadcast from any thread."""
        msg.setdefault("channel", "parametric")
        msg.setdefault("study_id", self._study_id)
        msg.setdefault("parameter_value", self._parameter_value)
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)
        except RuntimeError:
            # Loop closed; silently drop.
            pass

    def handle(self, event: ProgressEvent) -> None:
        if isinstance(event, RPMStartEvent):
            self._dispatch({
                "type": "parametric_rpm_start",
                "rpm": event.rpm,
                "rpm_index": event.rpm_index,
                "n_cycles_target": event.n_cycles_target,
                "ts": event.ts,
            })
        elif isinstance(event, CycleDoneEvent):
            self._dispatch({
                "type": "parametric_rpm_cycle",
                "rpm": event.rpm,
                "cycle": event.cycle,
                "delta": _safe_float(event.delta),
                "step_count": event.step_count,
                "elapsed": event.elapsed,
                "ts": event.ts,
            })
        elif isinstance(event, ConvergedEvent):
            self._dispatch({
                "type": "parametric_rpm_converged",
                "rpm": event.rpm,
                "cycle": event.cycle,
                "ts": event.ts,
            })
        elif isinstance(event, RPMDoneEvent):
            self._dispatch({
                "type": "parametric_rpm_done",
                "rpm": event.rpm,
                "perf": _coerce_perf(event.perf),
                "elapsed": event.elapsed,
                "step_count": event.step_count,
                "converged": event.converged,
                "ts": event.ts,
            })
        elif isinstance(event, RPMErrorEvent):
            self._dispatch({
                "type": "parametric_rpm_error",
                "rpm": event.rpm,
                "error_type": event.error_type,
                "error_msg": event.error_msg,
                "traceback": event.traceback,
                "ts": event.ts,
            })

    def close(self) -> None:
        pass
```

- [ ] **Step 5.4: Run tests to verify passing**

Run: `pytest tests/test_parametric_event_consumer.py -v`
Expected: All pass.

- [ ] **Step 5.5: Commit**

```bash
git add engine_simulator/gui/parametric/event_consumer.py \
        tests/test_parametric_event_consumer.py
git commit -m "feat(parametric): add event consumer bridge

ParametricEventConsumer wraps the inner sweep's progress events and
re-broadcasts them on the parametric WebSocket channel with the current
parameter_value attached. Coerces non-finite floats so JSON stays
browser-safe."
```

---

### Task 6: `ParametricStudyManager` — lifecycle

**Files:**
- Modify: `engine_simulator/gui/parametric/study_manager.py` (add manager class)
- Test: `tests/test_parametric_study_manager.py`

- [ ] **Step 6.1: Write failing tests for the manager**

Create `tests/test_parametric_study_manager.py`:

```python
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
    loop = asyncio.get_event_loop()

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
    loop = asyncio.get_event_loop()

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
    loop = asyncio.get_event_loop()

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
```

- [ ] **Step 6.2: Run to verify failure**

Run: `pytest tests/test_parametric_study_manager.py -v`
Expected: ImportError — manager class doesn't exist yet.

- [ ] **Step 6.3: Extend `study_manager.py` with the manager class**

Append to `engine_simulator/gui/parametric/study_manager.py`:

```python


# ============================================================================
# Manager
# ============================================================================

import asyncio
import copy
import json
import logging
import threading
import traceback as _traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from engine_simulator.gui.parametric.event_consumer import (
    ParametricEventConsumer,
)
from engine_simulator.gui.parametric.path_resolver import (
    BoundsError,
    set_parameter,
)
from engine_simulator.gui.parametric.parameters import find_parameter
from engine_simulator.gui.parametric.persistence import save_study, load_study


logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load_config_dict(config_name: str) -> dict:
    """Load a config JSON file as a raw dict (not an EngineConfig instance)."""
    config_dir = Path(__file__).resolve().parents[2] / "config"
    path = config_dir / config_name
    with open(path) as f:
        return json.load(f)


def _config_from_dict(config_dict: dict):
    """Reconstruct an EngineConfig dataclass instance from a dict.

    Routes through the existing loader that parses the same JSON shape the
    config editor produces.
    """
    # Write the dict to a temporary file the loader can read, then delete.
    # This is the simplest path that guarantees the mutated dict goes
    # through exactly the same code path as a loaded file.
    import tempfile
    from engine_simulator.config.engine_config import load_config

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False,
    ) as f:
        json.dump(config_dict, f)
        tmp_path = f.name
    try:
        return load_config(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# Imported lazily so tests can patch it
from engine_simulator.simulation.orchestrator import (  # noqa: E402
    SimulationOrchestrator,
)


class ParametricStudyManager:
    """Owns the lifecycle of a parametric study.

    Single active study at a time. Spawns a background thread that runs
    one full RPM sweep per parameter value, mutating the base config
    between iterations via the path resolver.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        studies_dir: str,
        broadcast_fn: Callable,
    ):
        self._loop = loop
        self._studies_dir = studies_dir
        self._broadcast = broadcast_fn
        self._current: Optional[LiveParametricStudy] = None
        self._stop_flag = threading.Event()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="param-study",
        )
        self._study_task: Optional[asyncio.Task] = None

    def get_current(self) -> Optional[LiveParametricStudy]:
        return self._current

    def list_studies(self) -> list[dict]:
        from engine_simulator.gui.parametric.persistence import list_studies
        return list_studies(self._studies_dir)

    def load_study(self, study_id: str) -> LiveParametricStudy:
        path = Path(self._studies_dir) / f"{study_id}.json"
        state = load_study(str(path))
        self._current = state
        return state

    async def start_study(self, definition: ParametricStudyDef) -> str:
        if self._current is not None and self._current.status == "running":
            raise RuntimeError("A parametric study is already running.")

        self._current = LiveParametricStudy(
            definition=definition,
            status="running",
            started_at=_iso_now(),
            runs=[
                ParametricRun(parameter_value=v) for v in definition.parameter_values
            ],
        )
        self._stop_flag.clear()

        await self._broadcast_safe({
            "channel": "parametric",
            "type": "parametric_study_start",
            "study_id": definition.study_id,
            "definition": _definition_to_dict(definition),
        })

        self._study_task = asyncio.create_task(self._run_study())
        return definition.study_id

    async def stop_study(self) -> None:
        if self._current is None or self._current.status != "running":
            return
        self._stop_flag.set()
        if self._study_task is not None:
            try:
                await self._study_task
            except Exception:
                pass

    async def _run_study(self) -> None:
        """Orchestrate the entire study: one RPM sweep per parameter value."""
        try:
            await self._loop.run_in_executor(
                self._executor, self._run_study_blocking,
            )
            if self._stop_flag.is_set():
                self._current.status = "stopped"
            else:
                self._current.status = "complete"
            self._current.completed_at = _iso_now()
            # Persist
            try:
                save_study(self._current, self._studies_dir)
            except Exception:
                logger.exception("failed to save parametric study")
            await self._broadcast_safe({
                "channel": "parametric",
                "type": (
                    "parametric_study_stopped"
                    if self._stop_flag.is_set()
                    else "parametric_study_complete"
                ),
                "study_id": self._current.definition.study_id,
            })
        except Exception as exc:
            self._current.status = "error"
            self._current.error = str(exc)
            self._current.completed_at = _iso_now()
            await self._broadcast_safe({
                "channel": "parametric",
                "type": "parametric_study_error",
                "study_id": self._current.definition.study_id,
                "error_msg": str(exc),
                "traceback": _traceback.format_exc(),
            })

    def _run_study_blocking(self) -> None:
        """Synchronous study loop — runs in the executor thread."""
        definition = self._current.definition
        param = find_parameter(definition.parameter_path)
        if param is None:
            raise RuntimeError(
                f"parameter {definition.parameter_path!r} not in whitelist"
            )

        base_config_dict = _load_config_dict(definition.config_name)

        for idx, value in enumerate(definition.parameter_values):
            if self._stop_flag.is_set():
                return

            run = self._current.runs[idx]
            run.status = "running"
            self._schedule_broadcast({
                "channel": "parametric",
                "type": "parametric_value_start",
                "study_id": definition.study_id,
                "parameter_value": value,
                "value_index": idx,
            })

            start = datetime.now(timezone.utc)
            try:
                mutated_dict = set_parameter(
                    base_config_dict,
                    definition.parameter_path,
                    value,
                    min_allowed=param.min_allowed,
                    max_allowed=param.max_allowed,
                )
                config = _config_from_dict(mutated_dict)
                orchestrator = SimulationOrchestrator(config)

                consumer = ParametricEventConsumer(
                    loop=self._loop,
                    broadcast_fn=self._broadcast,
                    study_id=definition.study_id,
                    parameter_value=value,
                )

                sweep_results = orchestrator.run_rpm_sweep(
                    rpm_start=definition.sweep_rpm_start,
                    rpm_end=definition.sweep_rpm_end,
                    rpm_step=definition.sweep_rpm_step,
                    n_cycles=definition.sweep_n_cycles,
                    verbose=False,
                    n_workers=definition.n_workers,
                    consumer=consumer,
                )

                run.sweep_results = list(sweep_results)
                run.status = "done"
            except (BoundsError, Exception) as exc:
                run.status = "error"
                run.error = f"{type(exc).__name__}: {exc}\n{_traceback.format_exc()}"

            end = datetime.now(timezone.utc)
            run.elapsed_seconds = (end - start).total_seconds()

            self._schedule_broadcast({
                "channel": "parametric",
                "type": (
                    "parametric_value_done"
                    if run.status == "done"
                    else "parametric_value_error"
                ),
                "study_id": definition.study_id,
                "parameter_value": value,
                "value_index": idx,
                "run": _run_to_dict(run),
            })

    def _schedule_broadcast(self, msg: dict) -> None:
        """Thread-safe: schedule a broadcast on the event loop."""
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)
        except RuntimeError:
            pass

    async def _broadcast_safe(self, msg: dict) -> None:
        """Async broadcast with error swallowing."""
        try:
            await self._broadcast(msg)
        except Exception:
            logger.exception("broadcast failed")


def _definition_to_dict(d: ParametricStudyDef) -> dict:
    from dataclasses import asdict
    return asdict(d)


def _run_to_dict(r: ParametricRun) -> dict:
    from dataclasses import asdict
    from engine_simulator.gui.parametric.persistence import _coerce_jsonable
    return _coerce_jsonable(asdict(r))
```

- [ ] **Step 6.4: Run tests to verify passing**

Run: `pytest tests/test_parametric_study_manager.py -v`
Expected: All pass.

If the `_FakeOrchestrator` patch paths don't resolve, it's because the `SimulationOrchestrator` import is at module level and `patch` needs the exact attribute name where it's looked up. Verify the patch target matches the `from ... import SimulationOrchestrator` line in `study_manager.py`.

- [ ] **Step 6.5: Commit**

```bash
git add engine_simulator/gui/parametric/study_manager.py \
        tests/test_parametric_study_manager.py
git commit -m "feat(parametric): add ParametricStudyManager lifecycle

Owns the study execution loop: mutates the base config for each
parameter value, runs a full RPM sweep via the unchanged
SimulationOrchestrator, and isolates errors so one failing value
doesn't abort the whole study."
```

---

## Phase 3 — Backend API

### Task 7: REST routes

**Files:**
- Create: `engine_simulator/gui/routes_parametric.py`
- Test: `tests/test_parametric_routes.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/test_parametric_routes.py`:

```python
"""FastAPI route tests for the parametric study endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from engine_simulator.gui.server import create_app
from engine_simulator.gui import server as server_module
from engine_simulator.gui.parametric.study_manager import (
    LiveParametricStudy, ParametricRun, ParametricStudyDef,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = create_app()

    # Inject a fake parametric manager that tests can control
    fake = MagicMock()
    fake.start_study = AsyncMock(return_value="param_test")
    fake.stop_study = AsyncMock(return_value=None)
    fake.get_current = MagicMock(return_value=None)
    fake.list_studies = MagicMock(return_value=[])
    fake.load_study = MagicMock()

    server_module.parametric_manager = fake
    yield TestClient(app), fake
    server_module.parametric_manager = None


def test_list_parameters(client):
    tc, _ = client
    resp = tc.get("/api/parametric/parameters")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "path" in data[0]
    assert "label" in data[0]
    assert "default_range" in data[0]


def test_start_study_success(client):
    tc, fake = client
    body = {
        "name": "plenum sweep",
        "config_name": "cbr600rr.json",
        "parameter_path": "plenum.volume",
        "value_start": 0.001,
        "value_end": 0.003,
        "value_step": 0.001,
        "sweep_rpm_start": 6000,
        "sweep_rpm_end": 8000,
        "sweep_rpm_step": 1000,
        "sweep_n_cycles": 2,
        "n_workers": 1,
    }
    resp = tc.post("/api/parametric/study/start", json=body)
    assert resp.status_code == 200
    assert resp.json()["study_id"] == "param_test"
    fake.start_study.assert_called_once()


def test_start_study_rejects_unknown_parameter(client):
    tc, _ = client
    body = {
        "name": "bad sweep",
        "config_name": "cbr600rr.json",
        "parameter_path": "cylinder.bore",
        "value_start": 0.06,
        "value_end": 0.08,
        "value_step": 0.005,
        "sweep_rpm_start": 6000,
        "sweep_rpm_end": 8000,
        "sweep_rpm_step": 1000,
        "sweep_n_cycles": 2,
        "n_workers": 1,
    }
    resp = tc.post("/api/parametric/study/start", json=body)
    assert resp.status_code == 422


def test_stop_study(client):
    tc, fake = client
    resp = tc.post("/api/parametric/study/stop")
    assert resp.status_code == 200
    fake.stop_study.assert_awaited_once()


def test_list_studies_empty(client):
    tc, _ = client
    resp = tc.get("/api/parametric/studies")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_study_not_found(client):
    tc, fake = client
    fake.load_study.side_effect = FileNotFoundError("nope")
    resp = tc.get("/api/parametric/studies/missing")
    assert resp.status_code == 404
```

- [ ] **Step 7.2: Run to verify failure**

Run: `pytest tests/test_parametric_routes.py -v`
Expected: ImportError on the route module / `parametric_manager` attribute.

- [ ] **Step 7.3: Implement the routes**

Create `engine_simulator/gui/routes_parametric.py`:

```python
"""REST endpoints for parametric studies. Prefix: /api/parametric"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from engine_simulator.gui.parametric.parameters import (
    SWEEPABLE_PARAMETERS,
    to_api_dict,
)
from engine_simulator.gui.parametric.schema import ParametricStudyStartRequest
from engine_simulator.gui.parametric.study_manager import ParametricStudyDef


router = APIRouter(prefix="/api/parametric")

_ID_RE = re.compile(r"^[A-Za-z0-9_\-:.]+$")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _make_study_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return f"param_{ts}"


@router.get("/parameters")
async def list_parameters():
    return [to_api_dict(p) for p in SWEEPABLE_PARAMETERS]


@router.get("/studies")
async def list_studies():
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        return []
    return server.parametric_manager.list_studies()


@router.get("/studies/{study_id}")
async def get_study(study_id: str):
    if not _ID_RE.match(study_id):
        raise HTTPException(status_code=400, detail=f"invalid id: {study_id!r}")
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        raise HTTPException(status_code=503, detail="manager not initialized")
    try:
        state = server.parametric_manager.load_study(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"study not found: {study_id}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Return the raw JSON (the study file is already in the browser-safe shape).
    studies_dir = Path(server.parametric_manager._studies_dir)
    file_path = studies_dir / f"{study_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="study file missing")
    import json
    with open(file_path) as f:
        return json.load(f)


@router.delete("/studies/{study_id}")
async def delete_study(study_id: str):
    if not _ID_RE.match(study_id):
        raise HTTPException(status_code=400, detail=f"invalid id: {study_id!r}")
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        raise HTTPException(status_code=503, detail="manager not initialized")
    studies_dir = Path(server.parametric_manager._studies_dir)
    file_path = studies_dir / f"{study_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="study not found")
    file_path.unlink()
    return {"deleted": study_id}


@router.post("/study/start")
async def start_study(req: ParametricStudyStartRequest):
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        raise HTTPException(status_code=503, detail="manager not initialized")

    definition = ParametricStudyDef(
        study_id=_make_study_id(),
        name=req.name,
        config_name=req.config_name,
        parameter_path=req.parameter_path,
        parameter_values=req.parameter_values(),
        sweep_rpm_start=req.sweep_rpm_start,
        sweep_rpm_end=req.sweep_rpm_end,
        sweep_rpm_step=req.sweep_rpm_step,
        sweep_n_cycles=req.sweep_n_cycles,
        n_workers=req.n_workers,
        created_at=_iso_now(),
    )

    try:
        study_id = await server.parametric_manager.start_study(definition)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"study_id": study_id, "status": "running"}


@router.post("/study/stop")
async def stop_study():
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        return {"status": "stopped"}
    await server.parametric_manager.stop_study()
    return {"status": "stopped"}


@router.get("/study/current")
async def get_current_study():
    from engine_simulator.gui import server
    if server.parametric_manager is None:
        return None
    current = server.parametric_manager.get_current()
    if current is None:
        return None
    from engine_simulator.gui.parametric.study_manager import _run_to_dict, _definition_to_dict
    return {
        "definition": _definition_to_dict(current.definition),
        "status": current.status,
        "started_at": current.started_at,
        "completed_at": current.completed_at,
        "error": current.error,
        "runs": [_run_to_dict(r) for r in current.runs],
    }
```

- [ ] **Step 7.4: Wire `parametric_manager` into server.py**

Edit `engine_simulator/gui/server.py`:

Add after the `sweep_manager = None` module-level declaration:

```python
parametric_manager = None
```

Inside the `lifespan` function, after the `SweepManager` initialization block, add:

```python
    try:
        from engine_simulator.gui.parametric.study_manager import (
            ParametricStudyManager,
        )
        parametric_sweeps_dir = str(
            Path(__file__).resolve().parents[2] / "sweeps" / "parametric"
        )
        Path(parametric_sweeps_dir).mkdir(parents=True, exist_ok=True)
        parametric_manager = ParametricStudyManager(
            loop=loop,
            studies_dir=parametric_sweeps_dir,
            broadcast_fn=broadcast,
        )
    except ImportError:
        logger.warning("ParametricStudyManager not yet available")
        parametric_manager = None
```

Inside `create_app()`, after the existing `app.include_router(routes_ws.router)` line, add:

```python
    from engine_simulator.gui import routes_parametric
    app.include_router(routes_parametric.router)
```

- [ ] **Step 7.5: Run tests to verify passing**

Run: `pytest tests/test_parametric_routes.py -v`
Expected: All pass.

- [ ] **Step 7.6: Commit**

```bash
git add engine_simulator/gui/routes_parametric.py \
        engine_simulator/gui/server.py \
        tests/test_parametric_routes.py
git commit -m "feat(parametric): add REST endpoints and server wiring

Exposes the parametric study manager via /api/parametric/* routes:
list parameters, list/load/delete studies, start/stop a study, and
fetch the current in-flight study snapshot."
```

---

### Task 8: Integration test (real orchestrator, tiny study)

**Files:**
- Test: `tests/test_parametric_integration.py`

- [ ] **Step 8.1: Write integration test**

Create `tests/test_parametric_integration.py`:

```python
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

    loop = asyncio.get_event_loop()
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
    assert current.status == "complete"
    assert len(current.runs) == 2

    for run in current.runs:
        assert run.status == "done", f"run failed: {run.error}"
        assert len(run.sweep_results) == 2
        # Basic sanity: brake_power_hp is present and positive
        for perf in run.sweep_results:
            assert perf["brake_power_hp"] > 0
            assert perf["brake_torque_Nm"] > 0

    # Persisted file exists
    assert (tmp_path / "param_integration.json").exists()

    # At least one parametric message was broadcast
    parametric_msgs = [m for m in messages if m.get("channel") == "parametric"]
    assert len(parametric_msgs) > 0
    assert any(m["type"] == "parametric_study_complete" for m in parametric_msgs)
```

- [ ] **Step 8.2: Run the integration test**

Run: `pytest tests/test_parametric_integration.py -v -s`
Expected: Passes in 30-120 seconds depending on hardware.

If it hangs or fails, the most likely causes are:
1. `_config_from_dict` not producing a valid EngineConfig for the solver — inspect the temp file it writes
2. Event consumer broadcasting into a closed loop — check the `asyncio.run_coroutine_threadsafe` error handling

- [ ] **Step 8.3: Commit**

```bash
git add tests/test_parametric_integration.py
git commit -m "test(parametric): add end-to-end integration test

Runs a real 2-value × 2-RPM × 1-cycle study through the full stack to
catch wiring bugs the mocked unit tests would miss."
```

---

## Phase 4 — Frontend Plumbing

### Task 9: TypeScript types

**Files:**
- Create: `gui-frontend/src/types/parametric.ts`

- [ ] **Step 9.1: Create the parametric types module**

Create `gui-frontend/src/types/parametric.ts`:

```typescript
/**
 * TypeScript mirrors of the backend parametric schema. Must stay in
 * sync with engine_simulator/gui/parametric/parameters.py and
 * study_manager.py.
 */

export interface Param {
  path: string;
  label: string;
  unit: string;
  default_range: [number, number, number];
  display_scale: number;
  min_allowed: number | null;
  max_allowed: number | null;
  category: string;
}

export interface ParametricStudyDef {
  study_id: string;
  name: string;
  config_name: string;
  parameter_path: string;
  parameter_values: number[];
  sweep_rpm_start: number;
  sweep_rpm_end: number;
  sweep_rpm_step: number;
  sweep_n_cycles: number;
  n_workers: number;
  created_at: string;
}

export type RunStatus = "queued" | "running" | "done" | "error";

export interface PerfDict {
  rpm: number;
  brake_power_hp?: number;
  brake_torque_Nm?: number;
  indicated_power_hp?: number;
  wheel_power_hp?: number;
  volumetric_efficiency_atm?: number;
  volumetric_efficiency_plenum?: number;
  plenum_pressure_bar?: number;
  imep_bar?: number;
  bmep_bar?: number;
  [key: string]: number | boolean | undefined;
}

export interface ParametricRun {
  parameter_value: number;
  status: RunStatus;
  sweep_results: PerfDict[];
  per_rpm_delta: Record<string, number>;
  elapsed_seconds: number;
  error: string | null;
}

export type StudyStatus = "running" | "complete" | "error" | "stopped";

export interface LiveParametricStudy {
  definition: ParametricStudyDef;
  status: StudyStatus;
  started_at: string;
  completed_at: string | null;
  error: string | null;
  runs: ParametricRun[];
}

export interface ParametricStudySummary {
  study_id: string;
  name: string;
  parameter_path: string;
  n_values: number;
  created_at: string;
  status: StudyStatus;
  run_count: number;
}

export type ObjectiveKey =
  | "peak_power"
  | "peak_torque"
  | "torque_area"
  | "power_at_rpm"
  | "torque_at_rpm";

export interface RunMetrics {
  peak_power_hp: number | null;
  peak_power_rpm: number | null;
  peak_torque_Nm: number | null;
  peak_torque_rpm: number | null;
  torque_area: number | null;
  power_at_rpm: number | null;
  torque_at_rpm: number | null;
  ve_peak: number | null;
  ve_avg: number | null;
}

export interface ComparisonRow {
  index: number;
  parameter_value: number;
  metrics: RunMetrics;
  status: RunStatus;
  rank: number | null;
  isBest: boolean;
  error: string | null;
}

// ---- WebSocket events ----

interface ParametricBase {
  channel: "parametric";
  study_id: string;
}

export type ParametricServerMessage =
  | (ParametricBase & {
      type: "parametric_snapshot";
      study: LiveParametricStudy | null;
    })
  | (ParametricBase & {
      type: "parametric_study_start";
      definition: ParametricStudyDef;
    })
  | (ParametricBase & {
      type: "parametric_value_start";
      parameter_value: number;
      value_index: number;
    })
  | (ParametricBase & {
      type: "parametric_rpm_start";
      parameter_value: number;
      rpm: number;
      rpm_index: number;
      n_cycles_target: number;
    })
  | (ParametricBase & {
      type: "parametric_rpm_cycle";
      parameter_value: number;
      rpm: number;
      cycle: number;
      delta: number | null;
      step_count: number;
      elapsed: number;
    })
  | (ParametricBase & {
      type: "parametric_rpm_done";
      parameter_value: number;
      rpm: number;
      perf: PerfDict;
      elapsed: number;
      converged: boolean;
    })
  | (ParametricBase & {
      type: "parametric_value_done";
      parameter_value: number;
      value_index: number;
      run: ParametricRun;
    })
  | (ParametricBase & {
      type: "parametric_value_error";
      parameter_value: number;
      value_index: number;
      error_msg: string;
    })
  | (ParametricBase & { type: "parametric_study_complete" })
  | (ParametricBase & { type: "parametric_study_stopped" })
  | (ParametricBase & { type: "parametric_study_error"; error_msg: string });
```

- [ ] **Step 9.2: Verify TypeScript compiles**

Run: `cd gui-frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 9.3: Commit**

```bash
git add gui-frontend/src/types/parametric.ts
git commit -m "feat(parametric): add frontend TypeScript types

Mirrors of the backend parametric schema plus ObjectiveKey and
ComparisonRow types used by the UI layer."
```

---

### Task 10: API client methods

**Files:**
- Modify: `gui-frontend/src/api/client.ts`

- [ ] **Step 10.1: Add parametric API methods**

Edit `gui-frontend/src/api/client.ts`. At the top of the file, add the parametric type imports:

```typescript
import type {
  Param,
  LiveParametricStudy,
  ParametricStudySummary,
} from "../types/parametric";
```

Add this type alias just before the `export const api = {` line:

```typescript
export interface StartParametricStudyParams {
  name: string;
  config_name: string;
  parameter_path: string;
  value_start: number;
  value_end: number;
  value_step: number;
  sweep_rpm_start: number;
  sweep_rpm_end: number;
  sweep_rpm_step: number;
  sweep_n_cycles: number;
  n_workers: number;
}
```

Inside the `api` object (after the `downloadReport` method), add:

```typescript
  // ---- Parametric studies ----

  listParametricParameters: () =>
    jsonFetch<Param[]>("/api/parametric/parameters"),

  listParametricStudies: () =>
    jsonFetch<ParametricStudySummary[]>("/api/parametric/studies"),

  loadParametricStudy: (id: string) =>
    jsonFetch<LiveParametricStudy>(
      `/api/parametric/studies/${encodeURIComponent(id)}`,
    ),

  deleteParametricStudy: (id: string) =>
    jsonFetch<{ deleted: string }>(
      `/api/parametric/studies/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),

  getCurrentParametricStudy: () =>
    jsonFetch<LiveParametricStudy | null>("/api/parametric/study/current"),

  startParametricStudy: (params: StartParametricStudyParams) =>
    jsonFetch<{ study_id: string; status: string }>(
      "/api/parametric/study/start",
      {
        method: "POST",
        body: JSON.stringify(params),
      },
    ),

  stopParametricStudy: () =>
    jsonFetch<{ status: string }>("/api/parametric/study/stop", {
      method: "POST",
    }),
```

- [ ] **Step 10.2: Verify TypeScript compiles**

Run: `cd gui-frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 10.3: Commit**

```bash
git add gui-frontend/src/api/client.ts
git commit -m "feat(parametric): add API client methods"
```

---

### Task 11: Parametric Zustand store

**Files:**
- Create: `gui-frontend/src/state/parametricStore.ts`

- [ ] **Step 11.1: Create the store**

Create `gui-frontend/src/state/parametricStore.ts`:

```typescript
import { create } from "zustand";
import type {
  LiveParametricStudy,
  ObjectiveKey,
  Param,
  ParametricRun,
  ParametricStudySummary,
  PerfDict,
} from "../types/parametric";

interface ParametricState {
  // Current live or loaded study
  current: LiveParametricStudy | null;

  // Past studies list (sidebar)
  studies: ParametricStudySummary[];
  studiesLoading: boolean;
  studiesError: string | null;

  // Sweepable parameters (loaded once at mount)
  availableParameters: Param[];
  parametersLoaded: boolean;

  // Results-view UI state
  selectedObjective: ObjectiveKey;
  objectiveRpm: number;
  objectiveRpmWindow: [number, number];
  selectedRunIndices: Set<number>;
  highlightedRunIndex: number | null;

  // Setter actions
  setCurrent: (study: LiveParametricStudy | null) => void;
  setStudies: (studies: ParametricStudySummary[]) => void;
  setStudiesLoading: (loading: boolean) => void;
  setStudiesError: (err: string | null) => void;
  setAvailableParameters: (params: Param[]) => void;
  setSelectedObjective: (obj: ObjectiveKey) => void;
  setObjectiveRpm: (rpm: number) => void;
  setObjectiveRpmWindow: (w: [number, number]) => void;
  toggleRunSelected: (index: number) => void;
  selectAllRuns: () => void;
  clearSelectedRuns: () => void;
  setHighlightedRun: (index: number | null) => void;
  clearCurrent: () => void;

  // Reducer-invoked mutations (internal to eventReducer)
  _applyStudyStart: (
    study_id: string,
    definition: LiveParametricStudy["definition"],
  ) => void;
  _applyValueStart: (value_index: number) => void;
  _applyRpmDone: (
    value_index: number,
    rpm: number,
    perf: PerfDict,
  ) => void;
  _applyValueDone: (value_index: number, run: ParametricRun) => void;
  _applyValueError: (
    value_index: number,
    error_msg: string,
  ) => void;
  _applyStudyComplete: () => void;
  _applyStudyStopped: () => void;
  _applyStudyError: (error_msg: string) => void;
}

export const useParametricStore = create<ParametricState>((set, get) => ({
  current: null,
  studies: [],
  studiesLoading: false,
  studiesError: null,
  availableParameters: [],
  parametersLoaded: false,

  selectedObjective: "peak_power",
  objectiveRpm: 9000,
  objectiveRpmWindow: [6000, 12000],
  selectedRunIndices: new Set<number>(),
  highlightedRunIndex: null,

  setCurrent: (study) => {
    const selected = new Set<number>();
    if (study) {
      study.runs.forEach((_, i) => selected.add(i));
    }
    set({ current: study, selectedRunIndices: selected });
  },
  setStudies: (studies) => set({ studies }),
  setStudiesLoading: (studiesLoading) => set({ studiesLoading }),
  setStudiesError: (studiesError) => set({ studiesError }),
  setAvailableParameters: (availableParameters) =>
    set({ availableParameters, parametersLoaded: true }),
  setSelectedObjective: (selectedObjective) => set({ selectedObjective }),
  setObjectiveRpm: (objectiveRpm) => set({ objectiveRpm }),
  setObjectiveRpmWindow: (objectiveRpmWindow) => set({ objectiveRpmWindow }),
  toggleRunSelected: (index) => {
    const next = new Set(get().selectedRunIndices);
    if (next.has(index)) {
      next.delete(index);
    } else {
      next.add(index);
    }
    set({ selectedRunIndices: next });
  },
  selectAllRuns: () => {
    const current = get().current;
    if (!current) return;
    const next = new Set<number>();
    current.runs.forEach((_, i) => next.add(i));
    set({ selectedRunIndices: next });
  },
  clearSelectedRuns: () => set({ selectedRunIndices: new Set() }),
  setHighlightedRun: (highlightedRunIndex) => set({ highlightedRunIndex }),
  clearCurrent: () =>
    set({
      current: null,
      selectedRunIndices: new Set(),
      highlightedRunIndex: null,
    }),

  _applyStudyStart: (study_id, definition) => {
    set({
      current: {
        definition,
        status: "running",
        started_at: new Date().toISOString(),
        completed_at: null,
        error: null,
        runs: definition.parameter_values.map((v) => ({
          parameter_value: v,
          status: "queued" as const,
          sweep_results: [],
          per_rpm_delta: {},
          elapsed_seconds: 0,
          error: null,
        })),
      },
      selectedRunIndices: new Set(
        definition.parameter_values.map((_, i) => i),
      ),
    });
  },

  _applyValueStart: (value_index) => {
    const current = get().current;
    if (!current) return;
    const runs = current.runs.map((r, i) =>
      i === value_index ? { ...r, status: "running" as const } : r,
    );
    set({ current: { ...current, runs } });
  },

  _applyRpmDone: (value_index, rpm, perf) => {
    const current = get().current;
    if (!current) return;
    const runs = current.runs.map((r, i) => {
      if (i !== value_index) return r;
      const existingIdx = r.sweep_results.findIndex((p) => p.rpm === rpm);
      const nextResults =
        existingIdx >= 0
          ? r.sweep_results.map((p, j) => (j === existingIdx ? perf : p))
          : [...r.sweep_results, perf];
      // Keep sorted by RPM so charts render correctly
      nextResults.sort((a, b) => a.rpm - b.rpm);
      return { ...r, sweep_results: nextResults };
    });
    set({ current: { ...current, runs } });
  },

  _applyValueDone: (value_index, run) => {
    const current = get().current;
    if (!current) return;
    const runs = current.runs.map((r, i) => (i === value_index ? run : r));
    set({ current: { ...current, runs } });
  },

  _applyValueError: (value_index, error_msg) => {
    const current = get().current;
    if (!current) return;
    const runs = current.runs.map((r, i) =>
      i === value_index
        ? { ...r, status: "error" as const, error: error_msg }
        : r,
    );
    set({ current: { ...current, runs } });
  },

  _applyStudyComplete: () => {
    const current = get().current;
    if (!current) return;
    set({
      current: {
        ...current,
        status: "complete",
        completed_at: new Date().toISOString(),
      },
    });
  },

  _applyStudyStopped: () => {
    const current = get().current;
    if (!current) return;
    set({
      current: {
        ...current,
        status: "stopped",
        completed_at: new Date().toISOString(),
      },
    });
  },

  _applyStudyError: (error_msg) => {
    const current = get().current;
    if (!current) return;
    set({
      current: {
        ...current,
        status: "error",
        error: error_msg,
        completed_at: new Date().toISOString(),
      },
    });
  },
}));
```

- [ ] **Step 11.2: Verify TypeScript compiles**

Run: `cd gui-frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 11.3: Commit**

```bash
git add gui-frontend/src/state/parametricStore.ts
git commit -m "feat(parametric): add parametricStore

Zustand store for the parametric tab: current live/loaded study,
results-view UI state (objective, run selection, highlight), and
reducer mutations for each parametric WebSocket event."
```

---

### Task 12: Derived-data selectors

**Files:**
- Create: `gui-frontend/src/state/parametricSelectors.ts`

- [ ] **Step 12.1: Create the selector module**

Create `gui-frontend/src/state/parametricSelectors.ts`:

```typescript
/**
 * Pure derived-data functions for the parametric tab.
 *
 * These are NOT stored in state. They take study data + UI controls
 * (objective, RPM window) and return computed views. This lets the
 * user change the objective and have the ranking re-compute instantly
 * without re-fetching anything.
 */

import type {
  ComparisonRow,
  LiveParametricStudy,
  ObjectiveKey,
  ParametricRun,
  PerfDict,
  RunMetrics,
} from "../types/parametric";

const EPSILON = 1e-9;

function getNum(perf: PerfDict, key: string): number | null {
  const v = perf[key];
  if (typeof v !== "number") return null;
  if (!Number.isFinite(v)) return null;
  return v;
}

function peakOf(
  run: ParametricRun,
  key: string,
): { value: number; rpm: number } | null {
  let best: { value: number; rpm: number } | null = null;
  for (const perf of run.sweep_results) {
    const v = getNum(perf, key);
    if (v === null) continue;
    if (best === null || v > best.value) {
      best = { value: v, rpm: perf.rpm };
    }
  }
  return best;
}

function interpolate(
  run: ParametricRun,
  key: string,
  targetRpm: number,
): number | null {
  const results = run.sweep_results.filter(
    (p) => getNum(p, key) !== null,
  );
  if (results.length === 0) return null;
  if (results.length === 1) {
    return getNum(results[0], key);
  }
  // results are already sorted by RPM (store guarantees it)
  if (targetRpm <= results[0].rpm) return getNum(results[0], key);
  if (targetRpm >= results[results.length - 1].rpm) {
    return getNum(results[results.length - 1], key);
  }
  for (let i = 0; i < results.length - 1; i++) {
    const a = results[i];
    const b = results[i + 1];
    if (targetRpm >= a.rpm && targetRpm <= b.rpm) {
      const aVal = getNum(a, key)!;
      const bVal = getNum(b, key)!;
      const t = (targetRpm - a.rpm) / (b.rpm - a.rpm + EPSILON);
      return aVal + t * (bVal - aVal);
    }
  }
  return null;
}

function torqueAreaOver(
  run: ParametricRun,
  window: [number, number],
): number | null {
  const [lo, hi] = window;
  // Use trapezoidal integration over the points inside the window
  const points = run.sweep_results
    .filter((p) => p.rpm >= lo && p.rpm <= hi)
    .slice()
    .sort((a, b) => a.rpm - b.rpm);
  if (points.length < 2) return null;

  let area = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const aT = getNum(a, "brake_torque_Nm");
    const bT = getNum(b, "brake_torque_Nm");
    if (aT === null || bT === null) continue;
    area += ((aT + bT) / 2) * (b.rpm - a.rpm);
  }
  return area;
}

function avgVe(run: ParametricRun): number | null {
  const values = run.sweep_results
    .map((p) => getNum(p, "volumetric_efficiency_atm"))
    .filter((v): v is number => v !== null);
  if (values.length === 0) return null;
  return values.reduce((s, v) => s + v, 0) / values.length;
}

export function computeRunMetrics(
  run: ParametricRun,
  objectiveRpm: number,
  objectiveRpmWindow: [number, number],
): RunMetrics {
  const peakPower = peakOf(run, "brake_power_hp");
  const peakTorque = peakOf(run, "brake_torque_Nm");
  const peakVe = peakOf(run, "volumetric_efficiency_atm");

  return {
    peak_power_hp: peakPower?.value ?? null,
    peak_power_rpm: peakPower?.rpm ?? null,
    peak_torque_Nm: peakTorque?.value ?? null,
    peak_torque_rpm: peakTorque?.rpm ?? null,
    torque_area: torqueAreaOver(run, objectiveRpmWindow),
    power_at_rpm: interpolate(run, "brake_power_hp", objectiveRpm),
    torque_at_rpm: interpolate(run, "brake_torque_Nm", objectiveRpm),
    ve_peak: peakVe?.value ?? null,
    ve_avg: avgVe(run),
  };
}

function metricForObjective(
  metrics: RunMetrics,
  objective: ObjectiveKey,
): number | null {
  switch (objective) {
    case "peak_power":
      return metrics.peak_power_hp;
    case "peak_torque":
      return metrics.peak_torque_Nm;
    case "torque_area":
      return metrics.torque_area;
    case "power_at_rpm":
      return metrics.power_at_rpm;
    case "torque_at_rpm":
      return metrics.torque_at_rpm;
  }
}

export function computeComparisonTable(
  study: LiveParametricStudy,
  objective: ObjectiveKey,
  objectiveRpm: number,
  objectiveRpmWindow: [number, number],
): ComparisonRow[] {
  const rows: ComparisonRow[] = study.runs.map((run, index) => ({
    index,
    parameter_value: run.parameter_value,
    metrics: computeRunMetrics(run, objectiveRpm, objectiveRpmWindow),
    status: run.status,
    rank: null,
    isBest: false,
    error: run.error,
  }));

  // Rank only successful runs by the selected objective (descending).
  const ranked = rows
    .filter((r) => r.status === "done")
    .map((r) => ({
      row: r,
      score: metricForObjective(r.metrics, objective),
    }))
    .filter((entry): entry is { row: ComparisonRow; score: number } =>
      entry.score !== null && Number.isFinite(entry.score),
    )
    .sort((a, b) => b.score - a.score);

  ranked.forEach((entry, i) => {
    entry.row.rank = i + 1;
    if (i === 0) entry.row.isBest = true;
  });

  // Return: ranked successes first, then errored runs at the bottom
  return [
    ...ranked.map((e) => e.row),
    ...rows.filter((r) => r.status !== "done" || r.rank === null),
  ];
}

export interface HeatmapData {
  parameterValues: number[];
  rpms: number[];
  values: (number | null)[][]; // [parameter_value_index][rpm_index]
  metricKey: string;
}

export function computeHeatmapData(
  study: LiveParametricStudy,
  metricKey: string,
): HeatmapData {
  // Collect the union of RPMs across all runs, sorted
  const rpmSet = new Set<number>();
  for (const run of study.runs) {
    for (const perf of run.sweep_results) {
      rpmSet.add(perf.rpm);
    }
  }
  const rpms = Array.from(rpmSet).sort((a, b) => a - b);

  // Sort by parameter value ascending
  const sortedRuns = study.runs
    .map((r, idx) => ({ run: r, idx }))
    .sort((a, b) => a.run.parameter_value - b.run.parameter_value);

  const parameterValues = sortedRuns.map((e) => e.run.parameter_value);

  const values: (number | null)[][] = sortedRuns.map(({ run }) => {
    return rpms.map((rpm) => {
      const perf = run.sweep_results.find((p) => p.rpm === rpm);
      if (!perf) return null;
      return getNum(perf, metricKey);
    });
  });

  return { parameterValues, rpms, values, metricKey };
}
```

- [ ] **Step 12.2: Verify TypeScript compiles**

Run: `cd gui-frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 12.3: Commit**

```bash
git add gui-frontend/src/state/parametricSelectors.ts
git commit -m "feat(parametric): add derived-data selectors

Pure functions to compute run metrics, comparison table ranking, and
heatmap data from a LiveParametricStudy. Kept separate from the store
so objective/window changes re-rank instantly without re-fetching."
```

---

### Task 13: Event reducer extension + configStore tab type

**Files:**
- Modify: `gui-frontend/src/state/eventReducer.ts`
- Modify: `gui-frontend/src/state/configStore.ts`

- [ ] **Step 13.1: Add "parametric" to the ActiveTab type**

In `gui-frontend/src/state/configStore.ts`, find the `ActiveTab` type declaration (search for `ActiveTab`). Change:

```typescript
export type ActiveTab = "simulation" | "config" | "dyno";
```

to:

```typescript
export type ActiveTab = "simulation" | "config" | "dyno" | "parametric";
```

- [ ] **Step 13.2: Route parametric messages in the event reducer**

Edit `gui-frontend/src/state/eventReducer.ts`. Add this import at the top:

```typescript
import { useParametricStore } from "./parametricStore";
import type { ParametricServerMessage } from "../types/parametric";
```

At the start of `applyServerMessage`, add the channel guard BEFORE the existing `switch`:

```typescript
export function applyServerMessage(msg: ServerMessage): void {
  // Parametric channel: route to the parametric store, don't touch the
  // sweep store.
  if ((msg as { channel?: string }).channel === "parametric") {
    handleParametricMessage(msg as unknown as ParametricServerMessage);
    return;
  }

  const store = useSweepStore.getState();
  // ... existing switch unchanged
```

Then add this function at the bottom of the file:

```typescript
function handleParametricMessage(msg: ParametricServerMessage): void {
  const store = useParametricStore.getState();
  switch (msg.type) {
    case "parametric_snapshot":
      store.setCurrent(msg.study);
      break;

    case "parametric_study_start":
      store._applyStudyStart(msg.study_id, msg.definition);
      break;

    case "parametric_value_start":
      store._applyValueStart(msg.value_index);
      break;

    case "parametric_rpm_start":
      // No state mutation — a run is already "running" from value_start.
      // UI components that want the current rpm can subscribe to
      // parametric_rpm_cycle instead.
      break;

    case "parametric_rpm_cycle":
      // No-op for now; the final perf dict arrives in parametric_rpm_done.
      break;

    case "parametric_rpm_done": {
      // parametric_rpm_done does not carry value_index — locate the run
      // by parameter_value instead.
      const current = store.current;
      if (!current) break;
      const idx = current.runs.findIndex(
        (r) => r.parameter_value === msg.parameter_value,
      );
      if (idx >= 0) {
        store._applyRpmDone(idx, msg.rpm, msg.perf);
      }
      break;
    }

    case "parametric_value_done":
      store._applyValueDone(msg.value_index, msg.run);
      break;

    case "parametric_value_error":
      store._applyValueError(msg.value_index, msg.error_msg);
      break;

    case "parametric_study_complete":
      store._applyStudyComplete();
      break;

    case "parametric_study_stopped":
      store._applyStudyStopped();
      break;

    case "parametric_study_error":
      store._applyStudyError(msg.error_msg);
      break;
  }
}
```

- [ ] **Step 13.3: Verify TypeScript compiles**

Run: `cd gui-frontend && npx tsc --noEmit`
Expected: No errors. If the `ServerMessage` union complains about missing `channel`, add `channel?: string` to its base type definition in `types/events.ts`.

- [ ] **Step 13.4: Commit**

```bash
git add gui-frontend/src/state/eventReducer.ts \
        gui-frontend/src/state/configStore.ts
git commit -m "feat(parametric): route channel-tagged events to parametric store

Extends eventReducer with a channel guard at the top that routes any
message carrying 'channel: parametric' to a dedicated handler. The
regular sweep reducer is untouched. Adds 'parametric' to the ActiveTab
union."
```

---

## Phase 5 — Frontend UI

### Task 14: Tab plumbing (TabBar, App routing, ParametricView shell)

**Files:**
- Modify: `gui-frontend/src/components/TabBar.tsx`
- Modify: `gui-frontend/src/App.tsx`
- Create: `gui-frontend/src/components/parametric/ParametricView.tsx`

- [ ] **Step 14.1: Add the 4th tab**

Edit `gui-frontend/src/components/TabBar.tsx`. Change the `TABS` constant:

```typescript
const TABS: TabDef[] = [
  { id: "simulation", label: "Simulation", index: "01" },
  { id: "config", label: "Config", index: "02" },
  { id: "dyno", label: "Dyno", index: "03" },
  { id: "parametric", label: "Parametric", index: "04" },
];
```

- [ ] **Step 14.2: Create the ParametricView shell**

Create `gui-frontend/src/components/parametric/ParametricView.tsx`:

```typescript
import { useEffect } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { api } from "../../api/client";
import ParametricSetupForm from "./ParametricSetupForm";
import ParametricRunGrid from "./ParametricRunGrid";
import ParametricResultsView from "./ParametricResultsView";

/**
 * Root component for the Parametric tab. Routes between three modes
 * based on the store state:
 *  - Mode A (setup): no current study
 *  - Mode B (running): current study status is "running"
 *  - Mode C (results): current study status is "complete"/"stopped"/"error"
 */
export default function ParametricView() {
  const current = useParametricStore((s) => s.current);
  const parametersLoaded = useParametricStore((s) => s.parametersLoaded);
  const setAvailableParameters = useParametricStore(
    (s) => s.setAvailableParameters,
  );
  const setStudies = useParametricStore((s) => s.setStudies);
  const setStudiesLoading = useParametricStore((s) => s.setStudiesLoading);
  const setStudiesError = useParametricStore((s) => s.setStudiesError);

  // Load sweepable parameters once
  useEffect(() => {
    if (parametersLoaded) return;
    let cancelled = false;
    api
      .listParametricParameters()
      .then((params) => {
        if (!cancelled) setAvailableParameters(params);
      })
      .catch((err) => {
        console.error("failed to load parametric parameters", err);
      });
    return () => {
      cancelled = true;
    };
  }, [parametersLoaded, setAvailableParameters]);

  // Load past studies on mount
  useEffect(() => {
    setStudiesLoading(true);
    api
      .listParametricStudies()
      .then((studies) => setStudies(studies))
      .catch((err) => setStudiesError(String(err)))
      .finally(() => setStudiesLoading(false));
  }, [setStudies, setStudiesLoading, setStudiesError]);

  // Routing
  if (current === null) {
    return <ParametricSetupForm />;
  }
  if (current.status === "running") {
    return <ParametricRunGrid />;
  }
  return <ParametricResultsView />;
}
```

- [ ] **Step 14.3: Route the tab in App.tsx**

Edit `gui-frontend/src/App.tsx`. Find the existing tab routing block (where `SimulationView`, `ConfigView`, `DynoView` are rendered based on `activeTab`). Add an import for `ParametricView`:

```typescript
import ParametricView from "./components/parametric/ParametricView";
```

Add a branch in the tab routing (match the existing pattern — likely `activeTab === "dyno"` etc.):

```typescript
{activeTab === "parametric" && <ParametricView />}
```

- [ ] **Step 14.4: Create placeholder child components so the file compiles**

Create `gui-frontend/src/components/parametric/ParametricSetupForm.tsx`:

```typescript
export default function ParametricSetupForm() {
  return (
    <div className="p-6 text-text-muted font-ui">
      Parametric study setup form — implemented in Task 15.
    </div>
  );
}
```

Create `gui-frontend/src/components/parametric/ParametricRunGrid.tsx`:

```typescript
export default function ParametricRunGrid() {
  return (
    <div className="p-6 text-text-muted font-ui">
      Parametric run grid — implemented in Task 16.
    </div>
  );
}
```

Create `gui-frontend/src/components/parametric/ParametricResultsView.tsx`:

```typescript
export default function ParametricResultsView() {
  return (
    <div className="p-6 text-text-muted font-ui">
      Parametric results view — implemented in Task 17.
    </div>
  );
}
```

- [ ] **Step 14.5: Verify TypeScript compiles and GUI builds**

Run: `cd gui-frontend && npm run build`
Expected: Successful build, no TypeScript errors.

- [ ] **Step 14.6: Manual smoke test**

Start the backend: `python -m engine_simulator.gui`
In the browser, click the new "Parametric [04]" tab. Expect the placeholder text.

- [ ] **Step 14.7: Commit**

```bash
git add gui-frontend/src/components/TabBar.tsx \
        gui-frontend/src/App.tsx \
        gui-frontend/src/components/parametric/
git commit -m "feat(parametric): wire up Parametric tab shell

Adds the 4th tab, routes the Parametric view based on study state, and
drops in placeholder components for the three modes so the app builds
cleanly. Implementation of the modes follows in subsequent tasks."
```

---

### Task 15: Parametric setup form (Mode A)

**Files:**
- Modify: `gui-frontend/src/components/parametric/ParametricSetupForm.tsx`

- [ ] **Step 15.1: Implement the full setup form**

Replace the contents of `gui-frontend/src/components/parametric/ParametricSetupForm.tsx`:

```typescript
import { useEffect, useMemo, useState } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { api, type ConfigSummary } from "../../api/client";
import type { Param } from "../../types/parametric";

interface FormState {
  name: string;
  config_name: string;
  parameter_path: string;
  value_start: string; // display-scaled strings
  value_end: string;
  value_step: string;
  sweep_rpm_start: string;
  sweep_rpm_end: string;
  sweep_rpm_step: string;
  sweep_n_cycles: string;
  n_workers: number;
}

const DEFAULTS: Omit<FormState, "parameter_path" | "config_name"> = {
  name: "",
  value_start: "",
  value_end: "",
  value_step: "",
  sweep_rpm_start: "3000",
  sweep_rpm_end: "15000",
  sweep_rpm_step: "500",
  sweep_n_cycles: "8",
  n_workers: 8,
};

export default function ParametricSetupForm() {
  const availableParameters = useParametricStore((s) => s.availableParameters);
  const [configs, setConfigs] = useState<ConfigSummary[]>([]);
  const [form, setForm] = useState<FormState>({
    ...DEFAULTS,
    config_name: "cbr600rr.json",
    parameter_path: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .listConfigs()
      .then(setConfigs)
      .catch((err) => setError(String(err)));
  }, []);

  // When parameter selection changes, auto-populate the value range from
  // the parameter's default_range, converted through display_scale.
  useEffect(() => {
    if (!form.parameter_path) return;
    const param = availableParameters.find(
      (p) => p.path === form.parameter_path,
    );
    if (!param) return;
    const [start, end, step] = param.default_range;
    const scale = param.display_scale;
    setForm((f) => ({
      ...f,
      value_start: (start * scale).toString(),
      value_end: (end * scale).toString(),
      value_step: (step * scale).toString(),
      name: f.name || `${param.label} sweep`,
    }));
  }, [form.parameter_path, availableParameters]);

  const selectedParam = useMemo(
    () => availableParameters.find((p) => p.path === form.parameter_path),
    [form.parameter_path, availableParameters],
  );

  // Group parameters by category
  const paramsByCategory = useMemo(() => {
    const map: Record<string, Param[]> = {};
    for (const p of availableParameters) {
      (map[p.category] ||= []).push(p);
    }
    return map;
  }, [availableParameters]);

  const parameterValueCount = useMemo(() => {
    const vs = parseFloat(form.value_start);
    const ve = parseFloat(form.value_end);
    const step = parseFloat(form.value_step);
    if (!Number.isFinite(vs) || !Number.isFinite(ve) || !Number.isFinite(step))
      return 0;
    if (step <= 0 || ve <= vs) return 0;
    return Math.round((ve - vs) / step) + 1;
  }, [form.value_start, form.value_end, form.value_step]);

  const rpmPointCount = useMemo(() => {
    const rs = parseFloat(form.sweep_rpm_start);
    const re = parseFloat(form.sweep_rpm_end);
    const step = parseFloat(form.sweep_rpm_step);
    if (!Number.isFinite(rs) || !Number.isFinite(re) || !Number.isFinite(step))
      return 0;
    if (step <= 0 || re <= rs) return 0;
    return Math.round((re - rs) / step) + 1;
  }, [form.sweep_rpm_start, form.sweep_rpm_end, form.sweep_rpm_step]);

  const totalSimulations = parameterValueCount * rpmPointCount;

  const canSubmit =
    selectedParam !== undefined &&
    parameterValueCount > 0 &&
    rpmPointCount > 0 &&
    form.name.trim().length > 0 &&
    !submitting;

  const handleSubmit = async () => {
    if (!selectedParam) return;
    setSubmitting(true);
    setError(null);
    try {
      const scale = selectedParam.display_scale;
      await api.startParametricStudy({
        name: form.name.trim(),
        config_name: form.config_name,
        parameter_path: form.parameter_path,
        value_start: parseFloat(form.value_start) / scale,
        value_end: parseFloat(form.value_end) / scale,
        value_step: parseFloat(form.value_step) / scale,
        sweep_rpm_start: parseFloat(form.sweep_rpm_start),
        sweep_rpm_end: parseFloat(form.sweep_rpm_end),
        sweep_rpm_step: parseFloat(form.sweep_rpm_step),
        sweep_n_cycles: parseInt(form.sweep_n_cycles, 10),
        n_workers: form.n_workers,
      });
      // The WebSocket will push parametric_study_start which flips the
      // store to running — this component will unmount.
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="flex h-full overflow-auto bg-bg text-text-primary font-ui">
      <div className="flex-1 p-8 max-w-3xl">
        <header className="mb-8">
          <h1 className="text-lg font-semibold tracking-wide">
            Parametric Study
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Sweep one engine-design parameter across a range and compare
            full RPM sweeps for each value.
          </p>
        </header>

        <div className="space-y-5">
          <Field index="01" label="Name">
            <input
              className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm outline-none focus:border-accent"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Intake runner length sweep"
            />
          </Field>

          <Field index="02" label="Engine Config">
            <select
              className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm outline-none focus:border-accent"
              value={form.config_name}
              onChange={(e) =>
                setForm((f) => ({ ...f, config_name: e.target.value }))
              }
            >
              {configs.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>

          <Field index="03" label="Parameter">
            <select
              className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm outline-none focus:border-accent"
              value={form.parameter_path}
              onChange={(e) =>
                setForm((f) => ({ ...f, parameter_path: e.target.value }))
              }
            >
              <option value="">— select a parameter —</option>
              {Object.entries(paramsByCategory).map(([category, params]) => (
                <optgroup key={category} label={category}>
                  {params.map((p) => (
                    <option key={p.path} value={p.path}>
                      {p.label} {p.unit ? `(${p.unit})` : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </Field>

          {selectedParam && (
            <div className="grid grid-cols-3 gap-3">
              <Field
                index="04"
                label={`Start${selectedParam.unit ? ` (${selectedParam.unit})` : ""}`}
              >
                <input
                  className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent"
                  value={form.value_start}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, value_start: e.target.value }))
                  }
                />
              </Field>
              <Field
                index="05"
                label={`End${selectedParam.unit ? ` (${selectedParam.unit})` : ""}`}
              >
                <input
                  className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent"
                  value={form.value_end}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, value_end: e.target.value }))
                  }
                />
              </Field>
              <Field
                index="06"
                label={`Step${selectedParam.unit ? ` (${selectedParam.unit})` : ""}`}
              >
                <input
                  className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent"
                  value={form.value_step}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, value_step: e.target.value }))
                  }
                />
              </Field>
            </div>
          )}

          <div className="grid grid-cols-3 gap-3">
            <Field index="07" label="RPM Start">
              <input
                className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent"
                value={form.sweep_rpm_start}
                onChange={(e) =>
                  setForm((f) => ({ ...f, sweep_rpm_start: e.target.value }))
                }
              />
            </Field>
            <Field index="08" label="RPM End">
              <input
                className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent"
                value={form.sweep_rpm_end}
                onChange={(e) =>
                  setForm((f) => ({ ...f, sweep_rpm_end: e.target.value }))
                }
              />
            </Field>
            <Field index="09" label="RPM Step">
              <input
                className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent"
                value={form.sweep_rpm_step}
                onChange={(e) =>
                  setForm((f) => ({ ...f, sweep_rpm_step: e.target.value }))
                }
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field index="10" label="Cycles per RPM">
              <input
                className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent"
                value={form.sweep_n_cycles}
                onChange={(e) =>
                  setForm((f) => ({ ...f, sweep_n_cycles: e.target.value }))
                }
              />
            </Field>
            <Field index="11" label="Workers">
              <input
                type="number"
                min={1}
                max={16}
                className="w-full bg-surface border border-border-default rounded px-2 py-1.5 text-sm font-mono outline-none focus:border-accent"
                value={form.n_workers}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    n_workers: Math.max(
                      1,
                      Math.min(16, parseInt(e.target.value, 10) || 1),
                    ),
                  }))
                }
              />
            </Field>
          </div>

          {error && (
            <div className="text-sm text-status-error border border-status-error p-3">
              {error}
            </div>
          )}

          <div className="flex items-center gap-4 pt-4">
            <button
              type="button"
              disabled={!canSubmit}
              onClick={handleSubmit}
              className="px-5 py-2 text-sm uppercase tracking-wider border border-accent text-accent hover:bg-accent hover:text-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? "Starting..." : "Start Study"}
            </button>
          </div>
        </div>
      </div>

      {/* Live readout panel */}
      <aside className="w-72 border-l border-border-default bg-surface p-6 text-sm font-ui">
        <h2 className="text-xs uppercase tracking-[0.18em] text-text-muted mb-4">
          Study Plan
        </h2>
        <dl className="space-y-3 font-mono">
          <Stat label="Parameter Values" value={String(parameterValueCount)} />
          <Stat label="RPM Points" value={String(rpmPointCount)} />
          <Stat
            label="Total Simulations"
            value={String(totalSimulations)}
            emphasis
          />
        </dl>
        {selectedParam && (
          <div className="mt-6 text-xs text-text-muted">
            <div className="uppercase tracking-wider mb-1">Bounds</div>
            <div className="font-mono">
              min: {selectedParam.min_allowed ?? "—"}
              <br />
              max: {selectedParam.max_allowed ?? "—"}
              <br />
              <span className="text-text-muted/70">
                (storage units, unscaled)
              </span>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function Field({
  index,
  label,
  children,
}: {
  index: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline gap-2 mb-1.5">
        <span className="text-[9px] font-mono text-text-muted">[{index}]</span>
        <span className="text-[11px] uppercase tracking-[0.14em] text-text-muted">
          {label}
        </span>
      </div>
      {children}
    </label>
  );
}

function Stat({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-[11px] uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <span
        className={
          emphasis ? "text-accent font-semibold" : "text-text-primary"
        }
      >
        {value}
      </span>
    </div>
  );
}
```

Note: this form uses raw `<input>` and `<select>` elements with concrete Tailwind classes rather than the existing `NumericField` / `TextField` form components in `gui-frontend/src/components/forms/`. That's intentional — those components have a richer structure (error display, unit suffixes) that doesn't map cleanly to the simpler layout here. If you prefer consistency with the Config tab, feel free to swap in `NumericField` for the numeric inputs.

- [ ] **Step 15.2: Verify build**

Run: `cd gui-frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 15.3: Manual test**

Start the backend, open the Parametric tab. Verify:
- Parameter dropdown populates with grouped options
- Selecting a parameter auto-fills the value range
- "Start Study" button is disabled until all fields valid
- Clicking start actually posts to `/api/parametric/study/start`

- [ ] **Step 15.4: Commit**

```bash
git add gui-frontend/src/components/parametric/ParametricSetupForm.tsx
git commit -m "feat(parametric): implement setup form (Mode A)"
```

---

### Task 16: Parametric run grid (Mode B)

**Files:**
- Modify: `gui-frontend/src/components/parametric/ParametricRunGrid.tsx`

- [ ] **Step 16.1: Implement live run grid**

Replace the contents of `gui-frontend/src/components/parametric/ParametricRunGrid.tsx`:

```typescript
import { useParametricStore } from "../../state/parametricStore";
import { api } from "../../api/client";
import type { ParametricRun } from "../../types/parametric";

export default function ParametricRunGrid() {
  const current = useParametricStore((s) => s.current);
  const availableParameters = useParametricStore((s) => s.availableParameters);

  if (!current) return null;

  const param = availableParameters.find(
    (p) => p.path === current.definition.parameter_path,
  );
  const scale = param?.display_scale ?? 1;
  const unit = param?.unit ?? "";

  const handleStop = async () => {
    try {
      await api.stopParametricStudy();
    } catch (err) {
      console.error(err);
    }
  };

  const doneCount = current.runs.filter((r) => r.status === "done").length;
  const totalCount = current.runs.length;

  return (
    <div className="h-full flex flex-col bg-bg text-text-primary font-ui">
      <header className="flex items-center justify-between border-b border-border-default p-6">
        <div>
          <h1 className="text-lg font-semibold">{current.definition.name}</h1>
          <p className="text-sm text-text-muted mt-1">
            {param?.label ?? current.definition.parameter_path} ·{" "}
            <span className="font-mono">
              {doneCount} / {totalCount}
            </span>{" "}
            runs complete
          </p>
        </div>
        <button
          type="button"
          onClick={handleStop}
          className="px-4 py-2 text-xs uppercase tracking-wider border border-status-error text-status-error hover:bg-status-error hover:text-bg transition-colors"
        >
          Stop Study
        </button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {current.runs.map((run, idx) => (
            <RunCard
              key={idx}
              run={run}
              displayValue={(run.parameter_value * scale).toFixed(3)}
              unit={unit}
              totalRpms={
                Math.round(
                  (current.definition.sweep_rpm_end -
                    current.definition.sweep_rpm_start) /
                    current.definition.sweep_rpm_step,
                ) + 1
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function RunCard({
  run,
  displayValue,
  unit,
  totalRpms,
}: {
  run: ParametricRun;
  displayValue: string;
  unit: string;
  totalRpms: number;
}) {
  const completedRpms = run.sweep_results.length;
  const progress = totalRpms > 0 ? completedRpms / totalRpms : 0;

  const statusColor = {
    queued: "text-text-muted",
    running: "text-accent",
    done: "text-status-success",
    error: "text-status-error",
  }[run.status];

  // Tiny power sparkline using inline SVG
  const powers = run.sweep_results
    .map((p) => (typeof p.brake_power_hp === "number" ? p.brake_power_hp : 0))
    .filter((v) => Number.isFinite(v));
  const maxPower = powers.length ? Math.max(...powers) : 1;
  const minPower = powers.length ? Math.min(...powers) : 0;
  const range = Math.max(maxPower - minPower, 1);

  return (
    <div
      className={`border p-3 transition-colors ${
        run.status === "running"
          ? "border-accent bg-surface-raised"
          : "border-border-default bg-surface"
      }`}
    >
      <div className="flex items-baseline justify-between mb-2">
        <span className="font-mono text-sm">
          {displayValue}
          <span className="text-text-muted ml-1">{unit}</span>
        </span>
        <span
          className={`text-[10px] uppercase tracking-wider ${statusColor}`}
        >
          {run.status}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-border-default mb-2 relative">
        <div
          className="h-full bg-accent transition-all"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      {/* Sparkline */}
      <svg viewBox="0 0 100 30" className="w-full h-8 text-accent">
        {powers.length > 1 && (
          <polyline
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            points={powers
              .map((p, i) => {
                const x = (i / (powers.length - 1)) * 100;
                const y = 30 - ((p - minPower) / range) * 26 - 2;
                return `${x},${y}`;
              })
              .join(" ")}
          />
        )}
      </svg>

      <div className="flex justify-between text-[10px] font-mono text-text-muted mt-1">
        <span>
          {completedRpms}/{totalRpms} RPM
        </span>
        <span>{run.elapsed_seconds.toFixed(1)}s</span>
      </div>

      {run.error && (
        <div className="mt-2 text-[10px] text-status-error font-mono line-clamp-2">
          {run.error.split("\n")[0]}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 16.2: Verify build**

Run: `cd gui-frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 16.3: Manual test**

Start a tiny study (2-3 parameter values, small RPM range) and verify the run grid shows live progress.

- [ ] **Step 16.4: Commit**

```bash
git add gui-frontend/src/components/parametric/ParametricRunGrid.tsx
git commit -m "feat(parametric): implement live run grid (Mode B)"
```

---

### Task 17: Parametric results view — shell and overlay charts

**Files:**
- Modify: `gui-frontend/src/components/parametric/ParametricResultsView.tsx`
- Create: `gui-frontend/src/components/parametric/ParametricOverlayCharts.tsx`

- [ ] **Step 17.1: Implement the results shell with objective controls**

Replace `gui-frontend/src/components/parametric/ParametricResultsView.tsx`:

```typescript
import { useParametricStore } from "../../state/parametricStore";
import type { ObjectiveKey } from "../../types/parametric";
import ParametricOverlayCharts from "./ParametricOverlayCharts";
import ParametricComparisonTable from "./ParametricComparisonTable";
import ParametricHeatmap from "./ParametricHeatmap";

const OBJECTIVES: { key: ObjectiveKey; label: string }[] = [
  { key: "peak_power", label: "Peak HP" },
  { key: "peak_torque", label: "Peak Torque" },
  { key: "torque_area", label: "Torque Area" },
  { key: "power_at_rpm", label: "HP @ RPM" },
  { key: "torque_at_rpm", label: "Torque @ RPM" },
];

export default function ParametricResultsView() {
  const current = useParametricStore((s) => s.current);
  const selectedObjective = useParametricStore((s) => s.selectedObjective);
  const objectiveRpm = useParametricStore((s) => s.objectiveRpm);
  const objectiveRpmWindow = useParametricStore((s) => s.objectiveRpmWindow);
  const setSelectedObjective = useParametricStore(
    (s) => s.setSelectedObjective,
  );
  const setObjectiveRpm = useParametricStore((s) => s.setObjectiveRpm);
  const setObjectiveRpmWindow = useParametricStore(
    (s) => s.setObjectiveRpmWindow,
  );
  const selectAllRuns = useParametricStore((s) => s.selectAllRuns);
  const clearSelectedRuns = useParametricStore((s) => s.clearSelectedRuns);
  const clearCurrent = useParametricStore((s) => s.clearCurrent);

  if (!current) return null;

  const needsRpm =
    selectedObjective === "power_at_rpm" ||
    selectedObjective === "torque_at_rpm";
  const needsWindow = selectedObjective === "torque_area";

  return (
    <div className="h-full overflow-auto bg-bg text-text-primary font-ui">
      <header className="sticky top-0 bg-bg border-b border-border-default px-6 py-4 z-10">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-lg font-semibold">{current.definition.name}</h1>
            <p className="text-xs text-text-muted mt-0.5 font-mono">
              {current.definition.parameter_path} · {current.runs.length} runs
              · status: {current.status}
            </p>
          </div>
          <button
            type="button"
            onClick={clearCurrent}
            className="px-3 py-1.5 text-xs uppercase tracking-wider border border-border-default hover:border-accent hover:text-accent"
          >
            New Study
          </button>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">
            Objective:
          </span>
          {OBJECTIVES.map((obj) => (
            <button
              key={obj.key}
              type="button"
              onClick={() => setSelectedObjective(obj.key)}
              className={`px-3 py-1 text-xs uppercase tracking-wider border transition-colors ${
                selectedObjective === obj.key
                  ? "border-accent text-accent bg-surface-raised"
                  : "border-border-default text-text-muted hover:text-text-primary"
              }`}
            >
              {obj.label}
            </button>
          ))}

          {needsRpm && (
            <label className="flex items-center gap-2 ml-4">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                RPM:
              </span>
              <input
                type="number"
                className="w-24 px-2 py-1 bg-surface border border-border-default text-sm font-mono"
                value={objectiveRpm}
                onChange={(e) => setObjectiveRpm(parseFloat(e.target.value))}
              />
            </label>
          )}

          {needsWindow && (
            <div className="flex items-center gap-2 ml-4">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                Window:
              </span>
              <input
                type="number"
                className="w-24 px-2 py-1 bg-surface border border-border-default text-sm font-mono"
                value={objectiveRpmWindow[0]}
                onChange={(e) =>
                  setObjectiveRpmWindow([
                    parseFloat(e.target.value),
                    objectiveRpmWindow[1],
                  ])
                }
              />
              <span className="text-text-muted">–</span>
              <input
                type="number"
                className="w-24 px-2 py-1 bg-surface border border-border-default text-sm font-mono"
                value={objectiveRpmWindow[1]}
                onChange={(e) =>
                  setObjectiveRpmWindow([
                    objectiveRpmWindow[0],
                    parseFloat(e.target.value),
                  ])
                }
              />
            </div>
          )}

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={selectAllRuns}
              className="text-xs text-text-muted hover:text-accent uppercase tracking-wider"
            >
              Show All
            </button>
            <span className="text-text-muted">·</span>
            <button
              type="button"
              onClick={clearSelectedRuns}
              className="text-xs text-text-muted hover:text-accent uppercase tracking-wider"
            >
              Hide All
            </button>
          </div>
        </div>
      </header>

      <div className="p-6 space-y-6">
        <ParametricOverlayCharts />
        <ParametricComparisonTable />
        <ParametricHeatmap />
      </div>
    </div>
  );
}
```

- [ ] **Step 17.2: Implement overlay charts**

Create `gui-frontend/src/components/parametric/ParametricOverlayCharts.tsx`:

```typescript
import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { useParametricStore } from "../../state/parametricStore";
import type { ParametricRun, PerfDict } from "../../types/parametric";

interface ChartSpec {
  title: string;
  dataKey: keyof PerfDict | string;
  unit: string;
}

const CHARTS: ChartSpec[] = [
  { title: "Brake Power", dataKey: "brake_power_hp", unit: "hp" },
  { title: "Brake Torque", dataKey: "brake_torque_Nm", unit: "Nm" },
  { title: "Volumetric Eff (atm)", dataKey: "volumetric_efficiency_atm", unit: "" },
  { title: "Plenum Pressure", dataKey: "plenum_pressure_bar", unit: "bar" },
];

/** Generate N distinct HSL colors (cool → warm) for the run overlays. */
function runColor(index: number, total: number): string {
  if (total <= 1) return "hsl(30, 90%, 60%)";
  const hue = 200 - (index / (total - 1)) * 180; // 200 (blue) → 20 (orange)
  return `hsl(${hue}, 75%, 60%)`;
}

interface ChartPoint {
  rpm: number;
  [runKey: string]: number | null;
}

function buildChartData(
  runs: ParametricRun[],
  selectedIndices: Set<number>,
  dataKey: string,
): ChartPoint[] {
  // Collect union of RPMs
  const rpmSet = new Set<number>();
  for (const run of runs) {
    for (const perf of run.sweep_results) {
      rpmSet.add(perf.rpm);
    }
  }
  const rpms = Array.from(rpmSet).sort((a, b) => a - b);

  return rpms.map((rpm) => {
    const point: ChartPoint = { rpm };
    runs.forEach((run, idx) => {
      if (!selectedIndices.has(idx)) {
        point[`run_${idx}`] = null;
        return;
      }
      const perf = run.sweep_results.find((p) => p.rpm === rpm);
      const value = perf ? (perf as Record<string, unknown>)[dataKey] : null;
      point[`run_${idx}`] =
        typeof value === "number" && Number.isFinite(value) ? value : null;
    });
    return point;
  });
}

export default function ParametricOverlayCharts() {
  const current = useParametricStore((s) => s.current);
  const selectedIndices = useParametricStore((s) => s.selectedRunIndices);
  const availableParameters = useParametricStore((s) => s.availableParameters);
  const toggleRunSelected = useParametricStore((s) => s.toggleRunSelected);

  if (!current) return null;

  const param = availableParameters.find(
    (p) => p.path === current.definition.parameter_path,
  );
  const scale = param?.display_scale ?? 1;
  const unit = param?.unit ?? "";

  return (
    <div>
      <div className="flex gap-4">
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4">
          {CHARTS.map((spec) => (
            <OverlayChart
              key={spec.title}
              spec={spec}
              runs={current.runs}
              selectedIndices={selectedIndices}
            />
          ))}
        </div>

        {/* Legend */}
        <aside className="w-48 shrink-0">
          <div className="text-[10px] uppercase tracking-wider text-text-muted mb-2">
            Runs
          </div>
          <div className="space-y-1">
            {current.runs.map((run, idx) => {
              const isSelected = selectedIndices.has(idx);
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => toggleRunSelected(idx)}
                  className={`flex items-center gap-2 w-full text-left px-2 py-1 text-xs font-mono transition-colors ${
                    isSelected
                      ? "text-text-primary"
                      : "text-text-muted opacity-40"
                  }`}
                >
                  <span
                    className="w-3 h-3 border border-border-default"
                    style={{
                      backgroundColor: isSelected
                        ? runColor(idx, current.runs.length)
                        : "transparent",
                    }}
                  />
                  <span>
                    {(run.parameter_value * scale).toFixed(3)} {unit}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>
      </div>
    </div>
  );
}

function OverlayChart({
  spec,
  runs,
  selectedIndices,
}: {
  spec: ChartSpec;
  runs: ParametricRun[];
  selectedIndices: Set<number>;
}) {
  const data = useMemo(
    () => buildChartData(runs, selectedIndices, String(spec.dataKey)),
    [runs, selectedIndices, spec.dataKey],
  );

  return (
    <div className="border border-border-default bg-surface p-3">
      <h3 className="text-xs uppercase tracking-wider text-text-muted mb-2">
        {spec.title}
        {spec.unit && (
          <span className="text-text-muted/60 ml-1">({spec.unit})</span>
        )}
      </h3>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid stroke="#333" strokeDasharray="3 3" />
            <XAxis
              dataKey="rpm"
              stroke="#888"
              tick={{ fontSize: 10, fontFamily: "monospace" }}
            />
            <YAxis
              stroke="#888"
              tick={{ fontSize: 10, fontFamily: "monospace" }}
            />
            <Tooltip
              contentStyle={{
                background: "#111",
                border: "1px solid #333",
                fontFamily: "monospace",
                fontSize: 11,
              }}
            />
            {runs.map((_, idx) => {
              if (!selectedIndices.has(idx)) return null;
              return (
                <Line
                  key={idx}
                  type="monotone"
                  dataKey={`run_${idx}`}
                  stroke={runColor(idx, runs.length)}
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

- [ ] **Step 17.3: Verify build**

Run: `cd gui-frontend && npm run build`
Expected: Build succeeds (placeholder table/heatmap components still exist from Task 14).

- [ ] **Step 17.4: Commit**

```bash
git add gui-frontend/src/components/parametric/ParametricResultsView.tsx \
        gui-frontend/src/components/parametric/ParametricOverlayCharts.tsx
git commit -m "feat(parametric): implement results view shell and overlay charts"
```

---

### Task 18: Comparison table

**Files:**
- Create: `gui-frontend/src/components/parametric/ParametricComparisonTable.tsx`

- [ ] **Step 18.1: Implement the ranked comparison table**

Create `gui-frontend/src/components/parametric/ParametricComparisonTable.tsx`:

```typescript
import { useMemo } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { computeComparisonTable } from "../../state/parametricSelectors";
import type { ObjectiveKey } from "../../types/parametric";

const OBJECTIVE_COLUMN: Record<ObjectiveKey, string> = {
  peak_power: "peak_power_hp",
  peak_torque: "peak_torque_Nm",
  torque_area: "torque_area",
  power_at_rpm: "power_at_rpm",
  torque_at_rpm: "torque_at_rpm",
};

function fmt(v: number | null, decimals = 1): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return v.toFixed(decimals);
}

export default function ParametricComparisonTable() {
  const current = useParametricStore((s) => s.current);
  const selectedObjective = useParametricStore((s) => s.selectedObjective);
  const objectiveRpm = useParametricStore((s) => s.objectiveRpm);
  const objectiveRpmWindow = useParametricStore((s) => s.objectiveRpmWindow);
  const availableParameters = useParametricStore((s) => s.availableParameters);
  const setHighlightedRun = useParametricStore((s) => s.setHighlightedRun);
  const highlightedRunIndex = useParametricStore((s) => s.highlightedRunIndex);

  const rows = useMemo(() => {
    if (!current) return [];
    return computeComparisonTable(
      current,
      selectedObjective,
      objectiveRpm,
      objectiveRpmWindow,
    );
  }, [current, selectedObjective, objectiveRpm, objectiveRpmWindow]);

  if (!current) return null;

  const param = availableParameters.find(
    (p) => p.path === current.definition.parameter_path,
  );
  const scale = param?.display_scale ?? 1;
  const unit = param?.unit ?? "";
  const objectiveCol = OBJECTIVE_COLUMN[selectedObjective];

  return (
    <div className="border border-border-default bg-surface">
      <div className="px-4 py-3 border-b border-border-default flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-[0.18em] text-text-muted">
          Comparison Table
        </h2>
        <span className="text-[10px] text-text-muted font-mono">
          ranked by {selectedObjective.replace("_", " ")}
        </span>
      </div>
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="border-b border-border-default text-text-muted">
            <Th>Rank</Th>
            <Th>Value</Th>
            <Th highlight={objectiveCol === "peak_power_hp"}>Peak HP (rpm)</Th>
            <Th highlight={objectiveCol === "peak_torque_Nm"}>
              Peak Torque (rpm)
            </Th>
            <Th highlight={objectiveCol === "torque_area"}>Torque Area</Th>
            <Th highlight={objectiveCol === "power_at_rpm"}>HP @ RPM</Th>
            <Th highlight={objectiveCol === "torque_at_rpm"}>Torque @ RPM</Th>
            <Th>VE peak</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isHighlighted = highlightedRunIndex === row.index;
            return (
              <tr
                key={row.index}
                onMouseEnter={() => setHighlightedRun(row.index)}
                onMouseLeave={() => setHighlightedRun(null)}
                className={`border-b border-border-default/30 cursor-pointer ${
                  isHighlighted
                    ? "bg-surface-raised"
                    : row.isBest
                      ? "bg-accent/5"
                      : ""
                }`}
              >
                <Td>
                  {row.rank !== null ? (
                    row.isBest ? (
                      <span className="text-accent font-semibold">
                        1
                      </span>
                    ) : (
                      <span>{row.rank}</span>
                    )
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </Td>
                <Td>
                  {(row.parameter_value * scale).toFixed(3)} {unit}
                </Td>
                <Td highlight={objectiveCol === "peak_power_hp"}>
                  {fmt(row.metrics.peak_power_hp)} (
                  {fmt(row.metrics.peak_power_rpm, 0)})
                </Td>
                <Td highlight={objectiveCol === "peak_torque_Nm"}>
                  {fmt(row.metrics.peak_torque_Nm)} (
                  {fmt(row.metrics.peak_torque_rpm, 0)})
                </Td>
                <Td highlight={objectiveCol === "torque_area"}>
                  {fmt(row.metrics.torque_area, 0)}
                </Td>
                <Td highlight={objectiveCol === "power_at_rpm"}>
                  {fmt(row.metrics.power_at_rpm)}
                </Td>
                <Td highlight={objectiveCol === "torque_at_rpm"}>
                  {fmt(row.metrics.torque_at_rpm)}
                </Td>
                <Td>{fmt(row.metrics.ve_peak, 2)}</Td>
                <Td>
                  <span
                    className={
                      row.status === "done"
                        ? "text-status-success"
                        : row.status === "error"
                          ? "text-status-error"
                          : "text-text-muted"
                    }
                  >
                    {row.status}
                  </span>
                </Td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.some((r) => r.error) && (
        <div className="p-3 text-[10px] text-status-error font-mono border-t border-border-default">
          {rows
            .filter((r) => r.error)
            .map((r) => (
              <div key={r.index}>
                value {(r.parameter_value * scale).toFixed(3)} {unit}:{" "}
                {r.error?.split("\n")[0]}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function Th({
  children,
  highlight = false,
}: {
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <th
      className={`text-left px-3 py-2 text-[10px] uppercase tracking-wider ${
        highlight ? "text-accent" : ""
      }`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  highlight = false,
}: {
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <td className={`px-3 py-2 ${highlight ? "font-semibold" : ""}`}>
      {children}
    </td>
  );
}
```

- [ ] **Step 18.2: Verify build**

Run: `cd gui-frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 18.3: Commit**

```bash
git add gui-frontend/src/components/parametric/ParametricComparisonTable.tsx
git commit -m "feat(parametric): implement ranked comparison table"
```

---

### Task 19: Heatmap

**Files:**
- Create: `gui-frontend/src/components/parametric/ParametricHeatmap.tsx`

- [ ] **Step 19.1: Implement the heatmap**

Create `gui-frontend/src/components/parametric/ParametricHeatmap.tsx`:

```typescript
import { useMemo, useState } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { computeHeatmapData } from "../../state/parametricSelectors";

const METRIC_OPTIONS = [
  { key: "brake_power_hp", label: "Brake HP" },
  { key: "brake_torque_Nm", label: "Brake Torque" },
  { key: "volumetric_efficiency_atm", label: "VE (atm)" },
  { key: "plenum_pressure_bar", label: "Plenum P" },
];

/** Linear interpolation from blue (low) to orange (high). */
function colorFor(
  value: number | null,
  min: number,
  max: number,
): string {
  if (value === null) return "#1a1a1a";
  const t = (value - min) / Math.max(max - min, 1e-9);
  const hue = 200 - t * 180; // 200 blue → 20 orange
  const lightness = 35 + t * 25;
  return `hsl(${hue}, 75%, ${lightness}%)`;
}

export default function ParametricHeatmap() {
  const current = useParametricStore((s) => s.current);
  const availableParameters = useParametricStore((s) => s.availableParameters);
  const [metricKey, setMetricKey] = useState("brake_power_hp");
  const [expanded, setExpanded] = useState(true);

  const heatmapData = useMemo(() => {
    if (!current) return null;
    return computeHeatmapData(current, metricKey);
  }, [current, metricKey]);

  if (!current || !heatmapData) return null;

  const param = availableParameters.find(
    (p) => p.path === current.definition.parameter_path,
  );
  const scale = param?.display_scale ?? 1;
  const unit = param?.unit ?? "";

  // Flatten to find global min/max
  const flat = heatmapData.values
    .flat()
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const min = flat.length ? Math.min(...flat) : 0;
  const max = flat.length ? Math.max(...flat) : 1;

  // For each RPM column, find the row index with the max value (the
  // "sweet spot" per RPM).
  const bestRowPerColumn: number[] = heatmapData.rpms.map((_, colIdx) => {
    let bestRow = -1;
    let bestVal = -Infinity;
    heatmapData.values.forEach((row, rowIdx) => {
      const v = row[colIdx];
      if (v !== null && v > bestVal) {
        bestVal = v;
        bestRow = rowIdx;
      }
    });
    return bestRow;
  });

  return (
    <div className="border border-border-default bg-surface">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 border-b border-border-default text-xs uppercase tracking-[0.18em] text-text-muted hover:text-text-primary"
      >
        <span>Heatmap: {METRIC_OPTIONS.find((m) => m.key === metricKey)?.label}</span>
        <span>{expanded ? "▼" : "▶"}</span>
      </button>

      {expanded && (
        <div className="p-4">
          <div className="mb-3">
            <label className="text-[10px] uppercase tracking-wider text-text-muted mr-2">
              Metric:
            </label>
            <select
              value={metricKey}
              onChange={(e) => setMetricKey(e.target.value)}
              className="bg-surface border border-border-default text-xs px-2 py-1"
            >
              {METRIC_OPTIONS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          <div className="overflow-x-auto">
            <table className="border-collapse text-[10px] font-mono">
              <thead>
                <tr>
                  <th className="sticky left-0 bg-surface p-1 text-text-muted text-right">
                    {param?.label ?? "Value"}
                  </th>
                  {heatmapData.rpms.map((rpm) => (
                    <th
                      key={rpm}
                      className="p-1 text-text-muted font-normal"
                      style={{ minWidth: 36 }}
                    >
                      {Math.round(rpm)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatmapData.parameterValues.map((value, rowIdx) => (
                  <tr key={rowIdx}>
                    <td className="sticky left-0 bg-surface p-1 text-right text-text-muted pr-2">
                      {(value * scale).toFixed(3)} {unit}
                    </td>
                    {heatmapData.values[rowIdx].map((cellValue, colIdx) => {
                      const isBest = bestRowPerColumn[colIdx] === rowIdx;
                      return (
                        <td
                          key={colIdx}
                          className="p-0 text-center relative"
                          style={{
                            backgroundColor: colorFor(cellValue, min, max),
                            minWidth: 36,
                            height: 24,
                          }}
                          title={
                            cellValue === null
                              ? "—"
                              : cellValue.toFixed(1)
                          }
                        >
                          {isBest && (
                            <span className="absolute inset-0 flex items-center justify-center text-[8px] text-bg">
                              ●
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center gap-3 text-[10px] font-mono text-text-muted">
            <span>{min.toFixed(1)}</span>
            <div
              className="flex-1 h-3 max-w-xs"
              style={{
                background:
                  "linear-gradient(to right, hsl(200,75%,35%), hsl(110,75%,48%), hsl(20,75%,60%))",
              }}
            />
            <span>{max.toFixed(1)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 19.2: Verify build**

Run: `cd gui-frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 19.3: Commit**

```bash
git add gui-frontend/src/components/parametric/ParametricHeatmap.tsx
git commit -m "feat(parametric): implement heatmap with per-RPM sweet-spot markers"
```

---

### Task 20: Parametric study list sidebar

**Files:**
- Create: `gui-frontend/src/components/parametric/ParametricStudyListSidebar.tsx`
- Modify: `gui-frontend/src/components/parametric/ParametricView.tsx` (mount the sidebar)

- [ ] **Step 20.1: Create the sidebar**

Create `gui-frontend/src/components/parametric/ParametricStudyListSidebar.tsx`:

```typescript
import { useState } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { api } from "../../api/client";
import type { LiveParametricStudy } from "../../types/parametric";

export default function ParametricStudyListSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const studies = useParametricStore((s) => s.studies);
  const studiesLoading = useParametricStore((s) => s.studiesLoading);
  const studiesError = useParametricStore((s) => s.studiesError);
  const setCurrent = useParametricStore((s) => s.setCurrent);
  const setStudies = useParametricStore((s) => s.setStudies);
  const setStudiesLoading = useParametricStore((s) => s.setStudiesLoading);
  const setStudiesError = useParametricStore((s) => s.setStudiesError);

  const refresh = async () => {
    setStudiesLoading(true);
    setStudiesError(null);
    try {
      setStudies(await api.listParametricStudies());
    } catch (err) {
      setStudiesError(err instanceof Error ? err.message : String(err));
    } finally {
      setStudiesLoading(false);
    }
  };

  const handleLoad = async (id: string) => {
    try {
      const study = await api.loadParametricStudy(id);
      // The API returns the raw JSON shape — cast carefully.
      setCurrent(study as unknown as LiveParametricStudy);
    } catch (err) {
      console.error(err);
    }
  };

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className="w-8 shrink-0 border-l border-border-default bg-surface hover:bg-surface-raised flex items-center justify-center"
      >
        <span className="[writing-mode:vertical-rl] text-[10px] uppercase tracking-[0.18em] text-text-muted">
          param · studies · {studies.length}
        </span>
      </button>
    );
  }

  return (
    <aside className="w-72 shrink-0 border-l border-border-default bg-surface flex flex-col overflow-hidden font-ui">
      <header className="flex items-center justify-between px-3 py-3 border-b border-border-default">
        <div className="flex items-baseline gap-2">
          <span className="text-[9px] font-mono text-text-muted">[P]</span>
          <span className="text-[11px] uppercase tracking-[0.14em] text-text-muted">
            Param Studies
          </span>
          <span className="text-[10px] font-mono text-text-muted">
            n={studies.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={refresh}
            className="text-[10px] text-text-muted hover:text-accent"
          >
            ↻
          </button>
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className="text-[10px] text-text-muted hover:text-accent"
          >
            ×
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto">
        {studiesLoading && (
          <div className="p-3 text-xs text-text-muted">Loading…</div>
        )}
        {studiesError && (
          <div className="p-3 text-xs text-status-error">{studiesError}</div>
        )}
        {!studiesLoading && studies.length === 0 && !studiesError && (
          <div className="p-3 text-xs text-text-muted">
            No past studies yet.
          </div>
        )}
        {studies.map((s) => (
          <button
            key={s.study_id}
            type="button"
            onClick={() => handleLoad(s.study_id)}
            className="w-full text-left border-b border-border-default/30 px-3 py-2 hover:bg-surface-raised"
          >
            <div className="text-xs font-mono text-text-primary truncate">
              {s.name || s.study_id}
            </div>
            <div className="text-[10px] font-mono text-text-muted mt-0.5">
              {s.parameter_path}
            </div>
            <div className="flex items-center justify-between mt-1 text-[10px] font-mono text-text-muted">
              <span>
                {s.n_values} val · {s.run_count} runs
              </span>
              <span
                className={
                  s.status === "complete"
                    ? "text-status-success"
                    : s.status === "error"
                      ? "text-status-error"
                      : "text-text-muted"
                }
              >
                {s.status}
              </span>
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}
```

- [ ] **Step 20.2: Mount the sidebar in ParametricView**

Edit `gui-frontend/src/components/parametric/ParametricView.tsx`. Add import:

```typescript
import ParametricStudyListSidebar from "./ParametricStudyListSidebar";
```

Wrap the existing routing return values in a flex row with the sidebar. Replace the bottom of `ParametricView`:

```typescript
  let content: React.ReactNode;
  if (current === null) {
    content = <ParametricSetupForm />;
  } else if (current.status === "running") {
    content = <ParametricRunGrid />;
  } else {
    content = <ParametricResultsView />;
  }

  return (
    <div className="flex h-full">
      <div className="flex-1 overflow-hidden">{content}</div>
      <ParametricStudyListSidebar />
    </div>
  );
}
```

- [ ] **Step 20.3: Verify build**

Run: `cd gui-frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 20.4: Commit**

```bash
git add gui-frontend/src/components/parametric/ParametricStudyListSidebar.tsx \
        gui-frontend/src/components/parametric/ParametricView.tsx
git commit -m "feat(parametric): add study list sidebar"
```

---

### Task 21: End-to-end smoke test and final cleanup

**Files:**
- None (manual testing)

- [ ] **Step 21.1: Full test suite**

Run: `pytest tests/test_parametric_*.py -v`
Expected: All tests pass, including the slow integration test.

- [ ] **Step 21.2: Frontend typecheck**

Run: `cd gui-frontend && npm run build`
Expected: Clean build, zero TypeScript errors.

- [ ] **Step 21.3: Build and stage the frontend bundle**

Run: `python scripts/build_gui.py`
Expected: The React bundle is copied to `engine_simulator/gui/static/`.

- [ ] **Step 21.4: Manual smoke test — full study**

Start the backend: `python -m engine_simulator.gui`

In the browser:
1. Click the **Parametric [04]** tab
2. Fill the form: name "Plenum test", parameter "Plenum Volume", value range 0.5–3.0 L step 0.5 L, RPM 6000–9000 step 1000, cycles 2, workers 4
3. Click **Start Study**
4. Verify **Mode B** shows the run grid with live progress cards
5. Verify each card's sparkline grows as RPMs complete
6. When the study finishes, verify **Mode C** automatically appears with:
   - Overlay charts showing 6 colored curves
   - Comparison table ranked by Peak HP
   - Heatmap with sweet-spot dots
7. Click other objectives (Peak Torque, Torque Area, HP @ RPM) and verify the table re-ranks instantly
8. Toggle runs in the legend and verify overlay charts respond
9. Click **New Study** → form reappears
10. Click the study in the sidebar → Mode C reappears with the saved data
11. Reload the browser and verify the study list still contains the run

- [ ] **Step 21.5: Verify no regressions in other tabs**

Click **Simulation**, **Config**, **Dyno** tabs in turn. Start a regular sweep from the **Simulation** tab and verify it still works end to end. The parametric tab should not interfere.

- [ ] **Step 21.6: Final commit**

If any small fixes came up during smoke testing, commit them now:

```bash
git add -A
git commit -m "feat(parametric): final polish and smoke-test fixes"
```

---

## Summary

This plan implements the Parametric Study tab in 21 tasks across 5 phases:

1. **Phase 1 (Tasks 1-2):** Parameter whitelist + path resolver
2. **Phase 2 (Tasks 3-6):** Schema, persistence, event bridging, study manager
3. **Phase 3 (Tasks 7-8):** REST routes, server wiring, integration test
4. **Phase 4 (Tasks 9-13):** Frontend types, API client, store, selectors, event routing
5. **Phase 5 (Tasks 14-21):** Tab shell, setup form, run grid, results view (charts + table + heatmap), sidebar, smoke test

Every backend task follows red-green-refactor TDD. Frontend tasks rely on TypeScript strict compilation plus manual browser verification, with derived logic isolated in pure-function selectors that can be unit-tested later without refactoring.

The existing `SweepManager`, `sweepStore`, and the three existing tabs are never modified — the feature is fully additive.

