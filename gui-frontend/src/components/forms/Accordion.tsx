import * as React from "react";
import { useConfigStore, selectIsSectionOpen } from "../../state/configStore";

interface AccordionProps {
  id: string;             // stable section id, e.g. "cylinder"
  index: string;          // "01" for the index mark
  label: string;
  rightSlot?: React.ReactNode;  // e.g. an "[+ pipe]" button
  children: React.ReactNode;
}

/**
 * Numbered, collapsible section header. State persisted in configStore
 * via `expandedSections`. Default is open.
 */
export function Accordion({ id, index, label, rightSlot, children }: AccordionProps) {
  const isOpen = useConfigStore(selectIsSectionOpen(id));
  const toggle = useConfigStore((s) => s.toggleSection);

  return (
    <section className="border border-border-default rounded">
      <header className="flex items-stretch border-b border-border-default bg-surface">
        <button
          type="button"
          onClick={() => toggle(id)}
          aria-expanded={isOpen}
          aria-controls={`accordion-body-${id}`}
          className="flex-1 flex items-center gap-2 px-4 py-2 text-left hover:bg-surface-raised transition-colors duration-150"
        >
          <span className="text-text-muted text-[10px] leading-none w-3">
            {isOpen ? "▾" : "▸"}
          </span>
          <span className="text-[9px] font-mono text-text-muted leading-none">
            [{index}]
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-primary leading-none">
            {label}
          </span>
        </button>
        {rightSlot && (
          <div className="flex items-center pr-3 border-l border-border-default px-3">
            {rightSlot}
          </div>
        )}
      </header>
      {isOpen && (
        <div
          id={`accordion-body-${id}`}
          className="p-4 bg-bg flex flex-col gap-4"
        >
          {children}
        </div>
      )}
    </section>
  );
}
