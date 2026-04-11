import { useEffect, useState } from "react";
import TopBar from "./components/TopBar";
import TabBar from "./components/TabBar";
import RunSweepDialog from "./components/RunSweepDialog";
import SimulationView from "./components/SimulationView";
import ConfigView from "./components/ConfigView";
import DynoView from "./components/DynoView";
import ParametricView from "./components/parametric/ParametricView";
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
        {activeTab === "simulation" && <SimulationView />}
        {activeTab === "config" && <ConfigView />}
        {activeTab === "dyno" && <DynoView />}
        {activeTab === "parametric" && <ParametricView />}
        {activeTab !== "parametric" && <SweepListSidebar />}
      </div>

      <RunSweepDialog
        isOpen={runSweepDialogOpen}
        onClose={() => setRunSweepDialogOpen(false)}
      />
    </div>
  );
}
