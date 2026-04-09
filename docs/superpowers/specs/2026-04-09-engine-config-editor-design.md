# Engine Configuration Editor — Design

**Date:** 2026-04-09
**Author:** brainstormed with Claude
**Status:** Approved (pending implementation plan)
**Supersedes scope of:** "Configuration editor (v2)" carved out by `2026-04-08-engine-sim-gui-v1-design.md` §"Out of scope"

## Motivation

The engine simulator's GUI v1 (`2026-04-08-engine-sim-gui-v1-design.md`) shipped a "Mission Control" view: live sweep monitor, completed-sweep browser, and per-RPM detail panels. It explicitly deferred the configuration editor to v2 because forms/validation/save-load are a separate UI surface from the live monitor.

This is that v2. Today, anyone tweaking engine parameters has to hand-edit `engine_simulator/config/cbr600rr.json` in a text editor and re-run a sweep. The user wants to do this from the GUI: load a config, edit fields with proper labels and units, save, and immediately run a sweep against the new values. They also want to keep multiple variants of the config side by side so different setups can be compared.

A future v3 will sweep parameters across configs (e.g. "vary intake runner length from 200 mm to 300 mm in 10 mm steps and plot peak power"). This spec lays the groundwork for that work — same data model, same backend endpoints, same form widgets — but does not implement it.

## Scope

### In scope
- A new "Config" tab in the GUI alongside the existing simulation/results view.
- Loading any JSON config from `engine_simulator/config/`.
- Editing every field in the `EngineConfig` dataclass tree, including the `cd_table` lift/Cd lookup pairs and the variable-length pipe arrays.
- Saving in place (overwrites the loaded file) and Save As (writes a new file in the same directory).
- A shared "active config" state across the Config tab and the Run Sweep dialog so the dialog defaults to whatever's loaded in the editor.
- Per-field validation, both client-side (instant) and server-side (authoritative).
- Tests that the round-trip Pydantic ↔ `load_config()` produces an `EngineConfig` equivalent to the original file.

### Out of scope
- Sweeping parameters across config variants (v3).
- Diff/merge between configs.
- Version history of saved configs (the user can use git for that).
- Schema migration tooling (`engine_config.py` and the GUI Pydantic schema are kept manually in sync; round-trip test catches drift).
- Frontend test infrastructure (`vitest`/`jest`). Out of scope for this work — backend round-trip tests + `tsc` strict mode + manual checklist cover the surface.
- Importing/exporting configs from other simulators (Wave, GT-POWER, etc.).
- Editing configs while a sweep is running. The dirty-state guard warns; it does not block.

## Hard constraints

1. **Solver code is not touched.** No changes to `engine_simulator/config/engine_config.py`'s dataclasses, no changes to `load_config()`, no changes to anything under `engine_simulator/engine/`, `gas_dynamics/`, `boundaries/`, `simulation/`, or `postprocessing/`. The editor is a new surface that produces JSON files that the existing loader reads.
2. **Numerical results unchanged.** A sweep run against a config saved through the GUI must produce bit-for-bit identical results to a sweep run against the same JSON written by hand. The save round-trip is verified by a backend test that loads the existing `cbr600rr.json` through the new Pydantic schema, dumps it, calls `load_config()` on the dump, and asserts field-by-field equivalence with `load_config()` on the original.
3. **No silent overwrites of canonical configs.** Save As rejects names that already exist (returns 409). Save in place is allowed and is the common case.
4. **Filename safety.** Server rejects any config name that doesn't match `^[A-Za-z0-9_\-]+\.json$` — no path separators, no traversal, no dotfiles.
5. **Visual identity matches v1.** The Config tab uses the same instrument-chassis aesthetic as `RunSweepDialog` and `TopBar` — corner brackets, `[NN]` index marks, JetBrains Mono tabular-nums on numerics, sharp 1px hairlines, the accent color reserved for the primary action (Save). Reusable form primitives are extracted out of `RunSweepDialog` into `gui-frontend/src/components/forms/` so both surfaces share them.

