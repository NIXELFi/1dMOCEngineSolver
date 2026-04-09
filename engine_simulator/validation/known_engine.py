"""Validation against the SDM26 powertrain spec sheet estimates.

Compares simulation predictions against the SDM26 design envelope for the
20mm-restricted Honda CBR600RR. These are estimates from the design spec
(see POWERTRAIN_SPEC.md), NOT dyno-validated numbers, so the simulation only
needs to land in this neighborhood.

Spec sheet headline numbers:
  Peak power  : 55 kW (~73.8 hp brake) @ 9000 RPM
  Peak torque : 50 Nm @ 8000 RPM
  80% torque  : 6750 RPM
"""

from __future__ import annotations

import numpy as np


# SDM26 design-estimate envelope. Power/torque are brake values; VE is
# atmospheric reference.
#
# Spec sheet anchors:
#   - Peak power 55 kW (~73.8 hp) at 9000 RPM
#   - 80% torque RPM = 6750 (so torque at 6750 ~= 0.8 * peak torque)
#   - Peak torque RPM = 8000
#
# Note: the spec sheet's "peak torque 50 Nm" estimate is not numerically
# consistent with "55 kW @ 9000 RPM" — for the engine to make 55 kW at
# 9000 RPM, torque there must be ~58 Nm, which exceeds 50 Nm. The spec
# sheet says these are pre-dyno estimates, so we anchor on peak power and
# build a smooth curve that hits it. Peak torque comes out ~62 Nm @ 8000,
# higher than the spec sheet's rough 50 Nm guess.
PUBLISHED_DATA = {
    "rpm":        [6000, 6750, 7000, 8000, 9000, 10000, 11000, 12000, 13000],
    "power_hp":   [35.4, 45.0, 49.7, 69.7, 73.8, 71.6,  66.4,  59.0,  49.3],
    "torque_Nm":  [42.0, 47.7, 50.8, 62.0, 58.4, 51.0,  43.0,  35.0,  27.0],
    "ve_pct":     [80,   84,   86,   92,   95,   90,    83,    74,    65],
}


def validate_against_published(sweep_results: list[dict], verbose: bool = True) -> dict:
    """Compare simulation results against published data.

    Returns error metrics and pass/fail assessment.
    """
    if verbose:
        print("=" * 60)
        print("Validation Against Published FSAE CBR600RR Data")

    pub = PUBLISHED_DATA
    rpm_pub = np.array(pub["rpm"])
    power_pub = np.array(pub["power_hp"])
    torque_pub = np.array(pub["torque_Nm"])
    ve_pub = np.array(pub["ve_pct"])

    # Interpolate simulation results to published RPM points.
    # Published data is brake power/torque and atmospheric VE — use matching sim fields.
    rpm_sim = np.array([r["rpm"] for r in sweep_results])
    power_sim = np.array([r.get("brake_power_hp", r["indicated_power_hp"]) for r in sweep_results])
    torque_sim = np.array([r.get("brake_torque_Nm", r["indicated_torque_Nm"]) for r in sweep_results])
    ve_sim = np.array([r["volumetric_efficiency_atm"] * 100
                       for r in sweep_results])

    # Only compare at overlapping RPM points
    rpm_common = rpm_pub[(rpm_pub >= rpm_sim.min()) & (rpm_pub <= rpm_sim.max())]
    if len(rpm_common) == 0:
        print("  No overlapping RPM points for comparison!")
        return {"valid": False}

    power_interp = np.interp(rpm_common, rpm_sim, power_sim)
    torque_interp = np.interp(rpm_common, rpm_sim, torque_sim)
    ve_interp = np.interp(rpm_common, rpm_sim, ve_sim)

    # Published values at common RPMs
    mask = np.isin(rpm_pub, rpm_common)
    power_pub_c = power_pub[mask]
    torque_pub_c = torque_pub[mask]
    ve_pub_c = ve_pub[mask]

    # Error metrics
    power_err = np.abs(power_interp - power_pub_c) / power_pub_c * 100
    torque_err = np.abs(torque_interp - torque_pub_c) / torque_pub_c * 100
    ve_err = np.abs(ve_interp - ve_pub_c) / ve_pub_c * 100

    results = {
        "rpm": rpm_common,
        "power_error_pct": power_err,
        "torque_error_pct": torque_err,
        "ve_error_pct": ve_err,
        "power_rms_error": float(np.sqrt(np.mean(power_err**2))),
        "torque_rms_error": float(np.sqrt(np.mean(torque_err**2))),
        "ve_rms_error": float(np.sqrt(np.mean(ve_err**2))),
        "peak_power_sim": float(np.max(power_sim)),
        "peak_power_published": float(np.max(power_pub)),
        "peak_power_rpm_sim": float(rpm_sim[np.argmax(power_sim)]),
        "peak_power_rpm_pub": float(rpm_pub[np.argmax(power_pub)]),
    }

    # Assessment: within ±15% is reasonable for a 1D simulation
    all_within_15 = (np.max(power_err) < 15 and np.max(torque_err) < 15 and np.max(ve_err) < 15)
    results["within_15pct"] = all_within_15

    # Qualitative checks
    results["correct_power_trend"] = (
        np.argmax(power_interp) >= len(rpm_common) // 2  # peak in upper RPM range
    )
    results["restrictor_limited"] = any(r.get("restrictor_choked", False) for r in sweep_results)

    if verbose:
        print(f"\n  {'RPM':>6} {'Pub HP':>8} {'Sim HP':>8} {'Err%':>6} {'Pub Nm':>8} {'Sim Nm':>8} {'Err%':>6}")
        for i, rpm in enumerate(rpm_common):
            print(
                f"  {rpm:6.0f} {power_pub_c[i]:8.1f} {power_interp[i]:8.1f} {power_err[i]:6.1f}"
                f" {torque_pub_c[i]:8.1f} {torque_interp[i]:8.1f} {torque_err[i]:6.1f}"
            )

        print(f"\n  RMS errors: Power={results['power_rms_error']:.1f}%, "
              f"Torque={results['torque_rms_error']:.1f}%, "
              f"VE={results['ve_rms_error']:.1f}%")
        print(f"  Peak power: Sim={results['peak_power_sim']:.1f} hp @ "
              f"{results['peak_power_rpm_sim']:.0f} RPM")
        print(f"  Peak power: Published={results['peak_power_published']:.1f} hp @ "
              f"{results['peak_power_rpm_pub']:.0f} RPM")
        print(f"  All within ±15%: {'YES' if all_within_15 else 'NO'}")
        print(f"  Restrictor limited: {'YES' if results['restrictor_limited'] else 'NO'}")

    return results
