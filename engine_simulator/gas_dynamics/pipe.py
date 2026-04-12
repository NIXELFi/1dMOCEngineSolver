"""Pipe class: 1D domain discretization with state arrays.

Stores Benson non-dimensional Riemann variables (lambda, beta, A_A) and
derived flow quantities at each grid point.
"""

from __future__ import annotations

import numpy as np

from engine_simulator.gas_dynamics.gas_properties import (
    A_REF,
    GAMMA_REF,
    P_REF,
    R_AIR,
    RHO_REF,
    T_REF,
    AU_from_riemann,
    density_from_A_AA,
    pressure_from_A_AA,
    temperature_from_A_AA,
)


class Pipe:
    """Represents a 1D duct discretized for the mesh Method of Characteristics."""

    def __init__(
        self,
        name: str,
        length: float,
        diameter: float,
        n_points: int = 30,
        diameter_out: float | None = None,
        wall_temperature: float = 320.0,
        roughness: float = 0.03e-3,
        gamma: float = GAMMA_REF,
        artificial_viscosity: float = -1.0,
    ):
        self.name = name
        self.length = length
        self.n_points = n_points
        self.wall_temperature = wall_temperature
        self.roughness = roughness
        self.gamma = gamma
        self.artificial_viscosity = artificial_viscosity

        # Grid
        self.dx = length / (n_points - 1) if n_points > 1 else length
        self.x = np.linspace(0.0, length, n_points)

        # Diameter and area at each grid point (supports taper)
        if diameter_out is None or diameter_out == diameter:
            self.diameter = np.full(n_points, diameter)
        else:
            self.diameter = np.linspace(diameter, diameter_out, n_points)
        self.area = np.pi / 4.0 * self.diameter**2

        # Area gradient dF/dx (central differences, one-sided at ends)
        self.dAdx = np.gradient(self.area, self.x) if n_points > 1 else np.zeros(1)

        # State arrays — Benson non-dimensional
        self.lam = np.ones(n_points)  # lambda = A + (gamma-1)/2 * U
        self.bet = np.ones(n_points)  # beta   = A - (gamma-1)/2 * U
        self.AA = np.ones(n_points)  # entropy level parameter

        # Derived dimensional arrays (updated by update_derived())
        self.p = np.full(n_points, P_REF)
        self.T = np.full(n_points, T_REF)
        self.rho = np.full(n_points, RHO_REF)
        self.u = np.zeros(n_points)
        self.a = np.full(n_points, A_REF)
        self.A_nd = np.ones(n_points)  # non-dimensional speed of sound
        self.U_nd = np.zeros(n_points)  # non-dimensional velocity

    def initialize(
        self, p: float = P_REF, T: float = T_REF, u: float = 0.0,
        gamma: float | None = None,
    ):
        """Set uniform initial conditions in the pipe."""
        gam = gamma if gamma is not None else self.gamma
        R = P_REF / (RHO_REF * T_REF)  # using reference to get R_air
        a = np.sqrt(gam * R * T)
        A = a / A_REF
        U = u / A_REF

        self.AA[:] = (p / P_REF) ** (-(gam - 1.0) / (2.0 * gam)) * A
        # For standard conditions, AA = 1.0
        # More precisely: AA = A * (p_ref/p)^((gamma-1)/(2*gamma))
        # But if p = p_ref and T = T_ref, then A = 1 and AA = 1

        self.lam[:] = A + 0.5 * (gam - 1.0) * U
        self.bet[:] = A - 0.5 * (gam - 1.0) * U

        self.update_derived()

    def update_derived(self):
        """Recompute dimensional quantities from Riemann variables.

        Benson non-homentropic formulation:
            A  = a / a_ref          → T = T_ref · A²   (sound speed → temperature)
            AA = A · (P_ref/p)^((γ-1)/(2γ))   → entropy parameter
            => p = P_ref · (A/AA)^(2γ/(γ-1))
            => ρ = p / (R·T)        (ideal gas, NOT a separate ratio formula)

        The earlier code used `T = T_ref · (A/AA)²` which is only correct on the
        REF isentrope (AA = 1) and forced every gas state onto that isentrope —
        a sub-atmospheric plenum at ambient temperature could not be represented.
        """
        gam = self.gamma
        self.A_nd = (self.lam + self.bet) / 2.0
        self.U_nd = (self.lam - self.bet) / (gam - 1.0)

        self.a = self.A_nd * A_REF
        self.u = self.U_nd * A_REF

        # Pressure: from the Benson definition of AA (entropy parameter)
        ratio = np.maximum(self.A_nd / np.maximum(self.AA, 1e-12), 1e-12)
        self.p = P_REF * ratio ** (2.0 * gam / (gam - 1.0))

        # Temperature: from the dimensional sound speed only
        A_safe = np.maximum(self.A_nd, 1e-12)
        self.T = T_REF * A_safe ** 2

        # Density: ideal gas from p and T (consistent by construction)
        self.rho = self.p / (R_AIR * np.maximum(self.T, 1.0))

    def max_wave_speed(self) -> float:
        """Maximum absolute wave speed across all grid points."""
        return float(np.max(np.maximum(
            np.abs(self.u + self.a),
            np.abs(self.u - self.a),
        )))

    def local_cfl_dt(self) -> float:
        """Maximum allowable dt from this pipe (CFL = 1)."""
        max_speed = self.max_wave_speed()
        if max_speed < 1e-10:
            return 1e10
        return self.dx / max_speed

    @classmethod
    def from_config(cls, cfg) -> Pipe:
        """Construct Pipe from a PipeConfig dataclass."""
        return cls(
            name=cfg.name,
            length=cfg.length,
            diameter=cfg.diameter,
            n_points=cfg.n_points,
            diameter_out=cfg.diameter_out,
            wall_temperature=cfg.wall_temperature,
            roughness=cfg.roughness,
            artificial_viscosity=getattr(cfg, 'artificial_viscosity', -1.0),
        )
