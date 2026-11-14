"""
Validation sur les essais de l'utilisateur : le modèle prédit les températures des
capteurs à partir des seules fiches de la librairie, sans ajustement propre à l'essai.

Les données d'essais sont internes : elles restent dans essais/measurements.py, dossier
ignoré par git. Sans lui (autre poste, dépôt cloné), ces tests sont sautés.
"""
import importlib.util
import math
import pathlib

import numpy as np
import pytest
from scipy.interpolate import RegularGridInterpolator

ROOT = pathlib.Path(__file__).resolve().parent.parent
MEASUREMENTS = ROOT / "essais" / "measurements.py"
if not MEASUREMENTS.is_file():
    pytest.skip("données d'essais absentes (essais/measurements.py)", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("measurements", MEASUREMENTS)
measurements = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measurements)
KL271_TESTS = measurements.KL271_TESTS
KL288_TEST = measurements.KL288_TEST
KL288_AIR_ABOVE = measurements.KL288_AIR_ABOVE

from model import library                                  # noqa: E402
from model.simulation import FORCED, NATURAL, Conditions, simulate  # noqa: E402

LIBRARY = ROOT / "library"


def sheet(name):
    return library.load_heatsink(LIBRARY / "dissipateurs" / f"Seifert {name}.json")


def surface_at(result, x_mm, y_mm):
    grid = result.grid
    xs = (np.arange(grid.nx) + 0.5) * grid.dx * 1e3
    ys = (np.arange(grid.ny) + 0.5) * grid.dy * 1e3
    field = RegularGridInterpolator((ys, xs), result.surface, bounds_error=False,
                                    fill_value=None)
    return field((y_mm, x_mm)).item()


def rise_errors(result, test):
    """Écart relatif sur l'échauffement de chaque capteur."""
    return np.array([(surface_at(result, x, y) - test.ambient) / (t - test.ambient) - 1
                     for x, y, t in test.sensors.values()])


def rms(errors):
    return math.sqrt(float(np.mean(np.square(errors))))


def test_kl271_convection_forcee():
    """Convection forcée, plusieurs débits : prédiction à moins de 10 % par capteur."""
    heatsink = sheet("KL-271x350")
    errors = []
    for test in KL271_TESTS:
        speed = test.flow / 3600 / heatsink.flow_area          # convention de la fiche
        result = simulate(heatsink, 0.350, test.sources,
                          Conditions(FORCED, ambient=test.ambient, speed=speed,
                                     reversed_flow=True))
        assert result.warnings == []
        errors.append(rise_errors(result, test))
    errors = np.array(errors)
    assert rms(errors) < 0.06
    assert np.abs(errors).max() < 0.10


def test_kl288_convection_naturelle():
    """Convection naturelle : capteurs et échauffement de l'air au-dessus des ailettes."""
    heatsink = sheet("KL-288x350")
    test = KL288_TEST
    result = simulate(heatsink, 0.350, test.sources,
                      Conditions(NATURAL, ambient=test.ambient, black_anodised=True))
    errors = rise_errors(result, test)
    assert rms(errors) < 0.03
    assert np.abs(errors).max() < 0.05
    assert result.air_outlet == pytest.approx(KL288_AIR_ABOVE, abs=1.0)
    # la fiche est déjà donnée pour une surface anodisée noire : pas de seconde correction
    assert result.warnings == []
    plain = simulate(heatsink, 0.350, test.sources,
                     Conditions(NATURAL, ambient=test.ambient, black_anodised=False))
    assert plain.hottest > result.hottest + 2.0


def test_conduction_des_ailettes_necessaire_en_convection_naturelle():
    """Sans la conduction des ailettes selon y, l'essai KL-288 n'est plus reproduit."""
    import dataclasses
    heatsink = dataclasses.replace(sheet("KL-288x350"), mass_per_m=0.0)
    assert heatsink.y_factor == 1.0
    result = simulate(heatsink, 0.350, KL288_TEST.sources,
                      Conditions(NATURAL, ambient=KL288_TEST.ambient, black_anodised=True))
    assert rms(rise_errors(result, KL288_TEST)) > 0.05
