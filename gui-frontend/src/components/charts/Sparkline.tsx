interface SparklineProps {
  /** Numeric series — no x-axis values, just the y values. */
  data: number[];
  /** SVG width in px. Defaults to 80. */
  width?: number;
  /** SVG height in px. Defaults to 24. */
  height?: number;
  /** Stroke color. Defaults to currentColor so the parent can tint via text-*. */
  color?: string;
  /** Line stroke width. Defaults to 1. */
  strokeWidth?: number;
}

/**
 * Sparkline — a tiny inline SVG line chart with zero dependencies.
 *
 * Used inside WorkerTile to visualize the convergence delta history. The
 * chart is deliberately chrome-free: no axes, no ticks, no labels, no dots.
 * It's a single polyline stroke on transparent background, meant to be read
 * as shape rather than precise value. If you want numbers, read the δ row
 * above it.
 *
 * Layout is always preserved — even with 0 or 1 points the SVG renders at
 * the requested size so the tile doesn't jitter when data arrives.
 */
export default function Sparkline({
  data,
  width = 80,
  height = 24,
  color = "currentColor",
  strokeWidth = 1,
}: SparklineProps) {
  // Not enough points for a line — render an empty, correctly-sized SVG so
  // the parent's layout stays stable as data streams in.
  if (!data || data.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden
      />
    );
  }

  // Filter out non-finite values defensively. If everything is non-finite,
  // fall back to the empty rendering above.
  const finite = data.filter((v) => Number.isFinite(v));
  if (finite.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden
      />
    );
  }

  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const range = max - min;

  // Inset the stroke by half its width so it doesn't get clipped at the
  // SVG edges. Matters most at strokeWidth 1.5+.
  const pad = strokeWidth / 2;
  const innerW = Math.max(0, width - strokeWidth);
  const innerH = Math.max(0, height - strokeWidth);

  // Degenerate case: all values equal → draw a flat mid-height line.
  if (range === 0) {
    const y = pad + innerH / 2;
    const points = finite
      .map((_, i) => {
        const x = pad + (i / (finite.length - 1)) * innerW;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        shapeRendering="geometricPrecision"
        aria-hidden
      >
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  // Normal case: normalize every value to 0..innerH, flipping y so that
  // higher numeric values rise to the top of the SVG (screen y grows down).
  const points = finite
    .map((v, i) => {
      const x = pad + (i / (finite.length - 1)) * innerW;
      const norm = (v - min) / range; // 0..1
      const y = pad + (1 - norm) * innerH;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      shapeRendering="geometricPrecision"
      aria-hidden
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
