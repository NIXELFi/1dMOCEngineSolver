"""Wiebe combustion model for SI engines."""

from __future__ import annotations

import numpy as np

from engine_simulator.config.engine_config import CombustionConfig


class WiebeCombustion:
    """Single Wiebe function combustion model.

    x_b(theta) = 1 - exp[-a * ((theta - theta0) / delta_theta)^(m+1)]

    Angles are stored in a canonical form where theta_start may be negative
    (BTDC firing). The is_combusting() and related methods handle the 0-720
    wrap-around transparently.
    """

    def __init__(self, cfg: CombustionConfig):
        self.a = cfg.wiebe_a
        self.m = cfg.wiebe_m
        self.combustion_duration = cfg.combustion_duration
        self.spark_advance = cfg.spark_advance
        self.ignition_delay = cfg.ignition_delay
        self.combustion_efficiency = cfg.combustion_efficiency
        self.q_lhv = cfg.q_lhv
        self.afr_target = cfg.afr_target
        self._update_angles()

    def _update_angles(self):
        # Combustion start in canonical form (may be negative for BTDC)
        self.theta_start_canonical = -self.spark_advance + self.ignition_delay
        self.theta_end_canonical = self.theta_start_canonical + self.combustion_duration

    def update_timing(self, spark_advance: float):
        """Update spark timing (useful for RPM-dependent timing)."""
        self.spark_advance = spark_advance
        self._update_angles()

    def _to_combustion_angle(self, theta_deg: float) -> float:
        """Convert a local crank angle [0, 720) to the canonical combustion
        coordinate where TDC firing = 0 and negative = BTDC.

        The combustion window straddles TDC (e.g., -18 to +32).
        If theta_deg is near 720 (approaching TDC from below), map it to
        a small negative value.
        """
        t = theta_deg % 720.0
        # If the combustion straddles TDC (theta_start < 0), angles near 720
        # should map to negative values
        if self.theta_start_canonical < 0 and t > 360.0:
            t -= 720.0
        return t

    def is_combusting(self, theta_deg: float) -> bool:
        """Check if combustion is active at this crank angle."""
        t = self._to_combustion_angle(theta_deg)
        return self.theta_start_canonical <= t <= self.theta_end_canonical

    def mass_fraction_burned(self, theta_deg: float) -> float:
        """Compute mass fraction burned x_b at given crank angle."""
        t = self._to_combustion_angle(theta_deg)
        if t < self.theta_start_canonical:
            return 0.0
        if t > self.theta_end_canonical:
            return 1.0

        tau = (t - self.theta_start_canonical) / self.combustion_duration
        tau = max(0.0, min(1.0, tau))
        return 1.0 - np.exp(-self.a * tau ** (self.m + 1.0))

    def burn_rate(self, theta_deg: float) -> float:
        """Compute dx_b/dtheta at given crank angle (1/degree)."""
        t = self._to_combustion_angle(theta_deg)
        if t < self.theta_start_canonical or t > self.theta_end_canonical:
            return 0.0

        tau = (t - self.theta_start_canonical) / self.combustion_duration
        tau = max(1e-12, min(1.0 - 1e-12, tau))
        return (
            self.a
            * (self.m + 1.0)
            / self.combustion_duration
            * tau**self.m
            * np.exp(-self.a * tau ** (self.m + 1.0))
        )

    def heat_release_rate(self, theta_deg: float, m_fuel: float) -> float:
        """Compute dQ_comb/dtheta (J/degree)."""
        return self.combustion_efficiency * m_fuel * self.q_lhv * self.burn_rate(theta_deg)

    def total_heat_release(self, m_fuel: float) -> float:
        """Total chemical energy released (J)."""
        return self.combustion_efficiency * m_fuel * self.q_lhv
