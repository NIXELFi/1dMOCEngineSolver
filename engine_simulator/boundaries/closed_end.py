"""Closed end (wall) boundary condition.

At a closed end, u = 0, so lambda = beta.
Pressure waves reflect with the same sign.
"""

from __future__ import annotations

from engine_simulator.boundaries.base import BoundaryCondition, PipeEnd
from engine_simulator.gas_dynamics.pipe import Pipe


class ClosedEndBC(BoundaryCondition):
    """Wall boundary condition: u = 0 -> lambda = beta."""

    def apply(self, pipe: Pipe, end: PipeEnd, dt: float, **kwargs):
        idx = self.get_index(end)

        if end == PipeEnd.RIGHT:
            # lambda arrives from interior, reflect as beta
            pipe.bet[idx] = pipe.lam[idx]
        else:
            # beta arrives from interior, reflect as lambda
            pipe.lam[idx] = pipe.bet[idx]
