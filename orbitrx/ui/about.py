"""About dialog."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from orbitrx import __version__
from orbitrx.paths import project_root

# TODO(jamie): replace with the real Buy Me a Coffee page before release.
BUY_ME_A_COFFEE_URL = "https://www.buymeacoffee.com/TODO-placeholder"


def _build_commit() -> str | None:
    """Short git commit hash, if run from a checkout (not available in a frozen build)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root(), capture_output=True, text=True, timeout=2,
        )
        commit = out.stdout.strip()
        return commit or None
    except Exception:
        return None


def _notice_url() -> str:
    notice_path = project_root() / "NOTICE"
    return QUrl.fromLocalFile(str(notice_path)).toString()


def _version_line() -> str:
    commit = _build_commit()
    return f"Version {__version__} ({commit})" if commit else f"Version {__version__}"


def _about_html() -> str:
    return f"""
<h2 style="margin-bottom:4px">OrbitRx Propagation Monitor</h2>
<p style="color:#90A4AE;margin-top:0;margin-bottom:12px" id="version-line">{_version_line()}</p>
<p style="margin-bottom:12px">HF propagation, space weather, DX cluster and live PSKReporter spots in one free desktop app.</p>
<p style="margin-bottom:12px">Copyright &copy; 2026 Jamie Sibley. Released under the MIT License.</p>
<p style="margin-bottom:12px"><b>Data sources:</b> NOAA SWPC, HamQSL (N0NBH), PSKReporter (Philip Gladstone),
DX cluster nodes, OpenStreetMap map tiles, Leaflet. See <a href="{_notice_url()}">NOTICE</a> for full credits.</p>
<p style="margin-bottom:12px">OrbitRx is free. If it helps you make contacts, you can
<a href="{BUY_ME_A_COFFEE_URL}">buy me a coffee</a>.</p>
"""


def show_about(parent=None) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("About OrbitRx")
    dlg.setFixedWidth(480)
    lay = QVBoxLayout(dlg)
    text = QLabel(_about_html())
    text.setTextFormat(Qt.TextFormat.RichText)
    text.setOpenExternalLinks(True)
    text.setWordWrap(True)
    text.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
    )
    lay.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    dlg.exec()
