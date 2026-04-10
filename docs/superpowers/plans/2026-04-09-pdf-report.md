# PDF Report Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a server-side PDF report generator (WeasyPrint + matplotlib) to the engine simulator GUI, triggered by a "Download Report" button in the TopBar.

**Architecture:** A new backend endpoint `GET /api/sweeps/{sweep_id}/report` loads the sweep JSON, generates matplotlib SVG charts, renders a Jinja2 HTML/CSS template, converts to PDF via WeasyPrint, and returns it as a file download. The frontend adds a single button + API call.

**Tech Stack:** Python (WeasyPrint, matplotlib, Jinja2), TypeScript/React (existing stack), Tailwind CSS (existing)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `requirements.txt` | Modify | Add `weasyprint` dependency |
| `engine_simulator/gui/persistence.py` | Modify | Persist convergence data (delta_history, p_ivc_history) in sweep JSON |
| `engine_simulator/gui/report_charts.py` | Create | Matplotlib chart functions, each returns SVG string |
| `engine_simulator/gui/report_template.html` | Create | Jinja2 HTML/CSS template for the PDF |
| `engine_simulator/gui/report.py` | Create | Orchestrates chart generation + template rendering + WeasyPrint PDF |
| `engine_simulator/gui/routes_api.py` | Modify | Add `GET /api/sweeps/{sweep_id}/report` endpoint |
| `gui-frontend/src/api/client.ts` | Modify | Add `downloadReport(sweepId)` function |
| `gui-frontend/src/components/TopBar.tsx` | Modify | Add "Download Report" button |
| `tests/test_report_charts.py` | Create | Tests for chart rendering functions |
| `tests/test_report.py` | Create | Tests for report generation |
| `tests/test_report_endpoint.py` | Create | Tests for the API endpoint |
| `tests/test_persistence_convergence.py` | Create | Tests for convergence data round-trip |

---

### Task 1: Add WeasyPrint Dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add weasyprint to requirements.txt**

```
weasyprint>=60
```

Add this line after the existing `websockets>=12` line in `requirements.txt`.

- [ ] **Step 2: Install the dependency**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/pip install weasyprint>=60`

WeasyPrint requires system libraries (Pango, Cairo, GDK-PixBuf). On macOS:
```bash
brew install pango
```

If already installed, `pip install` should succeed. Verify:
```bash
.venv/bin/python -c "from weasyprint import HTML; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add weasyprint for PDF report generation"
```

---

### Task 2: Persist Convergence Data in Sweep JSON

**Files:**
- Modify: `engine_simulator/gui/persistence.py:120-188` (save_sweep function)
- Modify: `engine_simulator/gui/persistence.py:191-244` (load_sweep function)
- Create: `tests/test_persistence_convergence.py`

The saved sweep JSON currently does NOT include per-RPM convergence data (delta_history, p_ivc_history, converged, converged_at_cycle). The report needs this data. We add a `"convergence"` key to the JSON document that maps each RPM to its convergence tracking.

- [ ] **Step 1: Write the failing test**

Create `tests/test_persistence_convergence.py`:

```python
"""Tests for convergence data round-trip in sweep persistence."""

import json
import os
import tempfile

from engine_simulator.gui.sweep_manager import LiveSweepState
from engine_simulator.gui.persistence import save_sweep, load_sweep


def _make_state_with_convergence() -> LiveSweepState:
    """Build a minimal LiveSweepState that includes convergence data."""
    return LiveSweepState(
        sweep_id="test-conv-001",
        status="complete",
        config={"name": "test", "n_cylinders": 4},
        config_name="test.json",
        rpm_points=[5000.0, 6000.0],
        n_cycles=10,
        n_workers=2,
        started_at="2026-04-09T00:00:00Z",
        completed_at="2026-04-09T00:05:00Z",
        rpms={
            5000.0: {
                "status": "done",
                "rpm_index": 0,
                "delta_history": [None, 0.15, 0.03, 0.004],
                "p_ivc_history": [
                    [101000.0, 101100.0, 101050.0, 101075.0],
                    [101200.0, 101300.0, 101250.0, 101275.0],
                    [101250.0, 101340.0, 101290.0, 101310.0],
                    [101252.0, 101342.0, 101291.0, 101312.0],
                ],
                "converged": True,
                "converged_at_cycle": 4,
                "perf": {"rpm": 5000.0, "indicated_power_hp": 30.0},
            },
            6000.0: {
                "status": "done",
                "rpm_index": 1,
                "delta_history": [None, 0.20, 0.08, 0.02, 0.003],
                "p_ivc_history": [
                    [102000.0, 102100.0, 102050.0, 102075.0],
                    [102400.0, 102500.0, 102450.0, 102475.0],
                    [102500.0, 102580.0, 102540.0, 102560.0],
                    [102520.0, 102595.0, 102555.0, 102575.0],
                    [102522.0, 102597.0, 102556.0, 102576.0],
                ],
                "converged": True,
                "converged_at_cycle": 5,
                "perf": {"rpm": 6000.0, "indicated_power_hp": 40.0},
            },
        },
        results_by_rpm={},
        sweep_results=[
            {"rpm": 5000.0, "indicated_power_hp": 30.0},
            {"rpm": 6000.0, "indicated_power_hp": 40.0},
        ],
    )


def test_convergence_data_round_trips():
    """Save a sweep with convergence data, load it, verify convergence is intact."""
    state = _make_state_with_convergence()
    with tempfile.TemporaryDirectory() as tmpdir:
        save_sweep(state, tmpdir)
        filepath = os.path.join(tmpdir, f"{state.sweep_id}.json")
        loaded = load_sweep(filepath)

    # Check that convergence data survived the round trip
    for rpm in [5000.0, 6000.0]:
        rpm_state = loaded.rpms[rpm]
        original = state.rpms[rpm]
        assert rpm_state.get("delta_history") == original["delta_history"]
        assert rpm_state.get("p_ivc_history") == original["p_ivc_history"]
        assert rpm_state.get("converged") == original["converged"]
        assert rpm_state.get("converged_at_cycle") == original["converged_at_cycle"]


def test_load_sweep_without_convergence_key():
    """Loading a legacy sweep file (no convergence key) should still work."""
    state = _make_state_with_convergence()
    with tempfile.TemporaryDirectory() as tmpdir:
        save_sweep(state, tmpdir)
        filepath = os.path.join(tmpdir, f"{state.sweep_id}.json")

        # Strip the convergence key to simulate a legacy file
        with open(filepath) as f:
            data = json.load(f)
        data.pop("convergence", None)
        with open(filepath, "w") as f:
            json.dump(data, f)

        loaded = load_sweep(filepath)

    # Should load fine, just no convergence data in rpms
    assert loaded.rpms[5000.0]["status"] == "done"
    # delta_history should be absent or empty
    assert loaded.rpms[5000.0].get("delta_history") in (None, [])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_persistence_convergence.py -v`

Expected: FAIL — `test_convergence_data_round_trips` fails because convergence data is not persisted.

- [ ] **Step 3: Modify save_sweep to persist convergence data**

In `engine_simulator/gui/persistence.py`, in the `save_sweep` function, add a `"convergence"` key to the document dict. Insert this after the `"results_by_rpm"` entry (after line 179):

```python
        "convergence": {
            str(rpm): {
                "delta_history": _coerce_jsonable(
                    rpm_state.get("delta_history", [])
                ),
                "p_ivc_history": _coerce_jsonable(
                    rpm_state.get("p_ivc_history", [])
                ),
                "converged": rpm_state.get("converged", False),
                "converged_at_cycle": rpm_state.get("converged_at_cycle"),
            }
            for rpm, rpm_state in state.rpms.items()
        },
```

- [ ] **Step 4: Modify load_sweep to restore convergence data**

In `engine_simulator/gui/persistence.py`, in the `load_sweep` function, after the rpms dict is built from perf data (around line 233-240), merge convergence data back in. Replace the rpms construction block:

```python
    # Build per-RPM state from perf list
    rpms = {
        float(p["rpm"]): {
            "status": "done",
            "rpm_index": idx,
            "perf": p,
        }
        for idx, p in enumerate(data.get("perf", []))
    }

    # Merge convergence data if present (added in report feature)
    convergence = data.get("convergence", {})
    for rpm_str, conv_data in convergence.items():
        rpm_key = float(rpm_str)
        if rpm_key in rpms:
            rpms[rpm_key]["delta_history"] = conv_data.get("delta_history", [])
            rpms[rpm_key]["p_ivc_history"] = conv_data.get("p_ivc_history", [])
            rpms[rpm_key]["converged"] = conv_data.get("converged", False)
            rpms[rpm_key]["converged_at_cycle"] = conv_data.get("converged_at_cycle")
