import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, FolderOpen } from "lucide-react";
import { useSweepStore } from "../state/sweepStore";
import { api } from "../api/client";
import type { SweepSummary } from "../types/events";

/**
 * SweepListSidebar — collapsible right-edge rail listing past sweeps.
 *
 * Visually mirrors the WorkersStrip / SweepCurves chassis (per
 * 2026-04-08-engine-sim-gui-v1-design.md §4/§5): hairline-bordered surface,
 * bracketed ordinal "[S]" header, JetBrains Mono numerics, sharp 4px corners,
 * single-accent discipline (accent reserved for the "RUN" status pip and
 * the load-error message).
 *
 * Two states:
 *   - Collapsed: 32px-wide rail with a `ChevronLeft` button. Click to expand.
 *   - Expanded: ~280px-wide column with a header strip + scrollable list of
 *     past sweeps. Each entry is a clickable row that triggers `api.loadSweep`
 *     after a confirmation dialog.
 *
 * The store's `availableSweeps` is populated by snapshot WS messages from
 * the backend, which means this list refreshes automatically whenever a
 * sweep finishes (the server broadcasts a new snapshot in `sweep_complete`).
 */
export default function SweepListSidebar() {
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const availableSweeps = useSweepStore((s) => s.availableSweeps);

  // Auto-clear the error message after 5s.
  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 5000);
    return () => clearTimeout(t);
  }, [error]);

  // Newest first. Backend already sorts this way, but be defensive.
  const sweeps = [...availableSweeps].sort((a, b) =>
    a.started_at < b.started_at ? 1 : a.started_at > b.started_at ? -1 : 0
  );

  const handleLoad = async (sweep: SweepSummary) => {
    if (
      !window.confirm(
        "Switch to this sweep? The current view will be replaced."
      )
    ) {
      return;
    }
    setLoadingId(sweep.id);
    setError(null);
    try {
      await api.loadSweep(sweep.id);
      // The server's load endpoint validates and reads the file. The
      // store-level snapshot update happens through the WS broadcast.
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sweep");
    } finally {
      setLoadingId(null);
    }
  };

  // ---------- COLLAPSED RAIL --------------------------------------------
  if (!expanded) {
    return (
      <aside
        className="flex flex-col bg-surface border-l border-border-default w-8 transition-all duration-150 ease-out"
        aria-label="Past sweeps (collapsed)"
      >
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="h-8 w-full flex items-center justify-center border-b border-border-default text-text-muted hover:text-text-primary hover:bg-surface-raised transition-colors duration-150"
          title="Expand past sweeps"
          aria-label="Expand past sweeps"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <div className="flex-1 flex items-center justify-center">
          <span
            className="text-[9px] font-mono uppercase tracking-[0.18em] text-text-muted [writing-mode:vertical-rl] rotate-180"
            aria-hidden
          >
            past · sweeps
          </span>
        </div>
        {sweeps.length > 0 && (
          <div className="border-t border-border-default px-1.5 py-2 flex items-center justify-center">
            <span className="text-[9px] font-mono tabular-nums text-text-secondary">
              {String(sweeps.length).padStart(2, "0")}
            </span>
          </div>
        )}
      </aside>
    );
  }

  // ---------- EXPANDED COLUMN -------------------------------------------
  return (
    <aside
      className="flex flex-col bg-surface border-l border-border-default w-72 transition-all duration-150 ease-out font-ui"
      aria-label="Past sweeps"
    >
      {/* Header strip — matches WorkersStrip / ChartPanel header --- */}
      <header className="flex items-stretch border-b border-border-default">
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="h-9 w-8 flex items-center justify-center border-r border-border-default text-text-muted hover:text-text-primary hover:bg-surface-raised transition-colors duration-150"
          title="Collapse past sweeps"
          aria-label="Collapse past sweeps"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>

        <div className="flex-1 flex items-baseline gap-2 px-3 min-w-0 self-center">
          <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
            [S]
          </span>
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
            Past Sweeps
          </h3>
        </div>

        <div className="flex items-center gap-1 px-3 border-l border-border-default self-stretch">
          <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
            n
          </span>
          <span className="text-[9px] font-mono text-text-muted leading-none">
            =
          </span>
          <span className="text-[9px] font-mono tabular-nums text-text-secondary leading-none">
            {String(sweeps.length).padStart(2, "0")}
          </span>
        </div>
      </header>

      {/* Inline error banner ------------------------------------- */}
      {error && (
        <div className="px-3 py-2 border-b border-border-default bg-status-error/10">
          <div className="text-[9px] font-mono uppercase tracking-[0.14em] text-status-error leading-tight">
            Load Failed
          </div>
          <div className="text-[10px] font-mono text-status-error/90 mt-0.5 break-words">
            {error}
          </div>
        </div>
      )}

      {/* List body ----------------------------------------------- */}
      <div className="flex-1 overflow-auto">
        {sweeps.length === 0 ? (
          <div className="flex items-center justify-center py-12 px-4">
            <div className="flex flex-col items-center gap-2 text-text-muted">
              <FolderOpen className="w-4 h-4 opacity-50" />
              <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-center">
                No past sweeps yet
              </span>
            </div>
          </div>
        ) : (
          sweeps.map((sweep, idx) => (
            <SweepEntry
              key={sweep.id}
              sweep={sweep}
              ordinal={idx + 1}
              isFirst={idx === 0}
              isLoading={loadingId === sweep.id}
              onClick={() => handleLoad(sweep)}
            />
          ))
        )}
      </div>
    </aside>
  );
}

