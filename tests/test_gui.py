import json

from qtsocle import options_panel, theme

from helpers import dispose, make_controller


def test_demarrage_avec_les_options_par_defaut(tmp_path):
    ctrl = make_controller(tmp_path)
    assert ctrl.options["library_dir"] == str(tmp_path / "library")
    assert ctrl.options["dark_mode"] is False
    dispose(ctrl)


def test_theme_sombre(tmp_path):
    ctrl = make_controller(tmp_path)
    ctrl.view.actionDark.setChecked(True)
    assert theme.colors() is theme.DARK
    ctrl.view.actionDark.setChecked(False)
    dispose(ctrl)


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


def test_fenetre_d_options(tmp_path):
    ctrl = make_controller(tmp_path)
    dialog = options_panel.OptionsPannel(ctrl.schema, ctrl.options, ctrl.view)
    assert dialog.getOptions() == {"library_dir": str(tmp_path / "library")}
    dispose(ctrl)
