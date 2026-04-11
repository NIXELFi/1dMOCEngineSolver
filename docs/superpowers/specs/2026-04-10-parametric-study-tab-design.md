# Parametric Study Tab — Design Spec

**Date:** 2026-04-10
**Status:** Approved, pending implementation plan

## Overview

Add a new GUI tab for running **parametric studies** — exhaustive sweeps of a single engine-design parameter (e.g. intake runner length, plenum volume, restrictor Cd) across a user-defined range, where each parameter value triggers a full RPM sweep. Results are compared side by side and ranked by a user-selectable optimization objective (peak HP, peak torque, torque area, power/torque at a specific RPM).

The feature is additive: it does not modify the existing Simulation/Config/Dyno tabs, the existing `SweepManager`, or the existing sweep persistence layer.

## Goals

- Let the user answer "what's the best intake runner length for torque area?" (or peak HP, or peak torque at 9000 RPM, etc.) without manually editing configs and running sweeps one at a time.
- Present results in a format that makes the answer obvious: a ranked table, overlay charts, and a heatmap.
- Keep parametric studies persistent and independently loadable, distinct from regular sweeps.
- Design the data model so that multi-parameter grid studies can be added later without breaking existing saved studies.

## Non-Goals (YAGNI)

- Multi-parameter grid sweeps (two or more parameters varied jointly) — the data model is forward-compatible but this is a follow-on feature.
- Automatic optimization (gradient descent, golden section, Bayesian optimization). Exhaustive enumeration only.
- Cross-study comparison (comparing two distinct parametric studies against each other).
- PDF report generation for parametric studies.
- Pause/resume. Stop means stop; restart from scratch.
- Sweeping arbitrary config fields outside an explicit whitelist.
- Custom user-defined objective functions.

## Architecture

### New backend pieces

- **`engine_simulator/gui/parametric/`** — new package:
  - `parameters.py` — whitelist of sweepable parameters
  - `path_resolver.py` — dotted-path get/set with `[*]` wildcard support
  - `study_manager.py` — `ParametricStudyManager` owning study lifecycle
  - `persistence.py` — save/load parametric studies
  - `event_consumer.py` — `ParametricEventConsumer` that bridges inner-sweep events onto the parametric channel
  - `schema.py` — Pydantic models for request validation
- **`engine_simulator/gui/routes_parametric.py`** — new REST router under `/api/parametric/`
- **`engine_simulator/gui/routes_ws.py`** — extended to broadcast parametric-channel messages
- **Persistence directory:** `sweeps/parametric/` (sibling to existing `sweeps/`)

### New frontend pieces

- **New `"parametric"` tab** in `gui-frontend/src/components/TabBar.tsx` (4th tab)
- **`gui-frontend/src/state/parametricStore.ts`** — new Zustand store
- **`gui-frontend/src/state/parametricSelectors.ts`** — pure functions computing derived metrics, comparison table, heatmap data
- **`gui-frontend/src/state/eventReducer.ts`** — extended with a parametric-channel branch at the top
- **`gui-frontend/src/api/client.ts`** — new API methods for parametric endpoints
- **`gui-frontend/src/components/parametric/`** — new component directory:
  - `ParametricView.tsx` — root, routes between Mode A/B/C
  - `ParametricSetupForm.tsx` — Mode A
  - `ParametricRunGrid.tsx` — Mode B (live progress cards)
  - `ParametricResultsView.tsx` — Mode C (controls + charts + table + heatmap)
  - `ParametricOverlayCharts.tsx` — 2×2 chart grid with color-coded runs
  - `ParametricComparisonTable.tsx` — ranked summary table
  - `ParametricHeatmap.tsx` — parameter-value × RPM heatmap
  - `ParametricStudyListSidebar.tsx` — past studies list

### Unchanged

- `SweepManager`, `sweepStore`, existing 3 tabs
- `SimulationOrchestrator` — used as-is
- `ParallelSweepRunner` — used as-is, internally by orchestrator

## Data Model

### ParametricStudyDef (study definition)

