"""Simulation results storage and probe history management."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ProbeData:
    """Time-series data at a specific location."""
    theta: list[float] = field(default_factory=list)  # crank angle degrees
    pressure: list[float] = field(default_factory=list)  # Pa
    temperature: list[float] = field(default_factory=list)  # K
    velocity: list[float] = field(default_factory=list)  # m/s
    density: list[float] = field(default_factory=list)  # kg/m^3

    def to_arrays(self):
        return {
            "theta": np.array(self.theta),
            "pressure": np.array(self.pressure),
            "temperature": np.array(self.temperature),
            "velocity": np.array(self.velocity),
            "density": np.array(self.density),
        }


class SimulationResults:
    """Collects and stores simulation data for post-processing."""

    def __init__(self):
        self.theta_history: list[float] = []
        self.dt_history: list[float] = []

        # Per-cylinder data
        self.cylinder_data: dict[int, ProbeData] = {}

        # Pipe probe data: keyed by (pipe_name, location_fraction)
        self.pipe_probes: dict[str, ProbeData] = {}

        # Plenum data
        self.plenum_pressure: list[float] = []
        self.plenum_temperature: list[float] = []

        # Restrictor data
        self.restrictor_mdot: list[float] = []
        self.restrictor_choked: list[bool] = []

    def record_step(self, theta, dt, cylinders, pipes, plenum, restrictor_mdot, restrictor_choked):
        """Record data at a single time step."""
        self.theta_history.append(theta)
        self.dt_history.append(dt)

        # Cylinder data
        for cyl in cylinders:
            if cyl.id not in self.cylinder_data:
                self.cylinder_data[cyl.id] = ProbeData()
            cd = self.cylinder_data[cyl.id]
            cd.theta.append(theta)
            cd.pressure.append(cyl.p)
            cd.temperature.append(cyl.T)
            cd.velocity.append(0.0)  # no velocity for 0D
            cd.density.append(cyl.m / cyl.V if cyl.V > 0 else 0.0)

        # Pipe midpoint probes
        for pipe in pipes:
            key = f"{pipe.name}_mid"
            if key not in self.pipe_probes:
                self.pipe_probes[key] = ProbeData()
            mid = pipe.n_points // 2
            pd = self.pipe_probes[key]
            pd.theta.append(theta)
            pd.pressure.append(pipe.p[mid])
            pd.temperature.append(pipe.T[mid])
            pd.velocity.append(pipe.u[mid])
            pd.density.append(pipe.rho[mid])

        # Plenum
        self.plenum_pressure.append(plenum.p)
        self.plenum_temperature.append(plenum.T)

        # Restrictor
        self.restrictor_mdot.append(restrictor_mdot)
        self.restrictor_choked.append(restrictor_choked)

    def get_cylinder_arrays(self, cyl_id: int) -> dict:
        """Get numpy arrays for a cylinder's data."""
        if cyl_id in self.cylinder_data:
            return self.cylinder_data[cyl_id].to_arrays()
        return {}

    def get_pipe_probe_arrays(self, pipe_name: str) -> dict:
        """Get numpy arrays for a pipe probe's data."""
        key = f"{pipe_name}_mid"
        if key in self.pipe_probes:
            return self.pipe_probes[key].to_arrays()
        return {}
