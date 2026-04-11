"""Whitelist of sweepable engine-design parameters.

Parameters listed here can be the subject of a parametric study. Paths use
dotted notation into the JSON dict representation of an EngineConfig.

- Dotted:   "plenum.volume"
- Indexed:  "intake_pipes[0].length"
- Wildcard: "intake_pipes[*].length" (applies to all list elements)

`default_range` and all API I/O use storage units (SI). `display_scale` is
a multiplier applied ONLY at the UI boundary — e.g. display_scale=1000 for
a length in meters shows mm to the user. The backend never sees scaled
values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Param:
    path: str                                  # dotted path into config dict
    label: str                                 # human-readable name
    unit: str                                  # display unit label (e.g. "mm", "deg CA")
    default_range: tuple[float, float, float]  # (start, end, step) in storage units
    display_scale: float = 1.0                 # e.g. 1000 to display meters as mm
    min_allowed: Optional[float] = None        # hard safety bound (storage units)
    max_allowed: Optional[float] = None
    category: str = "Other"                    # for UI grouping


SWEEPABLE_PARAMETERS: list[Param] = [
    # ---- Intake pipes (all 4 runners swept together by default) ----
    Param(
        path="intake_pipes[*].length",
        label="Intake Runner Length",
        unit="mm",
        default_range=(0.10, 0.40, 0.025),
        display_scale=1000,
        min_allowed=0.02,
        max_allowed=1.0,
        category="Intake",
    ),
    Param(
        path="intake_pipes[*].diameter",
        label="Intake Runner Diameter",
        unit="mm",
        default_range=(0.030, 0.050, 0.0025),
        display_scale=1000,
        min_allowed=0.015,
        max_allowed=0.080,
        category="Intake",
    ),

    # ---- Exhaust ----
    Param(
        path="exhaust_primaries[*].length",
        label="Exhaust Primary Length",
        unit="mm",
        default_range=(0.25, 0.60, 0.05),
        display_scale=1000,
        min_allowed=0.05,
        max_allowed=1.5,
        category="Exhaust",
    ),
    Param(
        path="exhaust_primaries[*].diameter",
        label="Exhaust Primary Diameter",
        unit="mm",
        default_range=(0.028, 0.045, 0.002),
        display_scale=1000,
        min_allowed=0.015,
        max_allowed=0.080,
        category="Exhaust",
    ),
    Param(
        path="exhaust_secondaries[*].length",
        label="Exhaust Secondary Length",
        unit="mm",
        default_range=(0.20, 0.50, 0.05),
        display_scale=1000,
        min_allowed=0.05,
        max_allowed=1.5,
        category="Exhaust",
    ),
    Param(
        path="exhaust_secondaries[*].diameter",
        label="Exhaust Secondary Diameter",
        unit="mm",
        default_range=(0.035, 0.055, 0.0025),
        display_scale=1000,
        min_allowed=0.020,
        max_allowed=0.100,
        category="Exhaust",
    ),

    # ---- Plenum ----
    Param(
        path="plenum.volume",
        label="Plenum Volume",
        unit="L",
        default_range=(0.0005, 0.004, 0.00025),  # 0.5 L to 4 L in 0.25 L steps
        display_scale=1000,  # m^3 -> L
        min_allowed=0.0001,
        max_allowed=0.02,
        category="Plenum",
    ),

    # ---- Restrictor ----
    Param(
        path="restrictor.discharge_coefficient",
        label="Restrictor Cd",
        unit="",
        default_range=(0.85, 0.98, 0.01),
        display_scale=1.0,
        min_allowed=0.5,
        max_allowed=1.0,
        category="Restrictor",
    ),

    # ---- Valve timing (all in degrees crank angle) ----
    Param(
        path="intake_valve.open_angle",
        label="IVO (BTDC)",
        unit="deg CA",
        default_range=(-20, 30, 5),
        display_scale=1.0,
        min_allowed=-40,
        max_allowed=60,
        category="Valve Timing",
    ),
    Param(
        path="intake_valve.close_angle",
        label="IVC (ABDC)",
        unit="deg CA",
        default_range=(30, 80, 5),
        display_scale=1.0,
        min_allowed=0,
        max_allowed=120,
        category="Valve Timing",
    ),
    Param(
        path="exhaust_valve.open_angle",
        label="EVO (BBDC)",
        unit="deg CA",
        default_range=(30, 80, 5),
        display_scale=1.0,
        min_allowed=0,
        max_allowed=120,
        category="Valve Timing",
    ),
    Param(
        path="exhaust_valve.close_angle",
        label="EVC (ATDC)",
        unit="deg CA",
        default_range=(-20, 30, 5),
        display_scale=1.0,
        min_allowed=-40,
        max_allowed=60,
        category="Valve Timing",
    ),
    Param(
        path="intake_valve.max_lift",
        label="Intake Max Lift",
        unit="mm",
        default_range=(0.006, 0.012, 0.0005),
        display_scale=1000,
        min_allowed=0.002,
        max_allowed=0.020,
        category="Valve Timing",
    ),
    Param(
        path="exhaust_valve.max_lift",
        label="Exhaust Max Lift",
        unit="mm",
        default_range=(0.006, 0.012, 0.0005),
        display_scale=1000,
        min_allowed=0.002,
        max_allowed=0.020,
        category="Valve Timing",
    ),

    # ---- Combustion ----
    Param(
        path="combustion.spark_advance",
        label="Spark Advance",
        unit="deg BTDC",
        default_range=(10, 40, 2),
        display_scale=1.0,
        min_allowed=0,
        max_allowed=60,
        category="Combustion",
    ),
    Param(
        path="combustion.combustion_duration",
        label="Burn Duration",
        unit="deg CA",
        default_range=(30, 70, 5),
        display_scale=1.0,
        min_allowed=10,
        max_allowed=120,
        category="Combustion",
    ),
    Param(
        path="combustion.afr_target",
        label="Target AFR",
        unit="",
        default_range=(11.5, 14.7, 0.25),
        display_scale=1.0,
        min_allowed=8.0,
        max_allowed=18.0,
        category="Combustion",
    ),
]


def find_parameter(path: str) -> Optional[Param]:
    """Return the Param with the given path, or None if not whitelisted."""
    for p in SWEEPABLE_PARAMETERS:
        if p.path == path:
            return p
    return None


def to_api_dict(param: Param) -> dict:
    """Serialize a Param to a JSON-friendly dict for the API."""
    return {
        "path": param.path,
        "label": param.label,
        "unit": param.unit,
        "default_range": list(param.default_range),
        "display_scale": param.display_scale,
        "min_allowed": param.min_allowed,
        "max_allowed": param.max_allowed,
        "category": param.category,
    }
