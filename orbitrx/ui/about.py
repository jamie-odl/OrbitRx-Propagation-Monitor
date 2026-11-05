"""About dialog."""

from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QPainterPath
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from orbitrx import __version__
from orbitrx.paths import project_root
from orbitrx.ui.theme import (
    ACCENT, BG_ELEVATED, BORDER, FONT_CAPTION, FONT_TITLE, MUTED, TEXT, TEXT_MUTED,
)
from orbitrx.ui.window_fit import fit_to_screen

# Jamie's Buy Me a Coffee page (set 2026-11-05).
BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/thevenom"
RELEASES_URL = "https://github.com/jamie-odl/OrbitRx-Propagation-Monitor/releases"


def _build_commit() -> str | None:
    """Short git commit hash for the About version line."""
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


class _OrbitMark(QWidget):
    """40 px simple Orbit glyph for the About header (M6)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(40, 40)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(ACCENT), 2.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(4, 4, 32, 32)
        p.drawEllipse(10, 10, 20, 20)
        # equatorial ring
        path = QPainterPath()
        path.moveTo(2, 20)
        path.cubicTo(12, 8, 28, 8, 38, 20)
        path.cubicTo(28, 32, 12, 32, 2, 20)
        p.drawPath(path)
        p.end()


def _build_about_dialog(parent=None) -> QDialog:
    dlg = QDialog(parent)
    dlg.setWindowTitle("About OrbitRx")
    dlg.setFixedWidth(500)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(20, 20, 20, 16)
    lay.setSpacing(12)

    header = QHBoxLayout()
    header.setSpacing(12)
    header.addWidget(_OrbitMark())
    title_col = QVBoxLayout()
    title_col.setSpacing(2)
    title = QLabel("OrbitRx Propagation Monitor")
    title.setStyleSheet(f"color: {TEXT}; font-size: {FONT_TITLE}px; font-weight: 600;")
    ver = QLabel(_version_line())
    ver.setObjectName("version-line")
    ver.setStyleSheet(f"color: {TEXT_MUTED}; font-size: {FONT_CAPTION}px;")
    title_col.addWidget(title)
    title_col.addWidget(ver)
    header.addLayout(title_col, stretch=1)
    lay.addLayout(header)

    body = QLabel(
        "HF propagation, space weather, DX cluster and live PSKReporter spots "
        "in one free desktop app."
    )
    body.setWordWrap(True)
    body.setStyleSheet(f"color: {TEXT}; font-size: 13px;")
    lay.addWidget(body)

    copy = QLabel("Copyright © 2026 Jamie Sibley. Released under the MIT License.")
    copy.setWordWrap(True)
    copy.setStyleSheet(f"color: {MUTED}; font-size: {FONT_CAPTION}px;")
    lay.addWidget(copy)

    sep = QLabel()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {BORDER};")
    lay.addWidget(sep)

    sources = QLabel(
        f'<span style="color:{MUTED}">Data sources:</span> NOAA SWPC, HamQSL (N0NBH), '
        f'PSKReporter, DX cluster, OpenStreetMap / CARTO, Leaflet. '
        f'See <a href="{_notice_url()}" style="color:{ACCENT}">NOTICE</a> for credits.'
    )
    sources.setTextFormat(Qt.TextFormat.RichText)
    sources.setOpenExternalLinks(True)
    sources.setWordWrap(True)
    sources.setStyleSheet(f"font-size: {FONT_CAPTION}px;")
    lay.addWidget(sources)

    unsigned = QLabel(
        f'This build is unsigned. '
        f'<a href="{RELEASES_URL}" style="color:{ACCENT}">Verify download</a> '
        f'(compare SHA256 with SHA256SUMS.txt on the release page).'
    )
    unsigned.setTextFormat(Qt.TextFormat.RichText)
    unsigned.setOpenExternalLinks(True)
    unsigned.setWordWrap(True)
    unsigned.setStyleSheet(
        f"background: {BG_ELEVATED}; border-radius: 8px; padding: 12px; "
        f"color: {MUTED}; font-size: {FONT_CAPTION}px;"
    )
    lay.addWidget(unsigned)

    if BUY_ME_A_COFFEE_URL:
        coffee = QLabel(
            f'OrbitRx is free. If it helps you make contacts, you can '
            f'<a href="{BUY_ME_A_COFFEE_URL}" style="color:{ACCENT}">buy me a coffee</a>.'
        )
        coffee.setTextFormat(Qt.TextFormat.RichText)
        coffee.setOpenExternalLinks(True)
        coffee.setWordWrap(True)
        coffee.setStyleSheet(f"color: {TEXT}; font-size: 13px;")
        lay.addWidget(coffee)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)

    dlg.adjustSize()
    fit_to_screen(dlg, 360, 200)
    return dlg




def _about_html() -> str:
    """HTML snapshot kept for tests and any text consumers."""
    coffee = (
        f'<p style="margin-bottom:12px">OrbitRx is free. If it helps you make contacts, you can '
        f'<a href="{BUY_ME_A_COFFEE_URL}">buy me a coffee</a>.</p>'
    )
    return f"""
<h2 style="margin-bottom:4px">OrbitRx Propagation Monitor</h2>
<p style="color:#6B7A90;margin-top:0;margin-bottom:12px" id="version-line">{_version_line()}</p>
<p style="margin-bottom:12px">HF propagation, space weather, DX cluster and live PSKReporter spots in one free desktop app.</p>
<p style="margin-bottom:12px">Copyright &copy; 2026 Jamie Sibley. Released under the MIT License.</p>
<p style="margin-bottom:12px"><b>Data sources:</b> NOAA SWPC, HamQSL (N0NBH), PSKReporter (Philip Gladstone),
DX cluster nodes, OpenStreetMap / CARTO map tiles, Leaflet. See <a href="{_notice_url()}">NOTICE</a> for full credits.</p>
<p style="margin-bottom:12px">This build is unsigned. <a href="{RELEASES_URL}">Verify download</a>
(compare the file's SHA256 with SHA256SUMS.txt on the release page).</p>
{coffee}
"""

def show_about(parent=None) -> None:
    _build_about_dialog(parent).exec()
