"""About dialog."""

from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from orbitrx import __version__
from orbitrx.paths import project_root
from orbitrx.ui.window_fit import fit_to_screen

# Jamie's Buy Me a Coffee page (set 2026-11-05).
BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/thevenom"
# M6: releases are unsigned; SHA256SUMS.txt is published next to each release.
RELEASES_URL = "https://github.com/jamie-odl/OrbitRx-Propagation-Monitor/releases"


def _build_commit() -> str | None:
    """Short git commit hash for the About version line.

    Preference order:
    1. ORBITRX_COMMIT_SHA env (CI / local override)
    2. Stamped orbitrx._build_meta.COMMIT_SHA (frozen release builds)
    3. `git rev-parse --short HEAD` when run from a checkout
    """
    env = (os.environ.get("ORBITRX_COMMIT_SHA") or "").strip()
    if env:
        return env[:12]
    try:
        from orbitrx._build_meta import COMMIT_SHA as stamped
        if stamped:
            return str(stamped).strip()[:12]
    except Exception:
        pass
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
    coffee = ""
    if BUY_ME_A_COFFEE_URL:
        coffee = (
            '<p style="margin-bottom:12px">OrbitRx is free. If it helps you make contacts, you can '
            f'<a href="{BUY_ME_A_COFFEE_URL}">buy me a coffee</a>.</p>'
        )
    else:
        coffee = (
            '<p style="margin-bottom:12px">OrbitRx is free. If it helps you make contacts, '
            "a tip link will appear here once it is set.</p>"
        )
    return f"""
<h2 style="margin-bottom:4px">OrbitRx Propagation Monitor</h2>
<p style="color:#90A4AE;margin-top:0;margin-bottom:12px" id="version-line">{_version_line()}</p>
<p style="margin-bottom:12px">HF propagation, space weather, DX cluster and live PSKReporter spots in one free desktop app.</p>
<p style="margin-bottom:12px">Copyright &copy; 2026 Jamie Sibley. Released under the MIT License.</p>
<p style="margin-bottom:12px"><b>Data sources:</b> NOAA SWPC, HamQSL (N0NBH), PSKReporter (Philip Gladstone),
DX cluster nodes, OpenStreetMap map tiles, Leaflet. See <a href="{_notice_url()}">NOTICE</a> for full credits.</p>
<p style="margin-bottom:12px">This build is unsigned. <a href="{RELEASES_URL}">Verify download</a>
(compare the file's SHA256 with SHA256SUMS.txt on the release page).</p>
{coffee}
"""


def _build_about_dialog(parent=None) -> QDialog:
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

    # Natural size at 100%, then clamped to the available screen so Close
    # stays reachable on a small or scaled-up display.
    dlg.adjustSize()
    fit_to_screen(dlg, 360, 200)
    return dlg


def show_about(parent=None) -> None:
    _build_about_dialog(parent).exec()
