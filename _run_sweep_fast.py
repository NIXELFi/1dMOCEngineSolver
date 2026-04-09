"""Fast sweep — fewer cycles, write to stdout incrementally."""
import os
import sys
os.environ['MPLBACKEND'] = 'Agg'
sys.stdout.reconfigure(line_buffering=True)
from engine_simulator.config.engine_config import EngineConfig
from engine_simulator.simulation.orchestrator import SimulationOrchestrator

cfg = EngineConfig()
sim = SimulationOrchestrator(cfg)
results = []
for rpm in [6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000]:
    print(f"\n--- {rpm} RPM ---", flush=True)
    perf = sim.run_single_rpm(rpm, n_cycles=8, verbose=True)
    print(
        f"  P_ind={perf['indicated_power_hp']:5.1f} hp  "
        f"P_brk={perf['brake_power_hp']:5.1f} hp  "
        f"T_brk={perf['brake_torque_Nm']:5.1f} Nm  "
        f"VE_atm={perf['volumetric_efficiency_atm']*100:5.1f}%  "
        f"VE_plen={perf['volumetric_efficiency_plenum']*100:5.1f}%  "
        f"IMEP={perf['imep_bar']:.2f}  "
        f"p_plen={perf['plenum_pressure_bar']:.3f}  "
        f"chk={perf['restrictor_choked']}",
        flush=True,
    )
    results.append(perf)

print("\n=== SUMMARY ===", flush=True)
print(f"{'RPM':>6} {'P_ind':>7} {'P_brk':>7} {'T_brk':>7} {'VE_atm':>7} {'VE_plen':>8} {'IMEP':>5} {'pPlen':>6}")
for r in results:
    print(
        f"{r['rpm']:6.0f} {r['indicated_power_hp']:7.1f} {r['brake_power_hp']:7.1f} "
        f"{r['brake_torque_Nm']:7.1f} {r['volumetric_efficiency_atm']*100:7.1f} "
        f"{r['volumetric_efficiency_plenum']*100:8.1f} {r['imep_bar']:5.2f} "
        f"{r['plenum_pressure_bar']:6.3f}"
    )
