"""Chart rendering module for PDF reports.

Each public function accepts data, creates a matplotlib figure, saves it to
an io.BytesIO as SVG, and returns the SVG string (or a list of SVG strings).
All figures are rendered headless via the Agg backend.
"""

from __future__ import annotations

import io
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
C_BLUE        = "#2563eb"
C_BLUE_LIGHT  = "#60a5fa"
C_ORANGE      = "#ea580c"
C_GREEN       = "#16a34a"
C_GREEN_LIGHT = "#4ade80"
C_PURPLE      = "#9333ea"
C_RED         = "#dc2626"
C_CYAN        = "#0891b2"

GRID_COLOR    = "#e0e0e0"
GRID_ALPHA    = 0.6
GRID_LW       = 0.5
LINE_WIDTH    = 1.5
MARKER_SIZE   = 4

# Per-cylinder colour rotation
CYL_COLORS = [C_BLUE, C_ORANGE, C_GREEN, C_PURPLE, C_CYAN, C_RED]

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _apply_style(ax, xlabel: str = "", ylabel: str = "", title: str = "") -> None:
    """Apply consistent label, grid, and spine style to an Axes."""
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold")
    ax.grid(True, color=GRID_COLOR, alpha=GRID_ALPHA, linewidth=GRID_LW)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=8)


def _fig_to_svg(fig) -> str:
    """Render a matplotlib Figure to an SVG string, then close the figure."""
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read().decode("utf-8")


