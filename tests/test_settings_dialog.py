"""Settings dialog: paged layout, masked QRZ key, validated spin box ranges (M1, M10, S8)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

EXPECTED_PAGES = ["Station", "Rig", "DX cluster", "Map & spots", "Services"]


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


def test_settings_has_five_pages_in_order(window): # S4: Live spots + Map merged
    dlg = window._build_settings_dialog()
    names = [dlg.page_list.item(i).text() for i in range(dlg.page_list.count())]
    assert names == EXPECTED_PAGES
    assert len(names) == 5


def test_every_settings_page_has_a_non_empty_description(window): # S4
    from PySide6.QtWidgets import QLabel

    dlg = window._build_settings_dialog()
    for i in range(dlg.stack.count()):
        page = dlg.stack.widget(i)
        descriptions = [
            lbl for lbl in page.findChildren(QLabel)
            if lbl.objectName() == "muted" and lbl.wordWrap()
        ]
        assert descriptions, EXPECTED_PAGES[i]
        assert descriptions[0].text().strip() != "", EXPECTED_PAGES[i]


def test_map_and_spots_page_keeps_all_merged_controls(window): # S4
    dlg = window._build_settings_dialog()
    for key in ("spots_mode", "pskreporter_poll_seconds"):
        field = dlg.fields[key]
        page = field.parentWidget()
        assert dlg.stack.indexOf(page) == EXPECTED_PAGES.index("Map & spots")


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


@pytest.mark.parametrize(
    "key", ["home_lat", "home_lon", "target_dx_lat", "target_dx_lon", "pskreporter_poll_seconds", "refresh_interval_seconds"],
)
def test_spin_boxes_are_tall_enough_for_both_arrows(window, key): # M3
    dlg = window._build_settings_dialog()
    assert dlg.fields[key].minimumHeight() >= 30


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
    dlg = window._build_settings_dialog(initial_page="Map & spots")
    assert dlg.page_list.currentRow() == EXPECTED_PAGES.index("Map & spots")
    assert dlg.stack.currentIndex() == EXPECTED_PAGES.index("Map & spots")


def test_ip_lookup_privacy_text_is_fully_visible(window): # R1
    from PySide6.QtWidgets import QLabel

    dlg = window._build_settings_dialog()
    checkbox = dlg.fields["ip_geolocation_enabled"]
    assert "ipinfo.io" not in checkbox.text()
    station_page = dlg.stack.widget(EXPECTED_PAGES.index("Station"))
    notes = [lbl for lbl in station_page.findChildren(QLabel) if "ipinfo.io" in lbl.text()]
    assert len(notes) == 1
    assert notes[0].wordWrap() is True


def test_location_label_baseline_matches_checkbox(window): # S1/R2
    dlg = window._build_settings_dialog()
    dlg.show()
    station_page = dlg.stack.widget(EXPECTED_PAGES.index("Station"))
    form = station_page.layout()
    checkbox = dlg.fields["ip_geolocation_enabled"]
    label = form.labelForField(checkbox)
    assert label is not None
    assert label.text() == "Location"
    label_center = label.mapTo(dlg, label.rect().center()).y()
    checkbox_center = checkbox.mapTo(dlg, checkbox.rect().center()).y()
    assert abs(label_center - checkbox_center) <= 2


def test_map_and_spots_description_uses_lowercase_live_spots(window): # S1
    dlg = window._build_settings_dialog()
    from orbitrx.ui.qt_app import SETTINGS_PAGE_DESCRIPTIONS
    assert "live spots" in SETTINGS_PAGE_DESCRIPTIONS["Map & spots"]
    assert "Live Spots" not in SETTINGS_PAGE_DESCRIPTIONS["Map & spots"]


def test_settings_label_column_is_consistent_across_pages(window): # N-new-3
    from orbitrx.ui.qt_app import SETTINGS_LABEL_WIDTH

    dlg = window._build_settings_dialog()
    sample_fields = [
        "spots_callsign", "cat_port", "dx_cluster_callsign",
        "spots_mode", "refresh_interval_seconds",
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


def test_spin_box_border_spans_full_field_width_with_buttons_inside(window): # M3
    """Every spin box must line up with the QLineEdit/QComboBox fields in the same
    form: same right edge (within 1px), same width (give or take the 1px border),
    and the up-button subcontrol rect fully inside the widget's own rect (not
    overhanging past a detached border)."""
    from PySide6.QtWidgets import (
        QAbstractSpinBox, QComboBox, QLineEdit, QStyle, QStyleOptionSpinBox,
    )

    dlg = window._build_settings_dialog()
    dlg.show()
    checked = 0
    for i in range(dlg.stack.count()):
        page = dlg.stack.widget(i)
        form = page.layout()
        for row in range(form.rowCount()):
            field_item = form.itemAt(row, form.ItemRole.FieldRole)
            if not field_item or not field_item.widget():
                continue
            field = field_item.widget()
            if not isinstance(field, (QLineEdit, QComboBox)):
                continue
            label_item = form.itemAt(row, form.ItemRole.LabelRole)
            if not label_item or not label_item.widget():
                continue
            for other_row in range(form.rowCount()):
                other_item = form.itemAt(other_row, form.ItemRole.FieldRole)
                if not other_item or not other_item.widget():
                    continue
                sb = other_item.widget()
                if not isinstance(sb, QAbstractSpinBox):
                    continue
                field_right = field.mapTo(dlg, field.rect().topRight()).x()
                sb_right = sb.mapTo(dlg, sb.rect().topRight()).x()
                assert abs(field_right - sb_right) <= 1, (page, field, sb)
                assert sb.width() >= field.width() - 1

                opt = QStyleOptionSpinBox()
                sb.initStyleOption(opt)
                up_rect = sb.style().subControlRect(
                    QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxUp, sb
                )
                assert sb.rect().contains(up_rect), (page, sb, up_rect, sb.rect())
                checked += 1
    assert checked > 0


def test_cluster_live_indicator_in_panel_header(window):
    window.ctrl.state.cluster_status = "connected"
    window._render_cluster_label()
    assert "Cluster: live" in window.cluster_live_lbl.text()
    assert "●" in window.cluster_live_lbl.text()
    window.ctrl.state.cluster_status = "disconnected"
    window._render_cluster_label()
    assert window.cluster_live_lbl.text() == "Cluster: disconnected"


def test_spinbox_text_inset_matches_line_edit(window):  # M3
    from PySide6.QtWidgets import QAbstractSpinBox
    dlg = window._build_settings_dialog()
    sbs = dlg.findChildren(QAbstractSpinBox)
    assert sbs
    for sb in sbs:
        assert sb.lineEdit().textMargins().left() == 6
