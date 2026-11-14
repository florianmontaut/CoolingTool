# view/scene.py
"""
Scène thermique : la semelle du dissipateur vue de dessus (face de montage), sa carte de
température, et les sources de chaleur, déplaçables à la souris. Coordonnées en mm :
x selon la largeur, y selon la longueur (sens de l'air, vers le haut).

La scène ne connaît pas les groupes : elle signale le déplacement d'une source, avec
l'état de la touche Alt au moment où on l'a saisie (Alt : la source seule), et le
contrôleur déplace le reste du groupe.
"""
import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

from qtsocle import theme

COLOR_MAP = "CET-R4"            # du bleu (froid) au rouge (chaud)
SOURCE_PEN = pg.mkPen("#101418", width=1.5)
SELECTED_PEN = pg.mkPen("#FFFFFF", width=3)
GROUP_PEN = pg.mkPen("#FFFFFF", width=1.5, style=QtCore.Qt.PenStyle.DashLine)
HOVER_PEN = pg.mkPen("#FFFFFF", width=1.5)
LABEL_FILL = pg.mkBrush(16, 20, 24, 170)
LABEL_COLOR = "#FFFFFF"
MARGIN = 0.12                   # marge autour de la semelle, en part de sa taille


class SourceItem(pg.ROI):
    """Rectangle d'une source : déplaçable, retenu dans la semelle, sans poignée."""

    def __init__(self, index: int, rect: QtCore.QRectF, bounds: QtCore.QRectF):
        super().__init__(rect.topLeft(), rect.size(), movable=True, rotatable=False,
                         resizable=False, maxBounds=bounds, pen=SOURCE_PEN,
                         hoverPen=HOVER_PEN)
        self.index = index
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton)
        self.setZValue(10)
        self.label = pg.TextItem(color=LABEL_COLOR, fill=LABEL_FILL, anchor=(0.5, 0.5))
        self.label.setParentItem(self)
        self._place_label()

    def _place_label(self):
        size = self.size()
        self.label.setPos(size.x() / 2, size.y() / 2)

    def set_rect(self, rect: QtCore.QRectF):
        """Déplace ou redimensionne sans émettre de signal (changement venu du modèle)."""
        self.setPos(rect.topLeft(), update=False)
        self.setSize(rect.size(), update=False)
        self.stateChanged(finish=False)
        self._place_label()

    def centre(self) -> tuple:
        pos, size = self.pos(), self.size()
        return pos.x() + size.x() / 2, pos.y() + size.y() / 2


