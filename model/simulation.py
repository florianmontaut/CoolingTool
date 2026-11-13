# model/simulation.py
"""
Simulation d'un dissipateur de catalogue portant des sources de chaleur.

Le catalogue donne une résistance thermique globale, mesurée dans une condition d'essai
précise (source uniforme au centre, couvrant la moitié de la semelle). Elle ne dit rien
de la répartition des températures. On en tire donc un coefficient d'échange h, par
calage : h est ajusté pour que le modèle, placé dans la condition d'essai, redonne la
résistance du catalogue (corrigée par les abaques pour la longueur et la vitesse d'air
voulues). Ce h sert ensuite au placement réel des sources.

Hypothèses à connaître :
    - vitesse d'air : celle du conduit en amont, sur la section de la zone d'ailettes
      (Heatsink.flow_area), sans fuite autour du dissipateur ;
    - air chaud ou en altitude : à vitesse égale, le débit massique baisse. On se ramène
      à la vitesse qui donnerait le même débit massique dans les conditions du catalogue
      (25 °C, niveau de la mer) ; la variation de conductivité et de viscosité de l'air
      avec la température est négligée ;
    - convection naturelle : h varie comme l'échauffement moyen puissance 0,25, et comme
      la racine de la pression (altitude). L'air est pris à la température ambiante
      partout : son échauffement le long des ailettes n'est pas réparti.
"""
import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from scipy.optimize import brentq

from . import air
from .heatsink import Heatsink
from .solver import Grid, Solution, solve

NATURAL = "naturelle"
FORCED = "forcée"

# correctifs du catalogue en convection naturelle
BLACK_ANODISED_FACTOR = 0.9     # surface anodisée noire : Rth - 10 %
HORIZONTAL_FACTOR = 1.2         # ailettes horizontales : Rth + 20 %
NATURAL_EXPONENT = 0.25         # h ~ échauffement ^ 0,25

CALIBRATION_CELLS = 40          # maillage du calage, par côté
CALIBRATION_LAYERS = 3
H_BOUNDS = (0.5, 2.0e5)         # W/m2.K, plage de recherche du calage


class CalibrationError(ValueError):
    """La résistance du catalogue ne peut pas être reproduite par le modèle."""


@dataclass(frozen=True)
class Conditions:
    mode: str = FORCED
    ambient: float = 25.0           # °C
    speed: float = 3.0              # m/s, convection forcée
    altitude: float = 0.0           # m
    reversed_flow: bool = False     # air de y = longueur vers y = 0
    black_anodised: bool = False    # convection naturelle
    horizontal: bool = False        # convection naturelle, ailettes horizontales

    def __post_init__(self):
        if self.mode not in (NATURAL, FORCED):
            raise ValueError(f"mode de convection inconnu : {self.mode!r}")


@dataclass(frozen=True)
class Source:
    """Source de chaleur rectangulaire posée sur la semelle. Longueurs en m."""
    name: str
    x: float                # centre, selon la largeur
    y: float                # centre, selon la longueur (sens de l'air)
    size_x: float
    size_y: float
    power: float            # W
    rth_jc: float = 0.0     # jonction - boîtier (K/W)
    rth_cs: float = 0.0     # boîtier - dissipateur, interface thermique (K/W)
    tj_max: float | None = None

    @property
    def bounds(self) -> tuple:
        return (self.x - self.size_x / 2, self.x + self.size_x / 2,
                self.y - self.size_y / 2, self.y + self.size_y / 2)


@dataclass
class SourceResult:
    source: Source
    sink_mean: float        # °C, température moyenne du dissipateur sous la source
    sink_max: float         # °C, maximum sous la source
    case: float             # °C, boîtier : sink_mean + P × rth_cs
    junction: float         # °C, jonction : case + P × rth_jc

    @property
    def margin(self) -> float | None:
        """Marge sur Tj max (K), None si elle n'est pas renseignée."""
        tj_max = self.source.tj_max
        return None if tj_max is None else tj_max - self.junction


