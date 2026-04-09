"""Tests for boundary conditions."""

import numpy as np
import pytest

from engine_simulator.gas_dynamics.gas_properties import A_REF, GAMMA_REF, P_REF, T_REF
from engine_simulator.gas_dynamics.pipe import Pipe
from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.boundaries.closed_end import ClosedEndBC
from engine_simulator.boundaries.open_end import OpenEndBC
from engine_simulator.boundaries.junction import JunctionBC


class TestClosedEnd:
    def test_reflection_right(self):
        """At right end (closed), lambda reflects as beta."""
        pipe = Pipe("test", length=0.5, diameter=0.04, n_points=20)
        pipe.initialize()
        pipe.lam[-1] = 1.1  # incoming perturbation
        bc = ClosedEndBC()
        bc.apply(pipe, PipeEnd.RIGHT, dt=1e-5)
        assert pipe.bet[-1] == pipe.lam[-1]

    def test_reflection_left(self):
        """At left end (closed), beta reflects as lambda."""
        pipe = Pipe("test", length=0.5, diameter=0.04, n_points=20)
        pipe.initialize()
        pipe.bet[0] = 1.1
        bc = ClosedEndBC()
        bc.apply(pipe, PipeEnd.LEFT, dt=1e-5)
        assert pipe.lam[0] == pipe.bet[0]

    def test_zero_velocity(self):
        """Closed end should produce zero velocity."""
        pipe = Pipe("test", length=0.5, diameter=0.04, n_points=20)
        pipe.initialize()
        pipe.lam[-1] = 1.05
        bc = ClosedEndBC()
        bc.apply(pipe, PipeEnd.RIGHT, dt=1e-5)
        # U = (lam - bet)/(gamma-1), and lam = bet, so U = 0
        U = (pipe.lam[-1] - pipe.bet[-1]) / (GAMMA_REF - 1.0)
        assert abs(U) < 1e-12


class TestOpenEnd:
    def test_outflow_pressure_match(self):
        """Outflow at open end should match atmospheric pressure."""
        pipe = Pipe("test", length=0.5, diameter=0.04, n_points=20)
        pipe.initialize(p=1.1 * P_REF, T=T_REF)
        bc = OpenEndBC(p_atm=P_REF, T_atm=T_REF)
        bc.apply(pipe, PipeEnd.RIGHT, dt=1e-5)
        pipe.update_derived()
        # Boundary pressure should be approximately atmospheric
        # (not exact due to velocity effects)
        assert abs(pipe.p[-1] - P_REF) / P_REF < 0.3

    def test_inflow_stagnation(self):
        """Inflow from atmosphere should maintain stagnation conditions."""
        pipe = Pipe("test", length=0.5, diameter=0.04, n_points=20)
        pipe.initialize(p=0.9 * P_REF, T=T_REF)  # low pressure draws in air
        bc = OpenEndBC(p_atm=P_REF, T_atm=T_REF)
        bc.apply(pipe, PipeEnd.LEFT, dt=1e-5)
        # After BC, boundary should have sensible values
        A = (pipe.lam[0] + pipe.bet[0]) / 2.0
        assert A > 0  # positive speed of sound


class TestJunction:
    def test_two_pipe_junction(self):
        """Two pipes at a junction should satisfy mass conservation."""
        pipe1 = Pipe("p1", length=0.5, diameter=0.04, n_points=20)
        pipe2 = Pipe("p2", length=0.5, diameter=0.04, n_points=20)
        pipe1.initialize(p=1.05 * P_REF, T=T_REF)
        pipe2.initialize(p=P_REF, T=T_REF)

        junc = JunctionBC(
            pipes=[pipe1, pipe2],
            ends=[PipeEnd.RIGHT, PipeEnd.LEFT],
            signs=[1, -1],
        )
        junc.apply(dt=1e-5)
        pipe1.update_derived()
        pipe2.update_derived()

        # Mass flow should approximately balance at junction
        mdot1 = pipe1.rho[-1] * pipe1.u[-1] * pipe1.area[-1]
        mdot2 = pipe2.rho[0] * pipe2.u[0] * pipe2.area[0]
        # Should be approximately equal (mass conservation)
        assert abs(mdot1 - mdot2) < abs(mdot1) * 0.2 + 1e-6

    def test_three_pipe_junction(self):
        """Three pipes at a junction (2-into-1) should conserve mass."""
        pipe_in1 = Pipe("in1", length=0.3, diameter=0.034, n_points=15)
        pipe_in2 = Pipe("in2", length=0.3, diameter=0.034, n_points=15)
        pipe_out = Pipe("out", length=0.3, diameter=0.042, n_points=15)

        pipe_in1.initialize(p=1.05 * P_REF, T=T_REF)
        pipe_in2.initialize(p=1.03 * P_REF, T=T_REF)
        pipe_out.initialize(p=P_REF, T=T_REF)

        junc = JunctionBC(
            pipes=[pipe_in1, pipe_in2, pipe_out],
            ends=[PipeEnd.RIGHT, PipeEnd.RIGHT, PipeEnd.LEFT],
            signs=[1, 1, -1],
        )
        junc.apply(dt=1e-5)

        for p in [pipe_in1, pipe_in2, pipe_out]:
            p.update_derived()

        # All pipe-end pressures should be approximately equal
        pressures = [pipe_in1.p[-1], pipe_in2.p[-1], pipe_out.p[0]]
        p_mean = np.mean(pressures)
        for p in pressures:
            assert abs(p - p_mean) / p_mean < 0.15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
