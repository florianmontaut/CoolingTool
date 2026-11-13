# CoolingTool

Simulation thermique 2D d'un dissipateur portant des sources de chaleur : repérer les
points chauds dus au placement des composants ou à un flux de chaleur trop fort.

État : le moteur de calcul est écrit et testé ; l'interface graphique reste à faire.

## Lancer

```
pip install -e ..\qtsocle
pip install -r requirements.txt
python main.py
python -m pytest tests
```

## Utiliser le moteur de calcul

```python
from model import library
from model.simulation import FORCED, Conditions, Source, simulate

heatsink = library.load_heatsink("library/dissipateurs/Meccal P300 83A.json")
sources = [Source("Q1", x=0.15, y=0.08, size_x=0.062, size_y=0.106, power=250,
                  rth_jc=0.06, rth_cs=0.02, tj_max=150)]
result = simulate(heatsink, 0.300, sources,
                  Conditions(FORCED, ambient=85, speed=4.0))
for item in result.sources:
    print(item.source.name, item.sink_mean, item.junction, item.margin)
```

Longueurs en mètres, températures en °C. `result.surface` est la carte de température de
la face de montage, `result.warnings` signale les sorties d'abaque.

## Principe

Le catalogue du constructeur donne une résistance thermique globale. Le logiciel en tire
un coefficient d'échange, puis calcule la conduction dans la semelle, l'échange avec
l'air et son échauffement le long des ailettes. Voir `model/simulation.py` pour les
hypothèses.

## Librairie

- `library/dissipateurs/` : une fiche JSON par profilé (dimensions, Rth du catalogue).
- `library/courbes/` : abaques de correction (vitesse d'air, longueur) d'un catalogue.

## Construire l'exécutable

```
build_exe.bat
```

Le résultat est `dist\CoolingTool.exe`, un seul fichier à diffuser.

## Où sont les données

| Lancement | Réglages, journal des erreurs |
|---|---|
| Depuis les sources | `donnees_locales\` (ignoré par git) |
| Depuis l'exécutable | `%APPDATA%\CoolingTool\` |
# CoolingTool
