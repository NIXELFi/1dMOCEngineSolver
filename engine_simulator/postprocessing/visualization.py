"""Visualization routines for simulation results."""

from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from engine_simulator.postprocessing.results import SimulationResults


def _check_matplotlib():
    if not HAS_MATPLOTLIB:
        raise ImportError("matplotlib is required for visualization. Install with: pip install matplotlib")


def _split_cycles(theta, *arrays):
    """Insert NaN at cycle boundaries (where wrapped theta drops) so that
    matplotlib does not draw straight lines connecting the end of one cycle
    to the start of the next when plotting theta % 720 over multiple cycles.

    Returns (theta_with_nans, *arrays_with_nans).
    """
    theta = np.asarray(theta, dtype=float)
    if theta.size < 2:
        return (theta,) + tuple(np.asarray(a, dtype=float) for a in arrays)
    # A wrap is where theta drops by more than half its range.
    wraps = np.where(np.diff(theta) < -360.0)[0] + 1
    if wraps.size == 0:
        return (theta,) + tuple(np.asarray(a, dtype=float) for a in arrays)
    out_theta = np.insert(theta, wraps, np.nan)
    out_arrays = tuple(np.insert(np.asarray(a, dtype=float), wraps, np.nan) for a in arrays)
    return (out_theta,) + out_arrays


def _extract_power_torque_layers(sweep_results: list[dict]) -> dict:
    """Extract indicated/brake/wheel power and torque series from sweep dicts.

    Returns a dict with keys: rpm, p_ind, p_brk, p_whl, t_ind, t_brk, t_whl.

    The wheel and brake series use a two-level defensive fallback: if
    ``wheel_power_hp`` is missing, fall back to ``brake_power_hp``; if
    ``brake_power_hp`` is also missing, fall back to ``indicated_power_hp``.
    Same for torque. This keeps legacy result dicts (pre-drivetrain-feature
    pickled sweeps) renderable without crashing — they'll just show three
    overlapping curves instead of three distinct loss layers.
    """
    rpm   = [r["rpm"] for r in sweep_results]
    p_ind = [r["indicated_power_hp"] for r in sweep_results]
    p_brk = [r.get("brake_power_hp", r["indicated_power_hp"]) for r in sweep_results]
    p_whl = [r.get("wheel_power_hp", r.get("brake_power_hp", r["indicated_power_hp"]))
             for r in sweep_results]
    t_ind = [r["indicated_torque_Nm"] for r in sweep_results]
    t_brk = [r.get("brake_torque_Nm", r["indicated_torque_Nm"]) for r in sweep_results]
    t_whl = [r.get("wheel_torque_Nm", r.get("brake_torque_Nm", r["indicated_torque_Nm"]))
             for r in sweep_results]
    return {
        "rpm": rpm,
        "p_ind": p_ind, "p_brk": p_brk, "p_whl": p_whl,
        "t_ind": t_ind, "t_brk": t_brk, "t_whl": t_whl,
    }


def plot_cylinder_pressure(results: SimulationResults, cyl_id: int = 0,
                            title: str = "Cylinder Pressure vs Crank Angle",
                            save_path: Optional[str] = None):
    """Plot in-cylinder pressure trace vs crank angle."""
    _check_matplotlib()

    data = results.get_cylinder_arrays(cyl_id)
    if not data:
        print(f"No data for cylinder {cyl_id}")
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    theta = data["theta"] % 720.0
    p_bar = data["pressure"] / 1e5
    theta, p_bar = _split_cycles(theta, p_bar)

    ax.plot(theta, p_bar, "b-", linewidth=0.8)
    ax.set_xlabel("Crank Angle (degrees)")
    ax.set_ylabel("Pressure (bar)")
    ax.set_title(title)
    ax.set_xlim(0, 720)
    ax.grid(True, alpha=0.3)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()


def plot_pv_diagram(results: SimulationResults, geometry, cyl_id: int = 0,
                     log_scale: bool = True, save_path: Optional[str] = None):
    """Plot P-V (indicator) diagram."""
    _check_matplotlib()

    data = results.get_cylinder_arrays(cyl_id)
    if not data:
        print(f"No data for cylinder {cyl_id}")
        return

    theta_wrapped = data["theta"] % 720.0
    V = geometry.volume_array(theta_wrapped) * 1e6  # cc
    p_bar = data["pressure"] / 1e5
    _, V, p_bar = _split_cycles(theta_wrapped, V, p_bar)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(V, p_bar, "b-", linewidth=0.8)
    ax.set_xlabel("Volume (cc)")
    ax.set_ylabel("Pressure (bar)")
    ax.set_title("P-V Diagram")
    if log_scale:
        ax.set_xscale("log")
        ax.set_yscale("log")
    ax.grid(True, alpha=0.3)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()


