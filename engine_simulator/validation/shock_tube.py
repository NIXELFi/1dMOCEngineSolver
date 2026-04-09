"""Sod's shock tube problem — Tier 1 analytical validation.

Exact solution exists for comparison. Tests the MOC solver's ability to
capture expansion fans and contact discontinuities in 1D compressible flow.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.gas_dynamics.gas_properties import (
    A_REF, GAMMA_REF, P_REF, R_AIR, T_REF,
)
from engine_simulator.gas_dynamics.moc_solver import advance_interior_points, extrapolate_boundary_incoming
from engine_simulator.gas_dynamics.pipe import Pipe
from engine_simulator.boundaries.closed_end import ClosedEndBC
from engine_simulator.boundaries.base import PipeEnd


def _solve_p_star(p_L, rho_L, a_L, p_R, rho_R, a_R, gamma):
    """Iteratively solve for post-wave pressure p_star using Newton-Raphson."""
    gam = gamma
    gp1 = gam + 1.0
    gm1 = gam - 1.0

    # Initial guess (linearized)
    p_star = 0.5 * (p_L + p_R)

    for _ in range(100):
        # Left side: expansion wave
        f_L = (2.0 * a_L / gm1) * ((p_star / p_L) ** (gm1 / (2.0 * gam)) - 1.0)
        df_L = (a_L / (gam * p_L)) * (p_star / p_L) ** (-(gp1) / (2.0 * gam))

        # Right side: shock wave
        A_R = 2.0 / (gp1 * rho_R)
        B_R = gm1 / gp1 * p_R
        sqrt_term = np.sqrt(A_R / (p_star + B_R))
        f_R = (p_star - p_R) * sqrt_term
        df_R = sqrt_term * (1.0 - 0.5 * (p_star - p_R) / (p_star + B_R))

        f = f_L + f_R + (a_R / gam - a_L / gam) * 0  # u_R - u_L = 0
        f = f_L + f_R
        df = df_L + df_R

        if abs(df) < 1e-30:
            break
        dp = -f / df
        p_star += dp
        p_star = max(p_star, 1e-6)

        if abs(dp / p_star) < 1e-10:
            break

    return p_star


def sod_exact_solution(x, t, x0, p_L, rho_L, u_L, p_R, rho_R, u_R, gamma=1.4):
    """Exact solution to the Riemann problem with arbitrary left/right states.

    All inputs in dimensional (SI) units. Returns dimensional arrays.
    """
    gam = gamma
    gp1 = gam + 1.0
    gm1 = gam - 1.0

    a_L = np.sqrt(gam * p_L / rho_L)
    a_R = np.sqrt(gam * p_R / rho_R)

    # Solve for p_star
    p_star = _solve_p_star(p_L, rho_L, a_L, p_R, rho_R, a_R, gam)

    # Contact velocity
    u_star = u_L + (2.0 * a_L / gm1) * (1.0 - (p_star / p_L) ** (gm1 / (2.0 * gam)))

    # Post-shock density (right of contact)
    pr_ratio = p_star / p_R
    rho_star_R = rho_R * (pr_ratio + gm1 / gp1) / (gm1 / gp1 * pr_ratio + 1.0)

    # Post-expansion density (left of contact)
    rho_star_L = rho_L * (p_star / p_L) ** (1.0 / gam)

    # Sound speed behind expansion
    a_star_L = np.sqrt(gam * p_star / rho_star_L)

    # Wave speeds
    s_shock = u_R + a_R * np.sqrt(gm1 / (2.0 * gam) + gp1 / (2.0 * gam) * p_star / p_R)

    # Positions at time t
    x_head = x0 + (u_L - a_L) * t  # head of expansion fan (leftward)
    x_tail = x0 + (u_star - a_star_L) * t  # tail of expansion fan
    x_contact = x0 + u_star * t  # contact discontinuity
    x_shock = x0 + s_shock * t  # shock front

    # Build solution
    rho = np.zeros_like(x)
    p = np.zeros_like(x)
    u = np.zeros_like(x)

    for i, xi in enumerate(x):
        if xi < x_head:
            rho[i], p[i], u[i] = rho_L, p_L, u_L
        elif xi < x_tail:
            # Inside expansion fan
            c_ratio = (2.0 / gp1) + (gm1 / (gp1 * a_L)) * (u_L - (xi - x0) / t)
            c_ratio = max(c_ratio, 1e-10)
            u[i] = (2.0 / gp1) * (a_L + gm1 / 2.0 * u_L + (xi - x0) / t)
            rho[i] = rho_L * c_ratio ** (2.0 / gm1)
            p[i] = p_L * c_ratio ** (2.0 * gam / gm1)
        elif xi < x_contact:
            rho[i], p[i], u[i] = rho_star_L, p_star, u_star
        elif xi < x_shock:
            rho[i], p[i], u[i] = rho_star_R, p_star, u_star
        else:
            rho[i], p[i], u[i] = rho_R, p_R, u_R

    return {"x": x, "rho": rho, "p": p, "u": u}


def run_shock_tube(
    n_points: int = 200,
    t_end: float = 0.0006,
    p_left: float = 3.0e5,
    rho_left: float = 3.0,
    p_right: float = 1.0e5,
    rho_right: float = 1.25,
    tube_length: float = 1.0,
    cfl: float = 0.85,
    plot: bool = True,
) -> dict:
    """Run shock tube problem and compare to exact solution.

    Uses Sod-style primary inputs: pressure and density on each side of the
    diaphragm. Temperature follows from the ideal gas law, so the sound
    speeds on the two sides differ and the Riemann variables lambda/beta
    carry a genuine jump across the diaphragm (required for the MOC interior
    advance to see any initial gradient). Default values are a 3:1 pressure
    ratio variant of the canonical Sod problem
    (rho_L/rho_R = 2.4, T_L approx 348 K, T_R approx 279 K).

    Args:
        n_points: Number of grid points
        t_end: Simulation end time (s)
        p_left: Left state pressure (Pa)
        rho_left: Left state density (kg/m^3)
        p_right: Right state pressure (Pa)
        rho_right: Right state density (kg/m^3)
        tube_length: Tube length (m)
        cfl: CFL number
        plot: Whether to plot results

    Returns:
        Dict with numerical and exact solutions + error metrics.
    """
    gam = GAMMA_REF
    R = R_AIR

    # Temperature from ideal gas law
    T_left = p_left / (rho_left * R)
    T_right = p_right / (rho_right * R)

    print("=" * 60)
    print("Shock Tube Problem")
    print(f"  Grid: {n_points} points, CFL = {cfl}")
    print(f"  Left:  p = {p_left/1e5:.2f} bar, rho = {rho_left:.3f} kg/m^3, T = {T_left:.0f} K")
    print(f"  Right: p = {p_right/1e5:.2f} bar, rho = {rho_right:.3f} kg/m^3, T = {T_right:.0f} K")
    print(f"  t_end = {t_end*1e6:.0f} us")

    # Create pipe
    pipe = Pipe(
        name="shock_tube",
        length=tube_length,
        diameter=0.05,
        n_points=n_points,
        wall_temperature=293.0,
    )

    # Initialize: left half at (p_left, T_left), right half at (p_right, T_right).
    # Use the same Benson convention as Pipe.initialize:
    #   A  = a / A_REF             (nondim sound speed)
    #   U  = u / A_REF             (nondim velocity, zero here)
    #   AA = A * (P_REF/p)^((g-1)/(2g))    (entropy level)
    #   lam = A + (g-1)/2 * U,  bet = A - (g-1)/2 * U
    mid = n_points // 2

    for i in range(n_points):
        if i < mid:
            p, T = p_left, T_left
        else:
            p, T = p_right, T_right

        a = np.sqrt(gam * R * T)
        A = a / A_REF
        U = 0.0
        AA = A * (P_REF / p) ** ((gam - 1.0) / (2.0 * gam))

        pipe.lam[i] = A + 0.5 * (gam - 1.0) * U
        pipe.bet[i] = A - 0.5 * (gam - 1.0) * U
        pipe.AA[i] = AA

    pipe.update_derived()

    # Boundary conditions: closed ends
    bc_left = ClosedEndBC()
    bc_right = ClosedEndBC()

    # Time integration
    t = 0.0
    step = 0
    while t < t_end:
        dt = cfl * pipe.local_cfl_dt()
        dt = min(dt, t_end - t)

        extrapolate_boundary_incoming(pipe, dt)
        bc_left.apply(pipe, PipeEnd.LEFT, dt)
        bc_right.apply(pipe, PipeEnd.RIGHT, dt)
        advance_interior_points(pipe, dt, include_sources=False)

        t += dt
        step += 1

    print(f"  Completed in {step} steps, final t = {t*1e6:.1f} us")

    # Compute exact solution (dimensional)
    x0 = tube_length / 2.0
    exact = sod_exact_solution(
        pipe.x, t_end, x0,
        p_L=p_left, rho_L=rho_left, u_L=0.0,
        p_R=p_right, rho_R=rho_right, u_R=0.0,
        gamma=gam,
    )

    p_exact = exact["p"]
    rho_exact = exact["rho"]
    u_exact = exact["u"]

    # Error metrics (exclude 10% near boundaries and discontinuities)
    margin = int(0.05 * n_points)
    interior = slice(margin, n_points - margin)
    p_err = np.sqrt(np.mean((pipe.p[interior] - p_exact[interior]) ** 2)) / np.mean(p_exact[interior]) * 100

    print(f"  Pressure RMS error: {p_err:.2f}%")

    result = {
        "x": pipe.x,
        "p_numerical": pipe.p.copy(),
        "rho_numerical": pipe.rho.copy(),
        "u_numerical": pipe.u.copy(),
        "p_exact": p_exact,
        "rho_exact": rho_exact,
        "u_exact": u_exact,
        "p_error_pct": p_err,
        "n_steps": step,
    }

    if plot:
        try:
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(15, 5))

            axes[0].plot(pipe.x, pipe.p / 1e5, "b-", label="MOC", linewidth=1.5)
            axes[0].plot(pipe.x, p_exact / 1e5, "r--", label="Exact", linewidth=1)
            axes[0].set_xlabel("Position (m)")
            axes[0].set_ylabel("Pressure (bar)")
            axes[0].legend()
            axes[0].set_title("Pressure")
            axes[0].grid(True, alpha=0.3)

            axes[1].plot(pipe.x, pipe.rho, "b-", label="MOC", linewidth=1.5)
            axes[1].plot(pipe.x, rho_exact, "r--", label="Exact", linewidth=1)
            axes[1].set_xlabel("Position (m)")
            axes[1].set_ylabel("Density (kg/m^3)")
            axes[1].legend()
            axes[1].set_title("Density")
            axes[1].grid(True, alpha=0.3)

            axes[2].plot(pipe.x, pipe.u, "b-", label="MOC", linewidth=1.5)
            axes[2].plot(pipe.x, u_exact, "r--", label="Exact", linewidth=1)
            axes[2].set_xlabel("Position (m)")
            axes[2].set_ylabel("Velocity (m/s)")
            axes[2].legend()
            axes[2].set_title("Velocity")
            axes[2].grid(True, alpha=0.3)

            fig.suptitle(f"Shock Tube -- {n_points} points, CFL={cfl}", fontsize=13)
            plt.tight_layout()
            plt.show()
        except ImportError:
            print("  (matplotlib not available for plotting)")

    return result