class ThermalScene(pg.GraphicsLayoutWidget):
    # index de la source, centre x, centre y (mm), Alt enfoncée à la saisie (la source
    # seule, sans son groupe) : émis pendant le déplacement
    sourceMoved = QtCore.pyqtSignal(int, float, float, bool)
    # index de la source sélectionnée à la souris, -1 pour aucune (Alt : voir alone)
    sourceSelected = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plot = self.addPlot()
        self.plot.setAspectLocked(True)
        self.plot.setLabel("bottom", "x (mm)")
        self.plot.setLabel("left", "y (mm)")
        self.plot.setMenuEnabled(False)
        self.plot.hideButtons()

        self.image = pg.ImageItem(axisOrder="row-major")
        self.plot.addItem(self.image)
        self.outline = pg.PlotCurveItem()
        self.outline.setZValue(5)
        self.plot.addItem(self.outline)
        self.flow = pg.PlotCurveItem(connect="pairs")
        self.plot.addItem(self.flow)
        self.flow_label = pg.TextItem("air", anchor=(0.5, 1.0))
        self.plot.addItem(self.flow_label)

        self.bar = pg.ColorBarItem(values=(0, 1), colorMap=pg.colormap.get(COLOR_MAP),
                                   label="Température de la semelle (°C)",
                                   interactive=False)
        self.bar.setImageItem(self.image, insert_in=self.plot)

        self.items_: list = []
        self._selected = -1
        self._highlighted: set = set()      # sources mises en évidence (groupe)
        self._related: set = set()          # reste du groupe de la source sélectionnée
        self.alone = False                  # Alt enfoncée à la dernière saisie
        self._bounds = QtCore.QRectF(0, 0, 1, 1)
        self._moving = False            # déplacement venu du modèle : pas de signal
        self.plot.scene().sigMouseClicked.connect(self._scene_clicked)
        self.refresh_theme()

    # ------------------------------------------------------------ semelle
    def set_plate(self, width: float, length: float):
        """Dimensions de la semelle (mm). Recadre la vue."""
        self._bounds = QtCore.QRectF(0, 0, width, length)
        self.outline.setData([0, width, width, 0, 0], [0, 0, length, length, 0])
        if self.image.image is not None:
            self.image.setRect(self._bounds)
        for item in self.items_:
            item.maxBounds = self._bounds
        margin = MARGIN * max(width, length)
        self.plot.setRange(xRange=(-margin, width + margin),
                           yRange=(-margin, length + margin), padding=0)

    def set_flow(self, visible: bool, reversed_flow: bool = False):
        """Flèche du sens de l'air, à gauche de la semelle."""
        self.flow.setVisible(visible)
        self.flow_label.setVisible(visible)
        if not visible:
            return
        width, length = self._bounds.width(), self._bounds.height()
        x = -0.06 * max(width, length)
        head = 0.03 * max(width, length)
        tail, tip = (0.7 * length, 0.3 * length) if reversed_flow \
            else (0.3 * length, 0.7 * length)
        back = tip - head if tip > tail else tip + head
        self.flow.setData([x, x, x, x - head / 2, x, x + head / 2],
                          [tail, tip, tip, back, tip, back])
        self.flow_label.setPos(x, min(tail, tip) - head / 2)

    def set_field(self, surface: np.ndarray, low: float, high: float):
        """Carte de température (ny, nx) et bornes de l'échelle de couleurs."""
        if high - low < 1.0:
            high = low + 1.0
        self.image.setImage(surface, autoLevels=False)
        self.image.setRect(self._bounds)
        self.bar.setLevels((low, high))

    # ------------------------------------------------------------ sources
    def set_sources(self, rects: list):
        """Rectangles (x0, y0, largeur, longueur) en mm, un par source."""
        self._moving = True
        try:
            while len(self.items_) > len(rects):
                self.plot.removeItem(self.items_.pop())
            for index, values in enumerate(rects):
                rect = QtCore.QRectF(*values)
                if index < len(self.items_):
                    self.items_[index].set_rect(rect)
                    continue
                item = SourceItem(index, rect, self._bounds)
                item.sigRegionChanged.connect(self._item_moved)
                item.sigRegionChangeStarted.connect(self._item_pressed)
                item.sigClicked.connect(self._item_pressed)
                self.plot.addItem(item)
                self.items_.append(item)
        finally:
            self._moving = False
        self.select(self._selected if self._selected < len(self.items_) else -1,
                    {i for i in self._highlighted if i < len(self.items_)},
                    self._related)

    def set_labels(self, texts: list):
        for item, text in zip(self.items_, texts):
            item.label.setText(text)

    def select(self, index: int, highlighted=(), related=()):
        """
        Met en évidence la source index (-1 : aucune), sans émettre de signal ;
        highlighted : autres sources affichées comme sélectionnées (un groupe entier) ;
        related : sources liées à la sélection (le reste de son groupe), en pointillés.
        """
        self._selected = index
        self._highlighted = set(highlighted) | ({index} if index >= 0 else set())
        self._related = set(related) - self._highlighted
        for item in self.items_:
            selected = item.index in self._highlighted
            item.setPen(SELECTED_PEN if selected
                        else GROUP_PEN if item.index in self._related else SOURCE_PEN)
            item.setZValue(11 if selected else 10)

    def source_rect(self, index: int) -> tuple:
        item = self.items_[index]
        return item.pos().x(), item.pos().y(), item.size().x(), item.size().y()

    def move_source(self, index: int, x: float, y: float, alone: bool = False):
        """
        Déplace une source comme le ferait la souris (centre en mm), Alt enfoncée si
        alone : pour les tests.
        """
        item = self.items_[index]
        size = item.size()
        self._press(item, alone)
        target = QtCore.QPointF(x - size.x() / 2, y - size.y() / 2)
        item.translate(target - item.pos())        # retenu dans la semelle, comme à la souris
        item.sigRegionChangeFinished.emit(item)

    def _item_moved(self, item: SourceItem):
        if not self._moving:
            self.sourceMoved.emit(item.index, *item.centre(), self.alone)

    def _item_pressed(self, item: SourceItem, *_):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        self._press(item, bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier))

    def _press(self, item: SourceItem, alone: bool):
        """Saisie d'une source : le contrôleur décide de la sélection (source ou groupe)."""
        self.alone = alone
        self.sourceSelected.emit(item.index)

    def _scene_clicked(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        under = self.plot.scene().items(event.scenePos())
        if not any(isinstance(item, SourceItem) for item in under) and self._highlighted:
            self.select(-1)
            self.sourceSelected.emit(-1)

    # ------------------------------------------------------------ thème
    def refresh_theme(self):
        """Couleurs des axes et du fond : à rappeler après theme.apply()."""
        colors = theme.colors()
        self.setBackground(colors["graph_bg"])
        theme.style_plot(self.plot)
        pen = pg.mkPen(colors["graph_text"], width=1.5)
        self.outline.setPen(pg.mkPen(colors["graph_axis"], width=1))
        self.flow.setPen(pen)
        self.flow_label.setColor(QtGui.QColor(colors["graph_text"]))
        axis = self.bar.axis
        axis.setPen(pg.mkPen(colors["graph_axis"]))
        axis.setTextPen(pg.mkPen(colors["graph_text"]))
