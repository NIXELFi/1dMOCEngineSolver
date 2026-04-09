"""Detailed mass balance: tracks runner mass and per-runner inlet flow."""
import os
os.environ["MPLBACKEND"] = "Agg"

import numpy as np
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.gas_dynamics.gas_properties import A_REF, GAMMA_REF, R_AIR, P_REF, T_REF, A_from_pressure, density_from_A_AA

cfg = EngineConfig()
sim = SimulationOrchestrator(cfg)

rpm = 10000.0
cycle_time = 120.0 / rpm
n_cycles = 12

# Hook into the run loop manually to capture per-step data
from engine_simulator.engine.kinematics import omega_from_rpm
from engine_simulator.gas_dynamics.cfl import compute_cfl_timestep
from engine_simulator.gas_dynamics.moc_solver import advance_interior_points, extrapolate_boundary_incoming
from engine_simulator.simulation.engine_cycle import EngineCycleTracker
from engine_simulator.simulation.convergence import ConvergenceChecker

sim._reinitialize(rpm)
omega = omega_from_rpm(rpm)
tracker = EngineCycleTracker(rpm)
convergence = ConvergenceChecker(cfg.n_cylinders, cfg.simulation.convergence_tolerance)
cfl_num = cfg.simulation.cfl_number

# Track per-step quantities
log_t = []
log_theta = []
log_dt = []
log_mdot_restrictor = []
log_mdot_runner_inlet_sum = []  # rho*u*A at runner LEFT ends
log_mdot_cylinder_intake_sum = []  # cylinder valve BC mdot
log_runner_mass_total = []  # int rho*A*dx for all runners
log_plenum_p = []
log_plenum_T = []
log_plenum_m = []
log_plenum_m_implied = []  # p*V/(RT)
log_cyl_intake_accum = []  # cumulative across all cylinders
log_cyl_exhaust_accum = []

current_cycle = 0
total_t = 0.0

while current_cycle < n_cycles:
    dt = compute_cfl_timestep(sim.all_pipes, cfl_num)
    dt = min(dt, 1e-3)
    dtheta = tracker.advance(dt)
    theta = tracker.theta
    total_t += dt

    for pipe in sim.all_pipes:
        extrapolate_boundary_incoming(pipe, dt)

    sim.restrictor_plenum.solve_and_apply(dt)

    for i in range(cfg.n_cylinders):
        sim.cylinders[i].mdot_intake = 0.0
        sim.cylinders[i].mdot_exhaust = 0.0

    for i in range(cfg.n_cylinders):
        sim.intake_valve_bcs[i].apply(sim.intake_runners[i], PipeEnd.RIGHT, dt, theta_deg=theta, rpm=rpm)
    for i in range(cfg.n_cylinders):
        sim.exhaust_valve_bcs[i].apply(sim.exhaust_primaries[i], PipeEnd.LEFT, dt, theta_deg=theta, rpm=rpm)

    for junc in sim.exhaust_junctions:
        junc.apply(dt)
    sim.exhaust_open_bc.apply(sim.exhaust_collector, PipeEnd.RIGHT, dt)

    for pipe in sim.all_pipes:
        advance_interior_points(pipe, dt, include_sources=True)

    for cyl in sim.cylinders:
        cyl.advance(theta, dtheta, rpm)

    # === RECORD DIAGNOSTICS ===
    if current_cycle >= n_cycles - 2:  # last 2 cycles
        log_t.append(total_t)
        log_theta.append(theta)
        log_dt.append(dt)
        log_mdot_restrictor.append(sim.restrictor_plenum.last_mdot_restrictor)

        # Per-runner inlet AND outlet mass flow (rho*u*A at both ends)
        runner_inlet_sum = 0.0
        runner_outlet_sum = 0.0
        runner_total_mass = 0.0
        for pipe in sim.intake_runners:
            runner_inlet_sum += pipe.rho[0] * pipe.u[0] * pipe.area[0]
            runner_outlet_sum += pipe.rho[-1] * pipe.u[-1] * pipe.area[-1]
            runner_total_mass += float(np.sum(pipe.rho * pipe.area)) * pipe.dx
        log_mdot_runner_inlet_sum.append(runner_inlet_sum)
        if not hasattr(sim, '_log_outlet'):
            sim._log_outlet = []
        sim._log_outlet.append(runner_outlet_sum)
        log_runner_mass_total.append(runner_total_mass)

        # Cylinder intake mdot sum (instantaneous)
        cyl_intake_sum = sum(c.mdot_intake for c in sim.cylinders)
        log_mdot_cylinder_intake_sum.append(cyl_intake_sum)

        log_plenum_p.append(sim.restrictor_plenum.p)
        log_plenum_T.append(sim.restrictor_plenum.T)
        log_plenum_m.append(sim.restrictor_plenum.m)
        log_plenum_m_implied.append(sim.restrictor_plenum.p * cfg.plenum.volume / (R_AIR * sim.restrictor_plenum.T))

        log_cyl_intake_accum.append(sum(c.m_intake_total for c in sim.cylinders))
        log_cyl_exhaust_accum.append(sum(c.m_exhaust_total for c in sim.cylinders))

    new_cycle = int(theta / 720.0)
    if new_cycle > current_cycle:
        if new_cycle >= n_cycles:
            current_cycle = new_cycle
            break
        for cyl in sim.cylinders:
            cyl.m_intake_total = 0.0
            cyl.m_exhaust_total = 0.0
            cyl.work_cycle = 0.0
        current_cycle = new_cycle

