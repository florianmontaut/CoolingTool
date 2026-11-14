# model/air.py
"""Propriétés de l'air (gaz parfait, atmosphère standard) et convection naturelle."""
import numpy as np

R_AIR = 287.05          # J/(kg.K)
CP_AIR = 1006.0         # J/(kg.K)
KELVIN = 273.15
P_SEA_LEVEL = 101325.0  # Pa

# conditions d'essai des catalogues : 25 °C au niveau de la mer
REFERENCE_TEMPERATURE = 25.0


def pressure(altitude: float = 0.0) -> float:
    """Pression (Pa) à l'altitude donnée (m), atmosphère standard jusqu'à 11 km."""
    return P_SEA_LEVEL * (1.0 - 2.25577e-5 * altitude) ** 5.25588


def density(temperature: float, altitude: float = 0.0) -> float:
    """Masse volumique (kg/m3) à la température (°C) et à l'altitude (m) données."""
    return pressure(altitude) / (R_AIR * (temperature + KELVIN))


REFERENCE_DENSITY = density(REFERENCE_TEMPERATURE)

G = 9.81                # m/s2
PRANDTL = 0.71
# conductivité (W/m.K) et viscosité cinématique à 1 atm (m2/s) selon la température (°C)
_TABLE_T = [0.0, 20.0, 40.0, 60.0, 80.0, 100.0, 150.0, 200.0]
_TABLE_K = [0.0243, 0.0257, 0.0271, 0.0285, 0.0299, 0.0314, 0.0349, 0.0386]
_TABLE_NU = [1.32e-5, 1.51e-5, 1.70e-5, 1.90e-5, 2.09e-5, 2.30e-5, 2.85e-5, 3.45e-5]


def conductivity(temperature: float) -> float:
    return float(np.interp(temperature, _TABLE_T, _TABLE_K))


def kinematic_viscosity(temperature: float, altitude: float = 0.0) -> float:
    """Viscosité cinématique (m2/s) : inversement proportionnelle à la pression."""
    return float(np.interp(temperature, _TABLE_T, _TABLE_NU)) * P_SEA_LEVEL / pressure(altitude)


def vertical_plate_h(surface: float, air: float, height: float,
                     altitude: float = 0.0) -> float:
    """
    Coefficient de convection naturelle (W/m2.K) d'une plaque verticale isotherme de
    hauteur donnée (m), en air calme : corrélation de Churchill et Chu, propriétés de
    l'air à la température de film.
    """
    rise = abs(surface - air)
    if rise < 1e-6 or height <= 0:
        return 0.0
    film = (surface + air) / 2
    nu = kinematic_viscosity(film, altitude)
    rayleigh = G / (film + KELVIN) * rise * height ** 3 / (nu * nu / PRANDTL)
    nusselt = (0.825 + 0.387 * rayleigh ** (1 / 6)
               / (1 + (0.492 / PRANDTL) ** (9 / 16)) ** (8 / 27)) ** 2
    return nusselt * conductivity(film) / height


SIGMA = 5.670e-8        # W/m2.K4


def radiation_h(surface: float, walls: float, emissivity: float) -> float:
    """
    Coefficient de rayonnement linéarisé (W/m2.K) d'une petite surface vers une enceinte
    qui l'entoure, à la température walls (°C).
    """
    ts, tw = surface + KELVIN, walls + KELVIN
    return emissivity * SIGMA * (ts * ts + tw * tw) * (ts + tw)

