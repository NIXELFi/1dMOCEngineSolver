"""Tests for the MOC solver core functionality."""

import numpy as np
import pytest

from engine_simulator.gas_dynamics.gas_properties import (
    A_REF, GAMMA_REF, P_REF, R_AIR, T_REF, RHO_REF,
    AA_from_p_T,
    lambda_from_AU, beta_from_AU, AU_from_riemann,
    pressure_from_A_AA, temperature_from_A_AA, density_from_A_AA,
    A_from_pressure, friction_factor_blasius,
)
from engine_simulator.gas_dynamics.pipe import Pipe
from engine_simulator.gas_dynamics.moc_solver import advance_interior_points
from engine_simulator.gas_dynamics.cfl import compute_cfl_timestep


class TestGasProperties:
    def test_reference_values(self):
        assert abs(A_REF - 347.2) < 1.0  # ~347 m/s at 300K
        assert abs(RHO_REF - 1.177) < 0.01

    def test_riemann_round_trip(self):
        A = np.array([1.0, 1.1, 0.9])
        U = np.array([0.0, 0.1, -0.05])
        lam = lambda_from_AU(A, U)
        bet = beta_from_AU(A, U)
        A2, U2 = AU_from_riemann(lam, bet)
        np.testing.assert_allclose(A2, A, atol=1e-12)
        np.testing.assert_allclose(U2, U, atol=1e-12)

    def test_pressure_at_reference(self):
        p = pressure_from_A_AA(np.array([1.0]), np.array([1.0]))
        assert abs(p[0] - P_REF) < 1.0

    def test_temperature_at_reference(self):
        T = temperature_from_A_AA(np.array([1.0]), np.array([1.0]))
        assert abs(T[0] - T_REF) < 0.1

    def test_A_from_pressure_round_trip(self):
        p_test = 2e5  # 2 bar
        A = A_from_pressure(p_test, AA=1.0)
        p_back = float(pressure_from_A_AA(np.array([A]), np.array([1.0]))[0])
        assert abs(p_back - p_test) / p_test < 1e-6

    def test_friction_factor(self):
        # Laminar
        f_lam = friction_factor_blasius(np.array([1000.0]))
        assert abs(f_lam[0] - 0.064) < 0.002  # 64/Re

        # Turbulent (Blasius)
        f_turb = friction_factor_blasius(np.array([10000.0]))
        assert 0.01 < f_turb[0] < 0.05

    def test_temperature_only_depends_on_A(self):
        """Benson: T = T_ref · A². Two states with the same A but different
        AA must give the same T (entropy doesn't shift T directly).
        """
        A_arr = np.array([1.0, 1.0])
        AA_arr = np.array([1.0, 1.05])  # different entropy
        T = temperature_from_A_AA(A_arr, AA_arr)
        np.testing.assert_allclose(T, T_REF, rtol=1e-12)

    def test_density_matches_ideal_gas(self):
        """Density from (A, AA) must equal p/(R·T) computed via the same
        (p, T) relations. The previous formula ρ = ρ_ref · (A/AA)^(2/(γ−1))
        violated this for AA ≠ 1.
        """
        # Sub-atmospheric warm gas (representative plenum state)
        p_plen = 0.78 * P_REF
        T_plen = T_REF  # 300 K
        AA_plen = float(AA_from_p_T(p_plen, T_plen))
        # By definition this gives A=1 (since T = T_ref → A² = 1)
        A = float(A_from_pressure(p_plen, AA_plen))
        assert abs(A - 1.0) < 1e-10

        rho = float(density_from_A_AA(np.array([A]), np.array([AA_plen]))[0])
        rho_expected = p_plen / (R_AIR * T_plen)
        np.testing.assert_allclose(rho, rho_expected, rtol=1e-10)

    def test_AA_from_p_T_round_trip(self):
        """AA_from_p_T should be the inverse of A_from_pressure for the
        case where (A, AA) corresponds to a given (p, T).
        """
        cases = [
            (P_REF, T_REF),
            (0.78 * P_REF, 300.0),  # warm sub-atm plenum
            (1.4 * P_REF, 350.0),   # mild boost, warmer
        ]
        for p, T in cases:
            AA = float(AA_from_p_T(p, T))
            A = float(A_from_pressure(p, AA))
            # T = T_ref · A²
            T_back = float(temperature_from_A_AA(np.array([A]), np.array([AA]))[0])
            p_back = float(pressure_from_A_AA(np.array([A]), np.array([AA]))[0])
            assert abs(p_back - p) / p < 1e-10
            assert abs(T_back - T) / T < 1e-10

    def test_pipe_initialize_warm_subatm_state(self):
        """A pipe initialized at sub-atmospheric pressure and ambient
        temperature must report exactly that (p, T, ρ) — not the isentropic
        derivative the broken formulation produced.
        """
        pipe = Pipe("warm_subatm", length=0.5, diameter=0.04, n_points=20)
        p_target = 0.78 * P_REF
        T_target = 300.0
        pipe.initialize(p=p_target, T=T_target)
        np.testing.assert_allclose(pipe.p, p_target, rtol=1e-8)
        np.testing.assert_allclose(pipe.T, T_target, rtol=1e-8)
        rho_expected = p_target / (R_AIR * T_target)
        np.testing.assert_allclose(pipe.rho, rho_expected, rtol=1e-8)


