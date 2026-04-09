# Drivetrain Losses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `drivetrain_efficiency` scalar to `EngineConfig` (default 0.85) that scales crank brake power down to wheel power, surfaces parallel `wheel_*` metrics in the performance dict, and shows all three loss layers (indicated/brake/wheel) on every plot that reports power or torque.

**Architecture:** Add a single field with `__post_init__` validation on `EngineConfig`. Add a tiny `apply_drivetrain_losses` helper to `postprocessing/performance.py` so the math is unit-testable. In `orchestrator._compute_performance`, call the helper after the existing brake-power computation and append `wheel_*` keys to the returned dict; brake/IMEP/BMEP/VE values are not modified. Update `plot_rpm_sweep` and `plot_dashboard` to plot all three power and torque curves; the dashboard's twin-axis power+torque panel is restructured into a nested 2-row gridspec (power top, torque bottom) so six lines are readable. Update `_full_sweep_dashboard.py` to print a `P_whl` column and a peak-wheel-power summary.

**Tech Stack:** Python 3, dataclasses, numpy, matplotlib (Agg backend for headless plotting), pytest.

**Repo notes:** This project has **no git repository**. Skip any commit steps. Verify each task by running its test command and visually inspecting generated plots in `_plot_review/`.

**Spec:** `docs/superpowers/specs/2026-04-08-drivetrain-losses-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `engine_simulator/postprocessing/performance.py` | Modify | Add `apply_drivetrain_losses` helper |
| `engine_simulator/config/engine_config.py` | Modify | Add `drivetrain_efficiency` field + `__post_init__` validator |
| `engine_simulator/simulation/orchestrator.py` | Modify | Compute wheel power, append wheel keys to perf dict, add `P_whl`/`T_whl` columns to sweep print table |
| `engine_simulator/postprocessing/visualization.py` | Modify | Add wheel curve to `plot_rpm_sweep`; restructure `plot_dashboard` power/torque panel into nested gridspec with 3 lines each |
| `_full_sweep_dashboard.py` | Modify | Print `drivetrain_efficiency` in header, add `P_whl` column to per-RPM line, add peak-wheel-power summary |
| `tests/test_drivetrain.py` | Create | Unit tests for helper, validation tests for `EngineConfig`, end-to-end integration test |

---

## Task 1: Helper function `apply_drivetrain_losses`

**Files:**
- Create: `tests/test_drivetrain.py`
- Modify: `engine_simulator/postprocessing/performance.py` (append at EOF, after `theoretical_max_power`)

- [ ] **Step 1.1: Write failing unit tests for the helper**

Create `tests/test_drivetrain.py`:

```python
"""Tests for drivetrain-loss feature: scalar parameter, helper, and integration."""

import pytest

from engine_simulator.postprocessing.performance import apply_drivetrain_losses


class TestApplyDrivetrainLosses:
    def test_typical_efficiency(self):
        # 100 W brake, 0.85 eff -> 85 W wheel
        assert apply_drivetrain_losses(100.0, 0.85) == pytest.approx(85.0)

    def test_perfect_efficiency_passes_through(self):
        assert apply_drivetrain_losses(100.0, 1.0) == pytest.approx(100.0)

    def test_zero_brake_power(self):
        assert apply_drivetrain_losses(0.0, 0.85) == pytest.approx(0.0)

    def test_real_units_sanity(self):
        # 50 kW brake, 0.5 eff -> 25 kW wheel
        assert apply_drivetrain_losses(50_000.0, 0.5) == pytest.approx(25_000.0)
```

- [ ] **Step 1.2: Run the tests to verify they fail with ImportError**

Run from project root:

```bash
pytest tests/test_drivetrain.py -v
```

Expected: ImportError or `AttributeError: module 'engine_simulator.postprocessing.performance' has no attribute 'apply_drivetrain_losses'`. All four tests fail at collection or run time.

- [ ] **Step 1.3: Implement the helper**

Append to `engine_simulator/postprocessing/performance.py` (at the end of the file, after `theoretical_max_power`):

```python


def apply_drivetrain_losses(brake_power_W: float, drivetrain_eff: float) -> float:
    """Return wheel power: brake power scaled by drivetrain efficiency.

    Drivetrain efficiency captures losses between the crankshaft and the
    wheels — clutch slip, gearbox/chain friction, differential, bearings.
    For a chain-drive FSAE car, typical values are 0.82–0.88.
    """
    return brake_power_W * drivetrain_eff
```

- [ ] **Step 1.4: Run the tests to verify they pass**

```bash
pytest tests/test_drivetrain.py -v
```

Expected: 4 passed.

---

## Task 2: `drivetrain_efficiency` field on `EngineConfig` with validation

**Files:**
- Modify: `engine_simulator/config/engine_config.py` (around lines 100-230, the `EngineConfig` dataclass)
- Modify: `tests/test_drivetrain.py` (append validation test class)

- [ ] **Step 2.1: Append failing validation tests to `tests/test_drivetrain.py`**

Append to `tests/test_drivetrain.py`:

```python