def _split_cycles(theta, *arrays):
    """Insert NaN at cycle wrap points (diff < -360) to prevent line artifacts.

    Returns (theta_with_nans, *arrays_with_nans).
    """
    theta = np.asarray(theta, dtype=float)
    if theta.size < 2:
        return (theta,) + tuple(np.asarray(a, dtype=float) for a in arrays)
    wraps = np.where(np.diff(theta) < -360.0)[0] + 1
    if wraps.size == 0:
        return (theta,) + tuple(np.asarray(a, dtype=float) for a in arrays)
    out_theta = np.insert(theta, wraps, np.nan)
    out_arrays = tuple(
        np.insert(np.asarray(a, dtype=float), wraps, np.nan) for a in arrays
    )
    return (out_theta,) + out_arrays


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_sweep_curves(perf_data: list[dict]) -> list[str]:
    """Return 6 SVG strings covering the RPM-sweep performance metrics.

    Charts (in order):
      1. Power (HP) — indicated / brake / wheel
      2. Torque (Nm) — indicated / brake / wheel
      3. Volumetric Efficiency (%) — atm / plenum + 100 % reference line
      4. IMEP / BMEP (bar)
      5. Plenum Pressure (bar)
      6. Restrictor Mass Flow (g/s) with choked markers
    """
    rpm      = [r["rpm"] for r in perf_data]
    p_ind    = [r["indicated_power_hp"] for r in perf_data]
    p_brk    = [r.get("brake_power_hp", r["indicated_power_hp"]) for r in perf_data]
    p_whl    = [r.get("wheel_power_hp", r.get("brake_power_hp", r["indicated_power_hp"])) for r in perf_data]
    t_ind    = [r["indicated_torque_Nm"] for r in perf_data]
    t_brk    = [r.get("brake_torque_Nm", r["indicated_torque_Nm"]) for r in perf_data]
    t_whl    = [r.get("wheel_torque_Nm", r.get("brake_torque_Nm", r["indicated_torque_Nm"])) for r in perf_data]
    ve_atm   = [r["volumetric_efficiency_atm"] * 100 for r in perf_data]
    ve_plen  = [r["volumetric_efficiency_plenum"] * 100 for r in perf_data]
    imep     = [r["imep_bar"] for r in perf_data]
    bmep     = [r["bmep_bar"] for r in perf_data]
    p_plen   = [r.get("plenum_pressure_bar", r.get("plenum_pressure", 0) / 1e5) for r in perf_data]
    mdot_gs  = [r["restrictor_mdot"] * 1000 for r in perf_data]
    choked   = [r["restrictor_choked"] for r in perf_data]

    svgs = []

    # 1. Power
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, p_ind, color=C_ORANGE, linewidth=LINE_WIDTH, marker="o",
            markersize=MARKER_SIZE, label="Indicated")
    ax.plot(rpm, p_brk, color=C_BLUE, linewidth=LINE_WIDTH, marker="s",
            markersize=MARKER_SIZE, label="Brake")
    ax.plot(rpm, p_whl, color=C_BLUE_LIGHT, linewidth=LINE_WIDTH, linestyle="--",
            marker="^", markersize=MARKER_SIZE, label="Wheel")
    ax.legend(fontsize=8)
    _apply_style(ax, xlabel="RPM", ylabel="Power (HP)", title="Power vs RPM")
    fig.tight_layout()
    svgs.append(_fig_to_svg(fig))

    # 2. Torque
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, t_ind, color=C_ORANGE, linewidth=LINE_WIDTH, marker="o",
            markersize=MARKER_SIZE, label="Indicated")
    ax.plot(rpm, t_brk, color=C_BLUE, linewidth=LINE_WIDTH, marker="s",
            markersize=MARKER_SIZE, label="Brake")
    ax.plot(rpm, t_whl, color=C_BLUE_LIGHT, linewidth=LINE_WIDTH, linestyle="--",
            marker="^", markersize=MARKER_SIZE, label="Wheel")
    ax.legend(fontsize=8)
    _apply_style(ax, xlabel="RPM", ylabel="Torque (Nm)", title="Torque vs RPM")
    fig.tight_layout()
    svgs.append(_fig_to_svg(fig))

    # 3. Volumetric Efficiency
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, ve_atm, color=C_GREEN, linewidth=LINE_WIDTH, marker="o",
            markersize=MARKER_SIZE, label="VE atm-ref")
    ax.plot(rpm, ve_plen, color=C_GREEN_LIGHT, linewidth=LINE_WIDTH, linestyle="--",
            marker="s", markersize=MARKER_SIZE, label="VE plenum-ref")
    ax.axhline(100, color="#888888", linestyle=":", linewidth=1.0, label="100%")
    ax.legend(fontsize=8)
    _apply_style(ax, xlabel="RPM", ylabel="VE (%)", title="Volumetric Efficiency vs RPM")
    fig.tight_layout()
    svgs.append(_fig_to_svg(fig))

    # 4. IMEP / BMEP
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, imep, color=C_ORANGE, linewidth=LINE_WIDTH, marker="o",
            markersize=MARKER_SIZE, label="IMEP")
    ax.plot(rpm, bmep, color=C_BLUE, linewidth=LINE_WIDTH, marker="s",
            markersize=MARKER_SIZE, label="BMEP")
    ax.legend(fontsize=8)
    _apply_style(ax, xlabel="RPM", ylabel="Pressure (bar)", title="IMEP / BMEP vs RPM")
    fig.tight_layout()
    svgs.append(_fig_to_svg(fig))

    # 5. Plenum Pressure
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, p_plen, color=C_CYAN, linewidth=LINE_WIDTH, marker="o",
            markersize=MARKER_SIZE)
    _apply_style(ax, xlabel="RPM", ylabel="Pressure (bar)", title="Plenum Pressure vs RPM")
    fig.tight_layout()
    svgs.append(_fig_to_svg(fig))

    # 6. Restrictor Flow
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(rpm, mdot_gs, color=C_PURPLE, linewidth=LINE_WIDTH, marker="o",
            markersize=MARKER_SIZE, label="Mass flow")
    choked_rpm   = [r for r, c in zip(rpm, choked) if c]
    choked_mdot  = [m for m, c in zip(mdot_gs, choked) if c]
    if choked_rpm:
        ax.scatter(choked_rpm, choked_mdot, color=C_RED, marker="x", s=60,
                   zorder=5, label="Choked")
    ax.legend(fontsize=8)
    _apply_style(ax, xlabel="RPM", ylabel="Mass Flow (g/s)",
                 title="Restrictor Mass Flow vs RPM")
    fig.tight_layout()
    svgs.append(_fig_to_svg(fig))

    return svgs