@dataclass(frozen=True)
class Calibration:
    h: float                    # W/m2.K, ramené à la surface de la semelle
    rth_target: float           # K/W, résistance du catalogue corrigée
    capacity_rate: float | None     # W/K, débit calorifique de l'air (forcée)
    equivalent_speed: float | None  # m/s, vitesse à débit massique égal (forcée)
    mean_rise: float            # K, échauffement moyen côté ailettes dans l'essai (naturelle)
    warnings: tuple = ()


@dataclass
class Result:
    grid: Grid
    surface: np.ndarray         # (ny, nx), °C, face de montage
    air_out: np.ndarray         # (ny, nx), °C
    sources: list
    calibration: Calibration
    h: float                    # W/m2.K effectivement utilisé
    power: float                # W injectés
    convected: float            # W cédés à l'air (égal à power : contrôle)
    air_outlet: float           # °C, température moyenne de l'air en sortie
    warnings: list = field(default_factory=list)

    @property
    def hottest(self) -> float:
        return float(self.surface.max())


def catalogue_source_bounds(heatsink: Heatsink, length: float) -> tuple:
    """Source d'essai du catalogue : centrée, de même forme que la semelle."""
    ratio = math.sqrt(heatsink.test_coverage)
    half_x, half_y = heatsink.width * ratio / 2, length * ratio / 2
    return (heatsink.width / 2 - half_x, heatsink.width / 2 + half_x,
            length / 2 - half_y, length / 2 + half_y)


def _mean_under(surface: np.ndarray, coverage: np.ndarray) -> float:
    return float((surface * coverage).sum() / coverage.sum())


@lru_cache(maxsize=512)
def _calibrate(heatsink: Heatsink, length: float, mode: str, equivalent_speed: float,
               black_anodised: bool, horizontal: bool) -> Calibration:
    curves = heatsink.curves
    warnings = []
    factor = curves.length_factor(length, heatsink.rth_length)
    if not curves.length.covers(length):
        warnings.append(f"longueur {length * 1000:.0f} mm hors de l'abaque "
                        f"({curves.length.x_min * 1000:.0f} à "
                        f"{curves.length.x_max * 1000:.0f} mm) : facteur extrapolé")
    if mode == FORCED:
        target = heatsink.rth_forced * factor * curves.speed_factor(equivalent_speed,
                                                                    heatsink.forced_speed)
        if not curves.speed.covers(equivalent_speed):
            warnings.append(f"vitesse équivalente {equivalent_speed:.1f} m/s hors de "
                            f"l'abaque ({curves.speed.x_min:g} à {curves.speed.x_max:g} "
                            "m/s) : facteur extrapolé")
        capacity_rate = (air.REFERENCE_DENSITY * equivalent_speed * heatsink.flow_area
                         * air.CP_AIR)
        power = 100.0       # le problème est linéaire : valeur sans importance
    else:
        target = heatsink.rth_natural * factor
        target *= BLACK_ANODISED_FACTOR if black_anodised else 1.0
        target *= HORIZONTAL_FACTOR if horizontal else 1.0
        capacity_rate = None
        power = heatsink.natural_delta_t / target

    grid = Grid(heatsink.width, length, heatsink.base,
                CALIBRATION_CELLS, CALIBRATION_CELLS, CALIBRATION_LAYERS)
    coverage = grid.coverage(*catalogue_source_bounds(heatsink, length))
    injected = power * coverage / coverage.sum()

    def run(h: float) -> Solution:
        return solve(grid, heatsink.conductivity, injected, 0.0, h, capacity_rate)

    def error(log_h: float) -> float:
        return _mean_under(run(math.exp(log_h)).surface, coverage) / power - target

    low, high = (math.log(bound) for bound in H_BOUNDS)
    if error(high) > 0:
        floor = _mean_under(run(H_BOUNDS[1]).surface, coverage) / power
        raise CalibrationError(
            f"{heatsink.name} : la résistance visée ({target:.4f} K/W) est inférieure à ce "
            f"que la conduction dans la semelle et le débit d'air permettent "
            f"({floor:.4f} K/W). Vérifier la fiche (épaisseur de semelle, section d'air).")
    if error(low) < 0:
        raise CalibrationError(f"{heatsink.name} : résistance visée ({target:.4f} K/W) "
                               "trop élevée pour le modèle.")
    h = math.exp(brentq(error, low, high, xtol=1e-6))
    mean_rise = float(run(h).sink_face.mean())
    return Calibration(h=h, rth_target=target, capacity_rate=capacity_rate,
                       equivalent_speed=equivalent_speed if mode == FORCED else None,
                       mean_rise=mean_rise, warnings=tuple(warnings))


