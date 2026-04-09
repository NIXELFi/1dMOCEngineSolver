import { useEffect, useState } from "react";
import { AlertTriangle, Check, Clock, Loader2 } from "lucide-react";
import type { RpmState } from "../types/events";
import Sparkline from "./charts/Sparkline";

interface WorkerTileProps {
  rpm: number;
  rpmState: RpmState;
  /** Target cycle count from sweep.config_summary.n_cycles. */
  nCyclesTarget: number;
  selected: boolean;
  onClick: () => void;
}

/* ------------------------------------------------------------------------- */
/* Color/label tables keyed by status — keeps the render function flat.      */
/* ------------------------------------------------------------------------- */

const STATUS_LABEL: Record<RpmState["status"], string> = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  error: "Error",
};

/**
 * WorkerTile — a dense per-RPM telemetry card.
 *
 * Visual language matches the rest of the Mission Control layout (per
 * 2026-04-08-engine-sim-gui-v1-design.md §5): hairline 1px borders, sharp
 * 4px corners, JetBrains Mono numerics with tabular-nums, the single
 * vermillion accent reserved for running state, bracketed [NN] ordinals
 * matching the SweepCurves chart panels. Every row of the tile is a
 * label/value pair so the eye can scan a wall of tiles like a table.
 *
 * The tile is deliberately fixed-height (150px) so that content arriving
 * asynchronously — cycle counter, delta row, sparkline — doesn't make the
 * workers strip jitter. Rows appear inside the reserved slot instead of
 * pushing siblings around.
 */
export default function WorkerTile({
  rpm,
  rpmState,
  nCyclesTarget,
  selected,
  onClick,
}: WorkerTileProps) {
  const { status } = rpmState;

  // Live wall-clock tick for the elapsed counter. We re-render once a
  // second while the rpm is running so the displayed elapsed value
  // ticks up smoothly between cycle_done events (which only fire every
  // 10-15s on the early cycles). Done/queued/error tiles don't need
  // the tick — their elapsed is frozen.
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (status !== "running") return;
    const id = window.setInterval(() => forceTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [status]);

  // Compute the elapsed value to display. For running tiles, prefer the
  // wall-clock interpolation from `client_started_at_ms` (which the
  // event reducer captures on rpm_start, and back-fills from snapshot
  // elapsed on reload). Falls back to the raw `elapsed` field for any
  // tile that doesn't have a client timestamp.
  const displayElapsed: number | undefined = (() => {
    if (status === "running" && rpmState.client_started_at_ms != null) {
      return (Date.now() - rpmState.client_started_at_ms) / 1000;
    }
    return rpmState.elapsed;
  })();

  /* -- Per-status border + optional glow ------------------------------- */
  const borderClass = (() => {
    switch (status) {
      case "running":
        // Border in accent + a 1px outer halo on top. The halo is a
        // box-shadow ring rather than a blur so it stays crisp at all
        // zoom levels — this is an instrument panel, not a glow demo.
        return "border-accent shadow-[0_0_0_1px_rgba(255,79,31,0.35)]";
      case "done":
        return "border-status-done";
      case "error":
        return "border-status-error";
      case "queued":
      default:
        return "border-border-default opacity-70";
    }
  })();

  /* -- Selection ring stacks on top of the border ---------------------- */
  const ringClass = selected
    ? "ring-1 ring-accent ring-offset-1 ring-offset-bg"
    : "";

  /* -- Error tiles get the error_msg in their title for hover tooltip -- */
  const titleAttr =
    status === "error"
      ? rpmState.traceback || rpmState.error_msg || "Error"
      : undefined;

  return (
    <button
      type="button"
      onClick={onClick}
      title={titleAttr}
      aria-label={`RPM ${rpm} — ${STATUS_LABEL[status]}`}
      className={[
        "group relative flex flex-col text-left",
        "w-[184px] h-[150px] p-2.5",
        "bg-surface border rounded",
        "font-ui cursor-pointer select-none",
        "transition-colors duration-150 ease-out",
        "hover:bg-surface-raised",
        borderClass,
        ringClass,
      ].join(" ")}
    >
      {/* ---- Row 1: RPM number + [NN] ordinal ---------------------- */}
      <div className="flex items-start justify-between leading-none">
        <span className="text-2xl font-mono font-medium tabular-nums text-text-primary leading-none">
          {rpm.toString()}
        </span>
        <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums pt-[3px]">
          [{String(rpmState.rpm_index ?? 0).padStart(2, "0")}]
        </span>
      </div>

      {/* ---- Row 2: status icon + label hairline ------------------ */}
      <StatusRow status={status} />

      {/* ---- Body area: status-dependent content ------------------- */}
      <div className="flex-1 min-h-0 flex flex-col justify-start gap-1 mt-1">
        {status === "queued" && <QueuedBody />}

        {status === "running" && (
          <RunningBody rpmState={rpmState} nCyclesTarget={nCyclesTarget} />
        )}

        {status === "done" && <DoneBody rpmState={rpmState} />}

        {status === "error" && <ErrorBody rpmState={rpmState} />}
      </div>

      {/* ---- Row N: elapsed time, bottom-aligned ------------------ */}
      <div className="flex items-baseline justify-between pt-1 border-t border-border-default/60">
        <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
          elapsed
        </span>
        <span className="text-[11px] font-mono font-medium tabular-nums text-text-secondary leading-none">
          {formatElapsed(displayElapsed)}
        </span>
      </div>
    </button>
  );
}

