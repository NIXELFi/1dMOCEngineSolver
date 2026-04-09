import { useSweepStore } from "../state/sweepStore";
import type { RpmState } from "../types/events";
import WorkerTile from "./WorkerTile";

/**
 * WorkersStrip — the horizontal row of live per-RPM telemetry tiles.
 *
 * Visually this panel mirrors the SweepCurves `ChartPanel` chrome (per the
 * Mission Control layout in 2026-04-08-engine-sim-gui-v1-design.md §4/§5):
 * a hairline-bordered surface with a header strip carrying a bracketed
 * ordinal "[W]", a section title, and a right-aligned "n = NN" count. When
 * any worker is running a small accent-pulse "RUNNING" badge sits in the
 * header between the title and the count so the strip's live-state is
 * readable at a glance — the same visual grammar as the TopBar status
 * readout.
 *
 * Returns null when there is no sweep loaded — the strip collapses entirely
 * in idle state, matching the layout sketch in §4 of the spec. It stays
 * visible for completed/error/stopped sweeps so the user can click any
 * tile to inspect that RPM in RpmDetail.
 */
export default function WorkersStrip() {
  const sweep = useSweepStore((s) => s.sweep);
  const selectedRpm = useSweepStore((s) => s.selectedRpm);
  const setSelectedRpm = useSweepStore((s) => s.setSelectedRpm);

  if (!sweep) return null;

  const nCyclesTarget = sweep.config_summary.n_cycles;

  // Build the ordered tile list. Keys on the rpms dict can be either the
  // integer string ("8000") or whatever JSON produced; try both forms to
  // be robust against either casing.
  const tiles = sweep.rpm_points
    .map((rpm) => {
      const state =
        sweep.rpms[String(rpm)] ?? sweep.rpms[String(Number(rpm))];
      return state ? { rpm, state } : null;
    })
    .filter((t): t is { rpm: number; state: RpmState } => t !== null)
    // Stable order by rpm_index when set, falling back to raw rpm.
    .sort((a, b) => {
      const ai = a.state.rpm_index ?? a.rpm;
      const bi = b.state.rpm_index ?? b.rpm;
      return ai - bi;
    });

  const totalPoints = sweep.rpm_points.length;
  const anyRunning = tiles.some((t) => t.state.status === "running");

  return (
    <section
      className="flex flex-col bg-surface border border-border-default rounded font-ui"
      aria-label="Worker tiles"
    >
      {/* ---- Header strip — matches SweepCurves ChartPanel header --- */}
      <header className="flex items-stretch border-b border-border-default">
        <div className="flex-1 flex items-baseline gap-2 px-3 py-2 min-w-0">
          <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
            [W]
          </span>
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
            Workers
          </h3>
          <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
            · per-rpm telemetry
          </span>
        </div>

        {/* Right side: optional RUNNING pulse, then n = NN */}
        <div className="flex items-center">
          {anyRunning && (
            <div className="flex items-center gap-1.5 px-2.5 border-l border-border-default">
              <span className="relative inline-flex w-1.5 h-1.5" aria-hidden>
                <span className="absolute inset-0 rounded-full bg-accent animate-ping opacity-60" />
                <span className="relative inline-block w-1.5 h-1.5 rounded-full bg-accent" />
              </span>
              <span className="text-[9px] font-mono font-semibold uppercase tracking-[0.14em] text-accent leading-none">
                Running
              </span>
            </div>
          )}
          <div className="flex items-center gap-1 px-3 border-l border-border-default">
            <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
              n
            </span>
            <span className="text-[9px] font-mono text-text-muted leading-none">
              =
            </span>
            <span className="text-[9px] font-mono tabular-nums text-text-secondary leading-none">
              {String(totalPoints).padStart(2, "0")}
            </span>
          </div>
        </div>
      </header>

      {/* ---- Tiles body -------------------------------------------- */}
      <div className="p-3">
        {tiles.length === 0 ? (
          <div className="flex items-center justify-center py-6">
            <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-muted leading-none">
              no workers
            </span>
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {tiles.map(({ rpm, state }) => (
              <WorkerTile
                key={rpm}
                rpm={rpm}
                rpmState={state}
                nCyclesTarget={nCyclesTarget}
                selected={selectedRpm === rpm}
                onClick={() => setSelectedRpm(rpm)}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
