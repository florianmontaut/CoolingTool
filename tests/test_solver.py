"""Solveur de conduction : comparaison à des solutions analytiques et à une référence."""
import numpy as np
import pytest

from model.analytic import centred_source_resistance
from model.solver import Grid, solve
from reference_solver import solve as reference_solve

W, L, T, K, H = 0.200, 0.300, 0.010, 200.0, 150.0
AMBIENT = 40.0


def centred(grid, size_x, size_y, power):
    coverage = grid.coverage(grid.width / 2 - size_x / 2, grid.width / 2 + size_x / 2,
                             grid.length / 2 - size_y / 2, grid.length / 2 + size_y / 2)
    return coverage, power * coverage / coverage.sum()


def mean_resistance(grid, size_x, size_y, power=100.0):
    coverage, injected = centred(grid, size_x, size_y, power)
    surface = solve(grid, K, injected, AMBIENT, H).surface
    return ((surface * coverage).sum() / coverage.sum() - AMBIENT) / power


# ------------------------------------------------------------------ maillage
def test_recouvrement_exact_des_cellules():
    grid = Grid(0.1, 0.2, 0.01, 10, 20, 1)          # cellules de 10 mm
    coverage = grid.coverage(0.015, 0.045, 0.100, 0.125)
    assert coverage.shape == (20, 10)
    assert coverage.sum() * grid.cell_area == pytest.approx(0.030 * 0.025)
    assert coverage[10, 1] == pytest.approx(0.5)     # demi-cellule en x
    assert coverage[12, 2] == pytest.approx(0.5)     # demi-cellule en y
    assert coverage[11, 3] == pytest.approx(1.0)
    assert coverage[9].sum() == 0 and coverage[:, 5:].sum() == 0


def test_source_debordante_tronquee():
    grid = Grid(0.1, 0.2, 0.01, 10, 20, 1)
    assert grid.coverage(-0.02, 0.02, -0.01, 0.01).sum() * grid.cell_area \
        == pytest.approx(0.02 * 0.01)
    assert grid.coverage(0.2, 0.3, 0.0, 0.1).sum() == 0


# ------------------------------------------------------------------ conduction
@pytest.mark.parametrize("nz", [1, 2, 5])
def test_flux_uniforme_exact(nz):
    """Flux uniforme sur toute la semelle : traversée 1D, exacte sur tout maillage."""
    grid = Grid(W, L, T, 6, 9, nz)
    power = np.full(grid.shape, 2.0)
    flux = 2.0 / grid.cell_area
    solution = solve(grid, K, power, AMBIENT, H)
    assert solution.surface == pytest.approx(AMBIENT + flux * (T / K + 1 / H), rel=1e-12)
    assert solution.convected.sum() == pytest.approx(power.sum())


@pytest.mark.parametrize("size_x, size_y, tolerance", [
    (0.020, 0.020, 0.03),       # source de la taille de l'épaisseur × 2 : épanouissement 3D
    (0.060, 0.100, 0.005),      # module de puissance
    (0.200, 0.300, 1e-9),       # toute la semelle
])
def test_resistance_d_epanouissement(size_x, size_y, tolerance):
    exact = centred_source_resistance(W, L, T, size_x, size_y, K, H)
    grid = Grid(W, L, T, 80, 120, 4)
    assert mean_resistance(grid, size_x, size_y) == pytest.approx(exact, rel=tolerance)


def test_convergence_avec_le_maillage():
    exact = centred_source_resistance(W, L, T, 0.02, 0.02, K, H)
    errors = [abs(mean_resistance(Grid(W, L, T, nx, ny, nz), 0.02, 0.02) / exact - 1)
              for nx, ny, nz in [(20, 30, 1), (40, 60, 2), (80, 120, 4), (160, 240, 8)]]
    assert errors == sorted(errors, reverse=True)
    assert errors[-1] < 0.01
    # une seule couche ignore l'épanouissement dans l'épaisseur : pessimiste de 10 %
    assert errors[0] > 0.08


