"""Grid convergence study for Issue 2 (acoustic resonance).

Runs run_acoustic_resonance at N in [100, 200, 500], extracts the first 5
FFT peaks, and compares against the analytical odd-harmonic series
f_n = (2n-1)*c/(4L) with c = sqrt(1.4*287*300).

Investigation only -- no code under engine_simulator/ is modified.
"""
from __future__ import annotations

import os
os.environ["MPLBACKEND"] = "Agg"

import time
import math
import sys

import numpy as np

from engine_simulator.validation.acoustic_resonance import run_acoustic_resonance


def parabolic_peak(freqs: np.ndarray, amp: np.ndarray, i: int):
    """Sub-bin accurate peak location via quadratic interpolation of 3
    adjacent FFT magnitudes. Returns (freq, amp).
    """
    if i <= 0 or i >= len(amp) - 1:
        return float(freqs[i]), float(amp[i])
    y0, y1, y2 = float(amp[i - 1]), float(amp[i]), float(amp[i + 1])
    denom = (y0 - 2.0 * y1 + y2)
    if abs(denom) < 1e-30:
        return float(freqs[i]), y1
    delta = 0.5 * (y0 - y2) / denom  # in bins, [-0.5, 0.5]
    df = float(freqs[1] - freqs[0])
    f_peak = float(freqs[i]) + delta * df
    a_peak = y1 - 0.25 * (y0 - y2) * delta
    return f_peak, a_peak


def analytical_freqs(L: float, c: float, n: int = 5):
    return [(2 * k - 1) * c / (4 * L) for k in range(1, n + 1)]


def main():
    L = 0.5
    t_end = 0.05
    c = math.sqrt(1.4 * 287.0 * 300.0)
    f_anal = analytical_freqs(L, c, 5)

    print("=" * 72)
    print("Grid convergence study -- acoustic resonance (closed-open pipe)")
    print(f"  L = {L} m, t_end = {t_end} s, c = {c:.3f} m/s")
    print(f"  Analytical: " + ", ".join(f"{f:.2f}" for f in f_anal))
    print("=" * 72)

    results = {}
    Ns = [100, 200, 500]

    # Peak-detection: we use the same scheme as run_acoustic_resonance but
    # extract the top 5 by amplitude so we can report amplitudes too.
    for N in Ns:
        print(f"\n--- N = {N} ---")
        t0 = time.perf_counter()
        res = run_acoustic_resonance(
            pipe_length=L,
            n_points=N,
            t_end=t_end,
            plot=False,
        )
        wall = time.perf_counter() - t0

        freqs = res["freqs"]
        amp = res["amplitude"]
        # Local maxima above 5% of max (skipping DC)
        threshold = 0.05 * float(np.max(amp[1:]))
        peak_idx = []
        for i in range(2, len(amp) - 1):
            if amp[i] > amp[i - 1] and amp[i] > amp[i + 1] and amp[i] > threshold:
                peak_idx.append(i)
        peak_idx = np.array(peak_idx, dtype=int)
        # Sort by frequency ascending, take first 5
        peak_idx = peak_idx[np.argsort(freqs[peak_idx])]
        top_idx = peak_idx[:5]
        # Parabolic sub-bin interpolation for accurate peak locations
        top_f_list = []
        top_a_list = []
        for i in top_idx:
            fp, ap = parabolic_peak(freqs, amp, int(i))
            top_f_list.append(fp)
            top_a_list.append(ap)
        top_f = np.array(top_f_list)
        top_a = np.array(top_a_list)

        n_steps = len(res["t"])
        df_bin = float(freqs[1] - freqs[0]) if len(freqs) > 1 else float("nan")

        print(f"  steps={n_steps}  wall={wall:.2f}s  FFT bin={df_bin:.2f} Hz")
        # Report all peaks above threshold (to flag any spurious modes)
        print(f"  all peaks above threshold ({len(peak_idx)}):")
        for i in peak_idx[:15]:
            fp, ap = parabolic_peak(freqs, amp, int(i))
            print(f"    {fp:>9.2f} Hz   amp={ap:.3e}")
        print(f"  {'n':>3} {'f_det(Hz)':>11} {'f_anal(Hz)':>11} {'err(%)':>8} {'amp':>12}")
        for k, (f, a) in enumerate(zip(top_f, top_a), start=1):
            if k <= len(f_anal):
                fa = f_anal[k - 1]
                err = (f - fa) / fa * 100.0
                print(f"  {k:>3} {f:>11.2f} {fa:>11.2f} {err:>+7.2f}% {a:>12.4e}")
            else:
                print(f"  {k:>3} {f:>11.2f} {'-':>11} {'-':>7}  {a:>12.4e}")

        results[N] = {
            "top_f": top_f.tolist(),
            "top_a": top_a.tolist(),
            "steps": n_steps,
            "wall": wall,
        }

    # Summary table
    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    hdr = f"{'N':>5} {'f1':>9} {'e1%':>7} {'f3':>9} {'e3%':>7} {'f5':>9} {'e5%':>7} {'steps':>8} {'wall(s)':>9}"
    print(hdr)
    print("-" * len(hdr))
    for N in Ns:
        r = results[N]
        tf = r["top_f"]
        def pair(k):
            if k - 1 < len(tf):
                f = tf[k - 1]
                e = (f - f_anal[k - 1]) / f_anal[k - 1] * 100.0
                return f, e
            return float("nan"), float("nan")
        f1, e1 = pair(1)
        f3, e3 = pair(3)
        f5, e5 = pair(5)
        print(f"{N:>5} {f1:>9.2f} {e1:>+6.2f}% {f3:>9.2f} {e3:>+6.2f}% {f5:>9.2f} {e5:>+6.2f}% {r['steps']:>8d} {r['wall']:>9.2f}")

    # Convergence check: successive ratio of errors
    print()
    print("Convergence check (|f_N - f_anal| / f_anal, percent):")
    for k in (1, 2, 3, 4, 5):
        row = []
        for N in Ns:
            tf = results[N]["top_f"]
            if k - 1 < len(tf):
                f = tf[k - 1]
                e = (f - f_anal[k - 1]) / f_anal[k - 1] * 100.0
                row.append(f"{e:+6.3f}%")
            else:
                row.append("   --  ")
        print(f"  mode {k} (f_anal={f_anal[k-1]:7.2f} Hz):  " + "  ".join(f"N={N}: {r}" for N, r in zip(Ns, row)))

    return results


if __name__ == "__main__":
    main()
