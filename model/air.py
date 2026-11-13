# model/air.py
"""Propriétés de l'air (gaz parfait, atmosphère standard)."""

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
