import { useEffect, useState } from "react";
import TopBar from "./components/TopBar";
import TabBar from "./components/TabBar";
import RunSweepDialog from "./components/RunSweepDialog";
import SimulationView from "./components/SimulationView";
import SweepListSidebar from "./components/SweepListSidebar";
import { makeEventSocket } from "./api/websocket";
import { applyServerMessage } from "./state/eventReducer";
import { useConfigStore } from "./state/configStore";

export default function App() {
  const [runSweepDialogOpen, setRunSweepDialogOpen] = useState(false);
  const activeTab = useConfigStore((s) => s.activeTab);

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
      <TabBar />

      <div className="flex-1 flex overflow-hidden">
        {activeTab === "simulation" ? (
          <SimulationView />
        ) : (
          <ConfigPlaceholder />
        )}
        <SweepListSidebar />
      </div>

      <RunSweepDialog
        isOpen={runSweepDialogOpen}
        onClose={() => setRunSweepDialogOpen(false)}
      />
    </div>
  );
}

/**
 * Stub Config view — replaced in the next phase by a real ConfigView
 * with sticky header and accordion sections. Lives inline here so the
 * tab navigation is fully wired without depending on a file we
 * haven't created yet.
 */
function ConfigPlaceholder() {
  return (
    <main className="flex-1 overflow-auto p-6 flex items-center justify-center text-text-muted text-xs uppercase tracking-[0.2em]">
      Config tab — coming up next
    </main>
  );
}
