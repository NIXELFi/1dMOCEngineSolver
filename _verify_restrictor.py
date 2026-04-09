"""Issue 3 verification: FSAE 20mm restrictor choked-flow behavior.

Runs the simulator at 10000 RPM for 8 cycles and checks:
  - Plenum pressure vs ambient (critical ratio 0.5283 for gamma=1.4)
  - Simulated steady-state mass flow vs theoretical choked max
  - lb/min conversion vs the 14.477 lb/min throttle body cap
"""

from __future__ import annotations

import math

import numpy as np

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator


KG_PER_LB = 0.45359237
GAMMA = 1.4
R_AIR = 287.05


def theoretical_choked_mdot(Cd: float, D: float, p0: float, T0: float,
                            gamma: float = GAMMA, R: float = R_AIR) -> float:
    """mdot = Cd * A * p0 * sqrt(gamma / (R*T0)) * (2/(gamma+1))^((gamma+1)/(2(gamma-1)))"""
    A = math.pi / 4.0 * D * D
    choke = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
    return Cd * A * p0 * math.sqrt(gamma / (R * T0)) * choke


def main() -> None:
    cfg = EngineConfig()

    p0 = cfg.p_ambient
    T0 = cfg.T_ambient
    D = cfg.restrictor.throat_diameter
    Cd_current = cfg.restrictor.discharge_coefficient

    Cd_baseline = 0.95
    Cd_adjusted = Cd_baseline * 1.018

    mdot_current = theoretical_choked_mdot(Cd_current, D, p0, T0)
    mdot_base = theoretical_choked_mdot(Cd_baseline, D, p0, T0)
    mdot_adj = theoretical_choked_mdot(Cd_adjusted, D, p0, T0)

    print("=" * 72)
    print("Issue 3: FSAE 20 mm restrictor verification")
    print("=" * 72)
    print(f"Ambient:      p0 = {p0:.1f} Pa, T0 = {T0:.1f} K")
    print(f"Throat diam:  D  = {D*1000:.3f} mm,  A = {math.pi/4*D*D*1e6:.3f} mm^2")
    print()
    print("Theoretical choked mass flow (p0=101325 Pa, T0=300 K, D=0.020 m):")
    print(f"  Current Cd   = {Cd_current:.4f}  -> {mdot_current*1000:7.3f} g/s"
          f"  ({mdot_current/KG_PER_LB*60:6.3f} lb/min)")
    print(f"  Baseline Cd  = {Cd_baseline:.4f}  -> {mdot_base*1000:7.3f} g/s"
          f"  ({mdot_base/KG_PER_LB*60:6.3f} lb/min)")
    print(f"  +1.8% Cd     = {Cd_adjusted:.4f}  -> {mdot_adj*1000:7.3f} g/s"
          f"  ({mdot_adj/KG_PER_LB*60:6.3f} lb/min)")
    print()
    print(f"Critical pressure ratio (gamma=1.4) = "
          f"{(2.0/(GAMMA+1.0))**(GAMMA/(GAMMA-1.0)):.4f}")
    print()

    print("-" * 72)
    print("Running simulator at 10000 RPM for 8 cycles...")
    print("-" * 72)

    sim = SimulationOrchestrator(cfg)
    perf = sim.run_single_rpm(rpm=10000.0, n_cycles=8, verbose=False)
    print()

    # Pull recorded arrays
    theta = np.array(sim.results.theta_history)
    dt_arr = np.array(sim.results.dt_history)
    p_plen = np.array(sim.results.plenum_pressure)
    mdot = np.array(sim.results.restrictor_mdot)
    choked_flags = np.array(sim.results.restrictor_choked, dtype=bool)

    if len(theta) == 0:
        print("ERROR: no recorded samples. Aborting.")
        return

    # Steady-state window: last recorded cycle (720 deg at 4-stroke)
    theta_end = theta[-1]
    mask = theta >= (theta_end - 720.0)
    p_plen_win = p_plen[mask]
    mdot_win = mdot[mask]
    dt_win = dt_arr[mask]
    choked_win = choked_flags[mask]

    p_plen_mean = float(np.mean(p_plen_win))
    p_plen_min = float(np.min(p_plen_win))
    p_plen_max = float(np.max(p_plen_win))

    # Time-averaged mass flow over the window
    total_time = float(np.sum(dt_win))
    mdot_avg = float(np.sum(mdot_win * dt_win) / total_time) if total_time > 0 else 0.0
    mdot_peak = float(np.max(mdot_win))

    pr_mean = p_plen_mean / p0
    pr_min = p_plen_min / p0
    pr_max = p_plen_max / p0
    pr_crit = (2.0 / (GAMMA + 1.0)) ** (GAMMA / (GAMMA - 1.0))

    choked_fraction = float(np.mean(choked_win.astype(float))) if choked_win.size else 0.0

    print(f"Recorded samples in last cycle: {len(p_plen_win)}  (dt span {total_time*1000:.3f} ms)")
    print()
    print("Plenum pressure over last cycle:")
    print(f"  mean = {p_plen_mean:9.1f} Pa  ({p_plen_mean/1e5:.4f} bar)")
    print(f"  min  = {p_plen_min:9.1f} Pa  ({p_plen_min/1e5:.4f} bar)")
    print(f"  max  = {p_plen_max:9.1f} Pa  ({p_plen_max/1e5:.4f} bar)")
    print()
    print("Pressure ratio p_plenum / p_ambient:")
    print(f"  mean = {pr_mean:.4f}")
    print(f"  min  = {pr_min:.4f}")
    print(f"  max  = {pr_max:.4f}")
    print(f"  critical (gamma=1.4) = {pr_crit:.4f}")
    if pr_max <= pr_crit:
        print("  -> FULLY CHOKED throughout last cycle (max pr <= critical)")
    elif pr_mean <= pr_crit:
        print("  -> CHOKED on average (mean pr <= critical)")
    else:
        print("  -> NOT fully choked (mean pr > critical)")
    print(f"  choked flag set in {choked_fraction*100:.1f}% of recorded steps")
    print()

    # Compare simulated steady-state mdot to theoretical choked max at current Cd
    mdot_avg_lbmin = mdot_avg / KG_PER_LB * 60.0
    mdot_peak_lbmin = mdot_peak / KG_PER_LB * 60.0
    mdot_theory_lbmin = mdot_current / KG_PER_LB * 60.0

    print("Restrictor mass flow over last cycle:")
    print(f"  simulated avg  = {mdot_avg*1000:7.3f} g/s  ({mdot_avg_lbmin:6.3f} lb/min)")
    print(f"  simulated peak = {mdot_peak*1000:7.3f} g/s  ({mdot_peak_lbmin:6.3f} lb/min)")
    print(f"  theoretical max (Cd={Cd_current:.4f}) = "
          f"{mdot_current*1000:7.3f} g/s  ({mdot_theory_lbmin:6.3f} lb/min)")
    if mdot_current > 0:
        ratio = mdot_avg / mdot_current
        print(f"  sim_avg / theory_max = {ratio:.4f}  ({ratio*100:.2f}%)")
    print()

    # Throttle body comparison
    tb_cap_lbmin = 14.477
    tb_cap_kgs = tb_cap_lbmin * KG_PER_LB / 60.0
    print("Throttle body (Bosch 32 mm ETC) cap = 14.477 lb/min "
          f"({tb_cap_kgs*1000:.3f} g/s)")
    print(f"  simulated avg = {mdot_avg_lbmin:6.3f} lb/min  "
          f"({mdot_avg_lbmin/tb_cap_lbmin*100:5.1f}% of cap)")
    print(f"  theory max    = {mdot_theory_lbmin:6.3f} lb/min  "
          f"({mdot_theory_lbmin/tb_cap_lbmin*100:5.1f}% of cap)")
    if mdot_theory_lbmin < tb_cap_lbmin:
        print("  -> restrictor is the binding constraint (below TB cap), as expected")
    else:
        print("  -> WARNING: restrictor exceeds TB cap (unexpected)")
    print()

    # Performance dict snapshot
    print("Engine performance summary at 10000 RPM:")
    print(f"  restrictor_choked = {perf.get('restrictor_choked')}")
    print(f"  restrictor_mdot   = {perf.get('restrictor_mdot')*1000:.3f} g/s")
    print(f"  plenum_pressure   = {perf.get('plenum_pressure_bar'):.4f} bar")


if __name__ == "__main__":
    main()
