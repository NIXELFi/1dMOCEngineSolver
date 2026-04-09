"""Pydantic models mirroring engine_simulator/config/engine_config.py.

Used by the GUI's PUT/POST config endpoints for validation. The parallel
schema is intentional — runtime introspection of the dataclasses is fragile
(loses field constraints, awkward Optional/list handling, no cross-field
rules). The drift between this file and engine_config.py is caught by
test_pydantic_round_trip in tests/test_config_schema.py.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CylinderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bore: float = Field(gt=0)
    stroke: float = Field(gt=0)
    con_rod_length: float = Field(gt=0)
    compression_ratio: float = Field(gt=1)
    n_intake_valves: int = Field(default=2, ge=1)
    n_exhaust_valves: int = Field(default=2, ge=1)


class ValveModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diameter: float = Field(gt=0)
    max_lift: float = Field(gt=0)
    open_angle: float = Field(ge=0)
    close_angle: float = Field(ge=0)
    seat_angle: float = Field(default=45.0, ge=0, le=90)
    cd_table: list[tuple[float, float]] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_angles(self):
        if self.close_angle <= self.open_angle:
            raise ValueError("close_angle must exceed open_angle")
        return self


class PipeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    length: float = Field(gt=0)
    diameter: float = Field(gt=0)
    diameter_out: Optional[float] = Field(default=None, gt=0)
    n_points: int = Field(default=30, ge=2, le=200)
    wall_temperature: float = Field(default=320.0, gt=0)
    roughness: float = Field(default=0.03e-3, ge=0)


class CombustionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wiebe_a: float = Field(default=5.0, gt=0)
    wiebe_m: float = Field(default=2.0, gt=0)
    combustion_duration: float = Field(default=50.0, gt=0, le=180)
    spark_advance: float = Field(default=25.0)
    ignition_delay: float = Field(default=7.0, ge=0)
    combustion_efficiency: float = Field(default=0.96, gt=0, le=1)
    q_lhv: float = Field(default=43.5e6, gt=0)
    afr_stoich: float = Field(default=14.7, gt=0)
    afr_target: float = Field(default=13.1, gt=0)


class RestrictorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    throat_diameter: float = Field(default=0.020, gt=0)
    discharge_coefficient: float = Field(default=0.967, gt=0, le=1)
    converging_half_angle: float = Field(default=12.0, gt=0, lt=90)
    diverging_half_angle: float = Field(default=6.0, gt=0, lt=90)


class PlenumModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    volume: float = Field(default=1.5e-3, gt=0)
    initial_pressure: float = Field(default=101325.0, gt=0)
    initial_temperature: float = Field(default=300.0, gt=0)


class SimulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rpm_start: float = Field(default=6000.0, gt=0)
    rpm_end: float = Field(default=13500.0, gt=0)
    rpm_step: float = Field(default=500.0, gt=0)
    n_cycles: int = Field(default=12, ge=1, le=200)
    cfl_number: float = Field(default=0.85, gt=0, le=1)
    convergence_tolerance: float = Field(default=0.005, gt=0)
    crank_step_max: float = Field(default=1.0, gt=0)
    artificial_viscosity: float = Field(default=0.05, ge=0)

    @model_validator(mode="after")
    def _check_rpm_range(self):
        if self.rpm_end <= self.rpm_start:
            raise ValueError("rpm_end must exceed rpm_start")
        return self


class EnginePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Custom Engine", min_length=1)
    n_cylinders: int = Field(default=4, ge=1)
    firing_order: list[int] = Field(default_factory=lambda: [1, 2, 4, 3], min_length=1)
    firing_interval: float = Field(default=180.0, gt=0)
    cylinder: CylinderModel
    intake_valve: ValveModel
    exhaust_valve: ValveModel
    intake_pipes: list[PipeModel] = Field(min_length=1)
    exhaust_primaries: list[PipeModel] = Field(min_length=1)
    exhaust_secondaries: list[PipeModel] = Field(min_length=1)
    exhaust_collector: PipeModel
    combustion: CombustionModel = Field(default_factory=CombustionModel)
    restrictor: RestrictorModel = Field(default_factory=RestrictorModel)
    plenum: PlenumModel = Field(default_factory=PlenumModel)
    simulation: SimulationModel = Field(default_factory=SimulationModel)
    p_ambient: float = Field(default=101325.0, gt=0)
    T_ambient: float = Field(default=300.0, gt=0)
    drivetrain_efficiency: float = Field(default=1.0, gt=0, le=1)