def render_convergence_overview(convergence_data: dict) -> str:
    """Bar chart: cycles-to-converge for each RPM point.

    convergence_data: {rpm_float: {"converged": bool, "converged_at_cycle": int, ...}}
    Green bars for converged, red for not converged.
    """
    rpms   = sorted(convergence_data.keys())
    cycles = []
    colors = []
    for r in rpms:
        info = convergence_data[r]
        cycles.append(info.get("converged_at_cycle", 0) or 0)
        colors.append(C_GREEN if info.get("converged", False) else C_RED)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    x = np.arange(len(rpms))
    bars = ax.bar(x, cycles, color=colors, width=0.6, edgecolor="white", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(r)}" for r in rpms], rotation=45, ha="right", fontsize=7)
    _apply_style(ax, xlabel="RPM", ylabel="Cycles to Converge",
                 title="Convergence Overview")

    # Legend patches
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C_GREEN, label="Converged"),
        Patch(facecolor=C_RED, label="Not converged"),
    ]
    ax.legend(handles=legend_elements, fontsize=8)
    fig.tight_layout()
    return _fig_to_svg(fig)


def render_cylinder_traces(results: dict) -> list[str]:
    """Return [pressure_svg, temperature_svg] with all cylinders overlaid.

    results must have a "cylinder_data" key mapping string cid -> dict with
    "theta", "pressure", "temperature" arrays.
    """
    cyl_data = results.get("cylinder_data", {})
    cids     = sorted(cyl_data.keys(), key=lambda k: int(k))

    svgs = []

    for field, ylabel, title, scale in [
        ("pressure",    "Pressure (bar)",    "Cylinder Pressure vs Crank Angle",    1e5),
        ("temperature", "Temperature (K)",   "Cylinder Temperature vs Crank Angle", 1.0),
    ]:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        for idx, cid in enumerate(cids):
            data  = cyl_data[cid]
            theta = np.asarray(data["theta"], dtype=float) % 720.0
            vals  = np.asarray(data[field], dtype=float) / scale
            theta_p, vals_p = _split_cycles(theta, vals)
            color = CYL_COLORS[idx % len(CYL_COLORS)]
            ax.plot(theta_p, vals_p, color=color, linewidth=LINE_WIDTH,
                    label=f"Cyl {cid}")
        ax.set_xlim(0, 720)
        ax.legend(fontsize=8)
        _apply_style(ax, xlabel="Crank Angle (deg)", ylabel=ylabel, title=title)
        fig.tight_layout()
        svgs.append(_fig_to_svg(fig))

    return svgs


def render_pv_diagrams(results: dict, engine_config: dict) -> str:
    """P-V diagram on log-log scale for all cylinders.

    Volume is computed from slider-crank geometry using bore, stroke,
    con_rod_length, and compression_ratio from engine_config["cylinder"].
    """
    cyl_cfg = engine_config["cylinder"]
    bore    = cyl_cfg["bore"]           # m
    stroke  = cyl_cfg["stroke"]         # m
    l_rod   = cyl_cfg["con_rod_length"] # m
    cr      = cyl_cfg["compression_ratio"]

    r_crank  = stroke / 2.0
    Vd       = math.pi / 4.0 * bore ** 2 * stroke  # displacement volume (m³)
    Vc       = Vd / (cr - 1.0)                     # clearance volume (m³)

    def _slider_crank_volume(theta_deg):
        """Instantaneous cylinder volume (m³) for given crank angle (degrees)."""
        theta_rad = np.radians(np.asarray(theta_deg, dtype=float))
        # Piston position from TDC
        cos_t = np.cos(theta_rad)
        sin_t = np.sin(theta_rad)
        lambda_ = r_crank / l_rod
        x = r_crank * (1.0 - cos_t) + l_rod * (1.0 - np.sqrt(1.0 - (lambda_ * sin_t) ** 2))
        return Vc + math.pi / 4.0 * bore ** 2 * x

    cyl_data = results.get("cylinder_data", {})
    cids     = sorted(cyl_data.keys(), key=lambda k: int(k))

    fig, ax = plt.subplots(figsize=(7, 3.5))
    for idx, cid in enumerate(cids):
        data      = cyl_data[cid]
        theta_raw = np.asarray(data["theta"], dtype=float) % 720.0
        pressure  = np.asarray(data["pressure"], dtype=float) / 1e5  # bar
        V_cc      = _slider_crank_volume(theta_raw) * 1e6  # cc

        # Split at wrap points (theta wraps)
        _, V_cc_p, pressure_p = _split_cycles(theta_raw, V_cc, pressure)
        color = CYL_COLORS[idx % len(CYL_COLORS)]
        ax.plot(V_cc_p, pressure_p, color=color, linewidth=LINE_WIDTH,
                label=f"Cyl {cid}")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.legend(fontsize=8)
    _apply_style(ax, xlabel="Volume (cc)", ylabel="Pressure (bar)", title="P-V Diagram")
    fig.tight_layout()
    return _fig_to_svg(fig)