class TestPipe:
    def test_creation(self):
        pipe = Pipe("test", length=1.0, diameter=0.05, n_points=50)
        assert pipe.n_points == 50
        assert abs(pipe.dx - 1.0 / 49) < 1e-10
        assert len(pipe.lam) == 50

    def test_initialization(self):
        pipe = Pipe("test", length=1.0, diameter=0.05, n_points=20)
        pipe.initialize(p=P_REF, T=T_REF)
        np.testing.assert_allclose(pipe.p, P_REF, rtol=1e-6)
        np.testing.assert_allclose(pipe.T, T_REF, rtol=1e-6)
        np.testing.assert_allclose(pipe.u, 0.0, atol=1e-10)

    def test_tapered_pipe(self):
        pipe = Pipe("taper", length=0.5, diameter=0.04, n_points=30, diameter_out=0.06)
        assert pipe.diameter[0] < pipe.diameter[-1]
        assert pipe.area[0] < pipe.area[-1]

    def test_max_wave_speed(self):
        pipe = Pipe("test", length=1.0, diameter=0.05, n_points=20)
        pipe.initialize(p=P_REF, T=T_REF)
        ws = pipe.max_wave_speed()
        # With u=0, max wave speed = a = A_REF
        assert abs(ws - A_REF) < 1.0

    def test_cfl_dt(self):
        pipe = Pipe("test", length=0.5, diameter=0.05, n_points=30)
        pipe.initialize()
        dt = pipe.local_cfl_dt()
        assert dt > 0
        # dt should be approximately dx/a_ref
        expected = pipe.dx / A_REF
        assert abs(dt - expected) / expected < 0.1


class TestMOCSolver:
    def test_uniform_state_unchanged(self):
        """A uniform initial state should remain unchanged (no waves)."""
        pipe = Pipe("test", length=1.0, diameter=0.05, n_points=50)
        pipe.initialize(p=P_REF, T=T_REF)

        lam_before = pipe.lam.copy()
        bet_before = pipe.bet.copy()

        dt = 0.5 * pipe.local_cfl_dt()
        # Apply closed ends to prevent boundary issues
        pipe.lam[0] = pipe.bet[0]
        pipe.bet[-1] = pipe.lam[-1]
        advance_interior_points(pipe, dt, include_sources=False)

        # Interior should be essentially unchanged
        np.testing.assert_allclose(pipe.lam[1:-1], lam_before[1:-1], atol=1e-6)
        np.testing.assert_allclose(pipe.bet[1:-1], bet_before[1:-1], atol=1e-6)

    def test_perturbation_propagates(self):
        """A pressure perturbation should propagate through the pipe."""
        pipe = Pipe("test", length=1.0, diameter=0.05, n_points=100)
        pipe.initialize(p=P_REF, T=T_REF)

        # Apply perturbation at midpoint
        mid = pipe.n_points // 2
        pipe.lam[mid] *= 1.05
        pipe.bet[mid] *= 1.05
        pipe.update_derived()

        p_before = pipe.p.copy()

        # Advance several steps
        for _ in range(20):
            dt = 0.8 * pipe.local_cfl_dt()
            pipe.lam[0] = pipe.bet[0]
            pipe.bet[-1] = pipe.lam[-1]
            advance_interior_points(pipe, dt, include_sources=False)

        # Perturbation should have spread
        p_after = pipe.p
        assert np.max(np.abs(p_after - p_before)) > 0.001 * P_REF

    def test_cfl_computation(self):
        pipes = [
            Pipe("p1", length=0.5, diameter=0.04, n_points=30),
            Pipe("p2", length=1.0, diameter=0.06, n_points=40),
        ]
        for p in pipes:
            p.initialize()
        dt = compute_cfl_timestep(pipes, cfl_number=0.85)
        assert dt > 0
        # Should be limited by the pipe with smaller dx
        assert dt < pipes[0].dx / A_REF


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
