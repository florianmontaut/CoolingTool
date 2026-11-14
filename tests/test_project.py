"""Fichiers de projet, table de librairie et tableau de résultats (sans écran)."""
import json
import shutil

import pytest
from PyQt6 import QtCore
from qtsocle import theme

from controller import main_controller as mc
from helpers import LIBRARY, dispose, make_controller
from model.project import EXTENSION, FORMAT, Project
from model.simulation import FORCED, NATURAL, Conditions, Source


@pytest.fixture
def ctrl(tmp_path):
    controller = make_controller(tmp_path / "donnees")
    yield controller
    dispose(controller)


def library_rows(ctrl):
    proxy = ctrl.library_proxy
    return [[proxy.index(row, column).data() for column in range(proxy.columnCount())]
            for row in range(proxy.rowCount())]


def result_rows(ctrl):
    model = ctrl.results_model
    return [[model.item(row, column).text() for column in range(model.columnCount())]
            for row in range(model.rowCount())]


def activate(ctrl, name):
    """Double-clic sur la ligne de la librairie qui porte ce nom."""
    proxy = ctrl.library_proxy
    for row in range(proxy.rowCount()):
        if proxy.index(row, 1).data() == name:
            ctrl.view.library_table.doubleClicked.emit(proxy.index(row, 1))
            return
    raise AssertionError(f"{name} absent de la librairie affichée")


# ------------------------------------------------------------------ format de projet
def test_projet_aller_retour(tmp_path):
    project = Project(
        heatsink_name="P300 83A", manufacturer="Mecc.Al", length=0.35,
        conditions=Conditions(NATURAL, ambient=45.0, speed=2.0, altitude=1500.0,
                              reversed_flow=True, black_anodised=True, horizontal=True),
        sources=[Source("IGBT haut", 0.1, 0.2, 0.0614, 0.1064, 320.0, 0.05, 0.02, 150.0),
                 Source("Q2", 0.2, 0.1, 0.0099, 0.0101, 8.0)])
    path = tmp_path / f"essai{EXTENSION}"
    project.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == FORMAT
    # le fichier est en mm, lisible à la main
    assert data["length_mm"] == pytest.approx(350.0)
    assert data["sources"][0]["size_y_mm"] == pytest.approx(106.4)
    assert data["sources"][1]["tj_max_C"] is None
    loaded = Project.load(path)
    assert loaded.heatsink_name == "P300 83A" and loaded.manufacturer == "Mecc.Al"
    assert loaded.length == pytest.approx(0.35)
    assert loaded.conditions == project.conditions
    for a, b in zip(loaded.sources, project.sources):
        assert a.name == b.name and a.tj_max == b.tj_max
        assert (a.x, a.y, a.size_x, a.size_y, a.power, a.rth_jc, a.rth_cs) \
            == pytest.approx((b.x, b.y, b.size_x, b.size_y, b.power, b.rth_jc, b.rth_cs))


@pytest.mark.parametrize("content, message", [
    ("{ pas du json", "fichier illisible"),
    ("[1, 2]", "n'est pas un projet CoolingTool"),
    ('{"format": "RLCmeter component v2"}', "n'est pas un projet CoolingTool"),
    (json.dumps({"format": FORMAT, "heatsink": {"name": "x"}}), "incomplet ou mal formé"),
])
def test_projet_illisible(tmp_path, content, message):
    path = tmp_path / "x.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        Project.load(path)


# ------------------------------------------------------------------ enregistrer, ouvrir
def test_titre_et_etat_modifie(ctrl):
    assert not ctrl.modified
    assert ctrl.view.windowTitle().startswith("Nouveau projet — ")
    ctrl.view.scene.move_source(0, 60.0, 80.0)
    assert ctrl.modified
    assert ctrl.view.windowTitle().startswith("Nouveau projet * — ")