```python
@dataclass
class ParametricStudyDef:
    study_id: str                    # server-assigned: "param_{ISO_TIMESTAMP}"
    name: str                        # user-supplied or auto-generated from parameter + range
    config_name: str                 # base engine config to mutate
    parameter_path: str              # dotted path, e.g. "intake_pipes[*].length"
    parameter_values: list[float]    # explicit list (server-generated from start/end/step if omitted)
    sweep_rpm_start: float           # default 3000
    sweep_rpm_end: float              # default 15000
    sweep_rpm_step: float             # default inherited from base config
    sweep_n_cycles: int              # default inherited from base config
    n_workers: int | None            # default inherited
    created_at: str                  # server-assigned ISO timestamp
```

### ParametricRun (per parameter value)

```python
@dataclass
class ParametricRun:
    parameter_value: float
    status: Literal["queued", "running", "done", "error"]
    sweep_results: list[dict]        # perf dicts, same shape as existing sweep results
    per_rpm_delta: dict[float, float] # last convergence delta per RPM
    elapsed_seconds: float
    error: str | None
```

### LiveParametricStudy (in-memory + persisted)

The same dataclass represents both the live in-memory study and the persisted form — on save, it's serialized to JSON; on load, it's deserialized back. This mirrors how `LiveSweepState` works for regular sweeps.

```python
@dataclass
class LiveParametricStudy:
    definition: ParametricStudyDef
    status: Literal["running", "complete", "error", "stopped"]
    started_at: str
    completed_at: str | None
    runs: list[ParametricRun]
    error: str | None
```

### Derived metrics (computed on demand, not stored)

Computed from `sweep_results` in the frontend so objective/window changes don't require re-fetching:

- `peak_power_hp`, `peak_power_rpm`
- `peak_torque_Nm`, `peak_torque_rpm`
- `torque_area` — integrated torque over user-selectable RPM window (default: full range)
- `power_at_rpm(rpm)` — linear interpolation
- `torque_at_rpm(rpm)` — linear interpolation
- `ve_peak`, `ve_avg`

## Sweepable Parameters (Whitelist)

Lives in `engine_simulator/gui/parametric/parameters.py`:

```python
@dataclass
class Param:
    path: str                                  # dotted path into config dict
    label: str                                 # human-readable name
    unit: str                                  # display unit
    default_range: tuple[float, float, float]  # (start, end, step) in storage units
    display_scale: float = 1.0                 # e.g. 1000 to display meters as mm
    min_allowed: float | None = None           # hard safety bound
    max_allowed: float | None = None

SWEEPABLE_PARAMETERS = [
    # Intake pipes (all runners swept together)
    # Storage: meters. UI displays as mm (display_scale=1000), UI labels as "mm".
    Param("intake_pipes[*].length",   "Intake Runner Length",   "mm", (0.10, 0.40, 0.025), display_scale=1000),
    Param("intake_pipes[*].diameter", "Intake Runner Diameter", "mm", (0.030, 0.050, 0.0025), display_scale=1000),

    # Exhaust pipes (storage: meters, display: mm)
    Param("exhaust_primaries[*].length",     "Exhaust Primary Length",     "mm", (0.25, 0.60, 0.05), display_scale=1000),
    Param("exhaust_primaries[*].diameter",   "Exhaust Primary Diameter",   "mm", (0.028, 0.045, 0.002), display_scale=1000),
    Param("exhaust_secondaries[*].length",   "Exhaust Secondary Length",   "mm", (0.20, 0.50, 0.05), display_scale=1000),
    Param("exhaust_secondaries[*].diameter", "Exhaust Secondary Diameter", "mm", (0.035, 0.055, 0.0025), display_scale=1000),

    # Plenum (storage: m³, display: liters)
    Param("plenum.volume", "Plenum Volume", "L", (0.0005, 0.004, 0.00025), display_scale=1000),

    # Restrictor
    Param("restrictor.discharge_coefficient", "Restrictor Cd", "", (0.85, 0.98, 0.01)),

    # Valve timing (storage: degrees crank angle, matches ValveConfig units)
    Param("intake_valve.open_angle",   "IVO (BTDC)", "deg CA", (-20, 30, 5)),
    Param("intake_valve.close_angle",  "IVC (ABDC)", "deg CA", (30, 80, 5)),
    Param("exhaust_valve.open_angle",  "EVO (BBDC)", "deg CA", (30, 80, 5)),
    Param("exhaust_valve.close_angle", "EVC (ATDC)", "deg CA", (-20, 30, 5)),
    # Valve lift (storage: meters, display: mm)
    Param("intake_valve.max_lift",     "Intake Max Lift",  "mm", (0.006, 0.012, 0.0005), display_scale=1000),
    Param("exhaust_valve.max_lift",    "Exhaust Max Lift", "mm", (0.006, 0.012, 0.0005), display_scale=1000),

    # Combustion
    Param("combustion.spark_advance",       "Spark Advance", "deg BTDC", (10, 40, 2)),
    Param("combustion.combustion_duration", "Burn Duration", "deg CA",   (30, 70, 5)),
    Param("combustion.afr_target",          "Target AFR",    "",          (11.5, 14.7, 0.25)),
]
```

