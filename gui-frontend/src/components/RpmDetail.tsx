import { useEffect, useState } from "react";
import { useSweepStore } from "../state/sweepStore";
import { api } from "../api/client";
import CylinderTraces from "./CylinderTraces";
import PvDiagrams from "./PvDiagrams";
import PipeTraces from "./PipeTraces";
import PlenumPanel from "./PlenumPanel";
import RestrictorPanel from "./RestrictorPanel";
import CycleConvergencePanel from "./CycleConvergencePanel";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

/**
 * Shape of the per-RPM simulation payload returned by
 * `GET /api/sweeps/current/results/{rpm}` — mirrors
 * `engine_simulator/gui/persistence.py:_serialize_results`.
 *
 * Exported so sibling tab components (CylinderTraces, PvDiagrams, and the
 * upcoming J6 tabs) can type-check their `results` prop against the same
 * canonical shape without reaching into `RpmDetail.tsx` for a re-export.
 */
export interface SimulationResultsData {
  theta_history: number[];
  dt_history: number[];
  plenum_pressure: number[];       // Pa
  plenum_temperature: number[];    // K
  restrictor_mdot: number[];       // kg/s
  restrictor_choked: boolean[];
  cylinder_data: Record<
    string,
    {
      theta: number[];       // crank angle deg, MAY exceed 720
      pressure: number[];    // Pa
      temperature: number[]; // K
      velocity: number[];    // m/s
      density: number[];     // kg/m^3
    }
  >;
  pipe_probes: Record<
    string,
    {
      theta: number[];
      pressure: number[];
      temperature: number[];
      velocity: number[];
      density: number[];
    }
  >;
}

/* ========================================================================= */
/* Tab identifiers                                                            */
/* ========================================================================= */

type TabId =
  | "cylinders"
  | "pv"
  | "pipes"
  | "plenum"
  | "restrictor"
  | "convergence";

interface TabDef {
  id: TabId;
  label: string;
}

const TABS: TabDef[] = [
  { id: "cylinders", label: "Cylinders" },
  { id: "pv", label: "P-V" },
  { id: "pipes", label: "Pipes" },
  { id: "plenum", label: "Plenum" },
  { id: "restrictor", label: "Restrictor" },
  { id: "convergence", label: "Convergence" },
];

/* ========================================================================= */
/* RpmDetail — the bottom detail panel of the Mission Control layout         */
/* ========================================================================= */

/**
 * RpmDetail — deep-inspection panel for one selected RPM.
 *
 * Visual language matches the rest of the Mission Control layout (per
 * `2026-04-08-engine-sim-gui-v1-design.md` §4/§5): a hairline-bordered
 * `bg-surface` section with a header strip carrying the bracketed [D]
 * ordinal, the big RPM readout, a native dropdown to jump between RPMs,
 * and a row of tabs on the right. The header chrome is the same grammar
 * used by `ChartPanel` in SweepCurves and by WorkersStrip — same padding,
 * same hairline separators, same `text-[10px] uppercase tracking` labels.
 *
 * Data lifecycle:
 *   1. When `selectedRpm` (or the active `sweep_id`) changes, the panel
 *      checks `resultsCache[${sweepId}:${rpm}]` in the Zustand store.
 *   2. If hit, the payload renders immediately with no network call.
 *   3. If miss, the panel fetches `api.getCurrentResults(rpm)`, caches
 *      the response, and renders. Stale responses from superseded
 *      selections are discarded via an `isMounted` guard.
 *   4. 404 (or any fetch error) collapses to a neutral
 *      "No recorded data" empty state — recorded data is optional and
 *      may not exist for every RPM (e.g. live-running ones).
 */
