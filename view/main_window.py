# view/main_window.py
"""
Fenêtre principale :
    - à gauche, l'arborescence du projet, et dessous la librairie (filtre + table) ;
    - au centre, la scène thermique, et dessous le tableau des résultats par source ;
    - à droite, les paramètres : élément sélectionné en haut ; dissipateur, conditions
      et actions en bas.
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
        self.resize(1500, 900)
        # posé par le contrôleur : renvoie False pour refuser la fermeture (projet
        # modifié, enregistrement annulé)
        self.can_close = None
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

        self.actionNew = action("Nouveau projet", "file", "Nouveau projet (Ctrl+N)",
                                shortcut="Ctrl+N")
        self.actionOpen = action("Ouvrir...", "open", "Ouvrir un projet (Ctrl+O)",
                                 shortcut="Ctrl+O")
        self.actionSave = action("Enregistrer", "save", "Enregistrer le projet (Ctrl+S)",
                                 shortcut="Ctrl+S")
        self.actionSaveAs = action("Enregistrer sous...", "export",
                                   "Enregistrer le projet sous un autre nom (Ctrl+Maj+S)",
                                   shortcut="Ctrl+Shift+S")
        toolbar.addSeparator()
        self.actionAdd = action("Ajouter une source", "plus",
                                "Ajouter une source du modèle choisi (Ctrl+I)",
                                shortcut="Ctrl+I")
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
        # gauche : projet, puis librairie
        self.tree = QtWidgets.QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)

        self.library_filter = QtWidgets.QLineEdit()
        self.library_filter.setPlaceholderText("Filtrer la librairie...")
        self.library_filter.setClearButtonEnabled(True)
        self.library_table = self._table(sortable=True)
        self.library_table.setToolTip(
            "Double-clic : charger le dissipateur, ou ajouter une source de ce modèle")
        library = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(library)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.library_filter)
        layout.addWidget(self.library_table)
        left = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        left.addWidget(self.tree)
        left.addWidget(library)
        left.setSizes([260, 590])

        # centre : scène, puis résultats
        self.scene = ThermalScene()
        self.results_table = self._table(sortable=False)
        centre = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        centre.addWidget(self.scene)
        centre.addWidget(self.results_table)
        centre.setStretchFactor(0, 1)
        centre.setSizes([690, 160])

        # droite : paramètres
        self.selection_tree = self._parameter_tree()
        self.project_tree = self._parameter_tree()
        right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        right.addWidget(self.selection_tree)
        right.addWidget(self.project_tree)
        right.setSizes([420, 430])

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        for widget in (left, centre, right):
            splitter.addWidget(widget)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([330, 780, 390])
        self.setCentralWidget(splitter)
        self.statusBar()

    @staticmethod
    def _table(sortable: bool) -> QtWidgets.QTableView:
        table = QtWidgets.QTableView()
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(sortable)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(24)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setHighlightSections(False)
        return table

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
        if self.can_close is not None and not self.can_close():
            event.ignore()
            return
        self.closing.emit()
        super().closeEvent(event)
