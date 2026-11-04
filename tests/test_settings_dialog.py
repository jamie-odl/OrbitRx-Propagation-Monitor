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


def test_serial_port_is_an_editable_combo_box(window): # N-new-1
    from PySide6.QtWidgets import QComboBox

    dlg = window._build_settings_dialog()
    field = dlg.fields["cat_port"]
    assert isinstance(field, QComboBox)
    assert field.isEditable() is True


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


def test_ip_lookup_privacy_text_is_fully_visible(window): # R1
    from PySide6.QtWidgets import QLabel

    dlg = window._build_settings_dialog()
    checkbox = dlg.fields["ip_geolocation_enabled"]
    assert "ipinfo.io" not in checkbox.text()
    station_page = dlg.stack.widget(EXPECTED_PAGES.index("Station"))
    notes = [lbl for lbl in station_page.findChildren(QLabel) if "ipinfo.io" in lbl.text()]
    assert len(notes) == 1
    assert notes[0].wordWrap() is True


def test_settings_label_column_is_consistent_across_pages(window): # N-new-3
    from orbitrx.ui.qt_app import SETTINGS_LABEL_WIDTH

    dlg = window._build_settings_dialog()
    sample_fields = [
        "spots_callsign", "cat_port", "dx_cluster_callsign",
        "spots_mode", "map_backend", "refresh_interval_seconds",
    ]
    for key in sample_fields:
        field = dlg.fields[key]
        form = field.parentWidget().layout()
        label = form.labelForField(field)
        assert label is not None, key
        assert label.minimumWidth() == SETTINGS_LABEL_WIDTH, key


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


def test_settings_serial_port_selects_first_real_port_when_saved_missing(window, monkeypatch):
    from PySide6.QtWidgets import QComboBox
    window.ctrl.cfg.data["cat_port"] = "COM3"
    monkeypatch.setattr(window.ctrl.cat, "list_ports_detailed",
                        lambda: [("COM2", "Communications Port (COM2)"), ("COM7", "USB Serial")])
    dlg = window._build_settings_dialog()
    port_combos = [c for c in dlg.findChildren(QComboBox) if c.findData("COM2") >= 0]
    assert len(port_combos) == 1
    assert port_combos[0].currentData() == "COM2"


def test_cluster_live_indicator_in_panel_header(window):
    window.ctrl.state.cluster_status = "connected"
    window._render_cluster_label()
    assert "Cluster: live" in window.cluster_live_lbl.text()
    assert "●" in window.cluster_live_lbl.text()
    window.ctrl.state.cluster_status = "disconnected"
    window._render_cluster_label()
    assert window.cluster_live_lbl.text() == "Cluster: disconnected"