class TestDrivetrainEfficiencyValidation:
    def test_default_value_is_0_85(self):
        from engine_simulator.config.engine_config import EngineConfig
        cfg = EngineConfig()
        assert cfg.drivetrain_efficiency == pytest.approx(0.85)

    def test_custom_valid_value(self):
        from engine_simulator.config.engine_config import EngineConfig
        cfg = EngineConfig(drivetrain_efficiency=0.9)
        assert cfg.drivetrain_efficiency == pytest.approx(0.9)

    def test_boundary_one_is_valid(self):
        from engine_simulator.config.engine_config import EngineConfig
        cfg = EngineConfig(drivetrain_efficiency=1.0)
        assert cfg.drivetrain_efficiency == pytest.approx(1.0)

    def test_zero_raises(self):
        from engine_simulator.config.engine_config import EngineConfig
        with pytest.raises(ValueError, match="drivetrain_efficiency"):
            EngineConfig(drivetrain_efficiency=0.0)

    def test_negative_raises(self):
        from engine_simulator.config.engine_config import EngineConfig
        with pytest.raises(ValueError, match="drivetrain_efficiency"):
            EngineConfig(drivetrain_efficiency=-0.1)

    def test_above_one_raises(self):
        from engine_simulator.config.engine_config import EngineConfig
        with pytest.raises(ValueError, match="drivetrain_efficiency"):
            EngineConfig(drivetrain_efficiency=1.5)
```

- [ ] **Step 2.2: Run the validation tests to verify they fail**

```bash
pytest tests/test_drivetrain.py::TestDrivetrainEfficiencyValidation -v
```

Expected: 6 failures. The default test fails with `AttributeError: 'EngineConfig' object has no attribute 'drivetrain_efficiency'`; the custom-value test fails with `TypeError: __init__() got an unexpected keyword argument`; the raise tests fail because no exception is raised.

- [ ] **Step 2.3: Add the field and `__post_init__` to `EngineConfig`**

Open `engine_simulator/config/engine_config.py`. Locate the `EngineConfig` dataclass (starts around line 102 with `class EngineConfig:`). Find the existing `T_ambient: float = 300.0  # K` line near the end (around line 230).

Immediately **after** the `T_ambient` line and **before** the `def _valve_from_dict` module-level function, add:

```python

    # Drivetrain efficiency: fraction of crank brake power that reaches the
    # wheels. Accounts for clutch, gearbox, chain/sprocket, diff, bearings.
    # Typical for a chain-drive FSAE car: 0.82–0.88. SDM26 estimate 0.85
    # (peak brake ~88 hp → ~75 hp at the wheels, matching this year's target).
    drivetrain_efficiency: float = 0.85

    def __post_init__(self) -> None:
        if not (0.0 < self.drivetrain_efficiency <= 1.0):
            raise ValueError(
                f"drivetrain_efficiency must be in (0, 1], got "
                f"{self.drivetrain_efficiency}"
            )
```

Note: the four-space indent on the field and the `def __post_init__` is the same indent as the other fields/methods inside the `EngineConfig` class — they are class-body items.

- [ ] **Step 2.4: Run validation tests to verify they pass**

```bash
pytest tests/test_drivetrain.py::TestDrivetrainEfficiencyValidation -v
```

Expected: 6 passed.

- [ ] **Step 2.5: Run the full drivetrain test file to confirm Task 1 helpers still pass**

```bash
pytest tests/test_drivetrain.py -v
```

Expected: 10 passed (4 from Task 1 + 6 from Task 2).

- [ ] **Step 2.6: Run the existing test suite to confirm nothing else broke**

```bash
pytest tests/ -v
```

Expected: All previously-passing tests still pass. (The new field has a default, so existing constructors are unchanged. `__post_init__` only fails for invalid values, which existing tests will not pass.)

---

## Task 3: Compute `wheel_power` in orchestrator and surface in perf dict

**Files:**
- Modify: `engine_simulator/simulation/orchestrator.py` (imports near top + `_compute_performance` around lines 419-454)
- Modify: `tests/test_drivetrain.py` (append integration test class)

- [ ] **Step 3.1: Append a failing end-to-end integration test**

Append to `tests/test_drivetrain.py`:

```python


class TestDrivetrainIntegration:
    """End-to-end: drivetrain efficiency must scale brake_power into wheel_power
    in the orchestrator's performance dict."""

    def test_wheel_power_equals_brake_times_efficiency(self):
        from engine_simulator.config.engine_config import EngineConfig
        from engine_simulator.simulation.orchestrator import SimulationOrchestrator

        cfg = EngineConfig(drivetrain_efficiency=0.5)
        sim = SimulationOrchestrator(cfg)
        perf = sim.run_single_rpm(8000.0, n_cycles=2, verbose=False)

        assert "wheel_power_hp" in perf
        assert "wheel_power_kW" in perf
        assert "wheel_torque_Nm" in perf
        assert "drivetrain_efficiency" in perf

        assert perf["wheel_power_hp"] == pytest.approx(perf["brake_power_hp"] * 0.5)
        assert perf["wheel_power_kW"] == pytest.approx(perf["brake_power_kW"] * 0.5)
        assert perf["wheel_torque_Nm"] == pytest.approx(perf["brake_torque_Nm"] * 0.5)
        assert perf["drivetrain_efficiency"] == pytest.approx(0.5)

    def test_efficiency_one_means_wheel_equals_brake(self):
        from engine_simulator.config.engine_config import EngineConfig
        from engine_simulator.simulation.orchestrator import SimulationOrchestrator

        cfg = EngineConfig(drivetrain_efficiency=1.0)
        sim = SimulationOrchestrator(cfg)
        perf = sim.run_single_rpm(8000.0, n_cycles=2, verbose=False)

        assert perf["wheel_power_hp"] == pytest.approx(perf["brake_power_hp"])
        assert perf["wheel_torque_Nm"] == pytest.approx(perf["brake_torque_Nm"])

    def test_drivetrain_does_not_back_leak_into_brake(self):
        """Changing drivetrain_efficiency must not change brake_power_hp.
        Brake is upstream of drivetrain in the loss chain."""
        from engine_simulator.config.engine_config import EngineConfig
        from engine_simulator.simulation.orchestrator import SimulationOrchestrator

        cfg_a = EngineConfig(drivetrain_efficiency=0.5)
        cfg_b = EngineConfig(drivetrain_efficiency=0.9)

        sim_a = SimulationOrchestrator(cfg_a)
        sim_b = SimulationOrchestrator(cfg_b)

        perf_a = sim_a.run_single_rpm(8000.0, n_cycles=2, verbose=False)
        perf_b = sim_b.run_single_rpm(8000.0, n_cycles=2, verbose=False)

        # Brake numbers must be identical (drivetrain is downstream)
        assert perf_a["brake_power_hp"] == pytest.approx(perf_b["brake_power_hp"])
        assert perf_a["indicated_power_hp"] == pytest.approx(perf_b["indicated_power_hp"])

        # But wheel numbers must differ proportionally
        assert perf_b["wheel_power_hp"] == pytest.approx(
            perf_a["wheel_power_hp"] * (0.9 / 0.5)
        )
```

- [ ] **Step 3.2: Run the integration tests to verify they fail**

```bash
pytest tests/test_drivetrain.py::TestDrivetrainIntegration -v
```

Expected: 3 failures. They fail with `KeyError: 'wheel_power_hp'` (or `AssertionError: assert "wheel_power_hp" in perf`) because the orchestrator doesn't yet emit the wheel keys.

- [ ] **Step 3.3: Add the import to `orchestrator.py`**