## Architecture

### High-level data flow

```
   ┌────────────────┐    GET /api/configs       ┌─────────────────┐
   │  configStore   │ ─────────────────────────>│ routes_api.py   │
   │  (zustand)     │                            │                 │
   │                │ <───────────────────────── │  list_configs() │
   │  - available   │                            │                 │
   │  - activeName  │    GET /api/configs/{name} │                 │
   │  - saved       │ ─────────────────────────> │  get_config()   │
   │  - draft       │                            │                 │
   │  - fieldErrors │ <───────────────────────── │  (returns JSON) │
   │                │                            │                 │
   │                │    PUT /api/configs/{name} │  save_config()  │
   │                │ ─────────────────────────> │     │           │
   │                │                            │     ▼           │
   │                │                            │  EnginePayload  │
   │                │                            │   (pydantic)    │
   │                │                            │     │           │
   │                │ <─── 200 OK or 422 ─────── │     ▼           │
   │                │                            │  write JSON     │
   └────────────────┘                            └─────────────────┘
         │
         │ (zustand subscription)
         ▼
   ┌────────────────┐                ┌─────────────────┐
   │  ConfigView    │                │ RunSweepDialog  │
   │  (Config tab)  │                │                 │
   │                │                │  reads          │
   │  reads/writes  │                │  activeName     │
   │  draft via     │                │  as default     │
   │  setField()    │                │                 │
   └────────────────┘                └─────────────────┘
```

The store is the single source of truth. The Config tab edits `draft`. The Run Sweep dialog reads `activeName` to default its config dropdown. `isDirty` is derived from `JSON.stringify(draft) !== JSON.stringify(saved)`.

### Tab navigation

`gui-frontend/src/App.tsx` gains a new row between `<TopBar/>` and the main flex row:

```
TopBar
TabBar           ← new: [ Simulation | Config ]
flex-1 row
  ├ main         ← swaps based on active tab
  │   ├ <SimulationView/>  ← new component, body of current App.tsx lifted in
  │   └ <ConfigView/>      ← new
  └ SweepListSidebar       ← stays visible on both tabs
```

- `SimulationView.tsx` is a near-zero-effort extraction: the existing `<SweepCurves/> <WorkersStrip/> <RpmDetail/>` block becomes a component.
- `TabBar.tsx` is a small new component: two pill-shaped buttons styled like `TopBar`'s action buttons, active tab highlighted.
- Active tab lives in the `configStore` (`activeTab: 'simulation' | 'config'`) so it persists if other state needs to react to it.
- `SweepListSidebar` stays visible on both tabs — it doesn't conflict with the Config view and the user often wants to glance at saved sweeps while tweaking.

### Frontend state — `gui-frontend/src/state/configStore.ts`

New zustand store mirroring the pattern in `sweepStore.ts`:

```ts
import { create } from "zustand";

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

export interface ConfigStore {
  // Catalog
  available: ConfigSummary[];

  // Active document
  activeName: string | null;
  saved: EngineConfigPayload | null;     // last clean copy from disk
  draft: EngineConfigPayload | null;     // in-memory edits

  // UI
  activeTab: "simulation" | "config";
  expandedSections: Record<string, boolean>;

  // Status
  loading: boolean;
  saving: boolean;
  loadError: string | null;
  saveError: string | null;
  saveFlash: number | null;              // timestamp of last successful save
  fieldErrors: Record<string, string>;   // dot-path → server error message

  // Actions
  setActiveTab: (tab: "simulation" | "config") => void;
  refreshList: () => Promise<void>;
  loadConfig: (name: string) => Promise<void>;
  setField: (path: string, value: unknown) => void;
  addPipe: (section: PipeArrayKey) => void;
  removePipe: (section: PipeArrayKey, index: number) => void;
  addCdRow: (valve: "intake_valve" | "exhaust_valve") => void;
  removeCdRow: (valve: "intake_valve" | "exhaust_valve", index: number) => void;
  save: () => Promise<void>;
  saveAs: (newName: string) => Promise<void>;
  revert: () => void;
  toggleSection: (id: string) => void;
}
```

