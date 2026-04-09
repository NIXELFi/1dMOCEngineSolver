import { useConfigStore, type ValveKey } from "../../state/configStore";
import { NumericField } from "./NumericField";

interface CdTableEditorProps {
  valve: ValveKey;
}

/**
 * Inline editor for the (L/D, Cd) lookup table on a valve. Each row is
 * two NumericFields plus a delete button. The "+ add row" button at the
 * bottom appends a new row with default values. The list is auto-sorted
 * by L/D ascending on save (the cd_table is a lookup that depends on
 * monotonic ordering); since this happens server-side, no warning here.
 */
export function CdTableEditor({ valve }: CdTableEditorProps) {
  const rows = useConfigStore((s) => s.draft?.[valve].cd_table ?? []);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  const addRow = useConfigStore((s) => s.addCdRow);
  const removeRow = useConfigStore((s) => s.removeCdRow);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-1.5">
        <span className="text-[9px] font-mono text-text-muted leading-none">[CD TABLE]</span>
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-secondary leading-none">
          Discharge Coefficient Lookup
        </span>
      </div>
      <div className="flex flex-col gap-2 border border-border-default rounded p-3 bg-surface">
        {rows.length === 0 && (
          <div className="text-[10px] text-text-muted uppercase tracking-widest text-center py-2">
            No rows
          </div>
        )}
        {rows.map((pair, i) => (
          <div key={i} className="flex items-end gap-3">
            <div className="flex-1">
              <NumericField
                index={String(i + 1).padStart(2, "0")}
                label="L/D"
                unit="—"
                value={pair[0]}
                onChange={(v) => setField(`${valve}.cd_table.${i}.0`, v)}
                error={fieldErrors[`${valve}.cd_table.${i}.0`]}
                step={0.01}
                min={0}
              />
            </div>
            <div className="flex-1">
              <NumericField
                index={String(i + 1).padStart(2, "0")}
                label="Cd"
                unit="—"
                value={pair[1]}
                onChange={(v) => setField(`${valve}.cd_table.${i}.1`, v)}
                error={fieldErrors[`${valve}.cd_table.${i}.1`]}
                step={0.01}
                min={0}
              />
            </div>
            <button
              type="button"
              onClick={() => removeRow(valve, i)}
              aria-label={`Remove row ${i + 1}`}
              className="h-9 w-9 inline-flex items-center justify-center border border-border-default rounded text-text-muted hover:text-status-error hover:border-status-error/60"
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => addRow(valve)}
          className="self-start text-[10px] font-medium uppercase tracking-[0.16em] text-text-secondary border border-border-default rounded px-3 py-1 hover:bg-bg hover:text-text-primary hover:border-border-emphasis"
        >
          + add row
        </button>
      </div>
    </div>
  );
}
