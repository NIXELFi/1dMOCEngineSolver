"""0D cylinder thermodynamic model.

Integrates pressure, temperature, and mass using the first law of thermodynamics
for both closed-cycle (compression/combustion/expansion) and open-cycle (gas exchange).
"""

from __future__ import annotations

import numpy as np

from engine_simulator.config.engine_config import CylinderConfig, CombustionConfig
from engine_simulator.engine.geometry import EngineGeometry
from engine_simulator.engine.combustion import WiebeCombustion
from engine_simulator.engine.heat_transfer import WoschniHeatTransfer
from engine_simulator.engine.valve import Valve
from engine_simulator.gas_dynamics.gas_properties import R_AIR, gamma_mixture, R_mixture


class CylinderModel:
    """0D thermodynamic model of a single engine cylinder."""

    def __init__(
        self,
        cyl_cfg: CylinderConfig,
        comb_cfg: CombustionConfig,
        intake_valve: Valve,
        exhaust_valve: Valve,
        cylinder_id: int = 0,
        phase_offset: float = 0.0,
    ):
        self.id = cylinder_id
        self.phase_offset = phase_offset  # degrees (for multi-cylinder phasing)

        self.geometry = EngineGeometry(cyl_cfg)
        self.combustion = WiebeCombustion(comb_cfg)
        self.heat_transfer = WoschniHeatTransfer(
            bore=cyl_cfg.bore, stroke=cyl_cfg.stroke
        )
        self.intake_valve = intake_valve
        self.exhaust_valve = exhaust_valve

        # State variables
        self.p = 101325.0  # Pa
        self.T = 300.0  # K
        self.m = 0.0  # kg (total gas mass in cylinder)
        self.m_fuel = 0.0  # kg (trapped fuel mass for combustion)
        self.x_b = 0.0  # mass fraction burned

        # Derived
        self.V = self.geometry.V_c + self.geometry.V_d  # start at BDC
        self.gamma = 1.38

        # Tracking
        self.m_intake_total = 0.0  # cumulative intake mass per cycle
        self.m_exhaust_total = 0.0
        self.work_cycle = 0.0  # J, accumulated over a cycle
        self.p_at_IVC = 101325.0
        self.T_at_IVC = 300.0

        # Flow to/from this cycle step (set by boundary conditions)
        self.mdot_intake = 0.0  # kg/s into cylinder
        self.mdot_exhaust = 0.0  # kg/s out of cylinder

        # Intake/exhaust conditions (set by pipe boundaries)
        self.T_intake = 300.0  # K
        self.T_exhaust = 900.0  # K (temperature of gas leaving)

    def local_theta(self, global_theta: float) -> float:
        """Convert global crank angle to this cylinder's local angle."""
        return (global_theta - self.phase_offset) % 720.0

    def initialize(self, p: float = 101325.0, T: float = 300.0, theta_deg: float = 0.0):
        """Set initial conditions."""
        self.p = p
        self.T = T
        local_theta = self.local_theta(theta_deg)
        self.V = self.geometry.volume(local_theta)
        R = R_AIR
        self.m = p * self.V / (R * T)
        self.x_b = 0.0
        self.gamma = gamma_mixture(T, self.x_b)
        self.m_fuel = 0.0
        self.m_intake_total = 0.0
        self.m_exhaust_total = 0.0
        self.work_cycle = 0.0

    def _determine_phase(self, theta_local: float) -> str:
        """Determine cycle phase from local crank angle."""
        iv_open = self.intake_valve.is_open(theta_local)
        ev_open = self.exhaust_valve.is_open(theta_local)

        if iv_open or ev_open:
            return "gas_exchange"

        # Closed valves: check if combustion is active
        if self.combustion.is_combusting(theta_local):
            return "combustion"

        # Between IVC and TDC firing: compression
        # IVC at ~583°, combustion starts at ~702° (= -18° + 720°)
        ivc = self.intake_valve.close_angle % 720.0
        evo = self.exhaust_valve.open_angle % 720.0
        if ivc < theta_local < 720.0 and not self.combustion.is_combusting(theta_local):
            return "compression"

        # After combustion ends (~32°), before EVO (~140°): expansion
        return "expansion"

    def advance(self, theta_deg: float, dtheta_deg: float, rpm: float):
        """Advance cylinder state by dtheta degrees.

        Uses 4th-order Runge-Kutta integration of the cylinder ODEs.

        Args:
            theta_deg: Current global crank angle (degrees)
            dtheta_deg: Crank angle increment (degrees)
            rpm: Engine speed (RPM)
        """
        theta_local = self.local_theta(theta_deg)
        omega = 2.0 * np.pi * rpm / 60.0
        dt = np.radians(dtheta_deg) / omega if omega > 0 else 0.0

        phase = self._determine_phase(theta_local)
        gam = gamma_mixture(self.T, self.x_b)
        self.gamma = gam
        R = R_mixture(self.x_b)

        V = self.geometry.volume(theta_local)
        dVdt = self.geometry.dVdtheta(theta_local) * omega  # m^3/s

        # Heat transfer
        A_surf = self.geometry.surface_area(theta_local)
        ht_phase = "combustion" if phase in ("combustion", "expansion") else phase
        if phase == "expansion":
            ht_phase = "combustion"  # still use combustion coefficients
        h_coeff = self.heat_transfer.heat_transfer_coefficient(
            self.p, self.T, rpm, V, self.geometry.V_d, ht_phase, gam
        )
        dQht_dt = h_coeff * A_surf * (self.T - self.heat_transfer.T_wall)

        # Combustion heat release
        dQcomb_dt = 0.0
        if phase == "combustion" and self.m_fuel > 0:
            dxb_dtheta = self.combustion.burn_rate(theta_local)  # 1/degree
            dxb_dt = dxb_dtheta * omega * 180.0 / np.pi  # 1/s (degrees/s * 1/degree)
            dQcomb_dt = self.combustion.combustion_efficiency * self.m_fuel * self.combustion.q_lhv * dxb_dt
            self.x_b = self.combustion.mass_fraction_burned(theta_local)

        if phase == "gas_exchange":
            # Open cycle equations
            mdot_in = self.mdot_intake  # kg/s (set by valve BC)
            mdot_out = self.mdot_exhaust

            # dp/dt (open cycle)
            dp_dt = (1.0 / V) * (
                -gam * self.p * dVdt
                + (gam - 1.0) * (dQcomb_dt - dQht_dt)
                + gam * R * self.T_intake * mdot_in
                - gam * R * self.T * mdot_out
            )

            # dm/dt
            dm_dt = mdot_in - mdot_out

            # dT/dt from ideal gas relation
            if self.m > 1e-10:
                dT_dt = self.T * (dp_dt / self.p + dVdt / V - dm_dt / self.m)
            else:
                dT_dt = 0.0

            # Euler integration for gas exchange (simpler, adequate for open cycle)
            self.p += dp_dt * dt
            self.m += dm_dt * dt
            self.T += dT_dt * dt

            # Track mass flows
            self.m_intake_total += mdot_in * dt
            self.m_exhaust_total += mdot_out * dt

        else:
            # Closed cycle (no mass flow): RK4 integration
            # State: [p] (T derived from ideal gas)
            # dp/dtheta = -gamma*(p/V)*dV/dtheta + (gamma-1)/V*(dQcomb/dtheta - dQht/dtheta)

            def dpdt_func(p_local, theta_l):
                V_l = self.geometry.volume(theta_l)
                dVdth_l = self.geometry.dVdtheta(theta_l)
                T_l = p_local * V_l / (self.m * R) if self.m > 1e-10 else self.T

                # Heat transfer at this state
                A_s = self.geometry.surface_area(theta_l)
                h_c = self.heat_transfer.heat_transfer_coefficient(
                    p_local, T_l, rpm, V_l, self.geometry.V_d, ht_phase, gam
                )
                dQht = h_c * A_s * (T_l - self.heat_transfer.T_wall) / omega  # J/rad

                # Combustion
                dQcomb = 0.0
                if self.combustion.is_combusting(theta_l) and self.m_fuel > 0:
                    dxb = self.combustion.burn_rate(theta_l)  # 1/degree
                    # Convert: dQ/dtheta(rad) = eta * m_f * Q_LHV * dxb(1/deg) * (180/pi)
                    dQcomb = (
                        self.combustion.combustion_efficiency
                        * self.m_fuel
                        * self.combustion.q_lhv
                        * dxb
                        * 180.0
                        / np.pi
                    )  # J/rad

                return -gam * p_local / V_l * dVdth_l + (gam - 1.0) / V_l * (dQcomb - dQht)

            # RK4 in crank angle
            dth_rad = np.radians(dtheta_deg)
            th0 = theta_local

            k1 = dpdt_func(self.p, th0)
            k2 = dpdt_func(self.p + 0.5 * dth_rad * k1, th0 + 0.5 * dtheta_deg)
            k3 = dpdt_func(self.p + 0.5 * dth_rad * k2, th0 + 0.5 * dtheta_deg)
            k4 = dpdt_func(self.p + dth_rad * k3, th0 + dtheta_deg)

            self.p += dth_rad / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        # Update volume and temperature
        theta_new = self.local_theta(theta_deg + dtheta_deg)
        self.V = self.geometry.volume(theta_new)
        if self.m > 1e-10:
            self.T = self.p * self.V / (self.m * R)
        self.T = max(self.T, 200.0)
        self.p = max(self.p, 1000.0)

        # Track work
        self.work_cycle += self.p * dVdt * dt

        # Set reference state at IVC for Woschni
        ivc = self.intake_valve.close_angle
        if theta_local <= ivc < theta_local + dtheta_deg:
            self.p_at_IVC = self.p
            self.T_at_IVC = self.T
            self.heat_transfer.set_reference_state(self.p, self.T, self.V)
            # Compute trapped fuel mass
            self.m_fuel = self.m / (1.0 + self.combustion.afr_target)
            self.x_b = 0.0

    def get_valve_areas(self, theta_deg: float):
        """Get effective valve areas at given global crank angle."""
        theta_local = self.local_theta(theta_deg)
        A_int = self.intake_valve.effective_area(theta_local)
        A_exh = self.exhaust_valve.effective_area(theta_local)
        return A_int, A_exh
