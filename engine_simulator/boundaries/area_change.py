"""Area change boundary conditions (sudden expansion/contraction).

For gradual area changes, the pipe itself handles varying F(x) via source terms.
This module handles sudden (discontinuous) area changes modeled as internal boundaries.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.gas_dynamics.gas_properties import (
    A_REF,
    GAMMA_REF,
    P_REF,
    A_from_pressure,
    density_from_A_AA,
)
from engine_simulator.gas_dynamics.pipe import Pipe


class SuddenAreaChangeBC:
    """Sudden area change between two pipes.

    Models the discontinuity as an internal boundary with loss coefficient.
    Mass conservation and stagnation enthalpy conservation are enforced.

    pipe_small connects at its end, pipe_large at its start (or vice versa).
    """

    def __init__(
        self,
        pipe_upstream: Pipe,
        end_upstream: PipeEnd,
        pipe_downstream: Pipe,
        end_downstream: PipeEnd,
        change_type: str = "expansion",  # or "contraction"
        gamma: float = GAMMA_REF,
    ):
        self.pipe_up = pipe_upstream
        self.end_up = end_upstream
        self.pipe_down = pipe_downstream
        self.end_down = end_downstream
        self.gamma = gamma

        idx_up = 0 if end_upstream == PipeEnd.LEFT else -1
        idx_down = 0 if end_downstream == PipeEnd.LEFT else -1
        A_small = min(pipe_upstream.area[idx_up], pipe_downstream.area[idx_down])
        A_large = max(pipe_upstream.area[idx_up], pipe_downstream.area[idx_down])
        area_ratio = A_small / A_large

        if change_type == "expansion":
            self.K_loss = (1.0 - area_ratio) ** 2
        else:
            self.K_loss = 0.5 * (1.0 - area_ratio)

    def apply(self, dt: float, **kwargs):
        """Apply sudden area change boundary using mass and energy conservation.

        Simplified approach: treat as a junction of 2 pipes with a loss.
        Iterate on junction pressure to satisfy mass conservation.
        """
        gam = self.gamma
        gm1 = gam - 1.0

        idx_up = 0 if self.end_up == PipeEnd.LEFT else -1
        idx_down = 0 if self.end_down == PipeEnd.LEFT else -1

        # Incoming Riemann invariants
        if self.end_up == PipeEnd.RIGHT:
            R_up = self.pipe_up.lam[idx_up]
        else:
            R_up = self.pipe_up.bet[idx_up]

        if self.end_down == PipeEnd.RIGHT:
            R_down = self.pipe_down.lam[idx_down]
        else:
            R_down = self.pipe_down.bet[idx_down]

        AA_up = self.pipe_up.AA[idx_up]
        AA_down = self.pipe_down.AA[idx_down]
        A_up_cross = self.pipe_up.area[idx_up]
        A_down_cross = self.pipe_down.area[idx_down]

        # Initial pressure guess
        p_j = 0.5 * (self.pipe_up.p[idx_up] + self.pipe_down.p[idx_down])

        for _ in range(20):
            # Upstream side
            A_j_up = A_from_pressure(p_j, AA_up, gam)
            if self.end_up == PipeEnd.RIGHT:
                U_up = 2.0 * (R_up - A_j_up) / gm1
            else:
                U_up = 2.0 * (A_j_up - R_up) / gm1

            u_up = U_up * A_REF
            rho_up = float(density_from_A_AA(np.array([A_j_up]), np.array([AA_up]), gam)[0])

            # Downstream side (with pressure loss)
            p_j_down = p_j - 0.5 * self.K_loss * rho_up * u_up**2
            p_j_down = max(p_j_down, 0.1 * P_REF)

            A_j_down = A_from_pressure(p_j_down, AA_down, gam)
            if self.end_down == PipeEnd.RIGHT:
                U_down = 2.0 * (R_down - A_j_down) / gm1
            else:
                U_down = 2.0 * (A_j_down - R_down) / gm1

            u_down = U_down * A_REF
            rho_down = float(density_from_A_AA(np.array([A_j_down]), np.array([AA_down]), gam)[0])

            # Mass residual
            mass_up = rho_up * u_up * A_up_cross
            mass_down = rho_down * u_down * A_down_cross
            residual = mass_up - mass_down

            if abs(residual) < 1e-6:
                break

            # Adjust pressure
            p_j += 0.1 * residual / max(abs(mass_up + mass_down), 1e-10) * p_j

        # Set reflected Riemann invariants
        A_j_up = A_from_pressure(p_j, AA_up, gam)
        if self.end_up == PipeEnd.RIGHT:
            self.pipe_up.bet[idx_up] = 2.0 * A_j_up - R_up
        else:
            self.pipe_up.lam[idx_up] = 2.0 * A_j_up - R_up

        A_j_down = A_from_pressure(p_j_down, AA_down, gam)
        if self.end_down == PipeEnd.RIGHT:
            self.pipe_down.bet[idx_down] = 2.0 * A_j_down - R_down
        else:
            self.pipe_down.lam[idx_down] = 2.0 * A_j_down - R_down