def test_enregistrer_puis_rouvrir(ctrl, tmp_path):
    ctrl.project_params.child("Dissipateur", mc.P_REFERENCE).setValue("P300 83A")
    ctrl.project_params.child("Dissipateur", mc.P_LENGTH).setValue(350.0)
    ctrl.project_params.child("Conditions", mc.P_SPEED).setValue(5.0)
    ctrl.view.scene.move_source(0, 80.0, 90.0)
    ctrl.add_source()
    ctrl.source_params.child("Source", mc.S_TJ_MAX).setValue(150.0)
    junctions = [item.junction for item in ctrl.result.sources]

    ctrl.save_path = tmp_path / "onduleur"             # sans extension
    ctrl.view.actionSave.trigger()
    path = tmp_path / f"onduleur{EXTENSION}"
    assert path.is_file() and ctrl.project_path == path
    assert not ctrl.modified
    assert ctrl.view.windowTitle().startswith(f"onduleur{EXTENSION} — ")
    assert ctrl.options["last_dir"] == str(tmp_path)

    # un second enregistrement ne redemande pas de nom
    ctrl.save_path = tmp_path / "autre"
    ctrl.source_params.child("Source", mc.S_NAME).setValue("Q2 bis")
    ctrl.source_params.child("Source", mc.S_NAME).setValue("Q2")
    assert ctrl.modified
    ctrl.view.actionSave.trigger()
    assert not (tmp_path / f"autre{EXTENSION}").exists()
    assert not ctrl.modified and len(Project.load(path).sources) == 2

    ctrl.view.actionNew.trigger()
    assert ctrl.heatsink.name == "P200 40A" and ctrl.project_path is None
    assert [s.name for s in ctrl.sources] == ["Q1"]
    assert ctrl.conditions == Conditions(FORCED, ambient=55.0)

    ctrl.open_path = path
    ctrl.view.actionOpen.trigger()
    assert ctrl.errors == []
    assert ctrl.heatsink.name == "P300 83A" and ctrl.length == pytest.approx(0.35)
    assert ctrl.conditions.speed == 5.0
    assert ctrl.project_params.child("Dissipateur", mc.P_LENGTH).value() == pytest.approx(350)
    assert ctrl.project_params.child("Conditions", mc.P_SPEED).value() == 5.0
    assert [s.name for s in ctrl.sources] == ["Q1", "Q2"]
    assert ctrl.sources[1].tj_max == 150.0
    assert [item.junction for item in ctrl.result.sources] == pytest.approx(junctions)
    assert len(ctrl.view.scene.items_) == 2
    assert not ctrl.modified and ctrl.selected == -1


def test_enregistrer_sous_garde_l_ancien_fichier(ctrl, tmp_path):
    ctrl.save_path = tmp_path / f"a{EXTENSION}"
    assert ctrl.save_project()
    ctrl.add_source()
    ctrl.save_path = tmp_path / "b.json"
    ctrl.view.actionSaveAs.trigger()
    assert ctrl.project_path == tmp_path / f"b{EXTENSION}"
    assert len(Project.load(tmp_path / f"a{EXTENSION}").sources) == 1
    assert len(Project.load(tmp_path / f"b{EXTENSION}").sources) == 2


def test_enregistrement_annule(ctrl):
    ctrl.add_source()
    ctrl.save_path = ""                                 # dialogue annulé
    assert ctrl.save_project() is False
    assert ctrl.modified and ctrl.project_path is None


def test_projet_modifie_confirmation(ctrl, tmp_path):
    ctrl.add_source()
    # annuler : rien ne change
    ctrl.answer = "cancel"
    ctrl.view.actionNew.trigger()
    assert len(ctrl.sources) == 2 and ctrl.asked == ["save changes"]
    ctrl.open_path = tmp_path / "inexistant.json"
    ctrl.view.actionOpen.trigger()
    assert len(ctrl.sources) == 2 and ctrl.errors == []
    # la fenêtre refuse de se fermer
    ctrl.view.show()
    ctrl.view.close()
    assert ctrl.view.isVisible()
    # enregistrer, puis poursuivre
    ctrl.answer = "save"
    ctrl.save_path = tmp_path / f"p{EXTENSION}"
    ctrl.view.actionNew.trigger()
    assert len(Project.load(tmp_path / f"p{EXTENSION}").sources) == 2
    assert len(ctrl.sources) == 1 and not ctrl.modified
    # projet non modifié : aucune question
    ctrl.asked.clear()
    ctrl.view.actionNew.trigger()
    assert ctrl.asked == []


