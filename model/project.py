# model/project.py
"""
Projet : un dissipateur de la librairie (cité par son nom), sa longueur, les conditions
de refroidissement et les sources posées dessus. Enregistré en JSON, longueurs en mm.
"""
import json
import pathlib
from dataclasses import dataclass, field

from .simulation import Conditions, Source

FORMAT = "CoolingTool projet v1"
EXTENSION = ".cooling.json"
MM = 1000.0


@dataclass
class Project:
    heatsink_name: str
    length: float                           # m
    conditions: Conditions = field(default_factory=Conditions)
    sources: list = field(default_factory=list)
    manufacturer: str = ""                  # pour le message si la fiche manque

    def to_dict(self) -> dict:
        c = self.conditions
        return {
            "format": FORMAT,
            "heatsink": {"name": self.heatsink_name, "manufacturer": self.manufacturer},
            "length_mm": self.length * MM,
            "conditions": {
                "mode": c.mode, "ambient_C": c.ambient, "speed_m_s": c.speed,
                "altitude_m": c.altitude, "reversed_flow": c.reversed_flow,
                "black_anodised": c.black_anodised, "horizontal": c.horizontal,
            },
            "sources": [{
                "name": s.name, "x_mm": s.x * MM, "y_mm": s.y * MM,
                "size_x_mm": s.size_x * MM, "size_y_mm": s.size_y * MM,
                "power_W": s.power, "rth_jc_K_W": s.rth_jc, "rth_cs_K_W": s.rth_cs,
                "tj_max_C": s.tj_max,
            } for s in self.sources],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            found = data.get("format") if isinstance(data, dict) else None
            raise ValueError(f"ce fichier n'est pas un projet CoolingTool (format {found!r})")
        try:
            c = data["conditions"]
            conditions = Conditions(
                mode=c["mode"], ambient=float(c["ambient_C"]), speed=float(c["speed_m_s"]),
                altitude=float(c.get("altitude_m", 0.0)),
                reversed_flow=bool(c.get("reversed_flow", False)),
                black_anodised=bool(c.get("black_anodised", False)),
                horizontal=bool(c.get("horizontal", False)))
            sources = [Source(
                name=str(s["name"]), x=s["x_mm"] / MM, y=s["y_mm"] / MM,
                size_x=s["size_x_mm"] / MM, size_y=s["size_y_mm"] / MM,
                power=float(s["power_W"]), rth_jc=float(s.get("rth_jc_K_W", 0.0)),
                rth_cs=float(s.get("rth_cs_K_W", 0.0)), tj_max=s.get("tj_max_C"),
            ) for s in data.get("sources", [])]
            return cls(heatsink_name=data["heatsink"]["name"],
                       manufacturer=data["heatsink"].get("manufacturer", ""),
                       length=data["length_mm"] / MM, conditions=conditions,
                       sources=sources)
        except (KeyError, TypeError) as error:
            raise ValueError(f"projet incomplet ou mal formé : {error!r}") from error

    def save(self, path) -> None:
        pathlib.Path(path).write_text(
            json.dumps(self.to_dict(), indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Project":
        try:
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except ValueError as error:
            raise ValueError(f"fichier illisible : {error}") from error
        return cls.from_dict(data)
