"""Interface : scène, paramètres, arborescence et calcul en direct (sans écran)."""
import json

import pytest
from qtsocle import options_panel, theme

from controller import main_controller as mc
from helpers import dispose, make_controller
from model.simulation import FORCED, NATURAL


@pytest.fixture
def ctrl(tmp_path):
    controller = make_controller(tmp_path)
    yield controller
    dispose(controller)


def source_param(ctrl, name):
    return ctrl.source_params.child("Source", name)


def project_param(ctrl, group, name):
    return ctrl.project_params.child(group, name)


def tree_texts(ctrl):
    root = ctrl.tree_model.item(0)
    return [root.text()] + [root.child(row).text() for row in range(root.rowCount())]


# ------------------------------------------------------------------ démarrage
def test_demarrage(ctrl):
    assert ctrl.heatsink.name == "P200 40A"
    assert ctrl.conditions.mode == FORCED and ctrl.conditions.ambient == 55.0
    # une première source du modèle par défaut, au centre de la semelle, sélectionnée
    assert [s.name for s in ctrl.sources] == ["Q1"]
    assert (ctrl.sources[0].x, ctrl.sources[0].y) == pytest.approx((0.100, 0.100))
    assert ctrl.selected == 0
    assert ctrl.result is not None and ctrl.result.hottest > 55.0
    assert ctrl.view.statusBar().currentMessage() == ""
    texts = tree_texts(ctrl)
    assert texts[0].startswith("P200 40A — 200 mm — max ")
    assert texts[1].startswith("Q1 — 300 W — Tj ")
    assert ctrl.view.scene.source_rect(0) == pytest.approx((69.3, 46.8, 61.4, 106.4))
    assert ctrl.options["library_dir"] == "" and ctrl.library_dir == ctrl.bundled_library
    assert project_param(ctrl, "Actions", mc.P_MODEL).opts["limits"] == [
        "EasyPACK 2B", "IM06B50GC1", "Module 34 mm", "Module 62 mm", "Q-DPAK", "TOLT"]


# ------------------------------------------------------------------ souris
def test_deplacement_a_la_souris_recalcule(ctrl):
    ctrl.add_source()                       # Q2, au centre comme Q1
    before = ctrl.result.sources[0].junction
    ctrl.view.scene.move_source(1, 150.0, 140.0)
    assert (ctrl.sources[1].x, ctrl.sources[1].y) == pytest.approx((0.150, 0.140))
    # Q2 s'est éloignée : Q1 refroidit
    assert ctrl.result.sources[0].junction < before - 1.0
    # Q2 est sélectionnée par son déplacement, ses paramètres suivent
    assert ctrl.selected == 1
    assert source_param(ctrl, mc.S_X).value() == pytest.approx(150.0)
    assert source_param(ctrl, mc.S_Y).value() == pytest.approx(140.0)
    assert ctrl.view.scene.items_[1].label.toPlainText().startswith("Q2  ")


def test_source_retenue_dans_la_semelle(ctrl):
    ctrl.view.scene.move_source(0, -500.0, 9999.0)
    source = ctrl.sources[0]
    assert source.x == pytest.approx(source.size_x / 2)
    assert source.y == pytest.approx(0.200 - source.size_y / 2)


# ------------------------------------------------------------------ paramètres
def test_edition_des_parametres_de_la_source(ctrl):
    rise = ctrl.result.sources[0].junction - 55.0
    source_param(ctrl, mc.S_POWER).setValue(600.0)
    assert ctrl.sources[0].power == 600.0
    assert ctrl.result.sources[0].junction - 55.0 == pytest.approx(2 * rise)
    source_param(ctrl, mc.S_X).setValue(60.0)
    assert ctrl.view.scene.source_rect(0)[0] == pytest.approx(60.0 - 61.4 / 2)
    source_param(ctrl, mc.S_NAME).setValue("IGBT haut")
    assert tree_texts(ctrl)[1].startswith("IGBT haut — 600 W")
    source_param(ctrl, mc.S_RTH_JC).setValue(0.05)
    source_param(ctrl, mc.S_RTH_CS).setValue(0.02)
    item = ctrl.result.sources[0]
    assert item.junction == pytest.approx(item.sink_mean + 600.0 * 0.07)
    results = ctrl.source_params.child("Résultats")
    assert results.child(mc.R_JUNCTION).value() == f"{item.junction:.1f} °C"
    assert results.child(mc.R_MARGIN).value() == "—"