```

Then use this `rpms` variable in the `LiveSweepState(...)` constructor instead of the inline dict comprehension.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_persistence_convergence.py -v`

Expected: Both tests PASS.

- [ ] **Step 6: Run existing persistence tests to check for regressions**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/ -k persistence -v`

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add engine_simulator/gui/persistence.py tests/test_persistence_convergence.py
git commit -m "feat: persist convergence data (delta_history, p_ivc_history) in sweep JSON"
```

---

### Task 3: Chart Rendering Module (report_charts.py)

**Files:**
- Create: `engine_simulator/gui/report_charts.py`
- Create: `tests/test_report_charts.py`

All chart functions follow the same pattern: accept data, create a matplotlib figure, save to an `io.BytesIO` as SVG, return the SVG string. Use a consistent style across all charts.

- [ ] **Step 1: Write the test for sweep curve charts**

Create `tests/test_report_charts.py`:

```python
"""Tests for report chart rendering functions."""

import pytest


SAMPLE_PERF = [
    {
        "rpm": 5000.0,
        "indicated_power_hp": 30.0, "brake_power_hp": 26.0, "wheel_power_hp": 22.0,
        "indicated_torque_Nm": 45.0, "brake_torque_Nm": 39.0, "wheel_torque_Nm": 33.0,
        "volumetric_efficiency_atm": 0.85, "volumetric_efficiency_plenum": 0.92,
        "imep_bar": 10.5, "bmep_bar": 9.1,
        "plenum_pressure_bar": 0.98, "restrictor_mdot": 0.055,
        "restrictor_choked": False,
    },
    {
        "rpm": 8000.0,
        "indicated_power_hp": 55.0, "brake_power_hp": 48.0, "wheel_power_hp": 41.0,
        "indicated_torque_Nm": 51.0, "brake_torque_Nm": 44.0, "wheel_torque_Nm": 38.0,
        "volumetric_efficiency_atm": 0.92, "volumetric_efficiency_plenum": 1.05,
        "imep_bar": 12.1, "bmep_bar": 10.5,
        "plenum_pressure_bar": 0.95, "restrictor_mdot": 0.068,
        "restrictor_choked": True,
    },
]


def test_render_sweep_curves_returns_six_svgs():
    from engine_simulator.gui.report_charts import render_sweep_curves
    svgs = render_sweep_curves(SAMPLE_PERF)
    assert len(svgs) == 6
    for svg in svgs:
        assert "<svg" in svg
        assert "</svg>" in svg


def test_render_convergence_overview_returns_svg():
    from engine_simulator.gui.report_charts import render_convergence_overview
    convergence_data = {
        5000.0: {"converged": True, "converged_at_cycle": 4, "delta_history": [None, 0.1, 0.01, 0.001]},
        8000.0: {"converged": True, "converged_at_cycle": 6, "delta_history": [None, 0.2, 0.08, 0.02, 0.005, 0.001]},
    }
    svg = render_convergence_overview(convergence_data)
    assert "<svg" in svg


def test_render_cylinder_traces_returns_svgs():
    from engine_simulator.gui.report_charts import render_cylinder_traces
    results = {
        "cylinder_data": {
            "0": {
                "theta": [0.0, 180.0, 360.0, 540.0, 720.0],
                "pressure": [101325.0, 500000.0, 3000000.0, 500000.0, 101325.0],
                "temperature": [300.0, 450.0, 2500.0, 1200.0, 400.0],
            },
            "1": {
                "theta": [0.0, 180.0, 360.0, 540.0, 720.0],
                "pressure": [101325.0, 500000.0, 3000000.0, 500000.0, 101325.0],
                "temperature": [300.0, 450.0, 2500.0, 1200.0, 400.0],
            },
        },
    }
    svgs = render_cylinder_traces(results)
    assert len(svgs) == 2  # pressure + temperature
    for svg in svgs:
        assert "<svg" in svg


def test_render_pv_diagrams_returns_svg():
    from engine_simulator.gui.report_charts import render_pv_diagrams
    results = {
        "cylinder_data": {
            "0": {
                "theta": [0.0, 180.0, 360.0, 540.0, 720.0],
                "pressure": [101325.0, 500000.0, 3000000.0, 500000.0, 101325.0],
            },
        },
    }
    engine_config = {
        "cylinder": {
            "bore": 0.067, "stroke": 0.042, "con_rod_length": 0.1,
            "compression_ratio": 12.2,
        },
    }
    svg = render_pv_diagrams(results, engine_config)
    assert "<svg" in svg


def test_render_pipe_traces_returns_svgs():
    from engine_simulator.gui.report_charts import render_pipe_traces
    results = {
        "pipe_probes": {
            "intake_runner_1_mid": {
                "theta": [0.0, 180.0, 360.0, 540.0, 720.0],
                "pressure": [101325.0, 98000.0, 95000.0, 99000.0, 101325.0],
                "temperature": [300.0, 298.0, 295.0, 299.0, 300.0],
                "velocity": [0.0, 50.0, 80.0, 30.0, 0.0],
            },
        },
    }
    svgs = render_pipe_traces(results)
    assert len(svgs) == 3  # pressure, temperature, velocity
    for svg in svgs:
        assert "<svg" in svg


def test_render_plenum_chart_returns_svg():
    from engine_simulator.gui.report_charts import render_plenum_chart
    results = {
        "theta_history": [0.0, 180.0, 360.0, 540.0, 720.0],
        "plenum_pressure": [101325.0, 100000.0, 99000.0, 100500.0, 101000.0],
        "plenum_temperature": [300.0, 299.0, 298.0, 299.5, 300.0],
    }
    svg = render_plenum_chart(results)
    assert "<svg" in svg


def test_render_restrictor_chart_returns_svg():
    from engine_simulator.gui.report_charts import render_restrictor_chart
    results = {
        "theta_history": [0.0, 180.0, 360.0, 540.0, 720.0],
        "restrictor_mdot": [0.05, 0.06, 0.072, 0.065, 0.055],
        "restrictor_choked": [False, False, True, False, False],
    }
    svg = render_restrictor_chart(results)
    assert "<svg" in svg


def test_render_convergence_detail_returns_svgs():
    from engine_simulator.gui.report_charts import render_convergence_detail
    delta_history = [None, 0.15, 0.03, 0.004]
    p_ivc_history = [
        [101000.0, 101100.0, 101050.0, 101075.0],
        [101200.0, 101300.0, 101250.0, 101275.0],
        [101250.0, 101340.0, 101290.0, 101310.0],
        [101252.0, 101342.0, 101291.0, 101312.0],
    ]
    svgs = render_convergence_detail(delta_history, p_ivc_history)
    assert len(svgs) == 2  # delta chart + p_ivc chart
    for svg in svgs:
        assert "<svg" in svg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_report_charts.py -v`

Expected: FAIL — `report_charts` module does not exist.

- [ ] **Step 3: Implement report_charts.py**

Create `engine_simulator/gui/report_charts.py`:

