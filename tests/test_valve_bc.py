"""Tests for the valve boundary condition (impedance-coupled solve)."""

import numpy as np
import pytest

from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.boundaries.valve_bc import ValveBoundaryCondition
from engine_simulator.gas_dynamics.gas_properties import A_REF, P_REF, R_AIR, T_REF
from engine_simulator.gas_dynamics.pipe import Pipe


class MockValve:
    """Valve with constant effective area (no crank-angle dependence)."""

    def __init__(self, area: float):
        self._area = area

    def effective_area(self, theta_deg: float) -> float:
        return self._area


class MockCylinder:
    """Minimal cylinder stub for valve BC tests."""

    def __init__(self, p: float = 3e5, T: float = 1200.0, exhaust_area: float = 4e-4):
        self.p = p
        self.T = T
        self.mdot_intake = 0.0
        self.mdot_exhaust = 0.0
        self.T_intake = 300.0
        self.T_exhaust = T
        self._phase_offset = 0.0
        self.intake_valve = MockValve(0.0)
        self.exhaust_valve = MockValve(exhaust_area)

    def local_theta(self, theta_deg: float) -> float:
        return (theta_deg - self._phase_offset) % 720.0


def _make_exhaust_pipe(diameter: float = 0.032, n_points: int = 30) -> Pipe:
    p = Pipe("test_exhaust", length=0.308, diameter=diameter, n_points=n_points,
             wall_temperature=650.0)
    p.initialize(p=P_REF, T=T_REF)
    return p


class TestValveClosed:
    """When the valve is closed, the boundary acts as a perfect closed end."""

    def test_closed_exhaust_left_end(self):
        cyl = MockCylinder(exhaust_area=0.0)
        bc = ValveBoundaryCondition(cyl, valve_type="exhaust")
        pipe = _make_exhaust_pipe()
        pipe.bet[0] = 1.05
        bc.apply(pipe, PipeEnd.LEFT, dt=1e-5, theta_deg=0.0, rpm=10000.0)
        assert pipe.lam[0] == pipe.bet[0]

    def test_closed_exhaust_right_end(self):
        cyl = MockCylinder(exhaust_area=0.0)
        bc = ValveBoundaryCondition(cyl, valve_type="exhaust")
        pipe = _make_exhaust_pipe()
        pipe.lam[-1] = 1.05
        bc.apply(pipe, PipeEnd.RIGHT, dt=1e-5, theta_deg=0.0, rpm=10000.0)
        assert pipe.bet[-1] == pipe.lam[-1]


class TestExhaustBlowdown:
    """Exhaust blowdown (p_cyl >> p_pipe) should create a compression wave."""

    def test_choked_exhaust_creates_compression_at_left_end(self):
        """When exhaust gas enters the pipe, lam must exceed bet (compression, not rarefaction)."""
        cyl = MockCylinder(p=3e5, T=1200.0, exhaust_area=4e-4)
        bc = ValveBoundaryCondition(cyl, valve_type="exhaust")
        pipe = _make_exhaust_pipe(diameter=0.032)

        bc.apply(pipe, PipeEnd.LEFT, dt=1e-5, theta_deg=0.0, rpm=10000.0)

        assert pipe.lam[0] > pipe.bet[0], (
            f"Exhaust blowdown must create compression wave: "
            f"lam={pipe.lam[0]:.4f} should exceed bet={pipe.bet[0]:.4f}"
        )

    def test_boundary_pressure_rises_during_blowdown(self):
        """Pipe-end pressure should rise above atmospheric when exhaust gas enters."""
        cyl = MockCylinder(p=3e5, T=1200.0, exhaust_area=4e-4)
        bc = ValveBoundaryCondition(cyl, valve_type="exhaust")
        pipe = _make_exhaust_pipe(diameter=0.032)

        bc.apply(pipe, PipeEnd.LEFT, dt=1e-5, theta_deg=0.0, rpm=10000.0)

        A_b = (pipe.lam[0] + pipe.bet[0]) / 2.0
        p_boundary = P_REF * (A_b / pipe.AA[0]) ** 7.0
        assert p_boundary > P_REF * 1.05, (
            f"Boundary pressure {p_boundary:.0f} Pa should exceed atmospheric by >5%"
        )

    def test_mass_conservation_at_boundary(self):
        """Mass flow through valve must equal rho*u*A at the pipe boundary."""
        cyl = MockCylinder(p=3e5, T=1200.0, exhaust_area=4e-4)
        bc = ValveBoundaryCondition(cyl, valve_type="exhaust")
        pipe = _make_exhaust_pipe(diameter=0.032)

        bc.apply(pipe, PipeEnd.LEFT, dt=1e-5, theta_deg=0.0, rpm=10000.0)

        gam = 1.4
        gm1 = 0.4
        A_b = (pipe.lam[0] + pipe.bet[0]) / 2.0
        U_b = (pipe.lam[0] - pipe.bet[0]) / gm1
        u_b = U_b * A_REF
        AA = pipe.AA[0]
        p_b = P_REF * (A_b / max(AA, 1e-6)) ** (2.0 * gam / gm1)
        T_b = T_REF * A_b ** 2
        rho_b = p_b / (R_AIR * T_b)
        A_pipe = pipe.area[0]

        mdot_pipe = rho_b * u_b * A_pipe
        mdot_valve = cyl.mdot_exhaust

        np.testing.assert_allclose(
            mdot_pipe, mdot_valve, rtol=0.02,
            err_msg="Pipe boundary mass flow must match valve mass flow"
        )


