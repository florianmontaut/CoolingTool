# CoolingTool — contexte pour Claude

Application de bureau Python : simulation thermique 2D d'un dissipateur portant des
sources de chaleur, pour repérer les points chauds dus au placement ou à un flux trop
fort. Objectif de précision : 10 à 15 % sur l'échauffement.
Dépôt : https://github.com/florianmontaut/CoolingTool (branche `main`).

## Travailler avec l'utilisateur

- Répondre en **français**. Avis francs, formulés avec douceur.
- Ne committer / pousser que sur demande explicite.
- Proposer et discuter l'approche avant un développement important.

## Environnement

- Python 3.11, PyQt6 6.4.2, pyqtgraph 0.13.3, numpy, scipy, pytest (`requirements.txt`).
- Interpréteur du poste : `..\..\env\Scripts\python.exe`.
- Socle commun **qtsocle** (dépôt voisin, installé par `pip install -e ..\qtsocle`) :
  thème, icônes, fenêtre d'options, démarrage, chemins, construction de l'exécutable.
  Ne pas recopier son code ici : une correction du socle se fait dans qtsocle.
- Lancer : `python main.py`. Tests : `python -m pytest tests`. Exécutable : `build_exe.bat`.

## Architecture

- `main.py` : point d'entrée, délègue à `qtsocle.app.run`.
- `model/` : calcul et données, sans Qt.
  - `solver.py` : conduction dans la semelle (volumes finis, quelques couches dans
    l'épaisseur), échange côté ailettes, échauffement de l'air canal par canal.
    Transformée en cosinus selon x + systèmes bande : 5 à 30 ms par calcul.
  - `simulation.py` : `Conditions`, `Source`, `calibrate` (h tiré du catalogue),
    `simulate` (températures de semelle, de boîtier, de jonction, marges).
  - `heatsink.py`, `curves.py`, `library.py` : fiches de dissipateurs et abaques (JSON).
  - `air.py` : masse volumique, pression selon l'altitude.
  - `analytic.py` : série de Fourier de l'épanouissement, référence des tests.
- `library/` : `dissipateurs/*.json` (fiches, en mm), `courbes/*.json` (abaques) et
  `sources/*.json` (modèles de sources : empreinte et valeurs par défaut).
- `view/scene.py` : `ThermalScene`, la semelle vue de dessus, sa carte de température et
  les sources (`SourceItem`, un `pg.ROI` retenu dans la semelle). Coordonnées en mm.
- `view/main_window.py` : arborescence du projet à gauche, scène au centre, deux arbres
  de paramètres à droite (élément sélectionné ; dissipateur, conditions, actions).
- `controller/main_controller.py` : tient le projet (dissipateur, longueur, sources,
  conditions), relance `simulate` à chaque changement, y compris pendant un déplacement
  à la souris, et met à jour la scène, l'arborescence et les résultats.
- `tests/` : `reference_solver.py` est une seconde écriture du solveur (matrice creuse),
  comparée à la première ; les autres tests s'appuient sur des solutions analytiques.

## Choix de conception à respecter

- Unités internes SI (m, W, K, °C pour les températures) ; mm dans les fichiers JSON.
- Axes : x = largeur de la semelle, y = longueur (sens de l'extrusion et de l'air),
  z = épaisseur. L'air va de y = 0 vers y = longueur (`reversed_flow` pour l'inverse).
- Le catalogue donne une résistance globale dans une condition d'essai (source uniforme
  centrée sur 50 % de la semelle). On n'applique jamais ce Rth directement : `calibrate`
  cherche le h qui fait retrouver ce Rth au modèle placé dans la condition d'essai.
  Sans cela l'échauffement de l'air serait compté deux fois.
- Vitesse d'air = vitesse du conduit en amont, sur la section de la zone d'ailettes
  (`Heatsink.flow_area`), sans fuite. Air chaud ou altitude : vitesse équivalente à
  débit massique égal dans les conditions du catalogue.
- Convection naturelle : h ~ échauffement^0,25 (point fixe), air à l'ambiante partout.
- Le solveur suppose une semelle homogène et un h uniforme : c'est ce qui permet la
  transformée en cosinus. Un h variable selon y resterait compatible ; selon x, non.
- Interface en mm et °C, modèle en SI : les conversions sont dans le contrôleur.
- Les sources sont des `Source` figées : une modification remplace l'objet dans
  `ctrl.sources`. `_structure_changed` après un ajout, un retrait ou un changement de
  taille ; `refresh` suffit après un déplacement.
- Un changement venu du contrôleur vers les paramètres ou l'arbre se fait sous
  `self._updating`, sinon les signaux bouclent.
- Données de l'utilisateur dans le dossier donné par `qtsocle.paths.user_data_dir`,
  jamais à côté du code : dans l'exécutable, ce dossier-là est temporaire.
- Fermeture : destruction ordonnée par `qtsocle.app.run`, modèles Qt parentés à leurs
  vues, slots en méthodes liées. Sinon plantage aléatoire en sortie.

## Hypothèses confirmées par l'utilisateur

- Vitesse d'air : vitesse moyenne dans un conduit de section largeur du dissipateur ×
  hauteur d'ailettes.
- Rth du catalogue : rapporté à la température moyenne sous la source d'essai.
- Conductivité : 200 W/m.K pour tous les extrudés (équivalence entre fabricants, dont
  ceux en 6061), même si un catalogue annonce davantage.
- Cas d'usage type : air à 55 °C au niveau des ailettes ; 85 °C est la température
  maximale tolérée à l'intérieur du boîtier, pas celle de l'air de refroidissement.

## Non validé

- Aucune comparaison à une mesure. L'utilisateur a des mesures sur KL-271 et KL-288.
- Abaques Meccal relevés à l'œil sur le PDF (3 % environ).
- Empreintes des sources : dimensions de boîtier usuelles ou tirées des pages Infineon,
  aucune relevée sur un plan coté (voir le champ `notes` de chaque fiche). Pour les
  boîtiers sans semelle ou refroidis par le dessus, la surface de contact réelle est plus
  petite que le boîtier.
- L'interface n'a été vue qu'en capture sans écran, pas manipulée à la souris.

## Limites connues

- Régime permanent seulement.
- Pas d'effet d'entrée (h plus fort au bord d'attaque), pas de fuite d'air.
- Convection naturelle : pas de différence entre le haut et le bas du dissipateur.
- Flux uniforme sous chaque source ; l'interface thermique est une résistance globale.
- Dissipateurs extrudés seulement (pas d'ailettes rapportées, caloducs, plaques froides).
- La librairie est celle du dépôt, embarquée dans l'exécutable ; l'option « Répertoire
  de la librairie » n'est pas encore prise en compte.
- Pas encore de table de librairie, d'enregistrement de projet, ni de tableau de
  résultats (étape suivante de l'interface).
- Rien n'empêche deux sources de se chevaucher : leurs puissances s'additionnent.