- `setField(path, value)` is a generic dot-path setter (e.g. `setField("intake_valve.open_angle", 340)`); used by `NumericField` `onChange` handlers. Implemented with a small immutable update helper, no external library.
- Pipe-array and cd-table mutations get dedicated actions because the indices need to stay stable and the UI needs to react to length changes.
- `isDirty` is a selector: `(s) => JSON.stringify(s.draft) !== JSON.stringify(s.saved)`. The configs are small (<10 KB JSON), so deep-compare via stringify is fine.
- The store is initialized empty. On first mount of the Config tab, `refreshList()` runs, then `loadConfig(available[0]?.name ?? "cbr600rr.json")` runs.
- `RunSweepDialog` is updated: drop the hard-coded `PREFERRED_CONFIG = "cbr600rr.json"` constant (`RunSweepDialog.tsx:28`) and instead read `activeName` from `configStore` as the default. The dialog's existing dropdown stays, so users can still pick a different config inside the dialog if they want.

### Backend additions — `engine_simulator/gui/`

**New file: `engine_simulator/gui/config_schema.py`**

Pydantic models that mirror every dataclass in `engine_simulator/config/engine_config.py`. One model per dataclass:

```python
from pydantic import BaseModel, Field

class CylinderModel(BaseModel):
    bore: float = Field(gt=0)
    stroke: float = Field(gt=0)
    con_rod_length: float = Field(gt=0)
    compression_ratio: float = Field(gt=1)
    n_intake_valves: int = Field(ge=1)
    n_exhaust_valves: int = Field(ge=1)

class ValveModel(BaseModel):
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
    name: str = Field(min_length=1)
    length: float = Field(gt=0)
    diameter: float = Field(gt=0)
    diameter_out: float | None = Field(default=None, gt=0)
    n_points: int = Field(ge=2, le=200)
    wall_temperature: float = Field(gt=0)
    roughness: float = Field(ge=0)

class CombustionModel(BaseModel):
    wiebe_a: float = Field(gt=0)
    wiebe_m: float = Field(gt=0)
    combustion_duration: float = Field(gt=0, le=180)
    spark_advance: float
    ignition_delay: float = Field(ge=0)
    combustion_efficiency: float = Field(gt=0, le=1)
    q_lhv: float = Field(gt=0)
    afr_stoich: float = Field(gt=0)
    afr_target: float = Field(gt=0)

class RestrictorModel(BaseModel):
    throat_diameter: float = Field(gt=0)
    discharge_coefficient: float = Field(gt=0, le=1)
    converging_half_angle: float = Field(gt=0, lt=90)
    diverging_half_angle: float = Field(gt=0, lt=90)

class PlenumModel(BaseModel):
    volume: float = Field(gt=0)
    initial_pressure: float = Field(gt=0)
    initial_temperature: float = Field(gt=0)

class SimulationModel(BaseModel):
    rpm_start: float = Field(gt=0)
    rpm_end: float = Field(gt=0)
    rpm_step: float = Field(gt=0)
    n_cycles: int = Field(ge=1, le=200)
    cfl_number: float = Field(gt=0, le=1)
    convergence_tolerance: float = Field(gt=0)
    crank_step_max: float = Field(gt=0)
    artificial_viscosity: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_rpm_range(self):
        if self.rpm_end <= self.rpm_start:
            raise ValueError("rpm_end must exceed rpm_start")
        return self

class EnginePayload(BaseModel):
    name: str = Field(min_length=1)
    n_cylinders: int = Field(ge=1)
    firing_order: list[int] = Field(min_length=1)
    firing_interval: float = Field(gt=0)
    cylinder: CylinderModel
    intake_valve: ValveModel
    exhaust_valve: ValveModel
    intake_pipes: list[PipeModel] = Field(min_length=1)
    exhaust_primaries: list[PipeModel] = Field(min_length=1)
    exhaust_secondaries: list[PipeModel] = Field(min_length=1)
    exhaust_collector: PipeModel
    combustion: CombustionModel
    restrictor: RestrictorModel
    plenum: PlenumModel
    simulation: SimulationModel
    p_ambient: float = Field(gt=0)
    T_ambient: float = Field(gt=0)
    drivetrain_efficiency: float = Field(default=1.0, gt=0, le=1)
```

