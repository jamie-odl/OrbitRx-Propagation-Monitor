"""About dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from orbitrx import __version__

# TODO(jamie): replace with the real Buy Me a Coffee page before release.
BUY_ME_A_COFFEE_URL = "https://www.buymeacoffee.com/TODO-placeholder"

ABOUT_HTML = f"""
<h2 style="margin-bottom:4px">OrbitRx Propagation Monitor</h2>
<p style="color:#90A4AE;margin-top:0">Version {__version__}</p>
<p>HF propagation, space weather, DX cluster and live PSKReporter spots in one free desktop app.</p>
<p>Copyright &copy; 2026 Jamie Sibley. Released under the MIT License.</p>
<p><b>Data sources:</b> NOAA SWPC, HamQSL (N0NBH), PSKReporter (Philip Gladstone),
DX cluster nodes, OpenStreetMap map tiles, Leaflet. See NOTICE for full credits.</p>
<p>OrbitRx is free. If it helps you make contacts, you can
<a href="{BUY_ME_A_COFFEE_URL}">buy me a coffee</a> (placeholder link, not live yet).</p>
"""


def show_about(parent=None) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("About OrbitRx")
    dlg.setMinimumWidth(460)
    lay = QVBoxLayout(dlg)
    text = QLabel(ABOUT_HTML)
    text.setTextFormat(Qt.TextFormat.RichText)
    text.setOpenExternalLinks(True)
    text.setWordWrap(True)
    lay.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    dlg.exec()
