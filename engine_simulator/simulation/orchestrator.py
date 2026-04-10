"""Main simulation orchestrator: time-stepping loop coupling all subsystems."""

from __future__ import annotations

import os
import time
from typing import Callable, Optional

import numpy as np

from engine_simulator.simulation.parallel_sweep import (
    ConvergedEvent,
    CycleDoneEvent,
    ProgressEvent,
    RPMDoneEvent,
    RPMStartEvent,
)
from engine_simulator.boundaries.base import PipeEnd
from engine_simulator.boundaries.junction import JunctionBC
from engine_simulator.boundaries.open_end import OpenEndBC
from engine_simulator.boundaries.restrictor import RestrictorBC
from engine_simulator.boundaries.valve_bc import ValveBoundaryCondition
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.engine.cylinder import CylinderModel
from engine_simulator.engine.kinematics import cylinder_phase_offsets, omega_from_rpm
from engine_simulator.engine.valve import Valve
from engine_simulator.gas_dynamics.cfl import compute_cfl_timestep
from engine_simulator.gas_dynamics.gas_properties import GAMMA_REF, P_REF, T_REF
from engine_simulator.simulation.plenum import RestrictorPlenumBC
# Note: the old 'Plenum' class is replaced by RestrictorPlenumBC
from engine_simulator.gas_dynamics.moc_solver import advance_interior_points, extrapolate_boundary_incoming
from engine_simulator.gas_dynamics.pipe import Pipe
from engine_simulator.postprocessing.performance import apply_drivetrain_losses
from engine_simulator.postprocessing.results import SimulationResults
from engine_simulator.simulation.convergence import ConvergenceChecker
from engine_simulator.simulation.engine_cycle import EngineCycleTracker


