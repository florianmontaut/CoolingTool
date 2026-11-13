# controller/main_controller.py
"""Contrôleur principal : relie la fenêtre, les réglages et (à venir) le modèle."""
import pathlib

from PyQt6 import QtCore, QtGui, QtWidgets

from qtsocle import options_panel, settings, theme
from ressources import app_settings


class MainController(QtCore.QObject):

    def __init__(self, view, data_dir):
        super().__init__()
        self.view = view
        self.data_dir = pathlib.Path(data_dir)
        self.settings_path = self.data_dir / "settings.json"
        self.schema = app_settings.schema(str(self.data_dir / "library"))
        # réglages : valeurs par défaut du schéma, remplacées par celles enregistrées
        self.options = settings.load(self.settings_path,
                                     {"dark_mode": False,
                                      **options_panel.schema_defaults(self.schema)})

        # modèles Qt parentés à leur vue : détruits avec elle, dans l'ordre
        self.tree_model = QtGui.QStandardItemModel(view.tree)
        view.tree.setModel(self.tree_model)

        # slots en méthodes liées (pas de lambda qui garderait le contrôleur en vie)
        view.actionOptions.triggered.connect(self.edit_options)
        view.actionDark.toggled.connect(self.set_dark_mode)
        view.closing.connect(self.save_settings)

        view.actionDark.setChecked(bool(self.options["dark_mode"]))
        self.apply_theme()

    # ------------------------------------------------------------ thème
    def set_dark_mode(self, enabled: bool):
        self.options["dark_mode"] = bool(enabled)
        self.apply_theme()

    def apply_theme(self):
        theme.apply(QtWidgets.QApplication.instance(), self.options["dark_mode"],
                    extra_qss=theme.ITEM_VIEW_QSS)
        self.view.refresh_theme()

    # ------------------------------------------------------------ réglages
    def edit_options(self):
        dialog = options_panel.OptionsPannel(self.schema, self.options, self.view)
        if dialog.exec():
            self.options.update(dialog.getOptions())
            self.save_settings()

    def save_settings(self):
        settings.save(self.settings_path, self.options)
