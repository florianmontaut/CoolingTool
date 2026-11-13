# model/library.py
"""
Lecture de la librairie :
    <librairie>/courbes/<nom>.json          abaques d'un catalogue
    <librairie>/dissipateurs/<nom>.json     fiches de dissipateurs (citent leurs abaques)
    <librairie>/sources/<nom>.json          modèles de sources de chaleur (empreintes)
"""
import json
import pathlib
from dataclasses import dataclass

from .curves import CurveSet
from .heatsink import Heatsink
from .simulation import Source

CURVES_DIR = "courbes"
HEATSINKS_DIR = "dissipateurs"
SOURCES_DIR = "sources"
SOURCE_FORMAT = "CoolingTool source v1"


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


@dataclass(frozen=True)
class SourceModel:
    """Modèle de source de la librairie : une empreinte et ses valeurs par défaut."""
    name: str
    size_x: float               # m
    size_y: float               # m
    power: float = 0.0          # W
    rth_jc: float = 0.0         # K/W
    rth_cs: float = 0.0         # K/W
    tj_max: float | None = None
    manufacturer: str = ""
    package: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SourceModel":
        if data.get("format") != SOURCE_FORMAT:
            raise ValueError(f"format de fiche inconnu : {data.get('format')!r}")
        return cls(name=data["name"],
                   size_x=data["size_x_mm"] / 1000.0, size_y=data["size_y_mm"] / 1000.0,
                   power=data.get("power_W", 0.0),
                   rth_jc=data.get("rth_jc_K_W", 0.0), rth_cs=data.get("rth_cs_K_W", 0.0),
                   tj_max=data.get("tj_max_C"),
                   manufacturer=data.get("manufacturer", ""),
                   package=data.get("package", ""), notes=data.get("notes", ""))

    def place(self, name: str, x: float, y: float) -> Source:
        """Source de ce modèle, centrée en (x, y)."""
        return Source(name=name, x=x, y=y, size_x=self.size_x, size_y=self.size_y,
                      power=self.power, rth_jc=self.rth_jc, rth_cs=self.rth_cs,
                      tj_max=self.tj_max)


def load_source_model(path) -> SourceModel:
    return SourceModel.from_dict(_read(path))


def list_source_models(library) -> list:
    """Fiches de modèles de sources, triées par nom de fichier."""
    return sorted((pathlib.Path(library) / SOURCES_DIR).glob("*.json"))