class SimulationOrchestrator:
    """Orchestrates the complete engine simulation.

    Manages the coupling between:
    - 1D pipe gas dynamics (MOC solver)
    - 0D cylinder thermodynamics
    - 0D plenum
    - Restrictor
    - All boundary conditions
    """

    def __init__(self, config: EngineConfig):
        self.config = config
        self.gamma = GAMMA_REF

        # Build all simulation components
        self._build_pipes()
        self._build_cylinders()
        self._build_plenum()
        self._build_boundaries()

        self.results = SimulationResults()

        # Per-RPM results aggregation (populated by run_rpm_sweep, both
        # sequential and parallel paths). Keyed by float(rpm).
        self.results_by_rpm: dict = {}

        # Set inside run_single_rpm so that workers in parallel mode can
        # report total step count and convergence status without re-deriving.
        self._last_step_count: int = 0
        self._last_converged: bool = False

    def _build_pipes(self):
        """Create all pipe objects from config."""
        cfg = self.config
        self.intake_runners: list[Pipe] = []
        for pc in cfg.intake_pipes:
            p = Pipe.from_config(pc)
            p.initialize(p=cfg.p_ambient, T=cfg.T_ambient)
            self.intake_runners.append(p)

        self.exhaust_primaries: list[Pipe] = []
        for pc in cfg.exhaust_primaries:
            p = Pipe.from_config(pc)
            p.initialize(p=cfg.p_ambient, T=cfg.T_ambient)
            self.exhaust_primaries.append(p)

        self.exhaust_secondaries: list[Pipe] = []
        for pc in cfg.exhaust_secondaries:
            p = Pipe.from_config(pc)
            p.initialize(p=cfg.p_ambient, T=cfg.T_ambient)
            self.exhaust_secondaries.append(p)

        self.exhaust_collector = Pipe.from_config(cfg.exhaust_collector)
        self.exhaust_collector.initialize(p=cfg.p_ambient, T=cfg.T_ambient)

        self.all_pipes: list[Pipe] = (
            self.intake_runners
            + self.exhaust_primaries
            + self.exhaust_secondaries
            + [self.exhaust_collector]
        )

    def _build_cylinders(self):
        """Create cylinder models with proper phasing."""
        cfg = self.config
        offsets = cylinder_phase_offsets(
            cfg.n_cylinders, cfg.firing_order, cfg.firing_interval
        )
        self.cylinders: list[CylinderModel] = []
        for i in range(cfg.n_cylinders):
            cyl_num = i + 1
            iv = Valve(cfg.intake_valve, cfg.cylinder.n_intake_valves)
            ev = Valve(cfg.exhaust_valve, cfg.cylinder.n_exhaust_valves)
            cyl = CylinderModel(
                cfg.cylinder, cfg.combustion, iv, ev,
                cylinder_id=i, phase_offset=offsets[cyl_num],
            )
            cyl.initialize(p=cfg.p_ambient, T=cfg.T_ambient, theta_deg=0.0)
            self.cylinders.append(cyl)

    def _build_plenum(self):
        """Plenum is now part of RestrictorPlenumBC, created in _build_boundaries."""
        pass

    def _build_boundaries(self):
        """Create all boundary conditions and wire up the system."""
        cfg = self.config

        # Restrictor: atmosphere -> plenum connection
        # The restrictor feeds into the plenum. We model the restrictor as
        # a mass flow source for the plenum.
        self.restrictor = RestrictorBC(
            cfg.restrictor, p_upstream=cfg.p_ambient, T_upstream=cfg.T_ambient
        )

        # Intake valve BCs: connect each intake runner RIGHT end to cylinder
        self.intake_valve_bcs: list[ValveBoundaryCondition] = []
        for i, cyl in enumerate(self.cylinders):
            vbc = ValveBoundaryCondition(cyl, valve_type="intake")
            self.intake_valve_bcs.append(vbc)

        # Exhaust valve BCs: connect each exhaust primary LEFT end to cylinder
        self.exhaust_valve_bcs: list[ValveBoundaryCondition] = []
        for i, cyl in enumerate(self.cylinders):
            vbc = ValveBoundaryCondition(cyl, valve_type="exhaust")
            self.exhaust_valve_bcs.append(vbc)

        # Coupled restrictor-plenum-runner boundary condition
        self.restrictor_plenum = RestrictorPlenumBC(
            restrictor=self.restrictor,
            runner_pipes=self.intake_runners,
            plenum_volume=cfg.plenum.volume,
            p_ambient=cfg.p_ambient,
            T_ambient=cfg.T_ambient,
        )

        # Exhaust junctions (4-2-1):
        # Junction 1: primaries 1,4 -> secondary 1 (cylinders 1,4 = 180° pair)
        # Junction 2: primaries 2,3 -> secondary 2 (cylinders 2,3 = 180° pair)
        # Junction 3: secondaries 1,2 -> collector
        self.exhaust_junctions: list[JunctionBC] = []

        if len(self.exhaust_secondaries) == 2:
            # 4-2-1 configuration
            # Pair primaries by firing order proximity (180° pairs)
            # Firing order 1-2-4-3: pairs are (1,4) and (2,3)
            j1 = JunctionBC(
                pipes=[self.exhaust_primaries[0], self.exhaust_primaries[3],
                       self.exhaust_secondaries[0]],
                ends=[PipeEnd.RIGHT, PipeEnd.RIGHT, PipeEnd.LEFT],
                signs=[1, 1, -1],
            )
            j2 = JunctionBC(
                pipes=[self.exhaust_primaries[1], self.exhaust_primaries[2],
                       self.exhaust_secondaries[1]],
                ends=[PipeEnd.RIGHT, PipeEnd.RIGHT, PipeEnd.LEFT],
                signs=[1, 1, -1],
            )
            j3 = JunctionBC(
                pipes=[self.exhaust_secondaries[0], self.exhaust_secondaries[1],
                       self.exhaust_collector],
                ends=[PipeEnd.RIGHT, PipeEnd.RIGHT, PipeEnd.LEFT],
                signs=[1, 1, -1],
            )
            self.exhaust_junctions = [j1, j2, j3]

        # Exhaust collector RIGHT end: open to atmosphere
        self.exhaust_open_bc = OpenEndBC(p_atm=cfg.p_ambient, T_atm=cfg.T_ambient)

    def _reinitialize(self, rpm: float):
        """Reinitialize all state for a new RPM point.

        Each cylinder is initialized at a pressure appropriate to its phase:
        - Near TDC firing: high pressure (compressed charge)
        - Expansion/exhaust: moderate pressure
        - Intake/compression: near atmospheric
        This prevents the first cycle from being completely unphysical.
        """
        cfg = self.config
        for pipe in self.all_pipes:
            pipe.initialize(p=cfg.p_ambient, T=cfg.T_ambient)

        for cyl in self.cylinders:
            local_theta = cyl.local_theta(0.0)
            # Estimate appropriate initial pressure based on phase
            if local_theta < 30 or local_theta > 680:
                # Near TDC firing: compressed charge
                p_init = cfg.p_ambient * cfg.cylinder.compression_ratio ** 1.3
                T_init = cfg.T_ambient * cfg.cylinder.compression_ratio ** 0.3
            elif local_theta < 180:
                # Expansion
                V_ratio = cyl.geometry.volume(local_theta) / cyl.geometry.V_c
                p_init = cfg.p_ambient * cfg.cylinder.compression_ratio ** 1.3 / V_ratio ** 1.3
                T_init = cfg.T_ambient * 2.0
            elif local_theta < 360:
                # Exhaust
                p_init = cfg.p_ambient * 1.1
                T_init = 900.0
            else:
                # Intake / compression
                p_init = cfg.p_ambient
                T_init = cfg.T_ambient

            cyl.initialize(p=p_init, T=T_init, theta_deg=0.0)

        self.restrictor_plenum.p = cfg.p_ambient
        self.restrictor_plenum.T = cfg.T_ambient
        self.restrictor_plenum.m = cfg.p_ambient * cfg.plenum.volume / (287.0 * cfg.T_ambient)

        # --- RPM-dependent combustion corrections ---------------------------
        # The Wiebe model uses fixed crank-angle parameters, but real SI
        # combustion quality degrades at low RPM:
        #   - Less in-cylinder turbulence → slower flame propagation
        #   - Longer real-time burn → more heat loss to walls during burn
        #   - Greater cycle-to-cycle variation → effective efficiency drop
        # We correct for this by scaling combustion duration and efficiency
        # as functions of RPM, referenced to a "design point" RPM where the
        # base config values are calibrated (typically peak-power RPM).
        #
        # The spark advance map is a simple linear ramp: full advance above
        # a threshold RPM, retarded below (real ECUs do this via MAP×RPM
        # lookup; this is a first-order approximation).
        rpm_ref = 10500.0  # RPM where base combustion params are calibrated
        rpm_lo = 3500.0   # below this, maximum degradation applied

        base_duration = cfg.combustion.combustion_duration
        base_advance = cfg.combustion.spark_advance
        base_efficiency = cfg.combustion.combustion_efficiency

        # Duration scales as (rpm_ref / rpm)^0.3 — Heywood Ch.9 empirical:
        # burn duration in crank degrees ~ RPM^0.7 (turbulent flame speed
        # scales with piston speed, but not linearly). At low RPM the
        # duration in degrees shrinks, but the REAL issue is that the burn
        # is so slow in absolute time that heat losses during combustion
        # eat the work. We model this as an effective duration stretch.
        rpm_clamped = max(rpm, rpm_lo)
        duration_factor = (rpm_ref / rpm_clamped) ** 0.3
        duration_factor = min(duration_factor, 2.0)  # cap at 2× base

        # Spark retard at low RPM: linearly reduce advance below rpm_ref,
        # floored at 40% of base advance (≈10° for base 25°).
        advance_factor = min(1.0, 0.4 + 0.6 * (rpm_clamped - rpm_lo) / (rpm_ref - rpm_lo))

        # Combustion efficiency: degrades at low RPM due to partial burns
        # and quenching. Linear ramp from 75% of base at rpm_lo to 100%
        # at rpm_ref.
        efficiency_factor = min(1.0, 0.75 + 0.25 * (rpm_clamped - rpm_lo) / (rpm_ref - rpm_lo))

        adj_duration = base_duration * duration_factor
        adj_advance = base_advance * advance_factor
        adj_efficiency = base_efficiency * efficiency_factor

        for cyl in self.cylinders:
            comb = cyl.combustion
            comb.combustion_duration = adj_duration
            comb.spark_advance = adj_advance
            comb.combustion_efficiency = adj_efficiency
            comb._update_angles()

    def run_single_rpm(
        self,
        rpm: float,
        n_cycles: int = 5,
        record_last_cycle: bool = True,
        verbose: bool = True,
        event_callback: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> dict:
        """Run simulation at a single RPM until convergence or max cycles.

        Returns dict with performance metrics.
        """
        self._reinitialize(rpm)

        cfg = self.config
        omega = omega_from_rpm(rpm)
        tracker = EngineCycleTracker(rpm)
        convergence = ConvergenceChecker(cfg.n_cylinders, cfg.simulation.convergence_tolerance)

        cfl_num = cfg.simulation.cfl_number
        include_sources = True

        cycle_start_theta = 0.0
        current_cycle = 0
        # When convergence is detected at a cycle boundary we don't break
        # immediately — instead we run ONE more cycle with recording forced
        # on, then break. Otherwise we'd exit before any data was captured.
        recording_cycle = False
        cycles_after_convergence = 0

        if verbose:
            print(f"  Running {rpm:.0f} RPM...", end="", flush=True)

        t_start = time.time()
        step_count = 0

        mdot_restrictor = 0.0

        if event_callback is not None:
            event_callback(RPMStartEvent(
                rpm=float(rpm),
                rpm_index=0,           # not known here; set by ParallelSweepRunner via _run_one_rpm
                n_cycles_target=n_cycles,
                ts=time.monotonic(),
            ))

        while current_cycle < n_cycles:
            # 1. Compute global time step from CFL
            dt = compute_cfl_timestep(self.all_pipes, cfl_num)
            dt = min(dt, 1e-3)  # safety cap
            dtheta = tracker.advance(dt)

            theta = tracker.theta
            step_count += 1

            # 2. Extrapolate incoming Riemann variables at boundaries
            for pipe in self.all_pipes:
                extrapolate_boundary_incoming(pipe, dt)

            # 3. Apply boundary conditions

            # Coupled restrictor-plenum-runner solve (sets runner LEFT end BCs)
            self.restrictor_plenum.solve_and_apply(dt)
            mdot_restrictor = self.restrictor_plenum.last_mdot_restrictor

            # Intake runner right end -> cylinder (valve BC)
            for i in range(cfg.n_cylinders):
                self.cylinders[i].mdot_intake = 0.0
                self.cylinders[i].mdot_exhaust = 0.0

            for i in range(cfg.n_cylinders):
                self.intake_valve_bcs[i].apply(
                    self.intake_runners[i], PipeEnd.RIGHT, dt,
                    theta_deg=theta, rpm=rpm,
                )

            # Exhaust: cylinder -> primary left end (valve BC)
            for i in range(cfg.n_cylinders):
                self.exhaust_valve_bcs[i].apply(
                    self.exhaust_primaries[i], PipeEnd.LEFT, dt,
                    theta_deg=theta, rpm=rpm,
                )

            # Exhaust junctions
            for junc in self.exhaust_junctions:
                junc.apply(dt)

            # Exhaust collector open end
            self.exhaust_open_bc.apply(self.exhaust_collector, PipeEnd.RIGHT, dt)

            # 4. Advance interior points for all pipes
            for pipe in self.all_pipes:
                advance_interior_points(
                    pipe, dt,
                    include_sources=include_sources,
                    artificial_viscosity=cfg.simulation.artificial_viscosity,
                )

            # 6. Update cylinder thermodynamics
            for cyl in self.cylinders:
                cyl.advance(theta, dtheta, rpm)

            # 7. Record data on the last cycle, OR on the bonus cycle that
            # follows a convergence detection.
            recording = record_last_cycle and (
                current_cycle >= n_cycles - 1 or recording_cycle
            )
            if recording:
                self.results.record_step(
                    theta=theta,
                    dt=dt,
                    cylinders=self.cylinders,
                    pipes=self.all_pipes,
                    plenum=self.restrictor_plenum,
                    restrictor_mdot=mdot_restrictor,
                    restrictor_choked=self.restrictor_plenum.last_choked,
                )

            # Check for cycle boundary
            new_cycle = int(theta / 720.0)
            if new_cycle > current_cycle:
                # Record convergence data
                p_ivc_values = [cyl.p_at_IVC for cyl in self.cylinders]
                convergence.record_cycle(p_ivc_values)

                change = convergence.max_relative_change()
                if verbose:
                    print(f" cycle {new_cycle} (delta={change:.4f})", end="", flush=True)
                if event_callback is not None:
                    event_callback(CycleDoneEvent(
                        rpm=float(rpm),
                        cycle=new_cycle,
                        delta=float(change),
                        p_ivc=tuple(float(p) for p in p_ivc_values),
                        step_count=step_count,
                        elapsed=time.time() - t_start,
                        ts=time.monotonic(),
                    ))

                # If we already ran the bonus recording cycle after convergence, stop now.
                if recording_cycle:
                    if verbose:
                        print(" [recorded]", end="")
                    current_cycle = new_cycle
                    break

                # On last cycle, the data we just finished IS the data we want —
                # don't reset, don't schedule a bonus cycle. Even if convergence
                # also fires here we already have everything we need (and a bonus
                # cycle has nowhere to run since the loop exits next iteration).
                if new_cycle >= n_cycles:
                    if convergence.is_converged():
                        if verbose:
                            print(" [converged-final]", end="")
                        if event_callback is not None:
                            event_callback(ConvergedEvent(
                                rpm=float(rpm),
                                cycle=new_cycle,
                                ts=time.monotonic(),
                            ))
                    current_cycle = new_cycle
                    break

                # Convergence: schedule one more cycle with recording, then break.
                # Only do this if there is room for the bonus cycle to actually run.
                if convergence.is_converged() and new_cycle >= 3:
                    if verbose:
                        print(" [converged]", end="")
                    if event_callback is not None:
                        event_callback(ConvergedEvent(
                            rpm=float(rpm),
                            cycle=new_cycle,
                            ts=time.monotonic(),
                        ))
                    recording_cycle = True
                    # Reset accumulators so the bonus cycle's totals reflect that cycle alone
                    for cyl in self.cylinders:
                        cyl.m_intake_total = 0.0
                        cyl.m_exhaust_total = 0.0
                        cyl.work_cycle = 0.0
                    current_cycle = new_cycle
                    continue

                # Reset per-cycle accumulators for the next cycle
                for cyl in self.cylinders:
                    cyl.m_intake_total = 0.0
                    cyl.m_exhaust_total = 0.0
                    cyl.work_cycle = 0.0

                current_cycle = new_cycle

        elapsed = time.time() - t_start
        if verbose:
            print(f" ({elapsed:.1f}s, {step_count} steps)")

        # Stash these so workers can attach them to RPMDoneEvent without
        # re-deriving from instance state.
        self._last_step_count = step_count
        self._last_converged = bool(convergence.is_converged())

        # Compute performance metrics
        perf = self._compute_performance(rpm)

        if event_callback is not None:
            event_callback(RPMDoneEvent(
                rpm=float(rpm),
                perf=perf,
                elapsed=elapsed,
                step_count=step_count,
                converged=self._last_converged,
                ts=time.monotonic(),
            ))

        return perf

    def _compute_performance(self, rpm: float) -> dict:
        """Compute performance metrics from the last complete cycle."""
        omega = omega_from_rpm(rpm)
        cfg = self.config

        total_work = sum(cyl.work_cycle for cyl in self.cylinders)
        total_intake_mass = sum(cyl.m_intake_total for cyl in self.cylinders)

        V_d_total = self.cylinders[0].geometry.V_d * cfg.n_cylinders

        # VE reference: post-restrictor (plenum) density, not freestream atmospheric.
        # For a restricted engine, the plenum is the actual gas supply that the
        # cylinders draw from, so volumetric efficiency relative to plenum density
        # measures how well each cylinder fills with the air it actually has access to.
        rho_plen = self.restrictor_plenum.p / (287.0 * max(self.restrictor_plenum.T, 200.0))
        rho_atm = cfg.p_ambient / (287.0 * cfg.T_ambient)

        # Plenum-referenced VE measures how well each cylinder fills relative
        # to the (sub-atmospheric) plenum density it actually has access to.
        # For a restricted engine this is naturally above 100% during ram
        # tuning even though the atm-referenced value stays bounded.
        volumetric_efficiency_plenum = (
            total_intake_mass / (rho_plen * V_d_total) if V_d_total > 0 else 0.0
        )
        # Atm-referenced VE is the conventional metric and is what should be
        # used for any "is the cylinder over-filling?" question.
        volumetric_efficiency_atm = (
            total_intake_mass / (rho_atm * V_d_total) if V_d_total > 0 else 0.0
        )

        # Indicated power: W_cycle * (RPM / 120) for 4-stroke
        indicated_power = total_work * rpm / 120.0  # W
        indicated_torque = indicated_power / omega if omega > 0 else 0.0

        # Brake estimate: indicated minus mechanical friction losses.
        # Heywood-style FMEP correlation tuned for a high-rpm 4-cyl bike
        # engine (CBR600RR-class). The bike's small bore + high rpm gives
        # appreciable rubbing + valvetrain + accessory losses that scale
        # super-linearly with mean piston speed:
        #     fmep[bar] = 0.97 + 0.15·Sp + 0.005·Sp²
        # This gives ~2.5 bar at 6000 RPM and ~4 bar at 12000 RPM for this
        # stroke, in line with published CBR600RR motoring data.
        Sp = 2.0 * cfg.cylinder.stroke * rpm / 60.0  # m/s, mean piston speed
        fmep_bar = 0.97 + 0.15 * Sp + 0.005 * Sp * Sp
        fmep = fmep_bar * 1e5  # Pa
        friction_power = fmep * V_d_total * rpm / 120.0  # W
        brake_power = max(indicated_power - friction_power, 0.0)
        brake_torque = brake_power / omega if omega > 0 else 0.0

        # Drivetrain losses: brake -> wheel power. Single scalar efficiency
        # captures clutch + gearbox + chain + diff + bearing losses (~0.85
        # for a chain-drive FSAE car). See engine_config.drivetrain_efficiency.
        wheel_power = apply_drivetrain_losses(brake_power, cfg.drivetrain_efficiency)
        wheel_torque = brake_torque * cfg.drivetrain_efficiency

        # IMEP
        imep = total_work / V_d_total if V_d_total > 0 else 0.0
        bmep = (total_work - friction_power * 120.0 / rpm) / V_d_total if V_d_total > 0 else 0.0

        return {
            "rpm": rpm,
            "indicated_power_kW": indicated_power / 1000.0,
            "indicated_power_hp": indicated_power / 745.7,
            "indicated_torque_Nm": indicated_torque,
            "brake_power_kW": brake_power / 1000.0,
            "brake_power_hp": brake_power / 745.7,
            "brake_torque_Nm": brake_torque,
            "wheel_power_kW": wheel_power / 1000.0,
            "wheel_power_hp": wheel_power / 745.7,
            "wheel_torque_Nm": wheel_torque,
            "drivetrain_efficiency": cfg.drivetrain_efficiency,
            "imep_bar": imep / 1e5,
            "bmep_bar": bmep / 1e5,
            "fmep_bar": fmep_bar,
            # Two flavors of VE. Plenum-ref is the post-restrictor metric and
            # naturally exceeds 100% with ram tuning because plenum density is
            # sub-atmospheric. Atm-ref is the conventional bounded metric.
            # The legacy key "volumetric_efficiency" is kept for backwards
            # compatibility and aliased to plenum-ref so old plots/scripts
            # don't crash, but new code should use the explicit names.
            "volumetric_efficiency_plenum": volumetric_efficiency_plenum,
            "volumetric_efficiency_atm": volumetric_efficiency_atm,
            "volumetric_efficiency": volumetric_efficiency_plenum,  # legacy alias
            "intake_mass_per_cycle_g": total_intake_mass * 1000.0,
            "restrictor_choked": self.restrictor_plenum.last_choked,
            "restrictor_mdot": self.restrictor_plenum.last_mdot_restrictor,
            "plenum_pressure_bar": self.restrictor_plenum.p / 1e5,
        }

    def run_rpm_sweep(
        self,
        rpm_start: Optional[float] = None,
        rpm_end: Optional[float] = None,
        rpm_step: Optional[float] = None,
        n_cycles: int = 5,
        verbose: bool = True,
        n_workers: Optional[int] = None,
        consumer=None,
    ) -> list[dict]:
        """Run simulation across an RPM range.

        Returns list of performance dicts, one per RPM point.
        """
        cfg = self.config.simulation
        if rpm_start is None:
            rpm_start = cfg.rpm_start
        if rpm_end is None:
            rpm_end = cfg.rpm_end
        if rpm_step is None:
            rpm_step = cfg.rpm_step

        rpm_points = np.arange(rpm_start, rpm_end + rpm_step / 2, rpm_step)
        rpm_points_list = [float(r) for r in rpm_points]

        # Decide which code path to take. Compute effective_workers using
        # the same formula ParallelSweepRunner uses, so the print line below
        # accurately reflects what will run.
        if n_workers is None:
            cpu = os.cpu_count() or 1
            effective_workers = max(1, min(cpu, len(rpm_points_list)))
        else:
            effective_workers = max(1, min(n_workers, len(rpm_points_list)))

        if verbose:
            print(f"RPM sweep: {rpm_start:.0f} to {rpm_end:.0f} step {rpm_step:.0f}")
            print(
                f"  {len(rpm_points)} RPM points, {n_cycles} cycles each, "
                f"{effective_workers} worker{'s' if effective_workers != 1 else ''}"
            )

        if effective_workers > 1:
            # Parallel path: delegate to ParallelSweepRunner.
            # Imported lazily so the sequential path doesn't pay the import cost.
            from engine_simulator.simulation.parallel_sweep import (
                CLIEventConsumer,
                ParallelSweepRunner,
            )
            runner = ParallelSweepRunner(
                config=self.config,
                n_workers=effective_workers,
                consumer=consumer or CLIEventConsumer(verbose=verbose),
            )
            sweep_results, results_by_rpm = runner.run(
                rpm_points_list, n_cycles=n_cycles,
            )
            self.results_by_rpm = results_by_rpm
            if results_by_rpm:
                # Backwards compat: self.results points at the last RPM,
                # matching the behavior of the sequential loop.
                self.results = results_by_rpm[rpm_points_list[-1]]
            if verbose:
                self._print_sweep_summary(sweep_results)
            return sweep_results

        # Sequential path. NOTE: a fresh SimulationOrchestrator is constructed
        # per RPM. This matches the parallel path's behavior (each worker has
        # its own orchestrator) and prevents pre-existing latent state-leak
        # bugs in BC and heat-transfer objects (e.g. WoschniHeatTransfer's
        # p_ref/T_ref/V_ref persist across RPMs without this) from causing
        # the second-and-later RPMs to drift slightly. With this construction,
        # the sequential and parallel paths produce bit-for-bit identical
        # results, which lets the equivalence test use `==` (not `np.isclose`).
        sweep_results = []
        for rpm in rpm_points:
            fresh_sim = SimulationOrchestrator(self.config)
            perf = fresh_sim.run_single_rpm(rpm, n_cycles=n_cycles, verbose=verbose)
            sweep_results.append(perf)
            self.results_by_rpm[float(rpm)] = fresh_sim.results
        # Backwards compat: self.results points at the last RPM's recorded data.
        if rpm_points_list:
            self.results = self.results_by_rpm[rpm_points_list[-1]]

        if verbose:
            self._print_sweep_summary(sweep_results)

        return sweep_results

    def _print_sweep_summary(self, sweep_results: list) -> None:
        """Print the per-RPM summary table. Identical for sequential and parallel
        paths so on-screen output is byte-for-byte identical regardless of --workers.
        """
        print("\n--- Performance Summary ---")
        print(f"{'RPM':>6} {'P_ind(hp)':>10} {'P_brk(hp)':>10} {'P_whl(hp)':>10} {'T_brk(Nm)':>10} {'T_whl(Nm)':>10} {'VE_p(%)':>8} {'VE_a(%)':>8} {'IMEP':>6} {'BMEP':>6} {'pPlen':>6} {'Chkd':>5}")
        for r in sweep_results:
            print(
                f"{r['rpm']:6.0f} {r['indicated_power_hp']:10.1f} "
                f"{r['brake_power_hp']:10.1f} {r['wheel_power_hp']:10.1f} "
                f"{r['brake_torque_Nm']:10.1f} {r['wheel_torque_Nm']:10.1f} "
                f"{r['volumetric_efficiency_plenum']*100:8.1f} {r['volumetric_efficiency_atm']*100:8.1f} "
                f"{r['imep_bar']:6.2f} {r['bmep_bar']:6.2f} {r['plenum_pressure_bar']:6.3f} "
                f"{'Yes' if r['restrictor_choked'] else 'No':>5}"
            )
