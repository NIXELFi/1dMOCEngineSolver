# Drivetrain Losses Design

**Date:** 2026-04-08
**Status:** Approved (pending user review of this doc)

## Goal

Add a tunable scalar **`drivetrain_efficiency`** parameter to `EngineConfig` that
introduces a third loss layer between crank brake power and the wheels. This
gives the user a single, easily-editable knob in `engine_config.py` whose
default value (0.85) lands the simulator's peak power at the SDM26 team's
estimated 75 hp at the wheels for this season.

The parameter must:

- Be a single scalar fraction (0 < value ≤ 1.0)
- Default to **0.85** (typical for chain-drive FSAE drivetrains; brings the
  current ~88 hp peak brake to ~75 hp at the wheels)
- Apply uniformly across all RPM points (no RPM table — that's a future
  extension if needed)
- Surface a parallel set of `wheel_*` metrics in the performance dict without
  altering existing `indicated_*` or `brake_*` numbers
- Show all three loss layers (indicated / brake / wheel) on every plot that
  reports power or torque

## Background

The current loss chain in `orchestrator.py:_compute_performance` is:

1. **Indicated power** = ∫p dV × RPM/120 (cylinder PV work)
2. **Brake power** = indicated − engine friction, where friction comes from
   a Heywood-style FMEP correlation `0.97 + 0.15·Sp + 0.005·Sp²` bar.

There is no representation of drivetrain losses (clutch, gearbox, chain,
final drive). For an FSAE chassis dyno comparison, what matters is wheel
power, which sits ~12–18 % below crank brake power on a chain-drive bike-engine
car. The current sim therefore over-reports vs. expected dyno results by
exactly that margin.

The current "Power & Torque vs RPM" panel in `plot_dashboard`
(`visualization.py:233-237`) plots **indicated** power as the headline curve,
not brake. This is a pre-existing inconsistency with `plot_rpm_sweep`, which
plots both indicated and brake. With the introduction of wheel power, both
plots will be unified to show all three layers.

## Architecture / Component Changes

### 1. `engine_simulator/config/engine_config.py`

Add a single field directly to `EngineConfig` (no new dataclass — one
scalar does not warrant a wrapper):

```python
# Drivetrain efficiency: fraction of crank brake power that reaches the
# wheels. Accounts for clutch, gearbox, chain/sprocket, diff, bearings.
# Typical for a chain-drive FSAE car: 0.82–0.88. SDM26 estimate 0.85
# (peak brake ~88 hp → ~75 hp at the wheels, matching this year's target).
drivetrain_efficiency: float = 0.85
```

Add a `__post_init__` to `EngineConfig` validating the range:

```python
def __post_init__(self) -> None:
    if not (0.0 < self.drivetrain_efficiency <= 1.0):
        raise ValueError(
            f"drivetrain_efficiency must be in (0, 1], got "
            f"{self.drivetrain_efficiency}"
        )
```

`load_config` (the JSON loader at `engine_config.py:242`) needs no schema
change because the field has a default; it can be optionally loaded with
`data.get("drivetrain_efficiency", 0.85)` in the `EngineConfig(...)` call.

### 2. `engine_simulator/postprocessing/performance.py`

Add a small helper so the math is testable in isolation:

```python
def apply_drivetrain_losses(brake_power_W: float, drivetrain_eff: float) -> float:
    """Return wheel power: brake power scaled by drivetrain efficiency.

    Drivetrain efficiency captures losses between the crankshaft and the
    wheels — clutch slip, gearbox/chain friction, differential, bearings.
    For a chain-drive FSAE car, typical values are 0.82–0.88.
    """
    return brake_power_W * drivetrain_eff
```

### 3. `engine_simulator/simulation/orchestrator.py`

In `_compute_performance` (currently around line 423, immediately after
`brake_power` is computed), add:

```python
from engine_simulator.postprocessing.performance import apply_drivetrain_losses

# ... existing brake_power computation ...
wheel_power = apply_drivetrain_losses(brake_power, cfg.drivetrain_efficiency)
wheel_torque = wheel_power / omega if omega > 0 else 0.0
```

Append to the returned dict:

```python
"wheel_power_kW": wheel_power / 1000.0,
"wheel_power_hp": wheel_power / 745.7,
"wheel_torque_Nm": wheel_torque,
"drivetrain_efficiency": cfg.drivetrain_efficiency,
```

