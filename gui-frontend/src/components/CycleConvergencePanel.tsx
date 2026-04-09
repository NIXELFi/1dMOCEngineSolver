import { useMemo } from "react";
import LineChart from "./charts/LineChart";
import { useSweepStore } from "../state/sweepStore";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

/** A chart row for the delta-vs-cycle sparkline. */
interface DeltaRow {
  cycle: number;
  delta: number;
  [extraKey: string]: number | boolean | undefined;
}

/* ========================================================================= */
/* Accent                                                                     */
/*                                                                           */
/* Convergence is the "is this result trustworthy?" tab. The palette picks  */
/* amber (status-converged) for the delta trace so the eye immediately      */
/* associates this tab with the convergence semantic used elsewhere in the  */
/* GUI (WorkerTile border colors, Bloomberg "converged" badges).            */
/* ========================================================================= */

const DELTA_COLOR = "#FFD15C";

/* ========================================================================= */
/* CycleConvergencePanel — the "Convergence" tab body inside RpmDetail       */
/* ========================================================================= */

/**
 * CycleConvergencePanel — unique among the RpmDetail tabs in that it does
 * NOT need the heavy `SimulationResults` payload from
 * `GET /api/sweeps/current/results/{rpm}`. Instead it reads the cycle-
 * by-cycle `delta_history` and `p_ivc_history` arrays directly off the
 * live `RpmState` in the Zustand store, which are populated by the
 * WebSocket event stream (`cycle_done` events).
 *
 * Layout (per §4 of the design spec):
 *   • Left — a dense data table with one row per cycle showing the
 *     convergence delta and the per-cylinder p_IVC in bar.
 *   • Right — a small delta-vs-cycle line chart so the reader can SEE
 *     the exponential drop toward zero (or the stall that says "didn't
 *     converge").
 *
 * Because this tab is driven by the event stream, it can render as soon
 * as a single cycle has arrived — no lazy fetch required.
 */
