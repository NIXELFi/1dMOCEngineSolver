"""Thermodynamic gas property functions.

All functions use SI units throughout.
"""

from __future__ import annotations

import numpy as np

# Universal gas constant
R_UNIVERSAL = 8.314  # J/(mol·K)

# Specific gas constants
R_AIR = 287.0  # J/(kg·K)
R_BURNED = 295.0  # J/(kg·K) (approximate for burned stoich gasoline-air)

# Reference conditions (Benson formulation)
P_REF = 101325.0  # Pa
T_REF = 300.0  # K
GAMMA_REF = 1.4
A_REF = np.sqrt(GAMMA_REF * R_AIR * T_REF)  # ~347.2 m/s
RHO_REF = P_REF / (R_AIR * T_REF)  # ~1.177 kg/m^3


def gamma_unburned(T: float | np.ndarray) -> float | np.ndarray:
    """Ratio of specific heats for unburned air-fuel mixture (300-900 K)."""
    return 1.38 - 1.2e-4 * (np.clip(T, 300, 900) - 300)


def gamma_burned(T: float | np.ndarray) -> float | np.ndarray:
    """Ratio of specific heats for burned gas (900-3000 K)."""
    return 1.30 - 8.0e-5 * (np.clip(T, 300, 3000) - 300)


def gamma_mixture(T: float | np.ndarray, x_b: float) -> float | np.ndarray:
    """Mass-weighted gamma during combustion."""
    return (1.0 - x_b) * gamma_unburned(T) + x_b * gamma_burned(T)


def R_mixture(x_b: float) -> float:
    """Mass-weighted gas constant during combustion."""
    return (1.0 - x_b) * R_AIR + x_b * R_BURNED


def speed_of_sound(gamma: float | np.ndarray, R: float, T: float | np.ndarray) -> float | np.ndarray:
    """Speed of sound: a = sqrt(gamma * R * T)."""
    return np.sqrt(gamma * R * np.maximum(T, 1.0))


def dynamic_viscosity(T: float | np.ndarray) -> float | np.ndarray:
    """Dynamic viscosity of air via Sutherland-like power law.
    mu ~ 1.8e-5 * (T/293)^0.7  Pa·s
    """
    return 1.8e-5 * (T / 293.0) ** 0.7


def thermal_conductivity(T: float | np.ndarray) -> float | np.ndarray:
    """Thermal conductivity of air.
    k ~ 0.026 * (T/300)^0.7  W/(m·K)
    """
    return 0.026 * (T / 300.0) ** 0.7


def prandtl_number() -> float:
    """Prandtl number for air (approximately constant)."""
    return 0.71


def friction_factor_blasius(Re: float | np.ndarray) -> float | np.ndarray:
    """Darcy friction factor via Blasius correlation (smooth pipe, Re < 1e5).
    f = 0.3164 * Re^(-0.25)
    Falls back to laminar (64/Re) for Re < 4000, and a minimum floor.
    """
    Re = np.asarray(Re, dtype=float)
    f = np.where(
        Re < 2300,
        np.where(Re > 1.0, 64.0 / np.maximum(Re, 1.0), 0.0),
        0.3164 * np.maximum(Re, 1.0) ** (-0.25),
    )
    return f


def nusselt_dittus_boelter(Re: float | np.ndarray, Pr: float = 0.71) -> float | np.ndarray:
    """Nusselt number via Dittus-Boelter correlation.
    Nu = 0.023 * Re^0.8 * Pr^0.4
    """
    Re = np.maximum(np.asarray(Re, dtype=float), 1.0)
    return 0.023 * Re**0.8 * Pr**0.4


def pipe_heat_transfer_coeff(Re: float | np.ndarray, T: float | np.ndarray, D: float) -> float | np.ndarray:
    """Convective heat transfer coefficient in a pipe.
    h = Nu * k / D
    """
    Nu = nusselt_dittus_boelter(Re)
    k = thermal_conductivity(T)
    return Nu * k / D


# ---- Benson non-dimensional conversions ----

def to_nondim_A(a: float | np.ndarray) -> float | np.ndarray:
    """Convert dimensional speed of sound to non-dimensional A = a/a_ref."""
    return a / A_REF