**Path format:**
- Dotted: `plenum.volume`
- Indexed: `intake_pipes[0].length`
- Wildcard: `intake_pipes[*].length` applies to all elements of the list. Used by default for pipes so multi-cylinder engines stay consistent.

**Display scale convention:** `default_range` and all API I/O use **storage units** (SI: meters, m³, radians). `display_scale` is a multiplier applied only at the UI boundary — e.g. `display_scale=1000` for a length in meters shows the user mm values and converts on submit. The backend never sees scaled values; the frontend converts at input/render time. This keeps all validation, persistence, and path resolution in consistent units.

**Excluded on purpose:** `bore`, `stroke`, `con_rod_length`, `compression_ratio`, `n_cylinders`, `firing_order`, CFL, convergence tolerance, ambient conditions. These are fundamental engine geometry or solver parameters — not design levers.

**API exposure:** `GET /api/parametric/parameters` returns this list so the frontend renders the dropdown dynamically without hardcoding.

## Backend: Study Execution Flow

### `ParametricStudyManager`

Lives in `engine_simulator/gui/parametric/study_manager.py`. Mirrors `SweepManager` structure. Single active study at a time.

```python
class ParametricStudyManager:
    def __init__(self, configs_dir, studies_dir, broadcaster):
        self._current: LiveParametricStudy | None
        self._executor: ThreadPoolExecutor
        self._stop_flag: threading.Event
        self._broadcast: Callable  # async broadcast callback

    def start_study(self, def_: ParametricStudyDef) -> str
    def stop_study(self) -> None
    def get_current(self) -> LiveParametricStudy | None
    def list_studies(self) -> list[dict]
    def load_study(self, study_id: str) -> LiveParametricStudy
```

### Execution loop (background thread)

```
1. Load base config from config_name
2. Validate parameter_path is in the whitelist
3. For each parameter_value in parameter_values:
   a. Check stop_flag — bail out if set
   b. Deep-copy base config dict, mutate via path_resolver.set_parameter()
   c. Broadcast parametric_value_start event
   d. Construct fresh SimulationOrchestrator(mutated_config_as_EngineConfig)
   e. Call orchestrator.run_rpm_sweep(..., consumer=ParametricEventConsumer(parameter_value))
      which re-broadcasts nested sweep events on the parametric channel
   f. Collect perf dicts → append to run.sweep_results
   g. Broadcast parametric_value_done event with completed ParametricRun
4. Compute summary (best parameter value per standard objective)
5. Persist to sweeps/parametric/{study_id}.json via persistence.save_study()
6. Broadcast parametric_study_complete event
```

### Path resolver

`engine_simulator/gui/parametric/path_resolver.py`:

```python
def get_parameter(config_dict: dict, path: str) -> Any
def set_parameter(config_dict: dict, path: str, value: float) -> dict  # returns new dict, non-mutating
```

- Operates on the JSON dict representation of the config, not on the `EngineConfig` dataclass.
- `set_parameter` always returns a fresh deep copy; the input dict is never mutated.
- Validates the new value against `Param.min_allowed` / `Param.max_allowed` if set.
- Wildcard `[*]` applies the mutation to every element of the matching list.

