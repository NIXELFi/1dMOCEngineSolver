"""Mesh Method of Characteristics solver for 1D unsteady compressible flow.

Implements the Benson non-dimensional Riemann variable formulation with
non-homentropic source terms (friction, heat transfer, area change).
"""

from __future__ import annotations

import numpy as np

from engine_simulator.gas_dynamics.gas_properties import (
    A_REF,
    GAMMA_REF,
    P_REF,
    RHO_REF,
    T_REF,
    dynamic_viscosity,
    friction_factor_blasius,
)
from engine_simulator.gas_dynamics.pipe import Pipe


def _interpolate_at(arr: np.ndarray, x_foot: float, dx: float, n_points: int) -> float:
    """Linear interpolation of array value at position x_foot."""
    idx_f = x_foot / dx
    j = int(np.floor(idx_f))
    j = max(0, min(j, n_points - 2))
    theta = idx_f - j
    theta = max(0.0, min(1.0, theta))
    return (1.0 - theta) * arr[j] + theta * arr[j + 1]


def extrapolate_boundary_incoming(pipe: Pipe, dt: float):
    """Extrapolate incoming Riemann variables at boundaries from interior.

    At the LEFT boundary (i=0):
      C- arrives from interior (dx/dt = u-a < 0 for subsonic).
      Trace backward to find bet[0] from the interior.

    At the RIGHT boundary (i=n-1):
      C+ arrives from interior (dx/dt = u+a > 0 for subsonic).
      Trace backward to find lam[-1] from the interior.

    Also extrapolates AA along C0 at both boundaries.
    """
    n = pipe.n_points
    dx = pipe.dx

    # --- LEFT boundary (i=0): incoming C- (beta) ---
    u0, a0 = pipe.u[0], pipe.a[0]
    # C- foot: x_foot = x[0] - (u-a)*dt = -(u-a)*dt = (a-u)*dt
    x_foot_L = -(u0 - a0) * dt  # positive for subsonic flow
    x_foot_L = max(0.0, min(x_foot_L, pipe.length))
    pipe.bet[0] = _interpolate_at(pipe.bet, x_foot_L, dx, n)

    # Entropy along C0: x_foot = x[0] - u*dt
    x_foot_S0 = -u0 * dt
    x_foot_S0 = max(0.0, min(x_foot_S0, pipe.length))
    pipe.AA[0] = _interpolate_at(pipe.AA, x_foot_S0, dx, n)

    # --- RIGHT boundary (i=n-1): incoming C+ (lambda) ---
    un, an = pipe.u[-1], pipe.a[-1]
    # C+ foot: x_foot = x[-1] - (u+a)*dt
    x_foot_R = pipe.length - (un + an) * dt
    x_foot_R = max(0.0, min(x_foot_R, pipe.length))
    pipe.lam[-1] = _interpolate_at(pipe.lam, x_foot_R, dx, n)

    # Entropy along C0 at right end
    x_foot_Sn = pipe.length - un * dt
    x_foot_Sn = max(0.0, min(x_foot_Sn, pipe.length))
    pipe.AA[-1] = _interpolate_at(pipe.AA, x_foot_Sn, dx, n)


