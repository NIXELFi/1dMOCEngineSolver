import { Play, Pause, RotateCcw } from "lucide-react";
import { useDynoStore } from "../../state/dynoStore";

const SPEEDS = [0.5, 1, 2];

export default function TransportBar() {
  const playing = useDynoStore((s) => s.playing);
  const currentRpm = useDynoStore((s) => s.currentRpm);
  const rpmMin = useDynoStore((s) => s.rpmMin);
  const rpmMax = useDynoStore((s) => s.rpmMax);
  const speed = useDynoStore((s) => s.speed);
  const play = useDynoStore((s) => s.play);
  const pause = useDynoStore((s) => s.pause);
  const reset = useDynoStore((s) => s.reset);
  const scrubTo = useDynoStore((s) => s.scrubTo);
  const setSpeed = useDynoStore((s) => s.setSpeed);

  const hasData = rpmMax > rpmMin;

  return (
    <div className="h-10 flex items-center gap-3 px-3 bg-surface border-b border-border-default font-ui">
      {/* Play / Pause */}
      <button
        type="button"
        onClick={() => (playing ? pause() : play())}
        disabled={!hasData}
        className={[
          "flex items-center justify-center w-7 h-7 rounded",
          "transition-colors duration-100",
          hasData
            ? "text-accent hover:bg-surface-raised"
            : "text-text-muted opacity-40 cursor-not-allowed",
        ].join(" ")}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? <Pause size={14} /> : <Play size={14} />}
      </button>

      {/* Reset */}
      <button
        type="button"
        onClick={reset}
        disabled={!hasData}
        className={[
          "flex items-center justify-center w-7 h-7 rounded",
          "transition-colors duration-100",
          hasData
            ? "text-text-secondary hover:text-text-primary hover:bg-surface-raised"
            : "text-text-muted opacity-40 cursor-not-allowed",
        ].join(" ")}
        aria-label="Reset"
      >
        <RotateCcw size={14} />
      </button>

      {/* Scrub slider */}
      <input
        type="range"
        min={rpmMin}
        max={rpmMax}
        step={1}
        value={currentRpm}
        onChange={(e) => scrubTo(Number(e.target.value))}
        disabled={!hasData}
        className="flex-1 h-1 accent-accent cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Scrub RPM"
      />

      {/* RPM readout */}
      <span className="text-[11px] font-mono tabular-nums text-text-secondary leading-none min-w-[4.5rem] text-right">
        {hasData ? `${Math.round(currentRpm)} RPM` : "— RPM"}
      </span>

      {/* Divider */}
      <div className="w-px h-5 bg-border-default" aria-hidden />

      {/* Speed buttons */}
      <div className="flex items-center gap-1">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSpeed(s)}
            disabled={!hasData}
            className={[
              "px-2 py-1 rounded text-[10px] font-mono font-medium leading-none",
              "transition-colors duration-100",
              s === speed
                ? "bg-accent text-white"
                : hasData
                  ? "text-text-muted hover:text-text-primary hover:bg-surface-raised"
                  : "text-text-muted opacity-40 cursor-not-allowed",
            ].join(" ")}
          >
            {s}x
          </button>
        ))}
      </div>
    </div>
  );
}
