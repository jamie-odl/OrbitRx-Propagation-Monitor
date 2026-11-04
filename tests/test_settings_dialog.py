"""Settings dialog: paged layout, masked QRZ key, validated spin box ranges (M1, M10, S8)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

EXPECTED_PAGES = ["Station", "Rig", "DX cluster", "Live spots", "Map", "Services"]


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication, QLineEdit

    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)

    app = QApplication.instance() or QApplication([])
    from orbitrx.ui.qt_app import QtOrbitRxApplication
    win = QtOrbitRxApplication()
    yield win
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_settings_has_six_pages_in_order(window):
    dlg = window._build_settings_dialog()
    names = [dlg.page_list.item(i).text() for i in range(dlg.page_list.count())]
    assert names == EXPECTED_PAGES


def test_settings_dialog_fits_release_size_budget(window):
    dlg = window._build_settings_dialog()
    assert dlg.width() <= 720
    assert dlg.height() <= 520


def test_settings_title_is_plain_settings(window):
    dlg = window._build_settings_dialog()
    assert dlg.windowTitle() == "Settings"


def test_qrz_key_is_masked_by_default(window):
    from PySide6.QtWidgets import QLineEdit

    dlg = window._build_settings_dialog()
    assert dlg.fields["qrz_api_key"].echoMode() == QLineEdit.EchoMode.Password
    actions = dlg.fields["qrz_api_key"].actions()
    assert len(actions) == 1 and actions[0].isCheckable()


def test_qrz_show_hide_action_toggles_echo_mode(window):
    from PySide6.QtWidgets import QLineEdit

    dlg = window._build_settings_dialog()
    action = dlg.fields["qrz_api_key"].actions()[0]
    action.setChecked(True)
    assert dlg.fields["qrz_api_key"].echoMode() == QLineEdit.EchoMode.Normal
    action.setChecked(False)
    assert dlg.fields["qrz_api_key"].echoMode() == QLineEdit.EchoMode.Password


@pytest.mark.parametrize(
    "key,lo,hi",
    [
        ("home_lat", -90.0, 90.0),
        ("home_lon", -180.0, 180.0),
        ("target_dx_lat", -90.0, 90.0),
        ("target_dx_lon", -180.0, 180.0),
    ],
)
def test_lat_lon_spin_box_ranges(window, key, lo, hi):
    dlg = window._build_settings_dialog()
    field = dlg.fields[key]
    assert field.minimum() == lo
    assert field.maximum() == hi


def test_poll_interval_spin_box_has_five_minute_floor(window):
    dlg = window._build_settings_dialog()
    field = dlg.fields["pskreporter_poll_seconds"]
    assert field.minimum() == 300
    assert field.suffix().strip() == "s"


def test_refresh_interval_spin_box_has_suffix(window):
    dlg = window._build_settings_dialog()
    field = dlg.fields["refresh_interval_seconds"]
    assert field.suffix().strip() == "s"


def test_rig_profile_and_baud_are_combo_boxes_matching_wizard(window):
    from orbitrx.cat import RIG_PROFILES
    from PySide6.QtWidgets import QComboBox

    dlg = window._build_settings_dialog()
    assert isinstance(dlg.fields["cat_rig_profile"], QComboBox)
    assert isinstance(dlg.fields["cat_baud"], QComboBox)
    items = {dlg.fields["cat_rig_profile"].itemText(i) for i in range(dlg.fields["cat_rig_profile"].count())}
    assert items == set(RIG_PROFILES.keys())


def test_test_qrz_button_lives_on_services_page_with_the_key(window):
    from PySide6.QtWidgets import QPushButton

    dlg = window._build_settings_dialog()
    services_page = dlg.fields["qrz_api_key"].parentWidget()
    buttons = [b.text() for b in services_page.findChildren(QPushButton)]
    assert "Test QRZ" in buttons


def test_initial_page_opens_requested_page(window):
    dlg = window._build_settings_dialog(initial_page="Map")
    assert dlg.page_list.currentRow() == EXPECTED_PAGES.index("Map")
    assert dlg.stack.currentIndex() == EXPECTED_PAGES.index("Map")


def test_settings_dialog_saves_values_into_config(window):
    dlg = window._build_settings_dialog()
    dlg.fields["spots_callsign"].setText("W1AW")
    dlg.fields["home_lat"].setValue(51.5)
    dlg.fields["home_lon"].setValue(-0.12)
    dlg.fields["qrz_api_key"].setText("secretkey")
    window._apply_settings_dialog(dlg)
    assert window.ctrl.cfg.get("spots_callsign") == "W1AW"
    assert window.ctrl.cfg.get("home_lat") == 51.5
    assert window.ctrl.cfg.get("home_lon") == -0.12
    assert window.ctrl.cfg.get("qrz_api_key") == "secretkey"
