"""Open end (atmosphere) boundary condition.

Handles both outflow (gas exits to atmosphere) and inflow (atmosphere enters pipe)
using pressure matching and stagnation conditions respectively.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.boundaries.base import BoundaryCondition, PipeEnd
from engine_simulator.gas_dynamics.gas_properties import (
    A_REF, GAMMA_REF, P_REF, T_REF,
    A_from_pressure,
)
from engine_simulator.gas_dynamics.pipe import Pipe


class OpenEndBC(BoundaryCondition):
    """Atmosphere boundary condition for pipe open ends.

    Outflow: pressure at exit = atmospheric.
    Inflow: stagnation conditions from atmosphere.
    """

    def __init__(self, p_atm: float = P_REF, T_atm: float = T_REF, gamma: float = GAMMA_REF):
        self.p_atm = p_atm
        self.T_atm = T_atm
        self.gamma = gamma

        # Non-dimensional atmospheric speed of sound
        self.A_atm = A_from_pressure(p_atm, AA=1.0, gamma=gamma)
        # Stagnation A for inflow
        a_atm = np.sqrt(gamma * (P_REF / (P_REF / (287.0 * T_REF))) * T_atm / T_REF) / A_REF
        # Simpler: A_stag based on stagnation temperature
        self.A0 = np.sqrt(T_atm / T_REF)  # A at stagnation, AA=1

    def apply(self, pipe: Pipe, end: PipeEnd, dt: float, **kwargs):
        idx = self.get_index(end)
        gam = self.gamma
        gm1 = gam - 1.0

        if end == PipeEnd.RIGHT:
            # C+ arrives from interior: lambda is known
            lam_in = pipe.lam[idx]
            AA = pipe.AA[idx]

            # Estimate velocity to determine flow direction
            A_est = (lam_in + pipe.bet[idx]) / 2.0
            U_est = (lam_in - pipe.bet[idx]) / (gam - 1.0)

            if U_est >= 0:
                # Outflow: match pressure to atmospheric
                # p = p_atm -> A = A_atm (for AA=1)
                A_boundary = A_from_pressure(self.p_atm, AA, gam)
                beta_new = 2.0 * A_boundary - lam_in * (gm1 / (gm1))
                # More precisely: A = (lam + beta)/2, so beta = 2*A - lam
                beta_new = 2.0 * A_boundary - lam_in
                pipe.bet[idx] = beta_new
                pipe.lam[idx] = lam_in
            else:
                # Inflow: stagnation conditions
                # A0^2 = A^2 + (gamma-1)/2 * U^2 (non-dimensional stagnation)
                A0 = self.A0 * AA  # adjust for entropy level
                # Known: beta from interior... wait, at RIGHT end, lambda arrives.
                # For inflow at right end (reversed flow), we need to solve:
                # A = (lam + beta)/2, U = (lam - beta)/(gamma-1)
                # A0^2 = A^2 + (gamma-1)/2 * U^2
                # And lam is the incoming characteristic
                # Newton-Raphson on beta:
                beta_guess = pipe.bet[idx]
                for _ in range(20):
                    A = (lam_in + beta_guess) / 2.0
                    U = (lam_in - beta_guess) / gm1
                    A0_calc = np.sqrt(A**2 + gm1 / 2.0 * U**2) if A**2 + gm1 / 2.0 * U**2 > 0 else A
                    residual = A0_calc - A0
                    # d(residual)/d(beta)
                    dA_db = 0.5
                    dU_db = -1.0 / gm1
                    if A0_calc > 1e-10:
                        dres_db = (A * dA_db + gm1 / 2.0 * U * dU_db) / A0_calc
                    else:
                        dres_db = 1.0
                    if abs(dres_db) < 1e-15:
                        break
                    beta_guess -= residual / dres_db
                    if abs(residual) < 1e-10:
                        break
                pipe.bet[idx] = beta_guess
                pipe.AA[idx] = 1.0  # fresh air from atmosphere

        else:
            # LEFT end: C- arrives from interior: beta is known
            bet_in = pipe.bet[idx]
            AA = pipe.AA[idx]

            A_est = (pipe.lam[idx] + bet_in) / 2.0
            U_est = (pipe.lam[idx] - bet_in) / (gam - 1.0)

            if U_est <= 0:
                # Outflow (flow exits through left end)
                A_boundary = A_from_pressure(self.p_atm, AA, gam)
                lam_new = 2.0 * A_boundary - bet_in
                pipe.lam[idx] = lam_new
                pipe.bet[idx] = bet_in
            else:
                # Inflow from atmosphere through left end
                A0 = self.A0 * AA
                lam_guess = pipe.lam[idx]
                for _ in range(20):
                    A = (lam_guess + bet_in) / 2.0
                    U = (lam_guess - bet_in) / gm1
                    A0_calc = np.sqrt(max(A**2 + gm1 / 2.0 * U**2, 0.0))
                    residual = A0_calc - A0
                    dA_dl = 0.5
                    dU_dl = 1.0 / gm1
                    if A0_calc > 1e-10:
                        dres_dl = (A * dA_dl + gm1 / 2.0 * U * dU_dl) / A0_calc
                    else:
                        dres_dl = 1.0
                    if abs(dres_dl) < 1e-15:
                        break
                    lam_guess -= residual / dres_dl
                    if abs(residual) < 1e-10:
                        break
                pipe.lam[idx] = lam_guess
                pipe.AA[idx] = 1.0
