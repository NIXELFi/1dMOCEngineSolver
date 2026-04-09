"""Verify the corrected gas property formulas + plenum BC are producing the
expected (p, T, ρ) at the runner inlet AND at the runner-valve end."""
import os
os.environ["MPLBACKEND"] = "Agg"

import numpy as np
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.gas_dynamics.gas_properties import (
    R_AIR, P_REF, T_REF, GAMMA_REF, AA_from_p_T,
)

cfg = EngineConfig()
sim = SimulationOrchestrator(cfg)
rpm = 10000.0
print(f"Running 8 cycles at {rpm:.0f} RPM ...")
perf = sim.run_single_rpm(rpm, n_cycles=8, verbose=False)

print(f"\nPlenum (post-converged): p={sim.restrictor_plenum.p/1e5:.3f} bar, T={sim.restrictor_plenum.T:.1f} K")
print(f"  AA_plen (computed) = {AA_from_p_T(sim.restrictor_plenum.p, sim.restrictor_plenum.T):.4f}")
print(f"  ρ_plen (ideal gas) = {sim.restrictor_plenum.p/(R_AIR*sim.restrictor_plenum.T):.4f} kg/m³")

for runner_idx, runner in enumerate(sim.intake_runners[:1]):
    print(f"\n--- Intake runner {runner_idx+1} state at end of recorded cycle ---")
    print(f"  n_points = {runner.n_points}")
    for j in [0, 1, 5, 14, 28, 29]:
        idx = j if j < runner.n_points else runner.n_points - 1
        rho_ideal = runner.p[idx] / (R_AIR * runner.T[idx])
        print(
            f"  i={idx:>3}  λ={runner.lam[idx]:.4f}  β={runner.bet[idx]:.4f}  "
            f"AA={runner.AA[idx]:.4f}  A={runner.A_nd[idx]:.4f}  "
            f"p={runner.p[idx]/1e5:.3f} bar  T={runner.T[idx]:.1f} K  "
            f"ρ={runner.rho[idx]:.4f}  ρ_ig={rho_ideal:.4f}"
        )

# Inspect mid-cycle pressure history to see ram boost behavior
mid = runner.n_points // 2
key = f"{runner.name}_mid"
probe = sim.results.pipe_probes.get(key)
if probe:
    p_arr = np.array(probe.pressure)
    u_arr = np.array(probe.velocity)
    th = np.array(probe.theta) % 720.0
    print(f"\nRunner 1 midpoint over recorded cycle:")
    print(f"  pressure   range: {p_arr.min()/1e5:.3f} … {p_arr.max()/1e5:.3f} bar  mean {p_arr.mean()/1e5:.3f}")
    print(f"  velocity   range: {u_arr.min():.1f} … {u_arr.max():.1f} m/s  mean {u_arr.mean():.1f}")

# Cylinder peak / IVC state from last cycle
cyl0 = sim.cylinders[0]
print(f"\nCylinder 0 final-cycle state:")
print(f"  p_at_IVC = {cyl0.p_at_IVC/1e5:.2f} bar, T_at_IVC = {cyl0.T_at_IVC:.0f} K")
print(f"  m_intake_total = {cyl0.m_intake_total*1000:.4f} g")
print(f"  m_fuel = {cyl0.m_fuel*1e6:.2f} mg")
print(f"  work_cycle = {cyl0.work_cycle:.1f} J")
print(f"  IMEP_cyl0 = {cyl0.work_cycle/cyl0.geometry.V_d/1e5:.2f} bar")
print(f"\nPerformance:")
print(f"  power_indicated = {perf['indicated_power_hp']:.1f} hp ({perf['indicated_power_kW']:.1f} kW)")
print(f"  VE_atm = {perf['volumetric_efficiency_atm']*100:.1f}%")
print(f"  VE_plen = {perf['volumetric_efficiency_plenum']*100:.1f}%")
print(f"  IMEP = {perf['imep_bar']:.2f} bar")
