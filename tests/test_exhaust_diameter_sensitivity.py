"""Integration test: exhaust primary diameter must affect engine performance.

Runs a few cycles at a single RPM with two different exhaust diameters.
After the impedance-coupled valve BC fix, the model should show measurable
sensitivity to exhaust geometry.
"""

import pytest

from engine_simulator.config.engine_config import load_config
from engine_simulator.simulation.orchestrator import SimulationOrchestrator

CONFIG_PATH = "engine_simulator/config/cbr600rr.json"
TEST_RPM = 8000.0
TEST_CYCLES = 4


def _run_with_exhaust_diameter(diameter: float) -> dict:
    """Load config, override all exhaust primary diameters, run, return perf dict."""
    cfg = load_config(CONFIG_PATH)
    for pc in cfg.exhaust_primaries:
        pc.diameter = diameter
    sim = SimulationOrchestrator(cfg)
    return sim.run_single_rpm(TEST_RPM, n_cycles=TEST_CYCLES, verbose=False)


@pytest.mark.slow
class TestExhaustDiameterSensitivity:
    def test_different_diameters_give_different_indicated_work(self):
        perf_25mm = _run_with_exhaust_diameter(0.025)
        perf_50mm = _run_with_exhaust_diameter(0.050)

        imep_25 = perf_25mm["imep_bar"]
        imep_50 = perf_50mm["imep_bar"]

        pct_diff = abs(imep_25 - imep_50) / max(imep_25, imep_50) * 100

        assert pct_diff > 0.5, (
            f"IMEP should differ by >0.5% between 25mm and 50mm exhaust primaries. "
            f"Got {imep_25:.3f} vs {imep_50:.3f} bar ({pct_diff:.2f}% difference). "
            f"The exhaust model is still insensitive to diameter."
        )

    def test_different_diameters_give_different_ve(self):
        perf_25mm = _run_with_exhaust_diameter(0.025)
        perf_50mm = _run_with_exhaust_diameter(0.050)

        ve_25 = perf_25mm["volumetric_efficiency_atm"]
        ve_50 = perf_50mm["volumetric_efficiency_atm"]

        pct_diff = abs(ve_25 - ve_50) / max(ve_25, ve_50) * 100

        assert pct_diff > 0.5, (
            f"VE_atm should differ by >0.5% between 25mm and 50mm. "
            f"Got {ve_25:.4f} vs {ve_50:.4f} ({pct_diff:.2f}% difference)."
        )
