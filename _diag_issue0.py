"""Targeted diagnostic for Issue 0 mass conservation bugs.

Hypotheses being tested:
H1) valve_bc.py exhaust override of mdot_exhaust set by intake reverse flow.
    Symptom: when intake valve has reverse flow during overlap, the addition
    to cyl.mdot_exhaust gets wiped by the exhaust valve's "= mdot" assignment.

H2) The pipe-boundary mass flux (rho*u*A at runner RIGHT end after the BC)
    differs from the orifice mdot used to advance the cylinder.
    Symptom: every step, the cylinder receives mass that the runner did not
    actually deliver (or vice versa).

H3) The runner mass is slowly drifting because the MOC interior update is
    not strictly conservative.

We instrument the orchestrator step-by-step at 10000 RPM and report:
  - per-step orifice mdot vs pipe-boundary rho*u*A
  - per-step intake reverse-flow event count
  - per-cycle mass integrals at each interface
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
from engine_simulator.engine.kinematics import omega_from_rpm
from engine_simulator.gas_dynamics.gas_properties import R_AIR

cfg = EngineConfig()
sim = SimulationOrchestrator(cfg)
rpm = 10000.0
n_cycles = 12

sim._reinitialize(rpm)
omega = omega_from_rpm(rpm)
tracker = EngineCycleTracker(rpm)
cfl_num = cfg.simulation.cfl_number

# Per-step diagnostic logs (recorded in last 2 cycles only)
log = {
    "theta": [],
    "dt": [],
    # mass flow at runner LEFT end (rho*u*A) per runner
    "runner_left": [[], [], [], []],
    # mass flow at runner RIGHT end (rho*u*A) per runner — POST-VALVE-BC
    "runner_right_post": [[], [], [], []],
    # mass flow at runner RIGHT end — PRE-VALVE-BC (after extrapolation/MOC interior advance previous step)
    "runner_right_pre": [[], [], [], []],
    # cylinder mdot_intake set by valve BC, per cyl
    "cyl_mdot_in": [[], [], [], []],
    "cyl_mdot_out": [[], [], [], []],
    # restrictor
    "restrictor": [],
    # plenum mass implied
    "plenum_m": [],
    # event counter: did the intake valve invoke reverse-flow path this step?
    "intake_reverse": [[], [], [], []],
    # net cylinder mass after step
    "cyl_mass": [[], [], [], []],
    # runner total mass integral
    "runner_total_mass": [],
}

current_cycle = 0
recording = False

def boundary_mdot(pipe, idx):
    return float(pipe.rho[idx] * pipe.u[idx] * pipe.area[idx])

while current_cycle < n_cycles:
    dt = compute_cfl_timestep(sim.all_pipes, cfl_num)
    dt = min(dt, 1e-3)
    dtheta = tracker.advance(dt)
    theta = tracker.theta

    for pipe in sim.all_pipes:
        extrapolate_boundary_incoming(pipe, dt)

    sim.restrictor_plenum.solve_and_apply(dt)

    # Pre-valve-BC right-end mass flux (this is the MOC state from the previous
    # interior advance, after restrictor BC at the LEFT but BEFORE the valve BC
    # at the RIGHT).
    pre_runner_right = [boundary_mdot(p, -1) for p in sim.intake_runners]

    # Zero cylinder mdot
    for i in range(cfg.n_cylinders):
        sim.cylinders[i].mdot_intake = 0.0
        sim.cylinders[i].mdot_exhaust = 0.0

    # Track whether the intake valve will hit its reverse-flow branch.
    # We replicate the valve_bc check: reverse if p_pipe < p_cyl with valve open.
    intake_reverse_flag = [0] * cfg.n_cylinders
    for i in range(cfg.n_cylinders):
        cyl = sim.cylinders[i]
        pipe = sim.intake_runners[i]
        idx = -1
        theta_local = cyl.local_theta(theta)
        A_eff = cyl.intake_valve.effective_area(theta_local)
        if A_eff > 1e-10 and pipe.p[idx] < cyl.p:
            intake_reverse_flag[i] = 1

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

    # POST-valve-BC, POST-interior-advance: pipe state for next step
    post_runner_right = [boundary_mdot(p, -1) for p in sim.intake_runners]
    post_runner_left = [boundary_mdot(p, 0) for p in sim.intake_runners]

    for cyl in sim.cylinders:
        cyl.advance(theta, dtheta, rpm)

    if current_cycle >= n_cycles - 2:
        log["theta"].append(theta)
        log["dt"].append(dt)
        log["restrictor"].append(sim.restrictor_plenum.last_mdot_restrictor)
        log["plenum_m"].append(
            sim.restrictor_plenum.p * cfg.plenum.volume / (R_AIR * sim.restrictor_plenum.T)
        )
        runner_total = sum(
            float(np.sum(p.rho * p.area)) * p.dx for p in sim.intake_runners
        )
        log["runner_total_mass"].append(runner_total)
        for i in range(cfg.n_cylinders):
            log["runner_left"][i].append(post_runner_left[i])
            log["runner_right_pre"][i].append(pre_runner_right[i])
            log["runner_right_post"][i].append(post_runner_right[i])
            log["cyl_mdot_in"][i].append(sim.cylinders[i].mdot_intake)
            log["cyl_mdot_out"][i].append(sim.cylinders[i].mdot_exhaust)
            log["intake_reverse"][i].append(intake_reverse_flag[i])
            log["cyl_mass"][i].append(sim.cylinders[i].m)

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


# Analyze
dt_arr = np.array(log["dt"])
elapsed = float(np.sum(dt_arr))
n_steps = len(dt_arr)
print(f"Recorded {elapsed*1000:.2f} ms = {elapsed/(120/rpm):.2f} cycles, {n_steps} steps")

# Hypothesis H1: did intake reverse flow happen at the same time as exhaust forward flow?
overlap_events = 0
for i in range(cfg.n_cylinders):
    rev = np.array(log["intake_reverse"][i])
    overlap_events += int(rev.sum())
print(f"\nH1) Intake reverse events across all cyl: {overlap_events} step-events "
      f"({overlap_events/(n_steps*cfg.n_cylinders)*100:.2f}% of cyl-steps)")

# Per-cylinder reverse intake mass that was added to mdot_exhaust by valve_bc
# AND then potentially overwritten by exhaust BC. We measure this by checking
# log["cyl_mdot_out"][i] > 0 simultaneously with intake_reverse=1.
for i in range(cfg.n_cylinders):
    rev = np.array(log["intake_reverse"][i])
    out = np.array(log["cyl_mdot_out"][i])
    n_rev = int(rev.sum())
    n_rev_with_out = int(((rev > 0) & (out > 0)).sum())
    print(f"  cyl {i}: {n_rev} reverse-intake steps, "
          f"{n_rev_with_out} of those had nonzero mdot_exhaust set by exh BC "
          f"(so the reverse intake addition was overwritten)")

# Hypothesis H2: orifice mdot vs pipe boundary rho*u*A AT THE RIGHT END
# After valve BC, pipe.rho[-1]*pipe.u[-1]*pipe.area[-1] should equal cyl.mdot_intake
# (when forward flow). Compare them.
print("\nH2) Per-cylinder orifice mdot vs pipe-boundary rho*u*A (post-BC):")
for i in range(cfg.n_cylinders):
    cyl_in = np.array(log["cyl_mdot_in"][i])
    pipe_out = np.array(log["runner_right_post"][i])
    # only steps with forward intake flow
    fwd = cyl_in > 1e-10
    if fwd.sum() > 0:
        diff = pipe_out[fwd] - cyl_in[fwd]
        rms = float(np.sqrt(np.mean(diff**2)))
        rel = float(np.mean(np.abs(diff) / np.maximum(cyl_in[fwd], 1e-12)))
        print(f"  cyl {i}: {int(fwd.sum())} fwd steps, "
              f"orifice={cyl_in[fwd].mean()*1000:.3f} g/s avg, "
              f"pipe-flux={pipe_out[fwd].mean()*1000:.3f} g/s avg, "
              f"RMS diff={rms*1000:.3f} g/s, mean rel err={rel*100:.1f}%")

# H3) Runner mass over time and integrated boundary fluxes
# Sum runner left/right mass and integrate over recorded period
runner_left_total = np.zeros(n_steps)
runner_right_total = np.zeros(n_steps)
for i in range(cfg.n_cylinders):
    runner_left_total += np.array(log["runner_left"][i])
    runner_right_total += np.array(log["runner_right_post"][i])

mass_in_left = float(np.sum(runner_left_total * dt_arr))
mass_out_right = float(np.sum(runner_right_total * dt_arr))
runner_total = np.array(log["runner_total_mass"])
dM_runner = float(runner_total[-1] - runner_total[0])
print(f"\nH3) Runner mass conservation over recorded period:")
print(f"  Sum runner LEFT inflow:    {mass_in_left*1000:+.4f} g")
print(f"  Sum runner RIGHT outflow:  {mass_out_right*1000:+.4f} g")
print(f"  Runner total mass change:  {dM_runner*1000:+.4f} g")
print(f"  Conservation residual (left - right - dM): "
      f"{(mass_in_left - mass_out_right - dM_runner)*1000:+.4f} g")
print(f"     If non-zero, MOC interior is non-conservative.")

# Now compare cyl_mdot_in integral to runner_right_post integral
cyl_in_total = 0.0
for i in range(cfg.n_cylinders):
    cyl_in_total += float(np.sum(np.array(log["cyl_mdot_in"][i]) * dt_arr))
cyl_out_total = 0.0
for i in range(cfg.n_cylinders):
    cyl_out_total += float(np.sum(np.array(log["cyl_mdot_out"][i]) * dt_arr))

print(f"\n  Cyl intake (mdot integral): {cyl_in_total*1000:+.4f} g")
print(f"  Cyl exhaust (mdot integral): {cyl_out_total*1000:+.4f} g")
print(f"  Pipe right-end outflow integral: {mass_out_right*1000:+.4f} g")
print(f"  Pipe right - cyl_intake = {(mass_out_right - cyl_in_total)*1000:+.4f} g")
print(f"     Should be ~0; nonzero means valve BC mdot ≠ MOC pipe flux at boundary.")

# Restrictor in
restrictor_in = float(np.sum(np.array(log["restrictor"]) * dt_arr))
plenum_dM = float(log["plenum_m"][-1] - log["plenum_m"][0])
print(f"\n  Restrictor in: {restrictor_in*1000:+.4f} g, plenum dM: {plenum_dM*1000:+.4f} g")
print(f"  Restrictor - left inflow - plenum dM = "
      f"{(restrictor_in - mass_in_left - plenum_dM)*1000:+.4f} g  (plenum BC residual)")
