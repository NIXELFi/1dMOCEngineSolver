# PDF Report Export — Design Spec

## Overview

Add a server-side PDF report generator to the 1D engine simulator GUI. A "Download Report" button in the TopBar triggers a backend endpoint that generates a comprehensive, beautifully styled engineering report from a completed sweep's data. The PDF is built using WeasyPrint (HTML/CSS → PDF) with matplotlib SVG charts embedded inline, and served as a file download.

## Report Structure

### Main Body

1. **Cover Page**
   - Title: "Engine Simulation Report"
   - Engine config name
   - Date/time of sweep
   - Headline stats: peak power (HP @ RPM), peak torque (Nm @ RPM)
   - Clean, minimal layout with accent line dividers

2. **Engine Configuration**
   - Full config parameters in grouped tables:
     - Cylinder geometry (bore, stroke, con rod, CR, valve count)
     - Intake valve (diameter, lift, timing, seat angle, Cd table)
     - Exhaust valve (same structure)
     - Intake pipes (name, length, diameters, n_points, wall temp, roughness)
     - Exhaust primaries, secondaries, collector (same structure)
     - Combustion (Wiebe params, spark advance, efficiency, fuel properties)
     - Restrictor (throat, Cd, angles)
     - Plenum (volume, initial conditions)
     - Simulation settings (RPM range, cycles, CFL, tolerance, crank step, viscosity)
     - Ambient conditions (P, T, drivetrain efficiency)
   - Each table: parameter name / value / unit columns

3. **Performance Sweep Curves**
   - Full-page layout with 6 charts, all vs RPM:
     - Power (HP) — indicated, brake, wheel
     - Torque (Nm) — indicated, brake, wheel
     - Volumetric Efficiency (%) — atmospheric & plenum
     - IMEP / BMEP (bar)
     - Plenum Pressure (bar)
     - Restrictor Mass Flow (g/s) + choked indicator
   - Charts rendered as matplotlib SVGs

4. **Performance Data Table**
   - Tabular data for every RPM point
   - Columns: RPM, Power (HP), Torque (Nm), VE (%), IMEP (bar), BMEP (bar), Plenum P (bar), Restrictor mdot (g/s), Choked
   - Alternating row shading

5. **Convergence Summary**
   - Table: RPM, converged (yes/no), cycles to converge, final delta
   - Overview chart: cycles-to-converge vs RPM

### Appendix — Per-RPM Detail Pages

One page (or more) per RPM point, each containing:

- **Cylinder Traces** — Pressure and temperature vs crank angle (all cylinders overlaid)
- **P-V Diagrams** — Pressure vs volume for all cylinders overlaid
- **Pipe Traces** — Intake and exhaust midpoint pressure, temperature, velocity vs crank angle
- **Plenum** — Pressure and temperature history vs crank angle
- **Restrictor** — Mass flow rate vs crank angle with choked regions highlighted
- **Convergence Detail** — Delta history per cycle + p_IVC per cylinder per cycle

Each appendix page has "Appendix — RPM Detail: {rpm}" as header.

## Backend Architecture

### New Files

- `engine_simulator/gui/report.py` — Main report generation orchestration
- `engine_simulator/gui/report_charts.py` — Matplotlib chart functions (each returns SVG string)
- `engine_simulator/gui/report_template.html` — Jinja2 HTML/CSS template for the entire report

### New API Endpoint

Added to `routes_api.py`:

```
GET /api/sweeps/{sweep_id}/report
```

- Loads sweep data from saved JSON (via existing persistence module)
- Calls `generate_report(sweep_data)` from `report.py`
- Returns `StreamingResponse` with:
  - `Content-Type: application/pdf`
  - `Content-Disposition: attachment; filename="{config_name}_{sweep_id}_report.pdf"`

### report.py — Generation Flow

