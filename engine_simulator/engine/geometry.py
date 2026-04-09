"""Engine geometry calculations: slider-crank kinematics."""

from __future__ import annotations

import numpy as np

from engine_simulator.config.engine_config import CylinderConfig


class EngineGeometry:
    """Computes cylinder volume and related geometric quantities from crank angle."""

    def __init__(self, cfg: CylinderConfig):
        self.bore = cfg.bore
        self.stroke = cfg.stroke
        self.con_rod = cfg.con_rod_length
        self.cr = cfg.compression_ratio

        self.crank_radius = self.stroke / 2.0
        self.rod_ratio = self.crank_radius / self.con_rod  # lambda_cr

        self.A_piston = np.pi / 4.0 * self.bore**2
        self.V_d = self.A_piston * self.stroke  # displacement per cylinder
        self.V_c = self.V_d / (self.cr - 1.0)  # clearance volume

    def piston_displacement(self, theta_rad: float) -> float:
        """Piston displacement from TDC (m). theta in radians."""
        r = self.crank_radius
        L = self.con_rod
        lam = self.rod_ratio
        sin_t = np.sin(theta_rad)
        cos_t = np.cos(theta_rad)
        return r * (1.0 - cos_t) + L * (1.0 - np.sqrt(1.0 - lam**2 * sin_t**2))

    def volume(self, theta_deg: float) -> float:
        """Instantaneous cylinder volume (m^3). theta in degrees from TDC firing."""
        theta_rad = np.radians(theta_deg)
        return self.V_c + self.A_piston * self.piston_displacement(theta_rad)

    def dVdtheta(self, theta_deg: float) -> float:
        """Rate of volume change dV/dtheta (m^3/rad). theta in degrees."""
        theta_rad = np.radians(theta_deg)
        r = self.crank_radius
        lam = self.rod_ratio
        sin_t = np.sin(theta_rad)
        cos_t = np.cos(theta_rad)
        sin_2t = np.sin(2.0 * theta_rad)
        denom = np.sqrt(1.0 - lam**2 * sin_t**2)
        return self.A_piston * r * (sin_t + lam * sin_2t / (2.0 * denom))

    def surface_area(self, theta_deg: float) -> float:
        """Instantaneous heat transfer surface area (m^2).
        A = pi*B^2/2 (head + piston) + pi*B*s(theta) (liner)
        """
        theta_rad = np.radians(theta_deg)
        s = self.piston_displacement(theta_rad)
        return np.pi * self.bore**2 / 2.0 + np.pi * self.bore * s

    def volume_array(self, theta_deg: np.ndarray) -> np.ndarray:
        """Vectorized volume computation."""
        theta_rad = np.radians(theta_deg)
        r = self.crank_radius
        L = self.con_rod
        lam = self.rod_ratio
        s = r * (1.0 - np.cos(theta_rad)) + L * (1.0 - np.sqrt(1.0 - lam**2 * np.sin(theta_rad)**2))
        return self.V_c + self.A_piston * s
