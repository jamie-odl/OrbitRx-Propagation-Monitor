"""Rig wizard: labels match Settings, Windows never shows a /dev path (M9)."""

from __future__ import annotations

import os
import sys
import time

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

    from PySide6.QtWidgets import QLabel

    def labels_of(root):
        return [lbl.text().replace("&", "") for lbl in root.findChildren(QLabel)]

    rig_row = next(i for i in range(settings_dlg.page_list.count()) if settings_dlg.page_list.item(i).text() == "Rig")
    settings_rig_page = settings_dlg.stack.widget(rig_row)
    settings_labels = labels_of(settings_rig_page)
    wizard_labels = labels_of(wizard)

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


def test_fresh_install_and_wizard_keep_rig_defaults(app, cfg, tmp_path):
    """New configs ask before a tune and use OmniRig Rig 1. The wizard writes
    those defaults when they are missing and does not overwrite a real choice."""
    from orbitrx.cat import CatController
    from orbitrx.config import DEFAULT_CONFIG, AppConfig
    from orbitrx.ui.rig_wizard import RigWizardDialog

    assert DEFAULT_CONFIG["omnirig_rig_number"] == 1
    assert DEFAULT_CONFIG["cat_confirm_before_tune"] is True
    assert DEFAULT_CONFIG["home_lat"] == 51.5081
    assert DEFAULT_CONFIG["home_lon"] == -0.1281

    fresh = AppConfig(path=tmp_path / "fresh.json").load()
    assert fresh.get("omnirig_rig_number") == 1
    assert fresh.get("cat_confirm_before_tune") is True

    cfg.data.pop("omnirig_rig_number", None)
    cfg.data.pop("cat_confirm_before_tune", None)
    dlg = RigWizardDialog(cfg, CatController(cfg))
    dlg._save()
    assert cfg.get("omnirig_rig_number") == 1
    assert cfg.get("cat_confirm_before_tune") is True

    cfg.set("omnirig_rig_number", 2)
    cfg.set("cat_confirm_before_tune", False)
    dlg2 = RigWizardDialog(cfg, CatController(cfg))
    dlg2._save()
    assert cfg.get("omnirig_rig_number") == 2
    assert cfg.get("cat_confirm_before_tune") is False


def test_present_saved_port_is_kept(app, cfg, monkeypatch):
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import populate_port_combo

    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [("COM2", "A"), ("COM7", "B")])
    combo = _editable_combo()
    populate_port_combo(combo, cat, "COM7")
    assert combo.currentData() == "COM7"


def test_simulated_cat_controller_shows_connected_state(app, cfg, monkeypatch): # N1
    from orbitrx.ui.rig_wizard import RigWizardDialog, SimulatedCatController

    monkeypatch.setenv("ORBITRX_TEST_SIMULATED_RIG", "1")
    dlg = RigWizardDialog(cfg, SimulatedCatController())
    dlg._test_cat()
    # Test CAT now runs on a worker thread; pump the event loop for the
    # queued result instead of asserting on it synchronously.
    deadline = time.time() + 2.0
    while not dlg.test_btn.isEnabled() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert dlg.status_text.text() == "Connected: 14.074 MHz"
    assert "●" not in dlg.status_text.text()  # single status dot comes from status_icon
    assert dlg.status_text.styleSheet() == "color: #3FB950;"
    assert dlg.status_icon.text() == "🟢"


def test_simulated_cat_controller_requires_env_var(monkeypatch): # M3
    from orbitrx.ui.rig_wizard import SimulatedCatController

    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    with pytest.raises(RuntimeError):
        SimulatedCatController()


def test_simulated_cat_controller_works_once_env_var_is_set(monkeypatch): # M3
    from orbitrx.ui.rig_wizard import SimulatedCatController

    monkeypatch.setenv("ORBITRX_TEST_SIMULATED_RIG", "1")
    sim = SimulatedCatController()
    assert sim.port == "COM9"


def test_wizard_port_list_never_contains_simulated_without_env_var(app, cfg, monkeypatch): # M3
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import RigWizardDialog

    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [("COM5", "USB Serial")])
    dlg = RigWizardDialog(cfg, cat)
    items = [dlg.port_combo.itemText(i) for i in range(dlg.port_combo.count())]
    assert not any("Simulated" in item for item in items)


def test_settings_port_list_never_contains_simulated_without_env_var(app, cfg, monkeypatch): # M3
    from orbitrx.cat import CatController
    from orbitrx.ui.rig_wizard import populate_port_combo
    from PySide6.QtWidgets import QComboBox

    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    cat = CatController(cfg)
    monkeypatch.setattr(cat, "list_ports_detailed", lambda: [("COM5", "USB Serial")])
    combo = QComboBox()
    populate_port_combo(combo, cat, "")
    items = [combo.itemText(i) for i in range(combo.count())]
    assert not any("Simulated" in item for item in items)


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
