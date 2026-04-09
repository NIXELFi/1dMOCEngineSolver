"""Valve model: lift profiles, discharge coefficients, effective flow area."""

from __future__ import annotations

import numpy as np

from engine_simulator.config.engine_config import ValveConfig


class Valve:
    """Models a poppet valve with harmonic lift profile and Cd lookup."""

    def __init__(self, cfg: ValveConfig, n_valves: int = 2):
        self.diameter = cfg.diameter
        self.max_lift = cfg.max_lift
        self.open_angle = cfg.open_angle  # degrees
        self.close_angle = cfg.close_angle  # degrees
        self.seat_angle_deg = cfg.seat_angle
        self.n_valves = n_valves

        # Cd lookup table: list of (L/D, Cd)
        self.cd_table = cfg.cd_table if cfg.cd_table else [
            (0.05, 0.20), (0.10, 0.40), (0.15, 0.52),
            (0.20, 0.58), (0.25, 0.60), (0.30, 0.60),
        ]

        # Duration and peak angle
        self.duration = self.close_angle - self.open_angle
        self.peak_angle = (self.open_angle + self.close_angle) / 2.0

        # Port area (limits flow at high lift)
        self.port_area = np.pi / 4.0 * self.diameter**2

    def is_open(self, theta_deg: float) -> bool:
        """Check if valve is open at given crank angle (handles wrap-around)."""
        # Normalize theta to 0-720 range
        theta = theta_deg % 720.0
        if self.open_angle < self.close_angle:
            return self.open_angle <= theta <= self.close_angle
        else:
            # Wraps around 720 -> 0
            return theta >= self.open_angle or theta <= self.close_angle

    def lift(self, theta_deg: float) -> float:
        """Valve lift using harmonic (sin^2) profile. Returns lift in meters."""
        theta = theta_deg % 720.0

        if self.open_angle < self.close_angle:
            if theta < self.open_angle or theta > self.close_angle:
                return 0.0
            phase = np.pi * (theta - self.open_angle) / self.duration
        else:
            # Wrap-around case (e.g., exhaust valve open 140-365 doesn't wrap,
            # but handle generically)
            if theta >= self.open_angle:
                phase = np.pi * (theta - self.open_angle) / self.duration
            elif theta <= self.close_angle:
                phase = np.pi * (theta + 720.0 - self.open_angle) / self.duration
            else:
                return 0.0

        if phase < 0 or phase > np.pi:
            return 0.0

        return self.max_lift * np.sin(phase) ** 2

    def discharge_coefficient(self, lift: float) -> float:
        """Interpolate Cd from L/D table."""
        if lift <= 0:
            return 0.0
        ld = lift / self.diameter

        # Linear interpolation on Cd table
        table = self.cd_table
        if ld <= table[0][0]:
            return table[0][1] * (ld / table[0][0])
        if ld >= table[-1][0]:
            return table[-1][1]

        for k in range(len(table) - 1):
            if table[k][0] <= ld <= table[k + 1][0]:
                frac = (ld - table[k][0]) / (table[k + 1][0] - table[k][0])
                return table[k][1] + frac * (table[k + 1][1] - table[k][1])

        return table[-1][1]

    def reference_area(self, lift: float) -> float:
        """Compute reference flow area based on lift regime.

        Low lift (L/D < 0.125): pi*D*L*cos(seat_angle)
        Medium lift (0.125 < L/D < 0.25): pi*D*L (curtain area)
        High lift (L/D > 0.25): pi/4*D_port^2 (port area limited)
        """
        if lift <= 0:
            return 0.0

        ld = lift / self.diameter
        seat_rad = np.radians(self.seat_angle_deg)

        if ld < 0.125:
            return np.pi * self.diameter * lift * np.cos(seat_rad)
        elif ld < 0.25:
            return np.pi * self.diameter * lift
        else:
            return self.port_area

    def effective_area(self, theta_deg: float) -> float:
        """Compute total effective valve flow area at given crank angle.

        A_eff = n_valves * Cd * A_ref
        """
        L = self.lift(theta_deg)
        if L <= 0:
            return 0.0
        Cd = self.discharge_coefficient(L)
        A_ref = self.reference_area(L)
        return self.n_valves * Cd * A_ref

    def mass_flow_compressible(
        self, p_upstream: float, T_upstream: float, p_downstream: float,
        A_eff: float, gamma: float = 1.4, R: float = 287.0,
    ) -> float:
        """Compute mass flow through valve using compressible orifice equations.

        Returns mass flow (kg/s), positive from upstream to downstream.
        """
        if A_eff <= 0 or p_upstream <= 0:
            return 0.0

        pr = p_downstream / p_upstream
        pr = max(pr, 0.0)

        # Critical pressure ratio
        pr_crit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))

        if pr <= pr_crit:
            # Choked flow
            choke_factor = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
            mdot = A_eff * p_upstream * np.sqrt(gamma / (R * T_upstream)) * choke_factor
        else:
            # Subsonic flow
            term1 = pr ** (2.0 / gamma)
            term2 = pr ** ((gamma + 1.0) / gamma)
            flow_fn = np.sqrt(max(2.0 * gamma / (gamma - 1.0) * (term1 - term2), 0.0))
            mdot = A_eff * p_upstream / np.sqrt(R * T_upstream) * flow_fn

        return mdot
