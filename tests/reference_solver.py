"""
Solveur de référence des tests : même discrétisation que model.solver, mais assemblée en
matrice creuse et résolue directement (lent, sans transformée). Deux écritures
indépendantes qui donnent le même champ se valident l'une l'autre.
"""
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve

from model.solver import Grid, Solution


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
    n_plate = nx * ny * nz
    index = np.arange(n_plate).reshape(nz, ny, nx)
    rows, cols, values = [], [], []

    def add(row, col, value):
        row = np.asarray(row).ravel()
        rows.append(row)
        cols.append(np.asarray(col).ravel())
        values.append(np.broadcast_to(value, row.shape))

    def couple(a, b, conductance):
        """Conductance entre cellules voisines : flux a -> b = conductance × (Ta - Tb)."""
        add(a, a, conductance)
        add(b, b, conductance)
        add(a, b, -conductance)
        add(b, a, -conductance)

    if nx > 1:
        couple(index[:, :, :-1], index[:, :, 1:], k * dy * dz / dx)
    if ny > 1:
        couple(index[:, :-1, :], index[:, 1:, :], y_factor * k * dx * dz / dy)
    if nz > 1:
        couple(index[:-1], index[1:], k * dx * dy / dz)

    power = np.asarray(power, dtype=float)
    bottom = index[-1]
    # du centre de la dernière couche à l'air : demi-cellule de métal, puis h
    exchange = grid.cell_area / (dz / (2.0 * k) + 1.0 / h)      # W/K par cellule

    if capacity_rate is None:
        n_total = n_plate
        rhs = np.zeros(n_total)
        add(bottom, bottom, exchange)
        rhs[bottom.ravel()] += exchange * ambient
    else:
        column_rate = capacity_rate * dx / grid.width            # W/K par canal
        efficiency = 1.0 - np.exp(-exchange / column_rate)
        gain = column_rate * efficiency                          # W/K, sur (T - T_air entrée)
        air = n_plate + np.arange(nx * ny).reshape(ny, nx)
        n_total = n_plate + nx * ny
        rhs = np.zeros(n_total)
        # semelle : gain × (T - T_air entrée) cédé à l'air
        add(bottom, bottom, gain)
        rhs[bottom[0]] += gain * ambient
        add(bottom[1:], air[:-1], -gain)
        # air : T_sortie = T_entrée + efficacité × (T - T_entrée)
        add(air, air, 1.0)
        add(air, bottom, -efficiency)
        rhs[air[0]] += (1.0 - efficiency) * ambient
        add(air[1:], air[:-1], -(1.0 - efficiency))

    rhs[index[0].ravel()] += power.ravel()
    matrix = sparse.coo_matrix((np.concatenate(values),
                                (np.concatenate(rows), np.concatenate(cols))),
                               shape=(n_total, n_total)).tocsc()
    x = spsolve(matrix, rhs)

    temperature = x[:n_plate].reshape(nz, ny, nx)
    if capacity_rate is None:
        air_out = np.full((ny, nx), float(ambient))
        convected = exchange * (temperature[-1] - ambient)
    else:
        air_out = x[n_plate:].reshape(ny, nx)
        air_in = np.vstack([np.full((1, nx), float(ambient)), air_out[:-1]])
        convected = gain * (temperature[-1] - air_in)
    # du centre de la première couche à la face de montage : demi-cellule de métal
    surface = temperature[0] + power / grid.cell_area * dz / (2.0 * k)
    return Solution(grid, temperature, surface, air_out, convected)
