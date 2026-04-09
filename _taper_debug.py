"""Debug the area-source-term collapse with the 40→32mm taper.

Track plenum pressure, runner state, and restrictor flow over the first
2-3 cycles to find where things go wrong.
"""
import os
os.environ["MPLBACKEND"] = "Agg"

import numpy as np
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.gas_dynamics.cfl import compute_cfl_timestep
from engine_simulator.gas_dynamics.moc_solver import (
    advance_interior_points, extrapolate_boundary_incoming
)
from engine_simulator.simulation.engine_cycle import EngineCycleTracker

cfg = EngineConfig()
# Apply the taper
for pc in cfg.intake_pipes:
    pc.diameter = 0.040
    pc.diameter_out = 0.032

sim = SimulationOrchestrator(cfg)
rpm = 10000.0
sim._reinitialize(rpm)
tracker = EngineCycleTracker(rpm)
cfl_num = cfg.simulation.cfl_number

print(f"Initial state at 10000 RPM with 40→32mm taper:")
runner = sim.intake_runners[0]
print(f"  runner area: inlet={runner.area[0]*1e6:.1f} mm², outlet={runner.area[-1]*1e6:.1f} mm²")
print(f"  initial p[0]={runner.p[0]/1e5:.3f}, p[-1]={runner.p[-1]/1e5:.3f} bar")
print(f"  plenum p={sim.restrictor_plenum.p/1e5:.3f} bar")

step_count = 0
max_steps_to_log = 15  # log first N steps in detail

while tracker.theta < 720.0 * 2:  # 2 cycles max
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
        advance_interior_points(
            pipe, dt,
            include_sources=True,
            artificial_viscosity=cfg.simulation.artificial_viscosity,
        )

    for cyl in sim.cylinders:
        cyl.advance(theta, dtheta, rpm)

    step_count += 1

    if step_count <= max_steps_to_log or step_count % 200 == 0:
        print(
            f"step {step_count:5d}  θ={theta:6.1f}  p_plen={sim.restrictor_plenum.p/1e5:.3f}  "
            f"p[0]={runner.p[0]/1e5:.3f}  p[14]={runner.p[14]/1e5:.3f}  p[-1]={runner.p[-1]/1e5:.3f}  "
            f"u[0]={runner.u[0]:6.1f}  u[14]={runner.u[14]:6.1f}  u[-1]={runner.u[-1]:6.1f}  "
            f"mdot_r={sim.restrictor_plenum.last_mdot_restrictor*1000:.1f} g/s"
        )

    if sim.restrictor_plenum.p < 1.5e4:
        print(f"PLENUM CRASH at step {step_count}, theta={theta:.1f}")
        # Dump full runner state
        print("Runner full state:")
        for j in range(0, runner.n_points, 3):
            print(f"  i={j:2d}  p={runner.p[j]/1e5:.4f}  u={runner.u[j]:7.1f}  ρ={runner.rho[j]:.3f}  A={runner.A_nd[j]:.3f}  AA={runner.AA[j]:.3f}  λ={runner.lam[j]:.3f}  β={runner.bet[j]:.3f}")
        break
