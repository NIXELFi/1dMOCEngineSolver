import { Play, Square, FolderOpen } from "lucide-react";
import { useSweepStore } from "../state/sweepStore";
import { api } from "../api/client";
import type { SweepSnapshot } from "../types/events";

interface TopBarProps {
  onRunSweepClick: () => void;
  onLoadClick: () => void;
}

/**
 * TopBar — persistent toolbar for the Mission Control layout.
 *
 * Visual direction (per 2026-04-08-engine-sim-gui-v1-design.md §5):
 * a technical instrument chassis, not a SaaS header. Sharp 1px hairlines,
 * 4px corner radius max, the single accent color reserved for the primary
 * action and the "running" indicator dot, JetBrains Mono for every numeric.
 */
export default function TopBar({ onRunSweepClick, onLoadClick }: TopBarProps) {
  const sweep = useSweepStore((s) => s.sweep);
  const connected = useSweepStore((s) => s.connected);
  const isRunning = sweep?.status === "running";
  const hasSweep = sweep !== null;

  const handleStop = async () => {
    if (!window.confirm("Stop the running sweep?")) return;
    try {
      await api.stopSweep();
    } catch (e) {
      console.error("Failed to stop sweep", e);
    }
  };

  return (
    <header
      className="h-14 flex items-stretch bg-surface border-b border-border-default select-none font-ui"
      role="banner"
    >
      {/* Brand slot ------------------------------------------------------ */}
      <div className="flex items-center gap-2.5 px-4 border-r border-border-default">
        <span className="text-[15px] font-semibold tracking-[0.18em] text-text-primary uppercase leading-none">
          Engine<span className="text-text-muted">&nbsp;</span>Sim
        </span>
        <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest border border-border-default px-1 py-[1px] leading-none">
          v1
        </span>
      </div>

      {/* Primary action cluster ------------------------------------------ */}
      <div className="flex items-center gap-1.5 px-3 border-r border-border-default">
        <button
          type="button"
          onClick={onRunSweepClick}
          disabled={isRunning}
          className={[
            "group inline-flex items-center gap-1.5 h-8 pl-2 pr-3 rounded",
            "text-[11px] font-semibold uppercase tracking-[0.14em] leading-none",
            "transition-colors duration-150 ease-out",
            isRunning
              ? "bg-accent/20 text-accent/50 cursor-not-allowed"
              : "bg-accent text-bg hover:bg-[#FF6A3D] active:bg-accent-dim",
          ].join(" ")}
          aria-label="Run sweep"
        >
          <Play className="w-3.5 h-3.5" strokeWidth={2} fill="currentColor" />
          <span>Run Sweep</span>
        </button>

        <button
          type="button"
          onClick={handleStop}
          disabled={!isRunning}
          className={[
            "inline-flex items-center gap-1.5 h-8 pl-2 pr-3 rounded border",
            "text-[11px] font-medium uppercase tracking-[0.14em] leading-none",
            "transition-colors duration-150 ease-out",
            !isRunning
              ? "border-border-default text-text-muted cursor-not-allowed"
              : "border-border-emphasis text-text-primary hover:bg-surface-raised hover:border-text-secondary",
          ].join(" ")}
          aria-label="Stop sweep"
        >
          <Square className="w-3.5 h-3.5" strokeWidth={1.8} />
          <span>Stop</span>
        </button>

        <button
          type="button"
          onClick={onLoadClick}
          className={[
            "inline-flex items-center gap-1.5 h-8 pl-2 pr-2.5 rounded border border-border-default",
            "text-[11px] font-medium uppercase tracking-[0.14em] leading-none text-text-secondary",
            "transition-colors duration-150 ease-out",
            "hover:bg-surface-raised hover:border-border-emphasis hover:text-text-primary",
          ].join(" ")}
          aria-label="Load past sweep"
        >
          <FolderOpen className="w-3.5 h-3.5" strokeWidth={1.8} />
          <span>Load</span>
          <span className="text-text-muted ml-0.5" aria-hidden>
            &#9662;
          </span>
        </button>
      </div>

      {/* Spacer ---------------------------------------------------------- */}
      <div className="flex-1" />

      {/* Status readout -------------------------------------------------- */}
      <div className="flex items-center border-l border-border-default">
        <StatusReadout sweep={sweep} />
      </div>

      {/* Connection pip -------------------------------------------------- */}
      <div
        className="flex items-center gap-2 px-4 border-l border-border-default"
        title={connected ? "WebSocket connected" : "WebSocket disconnected"}
      >
        <span
          className={[
            "inline-block w-1.5 h-1.5 rounded-full",
            connected ? "bg-status-done" : "bg-status-error",
          ].join(" ")}
          aria-hidden
        />
        <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-text-muted leading-none">
          {connected ? "LIVE" : "OFF"}
        </span>
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------------- */
/* Status readout                                                            */
/* ------------------------------------------------------------------------- */

function StatusReadout({ sweep }: { sweep: SweepSnapshot | null }) {
  if (sweep === null) {
    return (
      <div className="flex items-center gap-2 px-4 h-full">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted" aria-hidden />
        <span className="text-xs uppercase tracking-wider text-text-secondary leading-none">
          Idle
        </span>
      </div>
    );
  }

  const doneCount = Object.values(sweep.rpms).filter((r) => r.status === "done")
    .length;
  const totalCount = sweep.rpm_points.length;
  const elapsed = sweep.elapsed_seconds ?? 0;

  if (sweep.status === "running") {
    const eta =
      doneCount > 0 ? (elapsed / doneCount) * (totalCount - doneCount) : null;

    return (
      <div className="flex items-stretch h-full">
        {/* label */}
        <div className="flex items-center gap-2 px-4 border-r border-border-default">
          <span className="relative inline-flex w-1.5 h-1.5" aria-hidden>
            <span className="absolute inset-0 rounded-full bg-accent animate-ping opacity-60" />
            <span className="relative inline-block w-1.5 h-1.5 rounded-full bg-accent" />
          </span>
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent leading-none">
            Running
          </span>
        </div>

        {/* RPMs done */}
        <StatField label="RPMs">
          <span className="text-text-primary">
            {doneCount.toString().padStart(String(totalCount).length, "0")}
          </span>
          <span className="text-text-muted">/</span>
          <span className="text-text-secondary">{totalCount}</span>
        </StatField>

        {/* Elapsed */}
        <StatField label="Elapsed">
          <span className="text-text-primary">{formatDuration(elapsed)}</span>
        </StatField>

        {/* ETA */}
        <StatField label="ETA">
          <span className="text-text-primary">
            {eta !== null ? `~${formatDuration(eta)}` : "—"}
          </span>
        </StatField>
      </div>
    );
  }

  if (sweep.status === "complete") {
    return (
      <div className="flex items-stretch h-full">
        <div className="flex items-center gap-2 px-4 border-r border-border-default">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-status-done" aria-hidden />
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-status-done leading-none">
            Complete
          </span>
        </div>
        <StatField label="RPMs">
          <span className="text-text-primary">{doneCount}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-secondary">{totalCount}</span>
        </StatField>
        <StatField label="Duration">
          <span className="text-text-primary">{formatDuration(elapsed)}</span>
        </StatField>
      </div>
    );
  }

  if (sweep.status === "error") {
    return (
      <div className="flex items-stretch h-full">
        <div className="flex items-center gap-2 px-4 border-r border-border-default">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-status-error" aria-hidden />
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-status-error leading-none">
            Error
          </span>
        </div>
        <StatField label="Duration">
          <span className="text-status-error">{formatDuration(elapsed)}</span>
        </StatField>
      </div>
    );
  }

  if (sweep.status === "stopped") {
    return (
      <div className="flex items-stretch h-full">
        <div className="flex items-center gap-2 px-4 border-r border-border-default">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted" aria-hidden />
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-text-muted leading-none">
            Stopped
          </span>
        </div>
        <StatField label="RPMs">
          <span className="text-text-secondary">{doneCount}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-muted">{totalCount}</span>
        </StatField>
        <StatField label="Duration">
          <span className="text-text-secondary">{formatDuration(elapsed)}</span>
        </StatField>
      </div>
    );
  }

  // idle / unknown fallback
  return (
    <div className="flex items-center gap-2 px-4 h-full">
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted" aria-hidden />
      <span className="text-xs uppercase tracking-wider text-text-secondary leading-none">
        Idle
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* StatField — a vertically stacked label/value cell with right hairline     */
/* ------------------------------------------------------------------------- */

function StatField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col justify-center gap-0.5 px-4 border-r border-border-default min-w-[84px]">
      <span className="text-[9px] font-medium uppercase tracking-[0.18em] text-text-muted leading-none">
        {label}
      </span>
      <span className="text-[13px] font-mono font-medium tabular-nums leading-none flex items-baseline gap-0.5">
        {children}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* Duration formatter                                                        */
/* Format: "27s", "1m 12s", "1h 04m"                                         */
/* ------------------------------------------------------------------------- */

function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "—";
  const s = Math.round(totalSeconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const remS = s % 60;
  if (m < 60) {
    return remS === 0 ? `${m}m` : `${m}m ${String(remS).padStart(2, "0")}s`;
  }
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return `${h}h ${String(remM).padStart(2, "0")}m`;
}
