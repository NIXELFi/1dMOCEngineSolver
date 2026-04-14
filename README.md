# 1D MOC Engine Solver

> ### ⚠️ Known exhaust-side limitation — superseded by V2 for exhaust tuning
>
> This MOC-based solver has a structural limitation in its valve boundary
> condition: it carries the pipe's entropy level (AA) across the valve
> instead of the cylinder's exhaust-gas entropy, which causes exhaust
> gas temperatures at the primary valve face to be reported near
> **atmospheric (~275 K)** instead of their physical value (~1000–1400 K
> at WOT). Exhaust wave speeds are consequently underpredicted by ~2×.
>
> **Quantitative comparison across 6000–13500 RPM** (see
> `../1d_v2/docs/v2_vs_v1_comparison.md` in the parallel V2 repository
> for full data):
>
> | | This (V1 MOC) | V2 (FV + HLLC) |
> |---|---|---|
> | EGT at valve face, sweep range | 250–303 K (flat) | 1049–1351 K (rising with RPM) |
> | EGT delta (V2 − V1) | — | +778 K to +1064 K |
> | Mass conservation residual | O(1e-5) to O(1e-3) kg/cycle | O(1e-18) kg/cycle |
> | Numerical convergence | 13/16 sweep points | 16/16 |
>
> **Affected:** any exhaust geometry decision, primary/secondary length
> tuning, collector sizing, or anything that depends on exhaust wave
> timing. Tuned-length predictions from this code should be treated as
> known-wrong.
>
> **Not affected:** intake-side predictions. The intake BCs (restrictor,
> plenum, runners) are not known to be broken and continue to be usable
> while you are investigating intake geometry or ECU calibration.
>
> Production exhaust work should use the V2 solver at
> [`1dFVEngineSolver`](https://github.com/NIXELFi/1dFVEngineSolver).
> The V1 codebase here remains active for intake research and for
> impedance-coupled-valve-BC experimentation on the
> `feat/impedance-coupled-valve-bc` branch, which may eventually inform
> V2's valve BC treatment but does not fix the underlying entropy-
> transport issue on its own.

A high-performance 1D Method of Characteristics (MOC) engine simulation solver for the Honda CBR600RR motorcycle engine. Accurately models engine thermodynamics, combustion, intake/exhaust wave dynamics, and produces real-time performance predictions across operating ranges.

## Features

- **1D Method of Characteristics Solver**: Accurately simulates thermodynamic wave propagation through intake and exhaust systems
- **Combustion Modeling**: Realistic fuel combustion with detailed thermal analysis
- **Wave Dynamics**: Captures pressure waves, resonance, and tuning effects in intake/exhaust runners
- **Parallel Sweep Engine**: Run thousands of simulation points across RPM and load ranges efficiently
- **Interactive GUI**: Real-time visualization of engine behavior, parameter sweeps, and analysis
- **REST API & WebSockets**: FastAPI backend for integration with external systems
- **Comprehensive Testing**: Pytest suite with validation against grid convergence studies

## About the Vehicle

**Honda CBR600RR (FSAE Configuration)**
- **Displacement**: 599cc, 4-cylinder, naturally aspirated
- **Max Power**: ~55 kW @ 9000 RPM
- **Max Torque**: ~50 Nm @ 8000 RPM
- **Fuel**: 100 octane through 20mm restrictor (FSAE regulation)
- **ECU**: Link G4X FuryX with full sensor suite and ignition timing control

See [POWERTRAIN_SPEC.md](POWERTRAIN_SPEC.md) for complete technical specifications.

## Installation

### Requirements
- Python 3.9+
- Node.js 18+ (for GUI frontend)

### Setup

```bash
# Clone the repository
git clone https://github.com/NIXELFi/1dMOCEngineSolver.git
cd 1dMOCEngineSolver

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd gui-frontend
npm install
cd ..
```

## Running Simulations

### Command Line

**Single point simulation:**
```bash
python -c "from engine_sim import Simulator; s = Simulator(); s.run(rpm=6000, load=0.8)"
```

**Parameter sweep (RPM range):**
```bash
python _run_sweep.py  # Edit script to configure RPM range and step
```

**Grid convergence study:**
```bash
python _grid_convergence.py
```

### Interactive GUI

Start the simulation server and frontend:

```bash
# Terminal 1: Start FastAPI backend
python main.py  # or specify --port 8000

# Terminal 2: Start React frontend (from gui-frontend/)
npm run dev
```

Then open http://localhost:5173 in your browser.

**GUI Features:**
- Set target RPM, load, and throttle position
- Visualize pressure/temperature throughout intake and exhaust
- Run parameter sweeps with real-time progress
- Export results and plots
- Compare multiple simulation runs

## Project Structure

```
├── engine_sim/               # Core simulation engine
│   ├── moc.py              # Method of Characteristics solver
│   ├── boundaries.py        # Boundary conditions (valves, ports, etc)
│   ├── combustion.py        # Fuel combustion model
│   └── ...
├── gui-backend/            # FastAPI server
│   ├── main.py
│   ├── routes/             # REST API endpoints
│   └── events/             # WebSocket event handling
├── gui-frontend/           # React + TypeScript UI
│   ├── src/components/
│   ├── src/pages/
│   └── package.json
├── tests/                  # Pytest suite
├── sweeps/                 # Cached sweep results (JSON)
├── POWERTRAIN_SPEC.md      # Complete vehicle specifications
└── requirements.txt        # Python dependencies
```

## Testing

Run the test suite:

```bash
pytest                          # Run all tests
pytest tests/test_moc.py        # Run specific test file
pytest -v                       # Verbose output
pytest --cov=engine_sim         # With coverage report
```

Key test categories:
- **MOC Solver**: Grid convergence, boundary conditions, stability
- **Boundaries**: Valve models, port dynamics
- **GUI API**: WebSocket event handling, data persistence
- **Sweep**: Parallel execution, equivalence with serial runs

## Output & Visualization

Simulation results include:
- Pressure traces at all mesh nodes (intake, cylinder, exhaust)
- Temperature distribution through engine cycle
- Power and torque output
- Combustion analysis (burn rate, heat release)
- Inlet/exhaust resonance effects

Results are saved as JSON in `sweeps/` and can be visualized via the GUI or matplotlib scripts:
```bash
python _capture_plots.py      # Generate publication-quality plots
```

## Performance

- **Single point**: ~10-50ms depending on mesh resolution
- **Full sweep (50 points × 12 cycles)**: ~30-60 seconds on modern hardware
- **GUI responsiveness**: Sub-second updates for typical parameter changes

Cython-compiled critical sections ensure fast convergence on the MOC solver.

## Contributing

Contributions welcome! Areas of interest:
- Additional combustion models (Wiebe function variations)
- Turbocharger/supercharger modeling
- Knock detection and detonation boundaries
- Performance optimizations for GPU acceleration

Please submit issues and PRs to the repository.

## License

[Add your license here]

## Authors

Created for FSAE powertrain simulation and analysis.
