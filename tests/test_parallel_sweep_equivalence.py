"""Numerical equivalence between sequential and parallel RPM sweeps.

These are the keystone tests that pin "the math is unchanged" as a hard
falsifiable property. Each worker is a fully-deterministic sequence of
NumPy operations on private state — no shared memory, no parallel
reductions, no atomic ops. Therefore parallel results must be bit-for-bit
identical to sequential results, and the assertion is `==`, not allclose.

If this test ever fails by even one ULP, that's a real plumbing bug
(some shared state leaked, an operation order changed, etc.), not
floating-point noise.

NOTE: the sequential path constructs a fresh SimulationOrchestrator per
RPM, matching the parallel path's behavior. This sidesteps a latent
state-leak bug in the original sequential code where WoschniHeatTransfer's
p_ref/T_ref/V_ref (and other BC accumulators) carried over from the
previous RPM. With the fresh-orchestrator pattern in both code paths,
the two are bit-identical.
"""

import numpy as np
import pytest

from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator


# Use a small sweep so the test runs in reasonable time. The point is
# correctness, not coverage of every RPM.
RPM_START = 8000
RPM_END = 10000
RPM_STEP = 1000
N_CYCLES = 4


def _run_sequential():
    sim = SimulationOrchestrator(EngineConfig())
    sweep = sim.run_rpm_sweep(
        rpm_start=RPM_START, rpm_end=RPM_END, rpm_step=RPM_STEP,
        n_cycles=N_CYCLES, verbose=False, n_workers=1,
    )
    return sweep, sim


def _run_parallel(n_workers):
    sim = SimulationOrchestrator(EngineConfig())
    sweep = sim.run_rpm_sweep(
        rpm_start=RPM_START, rpm_end=RPM_END, rpm_step=RPM_STEP,
        n_cycles=N_CYCLES, verbose=False, n_workers=n_workers,
    )
    return sweep, sim


class TestPerfDictEquivalence:
    def test_parallel_2_workers_matches_sequential_bit_identical(self):
        seq_results, _seq_sim = _run_sequential()
        par_results, _par_sim = _run_parallel(n_workers=2)

        assert len(seq_results) == len(par_results)
        for seq, par in zip(seq_results, par_results):
            assert seq["rpm"] == par["rpm"]
            for key in seq:
                seq_val = seq[key]
                par_val = par[key]
                if isinstance(seq_val, (int, float)):
                    assert seq_val == par_val, (
                        f"Mismatch at RPM {seq['rpm']} key {key}: "
                        f"seq={seq_val} par={par_val}"
                    )
                else:
                    assert seq_val == par_val

    def test_parallel_3_workers_matches_sequential_bit_identical(self):
        # Use a different worker count to verify the result doesn't depend
        # on how many parallel processes are running.
        seq_results, _ = _run_sequential()
        par_results, _ = _run_parallel(n_workers=3)

        assert len(seq_results) == len(par_results)
        for seq, par in zip(seq_results, par_results):
            assert seq["rpm"] == par["rpm"]
            for key in seq:
                seq_val = seq[key]
                par_val = par[key]
                if isinstance(seq_val, (int, float)):
                    assert seq_val == par_val, (
                        f"Mismatch at RPM {seq['rpm']} key {key}: "
                        f"seq={seq_val} par={par_val}"
                    )
                else:
                    assert seq_val == par_val

    def test_rpm_order_preserved_in_parallel_results(self):
        par_results, _ = _run_parallel(n_workers=3)
        rpms = [r["rpm"] for r in par_results]
        assert rpms == sorted(rpms)


class TestSimulationResultsEquivalence:
    def test_results_by_rpm_arrays_bit_identical(self):
        """Recorded probe data must match between sequential and parallel paths.

        Catches the case where perf dicts match by coincidence but the
        underlying recorded state has drifted (e.g. a serialization
        round-trip dropped a field, an array was rebuilt with different
        dtype, an emit-side mutation got dropped, etc.).
        """
        _seq_perf, seq_sim = _run_sequential()
        _par_perf, par_sim = _run_parallel(n_workers=2)

        assert set(seq_sim.results_by_rpm.keys()) == set(par_sim.results_by_rpm.keys())

        for rpm in sorted(seq_sim.results_by_rpm.keys()):
            seq_r = seq_sim.results_by_rpm[rpm]
            par_r = par_sim.results_by_rpm[rpm]

            # Time history
            assert len(seq_r.theta_history) == len(par_r.theta_history), (
                f"Length mismatch at {rpm} RPM"
            )
            np.testing.assert_array_equal(
                np.asarray(seq_r.theta_history), np.asarray(par_r.theta_history),
                err_msg=f"theta_history at {rpm} RPM",
            )
            np.testing.assert_array_equal(
                np.asarray(seq_r.dt_history), np.asarray(par_r.dt_history),
                err_msg=f"dt_history at {rpm} RPM",
            )

            # Plenum
            np.testing.assert_array_equal(
                np.asarray(seq_r.plenum_pressure), np.asarray(par_r.plenum_pressure),
                err_msg=f"plenum_pressure at {rpm} RPM",
            )
            np.testing.assert_array_equal(
                np.asarray(seq_r.plenum_temperature), np.asarray(par_r.plenum_temperature),
                err_msg=f"plenum_temperature at {rpm} RPM",
            )

            # Restrictor
            np.testing.assert_array_equal(
                np.asarray(seq_r.restrictor_mdot), np.asarray(par_r.restrictor_mdot),
                err_msg=f"restrictor_mdot at {rpm} RPM",
            )

            # Per-cylinder probes
            assert set(seq_r.cylinder_data.keys()) == set(par_r.cylinder_data.keys())
            for cyl_id in seq_r.cylinder_data:
                seq_arrs = seq_r.get_cylinder_arrays(cyl_id)
                par_arrs = par_r.get_cylinder_arrays(cyl_id)
                for k in seq_arrs:
                    np.testing.assert_array_equal(
                        seq_arrs[k], par_arrs[k],
                        err_msg=f"cylinder {cyl_id} {k} at {rpm} RPM",
                    )

            # Per-pipe probes
            assert set(seq_r.pipe_probes.keys()) == set(par_r.pipe_probes.keys())
            for key in seq_r.pipe_probes:
                seq_p = seq_r.pipe_probes[key]
                par_p = par_r.pipe_probes[key]
                np.testing.assert_array_equal(
                    np.asarray(seq_p.pressure), np.asarray(par_p.pressure),
                    err_msg=f"pipe {key} pressure at {rpm} RPM",
                )
                np.testing.assert_array_equal(
                    np.asarray(seq_p.temperature), np.asarray(par_p.temperature),
                    err_msg=f"pipe {key} temperature at {rpm} RPM",
                )
                np.testing.assert_array_equal(
                    np.asarray(seq_p.velocity), np.asarray(par_p.velocity),
                    err_msg=f"pipe {key} velocity at {rpm} RPM",
                )
                np.testing.assert_array_equal(
                    np.asarray(seq_p.density), np.asarray(par_p.density),
                    err_msg=f"pipe {key} density at {rpm} RPM",
                )
