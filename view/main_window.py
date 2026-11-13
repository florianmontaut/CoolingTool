# view/main_window.py
"""Fenêtre principale : arbre à gauche, graphique au centre, paramètres à droite."""
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
from PyQt6 import QtCore, QtGui, QtWidgets

from qtsocle import theme


class MainWindow(QtWidgets.QMainWindow):
    # émis à la fermeture, avant la destruction : le contrôleur enregistre ses réglages
    closing = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(QtWidgets.QApplication.applicationName())
        self.resize(1200, 750)
        self._build_actions()
        self._build_panels()
        self.refresh_theme()

    def _build_actions(self):
        toolbar = self.addToolBar("Outils")
        toolbar.setMovable(False)

        def action(text, icon_name, tip, checkable=False):
            act = QtGui.QAction(text, self)
            act.setToolTip(tip)
            act.setCheckable(checkable)
            theme.set_action_icon(act, icon_name)
            toolbar.addAction(act)
            return act

        self.actionOpen = action("Ouvrir...", "open", "Ouvrir un fichier")
        self.actionSave = action("Enregistrer", "save", "Enregistrer")
        toolbar.addSeparator()
        self.actionOptions = action("Options...", "settings", "Options de l'application")
        self.actionDark = action("Thème sombre", "moon", "Thème sombre", checkable=True)

    def _build_panels(self):
        self.tree = QtWidgets.QTreeView()
        self.tree.setHeaderHidden(True)
        self.graph = pg.GraphicsLayoutWidget()
        self.plot = self.graph.addPlot()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.parameters = ptree.ParameterTree()
        self.parameters.setHeaderHidden(True)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        for widget in (self.tree, self.graph, self.parameters):
            splitter.addWidget(widget)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 700, 250])
        self.setCentralWidget(splitter)
        self.statusBar()

    def refresh_theme(self):
        """Couleurs du graphique : à rappeler après theme.apply()."""
        self.graph.setBackground(theme.colors()["graph_bg"])
        theme.style_plot(self.plot)

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)
