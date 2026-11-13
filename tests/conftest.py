import pathlib
import sys

from qtsocle import testing

# tests lancés sans écran, depuis n'importe quel dossier
testing.offscreen()
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
