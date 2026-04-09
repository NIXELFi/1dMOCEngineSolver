"""Tests for drivetrain-loss feature: scalar parameter, helper, and integration."""

import pytest

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.postprocessing.performance import apply_drivetrain_losses
from engine_simulator.simulation.orchestrator import SimulationOrchestrator


class TestApplyDrivetrainLosses:
    def test_typical_efficiency(self):
        # 100 W brake, 0.85 eff -> 85 W wheel
        assert apply_drivetrain_losses(100.0, 0.85) == pytest.approx(85.0)

    def test_perfect_efficiency_passes_through(self):
        assert apply_drivetrain_losses(100.0, 1.0) == pytest.approx(100.0)

    def test_zero_brake_power(self):
        assert apply_drivetrain_losses(0.0, 0.85) == pytest.approx(0.0)

    def test_real_units_sanity(self):
        # 50 kW brake, 0.5 eff -> 25 kW wheel
        assert apply_drivetrain_losses(50_000.0, 0.5) == pytest.approx(25_000.0)


class TestDrivetrainEfficiencyValidation:
    def test_default_value_is_1_0(self):
        # Default disables the drivetrain layer (wheel == brake). Users opt
        # in by setting a value < 1.0 when comparing against a chassis dyno.
        cfg = EngineConfig()
        assert cfg.drivetrain_efficiency == pytest.approx(1.0)

    def test_custom_valid_value(self):
        cfg = EngineConfig(drivetrain_efficiency=0.9)
        assert cfg.drivetrain_efficiency == pytest.approx(0.9)

    def test_boundary_one_is_valid(self):
        cfg = EngineConfig(drivetrain_efficiency=1.0)
        assert cfg.drivetrain_efficiency == pytest.approx(1.0)

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="drivetrain_efficiency"):
            EngineConfig(drivetrain_efficiency=0.0)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="drivetrain_efficiency"):
            EngineConfig(drivetrain_efficiency=-0.1)

    def test_above_one_raises(self):
        with pytest.raises(ValueError, match="drivetrain_efficiency"):
            EngineConfig(drivetrain_efficiency=1.5)


class TestDrivetrainIntegration:
    """End-to-end: drivetrain efficiency must scale brake_power into wheel_power
    in the orchestrator's performance dict."""

    def test_wheel_power_equals_brake_times_efficiency(self):
        cfg = EngineConfig(drivetrain_efficiency=0.5)
        sim = SimulationOrchestrator(cfg)
        perf = sim.run_single_rpm(8000.0, n_cycles=2, verbose=False)

        assert "wheel_power_hp" in perf
        assert "wheel_power_kW" in perf
        assert "wheel_torque_Nm" in perf
        assert "drivetrain_efficiency" in perf

        assert perf["wheel_power_hp"] == pytest.approx(perf["brake_power_hp"] * 0.5)
        assert perf["wheel_power_kW"] == pytest.approx(perf["brake_power_kW"] * 0.5)
        assert perf["wheel_torque_Nm"] == pytest.approx(perf["brake_torque_Nm"] * 0.5)
        assert perf["drivetrain_efficiency"] == pytest.approx(0.5)

    def test_efficiency_one_means_wheel_equals_brake(self):
        cfg = EngineConfig(drivetrain_efficiency=1.0)
        sim = SimulationOrchestrator(cfg)
        perf = sim.run_single_rpm(8000.0, n_cycles=2, verbose=False)

        assert perf["wheel_power_hp"] == pytest.approx(perf["brake_power_hp"])
        assert perf["wheel_torque_Nm"] == pytest.approx(perf["brake_torque_Nm"])

    def test_drivetrain_does_not_back_leak_into_brake(self):
        """Changing drivetrain_efficiency must not change brake_power_hp.
        Brake is upstream of drivetrain in the loss chain."""
        cfg_a = EngineConfig(drivetrain_efficiency=0.5)
        cfg_b = EngineConfig(drivetrain_efficiency=0.9)

        sim_a = SimulationOrchestrator(cfg_a)
        sim_b = SimulationOrchestrator(cfg_b)

        perf_a = sim_a.run_single_rpm(8000.0, n_cycles=2, verbose=False)
        perf_b = sim_b.run_single_rpm(8000.0, n_cycles=2, verbose=False)

        # Brake numbers must be identical (drivetrain is downstream)
        assert perf_a["brake_power_hp"] == pytest.approx(perf_b["brake_power_hp"])
        assert perf_a["indicated_power_hp"] == pytest.approx(perf_b["indicated_power_hp"])

        # But wheel numbers must differ proportionally
        assert perf_b["wheel_power_hp"] == pytest.approx(
            perf_a["wheel_power_hp"] * (0.9 / 0.5)
        )
