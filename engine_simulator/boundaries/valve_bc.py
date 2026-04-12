"""Valve boundary condition connecting 1D pipe domain to 0D cylinder.

Uses impedance-coupled compressible orifice model: Newton-Raphson on the
boundary non-dimensional sound speed A_b ensures mass conservation between
the valve orifice flow and the pipe's characteristic-compatible flow, with
self-consistent density derived from A_b at each iteration.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.boundaries.base import BoundaryCondition, PipeEnd
from engine_simulator.gas_dynamics.gas_properties import (
    A_REF,
    GAMMA_REF,
    P_REF,
    R_AIR,
    T_REF,
)
from engine_simulator.gas_dynamics.pipe import Pipe


class ValveBoundaryCondition(BoundaryCondition):
    """Connects a pipe end to a cylinder through a valve.

    The valve is modeled as a quasi-steady compressible orifice.
    Flow direction is determined by comparing cylinder and pipe pressures.
    The boundary state is found by a Newton-Raphson iteration that matches
    the valve mass flow to the pipe mass flow (rho * u * A) derived from
    the Benson Riemann variables, ensuring self-consistent density and
    proper acoustic impedance coupling.
    """

    def __init__(self, cylinder, valve_type: str = "intake"):
        self.cylinder = cylinder
        self.valve_type = valve_type  # "intake" or "exhaust"

    def apply(self, pipe: Pipe, end: PipeEnd, dt: float, **kwargs):
        theta_deg = kwargs.get("theta_deg", 0.0)

        idx = self.get_index(end)
        gam = pipe.gamma
        gm1 = gam - 1.0

        theta_local = self.cylinder.local_theta(theta_deg)

        if self.valve_type == "intake":
            A_eff = self.cylinder.intake_valve.effective_area(theta_local)
        else:
            A_eff = self.cylinder.exhaust_valve.effective_area(theta_local)

        if A_eff < 1e-10:
            if end == PipeEnd.RIGHT:
                pipe.bet[idx] = pipe.lam[idx]
            else:
                pipe.lam[idx] = pipe.bet[idx]
            if self.valve_type == "intake":
                self.cylinder.mdot_intake = 0.0
            else:
                self.cylinder.mdot_exhaust = 0.0
            return

        AA = pipe.AA[idx]
        R_in = pipe.lam[idx] if end == PipeEnd.RIGHT else pipe.bet[idx]
        A_pipe_area = pipe.area[idx]
        p_cyl = self.cylinder.p
        T_cyl = self.cylinder.T

        A_b = pipe.A_nd[idx]

        mdot_valve = 0.0
        flow_sign = 1.0
        p_b = pipe.p[idx]
        T_b = pipe.T[idx]

        for _ in range(20):
            F, mdot_valve, flow_sign, p_b, T_b = self._boundary_residual(
                A_b, R_in, AA, end, A_pipe_area, p_cyl, T_cyl, A_eff, gam,
            )

            if abs(F) < 1e-8:
                break

            eps = max(1e-6 * abs(A_b), 1e-8)
            F_plus = self._boundary_residual(
                A_b + eps, R_in, AA, end, A_pipe_area, p_cyl, T_cyl, A_eff, gam,
            )[0]
            dF = (F_plus - F) / eps

            if abs(dF) < 1e-20:
                break

            dA = -F / dF
            dA = max(-0.3 * A_b, min(0.3 * A_b, dA))
            A_b += dA
            A_b = max(A_b, 0.01)

        if end == PipeEnd.RIGHT:
            pipe.bet[idx] = 2.0 * A_b - R_in
        else:
            pipe.lam[idx] = 2.0 * A_b - R_in

        # Use += so two valve BCs can add their contributions during overlap.
        # The orchestrator zeros mdot_intake / mdot_exhaust before each step.
        if self.valve_type == "intake":
            if flow_sign > 0:
                self.cylinder.mdot_intake += mdot_valve
                self.cylinder.T_intake = T_b
            else:
                self.cylinder.mdot_exhaust += mdot_valve
        else:
            if flow_sign > 0:
                self.cylinder.mdot_exhaust += mdot_valve
                self.cylinder.T_exhaust = T_cyl
            else:
                self.cylinder.mdot_intake += mdot_valve

        # Note: pipe.AA[idx] is NOT overwritten here. The Newton-Raphson
        # solver used pipe.AA[idx] for the A_b <-> p_b mapping, so the
        # returned Riemann variables are self-consistent with the current
        # entropy level.  Exhaust entropy propagation into the pipe interior
        # is handled by the MOC contact-surface advection, not the BC.

    def _boundary_residual(
        self,
        A_b: float,
        R_in: float,
        AA: float,
        end: PipeEnd,
        A_pipe_area: float,
        p_cyl: float,
        T_cyl: float,
        A_eff: float,
        gam: float,
    ) -> tuple[float, float, float, float, float]:
        """Mass conservation residual at the pipe-valve boundary.

        Solves: mdot_pipe(A_b) - mdot_valve(A_b) = 0

        where mdot_pipe = rho(A_b) * u(A_b) * A_pipe is the pipe mass flow
        derived self-consistently from the boundary sound speed and the
        incoming Riemann variable, and mdot_valve is the quasi-steady
        orifice mass flow at the corresponding boundary pressure.

        Returns (residual, mdot_valve, flow_sign, p_b, T_b).
        """
        gm1 = gam - 1.0

        if end == PipeEnd.LEFT:
            U_b = 2.0 * (A_b - R_in) / gm1
        else:
            U_b = 2.0 * (R_in - A_b) / gm1

        u_b = U_b * A_REF
        A_ratio = max(A_b / max(AA, 1e-6), 1e-6)
        p_b = P_REF * A_ratio ** (2.0 * gam / gm1)
        T_b = T_REF * max(A_b, 1e-6) ** 2
        rho_b = p_b / (R_AIR * max(T_b, 1.0))

        mdot_pipe = rho_b * u_b * A_pipe_area

        if self.valve_type == "exhaust":
            if p_cyl > p_b:
                mdot_valve = self._mass_flow(p_cyl, T_cyl, p_b, A_eff, gam)
                flow_sign = 1.0
            else:
                mdot_valve = self._mass_flow(p_b, T_b, p_cyl, A_eff, gam)
                flow_sign = -1.0
        else:
            if p_b > p_cyl:
                mdot_valve = self._mass_flow(p_b, T_b, p_cyl, A_eff, gam)
                flow_sign = 1.0
            else:
                mdot_valve = self._mass_flow(p_cyl, T_cyl, p_b, A_eff, gam)
                flow_sign = -1.0

        standard_config = (self.valve_type == "exhaust") == (end == PipeEnd.LEFT)
        target_pipe = mdot_valve * flow_sign if standard_config else -mdot_valve * flow_sign

        return mdot_pipe - target_pipe, mdot_valve, flow_sign, p_b, T_b

    def _mass_flow(
        self, p_up: float, T_up: float, p_down: float, A_eff: float,
        gamma: float = GAMMA_REF
    ) -> float:
        """Compute mass flow through valve orifice."""
        if p_up <= 0 or A_eff <= 0:
            return 0.0

        pr = p_down / p_up
        pr = max(pr, 0.0)
        pr_crit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))

        R = R_AIR

        if pr <= pr_crit:
            choke_factor = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
            return A_eff * p_up * np.sqrt(gamma / (R * max(T_up, 100.0))) * choke_factor
        else:
            t1 = pr ** (2.0 / gamma)
            t2 = pr ** ((gamma + 1.0) / gamma)
            flow_fn = np.sqrt(max(2.0 * gamma / (gamma - 1.0) * (t1 - t2), 0.0))
            return A_eff * p_up / np.sqrt(R * max(T_up, 100.0)) * flow_fn