def render_pipe_traces(results: dict) -> list[str]:
    """Return [pressure_svg, temperature_svg, velocity_svg].

    Each figure has two subplots: left=intake probes, right=exhaust probes.
    Probes are separated by "intake"/"exhaust" in their name.
    results must have a "pipe_probes" key.
    """
    probes      = results.get("pipe_probes", {})
    intake_keys = sorted(k for k in probes if "intake" in k.lower())
    exhaust_keys= sorted(k for k in probes if "exhaust" in k.lower())
    other_keys  = sorted(k for k in probes if k not in intake_keys and k not in exhaust_keys)

    # Assign unclassified pipes to intake side for display purposes
    intake_keys  = intake_keys + other_keys

    fields = [
        ("pressure",    "Pressure (bar)",  "Pipe Pressure Traces",    1e5),
        ("temperature", "Temperature (K)", "Pipe Temperature Traces", 1.0),
        ("velocity",    "Velocity (m/s)",  "Pipe Velocity Traces",    1.0),
    ]

    svgs = []
    for field, ylabel, title, scale in fields:
        fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(7, 3.5), sharey=False)
        fig.suptitle(title, fontsize=10, fontweight="bold")

        for ax, key_list, side_label in [
            (ax_l, intake_keys,  "Intake"),
            (ax_r, exhaust_keys, "Exhaust"),
        ]:
            for idx, name in enumerate(key_list):
                data  = probes[name]
                theta = np.asarray(data["theta"], dtype=float) % 720.0
                vals  = np.asarray(data.get(field, []), dtype=float) / scale
                theta_p, vals_p = _split_cycles(theta, vals)
                color = CYL_COLORS[idx % len(CYL_COLORS)]
                ax.plot(theta_p, vals_p, color=color, linewidth=LINE_WIDTH,
                        label=name)
            ax.set_xlim(0, 720)
            _apply_style(ax, xlabel="Crank Angle (deg)", ylabel=ylabel,
                         title=side_label)
            if key_list:
                ax.legend(fontsize=7)

        fig.tight_layout()
        svgs.append(_fig_to_svg(fig))

    return svgs


def render_plenum_chart(results: dict) -> str:
    """Two-subplot figure: plenum pressure (bar) and temperature (K) vs crank angle."""
    theta_raw = np.asarray(results.get("theta_history", []), dtype=float) % 720.0
    p_bar     = np.asarray(results.get("plenum_pressure", []), dtype=float) / 1e5
    temp_k    = np.asarray(results.get("plenum_temperature", []), dtype=float)

    fig, (ax_p, ax_t) = plt.subplots(2, 1, figsize=(7, 3.5), sharex=True)
    fig.suptitle("Plenum Conditions vs Crank Angle", fontsize=10, fontweight="bold")

    if theta_raw.size > 0:
        theta_p, p_p = _split_cycles(theta_raw, p_bar)
        ax_p.plot(theta_p, p_p, color=C_CYAN, linewidth=LINE_WIDTH)
    ax_p.set_xlim(0, 720)
    _apply_style(ax_p, ylabel="Pressure (bar)")
    ax_p.spines["bottom"].set_visible(False)
    ax_p.tick_params(bottom=False)

    if theta_raw.size > 0:
        theta_t, temp_t = _split_cycles(theta_raw, temp_k)
        ax_t.plot(theta_t, temp_t, color=C_ORANGE, linewidth=LINE_WIDTH)
    ax_t.set_xlim(0, 720)
    _apply_style(ax_t, xlabel="Crank Angle (deg)", ylabel="Temperature (K)")

    fig.tight_layout()
    return _fig_to_svg(fig)


