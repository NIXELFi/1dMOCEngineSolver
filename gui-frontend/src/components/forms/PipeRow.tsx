import { useConfigStore, type PipeArrayKey } from "../../state/configStore";
import { NumericField } from "./NumericField";
import { TextField } from "./TextField";

interface PipeRowProps {
  /** Either a pipe array section + index, OR a single-pipe path. */
  arraySection?: PipeArrayKey;
  arrayIndex?: number;
  /** Used by exhaust_collector (single pipe, not in an array). */
  singlePath?: "exhaust_collector";
  /** Display index for the [NN] mark. */
  index: string;
  onRemove?: () => void;
}

/**
 * One row of pipe fields: name | length | diameter | diameter_out | n_points
 * | wall_temperature | roughness | × button. Used inside PipeListSection
 * (array entries) and PipeRowSection (single exhaust_collector pipe).
 */
export function PipeRow({
  arraySection,
  arrayIndex,
  singlePath,
  index,
  onRemove,
}: PipeRowProps) {
  const draft = useConfigStore((s) => s.draft);
  const fieldErrors = useConfigStore((s) => s.fieldErrors);
  const setField = useConfigStore((s) => s.setField);
  if (draft === null) return null;

  // Resolve the pipe object and the dot-path prefix
  let pipe;
  let pathPrefix: string;
  if (singlePath) {
    pipe = draft[singlePath];
    pathPrefix = singlePath;
  } else if (arraySection !== undefined && arrayIndex !== undefined) {
    pipe = draft[arraySection][arrayIndex];
    pathPrefix = `${arraySection}.${arrayIndex}`;
  } else {
    return null;
  }

  const err = (suffix: string): string | undefined =>
    fieldErrors[`${pathPrefix}.${suffix}`];

  return (
    <div className="border border-border-default rounded p-3 bg-surface flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="text-[9px] font-mono text-text-muted">[{index}]</span>
        <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
          {pipe.name}
        </span>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove ${pipe.name}`}
            className="ml-auto h-7 w-7 inline-flex items-center justify-center border border-border-default rounded text-text-muted hover:text-status-error hover:border-status-error/60"
          >
            ×
          </button>
        )}
      </div>

      <div className="grid grid-cols-4 gap-3">
        <TextField
          index="01"
          label="Name"
          value={pipe.name}
          onChange={(v) => setField(`${pathPrefix}.name`, v)}
          error={err("name")}
        />
        <NumericField
          index="02"
          label="Length"
          unit="mm"
          value={pipe.length}
          onChange={(n) => setField(`${pathPrefix}.length`, n)}
          error={err("length")}
          displayScale={1000}
          step={1}
        />
        <NumericField
          index="03"
          label="Diameter"
          unit="mm"
          value={pipe.diameter}
          onChange={(n) => setField(`${pathPrefix}.diameter`, n)}
          error={err("diameter")}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="04"
          label="Diameter Out"
          unit="mm"
          value={pipe.diameter_out ?? NaN}
          onChange={(n) =>
            setField(
              `${pathPrefix}.diameter_out`,
              Number.isFinite(n) ? n : null,
            )
          }
          error={err("diameter_out")}
          displayScale={1000}
          step={0.1}
        />
        <NumericField
          index="05"
          label="N Points"
          unit="—"
          value={pipe.n_points}
          onChange={(n) => setField(`${pathPrefix}.n_points`, n)}
          error={err("n_points")}
          step={1}
          min={2}
        />
        <NumericField
          index="06"
          label="Wall Temp"
          unit="K"
          value={pipe.wall_temperature}
          onChange={(n) => setField(`${pathPrefix}.wall_temperature`, n)}
          error={err("wall_temperature")}
          step={5}
        />
        <NumericField
          index="07"
          label="Roughness"
          unit="µm"
          value={pipe.roughness}
          onChange={(n) => setField(`${pathPrefix}.roughness`, n)}
          error={err("roughness")}
          displayScale={1e6}
          step={1}
        />
      </div>
    </div>
  );
}
