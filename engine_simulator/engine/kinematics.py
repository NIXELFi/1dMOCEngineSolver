"""Engine kinematics: crank angle conversions and multi-cylinder phasing."""

from __future__ import annotations

import numpy as np


def crank_angle_to_time(theta_deg: float, rpm: float) -> float:
    """Convert crank angle (degrees) to time (seconds) from reference."""
    return theta_deg / (6.0 * rpm)  # theta_deg / (360 * rpm/60)


def time_to_crank_angle(t: float, rpm: float) -> float:
    """Convert time (seconds) to crank angle (degrees)."""
    return 6.0 * rpm * t


def omega_from_rpm(rpm: float) -> float:
    """Angular velocity in rad/s from RPM."""
    return 2.0 * np.pi * rpm / 60.0


def mean_piston_speed(stroke: float, rpm: float) -> float:
    """Mean piston speed [m/s] = 2*S*N/60."""
    return 2.0 * stroke * rpm / 60.0


def cylinder_phase_offsets(n_cylinders: int, firing_order: list[int],
                            firing_interval: float = 180.0) -> dict[int, float]:
    """Compute crank angle offset for each cylinder.

    For even-firing inline-4 with firing order [1,2,4,3]:
    Cyl 1 fires at 0°, Cyl 2 at 180°, Cyl 4 at 360°, Cyl 3 at 540°.

    Returns dict mapping cylinder number (1-based) to phase offset in degrees.
    """
    offsets = {}
    for firing_position, cyl_number in enumerate(firing_order):
        offsets[cyl_number] = firing_position * firing_interval
    return offsets


def normalize_angle(theta_deg: float) -> float:
    """Normalize crank angle to [0, 720) range."""
    return theta_deg % 720.0