// ----------------------- Sub-components ----------------------------------

interface SweepEntryProps {
  sweep: SweepSummary;
  ordinal: number;
  isFirst: boolean;
  isLoading: boolean;
  onClick: () => void;
}

function SweepEntry({
  sweep,
  ordinal,
  isFirst,
  isLoading,
  onClick,
}: SweepEntryProps) {
  const ts = formatTimestamp(sweep.started_at);
  const dur = formatDuration(sweep.duration_seconds);
  const rpmRange = `${formatRpm(sweep.rpm_range[0])}–${formatRpm(
    sweep.rpm_range[1]
  )}`;

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isLoading}
      className={`w-full text-left px-3 py-2.5 hover:bg-surface-raised disabled:opacity-50 transition-colors duration-150 ${
        isFirst ? "" : "border-t border-border-default/60"
      }`}
    >
      <div className="flex items-baseline gap-2">
        <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
          [{String(ordinal).padStart(2, "0")}]
        </span>
        <span className="text-[10px] font-mono tabular-nums text-text-primary leading-none flex-1 truncate">
          {ts}
        </span>
        {isLoading && (
          <span className="text-[8px] font-mono uppercase tracking-[0.18em] text-accent leading-none">
            loading
          </span>
        )}
      </div>

      <div className="flex items-baseline gap-2 mt-1.5 ml-[1.85rem]">
        <span className="text-[10px] font-mono tabular-nums text-text-secondary leading-none">
          {rpmRange}
        </span>
        <span className="text-[9px] font-mono text-text-muted leading-none">
          rpm
        </span>
      </div>

      <div className="flex items-baseline gap-3 mt-1 ml-[1.85rem]">
        <span className="text-[9px] font-mono tabular-nums text-text-muted leading-none">
          {dur}
        </span>
        <span className="text-[9px] font-mono tabular-nums text-text-muted leading-none">
          {sweep.n_rpm_points} pts
        </span>
      </div>
    </button>
  );
}

// ----------------------- formatters ---------------------------------------

function formatTimestamp(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mi = String(d.getMinutes()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
  } catch {
    return iso;
  }
}

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return `${m}m ${String(rem).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return `${h}h ${String(remM).padStart(2, "0")}m`;
}

function formatRpm(rpm: number): string {
  return String(Math.round(rpm));
}
