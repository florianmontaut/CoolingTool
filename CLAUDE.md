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
- Socle commun **qtsocle** (https://github.com/florianmontaut/qtsocle) : thème, icônes,
  fenêtre d'options, démarrage, chemins, construction de l'exécutable. Figé à
  l'étiquette `v0.1.0` dans `requirements.txt` ; sur le poste de développement, la copie
  voisine est installée par `pip install -e ..\qtsocle`, à relancer après tout
  `pip install -r requirements.txt` (qui la remplace). Ne pas recopier son code ici :
  une correction du socle se fait dans qtsocle, puis nouvelle étiquette et mise à jour
  de `requirements.txt`.
- Lancer : `python main.py`. Tests : `python -m pytest tests`. Exécutable : `build_exe.bat`.

## Architecture

- `main.py` : point d'entrée, délègue à `qtsocle.app.run`.
- `model/` : calcul et données, sans Qt.
  - `solver.py` : conduction dans la semelle (volumes finis, quelques couches dans
    l'épaisseur), anisotrope (`y_factor` : apport des ailettes selon la longueur),
    échange côté ailettes, échauffement de l'air canal par canal.
    Transformée en cosinus selon x + systèmes bande : 5 à 30 ms par calcul.
  - `simulation.py` : `Conditions`, `Source`, `calibrate` (h tiré de la fiche),
    `simulate` (températures de semelle, de boîtier, de jonction, marges, part de la
    puissance cédée à l'intérieur du boîtier).
  - `heatsink.py`, `curves.py`, `library.py` : fiches de dissipateurs (catalogue ou
    mesure) et leurs courbes de correction (JSON).
  - `air.py` : masse volumique, pression selon l'altitude ; convection naturelle d'une
    plaque verticale (Churchill et Chu) et rayonnement, pour la face intérieure.
  - `analytic.py` : série de Fourier de l'épanouissement, référence des tests.
  - `references.py` : repères de dimensionnement (`library/reperes.json`).
- `library/` : `dissipateurs/*.json` (fiches, en mm), `courbes/*.json` (abaques ou lois
  en puissance, deux points suffisent : l'interpolation log-log les reproduit) et
  `sources/*.json` (modèles de sources : empreinte et valeurs par défaut).
  `reperes.json` : repères de dimensionnement de l'utilisateur (densités de flux par
  mode de refroidissement, chiffres clés), affichés par Aide › Repères (F1).
  Fiches Meccal (catalogue) et Seifert KL-250, KL-271, KL-288 à 350 mm (mesures de
  l'utilisateur et sa loi empirique des dissipateurs de 83 mm).
- `view/scene.py` : `ThermalScene`, la semelle vue de dessus, sa carte de température et
  les sources (`SourceItem`, un `pg.ROI` retenu dans la semelle). Coordonnées en mm.
  - `project.py` : `Project`, le fichier de projet (`*.cooling.json`, en mm). Le
    dissipateur y est cité par son nom : il doit être dans la librairie à l'ouverture.
- `view/references_dialog.py` : fenêtre non modale des repères ; les pertes admissibles
  par source y sont calculées (densité × empreinte de chaque modèle de la librairie).
- `view/main_window.py` : barre de menus (Fichier, Sources, Affichage, Aide) qui reprend
  les actions de la barre d'outils ; à gauche l'arborescence du projet puis la librairie (filtre et
  table) ; au centre la scène puis le tableau de résultats ; à droite deux arbres de
  paramètres (élément sélectionné ; dissipateur, conditions, actions).
- `controller/main_controller.py` : tient le projet (dissipateur, longueur, sources,
  conditions), relance `simulate` à chaque changement, y compris pendant un déplacement
  à la souris (en repartant du résultat précédent : `start`), et met à jour la scène,
  l'arborescence et les résultats. Gère les groupes de sources, la librairie (option
  « Répertoire de la librairie ») et les fichiers de projet.
- `tests/` : `reference_solver.py` est une seconde écriture du solveur (matrice creuse),
  comparée à la première ; les autres tests s'appuient sur des solutions analytiques.
  `test_validation.py` prédit les essais de l'utilisateur à partir des seules fiches ; il
  les lit dans `essais/measurements.py`, dossier **ignoré par git** (données internes de
  l'utilisateur, à ne jamais versionner ni recopier dans un fichier suivi) et se saute
  sans lui. `helpers.make_controller` remplace les dialogues du contrôleur.

## Choix de conception à respecter

- Unités internes SI (m, W, K, °C pour les températures) ; mm dans les fichiers JSON.
- Axes : x = largeur de la semelle, y = longueur (sens de l'extrusion et de l'air),
  z = épaisseur. L'air va de y = 0 vers y = longueur (`reversed_flow` pour l'inverse,
  en convection forcée). En convection naturelle, ailettes verticales, y = 0 est en bas.
- Le catalogue donne une résistance globale dans une condition d'essai (source uniforme
  centrée sur 50 % de la semelle). On n'applique jamais ce Rth directement : `calibrate`
  cherche le h qui fait retrouver ce Rth au modèle placé dans la condition d'essai.
  Sans cela l'échauffement de l'air serait compté deux fois.
- Vitesse d'air = débit / `Heatsink.flow_area` : la fenêtre d'air de la fiche
  (`air_window_mm2`, convention de l'utilisateur : conduit avec 5 mm de jeu autour du
  dissipateur, moins le métal), sinon largeur × hauteur d'ailettes. Air chaud ou
  altitude : vitesse équivalente à débit massique égal dans les conditions de référence.
- Conduction : selon y, toute la section de métal du profil (masse linéique / 2 700) ;
  selon x, la semelle seule. Sans masse linéique, isotrope. Indispensable en convection
  naturelle (essai KL-288 : 8 % d'écart sans, 1,6 % avec).
- Convection naturelle, ailettes verticales : l'air monte et s'échauffe ; son
  échauffement en haut vaut `natural_air_ratio` (0,35, essai KL-288) fois l'échauffement
  moyen de la semelle. h ~ échauffement^0,25. Ailettes horizontales : air à l'ambiante
  partout.
- Point fixe unique dans `simulate` : h et débit d'air (naturelle) et échange intérieur
  sont mis à jour ensemble, une résolution par itération (5 en naturelle, 2 en repartant
  d'un résultat précédent du même calage). Ne pas revenir à des boucles imbriquées :
  c'était 60 résolutions et 0,5 à 0,7 s par calcul.
- Face intérieure (`Conditions.internal`) : dissipateur en paroi du boîtier, ailettes
  dehors. La face de montage non couverte par les sources échange avec l'intérieur :
  convection naturelle d'une plaque verticale (hauteur = longueur, largeur si ailettes
  horizontales) + rayonnement (émissivité 0,85 anodisé, 0,15 brut) vers des parois à la
  température interne ; ou h imposé (`internal_h`). Cet échange est une puissance
  retranchée sur la face de montage : le solveur reste inchangé.
- Groupes : `Source.group` porte le nom du groupe (un seul niveau). Le contrôleur
  déplace, pivote, clone et supprime un groupe d'un bloc (`_shift` le garde entier dans
  la semelle). Sur la scène, saisir une source groupée prend le groupe ; Alt, la source
  seule. La scène ne connaît pas les groupes : elle transmet l'état d'Alt.
- Finition : une fiche `anodised` donne sa Rth naturelle pour une surface anodisée noire ;
  `finish_factor` ne la recorrige pas. Le contrôleur règle « Anodisé noir » sur la
  finition de la fiche quand on change de dissipateur.
- Le solveur suppose une semelle homogène et un h uniforme : c'est ce qui permet la
  transformée en cosinus. Un h variable selon y resterait compatible ; selon x, non.
- Interface en mm et °C, modèle en SI : les conversions sont dans le contrôleur.
- Les sources sont des `Source` figées : une modification remplace l'objet dans
  `ctrl.sources`. `_structure_changed` après un ajout, un retrait ou un changement de
  taille ; `refresh` suffit après un déplacement.
- Un changement venu du contrôleur vers les paramètres ou l'arbre se fait sous
  `self._updating`, sinon les signaux bouclent.
- Toute modification du projet passe par `_set_modified()` (titre étoilé, question à la
  fermeture). Les dialogues sont des méthodes à part (`_ask_open_path`, `_ask_save_path`,
  `_ask_save_changes`, `_error`) : un dialogue appelé directement bloquerait les tests.
- Option « Répertoire de la librairie » vide = librairie livrée. On n'y enregistre jamais
  le chemin de la librairie livrée : dans l'exécutable il change à chaque lancement.
  Une fiche illisible est ignorée et signalée dans la barre d'état.
- Données de l'utilisateur dans le dossier donné par `qtsocle.paths.user_data_dir`,
  jamais à côté du code : dans l'exécutable, ce dossier-là est temporaire.
- Fermeture : destruction ordonnée par `qtsocle.app.run`, modèles Qt parentés à leurs
  vues, slots en méthodes liées. Sinon plantage aléatoire en sortie.

## Hypothèses confirmées par l'utilisateur

- Vitesse d'air : vitesse moyenne dans le conduit. Ses mesures la rapportent à la
  fenêtre d'air nette (18 086,5 mm² pour le KL-271, 24 222 pour le KL-288, 10 760 pour
  le KL-250) ; les fiches Meccal, faute de mieux, à largeur × hauteur d'ailettes.
- Famille de 83 mm : ailettes de 68 mm, semelle de 15 mm (16 pour le KL-288). Ailettes
  ondulées (KL-271, KL-288) ou planes (KL-250).
- Rth naturelles de ses tableaux : dissipateurs anodisés noirs, ailettes verticales,
  prises au point le plus chaud.
- Données d'essais : internes, hors du dépôt (`essais/`, ignoré par git).
- Rth du catalogue : rapporté à la température moyenne sous la source d'essai.
- Conductivité : 200 W/m.K pour tous les extrudés (équivalence entre fabricants, dont
  ceux en 6061), même si un catalogue annonce davantage.
- Cas d'usage type : air à 55 °C au niveau des ailettes ; 85 °C est la température
  maximale tolérée à l'intérieur du boîtier, pas celle de l'air de refroidissement.
- Dissipateurs toujours placés à l'extérieur du boîtier, face de montage dedans.
- Repères (retour d'expérience, calculs et essais sur modules de puissance) : 5 W/cm²
  sous la source en convection naturelle, 15 en forcée, 60 en liquide sans changement
  de phase. Convection naturelle : 450 à 500 W au plus par dissipateur (ambiante 50 °C,
  85 °C au maximum, extrudés ou ailettes rapportées de 110 à 120 mm), limite pratique
  de la répartition des pertes ; environ 1 000 W avec un assemblage à caloducs.
  Pour l'instant affichés seulement (menu), sans vérification en direct.

## Non validé

- Validé sur deux essais seulement, à 350 mm : KL-271 en forcée (prédiction sans
  ajustement : 4,5 % d'écart moyen, 9 % au pire) et KL-288 en naturelle (1,6 % ; mais sa
  Rth naturelle et `natural_air_ratio` sont calés sur ce même essai, ce n'est donc pas
  une prédiction indépendante).
- Rth naturelles de l'utilisateur : point le plus chaud (marge de dimensionnement de sa
  feuille Excel). Les fiches portent l'équivalent au sens du catalogue, × 0,91 (rapport
  établi sur le KL-288 seul) : 0,1365 (KL-271), 0,1092 (KL-288), 0,2066 (KL-250). Pas de
  mesure en forcée du KL-288 (loi empirique), ni de l'épaisseur de semelle du KL-250.
