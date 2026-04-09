import SweepCurves from "./SweepCurves";
import WorkersStrip from "./WorkersStrip";
import RpmDetail from "./RpmDetail";

/**
 * The "live mission control" view: sweep curves, worker strip,
 * per-RPM detail panel. Lifted out of App.tsx so the new tab bar
 * can swap it with the Config view.
 */
export default function SimulationView() {
  return (
    <main className="flex-1 overflow-auto p-3 flex flex-col gap-3">
      <SweepCurves />
      <WorkersStrip />
      <RpmDetail />
    </main>
  );
}
