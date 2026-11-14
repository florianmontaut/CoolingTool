"""Outils communs aux tests de l'interface (sans écran)."""
import pathlib

from qtsocle import testing, theme

from controller.main_controller import MainController
from view.main_window import MainWindow

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "library"


def make_controller(tmp_path, library=LIBRARY):
    """
    Contrôleur sur un dossier de données temporaire et la librairie du dépôt. Les
    dialogues sont remplacés (ils bloqueraient les tests) : erreurs notées dans
    ctrl.errors, réponse à « enregistrer les modifications ? » prise dans ctrl.answer
    ("discard" par défaut), chemins de fichier pris dans ctrl.open_path et
    ctrl.save_path.
    """
    testing.get_app()
    theme.add_icon_dir(ROOT / "ressources" / "icons")      # comme main.py
    ctrl = MainController(MainWindow(), tmp_path, library)
    ctrl.errors, ctrl.asked = [], []
    ctrl.answer, ctrl.open_path, ctrl.save_path = "discard", "", ""
    ctrl._error = ctrl.errors.append

    def ask_save_changes():
        ctrl.asked.append("save changes")
        return ctrl.answer

    ctrl._ask_save_changes = ask_save_changes
    ctrl._ask_open_path = lambda: str(ctrl.open_path)
    ctrl._ask_save_path = lambda: str(ctrl.save_path)
    return ctrl


def dispose(ctrl):
    testing.dispose(ctrl.view)
