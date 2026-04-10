"""Trace runner pressure at every grid point over a single cycle to see
what the wave dynamics actually look like."""
import os
os.environ['MPLBACKEND'] = 'Agg'

import numpy as np
import matplotlib.pyplot as plt
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.gas_dynamics.cfl import compute_cfl_timestep
from engine_simulator.gas_dynamics.moc_solver import (
    advance_interior_points, extrapolate_boundary_incoming
)
from engine_simulator.simulation.engine_cycle import EngineCycleTracker
from engine_simulator.gas_dynamics.gas_properties import R_AIR

cfg = EngineConfig()
sim = SimulationOrchestrator(cfg)
rpm = 10000.0
n_cycles = 12

sim._reinitialize(rpm)
tracker = EngineCycleTracker(rpm)
cfl_num = cfg.simulation.cfl_number

# Record runner 1 valve-end and inlet-end pressure each step in last 2 cycles
log = {
    "theta": [],
    "p_inlet": [],
    "p_valve": [],
    "p_mid": [],
    "u_inlet": [],
    "u_valve": [],
    "u_mid": [],
    "rho_valve": [],
    "AA_valve": [],
    "T_valve": [],
    "valve_open": [],
    "cyl_p": [],
    "plen_p": [],
    "mdot_in": [],
}

current_cycle = 0
runner = sim.intake_runners[0]
cyl = sim.cylinders[0]

while current_cycle < n_cycles:
    dt = compute_cfl_timestep(sim.all_pipes, cfl_num)
    dt = min(dt, 1e-3)
    dtheta = tracker.advance(dt)
    theta = tracker.theta

    for pipe in sim.all_pipes:
        extrapolate_boundary_incoming(pipe, dt)

    sim.restrictor_plenum.solve_and_apply(dt)

    for i in range(cfg.n_cylinders):
        sim.cylinders[i].mdot_intake = 0.0
        sim.cylinders[i].mdot_exhaust = 0.0

    for i in range(cfg.n_cylinders):
        sim.intake_valve_bcs[i].apply(
            sim.intake_runners[i], PipeEnd.RIGHT, dt,
            theta_deg=theta, rpm=rpm,
        )

    for i in range(cfg.n_cylinders):
        sim.exhaust_valve_bcs[i].apply(
            sim.exhaust_primaries[i], PipeEnd.LEFT, dt,
            theta_deg=theta, rpm=rpm,
        )

    for junc in sim.exhaust_junctions:
        junc.apply(dt)
    sim.exhaust_open_bc.apply(sim.exhaust_collector, PipeEnd.RIGHT, dt)

    for pipe in sim.all_pipes:
        advance_interior_points(pipe, dt, include_sources=True)

    for cyl_i in sim.cylinders:
        cyl_i.advance(theta, dtheta, rpm)

    if current_cycle >= n_cycles - 2:
        log["theta"].append(theta)
        log["p_inlet"].append(runner.p[0])
        log["p_valve"].append(runner.p[-1])
        log["p_mid"].append(runner.p[runner.n_points // 2])
        log["u_inlet"].append(runner.u[0])
        log["u_valve"].append(runner.u[-1])
        log["u_mid"].append(runner.u[runner.n_points // 2])
        log["rho_valve"].append(runner.rho[-1])
        log["AA_valve"].append(runner.AA[-1])
        log["T_valve"].append(runner.T[-1])
        theta_local = cyl.local_theta(theta)
        A_eff = cyl.intake_valve.effective_area(theta_local)
        log["valve_open"].append(1.0 if A_eff > 1e-10 else 0.0)
        log["cyl_p"].append(cyl.p)
        log["plen_p"].append(sim.restrictor_plenum.p)
        log["mdot_in"].append(cyl.mdot_intake)

    new_cycle = int(theta / 720.0)
    if new_cycle > current_cycle:
        if new_cycle >= n_cycles:
            break
        for c in sim.cylinders:
            c.m_intake_total = 0.0
            c.m_exhaust_total = 0.0
            c.work_cycle = 0.0
        current_cycle = new_cycle


theta_arr = np.array(log["theta"]) % 720.0
order = np.argsort(theta_arr)

fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
axes[0].plot(theta_arr, np.array(log["p_inlet"]) / 1e5, "b-", linewidth=0.5, label="inlet (i=0)")
axes[0].plot(theta_arr, np.array(log["p_mid"]) / 1e5, "g-", linewidth=0.5, label="mid (i=15)")
axes[0].plot(theta_arr, np.array(log["p_valve"]) / 1e5, "r-", linewidth=0.5, label="valve (i=29)")
axes[0].plot(theta_arr, np.array(log["plen_p"]) / 1e5, "k--", linewidth=0.5, label="plenum")
axes[0].plot(theta_arr, np.array(log["cyl_p"]) / 1e5, "m-", linewidth=0.3, label="cylinder")
axes[0].set_ylabel("Pressure (bar)")
axes[0].set_yscale("log")
axes[0].legend(fontsize=8, loc="upper right")
axes[0].grid(True, alpha=0.3)
axes[0].set_title(f"Runner 1 pressure trace at {rpm:.0f} RPM (last 2 cycles)")

axes[1].plot(theta_arr, np.array(log["u_inlet"]), "b-", linewidth=0.5, label="inlet")
axes[1].plot(theta_arr, np.array(log["u_mid"]), "g-", linewidth=0.5, label="mid")
axes[1].plot(theta_arr, np.array(log["u_valve"]), "r-", linewidth=0.5, label="valve")
axes[1].set_ylabel("velocity (m/s)")
axes[1].grid(True, alpha=0.3)
axes[1].legend(fontsize=8)

axes[2].plot(theta_arr, np.array(log["rho_valve"]), "r-", linewidth=0.5, label="ρ at valve")
axes[2].axhline(1.177, color="k", linestyle=":", alpha=0.5, label="ρ_atm")
axes[2].set_ylabel("density (kg/m³)")
axes[2].legend(fontsize=8)
axes[2].grid(True, alpha=0.3)

axes[3].plot(theta_arr, np.array(log["mdot_in"]) * 1000, "g-", linewidth=0.5)
ax3b = axes[3].twinx()
ax3b.fill_between(theta_arr, 0, np.array(log["valve_open"]), alpha=0.2, color="b")
axes[3].set_ylabel("intake mdot (g/s)", color="g")
ax3b.set_ylabel("valve open", color="b")
axes[3].set_xlabel("crank angle (deg)")
axes[3].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig("_runner_history.png", dpi=120, bbox_inches="tight")
print(f"Saved _runner_history.png")

p_mid_arr = np.array(log["p_mid"])
p_valve_arr = np.array(log["p_valve"])
plen_arr = np.array(log["plen_p"])
print(f"\nStatistics over last 2 cycles:")
print(f"  Plenum:      mean={plen_arr.mean()/1e5:.3f} bar")
print(f"  Inlet (i=0): mean={np.mean(log['p_inlet'])/1e5:.3f}, range "
      f"{np.min(log['p_inlet'])/1e5:.3f}…{np.max(log['p_inlet'])/1e5:.3f} bar")
print(f"  Mid (i=15):  mean={p_mid_arr.mean()/1e5:.3f}, range {p_mid_arr.min()/1e5:.3f}…{p_mid_arr.max()/1e5:.3f} bar")
print(f"  Valve (i=29):mean={p_valve_arr.mean()/1e5:.3f}, range {p_valve_arr.min()/1e5:.3f}…{p_valve_arr.max()/1e5:.3f} bar")
print(f"  Ram boost (valve mean / plenum mean): {p_valve_arr.mean()/plen_arr.mean():.2f}x")
