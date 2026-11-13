"""Outils communs aux tests de l'interface (sans écran)."""
import pathlib

from qtsocle import testing, theme

from controller.main_controller import MainController
from view.main_window import MainWindow

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "library"


def make_controller(tmp_path):
    """Contrôleur sur un dossier de données temporaire et la librairie du dépôt."""
    testing.get_app()
    theme.add_icon_dir(ROOT / "ressources" / "icons")      # comme main.py
    return MainController(MainWindow(), tmp_path, LIBRARY)


def dispose(ctrl):
    testing.dispose(ctrl.view)
