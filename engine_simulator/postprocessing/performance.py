"""Performance calculations: VE, torque, power, IMEP, BSFC."""

from __future__ import annotations

import numpy as np


def compute_indicated_work(p_array: np.ndarray, V_array: np.ndarray) -> float:
    """Compute indicated work from P-V data using trapezoidal integration.
    W_i = integral(p dV) over the complete cycle.
    """
    return float(np.trapz(p_array, V_array))


def compute_imep(work: float, V_d: float) -> float:
    """Indicated Mean Effective Pressure.
    IMEP = W_i / V_d
    """
    return work / V_d if V_d > 0 else 0.0


def compute_indicated_power(work_per_cycle: float, rpm: float, n_cylinders: int = 4) -> float:
    """Indicated power (W) for a 4-stroke engine.
    P = W_cycle * N / 120  (for 4-stroke, each cylinder fires once per 2 revolutions)
    Total power = n_cyl * P_per_cyl
    """
    return work_per_cycle * rpm / 120.0


def compute_torque(power_W: float, rpm: float) -> float:
    """Torque from power. T = P / omega."""
    omega = 2.0 * np.pi * rpm / 60.0
    return power_W / omega if omega > 0 else 0.0


def compute_volumetric_efficiency(m_air: float, rho_ref: float, V_d: float) -> float:
    """Volumetric efficiency.
    eta_v = m_air / (rho_ref * V_d)
    """
    return m_air / (rho_ref * V_d) if rho_ref * V_d > 0 else 0.0


def compute_bsfc(fuel_flow_rate: float, power_W: float) -> float:
    """Brake Specific Fuel Consumption (g/kWh).
    BSFC = mdot_fuel / P * 3.6e6
    """
    if power_W <= 0:
        return float("inf")
    return fuel_flow_rate / power_W * 3.6e6  # kg/s / W * (g/kg * s/h)


def compute_thermal_efficiency(power_W: float, fuel_flow_rate: float,
                                 q_lhv: float = 44.0e6) -> float:
    """Brake thermal efficiency.
    eta_th = P / (mdot_fuel * Q_LHV)
    """
    heat_input = fuel_flow_rate * q_lhv
    return power_W / heat_input if heat_input > 0 else 0.0


def restrictor_max_mass_flow(
    throat_diameter: float = 0.020,
    Cd: float = 0.95,
    p0: float = 101325.0,
    T0: float = 300.0,
    gamma: float = 1.4,
    R: float = 287.0,
) -> float:
    """Maximum (choked) mass flow through FSAE restrictor."""
    A_throat = np.pi / 4.0 * throat_diameter**2
    choke_factor = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
    return Cd * A_throat * p0 * np.sqrt(gamma / (R * T0)) * choke_factor


def theoretical_max_power(
    mdot_air_max: float,
    afr: float = 13.1,
    q_lhv: float = 44.0e6,
    eta_thermal: float = 0.33,
) -> float:
    """Theoretical maximum power limited by restrictor (W)."""
    mdot_fuel = mdot_air_max / afr
    return mdot_fuel * q_lhv * eta_thermal


def apply_drivetrain_losses(brake_power_W: float, drivetrain_eff: float) -> float:
    """Return wheel power: brake power scaled by drivetrain efficiency.

    Drivetrain efficiency captures losses between the crankshaft and the
    wheels — clutch slip, gearbox/chain friction, differential, bearings.
    For a chain-drive FSAE car, typical values are 0.82–0.88.
    """
    return brake_power_W * drivetrain_eff