def plot_pipe_pressure(results: SimulationResults, pipe_name: str,
                        save_path: Optional[str] = None):
    """Plot pressure history at pipe midpoint."""
    _check_matplotlib()

    data = results.get_pipe_probe_arrays(pipe_name)
    if not data:
        print(f"No data for pipe {pipe_name}")
        return

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    theta = data["theta"] % 720.0
    pressure_bar = data["pressure"] / 1e5
    velocity = data["velocity"]
    theta, pressure_bar, velocity = _split_cycles(theta, pressure_bar, velocity)
    axes[0].plot(theta, pressure_bar, "r-", linewidth=0.8)
    axes[0].set_ylabel("Pressure (bar)")
    axes[0].set_title(f"Pipe: {pipe_name} — Midpoint")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(theta, velocity, "g-", linewidth=0.8)
    axes[1].set_ylabel("Velocity (m/s)")
    axes[1].set_xlabel("Crank Angle (degrees)")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()


def plot_rpm_sweep(sweep_results: list[dict], save_path: Optional[str] = None):
    """Plot power, torque, and VE vs RPM from sweep results.

    Shows three loss layers on power and torque: indicated (cylinder PV
    work), brake (after engine FMEP), and wheel (after drivetrain
    efficiency). Wheel uses dashed blue so the eye groups it with brake
    as the same loss family.
    """
    _check_matplotlib()

    layers = _extract_power_torque_layers(sweep_results)
    rpm   = layers["rpm"]
    p_ind = layers["p_ind"]
    p_brk = layers["p_brk"]
    p_whl = layers["p_whl"]
    t_ind = layers["t_ind"]
    t_brk = layers["t_brk"]
    t_whl = layers["t_whl"]
    ve_plen = [r["volumetric_efficiency_plenum"] * 100 for r in sweep_results]
    ve_atm = [r["volumetric_efficiency_atm"] * 100 for r in sweep_results]

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    axes[0].plot(rpm, p_ind, "r-o", markersize=4, linewidth=1.5, label="Indicated")
    axes[0].plot(rpm, p_brk, "b-s", markersize=4, linewidth=1.5, label="Brake")
    axes[0].plot(rpm, p_whl, "b--^", markersize=4, linewidth=1.5, label="Wheel")
    axes[0].set_ylabel("Power (hp)")
    axes[0].set_title("Engine Performance vs RPM (FSAE Restricted CBR600RR)")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="best")

    axes[1].plot(rpm, t_ind, "r-o", markersize=4, linewidth=1.5, label="Indicated")
    axes[1].plot(rpm, t_brk, "b-s", markersize=4, linewidth=1.5, label="Brake")
    axes[1].plot(rpm, t_whl, "b--^", markersize=4, linewidth=1.5, label="Wheel")
    axes[1].set_ylabel("Torque (Nm)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="best")

    axes[2].plot(rpm, ve_plen, "g-o", markersize=4, linewidth=1.5, label="VE (plenum ref)")
    axes[2].plot(rpm, ve_atm, "m-s", markersize=4, linewidth=1.5, label="VE (atmospheric ref)")
    axes[2].set_ylabel("Volumetric Efficiency (%)")
    axes[2].set_xlabel("Engine Speed (RPM)")
    axes[2].grid(True, alpha=0.3)
    axes[2].axhline(y=100, color="k", linestyle="--", alpha=0.3)
    axes[2].legend(loc="best")

    # Mark restrictor choking
    choked_rpm = [r["rpm"] for r in sweep_results if r["restrictor_choked"]]
    if choked_rpm:
        for ax in axes:
            ax.axvspan(min(choked_rpm), max(choked_rpm), alpha=0.1, color="red",
                       label="Restrictor choked" if ax == axes[0] else None)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()


def plot_valve_timing(intake_valve, exhaust_valve, save_path: Optional[str] = None):
    """Plot valve lift profiles on a polar diagram."""
    _check_matplotlib()

    theta = np.linspace(0, 720, 1441)
    theta_rad = np.radians(theta / 2.0)  # map 720° to 360° for polar

    lift_intake = np.array([intake_valve.lift(t) * 1000 for t in theta])  # mm
    lift_exhaust = np.array([exhaust_valve.lift(t) * 1000 for t in theta])  # mm

    fig, ax = plt.subplots(subplot_kw={"projection": "polar"}, figsize=(8, 8))
    ax.plot(theta_rad, lift_intake, "b-", label="Intake", linewidth=1.5)
    ax.plot(theta_rad, lift_exhaust, "r-", label="Exhaust", linewidth=1.5)
    ax.set_title("Valve Timing Diagram", pad=20)
    ax.legend(loc="upper right")

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()


def plot_restrictor_flow(results: SimulationResults, save_path: Optional[str] = None):
    """Plot restrictor mass flow rate vs crank angle."""
    _check_matplotlib()

    theta = np.array(results.theta_history) % 720.0
    mdot = np.array(results.restrictor_mdot) * 1000  # g/s
    theta, mdot = _split_cycles(theta, mdot)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(theta, mdot, "m-", linewidth=0.8)
    ax.set_xlabel("Crank Angle (degrees)")
    ax.set_ylabel("Restrictor Mass Flow (g/s)")
    ax.set_title("Restrictor Mass Flow Rate")
    ax.grid(True, alpha=0.3)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()


def plot_dashboard(results: SimulationResults, sweep_results: list[dict],
                    geometry=None, save_path: Optional[str] = None):
    """Create a comprehensive dashboard with multiple subplots."""
    _check_matplotlib()

    fig = plt.figure(figsize=(16, 12))
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.35, wspace=0.3)

    # 1. Power & Torque vs RPM — nested 2-row gridspec inside the gs[0, 0:2]
    # cell so we can show all three loss layers (indicated / brake / wheel)
    # without 6 lines on a single twin-axis plot.
    layers = _extract_power_torque_layers(sweep_results)
    rpm   = layers["rpm"]
    p_ind = layers["p_ind"]
    p_brk = layers["p_brk"]
    p_whl = layers["p_whl"]
    t_ind = layers["t_ind"]
    t_brk = layers["t_brk"]
    t_whl = layers["t_whl"]

    inner_pt = gs[0, 0:2].subgridspec(2, 1, hspace=0.15)
    ax1p = fig.add_subplot(inner_pt[0, 0])
    ax1t = fig.add_subplot(inner_pt[1, 0], sharex=ax1p)

    ax1p.plot(rpm, p_ind, "r-o", markersize=3, linewidth=1.2, label="Indicated")
    ax1p.plot(rpm, p_brk, "b-s", markersize=3, linewidth=1.2, label="Brake")
    ax1p.plot(rpm, p_whl, "b--^", markersize=3, linewidth=1.2, label="Wheel")
    ax1p.set_ylabel("Power (hp)")
    ax1p.set_title("Power & Torque vs RPM")
    ax1p.grid(True, alpha=0.3)
    ax1p.legend(loc="best", fontsize=8)
    plt.setp(ax1p.get_xticklabels(), visible=False)

    ax1t.plot(rpm, t_ind, "r-o", markersize=3, linewidth=1.2, label="Indicated")
    ax1t.plot(rpm, t_brk, "b-s", markersize=3, linewidth=1.2, label="Brake")
    ax1t.plot(rpm, t_whl, "b--^", markersize=3, linewidth=1.2, label="Wheel")
    ax1t.set_xlabel("RPM")
    ax1t.set_ylabel("Torque (Nm)")
    ax1t.grid(True, alpha=0.3)
    ax1t.legend(loc="best", fontsize=8)

    # 2. Volumetric Efficiency — show BOTH the atm-referenced curve (the
    # conventional bounded metric) and the plenum-referenced curve (which
    # naturally exceeds 100% with ram tuning because the plenum is
    # sub-atmospheric for a restricted engine). Plotting only the plenum-ref
    # curve makes it look like VE is "exploding past 140%" when actually
    # the engine is filling correctly relative to the air it has access to.
    ax2 = fig.add_subplot(gs[0, 2])
    ve_atm_plot = [r["volumetric_efficiency_atm"] * 100 for r in sweep_results]
    ve_plen_plot = [r["volumetric_efficiency_plenum"] * 100 for r in sweep_results]
    ax2.plot(rpm, ve_atm_plot, "g-o", markersize=3, label="VE (atm-ref)")
    ax2.plot(rpm, ve_plen_plot, "g--", markersize=3, alpha=0.5, label="VE (plenum-ref)")
    ax2.set_xlabel("RPM")
    ax2.set_ylabel("VE (%)")
    ax2.set_title("Volumetric Efficiency")
    ax2.axhline(100, color="k", linestyle="--", alpha=0.3)
    ax2.legend(loc="best", fontsize=8)
    ax2.grid(True, alpha=0.3)

    # 3. Cylinder pressure trace (Cyl 0)
    ax3 = fig.add_subplot(gs[1, 0:2])
    cyl_data = results.get_cylinder_arrays(0)
    if cyl_data:
        theta_c = cyl_data["theta"] % 720.0
        p_cyl_bar = cyl_data["pressure"] / 1e5
        theta_c_plot, p_cyl_plot = _split_cycles(theta_c, p_cyl_bar)
        ax3.plot(theta_c_plot, p_cyl_plot, "b-", linewidth=0.5)
        ax3.set_xlabel("Crank Angle (deg)")
        ax3.set_ylabel("Pressure (bar)")
        ax3.set_title("Cylinder 1 Pressure")
        ax3.set_xlim(0, 720)
        ax3.grid(True, alpha=0.3)

    # 4. P-V diagram
    ax4 = fig.add_subplot(gs[1, 2])
    if cyl_data and geometry is not None:
        theta_pv = cyl_data["theta"] % 720.0
        V_cc = geometry.volume_array(theta_pv) * 1e6
        p_pv_bar = cyl_data["pressure"] / 1e5
        _, V_cc, p_pv_bar = _split_cycles(theta_pv, V_cc, p_pv_bar)
        ax4.plot(V_cc, p_pv_bar, "b-", linewidth=0.5)
        ax4.set_xlabel("Volume (cc)")
        ax4.set_ylabel("Pressure (bar)")
        ax4.set_title("P-V Diagram")
        ax4.set_xscale("log")
        ax4.set_yscale("log")
        ax4.grid(True, alpha=0.3)

    # 5. Plenum pressure
    ax5 = fig.add_subplot(gs[2, 0])
    if results.plenum_pressure:
        theta_p = np.array(results.theta_history) % 720.0
        p_plen_bar = np.array(results.plenum_pressure) / 1e5
        theta_p_plot, p_plen_plot = _split_cycles(theta_p, p_plen_bar)
        ax5.plot(theta_p_plot, p_plen_plot, "c-", linewidth=0.5)
        ax5.set_xlabel("Crank Angle (deg)")
        ax5.set_ylabel("Pressure (bar)")
        ax5.set_title("Plenum Pressure")
        ax5.grid(True, alpha=0.3)

    # 6. Restrictor mass flow
    ax6 = fig.add_subplot(gs[2, 1])
    if results.restrictor_mdot:
        theta_r = np.array(results.theta_history) % 720.0
        mdot_g = np.array(results.restrictor_mdot) * 1000
        theta_r_plot, mdot_g_plot = _split_cycles(theta_r, mdot_g)
        ax6.plot(theta_r_plot, mdot_g_plot, "m-", linewidth=0.5)
        ax6.set_xlabel("Crank Angle (deg)")
        ax6.set_ylabel("Mass Flow (g/s)")
        ax6.set_title("Restrictor Flow")
        ax6.grid(True, alpha=0.3)

    # 7. IMEP bar chart
    ax7 = fig.add_subplot(gs[2, 2])
    imep = [r["imep_bar"] for r in sweep_results]
    ax7.bar(rpm, imep, width=rpm[1] - rpm[0] if len(rpm) > 1 else 200, color="orange", alpha=0.7)
    ax7.set_xlabel("RPM")
    ax7.set_ylabel("IMEP (bar)")
    ax7.set_title("IMEP vs RPM")
    ax7.grid(True, alpha=0.3)

    fig.suptitle("1D Engine Simulator — Honda CBR600RR (FSAE Restricted)", fontsize=14, y=0.98)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.show()
