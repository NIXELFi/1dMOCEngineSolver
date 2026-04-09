# Engine Configuration Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **For frontend tasks:** match the visual identity of the existing `RunSweepDialog` and `TopBar` — corner brackets, `[NN]` index marks, JetBrains Mono tabular-nums on numerics, sharp 1px hairlines, accent color reserved for the primary action. Reference points are Linear, Vercel, Cursor, Bloomberg Terminal — NOT Material Design.

**Goal:** Add an in-GUI editor for the engine configuration JSON. New "Config" tab with typed forms covering every field in `EngineConfig`. Save in place, Save As to create variants. Active config is shared with the Run Sweep dialog so the dialog defaults to whatever's loaded in the editor.

**Architecture:** A new Pydantic schema (`engine_simulator/gui/config_schema.py`) mirrors the dataclass tree in `engine_config.py` and is used by two new endpoints (`PUT /api/configs/{name}`, `POST /api/configs`) to validate edits at the API boundary. The frontend gets a new zustand store (`configStore.ts`) holding the catalog, the active draft, and a clean copy for dirty detection. Reusable form primitives (`NumericField`, `CornerBrackets`, `TextField`, `Accordion`, `CdTableEditor`, `PipeRow`) live under `gui-frontend/src/components/forms/` and are shared between the existing `RunSweepDialog` and the new `ConfigView`. A `TabBar` row inserted into `App.tsx` swaps the main pane between an extracted `SimulationView` (today's content) and the new `ConfigView`.

**Tech Stack:** Python 3.9, FastAPI, Pydantic v2, pytest. React 18, TypeScript, Vite, TailwindCSS, Zustand.

**Spec:** `docs/superpowers/specs/2026-04-09-engine-config-editor-design.md`

---

## File Structure

**New Python files:**

| Path | Responsibility |
|---|---|
| `engine_simulator/gui/config_schema.py` | Pydantic models mirroring `engine_config.py` dataclasses |

**New Python test files:**

| Path | Layer |
|---|---|
| `tests/test_config_schema.py` | Round-trip equivalence: Pydantic ↔ `load_config()` |
| `tests/test_config_routes.py` | REST endpoint integration tests for save / save-as / validation |

**New frontend files:**

| Path | Responsibility |
|---|---|
| `gui-frontend/src/state/configStore.ts` | Zustand store for active config + draft + dirty tracking |
| `gui-frontend/src/components/SimulationView.tsx` | Extracted body of current `App.tsx` (Sweep curves + workers + RPM detail) |
| `gui-frontend/src/components/TabBar.tsx` | Tab navigation strip below TopBar |
| `gui-frontend/src/components/ConfigView.tsx` | Top-level Config tab: sticky header + accordion sections |
| `gui-frontend/src/components/forms/NumericField.tsx` | Numeric input with `[NN]` index, label, unit ornament, error row (moved from `RunSweepDialog`) |
| `gui-frontend/src/components/forms/CornerBrackets.tsx` | Decorative chassis corner marks (moved from `RunSweepDialog`) |
| `gui-frontend/src/components/forms/TextField.tsx` | String input mirroring `NumericField` for `name` and `firing_order` |
| `gui-frontend/src/components/forms/Accordion.tsx` | Numbered collapsible section header + body |
| `gui-frontend/src/components/forms/CdTableEditor.tsx` | Inline (L/D, Cd) row editor |
| `gui-frontend/src/components/forms/PipeRow.tsx` | Single-row pipe field cluster |
| `gui-frontend/src/components/config/IdentitySection.tsx` | name, n_cylinders, firing_order, firing_interval |
| `gui-frontend/src/components/config/CylinderSection.tsx` | bore, stroke, con_rod_length, compression_ratio, valve counts |
| `gui-frontend/src/components/config/ValveSection.tsx` | Used for intake_valve and exhaust_valve |
| `gui-frontend/src/components/config/PipeListSection.tsx` | Used for intake_pipes, exhaust_primaries, exhaust_secondaries |
| `gui-frontend/src/components/config/PipeRowSection.tsx` | Used for the single exhaust_collector pipe |
| `gui-frontend/src/components/config/CombustionSection.tsx` | All combustion fields |
| `gui-frontend/src/components/config/RestrictorSection.tsx` | All restrictor fields |
| `gui-frontend/src/components/config/PlenumSection.tsx` | All plenum fields |
| `gui-frontend/src/components/config/SimulationSection.tsx` | All simulation fields |
| `gui-frontend/src/components/config/AmbientSection.tsx` | p_ambient, T_ambient, drivetrain_efficiency |

**Modified files:**

| Path | Changes |
|---|---|
| `engine_simulator/gui/routes_api.py` | Add `_validate_name`, `PUT /api/configs/{name}`, `POST /api/configs` |
| `gui-frontend/src/api/client.ts` | Add `EngineConfigPayload` type + `getConfig`, `saveConfig`, `saveConfigAs` |
| `gui-frontend/src/App.tsx` | Insert `<TabBar/>` row, swap main pane between `<SimulationView/>` and `<ConfigView/>` |
| `gui-frontend/src/components/RunSweepDialog.tsx` | Drop `PREFERRED_CONFIG`, read `activeName` from `configStore`, update import paths for moved primitives, add dirty-config warning strip |

**Files NOT touched:**
- `engine_simulator/config/engine_config.py` (dataclasses + `load_config()`)
- `engine_simulator/engine/`, `gas_dynamics/`, `boundaries/`, `simulation/`, `postprocessing/`
- `engine_simulator/main.py` (CLI)
- `engine_simulator/gui/sweep_manager.py`, `gui_event_consumer.py`, `routes_ws.py`, `server.py`, `persistence.py`, `snapshot.py`

---

## Phase A: Backend Pydantic schema & save endpoints

End of phase: Pydantic models accept the existing `cbr600rr.json`, round-trip cleanly to `load_config()`, and `PUT`/`POST` endpoints save to disk with field-level validation errors on bad input.

### Task A1: Create the Pydantic schema mirroring `engine_config.py`

**Files:**
- Create: `engine_simulator/gui/config_schema.py`

- [ ] **Step 1: Create the schema file with all models**

Create `engine_simulator/gui/config_schema.py`:

```python
"""Pydantic models mirroring engine_simulator/config/engine_config.py.

Used by the GUI's PUT/POST config endpoints for validation. The parallel
schema is intentional — runtime introspection of the dataclasses is fragile
(loses field constraints, awkward Optional/list handling, no cross-field
rules). The drift between this file and engine_config.py is caught by
test_pydantic_round_trip in tests/test_config_schema.py.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CylinderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bore: float = Field(gt=0)
    stroke: float = Field(gt=0)
    con_rod_length: float = Field(gt=0)
    compression_ratio: float = Field(gt=1)
    n_intake_valves: int = Field(default=2, ge=1)
    n_exhaust_valves: int = Field(default=2, ge=1)


class ValveModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diameter: float = Field(gt=0)
    max_lift: float = Field(gt=0)
    open_angle: float = Field(ge=0)
    close_angle: float = Field(ge=0)
    seat_angle: float = Field(default=45.0, ge=0, le=90)
    cd_table: list[tuple[float, float]] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_angles(self):
        if self.close_angle <= self.open_angle:
            raise ValueError("close_angle must exceed open_angle")
        return self


class PipeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    length: float = Field(gt=0)
    diameter: float = Field(gt=0)
    diameter_out: Optional[float] = Field(default=None, gt=0)
    n_points: int = Field(default=30, ge=2, le=200)
    wall_temperature: float = Field(default=320.0, gt=0)
    roughness: float = Field(default=0.03e-3, ge=0)


class CombustionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wiebe_a: float = Field(default=5.0, gt=0)
    wiebe_m: float = Field(default=2.0, gt=0)
    combustion_duration: float = Field(default=50.0, gt=0, le=180)
    spark_advance: float = Field(default=25.0)
    ignition_delay: float = Field(default=7.0, ge=0)
    combustion_efficiency: float = Field(default=0.96, gt=0, le=1)
    q_lhv: float = Field(default=43.5e6, gt=0)
    afr_stoich: float = Field(default=14.7, gt=0)
    afr_target: float = Field(default=13.1, gt=0)


class RestrictorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    throat_diameter: float = Field(default=0.020, gt=0)
    discharge_coefficient: float = Field(default=0.967, gt=0, le=1)
    converging_half_angle: float = Field(default=12.0, gt=0, lt=90)
    diverging_half_angle: float = Field(default=6.0, gt=0, lt=90)


class PlenumModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    volume: float = Field(default=1.5e-3, gt=0)
    initial_pressure: float = Field(default=101325.0, gt=0)
    initial_temperature: float = Field(default=300.0, gt=0)


class SimulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rpm_start: float = Field(default=6000.0, gt=0)
    rpm_end: float = Field(default=13500.0, gt=0)
    rpm_step: float = Field(default=500.0, gt=0)
    n_cycles: int = Field(default=12, ge=1, le=200)
    cfl_number: float = Field(default=0.85, gt=0, le=1)
    convergence_tolerance: float = Field(default=0.005, gt=0)
    crank_step_max: float = Field(default=1.0, gt=0)
    artificial_viscosity: float = Field(default=0.05, ge=0)

    @model_validator(mode="after")
    def _check_rpm_range(self):
        if self.rpm_end <= self.rpm_start:
            raise ValueError("rpm_end must exceed rpm_start")
        return self


class EnginePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Custom Engine", min_length=1)
    n_cylinders: int = Field(default=4, ge=1)
    firing_order: list[int] = Field(default_factory=lambda: [1, 2, 4, 3], min_length=1)
    firing_interval: float = Field(default=180.0, gt=0)
    cylinder: CylinderModel
    intake_valve: ValveModel
    exhaust_valve: ValveModel
    intake_pipes: list[PipeModel] = Field(min_length=1)
    exhaust_primaries: list[PipeModel] = Field(min_length=1)
    exhaust_secondaries: list[PipeModel] = Field(min_length=1)
    exhaust_collector: PipeModel
    combustion: CombustionModel = Field(default_factory=CombustionModel)
    restrictor: RestrictorModel = Field(default_factory=RestrictorModel)
    plenum: PlenumModel = Field(default_factory=PlenumModel)
    simulation: SimulationModel = Field(default_factory=SimulationModel)
    p_ambient: float = Field(default=101325.0, gt=0)
    T_ambient: float = Field(default=300.0, gt=0)
    drivetrain_efficiency: float = Field(default=1.0, gt=0, le=1)
```

- [ ] **Step 2: Quick syntax check**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -c "from engine_simulator.gui.config_schema import EnginePayload; print('ok')"`
Expected: `ok` (no exceptions).

- [ ] **Step 3: Commit**

```bash
git add engine_simulator/gui/config_schema.py
git commit -m "feat(gui): add Pydantic schema mirroring EngineConfig dataclasses

Mirrors every dataclass in engine_config.py with field validation rules
(positive numbers, ranges, cross-field checks like close_angle > open_angle).
Used by upcoming PUT/POST config endpoints to validate edits at the API
boundary. Drift from the dataclass shape is caught by the round-trip test
in the next task."
```

---

### Task A2: Round-trip equivalence test for the Pydantic schema

**Files:**
- Create: `tests/test_config_schema.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_schema.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_config_schema.py -v`
Expected: All 5 tests pass.

If `test_pydantic_dump_loads_via_load_config` fails, the diff between `_normalize(round_tripped)` and `_normalize(original_cfg)` is the schema drift — likely a field with wrong type, missing default, or a tuple-vs-list mismatch in `cd_table`. Fix `config_schema.py`, not the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_config_schema.py
git commit -m "test(gui): round-trip equivalence Pydantic ↔ load_config()

Loads cbr600rr.json through both engine_config.load_config() and
EnginePayload.model_validate(), dumps the pydantic side back to JSON,
re-loads via load_config(), and asserts field-by-field equivalence.
This is the critical drift detector — if engine_config.py adds a field
without a corresponding update to config_schema.py, this test fires."
```

---

### Task A3: Add `PUT /api/configs/{name}` endpoint

**Files:**
- Modify: `engine_simulator/gui/routes_api.py`
- Create: `tests/test_config_routes.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_routes.py`:

```python
"""REST endpoint tests for config save/save-as.

Uses FastAPI's TestClient. monkeypatch get_configs_dir() to a tmp_path
so the real cbr600rr.json is never touched.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REAL_CBR = (
    Path(__file__).resolve().parents[1]
    / "engine_simulator"
    / "config"
    / "cbr600rr.json"
)


@pytest.fixture
def configs_dir(tmp_path, monkeypatch):
    """Isolated configs directory seeded with a copy of cbr600rr.json."""
    shutil.copy(REAL_CBR, tmp_path / "cbr600rr.json")
    from engine_simulator.gui import routes_api
    monkeypatch.setattr(routes_api, "get_configs_dir", lambda: str(tmp_path))
    return tmp_path


@pytest.fixture
def client(configs_dir):
    from engine_simulator.gui.server import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


def _valid_payload(configs_dir):
    with open(configs_dir / "cbr600rr.json") as f:
        return json.load(f)


class TestSaveInPlace:
    def test_put_with_valid_payload_writes_file(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["intake_valve"]["open_angle"] = 339.5
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 200
        # Re-read from disk and check the change persisted
        with open(configs_dir / "cbr600rr.json") as f:
            on_disk = json.load(f)
        assert on_disk["intake_valve"]["open_angle"] == 339.5

    def test_put_to_nonexistent_returns_404(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        response = client.put("/api/configs/missing.json", json=payload)
        assert response.status_code == 404

    def test_put_with_negative_bore_returns_422(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["cylinder"]["bore"] = -1
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 422
        details = response.json()["detail"]
        # Pydantic 422 detail is a list of {loc, msg, type, ...}
        assert any("bore" in entry["loc"] for entry in details)

    def test_put_with_compression_ratio_below_one_returns_422(
        self, client, configs_dir
    ):
        payload = _valid_payload(configs_dir)
        payload["cylinder"]["compression_ratio"] = 0.5
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 422

    def test_put_with_dc_above_one_returns_422(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["restrictor"]["discharge_coefficient"] = 1.5
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 422

    def test_put_with_close_before_open_returns_422(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["intake_valve"]["close_angle"] = (
            payload["intake_valve"]["open_angle"] - 1
        )
        response = client.put("/api/configs/cbr600rr.json", json=payload)
        assert response.status_code == 422
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_config_routes.py::TestSaveInPlace -v`
Expected: All tests fail because `PUT /api/configs/{name}` does not exist (currently returns 405 Method Not Allowed).

- [ ] **Step 3: Add `_validate_name` and the PUT endpoint**

Read `engine_simulator/gui/routes_api.py` first. Add this just below the existing imports (after the `Path` and `BaseModel` imports):

```python
import re

_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+\.json$")


def _validate_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid config name: {name!r}")
    return name
```

Then add this endpoint just after the existing `@router.get("/configs/{name}")` block:

```python
from engine_simulator.gui.config_schema import EnginePayload


@router.put("/configs/{name}")
async def save_config(name: str, payload: EnginePayload):
    name = _validate_name(name)
    config_path = Path(get_configs_dir()) / name
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config not found: {name}")
    config_path.write_text(payload.model_dump_json(indent=4))
    return payload.model_dump(mode="json")
```

Note: place the `from engine_simulator.gui.config_schema import EnginePayload` near the other top-level imports, not inside the function — the existing code does some lazy `from engine_simulator.gui import server` imports inside functions to dodge circular imports, but `config_schema` has no such risk.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_config_routes.py::TestSaveInPlace -v`
Expected: All 6 tests in `TestSaveInPlace` pass.

- [ ] **Step 5: Run the full backend test suite to make sure nothing else broke**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest -q`
Expected: All previously passing tests still pass; the new tests pass.

- [ ] **Step 6: Commit**

```bash
git add engine_simulator/gui/routes_api.py tests/test_config_routes.py
git commit -m "feat(gui): PUT /api/configs/{name} endpoint with field validation

Validates filename via regex (no path traversal, no separators), validates
payload via the new EnginePayload pydantic model, writes to disk on success,
returns the dumped payload. Field-level errors come back as pydantic 422s
that the frontend will turn into per-field highlights."
```

---

### Task A4: Add `POST /api/configs` Save As endpoint

**Files:**
- Modify: `engine_simulator/gui/routes_api.py`
- Modify: `tests/test_config_routes.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_config_routes.py`:

```python
class TestSaveAs:
    def test_post_creates_new_file(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "tweaked.json", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 200
        assert (configs_dir / "tweaked.json").exists()

    def test_post_lists_via_get_configs(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "tweaked.json", "payload": payload}
        client.post("/api/configs", json=body)
        listing = client.get("/api/configs").json()
        names = [c["name"] for c in listing]
        assert "tweaked.json" in names

    def test_post_rejects_existing_name(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "cbr600rr.json", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 409

    def test_post_with_invalid_payload_returns_422(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        payload["cylinder"]["bore"] = -1
        body = {"name": "broken.json", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 422
        # And the file must NOT have been written
        assert not (configs_dir / "broken.json").exists()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_config_routes.py::TestSaveAs -v`
Expected: All 4 tests fail because `POST /api/configs` does not exist.

- [ ] **Step 3: Add the endpoint**

Append to `engine_simulator/gui/routes_api.py` (after the `save_config` PUT endpoint):

```python
class SaveAsRequest(BaseModel):
    name: str
    payload: EnginePayload


@router.post("/configs")
async def save_config_as(req: SaveAsRequest):
    name = _validate_name(req.name)
    config_path = Path(get_configs_dir()) / name
    if config_path.exists():
        raise HTTPException(
            status_code=409, detail=f"Config already exists: {name}"
        )
    config_path.write_text(req.payload.model_dump_json(indent=4))
    return req.payload.model_dump(mode="json")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_config_routes.py::TestSaveAs -v`
Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add engine_simulator/gui/routes_api.py tests/test_config_routes.py
git commit -m "feat(gui): POST /api/configs (Save As) with name uniqueness check

Returns 409 if the target name already exists — protects against silent
overwrites via Save As. The PUT endpoint is the explicit overwrite path."
```

---

### Task A5: Filename validation rejection tests

**Files:**
- Modify: `tests/test_config_routes.py`

- [ ] **Step 1: Add the rejection tests**

Append to `tests/test_config_routes.py`:

```python
class TestFilenameValidation:
    def test_put_rejects_path_separator(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        response = client.put("/api/configs/foo%2Fbar.json", json=payload)
        # FastAPI will URL-decode the path; either 400 (our regex) or 404
        # depending on how the routing resolves; both indicate rejection.
        assert response.status_code in (400, 404)

    def test_post_rejects_traversal(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "../etc/passwd.json", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 400

    def test_post_rejects_dotfile(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": ".secret.json", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 400

    def test_post_rejects_no_json_extension(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "tweaked", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 400

    def test_post_rejects_double_extension(self, client, configs_dir):
        payload = _valid_payload(configs_dir)
        body = {"name": "tweaked.json.bak", "payload": payload}
        response = client.post("/api/configs", json=body)
        assert response.status_code == 400
```

- [ ] **Step 2: Run the tests**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_config_routes.py::TestFilenameValidation -v`
Expected: All 5 tests pass (the existing `_validate_name` regex `^[A-Za-z0-9_\-]+\.json$` already handles all of them).

- [ ] **Step 3: Run the full test suite**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest -q`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_config_routes.py
git commit -m "test(gui): filename rejection coverage for config endpoints

Verifies the _validate_name regex blocks path separators, traversal,
dotfiles, missing/double extensions on both PUT and POST."
```

---

## Phase B: Frontend foundation

End of phase: shared form primitives extracted out of `RunSweepDialog` and importable, `configStore` exists with type definitions, API client has the new methods, and the app has a tab bar with two tabs (`Simulation` and `Config`) — clicking `Config` shows an empty placeholder.

### Task B1: Extract `NumericField` and `CornerBrackets` into `forms/`

**Files:**
- Create: `gui-frontend/src/components/forms/NumericField.tsx`
- Create: `gui-frontend/src/components/forms/CornerBrackets.tsx`
- Modify: `gui-frontend/src/components/RunSweepDialog.tsx` (remove inline definitions, add imports)

- [ ] **Step 1: Create `NumericField.tsx`**

Create `gui-frontend/src/components/forms/NumericField.tsx`:

```tsx
import * as React from "react";

export interface NumericFieldProps {
  index: string;          // "01" — shown in the [NN] index mark
  label: string;
  unit: string;
  value: number;
  onChange: (next: number) => void;
  error?: string;
  inputRef?: React.Ref<HTMLInputElement>;
  step?: number;
  min?: number;
  /** Multiply the stored value by this when displaying; divide on input. */
  displayScale?: number;
}

/**
 * Numeric input matching the engine-sim instrument-chassis aesthetic.
 *
 * Shared by RunSweepDialog and the Config tab. Pattern: small [NN]
 * index mark on the left of the label row, label in muted small caps,
 * inline unit ornament on the right of the input, optional inline error
 * pinned to the right of the label row.
 */
export function NumericField({
  index,
  label,
  unit,
  value,
  onChange,
  error,
  inputRef,
  step,
  min,
  displayScale = 1,
}: NumericFieldProps) {
  const display = Number.isFinite(value) ? value * displayScale : NaN;

  const handle = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (raw === "") {
      onChange(NaN);
      return;
    }
    const parsed = Number(raw);
    onChange(parsed / displayScale);
  };

  return (
    <label className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[9px] font-mono text-text-muted leading-none">
            [{index}]
          </span>
          <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-secondary leading-none">
            {label}
          </span>
        </div>
        {error && (
          <span className="text-[10px] font-mono text-status-error leading-none">
            {error}
          </span>
        )}
      </div>

      <div
        className={[
          "group flex items-stretch bg-surface border rounded",
          "transition-colors duration-150 ease-out",
          error
            ? "border-status-error/60 focus-within:border-status-error"
            : "border-border-default focus-within:border-border-emphasis",
        ].join(" ")}
      >
        <input
          ref={inputRef}
          type="number"
          value={Number.isNaN(display) ? "" : display}
          onChange={handle}
          step={step}
          min={min}
          inputMode="numeric"
          className={[
            "flex-1 min-w-0 bg-transparent outline-none",
            "px-3 py-2 text-sm font-mono tabular-nums text-text-primary",
            "placeholder:text-text-muted",
            "[appearance:textfield]",
            "[&::-webkit-outer-spin-button]:appearance-none [&::-webkit-outer-spin-button]:m-0",
            "[&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0",
          ].join(" ")}
        />
        <span className="flex items-center px-2 border-l border-border-default text-[9px] font-mono uppercase tracking-widest text-text-muted select-none">
          {unit}
        </span>
      </div>
    </label>
  );
}
```

Note: this differs from the version in `RunSweepDialog.tsx` in two ways. (1) `onChange` now takes a parsed number instead of a `ChangeEvent` — this removes per-call-site `setNum` boilerplate and makes the displayScale conversion possible. (2) `displayScale` prop is added for SI ↔ display unit conversion.

- [ ] **Step 2: Create `CornerBrackets.tsx`**

Create `gui-frontend/src/components/forms/CornerBrackets.tsx`:

```tsx
/**
 * Decorative chassis corner marks for instrument-style panels.
 * Used by RunSweepDialog and any framed surface in the Config tab.
 */
export function CornerBrackets() {
  const common = "absolute w-2 h-2 border-border-emphasis pointer-events-none";
  return (
    <>
      <span className={`${common} -top-px -left-px border-t border-l`} aria-hidden />
      <span className={`${common} -top-px -right-px border-t border-r`} aria-hidden />
      <span className={`${common} -bottom-px -left-px border-b border-l`} aria-hidden />
      <span className={`${common} -bottom-px -right-px border-b border-r`} aria-hidden />
    </>
  );
}
```

- [ ] **Step 3: Update `RunSweepDialog.tsx` to import the shared primitives**

Read `gui-frontend/src/components/RunSweepDialog.tsx`. Make these changes:

1. Add an import at the top, near the other imports:

```tsx
import { NumericField } from "./forms/NumericField";
import { CornerBrackets } from "./forms/CornerBrackets";
```

2. Delete the inline `function NumericField(...)` definition (around line 422–486 in the original file).
3. Delete the inline `function CornerBrackets()` definition (around line 695–711 in the original file).
4. Update the call sites of `NumericField` to pass `onChange={(n) => setForm((p) => ({ ...p, rpm_start: n }))}` style instead of `onChange={setNum("rpm_start")}`. The new signature takes a number, not a ChangeEvent.

Specifically, replace the existing `setNum` helper definition and its uses. Replace:

```tsx
const setNum =
  (key: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    const parsed = raw === "" ? NaN : Number(raw);
    setForm((prev) => ({ ...prev, [key]: parsed }));
  };
```

with:

```tsx
const setField = (key: keyof FormState) => (next: number) => {
  setForm((prev) => ({ ...prev, [key]: next }));
};
```

And replace the four `NumericField` invocations in the form body. Each looks like:

```tsx
<NumericField
  index="01"
  label="RPM Start"
  unit="rpm"
  value={form.rpm_start}
  onChange={setNum("rpm_start")}   // ← old
  ...
/>
```

becomes:

```tsx
<NumericField
  index="01"
  label="RPM Start"
  unit="rpm"
  value={form.rpm_start}
  onChange={setField("rpm_start")}  // ← new
  ...
/>
```

- [ ] **Step 4: Build the frontend to verify TypeScript compiles**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -20`
Expected: `vite build` succeeds. No TypeScript errors. Output shows the bundle size summary.

If there are errors about missing exports or signature mismatches, fix them. The most likely issue is forgetting to update one of the four `NumericField` call sites.

- [ ] **Step 5: Commit**

```bash
git add gui-frontend/src/components/forms/NumericField.tsx \
        gui-frontend/src/components/forms/CornerBrackets.tsx \
        gui-frontend/src/components/RunSweepDialog.tsx
git commit -m "refactor(gui): extract NumericField + CornerBrackets to forms/

Shared primitives for both RunSweepDialog and the upcoming Config tab.
NumericField's onChange now takes a parsed number instead of a
ChangeEvent, and adds displayScale for SI <-> display unit conversion."
```

---

### Task B2: Add `TextField` primitive

**Files:**
- Create: `gui-frontend/src/components/forms/TextField.tsx`

- [ ] **Step 1: Create the file**

Create `gui-frontend/src/components/forms/TextField.tsx`:

```tsx
import * as React from "react";

export interface TextFieldProps {
  index: string;
  label: string;
  unit?: string;
  value: string;
  onChange: (next: string) => void;
  error?: string;
  placeholder?: string;
}

/**
 * String input matching NumericField's visual treatment. Used for `name`
 * and `firing_order` in the Config tab.
 */
export function TextField({
  index,
  label,
  unit,
  value,
  onChange,
  error,
  placeholder,
}: TextFieldProps) {
  return (
    <label className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[9px] font-mono text-text-muted leading-none">
            [{index}]
          </span>
          <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-secondary leading-none">
            {label}
          </span>
        </div>
        {error && (
          <span className="text-[10px] font-mono text-status-error leading-none">
            {error}
          </span>
        )}
      </div>

      <div
        className={[
          "flex items-stretch bg-surface border rounded",
          "transition-colors duration-150 ease-out",
          error
            ? "border-status-error/60 focus-within:border-status-error"
            : "border-border-default focus-within:border-border-emphasis",
        ].join(" ")}
      >
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 min-w-0 bg-transparent outline-none px-3 py-2 text-sm font-mono text-text-primary placeholder:text-text-muted"
        />
        {unit && (
          <span className="flex items-center px-2 border-l border-border-default text-[9px] font-mono uppercase tracking-widest text-text-muted select-none">
            {unit}
          </span>
        )}
      </div>
    </label>
  );
}
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add gui-frontend/src/components/forms/TextField.tsx
git commit -m "feat(gui): TextField primitive matching NumericField style"
```

---

### Task B3: Create `configStore.ts` (zustand)

**Files:**
- Create: `gui-frontend/src/state/configStore.ts`

- [ ] **Step 1: Define the types and store**

Create `gui-frontend/src/state/configStore.ts`:

```ts
import { create } from "zustand";
import type { ConfigSummary } from "../api/client";

/* ========================================================================== */
/* Payload types — must match engine_simulator/gui/config_schema.py            */
/* ========================================================================== */

export interface CylinderPayload {
  bore: number;
  stroke: number;
  con_rod_length: number;
  compression_ratio: number;
  n_intake_valves: number;
  n_exhaust_valves: number;
}

export interface ValvePayload {
  diameter: number;
  max_lift: number;
  open_angle: number;
  close_angle: number;
  seat_angle: number;
  cd_table: [number, number][];
}

export interface PipePayload {
  name: string;
  length: number;
  diameter: number;
  diameter_out: number | null;
  n_points: number;
  wall_temperature: number;
  roughness: number;
}

export interface CombustionPayload {
  wiebe_a: number;
  wiebe_m: number;
  combustion_duration: number;
  spark_advance: number;
  ignition_delay: number;
  combustion_efficiency: number;
  q_lhv: number;
  afr_stoich: number;
  afr_target: number;
}

export interface RestrictorPayload {
  throat_diameter: number;
  discharge_coefficient: number;
  converging_half_angle: number;
  diverging_half_angle: number;
}

export interface PlenumPayload {
  volume: number;
  initial_pressure: number;
  initial_temperature: number;
}

export interface SimulationPayload {
  rpm_start: number;
  rpm_end: number;
  rpm_step: number;
  n_cycles: number;
  cfl_number: number;
  convergence_tolerance: number;
  crank_step_max: number;
  artificial_viscosity: number;
}

export interface EngineConfigPayload {
  name: string;
  n_cylinders: number;
  firing_order: number[];
  firing_interval: number;
  cylinder: CylinderPayload;
  intake_valve: ValvePayload;
  exhaust_valve: ValvePayload;
  intake_pipes: PipePayload[];
  exhaust_primaries: PipePayload[];
  exhaust_secondaries: PipePayload[];
  exhaust_collector: PipePayload;
  combustion: CombustionPayload;
  restrictor: RestrictorPayload;
  plenum: PlenumPayload;
  simulation: SimulationPayload;
  p_ambient: number;
  T_ambient: number;
  drivetrain_efficiency: number;
}

export type PipeArrayKey =
  | "intake_pipes"
  | "exhaust_primaries"
  | "exhaust_secondaries";

export type ValveKey = "intake_valve" | "exhaust_valve";

/* ========================================================================== */
/* Store                                                                      */
/* ========================================================================== */

export type ActiveTab = "simulation" | "config";

export interface ConfigStore {
  // Catalog
  available: ConfigSummary[];

  // Active document
  activeName: string | null;
  saved: EngineConfigPayload | null;
  draft: EngineConfigPayload | null;

  // UI
  activeTab: ActiveTab;
  expandedSections: Record<string, boolean>;

  // Status
  loading: boolean;
  saving: boolean;
  loadError: string | null;
  saveError: string | null;
  saveFlash: number | null;
  fieldErrors: Record<string, string>;

  // Actions
  setActiveTab: (tab: ActiveTab) => void;
  setAvailable: (list: ConfigSummary[]) => void;
  setActive: (
    name: string,
    payload: EngineConfigPayload,
  ) => void;
  setLoading: (loading: boolean) => void;
  setLoadError: (error: string | null) => void;
  setSaving: (saving: boolean) => void;
  setSaveError: (error: string | null) => void;
  setFieldErrors: (errors: Record<string, string>) => void;
  flashSaved: () => void;
  setField: (path: string, value: unknown) => void;
  addPipe: (section: PipeArrayKey) => void;
  removePipe: (section: PipeArrayKey, index: number) => void;
  addCdRow: (valve: ValveKey) => void;
  removeCdRow: (valve: ValveKey, index: number) => void;
  revert: () => void;
  toggleSection: (id: string) => void;
}

/* ----- helpers ----- */

function setByPath(obj: any, path: string, value: unknown): any {
  const segments = path.split(".");
  if (segments.length === 0) return value;
  const next = Array.isArray(obj) ? [...obj] : { ...obj };
  let cur = next;
  for (let i = 0; i < segments.length - 1; i++) {
    const seg = segments[i];
    const child = cur[seg];
    cur[seg] = Array.isArray(child) ? [...child] : { ...child };
    cur = cur[seg];
  }
  cur[segments[segments.length - 1]] = value;
  return next;
}

const DEFAULT_PIPE = (name: string): PipePayload => ({
  name,
  length: 0.25,
  diameter: 0.038,
  diameter_out: null,
  n_points: 30,
  wall_temperature: 325.0,
  roughness: 3e-5,
});

const DEFAULT_CD_ROW: [number, number] = [0.1, 0.4];

/* ----- store ----- */

export const useConfigStore = create<ConfigStore>((set) => ({
  available: [],
  activeName: null,
  saved: null,
  draft: null,
  activeTab: "simulation",
  expandedSections: {},
  loading: false,
  saving: false,
  loadError: null,
  saveError: null,
  saveFlash: null,
  fieldErrors: {},

  setActiveTab: (tab) => set({ activeTab: tab }),
  setAvailable: (list) => set({ available: list }),
  setActive: (name, payload) =>
    set({
      activeName: name,
      saved: payload,
      draft: payload,
      fieldErrors: {},
      saveError: null,
      loadError: null,
    }),
  setLoading: (loading) => set({ loading }),
  setLoadError: (error) => set({ loadError: error }),
  setSaving: (saving) => set({ saving }),
  setSaveError: (error) => set({ saveError: error }),
  setFieldErrors: (errors) => set({ fieldErrors: errors }),
  flashSaved: () => set({ saveFlash: Date.now() }),

  setField: (path, value) =>
    set((s) => {
      if (s.draft === null) return s;
      return { draft: setByPath(s.draft, path, value) };
    }),

  addPipe: (section) =>
    set((s) => {
      if (s.draft === null) return s;
      const list = s.draft[section];
      const newName = `${section}_${list.length + 1}`;
      return {
        draft: setByPath(s.draft, section, [...list, DEFAULT_PIPE(newName)]),
      };
    }),

  removePipe: (section, index) =>
    set((s) => {
      if (s.draft === null) return s;
      const list = s.draft[section].filter((_, i) => i !== index);
      return { draft: setByPath(s.draft, section, list) };
    }),

  addCdRow: (valve) =>
    set((s) => {
      if (s.draft === null) return s;
      const rows: [number, number][] = [
        ...s.draft[valve].cd_table,
        DEFAULT_CD_ROW,
      ];
      return { draft: setByPath(s.draft, `${valve}.cd_table`, rows) };
    }),

  removeCdRow: (valve, index) =>
    set((s) => {
      if (s.draft === null) return s;
      const rows = s.draft[valve].cd_table.filter((_, i) => i !== index);
      return { draft: setByPath(s.draft, `${valve}.cd_table`, rows) };
    }),

  revert: () =>
    set((s) => ({
      draft: s.saved,
      fieldErrors: {},
      saveError: null,
    })),

  toggleSection: (id) =>
    set((s) => ({
      expandedSections: {
        ...s.expandedSections,
        [id]: !(s.expandedSections[id] ?? true),
      },
    })),
}));

/* ========================================================================== */
/* Selectors                                                                  */
/* ========================================================================== */

export const selectIsDirty = (s: ConfigStore): boolean => {
  if (s.draft === null || s.saved === null) return false;
  return JSON.stringify(s.draft) !== JSON.stringify(s.saved);
};

export const selectIsSectionOpen = (id: string) => (s: ConfigStore): boolean => {
  return s.expandedSections[id] ?? true;
};
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add gui-frontend/src/state/configStore.ts
git commit -m "feat(gui): configStore with payload types, draft tracking, mutations

Zustand store mirroring sweepStore.ts pattern. Holds the available
config catalog, the active draft, a clean copy for dirty detection,
plus actions for setField (dot-path setter), pipe and cd_table
mutations, revert, and section toggle state."
```

---

### Task B4: Add API client methods for config save/load

**Files:**
- Modify: `gui-frontend/src/api/client.ts`

- [ ] **Step 1: Add types and methods**

Read `gui-frontend/src/api/client.ts`. Add a re-export and three new methods.

After the existing `import type { SweepSummary } from "../types/events";` line, add:

```ts
import type { EngineConfigPayload } from "../state/configStore";
export type { EngineConfigPayload };
```

Add a new interface near `ConfigSummary`:

```ts
export interface ApiFieldError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiValidationError {
  status: 422;
  fieldErrors: Record<string, string>;
}
```

Add a helper `parseFieldErrors` near `jsonFetch`:

```ts
function parseFieldErrors(detail: ApiFieldError[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const entry of detail) {
    // loc is e.g. ["body", "intake_valve", "cd_table", 0, 0]
    // skip the leading "body" segment
    const path = entry.loc
      .slice(1)
      .map((p) => String(p))
      .join(".");
    out[path] = entry.msg;
  }
  return out;
}
```

Add this helper above `api`:

```ts
async function jsonFetchWithFieldErrors<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${BASE}${url}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (response.status === 422) {
    const body = await response.json();
    const err = new Error("Validation failed") as Error & {
      fieldErrors: Record<string, string>;
      status: number;
    };
    err.fieldErrors = parseFieldErrors(body.detail ?? []);
    err.status = 422;
    throw err;
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      // body wasn't JSON
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
```

Inside the `api` object, after `getCurrentResults`, add:

```ts
  getConfig: (name: string) =>
    jsonFetch<EngineConfigPayload>(`/api/configs/${encodeURIComponent(name)}`),

  saveConfig: (name: string, payload: EngineConfigPayload) =>
    jsonFetchWithFieldErrors<EngineConfigPayload>(
      `/api/configs/${encodeURIComponent(name)}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    ),

  saveConfigAs: (name: string, payload: EngineConfigPayload) =>
    jsonFetchWithFieldErrors<EngineConfigPayload>(`/api/configs`, {
      method: "POST",
      body: JSON.stringify({ name, payload }),
    }),
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add gui-frontend/src/api/client.ts
git commit -m "feat(gui): api.getConfig / saveConfig / saveConfigAs

422 responses are parsed into a fieldErrors map keyed by dot-path so
each NumericField can render its server-side validation message inline."
```

---

### Task B5: Tab navigation — extract `SimulationView`, add `TabBar`, wire `App.tsx`

**Files:**
- Create: `gui-frontend/src/components/SimulationView.tsx`
- Create: `gui-frontend/src/components/TabBar.tsx`
- Modify: `gui-frontend/src/App.tsx`

- [ ] **Step 1: Create `SimulationView.tsx`**

Create `gui-frontend/src/components/SimulationView.tsx`:

```tsx
import SweepCurves from "./SweepCurves";
import WorkersStrip from "./WorkersStrip";
import RpmDetail from "./RpmDetail";

/**
 * The "live mission control" view: sweep curves, worker strip,
 * per-RPM detail panel. Lifted out of App.tsx so the new tab bar
 * can swap it with the Config view.
 */
export default function SimulationView() {
  return (
    <main className="flex-1 overflow-auto p-3 flex flex-col gap-3">
      <SweepCurves />
      <WorkersStrip />
      <RpmDetail />
    </main>
  );
}
```

- [ ] **Step 2: Create `TabBar.tsx`**

Create `gui-frontend/src/components/TabBar.tsx`:

```tsx
import { useConfigStore, type ActiveTab } from "../state/configStore";

interface TabDef {
  id: ActiveTab;
  label: string;
  index: string;
}

const TABS: TabDef[] = [
  { id: "simulation", label: "Simulation", index: "01" },
  { id: "config", label: "Config", index: "02" },
];

/**
 * Tab strip pinned below the TopBar. Two tabs in v2: Simulation (today's
 * mission control view) and Config (the new editor). Visual treatment
 * matches TopBar — sharp 1px hairlines, [NN] index marks, accent for the
 * active tab indicator.
 */
export default function TabBar() {
  const activeTab = useConfigStore((s) => s.activeTab);
  const setActiveTab = useConfigStore((s) => s.setActiveTab);

  return (
    <nav
      className="h-10 flex items-stretch bg-surface border-b border-border-default select-none font-ui"
      role="tablist"
      aria-label="Workspace tabs"
    >
      {TABS.map((tab) => {
        const active = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => setActiveTab(tab.id)}
            className={[
              "group relative inline-flex items-center gap-2 px-5 border-r border-border-default",
              "text-[11px] font-medium uppercase tracking-[0.18em] leading-none",
              "transition-colors duration-150 ease-out",
              active
                ? "bg-bg text-text-primary"
                : "text-text-muted hover:text-text-primary hover:bg-surface-raised",
            ].join(" ")}
          >
            <span className="text-[9px] font-mono text-text-muted">
              [{tab.index}]
            </span>
            <span>{tab.label}</span>
            {active && (
              <span
                className="absolute left-0 right-0 bottom-0 h-px bg-accent"
                aria-hidden
              />
            )}
          </button>
        );
      })}
      <div className="flex-1 border-r border-border-default" />
    </nav>
  );
}
```

- [ ] **Step 3: Update `App.tsx` to wire the tab bar**

Read `gui-frontend/src/App.tsx`. Replace the entire file with:

```tsx
import { useEffect, useState } from "react";
import TopBar from "./components/TopBar";
import TabBar from "./components/TabBar";
import RunSweepDialog from "./components/RunSweepDialog";
import SimulationView from "./components/SimulationView";
import SweepListSidebar from "./components/SweepListSidebar";
import { makeEventSocket } from "./api/websocket";
import { applyServerMessage } from "./state/eventReducer";
import { useConfigStore } from "./state/configStore";

export default function App() {
  const [runSweepDialogOpen, setRunSweepDialogOpen] = useState(false);
  const activeTab = useConfigStore((s) => s.activeTab);

  useEffect(() => {
    const sock = makeEventSocket();
    const unsub = sock.addListener(applyServerMessage);
    sock.connect();
    return () => {
      unsub();
      sock.close();
    };
  }, []);

  return (
    <div className="min-h-screen h-screen flex flex-col bg-bg text-text-primary font-ui">
      <TopBar
        onRunSweepClick={() => setRunSweepDialogOpen(true)}
        onLoadClick={() => {
          /* SweepListSidebar has its own toggle on the right edge */
        }}
      />
      <TabBar />

      <div className="flex-1 flex overflow-hidden">
        {activeTab === "simulation" ? (
          <SimulationView />
        ) : (
          <ConfigPlaceholder />
        )}
        <SweepListSidebar />
      </div>

      <RunSweepDialog
        isOpen={runSweepDialogOpen}
        onClose={() => setRunSweepDialogOpen(false)}
      />
    </div>
  );
}

/**
 * Stub Config view — replaced in the next phase by a real ConfigView
 * with sticky header and accordion sections. Lives inline here so the
 * tab navigation is fully wired without depending on a file we
 * haven't created yet.
 */
function ConfigPlaceholder() {
  return (
    <main className="flex-1 overflow-auto p-6 flex items-center justify-center text-text-muted text-xs uppercase tracking-[0.2em]">
      Config tab — coming up next
    </main>
  );
}
```

- [ ] **Step 4: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 5: Manual smoke test**

Start the dev server: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run dev` (background it or run in another terminal). Open http://localhost:5173 and verify:
- TabBar appears below the TopBar with two tabs.
- Clicking "Config" swaps the main pane to the placeholder text.
- Clicking "Simulation" swaps it back. The simulation view (SweepCurves, etc.) renders without errors.

Stop the dev server.

- [ ] **Step 6: Commit**

```bash
git add gui-frontend/src/components/SimulationView.tsx \
        gui-frontend/src/components/TabBar.tsx \
        gui-frontend/src/App.tsx
git commit -m "feat(gui): tab navigation with Simulation/Config tabs

Lifts the existing main pane into SimulationView.tsx and adds a TabBar
row between TopBar and the main flex row. Active tab state lives in
configStore. Config tab is a placeholder for now — real ConfigView
arrives in the next phase."
```

---

## Phase C: Config tab shell

End of phase: clicking the Config tab loads `cbr600rr.json` into the store, shows the sticky header (file dropdown, dirty dot, Save / Save As / Revert buttons), and the placeholder section list (no real sections wired up yet).

### Task C1: `Accordion` primitive

**Files:**
- Create: `gui-frontend/src/components/forms/Accordion.tsx`

- [ ] **Step 1: Create the file**

Create `gui-frontend/src/components/forms/Accordion.tsx`:

```tsx
import * as React from "react";
import { useConfigStore, selectIsSectionOpen } from "../../state/configStore";

interface AccordionProps {
  id: string;             // stable section id, e.g. "cylinder"
  index: string;          // "01" for the index mark
  label: string;
  rightSlot?: React.ReactNode;  // e.g. an "[+ pipe]" button
  children: React.ReactNode;
}

/**
 * Numbered, collapsible section header. State persisted in configStore
 * via `expandedSections`. Default is open.
 */
export function Accordion({ id, index, label, rightSlot, children }: AccordionProps) {
  const isOpen = useConfigStore(selectIsSectionOpen(id));
  const toggle = useConfigStore((s) => s.toggleSection);

  return (
    <section className="border border-border-default rounded">
      <header className="flex items-stretch border-b border-border-default bg-surface">
        <button
          type="button"
          onClick={() => toggle(id)}
          aria-expanded={isOpen}
          aria-controls={`accordion-body-${id}`}
          className="flex-1 flex items-center gap-2 px-4 py-2 text-left hover:bg-surface-raised transition-colors duration-150"
        >
          <span className="text-text-muted text-[10px] leading-none w-3">
            {isOpen ? "▾" : "▸"}
          </span>
          <span className="text-[9px] font-mono text-text-muted leading-none">
            [{index}]
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-primary leading-none">
            {label}
          </span>
        </button>
        {rightSlot && (
          <div className="flex items-center pr-3 border-l border-border-default px-3">
            {rightSlot}
          </div>
        )}
      </header>
      {isOpen && (
        <div
          id={`accordion-body-${id}`}
          className="p-4 bg-bg flex flex-col gap-4"
        >
          {children}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add gui-frontend/src/components/forms/Accordion.tsx
git commit -m "feat(gui): Accordion primitive with persisted expand/collapse state"
```

---

### Task C2: `ConfigView` shell with sticky header and load-on-mount

**Files:**
- Create: `gui-frontend/src/components/ConfigView.tsx`
- Modify: `gui-frontend/src/App.tsx` (replace the placeholder)

- [ ] **Step 1: Create `ConfigView.tsx`**

Create `gui-frontend/src/components/ConfigView.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  useConfigStore,
  selectIsDirty,
} from "../state/configStore";

const PREFERRED_DEFAULT = "cbr600rr.json";

/**
 * Top-level Config tab. Sticky header with file dropdown + dirty dot
 * + Save/Save As/Revert. Body is a stack of accordion sections (added
 * in later tasks).
 */
export default function ConfigView() {
  const available = useConfigStore((s) => s.available);
  const activeName = useConfigStore((s) => s.activeName);
  const draft = useConfigStore((s) => s.draft);
  const loading = useConfigStore((s) => s.loading);
  const saving = useConfigStore((s) => s.saving);
  const loadError = useConfigStore((s) => s.loadError);
  const saveError = useConfigStore((s) => s.saveError);
  const saveFlash = useConfigStore((s) => s.saveFlash);
  const isDirty = useConfigStore(selectIsDirty);

  const setAvailable = useConfigStore((s) => s.setAvailable);
  const setActive = useConfigStore((s) => s.setActive);
  const setLoading = useConfigStore((s) => s.setLoading);
  const setLoadError = useConfigStore((s) => s.setLoadError);
  const setSaving = useConfigStore((s) => s.setSaving);
  const setSaveError = useConfigStore((s) => s.setSaveError);
  const setFieldErrors = useConfigStore((s) => s.setFieldErrors);
  const flashSaved = useConfigStore((s) => s.flashSaved);
  const revert = useConfigStore((s) => s.revert);

  const [saveAsMode, setSaveAsMode] = useState(false);
  const [saveAsName, setSaveAsName] = useState("");
  const [saveAsError, setSaveAsError] = useState<string | null>(null);

  /* ---------------- Load on first mount ---------------- */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    api
      .listConfigs()
      .then(async (list) => {
        if (cancelled) return;
        setAvailable(list);
        if (activeName) return; // already loaded in a previous mount
        const preferred =
          list.find((c) => c.name === PREFERRED_DEFAULT) ?? list[0];
        if (!preferred) {
          setLoadError("No configs found in engine_simulator/config/");
          return;
        }
        const payload = await api.getConfig(preferred.name);
        if (cancelled) return;
        setActive(preferred.name, payload);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------------- Switching active config ------------ */
  const handleSelectFile = async (name: string) => {
    if (name === activeName) return;
    if (
      isDirty &&
      !window.confirm(
        "Discard unsaved changes to the current config?",
      )
    ) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const payload = await api.getConfig(name);
      setActive(name, payload);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- Save in place ----------------------- */
  const handleSave = async () => {
    if (!activeName || draft === null || saving) return;
    setSaving(true);
    setSaveError(null);
    setFieldErrors({});
    try {
      const result = await api.saveConfig(activeName, draft);
      setActive(activeName, result);
      flashSaved();
    } catch (e: unknown) {
      const err = e as Error & {
        fieldErrors?: Record<string, string>;
        status?: number;
      };
      if (err.status === 422 && err.fieldErrors) {
        setFieldErrors(err.fieldErrors);
        setSaveError("Validation failed — see highlighted fields.");
      } else {
        setSaveError(err.message ?? String(e));
      }
    } finally {
      setSaving(false);
    }
  };

  /* ---------------- Save As --------------------------- */
  const beginSaveAs = () => {
    setSaveAsMode(true);
    setSaveAsName("");
    setSaveAsError(null);
  };

  const cancelSaveAs = () => {
    setSaveAsMode(false);
    setSaveAsName("");
    setSaveAsError(null);
  };

  const handleSaveAs = async () => {
    if (draft === null) return;
    let name = saveAsName.trim();
    if (!name) {
      setSaveAsError("Enter a filename");
      return;
    }
    if (!name.endsWith(".json")) name += ".json";
    if (!/^[A-Za-z0-9_\-]+\.json$/.test(name)) {
      setSaveAsError("Letters, digits, _ and - only");
      return;
    }
    setSaving(true);
    setSaveAsError(null);
    setFieldErrors({});
    try {
      const result = await api.saveConfigAs(name, draft);
      const list = await api.listConfigs();
      setAvailable(list);
      setActive(name, result);
      flashSaved();
      setSaveAsMode(false);
      setSaveAsName("");
    } catch (e: unknown) {
      const err = e as Error & {
        fieldErrors?: Record<string, string>;
        status?: number;
      };
      if (err.status === 422 && err.fieldErrors) {
        setFieldErrors(err.fieldErrors);
        setSaveAsError("Validation failed");
      } else {
        setSaveAsError(err.message ?? String(e));
      }
    } finally {
      setSaving(false);
    }
  };

  /* ---------------- Render ---------------------------- */

  if (loading && draft === null) {
    return (
      <main className="flex-1 overflow-auto flex items-center justify-center text-text-muted text-xs uppercase tracking-[0.2em]">
        Loading config…
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="flex-1 overflow-auto flex items-center justify-center text-status-error text-xs">
        {loadError}
      </main>
    );
  }

  if (draft === null || activeName === null) {
    return (
      <main className="flex-1 overflow-auto flex items-center justify-center text-text-muted text-xs">
        No config loaded.
      </main>
    );
  }

  const flashedRecently =
    saveFlash !== null && Date.now() - saveFlash < 3000;

  return (
    <main className="flex-1 overflow-auto bg-bg flex flex-col">
      {/* Sticky header ---------------------------------------------- */}
      <header className="sticky top-0 z-10 bg-surface border-b border-border-default flex items-stretch">
        <div className="flex items-center gap-3 px-4 py-3 border-r border-border-default">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-accent"
            aria-hidden
          />
          <h2 className="text-[12px] font-semibold uppercase tracking-[0.2em] text-text-primary leading-none">
            Engine Config
          </h2>
          <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-text-muted leading-none border border-border-default px-1 py-[1px]">
            Edit
          </span>
        </div>

        {/* File picker / Save As inline prompt */}
        {saveAsMode ? (
          <div className="flex-1 flex items-center gap-2 px-3">
            <span className="text-[10px] font-mono uppercase tracking-widest text-text-muted">
              Save As
            </span>
            <input
              type="text"
              value={saveAsName}
              autoFocus
              placeholder="filename.json"
              onChange={(e) => setSaveAsName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleSaveAs();
                if (e.key === "Escape") cancelSaveAs();
              }}
              className="flex-1 max-w-xs bg-surface border border-border-default rounded px-2 py-1 text-sm font-mono text-text-primary focus:outline-none focus:border-border-emphasis"
            />
            {saveAsError && (
              <span className="text-[10px] font-mono text-status-error">
                {saveAsError}
              </span>
            )}
            <button
              type="button"
              onClick={handleSaveAs}
              disabled={saving}
              className="h-7 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] bg-accent text-bg hover:bg-[#FF6A3D] disabled:bg-accent/30 disabled:cursor-not-allowed"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={cancelSaveAs}
              className="h-7 px-3 text-[10px] font-medium uppercase tracking-[0.16em] border border-border-default text-text-secondary hover:bg-surface-raised"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex-1 flex items-center gap-3 px-3">
            <select
              value={activeName}
              onChange={(e) => void handleSelectFile(e.target.value)}
              className="bg-surface border border-border-default rounded px-2 py-1 text-sm font-mono text-text-primary focus:outline-none focus:border-border-emphasis"
            >
              {available.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
            {isDirty ? (
              <span className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-accent">
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full bg-accent"
                  aria-hidden
                />
                modified
              </span>
            ) : flashedRecently ? (
              <span className="text-[10px] font-mono uppercase tracking-widest text-status-done">
                saved
              </span>
            ) : null}
          </div>
        )}

        {/* Action buttons */}
        {!saveAsMode && (
          <div className="flex items-stretch border-l border-border-default">
            <button
              type="button"
              onClick={revert}
              disabled={!isDirty || saving}
              className="px-4 text-[10px] font-medium uppercase tracking-[0.16em] text-text-secondary hover:bg-surface-raised hover:text-text-primary disabled:text-text-muted disabled:cursor-not-allowed border-r border-border-default"
            >
              Revert
            </button>
            <button
              type="button"
              onClick={beginSaveAs}
              disabled={saving}
              className="px-4 text-[10px] font-medium uppercase tracking-[0.16em] text-text-secondary hover:bg-surface-raised hover:text-text-primary disabled:text-text-muted disabled:cursor-not-allowed border-r border-border-default"
            >
              Save As…
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!isDirty || saving}
              className="px-5 text-[11px] font-semibold uppercase tracking-[0.18em] bg-accent text-bg hover:bg-[#FF6A3D] disabled:bg-accent/20 disabled:text-accent/50 disabled:cursor-not-allowed"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        )}
      </header>

      {/* Save error strip */}
      {saveError && (
        <div className="mx-4 mt-3 border border-status-error/40 bg-status-error/[0.06] px-3 py-2">
          <div className="flex items-start gap-2">
            <span
              className="mt-[5px] inline-block w-1.5 h-1.5 rounded-full bg-status-error flex-shrink-0"
              aria-hidden
            />
            <div className="flex-1 min-w-0">
              <div className="text-[9px] font-semibold uppercase tracking-[0.2em] text-status-error leading-none mb-1">
                Save Failed
              </div>
              <div className="text-xs text-text-primary font-mono break-words leading-snug">
                {saveError}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Section list — populated by later tasks */}
      <div className="p-4 flex flex-col gap-3">
        <SectionPlaceholder />
      </div>
    </main>
  );
}

function SectionPlaceholder() {
  return (
    <div className="border border-dashed border-border-default rounded p-6 text-center text-[10px] uppercase tracking-[0.2em] text-text-muted">
      Sections appear here once Phase D is complete
    </div>
  );
}
```

- [ ] **Step 2: Wire `ConfigView` into `App.tsx`**

Edit `gui-frontend/src/App.tsx`. Replace the `import` section's stub `ConfigPlaceholder` and the inline component definition. The new file should look like:

```tsx
import { useEffect, useState } from "react";
import TopBar from "./components/TopBar";
import TabBar from "./components/TabBar";
import RunSweepDialog from "./components/RunSweepDialog";
import SimulationView from "./components/SimulationView";
import ConfigView from "./components/ConfigView";
import SweepListSidebar from "./components/SweepListSidebar";
import { makeEventSocket } from "./api/websocket";
import { applyServerMessage } from "./state/eventReducer";
import { useConfigStore } from "./state/configStore";

export default function App() {
  const [runSweepDialogOpen, setRunSweepDialogOpen] = useState(false);
  const activeTab = useConfigStore((s) => s.activeTab);

  useEffect(() => {
    const sock = makeEventSocket();
    const unsub = sock.addListener(applyServerMessage);
    sock.connect();
    return () => {
      unsub();
      sock.close();
    };
  }, []);

  return (
    <div className="min-h-screen h-screen flex flex-col bg-bg text-text-primary font-ui">
      <TopBar
        onRunSweepClick={() => setRunSweepDialogOpen(true)}
        onLoadClick={() => {
          /* SweepListSidebar has its own toggle on the right edge */
        }}
      />
      <TabBar />

      <div className="flex-1 flex overflow-hidden">
        {activeTab === "simulation" ? <SimulationView /> : <ConfigView />}
        <SweepListSidebar />
      </div>

      <RunSweepDialog
        isOpen={runSweepDialogOpen}
        onClose={() => setRunSweepDialogOpen(false)}
      />
    </div>
  );
}
```

- [ ] **Step 3: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 4: Manual smoke test**

Start the FastAPI backend in one terminal and the dev frontend in another:
```
cd /Users/nmurray/Developer/1d && .venv/bin/python -m engine_simulator.gui
cd /Users/nmurray/Developer/1d/gui-frontend && npm run dev
```

Open http://localhost:5173, click the "Config" tab. Verify:
- Sticky header appears with "ENGINE CONFIG · EDIT", a file dropdown showing `cbr600rr.json`, and Revert / Save As / Save buttons.
- The body shows the dashed-border placeholder.
- Save and Revert are disabled (nothing to save).
- Clicking Save As shows the inline filename prompt; Cancel restores the buttons.

Stop both processes.

- [ ] **Step 5: Commit**

```bash
git add gui-frontend/src/components/ConfigView.tsx \
        gui-frontend/src/App.tsx
git commit -m "feat(gui): ConfigView shell with sticky header and Save/Save As/Revert

Loads cbr600rr.json on first mount via the new api.getConfig + listConfigs.
Save and Save As wire through configStore.draft. Section body is a
placeholder; real sections land in Phase D."
```

---

## Phase D: Section components — simple

End of phase: Identity, Cylinder, Combustion, Restrictor, Plenum, Simulation, and Ambient sections all render and edit live. Editing any field flips the dirty dot. Save persists changes to disk.

> **Note for the engineer:** All section components follow the same pattern. They subscribe to one slice of `draft` from `configStore`, render `NumericField` (or `TextField`) instances bound to that slice via `setField(path, value)`, and live inside an `Accordion`. The pattern is repeated below for each section so you can read tasks in any order.

### Task D1: Identity + Cylinder sections

**Files:**
- Create: `gui-frontend/src/components/config/IdentitySection.tsx`
- Create: `gui-frontend/src/components/config/CylinderSection.tsx`
- Modify: `gui-frontend/src/components/ConfigView.tsx` (replace placeholder with section list)

- [ ] **Step 1: Create `IdentitySection.tsx`**

Create `gui-frontend/src/components/config/IdentitySection.tsx`:

```tsx
import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";
import { TextField } from "../forms/TextField";

export default function IdentitySection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;

  return (
    <Accordion id="identity" index="01" label="Identity">
      <div className="grid grid-cols-2 gap-3">
        <TextField
          index="01"
          label="Name"
          value={draft.name}
          onChange={(v) => setField("name", v)}
          error={fieldErrors["name"]}
        />
        <TextField
          index="02"
          label="Firing Order"
          unit="cyl"
          value={draft.firing_order.join(",")}
          onChange={(v) => {
            const parts = v
              .split(",")
              .map((s) => Number(s.trim()))
              .filter((n) => Number.isFinite(n));
            setField("firing_order", parts);
          }}
          error={fieldErrors["firing_order"]}
          placeholder="1,2,4,3"
        />
        <NumericField
          index="03"
          label="N Cylinders"
          unit="cyl"
          value={draft.n_cylinders}
          onChange={(v) => setField("n_cylinders", v)}
          error={fieldErrors["n_cylinders"]}
          step={1}
          min={1}
        />
        <NumericField
          index="04"
          label="Firing Interval"
          unit="deg"
          value={draft.firing_interval}
          onChange={(v) => setField("firing_interval", v)}
          error={fieldErrors["firing_interval"]}
          step={1}
        />
      </div>
    </Accordion>
  );
}
```

- [ ] **Step 2: Create `CylinderSection.tsx`**

Create `gui-frontend/src/components/config/CylinderSection.tsx`:

```tsx
import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function CylinderSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const c = draft.cylinder;

  return (
    <Accordion id="cylinder" index="02" label="Cylinder">
      <div className="grid grid-cols-2 gap-3">
        <NumericField
          index="01"
          label="Bore"
          unit="mm"
          value={c.bore}
          onChange={(v) => setField("cylinder.bore", v)}
          error={fieldErrors["cylinder.bore"]}
          displayScale={1000}
          step={0.1}
          min={0}
        />
        <NumericField
          index="02"
          label="Stroke"
          unit="mm"
          value={c.stroke}
          onChange={(v) => setField("cylinder.stroke", v)}
          error={fieldErrors["cylinder.stroke"]}
          displayScale={1000}
          step={0.1}
          min={0}
        />
        <NumericField
          index="03"
          label="Con Rod Length"
          unit="mm"
          value={c.con_rod_length}
          onChange={(v) => setField("cylinder.con_rod_length", v)}
          error={fieldErrors["cylinder.con_rod_length"]}
          displayScale={1000}
          step={0.1}
          min={0}
        />
        <NumericField
          index="04"
          label="Compression Ratio"
          unit="—"
          value={c.compression_ratio}
          onChange={(v) => setField("cylinder.compression_ratio", v)}
          error={fieldErrors["cylinder.compression_ratio"]}
          step={0.1}
          min={1}
        />
        <NumericField
          index="05"
          label="N Intake Valves"
          unit="n"
          value={c.n_intake_valves}
          onChange={(v) => setField("cylinder.n_intake_valves", v)}
          error={fieldErrors["cylinder.n_intake_valves"]}
          step={1}
          min={1}
        />
        <NumericField
          index="06"
          label="N Exhaust Valves"
          unit="n"
          value={c.n_exhaust_valves}
          onChange={(v) => setField("cylinder.n_exhaust_valves", v)}
          error={fieldErrors["cylinder.n_exhaust_valves"]}
          step={1}
          min={1}
        />
      </div>
    </Accordion>
  );
}
```

- [ ] **Step 3: Replace `SectionPlaceholder` in `ConfigView.tsx`**

In `gui-frontend/src/components/ConfigView.tsx`, replace the `<SectionPlaceholder />` JSX and the `SectionPlaceholder` function with:

```tsx
import IdentitySection from "./config/IdentitySection";
import CylinderSection from "./config/CylinderSection";
```

at the top, and change the section list to:

```tsx
{/* Section list */}
<div className="p-4 flex flex-col gap-3">
  <IdentitySection />
  <CylinderSection />
</div>
```

Delete the `function SectionPlaceholder()` definition.

- [ ] **Step 4: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 5: Manual smoke test**

Start backend + frontend, open the Config tab. Verify:
- Identity and Cylinder accordions are open.
- Bore shows `67` (not `0.067`) thanks to `displayScale={1000}`.
- Editing Bore to `68` flips the dirty dot to "modified" and enables Save.
- Click Save → SAVED appears, dot clears, the number on disk in `engine_simulator/config/cbr600rr.json` shows `0.068`.
- Click Revert (after re-editing) restores the previous value.

Stop both processes.

- [ ] **Step 6: Commit**

```bash
git add gui-frontend/src/components/config/IdentitySection.tsx \
        gui-frontend/src/components/config/CylinderSection.tsx \
        gui-frontend/src/components/ConfigView.tsx
git commit -m "feat(gui): Identity and Cylinder sections in the Config tab

First end-to-end edit path: change a field, see dirty state, save to
disk via PUT, server validates via pydantic. Bore/stroke/con-rod-length
displayed in mm (× 1000) for ergonomics."
```

---

### Task D2: Combustion + Restrictor sections

**Files:**
- Create: `gui-frontend/src/components/config/CombustionSection.tsx`
- Create: `gui-frontend/src/components/config/RestrictorSection.tsx`
- Modify: `gui-frontend/src/components/ConfigView.tsx`

- [ ] **Step 1: Create `CombustionSection.tsx`**

Create `gui-frontend/src/components/config/CombustionSection.tsx`:

```tsx
import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function CombustionSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const c = draft.combustion;

  return (
    <Accordion id="combustion" index="09" label="Combustion">
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="Wiebe a"
          unit="—"
          value={c.wiebe_a}
          onChange={(v) => setField("combustion.wiebe_a", v)}
          error={fieldErrors["combustion.wiebe_a"]}
          step={0.1}
        />
        <NumericField
          index="02"
          label="Wiebe m"
          unit="—"
          value={c.wiebe_m}
          onChange={(v) => setField("combustion.wiebe_m", v)}
          error={fieldErrors["combustion.wiebe_m"]}
          step={0.1}
        />
        <NumericField
          index="03"
          label="Combustion Duration"
          unit="deg"
          value={c.combustion_duration}
          onChange={(v) => setField("combustion.combustion_duration", v)}
          error={fieldErrors["combustion.combustion_duration"]}
          step={1}
        />
        <NumericField
          index="04"
          label="Spark Advance"
          unit="deg BTDC"
          value={c.spark_advance}
          onChange={(v) => setField("combustion.spark_advance", v)}
          error={fieldErrors["combustion.spark_advance"]}
          step={0.5}
        />
        <NumericField
          index="05"
          label="Ignition Delay"
          unit="deg"
          value={c.ignition_delay}
          onChange={(v) => setField("combustion.ignition_delay", v)}
          error={fieldErrors["combustion.ignition_delay"]}
          step={0.5}
        />
        <NumericField
          index="06"
          label="Combustion Efficiency"
          unit="—"
          value={c.combustion_efficiency}
          onChange={(v) => setField("combustion.combustion_efficiency", v)}
          error={fieldErrors["combustion.combustion_efficiency"]}
          step={0.01}
        />
        <NumericField
          index="07"
          label="LHV"
          unit="MJ/kg"
          value={c.q_lhv}
          onChange={(v) => setField("combustion.q_lhv", v)}
          error={fieldErrors["combustion.q_lhv"]}
          displayScale={1e-6}
          step={0.1}
        />
        <NumericField
          index="08"
          label="AFR Stoich"
          unit="—"
          value={c.afr_stoich}
          onChange={(v) => setField("combustion.afr_stoich", v)}
          error={fieldErrors["combustion.afr_stoich"]}
          step={0.1}
        />
        <NumericField
          index="09"
          label="AFR Target"
          unit="—"
          value={c.afr_target}
          onChange={(v) => setField("combustion.afr_target", v)}
          error={fieldErrors["combustion.afr_target"]}
          step={0.1}
        />
      </div>
    </Accordion>
  );
}
```

- [ ] **Step 2: Create `RestrictorSection.tsx`**

Create `gui-frontend/src/components/config/RestrictorSection.tsx`:

```tsx
import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function RestrictorSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const r = draft.restrictor;

  return (
    <Accordion id="restrictor" index="10" label="Restrictor">
      <div className="grid grid-cols-2 gap-3">
        <NumericField
          index="01"
          label="Throat Diameter"
          unit="mm"
          value={r.throat_diameter}
          onChange={(v) => setField("restrictor.throat_diameter", v)}
          error={fieldErrors["restrictor.throat_diameter"]}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="02"
          label="Discharge Coefficient"
          unit="—"
          value={r.discharge_coefficient}
          onChange={(v) => setField("restrictor.discharge_coefficient", v)}
          error={fieldErrors["restrictor.discharge_coefficient"]}
          step={0.001}
        />
        <NumericField
          index="03"
          label="Converging Half Angle"
          unit="deg"
          value={r.converging_half_angle}
          onChange={(v) => setField("restrictor.converging_half_angle", v)}
          error={fieldErrors["restrictor.converging_half_angle"]}
          step={0.5}
        />
        <NumericField
          index="04"
          label="Diverging Half Angle"
          unit="deg"
          value={r.diverging_half_angle}
          onChange={(v) => setField("restrictor.diverging_half_angle", v)}
          error={fieldErrors["restrictor.diverging_half_angle"]}
          step={0.5}
        />
      </div>
    </Accordion>
  );
}
```

- [ ] **Step 3: Wire into `ConfigView.tsx`**

Add imports to `gui-frontend/src/components/ConfigView.tsx`:

```tsx
import CombustionSection from "./config/CombustionSection";
import RestrictorSection from "./config/RestrictorSection";
```

Update the section list JSX:

```tsx
<div className="p-4 flex flex-col gap-3">
  <IdentitySection />
  <CylinderSection />
  <CombustionSection />
  <RestrictorSection />
</div>
```

- [ ] **Step 4: Build + smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

Optional manual test: open the GUI, expand Combustion, verify LHV shows `43.5` (MJ/kg) — confirming `displayScale={1e-6}` works correctly against the JSON value `43500000.0` (or `44000000.0` in the existing file).

- [ ] **Step 5: Commit**

```bash
git add gui-frontend/src/components/config/CombustionSection.tsx \
        gui-frontend/src/components/config/RestrictorSection.tsx \
        gui-frontend/src/components/ConfigView.tsx
git commit -m "feat(gui): Combustion and Restrictor sections"
```

---

### Task D3: Plenum + Simulation + Ambient sections

**Files:**
- Create: `gui-frontend/src/components/config/PlenumSection.tsx`
- Create: `gui-frontend/src/components/config/SimulationSection.tsx`
- Create: `gui-frontend/src/components/config/AmbientSection.tsx`
- Modify: `gui-frontend/src/components/ConfigView.tsx`

- [ ] **Step 1: Create `PlenumSection.tsx`**

Create `gui-frontend/src/components/config/PlenumSection.tsx`:

```tsx
import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function PlenumSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const p = draft.plenum;

  return (
    <Accordion id="plenum" index="11" label="Plenum">
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="Volume"
          unit="L"
          value={p.volume}
          onChange={(v) => setField("plenum.volume", v)}
          error={fieldErrors["plenum.volume"]}
          displayScale={1000}
          step={0.05}
        />
        <NumericField
          index="02"
          label="Initial Pressure"
          unit="kPa"
          value={p.initial_pressure}
          onChange={(v) => setField("plenum.initial_pressure", v)}
          error={fieldErrors["plenum.initial_pressure"]}
          displayScale={0.001}
          step={0.5}
        />
        <NumericField
          index="03"
          label="Initial Temperature"
          unit="K"
          value={p.initial_temperature}
          onChange={(v) => setField("plenum.initial_temperature", v)}
          error={fieldErrors["plenum.initial_temperature"]}
          step={1}
        />
      </div>
    </Accordion>
  );
}
```

- [ ] **Step 2: Create `SimulationSection.tsx`**

Create `gui-frontend/src/components/config/SimulationSection.tsx`:

```tsx
import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function SimulationSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const s = draft.simulation;

  return (
    <Accordion id="simulation" index="12" label="Simulation">
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="RPM Start"
          unit="rpm"
          value={s.rpm_start}
          onChange={(v) => setField("simulation.rpm_start", v)}
          error={fieldErrors["simulation.rpm_start"]}
          step={100}
        />
        <NumericField
          index="02"
          label="RPM End"
          unit="rpm"
          value={s.rpm_end}
          onChange={(v) => setField("simulation.rpm_end", v)}
          error={fieldErrors["simulation.rpm_end"]}
          step={100}
        />
        <NumericField
          index="03"
          label="RPM Step"
          unit="rpm"
          value={s.rpm_step}
          onChange={(v) => setField("simulation.rpm_step", v)}
          error={fieldErrors["simulation.rpm_step"]}
          step={50}
        />
        <NumericField
          index="04"
          label="N Cycles"
          unit="—"
          value={s.n_cycles}
          onChange={(v) => setField("simulation.n_cycles", v)}
          error={fieldErrors["simulation.n_cycles"]}
          step={1}
          min={1}
        />
        <NumericField
          index="05"
          label="CFL Number"
          unit="—"
          value={s.cfl_number}
          onChange={(v) => setField("simulation.cfl_number", v)}
          error={fieldErrors["simulation.cfl_number"]}
          step={0.05}
        />
        <NumericField
          index="06"
          label="Convergence Tol"
          unit="—"
          value={s.convergence_tolerance}
          onChange={(v) => setField("simulation.convergence_tolerance", v)}
          error={fieldErrors["simulation.convergence_tolerance"]}
          step={0.001}
        />
        <NumericField
          index="07"
          label="Crank Step Max"
          unit="deg"
          value={s.crank_step_max}
          onChange={(v) => setField("simulation.crank_step_max", v)}
          error={fieldErrors["simulation.crank_step_max"]}
          step={0.1}
        />
        <NumericField
          index="08"
          label="Artificial Viscosity"
          unit="—"
          value={s.artificial_viscosity}
          onChange={(v) => setField("simulation.artificial_viscosity", v)}
          error={fieldErrors["simulation.artificial_viscosity"]}
          step={0.01}
        />
      </div>
    </Accordion>
  );
}
```

- [ ] **Step 3: Create `AmbientSection.tsx`**

Create `gui-frontend/src/components/config/AmbientSection.tsx`:

```tsx
import { useConfigStore } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";

export default function AmbientSection() {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;

  return (
    <Accordion id="ambient" index="13" label="Ambient">
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="P Ambient"
          unit="kPa"
          value={draft.p_ambient}
          onChange={(v) => setField("p_ambient", v)}
          error={fieldErrors["p_ambient"]}
          displayScale={0.001}
          step={0.5}
        />
        <NumericField
          index="02"
          label="T Ambient"
          unit="K"
          value={draft.T_ambient}
          onChange={(v) => setField("T_ambient", v)}
          error={fieldErrors["T_ambient"]}
          step={1}
        />
        <NumericField
          index="03"
          label="Drivetrain Efficiency"
          unit="—"
          value={draft.drivetrain_efficiency}
          onChange={(v) => setField("drivetrain_efficiency", v)}
          error={fieldErrors["drivetrain_efficiency"]}
          step={0.01}
        />
      </div>
    </Accordion>
  );
}
```

- [ ] **Step 4: Wire into `ConfigView.tsx`**

Add imports:

```tsx
import PlenumSection from "./config/PlenumSection";
import SimulationSection from "./config/SimulationSection";
import AmbientSection from "./config/AmbientSection";
```

Update the section list:

```tsx
<div className="p-4 flex flex-col gap-3">
  <IdentitySection />
  <CylinderSection />
  <CombustionSection />
  <RestrictorSection />
  <PlenumSection />
  <SimulationSection />
  <AmbientSection />
</div>
```

- [ ] **Step 5: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 6: Commit**

```bash
git add gui-frontend/src/components/config/PlenumSection.tsx \
        gui-frontend/src/components/config/SimulationSection.tsx \
        gui-frontend/src/components/config/AmbientSection.tsx \
        gui-frontend/src/components/ConfigView.tsx
git commit -m "feat(gui): Plenum, Simulation, and Ambient sections"
```

---

## Phase E: Section components — complex (cd_table, pipes, valves)

### Task E1: `CdTableEditor` primitive

**Files:**
- Create: `gui-frontend/src/components/forms/CdTableEditor.tsx`

- [ ] **Step 1: Create the file**

Create `gui-frontend/src/components/forms/CdTableEditor.tsx`:

```tsx
import { useConfigStore, type ValveKey } from "../../state/configStore";
import { NumericField } from "./NumericField";

interface CdTableEditorProps {
  valve: ValveKey;
}

/**
 * Inline editor for the (L/D, Cd) lookup table on a valve. Each row is
 * two NumericFields plus a delete button. The "+ add row" button at the
 * bottom appends a new row with default values. The list is auto-sorted
 * by L/D ascending on save (the cd_table is a lookup that depends on
 * monotonic ordering); since this happens server-side, no warning here.
 */
export function CdTableEditor({ valve }: CdTableEditorProps) {
  const rows = useConfigStore((s) => s.draft?.[valve].cd_table ?? []);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  const addRow = useConfigStore((s) => s.addCdRow);
  const removeRow = useConfigStore((s) => s.removeCdRow);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-1.5">
        <span className="text-[9px] font-mono text-text-muted leading-none">[CD TABLE]</span>
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-secondary leading-none">
          Discharge Coefficient Lookup
        </span>
      </div>
      <div className="flex flex-col gap-2 border border-border-default rounded p-3 bg-surface">
        {rows.length === 0 && (
          <div className="text-[10px] text-text-muted uppercase tracking-widest text-center py-2">
            No rows
          </div>
        )}
        {rows.map((pair, i) => (
          <div key={i} className="flex items-end gap-3">
            <div className="flex-1">
              <NumericField
                index={String(i + 1).padStart(2, "0")}
                label="L/D"
                unit="—"
                value={pair[0]}
                onChange={(v) => setField(`${valve}.cd_table.${i}.0`, v)}
                error={fieldErrors[`${valve}.cd_table.${i}.0`]}
                step={0.01}
                min={0}
              />
            </div>
            <div className="flex-1">
              <NumericField
                index={String(i + 1).padStart(2, "0")}
                label="Cd"
                unit="—"
                value={pair[1]}
                onChange={(v) => setField(`${valve}.cd_table.${i}.1`, v)}
                error={fieldErrors[`${valve}.cd_table.${i}.1`]}
                step={0.01}
                min={0}
              />
            </div>
            <button
              type="button"
              onClick={() => removeRow(valve, i)}
              aria-label={`Remove row ${i + 1}`}
              className="h-9 w-9 inline-flex items-center justify-center border border-border-default rounded text-text-muted hover:text-status-error hover:border-status-error/60"
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => addRow(valve)}
          className="self-start text-[10px] font-medium uppercase tracking-[0.16em] text-text-secondary border border-border-default rounded px-3 py-1 hover:bg-bg hover:text-text-primary hover:border-border-emphasis"
        >
          + add row
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add gui-frontend/src/components/forms/CdTableEditor.tsx
git commit -m "feat(gui): CdTableEditor primitive for valve Cd lookup pairs"
```

---

### Task E2: `ValveSection` (used for intake + exhaust)

**Files:**
- Create: `gui-frontend/src/components/config/ValveSection.tsx`
- Modify: `gui-frontend/src/components/ConfigView.tsx`

- [ ] **Step 1: Create `ValveSection.tsx`**

Create `gui-frontend/src/components/config/ValveSection.tsx`:

```tsx
import { useConfigStore, type ValveKey } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { NumericField } from "../forms/NumericField";
import { CdTableEditor } from "../forms/CdTableEditor";

interface ValveSectionProps {
  valve: ValveKey;
  index: string;          // accordion index, e.g. "03"
  label: string;          // "Intake Valve" or "Exhaust Valve"
}

export default function ValveSection({ valve, index, label }: ValveSectionProps) {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;
  const v = draft[valve];

  return (
    <Accordion id={valve} index={index} label={label}>
      <div className="grid grid-cols-3 gap-3">
        <NumericField
          index="01"
          label="Diameter"
          unit="mm"
          value={v.diameter}
          onChange={(n) => setField(`${valve}.diameter`, n)}
          error={fieldErrors[`${valve}.diameter`]}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="02"
          label="Max Lift"
          unit="mm"
          value={v.max_lift}
          onChange={(n) => setField(`${valve}.max_lift`, n)}
          error={fieldErrors[`${valve}.max_lift`]}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="03"
          label="Seat Angle"
          unit="deg"
          value={v.seat_angle}
          onChange={(n) => setField(`${valve}.seat_angle`, n)}
          error={fieldErrors[`${valve}.seat_angle`]}
          step={1}
        />
        <NumericField
          index="04"
          label="Open Angle"
          unit="deg"
          value={v.open_angle}
          onChange={(n) => setField(`${valve}.open_angle`, n)}
          error={fieldErrors[`${valve}.open_angle`]}
          step={1}
        />
        <NumericField
          index="05"
          label="Close Angle"
          unit="deg"
          value={v.close_angle}
          onChange={(n) => setField(`${valve}.close_angle`, n)}
          error={fieldErrors[`${valve}.close_angle`]}
          step={1}
        />
      </div>
      <CdTableEditor valve={valve} />
    </Accordion>
  );
}
```

- [ ] **Step 2: Wire two instances into `ConfigView.tsx`**

Add an import to `gui-frontend/src/components/ConfigView.tsx`:

```tsx
import ValveSection from "./config/ValveSection";
```

Update the section list to insert the two valve sections after Cylinder:

```tsx
<div className="p-4 flex flex-col gap-3">
  <IdentitySection />
  <CylinderSection />
  <ValveSection valve="intake_valve" index="03" label="Intake Valve" />
  <ValveSection valve="exhaust_valve" index="04" label="Exhaust Valve" />
  <CombustionSection />
  <RestrictorSection />
  <PlenumSection />
  <SimulationSection />
  <AmbientSection />
</div>
```

- [ ] **Step 3: Build + smoke test**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

Optional manual test: open the GUI, expand Intake Valve. Add a row to the Cd table, edit values, save, verify the file on disk reflects the new row.

- [ ] **Step 4: Commit**

```bash
git add gui-frontend/src/components/config/ValveSection.tsx \
        gui-frontend/src/components/ConfigView.tsx
git commit -m "feat(gui): Intake/Exhaust valve sections with inline Cd table editor"
```

---

### Task E3: `PipeRow` primitive

**Files:**
- Create: `gui-frontend/src/components/forms/PipeRow.tsx`

- [ ] **Step 1: Create the file**

Create `gui-frontend/src/components/forms/PipeRow.tsx`:

```tsx
import { useConfigStore, type PipeArrayKey } from "../../state/configStore";
import { NumericField } from "./NumericField";
import { TextField } from "./TextField";

interface PipeRowProps {
  /** Either a pipe array section + index, OR a single-pipe path. */
  arraySection?: PipeArrayKey;
  arrayIndex?: number;
  /** Used by exhaust_collector (single pipe, not in an array). */
  singlePath?: "exhaust_collector";
  /** Display index for the [NN] mark. */
  index: string;
  onRemove?: () => void;
}

/**
 * One row of pipe fields: name | length | diameter | diameter_out | n_points
 * | wall_temperature | roughness | × button. Used inside PipeListSection
 * (array entries) and PipeRowSection (single exhaust_collector pipe).
 */
export function PipeRow({
  arraySection,
  arrayIndex,
  singlePath,
  index,
  onRemove,
}: PipeRowProps) {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;

  // Resolve the pipe object and the dot-path prefix
  let pipe;
  let pathPrefix: string;
  if (singlePath) {
    pipe = draft[singlePath];
    pathPrefix = singlePath;
  } else if (arraySection !== undefined && arrayIndex !== undefined) {
    pipe = draft[arraySection][arrayIndex];
    pathPrefix = `${arraySection}.${arrayIndex}`;
  } else {
    return null;
  }

  const err = (suffix: string): string | undefined =>
    fieldErrors[`${pathPrefix}.${suffix}`];

  return (
    <div className="border border-border-default rounded p-3 bg-surface flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="text-[9px] font-mono text-text-muted">[{index}]</span>
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
          {pipe.name}
        </span>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove ${pipe.name}`}
            className="ml-auto h-7 w-7 inline-flex items-center justify-center border border-border-default rounded text-text-muted hover:text-status-error hover:border-status-error/60"
          >
            ×
          </button>
        )}
      </div>

      <div className="grid grid-cols-4 gap-3">
        <TextField
          index="01"
          label="Name"
          value={pipe.name}
          onChange={(v) => setField(`${pathPrefix}.name`, v)}
          error={err("name")}
        />
        <NumericField
          index="02"
          label="Length"
          unit="mm"
          value={pipe.length}
          onChange={(n) => setField(`${pathPrefix}.length`, n)}
          error={err("length")}
          displayScale={1000}
          step={1}
        />
        <NumericField
          index="03"
          label="Diameter"
          unit="mm"
          value={pipe.diameter}
          onChange={(n) => setField(`${pathPrefix}.diameter`, n)}
          error={err("diameter")}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="04"
          label="Diameter Out"
          unit="mm"
          value={pipe.diameter_out ?? NaN}
          onChange={(n) =>
            setField(
              `${pathPrefix}.diameter_out`,
              Number.isFinite(n) ? n : null,
            )
          }
          error={err("diameter_out")}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="05"
          label="N Points"
          unit="—"
          value={pipe.n_points}
          onChange={(n) => setField(`${pathPrefix}.n_points`, n)}
          error={err("n_points")}
          step={1}
          min={2}
        />
        <NumericField
          index="06"
          label="Wall Temp"
          unit="K"
          value={pipe.wall_temperature}
          onChange={(n) => setField(`${pathPrefix}.wall_temperature`, n)}
          error={err("wall_temperature")}
          step={5}
        />
        <NumericField
          index="07"
          label="Roughness"
          unit="µm"
          value={pipe.roughness}
          onChange={(n) => setField(`${pathPrefix}.roughness`, n)}
          error={err("roughness")}
          displayScale={1e6}
          step={1}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add gui-frontend/src/components/forms/PipeRow.tsx
git commit -m "feat(gui): PipeRow primitive — handles array entries and single exhaust_collector"
```

---

### Task E4: `PipeListSection` and `PipeRowSection`

**Files:**
- Create: `gui-frontend/src/components/config/PipeListSection.tsx`
- Create: `gui-frontend/src/components/config/PipeRowSection.tsx`
- Modify: `gui-frontend/src/components/ConfigView.tsx`

- [ ] **Step 1: Create `PipeListSection.tsx`**

Create `gui-frontend/src/components/config/PipeListSection.tsx`:

```tsx
import { useConfigStore, type PipeArrayKey } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { PipeRow } from "../forms/PipeRow";

interface PipeListSectionProps {
  section: PipeArrayKey;
  index: string;
  label: string;
}

export default function PipeListSection({
  section,
  index,
  label,
}: PipeListSectionProps) {
  const list = useConfigStore((s) => s.draft?.[section] ?? []);
  const addPipe = useConfigStore((s) => s.addPipe);
  const removePipe = useConfigStore((s) => s.removePipe);

  const addButton = (
    <button
      type="button"
      onClick={() => addPipe(section)}
      className="text-[10px] font-medium uppercase tracking-[0.16em] text-text-secondary border border-border-default rounded px-3 py-1 hover:bg-bg hover:text-text-primary hover:border-border-emphasis"
    >
      + pipe
    </button>
  );

  return (
    <Accordion id={section} index={index} label={label} rightSlot={addButton}>
      <div className="flex flex-col gap-3">
        {list.map((_, i) => (
          <PipeRow
            key={i}
            arraySection={section}
            arrayIndex={i}
            index={String(i + 1).padStart(2, "0")}
            onRemove={() => removePipe(section, i)}
          />
        ))}
        {list.length === 0 && (
          <div className="text-[10px] uppercase tracking-widest text-text-muted text-center py-4">
            No pipes — click "+ pipe" to add one
          </div>
        )}
      </div>
    </Accordion>
  );
}
```

- [ ] **Step 2: Create `PipeRowSection.tsx`**

Create `gui-frontend/src/components/config/PipeRowSection.tsx`:

```tsx
import { Accordion } from "../forms/Accordion";
import { PipeRow } from "../forms/PipeRow";

interface PipeRowSectionProps {
  index: string;
  label: string;
}

/**
 * Single-pipe section, currently used only for exhaust_collector.
 */
export default function PipeRowSection({ index, label }: PipeRowSectionProps) {
  return (
    <Accordion id="exhaust_collector" index={index} label={label}>
      <PipeRow singlePath="exhaust_collector" index="01" />
    </Accordion>
  );
}
```

- [ ] **Step 3: Wire into `ConfigView.tsx`**

Add imports to `gui-frontend/src/components/ConfigView.tsx`:

```tsx
import PipeListSection from "./config/PipeListSection";
import PipeRowSection from "./config/PipeRowSection";
```

Update the section list (final ordering):

```tsx
<div className="p-4 flex flex-col gap-3">
  <IdentitySection />
  <CylinderSection />
  <ValveSection valve="intake_valve" index="03" label="Intake Valve" />
  <ValveSection valve="exhaust_valve" index="04" label="Exhaust Valve" />
  <PipeListSection section="intake_pipes" index="05" label="Intake Pipes" />
  <PipeListSection section="exhaust_primaries" index="06" label="Exhaust Primaries" />
  <PipeListSection section="exhaust_secondaries" index="07" label="Exhaust Secondaries" />
  <PipeRowSection index="08" label="Exhaust Collector" />
  <CombustionSection />
  <RestrictorSection />
  <PlenumSection />
  <SimulationSection />
  <AmbientSection />
</div>
```

- [ ] **Step 4: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 5: Manual smoke test**

Start backend + frontend, open Config tab. Verify:
- All 13 sections render in the listed order.
- Intake Pipes shows 4 pipes; clicking "+ pipe" adds a 5th with default values.
- Editing a pipe length and saving persists to disk.
- Removing the added pipe and saving persists removal.

Stop both processes.

- [ ] **Step 6: Commit**

```bash
git add gui-frontend/src/components/config/PipeListSection.tsx \
        gui-frontend/src/components/config/PipeRowSection.tsx \
        gui-frontend/src/components/ConfigView.tsx
git commit -m "feat(gui): pipe array sections + single exhaust_collector section

All 13 Config tab sections are now wired. The Config tab can edit any
field in the EngineConfig dataclass tree and save through the validated
PUT/POST endpoints."
```

---

## Phase F: Validation, integration, and Run Sweep dialog wiring

### Task F1: Sweep-while-dirty warning + active config sharing in `RunSweepDialog`

**Files:**
- Modify: `gui-frontend/src/components/RunSweepDialog.tsx`

- [ ] **Step 1: Read the current dialog**

Read `gui-frontend/src/components/RunSweepDialog.tsx` again. We're going to:
1. Drop the hard-coded `PREFERRED_CONFIG = "cbr600rr.json"` constant.
2. Default `form.config_name` from `configStore.activeName` (falling back to `cbr600rr.json` if the store is unloaded).
3. Show a warning strip when the active config is dirty.

- [ ] **Step 2: Apply the changes**

In `gui-frontend/src/components/RunSweepDialog.tsx`:

a. Add an import near the top:

```tsx
import {
  useConfigStore,
  selectIsDirty,
} from "../state/configStore";
```

b. Delete the line `const PREFERRED_CONFIG = "cbr600rr.json";`.

c. Inside the `RunSweepDialog` component body, after the existing `useState` calls, add:

```tsx
const activeName = useConfigStore((s) => s.activeName);
const isDirty = useConfigStore(selectIsDirty);
```

d. Find the existing `useEffect` that fetches configs (the block starting `if (!isOpen) return;` followed by `setConfigsLoading(true)`). Replace the inner `setForm` call inside the `.then(...)` callback. The current code has:

```tsx
setForm((prev) => {
  if (prev.config_name && list.some((c) => c.name === prev.config_name)) {
    return prev;
  }
  const preferred = list.find((c) => c.name === PREFERRED_CONFIG);
  const next = preferred ?? list[0];
  return next ? { ...prev, config_name: next.name } : prev;
});
```

Replace with:

```tsx
setForm((prev) => {
  if (prev.config_name && list.some((c) => c.name === prev.config_name)) {
    return prev;
  }
  const fromStore =
    activeName && list.some((c) => c.name === activeName) ? activeName : null;
  const fallback = list.find((c) => c.name === "cbr600rr.json") ?? list[0];
  const next = fromStore ? { name: fromStore } : fallback;
  return next ? { ...prev, config_name: next.name } : prev;
});
```

e. In the form body, just below the `<ConfigField ... />` invocation, add the dirty-state warning strip:

```tsx
{isDirty && form.config_name === activeName && (
  <div className="border border-status-warning/40 bg-status-warning/[0.06] px-3 py-2">
    <div className="flex items-start gap-2">
      <span
        className="mt-[5px] inline-block w-1.5 h-1.5 rounded-full bg-status-warning flex-shrink-0"
        aria-hidden
      />
      <div className="flex-1 min-w-0">
        <div className="text-[9px] font-semibold uppercase tracking-[0.2em] text-status-warning leading-none mb-1">
          Unsaved Changes
        </div>
        <div className="text-xs text-text-primary font-mono break-words leading-snug">
          Active config has unsaved edits — sweep will use the saved version on disk.
        </div>
      </div>
    </div>
  </div>
)}
```

If the project's tailwind theme does not have `status-warning`, fall back to the existing `accent` color: replace `status-warning` with `accent` everywhere in the strip above (the `border-status-warning/40` becomes `border-accent/40`, etc.). Check the tailwind config quickly to confirm:

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && grep -E "(status-warning|warning:)" tailwind.config.js`
- If output is empty: use `accent` instead of `status-warning` in the strip above.
- If `status-warning` exists: keep as written.

- [ ] **Step 3: Build to verify**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build 2>&1 | tail -10`
Expected: clean build.

- [ ] **Step 4: Manual smoke test**

Start backend + frontend. Verify:
- Open Config tab, the sweep dialog should default to whatever's loaded (`cbr600rr.json`).
- Save As to a new variant `tweaked.json`. The Config tab now shows `tweaked.json` selected.
- Open Run Sweep — the config dropdown defaults to `tweaked.json`.
- Edit a field in the Config tab, do NOT save. Open Run Sweep — the warning strip appears.
- Close Run Sweep, hit Revert in the Config tab. Open Run Sweep — warning is gone.

Stop both processes. Delete the `tweaked.json` test artifact: `rm engine_simulator/config/tweaked.json` (only if it was created).

- [ ] **Step 5: Commit**

```bash
git add gui-frontend/src/components/RunSweepDialog.tsx
git commit -m "feat(gui): RunSweepDialog defaults to active config + dirty warning

Reads the active config name from configStore so the Config tab and the
Run Sweep dialog stay in sync. Shows a warning strip when starting a
sweep against a config with unsaved edits."
```

---

### Task F2: Full backend test sweep + integration verification

**Files:** none new — this task is verification only

- [ ] **Step 1: Run the full pytest suite**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest -q`
Expected: All previously passing tests still pass; the new `test_config_schema.py` and `test_config_routes.py` pass. No regressions.

- [ ] **Step 2: Run the manual integration checklist from the spec**

Follow §"Manual integration checklist" in `docs/superpowers/specs/2026-04-09-engine-config-editor-design.md`:

1. Open Config tab, see `cbr600rr.json` loaded with all 13 sections populated.
2. Change `intake_valve.open_angle` from `338` to `340`. Dirty dot appears. Click `Save`. Dot clears, `cbr600rr.json` on disk shows `340.0`.
3. Type `-1` into `cylinder.bore`. Inline red error appears (from server 422 after attempting save). Save is enabled but errors out — alternatively the form shows nothing until you press save and the server responds.
4. Click `Save As`, type `tweaked`, confirm. Dropdown shows `tweaked.json` selected. Open `Run Sweep` — `tweaked.json` is the default in the config dropdown.
5. With `tweaked.json` dirty (edit some field), click `Run Sweep`. Dialog opens with warning strip about unsaved changes.
6. Add a new pipe to `intake_pipes`, save, run a 1-RPM sweep against `tweaked.json`. Confirm the sweep completes and the per-pipe traces in `PipeTraces.tsx` include the added pipe.
7. Click `Revert` (after editing). All fields restore to last saved values without page reload.
8. Edit a `cd_table` row, delete a row, add a row. Save. Open `tweaked.json` on disk and confirm the cd_table reflects all three changes.
9. Restore `cbr600rr.json` to its original committed state: `git checkout engine_simulator/config/cbr600rr.json`. Delete the test variant: `rm engine_simulator/config/tweaked.json`.

Document any unexpected behavior in the commit message of the next task.

- [ ] **Step 3: Restore the canonical config**

Run: `cd /Users/nmurray/Developer/1d && git checkout engine_simulator/config/cbr600rr.json && rm -f engine_simulator/config/tweaked.json && git status --short`
Expected: clean working tree (apart from any untracked sweep artifacts in `sweeps/`).

- [ ] **Step 4: Final commit (no code changes — empty unless something needed fixing)**

If the manual checklist surfaced any issues, fix them and commit. Otherwise this task ends with a clean working tree and no commit.

---

## Self-Review

Verify before declaring the plan complete:

**Spec coverage** — every section of `docs/superpowers/specs/2026-04-09-engine-config-editor-design.md` has at least one task covering it:
- §Architecture > Data flow → Tasks A1, A3, A4, B3, B4, C2
- §Architecture > Tab navigation → Task B5
- §Frontend state → Task B3
- §Backend additions → Tasks A1–A5
- §Config tab UI > Layout, Section components → Tasks C2, D1–D3, E2, E4
- §Reusable form primitives → Tasks B1, B2, C1, E1, E3
- §Field unit conventions → Tasks D1–D3, E2, E3 (each shows the displayScale where applicable)
- §Validation > Server-side → Tasks A3, B4
- §Validation > Save flow → Task C2
- §Validation > Save As flow → Task C2
- §Validation > Sweep-while-dirty guard → Task F1
- §Testing > Backend (pytest) → Tasks A2 (round-trip), A3 (PUT validation), A4 (Save As), A5 (filename rejection)
- §Testing > Manual integration checklist → Task F2

**Placeholder scan** — searched the plan for "TODO", "TBD", "implement later", "fill in", "etc.", "similar to" — none found in code blocks. Each step shows the actual code.

**Type consistency** — `EngineConfigPayload`, `setField(path, value)`, `addPipe(section)`, `addCdRow(valve)`, `removePipe`, `removeCdRow`, `selectIsDirty`, `selectIsSectionOpen` are referenced consistently across tasks. `ValveKey` and `PipeArrayKey` types are defined in Task B3 and used in E1, E2, E3, E4.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-09-engine-config-editor.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
