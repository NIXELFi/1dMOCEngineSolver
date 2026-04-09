"""N-pipe junction boundary condition (constant-pressure model).

Assumes uniform pressure at the junction, with mass conservation
enforced via Newton-Raphson iteration.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.gas_dynamics.gas_properties import (
    A_REF,
    GAMMA_REF,
    P_REF,
    RHO_REF,
    T_REF,
    A_from_pressure,
    density_from_A_AA,
)
from engine_simulator.gas_dynamics.pipe import Pipe


class JunctionBC:
    """N-pipe junction boundary condition.

    All pipes share a common junction pressure. Mass conservation is
    enforced iteratively. Each pipe connects at either its LEFT or RIGHT end.

    Convention: sign = +1 means flow out of the pipe into the junction is positive.
    """

    def __init__(
        self,
        pipes: list[Pipe],
        ends: list[PipeEnd],
        signs: list[int] | None = None,
        gamma: float = GAMMA_REF,
    ):
        self.pipes = pipes
        self.ends = ends
        self.gamma = gamma
        self.n_pipes = len(pipes)

        # Sign convention: +1 if flow into junction is positive at this pipe end
        # Default: RIGHT end -> +1 (flow exits rightward into junction)
        #          LEFT end -> -1 (flow into junction requires leftward flow)
        if signs is None:
            self.signs = [1 if e == PipeEnd.RIGHT else -1 for e in ends]
        else:
            self.signs = signs

    def apply(self, dt: float, **kwargs):
        """Solve the junction boundary condition for all connected pipes.

        Algorithm:
        1. Guess p_junction from average of pipe-end pressures
        2. For each pipe: compute velocity from known Riemann invariant and p_junction
        3. Evaluate mass residual F = sum(rho_i * u_i * A_i * sign_i)
        4. Newton-Raphson iteration until |F| < tolerance
        5. Set reflected Riemann invariants
        """
        gam = self.gamma
        gm1 = gam - 1.0

        # Initial guess: average pressure at pipe ends
        p_sum = 0.0
        for i, (pipe, end) in enumerate(zip(self.pipes, self.ends)):
            idx = 0 if end == PipeEnd.LEFT else -1
            p_sum += pipe.p[idx]
        p_junction = p_sum / self.n_pipes

        # Collect incoming Riemann invariants and entropy levels
        riemann_in = []
        AA_vals = []
        areas = []
        for pipe, end in zip(self.pipes, self.ends):
            idx = 0 if end == PipeEnd.LEFT else -1
            if end == PipeEnd.RIGHT:
                riemann_in.append(pipe.lam[idx])  # lambda arrives at right end
            else:
                riemann_in.append(pipe.bet[idx])  # beta arrives at left end
            AA_vals.append(pipe.AA[idx])
            areas.append(pipe.area[idx])

        # Newton-Raphson iteration
        for iteration in range(30):
            mass_residual = 0.0
            d_residual_dp = 0.0

            for i in range(self.n_pipes):
                pipe = self.pipes[i]
                end = self.ends[i]
                sign = self.signs[i]
                AA = AA_vals[i]
                R_in = riemann_in[i]
                A_pipe = areas[i]

                # Compute A at junction pressure
                A_j = A_from_pressure(p_junction, AA, gam)

                if end == PipeEnd.RIGHT:
                    # lambda known: U = (lambda - beta)/(gamma-1)
                    # beta = 2*A - lambda
                    # Actually: A = (lambda + beta)/2, so beta = 2*A_j - ... no
                    # We need A at the boundary = A_j
                    # lambda = A + (gamma-1)/2 * U
                    # So U = (lambda - A_j) / ((gamma-1)/2) = 2*(lambda - A_j)/(gamma-1)
                    # Wait, that's not right either.
                    # A = (lam + beta)/2, U = (lam - beta)/(gamma-1)
                    # We know lam and want to impose A = A_j
                    # Then beta = 2*A_j - lam
                    # U = (lam - (2*A_j - lam))/(gamma-1) = (2*lam - 2*A_j)/(gamma-1)
                    U = 2.0 * (R_in - A_j) / gm1
                else:
                    # beta known: lambda = 2*A_j - beta
                    # U = ((2*A_j - beta) - beta)/(gamma-1) = 2*(A_j - beta)/(gamma-1)
                    U = 2.0 * (A_j - R_in) / gm1

                u = U * A_REF
                rho = density_from_A_AA(np.array([A_j]), np.array([AA]), gam)[0]

                mass_residual += sign * rho * u * A_pipe

                # Derivative: d(rho*u*A)/dp_junction
                # dA_j/dp = A_j * (gamma-1)/(2*gamma*p_junction)
                dA_dp = A_j * gm1 / (2.0 * gam * max(p_junction, 1.0))

                # d(rho)/dp = rho * 2/(gm1) * dA_dp/A_j = rho * 2/(gm1*A_j) * dA_dp
                # But we need d(rho)/dp via A: rho = rho_ref*(A/AA)^(2/gm1)
                # d(rho)/dA = rho * 2/(gm1*A)
                drho_dp = rho * 2.0 / (gm1 * max(A_j, 1e-6)) * dA_dp

                # dU/dp = -2/(gm1) * dA_dp (for RIGHT end) or 2/(gm1)*dA_dp (LEFT end)
                if end == PipeEnd.RIGHT:
                    dU_dp = -2.0 / gm1 * dA_dp
                else:
                    dU_dp = 2.0 / gm1 * dA_dp
                du_dp = dU_dp * A_REF

                d_residual_dp += sign * (drho_dp * u + rho * du_dp) * A_pipe

            if abs(d_residual_dp) < 1e-20:
                break

            dp = -mass_residual / d_residual_dp
            p_junction += dp

            # Clamp pressure to reasonable range
            p_junction = max(p_junction, 0.1 * P_REF)
            p_junction = min(p_junction, 10.0 * P_REF)

            if abs(mass_residual) < 1e-6:
                break

        # Set reflected Riemann invariants
        for i in range(self.n_pipes):
            pipe = self.pipes[i]
            end = self.ends[i]
            AA = AA_vals[i]
            idx = 0 if end == PipeEnd.LEFT else -1

            A_j = A_from_pressure(p_junction, AA, gam)

            if end == PipeEnd.RIGHT:
                pipe.bet[idx] = 2.0 * A_j - riemann_in[i]
            else:
                pipe.lam[idx] = 2.0 * A_j - riemann_in[i]

        # Handle entropy mixing at junction (simplified: mass-weighted)
        total_mass_in = 0.0
        entropy_sum = 0.0
        for i in range(self.n_pipes):
            idx = 0 if self.ends[i] == PipeEnd.LEFT else -1
            pipe = self.pipes[i]
            u = pipe.u[idx]
            sign = self.signs[i]
            if sign * u > 0:  # flow into junction
                mdot = pipe.rho[idx] * abs(u) * pipe.area[idx]
                total_mass_in += mdot
                entropy_sum += mdot * pipe.AA[idx]

        if total_mass_in > 1e-10:
            AA_mixed = entropy_sum / total_mass_in
            # Apply mixed entropy to pipes receiving flow from junction
            for i in range(self.n_pipes):
                idx = 0 if self.ends[i] == PipeEnd.LEFT else -1
                pipe = self.pipes[i]
                u = pipe.u[idx]
                sign = self.signs[i]
                if sign * u <= 0:  # flow from junction into pipe
                    pipe.AA[idx] = AA_mixed
