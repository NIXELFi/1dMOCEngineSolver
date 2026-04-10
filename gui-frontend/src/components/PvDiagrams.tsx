import { useEffect, useMemo, useState } from "react";
import LineChart, { type SeriesDef } from "./charts/LineChart";
import type { SimulationResultsData } from "./RpmDetail";
import { useSweepStore } from "../state/sweepStore";
import { api } from "../api/client";
import type { CylinderPayload } from "../state/configStore";

/* ========================================================================= */
/* Types                                                                     */
/* ========================================================================= */

interface PvDiagramsProps {
  results: SimulationResultsData;
}

/** One data point for a P-V chart: volume in cc, pressure in bar. */
interface PvRow {
  volume: number;
  pressure: number;
  [extraKey: string]: number | boolean | undefined;
}

/** Per-cylinder derived display data. */
interface CylDerived {
  key: string;
  ordinal: string;
  label: string;
  title: string;
  color: string;
  rows: PvRow[];
}

/** Overlay row: one volume column + one pressure column per cylinder. */
interface OverlayRow {
  volume: number;
  cyl_0?: number;
  cyl_1?: number;
  cyl_2?: number;
  cyl_3?: number;
  [extraKey: string]: number | boolean | undefined;
}

/* ========================================================================= */
/* Slider-crank kinematics — matches engine_simulator/engine/geometry.py     */
/* ========================================================================= */

function computeVolume(
  thetaDeg: number,
  bore: number,
  stroke: number,
  conRodLength: number,
  compressionRatio: number,
): number {
  const crankRadius = stroke / 2;
  const rodRatio = crankRadius / conRodLength;
  const aPiston = (Math.PI / 4) * bore * bore;
  const vDisp = aPiston * stroke;
  const vClearance = vDisp / (compressionRatio - 1);

  const thetaRad = (thetaDeg * Math.PI) / 180;
  const sinT = Math.sin(thetaRad);
  const cosT = Math.cos(thetaRad);
  const s =
    crankRadius * (1 - cosT) +
    conRodLength * (1 - Math.sqrt(1 - rodRatio * rodRatio * sinT * sinT));
  return vClearance + aPiston * s;
}

/* ========================================================================= */
/* Per-cylinder color assignments (same as CylinderTraces)                   */
/* ========================================================================= */

const CYL_COLORS = {
  "0": "#E5484D",
  "1": "#4493F8",
  "2": "#3DD68C",
  "3": "#C586E8",
} as const;

/* ========================================================================= */
/* PvDiagrams component                                                      */
/* ========================================================================= */

