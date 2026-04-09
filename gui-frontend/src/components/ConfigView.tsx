import { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  useConfigStore,
  selectIsDirty,
} from "../state/configStore";
import IdentitySection from "./config/IdentitySection";
import CylinderSection from "./config/CylinderSection";

const PREFERRED_DEFAULT = "cbr600rr.json";

/**
 * Top-level Config tab. Sticky header with file dropdown + dirty dot
 * + Save/Save As/Revert. Body is a stack of accordion sections (added
 * in later tasks).
 */
export default function ConfigView() {
  const available = useConfigStore((s) => s.available);
  const activeName = useConfigStore((s) => s.activeName);
  const draft = useConfigStore((s) => s.draft);
  const loading = useConfigStore((s) => s.loading);
  const saving = useConfigStore((s) => s.saving);
  const loadError = useConfigStore((s) => s.loadError);
  const saveError = useConfigStore((s) => s.saveError);
  const saveFlash = useConfigStore((s) => s.saveFlash);
  const isDirty = useConfigStore(selectIsDirty);

  const setAvailable = useConfigStore((s) => s.setAvailable);
  const setActive = useConfigStore((s) => s.setActive);
  const setLoading = useConfigStore((s) => s.setLoading);
  const setLoadError = useConfigStore((s) => s.setLoadError);
  const setSaving = useConfigStore((s) => s.setSaving);
  const setSaveError = useConfigStore((s) => s.setSaveError);
  const setFieldErrors = useConfigStore((s) => s.setFieldErrors);
  const flashSaved = useConfigStore((s) => s.flashSaved);
  const revert = useConfigStore((s) => s.revert);

  const [saveAsMode, setSaveAsMode] = useState(false);
  const [saveAsName, setSaveAsName] = useState("");
  const [saveAsError, setSaveAsError] = useState<string | null>(null);

  /* ---------------- Load on first mount ---------------- */
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    api
      .listConfigs()
      .then(async (list) => {
        if (cancelled) return;
        setAvailable(list);
        if (activeName) return; // already loaded in a previous mount
        const preferred =
          list.find((c) => c.name === PREFERRED_DEFAULT) ?? list[0];
        if (!preferred) {
          setLoadError("No configs found in engine_simulator/config/");
          return;
        }
        const payload = await api.getConfig(preferred.name);
        if (cancelled) return;
        setActive(preferred.name, payload);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------------- Switching active config ------------ */
  const handleSelectFile = async (name: string) => {
    if (name === activeName) return;
    if (
      isDirty &&
      !window.confirm(
        "Discard unsaved changes to the current config?",
      )
    ) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const payload = await api.getConfig(name);
      setActive(name, payload);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  /* ---------------- Save in place ----------------------- */
  const handleSave = async () => {
    if (!activeName || draft === null || saving) return;
    setSaving(true);
    setSaveError(null);
    setFieldErrors({});
    try {
      const result = await api.saveConfig(activeName, draft);
      setActive(activeName, result);
      flashSaved();
    } catch (e: unknown) {
      const err = e as Error & {
        fieldErrors?: Record<string, string>;
        status?: number;
      };
      if (err.status === 422 && err.fieldErrors) {
        setFieldErrors(err.fieldErrors);
        setSaveError("Validation failed — see highlighted fields.");
      } else {
        setSaveError(err.message ?? String(e));
      }
    } finally {
      setSaving(false);
    }
  };

  /* ---------------- Save As --------------------------- */
  const beginSaveAs = () => {
    setSaveAsMode(true);
    setSaveAsName("");
    setSaveAsError(null);
  };

  const cancelSaveAs = () => {
    setSaveAsMode(false);
    setSaveAsName("");
    setSaveAsError(null);
  };

  const handleSaveAs = async () => {
    if (draft === null) return;
    let name = saveAsName.trim();
    if (!name) {
      setSaveAsError("Enter a filename");
      return;
    }
    if (!name.endsWith(".json")) name += ".json";
    if (!/^[A-Za-z0-9_\-]+\.json$/.test(name)) {
      setSaveAsError("Letters, digits, _ and - only");
      return;
    }
    setSaving(true);
    setSaveAsError(null);
    setFieldErrors({});
    try {
      const result = await api.saveConfigAs(name, draft);
      const list = await api.listConfigs();
      setAvailable(list);
      setActive(name, result);
      flashSaved();
      setSaveAsMode(false);
      setSaveAsName("");
    } catch (e: unknown) {
      const err = e as Error & {
        fieldErrors?: Record<string, string>;
        status?: number;
      };
      if (err.status === 422 && err.fieldErrors) {
        setFieldErrors(err.fieldErrors);
        setSaveAsError("Validation failed");
      } else {
        setSaveAsError(err.message ?? String(e));
      }
    } finally {
      setSaving(false);
    }
  };

  /* ---------------- Render ---------------------------- */

  if (loading && draft === null) {
    return (
      <main className="flex-1 overflow-auto flex items-center justify-center text-text-muted text-xs uppercase tracking-[0.2em]">
        Loading config…
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="flex-1 overflow-auto flex items-center justify-center text-status-error text-xs">
        {loadError}
      </main>
    );
  }

  if (draft === null || activeName === null) {
    return (
      <main className="flex-1 overflow-auto flex items-center justify-center text-text-muted text-xs">
        No config loaded.
      </main>
    );
  }

  const flashedRecently =
    saveFlash !== null && Date.now() - saveFlash < 3000;

  return (
    <main className="flex-1 overflow-auto bg-bg flex flex-col">
      {/* Sticky header ---------------------------------------------- */}
      <header className="sticky top-0 z-10 bg-surface border-b border-border-default flex items-stretch">
        <div className="flex items-center gap-3 px-4 py-3 border-r border-border-default">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-accent"
            aria-hidden
          />
          <h2 className="text-[12px] font-semibold uppercase tracking-[0.2em] text-text-primary leading-none">
            Engine Config
          </h2>
          <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-text-muted leading-none border border-border-default px-1 py-[1px]">
            Edit
          </span>
        </div>

        {/* File picker / Save As inline prompt */}
        {saveAsMode ? (
          <div className="flex-1 flex items-center gap-2 px-3">
            <span className="text-[10px] font-mono uppercase tracking-widest text-text-muted">
              Save As
            </span>
            <input
              type="text"
              value={saveAsName}
              autoFocus
              placeholder="filename.json"
              onChange={(e) => setSaveAsName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleSaveAs();
                if (e.key === "Escape") cancelSaveAs();
              }}
              className="flex-1 max-w-xs bg-surface border border-border-default rounded px-2 py-1 text-sm font-mono text-text-primary focus:outline-none focus:border-border-emphasis"
            />
            {saveAsError && (
              <span className="text-[10px] font-mono text-status-error">
                {saveAsError}
              </span>
            )}
            <button
              type="button"
              onClick={handleSaveAs}
              disabled={saving}
              className="h-7 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] bg-accent text-bg hover:bg-[#FF6A3D] disabled:bg-accent/30 disabled:cursor-not-allowed"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={cancelSaveAs}
              className="h-7 px-3 text-[10px] font-medium uppercase tracking-[0.16em] border border-border-default text-text-secondary hover:bg-surface-raised"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex-1 flex items-center gap-3 px-3">
            <select
              value={activeName}
              onChange={(e) => void handleSelectFile(e.target.value)}
              className="bg-surface border border-border-default rounded px-2 py-1 text-sm font-mono text-text-primary focus:outline-none focus:border-border-emphasis"
            >
              {available.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
            {isDirty ? (
              <span className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-accent">
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full bg-accent"
                  aria-hidden
                />
                modified
              </span>
            ) : flashedRecently ? (
              <span className="text-[10px] font-mono uppercase tracking-widest text-status-done">
                saved
              </span>
            ) : null}
          </div>
        )}

        {/* Action buttons */}
        {!saveAsMode && (
          <div className="flex items-stretch border-l border-border-default">
            <button
              type="button"
              onClick={revert}
              disabled={!isDirty || saving}
              className="px-4 text-[10px] font-medium uppercase tracking-[0.16em] text-text-secondary hover:bg-surface-raised hover:text-text-primary disabled:text-text-muted disabled:cursor-not-allowed border-r border-border-default"
            >
              Revert
            </button>
            <button
              type="button"
              onClick={beginSaveAs}
              disabled={saving}
              className="px-4 text-[10px] font-medium uppercase tracking-[0.16em] text-text-secondary hover:bg-surface-raised hover:text-text-primary disabled:text-text-muted disabled:cursor-not-allowed border-r border-border-default"
            >
              Save As…
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!isDirty || saving}
              className="px-5 text-[11px] font-semibold uppercase tracking-[0.18em] bg-accent text-bg hover:bg-[#FF6A3D] disabled:bg-accent/20 disabled:text-accent/50 disabled:cursor-not-allowed"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        )}
      </header>

      {/* Save error strip */}
      {saveError && (
        <div className="mx-4 mt-3 border border-status-error/40 bg-status-error/[0.06] px-3 py-2">
          <div className="flex items-start gap-2">
            <span
              className="mt-[5px] inline-block w-1.5 h-1.5 rounded-full bg-status-error flex-shrink-0"
              aria-hidden
            />
            <div className="flex-1 min-w-0">
              <div className="text-[9px] font-semibold uppercase tracking-[0.2em] text-status-error leading-none mb-1">
                Save Failed
              </div>
              <div className="text-xs text-text-primary font-mono break-words leading-snug">
                {saveError}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Section list */}
      <div className="p-4 flex flex-col gap-3">
        <IdentitySection />
        <CylinderSection />
      </div>
    </main>
  );
}