def to_nondim_U(u: float | np.ndarray) -> float | np.ndarray:
    """Convert dimensional velocity to non-dimensional U = u/a_ref."""
    return u / A_REF


def to_dim_a(A: float | np.ndarray) -> float | np.ndarray:
    """Convert non-dimensional A to dimensional speed of sound."""
    return A * A_REF


def to_dim_u(U: float | np.ndarray) -> float | np.ndarray:
    """Convert non-dimensional U to dimensional velocity."""
    return U * A_REF


def lambda_from_AU(A: np.ndarray, U: np.ndarray, gamma: float = GAMMA_REF) -> np.ndarray:
    """Compute Riemann variable lambda = A + (gamma-1)/2 * U."""
    return A + 0.5 * (gamma - 1.0) * U


def beta_from_AU(A: np.ndarray, U: np.ndarray, gamma: float = GAMMA_REF) -> np.ndarray:
    """Compute Riemann variable beta = A - (gamma-1)/2 * U."""
    return A - 0.5 * (gamma - 1.0) * U


def AU_from_riemann(lam: np.ndarray, bet: np.ndarray, gamma: float = GAMMA_REF):
    """Recover A, U from Riemann variables lambda, beta."""
    A = (lam + bet) / 2.0
    U = (lam - bet) / (gamma - 1.0)
    return A, U


def pressure_from_A_AA(A: np.ndarray, AA: np.ndarray, gamma: float = GAMMA_REF) -> np.ndarray:
    """Pressure from non-dimensional speed of sound and entropy level.
    p/p_ref = (A/AA)^(2*gamma/(gamma-1))
    """
    ratio = np.maximum(A / np.maximum(AA, 1e-12), 1e-12)
    return P_REF * ratio ** (2.0 * gamma / (gamma - 1.0))


def temperature_from_A_AA(A: np.ndarray, AA: np.ndarray = None) -> np.ndarray:
    """Temperature from non-dimensional speed of sound.

    In the Benson non-homentropic formulation, A = a/a_ref where a = sqrt(γRT),
    so T = T_ref · A². Temperature depends ONLY on A (not AA); the entropy
    parameter AA enters the (A, AA)→p relation but not (A→T).
    The AA argument is accepted for backward compatibility but ignored.
    """
    A_safe = np.maximum(A, 1e-12)
    return T_REF * A_safe ** 2


def density_from_A_AA(A: np.ndarray, AA: np.ndarray, gamma: float = GAMMA_REF) -> np.ndarray:
    """Density from non-dimensional speed of sound and entropy level.

    Computed as ρ = p/(RT) using the corrected Benson relations:
        T = T_ref · A²
        p = p_ref · (A/AA)^(2γ/(γ-1))
        ρ = p / (R · T) = ρ_ref · (A/AA)^(2γ/(γ-1)) / A²
    """
    A_safe = np.maximum(A, 1e-12)
    ratio = np.maximum(A_safe / np.maximum(AA, 1e-12), 1e-12)
    p_val = P_REF * ratio ** (2.0 * gamma / (gamma - 1.0))
    T_val = T_REF * A_safe ** 2
    return p_val / (R_AIR * T_val)


def A_from_pressure(p: float | np.ndarray, AA: float | np.ndarray = 1.0,
                     gamma: float = GAMMA_REF) -> float | np.ndarray:
    """Non-dimensional speed of sound from pressure and entropy level."""
    return AA * (p / P_REF) ** ((gamma - 1.0) / (2.0 * gamma))


def AA_from_p_T(p: float | np.ndarray, T: float | np.ndarray,
                 gamma: float = GAMMA_REF) -> float | np.ndarray:
    """Entropy parameter AA for a gas at the given (p, T).

    Inverts AA = A · (P_ref/p)^((γ-1)/(2γ)) using A = sqrt(T/T_ref):
        AA = sqrt(T/T_ref) · (P_ref/p)^((γ-1)/(2γ))

    For (P_ref, T_ref): AA = 1.   For sub-atmospheric gas at ambient T: AA > 1.
    """
    A = np.sqrt(np.maximum(T, 1.0) / T_REF)
    return A * (P_REF / np.maximum(p, 1.0)) ** ((gamma - 1.0) / (2.0 * gamma))
