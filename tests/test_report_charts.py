"""Tests for report chart rendering functions."""

import pytest


SAMPLE_PERF = [
    {
        "rpm": 5000.0,
        "indicated_power_hp": 30.0, "brake_power_hp": 26.0, "wheel_power_hp": 22.0,
        "indicated_torque_Nm": 45.0, "brake_torque_Nm": 39.0, "wheel_torque_Nm": 33.0,
        "volumetric_efficiency_atm": 0.85, "volumetric_efficiency_plenum": 0.92,
        "imep_bar": 10.5, "bmep_bar": 9.1,
        "plenum_pressure_bar": 0.98, "restrictor_mdot": 0.055,
        "restrictor_choked": False,
    },
    {
        "rpm": 8000.0,
        "indicated_power_hp": 55.0, "brake_power_hp": 48.0, "wheel_power_hp": 41.0,
        "indicated_torque_Nm": 51.0, "brake_torque_Nm": 44.0, "wheel_torque_Nm": 38.0,
        "volumetric_efficiency_atm": 0.92, "volumetric_efficiency_plenum": 1.05,
        "imep_bar": 12.1, "bmep_bar": 10.5,
        "plenum_pressure_bar": 0.95, "restrictor_mdot": 0.068,
        "restrictor_choked": True,
    },
]


def test_render_sweep_curves_returns_six_svgs():
    from engine_simulator.gui.report_charts import render_sweep_curves
    svgs = render_sweep_curves(SAMPLE_PERF)
    assert len(svgs) == 6
    for svg in svgs:
        assert "<svg" in svg
        assert "</svg>" in svg


def test_render_convergence_overview_returns_svg():
    from engine_simulator.gui.report_charts import render_convergence_overview
    convergence_data = {
        5000.0: {"converged": True, "converged_at_cycle": 4, "delta_history": [None, 0.1, 0.01, 0.001]},
        8000.0: {"converged": True, "converged_at_cycle": 6, "delta_history": [None, 0.2, 0.08, 0.02, 0.005, 0.001]},
    }
    svg = render_convergence_overview(convergence_data)
    assert "<svg" in svg


def test_render_cylinder_traces_returns_svgs():
    from engine_simulator.gui.report_charts import render_cylinder_traces
    results = {
        "cylinder_data": {
            "0": {
                "theta": [0.0, 180.0, 360.0, 540.0, 720.0],
                "pressure": [101325.0, 500000.0, 3000000.0, 500000.0, 101325.0],
                "temperature": [300.0, 450.0, 2500.0, 1200.0, 400.0],
            },
            "1": {
                "theta": [0.0, 180.0, 360.0, 540.0, 720.0],
                "pressure": [101325.0, 500000.0, 3000000.0, 500000.0, 101325.0],
                "temperature": [300.0, 450.0, 2500.0, 1200.0, 400.0],
            },
        },
    }
    svgs = render_cylinder_traces(results)
    assert len(svgs) == 2  # pressure + temperature
    for svg in svgs:
        assert "<svg" in svg


def test_render_pv_diagrams_returns_svg():
    from engine_simulator.gui.report_charts import render_pv_diagrams
    results = {
        "cylinder_data": {
            "0": {
                "theta": [0.0, 180.0, 360.0, 540.0, 720.0],
                "pressure": [101325.0, 500000.0, 3000000.0, 500000.0, 101325.0],
            },
        },
    }
    engine_config = {
        "cylinder": {
            "bore": 0.067, "stroke": 0.042, "con_rod_length": 0.1,
            "compression_ratio": 12.2,
        },
    }
    svg = render_pv_diagrams(results, engine_config)
    assert "<svg" in svg


def test_render_pipe_traces_returns_svgs():
    from engine_simulator.gui.report_charts import render_pipe_traces
    results = {
        "pipe_probes": {
            "intake_runner_1_mid": {
                "theta": [0.0, 180.0, 360.0, 540.0, 720.0],
                "pressure": [101325.0, 98000.0, 95000.0, 99000.0, 101325.0],
                "temperature": [300.0, 298.0, 295.0, 299.0, 300.0],
                "velocity": [0.0, 50.0, 80.0, 30.0, 0.0],
            },
        },
    }
    svgs = render_pipe_traces(results)
    assert len(svgs) == 3  # pressure, temperature, velocity
    for svg in svgs:
        assert "<svg" in svg


def test_render_plenum_chart_returns_svg():
    from engine_simulator.gui.report_charts import render_plenum_chart
    results = {
        "theta_history": [0.0, 180.0, 360.0, 540.0, 720.0],
        "plenum_pressure": [101325.0, 100000.0, 99000.0, 100500.0, 101000.0],
        "plenum_temperature": [300.0, 299.0, 298.0, 299.5, 300.0],
    }
    svg = render_plenum_chart(results)
    assert "<svg" in svg


def test_render_restrictor_chart_returns_svg():
    from engine_simulator.gui.report_charts import render_restrictor_chart
    results = {
        "theta_history": [0.0, 180.0, 360.0, 540.0, 720.0],
        "restrictor_mdot": [0.05, 0.06, 0.072, 0.065, 0.055],
        "restrictor_choked": [False, False, True, False, False],
    }
    svg = render_restrictor_chart(results)
    assert "<svg" in svg


def test_render_convergence_detail_returns_svgs():
    from engine_simulator.gui.report_charts import render_convergence_detail
    delta_history = [None, 0.15, 0.03, 0.004]
    p_ivc_history = [
        [101000.0, 101100.0, 101050.0, 101075.0],
        [101200.0, 101300.0, 101250.0, 101275.0],
        [101250.0, 101340.0, 101290.0, 101310.0],
        [101252.0, 101342.0, 101291.0, 101312.0],
    ]
    svgs = render_convergence_detail(delta_history, p_ivc_history)
    assert len(svgs) == 2  # delta chart + p_ivc chart
    for svg in svgs:
        assert "<svg" in svg
