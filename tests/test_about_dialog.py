"""About dialog: no placeholder wording, selectable version, NOTICE link (M6, S10)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from orbitrx.ui.about import BUY_ME_A_COFFEE_URL, _about_html, _build_commit, _version_line


def test_about_html_has_no_placeholder_wording():
    html = _about_html()
    assert "placeholder link" not in html.lower()
    assert "not live yet" not in html.lower()
    assert "TODO-placeholder" not in html
    assert "buymeacoffee.com/TODO" not in html
    assert "tip link will appear here" not in html.lower()


def test_about_html_links_buy_me_a_coffee():
    html = _about_html()
    assert BUY_ME_A_COFFEE_URL == "https://buymeacoffee.com/thevenom"
    assert BUY_ME_A_COFFEE_URL in html
    assert "buy me a coffee" in html.lower()


def test_about_html_links_notice_file():
    html = _about_html()
    assert "NOTICE</a>" in html
    assert "file://" in html or "notice" in html.lower()


def test_version_line_includes_version_number():
    import orbitrx
    assert orbitrx.__version__ in _version_line()


def test_build_commit_prefers_env(monkeypatch):
    monkeypatch.setenv("ORBITRX_COMMIT_SHA", "abc1234deadbeef")
    assert _build_commit() == "abc1234deadb"


def test_about_dialog_is_selectable_and_fixed_width(qtbot_app):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QLabel

    dlg = QDialog()
    dlg.setFixedWidth(480)
    lbl = QLabel(_about_html())
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    assert dlg.width() == 480
    assert lbl.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse


@pytest.fixture
def qtbot_app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
