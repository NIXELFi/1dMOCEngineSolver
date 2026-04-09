"""In-cylinder heat transfer correlations (Woschni, Annand)."""

from __future__ import annotations

import numpy as np


class WoschniHeatTransfer:
    """Woschni correlation for in-cylinder convective heat transfer.

    h_c = 3.26 * B^(-0.2) * p^(0.8) * T^(-0.53) * w^(0.8)

    Units: h_c [W/m^2/K], B [m], p [kPa], T [K], w [m/s]
    """

    def __init__(self, bore: float, stroke: float, T_wall: float = 450.0):
        self.bore = bore
        self.stroke = stroke
        self.T_wall = T_wall  # K (cylinder wall temperature)

        # Coefficients for characteristic velocity
        self.C1_gas_exchange = 6.18
        self.C1_compression = 2.28
        self.C1_combustion = 2.28
        self.C2_combustion = 3.24e-3

        # Reference state set at IVC
        self.p_ref = None
        self.T_ref = None
        self.V_ref = None

    def set_reference_state(self, p_IVC: float, T_IVC: float, V_IVC: float):
        """Set reference state at IVC for motored pressure calculation."""
        self.p_ref = p_IVC
        self.T_ref = T_IVC
        self.V_ref = V_IVC

    def mean_piston_speed(self, rpm: float) -> float:
        """Mean piston speed S_bar_p = 2*S*N/60 [m/s]."""
        return 2.0 * self.stroke * rpm / 60.0

    def motored_pressure(self, V: float, gamma: float = 1.35) -> float:
        """Motored (polytropic) pressure at volume V.
        p_mot = p_ref * (V_ref/V)^gamma
        """
        if self.p_ref is None or self.V_ref is None:
            return 0.0
        return self.p_ref * (self.V_ref / V) ** gamma

    def characteristic_velocity(
        self, rpm: float, p: float, V: float, V_d: float,
        phase: str = "compression", gamma: float = 1.35
    ) -> float:
        """Compute characteristic velocity w [m/s].

        w = C1*S_p + C2*(V_d*T_r)/(p_r*V_r)*(p - p_mot)

        Args:
            rpm: Engine speed
            p: Instantaneous cylinder pressure (Pa)
            V: Instantaneous cylinder volume (m^3)
            V_d: Displacement volume (m^3)
            phase: 'gas_exchange', 'compression', or 'combustion'
            gamma: Polytropic exponent for motored pressure
        """
        S_p = self.mean_piston_speed(rpm)

        if phase == "gas_exchange":
            return self.C1_gas_exchange * S_p

        p_mot = self.motored_pressure(V, gamma)

        if phase == "compression":
            return self.C1_compression * S_p

        # Combustion / expansion
        if self.p_ref is None or self.V_ref is None:
            return self.C1_combustion * S_p

        pressure_term = self.C2_combustion * (V_d * self.T_ref) / (self.p_ref * self.V_ref)
        pressure_term *= max(p - p_mot, 0.0)
        return self.C1_combustion * S_p + pressure_term

    def heat_transfer_coefficient(
        self, p: float, T: float, rpm: float, V: float, V_d: float,
        phase: str = "compression", gamma: float = 1.35
    ) -> float:
        """Compute Woschni heat transfer coefficient h_c [W/m^2/K].

        h_c = 3.26 * B^(-0.2) * p_kPa^(0.8) * T^(-0.53) * w^(0.8)
        """
        w = self.characteristic_velocity(rpm, p, V, V_d, phase, gamma)
        w = max(w, 0.1)  # prevent zero velocity
        p_kPa = p / 1000.0
        return 3.26 * self.bore**(-0.2) * p_kPa**0.8 * max(T, 100.0)**(-0.53) * w**0.8

    def heat_transfer_rate(
        self, p: float, T_gas: float, A_surface: float, rpm: float,
        V: float, V_d: float, phase: str = "compression", gamma: float = 1.35
    ) -> float:
        """Compute heat transfer rate dQ_ht/dt [W].

        dQ_ht/dt = h_c * A * (T_gas - T_wall)
        """
        h = self.heat_transfer_coefficient(p, T_gas, rpm, V, V_d, phase, gamma)
        return h * A_surface * (T_gas - self.T_wall)

    def heat_transfer_per_crank_angle(
        self, p: float, T_gas: float, A_surface: float, rpm: float,
        V: float, V_d: float, phase: str = "compression", gamma: float = 1.35
    ) -> float:
        """Compute dQ_ht/dtheta [J/rad].

        dQ_ht/dtheta = h_c * A * (T_gas - T_wall) / omega
        """
        omega = 2.0 * np.pi * rpm / 60.0
        return self.heat_transfer_rate(p, T_gas, A_surface, rpm, V, V_d, phase, gamma) / omega
