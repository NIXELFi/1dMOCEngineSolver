"""Main entry point for the 1D Engine CFD Simulator.

Usage:
    python -m engine_simulator.main [command] [options]

Commands:
    validate    Run validation tests (shock tube, acoustic resonance)
    single      Run simulation at a single RPM
    sweep       Run full RPM sweep
    all         Run validation + sweep + visualization

Examples:
    python -m engine_simulator.main validate
    python -m engine_simulator.main single --rpm 10000
    python -m engine_simulator.main sweep --rpm-start 6000 --rpm-end 13000 --rpm-step 1000
    python -m engine_simulator.main all
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np


def run_validation(plot: bool = True):
    """Run Tier 1 validation tests."""
    from engine_simulator.validation.shock_tube import run_shock_tube
    from engine_simulator.validation.acoustic_resonance import run_acoustic_resonance

    print("\n" + "=" * 60)
    print("TIER 1 VALIDATION TESTS")
    print("=" * 60)

    # Test 1: Sod's shock tube
    shock_result = run_shock_tube(n_points=200, t_end=0.0006, plot=plot)
    print(f"  Shock tube pressure error: {shock_result['p_error_pct']:.2f}%")

    # Test 2: Acoustic resonance
    acoustic_result = run_acoustic_resonance(
        pipe_length=0.5, n_points=100, t_end=0.02, plot=plot
    )
    if acoustic_result["errors_pct"]:
        avg_err = np.mean(acoustic_result["errors_pct"])
        print(f"  Acoustic resonance avg frequency error: {avg_err:.1f}%")

    return shock_result, acoustic_result


def run_single_rpm(rpm: float = 10000.0, n_cycles: int = 12, plot: bool = True):
    """Run simulation at a single RPM."""
    from engine_simulator.config.engine_config import EngineConfig
    from engine_simulator.simulation.orchestrator import SimulationOrchestrator

    print(f"\nRunning single RPM simulation at {rpm:.0f} RPM...")
    config = EngineConfig()
    sim = SimulationOrchestrator(config)
    perf = sim.run_single_rpm(rpm, n_cycles=n_cycles, verbose=True)

    print(f"\n--- Results at {rpm:.0f} RPM ---")
    print(f"  Indicated Power:  {perf['indicated_power_hp']:.1f} hp ({perf['indicated_power_kW']:.1f} kW)")
    print(f"  Brake Power:      {perf['brake_power_hp']:.1f} hp ({perf['brake_power_kW']:.1f} kW)")
    print(f"  Indicated Torque: {perf['indicated_torque_Nm']:.1f} Nm")
    print(f"  Brake Torque:     {perf['brake_torque_Nm']:.1f} Nm")
    print(f"  IMEP / BMEP:      {perf['imep_bar']:.2f} / {perf['bmep_bar']:.2f} bar  (FMEP {perf['fmep_bar']:.2f})")
    print(f"  VE (plenum ref):  {perf['volumetric_efficiency']*100:.1f}%")
    print(f"  VE (atm ref):     {perf['volumetric_efficiency_atm']*100:.1f}%")
    print(f"  Plenum Pressure:  {perf['plenum_pressure_bar']:.3f} bar")
    print(f"  Restrictor Choked: {'Yes' if perf['restrictor_choked'] else 'No'}")
    print(f"  Restrictor Mass Flow: {perf['restrictor_mdot']*1000:.1f} g/s")

    if plot:
        try:
            from engine_simulator.postprocessing.visualization import (
                plot_cylinder_pressure,
                plot_pipe_pressure,
            )
            plot_cylinder_pressure(sim.results, cyl_id=0,
                                    title=f"Cylinder 1 Pressure @ {rpm:.0f} RPM")
            plot_pipe_pressure(sim.results, "intake_runner_1")
        except ImportError:
            print("  (matplotlib not available for plotting)")

    return perf, sim


def run_rpm_sweep(
    rpm_start: float = 6000.0, rpm_end: float = 13000.0, rpm_step: float = 1000.0,
    n_cycles: int = 12, plot: bool = True,
    n_workers=None, quiet: bool = False,
):
    """Run RPM sweep and generate performance curves."""
    from engine_simulator.config.engine_config import EngineConfig
    from engine_simulator.simulation.orchestrator import SimulationOrchestrator

    print(f"\nRunning RPM sweep: {rpm_start:.0f} to {rpm_end:.0f}, step {rpm_step:.0f}")
    config = EngineConfig()
    sim = SimulationOrchestrator(config)
    sweep = sim.run_rpm_sweep(
        rpm_start=rpm_start, rpm_end=rpm_end, rpm_step=rpm_step,
        n_cycles=n_cycles, verbose=not quiet,
        n_workers=n_workers,
    )

    if plot:
        try:
            from engine_simulator.postprocessing.visualization import plot_rpm_sweep
            plot_rpm_sweep(sweep)
        except ImportError:
            print("  (matplotlib not available for plotting)")

    return sweep, sim


def main():
    parser = argparse.ArgumentParser(
        description="1D Engine CFD Simulator — Honda CBR600RR (FSAE)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command", nargs="?", default="all",
        choices=["validate", "single", "sweep", "all"],
        help="Command to run (default: all)",
    )
    parser.add_argument("--rpm", type=float, default=10000.0, help="RPM for single-point run")
    parser.add_argument("--rpm-start", type=float, default=6000.0, help="Sweep start RPM")
    parser.add_argument("--rpm-end", type=float, default=13000.0, help="Sweep end RPM")
    parser.add_argument("--rpm-step", type=float, default=1000.0, help="Sweep RPM step")
    parser.add_argument("--cycles", type=int, default=12, help="Number of engine cycles")
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting")
    parser.add_argument(
        "--workers", type=int, default=None,
        help="Number of parallel worker processes for RPM sweep. "
             "Default: min(cpu_count, n_rpm_points). "
             "Use --workers 1 to force the original sequential solver path.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-cycle progress events during the sweep. "
             "The final summary table is still printed.",
    )

    args = parser.parse_args()
    do_plot = not args.no_plot

    print("=" * 60)
    print("1D Engine CFD Simulator")
    print("Method of Characteristics — Benson Formulation")
    print("Target: Honda CBR600RR 599cc I4 with FSAE 20mm Restrictor")
    print("=" * 60)

    t_start = time.time()

    if args.command in ("validate", "all"):
        run_validation(plot=do_plot)

    if args.command in ("single",):
        run_single_rpm(rpm=args.rpm, n_cycles=args.cycles, plot=do_plot)

    if args.command in ("sweep", "all"):
        sweep, sim = run_rpm_sweep(
            rpm_start=args.rpm_start, rpm_end=args.rpm_end,
            rpm_step=args.rpm_step, n_cycles=args.cycles, plot=do_plot,
            n_workers=args.workers, quiet=args.quiet,
        )

        # Validation against published data
        if args.command == "all":
            from engine_simulator.validation.known_engine import validate_against_published
            validate_against_published(sweep, verbose=True)

    elapsed = time.time() - t_start
    print(f"\nTotal simulation time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
