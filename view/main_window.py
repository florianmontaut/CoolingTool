# view/main_window.py
"""
Fenêtre principale : arborescence du projet à gauche, scène thermique au centre,
paramètres à droite (élément sélectionné en haut ; dissipateur, conditions et actions en
bas).
"""
import pyqtgraph.parametertree as ptree
from PyQt6 import QtCore, QtGui, QtWidgets

from qtsocle import theme

from .scene import ThermalScene


class MainWindow(QtWidgets.QMainWindow):
    # émis à la fermeture, avant la destruction : le contrôleur enregistre ses réglages
    closing = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(QtWidgets.QApplication.applicationName())
        self.resize(1400, 850)
        self._build_actions()
        self._build_panels()
        self.refresh_theme()

    def _build_actions(self):
        toolbar = self.addToolBar("Outils")
        toolbar.setMovable(False)

        def action(text, icon_name, tip, checkable=False, shortcut=None):
            act = QtGui.QAction(text, self)
            act.setToolTip(tip)
            act.setCheckable(checkable)
            if shortcut is not None:
                act.setShortcut(QtGui.QKeySequence(shortcut))
            theme.set_action_icon(act, icon_name)
            toolbar.addAction(act)
            return act

        self.actionAdd = action("Ajouter une source", "plus",
                                "Ajouter une source du modèle choisi (Ctrl+N)",
                                shortcut="Ctrl+N")
        self.actionClone = action("Cloner", "copy", "Cloner la source sélectionnée (Ctrl+D)",
                                  shortcut="Ctrl+D")
        self.actionRotate = action("Pivoter", "rotate",
                                   "Pivoter la source sélectionnée de 90° (R)", shortcut="R")
        self.actionDelete = action("Supprimer", "trash",
                                   "Supprimer la source sélectionnée (Suppr)",
                                   shortcut=QtGui.QKeySequence.StandardKey.Delete)
        toolbar.addSeparator()
        self.actionOptions = action("Options...", "settings", "Options de l'application")
        self.actionDark = action("Thème sombre", "moon", "Thème sombre", checkable=True)

    def _build_panels(self):
        self.tree = QtWidgets.QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)

        self.scene = ThermalScene()

        self.selection_tree = self._parameter_tree()
        self.project_tree = self._parameter_tree()
        right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        right.addWidget(self.selection_tree)
        right.addWidget(self.project_tree)
        right.setSizes([420, 430])

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        for widget in (self.tree, self.scene, right):
            splitter.addWidget(widget)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 760, 400])
        self.setCentralWidget(splitter)
        self.statusBar()

    @staticmethod
    def _parameter_tree() -> ptree.ParameterTree:
        """Arbre de paramètres dont la colonne des noms garde une largeur raisonnable."""
        tree = ptree.ParameterTree()
        tree.setHeaderHidden(True)
        header = tree.header()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        tree.setColumnWidth(0, 190)
        return tree

    def refresh_theme(self):
        """Couleurs du graphique : à rappeler après theme.apply()."""
        self.scene.refresh_theme()

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)
