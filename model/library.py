# model/library.py
"""
Lecture de la librairie :
    <librairie>/courbes/<nom>.json          abaques d'un catalogue
    <librairie>/dissipateurs/<nom>.json     fiches de dissipateurs (citent leurs abaques)
"""
import json
import pathlib

from .curves import CurveSet
from .heatsink import Heatsink

CURVES_DIR = "courbes"
HEATSINKS_DIR = "dissipateurs"


def _read(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def load_curves(library, name: str) -> CurveSet:
    return CurveSet.from_dict(_read(pathlib.Path(library) / CURVES_DIR / f"{name}.json"))


def load_heatsink(path, library=None) -> Heatsink:
    """Fiche path ; ses abaques sont cherchés dans library (par défaut : celle de la fiche)."""
    path = pathlib.Path(path)
    data = _read(path)
    library = pathlib.Path(library) if library is not None else path.parent.parent
    return Heatsink.from_dict(data, load_curves(library, data["curves"]))


def list_heatsinks(library) -> list:
    """Fiches de la librairie, triées par nom de fichier."""
    return sorted((pathlib.Path(library) / HEATSINKS_DIR).glob("*.json"))