1. Load sweep JSON via `persistence.load_sweep(sweep_id)`
2. Extract: engine config, perf list, results_by_rpm, convergence data (delta_history, p_ivc_history from rpms dict)
3. Call chart functions from `report_charts.py` → collect SVG strings
4. Build template context dict with all data + SVGs
5. Render Jinja2 template → HTML string
6. Pass HTML to `weasyprint.HTML(string=html).write_pdf()` → PDF bytes
7. Return bytes

### report_charts.py — Chart Functions

All functions return SVG strings via `fig.savefig(buf, format='svg')`.

Consistent matplotlib style across all charts:
- White background, subtle grid (#e0e0e0, alpha 0.5)
- Color cycle: blues, oranges, greens (consistent palette)
- Proper axis labels with units
- Clean, professional, minimal chartjunk

Functions:

| Function | Input | Output |
|----------|-------|--------|
| `render_sweep_curves(perf_data)` | List of PerfDicts | 6 SVG charts (power, torque, VE, MEP, plenum, restrictor) |
| `render_convergence_overview(rpms_data)` | RPM convergence data | 1 SVG (cycles-to-converge vs RPM) |
| `render_cylinder_traces(results)` | SimulationResults for one RPM | 2 SVGs (pressure + temperature vs θ) |
| `render_pv_diagrams(results)` | SimulationResults for one RPM | 1 SVG (P-V all cylinders) |
| `render_pipe_traces(results)` | SimulationResults for one RPM | 3 SVGs (P, T, velocity vs θ) |
| `render_plenum_chart(results)` | SimulationResults for one RPM | 1 SVG (P + T vs θ) |
| `render_restrictor_chart(results)` | SimulationResults for one RPM | 1 SVG (mdot + choked vs θ) |
| `render_convergence_detail(delta_history, p_ivc_history)` | Per-RPM convergence arrays | 2 SVGs (delta vs cycle, p_IVC vs cycle) |

### Dependencies

Add to `requirements.txt`:
- `weasyprint` — HTML/CSS to PDF conversion
- `matplotlib` — chart rendering (verify if already available)

`jinja2` is already a transitive dependency of FastAPI/Starlette.

## Frontend Changes

### TopBar Component

Add a "Download Report" button:
- Position: next to existing Run/Stop buttons
- Icon: document/download icon from Lucide (e.g., `FileDown`)
- Enabled only when sweep status is `"complete"`
- Disabled state: grayed out, no tooltip needed (contextually obvious)
- Loading state: spinner replaces icon while PDF is generating
- On click: calls `downloadReport(sweepId)`

### API Client

Add to `api/client.ts`:

```typescript
async function downloadReport(sweepId: string): Promise<void> {
  const response = await fetch(`/api/sweeps/${sweepId}/report`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `report_${sweepId}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
```

No new components, no new Zustand state. Uses existing `sweepId` from the sweep store.

## Visual Design

### Typography & Color

- Font stack: Helvetica Neue, Arial, sans-serif (system fonts, no downloads)
- Primary text: dark charcoal (#1a1a2e)
- Accent color: deep blue (#1e3a5f) for headers and rules
- Table alternating rows: light gray (#f4f6f8)
- White page background

### Layout

- A4 page size, 20mm margins
- Cover page: centered, minimal — large title, thin accent dividers
- Section headers: large bold text with colored underline rule
- Config tables: clean bordered, grouped by category, 3 columns (parameter / value / unit)
- Charts: full-width for sweep curves, arranged 2-3 per page for detail sections
- Performance data table: compact, alternating row shading, bold headers

### Page Furniture

- Header (all pages except cover): config name + "Engine Simulation Report" — small, gray, top-right
- Footer: centered page number
- Appendix headers: "Appendix — RPM Detail: {rpm}"

### Chart Style (matplotlib)

- Consistent figure sizes per context
- White background, subtle grid
- Matched color palette across all charts
- SVG output for crisp rendering at any zoom level
- Proper axis labels with units, legend where needed
- No excessive decoration — professional, data-focused
