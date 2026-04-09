"""Issue 4 — multi-RPM comparison of intake runner 1 midpoint pressure
and velocity at 6750, 8000, 9000, 10000 RPM.

Recorded at the runner 1 midpoint over the last (recording) cycle of each
run. Output: a single PNG with two stacked subplots (pressure on top,
velocity on bottom), one trace per RPM, plus a small per-RPM stats table
printed to stdout.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

os.environ["MPLBACKEND"] = "Agg"
sys.stdout.reconfigure(line_buffering=True)

import matplotlib.pyplot as plt

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator


RPMS = [6750, 8000, 9000, 10000]
COLORS = {6750: "#1f77b4", 8000: "#2ca02c", 9000: "#ff7f0e", 10000: "#d62728"}


def main() -> None:
    cfg = EngineConfig()
    runs = []
    for rpm in RPMS:
        sim = SimulationOrchestrator(cfg)
        t0 = time.time()
        perf = sim.run_single_rpm(rpm, n_cycles=8, verbose=False)
        elapsed = time.time() - t0
        probe = sim.results.get_pipe_probe_arrays("intake_runner_1")
        if not probe:
            print(f"  ERROR: no probe data for {rpm} RPM", flush=True)
            continue
        theta_deg = probe["theta"] % 720.0
        order = np.argsort(theta_deg)
        theta_sorted = theta_deg[order]
        p_sorted = probe["pressure"][order] / 1e5
        u_sorted = probe["velocity"][order]
        runs.append({
            "rpm": rpm,
            "theta": theta_sorted,
            "p": p_sorted,
            "u": u_sorted,
            "ve_atm": perf["volumetric_efficiency_atm"],
            "ve_plen": perf["volumetric_efficiency_plenum"],
            "p_plen": perf["plenum_pressure_bar"],
            "power_hp": perf["indicated_power_hp"],
            "imep": perf["imep_bar"],
        })
        print(
            f"  {rpm:>5d} RPM done in {elapsed:5.1f}s  "
            f"VE_atm={perf['volumetric_efficiency_atm']*100:5.1f}%  "
            f"P_ind={perf['indicated_power_hp']:5.1f} hp  "
            f"p_plen={perf['plenum_pressure_bar']:.3f} bar",
            flush=True,
        )

    if not runs:
        print("No runs succeeded — aborting plot.")
        return

    # --- Plot ---
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    for r in runs:
        axes[0].plot(
            r["theta"], r["p"],
            color=COLORS[r["rpm"]], linewidth=1.0,
            label=f"{r['rpm']} RPM (VE_atm={r['ve_atm']*100:.0f}%, p_plen={r['p_plen']:.2f} bar)",
        )
        axes[1].plot(
            r["theta"], r["u"],
            color=COLORS[r["rpm"]], linewidth=1.0,
            label=f"{r['rpm']} RPM",
        )

    axes[0].axhline(1.0, color="k", linestyle=":", alpha=0.3, label="atmospheric")
    axes[0].set_ylabel("Runner 1 midpoint pressure (bar)")
    axes[0].set_title("Issue 4: Intake runner 1 midpoint, multi-RPM comparison")
    axes[0].legend(fontsize=8, loc="upper left", ncol=2)
    axes[0].grid(True, alpha=0.3)

    axes[1].axhline(0.0, color="k", linestyle=":", alpha=0.3)
    axes[1].set_ylabel("Runner 1 midpoint velocity (m/s)")
    axes[1].set_xlabel("Crank angle (degrees, mod 720)")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = "/Users/nmurray/Developer/1d/_plot_review/07_issue4_multi_rpm_runner1.png"
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    print(f"\nSaved {out_path}")

    # --- Stats table ---
    print("\nPer-RPM runner 1 midpoint stats:")
    print(f"{'RPM':>6} {'p_min':>8} {'p_max':>8} {'p_mean':>8} {'u_min':>8} {'u_max':>8} {'u_mean':>8} {'VE_atm':>8} {'P_ind':>8}")
    for r in runs:
        p, u = r["p"], r["u"]
        print(
            f"{r['rpm']:>6d} {p.min():8.3f} {p.max():8.3f} {p.mean():8.3f} "
            f"{u.min():8.1f} {u.max():8.1f} {u.mean():8.1f} "
            f"{r['ve_atm']*100:7.1f}% {r['power_hp']:7.1f}"
        )

    # Comment on which RPM has best recovery
    best_rpm = max(runs, key=lambda r: r["p"].mean())["rpm"]
    print(
        f"\nHighest mean midpoint pressure (best wave-tuning recovery): "
        f"{best_rpm} RPM",
    )


if __name__ == "__main__":
    main()
