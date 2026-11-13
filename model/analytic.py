# model/analytic.py
"""
Solutions analytiques de référence, pour vérifier le solveur.

Source rectangulaire à flux uniforme, centrée sur une plaque rectangulaire d'épaisseur
uniforme, refroidie sur la face opposée par un coefficient h uniforme (bords isolés) :
série de Fourier de Yovanovich, Muzychka et Culham, « Spreading resistance of isoflux
rectangles and strips on compound flux channels », J. Thermophysics and Heat Transfer,
1999.
"""
import numpy as np


def centred_source_resistance(plate_x: float, plate_y: float, thickness: float,
                              source_x: float, source_y: float, conductivity: float,
                              h: float, terms: int = 400) -> float:
    """
    Résistance (K/W) entre la température moyenne de la source et l'air : traversée 1D
    de la plaque, échange, et résistance d'épanouissement.
    """
    a, b = source_x / 2.0, source_y / 2.0       # demi-côtés de la source
    c, d = plate_x / 2.0, plate_y / 2.0         # demi-côtés de la plaque
    k, t = conductivity, thickness

    def phi(zeta):
        # tanh plutôt que sinh / cosh : pas de dépassement aux grands arguments
        th = np.tanh(zeta * t)
        return (zeta + h / k * th) / (zeta * th + h / k)

    m = np.arange(1, terms + 1)
    delta = m * np.pi / c
    lam = m * np.pi / d
    r_x = np.sum(np.sin(a * delta) ** 2 / delta ** 3 * phi(delta)) / (2 * a * a * c * d * k)
    r_y = np.sum(np.sin(b * lam) ** 2 / lam ** 3 * phi(lam)) / (2 * b * b * c * d * k)
    dd, ll = np.meshgrid(delta, lam, indexing="ij")
    beta = np.hypot(dd, ll)
    r_xy = np.sum(np.sin(a * dd) ** 2 * np.sin(b * ll) ** 2
                  / (dd ** 2 * ll ** 2 * beta) * phi(beta)) / (a * a * b * b * c * d * k)
    area = plate_x * plate_y
    return thickness / (k * area) + 1.0 / (h * area) + r_x + r_y + r_xy