### Config mutation strategy

Mutate at the dict level (post-JSON-serialization, pre-`EngineConfig` reconstruction). This keeps `EngineConfig` immutable, avoids state bleed between iterations, and uses the same serialization format that the GUI config editor uses. Each iteration: `dict → set_parameter → EngineConfig.from_dict → SimulationOrchestrator`.

### Stop behavior

`stop_study()` sets `_stop_flag`. The loop checks the flag between parameter values (not mid-sweep). An in-flight RPM sweep completes its current parameter value, then the loop exits cleanly. This matches the behavior model of stopping a regular sweep mid-RPM: the current atomic unit finishes.

### Error isolation

If one parameter value's sweep raises (e.g. numerical instability at an extreme value), the manager:
1. Catches the exception
2. Marks that `ParametricRun` as `status="error"` with `error=traceback`
3. Broadcasts `parametric_value_error`
4. Continues to the next parameter value

The whole study does not abort on a single failed value — critical for convergence studies where extreme values may be unstable.

## Backend: API & WebSocket Events

### REST endpoints (`/api/parametric/`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/parametric/parameters` | GET | List sweepable parameters (the whitelist) |
| `/api/parametric/studies` | GET | List saved studies (metadata only) |
| `/api/parametric/studies/{id}` | GET | Load full study result JSON |
| `/api/parametric/studies/{id}` | DELETE | Delete a saved study |
| `/api/parametric/study/start` | POST | Start new study. Body: `ParametricStudyStartRequest` |
| `/api/parametric/study/stop` | POST | Stop the currently running study |
| `/api/parametric/study/current` | GET | Snapshot of current live study (for reconnect) |

### Request validation (Pydantic)

- `config_name` must exist in the configs directory
- `parameter_path` must be in the whitelist
- `parameter_values` must be non-empty, finite, within `min_allowed`/`max_allowed`
- If `parameter_values` is omitted but `(start, end, step)` is provided, the server generates the list
- `rpm_end > rpm_start`, `rpm_step > 0`

### WebSocket events

Multiplexed on the existing `/ws/events` connection. Every parametric message carries a `"channel": "parametric"` field so the frontend reducer routes it to the correct store without touching the regular sweep reducer.

| Event type | Fields | When |
|---|---|---|
| `parametric_snapshot` | `study` (full LiveParametricStudy) | On connect, after `load_study`, or reset |
| `parametric_study_start` | `study_id, definition` | Study kicks off |
| `parametric_value_start` | `study_id, parameter_value, value_index` | Starting this parameter value's sweep |
| `parametric_rpm_start` | `study_id, parameter_value, rpm, rpm_index, n_cycles_target` | Inner sweep RPM start (re-broadcast) |
| `parametric_rpm_cycle` | `study_id, parameter_value, rpm, cycle, delta` | Inner sweep cycle-done |
| `parametric_rpm_done` | `study_id, parameter_value, rpm, perf, converged` | Inner sweep RPM complete |
| `parametric_value_done` | `study_id, parameter_value, value_index, run` | Parameter value's full RPM sweep finished |
| `parametric_value_error` | `study_id, parameter_value, error_type, error_msg` | Parameter value's sweep errored (study continues) |
| `parametric_study_complete` | `study_id, filename` | All values done, saved to disk |
| `parametric_study_stopped` | `study_id` | User stopped the study |
| `parametric_study_error` | `study_id, error_msg` | Study-level error |

### Event bridging

`ParametricEventConsumer` implements the existing `EventConsumer` protocol, wrapping the inner sweep's `RPMStartEvent`/`CycleDoneEvent`/`RPMDoneEvent` and re-emitting them as parametric-channel messages tagged with the current `parameter_value`. The inner sweep remains completely unaware it's running inside a parametric study.

### Broadcast infrastructure

Reuses the existing WebSocket broadcaster in `routes_ws.py`. No new connection, no new port — the broadcaster just adds the `channel` field to each outgoing message.

