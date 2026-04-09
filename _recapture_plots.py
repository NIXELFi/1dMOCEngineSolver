"""Re-capture the single-RPM dashboard plots after the Issue 0 fix.
Skips the full sweep + dashboard which takes 20+ minutes; just rebuilds
plots 03-06 in _plot_review/ for direct comparison with the user's
original snapshots.
"""
import os
os.environ["MPLBACKEND"] = "Agg"

import sys
sys.stdout.reconfigure(line_buffering=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pathlib import Path

OUT = Path("_plot_review")
OUT.mkdir(exist_ok=True)

_state = {"i": 2, "next_name": "plot"}  # start at 03 (3, 4, 5, 6)

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

print("=== Single RPM @ 10000 (8 cycles) ===")
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.postprocessing.visualization import (
    plot_cylinder_pressure,
    plot_pipe_pressure,
    plot_pv_diagram,
    plot_restrictor_flow,
)

config = EngineConfig()
sim = SimulationOrchestrator(config)
perf = sim.run_single_rpm(10000.0, n_cycles=8, verbose=True)
print(
    f"\n  result: {perf['indicated_power_hp']:.1f} hp ind, "
    f"{perf['brake_power_hp']:.1f} hp brake, "
    f"VE_atm={perf['volumetric_efficiency_atm']*100:.1f}%, "
    f"VE_plen={perf['volumetric_efficiency']*100:.1f}%, "
    f"p_plen={perf['plenum_pressure_bar']:.3f} bar, "
    f"IMEP={perf['imep_bar']:.2f} bar"
)

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

print(f"\nTotal plots saved: {_state['i'] - 2}")
print(f"Output dir: {OUT.resolve()}")