def test_marge_negative_signalee(ctrl):
    source_param(ctrl, mc.S_TJ_MAX).setValue(100.0)
    item = ctrl.result.sources[0]
    assert item.margin < 0
    assert ctrl.source_params.child("Résultats", mc.R_MARGIN).value() \
        == f"{item.margin:+.1f} K"
    row = ctrl.tree_model.item(0).child(0)
    assert row.foreground().color() == theme.color("danger")
    source_param(ctrl, mc.S_TJ_MAX).setValue(0.0)            # 0 : non renseignée
    assert ctrl.sources[0].tj_max is None
    assert ctrl.tree_model.item(0).child(0).foreground().color() == theme.color("text")


def test_position_saisie_hors_semelle_ramenee(ctrl):
    source_param(ctrl, mc.S_X).setValue(500.0)
    assert ctrl.sources[0].x == pytest.approx(0.200 - 0.0614 / 2)
    assert source_param(ctrl, mc.S_X).value() == pytest.approx(200.0 - 61.4 / 2)


# ------------------------------------------------------------------ actions
def test_ajouter_cloner_pivoter_supprimer(ctrl):
    project_param(ctrl, "Actions", mc.P_MODEL).setValue("TOLT")
    project_param(ctrl, "Actions", mc.P_ADD).activate()
    assert [s.name for s in ctrl.sources] == ["Q1", "Q2"]
    assert (ctrl.sources[1].size_x, ctrl.sources[1].size_y) == pytest.approx((0.0099, 0.0101))
    assert ctrl.selected == 1

    ctrl.select(0)
    ctrl.view.actionClone.trigger()
    clone = ctrl.sources[2]
    assert clone.name == "Q3" and clone.power == ctrl.sources[0].power
    assert (clone.x, clone.y) == pytest.approx((0.110, 0.110))     # décalée de 10 mm
    assert len(ctrl.view.scene.items_) == 3 and ctrl.selected == 2

    ctrl.view.actionRotate.trigger()
    assert (ctrl.sources[2].size_x, ctrl.sources[2].size_y) == pytest.approx((0.1064, 0.0614))
    assert ctrl.view.scene.source_rect(2)[2:] == pytest.approx((106.4, 61.4))

    ctrl.select(1)
    ctrl.view.actionDelete.trigger()
    assert [s.name for s in ctrl.sources] == ["Q1", "Q3"]
    assert ctrl.selected == -1 and len(ctrl.view.scene.items_) == 2
    assert len(tree_texts(ctrl)) == 3
    # sans sélection : rien à cloner, pivoter ou supprimer
    assert not ctrl.view.actionDelete.isEnabled()
    ctrl.delete_source()
    ctrl.clone_source()
    assert len(ctrl.sources) == 2
    ctrl.add_source()
    assert ctrl.sources[-1].name == "Q2"            # premier numéro libre


def test_selection_synchronisee(ctrl):
    ctrl.add_source()
    ctrl.view.tree.setCurrentIndex(ctrl.tree_model.item(0).child(0).index())
    assert ctrl.selected == 0
    assert ctrl.view.scene._selected == 0
    assert source_param(ctrl, mc.S_NAME).value() == "Q1"
    # clic sur le dissipateur : ses caractéristiques remplacent celles de la source
    ctrl.view.tree.setCurrentIndex(ctrl.tree_model.item(0).index())
    assert ctrl.selected == -1
    assert ctrl.heatsink_params.child("Dissipateur", mc.P_REFERENCE).value() \
        == "Mecc.Al P200 40A"
    assert ctrl.heatsink_params.child("Résultats", mc.H_POWER).value() == "600 W"
    # sélection à la souris dans la scène
    ctrl.view.scene.sourceSelected.emit(1)
    assert ctrl.view.tree.currentIndex().data(mc.INDEX_ROLE) == 1


