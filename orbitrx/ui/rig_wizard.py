from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QVBoxLayout,
)

from orbitrx.cat import CatController, RIG_PROFILES, default_port_fallback
from orbitrx.config import AppConfig
from orbitrx.ui.theme import ERR, OK
from orbitrx.ui.window_fit import fit_to_screen

# N1: distinct from the normal OK colour, this marks a *simulated* connected state
# (screenshots/tests only) so it is never mistaken for a genuine CAT success.
SIMULATED_CAT_COLOR = "#3FB950"
_SIMULATED_PREFIX = "SIMULATED_CONNECTED:"


class SimulatedCatController:
    """Fake CAT backend that always reports a connected rig, for screenshots and
    tests. Never used by production code: RigWizardDialog defaults to the real
    CatController, this is only passed in explicitly by callers that want it.

    M3: unusable unless ORBITRX_TEST_SIMULATED_RIG=1 is set, so a release build can
    never surface the simulated port even if something constructs this by mistake."""

    def __init__(self, freq_mhz: float = 14.074, port: str = "COM9") -> None:
        if os.environ.get("ORBITRX_TEST_SIMULATED_RIG") != "1":
            raise RuntimeError(
                "SimulatedCatController is for screenshots/tests only; "
                "set ORBITRX_TEST_SIMULATED_RIG=1 to use it."
            )
        self.freq_mhz = freq_mhz
        self.port = port

    def list_ports_detailed(self) -> list[tuple[str, str]]:
        return [(self.port, "Simulated rig (screenshots/tests)")]

    def tune(self, freq_mhz: float | str, confirm=None) -> str:
        return f"{_SIMULATED_PREFIX}{self.freq_mhz:.3f}"


def _port_label(device: str, desc: str) -> str:
    """"COM2 - Communications Port", never "COM2 (Communications Port (COM2))" (S5):
    pyserial's description often already repeats the device name in brackets.
    """
    desc = (desc or "").strip()
    suffix = f" ({device})"
    if desc.endswith(suffix):
        desc = desc[: -len(suffix)].strip()
    if not desc or desc == device:
        return device
    return f"{device} - {desc}"


def populate_port_combo(combo: QComboBox, cat: CatController, current_port: str) -> None:
    """Fill a serial-port combo from the same enumeration CatController uses everywhere,
    so Settings and the rig wizard never disagree (N-new-1)."""
    combo.clear()
    ports = cat.list_ports_detailed()
    if ports:
        for device, desc in ports:
            combo.addItem(_port_label(device, desc), device)
    else:
        fallback = current_port or default_port_fallback()
        combo.addItem(fallback, fallback)
    idx = combo.findData(current_port)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    elif ports:
        # Saved port is not present on this machine: pick the first real port.
        combo.setCurrentIndex(0)
    elif current_port:
        combo.setEditText(current_port)


class RigWizardDialog(QDialog):
    """Detect serial port, test CAT, save rig profile."""

    def __init__(self, cfg: AppConfig, cat: CatController, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.cat = cat
        self.setWindowTitle("Rig setup")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self._fill_ports()
        form.addRow("Serial port", self.port_combo)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(sorted(RIG_PROFILES.keys()))
        pidx = self.profile_combo.findText(str(cfg.get("cat_rig_profile", "kenwood")))
        if pidx >= 0:
            self.profile_combo.setCurrentIndex(pidx)
        form.addRow("Rig profile", self.profile_combo)

        self.baud_combo = QComboBox()
        for b in ("4800", "9600", "19200", "38400", "115200"):
            self.baud_combo.addItem(b)
        bidx = self.baud_combo.findText(str(cfg.get("cat_baud", 9600)))
        if bidx >= 0:
            self.baud_combo.setCurrentIndex(bidx)
        form.addRow("Baud rate", self.baud_combo)

        lay.addLayout(form)

        self.status_icon = QLabel("")
        self.status_icon.setFixedWidth(16)
        self.status_text = QLabel("Select a port and click Test CAT.")
        self.status_text.setWordWrap(True)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_icon)
        status_row.addWidget(self.status_text, stretch=1)
        lay.addLayout(status_row)

        test_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh ports", clicked=self._refresh_ports)
        test_btn = QPushButton("Test CAT", clicked=self._test_cat)
        test_row.addWidget(refresh_btn, stretch=1)
        test_row.addWidget(test_btn, stretch=1)
        lay.addLayout(test_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        # Natural size at 100%, then clamped to the available screen so Save/Cancel
        # stay reachable on a small or scaled-up display.
        self.adjustSize()
        fit_to_screen(self, 420, 200)

    def _fill_ports(self) -> None:
        populate_port_combo(self.port_combo, self.cat, str(self.cfg.get("cat_port", "") or ""))

    def _current_port(self) -> str:
        data = self.port_combo.currentData()
        return data if data else self.port_combo.currentText()

    def _refresh_ports(self) -> None:
        self._fill_ports()
        n = len(self.cat.list_ports_detailed())
        if n:
            self.status_text.setText(f"Found {n} port(s).")
            self.status_icon.setText("")
        else:
            self.status_text.setText("No serial ports detected (pyserial missing or no USB rigs).")
            self.status_icon.setText("")

    def _test_cat(self) -> None:
        self.cfg.data["cat_port"] = self._current_port()
        self.cfg.data["cat_baud"] = int(self.baud_combo.currentText())
        self.cfg.data["cat_rig_profile"] = self.profile_combo.currentText()
        test_freq = 14.200
        result = self.cat.tune(test_freq, confirm=None)
        if result.startswith(_SIMULATED_PREFIX):
            freq = result[len(_SIMULATED_PREFIX):]
            self.status_icon.setText("🟢")
            self.status_text.setText(f"Connected: {freq} MHz")  # the status icon already shows the dot
            self.status_text.setStyleSheet(f"color: {SIMULATED_CAT_COLOR};")
            return
        ok = "Sent CAT" in result
        self.status_icon.setText("🟢" if ok else "🔴")
        self.status_text.setText(f"{result} (test frequency {test_freq} MHz)" if ok else result)
        self.status_text.setStyleSheet(f"color: {OK if ok else ERR};")
        if ok:
            QMessageBox.information(self, "CAT", "Rig responded. Profile looks good.")

    def _save(self) -> None:
        port = self._current_port()
        profile = {
            "name": f"{self.profile_combo.currentText()} @ {port}",
            "port": port,
            "baud": int(self.baud_combo.currentText()),
            "rig_profile": self.profile_combo.currentText(),
        }
        profiles = list(self.cfg.get("rig_profiles") or [])
        profiles = [p for p in profiles if p.get("port") != profile["port"]]
        profiles.insert(0, profile)
        self.cfg.set("rig_profiles", profiles[:5])
        self.cfg.set("cat_port", profile["port"])
        self.cfg.set("cat_baud", profile["baud"])
        self.cfg.set("cat_rig_profile", profile["rig_profile"])
        self.accept()
