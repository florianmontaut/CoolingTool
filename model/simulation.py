# model/simulation.py
"""
Simulation d'un dissipateur portant des sources de chaleur.

La fiche du dissipateur (catalogue ou mesures) donne une résistance thermique globale,
dans une condition d'essai précise (source uniforme au centre, couvrant la moitié de la
semelle). Elle ne dit rien de la répartition des températures. On en tire donc un
coefficient d'échange h, par calage : h est ajusté pour que le modèle, placé dans la
condition d'essai, redonne la résistance de la fiche (corrigée par ses courbes pour la
longueur et la vitesse d'air voulues). Ce h sert ensuite au placement réel des sources.

Hypothèses à connaître :
    - vitesse d'air : celle du conduit en amont, sur la section de la zone d'ailettes
      (Heatsink.flow_area), sans fuite autour du dissipateur ;
    - air chaud ou en altitude : à vitesse égale, le débit massique baisse. On se ramène
      à la vitesse qui donnerait le même débit massique dans les conditions du catalogue
      (25 °C, niveau de la mer) ; la variation de conductivité et de viscosité de l'air
      avec la température est négligée ;
    - conduction : selon la longueur, toute la section de métal du profil (les ailettes
      sont continues) ; selon la largeur, la semelle seule (Heatsink.y_factor) ;
    - convection naturelle, ailettes verticales : y = 0 en bas. L'air monte le long des
      ailettes et s'échauffe ; son échauffement en haut est fixé à natural_air_ratio fois
      l'échauffement moyen de la semelle (0,35 : essai du KL-288). h varie comme
      l'échauffement moyen puissance 0,25, et comme la racine de la pression (altitude) ;
    - ailettes horizontales : air à la température ambiante partout ;
    - face intérieure (Conditions.internal) : le dissipateur forme une paroi du boîtier,
      ailettes dehors. La partie de la face de montage que les sources ne couvrent pas
      échange avec l'intérieur (convection naturelle d'une plaque verticale, plus
      rayonnement vers des parois à la température interne). Les boîtiers des sources,
      leurs barres et le circuit imprimé ne sont pas comptés.

Résolution : en convection naturelle, h dépend de l'échauffement, le débit d'air aussi,
et l'échange intérieur de la température de la face. Un seul point fixe met les trois à
jour à chaque résolution ; il peut repartir d'un résultat précédent (start), ce qui
suffit à suivre une source déplacée à la souris en deux ou trois résolutions.
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

# face intérieure : émissivité selon la finition
EMISSIVITY_ANODISED = 0.85
EMISSIVITY_BARE = 0.15          # aluminium extrudé, légèrement oxydé

FIXED_POINT_TOLERANCE = 1e-5    # écart relatif sur h, le débit d'air et l'échange intérieur
FIXED_POINT_ITERATIONS = 60

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
    internal: float | None = None   # °C, intérieur du boîtier côté face de montage ;
                                    # None : face de montage sans échange
    internal_h: float = 0.0         # W/m2.K imposé côté intérieur ; 0 : calculé

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
    group: str = ""         # nom du groupe (déplacé d'un bloc), vide : aucun

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
    air_rate: float | None = None   # W/K, débit calorifique de l'air retenu
    internal_power: float = 0.0     # W cédés à l'intérieur du boîtier (négatif : reçus)
    internal_h: float | None = None     # W/m2.K, côté intérieur (None : sans échange)
    iterations: int = 1         # résolutions du point fixe

    @property
    def hottest(self) -> float:
        return float(self.surface.max())

    @property
    def internal_ratio(self) -> float:
        """Part de la puissance qui part dans le boîtier plutôt que par les ailettes."""
        return self.internal_power / self.power if self.power else 0.0


def catalogue_source_bounds(heatsink: Heatsink, length: float) -> tuple:
    """Source d'essai du catalogue : centrée, de même forme que la semelle."""
    ratio = math.sqrt(heatsink.test_coverage)
    half_x, half_y = heatsink.width * ratio / 2, length * ratio / 2
    return (heatsink.width / 2 - half_x, heatsink.width / 2 + half_x,
            length / 2 - half_y, length / 2 + half_y)


def _mean_under(surface: np.ndarray, coverage: np.ndarray) -> float:
    return float((surface * coverage).sum() / coverage.sum())


def _natural_rate(mean_rise: float, power: float, heatsink: Heatsink) -> float | None:
    """Débit calorifique de l'air qui monte le long des ailettes (W/K)."""
    if mean_rise <= 0 or power <= 0 or heatsink.natural_air_ratio <= 0:
        return None
    return power / (heatsink.natural_air_ratio * mean_rise)


