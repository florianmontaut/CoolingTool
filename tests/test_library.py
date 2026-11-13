"""Fiches de la librairie, abaques et propriétés de l'air."""
import json
import pathlib

import pytest

from model import air, library
from model.curves import Curve

LIBRARY = pathlib.Path(__file__).resolve().parent.parent / "library"


def test_fiches_de_la_librairie():
    names = [path.stem for path in library.list_heatsinks(LIBRARY)]
    assert names == ["Meccal P200 40A", "Meccal P300 83A"]
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