def render_restrictor_chart(results: dict) -> str:
    """Mass flow (g/s) vs crank angle with choked regions shaded."""
    theta_raw = np.asarray(results.get("theta_history", []), dtype=float) % 720.0
    mdot_gs   = np.asarray(results.get("restrictor_mdot", []), dtype=float) * 1000
    choked    = np.asarray(results.get("restrictor_choked", []), dtype=bool)

    fig, ax = plt.subplots(figsize=(7, 3.5))

    if theta_raw.size > 0:
        theta_p, mdot_p = _split_cycles(theta_raw, mdot_gs)
        ax.plot(theta_p, mdot_p, color=C_PURPLE, linewidth=LINE_WIDTH,
                label="Mass flow")

        # Shade choked regions
        if choked.size == theta_raw.size and choked.any():
            # Find contiguous choked intervals and shade them
            in_choked = False
            start_theta = None
            for i, (th, is_choked) in enumerate(zip(theta_raw, choked)):
                if is_choked and not in_choked:
                    start_theta = th
                    in_choked = True
                elif not is_choked and in_choked:
                    ax.axvspan(start_theta, th, alpha=0.15, color=C_RED)
                    in_choked = False
            if in_choked and start_theta is not None:
                ax.axvspan(start_theta, theta_raw[-1], alpha=0.15, color=C_RED,
                           label="Choked")

    ax.set_xlim(0, 720)
    ax.legend(fontsize=8)
    _apply_style(ax, xlabel="Crank Angle (deg)", ylabel="Mass Flow (g/s)",
                 title="Restrictor Mass Flow Rate")
    fig.tight_layout()
    return _fig_to_svg(fig)


def render_convergence_detail(
    delta_history: list,
    p_ivc_history: list,
) -> list[str]:
    """Return [delta_svg, p_ivc_svg].

    delta_history: list where index=cycle; first entry may be None (no delta
    for cycle 0).  Plotted on a semilogy scale.

    p_ivc_history: list of lists — outer index=cycle, inner index=cylinder.
    Values divided by 1e5 to get bar.
    """
    svgs = []

    # 1. Delta (convergence metric) per cycle — semilogy
    fig, ax = plt.subplots(figsize=(7, 3.5))
    cycles_d = []
    vals_d   = []
    for i, v in enumerate(delta_history):
        if v is not None:
            cycles_d.append(i)
            vals_d.append(v)
    if cycles_d:
        ax.semilogy(cycles_d, vals_d, color=C_BLUE, linewidth=LINE_WIDTH,
                    marker="o", markersize=MARKER_SIZE)
    _apply_style(ax, xlabel="Cycle", ylabel="Convergence Delta",
                 title="Convergence Delta per Cycle")
    fig.tight_layout()
    svgs.append(_fig_to_svg(fig))

    # 2. p_IVC per cylinder per cycle
    fig, ax = plt.subplots(figsize=(7, 3.5))
    if p_ivc_history:
        n_cycles = len(p_ivc_history)
        n_cyls   = len(p_ivc_history[0]) if p_ivc_history else 0
        cycles_x = np.arange(n_cycles)
        for cyl_idx in range(n_cyls):
            p_vals = np.array([p_ivc_history[c][cyl_idx] for c in range(n_cycles)]) / 1e5
            color  = CYL_COLORS[cyl_idx % len(CYL_COLORS)]
            ax.plot(cycles_x, p_vals, color=color, linewidth=LINE_WIDTH,
                    marker="o", markersize=MARKER_SIZE, label=f"Cyl {cyl_idx}")
    ax.legend(fontsize=8)
    _apply_style(ax, xlabel="Cycle", ylabel="p_IVC (bar)",
                 title="IVC Pressure per Cycle")
    fig.tight_layout()
    svgs.append(_fig_to_svg(fig))

    return svgs