```python
"""Matplotlib chart rendering for PDF reports.

Each public function generates one or more charts and returns SVG string(s).
All figures use a consistent visual style: white background, subtle grid,
professional color palette, clean axis labels with units.
"""

from __future__ import annotations

import io
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server-side rendering
import matplotlib.pyplot as plt
import numpy as np


# ── Consistent style ────────────────────────────────────────────────────────

COLORS = {
    "blue": "#2563eb",
    "blue_light": "#60a5fa",
    "orange": "#ea580c",
    "green": "#16a34a",
    "green_light": "#4ade80",
    "purple": "#9333ea",
    "red": "#dc2626",
    "gray": "#6b7280",
    "cyan": "#0891b2",
}

GRID_STYLE = {"color": "#e0e0e0", "alpha": 0.6, "linewidth": 0.5}
LINE_WIDTH = 1.5
MARKER_SIZE = 4


def _apply_style(ax, xlabel: str = "", ylabel: str = "", title: str = ""):
    """Apply consistent styling to an axes."""
    ax.set_xlabel(xlabel, fontsize=9, fontweight="medium")
    ax.set_ylabel(ylabel, fontsize=9, fontweight="medium")
    if title:
        ax.set_title(title, fontsize=10, fontweight="semibold", pad=8)
    ax.grid(True, **GRID_STYLE)
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _fig_to_svg(fig) -> str:
    """Render a matplotlib figure to an SVG string and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read().decode("utf-8")


def _split_cycles(theta, *arrays):
    """Insert NaN at cycle boundaries so matplotlib doesn't draw wrap lines."""
    theta = np.asarray(theta, dtype=float)
    if theta.size < 2:
        return (theta,) + tuple(np.asarray(a, dtype=float) for a in arrays)
    wraps = np.where(np.diff(theta) < -360.0)[0] + 1
    if wraps.size == 0:
        return (theta,) + tuple(np.asarray(a, dtype=float) for a in arrays)
    out_theta = np.insert(theta, wraps, np.nan)
    out_arrays = tuple(
        np.insert(np.asarray(a, dtype=float), wraps, np.nan) for a in arrays
    )
    return (out_theta,) + out_arrays


# ── Sweep-level charts ──────────────────────────────────────────────────────


def render_sweep_curves(perf_data: list[dict]) -> list[str]:
    """Render the 6 performance-vs-RPM sweep charts.

    Returns a list of 6 SVG strings:
    [power, torque, VE, IMEP/BMEP, plenum_pressure, restrictor_flow]
    """
    rpm = [p["rpm"] for p in perf_data]
    svgs = []

    # 1. Power
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, [p["indicated_power_hp"] for p in perf_data],
            "-o", color=COLORS["orange"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="Indicated")
    ax.plot(rpm, [p["brake_power_hp"] for p in perf_data],
            "-s", color=COLORS["blue"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="Brake")
    ax.plot(rpm, [p.get("wheel_power_hp", p["brake_power_hp"]) for p in perf_data],
            "--^", color=COLORS["blue_light"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="Wheel")
    _apply_style(ax, "RPM", "Power (HP)", "Power vs RPM")
    ax.legend(fontsize=8, framealpha=0.9)
    svgs.append(_fig_to_svg(fig))

    # 2. Torque
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, [p["indicated_torque_Nm"] for p in perf_data],
            "-o", color=COLORS["orange"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="Indicated")
    ax.plot(rpm, [p["brake_torque_Nm"] for p in perf_data],
            "-s", color=COLORS["blue"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="Brake")
    ax.plot(rpm, [p.get("wheel_torque_Nm", p["brake_torque_Nm"]) for p in perf_data],
            "--^", color=COLORS["blue_light"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="Wheel")
    _apply_style(ax, "RPM", "Torque (Nm)", "Torque vs RPM")
    ax.legend(fontsize=8, framealpha=0.9)
    svgs.append(_fig_to_svg(fig))

    # 3. Volumetric Efficiency
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, [p["volumetric_efficiency_atm"] * 100 for p in perf_data],
            "-o", color=COLORS["green"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="Atmospheric")
    ax.plot(rpm, [p.get("volumetric_efficiency_plenum", p["volumetric_efficiency_atm"]) * 100
                  for p in perf_data],
            "--s", color=COLORS["green_light"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="Plenum")
    ax.axhline(100, color="#999", linestyle="--", alpha=0.4, lw=0.8)
    _apply_style(ax, "RPM", "VE (%)", "Volumetric Efficiency vs RPM")
    ax.legend(fontsize=8, framealpha=0.9)
    svgs.append(_fig_to_svg(fig))

    # 4. IMEP / BMEP
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, [p.get("imep_bar", 0) for p in perf_data],
            "-o", color=COLORS["orange"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="IMEP")
    ax.plot(rpm, [p.get("bmep_bar", 0) for p in perf_data],
            "-s", color=COLORS["blue"], ms=MARKER_SIZE, lw=LINE_WIDTH, label="BMEP")
    _apply_style(ax, "RPM", "MEP (bar)", "Mean Effective Pressure vs RPM")
    ax.legend(fontsize=8, framealpha=0.9)
    svgs.append(_fig_to_svg(fig))

    # 5. Plenum Pressure
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, [p.get("plenum_pressure_bar", 0) for p in perf_data],
            "-o", color=COLORS["cyan"], ms=MARKER_SIZE, lw=LINE_WIDTH)
    _apply_style(ax, "RPM", "Pressure (bar)", "Plenum Pressure vs RPM")
    svgs.append(_fig_to_svg(fig))

    # 6. Restrictor Flow
    fig, ax = plt.subplots(figsize=(7, 3.5))
    mdot_gs = [p.get("restrictor_mdot", 0) * 1000 for p in perf_data]
    choked = [p.get("restrictor_choked", False) for p in perf_data]
    ax.plot(rpm, mdot_gs, "-o", color=COLORS["purple"], ms=MARKER_SIZE, lw=LINE_WIDTH)
    # Mark choked points
    choked_rpm = [r for r, c in zip(rpm, choked) if c]
    choked_mdot = [m for m, c in zip(mdot_gs, choked) if c]
    if choked_rpm:
        ax.scatter(choked_rpm, choked_mdot, color=COLORS["red"], s=40,
                   zorder=5, label="Choked", marker="x", linewidths=2)
        ax.legend(fontsize=8, framealpha=0.9)
    _apply_style(ax, "RPM", "Mass Flow (g/s)", "Restrictor Flow vs RPM")
    svgs.append(_fig_to_svg(fig))

    return svgs


def render_convergence_overview(convergence_data: dict) -> str:
    """Render cycles-to-converge vs RPM overview chart.

    convergence_data: {rpm_float: {"converged": bool, "converged_at_cycle": int|None, "delta_history": [...]}}
    """
    rpms = sorted(convergence_data.keys())
    cycles = []
    colors = []
    for rpm in rpms:
        d = convergence_data[rpm]
        c = d.get("converged_at_cycle")
        if c is not None:
            cycles.append(c)
            colors.append(COLORS["green"])
        else:
            # Use total cycles (length of delta_history) for non-converged
            cycles.append(len(d.get("delta_history", [])))
            colors.append(COLORS["red"])

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(rpms, cycles, width=(rpms[1] - rpms[0]) * 0.7 if len(rpms) > 1 else 200,
           color=colors, alpha=0.8)
    _apply_style(ax, "RPM", "Cycles to Converge", "Convergence vs RPM")
    return _fig_to_svg(fig)


# ── Per-RPM detail charts ───────────────────────────────────────────────────


def render_cylinder_traces(results: dict) -> list[str]:
    """Render cylinder pressure and temperature vs crank angle.

    Returns [pressure_svg, temperature_svg].
    results: deserialized per-RPM dict with "cylinder_data" key.
    """
    cyl_data = results.get("cylinder_data", {})
    cyl_colors = [COLORS["blue"], COLORS["orange"], COLORS["green"], COLORS["purple"]]
    svgs = []

    # Pressure
    fig, ax = plt.subplots(figsize=(7, 3.5))
    for i, (cid, cd) in enumerate(sorted(cyl_data.items(), key=lambda x: int(x[0]))):
        theta = np.array(cd["theta"], dtype=float) % 720.0
        p_bar = np.array(cd["pressure"], dtype=float) / 1e5
        theta, p_bar = _split_cycles(theta, p_bar)
        color = cyl_colors[int(cid) % len(cyl_colors)]
        ax.plot(theta, p_bar, color=color, lw=0.8, label=f"Cyl {int(cid)+1}")
    ax.set_xlim(0, 720)
    _apply_style(ax, "Crank Angle (\u00b0)", "Pressure (bar)", "Cylinder Pressure")
    ax.legend(fontsize=7, framealpha=0.9, ncol=2)
    svgs.append(_fig_to_svg(fig))

    # Temperature
    fig, ax = plt.subplots(figsize=(7, 3.5))
    for i, (cid, cd) in enumerate(sorted(cyl_data.items(), key=lambda x: int(x[0]))):
        theta = np.array(cd["theta"], dtype=float) % 720.0
        temp = np.array(cd["temperature"], dtype=float)
        theta, temp = _split_cycles(theta, temp)
        color = cyl_colors[int(cid) % len(cyl_colors)]
        ax.plot(theta, temp, color=color, lw=0.8, label=f"Cyl {int(cid)+1}")
    ax.set_xlim(0, 720)
    _apply_style(ax, "Crank Angle (\u00b0)", "Temperature (K)", "Cylinder Temperature")
    ax.legend(fontsize=7, framealpha=0.9, ncol=2)
    svgs.append(_fig_to_svg(fig))

    return svgs


def render_pv_diagrams(results: dict, engine_config: dict) -> str:
    """Render P-V diagram for all cylinders overlaid.

    Uses engine geometry from engine_config to compute volume from crank angle.
    """
    cyl = engine_config.get("cylinder", {})
    bore = cyl.get("bore", 0.067)
    stroke = cyl.get("stroke", 0.042)
    con_rod = cyl.get("con_rod_length", 0.1)
    cr = cyl.get("compression_ratio", 12.0)

    # Compute volume from theta
    A_piston = np.pi / 4 * bore**2
    V_d = A_piston * stroke  # displacement per cylinder
    V_c = V_d / (cr - 1)    # clearance volume

    def volume_at_theta(theta_deg):
        theta_rad = np.radians(theta_deg)
        x = (con_rod + stroke / 2) - (
            stroke / 2 * np.cos(theta_rad)
            + np.sqrt(con_rod**2 - (stroke / 2 * np.sin(theta_rad))**2)
        )
        return (V_c + A_piston * x) * 1e6  # cc

    cyl_data = results.get("cylinder_data", {})
    cyl_colors = [COLORS["blue"], COLORS["orange"], COLORS["green"], COLORS["purple"]]

    fig, ax = plt.subplots(figsize=(6, 4.5))
    for cid, cd in sorted(cyl_data.items(), key=lambda x: int(x[0])):
        theta = np.array(cd["theta"], dtype=float) % 720.0
        p_bar = np.array(cd["pressure"], dtype=float) / 1e5
        V_cc = volume_at_theta(theta)
        _, V_cc, p_bar = _split_cycles(theta, V_cc, p_bar)
        color = cyl_colors[int(cid) % len(cyl_colors)]
        ax.plot(V_cc, p_bar, color=color, lw=0.8, label=f"Cyl {int(cid)+1}")
    ax.set_xscale("log")
    ax.set_yscale("log")
    _apply_style(ax, "Volume (cc)", "Pressure (bar)", "P-V Diagram")
    ax.legend(fontsize=7, framealpha=0.9, ncol=2)
    return _fig_to_svg(fig)


def render_pipe_traces(results: dict) -> list[str]:
    """Render pipe probe pressure, temperature, velocity.

    Returns [pressure_svg, temperature_svg, velocity_svg].
    """
    probes = results.get("pipe_probes", {})
    if not probes:
        return []

    # Separate intake and exhaust probes
    intake_probes = {k: v for k, v in probes.items() if "intake" in k}
    exhaust_probes = {k: v for k, v in probes.items() if "exhaust" in k}

    svgs = []
    for field, ylabel, title_suffix in [
        ("pressure", "Pressure (bar)", "Pressure"),
        ("temperature", "Temperature (K)", "Temperature"),
        ("velocity", "Velocity (m/s)", "Velocity"),
    ]:
        fig, axes = plt.subplots(1, 2, figsize=(7, 3.5), sharey=True)

        for ax, (label, subset) in zip(axes, [("Intake", intake_probes), ("Exhaust", exhaust_probes)]):
            for i, (name, pd) in enumerate(sorted(subset.items())):
                theta = np.array(pd["theta"], dtype=float) % 720.0
                vals = np.array(pd[field], dtype=float)
                if field == "pressure":
                    vals = vals / 1e5
                theta, vals = _split_cycles(theta, vals)
                short_name = name.replace("_mid", "").replace("_", " ").title()
                ax.plot(theta, vals, lw=0.6, label=short_name, alpha=0.8)
            ax.set_xlim(0, 720)
            _apply_style(ax, "Crank Angle (\u00b0)", ylabel if ax == axes[0] else "",
                         f"{label} {title_suffix}")
            ax.legend(fontsize=5, framealpha=0.9, ncol=1, loc="best")

        fig.tight_layout()
        svgs.append(_fig_to_svg(fig))

    return svgs


def render_plenum_chart(results: dict) -> str:
    """Render plenum pressure and temperature vs crank angle."""
    theta = np.array(results.get("theta_history", []), dtype=float) % 720.0
    p_bar = np.array(results.get("plenum_pressure", []), dtype=float) / 1e5
    temp = np.array(results.get("plenum_temperature", []), dtype=float)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 4.5), sharex=True)
    t_p, p_p = _split_cycles(theta, p_bar)
    ax1.plot(t_p, p_p, color=COLORS["cyan"], lw=0.6)
    _apply_style(ax1, "", "Pressure (bar)", "Plenum Pressure")
    ax1.set_xlim(0, 720)

    t_t, temp_p = _split_cycles(theta, temp)
    ax2.plot(t_t, temp_p, color=COLORS["orange"], lw=0.6)
    _apply_style(ax2, "Crank Angle (\u00b0)", "Temperature (K)", "Plenum Temperature")
    ax2.set_xlim(0, 720)

    fig.tight_layout()
    return _fig_to_svg(fig)


def render_restrictor_chart(results: dict) -> str:
    """Render restrictor mass flow rate vs crank angle with choked regions."""
    theta = np.array(results.get("theta_history", []), dtype=float) % 720.0
    mdot = np.array(results.get("restrictor_mdot", []), dtype=float) * 1000  # g/s
    choked = np.array(results.get("restrictor_choked", []), dtype=bool)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    t_plot, mdot_plot = _split_cycles(theta, mdot)
    ax.plot(t_plot, mdot_plot, color=COLORS["purple"], lw=0.6)

    # Shade choked regions
    if choked.any():
        t_choke, choke_f = _split_cycles(theta, choked.astype(float))
        ax.fill_between(t_choke, 0, mdot_plot, where=(choke_f > 0.5),
                        alpha=0.15, color=COLORS["red"], label="Choked")
        ax.legend(fontsize=7, framealpha=0.9)

    ax.set_xlim(0, 720)
    _apply_style(ax, "Crank Angle (\u00b0)", "Mass Flow (g/s)", "Restrictor Flow")
    return _fig_to_svg(fig)


def render_convergence_detail(
    delta_history: list, p_ivc_history: list
) -> list[str]:
    """Render per-RPM convergence charts.

    Returns [delta_svg, p_ivc_svg].
    delta_history: [None, 0.15, 0.03, ...] — one per cycle
    p_ivc_history: [[p0, p1, ...], [p0, p1, ...], ...] — one list per cycle, one value per cylinder
    """
    svgs = []

    # Delta history
    fig, ax = plt.subplots(figsize=(7, 3))
    cycles = list(range(1, len(delta_history) + 1))
    deltas = [d if d is not None else float("nan") for d in delta_history]
    ax.semilogy(cycles, deltas, "-o", color=COLORS["blue"], ms=MARKER_SIZE, lw=LINE_WIDTH)
    _apply_style(ax, "Cycle", "\u0394 (max relative change)", "Convergence History")
    svgs.append(_fig_to_svg(fig))

    # p_IVC per cylinder
    if p_ivc_history:
        n_cyls = len(p_ivc_history[0]) if p_ivc_history else 0
        fig, ax = plt.subplots(figsize=(7, 3))
        cyl_colors = [COLORS["blue"], COLORS["orange"], COLORS["green"], COLORS["purple"]]
        for cyl_idx in range(n_cyls):
            p_ivc_vals = [
                cycle[cyl_idx] / 1e5 if cycle[cyl_idx] is not None else float("nan")
                for cycle in p_ivc_history
            ]
            color = cyl_colors[cyl_idx % len(cyl_colors)]
            ax.plot(cycles[:len(p_ivc_vals)], p_ivc_vals, "-o", color=color,
                    ms=3, lw=1.2, label=f"Cyl {cyl_idx+1}")
        _apply_style(ax, "Cycle", "p_IVC (bar)", "IVC Pressure Convergence")
        ax.legend(fontsize=7, framealpha=0.9, ncol=2)
        svgs.append(_fig_to_svg(fig))
    else:
        # Empty chart if no data
        fig, ax = plt.subplots(figsize=(7, 3))
        _apply_style(ax, "Cycle", "p_IVC (bar)", "IVC Pressure Convergence")
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center",
                fontsize=12, color="#999")
        svgs.append(_fig_to_svg(fig))

    return svgs
```

