# model/curves.py
"""
Abaques de correction d'un constructeur : facteur multiplicatif de la résistance
thermique en fonction de la vitesse d'air et de la longueur du profilé.
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Curve:
    """
    Courbe y(x) relevée par points, x et y strictement positifs. Interpolée en
    log-log (ces abaques sont proches de lois en puissance), et prolongée au-delà des
    points par la pente du dernier segment.
    """
    points: tuple       # ((x, y), ...) triés par x croissant

    def __post_init__(self):
        points = tuple(sorted((float(x), float(y)) for x, y in self.points))
        if len(points) < 2 or any(x <= 0 or y <= 0 for x, y in points):
            raise ValueError("une courbe demande au moins 2 points, à x et y positifs")
        object.__setattr__(self, "points", points)

    @property
    def x_min(self) -> float:
        return self.points[0][0]

    @property
    def x_max(self) -> float:
        return self.points[-1][0]

    def covers(self, x: float) -> bool:
        """Vrai si x est dans la plage relevée (sinon la valeur est extrapolée)."""
        return self.x_min <= x <= self.x_max

    def __call__(self, x: float) -> float:
        if x <= 0:
            raise ValueError(f"abscisse non positive : {x}")
        points = self.points
        index = 1
        while index < len(points) - 1 and x > points[index][0]:
            index += 1
        (x0, y0), (x1, y1) = points[index - 1], points[index]
        slope = math.log(y1 / y0) / math.log(x1 / x0)
        return y0 * (x / x0) ** slope


@dataclass(frozen=True)
class CurveSet:
    """
    Courbes de correction d'une famille de dissipateurs (un catalogue, ou des mesures) :
    facteur sur la Rth forcée selon la vitesse d'air, et selon la longueur. La longueur
    peut avoir une courbe propre à la convection naturelle (sinon la même).
    """
    name: str
    speed: Curve        # facteur sur Rth forcée en fonction de la vitesse (m/s)
    length: Curve       # facteur sur Rth en fonction de la longueur (m)
    source: str = ""
    length_natural: Curve | None = None

    def speed_factor(self, speed: float, reference: float) -> float:
        """Rth(speed) / Rth(reference)."""
        return self.speed(speed) / self.speed(reference)

    def length_curve(self, natural: bool = False) -> Curve:
        return self.length_natural if natural and self.length_natural else self.length

    def length_factor(self, length: float, reference: float, natural: bool = False) -> float:
        """Rth(length) / Rth(reference)."""
        curve = self.length_curve(natural)
        return curve(length) / curve(reference)

    @classmethod
    def from_dict(cls, data: dict) -> "CurveSet":
        def lengths(points):
            return Curve(tuple((x / 1000.0, y) for x, y in points))

        natural = data.get("length_natural_mm")
        return cls(name=data["name"], source=data.get("source", ""),
                   speed=Curve(tuple(map(tuple, data["speed_m_s"]))),
                   length=lengths(data["length_mm"]),
                   length_natural=lengths(natural) if natural else None)