export default function PvDiagrams({ results }: PvDiagramsProps) {
  const sweep = useSweepStore((s) => s.sweep);
  const [geom, setGeom] = useState<CylinderPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  /* Fetch cylinder geometry from the config that produced this sweep. */
  useEffect(() => {
    const configName = sweep?.config_summary?.config_name;
    if (!configName) return;

    let cancelled = false;
    api
      .getConfig(configName)
      .then((cfg) => {
        if (!cancelled) setGeom(cfg.cylinder);
      })
      .catch((e: unknown) => {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [sweep?.config_summary?.config_name]);

  /* ---- Per-cylinder P-V derivation ---------------------------------------- */
  const cylinders = useMemo<CylDerived[]>(() => {
    if (!geom) return [];
    const out: CylDerived[] = [];
    for (let i = 0; i < 4; i++) {
      const key = String(i);
      const cd = results.cylinder_data[key];
      const ordinal = `C${i + 1}`;
      const label = `Cyl ${i + 1}`;
      const title = `CYL ${i + 1}`;
      const color = CYL_COLORS[key as keyof typeof CYL_COLORS];

      if (!cd || !cd.theta || cd.theta.length === 0) {
        out.push({ key, ordinal, label, title, color, rows: [] });
        continue;
      }

      const { theta, pressure } = cd;
      // Take the last 720° window (one full cycle).
      let maxTheta = -Infinity;
      for (const t of theta) {
        if (Number.isFinite(t) && t > maxTheta) maxTheta = t;
      }
      if (!Number.isFinite(maxTheta)) {
        out.push({ key, ordinal, label, title, color, rows: [] });
        continue;
      }
      const cutoff = maxTheta - 720;

      const rows: PvRow[] = [];
      const n = Math.min(theta.length, pressure.length);
      for (let k = 0; k < n; k++) {
        const t = theta[k];
        if (!Number.isFinite(t) || t < cutoff) continue;
        const p = pressure[k];
        if (!Number.isFinite(p)) continue;
        // Volume in cc (m³ → cc = × 1e6), pressure in bar (Pa → bar = / 1e5)
        const v = computeVolume(
          t - cutoff,
          geom.bore,
          geom.stroke,
          geom.con_rod_length,
          geom.compression_ratio,
        );
        rows.push({
          volume: v * 1e6,
          pressure: p / 1e5,
        });
      }
      out.push({ key, ordinal, label, title, color, rows });
    }
    return out;
  }, [results, geom]);

  /* ---- Overlay rows ------------------------------------------------------- */
  const overlayRows = useMemo<OverlayRow[]>(() => {
    if (!geom) return [];
    const cyl0 = results.cylinder_data["0"];
    if (!cyl0 || !cyl0.theta || cyl0.theta.length === 0) return [];

    let maxTheta = -Infinity;
    for (const t of cyl0.theta) {
      if (Number.isFinite(t) && t > maxTheta) maxTheta = t;
    }
    if (!Number.isFinite(maxTheta)) return [];
    const cutoff = maxTheta - 720;

    const rows: OverlayRow[] = [];
    const n = cyl0.theta.length;
    for (let k = 0; k < n; k++) {
      const t = cyl0.theta[k];
      if (!Number.isFinite(t) || t < cutoff) continue;
      const v = computeVolume(
        t - cutoff,
        geom.bore,
        geom.stroke,
        geom.con_rod_length,
        geom.compression_ratio,
      );
      const row: OverlayRow = { volume: v * 1e6 };
      const p0 = cyl0.pressure[k];
      if (Number.isFinite(p0)) row.cyl_0 = p0 / 1e5;

      for (let ci = 1; ci <= 3; ci++) {
        const cd = results.cylinder_data[String(ci)];
        if (cd) {
          const p = cd.pressure[k];
          if (Number.isFinite(p))
            (row as Record<string, number>)[`cyl_${ci}`] = p / 1e5;
        }
      }
      rows.push(row);
    }
    return rows;
  }, [results, geom]);

  /* ---- Overlay series definitions ----------------------------------------- */
  const overlaySeries: SeriesDef[] = [
    { key: "cyl_0", label: "Cyl 1", color: CYL_COLORS["0"] },
    { key: "cyl_1", label: "Cyl 2", color: CYL_COLORS["1"] },
    { key: "cyl_2", label: "Cyl 3", color: CYL_COLORS["2"] },
    { key: "cyl_3", label: "Cyl 4", color: CYL_COLORS["3"] },
  ];

  /* ---- Loading / error states --------------------------------------------- */
  if (loadError) {
    return (
      <div className="py-10 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 max-w-[460px]">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-status-error" aria-hidden />
          <div className="w-16 h-px bg-border-default" aria-hidden />
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-status-error leading-none text-center">
            Failed to Load Geometry
          </p>
          <p className="text-[10px] font-mono text-text-muted/70 leading-snug text-center">
            {loadError}
          </p>
        </div>
      </div>
    );
  }

  if (!geom) {
    return (
      <div className="py-10 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted" aria-hidden />
          <div className="w-16 h-px bg-border-default" aria-hidden />
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-text-muted leading-none text-center">
            Loading Cylinder Geometry…
          </p>
        </div>
      </div>
    );
  }

  /* ---- Render ------------------------------------------------------------- */
  return (
    <div className="flex flex-col gap-2">
      {/* 4-up small P-V traces */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2">
        {cylinders.map((cyl) => (
          <PvPanel
            key={cyl.key}
            ordinal={cyl.ordinal}
            title={cyl.title}
            nPoints={cyl.rows.length}
            accent={cyl.color}
          >
            {cyl.rows.length === 0 ? (
              <NoData />
            ) : (
              <LineChart
                data={cyl.rows}
                xKey="volume"
                series={[{ key: "pressure", label: "P", color: cyl.color }]}
                yLabel="PRESSURE · BAR"
                height={150}
                showDots={false}
              />
            )}
          </PvPanel>
        ))}
      </div>

      {/* Overlay comparison chart */}
      <PvPanel
        ordinal="CX"
        title="All Cylinders"
        nPoints={overlayRows.length}
        accent="#8B8B95"
      >
        {overlayRows.length === 0 ? (
          <NoData />
        ) : (
          <LineChart
            data={overlayRows}
            xKey="volume"
            series={overlaySeries}
            yLabel="PRESSURE · BAR"
            height={250}
            showDots={false}
          />
        )}
      </PvPanel>
    </div>
  );
}

/* ========================================================================= */
/* PvPanel — bordered chrome for each sub-chart (mirrors CylinderPanel)     */
/* ========================================================================= */

function PvPanel({
  ordinal,
  title,
  nPoints,
  accent,
  children,
}: {
  ordinal: string;
  title: string;
  nPoints: number;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="flex flex-col bg-surface-raised border border-border-default rounded font-ui"
      aria-label={title}
    >
      <header className="flex items-stretch border-b border-border-default">
        <div className="flex-1 flex items-center gap-2 px-2.5 py-1.5 min-w-0">
          <span
            className="inline-block w-[3px] h-3"
            style={{ backgroundColor: accent }}
            aria-hidden
          />
          <span className="text-[9px] font-mono text-text-muted leading-none tabular-nums">
            [{ordinal}]
          </span>
          <h4 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-text-primary leading-none truncate">
            {title}
          </h4>
        </div>

        <div className="flex items-center gap-1 px-2.5 border-l border-border-default">
          <span className="text-[9px] font-mono uppercase tracking-[0.14em] text-text-muted leading-none">
            n
          </span>
          <span className="text-[9px] font-mono text-text-muted leading-none">
            =
          </span>
          <span className="text-[9px] font-mono tabular-nums text-text-secondary leading-none">
            {formatCount(nPoints)}
          </span>
        </div>
      </header>

      <div className="p-2.5">{children}</div>
    </section>
  );
}

/* ========================================================================= */
/* NoData — compact in-panel empty state                                     */
/* ========================================================================= */

function NoData() {
  return (
    <div className="h-[150px] flex flex-col items-center justify-center gap-2">
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-text-muted" aria-hidden />
      <div className="w-10 h-px bg-border-default" aria-hidden />
      <span className="text-[9px] font-mono font-semibold uppercase tracking-[0.22em] text-text-muted leading-none">
        No Data
      </span>
    </div>
  );
}

/* ========================================================================= */
/* Helpers                                                                    */
/* ========================================================================= */

function formatCount(n: number): string {
  if (n < 100) return String(n).padStart(2, "0");
  if (n < 10000) return String(n);
  return `${Math.round(n / 1000)}k`;
}
