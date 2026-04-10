"""PDF report generation for engine simulation sweeps.

Orchestrates: data extraction → chart rendering → Jinja2 template → WeasyPrint PDF.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from engine_simulator.gui import report_charts


_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_NAME = "report_template.html"


def _ensure_library_path():
    """Ensure WeasyPrint can find system libraries on macOS (Homebrew)."""
    if sys.platform == "darwin":
        homebrew_lib = "/opt/homebrew/lib"
        fallback = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        if homebrew_lib not in fallback:
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
                f"{homebrew_lib}:{fallback}" if fallback else homebrew_lib
            )


def _extract_headline_stats(perf_data: list[dict]) -> dict:
    """Find peak power and peak torque from the perf list."""
    peak_power = max(perf_data, key=lambda p: p.get("brake_power_hp", 0))
    peak_torque = max(perf_data, key=lambda p: p.get("brake_torque_Nm", 0))
    return {
        "peak_power_hp": peak_power["brake_power_hp"],
        "peak_power_rpm": peak_power["rpm"],
        "peak_torque_nm": peak_torque["brake_torque_Nm"],
        "peak_torque_rpm": peak_torque["rpm"],
    }


def _build_convergence_table(convergence: dict, perf_data: list[dict]) -> list[SimpleNamespace]:
    """Build convergence summary table rows."""
    rows = []
    for p in perf_data:
        rpm = p["rpm"]
        conv = convergence.get(str(rpm), convergence.get(str(float(rpm)), {}))
        delta_hist = conv.get("delta_history", [])
        converged = conv.get("converged", False)
        converged_at = conv.get("converged_at_cycle")
        final_delta = "—"
        for d in reversed(delta_hist):
            if d is not None:
                final_delta = f"{d:.4e}"
                break
        rows.append(SimpleNamespace(
            rpm=rpm,
            converged=converged,
            cycles=converged_at if converged_at is not None else len(delta_hist),
            final_delta=final_delta,
        ))
    return rows


def _build_perf_rows(perf_data: list[dict]) -> list[SimpleNamespace]:
    """Convert perf dicts to SimpleNamespace for template dot-access."""
    return [SimpleNamespace(**p) for p in perf_data]


def _build_rpm_detail_pages(perf_data, results_by_rpm, convergence, engine_config):
    """Build per-RPM detail page data with pre-rendered chart SVGs."""
    pages = []
    for p in perf_data:
        rpm = p["rpm"]
        rpm_key = str(rpm)
        results = results_by_rpm.get(rpm_key, results_by_rpm.get(str(float(rpm)), {}))
        conv = convergence.get(rpm_key, convergence.get(str(float(rpm)), {}))

        cylinder_svgs = report_charts.render_cylinder_traces(results) if results.get("cylinder_data") else []
        pv_svg = report_charts.render_pv_diagrams(results, engine_config) if results.get("cylinder_data") else ""
        pipe_svgs = report_charts.render_pipe_traces(results) if results.get("pipe_probes") else []
        plenum_svg = report_charts.render_plenum_chart(results) if results.get("plenum_pressure") else ""
        restrictor_svg = report_charts.render_restrictor_chart(results) if results.get("restrictor_mdot") else ""

        delta_hist = conv.get("delta_history", [])
        p_ivc_hist = conv.get("p_ivc_history", [])
        convergence_svgs = report_charts.render_convergence_detail(delta_hist, p_ivc_hist) if delta_hist else []

        pages.append(SimpleNamespace(
            rpm=rpm,
            cylinder_svgs=cylinder_svgs,
            pv_svg=pv_svg,
            pipe_svgs=pipe_svgs,
            plenum_svg=plenum_svg,
            restrictor_svg=restrictor_svg,
            convergence_svgs=convergence_svgs,
        ))
    return pages


def _deep_namespace(d):
    """Recursively convert dicts to allow dot-access in Jinja2.
    Returns a dict whose nested dicts become SimpleNamespace,
    lists of dicts become lists of SimpleNamespace, primitives stay as-is.
    """
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = SimpleNamespace(**_deep_namespace(v))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            out[k] = [SimpleNamespace(**_deep_namespace(item)) for item in v]
        elif isinstance(v, list) and v and isinstance(v[0], list):
            out[k] = v  # cd_table is list of [float, float]
        else:
            out[k] = v
    return out


def generate_report(sweep_data: dict) -> bytes:
    """Generate a PDF report from sweep data (as loaded from the sweep JSON).
    Returns PDF bytes.
    """
    _ensure_library_path()
    from weasyprint import HTML

    perf_data = sweep_data.get("perf", [])
    engine_config = sweep_data.get("engine_config", {})
    results_by_rpm = sweep_data.get("results_by_rpm", {})
    convergence = sweep_data.get("convergence", {})
    metadata = sweep_data.get("metadata", {})

    stats = _extract_headline_stats(perf_data)

    sweep_date = metadata.get("started_at", "Unknown")
    if "T" in sweep_date:
        sweep_date = sweep_date.replace("T", " ").split(".")[0] + " UTC"

    config_name = metadata.get("config_name", "Unknown")
    if config_name.endswith(".json"):
        config_name = config_name[:-5]

    sweep_curve_svgs = report_charts.render_sweep_curves(perf_data)

    convergence_overview_svg = ""
    if convergence:
        conv_for_overview = {float(k): v for k, v in convergence.items()}
        convergence_overview_svg = report_charts.render_convergence_overview(conv_for_overview)

    convergence_table = _build_convergence_table(convergence, perf_data)
    perf_rows = _build_perf_rows(perf_data)
    rpm_detail_pages = _build_rpm_detail_pages(perf_data, results_by_rpm, convergence, engine_config)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,  # SVG must not be escaped
    )
    template = env.get_template(_TEMPLATE_NAME)
    html_str = template.render(
        config_name=config_name,
        sweep_date=sweep_date,
        engine_config=SimpleNamespace(**_deep_namespace(engine_config)),
        perf_data=perf_rows,
        sweep_curve_svgs=sweep_curve_svgs,
        convergence_overview_svg=convergence_overview_svg,
        convergence_table=convergence_table,
        rpm_detail_pages=rpm_detail_pages,
        **stats,
    )

    return HTML(string=html_str).write_pdf()
