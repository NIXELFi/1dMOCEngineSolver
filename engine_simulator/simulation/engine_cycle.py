"""Engine cycle tracking and management."""

from __future__ import annotations

import numpy as np

from engine_simulator.engine.kinematics import normalize_angle, omega_from_rpm


class EngineCycleTracker:
    """Tracks crank angle position, cycle count, and phase information."""

    def __init__(self, rpm: float, theta_start: float = 0.0):
        self.rpm = rpm
        self.omega = omega_from_rpm(rpm)
        self.theta = theta_start  # degrees, cumulative
        self.cycle_count = 0
        self.time = 0.0  # seconds

    @property
    def theta_local(self) -> float:
        """Current crank angle in [0, 720) range."""
        return normalize_angle(self.theta)

    @property
    def cycle_period(self) -> float:
        """Time for one complete 4-stroke cycle (720° = 2 revolutions)."""
        return 720.0 / (6.0 * self.rpm)  # seconds

    def advance(self, dt: float) -> float:
        """Advance by dt seconds. Returns crank angle increment in degrees."""
        dtheta = np.degrees(self.omega * dt)
        self.theta += dtheta
        self.time += dt

        # Check for cycle completion
        new_cycle = int(self.theta / 720.0)
        if new_cycle > self.cycle_count:
            self.cycle_count = new_cycle

        return dtheta

    def degrees_to_seconds(self, dtheta_deg: float) -> float:
        """Convert a crank angle interval to time interval."""
        return np.radians(dtheta_deg) / self.omega if self.omega > 0 else 0.0

    def reset_cycle(self):
        """Reset to start of a new cycle."""
        self.theta = 0.0
        self.cycle_count = 0
        self.time = 0.0