- [ ] **Step 4: Run the tests**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_report_charts.py -v`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add engine_simulator/gui/report_charts.py tests/test_report_charts.py
git commit -m "feat: add matplotlib chart rendering module for PDF reports"
```

---

### Task 4: HTML/CSS Report Template

**Files:**
- Create: `engine_simulator/gui/report_template.html`

This is a Jinja2 template with embedded CSS that WeasyPrint will convert to PDF.

- [ ] **Step 1: Create the template file**

Create `engine_simulator/gui/report_template.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  @page {
    size: A4;
    margin: 20mm;
    @top-right {
      content: "{{ config_name }} — Engine Simulation Report";
      font-family: Helvetica Neue, Arial, sans-serif;
      font-size: 7pt;
      color: #999;
    }
    @bottom-center {
      content: counter(page);
      font-family: Helvetica Neue, Arial, sans-serif;
      font-size: 8pt;
      color: #999;
    }
  }
  @page cover {
    @top-right { content: none; }
    @bottom-center { content: none; }
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: "Helvetica Neue", Arial, sans-serif;
    font-size: 9pt;
    color: #1a1a2e;
    line-height: 1.5;
  }

  /* ── Cover Page ─────────────────────────────────────────── */
  .cover {
    page: cover;
    page-break-after: always;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    height: 100vh;
    text-align: center;
  }
  .cover-title {
    font-size: 28pt;
    font-weight: 700;
    color: #1e3a5f;
    letter-spacing: 0.03em;
    margin-bottom: 8mm;
  }
  .cover-rule {
    width: 60mm;
    height: 0.5mm;
    background: #1e3a5f;
    margin: 4mm auto;
  }
  .cover-config {
    font-size: 14pt;
    font-weight: 500;
    color: #333;
    margin-bottom: 6mm;
  }
  .cover-date {
    font-size: 10pt;
    color: #777;
    margin-bottom: 12mm;
  }
  .cover-stats {
    display: flex;
    gap: 20mm;
    margin-top: 6mm;
  }
  .cover-stat {
    text-align: center;
  }
  .cover-stat-value {
    font-size: 20pt;
    font-weight: 700;
    color: #1e3a5f;
  }
  .cover-stat-label {
    font-size: 8pt;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .cover-stat-sub {
    font-size: 8pt;
    color: #666;
  }

  /* ── Section Headers ────────────────────────────────────── */
  h2 {
    font-size: 16pt;
    font-weight: 700;
    color: #1e3a5f;
    border-bottom: 2px solid #1e3a5f;
    padding-bottom: 2mm;
    margin: 8mm 0 4mm 0;
    page-break-after: avoid;
  }
  h3 {
    font-size: 11pt;
    font-weight: 600;
    color: #333;
    margin: 5mm 0 2mm 0;
    page-break-after: avoid;
  }

  /* ── Tables ─────────────────────────────────────────────── */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 3mm 0 5mm 0;
    font-size: 8pt;
    page-break-inside: auto;
  }
  thead th {
    background: #1e3a5f;
    color: #fff;
    font-weight: 600;
    text-align: left;
    padding: 2mm 3mm;
    font-size: 7.5pt;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  tbody td {
    padding: 1.5mm 3mm;
    border-bottom: 0.25pt solid #e0e0e0;
  }
  tbody tr:nth-child(even) {
    background: #f4f6f8;
  }
  .unit {
    color: #888;
    font-size: 7pt;
  }
  .num {
    font-family: "Courier New", monospace;
    font-size: 8pt;
  }

  /* ── Charts ─────────────────────────────────────────────── */
  .chart-full {
    width: 100%;
    margin: 3mm 0;
    page-break-inside: avoid;
  }
  .chart-full svg {
    width: 100%;
    height: auto;
  }
  .chart-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 3mm;
    margin: 3mm 0;
  }
  .chart-half {
    width: 48%;
    page-break-inside: avoid;
  }
  .chart-half svg {
    width: 100%;
    height: auto;
  }

  /* ── Appendix ───────────────────────────────────────────── */
  .appendix-page {
    page-break-before: always;
  }
  .appendix-header {
    font-size: 14pt;
    font-weight: 700;
    color: #1e3a5f;
    border-bottom: 2px solid #1e3a5f;
    padding-bottom: 2mm;
    margin-bottom: 4mm;
  }
  .appendix-rpm {
    font-size: 12pt;
    color: #333;
    margin-bottom: 4mm;
  }

  /* ── Utilities ──────────────────────────────────────────── */
  .page-break { page-break-before: always; }
  .avoid-break { page-break-inside: avoid; }
  .text-right { text-align: right; }
  .text-center { text-align: center; }
  .green { color: #16a34a; }
  .red { color: #dc2626; }
</style>
</head>
<body>

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- COVER PAGE                                                      -->
<!-- ════════════════════════════════════════════════════════════════ -->
<div class="cover">
  <div class="cover-title">Engine Simulation Report</div>
  <div class="cover-rule"></div>
  <div class="cover-config">{{ config_name }}</div>
  <div class="cover-date">{{ sweep_date }}</div>
  <div class="cover-rule"></div>
  <div class="cover-stats">
    <div class="cover-stat">
      <div class="cover-stat-value">{{ "%.1f"|format(peak_power_hp) }}</div>
      <div class="cover-stat-label">Peak Power (HP)</div>
      <div class="cover-stat-sub">@ {{ "%.0f"|format(peak_power_rpm) }} RPM</div>
    </div>
    <div class="cover-stat">
      <div class="cover-stat-value">{{ "%.1f"|format(peak_torque_nm) }}</div>
      <div class="cover-stat-label">Peak Torque (Nm)</div>
      <div class="cover-stat-sub">@ {{ "%.0f"|format(peak_torque_rpm) }} RPM</div>
    </div>
  </div>
</div>

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- SECTION 1: ENGINE CONFIGURATION                                 -->
<!-- ════════════════════════════════════════════════════════════════ -->
<h2>Engine Configuration</h2>

<h3>General</h3>
<table>
  <thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead>
  <tbody>
    <tr><td>Cylinders</td><td class="num">{{ engine_config.n_cylinders }}</td><td></td></tr>
    <tr><td>Firing Order</td><td class="num">{{ engine_config.firing_order }}</td><td></td></tr>
    <tr><td>Firing Interval</td><td class="num">{{ engine_config.firing_interval }}</td><td class="unit">°</td></tr>
    <tr><td>Ambient Pressure</td><td class="num">{{ "%.0f"|format(engine_config.p_ambient) }}</td><td class="unit">Pa</td></tr>
    <tr><td>Ambient Temperature</td><td class="num">{{ "%.1f"|format(engine_config.T_ambient) }}</td><td class="unit">K</td></tr>
    <tr><td>Drivetrain Efficiency</td><td class="num">{{ "%.3f"|format(engine_config.drivetrain_efficiency) }}</td><td></td></tr>
  </tbody>
</table>

<h3>Cylinder Geometry</h3>
<table>
  <thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead>
  <tbody>
    {% set cyl = engine_config.cylinder %}
    <tr><td>Bore</td><td class="num">{{ "%.1f"|format(cyl.bore * 1000) }}</td><td class="unit">mm</td></tr>
    <tr><td>Stroke</td><td class="num">{{ "%.1f"|format(cyl.stroke * 1000) }}</td><td class="unit">mm</td></tr>
    <tr><td>Con Rod Length</td><td class="num">{{ "%.1f"|format(cyl.con_rod_length * 1000) }}</td><td class="unit">mm</td></tr>
    <tr><td>Compression Ratio</td><td class="num">{{ "%.1f"|format(cyl.compression_ratio) }}</td><td class="unit">:1</td></tr>
    <tr><td>Intake Valves</td><td class="num">{{ cyl.n_intake_valves }}</td><td></td></tr>
    <tr><td>Exhaust Valves</td><td class="num">{{ cyl.n_exhaust_valves }}</td><td></td></tr>
  </tbody>
</table>

{% for valve_key, valve_label in [("intake_valve", "Intake Valve"), ("exhaust_valve", "Exhaust Valve")] %}
<h3>{{ valve_label }}</h3>
<table>
  <thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead>
  <tbody>
    {% set v = engine_config[valve_key] %}
    <tr><td>Diameter</td><td class="num">{{ "%.1f"|format(v.diameter * 1000) }}</td><td class="unit">mm</td></tr>
    <tr><td>Max Lift</td><td class="num">{{ "%.2f"|format(v.max_lift * 1000) }}</td><td class="unit">mm</td></tr>
    <tr><td>Open Angle</td><td class="num">{{ "%.1f"|format(v.open_angle) }}</td><td class="unit">°</td></tr>
    <tr><td>Close Angle</td><td class="num">{{ "%.1f"|format(v.close_angle) }}</td><td class="unit">°</td></tr>
    <tr><td>Seat Angle</td><td class="num">{{ "%.1f"|format(v.seat_angle) }}</td><td class="unit">°</td></tr>
  </tbody>
</table>
{% if v.cd_table %}
<h3>{{ valve_label }} — Cd Table</h3>
<table>
  <thead><tr><th>Lift/Diameter</th><th>Cd</th></tr></thead>
  <tbody>
    {% for row in v.cd_table %}
    <tr><td class="num">{{ "%.3f"|format(row[0]) }}</td><td class="num">{{ "%.4f"|format(row[1]) }}</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}
{% endfor %}

{% for pipe_key, pipe_label in [("intake_pipes", "Intake Pipes"), ("exhaust_primaries", "Exhaust Primaries"), ("exhaust_secondaries", "Exhaust Secondaries")] %}
{% if engine_config.get(pipe_key) %}
<h3>{{ pipe_label }}</h3>
<table>
  <thead><tr><th>Name</th><th>Length</th><th>Dia In</th><th>Dia Out</th><th>Points</th><th>Wall T</th><th>Roughness</th></tr></thead>
  <tbody>
    {% for p in engine_config[pipe_key] %}
    <tr>
      <td>{{ p.name }}</td>
      <td class="num">{{ "%.0f"|format(p.length * 1000) }} <span class="unit">mm</span></td>
      <td class="num">{{ "%.1f"|format(p.diameter * 1000) }} <span class="unit">mm</span></td>
      <td class="num">{{ "%.1f"|format(p.get("diameter_out", p.diameter) * 1000) }} <span class="unit">mm</span></td>
      <td class="num">{{ p.n_points }}</td>
      <td class="num">{{ "%.0f"|format(p.wall_temperature) }} <span class="unit">K</span></td>
      <td class="num">{{ p.roughness }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}
{% endfor %}

{% if engine_config.get("exhaust_collector") %}
<h3>Exhaust Collector</h3>
<table>
  <thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead>
  <tbody>
    {% set ec = engine_config.exhaust_collector %}
    <tr><td>Length</td><td class="num">{{ "%.0f"|format(ec.length * 1000) }}</td><td class="unit">mm</td></tr>
    <tr><td>Diameter</td><td class="num">{{ "%.1f"|format(ec.diameter * 1000) }}</td><td class="unit">mm</td></tr>
    <tr><td>Points</td><td class="num">{{ ec.n_points }}</td><td></td></tr>
  </tbody>
</table>
{% endif %}

<h3>Combustion</h3>
<table>
  <thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead>
  <tbody>
    {% set c = engine_config.combustion %}
    <tr><td>Wiebe a</td><td class="num">{{ c.wiebe_a }}</td><td></td></tr>
    <tr><td>Wiebe m</td><td class="num">{{ c.wiebe_m }}</td><td></td></tr>
    <tr><td>Combustion Duration</td><td class="num">{{ c.combustion_duration }}</td><td class="unit">°</td></tr>
    <tr><td>Spark Advance</td><td class="num">{{ c.spark_advance }}</td><td class="unit">° BTDC</td></tr>
    <tr><td>Ignition Delay</td><td class="num">{{ c.ignition_delay }}</td><td class="unit">°</td></tr>
    <tr><td>Combustion Efficiency</td><td class="num">{{ c.combustion_efficiency }}</td><td></td></tr>
    <tr><td>Q LHV</td><td class="num">{{ "%.2e"|format(c.q_lhv) }}</td><td class="unit">J/kg</td></tr>
    <tr><td>AFR Stoich</td><td class="num">{{ c.afr_stoich }}</td><td></td></tr>
    <tr><td>AFR Target</td><td class="num">{{ c.afr_target }}</td><td></td></tr>
  </tbody>
</table>

<h3>Restrictor</h3>
<table>
  <thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead>
  <tbody>
    {% set r = engine_config.restrictor %}
    <tr><td>Throat Diameter</td><td class="num">{{ "%.1f"|format(r.throat_diameter * 1000) }}</td><td class="unit">mm</td></tr>
    <tr><td>Discharge Coefficient</td><td class="num">{{ r.discharge_coefficient }}</td><td></td></tr>
    <tr><td>Converging Half Angle</td><td class="num">{{ r.converging_half_angle }}</td><td class="unit">°</td></tr>
    <tr><td>Diverging Half Angle</td><td class="num">{{ r.diverging_half_angle }}</td><td class="unit">°</td></tr>
  </tbody>
</table>

<h3>Plenum</h3>
<table>
  <thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead>
  <tbody>
    {% set pl = engine_config.plenum %}
    <tr><td>Volume</td><td class="num">{{ "%.1f"|format(pl.volume * 1e6) }}</td><td class="unit">cc</td></tr>
    <tr><td>Initial Pressure</td><td class="num">{{ "%.0f"|format(pl.initial_pressure) }}</td><td class="unit">Pa</td></tr>
    <tr><td>Initial Temperature</td><td class="num">{{ "%.1f"|format(pl.initial_temperature) }}</td><td class="unit">K</td></tr>
  </tbody>
</table>

<h3>Simulation Settings</h3>
<table>
  <thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead>
  <tbody>
    {% set s = engine_config.simulation %}
    <tr><td>RPM Start</td><td class="num">{{ s.rpm_start }}</td><td class="unit">RPM</td></tr>
    <tr><td>RPM End</td><td class="num">{{ s.rpm_end }}</td><td class="unit">RPM</td></tr>
    <tr><td>RPM Step</td><td class="num">{{ s.rpm_step }}</td><td class="unit">RPM</td></tr>
    <tr><td>Max Cycles</td><td class="num">{{ s.n_cycles }}</td><td></td></tr>
    <tr><td>CFL Number</td><td class="num">{{ s.cfl_number }}</td><td></td></tr>
    <tr><td>Convergence Tolerance</td><td class="num">{{ s.convergence_tolerance }}</td><td></td></tr>
    <tr><td>Max Crank Step</td><td class="num">{{ s.crank_step_max }}</td><td class="unit">°</td></tr>
    <tr><td>Artificial Viscosity</td><td class="num">{{ s.artificial_viscosity }}</td><td></td></tr>
  </tbody>
</table>

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- SECTION 2: PERFORMANCE SWEEP CURVES                             -->
<!-- ════════════════════════════════════════════════════════════════ -->
<div class="page-break"></div>
<h2>Performance Sweep Curves</h2>

{% for svg in sweep_curve_svgs %}
<div class="chart-full">{{ svg }}</div>
{% endfor %}

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- SECTION 3: PERFORMANCE DATA TABLE                               -->
<!-- ════════════════════════════════════════════════════════════════ -->
<div class="page-break"></div>
<h2>Performance Data</h2>

<table>
  <thead>
    <tr>
      <th>RPM</th>
      <th>Power <span style="font-weight:normal; opacity:0.7">(HP)</span></th>
      <th>Torque <span style="font-weight:normal; opacity:0.7">(Nm)</span></th>
      <th>VE <span style="font-weight:normal; opacity:0.7">(%)</span></th>
      <th>IMEP <span style="font-weight:normal; opacity:0.7">(bar)</span></th>
      <th>BMEP <span style="font-weight:normal; opacity:0.7">(bar)</span></th>
      <th>Plenum <span style="font-weight:normal; opacity:0.7">(bar)</span></th>
      <th>Restr. <span style="font-weight:normal; opacity:0.7">(g/s)</span></th>
      <th>Choked</th>
    </tr>
  </thead>
  <tbody>
    {% for p in perf_data %}
    <tr>
      <td class="num">{{ "%.0f"|format(p.rpm) }}</td>
      <td class="num">{{ "%.1f"|format(p.brake_power_hp) }}</td>
      <td class="num">{{ "%.1f"|format(p.brake_torque_Nm) }}</td>
      <td class="num">{{ "%.1f"|format(p.volumetric_efficiency_atm * 100) }}</td>
      <td class="num">{{ "%.2f"|format(p.imep_bar) }}</td>
      <td class="num">{{ "%.2f"|format(p.bmep_bar) }}</td>
      <td class="num">{{ "%.3f"|format(p.plenum_pressure_bar) }}</td>
      <td class="num">{{ "%.1f"|format(p.restrictor_mdot * 1000) }}</td>
      <td class="text-center">{% if p.restrictor_choked %}<span class="red">●</span>{% else %}<span class="green">○</span>{% endif %}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- SECTION 4: CONVERGENCE SUMMARY                                  -->
<!-- ════════════════════════════════════════════════════════════════ -->
<div class="page-break"></div>
<h2>Convergence Summary</h2>

{% if convergence_overview_svg %}
<div class="chart-full">{{ convergence_overview_svg }}</div>
{% endif %}

<table>
  <thead>
    <tr><th>RPM</th><th>Converged</th><th>Cycles</th><th>Final Δ</th></tr>
  </thead>
  <tbody>
    {% for rpm in convergence_table %}
    <tr>
      <td class="num">{{ "%.0f"|format(rpm.rpm) }}</td>
      <td class="text-center">{% if rpm.converged %}<span class="green">Yes</span>{% else %}<span class="red">No</span>{% endif %}</td>
      <td class="num">{{ rpm.cycles }}</td>
      <td class="num">{{ rpm.final_delta }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<!-- ════════════════════════════════════════════════════════════════ -->
<!-- APPENDIX: PER-RPM DETAIL PAGES                                  -->
<!-- ════════════════════════════════════════════════════════════════ -->
{% for rpm_page in rpm_detail_pages %}
<div class="appendix-page">
  <div class="appendix-header">Appendix — RPM Detail: {{ "%.0f"|format(rpm_page.rpm) }}</div>

  {% if rpm_page.cylinder_svgs %}
  <h3>Cylinder Traces</h3>
  <div class="chart-grid">
    {% for svg in rpm_page.cylinder_svgs %}
    <div class="chart-half">{{ svg }}</div>
    {% endfor %}
  </div>
  {% endif %}

  {% if rpm_page.pv_svg %}
  <h3>P-V Diagram</h3>
  <div class="chart-full">{{ rpm_page.pv_svg }}</div>
  {% endif %}

  {% if rpm_page.pipe_svgs %}
  <h3>Pipe Traces</h3>
  {% for svg in rpm_page.pipe_svgs %}
  <div class="chart-full">{{ svg }}</div>
  {% endfor %}
  {% endif %}

  {% if rpm_page.plenum_svg %}
  <h3>Plenum</h3>
  <div class="chart-full">{{ rpm_page.plenum_svg }}</div>
  {% endif %}

  {% if rpm_page.restrictor_svg %}
  <h3>Restrictor</h3>
  <div class="chart-full">{{ rpm_page.restrictor_svg }}</div>
  {% endif %}

  {% if rpm_page.convergence_svgs %}
  <h3>Convergence</h3>
  <div class="chart-grid">
    {% for svg in rpm_page.convergence_svgs %}
    <div class="chart-half">{{ svg }}</div>
    {% endfor %}
  </div>
  {% endif %}
</div>
{% endfor %}

</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add engine_simulator/gui/report_template.html
git commit -m "feat: add Jinja2 HTML/CSS template for PDF report"
```

