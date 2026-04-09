"""Tests for cylinder model components."""

import numpy as np
import pytest

from engine_simulator.config.engine_config import CylinderConfig, CombustionConfig, ValveConfig
from engine_simulator.engine.geometry import EngineGeometry
from engine_simulator.engine.combustion import WiebeCombustion
from engine_simulator.engine.heat_transfer import WoschniHeatTransfer
from engine_simulator.engine.valve import Valve


class TestGeometry:
    @pytest.fixture
    def geom(self):
        cfg = CylinderConfig(
            bore=0.067, stroke=0.0425, con_rod_length=0.0963,
            compression_ratio=12.2,
        )
        return EngineGeometry(cfg)

    def test_displacement(self, geom):
        """Displacement volume should match spec."""
        assert abs(geom.V_d * 1e6 - 149.75) < 1.0  # cc

    def test_clearance_volume(self, geom):
        """Clearance volume = V_d / (CR - 1)."""
        V_c_expected = geom.V_d / (12.2 - 1.0)
        assert abs(geom.V_c - V_c_expected) < 1e-8

    def test_volume_at_tdc(self, geom):
        """Volume at TDC should equal clearance volume."""
        V_tdc = geom.volume(0.0)
        assert abs(V_tdc - geom.V_c) < 1e-10

    def test_volume_at_bdc(self, geom):
        """Volume at BDC should equal V_c + V_d."""
        V_bdc = geom.volume(180.0)
        assert abs(V_bdc - (geom.V_c + geom.V_d)) < geom.V_d * 0.01

    def test_compression_ratio(self, geom):
        """V_BDC / V_TDC should equal compression ratio."""
        cr_computed = geom.volume(180.0) / geom.volume(0.0)
        assert abs(cr_computed - 12.2) < 0.1

    def test_dVdtheta_at_tdc(self, geom):
        """dV/dtheta should be zero at TDC (piston at rest)."""
        dVdth = geom.dVdtheta(0.0)
        assert abs(dVdth) < 1e-8

    def test_dVdtheta_at_bdc(self, geom):
        """dV/dtheta should be zero at BDC."""
        dVdth = geom.dVdtheta(180.0)
        assert abs(dVdth) < 1e-8

    def test_volume_symmetry(self, geom):
        """Volume should be symmetric about TDC (for single revolution)."""
        V_30 = geom.volume(30.0)
        V_330 = geom.volume(330.0)
        # Not exactly equal due to con-rod effect, but close
        assert abs(V_30 - V_330) / geom.V_d < 0.05


class TestCombustion:
    @pytest.fixture
    def wiebe(self):
        cfg = CombustionConfig(
            wiebe_a=5.0, wiebe_m=2.0, combustion_duration=50.0,
            spark_advance=25.0, ignition_delay=7.0,
        )
        return WiebeCombustion(cfg)

    def test_zero_before_start(self, wiebe):
        """No burn before combustion starts."""
        assert wiebe.mass_fraction_burned(-30.0) == 0.0

    def test_complete_after_end(self, wiebe):
        """Burn should be ~1.0 after combustion ends."""
        xb = wiebe.mass_fraction_burned(wiebe.theta_end_canonical + 1.0)
        assert xb > 0.99

    def test_wiebe_at_50pct(self, wiebe):
        """Mass fraction should be approximately 0.5 near 50% point."""
        # Find 50% burn angle numerically
        thetas = np.linspace(wiebe.theta_start_canonical, wiebe.theta_end_canonical, 1000)
        xb = [wiebe.mass_fraction_burned(t) for t in thetas]
        idx_50 = np.argmin(np.abs(np.array(xb) - 0.5))
        assert 0.3 < xb[idx_50] < 0.7

    def test_burn_rate_positive(self, wiebe):
        """Burn rate should be positive during combustion."""
        thetas = np.linspace(wiebe.theta_start_canonical + 1, wiebe.theta_end_canonical - 1, 100)
        for t in thetas:
            assert wiebe.burn_rate(t) >= 0

    def test_total_integral(self, wiebe):
        """Integral of burn rate over duration should be ~1.0."""
        thetas = np.linspace(wiebe.theta_start_canonical, wiebe.theta_end_canonical, 10000)
        dth = thetas[1] - thetas[0]
        rates = [wiebe.burn_rate(t) for t in thetas]
        integral = np.sum(rates) * dth
        assert abs(integral - 1.0) < 0.02


class TestHeatTransfer:
    def test_woschni_positive(self):
        ht = WoschniHeatTransfer(bore=0.067, stroke=0.0425)
        ht.set_reference_state(p_IVC=1e5, T_IVC=350.0, V_IVC=1.5e-4)
        h = ht.heat_transfer_coefficient(
            p=20e5, T=2000.0, rpm=10000, V=1.5e-5, V_d=1.5e-4,
            phase="combustion"
        )
        assert h > 0
        assert h < 1e5  # reasonable upper bound


class TestValve:
    @pytest.fixture
    def intake_valve(self):
        cfg = ValveConfig(
            diameter=0.0275, max_lift=0.0081,
            open_angle=338.0, close_angle=583.0,
            cd_table=[(0.05, 0.20), (0.10, 0.40), (0.15, 0.52),
                      (0.20, 0.58), (0.25, 0.60), (0.30, 0.60)],
        )
        return Valve(cfg, n_valves=2)

    def test_closed_before_open(self, intake_valve):
        assert not intake_valve.is_open(300.0)
        assert intake_valve.lift(300.0) == 0.0

    def test_open_at_midpoint(self, intake_valve):
        mid = (338.0 + 583.0) / 2.0  # 460.5
        assert intake_valve.is_open(mid)
        L = intake_valve.lift(mid)
        assert abs(L - 0.0081) < 0.001  # near max lift at midpoint

    def test_closed_after_close(self, intake_valve):
        assert not intake_valve.is_open(600.0)

    def test_effective_area_positive(self, intake_valve):
        A = intake_valve.effective_area(460.0)
        assert A > 0

    def test_effective_area_zero_when_closed(self, intake_valve):
        A = intake_valve.effective_area(0.0)
        assert A == 0.0

    def test_cd_interpolation(self, intake_valve):
        cd = intake_valve.discharge_coefficient(0.0025)  # L/D ~ 0.09
        assert 0.15 < cd < 0.45

    def test_mass_flow_subsonic(self, intake_valve):
        mdot = intake_valve.mass_flow_compressible(
            p_upstream=1.1e5, T_upstream=300.0, p_downstream=1.0e5,
            A_eff=1e-4
        )
        assert mdot > 0

    def test_mass_flow_choked(self, intake_valve):
        mdot = intake_valve.mass_flow_compressible(
            p_upstream=3e5, T_upstream=300.0, p_downstream=1e5,
            A_eff=1e-4
        )
        assert mdot > 0
        # Choked flow should not increase if we lower downstream pressure more
        mdot2 = intake_valve.mass_flow_compressible(
            p_upstream=3e5, T_upstream=300.0, p_downstream=0.5e5,
            A_eff=1e-4
        )
        assert abs(mdot2 - mdot) / mdot < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
