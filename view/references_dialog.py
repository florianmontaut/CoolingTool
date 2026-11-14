# view/references_dialog.py
"""
Fenêtre « Repères de dimensionnement » : densités de flux admissibles par mode de
refroidissement, ce qu'elles donnent pour chaque modèle de source de la librairie, et
les chiffres clés. Non modale : on peut la garder ouverte en travaillant.
"""
import html

from PyQt6 import QtCore, QtWidgets

MM = 1000.0


def _fr(value: float) -> str:
    """Nombre court à la française : 5 ; 65,3 ; 100."""
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


class ReferencesDialog(QtWidgets.QDialog):

    def __init__(self, references, models, parent=None):
        """references : model.references.References ; models : modèles de sources."""
        super().__init__(parent)
        self.setWindowTitle("Repères de dimensionnement")
        self.resize(820, 700)
        layout = QtWidgets.QVBoxLayout(self)

        def heading(text):
            label = QtWidgets.QLabel(f"<b>{text}</b>")
            layout.addWidget(label)

        def note(text):
            if text:
                label = QtWidgets.QLabel(text)
                label.setWordWrap(True)
                layout.addWidget(label)

        densities = references.densities
        heading("Densité de flux admissible sous la source")
        note(references.density_notes)
        self.density_table = self._table(
            ["Refroidissement", "W/cm²", "Remarques"],
            [[d.cooling, _fr(d.w_cm2), d.notes] for d in densities])
        layout.addWidget(self.density_table)

        heading("Pertes admissibles par source, selon ces densités")
        models = sorted(models, key=lambda m: m.size_x * m.size_y, reverse=True)
        self.source_table = self._table(
            ["Source", "Empreinte"] + [f"{d.cooling.split(' (')[0]} (W)" for d in densities],
            [[m.name, f"{_fr(m.size_x * MM)} × {_fr(m.size_y * MM)} mm "
                      f"({_fr(m.size_x * m.size_y * 1e4)} cm²)"]
             + [f"{d.power(m.size_x * m.size_y):.0f}" for d in densities]
             for m in models], stretch=range(2, 2 + len(densities)))
        layout.addWidget(self.source_table)

        heading("Chiffres clés")
        # textes longs : mis en forme plutôt qu'en tableau
        self.figures = QtWidgets.QTextBrowser()
        self.figures.setHtml("".join(
            f"<p><b>{html.escape(f.subject)} : {html.escape(f.value)}</b>"
            + (f"<br>{html.escape(f.conditions)}." if f.conditions else "")
            + (f"<br><i>{html.escape(f.notes)}</i>" if f.notes else "") + "</p>"
            for f in references.figures))
        layout.addWidget(self.figures, stretch=1)

        note(references.source)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    @staticmethod
    def _table(headers: list, rows: list, stretch=None) -> QtWidgets.QTableWidget:
        """
        Petit tableau en lecture seule ; les colonnes stretch (par défaut la dernière) se
        partagent la place restante, les autres prennent la largeur de leur contenu.
        """
        table = QtWidgets.QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().hide()
        table.setWordWrap(False)
        for row, texts in enumerate(rows):
            for column, text in enumerate(texts):
                item = QtWidgets.QTableWidgetItem(text)
                item.setToolTip(text)
                if text and text[0].isdigit() and len(text) < 8:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight
                                          | QtCore.Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, column, item)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        for column in (stretch if stretch is not None else [len(headers) - 1]):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # hauteur ajustée au contenu : quelques lignes, sans défilement
        height = header.sizeHint().height() + 2 * table.frameWidth()
        height += table.verticalHeader().defaultSectionSize() * len(rows)
        table.setFixedHeight(height)
        return table
