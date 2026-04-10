import { useEffect } from "react";
import { useDynoStore } from "../state/dynoStore";
import { useSweepStore } from "../state/sweepStore";
import GaugePanel from "./dyno/GaugePanel";
import TransportBar from "./dyno/TransportBar";
import ProgressiveCharts from "./dyno/ProgressiveCharts";

/**
 * DynoView — the "Dyno" tab: animated playback of a completed sweep.
 *
 * Reads from sweepStore, loads data into dynoStore on mount and when
 * the sweep changes. Sub-components read from dynoStore.
 */
export default function DynoView() {
  const sweep = useSweepStore((s) => s.sweep);
  const loadSweepData = useDynoStore((s) => s.loadSweepData);
  const sweepPoints = useDynoStore((s) => s.sweepPoints);

  // Load/reload sweep data when the sweep changes
  useEffect(() => {
    loadSweepData();
  }, [sweep, loadSweepData]);

  // Pause playback when leaving the Dyno tab
  useEffect(() => {
    return () => {
      useDynoStore.getState().pause();
    };
  }, []);

  const hasSweep = sweepPoints.length > 0;

  return (
    <main className="flex-1 overflow-auto flex flex-col">
      {hasSweep ? (
        <>
          <div className="p-3 pb-0">
            <GaugePanel />
          </div>
          <TransportBar />
          <div className="flex-1 p-3 overflow-auto">
            <ProgressiveCharts />
          </div>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="flex items-center gap-2">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted"
                aria-hidden
              />
              <span className="text-[10px] font-ui font-semibold uppercase tracking-[0.22em] text-text-muted leading-none">
                No Sweep Data
              </span>
            </div>
            <div className="w-16 h-px bg-border-default" aria-hidden />
            <p className="text-[11px] font-mono text-text-secondary leading-none text-center">
              Load a sweep from the Simulation tab to use Dyno playback
            </p>
          </div>
        </div>
      )}
    </main>
  );
}
