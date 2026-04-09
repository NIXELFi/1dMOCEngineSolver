"""Capture all plots the simulator outputs to PNG for review."""
import os
os.environ["MPLBACKEND"] = "Agg"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pathlib import Path

OUT = Path("_plot_review")
OUT.mkdir(exist_ok=True)

_state = {"i": 0, "next_name": "plot"}


def name_next(n):
    _state["next_name"] = n


def _save_show(*args, **kwargs):
    _state["i"] += 1
    fig = plt.gcf()
    path = OUT / f"{_state['i']:02d}_{_state['next_name']}.png"
    fig.savefig(path, dpi=110, bbox_inches="tight")
    print(f"  -> {path}")
    plt.close(fig)


plt.show = _save_show


# === Validation plots ===
print("=== Validation ===")
from engine_simulator.validation.shock_tube import run_shock_tube
from engine_simulator.validation.acoustic_resonance import run_acoustic_resonance

name_next("shock_tube")
run_shock_tube(n_points=200, t_end=0.0006, plot=True)

name_next("acoustic_resonance")
run_acoustic_resonance(pipe_length=0.5, n_points=100, t_end=0.02, plot=True)

# === Single RPM plots ===
print("=== Single RPM @ 10000 (2 cycles) ===")
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.postprocessing.visualization import (
    plot_cylinder_pressure,
    plot_pipe_pressure,
    plot_pv_diagram,
    plot_rpm_sweep,
    plot_dashboard,
    plot_restrictor_flow,
)

config = EngineConfig()
sim = SimulationOrchestrator(config)
perf = sim.run_single_rpm(10000.0, n_cycles=12, verbose=False)
print(f"  result: {perf['indicated_power_hp']:.1f} hp ind, {perf['brake_power_hp']:.1f} hp brake")
print(f"  VE_plen={perf['volumetric_efficiency']*100:.1f}%, VE_atm={perf['volumetric_efficiency_atm']*100:.1f}%, p_plen={perf['plenum_pressure_bar']:.3f} bar")

name_next("cylinder_pressure_10000")
plot_cylinder_pressure(sim.results, cyl_id=0, title="Cylinder 1 Pressure @ 10000 RPM")

name_next("pipe_pressure_intake_runner_1")
plot_pipe_pressure(sim.results, "intake_runner_1")

name_next("restrictor_flow")
plot_restrictor_flow(sim.results)

name_next("pv_diagram")
try:
    plot_pv_diagram(sim.results, sim.cylinders[0].geometry, cyl_id=0)
except Exception as e:
    print(f"  PV diagram failed: {e}")

# === Full RPM sweep ===
print("=== RPM sweep 6000-13000 step 1000 (12 cycles) ===")
sim2 = SimulationOrchestrator(config)
sweep = sim2.run_rpm_sweep(rpm_start=6000, rpm_end=13000, rpm_step=1000, n_cycles=12, verbose=True)
print(f"  swept {len(sweep)} points")

name_next("rpm_sweep")
plot_rpm_sweep(sweep)

name_next("dashboard")
try:
    plot_dashboard(sim2.results, sweep, geometry=sim2.cylinders[0].geometry)
except Exception as e:
    print(f"  Dashboard failed: {e}")

print(f"\nTotal plots saved: {_state['i']}")
print(f"Output dir: {OUT.resolve()}")