/* ========================================================================= */
/* StatusRow — thin label row with the lucide icon + uppercase status text   */
/* ========================================================================= */

function StatusRow({ status }: { status: RpmState["status"] }) {
  const common = "flex items-center gap-1.5 mt-1.5 leading-none";

  if (status === "queued") {
    return (
      <div className={common}>
        <Clock className="w-3 h-3 text-text-muted" strokeWidth={1.8} />
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-text-muted">
          Queued
        </span>
      </div>
    );
  }

  if (status === "running") {
    return (
      <div className={common}>
        <Loader2 className="w-3 h-3 text-accent animate-spin" strokeWidth={2} />
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent">
          Running
        </span>
      </div>
    );
  }

  if (status === "done") {
    return (
      <div className={common}>
        <Check className="w-3 h-3 text-status-done" strokeWidth={2.2} />
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-status-done">
          Done
        </span>
      </div>
    );
  }

  // error
  return (
    <div className={common}>
      <AlertTriangle
        className="w-3 h-3 text-status-error"
        strokeWidth={2}
      />
      <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-status-error">
        Error
      </span>
    </div>
  );
}

/* ========================================================================= */
/* QueuedBody — almost empty, just a muted placeholder                        */
/* ========================================================================= */

function QueuedBody() {
  return (
    <div className="flex-1 flex items-center">
      <span className="text-[10px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
        awaiting worker
      </span>
    </div>
  );
}

/* ========================================================================= */
/* RunningBody — cycle counter, delta row, delta_history sparkline            */
/* ========================================================================= */

function RunningBody({
  rpmState,
  nCyclesTarget,
}: {
  rpmState: RpmState;
  nCyclesTarget: number;
}) {
  const cycle = rpmState.current_cycle ?? 0;
  const delta = rpmState.delta;
  // Filter out null/non-finite values (the first cycle's delta is null
  // because the convergence checker has no previous cycle to compare).
  // The Sparkline expects a clean number[] and would otherwise try to
  // render NaN-ish y-coordinates.
  const history = (rpmState.delta_history ?? []).filter(
    (v): v is number => v != null && Number.isFinite(v)
  );

  return (
    <>
      <LabelValueRow
        label="cyc"
        value={
          <>
            <span className="text-text-primary">
              {String(cycle).padStart(2, "0")}
            </span>
            <span className="text-text-muted">/</span>
            <span className="text-text-secondary">
              {String(nCyclesTarget).padStart(2, "0")}
            </span>
          </>
        }
      />
      <LabelValueRow
        label="δ"
        value={
          <span className="text-text-primary">{formatDelta(delta)}</span>
        }
      />
      <div className="mt-0.5 text-accent">
        <Sparkline
          data={history}
          width={160}
          height={20}
          strokeWidth={1.25}
        />
      </div>
    </>
  );
}

