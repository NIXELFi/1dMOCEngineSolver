"""CFL time step computation for the MOC solver."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine_simulator.gas_dynamics.pipe import Pipe


def compute_cfl_timestep(pipes: list[Pipe], cfl_number: float = 0.85) -> float:
    """Compute the global time step satisfying the CFL condition across all pipes.

    dt <= cfl_number * min(dx / max(|u+a|, |u-a|)) over all pipes and points.
    """
    dt_min = 1e10
    for pipe in pipes:
        dt_pipe = pipe.local_cfl_dt()
        if dt_pipe < dt_min:
            dt_min = dt_pipe

    return cfl_number * dt_min
