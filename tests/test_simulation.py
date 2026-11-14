"""Calage sur les fiches du catalogue et simulation d'un placement de sources."""
import dataclasses
import pathlib

import pytest

from model import air, library
from model.simulation import (FORCED, NATURAL, CalibrationError, Conditions, Source,
                              calibrate, catalogue_source_bounds, simulate)

LIBRARY = pathlib.Path(__file__).resolve().parent.parent / "library"


@pytest.fixture(scope="module", params=["Meccal P200 40A", "Meccal P300 83A"])
def heatsink(request):
    return library.load_heatsink(LIBRARY / "dissipateurs" / f"{request.param}.json")


@pytest.fixture(scope="module")
def p300():
    return library.load_heatsink(LIBRARY / "dissipateurs" / "Meccal P300 83A.json")


def catalogue_source(heatsink, length, power):
    x0, x1, y0, y1 = catalogue_source_bounds(heatsink, length)
    return Source("essai", (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0, power)


def module(name, x, y, power=300.0, **fields):
    """Module de puissance 62 × 106 mm."""
    return Source(name, x, y, 0.062, 0.106, power, **fields)


def rth(result, conditions, index=0):
    item = result.sources[index]
    return (item.sink_mean - conditions.ambient) / item.source.power


# ------------------------------------------------------------------ calage
def test_l_essai_du_catalogue_est_reproduit_en_convection_forcee(heatsink):
    conditions = Conditions(FORCED, speed=3.0)
    result = simulate(heatsink, heatsink.rth_length,
                      [catalogue_source(heatsink, heatsink.rth_length, 400.0)], conditions)
    assert rth(result, conditions) == pytest.approx(heatsink.rth_forced, rel=0.01)
    assert result.warnings == []


def test_l_essai_du_catalogue_est_reproduit_en_convection_naturelle(heatsink):
    conditions = Conditions(NATURAL)
    power = heatsink.natural_delta_t / heatsink.rth_natural
    result = simulate(heatsink, heatsink.rth_length,
                      [catalogue_source(heatsink, heatsink.rth_length, power)], conditions)
    assert rth(result, conditions) == pytest.approx(heatsink.rth_natural, rel=0.01)
    assert result.sources[0].sink_mean == pytest.approx(25 + 70, abs=0.7)


def test_abaques_de_vitesse_et_de_longueur(heatsink):
    length = heatsink.rth_length
    slow = calibrate(heatsink, length, Conditions(FORCED, speed=1.0))
    fast = calibrate(heatsink, length, Conditions(FORCED, speed=6.0))
    assert slow.rth_target == pytest.approx(1.90 * heatsink.rth_forced)
    assert fast.rth_target == pytest.approx(0.69 * heatsink.rth_forced)
    assert fast.h > slow.h
    longer = calibrate(heatsink, 0.5, Conditions(FORCED, speed=3.0))
    expected = heatsink.curves.length(0.5) / heatsink.curves.length(length)
    assert longer.rth_target == pytest.approx(expected * heatsink.rth_forced)
    assert longer.rth_target < heatsink.rth_forced


def test_correctifs_de_convection_naturelle(p300):
    plain = calibrate(p300, 0.3, Conditions(NATURAL))
    black = calibrate(p300, 0.3, Conditions(NATURAL, black_anodised=True))
    flat = calibrate(p300, 0.3, Conditions(NATURAL, horizontal=True))
    assert black.rth_target == pytest.approx(0.9 * plain.rth_target)
    assert flat.rth_target == pytest.approx(1.2 * plain.rth_target)
    assert black.h > plain.h > flat.h


def test_hors_abaque_signale(p300):
    result = simulate(p300, 0.8, [module("Q1", 0.15, 0.4)], Conditions(FORCED, speed=12.0))
    assert len(result.warnings) == 2
    assert "longueur 800 mm hors de la courbe de longueur" in result.warnings[0]
    assert "vitesse équivalente 12.0 m/s hors de la courbe de vitesse" in result.warnings[1]


def test_fiche_incoherente_refusee(p300):
    impossible = dataclasses.replace(p300, rth_forced=0.002)
    with pytest.raises(CalibrationError, match="inférieure à ce que"):
        calibrate(impossible, 0.3, Conditions(FORCED))


# ------------------------------------------------------------------ placement
def test_bilan_de_puissance_et_air_en_sortie(p300):
    conditions = Conditions(FORCED, ambient=40.0, speed=4.0)
    result = simulate(p300, 0.3, [module("Q1", 0.08, 0.10, 350.0),
                                  module("Q2", 0.22, 0.20, 250.0)], conditions)
    assert result.power == pytest.approx(600.0)
    assert result.convected == pytest.approx(600.0)
    rate = air.density(40.0) * 4.0 * p300.flow_area * air.CP_AIR
    assert result.calibration.capacity_rate == pytest.approx(rate)
    assert result.air_outlet == pytest.approx(40.0 + 600.0 / rate)


def test_une_source_en_aval_d_une_autre_est_plus_chaude(p300):
    conditions = Conditions(FORCED, speed=3.0)
    first, second = module("Q1", 0.15, 0.075), module("Q2", 0.15, 0.225)
    result = simulate(p300, 0.3, [first, second], conditions)
    upstream, downstream = (item.sink_mean for item in result.sources)
    assert downstream - upstream > 0.5
    # en convection naturelle, ailettes verticales, l'air monte (y croissant) et s'échauffe
    natural = simulate(p300, 0.3, [first, second], Conditions(NATURAL))
    assert natural.sources[1].sink_mean > natural.sources[0].sink_mean + 0.5
    # ailettes horizontales : air à l'ambiante partout, plus de haut ni de bas
    flat = simulate(p300, 0.3, [first, second], Conditions(NATURAL, horizontal=True))
    assert flat.sources[0].sink_mean == pytest.approx(flat.sources[1].sink_mean)


def test_une_source_seule_est_aussi_chaude_en_amont_qu_en_aval(p300):
    """
    Propriété du modèle (h uniforme) : l'air n'apporte de la chaleur qu'aux sources
    situées en aval d'une autre. Seule, une source voit arriver de l'air frais où
    qu'elle soit.
    """
    conditions = Conditions(FORCED, speed=3.0)
    upstream = simulate(p300, 0.3, [module("Q", 0.15, 0.075)], conditions)
    downstream = simulate(p300, 0.3, [module("Q", 0.15, 0.225)], conditions)
    assert downstream.sources[0].sink_mean == pytest.approx(upstream.sources[0].sink_mean)


def test_sens_de_l_air_inverse(p300):
    sources = [module("Q1", 0.10, 0.08, 400.0), module("Q2", 0.20, 0.21, 150.0)]
    mirrored = [dataclasses.replace(s, y=0.3 - s.y) for s in sources]
    normal = simulate(p300, 0.3, sources, Conditions(FORCED))
    reverse = simulate(p300, 0.3, mirrored, Conditions(FORCED, reversed_flow=True))
    assert reverse.surface == pytest.approx(normal.surface[::-1])
    assert reverse.air_outlet == pytest.approx(normal.air_outlet)
    for a, b in zip(normal.sources, reverse.sources):
        assert b.sink_mean == pytest.approx(a.sink_mean)


def test_superposition_des_sources_en_convection_forcee(p300):
    conditions = Conditions(FORCED, ambient=30.0)
    a, b = module("Q1", 0.08, 0.10, 350.0), module("Q2", 0.22, 0.20, 250.0)
    both = simulate(p300, 0.3, [a, b], conditions).surface - 30.0
    alone = sum(simulate(p300, 0.3, [s], conditions).surface - 30.0 for s in (a, b))
    assert both == pytest.approx(alone)


def test_jonction_et_marge(p300):
    source = module("IGBT", 0.15, 0.15, 400.0, rth_jc=0.05, rth_cs=0.02, tj_max=150.0)
    item = simulate(p300, 0.3, [source], Conditions(FORCED, ambient=45.0)).sources[0]
    assert item.sink_max > item.sink_mean > 45.0
    assert item.case == pytest.approx(item.sink_mean + 400.0 * 0.02)
    assert item.junction == pytest.approx(item.sink_mean + 400.0 * 0.07)
    assert item.margin == pytest.approx(150.0 - item.junction)
    assert simulate(p300, 0.3, [module("Q", 0.15, 0.15)],
                    Conditions(FORCED)).sources[0].margin is None


def test_convection_naturelle_non_lineaire(p300):
    conditions = Conditions(NATURAL)
    full = simulate(p300, 0.3, [catalogue_source(p300, 0.3, 300.0)], conditions)
    half = simulate(p300, 0.3, [catalogue_source(p300, 0.3, 150.0)], conditions)
    # h ~ échauffement^0,25 : Rth ~ puissance^-0,2, soit + 15 % à demi-puissance
    assert 1.10 < rth(half, conditions) / rth(full, conditions) < 1.16
    assert half.h < full.h


def test_air_chaud_et_altitude(p300):
    source = [module("Q", 0.15, 0.15, 400.0)]
    sea = simulate(p300, 0.3, source, Conditions(FORCED, ambient=25.0))
    hot_high = simulate(p300, 0.3, source,
                        Conditions(FORCED, ambient=85.0, altitude=2000.0))
    ratio = air.density(85.0, 2000.0) / air.density(25.0)
    assert hot_high.calibration.equivalent_speed == pytest.approx(3.0 * ratio)
    # moins de débit massique : échauffement plus fort, au-delà du simple décalage de 60 K
    assert (hot_high.sources[0].sink_mean - 85.0) > 1.15 * (sea.sources[0].sink_mean - 25.0)
    natural_sea = simulate(p300, 0.3, source, Conditions(NATURAL))
    natural_high = simulate(p300, 0.3, source, Conditions(NATURAL, altitude=3000.0))
    assert natural_high.sources[0].sink_mean > natural_sea.sources[0].sink_mean + 2.0


def test_source_qui_depasse_ou_hors_semelle(p300):
    result = simulate(p300, 0.3, [module("Q", 0.01, 0.15)], Conditions(FORCED))
    assert "Q dépasse de la semelle" in result.warnings[0]
    assert result.convected == pytest.approx(300.0)
    with pytest.raises(ValueError, match="hors de la semelle"):
        simulate(p300, 0.3, [module("Q", 0.5, 0.15)], Conditions(FORCED))


def test_sans_puissance_tout_est_a_l_ambiante(p300):
    for mode in (FORCED, NATURAL):
        result = simulate(p300, 0.3, [module("Q", 0.15, 0.15, 0.0)],
                          Conditions(mode, ambient=55.0))
        assert result.surface == pytest.approx(55.0)
        assert result.sources[0].junction == pytest.approx(55.0)


def test_air_qui_monte_en_convection_naturelle(p300):
    conditions = Conditions(NATURAL, ambient=30.0)
    result = simulate(p300, 0.3, [module("Q", 0.15, 0.15, 200.0)], conditions)
    rise = result.surface.mean() - 30.0
    # échauffement de l'air en haut des ailettes : natural_air_ratio × échauffement moyen
    assert result.air_outlet - 30.0 == pytest.approx(p300.natural_air_ratio * rise, rel=0.02)
    assert result.convected == pytest.approx(200.0)
    # le haut de la semelle est plus chaud que le bas
    assert result.surface[-1].mean() > result.surface[0].mean()


def test_finition_anodisee_de_la_fiche(p300):
    from model.simulation import finish_factor
    anodised = dataclasses.replace(p300, anodised=True)
    assert finish_factor(p300, True) == pytest.approx(0.9)
    assert finish_factor(anodised, True) == pytest.approx(1.0)
    assert finish_factor(anodised, False) == pytest.approx(1 / 0.9)
    plain = calibrate(anodised, 0.3, Conditions(NATURAL))
    assert plain.rth_target == pytest.approx(p300.rth_natural / 0.9)
