"""Full RPM sweep + dashboard plot regeneration with the final tuned settings.

Runs the configured rpm_start..rpm_end range, captures every dashboard plot
into _plot_review/, and prints a summary table for the user.
"""
from __future__ import annotations

import os
import sys
import time

os.environ["MPLBACKEND"] = "Agg"
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.postprocessing.visualization import (
    plot_cylinder_pressure,
    plot_pipe_pressure,
    plot_pv_diagram,
    plot_restrictor_flow,
    plot_rpm_sweep,
    plot_dashboard,
)

OUT = Path("_plot_review")
OUT.mkdir(exist_ok=True)

_state = {"i": 0, "next_name": "plot"}


def name_next(n: str) -> None:
    _state["next_name"] = n


def _save_show(*args, **kwargs):
    _state["i"] += 1
    fig = plt.gcf()
    path = OUT / f"{_state['i']:02d}_{_state['next_name']}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    print(f"  -> {path}")
    plt.close(fig)


plt.show = _save_show


def main() -> None:
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

    # === Validation plots (re-run with final solver state) ===
    print("=== Validation: shock tube ===")
    from engine_simulator.validation.shock_tube import run_shock_tube
    name_next("shock_tube")
    run_shock_tube(n_points=200, t_end=0.0006, plot=True)

    print("=== Validation: acoustic resonance ===")
    from engine_simulator.validation.acoustic_resonance import run_acoustic_resonance
    name_next("acoustic_resonance")
    run_acoustic_resonance(pipe_length=0.5, n_points=100, t_end=0.02, plot=True)

    # === Single-RPM probes at 10000 RPM ===
    print("\n=== Single RPM @ 10 000 (8 cycles) ===")
    sim = SimulationOrchestrator(cfg)
    t0 = time.time()
    perf = sim.run_single_rpm(10000.0, n_cycles=8, verbose=True)
    print(
        f"\n  result: {perf['indicated_power_hp']:.1f} hp ind, "
        f"{perf['brake_power_hp']:.1f} hp brake, "
        f"VE_atm={perf['volumetric_efficiency_atm']*100:.1f}%, "
        f"p_plen={perf['plenum_pressure_bar']:.3f} bar, "
        f"IMEP={perf['imep_bar']:.2f} bar  ({time.time()-t0:.1f}s)"
    )

    name_next("cylinder_pressure_10000")
    plot_cylinder_pressure(sim.results, cyl_id=0, title="Cylinder 1 Pressure @ 10000 RPM")

    name_next("pipe_pressure_intake_runner_1")
    plot_pipe_pressure(sim.results, "intake_runner_1")

    name_next("restrictor_flow")
    plot_restrictor_flow(sim.results)

    name_next("pv_diagram")
    plot_pv_diagram(sim.results, sim.cylinders[0].geometry, cyl_id=0)

    # Save the single-RPM sim object so the dashboard can read it later
    single_sim = sim

    # === Full RPM sweep ===
    rpms = list(range(6000, 13001, 1000))
    print(f"\n=== Full RPM sweep: {rpms[0]}–{rpms[-1]} step 1000 (8 cycles each) ===")
    sweep_results = []
    sweep_sim = SimulationOrchestrator(cfg)
    for rpm in rpms:
        t0 = time.time()
        perf = sweep_sim.run_single_rpm(float(rpm), n_cycles=8, verbose=False)
        elapsed = time.time() - t0
        sweep_results.append(perf)
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
        f"  (target 75 hp at 9000)"
    )
    print(
        f"Peak brake torque: {peak_t['brake_torque_Nm']:.1f} Nm at {peak_t['rpm']:.0f} RPM"
        f"  (spec 50 Nm at 8000)"
    )

    name_next("rpm_sweep")
    plot_rpm_sweep(sweep_results)

    name_next("dashboard")
    plot_dashboard(single_sim.results, sweep_results, geometry=single_sim.cylinders[0].geometry)

    # Multi-RPM runner comparison (re-uses _issue4_runner_compare logic but
    # we already have it as a separate plot 07; not regenerated here).

    print(f"\nTotal plots saved: {_state['i']}")
    print(f"Output dir: {OUT.resolve()}")


if __name__ == "__main__":
    main()
