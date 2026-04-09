import { useConfigStore, type ActiveTab } from "../state/configStore";

interface TabDef {
  id: ActiveTab;
  label: string;
  index: string;
}

const TABS: TabDef[] = [
  { id: "simulation", label: "Simulation", index: "01" },
  { id: "config", label: "Config", index: "02" },
];

/**
 * Tab strip pinned below the TopBar. Two tabs in v2: Simulation (today's
 * mission control view) and Config (the new editor). Visual treatment
 * matches TopBar — sharp 1px hairlines, [NN] index marks, accent for the
 * active tab indicator.
 */
export default function TabBar() {
  const activeTab = useConfigStore((s) => s.activeTab);
  const setActiveTab = useConfigStore((s) => s.setActiveTab);

  return (
    <nav
      className="h-10 flex items-stretch bg-surface border-b border-border-default select-none font-ui"
      role="tablist"
      aria-label="Workspace tabs"
    >
      {TABS.map((tab) => {
        const active = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => setActiveTab(tab.id)}
            className={[
              "group relative inline-flex items-center gap-2 px-5 border-r border-border-default",
              "text-[11px] font-medium uppercase tracking-[0.18em] leading-none",
              "transition-colors duration-150 ease-out",
              active
                ? "bg-bg text-text-primary"
                : "text-text-muted hover:text-text-primary hover:bg-surface-raised",
            ].join(" ")}
          >
            <span className="text-[9px] font-mono text-text-muted">
              [{tab.index}]
            </span>
            <span>{tab.label}</span>
            {active && (
              <span
                className="absolute left-0 right-0 bottom-0 h-px bg-accent"
                aria-hidden
              />
            )}
          </button>
        );
      })}
      <div className="flex-1 border-r border-border-default" />
    </nav>
  );
}
