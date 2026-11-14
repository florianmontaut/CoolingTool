"""Fiches de la librairie, abaques et propriétés de l'air."""
import json
import pathlib

import pytest

from model import air, library
from model.curves import Curve

LIBRARY = pathlib.Path(__file__).resolve().parent.parent / "library"


def test_fiches_de_la_librairie():
    names = [path.stem for path in library.list_heatsinks(LIBRARY)]
    assert names == ["Meccal P200 40A", "Meccal P300 83A", "Seifert KL-250x350",
                     "Seifert KL-271x350", "Seifert KL-288x350"]
    p300 = library.load_heatsink(LIBRARY / "dissipateurs" / "Meccal P300 83A.json")
    assert (p300.name, p300.manufacturer) == ("P300 83A", "Mecc.Al")
    # unités internes : SI
    assert (p300.width, p300.height, p300.base) == pytest.approx((0.300, 0.083, 0.0117))
    assert p300.rth_length == pytest.approx(0.300)
    assert (p300.rth_natural, p300.rth_forced) == (0.23, 0.078)
    assert p300.flow_area == pytest.approx(0.300 * (0.083 - 0.0117))
    assert p300.curves.name == "meccal_air"


def test_format_de_fiche_inconnu(tmp_path):
    (tmp_path / "courbes").mkdir()
    (tmp_path / "dissipateurs").mkdir()
    sheet = tmp_path / "dissipateurs" / "x.json"
    sheet.write_text(json.dumps({"format": "autre", "curves": "meccal_air"}), "utf-8")
    (tmp_path / "courbes" / "meccal_air.json").write_text(
        (LIBRARY / "courbes" / "meccal_air.json").read_text("utf-8"), "utf-8")
    with pytest.raises(ValueError, match="format de fiche inconnu"):
        library.load_heatsink(sheet)


def test_abaques_meccal():
    curves = library.load_curves(LIBRARY, "meccal_air")
    assert curves.speed(3.0) == pytest.approx(1.0)
    assert curves.length(0.150) == pytest.approx(1.0)
    assert curves.speed_factor(6.0, 3.0) == pytest.approx(0.69)
    assert curves.length_factor(0.300, 0.150) == pytest.approx(0.64)
    # entre deux points : entre leurs valeurs
    assert 0.77 < curves.speed(4.5) < 0.86
    assert curves.speed.covers(8.0) and not curves.speed.covers(10.0)
    # au-delà : prolongée par la pente du dernier segment, donc toujours décroissante
    assert 0.45 < curves.speed(10.0) < 0.58


def test_courbe_interpolation_log_log():
    curve = Curve(((4.0, 0.5), (1.0, 1.0), (2.0, 1 / 2 ** 0.5)))     # y = x^-0,5, en désordre
    assert curve.points[0] == (1.0, 1.0)
    for x in (1.0, 1.5, 3.0, 0.25, 16.0):
        assert curve(x) == pytest.approx(x ** -0.5)
    with pytest.raises(ValueError):
        Curve(((1.0, 1.0),))
    with pytest.raises(ValueError):
        Curve(((0.0, 1.0), (1.0, 2.0)))
    with pytest.raises(ValueError):
        curve(0.0)


def test_air():
    assert air.density(25.0) == pytest.approx(1.184, abs=0.002)
    assert air.density(85.0) == pytest.approx(0.986, abs=0.002)
    assert air.pressure(2000.0) == pytest.approx(79500, rel=0.002)
    assert air.density(25.0, 2000.0) / air.density(25.0) == pytest.approx(0.785, abs=0.002)


def test_fiche_mesuree_kl271():
    kl271 = library.load_heatsink(LIBRARY / "dissipateurs" / "Seifert KL-271x350.json")
    assert kl271.origin == "mesure" and kl271.anodised
    # la vitesse se rapporte à la fenêtre d'air nette de la fiche
    assert kl271.flow_area == pytest.approx(18086.5e-6)
    # conduction selon la longueur : toute la section de métal (26,64 kg/m)
    assert kl271.metal_area == pytest.approx(26.64 / 2700)
    assert kl271.y_factor == pytest.approx(26.64 / 2700 / (0.300 * 0.015))
    # loi mesurée Rth = 0,0873 × v^-0,483 à 350 mm, reproduite par la courbe de vitesse
    for v in (1.0, 2.0, 3.5):
        rth = kl271.rth_forced * kl271.curves.speed_factor(v, kl271.forced_speed)
        assert rth == pytest.approx(0.08734672622319249 * v ** -0.48348463491158106)
    # longueur : exposants de la loi empirique, différents en forcée et en naturelle
    assert kl271.curves.length_factor(0.7, 0.35) == pytest.approx(2 ** -0.6866304106846668)
    assert kl271.curves.length_factor(0.7, 0.35, natural=True) \
        == pytest.approx(2 ** (0.00017 * 300 - 0.7708333333333333))


def test_fiche_sans_masse_ni_fenetre():
    p300 = library.load_heatsink(LIBRARY / "dissipateurs" / "Meccal P300 83A.json")
    assert p300.air_window == 0 and not p300.anodised
    import dataclasses
    assert dataclasses.replace(p300, mass_per_m=0.0).y_factor == 1.0
    assert p300.y_factor == pytest.approx(23.07 / 2700 / (0.300 * 0.0117))
