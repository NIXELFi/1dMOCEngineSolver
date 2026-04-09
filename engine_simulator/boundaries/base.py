"""Abstract base class for boundary conditions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine_simulator.gas_dynamics.pipe import Pipe


class PipeEnd(Enum):
    """Which end of the pipe the boundary condition applies to."""
    LEFT = 0   # x = 0, index 0
    RIGHT = 1  # x = L, index -1


class BoundaryCondition(ABC):
    """Abstract base for all boundary conditions.

    Convention:
    - At LEFT end (x=0): C- arrives from interior (beta known), must determine lambda.
    - At RIGHT end (x=L): C+ arrives from interior (lambda known), must determine beta.

    Note: The convention follows from characteristic directions:
    - C+ travels rightward (dx/dt = u+a > 0 for subsonic), so at the RIGHT end
      a C+ characteristic arrives from the interior.
    - C- travels leftward (dx/dt = u-a < 0 for subsonic), so at the LEFT end
      a C- characteristic arrives from the interior.
    """

    @abstractmethod
    def apply(self, pipe: Pipe, end: PipeEnd, dt: float, **kwargs):
        """Apply the boundary condition to the specified end of the pipe.

        Must set pipe.lam[idx] and pipe.bet[idx] (and optionally pipe.AA[idx])
        where idx is 0 for LEFT, -1 for RIGHT.
        """
        ...

    @staticmethod
    def get_index(end: PipeEnd) -> int:
        """Get array index for the pipe end."""
        return 0 if end == PipeEnd.LEFT else -1

    @staticmethod
    def get_incoming_riemann(pipe: Pipe, end: PipeEnd) -> float:
        """Get the Riemann variable arriving from the interior.

        At RIGHT end: lambda arrives (C+ from interior)
        At LEFT end: beta arrives (C- from interior)
        """
        if end == PipeEnd.RIGHT:
            return float(pipe.lam[-1])
        else:
            return float(pipe.bet[0])
