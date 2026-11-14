"""Groupes de sources : création, déplacement d'un bloc, actions, fichier (sans écran)."""
import pytest
from PyQt6 import QtCore

from controller import main_controller as mc
from helpers import dispose, make_controller
from model.project import Project

PLATE = 0.200                                   # P200 40A : semelle de 200 × 200 mm
HALF_X, HALF_Y = 0.0614 / 2, 0.1064 / 2         # module 62 mm


@pytest.fixture
def ctrl(tmp_path):
    controller = make_controller(tmp_path)
    yield controller
    dispose(controller)


def three_modules(ctrl):
    """Q1, Q2, Q3 côte à côte en bas de la semelle, puis groupés depuis l'arborescence."""
    ctrl.add_source()
    ctrl.add_source()
    for index, x in enumerate((40.0, 100.0, 160.0)):
        ctrl.view.scene.move_source(index, x, 60.0)
    selection = ctrl.view.tree.selectionModel()
    flags = QtCore.QItemSelectionModel.SelectionFlag
    selection.clearSelection()
    for index in range(3):
        selection.select(ctrl._source_items[index].index(), flags.Select)
    ctrl.view.actionGroup.trigger()


def centres(ctrl):
    return [(round(s.x * 1000, 3), round(s.y * 1000, 3)) for s in ctrl.sources]


def test_grouper_depuis_l_arborescence(ctrl):
    three_modules(ctrl)
    assert [s.group for s in ctrl.sources] == ["Groupe 1"] * 3
    assert ctrl.selected_group == "Groupe 1" and ctrl.selected == -1
    # arborescence : dissipateur › groupe › sources
    group = ctrl.tree_model.item(0).child(0)
    assert group.data(mc.GROUP_ROLE) == "Groupe 1" and group.rowCount() == 3
    assert group.text().startswith("Groupe 1 — 900 W — Tj max ")
    assert [group.child(row).text().split(" — ")[0] for row in range(3)] == ["Q1", "Q2", "Q3"]
    # ligne de synthèse du groupe sous celles des sources
    model = ctrl.results_model
    assert model.rowCount() == 4
    assert model.item(3, 0).text() == "Σ Groupe 1" and model.item(3, 1).text() == "900"
    hottest = max(item.junction for item in ctrl.result.sources)
    assert model.item(3, 5).text() == f"{hottest:.1f}"
    # panneau du groupe
    values = ctrl.group_params.child("Groupe")
    assert values.child(mc.G_COUNT).value() == "3"
    assert values.child(mc.G_POWER).value() == "900 W"
    assert values.child(mc.G_X).value() == pytest.approx(100.0)
    assert ctrl.group_params.child("Résultats", mc.G_HOTTEST).value().endswith(")")
    # les trois rectangles sont en évidence sur la scène
    assert ctrl.view.scene._highlighted == {0, 1, 2}


def test_le_groupe_se_deplace_d_un_bloc(ctrl):
    three_modules(ctrl)
    ctrl.view.scene.move_source(1, 100.0, 120.0)
    assert centres(ctrl) == [(40.0, 120.0), (100.0, 120.0), (160.0, 120.0)]
    assert ctrl.selected_group == "Groupe 1"        # saisir une source prend le groupe
    # les autres rectangles ont suivi sur la scène
    assert ctrl.view.scene.source_rect(2)[1] == pytest.approx(120.0 - HALF_Y * 1000)
    # le bloc bute sur le bord sans se déformer
    ctrl.view.scene.move_source(0, 40.0, 900.0)
    top = round((PLATE - HALF_Y) * 1000, 3)
    assert centres(ctrl) == [(40.0, top), (100.0, top), (160.0, top)]


def test_alt_deplace_la_source_seule(ctrl):
    three_modules(ctrl)
    ctrl.view.scene.move_source(2, 160.0, 140.0, alone=True)
    assert centres(ctrl) == [(40.0, 60.0), (100.0, 60.0), (160.0, 140.0)]
    # Alt+clic sélectionne la source ; le reste du groupe est en pointillés
    assert ctrl.selected == 2 and ctrl.selected_group == ""
    assert ctrl.view.scene._related == {0, 1}
    assert ctrl.source_params.child("Source", mc.S_GROUP).value() == "Groupe 1"


def test_position_et_nom_saisis(ctrl):
    three_modules(ctrl)
    values = ctrl.group_params.child("Groupe")
    values.child(mc.G_Y).setValue(100.0)
    assert [y for _, y in centres(ctrl)] == [100.0] * 3
    values.child(mc.G_NAME).setValue("Onduleur")
    assert [s.group for s in ctrl.sources] == ["Onduleur"] * 3
    assert ctrl.selected_group == "Onduleur"
    assert ctrl.tree_model.item(0).child(0).text().startswith("Onduleur — ")


def test_pivoter_cloner_supprimer_le_groupe(ctrl):
    three_modules(ctrl)
    ctrl.view.actionRotate.trigger()
    # rotation autour du centre du bloc (100 ; 60), puis bloc ramené dans la semelle
    assert all((s.size_x, s.size_y) == pytest.approx((0.1064, 0.0614)) for s in ctrl.sources)
    xs = [x for x, _ in centres(ctrl)]
    ys = [y for _, y in centres(ctrl)]
    assert xs[0] == xs[1] == xs[2]
    assert ys[1] - ys[0] == pytest.approx(60.0) and ys[2] - ys[1] == pytest.approx(60.0)

    ctrl.view.actionClone.trigger()
    assert [s.name for s in ctrl.sources] == ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
    assert [s.group for s in ctrl.sources[3:]] == ["Groupe 2"] * 3
    assert ctrl.selected_group == "Groupe 2"

    ctrl.view.actionDelete.trigger()
    assert [s.name for s in ctrl.sources] == ["Q1", "Q2", "Q3"]
    assert ctrl.selected_group == "" and ctrl.selected == -1


def test_ajouter_dans_le_groupe_puis_degrouper(ctrl):
    three_modules(ctrl)
    ctrl.add_source()
    assert ctrl.sources[3].group == "Groupe 1" and ctrl.selected == 3
    ctrl.view.actionUngroup.trigger()               # la source sélectionnée en sort
    assert ctrl.sources[3].group == ""
    ctrl.select_group("Groupe 1")
    ctrl.view.actionUngroup.trigger()               # le groupe est dissous
    assert all(s.group == "" for s in ctrl.sources)
    assert ctrl.results_model.rowCount() == 4
    assert not ctrl.view.actionUngroup.isEnabled()


def test_selection_du_groupe_par_le_tableau(ctrl):
    three_modules(ctrl)
    ctrl.select(-1)
    ctrl.view.results_table.setCurrentIndex(ctrl.results_model.index(3, 0))
    assert ctrl.selected_group == "Groupe 1"
    assert ctrl.view.tree.currentIndex().data(mc.GROUP_ROLE) == "Groupe 1"


def test_groupe_enregistre(ctrl, tmp_path):
    three_modules(ctrl)
    path = tmp_path / "onduleur.cooling.json"
    ctrl.save_path = path
    assert ctrl.save_project()
    assert [s.group for s in Project.load(path).sources] == ["Groupe 1"] * 3
    assert ctrl.load_project(path)
    assert ctrl.tree_model.item(0).child(0).data(mc.GROUP_ROLE) == "Groupe 1"
