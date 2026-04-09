"""0D plenum model and coupled restrictor-plenum boundary condition.

The RestrictorPlenumBC class implements an implicit Newton-Raphson solve at
each time step to find the plenum pressure that satisfies mass conservation:

    mdot_restrictor(p_plen) = sum(mdot_runner_i(p_plen)) + dM_plenum/dt

This provides stable, physically correct coupling between the restrictor,
plenum, and intake runners.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.gas_dynamics.gas_properties import (
    A_REF,
    GAMMA_REF,
    P_REF,
    R_AIR,
    RHO_REF,
    T_REF,
    AA_from_p_T,
    A_from_pressure,
    density_from_A_AA,
)

if TYPE_CHECKING:
    from engine_simulator.boundaries.restrictor import RestrictorBC
    from engine_simulator.gas_dynamics.pipe import Pipe


class RestrictorPlenumBC:
    """Coupled restrictor-plenum-runner boundary condition.

    At each time step, solves for the plenum pressure p_plen such that:
        F(p_plen) = mdot_restrictor(p_plen)
                    - sum_i(mdot_runner_i(p_plen))
                    - (V_plen / (R * T_plen * dt)) * (p_plen - p_plen_old)
                  = 0

    The last term is the plenum capacitance: mass storage from pressure change.
    """

    def __init__(
        self,
        restrictor: RestrictorBC,
        runner_pipes: list[Pipe],
        plenum_volume: float,
        p_ambient: float = P_REF,
        T_ambient: float = T_REF,
        gamma: float = GAMMA_REF,
    ):
        self.restrictor = restrictor
        self.runners = runner_pipes
        self.volume = plenum_volume
        self.p_ambient = p_ambient
        self.T_ambient = T_ambient
        self.gamma = gamma

        # Plenum state
        self.p = p_ambient
        self.T = T_ambient
        self.m = p_ambient * plenum_volume / (R_AIR * T_ambient)

        # Monitoring
        self.last_mdot_restrictor = 0.0
        self.last_choked = False

    def solve_and_apply(self, dt: float):
        """Solve the coupled restrictor-plenum-runner system and set BCs.

        With the corrected (A, AA, T) Benson relations, AA at the runner inlet
        must reflect the actual plenum entropy state, NOT be forced to 1.

        Steps:
        1. Compute the plenum entropy parameter AA_plen from (T_plen, p_plen).
           For warm sub-atmospheric gas (the real plenum after the restrictor),
           AA_plen > 1.
        2. Newton-Raphson on p_plen for the residual
              mdot_restrictor − Σ mdot_runner − dM_plen/dt = 0
           using AA_plen for the runner-side density / sound speed (so the
           inflow gas IS the plenum gas, not a fictional isentropic state).
        3. Set lambda[0] at each runner so A[0] = A_j = AA_plen·(p_plen/p_ref)^k
           and set AA[0] = AA_plen. After update_derived this gives
              p[0] = p_plen,  T[0] = T_plen,  ρ[0] = p_plen / (R · T_plen).
        4. Update plenum mass + thermal-relaxation T toward ambient.
        """
        gam = self.gamma
        gm1 = gam - 1.0
        n = len(self.runners)

        # --- Plenum entropy parameter (computed from current plenum state) ---
        T_plen_safe = max(self.T, 200.0)
        AA_plen = float(AA_from_p_T(self.p, T_plen_safe, gam))

        # Collect incoming Riemann invariants from each runner LEFT end
        betas = np.zeros(n)
        areas = np.zeros(n)
        for i, pipe in enumerate(self.runners):
            betas[i] = pipe.bet[0]
            areas[i] = pipe.area[0]

        p_old = self.p
        # Plenum capacitance: C = V / (R · T) → dM/dt = C · dp/dt
        capacitance = self.volume / (R_AIR * T_plen_safe)
        C_coeff = capacitance / max(dt, 1e-10)  # kg/s per Pa

        # Newton-Raphson on p_plen
        p_plen = p_old

        for iteration in range(20):
            mdot_r, dmdot_r_dp = self.restrictor.compute_mass_flow_and_derivative(p_plen)

            mdot_runners_total = 0.0
            dmdot_runners_dp = 0.0

            for i in range(n):
                A_j = A_from_pressure(p_plen, AA_plen, gam)
                # At LEFT end with beta arriving: U = 2·(A_j − β)/(γ−1)
                U_i = 2.0 * (A_j - betas[i]) / gm1
                u_i = U_i * A_REF
                rho_i = float(
                    density_from_A_AA(
                        np.array([A_j]), np.array([AA_plen]), gam
                    )[0]
                )
                mdot_i = rho_i * u_i * areas[i]
                mdot_runners_total += mdot_i

                # d/dp_plen of mdot_i — chain through A_j(p_plen)
                dA_dp = A_j * gm1 / (2.0 * gam * max(p_plen, 1.0))
                dU_dp = 2.0 / gm1 * dA_dp
                du_dp = dU_dp * A_REF
                # ρ = ρ_ref · (A/AA)^(2γ/(γ-1)) / A²
                # dρ/dA at fixed AA simplifies to ρ · ( (2γ/(γ-1))/A − 2/A )
                #                              = ρ · (2/((γ-1)·A))
                drho_dA = rho_i * 2.0 / (gm1 * max(A_j, 1e-6))
                drho_dp = drho_dA * dA_dp
                dmdot_i_dp = (drho_dp * u_i + rho_i * du_dp) * areas[i]
                dmdot_runners_dp += dmdot_i_dp

            residual = mdot_r - mdot_runners_total - C_coeff * (p_plen - p_old)
            jacobian = dmdot_r_dp - dmdot_runners_dp - C_coeff

            if abs(jacobian) < 1e-20:
                break

            dp = -residual / jacobian
            dp = max(-0.2 * p_plen, min(dp, 0.2 * p_plen))
            p_plen += dp
            p_plen = max(p_plen, 1e4)
            p_plen = min(p_plen, self.p_ambient * 1.01)

            if abs(residual) < 1e-5:
                break

        # --- Apply BC at each runner LEFT end ---
        # With AA[0] = AA_plen and A[0] = A_j_final, update_derived produces
        # the correct (p, T, ρ) for the plenum gas — no longer the isentropic
        # fiction the old AA[0]=1 line forced.
        A_j_final = A_from_pressure(p_plen, AA_plen, gam)
        for i, pipe in enumerate(self.runners):
            pipe.lam[0] = 2.0 * A_j_final - betas[i]
            pipe.AA[0] = AA_plen

        # --- Final mass-flow tally for plenum state update ---
        mdot_r_final, _ = self.restrictor.compute_mass_flow_and_derivative(p_plen)
        rho_final = float(
            density_from_A_AA(
                np.array([A_j_final]), np.array([AA_plen]), gam
            )[0]
        )
        mdot_out_final = 0.0
        for i in range(n):
            U_i = 2.0 * (A_j_final - betas[i]) / gm1
            u_i = U_i * A_REF
            mdot_out_final += rho_final * u_i * areas[i]

        dm = (mdot_r_final - mdot_out_final) * dt
        self.m = max(self.m + dm, capacitance * 1e4)
        self.p = p_plen

        # Temperature: relax toward ambient (walls + fresh charge from restrictor).
        # Restrictor flow is essentially isenthalpic for an ideal gas, so the
        # gas crossing the throat keeps its upstream T ≈ T_ambient.
        tau_thermal = 0.005
        alpha = min(dt / tau_thermal, 0.5)
        self.T = (1.0 - alpha) * self.T + alpha * self.T_ambient
        self.T = max(self.T, 250.0)

        self.last_mdot_restrictor = mdot_r_final
        self.last_choked = self.restrictor.is_choked(p_plen)