export default function CycleConvergencePanel() {
  const sweep = useSweepStore((s) => s.sweep);
  const selectedRpm = useSweepStore((s) => s.selectedRpm);

  /* ---- Pull the live rpm state out of the store ------------------------- */
  const rpmState =
    sweep && selectedRpm !== null
      ? sweep.rpms[String(selectedRpm)]
      : null;

  const deltaHistory = rpmState?.delta_history ?? [];
  const pIvcHistory = rpmState?.p_ivc_history ?? [];
  const nCylinders = pIvcHistory.length > 0 ? pIvcHistory[0].length : 4;

  /* ---- Chart rows ------------------------------------------------------- */
  const deltaRows = useMemo<DeltaRow[]>(() => {
    return deltaHistory.map((d, i) => ({
      cycle: i + 1,
      // d may be null (first cycle's convergence delta is non-finite,
      // coerced to null by the backend) — render as NaN so the chart
      // skips the point.
      delta: d != null && Number.isFinite(d) && d > 0 ? d : Number.NaN,
    }));
  }, [deltaHistory]);

  const hasData = deltaHistory.length > 0;

  /* ---- Render ----------------------------------------------------------- */
  if (!hasData) {
    return (
      <div className="py-10 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 max-w-[460px]">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted"
            aria-hidden
          />
          <div className="w-16 h-px bg-border-default" aria-hidden />
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-text-muted leading-none text-center">
            No Cycle Data Yet
          </p>
          <p className="text-[10px] font-mono text-text-muted/70 leading-snug text-center">
            Convergence history streams in via cycle_done events.
          </p>
        </div>
      </div>
    );
  }

  const nCycles = deltaHistory.length;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(260px,420px)] gap-2">
      {/* ==================================================================*/}
      {/* Left — cycle-by-cycle table                                       */}
      {/* ==================================================================*/}
      <section
        className="flex flex-col bg-surface-raised border border-border-default rounded font-ui overflow-hidden"
        aria-label="Cycle convergence table"
      >
        <header className="flex items-stretch border-b border-border-default">
          <div className="flex-1 flex items-center gap-2 px-3 py-1.5 min-w-0">
            <span
              className="inline-block w-[3px] h-3"
              style={{ backgroundColor: DELTA_COLOR }}
              aria-hidden
            />
            <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
              [T1]
            </span>
            <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
              Cycle History
            </h4>
          </div>

          <div className="flex items-center gap-1 px-3 border-l border-border-default">
            <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
              cycles
            </span>
            <span className="text-[9px] font-mono tabular-nums text-text-secondary leading-none">
              {String(nCycles).padStart(2, "0")}
            </span>
          </div>
        </header>

        {/* Scroll wrapper so long histories don't blow out the panel. */}
        <div className="overflow-auto max-h-[340px]">
          <table
            className="w-full border-collapse font-mono tabular-nums"
            aria-label="Cycle-by-cycle convergence"
          >
            <thead>
              <tr className="h-7 border-b border-border-default bg-surface/60">
                <th className="pl-3 pr-2 text-left text-[9px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                  Cycle
                </th>
                <th className="px-2 text-right text-[9px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                  Δ
                </th>
                {Array.from({ length: nCylinders }, (_, i) => (
                  <th
                    key={i}
                    className="px-2 text-right text-[9px] font-semibold uppercase tracking-[0.18em] text-text-muted"
                  >
                    p<span className="lowercase">ivc</span> · C{i + 1}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {deltaHistory.map((delta, cycleIdx) => {
                const pIvcRow = pIvcHistory[cycleIdx] ?? [];
                const isLast = cycleIdx === deltaHistory.length - 1;
                return (
                  <tr
                    key={cycleIdx}
                    className={[
                      "h-7 border-b border-border-default/70",
                      "hover:bg-surface/50 transition-colors duration-100",
                      isLast ? "bg-surface/40" : "",
                    ].join(" ")}
                  >
                    {/* Cycle number */}
                    <td className="pl-3 pr-2 text-[10px] text-text-secondary">
                      <span className="text-text-muted">#</span>
                      {String(cycleIdx + 1).padStart(2, "0")}
                    </td>

                    {/* Delta — color-graded: warm when high, neutral when
                        converged. The default convergence threshold on
                        the solver side is ~0.01, so we use that as the
                        visual inflection point. delta may be null for the
                        first cycle (no previous cycle to compare). */}
                    <td className="px-2 text-right text-[10px]">
                      <span
                        className={
                          delta != null &&
                          Number.isFinite(delta) &&
                          delta < 0.01
                            ? "text-status-done"
                            : "text-accent"
                        }
                      >
                        {delta != null && Number.isFinite(delta)
                          ? delta.toFixed(4)
                          : "—"}
                      </span>
                    </td>

                    {/* Per-cylinder p_IVC in bar */}
                    {Array.from({ length: nCylinders }, (_, i) => {
                      const p = pIvcRow[i];
                      return (
                        <td
                          key={i}
                          className="px-2 text-right text-[10px] text-text-primary"
                        >
                          {Number.isFinite(p) ? (p / 1e5).toFixed(3) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ==================================================================*/}
      {/* Right — delta vs cycle line chart                                 */}
      {/* ==================================================================*/}
      <section
        className="flex flex-col bg-surface-raised border border-border-default rounded font-ui"
        aria-label="Convergence delta trace"
      >
        <header className="flex items-stretch border-b border-border-default">
          <div className="flex-1 flex items-center gap-2 px-3 py-1.5 min-w-0">
            <span
              className="inline-block w-[3px] h-3"
              style={{ backgroundColor: DELTA_COLOR }}
              aria-hidden
            />
            <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
              [C1]
            </span>
            <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
              Delta vs Cycle
            </h4>
          </div>

          <div className="flex items-center gap-1.5 px-3 border-l border-border-default">
            <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
              last
            </span>
            <span className="text-[10px] font-mono tabular-nums text-text-secondary leading-none">
              {(() => {
                const last = deltaHistory[deltaHistory.length - 1];
                return last != null && Number.isFinite(last)
                  ? last.toFixed(4)
                  : "—";
              })()}
            </span>
          </div>
        </header>

        <div className="p-3">
          <LineChart
            data={deltaRows}
            xKey="cycle"
            series={[{ key: "delta", label: "Δ", color: DELTA_COLOR }]}
            yLabel="Δ · LINEAR"
            height={200}
          />
        </div>
      </section>
    </div>
  );
}
