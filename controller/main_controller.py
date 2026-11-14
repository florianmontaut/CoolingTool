# controller/main_controller.py
"""
Contrôleur principal : tient le projet (dissipateur, longueur, sources, conditions),
relance le calcul à chaque changement et met à jour la scène, l'arborescence, les
paramètres et le tableau de résultats. Gère aussi la librairie et les fichiers de projet.
Le modèle est en SI ; l'interface en mm et °C.
"""
import dataclasses
import pathlib

import pyqtgraph.parametertree as ptree
from PyQt6 import QtCore, QtGui, QtWidgets

from qtsocle import options_panel, settings, theme
from model import library
from model.project import EXTENSION, Project
from model.simulation import (FORCED, NATURAL, CalibrationError, Conditions, Source,
                              simulate)
from ressources import app_settings

MM = 1000.0
DEFAULT_AMBIENT = 55.0              # °C, air au niveau des ailettes
DEFAULT_MODEL = "Module 62 mm"
CLONE_OFFSET = 0.010                # m
LOW_MARGIN = 10.0                   # K : marge sur Tj max signalée en orange en dessous
WARNING_COLOR = "#E08A00"
INDEX_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
KIND_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2     # librairie : type de fiche
NAME_ROLE = QtCore.Qt.ItemDataRole.UserRole + 3     # librairie : nom de la fiche
KIND_HEATSINK, KIND_SOURCE = "Dissipateur", "Source"
LIBRARY_HEADERS = ["Type", "Nom", "Fabricant", "Dimensions", "Données"]
RESULT_HEADERS = ["Source", "Pertes (W)", "Semelle moy. (°C)", "Semelle max (°C)",
                  "Boîtier (°C)", "Jonction (°C)", "Tj max (°C)", "Marge (K)"]
PROJECT_FILTER = f"Projet CoolingTool (*{EXTENSION});;Tous les fichiers (*)"

# noms des paramètres (affichés tels quels)
P_REFERENCE, P_LENGTH = "Référence", "Longueur"
P_MODE, P_AMBIENT, P_SPEED, P_ALTITUDE = ("Convection", "Température d'air",
                                          "Vitesse d'air", "Altitude")
P_REVERSED, P_BLACK, P_HORIZONTAL = ("Sens de l'air inversé", "Anodisé noir",
                                     "Ailettes horizontales")
P_MODEL, P_ADD, P_CLONE, P_ROTATE, P_DELETE = ("Modèle", "Ajouter une source",
                                               "Cloner la source", "Pivoter de 90°",
                                               "Supprimer la source")
S_NAME, S_X, S_Y, S_SIZE_X, S_SIZE_Y = ("Nom", "X (centre)", "Y (centre)", "Largeur (x)",
                                        "Longueur (y)")
S_POWER, S_RTH_JC, S_RTH_CS, S_TJ_MAX = ("Pertes", "Rth jonction-boîtier",
                                         "Rth boîtier-semelle", "Tj max")
R_SINK_MEAN, R_SINK_MAX, R_CASE, R_JUNCTION, R_MARGIN = (
    "Semelle (moyenne)", "Semelle (maximum)", "Boîtier", "Jonction", "Marge sur Tj max")
H_WIDTH, H_HEIGHT, H_BASE, H_RTH_N, H_RTH_F = ("Largeur", "Hauteur", "Semelle",
                                               "Rth naturelle", "Rth forcée")
H_ORIGIN, H_WINDOW, H_METAL = "Données", "Section d'air", "Conduction des ailettes"
H_TARGET, H_COEFFICIENT, H_POWER, H_HOTTEST, H_AIR_OUT = (
    "Rth visée", "Coefficient d'échange", "Puissance totale", "Point le plus chaud",
    "Air en sortie")


def _number(name, value=0.0, suffix="", **options):
    return {"name": name, "type": "float", "value": value, "suffix": suffix,
            "decimals": 5, **options}


def _readout(name, suffix=""):
    return {"name": name, "type": "str", "value": "", "readonly": True, "suffix": suffix}


def _clamp_centre(centre: float, size: float, extent: float) -> float:
    """Centre ramené pour que [centre ± size/2] tienne dans [0, extent]."""
    if size >= extent:
        return extent / 2
    return min(max(centre, size / 2), extent - size / 2)


def _fr(value: float, decimals: int = 1) -> str:
    """Nombre court à la française : 61,4 ; 200."""
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".").replace(".", ",")


