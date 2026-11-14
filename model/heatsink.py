# model/heatsink.py
"""
Fiche d'un dissipateur extrudé, décrite par des données de catalogue ou de mesure :
géométrie hors tout, résistance thermique en convection naturelle et forcée à une
longueur de référence, et courbes de correction (vitesse d'air, longueur).

Unités internes : SI (m, W, K). Les fichiers de la librairie sont en mm.
"""
from dataclasses import dataclass

from .curves import CurveSet

FORMAT = "CoolingTool dissipateur v1"
ALUMINIUM_DENSITY = 2700.0      # kg/m3
DEFAULT_NATURAL_AIR_RATIO = 0.35


@dataclass(frozen=True)
class Heatsink:
    name: str
    width: float                # largeur de la semelle (m)
    height: float               # hauteur hors tout (m)
    base: float                 # épaisseur de la semelle (m)
    conductivity: float         # W/(m.K)
    rth_length: float           # longueur de référence des Rth (m)
    rth_natural: float          # K/W, ailettes verticales
    rth_forced: float           # K/W à forced_speed
    curves: CurveSet
    natural_delta_t: float = 70.0   # échauffement de référence en convection naturelle (K)
    forced_speed: float = 3.0       # vitesse de référence en convection forcée (m/s)
    test_coverage: float = 0.5      # part de la semelle couverte par la source d'essai
    manufacturer: str = ""
    mass_per_m: float = 0.0     # kg/m ; donne la section de métal (conduction des ailettes)
    air_window: float = 0.0     # m2 ; section d'air de référence de la vitesse, si connue
    anodised: bool = False      # Rth naturelle donnée pour une surface anodisée noire
    # convection naturelle : échauffement de l'air en haut des ailettes rapporté à
    # l'échauffement moyen de la semelle
    natural_air_ratio: float = DEFAULT_NATURAL_AIR_RATIO
    origin: str = "catalogue"   # catalogue ou mesure
    source: str = ""
    notes: str = ""

    @property
    def flow_area(self) -> float:
        """
        Section d'air (m2) à laquelle se rapporte la vitesse d'air : la fenêtre d'air
        donnée par la fiche, sinon la zone des ailettes vue de face (largeur × hauteur
        d'ailettes). La vitesse est celle mesurée dans le conduit en amont.
        """
        if self.air_window > 0:
            return self.air_window
        return self.width * (self.height - self.base)

    @property
    def metal_area(self) -> float:
        """Section de métal du profil (m2), tirée de la masse linéique ; 0 si inconnue."""
        return self.mass_per_m / ALUMINIUM_DENSITY

    @property
    def y_factor(self) -> float:
        """
        Facteur de conduction selon la longueur : section de métal du profil (semelle et
        ailettes, continues sur toute la longueur) rapportée à celle de la semelle.
        1 si la masse linéique n'est pas renseignée.
        """
        if self.metal_area <= 0:
            return 1.0
        return max(1.0, self.metal_area / (self.width * self.base))

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
            air_window=data.get("air_window_mm2", 0.0) / 1e6,
            anodised=bool(data.get("anodised", False)),
            natural_air_ratio=data.get("natural_air_ratio", DEFAULT_NATURAL_AIR_RATIO),
            conductivity=data["conductivity_W_mK"],
            rth_length=rth["length_mm"] / 1000.0,
            rth_natural=rth["natural_K_W"],
            natural_delta_t=rth.get("natural_delta_T_K", 70.0),
            rth_forced=rth["forced_K_W"],
            forced_speed=rth.get("forced_speed_m_s", 3.0),
            test_coverage=rth.get("source_coverage", 0.5),
            curves=curves,
            origin=data.get("origin", "catalogue"),
            source=data.get("source", ""),
            notes=data.get("notes", ""),
        )
