# model/solver.py
"""
Conduction en régime permanent dans la semelle d'un dissipateur.

La semelle est un pavé largeur (x) × longueur (y, sens de l'extrusion et de l'air) ×
épaisseur (z), découpé en volumes finis. Les sources chauffent la face de montage
(z = 0) ; la face opposée, côté ailettes, échange avec l'air par un coefficient h ramené
à la surface de la semelle (les ailettes et leur rendement y sont inclus).

Deux modes :
    - convection naturelle : l'air est à la température ambiante partout ;
    - convection forcée : l'air circule de y = 0 vers y = longueur et s'échauffe. Chaque
      colonne de cellules (un canal entre ailettes, sans mélange latéral) porte sa part
      du débit ; l'échange d'une cellule suit la loi d'un échangeur à paroi isotherme
      (efficacité 1 - exp(-NUT)), exacte quelle que soit la taille de la cellule.

Quelques couches dans l'épaisseur suffisent à rendre l'épanouissement de la chaleur sous
une source petite devant l'épaisseur de la semelle.

Conduction anisotrope (y_factor) : les ailettes d'un profilé extrudé sont continues sur
toute la longueur. Elles conduisent la chaleur selon y, pas selon x. La conduction selon y
est donc celle de toute la section de métal du profil, répartie sur l'épaisseur de la
semelle ; selon x, celle de la semelle seule.

Résolution : la semelle est homogène et ses bords isolés, et les canaux d'air sont
indépendants les uns des autres ; une transformée en cosinus selon x découple donc le
problème en nx systèmes bande (y, z, air), résolus directement. Un calcul prend quelques
dizaines de millisecondes, ce qui permet de suivre une source déplacée à la souris.
"""
from dataclasses import dataclass

import numpy as np
from scipy.fft import dct, idct
from scipy.linalg import solve_banded


@dataclass(frozen=True)
class Grid:
    width: float        # x (m)
    length: float       # y (m)
    thickness: float    # z (m)
    nx: int
    ny: int
    nz: int

    @property
    def dx(self) -> float:
        return self.width / self.nx

    @property
    def dy(self) -> float:
        return self.length / self.ny

    @property
    def dz(self) -> float:
        return self.thickness / self.nz

    @property
    def cell_area(self) -> float:
        return self.dx * self.dy

    @property
    def shape(self) -> tuple:
        return (self.ny, self.nx)

    def coverage(self, x0: float, x1: float, y0: float, y1: float) -> np.ndarray:
        """
        Part (0 à 1) de chaque cellule couverte par le rectangle [x0, x1] × [y0, y1].
        Tableau (ny, nx). Le recouvrement partiel est exact : une source qui glisse
        d'une fraction de cellule déplace sa puissance d'autant.
        """
        def overlap(lo, hi, size, count):
            edges = np.linspace(0.0, size, count + 1)
            return np.clip(np.minimum(hi, edges[1:]) - np.maximum(lo, edges[:-1]),
                           0.0, None) / (size / count)

        return np.outer(overlap(y0, y1, self.length, self.ny),
                        overlap(x0, x1, self.width, self.nx))


@dataclass
class Solution:
    grid: Grid
    temperature: np.ndarray     # (nz, ny, nx), °C, au centre des cellules
    surface: np.ndarray         # (ny, nx), °C, face de montage
    air_out: np.ndarray         # (ny, nx), °C, air en sortie de chaque cellule
    convected: np.ndarray       # (ny, nx), W cédés à l'air par chaque cellule

    @property
    def sink_face(self) -> np.ndarray:
        """Température de la couche côté ailettes, (ny, nx)."""
        return self.temperature[-1]


