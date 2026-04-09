"""Valve boundary condition connecting 1D pipe domain to 0D cylinder.

Uses quasi-steady compressible orifice model with iterative pressure matching.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.boundaries.base import BoundaryCondition, PipeEnd
from engine_simulator.engine.cylinder import CylinderModel
from engine_simulator.gas_dynamics.gas_properties import (
    A_REF,
    GAMMA_REF,
    P_REF,
    R_AIR,
    T_REF,
    A_from_pressure,
    pressure_from_A_AA,
    temperature_from_A_AA,
)
from engine_simulator.gas_dynamics.pipe import Pipe


class ValveBoundaryCondition(BoundaryCondition):
    """Connects a pipe end to a cylinder through a valve.

    The valve is modeled as a quasi-steady compressible orifice.
    Flow direction is determined by comparing cylinder and pipe pressures.
    """

    def __init__(self, cylinder: CylinderModel, valve_type: str = "intake"):
        self.cylinder = cylinder
        self.valve_type = valve_type  # "intake" or "exhaust"

    def apply(self, pipe: Pipe, end: PipeEnd, dt: float, **kwargs):
        theta_deg = kwargs.get("theta_deg", 0.0)
        rpm = kwargs.get("rpm", 10000.0)

        idx = self.get_index(end)
        gam = pipe.gamma
        gm1 = gam - 1.0

        theta_local = self.cylinder.local_theta(theta_deg)

        # Get effective valve area
        if self.valve_type == "intake":
            A_eff = self.cylinder.intake_valve.effective_area(theta_local)
        else:
            A_eff = self.cylinder.exhaust_valve.effective_area(theta_local)

        if A_eff < 1e-10:
            # Valve closed: treat as closed end
            if end == PipeEnd.RIGHT:
                pipe.bet[idx] = pipe.lam[idx]
            else:
                pipe.lam[idx] = pipe.bet[idx]
            # Zero mass flow
            if self.valve_type == "intake":
                self.cylinder.mdot_intake = 0.0
            else:
                self.cylinder.mdot_exhaust = 0.0
            return

        # Get incoming Riemann variable and pipe state
        AA = pipe.AA[idx]

        if end == PipeEnd.RIGHT:
            riemann_in = pipe.lam[idx]  # lambda arrives
        else:
            riemann_in = pipe.bet[idx]  # beta arrives

        # Estimate pipe-end pressure from incoming Riemann variable
        # Use current state as starting estimate
        p_pipe = pipe.p[idx]
        T_pipe = pipe.T[idx]
        p_cyl = self.cylinder.p
        T_cyl = self.cylinder.T

        # Determine flow direction
        A_pipe_cross = pipe.area[idx]

        if self.valve_type == "intake":
            # Intake: flow typically from pipe into cylinder (p_pipe > p_cyl)
            if p_pipe > p_cyl:
                p_up, T_up = p_pipe, T_pipe
                p_down = p_cyl
                flow_sign = 1.0  # positive = into cylinder
            else:
                p_up, T_up = p_cyl, T_cyl
                p_down = p_pipe
                flow_sign = -1.0  # reverse flow
        else:
            # Exhaust: flow typically from cylinder into pipe (p_cyl > p_pipe)
            if p_cyl > p_pipe:
                p_up, T_up = p_cyl, T_cyl
                p_down = p_pipe
                flow_sign = 1.0  # positive = out of cylinder
            else:
                p_up, T_up = p_pipe, T_pipe
                p_down = p_cyl
                flow_sign = -1.0  # reverse flow

        # Compute mass flow through valve
        mdot = self._mass_flow(p_up, T_up, p_down, A_eff, gam)
        mdot_signed = mdot * flow_sign

        # Set cylinder mass flow rates
        # IMPORTANT: use += everywhere so two valve BCs can ADD their
        # contributions in the same step. Previously the exhaust BC's `=`
        # would overwrite any reverse-intake mass that the intake BC had
        # added to mdot_exhaust during valve overlap, losing ~22% of those
        # reverse-flow events from the per-cycle mass tally.
        # The orchestrator zeros mdot_intake / mdot_exhaust at the start of
        # each step, so += starts from a clean slate.
        if self.valve_type == "intake":
            if flow_sign > 0:
                self.cylinder.mdot_intake += mdot
                self.cylinder.T_intake = T_pipe
            else:
                self.cylinder.mdot_exhaust += mdot  # reverse flow out through intake
        else:
            if flow_sign > 0:
                self.cylinder.mdot_exhaust += mdot
                self.cylinder.T_exhaust = T_cyl
            else:
                self.cylinder.mdot_intake += mdot  # reverse flow back into cyl through exhaust

        # Compute boundary velocity in pipe
        rho_pipe = pipe.rho[idx]
        if rho_pipe > 1e-6 and A_pipe_cross > 1e-10:
            u_boundary = mdot_signed / (rho_pipe * A_pipe_cross)
            if self.valve_type == "exhaust":
                u_boundary = -u_boundary if end == PipeEnd.LEFT else u_boundary
        else:
            u_boundary = 0.0

        # Convert to non-dimensional and compute reflected Riemann variable
        U_boundary = u_boundary / A_REF
        A_boundary = A_from_pressure(p_pipe, AA, gam)

        # Iterate on boundary pressure for consistency
        for _ in range(10):
            if end == PipeEnd.RIGHT:
                beta_new = riemann_in - gm1 * U_boundary
                A_new = (riemann_in + beta_new) / 2.0
            else:
                lam_new = riemann_in + gm1 * U_boundary
                A_new = (lam_new + riemann_in) / 2.0
                beta_new = riemann_in

            # Recompute pressure from new A
            p_new = P_REF * (max(A_new / max(AA, 1e-6), 1e-6)) ** (2.0 * gam / gm1)

            # Check convergence
            if abs(p_new - p_pipe) / max(p_pipe, 1.0) < 1e-4:
                p_pipe = p_new
                break
            p_pipe = 0.5 * (p_pipe + p_new)
            A_boundary = A_from_pressure(p_pipe, AA, gam)

            # Recompute mass flow with updated pressures
            if self.valve_type == "intake":
                if flow_sign > 0:
                    mdot = self._mass_flow(p_pipe, T_pipe, p_cyl, A_eff, gam)
                else:
                    mdot = self._mass_flow(p_cyl, T_cyl, p_pipe, A_eff, gam)
            else:
                if flow_sign > 0:
                    mdot = self._mass_flow(p_cyl, T_cyl, p_pipe, A_eff, gam)
                else:
                    mdot = self._mass_flow(p_pipe, T_pipe, p_cyl, A_eff, gam)

            if rho_pipe > 1e-6 and A_pipe_cross > 1e-10:
                u_boundary = mdot * flow_sign / (rho_pipe * A_pipe_cross)
                if self.valve_type == "exhaust":
                    u_boundary = -u_boundary if end == PipeEnd.LEFT else u_boundary
            U_boundary = u_boundary / A_REF

        # Set final boundary state
        if end == PipeEnd.RIGHT:
            pipe.bet[idx] = riemann_in - gm1 * U_boundary
        else:
            pipe.lam[idx] = riemann_in + gm1 * U_boundary

        # Update entropy if exhaust gas enters pipe
        if self.valve_type == "exhaust" and flow_sign > 0 and mdot > 1e-8:
            # Exhaust gas has higher entropy (A_A > 1)
            T_ratio = T_cyl / T_REF
            p_ratio = p_cyl / P_REF
            AA_exhaust = np.sqrt(T_ratio) * p_ratio ** (-(gam - 1.0) / (2.0 * gam))
            pipe.AA[idx] = max(AA_exhaust, 0.01)

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
            # Choked
            choke_factor = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
            return A_eff * p_up * np.sqrt(gamma / (R * max(T_up, 100.0))) * choke_factor
        else:
            # Subsonic
            t1 = pr ** (2.0 / gamma)
            t2 = pr ** ((gamma + 1.0) / gamma)
            flow_fn = np.sqrt(max(2.0 * gamma / (gamma - 1.0) * (t1 - t2), 0.0))
            return A_eff * p_up / np.sqrt(R * max(T_up, 100.0)) * flow_fn