@pytest.mark.parametrize("y_factor", [1.0, 3.0])
def test_ailette_1d(y_factor):
    """
    Bande chauffée à une extrémité d'une plaque mince : profil en cosh. Le facteur de
    conduction selon y multiplie la conductance de la plaque dans ce sens.
    """
    thickness, width, length, power = 0.002, 0.05, 0.3, 10.0
    grid = Grid(width, length, thickness, 4, 300, 1)
    injected = power * grid.coverage(0, width, 0, grid.dy)
    injected /= injected.sum() / power
    solution = solve(grid, K, injected, AMBIENT, H, y_factor=y_factor)
    exchange = 1 / (thickness / (2 * K) + 1 / H)
    k_y = K * y_factor
    m = np.sqrt(exchange / (k_y * thickness))
    y = (np.arange(grid.ny) + 0.5) * grid.dy
    exact = power * np.cosh(m * (length - y)) / (k_y * thickness * width * m
                                                 * np.sinh(m * length))
    computed = solution.temperature[0, :, 0] - AMBIENT
    assert computed[5:] == pytest.approx(exact[5:], rel=0.01)


# ------------------------------------------------------------------ air
def test_echauffement_de_l_air_sans_conduction_laterale():
    """Semelle très peu conductrice, flux uniforme : l'air monte linéairement."""
    grid = Grid(0.1, 0.2, 0.001, 5, 40, 1)
    conductivity, rate = 1e-3, 20.0
    power = np.full(grid.shape, 0.5)
    solution = solve(grid, conductivity, power, AMBIENT, H, capacity_rate=rate)
    column_rate = rate / grid.nx
    air_out = AMBIENT + 0.5 * (np.arange(grid.ny) + 1) / column_rate
    assert solution.air_out[:, 2] == pytest.approx(air_out, rel=1e-4)
    exchange = grid.cell_area / (grid.dz / (2 * conductivity) + 1 / H)
    gain = column_rate * (1 - np.exp(-exchange / column_rate))
    air_in = air_out - 0.5 / column_rate
    assert solution.temperature[0, :, 2] == pytest.approx(air_in + 0.5 / gain, rel=1e-3)


def test_bilan_de_puissance_en_convection_forcee():
    grid = Grid(W, L, T, 40, 60, 3)
    _, injected = centred(grid, 0.06, 0.1, 500.0)
    solution = solve(grid, K, injected, AMBIENT, H, capacity_rate=60.0)
    assert solution.convected.sum() == pytest.approx(500.0)
    assert solution.air_out[-1].mean() == pytest.approx(AMBIENT + 500.0 / 60.0)
    # l'air ne refroidit jamais sous l'ambiante, et l'aval est plus chaud que l'amont
    assert solution.air_out.min() >= AMBIENT - 1e-9
    assert solution.surface[-1].mean() > solution.surface[0].mean()


def test_debit_tres_grand_equivaut_a_la_convection_naturelle():
    grid = Grid(W, L, T, 20, 30, 2)
    _, injected = centred(grid, 0.06, 0.1, 200.0)
    forced = solve(grid, K, injected, AMBIENT, H, capacity_rate=1e9)
    natural = solve(grid, K, injected, AMBIENT, H)
    assert forced.surface == pytest.approx(natural.surface, rel=1e-6)


# ------------------------------------------------------------------ référence
@pytest.mark.parametrize("y_factor", [1.0, 2.5])
@pytest.mark.parametrize("nz", [1, 3])
@pytest.mark.parametrize("rate", [None, 60.0])
def test_identique_au_solveur_de_reference(nz, rate, y_factor):
    grid = Grid(W, L, T, 24, 36, nz)
    coverage = grid.coverage(0.031, 0.093, 0.050, 0.151)        # source excentrée
    injected = 500.0 * coverage / coverage.sum()
    fast = solve(grid, K, injected, AMBIENT, H, rate, y_factor)
    reference = reference_solve(grid, K, injected, AMBIENT, H, rate, y_factor)
    assert fast.temperature == pytest.approx(reference.temperature, abs=1e-8)
    assert fast.surface == pytest.approx(reference.surface, abs=1e-8)
    assert fast.air_out == pytest.approx(reference.air_out, abs=1e-8)
    assert fast.convected == pytest.approx(reference.convected, abs=1e-8)