## Frontend: Store & Event Handling

### `parametricStore.ts` (Zustand)

```typescript
interface ParametricState {
  // Current live or loaded study
  current: LiveParametricStudy | null;

  // Past studies (sidebar)
  studies: ParametricStudySummary[];
  studiesLoading: boolean;
  studiesError: string | null;

  // Sweepable parameters (loaded once on mount)
  availableParameters: Param[];

  // UI state for results view
  selectedObjective: ObjectiveKey;
    // "peak_power" | "peak_torque" | "torque_area" | "power_at_rpm" | "torque_at_rpm"
  objectiveRpm: number | null;           // for "power_at_rpm" / "torque_at_rpm"
  objectiveRpmWindow: [number, number];  // for "torque_area"
  selectedRunIndices: Set<number>;       // which runs visible on overlay charts
  highlightedRunIndex: number | null;    // hover state

  // Connection state (same ws as regular sweeps)
  connected: boolean;

  // Actions
  setSelectedObjective, setObjectiveRpm, setObjectiveRpmWindow,
  toggleRunSelected, setHighlightedRun, clearCurrent,

  // Internal reducer mutations
  _applySnapshot, _applyValueStart, _applyRpmDone, _applyValueDone, ...
}
```

### Derived data (`parametricSelectors.ts`)

Pure functions — not stored in state — so changing the objective or RPM window re-ranks instantly with no re-fetch:

```typescript
computeRunMetrics(run, objectiveRpm, objectiveRpmWindow): RunMetrics
computeComparisonTable(study, objective, objectiveRpm, window): ComparisonRow[]
computeHeatmapData(study, metric): HeatmapData
```

### Event reducer extension (`eventReducer.ts`)

```typescript
if (message.channel === "parametric") {
  handleParametricEvent(message);
  return;
}
// existing sweep handling unchanged
```

`handleParametricEvent` is a switch over parametric event types, calling `_apply*` mutations on `parametricStore`. The existing sweep reducer is completely untouched.

### API client additions

```typescript
api.listParametricParameters(): Promise<Param[]>
api.listParametricStudies(): Promise<ParametricStudySummary[]>
api.loadParametricStudy(id): Promise<LiveParametricStudy>
api.deleteParametricStudy(id): Promise<void>
api.startParametricStudy(def): Promise<{ study_id: string }>
api.stopParametricStudy(): Promise<void>
```

## Frontend: UI Layout

The **Parametric tab** routes between three modes based on store state:

- `current == null && no selected saved study` → **Mode A (Setup)**
- `current?.status === "running"` → **Mode B (Running)**
- otherwise → **Mode C (Results)**

### Mode A: Setup form

Matches the visual style of `RunSweepDialog` (numbered fields, corner brackets, dark surface):

- [01] Engine Config — dropdown (same source as `RunSweepDialog`)
- [02] Parameter — grouped dropdown from `availableParameters` (Intake / Exhaust / Plenum / Restrictor / Valve Timing / Combustion)
- [03] Value Start — numeric, auto-populated from `param.default_range[0]`, display-scaled
- [04] Value End — numeric, auto-populated from `param.default_range[1]`
- [05] Value Step — numeric, auto-populated from `param.default_range[2]`
- [06] RPM Start — default 3000
- [07] RPM End — default 15000
- [08] RPM Step — default from config
- [09] Cycles per RPM — default from config
- [10] Workers — discrete slider (reuse `WorkersField` from `RunSweepDialog`)

**Live readout panel:**
- Number of parameter values
- Number of RPM points
- Total simulations = values × RPM points
- Rough estimated runtime (from historical `rpm_done` elapsed times, else hidden)

**Dispatch button** — disabled until validation passes.

### Mode B: Running

Top bar: study definition summary + stop button.

**Main area:** grid of mini-cards, one per parameter value:
- Parameter value label (e.g. "L = 250mm")
- Status badge: queued / running / done / error
- Mini RPM progress bar
- Compact power curve sparkline (fills in as RPM results stream)
- Elapsed time

Current value highlighted. Finished cards are clickable → drawer with full RPM sweep data.