# Now analyze
t_arr = np.array(log_t)
dt_arr = np.array(log_dt)
mdot_r_arr = np.array(log_mdot_restrictor)
mdot_runner_arr = np.array(log_mdot_runner_inlet_sum)
mdot_cyl_arr = np.array(log_mdot_cylinder_intake_sum)
runner_mass_arr = np.array(log_runner_mass_total)
plen_p_arr = np.array(log_plenum_p)
plen_m_arr = np.array(log_plenum_m)
plen_m_implied_arr = np.array(log_plenum_m_implied)
cyl_intake_accum_arr = np.array(log_cyl_intake_accum)
cyl_exhaust_accum_arr = np.array(log_cyl_exhaust_accum)

elapsed = float(np.sum(dt_arr))
print(f"Recorded {elapsed*1000:.2f} ms = {elapsed/cycle_time:.2f} cycles, {len(t_arr)} steps")

# Integrated quantities
restrictor_in = float(np.sum(mdot_r_arr * dt_arr))
runner_in = float(np.sum(mdot_runner_arr * dt_arr))
runner_outlet_arr = np.array(sim._log_outlet)
runner_out = float(np.sum(runner_outlet_arr * dt_arr))
cyl_in_via_mdot = float(np.sum(mdot_cyl_arr * dt_arr))

# Last-cycle accumulator
cyl_in_accum_final = cyl_intake_accum_arr[-1]
cyl_in_accum_initial = cyl_intake_accum_arr[0]

# Plenum mass change (actual vs implied)
dM_plen = plen_m_arr[-1] - plen_m_arr[0]
dM_plen_implied = plen_m_implied_arr[-1] - plen_m_implied_arr[0]
plen_drift = plen_m_arr - plen_m_implied_arr

# Runner mass change
dM_runner = runner_mass_arr[-1] - runner_mass_arr[0]

print(f"\n--- Mass flow integrals over recorded period ---")
print(f"Restrictor in:                       {restrictor_in*1000:.4f} g")
print(f"Sum runner inlets   (rho*u*A) LEFT:  {runner_in*1000:.4f} g")
print(f"Sum runner outlets  (rho*u*A) RIGHT: {runner_out*1000:.4f} g")
print(f"Sum cyl intake (BC mdot * dt):       {cyl_in_via_mdot*1000:.4f} g")
print(f"Cyl intake accumulator (delta):      {(cyl_in_accum_final - cyl_in_accum_initial)*1000:.4f} g")
print(f"\n--- State changes ---")
print(f"Plenum dM (self.m):       {dM_plen*1000:+.4f} g")
print(f"Plenum dM (p*V/RT):       {dM_plen_implied*1000:+.4f} g")
print(f"Plenum drift (m - implied): start={plen_drift[0]*1000:+.4f} g, end={plen_drift[-1]*1000:+.4f} g")
print(f"Runner total mass dM:     {dM_runner*1000:+.4f} g")

print(f"\n--- Mass balance equations ---")
print(f"  restrictor_in - runner_in - dM_plen = {(restrictor_in - runner_in - dM_plen)*1000:+.4f} g")
print(f"     (should be 0 if plenum BC enforces conservation)")
print(f"  runner_in - cyl_in_via_mdot - dM_runner = {(runner_in - cyl_in_via_mdot - dM_runner)*1000:+.4f} g")
print(f"     (should be 0 if runner mass is conserved)")
print(f"  cyl_in_via_mdot vs accumulator: diff = {(cyl_in_via_mdot - (cyl_in_accum_final - cyl_in_accum_initial))*1000:+.4f} g")

# Per-cycle averages
print(f"\n--- Per-cycle averages ---")
n_cyc = elapsed / cycle_time
print(f"  Restrictor: {restrictor_in/n_cyc*1000:.4f} g/cycle  ({restrictor_in/elapsed*1000:.2f} g/s)")
print(f"  Runner inlet sum: {runner_in/n_cyc*1000:.4f} g/cycle  ({runner_in/elapsed*1000:.2f} g/s)")
print(f"  Cyl intake (mdot): {cyl_in_via_mdot/n_cyc*1000:.4f} g/cycle  ({cyl_in_via_mdot/elapsed*1000:.2f} g/s)")
print(f"  Plenum p avg: {np.mean(plen_p_arr)/1e5:.3f} bar")