def solve(grid: Grid, conductivity: float, power: np.ndarray, ambient: float,
          h: float, capacity_rate: float | None = None, y_factor: float = 1.0) -> Solution:
    """
    power           (ny, nx), W injectés par cellule sur la face de montage
    ambient         température de l'air à l'entrée (°C)
    h               coefficient d'échange ramené à la surface de la semelle (W/m2.K)
    capacity_rate   débit calorifique total de l'air, débit massique × cp (W/K) ;
                    None : air à ambient partout
    y_factor        conduction selon y multipliée par ce facteur : les ailettes, continues
                    sur toute la longueur, conduisent la chaleur dans ce sens et pas selon x
    """
    nx, ny, nz = grid.nx, grid.ny, grid.nz
    dx, dy, dz = grid.dx, grid.dy, grid.dz
    k = conductivity
    forced = capacity_rate is not None
    power = np.asarray(power, dtype=float)

    # Inconnues d'un mode : échauffements (T - ambient) rangés par tranche y, et dans
    # chaque tranche les nz couches de la semelle puis, en convection forcée, l'air en
    # sortie de la tranche. Les couplages ne dépassent pas la tranche voisine : bande.
    block = nz + (1 if forced else 0)
    size = ny * block
    band = np.zeros((2 * block + 1, size))

    def add(row, col, value):
        row, col = np.broadcast_arrays(np.asarray(row), np.asarray(col))
        np.add.at(band, (block + row - col, col), value)

    def couple(a, b, conductance):
        """Conductance entre cellules voisines : flux a -> b = conductance × (Ta - Tb)."""
        add(a, a, conductance)
        add(b, b, conductance)
        add(a, b, -conductance)
        add(b, a, -conductance)

    slices = np.arange(ny)[:, None] * block
    layers = np.arange(nz)[None, :]
    plate = slices + layers                     # (ny, nz) : indice de chaque cellule
    if nz > 1:
        couple(plate[:, :-1], plate[:, 1:], k * dx * dy / dz)
    if ny > 1:
        couple(plate[:-1], plate[1:], y_factor * k * dx * dz / dy)

    bottom = plate[:, -1]
    # du centre de la dernière couche à l'air : demi-cellule de métal, puis h
    exchange = grid.cell_area / (dz / (2.0 * k) + 1.0 / h)      # W/K par cellule
    if forced:
        column_rate = capacity_rate * dx / grid.width            # W/K par canal
        efficiency = 1.0 - np.exp(-exchange / column_rate)
        gain = column_rate * efficiency                          # W/K, sur (T - T_air entrée)
        air = slices[:, 0] + nz
        # semelle : gain × (T - T_air entrée) cédé à l'air (l'air entre à ambient)
        add(bottom, bottom, gain)
        add(bottom[1:], air[:-1], -gain)
        # air : T_sortie = T_entrée + efficacité × (T - T_entrée)
        add(air, air, 1.0)
        add(air, bottom, -efficiency)
        add(air[1:], air[:-1], -(1.0 - efficiency))
    else:
        add(bottom, bottom, exchange)

    # conduction selon x : valeur propre de chaque mode de la transformée en cosinus
    eigen = k * dy * dz / dx * (2.0 - 2.0 * np.cos(np.pi * np.arange(nx) / nx))
    rhs = np.zeros((size, nx))
    rhs[plate[:, 0]] = dct(power, type=2, norm="ortho", axis=1)
    modes = np.empty((size, nx))
    diagonal = plate.ravel()
    for m in range(nx):
        matrix = band.copy()
        matrix[block, diagonal] += eigen[m]
        modes[:, m] = solve_banded((block, block), matrix, rhs[:, m],
                                   overwrite_ab=True, check_finite=False)
    field = idct(modes, type=2, norm="ortho", axis=1).reshape(ny, block, nx) + ambient

    temperature = np.ascontiguousarray(field[:, :nz].transpose(1, 0, 2))
    if forced:
        air_out = np.ascontiguousarray(field[:, nz])
        air_in = np.vstack([np.full((1, nx), float(ambient)), air_out[:-1]])
        convected = gain * (temperature[-1] - air_in)
    else:
        air_out = np.full((ny, nx), float(ambient))
        convected = exchange * (temperature[-1] - ambient)
    # du centre de la première couche à la face de montage : demi-cellule de métal
    surface = temperature[0] + power / grid.cell_area * dz / (2.0 * k)
    return Solution(grid, temperature, surface, air_out, convected)
