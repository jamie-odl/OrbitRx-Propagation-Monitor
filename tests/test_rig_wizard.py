"""Rig wizard: labels match Settings, Windows never shows a /dev path (M9)."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def cfg(tmp_path):
    from pathlib import Path
    from orbitrx.config import AppConfig
    return AppConfig(path=Path(tmp_path) / "c.json").load()


def test_rig_wizard_port_combo_is_editable(app, cfg):
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import RigWizardDialog
    dlg = RigWizardDialog(cfg, CatController(cfg))
    assert dlg.port_combo.isEditable() is True


def test_populate_port_combo_uses_cat_controller_enumeration(app, cfg, monkeypatch): # N-new-1
    from PySide6.QtWidgets import QComboBox
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import populate_port_combo

    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [("COM5", "USB Serial")])
    combo = QComboBox()
    populate_port_combo(combo, cat, "")
    assert combo.count() == 1
    assert combo.itemData(0) == "COM5"
    assert "COM5" in combo.itemText(0)


def test_populate_port_combo_falls_back_when_no_ports(app, cfg, monkeypatch): # N-new-1
    from PySide6.QtWidgets import QComboBox
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import populate_port_combo

    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [])
    combo = QComboBox()
    populate_port_combo(combo, cat, "COM9")
    assert combo.count() == 1
    assert combo.currentText() == "COM9"


def test_rig_wizard_title_is_rig_setup(app, cfg):
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import RigWizardDialog
    dlg = RigWizardDialog(cfg, CatController(cfg))
    assert dlg.windowTitle() == "Rig setup"
    assert dlg.minimumWidth() >= 420


def test_rig_wizard_labels_match_settings_dialog(app, cfg, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)

    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import RigWizardDialog
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    win = QtOrbitRxApplication()
    settings_dlg = win._build_settings_dialog(initial_page="Rig")
    wizard = RigWizardDialog(cfg, CatController(cfg))

    def labels_of(form_layout):
        out = []
        for i in range(form_layout.rowCount()):
            item = form_layout.itemAt(i, form_layout.ItemRole.LabelRole)
            if item and item.widget():
                out.append(item.widget().text())
        return out

    rig_row = next(i for i in range(settings_dlg.page_list.count()) if settings_dlg.page_list.item(i).text() == "Rig")
    settings_rig_page = settings_dlg.stack.widget(rig_row)
    settings_labels = labels_of(settings_rig_page.layout())
    wizard_labels = labels_of(wizard.layout().itemAt(0).layout())

    assert "Serial port" in wizard_labels and "Serial port" in settings_labels
    assert "Rig profile" in wizard_labels and "Rig profile" in settings_labels
    assert "Baud rate" in wizard_labels and "Baud rate" in settings_labels

    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_windows_never_shows_dev_tty_port(monkeypatch, cfg):
    from orbitrx import cat as catmod
    from serial.tools import list_ports as real_list_ports

    class FakePort:
        def __init__(self, device, description):
            self.device = device
            self.description = description

    def fake_comports():
        return [FakePort("/dev/ttyS0", "Linux serial"), FakePort("COM4", "USB Serial Port")]

    monkeypatch.setattr(catmod, "CAT_AVAILABLE", True)
    monkeypatch.setattr(catmod.sys, "platform", "win32")
    monkeypatch.setattr(real_list_ports, "comports", fake_comports)

    controller = catmod.CatController(cfg)
    ports = controller.list_ports_detailed()
    assert all(device.upper().startswith("COM") for device, _ in ports)
    assert ("/dev/ttyS0", "Linux serial") not in ports


def test_default_port_fallback_is_platform_appropriate(monkeypatch):
    from orbitrx import cat as catmod

    monkeypatch.setattr(catmod.sys, "platform", "win32")
    assert catmod.default_port_fallback() == "COM3"
    monkeypatch.setattr(catmod.sys, "platform", "linux")
    assert catmod.default_port_fallback() != "COM3"


def _editable_combo():
    from PySide6.QtWidgets import QComboBox
    combo = QComboBox()
    combo.setEditable(True)
    return combo


def test_missing_saved_port_selects_first_enumerated_port(app, cfg, monkeypatch):
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import populate_port_combo

    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [("COM2", "Communications Port (COM2)"), ("COM7", "USB Serial")])
    combo = _editable_combo()
    populate_port_combo(combo, cat, "COM3")  # saved port no longer exists
    assert combo.currentIndex() == 0
    assert combo.currentData() == "COM2"
    assert combo.currentText().startswith("COM2")
    assert "COM3" not in combo.currentText()


def test_present_saved_port_is_kept(app, cfg, monkeypatch):
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import populate_port_combo

    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [("COM2", "A"), ("COM7", "B")])
    combo = _editable_combo()
    populate_port_combo(combo, cat, "COM7")
    assert combo.currentData() == "COM7"


def test_simulated_cat_controller_shows_connected_state(app, cfg): # N1
    from orbitrx.ui.rig_wizard import RigWizardDialog, SimulatedCatController

    dlg = RigWizardDialog(cfg, SimulatedCatController())
    dlg._test_cat()
    assert dlg.status_text.text() == "● Connected: 14.074 MHz"
    assert dlg.status_text.styleSheet() == "color: #3FB950;"
    assert dlg.status_icon.text() == "🟢"


def test_simulated_cat_controller_is_not_the_production_default(app, cfg): # N1
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import RigWizardDialog, SimulatedCatController

    dlg = RigWizardDialog(cfg, CatController(cfg))
    assert not isinstance(dlg.cat, SimulatedCatController)


def test_port_label_has_no_nested_brackets(): # S5
    from orbitrx.ui.rig_wizard import _port_label

    assert _port_label("COM2", "Communications Port (COM2)") == "COM2 - Communications Port"
    assert _port_label("COM5", "USB Serial") == "COM5 - USB Serial"
    assert _port_label("COM9", "") == "COM9"
    assert _port_label("COM9", "COM9") == "COM9"
    assert "(" not in _port_label("COM2", "Communications Port (COM2)")


def test_populate_port_combo_strips_nested_brackets(app, cfg, monkeypatch): # S5
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import populate_port_combo
    from PySide6.QtWidgets import QComboBox

    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [("COM2", "Communications Port (COM2)")])
    combo = QComboBox()
    populate_port_combo(combo, cat, "COM2")
    assert combo.itemText(0) == "COM2 - Communications Port"


def test_rig_wizard_selects_first_real_port_when_saved_port_missing(app, cfg, monkeypatch):
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import RigWizardDialog

    cfg.set("cat_port", "COM3") if hasattr(cfg, "set") else cfg.__setitem__("cat_port", "COM3")
    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [("COM2", "Communications Port (COM2)")])
    dlg = RigWizardDialog(cfg, cat)
    assert dlg.port_combo.currentData() == "COM2"
