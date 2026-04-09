import { useEffect, useState } from "react";
import TopBar from "./components/TopBar";
import RunSweepDialog from "./components/RunSweepDialog";
import SweepCurves from "./components/SweepCurves";
import WorkersStrip from "./components/WorkersStrip";
import RpmDetail from "./components/RpmDetail";
import SweepListSidebar from "./components/SweepListSidebar";
import { makeEventSocket } from "./api/websocket";
import { applyServerMessage } from "./state/eventReducer";

export default function App() {
  const [runSweepDialogOpen, setRunSweepDialogOpen] = useState(false);

  useEffect(() => {
    const sock = makeEventSocket();
    const unsub = sock.addListener(applyServerMessage);
    sock.connect();
    return () => {
      unsub();
      sock.close();
    };
  }, []);

  return (
    <div className="min-h-screen h-screen flex flex-col bg-bg text-text-primary font-ui">
      <TopBar
        onRunSweepClick={() => setRunSweepDialogOpen(true)}
        onLoadClick={() => {
          /* SweepListSidebar has its own toggle on the right edge */
        }}
      />

      <div className="flex-1 flex overflow-hidden">
        <main className="flex-1 overflow-auto p-3 flex flex-col gap-3">
          <SweepCurves />
          <WorkersStrip />
          <RpmDetail />
        </main>
        <SweepListSidebar />
      </div>

      <RunSweepDialog
        isOpen={runSweepDialogOpen}
        onClose={() => setRunSweepDialogOpen(false)}
      />
    </div>
  );
}
