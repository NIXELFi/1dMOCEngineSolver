import os
os.environ['MPLBACKEND'] = 'Agg'
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator
cfg = EngineConfig()
sim = SimulationOrchestrator(cfg)
sweep = sim.run_rpm_sweep(rpm_start=6000, rpm_end=13000, rpm_step=1000, n_cycles=12, verbose=True)