---

### Task 5: Report Generation Module (report.py)

**Files:**
- Create: `engine_simulator/gui/report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
"""Tests for report generation orchestration."""

import json
import os


def _load_sample_sweep():
    """Load the smaller saved sweep for testing."""
    sweep_path = os.path.join(
        os.path.dirname(__file__), "..", "sweeps",
        "2026-04-10T03-47-56_2500-15000_step1000_12cyc.json",
    )
    with open(sweep_path) as f:
        return json.load(f)


def test_generate_report_returns_pdf_bytes():
    """generate_report should return bytes starting with %PDF."""
    from engine_simulator.gui.report import generate_report
    sweep_data = _load_sample_sweep()
    pdf_bytes = generate_report(sweep_data)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 1000  # should be a non-trivial PDF


def test_generate_report_with_no_convergence_data():
    """Report should generate even without convergence data."""
    from engine_simulator.gui.report import generate_report
    sweep_data = _load_sample_sweep()
    # Strip convergence key
    sweep_data.pop("convergence", None)
    pdf_bytes = generate_report(sweep_data)
    assert pdf_bytes[:5] == b"%PDF-"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_report.py -v`

Expected: FAIL — `report` module does not exist.

- [ ] **Step 3: Implement report.py**

Create `engine_simulator/gui/report.py`:

```python
"""PDF report generation for engine simulation sweeps.

Orchestrates: data extraction → chart rendering → Jinja2 template → WeasyPrint PDF.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from engine_simulator.gui import report_charts


_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_NAME = "report_template.html"


def _extract_headline_stats(perf_data: list[dict]) -> dict:
    """Find peak power and peak torque from the perf list."""
    peak_power = max(perf_data, key=lambda p: p.get("brake_power_hp", 0))
    peak_torque = max(perf_data, key=lambda p: p.get("brake_torque_Nm", 0))
    return {
        "peak_power_hp": peak_power["brake_power_hp"],
        "peak_power_rpm": peak_power["rpm"],
        "peak_torque_nm": peak_torque["brake_torque_Nm"],
        "peak_torque_rpm": peak_torque["rpm"],
    }


def _build_convergence_table(
    convergence: dict, perf_data: list[dict]
) -> list[SimpleNamespace]:
    """Build the convergence summary table rows."""
    rows = []
    for p in perf_data:
        rpm = p["rpm"]
        conv = convergence.get(str(rpm), convergence.get(str(float(rpm)), {}))
        delta_hist = conv.get("delta_history", [])
        converged = conv.get("converged", False)
        converged_at = conv.get("converged_at_cycle")
        # Final delta: last non-None value
        final_delta = "—"
        for d in reversed(delta_hist):
            if d is not None:
                final_delta = f"{d:.4e}"
                break
        rows.append(SimpleNamespace(
            rpm=rpm,
            converged=converged,
            cycles=converged_at if converged_at is not None else len(delta_hist),
            final_delta=final_delta,
        ))
    return rows


def _build_perf_rows(perf_data: list[dict]) -> list[SimpleNamespace]:
    """Convert perf dicts to SimpleNamespace for template dot-access."""
    return [SimpleNamespace(**p) for p in perf_data]


def _build_rpm_detail_pages(
    perf_data: list[dict],
    results_by_rpm: dict,
    convergence: dict,
    engine_config: dict,
) -> list[SimpleNamespace]:
    """Build per-RPM detail page data with pre-rendered chart SVGs."""
    pages = []
    for p in perf_data:
        rpm = p["rpm"]
        rpm_key = str(rpm)

        results = results_by_rpm.get(rpm_key, results_by_rpm.get(str(float(rpm)), {}))
        conv = convergence.get(rpm_key, convergence.get(str(float(rpm)), {}))

        # Render charts (each function handles empty data gracefully)
        cylinder_svgs = report_charts.render_cylinder_traces(results) if results.get("cylinder_data") else []
        pv_svg = report_charts.render_pv_diagrams(results, engine_config) if results.get("cylinder_data") else ""
        pipe_svgs = report_charts.render_pipe_traces(results) if results.get("pipe_probes") else []
        plenum_svg = report_charts.render_plenum_chart(results) if results.get("plenum_pressure") else ""
        restrictor_svg = report_charts.render_restrictor_chart(results) if results.get("restrictor_mdot") else ""

        delta_hist = conv.get("delta_history", [])
        p_ivc_hist = conv.get("p_ivc_history", [])
        convergence_svgs = report_charts.render_convergence_detail(delta_hist, p_ivc_hist) if delta_hist else []

        pages.append(SimpleNamespace(
            rpm=rpm,
            cylinder_svgs=cylinder_svgs,
            pv_svg=pv_svg,
            pipe_svgs=pipe_svgs,
            plenum_svg=plenum_svg,
            restrictor_svg=restrictor_svg,
            convergence_svgs=convergence_svgs,
        ))
    return pages


def generate_report(sweep_data: dict) -> bytes:
    """Generate a PDF report from sweep data (as loaded from the sweep JSON).

    Returns PDF bytes.
    """
    from weasyprint import HTML

    perf_data = sweep_data.get("perf", [])
    engine_config = sweep_data.get("engine_config", {})
    results_by_rpm = sweep_data.get("results_by_rpm", {})
    convergence = sweep_data.get("convergence", {})
    metadata = sweep_data.get("metadata", {})

    # Headline stats
    stats = _extract_headline_stats(perf_data)

    # Sweep date
    sweep_date = metadata.get("started_at", "Unknown")
    if "T" in sweep_date:
        sweep_date = sweep_date.replace("T", " ").split(".")[0] + " UTC"

    # Config name
    config_name = metadata.get("config_name", "Unknown")
    if config_name.endswith(".json"):
        config_name = config_name[:-5]

    # Sweep-level charts
    sweep_curve_svgs = report_charts.render_sweep_curves(perf_data)

    # Convergence overview
    convergence_overview_svg = ""
    if convergence:
        conv_for_overview = {
            float(k): v for k, v in convergence.items()
        }
        convergence_overview_svg = report_charts.render_convergence_overview(conv_for_overview)

    # Convergence table
    convergence_table = _build_convergence_table(convergence, perf_data)

    # Perf data table rows
    perf_rows = _build_perf_rows(perf_data)

    # Per-RPM detail pages
    rpm_detail_pages = _build_rpm_detail_pages(
        perf_data, results_by_rpm, convergence, engine_config,
    )

    # Render template
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,  # SVG output must not be escaped
    )
    template = env.get_template(_TEMPLATE_NAME)
    html_str = template.render(
        config_name=config_name,
        sweep_date=sweep_date,
        engine_config=SimpleNamespace(**_deep_namespace(engine_config)),
        perf_data=perf_rows,
        sweep_curve_svgs=sweep_curve_svgs,
        convergence_overview_svg=convergence_overview_svg,
        convergence_table=convergence_table,
        rpm_detail_pages=rpm_detail_pages,
        **stats,
    )

    # Convert to PDF
    return HTML(string=html_str).write_pdf()


def _deep_namespace(d):
    """Recursively convert dicts to allow dot-access in Jinja2 templates.

    Returns a dict whose values are SimpleNamespace (for nested dicts)
    or lists of SimpleNamespace (for lists of dicts). Primitive values
    are left as-is. The caller wraps the top-level result.
    """
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = SimpleNamespace(**_deep_namespace(v))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            out[k] = [SimpleNamespace(**_deep_namespace(item)) for item in v]
        elif isinstance(v, list) and v and isinstance(v[0], list):
            # cd_table is list of [float, float] — leave as-is
            out[k] = v
        else:
            out[k] = v
    return out
```