Maintaining the parallel schema (Pydantic ↔ dataclass) is a deliberate trade. The alternative is runtime introspection of the dataclasses, which is fragile (loses field constraints, awkward `Optional`/`list` handling, hard to add cross-field rules like `close_angle > open_angle`). The duplication is small (~80 lines), the round-trip test in §Testing catches any drift, and Pydantic's validation is exactly what we want at the API boundary.

**Updated file: `engine_simulator/gui/routes_api.py`**

Add three new endpoints next to the existing config endpoints:

```python
import re
from engine_simulator.gui.config_schema import EnginePayload

_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+\.json$")

def _validate_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Invalid config name: {name!r}")
    return name

@router.put("/configs/{name}")
async def save_config(name: str, payload: EnginePayload):
    name = _validate_name(name)
    config_path = Path(get_configs_dir()) / name
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config not found: {name}")
    config_path.write_text(payload.model_dump_json(indent=4))
    return payload.model_dump()

class SaveAsRequest(BaseModel):
    name: str
    payload: EnginePayload

@router.post("/configs")
async def save_config_as(req: SaveAsRequest):
    name = _validate_name(req.name)
    config_path = Path(get_configs_dir()) / name
    if config_path.exists():
        raise HTTPException(status_code=409, detail=f"Config already exists: {name}")
    config_path.write_text(req.payload.model_dump_json(indent=4))
    return req.payload.model_dump()
```

The existing `GET /api/configs` and `GET /api/configs/{name}` are unchanged.

**Frontend client additions — `gui-frontend/src/api/client.ts`**

```ts
api.getConfig(name: string): Promise<EngineConfigPayload>
api.saveConfig(name: string, payload: EngineConfigPayload): Promise<EngineConfigPayload>
api.saveConfigAs(name: string, payload: EngineConfigPayload): Promise<EngineConfigPayload>
```

422 responses are parsed and the per-field error array is converted to a `Record<dotpath, message>` map and stored in `configStore.fieldErrors`.

## Config tab UI