- Longueurs autres que 350 mm : exposants de la loi empirique (abaques Meccal), non
  mesurés sur les profils Seifert.
- Abaques Meccal relevés à l'œil sur le PDF (3 % environ).
- Empreintes des sources : dimensions de boîtier usuelles ou tirées des pages Infineon,
  aucune relevée sur un plan coté (voir le champ `notes` de chaque fiche). Pour les
  boîtiers sans semelle ou refroidis par le dessus, la surface de contact réelle est plus
  petite que le boîtier.
- Première interface (scène, paramètres) essayée et validée par l'utilisateur. La table
  de librairie, le tableau de résultats et les fichiers de projet n'ont été vus par
  Claude qu'en capture sans écran.
- Librairie sur un vrai partage réseau.
- Échange avec l'intérieur : corrélations de plaque libre, aucune mesure. Les
  composants, cartes et câbles devant la face gênent la convection ; le rayonnement suppose
  des parois à la température interne.
- Groupes et face intérieure : vus seulement en tests et en capture sans écran.

## Limites connues

- Régime permanent seulement. Pour un transitoire (surcharge, essai d'arrêt en tunnel),
  il faudra un calcul lancé à part, dans un thread, avec progression et annulation.
- Échange intérieur par la face de montage seulement : ni le dessus des boîtiers, ni
  les barres de puissance, ni le circuit imprimé (souvent les fuites les plus fortes).
- Les étiquettes de sources voisines se chevauchent sur la scène.
- Pas d'effet d'entrée (h plus fort au bord d'attaque), pas de fuite d'air.
- Convection naturelle : `natural_air_ratio` tiré d'un seul essai ; pas de calcul du
  tirage d'air à partir de la géométrie.
- Flux uniforme sous chaque source ; l'interface thermique est une résistance globale.
- Dissipateurs extrudés seulement (pas d'ailettes rapportées, caloducs, plaques froides).
- La librairie se lit seulement : pas d'édition ni de création de fiche depuis
  l'interface (les fiches JSON se modifient à la main).
- Un projet ne contient pas la fiche de son dissipateur : il ne s'ouvre pas sur un poste
  dont la librairie ne l'a pas.
- Pas d'annuler / rétablir, pas d'export des résultats ni de la carte.
- Rien n'empêche deux sources de se chevaucher : leurs puissances s'additionnent.