### Mode C: Results

**1. Controls bar (sticky):**
- Objective selector: Peak HP / Peak Torque / Torque Area / HP @ RPM / Torque @ RPM
- RPM field(s) appear when objective requires them
- Show-all / Hide-all toggle for overlay chart runs

**2. Overlay charts (2×2, using existing `LineChart`):**
- Brake Power vs RPM (color-coded by parameter value, cool → warm gradient)
- Brake Torque vs RPM
- VE (atm) vs RPM
- Plenum Pressure vs RPM

Chart hover ↔ table row highlight is bidirectional. Color legend on the right lists each parameter value with a visibility checkbox.

**3. Summary table:** ranked by selected objective, columns:

| Rank | Param Value | Peak HP (rpm) | Peak Torque (rpm) | Torque Area | HP @ RPM | VE peak | Status |

- Bold column = current objective
- Row click → drawer with per-RPM breakdown
- Errored runs at bottom with error message

**4. Heatmap (collapsible section below table):**
- Y: parameter values (ascending)
- X: RPM
- Cell color: brake HP (or metric chosen from small dropdown)
- Per-RPM optimum marked with a dot

### Sidebar

New `ParametricStudyListSidebar` shown below the existing `SweepListSidebar` (or as a second collapsible section). Each entry: parameter label, range, created time, run count, status. Click to load.

## Testing Strategy

### Backend unit tests (pytest)

- `tests/test_parametric_path_resolver.py` — get/set on all whitelisted paths, `[*]` wildcard, deep-copy isolation, `min_allowed`/`max_allowed` enforcement
- `tests/test_parametric_parameters.py` — whitelist integrity; each `default_range` valid; each path resolvable against the default config
- `tests/test_parametric_study_manager.py` — with `SimulationOrchestrator.run_rpm_sweep` mocked to return canned perf dicts:
  - Happy path: N values → N sweeps in order
  - Stop mid-study: flag honored between values
  - Error isolation: one value raises, others still complete
  - Config mutation correctness: each iteration sees the right parameter value, no state bleed
- `tests/test_parametric_persistence.py` — save → load round-trip, numpy coercion, non-finite handling
- `tests/test_parametric_api.py` — FastAPI TestClient: request validation, 404s, end-to-end start/list/load flow

### Backend integration test

One end-to-end test that runs a tiny real study (2 parameter values × 2 RPM points × 1 cycle) with the actual orchestrator — catches wiring bugs the mocked tests miss.

### Frontend unit tests (vitest)

- `parametricSelectors.test.ts` — metric computation from canned sweep_results, ranking logic, objective switching, heatmap shape
- `parametricStore.test.ts` — reducer actions produce expected state transitions
- `eventReducer.test.ts` — parametric-channel events route to parametric store; sweep-channel events remain unaffected

### Frontend manual smoke

Manual browser verification of Mode A → B → C transitions with a tiny study after implementation.

## Implementation Phasing

1. **Backend foundation** — `parameters.py` whitelist + `path_resolver.py` + tests
2. **Study manager** — `ParametricStudyManager`, persistence, unit tests with mocked orchestrator
3. **API + WebSocket** — routes, event broadcasting, integration test with real orchestrator on a tiny study
4. **Frontend plumbing** — store, selectors, API client, event reducer extension + unit tests
5. **Frontend UI — Mode A** — setup form, parameter dropdown, validation
6. **Frontend UI — Mode B** — live progress grid
7. **Frontend UI — Mode C** — controls, overlay charts, summary table, heatmap
8. **Sidebar integration** — parametric study list

Each phase is independently testable. The backend can be driven from the CLI / curl before any frontend exists.

## Forward Compatibility

The data model is designed so multi-parameter grid sweeps can be added later without breaking existing saved studies:
- `ParametricStudyDef.parameter_path` and `parameter_values` can be generalized to `axes: list[ParameterAxis]` where a single-axis study is the current shape.
- `ParametricRun.parameter_value` would become `parameter_values: dict[str, float]`.
- A version field in the persisted JSON lets the loader migrate old studies to the new shape on read.
