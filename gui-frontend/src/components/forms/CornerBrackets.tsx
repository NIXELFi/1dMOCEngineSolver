/**
 * Decorative chassis corner marks for instrument-style panels.
 * Used by RunSweepDialog and any framed surface in the Config tab.
 */
export function CornerBrackets() {
  const common = "absolute w-2 h-2 border-border-emphasis pointer-events-none";
  return (
    <>
      <span className={`${common} -top-px -left-px border-t border-l`} aria-hidden />
      <span className={`${common} -top-px -right-px border-t border-r`} aria-hidden />
      <span className={`${common} -bottom-px -left-px border-b border-l`} aria-hidden />
      <span className={`${common} -bottom-px -right-px border-b border-r`} aria-hidden />
    </>
  );
}