/* ========================================================================= */
/* DoneBody — perf summary + muted delta history sparkline                    */
/* ========================================================================= */

function DoneBody({ rpmState }: { rpmState: RpmState }) {
  const perf = rpmState.perf;
  const history = (rpmState.delta_history ?? []).filter(
    (v): v is number => v != null && Number.isFinite(v)
  );

  // Prefer brake power if available, otherwise indicated. This matches what
  // a dyno operator would look at first on the headline row.
  const power =
    perf?.brake_power_hp ??
    perf?.indicated_power_hp ??
    null;
  const torque = perf?.brake_torque_Nm ?? null;
  const ve =
    perf?.volumetric_efficiency_atm != null
      ? perf.volumetric_efficiency_atm * 100
      : null;

  return (
    <>
      {/* Perf summary — three tight pairs separated by middle dots */}
      <div className="flex items-baseline gap-1 text-[11px] font-mono tabular-nums leading-tight">
        <span className="text-text-muted">P</span>
        <span className="text-text-primary">
          {power != null ? power.toFixed(1) : "—"}
        </span>
        <span className="text-text-muted text-[9px]">hp</span>
      </div>
      <div className="flex items-baseline gap-1 text-[11px] font-mono tabular-nums leading-tight">
        <span className="text-text-muted">T</span>
        <span className="text-text-primary">
          {torque != null ? torque.toFixed(1) : "—"}
        </span>
        <span className="text-text-muted text-[9px]">Nm</span>
      </div>
      <div className="flex items-baseline gap-1 text-[11px] font-mono tabular-nums leading-tight">
        <span className="text-text-muted">VE</span>
        <span className="text-text-primary">
          {ve != null ? ve.toFixed(1) : "—"}
        </span>
        <span className="text-text-muted text-[9px]">%</span>
      </div>

      {/* Muted sparkline of the final delta history — shows convergence
          trajectory retrospectively, in the neutral secondary color. */}
      {history.length >= 2 && (
        <div className="mt-auto text-text-secondary">
          <Sparkline
            data={history}
            width={160}
            height={14}
            strokeWidth={1}
          />
        </div>
      )}
    </>
  );
}

/* ========================================================================= */
/* ErrorBody — single-line truncated error; full traceback in title=         */
/* ========================================================================= */

function ErrorBody({ rpmState }: { rpmState: RpmState }) {
  const type = rpmState.error_type ?? "Error";
  const msg = rpmState.error_msg ?? "Unknown error";

  return (
    <div className="flex-1 flex flex-col gap-1 min-h-0">
      <div className="text-[9px] font-mono uppercase tracking-[0.14em] text-status-error/80 leading-none truncate">
        {type}
      </div>
      <div className="text-[10px] font-mono text-status-error leading-snug overflow-hidden text-ellipsis line-clamp-3 break-all">
        {msg}
      </div>
    </div>
  );
}

/* ========================================================================= */
/* LabelValueRow — tiny label in muted, mono value right-aligned             */
/* ========================================================================= */

function LabelValueRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 leading-none">
      <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted">
        {label}
      </span>
      <span className="text-[11px] font-mono font-medium tabular-nums flex items-baseline gap-0.5">
        {value}
      </span>
    </div>
  );
}

/* ========================================================================= */
/* Formatters                                                                 */
/* ========================================================================= */

function formatDelta(delta: number | null | undefined): string {
  if (delta == null || !Number.isFinite(delta)) return "—";
  return delta.toFixed(4);
}

function formatElapsed(elapsed: number | undefined): string {
  if (elapsed == null || !Number.isFinite(elapsed) || elapsed < 0) return "—";
  if (elapsed < 100) return `${elapsed.toFixed(1)}s`;
  return `${elapsed.toFixed(0)}s`;
}