def _solve_natural(grid: Grid, heatsink: Heatsink, injected: np.ndarray, ambient: float,
                   h: float, rate: float | None = None) -> tuple:
    """
    Convection naturelle, ailettes verticales : le débit d'air dépend de l'échauffement,
    qui dépend du débit. Point fixe ; renvoie (solution, débit calorifique).
    """
    power = float(injected.sum())
    if rate is None:
        start = solve(grid, heatsink.conductivity, injected, ambient, h, None,
                      heatsink.y_factor)
        rate = _natural_rate(float(start.sink_face.mean()) - ambient, power, heatsink)
        if rate is None:
            return start, None
    for _ in range(40):
        solution = solve(grid, heatsink.conductivity, injected, ambient, h, rate,
                         heatsink.y_factor)
        updated = _natural_rate(float(solution.sink_face.mean()) - ambient, power, heatsink)
        if updated is None:
            return solution, rate
        converged = abs(updated - rate) <= 1e-6 * rate
        rate = updated
        if converged:
            break
    return solve(grid, heatsink.conductivity, injected, ambient, h, rate,
                 heatsink.y_factor), rate


def finish_factor(heatsink: Heatsink, black_anodised: bool) -> float:
    """
    Correction de la Rth naturelle selon la finition voulue, sachant celle de la fiche :
    une fiche donnée pour une surface anodisée noire n'est pas corrigée une seconde fois.
    """
    wanted = BLACK_ANODISED_FACTOR if black_anodised else 1.0
    sheet = BLACK_ANODISED_FACTOR if heatsink.anodised else 1.0
    return wanted / sheet


@lru_cache(maxsize=512)
def _calibrate(heatsink: Heatsink, length: float, mode: str, equivalent_speed: float,
               black_anodised: bool, horizontal: bool) -> Calibration:
    curves = heatsink.curves
    warnings = []
    natural = mode == NATURAL
    factor = curves.length_factor(length, heatsink.rth_length, natural)
    length_curve = curves.length_curve(natural)
    if not length_curve.covers(length):
        warnings.append(f"longueur {length * 1000:.0f} mm hors de la courbe de longueur "
                        f"({length_curve.x_min * 1000:.0f} à "
                        f"{length_curve.x_max * 1000:.0f} mm) : facteur extrapolé")
    if mode == FORCED:
        target = heatsink.rth_forced * factor * curves.speed_factor(equivalent_speed,
                                                                    heatsink.forced_speed)
        if not curves.speed.covers(equivalent_speed):
            warnings.append(f"vitesse équivalente {equivalent_speed:.1f} m/s hors de "
                            f"la courbe de vitesse ({curves.speed.x_min:g} à "
                            f"{curves.speed.x_max:g} m/s) : facteur extrapolé")
        capacity_rate = (air.REFERENCE_DENSITY * equivalent_speed * heatsink.flow_area
                         * air.CP_AIR)
        power = 100.0       # le problème est linéaire : valeur sans importance
    else:
        target = heatsink.rth_natural * factor * finish_factor(heatsink, black_anodised)
        target *= HORIZONTAL_FACTOR if horizontal else 1.0
        capacity_rate = None
        power = heatsink.natural_delta_t / target

    grid = Grid(heatsink.width, length, heatsink.base,
                CALIBRATION_CELLS, CALIBRATION_CELLS, CALIBRATION_LAYERS)
    coverage = grid.coverage(*catalogue_source_bounds(heatsink, length))
    injected = power * coverage / coverage.sum()

    rising_air = natural and not horizontal

    def run(h: float) -> Solution:
        if rising_air:
            return _solve_natural(grid, heatsink, injected, 0.0, h)[0]
        return solve(grid, heatsink.conductivity, injected, 0.0, h, capacity_rate,
                     heatsink.y_factor)

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


def internal_coefficient(conditions: Conditions, surface: float, height: float) -> float:
    """
    Coefficient d'échange (W/m2.K) de la face de montage avec l'intérieur du boîtier :
    convection naturelle d'une plaque verticale de cette hauteur, plus rayonnement
    vers des parois à la température interne. Une valeur imposée le remplace.
    """
    if conditions.internal_h > 0:
        return conditions.internal_h
    inside = conditions.internal
    emissivity = EMISSIVITY_ANODISED if conditions.black_anodised else EMISSIVITY_BARE
    return (air.vertical_plate_h(surface, inside, height, conditions.altitude)
            + air.radiation_h(surface, inside, emissivity))


