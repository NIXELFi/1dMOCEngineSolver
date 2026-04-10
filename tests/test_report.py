"""Tests for report generation orchestration."""

import json
import os


def _load_sample_sweep():
    """Load the smaller saved sweep for testing."""
    sweep_path = os.path.join(
        os.path.dirname(__file__), "..", "sweeps",
        "2026-04-10T03-47-56_2500-15000_step1000_12cyc.json",
    )
    with open(sweep_path) as f:
        return json.load(f)


def test_generate_report_returns_pdf_bytes():
    """generate_report should return bytes starting with %PDF."""
    from engine_simulator.gui.report import generate_report
    sweep_data = _load_sample_sweep()
    pdf_bytes = generate_report(sweep_data)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 1000


def test_generate_report_with_no_convergence_data():
    """Report should generate even without convergence data."""
    from engine_simulator.gui.report import generate_report
    sweep_data = _load_sample_sweep()
    sweep_data.pop("convergence", None)
    pdf_bytes = generate_report(sweep_data)
    assert pdf_bytes[:5] == b"%PDF-"
