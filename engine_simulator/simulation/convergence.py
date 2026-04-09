"""Cyclic steady-state convergence detection."""

from __future__ import annotations

import numpy as np


class ConvergenceChecker:
    """Monitors cycle-to-cycle convergence of key quantities.

    Compares pressure at IVC between successive cycles. When the relative
    change falls below the tolerance, cyclic steady state is declared.
    """

    def __init__(self, n_cylinders: int, tolerance: float = 0.005):
        self.tolerance = tolerance
        self.n_cylinders = n_cylinders

        # Store p_IVC for each cylinder per cycle
        self.history: list[list[float]] = []  # history[cycle][cyl_idx]

    def record_cycle(self, p_ivc_values: list[float]):
        """Record IVC pressures for all cylinders at end of a cycle."""
        self.history.append(list(p_ivc_values))

    def is_converged(self) -> bool:
        """Check if cyclic steady state has been reached."""
        if len(self.history) < 2:
            return False

        prev = np.array(self.history[-2])
        curr = np.array(self.history[-1])

        # Relative change for each cylinder
        rel_change = np.abs(curr - prev) / np.maximum(np.abs(prev), 1.0)
        max_change = np.max(rel_change)

        return max_change < self.tolerance

    def max_relative_change(self) -> float:
        """Get the maximum relative change from the last cycle comparison."""
        if len(self.history) < 2:
            return float("inf")

        prev = np.array(self.history[-2])
        curr = np.array(self.history[-1])
        rel_change = np.abs(curr - prev) / np.maximum(np.abs(prev), 1.0)
        return float(np.max(rel_change))

    def reset(self):
        """Clear history for a new RPM point."""
        self.history.clear()