def test_ouverture_en_echec_garde_le_projet_courant(ctrl, tmp_path):
    ctrl.view.scene.move_source(0, 60.0, 80.0)
    bad = tmp_path / "bad.json"
    bad.write_text("{ pas du json", encoding="utf-8")
    assert ctrl.load_project(bad) is False
    assert "Impossible d'ouvrir bad.json" in ctrl.errors[0]
    unknown = tmp_path / "inconnu.json"
    Project("KL-999", 0.3, manufacturer="Seifert").save(unknown)
    assert ctrl.load_project(unknown) is False
    assert "« KL-999 » (Seifert) n'est pas dans la librairie" in ctrl.errors[1]
    assert ctrl.load_project(tmp_path / "absent.json") is False
    assert ctrl.sources[0].x == pytest.approx(0.060) and ctrl.modified


def test_source_hors_semelle_ramenee_a_l_ouverture(ctrl, tmp_path):
    path = tmp_path / "p.json"
    Project("P200 40A", 0.2, sources=[Source("Q1", 0.9, 0.9, 0.02, 0.02, 10.0)]).save(path)
    assert ctrl.load_project(path)
    assert (ctrl.sources[0].x, ctrl.sources[0].y) == pytest.approx((0.19, 0.19))


# ------------------------------------------------------------------ librairie
def test_table_de_la_librairie(ctrl):
    rows = library_rows(ctrl)
    assert [row[0] for row in rows] == ["Dissipateur"] * 5 + ["Source"] * 6
    assert rows[1] == ["Dissipateur", "P300 83A", "Mecc.Al", "300 × 83 mm, semelle 11,7",
                       "0,23 / 0,078 K/W à 300 mm"]
    assert ["Source", "Module 62 mm", "Standard industriel", "61,4 × 106,4 mm",
            "62 mm ; 300 W"] in rows
    ctrl.view.library_filter.setText("infineon")
    assert sorted(row[1] for row in library_rows(ctrl)) \
        == ["EasyPACK 2B", "IM06B50GC1", "Q-DPAK", "TOLT"]
    ctrl.view.library_filter.setText("p300")
    assert [row[1] for row in library_rows(ctrl)] == ["P300 83A"]
    index = ctrl.library_proxy.index(0, 1)
    assert "Catalogue Mecc.Al" in index.data(QtCore.Qt.ItemDataRole.ToolTipRole)


def test_double_clic_dans_la_librairie(ctrl):
    activate(ctrl, "P300 83A")
    assert ctrl.heatsink.name == "P300 83A"
    assert ctrl.length == pytest.approx(0.200)          # la longueur du projet est gardée
    assert ctrl.project_params.child("Dissipateur", mc.P_REFERENCE).value() == "P300 83A"
    activate(ctrl, "Q-DPAK")
    assert [s.name for s in ctrl.sources] == ["Q1", "Q2"]
    assert (ctrl.sources[1].size_x, ctrl.sources[1].size_y) == pytest.approx((0.0154, 0.015))
    assert ctrl.selected == 1 and ctrl.modified
    assert ctrl.project_params.child("Actions", mc.P_MODEL).value() == "Q-DPAK"