def calibrate(heatsink: Heatsink, length: float, conditions: Conditions) -> Calibration:
    """Coefficient d'échange tiré du catalogue pour cette longueur et ces conditions."""
    if conditions.mode == FORCED:
        density_ratio = (air.density(conditions.ambient, conditions.altitude)
                         / air.REFERENCE_DENSITY)
        return _calibrate(heatsink, length, FORCED, conditions.speed * density_ratio,
                          False, False)
    return _calibrate(heatsink, length, NATURAL, 0.0, conditions.black_anodised,
                      conditions.horizontal)


def make_grid(heatsink: Heatsink, length: float, cell: float = 2.5e-3, layers: int = 3,
              max_cells: int = 200) -> Grid:
    """Maillage de la semelle : cellules d'environ cell (m) de côté."""
    def count(size):
        return int(min(max_cells, max(8, round(size / cell))))

    return Grid(heatsink.width, length, heatsink.base,
                count(heatsink.width), count(length), layers)


def simulate(heatsink: Heatsink, length: float, sources, conditions: Conditions,
             grid: Grid | None = None) -> Result:
    """Températures du dissipateur et des sources, en régime permanent."""
    grid = grid or make_grid(heatsink, length)
    calibration = calibrate(heatsink, length, conditions)
    warnings = list(calibration.warnings)
    sources = list(sources)

    injected = np.zeros(grid.shape)
    coverages = []
    for source in sources:
        coverage = grid.coverage(*source.bounds)
        covered = coverage.sum() * grid.cell_area
        if covered <= 0:
            raise ValueError(f"la source {source.name} est hors de la semelle")
        if covered < 0.999 * source.size_x * source.size_y:
            warnings.append(f"{source.name} dépasse de la semelle : toute sa puissance "
                            "est reportée sur la partie en contact")
        injected += source.power * coverage / coverage.sum()
        coverages.append(coverage)
    # le solveur souffle de y = 0 vers y = longueur : on retourne la semelle si besoin
    flip = conditions.mode == FORCED and conditions.reversed_flow

    def run(h: float) -> Solution:
        return solve(grid, heatsink.conductivity, injected[::-1] if flip else injected,
                     conditions.ambient, h, calibration.capacity_rate)

    h = calibration.h
    if conditions.mode == NATURAL:
        h *= math.sqrt(air.pressure(conditions.altitude) / air.P_SEA_LEVEL)
        base_h = h
        solution = run(h)
        # h dépend de l'échauffement, qui dépend de h : point fixe (convergence rapide)
        for _ in range(30):
            rise = float(solution.sink_face.mean()) - conditions.ambient
            if rise <= 0:
                break
            updated = base_h * (rise / calibration.mean_rise) ** NATURAL_EXPONENT
            converged = abs(updated - h) <= 1e-5 * h
            h = updated
            solution = run(h)
            if converged:
                break
    else:
        solution = run(h)

    surface = solution.surface[::-1] if flip else solution.surface
    air_out = solution.air_out[::-1] if flip else solution.air_out
    results = []
    for source, coverage in zip(sources, coverages):
        mean = _mean_under(surface, coverage)
        case = mean + source.power * source.rth_cs
        results.append(SourceResult(source=source, sink_mean=mean,
                                    sink_max=float(surface[coverage > 0].max()),
                                    case=case,
                                    junction=case + source.power * source.rth_jc))
    return Result(grid=grid, surface=surface, air_out=air_out, sources=results,
                  calibration=calibration, h=h, power=float(injected.sum()),
                  convected=float(solution.convected.sum()),
                  air_outlet=float(solution.air_out[-1].mean()), warnings=warnings)
