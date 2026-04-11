import { useState } from "react";
import { useParametricStore } from "../../state/parametricStore";
import { api } from "../../api/client";
import type { LiveParametricStudy } from "../../types/parametric";

export default function ParametricStudyListSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const studies = useParametricStore((s) => s.studies);
  const studiesLoading = useParametricStore((s) => s.studiesLoading);
  const studiesError = useParametricStore((s) => s.studiesError);
  const setCurrent = useParametricStore((s) => s.setCurrent);
  const setStudies = useParametricStore((s) => s.setStudies);
  const setStudiesLoading = useParametricStore((s) => s.setStudiesLoading);
  const setStudiesError = useParametricStore((s) => s.setStudiesError);

  const refresh = async () => {
    setStudiesLoading(true);
    setStudiesError(null);
    try {
      setStudies(await api.listParametricStudies());
    } catch (err) {
      setStudiesError(err instanceof Error ? err.message : String(err));
    } finally {
      setStudiesLoading(false);
    }
  };

  const handleLoad = async (id: string) => {
    try {
      const study = await api.loadParametricStudy(id);
      // The API returns the raw JSON shape — cast carefully.
      setCurrent(study as unknown as LiveParametricStudy);
    } catch (err) {
      console.error(err);
    }
  };

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className="w-8 shrink-0 border-l border-border-default bg-surface hover:bg-surface-raised flex items-center justify-center"
      >
        <span className="[writing-mode:vertical-rl] text-[10px] uppercase tracking-[0.18em] text-text-muted">
          param · studies · {studies.length}
        </span>
      </button>
    );
  }

  return (
    <aside className="w-72 shrink-0 border-l border-border-default bg-surface flex flex-col overflow-hidden font-ui">
      <header className="flex items-center justify-between px-3 py-3 border-b border-border-default">
        <div className="flex items-baseline gap-2">
          <span className="text-[9px] font-mono text-text-muted">[P]</span>
          <span className="text-[11px] uppercase tracking-[0.14em] text-text-muted">
            Param Studies
          </span>
          <span className="text-[10px] font-mono text-text-muted">
            n={studies.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={refresh}
            className="text-[10px] text-text-muted hover:text-accent"
          >
            ↻
          </button>
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className="text-[10px] text-text-muted hover:text-accent"
          >
            ×
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto">
        {studiesLoading && (
          <div className="p-3 text-xs text-text-muted">Loading…</div>
        )}
        {studiesError && (
          <div className="p-3 text-xs text-status-error">{studiesError}</div>
        )}
        {!studiesLoading && studies.length === 0 && !studiesError && (
          <div className="p-3 text-xs text-text-muted">
            No past studies yet.
          </div>
        )}
        {studies.map((s) => (
          <button
            key={s.study_id}
            type="button"
            onClick={() => handleLoad(s.study_id)}
            className="w-full text-left border-b border-border-default/30 px-3 py-2 hover:bg-surface-raised"
          >
            <div className="text-xs font-mono text-text-primary truncate">
              {s.name || s.study_id}
            </div>
            <div className="text-[10px] font-mono text-text-muted mt-0.5">
              {s.parameter_path}
            </div>
            <div className="flex items-center justify-between mt-1 text-[10px] font-mono text-text-muted">
              <span>
                {s.n_values} val · {s.run_count} runs
              </span>
              <span
                className={
                  s.status === "complete"
                    ? "text-status-success"
                    : s.status === "error"
                      ? "text-status-error"
                      : "text-text-muted"
                }
              >
                {s.status}
              </span>
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}
