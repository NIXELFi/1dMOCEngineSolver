"""Acoustic resonance validation — closed-open pipe natural frequencies.

A pipe closed at one end and open at the other has resonant frequencies:
    f_n = (2n - 1) * c / (4L)   for n = 1, 2, 3, ...

The MOC solver should capture these frequencies when an initial pressure
perturbation is applied and the response is analyzed via FFT.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.gas_dynamics.gas_properties import (
    A_REF, GAMMA_REF, P_REF, R_AIR, T_REF,
)
from engine_simulator.gas_dynamics.moc_solver import advance_interior_points, extrapolate_boundary_incoming
from engine_simulator.gas_dynamics.pipe import Pipe
from engine_simulator.boundaries.closed_end import ClosedEndBC
from engine_simulator.boundaries.open_end import OpenEndBC
from engine_simulator.boundaries.base import PipeEnd


def run_acoustic_resonance(
    pipe_length: float = 0.5,
    pipe_diameter: float = 0.04,
    n_points: int = 100,
    t_end: float = 0.05,
    perturbation: float = 0.05,
    cfl: float = 0.85,
    T_ambient: float = 300.0,
    plot: bool = True,
) -> dict:
    """Run acoustic resonance test on a closed-open pipe.

    Applies a pressure perturbation near the closed end and records
    pressure history. FFT of the signal should show peaks at the pipe's
    natural frequencies.

    Args:
        pipe_length: Length of the pipe (m)
        pipe_diameter: Diameter (m)
        n_points: Grid points
        t_end: Simulation time (s)
        perturbation: Fractional pressure perturbation at closed end
        cfl: CFL number
        T_ambient: Ambient temperature (K)
        plot: Whether to plot results

    Returns:
        Dict with frequencies, amplitudes, and analytical comparisons.
    """
    print("=" * 60)
    print("Acoustic Resonance Test (Closed-Open Pipe)")
    print(f"  L = {pipe_length:.3f} m, D = {pipe_diameter*1000:.0f} mm")
    print(f"  Grid: {n_points} points, CFL = {cfl}")

    c = np.sqrt(GAMMA_REF * R_AIR * T_ambient)
    print(f"  Speed of sound: {c:.1f} m/s")

    # Analytical frequencies
    f_analytical = [(2 * n - 1) * c / (4 * pipe_length) for n in range(1, 6)]
    print(f"  Analytical resonant frequencies (Hz):")
    for n, f in enumerate(f_analytical, 1):
        print(f"    f_{n} = {f:.1f} Hz")

    # Create pipe
    pipe = Pipe(
        name="resonance_test",
        length=pipe_length,
        diameter=pipe_diameter,
        n_points=n_points,
        wall_temperature=T_ambient,
    )
    pipe.initialize(p=P_REF, T=T_ambient)

    # Apply initial perturbation: pressure step in first 20% of pipe
    gam = GAMMA_REF
    for i in range(n_points):
        x = pipe.x[i]
        frac = x / pipe_length
        if frac < 0.2:
            p_local = P_REF * (1.0 + perturbation * (1.0 - frac / 0.2))
        else:
            p_local = P_REF

        a_local = np.sqrt(gam * R_AIR * T_ambient)
        # Isentropic: a/a_ref = (p/p_ref)^((gamma-1)/(2*gamma))
        A = (p_local / P_REF) ** ((gam - 1.0) / (2.0 * gam))
        pipe.lam[i] = A + 0.5 * (gam - 1) * 0.0  # U = 0
        pipe.bet[i] = A - 0.5 * (gam - 1) * 0.0
        pipe.AA[i] = 1.0

    pipe.update_derived()

    # Boundary conditions
    bc_closed = ClosedEndBC()
    bc_open = OpenEndBC(p_atm=P_REF, T_atm=T_ambient)

    # Time integration with pressure recording at closed end
    t = 0.0
    step = 0
    t_history = []
    p_history = []  # pressure at closed end (x=0)

    while t < t_end:
        dt = cfl * pipe.local_cfl_dt()
        dt = min(dt, t_end - t)

        extrapolate_boundary_incoming(pipe, dt)
        bc_closed.apply(pipe, PipeEnd.LEFT, dt)
        bc_open.apply(pipe, PipeEnd.RIGHT, dt)
        advance_interior_points(pipe, dt, include_sources=False)

        t += dt
        step += 1

        t_history.append(t)
        p_history.append(pipe.p[0])

    print(f"  Completed in {step} steps")

    # FFT analysis
    t_arr = np.array(t_history)
    p_arr = np.array(p_history)
    p_fluct = p_arr - np.mean(p_arr)

    # Interpolate to uniform time spacing for FFT
    n_uniform = len(t_arr)
    dt_uniform = t_end / n_uniform
    t_uniform = np.linspace(0, t_end, n_uniform)
    p_uniform = np.interp(t_uniform, t_arr, p_fluct)

    # Apply window to reduce spectral leakage
    window = np.hanning(n_uniform)
    p_windowed = p_uniform * window

    N = len(t_uniform)
    fft_vals = np.fft.rfft(p_windowed)
    freqs = np.fft.rfftfreq(N, dt_uniform)
    amplitude = 2.0 / N * np.abs(fft_vals)

    # Find peaks (above 5% of max)
    threshold = 0.05 * np.max(amplitude[1:])  # skip DC
    peak_indices = []
    for i in range(2, len(amplitude) - 1):
        if (amplitude[i] > amplitude[i - 1] and amplitude[i] > amplitude[i + 1]
                and amplitude[i] > threshold):
            peak_indices.append(i)

    detected_freqs = freqs[peak_indices] if peak_indices else np.array([])

    if len(detected_freqs) > 0:
        print(f"  Detected frequency peaks (Hz): {', '.join(f'{f:.0f}' for f in detected_freqs[:5])}")
    else:
        print(f"  No clear peaks detected (max amplitude = {np.max(amplitude[1:]):.2e})")

    # Compare with analytical
    errors = []
    for f_anal in f_analytical[:min(3, len(detected_freqs))]:
        if len(detected_freqs) > 0:
            closest = detected_freqs[np.argmin(np.abs(detected_freqs - f_anal))]
            err = abs(closest - f_anal) / f_anal * 100
            errors.append(err)
            print(f"    f = {f_anal:.0f} Hz: detected {closest:.0f} Hz, error = {err:.1f}%")

    result = {
        "t": t_arr,
        "p_closed_end": p_arr,
        "freqs": freqs,
        "amplitude": amplitude,
        "f_analytical": f_analytical,
        "f_detected": detected_freqs,
        "errors_pct": errors,
    }

    if plot:
        try:
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(14, 5))

            axes[0].plot(t_arr * 1000, (p_arr - P_REF) / P_REF * 100, "b-", linewidth=0.8)
            axes[0].set_xlabel("Time (ms)")
            axes[0].set_ylabel("Pressure fluctuation (%)")
            axes[0].set_title("Pressure at Closed End")
            axes[0].grid(True, alpha=0.3)

            axes[1].plot(freqs, amplitude, "b-", linewidth=1)
            for f in f_analytical[:5]:
                axes[1].axvline(f, color="r", linestyle="--", alpha=0.5, label=f"{f:.0f} Hz")
            axes[1].set_xlabel("Frequency (Hz)")
            axes[1].set_ylabel("Amplitude")
            axes[1].set_title("FFT Spectrum")
            max_freq = f_analytical[4] * 1.5 if len(f_analytical) > 4 else 5000
            axes[1].set_xlim(0, max_freq)
            axes[1].legend(fontsize=8)
            axes[1].grid(True, alpha=0.3)

            fig.suptitle(f"Acoustic Resonance -- L={pipe_length}m, {n_points} points", fontsize=13)
            plt.tight_layout()
            plt.show()
        except ImportError:
            print("  (matplotlib not available for plotting)")

    return result