- [ ] **Step 4: Run the tests**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_report.py -v`

Expected: Both tests PASS. The PDF bytes should start with `%PDF-`.

Note: This test requires the saved sweep file at `sweeps/2026-04-10T03-47-56_2500-15000_step1000_12cyc.json` and may take 10-30 seconds due to matplotlib chart rendering + WeasyPrint PDF generation.

- [ ] **Step 5: Commit**

```bash
git add engine_simulator/gui/report.py tests/test_report.py
git commit -m "feat: add report generation module (data extraction + Jinja2 + WeasyPrint)"
```

---

### Task 6: API Endpoint

**Files:**
- Modify: `engine_simulator/gui/routes_api.py:162-178` (add after existing endpoints)
- Create: `tests/test_report_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_endpoint.py`:

```python
"""Tests for the PDF report download endpoint."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """Create a test client with routes patched to use tmp dirs."""
    from engine_simulator.gui.routes_api import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    # Copy the small sweep file to tmp
    import shutil
    sweep_src = os.path.join(
        os.path.dirname(__file__), "..", "sweeps",
        "2026-04-10T03-47-56_2500-15000_step1000_12cyc.json",
    )
    shutil.copy(sweep_src, tmp_path / "2026-04-10T03-47-56_2500-15000_step1000_12cyc.json")

    with patch("engine_simulator.gui.routes_api.get_sweeps_dir", return_value=str(tmp_path)):
        yield TestClient(app)


def test_report_endpoint_returns_pdf(client):
    resp = client.get("/api/sweeps/2026-04-10T03-47-56_2500-15000_step1000_12cyc/report")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


def test_report_endpoint_404_for_missing_sweep(client):
    resp = client.get("/api/sweeps/nonexistent-sweep/report")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_report_endpoint.py -v`

Expected: FAIL — endpoint does not exist (404 on both tests, or the second might accidentally pass).

- [ ] **Step 3: Add the endpoint to routes_api.py**

Add the following at the end of `engine_simulator/gui/routes_api.py` (after the `get_current_sweep_results` endpoint):

```python
@router.get("/sweeps/{sweep_id}/report")
async def download_report(sweep_id: str):
    import json
    from fastapi.responses import Response
    from engine_simulator.gui.report import generate_report

    sweeps_dir = Path(get_sweeps_dir())
    file_path = sweeps_dir / f"{sweep_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Sweep not found: {sweep_id}")

    with open(file_path) as f:
        sweep_data = json.load(f)

    pdf_bytes = generate_report(sweep_data)

    config_name = sweep_data.get("metadata", {}).get("config_name", "report")
    if config_name.endswith(".json"):
        config_name = config_name[:-5]
    filename = f"{config_name}_{sweep_id}_report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run the tests**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/test_report_endpoint.py -v`

Expected: Both tests PASS.

- [ ] **Step 5: Run all tests to check for regressions**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/ -v --timeout=120`

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add engine_simulator/gui/routes_api.py tests/test_report_endpoint.py
git commit -m "feat: add GET /api/sweeps/{sweep_id}/report endpoint for PDF download"
```

---

### Task 7: Frontend — Download Report Button

**Files:**
- Modify: `gui-frontend/src/api/client.ts:102-141` (add downloadReport to api object)
- Modify: `gui-frontend/src/components/TopBar.tsx` (add button)

- [ ] **Step 1: Add downloadReport to the API client**

In `gui-frontend/src/api/client.ts`, add this function to the `api` object (after the `saveConfigAs` entry, before the closing `};`):

```typescript
  downloadReport: async (sweepId: string): Promise<void> => {
    const response = await fetch(
      `${BASE}/api/sweeps/${encodeURIComponent(sweepId)}/report`,
    );
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (body.detail) detail = body.detail;
      } catch {
        // body wasn't JSON (it's a PDF)
      }
      throw new Error(detail);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `report_${sweepId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  },
```

- [ ] **Step 2: Add the Download Report button to TopBar**

In `gui-frontend/src/components/TopBar.tsx`:

First, add the `FileDown` import to the lucide-react import line (line 1):

```typescript
import { Play, Square, FolderOpen, FileDown, Loader2 } from "lucide-react";
```

Then add state for the download loading state. Inside the `TopBar` function, after the existing `const hasSweep = ...` line (line 23), add:

```typescript
  const [downloading, setDownloading] = useState(false);
  const sweepId = sweep?.sweep_id ?? null;
  const canDownload = sweep?.status === "complete" && !downloading;

  const handleDownloadReport = async () => {
    if (!sweepId) return;
    setDownloading(true);
    try {
      await api.downloadReport(sweepId);
    } catch (e) {
      console.error("Failed to download report", e);
    } finally {
      setDownloading(false);
    }
  };
```

Add the `useState` import — update line 1 area:

```typescript
import { useState } from "react";
```

Wait — `useState` is not currently imported in TopBar.tsx. Add it.

Then add the button in the primary action cluster (after the Load button, before the closing `</div>` of the action cluster at line 104). Insert before line 104:

```tsx
        <button
          type="button"
          onClick={handleDownloadReport}
          disabled={!canDownload}
          className={[
            "inline-flex items-center gap-1.5 h-8 pl-2 pr-2.5 rounded border border-border-default",
            "text-[11px] font-medium uppercase tracking-[0.14em] leading-none",
            "transition-colors duration-150 ease-out",
            !canDownload
              ? "text-text-muted cursor-not-allowed"
              : "text-text-secondary hover:bg-surface-raised hover:border-border-emphasis hover:text-text-primary",
          ].join(" ")}
          aria-label="Download PDF report"
        >
          {downloading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.8} />
          ) : (
            <FileDown className="w-3.5 h-3.5" strokeWidth={1.8} />
          )}
          <span>Report</span>
        </button>
```

- [ ] **Step 3: Build the frontend**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build`

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add gui-frontend/src/api/client.ts gui-frontend/src/components/TopBar.tsx
git commit -m "feat: add Download Report button to TopBar"
```

---

### Task 8: Rebuild Static Bundle and End-to-End Test

**Files:**
- Modify: `gui-frontend/dist/` (rebuild)

- [ ] **Step 1: Rebuild the frontend dist**

Run: `cd /Users/nmurray/Developer/1d/gui-frontend && npm run build`

Expected: Build succeeds. The `dist/` folder is updated.

- [ ] **Step 2: Start the server and test manually**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m engine_simulator.gui`

In the browser:
1. Load a saved sweep from the sidebar
2. Verify the "Report" button in the TopBar becomes enabled (non-grayed)
3. Click it
4. Verify a PDF file downloads
5. Open the PDF and check: cover page, config tables, 6 sweep charts, perf table, convergence summary, appendix detail pages

- [ ] **Step 3: Run all tests one final time**

Run: `cd /Users/nmurray/Developer/1d && .venv/bin/python -m pytest tests/ -v --timeout=120`

Expected: All PASS.

- [ ] **Step 4: Commit the dist bundle**

```bash
git add gui-frontend/dist/
git commit -m "build: rebuild frontend dist with report button"
```
