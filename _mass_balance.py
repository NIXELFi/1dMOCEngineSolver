"""Mass balance diagnostic: restrictor flow vs cylinder intake mass per cycle."""
import os
os.environ["MPLBACKEND"] = "Agg"

import numpy as np
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.postprocessing.performance import restrictor_max_mass_flow

cfg = EngineConfig()
print("Config:")
print(f"  Restrictor: D={cfg.restrictor.throat_diameter*1000:.1f} mm, Cd={cfg.restrictor.discharge_coefficient}")
print(f"  Plenum vol: {cfg.plenum.volume*1e3:.2f} L")
print(f"  Cylinder: bore={cfg.cylinder.bore*1000:.1f} mm, stroke={cfg.cylinder.stroke*1000:.1f} mm, CR={cfg.cylinder.compression_ratio}")
print(f"  N cyl: {cfg.n_cylinders}")
print(f"  V_d per cyl: {(np.pi/4*cfg.cylinder.bore**2 * cfg.cylinder.stroke)*1e6:.1f} cc")
print(f"  Total V_d: {(np.pi/4*cfg.cylinder.bore**2 * cfg.cylinder.stroke * cfg.n_cylinders)*1e6:.1f} cc")
print(f"  p_amb={cfg.p_ambient:.0f} Pa, T_amb={cfg.T_ambient:.0f} K")

# Theoretical choked max
mdot_max = restrictor_max_mass_flow(
    throat_diameter=cfg.restrictor.throat_diameter,
    Cd=cfg.restrictor.discharge_coefficient,
    p0=cfg.p_ambient,
    T0=cfg.T_ambient,
)
print(f"\nTheoretical choked max mdot: {mdot_max*1000:.2f} g/s")

V_d_total = np.pi/4 * cfg.cylinder.bore**2 * cfg.cylinder.stroke * cfg.n_cylinders
rho_atm = cfg.p_ambient / (287.0 * cfg.T_ambient)

print(f"  rho_atm = {rho_atm:.3f} kg/m^3")

for rpm in [8000.0, 10000.0, 12000.0]:
    print(f"\n=== {rpm:.0f} RPM ===")
    cycle_time = 120.0 / rpm  # 4-stroke cycle = 2 revs
    air_at_VE100_per_cycle = rho_atm * V_d_total
    mdot_required_VE100 = air_at_VE100_per_cycle / cycle_time
    print(f"  Cycle time: {cycle_time*1000:.2f} ms")
    print(f"  air @ VE=100% (atm): {air_at_VE100_per_cycle*1000:.3f} g/cycle = {mdot_required_VE100*1000:.2f} g/s")
    print(f"  Choke ceiling = {mdot_max/mdot_required_VE100*100:.1f}% of VE=100% atm demand")

    sim = SimulationOrchestrator(cfg)
    perf = sim.run_single_rpm(rpm, n_cycles=8, verbose=False)

    # Compute mass balance from recorded last cycle
    theta_arr = np.array(sim.results.theta_history)
    dt_arr = np.array(sim.results.dt_history)
    mdot_arr = np.array(sim.results.restrictor_mdot)
    p_plen_arr = np.array(sim.results.plenum_pressure)
    T_plen_arr = np.array(sim.results.plenum_temperature)

    # Total restrictor mass in the recorded period
    restrictor_mass = float(np.sum(mdot_arr * dt_arr))
    elapsed = float(np.sum(dt_arr))
    avg_restrictor_mdot = restrictor_mass / elapsed if elapsed > 0 else 0.0

    # Total cylinder intake/exhaust (last cycle)
    cyl_intake_total = sum(c.m_intake_total for c in sim.cylinders)
    cyl_exhaust_total = sum(c.m_exhaust_total for c in sim.cylinders)
    n_recorded_cycles = elapsed / cycle_time
    avg_cyl_mdot = cyl_intake_total / (n_recorded_cycles * cycle_time) if n_recorded_cycles > 0 else 0.0

    # Plenum mass change over recorded period (uses ideal gas; not exact since solver tracks self.m)
    M_plen_start = p_plen_arr[0] * cfg.plenum.volume / (287.0 * T_plen_arr[0])
    M_plen_end = p_plen_arr[-1] * cfg.plenum.volume / (287.0 * T_plen_arr[-1])
    dM_plen = M_plen_end - M_plen_start

    print(f"  Recorded period: {elapsed*1000:.2f} ms = {n_recorded_cycles:.2f} cycles ({len(theta_arr)} steps)")
    print(f"  Restrictor mass in:    {restrictor_mass*1000:.4f} g  (avg {avg_restrictor_mdot*1000:.2f} g/s)")
    print(f"  Cylinder intake (sum): {cyl_intake_total*1000:.4f} g  (avg {avg_cyl_mdot*1000:.2f} g/s)")
    print(f"  Cylinder exhaust (sum):{cyl_exhaust_total*1000:.4f} g")
    print(f"  Plenum dM over period: {dM_plen*1000:+.4f} g (start {M_plen_start*1000:.3f} -> end {M_plen_end*1000:.3f})")
    print(f"  Plenum p: avg={np.mean(p_plen_arr)/1e5:.3f} bar  start={p_plen_arr[0]/1e5:.3f} end={p_plen_arr[-1]/1e5:.3f}")
    print(f"  Plenum T: avg={np.mean(T_plen_arr):.1f} K")

    # Mass balance: restrictor_in - cyl_intake = dM_plen?
    balance = restrictor_mass - cyl_intake_total - dM_plen
    print(f"  Mass balance:  restrictor - cyl_intake - dM_plen = {balance*1000:+.4f} g")
    print(f"     (should be ~0 if mass is conserved)")
    print(f"     leak as fraction of cyl intake: {balance/cyl_intake_total*100:+.2f}%")

    print(
        f"  Sim VE_atm:  {perf['volumetric_efficiency_atm']*100:6.1f}%"
        f"   VE_plen: {perf['volumetric_efficiency_plenum']*100:6.1f}%"
        f"   power_indicated: {perf['indicated_power_hp']:.1f} hp"
    )
    rho_plen = np.mean(p_plen_arr) / (287 * np.mean(T_plen_arr))
    VE_plen = cyl_intake_total / (rho_plen * V_d_total)
    print(f"  Sim VE_plen (using actual plenum density {rho_plen:.3f}): {VE_plen*100:.1f}%")
