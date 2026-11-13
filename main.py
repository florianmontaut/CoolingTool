# main.py
"""CoolingTool : simulation thermique 2D d'un dissipateur et de ses sources de chaleur."""
import sys

from qtsocle import app, paths, theme

ROOT = paths.bundle_root(__file__)
sys.path.insert(0, str(ROOT))

from controller.main_controller import MainController      # noqa: E402
from version import __version__                            # noqa: E402
from view.main_window import MainWindow                    # noqa: E402

APP_NAME = "CoolingTool"
RESSOURCES = ROOT / "ressources"


def main() -> int:
    # depuis les sources : données dans donnees_locales/ (ignoré par git) ;
    # depuis l'exécutable : %APPDATA%\CoolingTool
    data_dir = paths.user_data_dir(APP_NAME, dev_root=ROOT / "donnees_locales")
    theme.add_icon_dir(RESSOURCES / "icons")
    return app.run(MainWindow, lambda window: MainController(window, data_dir),
                   name=APP_NAME, version=__version__,
                   icon=RESSOURCES / "icons" / "icon.ico",
                   log_file=data_dir / "erreurs.log")


if __name__ == "__main__":
    sys.exit(main())