def test_librairie_choisie_dans_les_options(ctrl, tmp_path):
    shared = tmp_path / "partage"
    shutil.copytree(LIBRARY, shared)
    sheet = json.loads((shared / "dissipateurs" / "Meccal P300 83A.json").read_text("utf-8"))
    sheet["name"] = "KL-271"
    (shared / "dissipateurs" / "KL-271.json").write_text(json.dumps(sheet), "utf-8")
    (shared / "dissipateurs" / "cassee.json").write_text("{ pas du json", "utf-8")
    (shared / "sources" / "TOLT.json").unlink()

    ctrl.apply_options({"library_dir": str(shared)})
    assert ctrl.library_dir == shared
    assert "KL-271" in ctrl.heatsinks and "TOLT" not in ctrl.models
    assert "KL-271" in [row[1] for row in library_rows(ctrl)]
    assert "KL-271" in ctrl.project_params.child("Dissipateur", mc.P_REFERENCE).opts["limits"]
    assert "fiche ignorée, cassee.json" in ctrl.view.statusBar().currentMessage()
    saved = json.loads(ctrl.settings_path.read_text(encoding="utf-8"))
    assert saved["library_dir"] == str(shared)

    # dossier disparu : retour à la librairie livrée, avec un avertissement
    ctrl.apply_options({"library_dir": str(tmp_path / "absent")})
    assert ctrl.library_dir == ctrl.bundled_library
    assert "librairie introuvable" in ctrl.view.statusBar().currentMessage()
    ctrl.apply_options({"library_dir": ""})
    assert ctrl.view.statusBar().currentMessage() == ""


def test_librairie_enregistree_relue_au_demarrage(tmp_path):
    shared = tmp_path / "partage"
    shutil.copytree(LIBRARY, shared)
    (shared / "sources" / "TOLT.json").unlink()
    first = make_controller(tmp_path / "donnees")
    first.apply_options({"library_dir": str(shared)})
    dispose(first)
    second = make_controller(tmp_path / "donnees")
    assert second.library_dir == shared and "TOLT" not in second.models
    dispose(second)


# ------------------------------------------------------------------ tableau de résultats
def test_tableau_de_resultats(ctrl):
    assert [ctrl.results_model.horizontalHeaderItem(c).text()
            for c in range(ctrl.results_model.columnCount())] == mc.RESULT_HEADERS
    ctrl.add_source()
    ctrl.view.scene.move_source(1, 150.0, 140.0)
    rows = result_rows(ctrl)
    assert [row[0] for row in rows] == ["Q1", "Q2"]
    for row, item in zip(rows, ctrl.result.sources):
        assert row[1] == "300"
        assert row[2] == f"{item.sink_mean:.1f}" and row[3] == f"{item.sink_max:.1f}"
        assert row[5] == f"{item.junction:.1f}"
        assert row[6:] == ["—", "—"]


def test_marge_coloree_dans_le_tableau(ctrl):
    junction = ctrl.result.sources[0].junction
    cell = lambda column: ctrl.results_model.item(0, column)      # noqa: E731
    ctrl.source_params.child("Source", mc.S_TJ_MAX).setValue(round(junction) + 50.0)
    assert cell(7).text().startswith("+")
    assert cell(7).foreground().color() == theme.color("text")
    ctrl.source_params.child("Source", mc.S_TJ_MAX).setValue(round(junction) + 5.0)
    assert cell(7).foreground().color().name().upper() == mc.WARNING_COLOR
    ctrl.source_params.child("Source", mc.S_TJ_MAX).setValue(round(junction) - 20.0)
    assert cell(7).text().startswith("-")
    assert cell(7).foreground().color() == theme.color("danger")
    assert cell(5).foreground().color() == theme.color("danger")
    assert cell(2).foreground().color() == theme.color("text")


def test_selection_par_le_tableau(ctrl):
    ctrl.add_source()
    ctrl.view.results_table.setCurrentIndex(ctrl.results_model.index(0, 3))
    assert ctrl.selected == 0 and ctrl.view.scene._selected == 0
    assert ctrl.view.tree.currentIndex().data(mc.INDEX_ROLE) == 0
    ctrl.select(1)
    assert ctrl.view.results_table.currentIndex().row() == 1
    ctrl.select(-1)
    assert not ctrl.view.results_table.currentIndex().isValid()