def make_grid(heatsink: Heatsink, length: float, cell: float = 2.5e-3, layers: int = 3,
              max_cells: int = 200) -> Grid:
    """Maillage de la semelle : cellules d'environ cell (m) de côté."""
    def count(size):
        return int(min(max_cells, max(8, round(size / cell))))

    return Grid(heatsink.width, length, heatsink.base,
                count(heatsink.width), count(length), layers)


def simulate(heatsink: Heatsink, length: float, sources, conditions: Conditions,
             grid: Grid | None = None, start: Result | None = None) -> Result:
    """
    Températures du dissipateur et des sources, en régime permanent.
    start : résultat précédent pour le même dissipateur, la même longueur et les mêmes
    conditions de convection ; le point fixe repart de son h et de son débit d'air.
    """
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
    plate = injected[::-1] if flip else injected
    natural = conditions.mode == NATURAL
    rising_air = natural and not conditions.horizontal

    # point fixe : h et débit d'air (convection naturelle), échange intérieur
    h = calibration.h
    base_h = h * (math.sqrt(air.pressure(conditions.altitude) / air.P_SEA_LEVEL)
                  if natural else 1.0)
    h, rate = base_h, (None if natural else calibration.capacity_rate)
    if natural and start is not None and start.calibration is calibration:
        h, rate = start.h, start.air_rate if rising_air else None
    inside = conditions.internal
    exposed = np.zeros(grid.shape)
    if inside is not None:
        exposed = np.clip(1.0 - sum(coverages, np.zeros(grid.shape)), 0.0, 1.0)
        exposed = exposed[::-1] if flip else exposed
    # face intérieure verticale : sa hauteur est la longueur, ou la largeur si les
    # ailettes sont horizontales
    height = grid.width if natural and conditions.horizontal else grid.length
    leak = np.zeros(grid.shape)             # W cédés à l'intérieur, par cellule
    h_inside = None
    power = float(injected.sum())
    scale = max(power, 1.0)
    iterations, converged = 0, False
    while iterations < FIXED_POINT_ITERATIONS:
        iterations += 1
        solution = solve(grid, heatsink.conductivity, plate - leak, conditions.ambient, h,
                         rate, heatsink.y_factor)
        if not natural and inside is None:
            converged = True
            break
        change, new_h, new_rate, new_leak = 0.0, h, rate, leak
        if natural:
            rise = float(solution.sink_face.mean()) - conditions.ambient
            if rise > 0:
                new_h = base_h * (rise / calibration.mean_rise) ** NATURAL_EXPONENT
                change = abs(new_h - h) / h
            if rising_air:
                fins = float(solution.convected.sum())
                updated = _natural_rate(rise, fins, heatsink)
                if updated is not None:
                    if rate is not None:
                        change = max(change, abs(updated - rate) / rate)
                    else:
                        change = 1.0
                    new_rate = updated
        if inside is not None:
            face = solution.surface
            mean = float((face * exposed).sum() / exposed.sum()) if exposed.sum() else inside
            h_inside = internal_coefficient(conditions, mean, height)
            new_leak = h_inside * grid.cell_area * exposed * (face - inside)
            change = max(change, float(np.abs(new_leak - leak).sum()) / scale)
        if change <= FIXED_POINT_TOLERANCE:
            converged = True
            break
        h, rate, leak = new_h, new_rate, new_leak
    if not converged:
        warnings.append("calcul non convergé : résultat approché")

    surface = solution.surface[::-1] if flip else solution.surface
    air_out = solution.air_out[::-1] if flip else solution.air_out
    internal_power = float(leak.sum())
    if inside is not None and internal_power < 0:
        warnings.append(f"intérieur plus chaud que la semelle : le dissipateur en "
                        f"évacue {-internal_power:.0f} W")
    results = []
    for source, coverage in zip(sources, coverages):
        mean = _mean_under(surface, coverage)
        case = mean + source.power * source.rth_cs
        results.append(SourceResult(source=source, sink_mean=mean,
                                    sink_max=float(surface[coverage > 0].max()),
                                    case=case,
                                    junction=case + source.power * source.rth_jc))
    return Result(grid=grid, surface=surface, air_out=air_out, sources=results,
                  calibration=calibration, h=h, power=power,
                  convected=float(solution.convected.sum()),
                  air_outlet=float(solution.air_out[-1].mean()), warnings=warnings,
                  air_rate=rate, internal_power=internal_power, internal_h=h_inside,
                  iterations=iterations)