# ------------------------------------------------------------------ dissipateur, conditions
def test_changement_de_dissipateur_et_de_longueur(ctrl):
    ctrl.view.scene.move_source(0, 150.0, 140.0)
    small = ctrl.result.sources[0].junction
    project_param(ctrl, "Dissipateur", mc.P_REFERENCE).setValue("P300 83A")
    assert ctrl.heatsink.name == "P300 83A"
    assert ctrl.result.sources[0].junction < small
    assert tree_texts(ctrl)[0].startswith("P300 83A — 200 mm")
    project_param(ctrl, "Dissipateur", mc.P_LENGTH).setValue(120.0)
    # la source (106,4 mm de long) est ramenée dans la semelle raccourcie
    assert ctrl.sources[0].y == pytest.approx(0.120 - 0.1064 / 2)
    project_param(ctrl, "Dissipateur", mc.P_LENGTH).setValue(800.0)
    assert "longueur 800 mm hors de l'abaque" in ctrl.view.statusBar().currentMessage()


def test_convection_naturelle(ctrl):
    conditions = ctrl.project_params.child("Conditions")
    forced = ctrl.result.sources[0].junction
    assert conditions.child(mc.P_SPEED).opts["visible"]
    assert not conditions.child(mc.P_BLACK).opts["visible"]
    conditions.child(mc.P_MODE).setValue(NATURAL)
    assert ctrl.conditions.mode == NATURAL
    assert ctrl.result.sources[0].junction > forced
    assert not conditions.child(mc.P_SPEED).opts["visible"]
    assert conditions.child(mc.P_BLACK).opts["visible"]
    assert not ctrl.view.scene.flow.isVisible()
    ctrl.select(-1)
    assert ctrl.heatsink_params.child("Résultats", mc.H_AIR_OUT).value() == "—"
    natural = ctrl.result.sources[0].junction
    conditions.child(mc.P_BLACK).setValue(True)
    assert ctrl.result.sources[0].junction < natural


def test_conditions_de_convection_forcee(ctrl):
    conditions = ctrl.project_params.child("Conditions")
    base = ctrl.result.sources[0].junction
    conditions.child(mc.P_SPEED).setValue(6.0)
    faster = ctrl.result.sources[0].junction
    assert faster < base
    conditions.child(mc.P_AMBIENT).setValue(25.0)
    assert ctrl.result.sources[0].junction < faster - 25.0
    conditions.child(mc.P_ALTITUDE).setValue(3000.0)
    assert ctrl.conditions.altitude == 3000.0
    conditions.child(mc.P_SPEED).setValue(20.0)
    assert "hors de l'abaque" in ctrl.view.statusBar().currentMessage()


# ------------------------------------------------------------------ thème, réglages
def test_theme_sombre(ctrl):
    ctrl.view.actionDark.setChecked(True)
    assert theme.colors() is theme.DARK
    ctrl.view.actionDark.setChecked(False)


def test_reglages_enregistres_a_la_fermeture(tmp_path):
    ctrl = make_controller(tmp_path)
    ctrl.view.actionDark.setChecked(True)
    dispose(ctrl)
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["dark_mode"] is True

    ctrl = make_controller(tmp_path)
    assert ctrl.view.actionDark.isChecked()
    ctrl.view.actionDark.setChecked(False)
    dispose(ctrl)


def test_fenetre_d_options(ctrl):
    dialog = options_panel.OptionsPannel(ctrl.schema, ctrl.options, ctrl.view)
    assert dialog.getOptions() == {"library_dir": ""}
