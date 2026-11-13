# controller/main_controller.py
"""
Contrôleur principal : tient le projet (dissipateur, longueur, sources, conditions),
relance le calcul à chaque changement et met à jour la scène, l'arborescence et les
paramètres. Le modèle est en SI ; l'interface en mm et °C.
"""
import dataclasses
import pathlib

import pyqtgraph.parametertree as ptree
from PyQt6 import QtCore, QtGui, QtWidgets

from qtsocle import options_panel, settings, theme
from model import library
from model.simulation import (FORCED, NATURAL, CalibrationError, Conditions, Source,
                              simulate)
from ressources import app_settings

MM = 1000.0
DEFAULT_AMBIENT = 55.0              # °C, air au niveau des ailettes
DEFAULT_MODEL = "Module 62 mm"
CLONE_OFFSET = 0.010                # m
INDEX_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1

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


class MainController(QtCore.QObject):

    def __init__(self, view, data_dir, library_dir):
        super().__init__()
        self.view = view
        self.data_dir = pathlib.Path(data_dir)
        self.library_dir = pathlib.Path(library_dir)
        self.settings_path = self.data_dir / "settings.json"
        self.schema = app_settings.schema(str(self.library_dir))
        # réglages : valeurs par défaut du schéma, remplacées par celles enregistrées
        self.options = settings.load(self.settings_path,
                                     {"dark_mode": False,
                                      **options_panel.schema_defaults(self.schema)})

        self.heatsinks = {}
        for path in library.list_heatsinks(self.library_dir):
            sheet = library.load_heatsink(path)
            self.heatsinks[sheet.name] = sheet
        self.models = {}
        for path in library.list_source_models(self.library_dir):
            model = library.load_source_model(path)
            self.models[model.name] = model
        if not self.heatsinks:
            raise FileNotFoundError(f"aucun dissipateur dans {self.library_dir}")

        # projet
        self.heatsink = next(iter(self.heatsinks.values()))
        self.length = self.heatsink.rth_length
        self.sources: list = []
        self.conditions = Conditions(FORCED, ambient=DEFAULT_AMBIENT)
        self.selected = -1
        self.result = None
        self._updating = False          # changement venu du contrôleur : pas de boucle

        # modèles Qt parentés à leur vue : détruits avec elle, dans l'ordre
        self.tree_model = QtGui.QStandardItemModel(view.tree)
        view.tree.setModel(self.tree_model)

        self._build_parameters()

        # slots en méthodes liées (pas de lambda qui garderait le contrôleur en vie)
        view.actionAdd.triggered.connect(self.add_source)
        view.actionClone.triggered.connect(self.clone_source)
        view.actionRotate.triggered.connect(self.rotate_source)
        view.actionDelete.triggered.connect(self.delete_source)
        view.actionOptions.triggered.connect(self.edit_options)
        view.actionDark.toggled.connect(self.set_dark_mode)
        view.closing.connect(self.save_settings)
        view.scene.sourceMoved.connect(self._source_dragged)
        view.scene.sourceSelected.connect(self.select)
        view.tree.selectionModel().currentChanged.connect(self._tree_selected)

        view.actionDark.setChecked(bool(self.options["dark_mode"]))
        self.apply_theme()
        self._plate_changed()
        if DEFAULT_MODEL in self.models:
            self.add_source()
        else:
            self._structure_changed()

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
                _number(P_SPEED, self.conditions.speed, "m/s", limits=(0.1, 30.0), step=0.5),
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

        self.heatsink_params = ptree.Parameter.create(name="", type="group",
                                                      children=[
            {"name": "Dissipateur", "type": "group", "children": [
                _readout(P_REFERENCE), _readout(H_WIDTH), _readout(H_HEIGHT),
                _readout(H_BASE), _readout(H_RTH_N), _readout(H_RTH_F),
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
        self.view.scene.set_flow(forced, self.conditions.reversed_flow)

    def _heatsink_edited(self, *_):
        if self._updating:
            return
        group = self.project_params.child("Dissipateur")
        self.heatsink = self.heatsinks[group.child(P_REFERENCE).value()]
        self.length = group.child(P_LENGTH).value() / MM
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

    def add_source(self, *_):
        model = self.models.get(self.project_params.child("Actions", P_MODEL).value())
        if model is None:
            return
        source = model.place(self._next_name(), self.heatsink.width / 2, self.length / 2)
        self.sources.append(self._inside(source))
        self.selected = len(self.sources) - 1
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
        self._structure_changed()

    def rotate_source(self, *_):
        if self.selected < 0:
            return
        source = self.sources[self.selected]
        self.sources[self.selected] = self._inside(dataclasses.replace(
            source, size_x=source.size_y, size_y=source.size_x))
        self._structure_changed()

    def delete_source(self, *_):
        if self.selected < 0:
            return
        del self.sources[self.selected]
        self.selected = -1
        self._structure_changed()

    def _source_dragged(self, index: int, x: float, y: float):
        """Source déplacée à la souris (centre en mm) : calcul en direct."""
        self.sources[index] = dataclasses.replace(self.sources[index], x=x / MM, y=y / MM)
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
        self._structure_changed()

    # ------------------------------------------------------------ sélection
    def select(self, index: int):
        """Sélectionne une source (-1 : le dissipateur)."""
        self.selected = index if 0 <= index < len(self.sources) else -1
        self.view.scene.select(self.selected)
        self._show_selection()
        self._sync_tree_selection()

    def _tree_selected(self, current, _previous):
        if self._updating:
            return
        index = current.data(INDEX_ROLE) if current.isValid() else -1
        self.select(-1 if index is None else index)

    def _sync_tree_selection(self):
        root = self.tree_model.item(0)
        if root is None:
            return
        item = root.child(self.selected) if self.selected >= 0 else root
        self._updating = True
        try:
            self.view.tree.setCurrentIndex(item.index())
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
            message = " ; ".join(self.result.warnings)
        except (CalibrationError, ValueError) as error:
            self.result = None
            message = f"Calcul impossible : {error}"
        self.view.statusBar().showMessage(message)
        self._show_field()
        self._show_results()

    def _show_field(self):
        scene, result = self.view.scene, self.result
        root = self.tree_model.item(0)
        title = f"{self.heatsink.name} — {self.length * MM:.0f} mm"
        if result is None:
            scene.set_labels([source.name for source in self.sources])
            if root is not None:
                root.setText(title)
                for index, source in enumerate(self.sources):
                    root.child(index).setText(source.name)
            return
        # échelle de couleurs sur l'étendue de la carte : c'est le relief qui compte
        scene.set_field(result.surface, float(result.surface.min()), result.hottest)
        labels = []
        for index, item in enumerate(result.sources):
            text = f"{item.source.name}  {item.junction:.0f} °C"
            labels.append(text)
            if root is not None:
                root.child(index).setText(f"{item.source.name} — {item.source.power:.0f} W"
                                          f" — Tj {item.junction:.0f} °C")
                over = item.margin is not None and item.margin < 0
                root.child(index).setForeground(QtGui.QBrush(
                    theme.color("danger" if over else "text")))
        scene.set_labels(labels)
        if root is not None:
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
                                     f"{sheet.forced_speed:g} m/s")):
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
            f"{result.air_outlet:.1f} °C" if self.conditions.mode == FORCED else "—")
        if 0 <= self.selected < len(result.sources):
            item = result.sources[self.selected]
            readouts.child(R_SINK_MEAN).setValue(f"{item.sink_mean:.1f} °C")
            readouts.child(R_SINK_MAX).setValue(f"{item.sink_max:.1f} °C")
            readouts.child(R_CASE).setValue(f"{item.case:.1f} °C")
            readouts.child(R_JUNCTION).setValue(f"{item.junction:.1f} °C")
            readouts.child(R_MARGIN).setValue(
                "—" if item.margin is None else f"{item.margin:+.1f} K")

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
            self.options.update(dialog.getOptions())
            self.save_settings()

    def save_settings(self):
        settings.save(self.settings_path, self.options)
