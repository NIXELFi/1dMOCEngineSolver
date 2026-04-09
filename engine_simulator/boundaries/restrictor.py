"""FSAE 20 mm intake restrictor boundary condition.

Models the restrictor as an isentropic convergent-divergent nozzle with
discharge coefficient. Handles both subsonic and choked (sonic throat) flow.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.config.engine_config import RestrictorConfig
from engine_simulator.gas_dynamics.gas_properties import (
    A_REF,
    GAMMA_REF,
    P_REF,
    R_AIR,
    T_REF,
    A_from_pressure,
)
from engine_simulator.gas_dynamics.pipe import Pipe


class RestrictorBC:
    """FSAE restrictor boundary condition.

    Connects atmospheric conditions (upstream) to the plenum/pipe (downstream).
    The restrictor chokes when the downstream-to-upstream pressure ratio drops
    below the critical ratio (~0.5283 for gamma=1.4).

    When choked, mass flow is capped at m_dot_max and downstream conditions
    cannot influence upstream conditions (one-way information barrier).
    """

    def __init__(
        self,
        cfg: RestrictorConfig,
        p_upstream: float = P_REF,
        T_upstream: float = T_REF,
        gamma: float = GAMMA_REF,
    ):
        self.Cd = cfg.discharge_coefficient
        self.throat_diameter = cfg.throat_diameter
        self.A_throat = np.pi / 4.0 * self.throat_diameter**2
        self.p0 = p_upstream
        self.T0 = T_upstream
        self.gamma = gamma

        # Precompute maximum (choked) mass flow
        self.pr_crit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
        choke_factor = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
        self.mdot_max = (
            self.Cd * self.A_throat * self.p0
            * np.sqrt(gamma / (R_AIR * self.T0))
            * choke_factor
        )

        # Downstream pipe and end
        self.pipe: Pipe | None = None
        self.pipe_end: PipeEnd | None = None

    def connect(self, pipe: Pipe, end: PipeEnd):
        """Connect the restrictor to a downstream pipe."""
        self.pipe = pipe
        self.pipe_end = end

    def compute_mass_flow(self, p_downstream: float) -> float:
        """Compute mass flow through restrictor given downstream pressure.

        Returns mass flow in kg/s.
        """
        gam = self.gamma
        pr = p_downstream / self.p0
        pr = max(pr, 0.0)

        if pr <= self.pr_crit:
            # Choked: mass flow is maximum, independent of downstream
            return self.mdot_max
        elif pr >= 1.0:
            # No flow (downstream >= upstream)
            return 0.0
        else:
            # Subsonic
            t1 = pr ** (2.0 / gam)
            t2 = pr ** ((gam + 1.0) / gam)
            flow_fn = np.sqrt(max(2.0 * gam / (gam - 1.0) * (t1 - t2), 0.0))
            return self.Cd * self.A_throat * self.p0 / np.sqrt(R_AIR * self.T0) * flow_fn

    def compute_mass_flow_and_derivative(self, p_downstream: float) -> tuple[float, float]:
        """Compute mass flow and its derivative w.r.t. downstream pressure.

        Returns (mdot, d_mdot/d_p_downstream).
        """
        gam = self.gamma
        pr = max(p_downstream / self.p0, 1e-6)
        coeff = self.Cd * self.A_throat * self.p0 / np.sqrt(R_AIR * self.T0)

        if pr <= self.pr_crit:
            return self.mdot_max, 0.0
        elif pr >= 1.0:
            return 0.0, 0.0
        else:
            e1 = 2.0 / gam
            e2 = (gam + 1.0) / gam
            t1 = pr ** e1
            t2 = pr ** e2
            inner = 2.0 * gam / (gam - 1.0) * (t1 - t2)
            inner = max(inner, 1e-20)
            mdot = coeff * np.sqrt(inner)

            # Derivative: d(mdot)/d(p_down) = d(mdot)/d(pr) * d(pr)/d(p_down)
            # d(inner)/d(pr) = 2*gam/(gam-1) * (e1*pr^(e1-1) - e2*pr^(e2-1))
            d_inner = 2.0 * gam / (gam - 1.0) * (
                e1 * pr ** (e1 - 1.0) - e2 * pr ** (e2 - 1.0)
            )
            d_mdot_dpr = coeff * d_inner / (2.0 * np.sqrt(inner))
            d_mdot_dp = d_mdot_dpr / self.p0

            return mdot, d_mdot_dp

    def is_choked(self, p_downstream: float) -> bool:
        """Check if the restrictor throat is choked."""
        return (p_downstream / self.p0) <= self.pr_crit

    def apply(self, dt: float, **kwargs):
        """Apply restrictor boundary condition to connected pipe.

        Sets the boundary state at the pipe end based on restrictor flow.
        """
        if self.pipe is None or self.pipe_end is None:
            return

        pipe = self.pipe
        end = self.pipe_end
        idx = 0 if end == PipeEnd.LEFT else -1
        gam = self.gamma
        gm1 = gam - 1.0

        # Get downstream state from pipe
        p_down = pipe.p[idx]
        AA = pipe.AA[idx]

        # Compute mass flow
        mdot = self.compute_mass_flow(p_down)

        # Compute conditions at pipe entry
        # The flow enters the pipe from the restrictor
        rho_down = pipe.rho[idx]
        A_pipe_cross = pipe.area[idx]

        if rho_down > 1e-6 and A_pipe_cross > 1e-10 and mdot > 0:
            u_entry = mdot / (rho_down * A_pipe_cross)
        else:
            u_entry = 0.0

        U_entry = u_entry / A_REF

        # Get incoming Riemann variable
        if end == PipeEnd.LEFT:
            # beta arrives from interior
            bet_in = pipe.bet[idx]
            # Set lambda: lam = bet + (gamma-1)*U
            pipe.lam[idx] = bet_in + gm1 * U_entry
        else:
            # lambda arrives from interior
            lam_in = pipe.lam[idx]
            pipe.bet[idx] = lam_in - gm1 * U_entry

        # Set entropy: fresh air from atmosphere
        pipe.AA[idx] = 1.0

        # Store mass flow for monitoring
        self._last_mdot = mdot
        self._last_choked = self.is_choked(p_down)

    @property
    def last_mass_flow(self) -> float:
        return getattr(self, "_last_mdot", 0.0)

    @property
    def last_choked(self) -> bool:
        return getattr(self, "_last_choked", False)