Open `engine_simulator/simulation/orchestrator.py`. Find the import block at the top (around lines 1-27). Add this import (in alphabetical order with the other `engine_simulator.postprocessing.*` imports — there's already `from engine_simulator.postprocessing.results import SimulationResults` near line 25):

```python
from engine_simulator.postprocessing.performance import apply_drivetrain_losses
```

Place it directly above the `from engine_simulator.postprocessing.results import SimulationResults` line.

- [ ] **Step 3.4: Compute wheel power and add to the returned dict**

In the same file, find `_compute_performance` (starts around line 377). Locate the line that computes `brake_torque` (around line 424):

```python
        brake_power = max(indicated_power - friction_power, 0.0)
        brake_torque = brake_power / omega if omega > 0 else 0.0
```

Immediately **after** the `brake_torque = ...` line and **before** the `# IMEP` comment, insert:

```python

        # Drivetrain losses: brake -> wheel power. Single scalar efficiency
        # captures clutch + gearbox + chain + diff + bearing losses (~0.85
        # for a chain-drive FSAE car). See engine_config.drivetrain_efficiency.
        wheel_power = apply_drivetrain_losses(brake_power, cfg.drivetrain_efficiency)
        wheel_torque = wheel_power / omega if omega > 0 else 0.0
```

Then in the `return { ... }` block (around lines 430-454), add four new keys. Find the `"brake_torque_Nm": brake_torque,` line and append immediately after it:

```python
            "wheel_power_kW": wheel_power / 1000.0,
            "wheel_power_hp": wheel_power / 745.7,
            "wheel_torque_Nm": wheel_torque,
            "drivetrain_efficiency": cfg.drivetrain_efficiency,
```

- [ ] **Step 3.5: Run the integration tests to verify they pass**

```bash
pytest tests/test_drivetrain.py::TestDrivetrainIntegration -v
```

Expected: 3 passed. (Each test runs a 2-cycle sim at 8000 RPM, so this will take a few seconds per test.)

- [ ] **Step 3.6: Run the full drivetrain test suite**

```bash
pytest tests/test_drivetrain.py -v
```

Expected: 13 passed (4 helper + 6 validation + 3 integration).

- [ ] **Step 3.7: Run the full test suite to catch any regressions**

```bash
pytest tests/ -v
```

Expected: All passing.

---

## Task 4: Add `P_whl`/`T_whl` columns to `run_rpm_sweep` print table

**Files:**
- Modify: `engine_simulator/simulation/orchestrator.py:489-498`

This is a print-formatting-only change with no test (the surrounding logic is unchanged). Verification is by running a tiny sweep and reading the output.

- [ ] **Step 4.1: Update the header line**

In `engine_simulator/simulation/orchestrator.py`, find the print summary block in `run_rpm_sweep` (around line 489-498). Replace the header line:

```python
            print(f"{'RPM':>6} {'P_ind(hp)':>10} {'P_brk(hp)':>10} {'T_brk(Nm)':>10} {'VE_p(%)':>8} {'VE_a(%)':>8} {'IMEP':>6} {'BMEP':>6} {'pPlen':>6} {'Chkd':>5}")
```

with:

```python
            print(f"{'RPM':>6} {'P_ind(hp)':>10} {'P_brk(hp)':>10} {'P_whl(hp)':>10} {'T_brk(Nm)':>10} {'T_whl(Nm)':>10} {'VE_p(%)':>8} {'VE_a(%)':>8} {'IMEP':>6} {'BMEP':>6} {'pPlen':>6} {'Chkd':>5}")
```

- [ ] **Step 4.2: Update the per-row print**

In the same block, replace:

```python
            for r in sweep_results:
                print(
                    f"{r['rpm']:6.0f} {r['indicated_power_hp']:10.1f} "
                    f"{r['brake_power_hp']:10.1f} {r['brake_torque_Nm']:10.1f} "
                    f"{r['volumetric_efficiency_plenum']*100:8.1f} {r['volumetric_efficiency_atm']*100:8.1f} "
                    f"{r['imep_bar']:6.2f} {r['bmep_bar']:6.2f} {r['plenum_pressure_bar']:6.3f} "
                    f"{'Yes' if r['restrictor_choked'] else 'No':>5}"
                )
```

with:

```python
            for r in sweep_results:
                print(
                    f"{r['rpm']:6.0f} {r['indicated_power_hp']:10.1f} "
                    f"{r['brake_power_hp']:10.1f} {r['wheel_power_hp']:10.1f} "
                    f"{r['brake_torque_Nm']:10.1f} {r['wheel_torque_Nm']:10.1f} "
                    f"{r['volumetric_efficiency_plenum']*100:8.1f} {r['volumetric_efficiency_atm']*100:8.1f} "
                    f"{r['imep_bar']:6.2f} {r['bmep_bar']:6.2f} {r['plenum_pressure_bar']:6.3f} "
                    f"{'Yes' if r['restrictor_choked'] else 'No':>5}"
                )
```

- [ ] **Step 4.3: Confirm tests still pass**

```bash
pytest tests/ -v
```

Expected: All passing (no logic changed).

---

## Task 5: Add wheel curves to `plot_rpm_sweep`

**Files:**
- Modify: `engine_simulator/postprocessing/visualization.py:133-178`

- [ ] **Step 5.1: Update `plot_rpm_sweep` to read wheel data and plot a third curve**

Open `engine_simulator/postprocessing/visualization.py`. Find `plot_rpm_sweep` (starts around line 133). Replace the entire function body (from the `"""docstring"""` through `plt.show()`) with the version below. The structural change: add `p_whl` / `t_whl` reads with defensive `.get()`, plot a third dashed-blue triangle line on each of the power and torque subplots.

Replace (lines 133–178):

```python
def plot_rpm_sweep(sweep_results: list[dict], save_path: Optional[str] = None):
    """Plot power, torque, and VE vs RPM from sweep results."""
    _check_matplotlib()

    rpm = [r["rpm"] for r in sweep_results]
    p_ind = [r["indicated_power_hp"] for r in sweep_results]
    p_brk = [r.get("brake_power_hp", r["indicated_power_hp"]) for r in sweep_results]
    t_ind = [r["indicated_torque_Nm"] for r in sweep_results]
    t_brk = [r.get("brake_torque_Nm", r["indicated_torque_Nm"]) for r in sweep_results]
    ve_plen = [r["volumetric_efficiency_plenum"] * 100 for r in sweep_results]
    ve_atm = [r["volumetric_efficiency_atm"] * 100 for r in sweep_results]

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    axes[0].plot(rpm, p_ind, "r-o", markersize=4, linewidth=1.5, label="Indicated")
    axes[0].plot(rpm, p_brk, "b-s", markersize=4, linewidth=1.5, label="Brake (estimated)")
    axes[0].set_ylabel("Power (hp)")
    axes[0].set_title("Engine Performance vs RPM (FSAE Restricted CBR600RR)")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="best")

    axes[1].plot(rpm, t_ind, "r-o", markersize=4, linewidth=1.5, label="Indicated")
    axes[1].plot(rpm, t_brk, "b-s", markersize=4, linewidth=1.5, label="Brake")
    axes[1].set_ylabel("Torque (Nm)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="best")

    axes[2].plot(rpm, ve_plen, "g-o", markersize=4, linewidth=1.5, label="VE (plenum ref)")
    axes[2].plot(rpm, ve_atm, "m-s", markersize=4, linewidth=1.5, label="VE (atmospheric ref)")
    axes[2].set_ylabel("Volumetric Efficiency (%)")
    axes[2].set_xlabel("Engine Speed (RPM)")
    axes[2].grid(True, alpha=0.3)
    axes[2].axhline(y=100, color="k", linestyle="--", alpha=0.3)
    axes[2].legend(loc="best")

    # Mark restrictor choking
    choked_rpm = [r["rpm"] for r in sweep_results if r["restrictor_choked"]]
    if choked_rpm:
        for ax in axes:
            ax.axvspan(min(choked_rpm), max(choked_rpm), alpha=0.1, color="red",
                       label="Restrictor choked" if ax == axes[0] else None)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
```

with:

```python
def plot_rpm_sweep(sweep_results: list[dict], save_path: Optional[str] = None):
    """Plot power, torque, and VE vs RPM from sweep results.

    Shows three loss layers on power and torque: indicated (cylinder PV
    work), brake (after engine FMEP), and wheel (after drivetrain
    efficiency). Wheel uses dashed blue so the eye groups it with brake
    as the same loss family.
    """
    _check_matplotlib()

    rpm = [r["rpm"] for r in sweep_results]
    p_ind = [r["indicated_power_hp"] for r in sweep_results]
    p_brk = [r.get("brake_power_hp", r["indicated_power_hp"]) for r in sweep_results]
    p_whl = [r.get("wheel_power_hp", r.get("brake_power_hp", r["indicated_power_hp"]))
             for r in sweep_results]
    t_ind = [r["indicated_torque_Nm"] for r in sweep_results]
    t_brk = [r.get("brake_torque_Nm", r["indicated_torque_Nm"]) for r in sweep_results]
    t_whl = [r.get("wheel_torque_Nm", r.get("brake_torque_Nm", r["indicated_torque_Nm"]))
             for r in sweep_results]
    ve_plen = [r["volumetric_efficiency_plenum"] * 100 for r in sweep_results]
    ve_atm = [r["volumetric_efficiency_atm"] * 100 for r in sweep_results]

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    axes[0].plot(rpm, p_ind, "r-o", markersize=4, linewidth=1.5, label="Indicated")
    axes[0].plot(rpm, p_brk, "b-s", markersize=4, linewidth=1.5, label="Brake")
    axes[0].plot(rpm, p_whl, "b--^", markersize=4, linewidth=1.5, label="Wheel")
    axes[0].set_ylabel("Power (hp)")
    axes[0].set_title("Engine Performance vs RPM (FSAE Restricted CBR600RR)")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="best")

    axes[1].plot(rpm, t_ind, "r-o", markersize=4, linewidth=1.5, label="Indicated")
    axes[1].plot(rpm, t_brk, "b-s", markersize=4, linewidth=1.5, label="Brake")
    axes[1].plot(rpm, t_whl, "b--^", markersize=4, linewidth=1.5, label="Wheel")
    axes[1].set_ylabel("Torque (Nm)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="best")

    axes[2].plot(rpm, ve_plen, "g-o", markersize=4, linewidth=1.5, label="VE (plenum ref)")
    axes[2].plot(rpm, ve_atm, "m-s", markersize=4, linewidth=1.5, label="VE (atmospheric ref)")
    axes[2].set_ylabel("Volumetric Efficiency (%)")
    axes[2].set_xlabel("Engine Speed (RPM)")
    axes[2].grid(True, alpha=0.3)
    axes[2].axhline(y=100, color="k", linestyle="--", alpha=0.3)
    axes[2].legend(loc="best")

    # Mark restrictor choking
    choked_rpm = [r["rpm"] for r in sweep_results if r["restrictor_choked"]]
    if choked_rpm:
        for ax in axes:
            ax.axvspan(min(choked_rpm), max(choked_rpm), alpha=0.1, color="red",
                       label="Restrictor choked" if ax == axes[0] else None)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
```

- [ ] **Step 5.2: Smoke-test the function with a synthetic sweep**

Run this one-liner from the project root to confirm the function imports and renders without crashing on synthetic data:

```bash
python -c "
import os; os.environ['MPLBACKEND'] = 'Agg'
import matplotlib; matplotlib.use('Agg')
from engine_simulator.postprocessing.visualization import plot_rpm_sweep
fake = [
    {'rpm': r, 'indicated_power_hp': 90 + r/1000, 'brake_power_hp': 80 + r/1000,
     'wheel_power_hp': 68 + r/1000, 'indicated_torque_Nm': 70, 'brake_torque_Nm': 62,
     'wheel_torque_Nm': 53, 'volumetric_efficiency_plenum': 1.1,
     'volumetric_efficiency_atm': 0.95, 'restrictor_choked': True}
    for r in range(6000, 13001, 1000)
]
plot_rpm_sweep(fake, save_path='/tmp/_drivetrain_smoke_sweep.png')
print('OK: /tmp/_drivetrain_smoke_sweep.png')
"
```

Expected: prints `OK: /tmp/_drivetrain_smoke_sweep.png` with no traceback. Open the PNG and confirm three lines on each of the power and torque subplots, with wheel below brake below indicated.

---

## Task 6: Restructure `plot_dashboard` power/torque panel into nested gridspec

**Files:**
- Modify: `engine_simulator/postprocessing/visualization.py:222-329`

This is the largest visual change. The current `plot_dashboard` puts a single twin-axis power+torque chart at `gs[0, 0:2]` (one power line, one torque line). We split that cell into a nested 2-row gridspec — power on top with three lines, torque on bottom with three lines, sharing x-axis.

- [ ] **Step 6.1: Replace the power/torque panel block in `plot_dashboard`**

Open `engine_simulator/postprocessing/visualization.py`. Find `plot_dashboard` (starts around line 222). Locate the block beginning with the comment `# 1. Power & Torque vs RPM` (around line 230) and ending immediately before `# 2. Volumetric Efficiency` (around line 244).

Replace the existing block (these lines):

```python
    # 1. Power & Torque vs RPM
    ax1 = fig.add_subplot(gs[0, 0:2])
    rpm = [r["rpm"] for r in sweep_results]
    power = [r["indicated_power_hp"] for r in sweep_results]
    torque = [r["indicated_torque_Nm"] for r in sweep_results]
    ax1.plot(rpm, power, "r-o", markersize=3, label="Power (hp)")
    ax1_t = ax1.twinx()
    ax1_t.plot(rpm, torque, "b-s", markersize=3, label="Torque (Nm)")
    ax1.set_xlabel("RPM")
    ax1.set_ylabel("Power (hp)", color="r")
    ax1_t.set_ylabel("Torque (Nm)", color="b")
    ax1.set_title("Power & Torque vs RPM")
    ax1.grid(True, alpha=0.3)
```

with:

```python
    # 1. Power & Torque vs RPM — nested 2-row gridspec inside the gs[0, 0:2]
    # cell so we can show all three loss layers (indicated / brake / wheel)
    # without 6 lines on a single twin-axis plot.
    rpm = [r["rpm"] for r in sweep_results]
    p_ind = [r["indicated_power_hp"] for r in sweep_results]
    p_brk = [r.get("brake_power_hp", r["indicated_power_hp"]) for r in sweep_results]
    p_whl = [r.get("wheel_power_hp", r.get("brake_power_hp", r["indicated_power_hp"]))
             for r in sweep_results]
    t_ind = [r["indicated_torque_Nm"] for r in sweep_results]
    t_brk = [r.get("brake_torque_Nm", r["indicated_torque_Nm"]) for r in sweep_results]
    t_whl = [r.get("wheel_torque_Nm", r.get("brake_torque_Nm", r["indicated_torque_Nm"]))
             for r in sweep_results]

    inner_pt = gs[0, 0:2].subgridspec(2, 1, hspace=0.15)
    ax1p = fig.add_subplot(inner_pt[0, 0])
    ax1t = fig.add_subplot(inner_pt[1, 0], sharex=ax1p)

    ax1p.plot(rpm, p_ind, "r-o", markersize=3, linewidth=1.2, label="Indicated")
    ax1p.plot(rpm, p_brk, "b-s", markersize=3, linewidth=1.2, label="Brake")
    ax1p.plot(rpm, p_whl, "b--^", markersize=3, linewidth=1.2, label="Wheel")
    ax1p.set_ylabel("Power (hp)")
    ax1p.set_title("Power & Torque vs RPM")
    ax1p.grid(True, alpha=0.3)
    ax1p.legend(loc="best", fontsize=8)
    plt.setp(ax1p.get_xticklabels(), visible=False)

    ax1t.plot(rpm, t_ind, "r-o", markersize=3, linewidth=1.2, label="Indicated")
    ax1t.plot(rpm, t_brk, "b-s", markersize=3, linewidth=1.2, label="Brake")
    ax1t.plot(rpm, t_whl, "b--^", markersize=3, linewidth=1.2, label="Wheel")
    ax1t.set_xlabel("RPM")
    ax1t.set_ylabel("Torque (Nm)")
    ax1t.grid(True, alpha=0.3)
    ax1t.legend(loc="best", fontsize=8)
```

- [ ] **Step 6.2: Smoke-test the dashboard plot with synthetic data**

Run from the project root:

```bash
python -c "
import os; os.environ['MPLBACKEND'] = 'Agg'
import matplotlib; matplotlib.use('Agg')
from engine_simulator.postprocessing.visualization import plot_dashboard
from engine_simulator.postprocessing.results import SimulationResults
fake_sweep = [
    {'rpm': r, 'indicated_power_hp': 90 + r/1000, 'brake_power_hp': 80 + r/1000,
     'wheel_power_hp': 68 + r/1000, 'indicated_torque_Nm': 70, 'brake_torque_Nm': 62,
     'wheel_torque_Nm': 53, 'volumetric_efficiency_plenum': 1.1,
     'volumetric_efficiency_atm': 0.95, 'restrictor_choked': True,
     'imep_bar': 12.0}
    for r in range(6000, 13001, 1000)
]
results = SimulationResults()
plot_dashboard(results, fake_sweep, geometry=None, save_path='/tmp/_drivetrain_smoke_dash.png')
print('OK: /tmp/_drivetrain_smoke_dash.png')
"
```

Expected: prints `OK: /tmp/_drivetrain_smoke_dash.png` with no traceback. Open the PNG. Confirm:
- Top-left now has TWO stacked sub-panels (power on top, torque on bottom)
- Each sub-panel has three lines: red solid (Indicated), blue solid (Brake), blue dashed (Wheel)
- The layout for the rest of the dashboard (VE top-right, cylinder pressure middle, P-V, plenum, restrictor, IMEP) is unchanged
- Wheel curve is below brake curve, brake below indicated

---

## Task 7: Update `_full_sweep_dashboard.py` driver

**Files:**
- Modify: `_full_sweep_dashboard.py:54-149`

- [ ] **Step 7.1: Add `drivetrain_efficiency` to the printed config header**

Open `_full_sweep_dashboard.py`. Find the `print(f"Final config: ...")` block in `main()` (around lines 56-63). Replace:

```python
    cfg = EngineConfig()
    print(
        f"Final config:\n"
        f"  Cd_restrictor = {cfg.restrictor.discharge_coefficient}\n"
        f"  Intake valve max Cd = {max(p[1] for p in cfg.intake_valve.cd_table):.3f}\n"
        f"  Runner: D = {cfg.intake_pipes[0].diameter*1000:.0f} mm constant\n"
        f"  Plenum vol = {cfg.plenum.volume*1e3:.1f} L\n"
        f"  artificial_viscosity = {cfg.simulation.artificial_viscosity}\n"
    )
```

with:

```python
    cfg = EngineConfig()
    print(
        f"Final config:\n"
        f"  Cd_restrictor = {cfg.restrictor.discharge_coefficient}\n"
        f"  Intake valve max Cd = {max(p[1] for p in cfg.intake_valve.cd_table):.3f}\n"
        f"  Runner: D = {cfg.intake_pipes[0].diameter*1000:.0f} mm constant\n"
        f"  Plenum vol = {cfg.plenum.volume*1e3:.1f} L\n"
        f"  artificial_viscosity = {cfg.simulation.artificial_viscosity}\n"
        f"  drivetrain_efficiency = {cfg.drivetrain_efficiency}\n"
    )
```

- [ ] **Step 7.2: Update the per-RPM print line to include `P_whl` / `T_whl`**

In the same file, find the per-RPM `print(...)` inside the sweep loop (around lines 114-125). Replace:

```python
        print(
            f"  {rpm:>5d}  P_ind={perf['indicated_power_hp']:5.1f}  "
            f"P_brk={perf['brake_power_hp']:5.1f}  "
            f"T_brk={perf['brake_torque_Nm']:5.1f}  "
            f"VE_atm={perf['volumetric_efficiency_atm']*100:5.1f}%  "
            f"IMEP={perf['imep_bar']:5.2f}  "
            f"FMEP={perf['fmep_bar']:.2f}  "
            f"pPlen={perf['plenum_pressure_bar']:.3f}  "
            f"chk={'Y' if perf['restrictor_choked'] else 'N'}  "
            f"({elapsed:.0f}s)",
            flush=True,
        )
```

with:

```python
        print(
            f"  {rpm:>5d}  P_ind={perf['indicated_power_hp']:5.1f}  "
            f"P_brk={perf['brake_power_hp']:5.1f}  "
            f"P_whl={perf['wheel_power_hp']:5.1f}  "
            f"T_brk={perf['brake_torque_Nm']:5.1f}  "
            f"T_whl={perf['wheel_torque_Nm']:5.1f}  "
            f"VE_atm={perf['volumetric_efficiency_atm']*100:5.1f}%  "
            f"IMEP={perf['imep_bar']:5.2f}  "
            f"FMEP={perf['fmep_bar']:.2f}  "
            f"pPlen={perf['plenum_pressure_bar']:.3f}  "
            f"chk={'Y' if perf['restrictor_choked'] else 'N'}  "
            f"({elapsed:.0f}s)",
            flush=True,
        )
```

- [ ] **Step 7.3: Add a peak-wheel-power summary line**

In the same file, find the existing peak summary block (around lines 127-137). Replace:

```python
    # Sweep summary
    peak_p = max(sweep_results, key=lambda r: r["brake_power_hp"])
    peak_t = max(sweep_results, key=lambda r: r["brake_torque_Nm"])
    print(
        f"\nPeak brake power: {peak_p['brake_power_hp']:.1f} hp at {peak_p['rpm']:.0f} RPM"
        f"  (spec 74 hp at 9000)"
    )
    print(
        f"Peak brake torque: {peak_t['brake_torque_Nm']:.1f} Nm at {peak_t['rpm']:.0f} RPM"
        f"  (spec 50 Nm at 8000)"
    )
```

with:

```python
    # Sweep summary
    peak_p = max(sweep_results, key=lambda r: r["brake_power_hp"])
    peak_w = max(sweep_results, key=lambda r: r["wheel_power_hp"])
    peak_t = max(sweep_results, key=lambda r: r["brake_torque_Nm"])
    print(
        f"\nPeak brake power: {peak_p['brake_power_hp']:.1f} hp at {peak_p['rpm']:.0f} RPM"
        f"  (spec 74 hp at 9000)"
    )
    print(
        f"Peak wheel power: {peak_w['wheel_power_hp']:.1f} hp at {peak_w['rpm']:.0f} RPM"
        f"  (target 75 hp)"
    )
    print(
        f"Peak brake torque: {peak_t['brake_torque_Nm']:.1f} Nm at {peak_t['rpm']:.0f} RPM"
        f"  (spec 50 Nm at 8000)"
    )
```

---

## Task 8: Final acceptance — full sweep + plot regeneration

This task verifies all six acceptance criteria from the spec end-to-end. No code changes — just runs and inspections.

- [ ] **Step 8.1: Run the entire test suite**

```bash
pytest tests/ -v
```

Expected: All passing, including the 13 new tests in `tests/test_drivetrain.py`. (Acceptance criteria 1, 2, 6.)

- [ ] **Step 8.2: Run the full sweep dashboard**

```bash
python _full_sweep_dashboard.py
```

Expected: Script completes without errors. Look at the printed output:
- Header line includes `drivetrain_efficiency = 0.85`
- Each per-RPM line shows both `P_brk=` and `P_whl=` columns
- The sweep summary at the bottom prints both `Peak brake power:` and `Peak wheel power:` lines
- Peak wheel power is **≈ 75 hp (within ~1 hp)**. (Acceptance criterion 3.)

- [ ] **Step 8.3: Inspect `_plot_review/07_rpm_sweep.png`**

Open `_plot_review/07_rpm_sweep.png` and confirm the power and torque subplots each show **three** curves (Indicated red, Brake blue solid, Wheel blue dashed). The wheel curve must sit below the brake curve everywhere by exactly the 0.85 factor. (Acceptance criterion 4.)

- [ ] **Step 8.4: Inspect `_plot_review/08_dashboard.png`**

Open `_plot_review/08_dashboard.png` and confirm:
- The top-left area now has **two stacked sub-panels** (power on top, torque on bottom)
- Each sub-panel has three lines (Indicated / Brake / Wheel)
- Rest of the dashboard layout is unchanged (VE top-right, cylinder pressure middle, etc.)
- (Acceptance criterion 5.)

- [ ] **Step 8.5: Sanity-check the comment in `engine_config.py`**

Open `engine_simulator/config/engine_config.py:119-125`. The pre-existing comment claims the 0.78 in-engine Cd factor *"lands the simulator's peak power within ~5 hp of the SDM26 spec-sheet 55 kW"*. This was identified as stale during reconstruction (actual peak brake is ~88 hp, not ~74). Update the wrapped sentence so it's no longer misleading.

Replace the existing two-line comment:

```python
    # effective Cd is typically 70–85 % of the static-bench Cd. 0.78 lands
    # the simulator's peak power within ~5 hp of the SDM26 spec-sheet 55 kW.
```

with:

```python
    # effective Cd is typically 70–85 % of the static-bench Cd. 0.78 lands
    # peak BRAKE power around 88 hp; with the drivetrain_efficiency=0.85
    # layer this becomes ~75 hp at the wheels, matching the SDM26 team's
    # chassis-dyno target for the season.
```

(This is a comment-only clarification, not a behavior change.)

- [ ] **Step 8.6: Final test run after the comment edit**

```bash
pytest tests/ -v
```

Expected: All passing.

---

## Summary

Files modified: 5 source files + 1 driver script + 1 new test file. New test count: 13. The drivetrain knob is a single line at the bottom of `EngineConfig`; everything else is computation downstream of `brake_power` and additive plotting.
