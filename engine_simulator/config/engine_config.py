"""Engine configuration dataclasses and JSON loader."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CylinderConfig:
    bore: float  # m
    stroke: float  # m
    con_rod_length: float  # m
    compression_ratio: float
    n_intake_valves: int = 2
    n_exhaust_valves: int = 2


@dataclass
class ValveConfig:
    diameter: float  # m
    max_lift: float  # m
    open_angle: float  # degrees crank angle (0 = TDC firing)
    close_angle: float  # degrees crank angle
    seat_angle: float = 45.0  # degrees

    # Cd lookup: list of (L/D, Cd) pairs
    cd_table: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class PipeConfig:
    name: str
    length: float  # m
    diameter: float  # m (or inlet diameter for tapered)
    diameter_out: Optional[float] = None  # m (for tapered pipes, None = constant)
    n_points: int = 30
    wall_temperature: float = 320.0  # K
    roughness: float = 0.03e-3  # m (surface roughness for friction)


@dataclass
class CombustionConfig:
    # SDM26 powertrain: 100-octane race gasoline, Link G4X FuryX ignition,
    # MAP vs RPM map with 15 deg base, 40 deg max advance.
    wiebe_a: float = 5.0
    wiebe_m: float = 2.0
    combustion_duration: float = 50.0  # degrees crank angle
    spark_advance: float = 25.0  # degrees BTDC (positive) — typical mid-RPM operating point
    ignition_delay: float = 7.0  # degrees after spark
    combustion_efficiency: float = 0.96
    q_lhv: float = 43.5e6  # J/kg (100-octane racing gasoline LHV)
    afr_stoich: float = 14.7
    afr_target: float = 13.1  # slightly rich for power (Deatschwerks 300cc injector)


@dataclass
class RestrictorConfig:
    throat_diameter: float = 0.020  # m (FSAE 20 mm)
    # Vapor-smoothed ASA insert (Ra ~10 µm → ~1 µm) measured on the static
    # flow bench at +1.8 % vs the as-printed baseline (0.95 × 1.018 ≈ 0.967).
    discharge_coefficient: float = 0.967
    converging_half_angle: float = 12.0  # degrees
    diverging_half_angle: float = 6.0  # degrees


@dataclass
class PlenumConfig:
    # SDM26 intake plenum: 1.5 L
    volume: float = 1.5e-3  # m^3 (1.5 liters)
    initial_pressure: float = 101325.0  # Pa
    initial_temperature: float = 300.0  # K


@dataclass
class JunctionConfig:
    name: str
    pipe_names: list[str]  # names of pipes meeting at junction
    pipe_signs: list[int]  # +1 if pipe end faces junction, -1 if pipe start


@dataclass
class SimulationConfig:
    rpm_start: float = 6000.0
    rpm_end: float = 13500.0
    rpm_step: float = 500.0
    n_cycles: int = 12
    cfl_number: float = 0.85
    convergence_tolerance: float = 0.005  # 0.5%
    crank_step_max: float = 1.0  # max degrees per substep for cylinder ODE
    # Artificial viscosity (Laplacian smoothing) coefficient applied to lam,
    # bet in the MOC interior advance. Damps the closed-end (intake-valve)
    # standing wave whose amplitude would otherwise grow unphysically — the
    # 1D Benson MOC has no native acoustic absorption to model the 3D
    # dissipation a real plenum provides. ~0.05 is mild, ~0.15 is firm.
    artificial_viscosity: float = 0.05


@dataclass
class EngineConfig:
    # SDM26 powertrain: Honda CBR600RR, 599cc, FSAE 20mm restricted.
    # See POWERTRAIN_SPEC.md for full vehicle spec sheet.
    name: str = "Honda CBR600RR (SDM26)"
    n_cylinders: int = 4
    firing_order: list[int] = field(default_factory=lambda: [1, 2, 4, 3])
    firing_interval: float = 180.0  # degrees (even firing inline-4)

    cylinder: CylinderConfig = field(
        default_factory=lambda: CylinderConfig(
            bore=0.067,           # 67.0 mm
            stroke=0.0425,        # 42.5 mm
            con_rod_length=0.0963,
            compression_ratio=12.7,  # SDM26 spec sheet
        )
    )

    # Cd tables: bench-measured values (0.20…0.60 at peak L/D) multiplied by
    # an in-engine effective-Cd factor of 0.78. 1D MOC misses several real
    # losses (port-to-runner sudden contraction, valve seat / port radius,
    # boundary-layer separation around the back side of the valve, secondary
    # flow rotation, finite-amplitude inertial effects), so the on-engine
    # effective Cd is typically 70–85 % of the static-bench Cd. 0.78 lands
    # peak brake power around 71 hp at 8000 RPM, which is close to the
    # SDM26 team's chassis-dyno expectation.
    intake_valve: ValveConfig = field(
        default_factory=lambda: ValveConfig(
            diameter=0.0275,
            max_lift=0.0081,
            open_angle=338.0,
            close_angle=583.0,
            cd_table=[
                (0.05, 0.156),  # 0.20 × 0.78
                (0.10, 0.312),  # 0.40 × 0.78
                (0.15, 0.406),  # 0.52 × 0.78
                (0.20, 0.452),  # 0.58 × 0.78
                (0.25, 0.468),  # 0.60 × 0.78
                (0.30, 0.468),
            ],
        )
    )

    exhaust_valve: ValveConfig = field(
        default_factory=lambda: ValveConfig(
            diameter=0.023,
            max_lift=0.00692,
            open_angle=140.0,
            close_angle=365.0,
            cd_table=[
                (0.05, 0.140),  # 0.18 × 0.78
                (0.10, 0.273),  # 0.35 × 0.78
                (0.15, 0.374),  # 0.48 × 0.78
                (0.20, 0.429),  # 0.55 × 0.78
                (0.25, 0.445),  # 0.57 × 0.78
                (0.30, 0.452),  # 0.58 × 0.78
            ],
        )
    )

    # SDM26 intake runners: 245 mm long. POWERTRAIN_SPEC.md describes a
    # 40 mm → 32 mm taper but the current MOC area-source-term handling is
    # not robust to that gradient (collapses the plenum, and even mild
    # tapers like 40 → 36 mm give erratic plenum-pressure behavior across
    # RPM — the source term is unstable for any non-trivial dF/dx). Using
    # the area-weighted equivalent constant diameter of 36 mm here so the
    # runner volume + average flow area match the spec without triggering
    # the area-source bug. TODO: rewrite the area source as an implicit
    # / two-step (predictor–corrector) integration to make the taper work.
    intake_pipes: list[PipeConfig] = field(
        default_factory=lambda: [
            PipeConfig(
                name=f"intake_runner_{i+1}",
                length=0.245,
                diameter=0.036,
                n_points=30,
                wall_temperature=325.0,
            )
            for i in range(4)
        ]
    )

    # SDM26 4-2-1 exhaust: effective runner lengths 308 mm (primary) + 84 mm (secondary)
    # for a total path of 392 mm from valve to collector. Primary 31.8 mm OD,
    # secondary 38.1 mm OD. Per-cylinder length variation +/-3 mm baked in by averaging.
    exhaust_primaries: list[PipeConfig] = field(
        default_factory=lambda: [
            PipeConfig(
                name=f"exhaust_primary_{i+1}",
                length=0.308,
                diameter=0.0318,
                n_points=30,
                wall_temperature=650.0,
            )
            for i in range(4)
        ]
    )

    exhaust_secondaries: list[PipeConfig] = field(
        default_factory=lambda: [
            PipeConfig(
                name=f"exhaust_secondary_{i+1}",
                length=0.084,
                diameter=0.0381,
                n_points=15,
                wall_temperature=550.0,
            )
            for i in range(2)
        ]
    )

    # Tapered collector: 38.1 mm at the secondary merge expanding to 50.8 mm at muffler
    exhaust_collector: PipeConfig = field(
        default_factory=lambda: PipeConfig(
            name="exhaust_collector",
            length=0.400,
            diameter=0.0381,
            diameter_out=0.0508,
            n_points=20,
            wall_temperature=500.0,
        )
    )

    combustion: CombustionConfig = field(default_factory=CombustionConfig)
    restrictor: RestrictorConfig = field(default_factory=RestrictorConfig)
    plenum: PlenumConfig = field(default_factory=PlenumConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)

    # Ambient conditions
    p_ambient: float = 101325.0  # Pa
    T_ambient: float = 300.0  # K

    # Drivetrain efficiency: fraction of crank brake power that reaches the
    # wheels. Accounts for clutch, gearbox, chain/sprocket, diff, bearings.
    # Default 1.0 = layer disabled (wheel == brake). The simulator's brake
    # number is already close to the team's dyno expectation, so the wheel
    # layer is opt-in: set to a value < 1.0 (e.g. 0.85 for a chain-drive
    # FSAE car) when comparing against an actual chassis-dyno measurement.
    drivetrain_efficiency: float = 1.0

    def __post_init__(self) -> None:
        if not (0.0 < self.drivetrain_efficiency <= 1.0):
            raise ValueError(
                f"drivetrain_efficiency must be in (0, 1], got "
                f"{self.drivetrain_efficiency}"
            )


def _valve_from_dict(d: dict) -> ValveConfig:
    cd = [tuple(pair) for pair in d.pop("cd_table", [])]
    return ValveConfig(**d, cd_table=cd)


def _pipe_from_dict(d: dict) -> PipeConfig:
    return PipeConfig(**d)


def load_config(path: str | Path) -> EngineConfig:
    """Load engine configuration from a JSON file."""
    with open(path, "r") as f:
        data = json.load(f)

    cfg = EngineConfig(
        name=data.get("name", "Custom Engine"),
        n_cylinders=data.get("n_cylinders", 4),
        firing_order=data.get("firing_order", [1, 2, 4, 3]),
        firing_interval=data.get("firing_interval", 180.0),
        cylinder=CylinderConfig(**data["cylinder"]),
        intake_valve=_valve_from_dict(dict(data["intake_valve"])),
        exhaust_valve=_valve_from_dict(dict(data["exhaust_valve"])),
        intake_pipes=[_pipe_from_dict(p) for p in data["intake_pipes"]],
        exhaust_primaries=[_pipe_from_dict(p) for p in data["exhaust_primaries"]],
        exhaust_secondaries=[_pipe_from_dict(p) for p in data["exhaust_secondaries"]],
        exhaust_collector=_pipe_from_dict(data["exhaust_collector"]),
        combustion=CombustionConfig(**data["combustion"]),
        restrictor=RestrictorConfig(**data["restrictor"]),
        plenum=PlenumConfig(**data["plenum"]),
        simulation=SimulationConfig(**data["simulation"]),
        p_ambient=data.get("p_ambient", 101325.0),
        T_ambient=data.get("T_ambient", 300.0),
    )
    return cfg