class MainController(QtCore.QObject):

    def __init__(self, view, data_dir, library_dir):
        super().__init__()
        self.view = view
        self.data_dir = pathlib.Path(data_dir)
        self.bundled_library = pathlib.Path(library_dir)     # livrée avec l'application
        self.settings_path = self.data_dir / "settings.json"
        self.schema = app_settings.schema()
        # réglages : valeurs par défaut du schéma, remplacées par celles enregistrées
        self.options = settings.load(self.settings_path,
                                     {"dark_mode": False, "last_dir": "",
                                      **options_panel.schema_defaults(self.schema)})

        self.heatsinks, self.models, self.library_errors = {}, {}, []
        self.library_dir = self.bundled_library
        self._load_library()

        # projet
        self.heatsink = next(iter(self.heatsinks.values()))
        self.length = self.heatsink.rth_length
        self.sources: list = []
        self.conditions = Conditions(FORCED, ambient=DEFAULT_AMBIENT)
        self.project_path = None
        self.modified = False
        self.selected = -1
        self.result = None
        self._updating = False          # changement venu du contrôleur : pas de boucle

        # modèles Qt parentés à leur vue : détruits avec elle, dans l'ordre
        self.tree_model = QtGui.QStandardItemModel(view.tree)
        view.tree.setModel(self.tree_model)
        self.results_model = QtGui.QStandardItemModel(view.results_table)
        self.results_model.setHorizontalHeaderLabels(RESULT_HEADERS)
        view.results_table.setModel(self.results_model)
        # colonnes à largeur égale : tout le tableau reste visible sans défilement
        view.results_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.library_model = QtGui.QStandardItemModel(view.library_table)
        self.library_proxy = QtCore.QSortFilterProxyModel(view.library_table)
        self.library_proxy.setSourceModel(self.library_model)
        self.library_proxy.setFilterKeyColumn(-1)           # toutes les colonnes
        self.library_proxy.setFilterCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        view.library_table.setModel(self.library_proxy)

        self._build_parameters()
        self._show_library()

        # slots en méthodes liées (pas de lambda qui garderait le contrôleur en vie)
        view.actionNew.triggered.connect(self.new_project)
        view.actionOpen.triggered.connect(self.open_project)
        view.actionSave.triggered.connect(self.save_project)
        view.actionSaveAs.triggered.connect(self.save_project_as)
        view.actionAdd.triggered.connect(self.add_source)
        view.actionClone.triggered.connect(self.clone_source)
        view.actionRotate.triggered.connect(self.rotate_source)
        view.actionDelete.triggered.connect(self.delete_source)
        view.actionOptions.triggered.connect(self.edit_options)
        view.actionDark.toggled.connect(self.set_dark_mode)
        view.closing.connect(self.save_settings)
        view.can_close = self.confirm_discard
        view.scene.sourceMoved.connect(self._source_dragged)
        view.scene.sourceSelected.connect(self.select)
        view.tree.selectionModel().currentChanged.connect(self._tree_selected)
        view.results_table.selectionModel().currentRowChanged.connect(self._result_selected)
        view.library_filter.textChanged.connect(self.library_proxy.setFilterFixedString)
        view.library_table.doubleClicked.connect(self._library_activated)

        view.actionDark.setChecked(bool(self.options["dark_mode"]))
        self.apply_theme()
        self._plate_changed()
        self._default_sources()
        self._structure_changed()
        self._set_modified(False)

    # ------------------------------------------------------------ librairie
    def _load_library(self):
        """
        Lit la librairie : celle de l'option « Répertoire de la librairie » si elle
        existe, sinon celle livrée avec l'application. Une fiche illisible est ignorée
        et signalée, sans empêcher le démarrage.
        """
        chosen = str(self.options.get("library_dir") or "").strip()
        folder = pathlib.Path(chosen) if chosen else self.bundled_library
        errors = []
        if chosen and not folder.is_dir():
            errors.append(f"librairie introuvable : {folder} (librairie livrée utilisée)")
            folder = self.bundled_library
        heatsinks, models = {}, {}
        for paths, load, target in ((library.list_heatsinks(folder), library.load_heatsink,
                                     heatsinks),
                                    (library.list_source_models(folder),
                                     library.load_source_model, models)):
            for path in paths:
                try:
                    sheet = load(path)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    errors.append(f"fiche ignorée, {path.name} : {error}")
                    continue
                target[sheet.name] = sheet
        if not heatsinks:
            if folder == self.bundled_library:
                raise FileNotFoundError(f"aucun dissipateur dans {folder}")
            errors.append(f"aucun dissipateur dans {folder} (librairie livrée utilisée)")
            self.options["library_dir"] = ""
            self._load_library()
            self.library_errors = errors + self.library_errors
            return
        self.library_dir, self.heatsinks, self.models = folder, heatsinks, models
        self.library_errors = errors

    def _show_library(self):
        """Remplit la table de la librairie et les listes de choix des paramètres."""
        model = self.library_model
        model.clear()
        model.setHorizontalHeaderLabels(LIBRARY_HEADERS)

        def row(kind, name, texts, tip):
            items = [QtGui.QStandardItem(text) for text in [kind] + texts]
            for item in items:
                item.setData(kind, KIND_ROLE)
                item.setData(name, NAME_ROLE)
                item.setToolTip(tip)
            model.appendRow(items)

        for sheet in self.heatsinks.values():
            row(KIND_HEATSINK, sheet.name,
                [sheet.name, sheet.manufacturer,
                 f"{_fr(sheet.width * MM)} × {_fr(sheet.height * MM)} mm, "
                 f"semelle {_fr(sheet.base * MM)}",
                 f"{_fr(sheet.rth_natural, 3)} / {_fr(sheet.rth_forced, 3)} K/W "
                 f"à {_fr(sheet.rth_length * MM)} mm"],
                "\n".join(filter(None, [sheet.source, sheet.notes])))
        for sheet in self.models.values():
            row(KIND_SOURCE, sheet.name,
                [sheet.name, sheet.manufacturer,
                 f"{_fr(sheet.size_x * MM)} × {_fr(sheet.size_y * MM)} mm",
                 " ; ".join(filter(None, [sheet.package, f"{_fr(sheet.power)} W"]))],
                sheet.notes)
        table = self.view.library_table
        table.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        table.resizeColumnsToContents()

        self._updating = True
        try:
            reference = self.project_params.child("Dissipateur", P_REFERENCE)
            reference.setLimits(list(self.heatsinks))
            reference.setValue(self.heatsink.name)
            chooser = self.project_params.child("Actions", P_MODEL)
            current = chooser.value()
            names = list(self.models)
            chooser.setLimits(names)
            if names:
                chooser.setValue(current if current in names
                                 else (DEFAULT_MODEL if DEFAULT_MODEL in names else names[0]))
        finally:
            self._updating = False

    def _library_activated(self, index):
        """Double-clic dans la librairie : charge le dissipateur ou ajoute la source."""
        kind, name = index.data(KIND_ROLE), index.data(NAME_ROLE)
        if kind == KIND_HEATSINK:
            self.project_params.child("Dissipateur", P_REFERENCE).setValue(name)
        elif kind == KIND_SOURCE:
            self.project_params.child("Actions", P_MODEL).setValue(name)
            self.add_source()

    # ------------------------------------------------------------ paramètres
    def _build_parameters(self):
        models = list(self.models)
        self.project_params = ptree.Parameter.create(name="", type="group", children=[
            {"name": "Dissipateur", "type": "group", "children": [
                {"name": P_REFERENCE, "type": "list", "limits": list(self.heatsinks),
                 "value": self.heatsink.name},
                _number(P_LENGTH, self.length * MM, "mm", limits=(20.0, 3000.0), step=10.0),
            ]},
            {"name": "Conditions", "type": "group", "children": [
                {"name": P_MODE, "type": "list", "limits": [FORCED, NATURAL],
                 "value": self.conditions.mode},
                _number(P_AMBIENT, self.conditions.ambient, "°C", step=5.0),
                _number(P_SPEED, self.conditions.speed, "m/s", limits=(0.1, 30.0), step=0.5,
                        tip="Vitesse moyenne de l'air dans le conduit, rapportée à la "
                            "section d'air de la fiche du dissipateur"),
                _number(P_ALTITUDE, 0.0, "m", limits=(0.0, 6000.0), step=100.0),
                {"name": P_REVERSED, "type": "bool", "value": False},
                {"name": P_BLACK, "type": "bool", "value": False},
                {"name": P_HORIZONTAL, "type": "bool", "value": False},
            ]},
            {"name": "Actions", "type": "group", "children": [
                {"name": P_MODEL, "type": "list", "limits": models,
                 "value": DEFAULT_MODEL if DEFAULT_MODEL in models
                 else (models[0] if models else None)},
                {"name": P_ADD, "type": "action"},
                {"name": P_CLONE, "type": "action"},
                {"name": P_ROTATE, "type": "action"},
                {"name": P_DELETE, "type": "action"},
            ]},
        ])
        self.view.project_tree.setParameters(self.project_params, showTop=False)
        self.project_params.child("Dissipateur").sigTreeStateChanged.connect(
            self._heatsink_edited)
        self.project_params.child("Conditions").sigTreeStateChanged.connect(
            self._conditions_edited)
        actions = self.project_params.child("Actions")
        actions.child(P_ADD).sigActivated.connect(self.add_source)
        actions.child(P_CLONE).sigActivated.connect(self.clone_source)
        actions.child(P_ROTATE).sigActivated.connect(self.rotate_source)
        actions.child(P_DELETE).sigActivated.connect(self.delete_source)

        self.source_params = ptree.Parameter.create(name="", type="group", children=[
            {"name": "Source", "type": "group", "children": [
                {"name": S_NAME, "type": "str", "value": ""},
                _number(S_X, suffix="mm", step=1.0),
                _number(S_Y, suffix="mm", step=1.0),
                _number(S_SIZE_X, 10.0, "mm", limits=(1.0, 3000.0), step=1.0),
                _number(S_SIZE_Y, 10.0, "mm", limits=(1.0, 3000.0), step=1.0),
                _number(S_POWER, suffix="W", limits=(0.0, 1e6), step=10.0),
                _number(S_RTH_JC, suffix="K/W", limits=(0.0, 1e3), step=0.01),
                _number(S_RTH_CS, suffix="K/W", limits=(0.0, 1e3), step=0.01),
                _number(S_TJ_MAX, suffix="°C", limits=(0.0, 1e3), step=5.0,
                        tip="0 : non renseignée"),
            ]},
            {"name": "Résultats", "type": "group", "children": [
                _readout(R_SINK_MEAN), _readout(R_SINK_MAX), _readout(R_CASE),
                _readout(R_JUNCTION), _readout(R_MARGIN),
            ]},
        ])
        self.source_params.child("Source").sigTreeStateChanged.connect(self._source_edited)

        self.heatsink_params = ptree.Parameter.create(name="", type="group", children=[
            {"name": "Dissipateur", "type": "group", "children": [
                _readout(P_REFERENCE), _readout(H_WIDTH), _readout(H_HEIGHT),
                _readout(H_BASE), _readout(H_RTH_N), _readout(H_RTH_F),
                _readout(H_ORIGIN), _readout(H_WINDOW), _readout(H_METAL),
            ]},
            {"name": "Résultats", "type": "group", "children": [
                _readout(H_TARGET), _readout(H_COEFFICIENT), _readout(H_POWER),
                _readout(H_HOTTEST), _readout(H_AIR_OUT),
            ]},
        ])

    def _condition(self, name):
        return self.project_params.child("Conditions", name).value()

    def _conditions_edited(self, *_):
        if self._updating:
            return
        self.conditions = Conditions(
            mode=self._condition(P_MODE), ambient=self._condition(P_AMBIENT),
            speed=self._condition(P_SPEED), altitude=self._condition(P_ALTITUDE),
            reversed_flow=self._condition(P_REVERSED),
            black_anodised=self._condition(P_BLACK),
            horizontal=self._condition(P_HORIZONTAL))
        self._set_modified()
        self._show_conditions()
        self.refresh()

    def _show_conditions(self):
        """N'affiche que les réglages qui comptent dans le mode de convection choisi."""
        forced = self.conditions.mode == FORCED
        group = self.project_params.child("Conditions")
        for name in (P_SPEED, P_REVERSED):
            group.child(name).setOpts(visible=forced)
        for name in (P_BLACK, P_HORIZONTAL):
            group.child(name).setOpts(visible=not forced)
        # convection naturelle, ailettes verticales : l'air monte (y croissant)
        self.view.scene.set_flow(forced or not self.conditions.horizontal,
                                 forced and self.conditions.reversed_flow)

    def _show_project_values(self):
        """Reporte le projet dans les paramètres (ouverture, nouveau projet)."""
        c = self.conditions
        group = self.project_params.child("Conditions")
        self._updating = True
        try:
            self.project_params.child("Dissipateur", P_REFERENCE).setValue(self.heatsink.name)
            self.project_params.child("Dissipateur", P_LENGTH).setValue(self.length * MM)
            for name, value in ((P_MODE, c.mode), (P_AMBIENT, c.ambient), (P_SPEED, c.speed),
                                (P_ALTITUDE, c.altitude), (P_REVERSED, c.reversed_flow),
                                (P_BLACK, c.black_anodised), (P_HORIZONTAL, c.horizontal)):
                group.child(name).setValue(value)
        finally:
            self._updating = False

    def _heatsink_edited(self, *_):
        if self._updating:
            return
        group = self.project_params.child("Dissipateur")
        heatsink = self.heatsinks[group.child(P_REFERENCE).value()]
        if heatsink is not self.heatsink:
            # finition par défaut : celle pour laquelle la fiche est donnée
            self.heatsink = heatsink
            self.project_params.child("Conditions", P_BLACK).setValue(heatsink.anodised)
        self.length = group.child(P_LENGTH).value() / MM
        self._set_modified()
        self._plate_changed()
        self._structure_changed()

    def _plate_changed(self):
        """Nouvelle semelle : les sources y sont ramenées, la vue est recadrée."""
        self.sources = [self._inside(source) for source in self.sources]
        self.view.scene.set_plate(self.heatsink.width * MM, self.length * MM)
        self._show_conditions()

    def _inside(self, source: Source) -> Source:
        return dataclasses.replace(
            source,
            x=_clamp_centre(source.x, source.size_x, self.heatsink.width),
            y=_clamp_centre(source.y, source.size_y, self.length))

    # ------------------------------------------------------------ sources
    def _next_name(self) -> str:
        names = {source.name for source in self.sources}
        number = 1
        while f"Q{number}" in names:
            number += 1
        return f"Q{number}"

    def _default_sources(self):
        """Projet de départ : une source du modèle par défaut, au centre."""
        model = self.models.get(DEFAULT_MODEL)
        self.sources = [] if model is None else [self._inside(
            model.place("Q1", self.heatsink.width / 2, self.length / 2))]
        self.selected = 0 if self.sources else -1

    def add_source(self, *_):
        model = self.models.get(self.project_params.child("Actions", P_MODEL).value())
        if model is None:
            return
        source = model.place(self._next_name(), self.heatsink.width / 2, self.length / 2)
        self.sources.append(self._inside(source))
        self.selected = len(self.sources) - 1
        self._set_modified()
        self._structure_changed()

    def clone_source(self, *_):
        if self.selected < 0:
            return
        original = self.sources[self.selected]
        clone = dataclasses.replace(original, name=self._next_name(),
                                    x=original.x + CLONE_OFFSET,
                                    y=original.y + CLONE_OFFSET)
        self.sources.append(self._inside(clone))
        self.selected = len(self.sources) - 1
        self._set_modified()
        self._structure_changed()

    def rotate_source(self, *_):
        if self.selected < 0:
            return
        source = self.sources[self.selected]
        self.sources[self.selected] = self._inside(dataclasses.replace(
            source, size_x=source.size_y, size_y=source.size_x))
        self._set_modified()
        self._structure_changed()

    def delete_source(self, *_):
        if self.selected < 0:
            return
        del self.sources[self.selected]
        self.selected = -1
        self._set_modified()
        self._structure_changed()

    def _source_dragged(self, index: int, x: float, y: float):
        """Source déplacée à la souris (centre en mm) : calcul en direct."""
        self.sources[index] = dataclasses.replace(self.sources[index], x=x / MM, y=y / MM)
        self._set_modified()
        if index == self.selected:
            self._show_source_values()
        self.refresh()

    def _source_edited(self, *_):
        if self._updating or self.selected < 0:
            return
        value = self.source_params.child("Source").child
        tj_max = value(S_TJ_MAX).value()
        source = Source(
            name=value(S_NAME).value().strip() or self.sources[self.selected].name,
            x=value(S_X).value() / MM, y=value(S_Y).value() / MM,
            size_x=value(S_SIZE_X).value() / MM, size_y=value(S_SIZE_Y).value() / MM,
            power=value(S_POWER).value(), rth_jc=value(S_RTH_JC).value(),
            rth_cs=value(S_RTH_CS).value(), tj_max=tj_max if tj_max > 0 else None)
        self.sources[self.selected] = self._inside(source)
        self._set_modified()
        self._structure_changed()

    # ------------------------------------------------------------ sélection
    def select(self, index: int):
        """Sélectionne une source (-1 : le dissipateur)."""
        self.selected = index if 0 <= index < len(self.sources) else -1
        self.view.scene.select(self.selected)
        self._show_selection()
        self._sync_selection()

    def _tree_selected(self, current, _previous):
        if self._updating:
            return
        index = current.data(INDEX_ROLE) if current.isValid() else -1
        self.select(-1 if index is None else index)

    def _result_selected(self, current, _previous):
        if not self._updating and current.isValid():
            self.select(current.row())

    def _sync_selection(self):
        """Reporte la sélection dans l'arborescence et le tableau de résultats."""
        root = self.tree_model.item(0)
        if root is None:
            return
        item = root.child(self.selected) if self.selected >= 0 else root
        table = self.view.results_table
        self._updating = True
        try:
            self.view.tree.setCurrentIndex(item.index())
            if self.selected >= 0 and self.selected < self.results_model.rowCount():
                table.setCurrentIndex(self.results_model.index(self.selected, 0))
            else:
                table.setCurrentIndex(QtCore.QModelIndex())
                table.clearSelection()
        finally:
            self._updating = False

    def _show_selection(self):
        """Paramètres de l'élément sélectionné, en haut à droite."""
        has_source = self.selected >= 0
        params = self.source_params if has_source else self.heatsink_params
        self.view.selection_tree.setParameters(params, showTop=False)
        for action in (self.view.actionClone, self.view.actionRotate,
                       self.view.actionDelete):
            action.setEnabled(has_source)
        for name in (P_CLONE, P_ROTATE, P_DELETE):
            self.project_params.child("Actions", name).setOpts(enabled=has_source)
        if has_source:
            self._show_source_values()
        self._show_results()

    def _show_source_values(self):
        source = self.sources[self.selected]
        group = self.source_params.child("Source")
        values = {S_NAME: source.name, S_X: source.x * MM, S_Y: source.y * MM,
                  S_SIZE_X: source.size_x * MM, S_SIZE_Y: source.size_y * MM,
                  S_POWER: source.power, S_RTH_JC: source.rth_jc, S_RTH_CS: source.rth_cs,
                  S_TJ_MAX: source.tj_max or 0.0}
        self._updating = True
        try:
            for name, value in values.items():
                group.child(name).setValue(value)
        finally:
            self._updating = False

    # ------------------------------------------------------------ calcul et affichage
    def _structure_changed(self):
        """Sources ajoutées, retirées, renommées ou redimensionnées."""
        scene = self.view.scene
        scene.set_sources([((s.x - s.size_x / 2) * MM, (s.y - s.size_y / 2) * MM,
                            s.size_x * MM, s.size_y * MM) for s in self.sources])
        self._updating = True
        try:
            self.tree_model.clear()
            root = QtGui.QStandardItem(theme.icon("table"), "")
            root.setData(-1, INDEX_ROLE)
            for index, _source in enumerate(self.sources):
                item = QtGui.QStandardItem("")
                item.setData(index, INDEX_ROLE)
                root.appendRow(item)
            self.tree_model.appendRow(root)
            self.view.tree.expandAll()
            self.results_model.setRowCount(len(self.sources))
            for row in range(len(self.sources)):
                for column in range(len(RESULT_HEADERS)):
                    item = QtGui.QStandardItem("")
                    if column:
                        item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight
                                              | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    self.results_model.setItem(row, column, item)
        finally:
            self._updating = False
        if self.selected >= len(self.sources):
            self.selected = -1
        self.select(self.selected)
        self.refresh()

    def refresh(self):
        """Relance le calcul et met à jour la carte, les étiquettes et les résultats."""
        try:
            self.result = simulate(self.heatsink, self.length, self.sources, self.conditions)
            messages = list(self.result.warnings)
        except (CalibrationError, ValueError) as error:
            self.result = None
            messages = [f"Calcul impossible : {error}"]
        self.view.statusBar().showMessage(" ; ".join(messages + self.library_errors))
        self._show_field()
        self._show_results()

    def _margin_brush(self, margin):
        if margin is not None and margin < 0:
            return QtGui.QBrush(theme.color("danger"))
        if margin is not None and margin < LOW_MARGIN:
            return QtGui.QBrush(QtGui.QColor(WARNING_COLOR))
        return QtGui.QBrush(theme.color("text"))

    def _show_field(self):
        scene, result = self.view.scene, self.result
        root = self.tree_model.item(0)
        title = f"{self.heatsink.name} — {_fr(self.length * MM)} mm"
        if root is None:
            return
        if result is None:
            scene.set_labels([source.name for source in self.sources])
            root.setText(title)
            for index, source in enumerate(self.sources):
                root.child(index).setText(source.name)
                self.results_model.item(index, 0).setText(source.name)
                for column in range(1, len(RESULT_HEADERS)):
                    self.results_model.item(index, column).setText("—")
            return
        # échelle de couleurs sur l'étendue de la carte : c'est le relief qui compte
        scene.set_field(result.surface, float(result.surface.min()), result.hottest)
        labels = []
        for index, item in enumerate(result.sources):
            source = item.source
            labels.append(f"{source.name}  {item.junction:.0f} °C")
            brush = self._margin_brush(item.margin)
            row = root.child(index)
            row.setText(f"{source.name} — {source.power:.0f} W — Tj {item.junction:.0f} °C")
            row.setForeground(QtGui.QBrush(theme.color("danger"))
                              if item.margin is not None and item.margin < 0
                              else QtGui.QBrush(theme.color("text")))
            texts = [source.name, f"{source.power:.0f}", f"{item.sink_mean:.1f}",
                     f"{item.sink_max:.1f}", f"{item.case:.1f}", f"{item.junction:.1f}",
                     "—" if source.tj_max is None else f"{source.tj_max:.0f}",
                     "—" if item.margin is None else f"{item.margin:+.1f}"]
            for column, text in enumerate(texts):
                cell = self.results_model.item(index, column)
                cell.setText(text)
                cell.setForeground(brush if column in (5, 7)
                                   else QtGui.QBrush(theme.color("text")))
        scene.set_labels(labels)
        root.setText(f"{title} — max {result.hottest:.0f} °C")

    def _show_results(self):
        result = self.result
        sheet = self.heatsink
        info = self.heatsink_params.child("Dissipateur")
        for name, text in ((P_REFERENCE, f"{sheet.manufacturer} {sheet.name}".strip()),
                           (H_WIDTH, f"{sheet.width * MM:g} mm"),
                           (H_HEIGHT, f"{sheet.height * MM:g} mm"),
                           (H_BASE, f"{sheet.base * MM:g} mm"),
                           (H_RTH_N, f"{sheet.rth_natural:g} K/W à "
                                     f"{sheet.rth_length * MM:g} mm"),
                           (H_RTH_F, f"{sheet.rth_forced:g} K/W à "
                                     f"{sheet.rth_length * MM:g} mm, "
                                     f"{sheet.forced_speed:g} m/s"),
                           (H_ORIGIN, sheet.origin + (", anodisé noir" if sheet.anodised
                                                      else "")),
                           (H_WINDOW, f"{sheet.flow_area * 1e6:.0f} mm²"
                                      + ("" if sheet.air_window else
                                         " (largeur × hauteur d'ailettes)")),
                           (H_METAL, f"× {sheet.y_factor:.2f} selon la longueur"
                                     if sheet.metal_area else "non (masse inconnue)")):
            info.child(name).setValue(text)
        totals = self.heatsink_params.child("Résultats")
        readouts = self.source_params.child("Résultats")
        if result is None:
            for group in (totals, readouts):
                for child in group.children():
                    child.setValue("—")
            return
        totals.child(H_TARGET).setValue(f"{result.calibration.rth_target:.4f} K/W")
        totals.child(H_COEFFICIENT).setValue(f"{result.h:.0f} W/m².K")
        totals.child(H_POWER).setValue(f"{result.power:.0f} W")
        totals.child(H_HOTTEST).setValue(f"{result.hottest:.1f} °C")
        totals.child(H_AIR_OUT).setValue(
            "—" if self.conditions.mode == NATURAL and self.conditions.horizontal
            else f"{result.air_outlet:.1f} °C")
        if 0 <= self.selected < len(result.sources):
            item = result.sources[self.selected]
            readouts.child(R_SINK_MEAN).setValue(f"{item.sink_mean:.1f} °C")
            readouts.child(R_SINK_MAX).setValue(f"{item.sink_max:.1f} °C")
            readouts.child(R_CASE).setValue(f"{item.case:.1f} °C")
            readouts.child(R_JUNCTION).setValue(f"{item.junction:.1f} °C")
            readouts.child(R_MARGIN).setValue(
                "—" if item.margin is None else f"{item.margin:+.1f} K")

    # ------------------------------------------------------------ fichiers de projet
    def project(self) -> Project:
        return Project(heatsink_name=self.heatsink.name,
                       manufacturer=self.heatsink.manufacturer, length=self.length,
                       conditions=self.conditions, sources=list(self.sources))

    def _set_modified(self, modified: bool = True):
        self.modified = modified
        name = self.project_path.name if self.project_path else "Nouveau projet"
        application = QtWidgets.QApplication.applicationName() or "CoolingTool"
        self.view.setWindowTitle(f"{name}{' *' if modified else ''} — {application}")

    def _apply_project(self, project: Project, path=None):
        if project.heatsink_name not in self.heatsinks:
            maker = f" ({project.manufacturer})" if project.manufacturer else ""
            raise ValueError(f"le dissipateur « {project.heatsink_name} »{maker} "
                             "n'est pas dans la librairie")
        self.heatsink = self.heatsinks[project.heatsink_name]
        self.length = project.length
        self.conditions = project.conditions
        self.sources = list(project.sources)
        self.selected = -1
        self.project_path = pathlib.Path(path) if path else None
        self._show_project_values()
        self._plate_changed()
        self._structure_changed()
        self._set_modified(False)

    def new_project(self, *_):
        if not self.confirm_discard():
            return
        heatsink = next(iter(self.heatsinks.values()))
        self.heatsink, self.length = heatsink, heatsink.rth_length
        self.conditions = Conditions(FORCED, ambient=DEFAULT_AMBIENT)
        self.project_path = None
        self._default_sources()
        self._show_project_values()
        self._plate_changed()
        self._structure_changed()
        self._set_modified(False)

    def open_project(self, *_):
        if not self.confirm_discard():
            return
        path = self._ask_open_path()
        if path:
            self.load_project(path)

    def load_project(self, path) -> bool:
        try:
            self._apply_project(Project.load(path), path)
        except (OSError, ValueError) as error:
            self._error(f"Impossible d'ouvrir {pathlib.Path(path).name} :\n{error}")
            return False
        self.options["last_dir"] = str(pathlib.Path(path).parent)
        return True

    def save_project(self, *_) -> bool:
        if self.project_path is None:
            return self.save_project_as()
        return self._write_project(self.project_path)

    def save_project_as(self, *_) -> bool:
        path = self._ask_save_path()
        if not path:
            return False
        path = pathlib.Path(path)
        if not path.name.endswith(EXTENSION):
            # un nom saisi sans extension, ou en .json seul, reçoit l'extension complète
            stem = path.name[:-len(".json")] if path.name.endswith(".json") else path.name
            path = path.with_name(stem + EXTENSION)
        return self._write_project(path)

    def _write_project(self, path) -> bool:
        try:
            self.project().save(path)
        except OSError as error:
            self._error(f"Impossible d'enregistrer {pathlib.Path(path).name} :\n{error}")
            return False
        self.project_path = pathlib.Path(path)
        self.options["last_dir"] = str(self.project_path.parent)
        self._set_modified(False)
        return True

    def confirm_discard(self) -> bool:
        """Vrai si le projet courant peut être quitté (enregistré, ou abandon accepté)."""
        if not self.modified:
            return True
        answer = self._ask_save_changes()
        if answer == "save":
            return self.save_project()
        return answer == "discard"

    # dialogues : méthodes à part, remplacées dans les tests
    def _start_dir(self) -> str:
        last = self.options.get("last_dir") or ""
        return last if last and pathlib.Path(last).is_dir() else str(pathlib.Path.home())

    def _ask_open_path(self) -> str:
        return QtWidgets.QFileDialog.getOpenFileName(
            self.view, "Ouvrir un projet", self._start_dir(), PROJECT_FILTER)[0]

    def _ask_save_path(self) -> str:
        name = self.project_path.name if self.project_path else f"projet{EXTENSION}"
        return QtWidgets.QFileDialog.getSaveFileName(
            self.view, "Enregistrer le projet",
            str(pathlib.Path(self._start_dir()) / name), PROJECT_FILTER)[0]

    def _ask_save_changes(self) -> str:
        buttons = QtWidgets.QMessageBox.StandardButton
        answer = QtWidgets.QMessageBox.question(
            self.view, "Projet modifié", "Enregistrer les modifications du projet ?",
            buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save)
        return {buttons.Save: "save", buttons.Discard: "discard"}.get(answer, "cancel")

    def _error(self, text: str):
        QtWidgets.QMessageBox.warning(self.view, "CoolingTool", text)

    # ------------------------------------------------------------ thème
    def set_dark_mode(self, enabled: bool):
        self.options["dark_mode"] = bool(enabled)
        self.apply_theme()

    def apply_theme(self):
        theme.apply(QtWidgets.QApplication.instance(), self.options["dark_mode"],
                    extra_qss=theme.ITEM_VIEW_QSS)
        self.view.refresh_theme()
        if self.tree_model.item(0) is not None:
            self.tree_model.item(0).setIcon(theme.icon("table"))
            self._show_field()

    # ------------------------------------------------------------ réglages
    def edit_options(self):
        dialog = options_panel.OptionsPannel(self.schema, self.options, self.view)
        if dialog.exec():
            self.apply_options(dialog.getOptions())

    def apply_options(self, values: dict):
        """Prend en compte de nouvelles options (changement de librairie compris)."""
        previous = self.options.get("library_dir")
        self.options.update(values)
        if self.options.get("library_dir") != previous:
            self._load_library()
            # le dissipateur du projet reste utilisable même s'il n'est plus en librairie
            self.heatsinks.setdefault(self.heatsink.name, self.heatsink)
            self._show_library()
            self.refresh()
        self.save_settings()

    def save_settings(self):
        settings.save(self.settings_path, self.options)
