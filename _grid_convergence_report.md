# Grid Convergence Study — Issue 2 (Acoustic Resonance)

Closed-open pipe, L = 0.5 m, D = 40 mm, T = 300 K, c = 347.19 m/s,
t_end = 0.05 s, CFL = 0.85. Peak frequencies extracted via parabolic
(sub-bin) interpolation of the FFT magnitude spectrum (raw FFT bin
resolution is only 20 Hz at this t_end, so unassisted peak picking
aliases every peak to its nearest 20 Hz gridpoint and hides the trend).

## Results

| N   | f1 (Hz) | err1     | f3 (Hz) | err3     | f5 (Hz) | err5     | steps  | wall (s) |
|-----|---------|----------|---------|----------|---------|----------|--------|----------|
| 100 | 176.11  | +1.45 %  | 876.61  | +1.00 %  |   —     |    —     |  4 077 |   1.2    |
| 200 | 175.39  | +1.04 %  | 872.52  | +0.52 %  | 1568.56 | +0.40 %  |  8 208 |   4.8    |
| 500 | 174.94  | +0.78 %  | 869.07  | +0.13 %  | 1563.87 | +0.10 %  | 20 624 |  30.7    |

Analytical targets: f1 = 173.59 Hz, f3 = 867.97 Hz, f5 = 1562.35 Hz
(`f_n = (2n−1)·c/(4L)`).

All five modes, all N:

| mode | f_anal (Hz) | N=100     | N=200     | N=500     |
|------|-------------|-----------|-----------|-----------|
| 1    |  173.59     | +1.451 %  | +1.036 %  | +0.776 %  |
| 2    |  520.78     | +0.686 %  | +0.297 %  | +0.089 %  |
| 3    |  867.97     | +0.995 %  | +0.525 %  | +0.126 %  |
| 4    | 1215.16     | +0.811 %  | +0.424 %  | +0.219 %  |
| 5    | 1562.35     |    —      | +0.397 %  | +0.097 %  |

## Convergence conclusion

- Every mode's error is **positive** (detected > analytical) and
  **shrinks monotonically** with N. Successive-N error ratios are
  roughly 1.4×–4× per doubling, consistent with the MOC grid's
  first-order numerical dispersion.
- **N = 500 is grid-converged to within 1 %** on every harmonic
  (worst-case 0.78 % on the fundamental, ≤ 0.22 % on modes 2–5).
  N = 200 is converged to within ~1.1 %, adequate for most engineering
  purposes. N = 100 leaves 1–1.5 % error on the fundamental.

## Which cause dominates: discretization, NOT end correction

- The open-end BC (`engine_simulator/boundaries/open_end.py`) sets
  `p = p_atm` *exactly at the last cell* (`A_boundary =
  A_from_pressure(p_atm, AA, gam)`, then `bet = 2·A_boundary − lam`).
  There is no end-correction offset baked into the BC: it is an ideal
  open-end pressure node.
- A physical end correction of ~0.61·R = 12.2 mm would make the pipe
  **acoustically longer**, which shifts the fundamental from 173.6 Hz
  *down* to ~169.4 Hz (−2.4 %). The simulator's bias is in the opposite
  direction (+0.8 %…+1.5 %), so end correction cannot be the cause.
- Because the bias (a) has the wrong sign for end correction and
  (b) shrinks with N, the remaining shift is entirely **numerical
  dispersion / discretization error** in the MOC scheme.

## Spurious modes

None. The only "extra" peaks above the 5 %-of-max threshold at N = 200
(1918 Hz) and N = 500 (1913 Hz, 2260 Hz) are the true 6th and 7th odd
harmonics (analytical 1909.6 Hz and 2256.7 Hz, both within 0.5 %). No
sub-harmonics, no grid-aliasing modes, no growing noise floor.

## Files

- Study script: `/Users/nmurray/Developer/1d/_grid_convergence.py`
- This report:  `/Users/nmurray/Developer/1d/_grid_convergence_report.md`