class TestDiameterSensitivity:
    """Different pipe diameters must produce different boundary states."""

    def test_wider_pipe_gives_weaker_wave(self):
        """A wider pipe should produce a weaker compression wave (lam closer to bet)."""
        results = {}
        for diam in [0.025, 0.050]:
            cyl = MockCylinder(p=3e5, T=1200.0, exhaust_area=4e-4)
            bc = ValveBoundaryCondition(cyl, valve_type="exhaust")
            pipe = _make_exhaust_pipe(diameter=diam)
            bc.apply(pipe, PipeEnd.LEFT, dt=1e-5, theta_deg=0.0, rpm=10000.0)
            results[diam] = pipe.lam[0] - pipe.bet[0]

        wave_25mm = results[0.025]
        wave_50mm = results[0.050]

        assert wave_25mm > wave_50mm * 1.5, (
            f"25mm pipe wave amplitude ({wave_25mm:.4f}) should be substantially "
            f"larger than 50mm ({wave_50mm:.4f}) — same mass flow, 4x smaller area"
        )

    def test_boundary_velocity_inversely_proportional_to_area(self):
        """For choked flow (same mdot), boundary velocity should scale as 1/A_pipe."""
        results = {}
        for diam in [0.025, 0.050]:
            cyl = MockCylinder(p=3e5, T=1200.0, exhaust_area=4e-4)
            bc = ValveBoundaryCondition(cyl, valve_type="exhaust")
            pipe = _make_exhaust_pipe(diameter=diam)
            bc.apply(pipe, PipeEnd.LEFT, dt=1e-5, theta_deg=0.0, rpm=10000.0)
            U_b = (pipe.lam[0] - pipe.bet[0]) / 0.4
            results[diam] = U_b * A_REF

        u_25 = results[0.025]
        u_50 = results[0.050]
        area_ratio = (0.050 / 0.025) ** 2

        vel_ratio = u_25 / u_50
        assert vel_ratio > area_ratio * 0.5, (
            f"Velocity ratio ({vel_ratio:.2f}) should reflect area ratio ({area_ratio:.1f})"
        )


class TestSubsonicExhaust:
    """Subsonic exhaust flow (small pressure difference)."""

    def test_subsonic_exhaust_still_creates_compression(self):
        """Even low-pressure exhaust should produce lam > bet (rightward flow)."""
        cyl = MockCylinder(p=1.2e5, T=500.0, exhaust_area=4e-4)
        bc = ValveBoundaryCondition(cyl, valve_type="exhaust")
        pipe = _make_exhaust_pipe(diameter=0.032)

        bc.apply(pipe, PipeEnd.LEFT, dt=1e-5, theta_deg=0.0, rpm=10000.0)

        assert pipe.lam[0] > pipe.bet[0], (
            f"Subsonic exhaust must also create compression: "
            f"lam={pipe.lam[0]:.4f}, bet={pipe.bet[0]:.4f}"
        )