export default function RpmDetail() {
  const sweep = useSweepStore((s) => s.sweep);
  const selectedRpm = useSweepStore((s) => s.selectedRpm);
  const setSelectedRpm = useSweepStore((s) => s.setSelectedRpm);
  const resultsCache = useSweepStore((s) => s.resultsCache);
  const cacheResults = useSweepStore((s) => s.cacheResults);

  const [activeTab, setActiveTab] = useState<TabId>("cylinders");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sweepId = sweep?.sweep_id ?? null;
  const cacheKey =
    sweepId != null && selectedRpm != null
      ? `${sweepId}:${selectedRpm}`
      : null;
  const cached = cacheKey ? resultsCache[cacheKey] : undefined;
  const results = (cached ?? null) as SimulationResultsData | null;

  /* -- Fetch on selection change, skip if cached ------------------------- */
  useEffect(() => {
    if (selectedRpm == null || sweepId == null) {
      setLoading(false);
      setError(null);
      return;
    }

    // Cache hit — nothing to do.
    if (resultsCache[`${sweepId}:${selectedRpm}`] !== undefined) {
      setLoading(false);
      setError(null);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    api
      .getCurrentResults(selectedRpm)
      .then((data) => {
        if (!isMounted) return;
        cacheResults(sweepId, selectedRpm, data);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (!isMounted) return;
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sweepId, selectedRpm]);

  /* -- Build the dropdown options from sweep.rpm_points ------------------ */
  const rpmPoints = sweep?.rpm_points ?? [];

  /* -- Render the body based on state ------------------------------------ */
  const body = (() => {
    if (selectedRpm == null) {
      return (
        <EmptyMessage>
          Select an RPM from the workers strip or click a point on the curves
          above
        </EmptyMessage>
      );
    }

    // Convergence tab is special: it reads from the live event stream
    // (delta_history / p_ivc_history on the RpmState in the store) and
    // does NOT need the heavy SimulationResults payload. Render it ahead
    // of the loading / no-results guards so it works even while the
    // cylinder/pipe fetch is still in flight or unavailable.
    if (activeTab === "convergence") {
      return <CycleConvergencePanel />;
    }

    if (loading) {
      return (
        <div className="flex items-center justify-center gap-2 py-10">
          <span className="relative inline-flex w-1.5 h-1.5" aria-hidden>
            <span className="absolute inset-0 rounded-full bg-accent animate-ping opacity-60" />
            <span className="relative inline-block w-1.5 h-1.5 rounded-full bg-accent" />
          </span>
          <span className="text-[10px] font-mono font-semibold uppercase tracking-[0.22em] text-text-muted leading-none">
            Loading…
          </span>
        </div>
      );
    }

    if (error || !results) {
      return <EmptyMessage>No recorded data for this RPM</EmptyMessage>;
    }

    switch (activeTab) {
      case "cylinders":
        return <CylinderTraces results={results} />;
      case "pv":
        return <PvDiagrams results={results} />;
      case "pipes":
        return <PipeTraces results={results} />;
      case "plenum":
        return <PlenumPanel results={results} />;
      case "restrictor":
        return <RestrictorPanel results={results} />;
      default:
        return <EmptyMessage>Unknown tab</EmptyMessage>;
    }
  })();

  /* -- Render ------------------------------------------------------------- */
  return (
    <section
      className="flex flex-col bg-surface border border-border-default rounded font-ui"
      aria-label="RPM detail"
    >
      {/* =============================================================== */}
      {/* Header strip                                                    */}
      {/* =============================================================== */}
      <header className="flex items-stretch border-b border-border-default">
        {/* ---- Left cluster: [D] ordinal + big RPM number + dropdown --- */}
        <div className="flex items-center gap-3 px-3 py-2 min-w-0">
          {/* Bracketed instrument ordinal */}
          <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums self-start pt-1">
            [D]
          </span>

          {/* Big RPM number */}
          <div className="flex items-baseline gap-1.5 leading-none">
            <span className="text-2xl font-mono font-medium tabular-nums text-text-primary leading-none">
              {selectedRpm != null ? selectedRpm.toString() : "—"}
            </span>
            <span className="text-[9px] font-mono font-semibold uppercase tracking-[0.18em] text-text-muted leading-none">
              RPM
            </span>
          </div>

          {/* Dropdown — only render when we have a sweep + rpm list */}
          {rpmPoints.length > 0 && (
            <div className="relative">
              <select
                value={selectedRpm ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "") return;
                  setSelectedRpm(Number(v));
                }}
                aria-label="Jump to RPM"
                className={[
                  "appearance-none cursor-pointer",
                  "h-7 pl-2 pr-6 rounded",
                  "bg-surface-raised border border-border-default",
                  "text-[10px] font-mono font-medium uppercase tracking-[0.14em] tabular-nums",
                  "text-text-secondary leading-none",
                  "transition-colors duration-150 ease-out",
                  "hover:border-border-emphasis hover:text-text-primary",
                  "focus:outline-none focus:border-border-emphasis focus:text-text-primary",
                ].join(" ")}
              >
                {selectedRpm != null &&
                  !rpmPoints.includes(selectedRpm) && (
                    <option value={selectedRpm}>
                      {selectedRpm.toString()}
                    </option>
                  )}
                {rpmPoints.map((rpm) => (
                  <option key={rpm} value={rpm}>
                    {rpm.toString()}
                  </option>
                ))}
              </select>
              {/* Caret indicator — absolutely positioned so native select's
                  browser caret is hidden via appearance-none and we draw our
                  own in the design's tone. */}
              <span
                className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-text-muted text-[10px] leading-none"
                aria-hidden
              >
                &#9662;
              </span>
            </div>
          )}
        </div>

        {/* ---- Spacer ------------------------------------------------- */}
        <div className="flex-1" />

        {/* ---- Right cluster: tab row --------------------------------- */}
        <nav
          className="flex items-stretch border-l border-border-default"
          role="tablist"
          aria-label="Detail view tabs"
        >
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveTab(tab.id)}
                className={[
                  "relative flex items-center px-3",
                  "text-[10px] font-semibold uppercase tracking-[0.14em] leading-none",
                  "border-l border-border-default first:border-l-0",
                  "transition-colors duration-150 ease-out",
                  isActive
                    ? "text-text-primary bg-surface-raised/40"
                    : "text-text-muted hover:text-text-secondary hover:bg-surface-raised/30",
                ].join(" ")}
              >
                {tab.label}
                {isActive && (
                  <span
                    className="absolute left-0 right-0 bottom-[-1px] h-[2px] bg-accent"
                    aria-hidden
                  />
                )}
              </button>
            );
          })}
        </nav>
      </header>

      {/* =============================================================== */}
      {/* Body                                                            */}
      {/* =============================================================== */}
      <div className="p-3">{body}</div>
    </section>
  );
}

/* ========================================================================= */
/* EmptyMessage — the neutral centered placeholder used by several states    */
/* ========================================================================= */

function EmptyMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-10 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        {/* Tiny muted dot + hairline divider — keeps the empty state from
            feeling like a dead zone while staying well inside the
            instrument-panel tone. */}
        <span
          className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted"
          aria-hidden
        />
        <div className="w-16 h-px bg-border-default" aria-hidden />
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-text-muted leading-none text-center max-w-[420px]">
          {children}
        </p>
      </div>
    </div>
  );
}
