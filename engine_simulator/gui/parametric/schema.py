"""Pydantic request models for parametric study endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from engine_simulator.gui.parametric.parameters import find_parameter

MAX_PARAMETER_VALUES = 200


def resolve_parameter_values(
    start: float, end: float, step: float
) -> list[float]:
    """Generate parameter values from (start, end, step).

    When `step` divides `(end - start)` evenly, the returned list is
    inclusive of `end`. When it does not, the last value is the largest
    `start + i * step` that stays within a half-step tolerance of `end`
    (i.e. nearest-integer rounding of the step count). A `value_step`
    that does not cleanly divide the range will therefore produce a
    sweep that stops short of `value_end`; the schema validation warns
    about this via the divisibility check in ParametricStudyStartRequest.

    Uses index multiplication (`start + i * step`) rather than repeated
    addition to avoid floating-point drift at the endpoint.
    """
    if step <= 0:
        raise ValueError("step must be positive")
    if end < start:
        raise ValueError("end must be >= start")
    # Add a half-step tolerance to make sure the endpoint is included when
    # the range divides cleanly, without overshooting when it doesn't.
    n_steps = int(round((end - start) / step))
    return [start + i * step for i in range(n_steps + 1)]


class ParametricStudyStartRequest(BaseModel):
    """Request body for POST /api/parametric/study/start."""

    name: str = Field(..., min_length=1, max_length=200)
    config_name: str = Field(..., min_length=1, max_length=200)
    parameter_path: str = Field(..., min_length=1, max_length=200)

    value_start: float
    value_end: float
    value_step: float = Field(..., gt=0)

    sweep_rpm_start: float = Field(..., gt=0)
    sweep_rpm_end: float = Field(..., gt=0)
    sweep_rpm_step: float = Field(..., gt=0)
    sweep_n_cycles: int = Field(..., gt=0, le=100)
    n_workers: int = Field(..., gt=0, le=64)

    @field_validator("parameter_path")
    @classmethod
    def _path_in_whitelist(cls, v: str) -> str:
        if find_parameter(v) is None:
            raise ValueError(f"parameter_path {v!r} not in whitelist")
        return v

    @model_validator(mode="after")
    def _check_ranges(self):
        if self.sweep_rpm_end <= self.sweep_rpm_start:
            raise ValueError("sweep_rpm_end must be > sweep_rpm_start")
        if self.value_end <= self.value_start:
            raise ValueError("value_end must be > value_start")
        # Guard against DoS from huge requests: cap the number of points.
        if self.value_step > 0:
            n_approx = round((self.value_end - self.value_start) / self.value_step) + 1
            if n_approx > MAX_PARAMETER_VALUES:
                raise ValueError(
                    f"value range would produce ~{n_approx} points; "
                    f"maximum is {MAX_PARAMETER_VALUES}"
                )
        param = find_parameter(self.parameter_path)
        if param is None:
            return self  # already caught by field_validator
        if param.min_allowed is not None and self.value_start < param.min_allowed:
            raise ValueError(
                f"value_start={self.value_start} below min_allowed={param.min_allowed} "
                f"for {self.parameter_path}"
            )
        if param.max_allowed is not None and self.value_end > param.max_allowed:
            raise ValueError(
                f"value_end={self.value_end} above max_allowed={param.max_allowed} "
                f"for {self.parameter_path}"
            )
        if self.sweep_rpm_step > 0:
            n_rpms = round(
                (self.sweep_rpm_end - self.sweep_rpm_start) / self.sweep_rpm_step
            ) + 1
            if n_rpms > 500:
                raise ValueError(
                    f"RPM range would produce ~{n_rpms} points; maximum is 500"
                )
        return self

    def parameter_values(self) -> list[float]:
        return resolve_parameter_values(
            self.value_start, self.value_end, self.value_step
        )