`gui-frontend/src/components/ConfigView.tsx` is the top-level for the tab. It composes a sticky header and a stack of section accordions.

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ ◆ ENGINE CONFIG · EDIT      [cbr600rr.json ▾]  ●dirty       │   ← sticky header strip
│                              REVERT  SAVE AS…  SAVE          │
├─────────────────────────────────────────────────────────────┤
│  ▾ [01] IDENTITY                                             │
│        name, n_cylinders, firing_order, firing_interval      │
│  ▾ [02] CYLINDER                                             │
│  ▾ [03] INTAKE VALVE                                         │
│  ▾ [04] EXHAUST VALVE                                        │
│  ▾ [05] INTAKE PIPES         [+ pipe]                        │
│  ▾ [06] EXHAUST PRIMARIES    [+ pipe]                        │
│  ▾ [07] EXHAUST SECONDARIES  [+ pipe]                        │
│  ▾ [08] EXHAUST COLLECTOR                                    │
│  ▾ [09] COMBUSTION                                           │
│  ▾ [10] RESTRICTOR                                           │
│  ▾ [11] PLENUM                                               │
│  ▾ [12] SIMULATION                                           │
│  ▾ [13] AMBIENT                                              │
└─────────────────────────────────────────────────────────────┘
```

- The sticky header is one row pinned to the top of the scroll area.
- File dropdown lists every entry in `available`. Selecting a different name calls `loadConfig(name)`. If `isDirty`, the dropdown shows a confirmation: "Discard unsaved changes?"
- The dirty dot (`●`) is the same accent-colored 6px circle used elsewhere in the UI.
- `Save` is the only button in accent color when dirty; `Save As` and `Revert` are secondary outline buttons matching the `Stop` and `Load` button styles in `TopBar`.
- Sections are collapsible accordions, all open by default. State persists across tab switches via `expandedSections` in the store.

### Section components

One file per section under `gui-frontend/src/components/config/`:

- `IdentitySection.tsx` — `name`, `n_cylinders`, `firing_order` (comma-separated string in/out), `firing_interval`
- `CylinderSection.tsx` — `bore`, `stroke`, `con_rod_length`, `compression_ratio`, `n_intake_valves`, `n_exhaust_valves`
- `ValveSection.tsx` — used twice (intake + exhaust). Takes a `valve: "intake_valve" | "exhaust_valve"` prop. Renders `diameter`, `max_lift`, `open_angle`, `close_angle`, `seat_angle`, then a `<CdTableEditor/>` below
- `PipeListSection.tsx` — used three times (intake_pipes, exhaust_primaries, exhaust_secondaries). Takes a `section: "intake_pipes" | "exhaust_primaries" | "exhaust_secondaries"` prop. Renders one `<PipeRow/>` per pipe plus a `[+ add pipe]` button
- `PipeRowSection.tsx` — used once for `exhaust_collector` (single pipe, no array)
- `CombustionSection.tsx` — all combustion fields
- `RestrictorSection.tsx`, `PlenumSection.tsx`, `SimulationSection.tsx`, `AmbientSection.tsx` — same shape as combustion

Each section is small (one screen of code), reads its slice from the store via a selector, and emits changes via `setField(path, value)`.

### Reusable form primitives — `gui-frontend/src/components/forms/`

These are extracted out of `RunSweepDialog.tsx` (one call site to update there) so the dialog and the Config tab share them:

- `NumericField.tsx` — already exists in `RunSweepDialog.tsx:422`. Move it here unchanged.
- `CornerBrackets.tsx` — already exists in `RunSweepDialog.tsx:695`. Move it here unchanged.
- `TextField.tsx` — new, mirrors `NumericField` but for `name` and `firing_order` strings.
- `Accordion.tsx` — new. Header row with `▾`/`▸` chevron, `[NN]` index mark, label, optional right-side action slot (used for `[+ pipe]` buttons). Body slot with collapse animation.
- `CdTableEditor.tsx` — new. Renders a list of `(L/D, Cd)` rows, each row is two `NumericField`s side by side plus a `[×]` delete button. `[+ add row]` button below. On save, rows are sorted by L/D ascending (the `cd_table` is a lookup that depends on monotonic ordering).
- `PipeRow.tsx` — new. Single-row layout: `name` text field on the left, then `length`, `diameter`, `diameter_out` (optional, blank means constant-area), `n_points`, `wall_temperature`, `roughness` `NumericField`s in a horizontal row, then a `[×]` delete button.

### Field unit conventions

The JSON file stores SI units (meters, Kelvin, Pascal). Typing `0.0275` for valve diameter is unfriendly. The form converts at the field level: the input shows the friendly unit, the store keeps SI.

| Field type | JSON unit | Display unit | Conversion |
|---|---|---|---|
| pipe length, valve diameter, bore, stroke, con rod, max_lift, throat_diameter | m | mm | × 1000 in / out |
| plenum volume | m³ | L | × 1000 in / out |
| pressure (initial_pressure, p_ambient) | Pa | kPa | × 0.001 in / out |
| temperature (wall_temperature, T_ambient, initial_temperature) | K | K | none |
| angle (open_angle, close_angle, seat_angle, half_angles, spark_advance, etc.) | deg | deg | none |
| roughness | m | µm | × 1e6 in / out |
| LHV (q_lhv) | J/kg | MJ/kg | × 1e-6 in / out |
| RPM | rpm | rpm | none |
| dimensionless (Cd, AFR, CFL, n_cycles, etc.) | — | — | none |

The conversion is encapsulated in `NumericField` props (`displayScale: number`, `displayUnit: string`). Section components specify the scale and unit; the field handles the round-trip on input and display.

## Validation & error handling

Two layers, both lightweight.

### Client-side (instant feedback)

- Per `NumericField`, validation runs on every change. Errors render inline in the field's label row, same pattern as `RunSweepDialog.tsx:122`.
- Rules are simple type/sign checks living next to each section component as a small `validate(slice): Record<path, string>` function. The store derives `clientErrors` by merging all section validators.
- Specific cross-field rules:
  - `cylinder.compression_ratio > 1`
  - `restrictor.discharge_coefficient ∈ (0, 1]`
  - `0 < drivetrain_efficiency ≤ 1`
  - `intake_valve.close_angle > intake_valve.open_angle` (same for exhaust)
  - `simulation.rpm_end > simulation.rpm_start`
  - `cd_table` rows are auto-sorted by L/D ascending on save (the lookup requires monotonic ordering); the user is not warned because the result is visible after the save round-trip
- `Save` is disabled when `clientErrors` is non-empty. `Revert` and `Save As` are always enabled — Save As lets the user snapshot a known-good state under a new name even mid-edit.

### Server-side (authoritative)

- Pydantic models in `config_schema.py` enforce the same constraints plus structural shape. Anything the client missed gets caught here.
- 422 response body's `detail` array is parsed in `client.ts`: each entry's `loc` (e.g. `["body", "intake_valve", "cd_table", 0, 0]`) is joined with `.` to form a dot-path key (`intake_valve.cd_table.0.0`) and stored in `configStore.fieldErrors`.
- Each `NumericField` reads from both `clientErrors` and `fieldErrors` (server takes precedence) and renders whichever is set.
- Server errors clear when the user edits the offending field.

### Save flow

1. User clicks `Save`. `saving = true`, button shows the same spinner as `RunSweepDialog`'s dispatch button.
2. Success: `saved` updates to the returned payload, `draft` is also updated to match (so any server-side normalization like sorted cd_table is reflected), dirty dot clears, `saveFlash` set to current timestamp. Header strip shows `SAVED · 14:32:05` for ~3 seconds.
3. Failure: `saving = false`, red error strip identical to the `RunSweepDialog` error strip pattern (`RunSweepDialog.tsx:343`) appears at the top of the form, fields with `loc` errors highlighted.

### Save As flow

- Inline prompt in the header strip (no modal): `Save As [______________.json] [confirm] [cancel]`. The input swaps in where the buttons were.
- Frontend appends `.json` if the user omits the extension, then validates against the same regex the server uses (`^[A-Za-z0-9_\-]+\.json$`) before sending.
- On success: `available` is refreshed via `refreshList()`, `activeName` switches to the new file, `saved` and `draft` updated, dirty clears.
- On 409 (file exists): the prompt shows `Already exists. Use a different name.` inline.

### Sweep-while-dirty guard

- If the user clicks `Run Sweep` (TopBar) while `isDirty && activeName !== null`, the dialog opens with a small warning strip near the config dropdown: `Active config has unsaved changes — sweep will use the saved version on disk`.
- The user can still proceed. We don't block, because they may have started editing speculatively and want to compare.

## Testing

### Backend (pytest)

**New file: `tests/test_config_routes.py`**
- `test_get_config_returns_existing` — `GET /api/configs/cbr600rr.json` returns the file as JSON.
- `test_save_roundtrips_valid_payload` — `PUT /api/configs/{name}` with a valid payload writes to disk; reading the file back matches the request.
- `test_save_rejects_negative_bore` — `PUT` with `cylinder.bore = -1` returns 422 with a `loc` of `["body", "cylinder", "bore"]`.
- `test_save_rejects_invalid_compression_ratio` — `compression_ratio = 0.5` → 422.
- `test_save_rejects_dc_above_one` — `restrictor.discharge_coefficient = 1.5` → 422.
- `test_save_rejects_close_before_open` — `intake_valve.close_angle <= open_angle` → 422.
- `test_save_rejects_traversal_name` — name `../../etc/passwd.json` → 400.
- `test_save_rejects_path_separator` — name `foo/bar.json` → 400.
- `test_save_as_creates_new_file` — `POST /api/configs` with new name writes the file; `GET /api/configs` lists it.
- `test_save_as_rejects_existing_name` — `POST` with an existing name returns 409.
- All tests `monkeypatch` `get_configs_dir` to point at `tmp_path` so the real `cbr600rr.json` is never touched.

**New file: `tests/test_config_schema.py`**
- `test_existing_cbr600rr_loads_into_pydantic` — open `engine_simulator/config/cbr600rr.json`, parse with `EnginePayload.model_validate()`, no errors.
- `test_pydantic_dump_loads_via_load_config` — load the file via Pydantic, dump it back to JSON, write to a temp file, call `engine_simulator.config.engine_config.load_config()` on the temp file, and compare every field of the resulting `EngineConfig` to a `load_config()` of the original. Bit-for-bit equivalence is required. **This is the critical test** — it's the whole reason the parallel Pydantic schema exists.
- `test_pydantic_round_trip_preserves_cd_table` — specifically verifies `cd_table` round-trips as a list of tuples (Pydantic and JSON have nuance about tuples vs lists).
- `test_pydantic_round_trip_preserves_optional_diameter_out` — verifies `PipeModel.diameter_out = None` round-trips correctly.

### Frontend

- No new test runner. The frontend is verified by the backend round-trip test (the server rejects bad payloads regardless of what the frontend sends), `tsc` strict mode, and the manual checklist below.
- `setField` is implemented with a typed dot-path so mistyped paths are caught at compile time.
- If the user wants `vitest` later, it's a separate piece of work.

### Manual integration checklist

Run after implementation, document outcomes in the PR description:

1. Open Config tab, see `cbr600rr.json` loaded with all 13 sections populated.
2. Change `intake_valve.open_angle` from `338` to `340`. Dirty dot appears. Click `Save`. Dot clears, `cbr600rr.json` on disk shows `340`.
3. Type `-1` into `cylinder.bore`. Inline red error appears. `Save` is disabled.
4. Click `Save As`, type `tweaked.json`, confirm. Dropdown shows `tweaked.json` selected. Open `Run Sweep` — `tweaked.json` is the default in the config dropdown.
5. With `tweaked.json` dirty (edit some field), click `Run Sweep`. Dialog opens with warning strip about unsaved changes.
6. Add a new pipe to `intake_pipes`, save, run a 1-RPM sweep. Confirm in the worker output that the new pipe is part of the simulation (the per-pipe traces shown in `PipeTraces.tsx` include the added pipe).
7. Click `Revert`. All fields restore to last saved values without page reload.
8. Edit a `cd_table` row (change `0.10 → 0.312` to `0.10 → 0.350`). Delete a row. Add a row. Save. Open `tweaked.json` on disk and confirm the cd_table reflects all three changes and is sorted by L/D.
9. Try to save with name `../etc/passwd.json` via dev tools → server returns 400 with the validation error.

That last item is a sanity check on the filename safety net — not user-reachable, but good to confirm the server-side guard fires.

## File-by-file change list

### New files
- `engine_simulator/gui/config_schema.py` — Pydantic models mirroring `engine_config.py` dataclasses
- `tests/test_config_routes.py` — endpoint tests
- `tests/test_config_schema.py` — round-trip equivalence tests
- `gui-frontend/src/state/configStore.ts` — zustand store for config state
- `gui-frontend/src/components/ConfigView.tsx` — Config tab top-level
- `gui-frontend/src/components/SimulationView.tsx` — extracted from `App.tsx`
- `gui-frontend/src/components/TabBar.tsx` — tab navigation strip
- `gui-frontend/src/components/forms/NumericField.tsx` — moved out of `RunSweepDialog.tsx`
- `gui-frontend/src/components/forms/TextField.tsx`
- `gui-frontend/src/components/forms/CornerBrackets.tsx` — moved out of `RunSweepDialog.tsx`
- `gui-frontend/src/components/forms/Accordion.tsx`
- `gui-frontend/src/components/forms/CdTableEditor.tsx`
- `gui-frontend/src/components/forms/PipeRow.tsx`
- `gui-frontend/src/components/config/IdentitySection.tsx`
- `gui-frontend/src/components/config/CylinderSection.tsx`
- `gui-frontend/src/components/config/ValveSection.tsx`
- `gui-frontend/src/components/config/PipeListSection.tsx`
- `gui-frontend/src/components/config/PipeRowSection.tsx`
- `gui-frontend/src/components/config/CombustionSection.tsx`
- `gui-frontend/src/components/config/RestrictorSection.tsx`
- `gui-frontend/src/components/config/PlenumSection.tsx`
- `gui-frontend/src/components/config/SimulationSection.tsx`
- `gui-frontend/src/components/config/AmbientSection.tsx`

### Modified files
- `engine_simulator/gui/routes_api.py` — add `PUT /api/configs/{name}` and `POST /api/configs` endpoints, add `_validate_name` helper
- `gui-frontend/src/api/client.ts` — add `getConfig`, `saveConfig`, `saveConfigAs` methods and `EngineConfigPayload` type
- `gui-frontend/src/App.tsx` — insert `<TabBar/>` row, swap main pane between `<SimulationView/>` and `<ConfigView/>` based on `activeTab`
- `gui-frontend/src/components/RunSweepDialog.tsx` — remove `PREFERRED_CONFIG` constant, read default config from `configStore.activeName`, update import path for `NumericField` and `CornerBrackets`

### Files explicitly NOT touched
- `engine_simulator/config/engine_config.py` — dataclasses and `load_config()` unchanged
- `engine_simulator/engine/`, `gas_dynamics/`, `boundaries/`, `simulation/`, `postprocessing/` — solver code unchanged
- `engine_simulator/main.py` — CLI unchanged
- `engine_simulator/gui/sweep_manager.py`, `gui_event_consumer.py`, `routes_ws.py`, `server.py` — sweep flow unchanged

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Pydantic schema drifts from dataclass schema as fields are added | `test_pydantic_dump_loads_via_load_config` round-trip test fails immediately; CI catches it |
| User saves invalid config that crashes the solver | Pydantic validates structurally + range; the solver is only run after save succeeds; if a runtime crash occurs the existing sweep error handling reports it in the UI |
| User accidentally overwrites `cbr600rr.json` | Save in place is intentional; `git status` will show the change; this is the same risk as editing the file in a text editor and matches the user's stated workflow |
| Save As clobbers an existing file | 409 response; user must pick a different name |
| Form layout breaks on small screens | The aesthetic is desktop-first like the rest of the GUI; we don't optimize for narrow widths in v1 |
| Future v3 parameter sweep needs JSON-path addressing of fields, not currently exposed | The `setField(path, value)` API is exactly that addressing scheme; v3 will reuse it directly |

## Future work (out of scope for this spec)

- **v3 parameter sweep**: select a single field (or multiple), specify a range, run a sweep that varies the field across configs and plots the perf metric. This spec's `setField(path, value)` and `EnginePayload` are the foundation.
- **Diff between configs**: side-by-side view of two configs with changed fields highlighted.
- **Presets**: snapshot common tunes (e.g. "intake-tuned", "exhaust-tuned", "stock") as named preset buttons.
- **Schema documentation**: hover on a field to see the dataclass field's docstring/comment from `engine_config.py`. Requires either parsing the dataclass source or maintaining a parallel description map.
