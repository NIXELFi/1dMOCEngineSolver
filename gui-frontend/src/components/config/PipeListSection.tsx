import { useConfigStore, type PipeArrayKey } from "../../state/configStore";
import { Accordion } from "../forms/Accordion";
import { PipeRow } from "../forms/PipeRow";

interface PipeListSectionProps {
  section: PipeArrayKey;
  index: string;
  label: string;
}

export default function PipeListSection({
  section,
  index,
  label,
}: PipeListSectionProps) {
  const list = useConfigStore((s) => s.draft?.[section] ?? []);
  const addPipe = useConfigStore((s) => s.addPipe);
  const removePipe = useConfigStore((s) => s.removePipe);

  const addButton = (
    <button
      type="button"
      onClick={() => addPipe(section)}
      className="text-[10px] font-medium uppercase tracking-[0.16em] text-text-secondary border border-border-default rounded px-3 py-1 hover:bg-bg hover:text-text-primary hover:border-border-emphasis"
    >
      + pipe
    </button>
  );

  return (
    <Accordion id={section} index={index} label={label} rightSlot={addButton}>
      <div className="flex flex-col gap-3">
        {list.map((_, i) => (
          <PipeRow
            key={i}
            arraySection={section}
            arrayIndex={i}
            index={String(i + 1).padStart(2, "0")}
            onRemove={() => removePipe(section, i)}
          />
        ))}
        {list.length === 0 && (
          <div className="text-[10px] uppercase tracking-widest text-text-muted text-center py-4">
            No pipes — click "+ pipe" to add one
          </div>
        )}
      </div>
    </Accordion>
  );
}