The existing `indicated_*`, `brake_*`, `imep_bar`, `bmep_bar`, `fmep_bar`,
`volumetric_efficiency_*`, and restrictor fields are **not modified**.
IMEP/BMEP/VE are physical quantities that do not change because of the
drivetrain.

The `print` summary table at `orchestrator.py:489-498` (in `run_rpm_sweep`)
gains a `P_whl` column:

```
RPM    P_ind(hp)  P_brk(hp)  P_whl(hp)  T_brk(Nm)  T_whl(Nm)  ...
```

### 4. `engine_simulator/postprocessing/visualization.py`

#### `plot_rpm_sweep` (around line 133)

Add a third line to both the power and torque subplots:

- Indicated → solid red, circle marker (existing)
- Brake → solid blue, square marker (existing)
- **Wheel → dashed blue, triangle marker (new)** — same blue as brake so
  the eye reads brake/wheel as the same loss family

Read with defensive `.get()` so old result dicts (without `wheel_*`) still
fall back to brake values:

```python
p_whl = [r.get("wheel_power_hp", r.get("brake_power_hp", r["indicated_power_hp"]))
         for r in sweep_results]
t_whl = [r.get("wheel_torque_Nm", r.get("brake_torque_Nm", r["indicated_torque_Nm"]))
         for r in sweep_results]
```

Legend reads: `Indicated / Brake / Wheel`.

#### `plot_dashboard` (around line 222)

The current "Power & Torque vs RPM" panel uses a **twin axis** with one
power curve and one torque curve. Going to 3+3 lines on a twin axis would
be unreadable, so this panel is restructured.

**Restructured panel:** replace the current single twin-axis cell at
`gs[0, 0:2]` with a **nested 2-row gridspec** inside that same cell —
power on top, torque on bottom, each as its own subplot with three lines.
The rest of the dashboard layout (VE, cylinder pressure, P-V, plenum,
restrictor, IMEP) is unchanged.

```python
# Replace existing ax1/ax1_t block (~lines 231-242):
inner = gs[0, 0:2].subgridspec(2, 1, hspace=0.15)
ax1p = fig.add_subplot(inner[0, 0])
ax1t = fig.add_subplot(inner[1, 0], sharex=ax1p)

ax1p.plot(rpm, p_ind, "r-o", markersize=3, label="Indicated")
ax1p.plot(rpm, p_brk, "b-s", markersize=3, label="Brake")
ax1p.plot(rpm, p_whl, "b--^", markersize=3, label="Wheel")
ax1p.set_ylabel("Power (hp)")
ax1p.set_title("Power & Torque vs RPM")
ax1p.grid(True, alpha=0.3)
ax1p.legend(loc="best", fontsize=8)
plt.setp(ax1p.get_xticklabels(), visible=False)

ax1t.plot(rpm, t_ind, "r-o", markersize=3, label="Indicated")
ax1t.plot(rpm, t_brk, "b-s", markersize=3, label="Brake")
ax1t.plot(rpm, t_whl, "b--^", markersize=3, label="Wheel")
ax1t.set_xlabel("RPM")
ax1t.set_ylabel("Torque (Nm)")
ax1t.grid(True, alpha=0.3)
ax1t.legend(loc="best", fontsize=8)
```

This also fixes the pre-existing inconsistency where the dashboard headline
curve was indicated rather than brake — both layers are now visible
simultaneously, making it obvious how much each loss tier costs.

### 5. `_full_sweep_dashboard.py` (driver script)

The printed per-RPM line at lines ~114-125 is updated to include wheel:

```
{rpm:>5d}  P_ind=...  P_brk=...  P_whl=...  T_brk=...  T_whl=...  ...
```

The peak-summary printout at lines ~128-137 adds a wheel-power summary:

```python
peak_w = max(sweep_results, key=lambda r: r["wheel_power_hp"])
print(
    f"Peak wheel power: {peak_w['wheel_power_hp']:.1f} hp at "
    f"{peak_w['rpm']:.0f} RPM  (target 75 hp)"
)
```

The "Final config" header at lines ~57-63 adds:

```python
f"  drivetrain_efficiency = {cfg.drivetrain_efficiency}\n"
```

