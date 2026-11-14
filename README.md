# CoolingTool

Simulation thermique 2D d'un dissipateur portant des sources de chaleur : repérer les
points chauds dus au placement des composants ou à un flux de chaleur trop fort.

État : moteur de calcul et interface (scène, sources déplaçables et groupables, calcul
en direct, librairie, tableau de résultats, fichiers de projet), part de la chaleur
cédée à l'intérieur du boîtier. Validé sur deux essais à 350 mm :
KL-271 en convection forcée (4,5 % d'écart moyen sur l'échauffement) et KL-288 en
convection naturelle (1,6 %).

## Lancer

```
pip install -r requirements.txt
python main.py
python -m pytest tests
```

`requirements.txt` installe le socle commun [qtsocle](https://github.com/florianmontaut/qtsocle)
à la version figée (étiquette git). Pour modifier aussi le socle, installer ensuite sa
copie locale, qui remplace cette version :

```
pip install -e ..\qtsocle
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

Avec `Conditions(..., internal=85)`, la face de montage non couverte échange avec
l'intérieur du boîtier à 85 °C : `result.internal_power` (W) et `result.internal_ratio`
donnent la part de chaleur qui y part (négative si l'intérieur est plus chaud).

## Groupes de sources

Dans l'arborescence, Ctrl+clic sur plusieurs sources puis « Grouper » (Ctrl+G). Sur la
scène, saisir une source groupée déplace tout le groupe ; Alt+glisser, la source seule.
Un groupe sélectionné se pivote, se clone (un second onduleur) ou se supprime d'un bloc.

## Principe

Le catalogue du constructeur donne une résistance thermique globale. Le logiciel en tire
un coefficient d'échange, puis calcule la conduction dans la semelle, l'échange avec
l'air et son échauffement le long des ailettes. Voir `model/simulation.py` pour les
hypothèses.

## Librairie

- `library/dissipateurs/` : une fiche JSON par profilé : dimensions, Rth du catalogue ou
  des mesures, et facultativement masse linéique (conduction des ailettes), fenêtre
  d'air (convention de vitesse) et finition anodisée.
- `library/courbes/` : courbes de correction (vitesse d'air, longueur ; longueur en
  convection naturelle si elle diffère), relevées sur un abaque ou tirées d'une loi.
- `library/sources/` : modèles de sources de chaleur (empreinte, pertes et Rth par défaut).

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
