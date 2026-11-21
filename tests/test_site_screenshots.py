"""Website captures: three window-only PNGs, offline fixture, exact size."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1")
pytest.importorskip("PySide6.QtWidgets")


def test_site_screenshot_hook_writes_three_exact_pngs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ORBITRX_OFFLINE_FIXTURE", "1")
    monkeypatch.delenv("ORBITRX_CAPTURE_DIR", raising=False)
    monkeypatch.delenv("ORBITRX_SITE_SHOTS", raising=False)

    from PIL import Image

    from orbitrx.ui.qt_app import run_site_screenshot_hook

    out = tmp_path / "shots"
    assert run_site_screenshot_hook(out) == 0
    for name in ("main-window.png", "history.png", "settings-rig.png"):
        path = out / name
        assert path.is_file(), name
        assert Image.open(path).size == (1460, 928), name


def test_run_qt_app_uses_the_site_hook_only_when_asked():
    text = (Path(__file__).resolve().parents[1] / "orbitrx" / "ui" / "qt_app.py").read_text(encoding="utf-8")
    assert 'os.environ.get("ORBITRX_SITE_SHOTS")' in text
    assert "run_site_screenshot_hook" in text