### 6. Tests

New file `tests/test_drivetrain.py`:

- **Unit math** — `apply_drivetrain_losses`:
  - `(100.0, 0.85) → 85.0`
  - `(100.0, 1.0) → 100.0`
  - `(0.0, 0.85) → 0.0`
  - `(50000.0, 0.5) → 25000.0` (real-units sanity)
- **Validation** — `EngineConfig.__post_init__`:
  - `EngineConfig(drivetrain_efficiency=0.0)` raises `ValueError`
  - `EngineConfig(drivetrain_efficiency=-0.1)` raises `ValueError`
  - `EngineConfig(drivetrain_efficiency=1.5)` raises `ValueError`
  - `EngineConfig(drivetrain_efficiency=1.0)` is valid (boundary)
  - `EngineConfig(drivetrain_efficiency=0.85)` is valid (default)
- **End-to-end integration** — short low-cycle run:
  - Build `EngineConfig(drivetrain_efficiency=0.5)`
  - Run `SimulationOrchestrator(cfg).run_single_rpm(8000.0, n_cycles=2,
    verbose=False)`
  - Assert `perf["wheel_power_hp"] == pytest.approx(perf["brake_power_hp"] * 0.5)`
  - Assert `perf["wheel_torque_Nm"] == pytest.approx(perf["brake_torque_Nm"] * 0.5)`
  - Assert `perf["drivetrain_efficiency"] == 0.5`
  - Assert existing `brake_power_hp` is unchanged compared to a baseline
    `EngineConfig()` (i.e. drivetrain knob does not back-leak into brake)

Existing tests (`test_boundaries.py`, `test_cylinder.py`, `test_moc.py`)
need no changes — they do not exercise the performance dict's brake fields
and the new `wheel_*` fields are additive.

## Data Flow

```
cylinder PV work
      │
      ▼
indicated_power  ──────► indicated_power_hp / indicated_torque_Nm
      │
      │  − FMEP·V_d·N/120  (engine internal friction, existing)
      ▼
brake_power      ──────► brake_power_hp / brake_torque_Nm / bmep_bar
      │
      │  × drivetrain_efficiency  (NEW)
      ▼
wheel_power      ──────► wheel_power_hp / wheel_torque_Nm
```

## Error Handling

- Out-of-range `drivetrain_efficiency` → `ValueError` at config construction
  time (fail fast, not at first compute).
- Old result dicts without `wheel_*` keys → plotting code uses `.get()` with
  brake fallback so legacy `_plot_review/*.png` regenerations still work
  with stale pickled results.
- No runtime fallback inside `_compute_performance` — if the config is
  valid, the wheel keys are always present.

## Out of Scope

- **RPM-dependent drivetrain table.** The scalar → list-of-(rpm, eff) change
  is one-line if it's ever needed. Not needed today.
- **Auto-calibration mode** ("set target peak hp = 75, sim back-solves the
  factor"). Future `_calibrate_drivetrain.py` script if wanted.
- **Wheel torque referenced to wheel rpm.** No gearbox in the sim;
  `wheel_torque_Nm` here is "brake torque scaled by efficiency at engine
  rpm", which is the right number for dyno comparison.
- **Updating `_issue4_runner_compare.py`, `_recapture_plots.py`, etc.**
  Those are session-debug scripts; they read the dict by name and will
  pick up `wheel_*` automatically if/when modified.
- **Schema enforcement in `load_config`.** The JSON loader uses defaults,
  so a missing field is fine; an out-of-range field will be caught by
  `__post_init__`.

## Acceptance Criteria

1. `cfg = EngineConfig(); cfg.drivetrain_efficiency == 0.85`.
2. `EngineConfig(drivetrain_efficiency=2.0)` raises `ValueError`.
3. After re-running `_full_sweep_dashboard.py`, the printed summary shows
   a `peak wheel power` line ≈ 75 hp (within ~1 hp).
4. `_plot_review/07_rpm_sweep.png` shows three power curves and three
   torque curves; wheel curve is below brake curve by exactly the
   efficiency factor.
5. `_plot_review/08_dashboard.png` shows the restructured power/torque panel
   with stacked power-top / torque-bottom subplots, each with all three
   curves.
6. All existing tests still pass; new `tests/test_drivetrain.py` passes.
