# model/references.py
"""
Repères de dimensionnement : ordres de grandeur tirés de l'expérience, pour un premier
choix du mode de refroidissement. Ils ne remplacent pas la simulation.

Fichier <librairie>/reperes.json, modifiable à la main par l'équipe :
    densities   densité de flux admissible sous la source (W/cm²), par mode de
                refroidissement ; rapportée à l'empreinte de la source sur la semelle
    figures     chiffres clés : sujet, valeur, conditions, remarques
    source      origine des chiffres
"""
import json
import pathlib
from dataclasses import dataclass

FILE_NAME = "reperes.json"
FORMAT = "CoolingTool repères v1"
CM2 = 1.0e-4                    # m²


@dataclass(frozen=True)
class Density:
    cooling: str                # mode de refroidissement
    w_cm2: float                # W/cm² sous la source
    notes: str = ""

    def power(self, area: float) -> float:
        """Puissance admissible (W) sur une empreinte de area m²."""
        return self.w_cm2 * area / CM2


@dataclass(frozen=True)
class Figure:
    subject: str
    value: str
    conditions: str = ""
    notes: str = ""


@dataclass(frozen=True)
class References:
    densities: tuple = ()
    figures: tuple = ()
    density_notes: str = ""
    source: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "References":
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            found = data.get("format") if isinstance(data, dict) else None
            raise ValueError(f"format de repères inconnu : {found!r}")
        try:
            return cls(
                densities=tuple(Density(str(d["cooling"]), float(d["W_cm2"]),
                                        str(d.get("notes", "")))
                                for d in data.get("densities", [])),
                figures=tuple(Figure(str(f["subject"]), str(f["value"]),
                                     str(f.get("conditions", "")), str(f.get("notes", "")))
                              for f in data.get("figures", [])),
                density_notes=str(data.get("density_notes", "")),
                source=str(data.get("source", "")))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"repères mal formés : {error!r}") from error


def load_references(library) -> References:
    """Repères de la librairie ; OSError si le fichier manque, ValueError s'il est faux."""
    path = pathlib.Path(library) / FILE_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"{FILE_NAME} illisible : {error}") from error
    return References.from_dict(data)
