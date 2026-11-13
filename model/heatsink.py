# model/heatsink.py
"""
Fiche d'un dissipateur extrudé, décrit par les données de son catalogue : géométrie
hors tout, résistance thermique en convection naturelle et forcée à une longueur de
référence, et abaques de correction (vitesse d'air, longueur).

Unités internes : SI (m, W, K). Les fichiers de la librairie sont en mm.
"""
from dataclasses import dataclass

from .curves import CurveSet

FORMAT = "CoolingTool dissipateur v1"


@dataclass(frozen=True)
class Heatsink:
    name: str
    width: float                # largeur de la semelle (m)
    height: float               # hauteur hors tout (m)
    base: float                 # épaisseur de la semelle (m)
    conductivity: float         # W/(m.K)
    rth_length: float           # longueur d'essai du catalogue (m)
    rth_natural: float          # K/W, ailettes verticales, surface brute
    rth_forced: float           # K/W à forced_speed
    curves: CurveSet
    natural_delta_t: float = 70.0   # échauffement de l'essai en convection naturelle (K)
    forced_speed: float = 3.0       # vitesse de l'essai en convection forcée (m/s)
    test_coverage: float = 0.5      # part de la semelle couverte par la source d'essai
    manufacturer: str = ""
    mass_per_m: float = 0.0     # kg/m
    source: str = ""
    notes: str = ""

    @property
    def flow_area(self) -> float:
        """
        Section du conduit d'air (m2) : zone des ailettes, vue de face. La vitesse
        d'air est celle mesurée dans ce conduit en amont du dissipateur.
        """
        return self.width * (self.height - self.base)

    @classmethod
    def from_dict(cls, data: dict, curves: CurveSet) -> "Heatsink":
        if data.get("format") != FORMAT:
            raise ValueError(f"format de fiche inconnu : {data.get('format')!r}")
        rth = data["rth"]
        return cls(
            name=data["name"],
            manufacturer=data.get("manufacturer", ""),
            width=data["width_mm"] / 1000.0,
            height=data["height_mm"] / 1000.0,
            base=data["base_mm"] / 1000.0,
            mass_per_m=data.get("mass_kg_per_m", 0.0),
            conductivity=data["conductivity_W_mK"],
            rth_length=rth["length_mm"] / 1000.0,
            rth_natural=rth["natural_K_W"],
            natural_delta_t=rth.get("natural_delta_T_K", 70.0),
            rth_forced=rth["forced_K_W"],
            forced_speed=rth.get("forced_speed_m_s", 3.0),
            test_coverage=rth.get("source_coverage", 0.5),
            curves=curves,
            source=data.get("source", ""),
            notes=data.get("notes", ""),
        )