def advance_interior_points(
    pipe: Pipe, dt: float, include_sources: bool = True,
    artificial_viscosity: float = 0.0,
):
    """Advance all interior grid points by dt using the MOC algorithm.

    For each interior point i at time level n+1:
    1. Trace C+, C-, C0 characteristics back to time level n
    2. Interpolate Riemann variables at foot points
    3. Apply compatibility equations with source terms
    4. Optionally add an artificial-viscosity / Laplacian-smoothing term to
       damp under-resolved standing waves (the 1D Benson MOC has no built-in
       mechanism to capture the ~3D acoustic absorption a real plenum
       provides; without it, runner standing waves at the closed-valve end
       grow to unphysical amplitudes).
    5. Store new values

    This modifies pipe.lam, pipe.bet, pipe.AA for interior points only.
    Boundary points (i=0, i=n_points-1) are handled by boundary conditions.

    Args:
        artificial_viscosity: dimensionless coefficient ν·dt/dx² for the
            second-derivative smoothing applied to lam, bet, AA. Acts as
            numerical damping; ~0.05 is mild, ~0.2 is aggressive. Stability
            requires ν·dt/dx² ≤ 0.5 for the explicit diffusion update.
            0.0 disables damping.
    """
    gam = pipe.gamma
    n = pipe.n_points
    if n <= 2:
        return

    gm1 = gam - 1.0
    gm1_2 = gm1 / 2.0

    # Current state (time level n)
    lam_old = pipe.lam.copy()
    bet_old = pipe.bet.copy()
    AA_old = pipe.AA.copy()
    A_old = pipe.A_nd.copy()
    U_old = pipe.U_nd.copy()
    u_old = pipe.u.copy()
    a_old = pipe.a.copy()
    rho_old = pipe.rho.copy()
    T_old = pipe.T.copy()

    dx = pipe.dx

    new_lam = pipe.lam.copy()
    new_bet = pipe.bet.copy()
    new_AA = pipe.AA.copy()

    for i in range(1, n - 1):
        # Step 1: Locate foot points at time level n
        # C+ foot: x_R = x_i - (u + a) * dt
        x_R = pipe.x[i] - (u_old[i] + a_old[i]) * dt
        # C- foot: x_L = x_i - (u - a) * dt
        x_L = pipe.x[i] - (u_old[i] - a_old[i]) * dt
        # C0 foot: x_S = x_i - u * dt
        x_S = pipe.x[i] - u_old[i] * dt

        # Clamp to pipe bounds
        x_R = max(0.0, min(x_R, pipe.length))
        x_L = max(0.0, min(x_L, pipe.length))
        x_S = max(0.0, min(x_S, pipe.length))

        # Step 2: Interpolate at foot points
        lam_R = _interpolate_at(lam_old, x_R, dx, n)
        bet_L = _interpolate_at(bet_old, x_L, dx, n)
        AA_S = _interpolate_at(AA_old, x_S, dx, n)

        if not include_sources:
            # Homentropic, inviscid, constant-area: Riemann invariants carried unchanged
            new_lam[i] = lam_R
            new_bet[i] = bet_L
            new_AA[i] = AA_S
            continue

        # Interpolate flow variables at foot points for source evaluation
        A_R = _interpolate_at(A_old, x_R, dx, n)
        U_R = _interpolate_at(U_old, x_R, dx, n)
        rho_R = _interpolate_at(rho_old, x_R, dx, n)
        T_R = _interpolate_at(T_old, x_R, dx, n)
        AA_R = _interpolate_at(AA_old, x_R, dx, n)
        area_R = _interpolate_at(pipe.area, x_R, dx, n)
        dAdx_R = _interpolate_at(pipe.dAdx, x_R, dx, n)
        D_R = _interpolate_at(pipe.diameter, x_R, dx, n)

        A_L = _interpolate_at(A_old, x_L, dx, n)
        U_L = _interpolate_at(U_old, x_L, dx, n)
        rho_L = _interpolate_at(rho_old, x_L, dx, n)
        T_L = _interpolate_at(T_old, x_L, dx, n)
        AA_L = _interpolate_at(AA_old, x_L, dx, n)
        area_L = _interpolate_at(pipe.area, x_L, dx, n)
        dAdx_L = _interpolate_at(pipe.dAdx, x_L, dx, n)
        D_L = _interpolate_at(pipe.diameter, x_L, dx, n)

        A_S = _interpolate_at(A_old, x_S, dx, n)
        U_S = _interpolate_at(U_old, x_S, dx, n)
        rho_S = _interpolate_at(rho_old, x_S, dx, n)
        T_S = _interpolate_at(T_old, x_S, dx, n)
        area_S = _interpolate_at(pipe.area, x_S, dx, n)
        D_S = _interpolate_at(pipe.diameter, x_S, dx, n)

        # Friction factor (Blasius)
        mu_R = dynamic_viscosity(T_R * T_REF / max(T_R, 0.01))
        # Actually T_R is already dimensional from pipe.T
        Re_R = rho_R * abs(U_R * A_REF) * D_R / dynamic_viscosity(T_R)
        f_R = float(friction_factor_blasius(np.array(max(Re_R, 1.0))))

        Re_L = rho_L * abs(U_L * A_REF) * D_L / dynamic_viscosity(T_L)
        f_L = float(friction_factor_blasius(np.array(max(Re_L, 1.0))))

        Re_S = rho_S * abs(U_S * A_REF) * D_S / dynamic_viscosity(T_S)
        f_S = float(friction_factor_blasius(np.array(max(Re_S, 1.0))))

        # Wall heat transfer
        T_wall = pipe.wall_temperature
        Nu_R = 0.023 * max(Re_R, 1.0) ** 0.8 * 0.71**0.4
        k_R = 0.026 * (T_R / 300.0) ** 0.7
        h_R = Nu_R * k_R / D_R
        qw_R = h_R * (T_R - T_wall)

        Nu_L = 0.023 * max(Re_L, 1.0) ** 0.8 * 0.71**0.4
        k_L = 0.026 * (T_L / 300.0) ** 0.7
        h_L = Nu_L * k_L / D_L
        qw_L = h_L * (T_L - T_wall)

        Nu_S = 0.023 * max(Re_S, 1.0) ** 0.8 * 0.71**0.4
        k_S = 0.026 * (T_S / 300.0) ** 0.7
        h_S = Nu_S * k_S / D_S
        qw_S = h_S * (T_S - T_wall)

        # Source terms for C+ (at R foot point)
        A_safe_R = max(A_R, 1e-6)
        friction_R = f_R * A_REF * U_R * abs(U_R) / (2.0 * D_R)
        heat_R = gm1 * qw_R * np.pi * D_R / (rho_R * area_R * A_safe_R * A_REF * A_REF)
        area_src_R = A_safe_R * U_R * dAdx_R * A_REF / max(area_R, 1e-12)

        dlam_source = gm1_2 * (
            -(1.0 + U_R / A_safe_R) * friction_R
            + heat_R
            - area_src_R
        ) * dt

        # Entropy correction for C+ (dA_A term)
        # dA_A along C0 from entropy generation
        AA_safe_R = max(AA_R, 1e-6)
        dAA_R = AA_safe_R * gm1 / (2.0 * A_safe_R**2) * (
            gm1 * qw_R * np.pi * D_R / (rho_R * area_R * A_REF**2)
            + f_R * abs(U_R)**2 * U_R * A_REF / (2.0 * D_R)  # Note: U_R^2 * |U_R| but need sign care
        ) * dt
        # Simplified: just use entropy from C0 path
        lam_correction = (A_R / AA_safe_R) * dAA_R if abs(dAA_R) > 0 else 0.0

        # Source terms for C- (at L foot point)
        A_safe_L = max(A_L, 1e-6)
        friction_L = f_L * A_REF * U_L * abs(U_L) / (2.0 * D_L)
        heat_L = gm1 * qw_L * np.pi * D_L / (rho_L * area_L * A_safe_L * A_REF * A_REF)
        area_src_L = A_safe_L * U_L * dAdx_L * A_REF / max(area_L, 1e-12)

        dbet_source = gm1_2 * (
            +(1.0 - U_L / A_safe_L) * friction_L
            + heat_L
            + area_src_L
        ) * dt

        AA_safe_L = max(AA_L, 1e-6)
        dAA_L = AA_safe_L * gm1 / (2.0 * A_safe_L**2) * (
            gm1 * qw_L * np.pi * D_L / (rho_L * area_L * A_REF**2)
            + f_L * abs(U_L)**2 * U_L * A_REF / (2.0 * D_L)
        ) * dt
        bet_correction = (A_L / AA_safe_L) * dAA_L if abs(dAA_L) > 0 else 0.0

        # Source terms for C0 (entropy, at S foot point)
        A_safe_S = max(A_S, 1e-6)
        AA_safe_S = max(AA_S, 1e-6)
        dAA_source = AA_safe_S * gm1 / (2.0 * A_safe_S**2) * (
            gm1 * qw_S * np.pi * D_S / (rho_S * area_S * A_REF**2)
            + f_S * abs(U_S) * U_S**2 * A_REF / (2.0 * D_S)
        ) * dt

        # Step 3: Apply compatibility equations
        new_lam[i] = lam_R + dlam_source + lam_correction
        new_bet[i] = bet_L + dbet_source + bet_correction
        new_AA[i] = AA_S + dAA_source

    # Optional artificial viscosity (Laplacian smoothing) for runner standing
    # waves. Applied to lam and bet AFTER the characteristic update so it acts
    # as a small numerical diffusion of high-wavenumber content. Without this
    # term, the closed-end (valve) standing-wave amplitude grows unphysically
    # because 1D MOC has no native acoustic absorption.
    if artificial_viscosity > 0.0 and n > 2:
        nu = artificial_viscosity
        new_lam[1:-1] += nu * (lam_old[2:] - 2.0 * lam_old[1:-1] + lam_old[:-2])
        new_bet[1:-1] += nu * (bet_old[2:] - 2.0 * bet_old[1:-1] + bet_old[:-2])

    # Update pipe state
    pipe.lam[1:-1] = new_lam[1:-1]
    pipe.bet[1:-1] = new_bet[1:-1]
    pipe.AA[1:-1] = new_AA[1:-1]

    # Enforce minimum values to prevent negative pressure/temperature
    pipe.lam = np.maximum(pipe.lam, 0.01)
    pipe.bet = np.maximum(pipe.bet, 0.01)
    pipe.AA = np.maximum(pipe.AA, 0.01)

    pipe.update_derived()
