"""Settings dialog (P3a).

Left section list, sticky Cancel / Apply / Save footer, validation, dirty
tracking, and a CAT test that reads the radio instead of retuning it.
"""

from __future__ import annotations

import re
import sys
import time

from PySide6.QtCore import QEvent, QLocale, QObject, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAccessible,
    QAccessibleEvent,
    QColor,
    QDoubleValidator,
    QFont,
    QFontMetrics,
    QIcon,
    QIntValidator,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QStylePainter,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from orbitrx.cat import (
    CAT_AVAILABLE,
    RIG_PROFILE_LABELS,
    RIG_PROFILES,
    parse_probe_result,
)
from orbitrx.propagation import HF_BANDS
from orbitrx.ui.async_utils import BackgroundTask, CatTestRunner
from orbitrx.ui.theme import (
    ACCENT,
    ACCENT_SOFT,
    BG_CANVAS,
    BG_HOVER,
    BG_INSET,
    BG_RAISED,
    BG_SURFACE,
    BORDER_CONTROL,
    BORDER_DEFAULT,
    BORDER_SUBTLE,
    FAIR,
    FONT_MONO,
    FONT_UI,
    GOOD,
    POOR,
    POOR_BG,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)
from orbitrx.ui.toast import ToastManager
from orbitrx.ui.window_fit import fit_to_screen

# A dialog that has filled a 683-wide screen is still wider than the spec's
# written 640 line, but settings-683x485.png is the compact layout (section
# combo, no nav). Enter below 720 and leave above 752 so 683 is compact and
# the 760 default stays wide, with the same ±16 hysteresis the spec asks for.
_COMPACT_ENTER = 720
_COMPACT_LEAVE = 752

SETTINGS_LABEL_WIDTH = 152
_WIDTHS = {"S": 160, "M": 220, "L": 300}
_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,4}(/[A-Z0-9]{1,4})?$")
_COM_RE = re.compile(r"^COM\d{1,3}$", re.IGNORECASE)
_PAGE_NAMES = ["Station", "Rig", "DX cluster", "Map & spots", "Services"]

PAGE_DESCRIPTIONS = {
    "Station": "Your callsign and home coordinates, used to centre the map and tag your spots.",
    "Rig": "Connect to your radio over CAT so clicking a spot on the map can tune it for you.",
    "DX cluster": "Your cluster login, an optional target station, and which spots show on the map.",
    "Map & spots": "How often live spots refresh from PSKReporter, and which mode they show.",
    "Services": "Optional QRZ lookups and how often space weather data refreshes.",
}

_ROLE_DIRTY = Qt.ItemDataRole.UserRole
_ROLE_ERRORS = Qt.ItemDataRole.UserRole + 1

SETTINGS_QSS = f"""
QDialog#settingsDialog, QDialog#unsavedPrompt {{ background: {BG_SURFACE}; color: {TEXT_PRIMARY};
    font-family: {FONT_UI}; font-size: 13px; }}
QWidget#formRow {{ background: transparent; }}
QListWidget#settingsNav {{ background: {BG_INSET}; border: none; border-right: 1px solid {BORDER_SUBTLE};
    padding: 12px 8px; outline: none; }}
QListWidget#settingsNav::item {{ height: 32px; padding: 0 10px; margin-bottom: 2px; border-radius: 6px;
    color: {TEXT_SECONDARY}; border-left: 2px solid transparent; }}
QListWidget#settingsNav::item:hover {{ background: {BG_RAISED}; color: {TEXT_PRIMARY}; }}
QListWidget#settingsNav::item:selected {{ background: {BG_HOVER}; color: {TEXT_PRIMARY}; font-weight: 600;
    border-left: 2px solid {ACCENT}; }}
QComboBox#sectionCombo {{ min-height: 30px; font-size: 14px; font-weight: 600; }}
QScrollArea#settingsScroll, QWidget#settingsPage {{ background: {BG_SURFACE}; border: none; }}
QLabel#pageTitle {{ font-size: 15px; font-weight: 600; color: {TEXT_PRIMARY}; background: transparent; }}
QLabel#pageDescription, QLabel#fieldHelp {{ font-size: 12px; color: {TEXT_TERTIARY}; background: transparent; }}
QLabel#groupTitle {{ font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY}; background: transparent; }}
QFrame#groupRule {{ background: {BORDER_SUBTLE}; max-height: 1px; min-height: 1px; border: none; }}
QLabel#fieldLabel {{ font-size: 13px; color: {TEXT_SECONDARY}; background: transparent; }}
QLabel#fieldLabel:disabled {{ color: {TEXT_DISABLED}; }}
QLabel#optionalMark {{ font-size: 11px; color: {TEXT_TERTIARY}; background: transparent; }}
QLabel#fieldError, QLabel#fieldErrorIcon {{ font-size: 12px; color: {POOR}; background: transparent; }}
QLabel#fieldErrorIcon {{ font-size: 14px; font-weight: 600; }}
QLineEdit, QComboBox, QAbstractSpinBox {{ background: {BG_RAISED}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_CONTROL}; border-radius: 6px; padding: 0 10px; min-height: 26px; }}
QLineEdit:hover, QComboBox:hover, QAbstractSpinBox:hover {{ border-color: #8A95A8; }}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{ border: 2px solid {ACCENT}; padding: 0 9px; }}
QLineEdit[invalid="true"], QComboBox[invalid="true"], QAbstractSpinBox[invalid="true"],
QFrame#coordField[invalid="true"] {{ border: 2px solid {POOR}; }}
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{ background: transparent;
    border-color: {BORDER_DEFAULT}; color: {TEXT_DISABLED}; }}
QFrame#coordField {{ background: {BG_RAISED}; border: 1px solid {BORDER_CONTROL}; border-radius: 6px; }}
QFrame#coordField:disabled {{ background: transparent; border-color: {BORDER_DEFAULT}; }}
QFrame#coordField QLineEdit {{ border: none; background: transparent; padding: 0 4px; min-height: 24px; }}
QLabel#coordSuffix {{ color: {TEXT_TERTIARY}; background: transparent; font-size: 12px; }}
QToolButton#chip {{ min-height: 24px; min-width: 44px; padding: 0 10px; border-radius: 6px;
    border: 1px solid {BORDER_DEFAULT}; color: {TEXT_TERTIARY}; background: transparent; font-size: 12px; }}
QToolButton#chip:hover {{ background: {BG_HOVER}; color: {TEXT_SECONDARY}; }}
QToolButton#chip:checked {{ background: {ACCENT_SOFT}; color: {TEXT_PRIMARY}; border-color: {ACCENT_SOFT}; }}
QToolButton#chip:focus {{ border-color: {ACCENT}; }}
QToolButton#chip:disabled {{ color: {TEXT_DISABLED}; }}
QFrame#segTrack {{ background: {BG_RAISED}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; }}
QToolButton#segButton {{ background: transparent; color: {TEXT_SECONDARY}; border: none; border-radius: 6px;
    padding: 0 12px; min-height: 24px; }}
QToolButton#segButton:checked {{ background: {BG_HOVER}; color: {TEXT_PRIMARY}; font-weight: 600; }}
QToolButton#segButton:focus {{ border: 1px solid {ACCENT}; }}
QToolButton#segButton:disabled {{ color: {TEXT_DISABLED}; }}
QPushButton {{ min-height: 28px; min-width: 80px; padding: 0 14px; border-radius: 6px;
    border: 1px solid {BORDER_DEFAULT}; background: transparent; color: {TEXT_PRIMARY}; }}
QPushButton:hover {{ background: {BG_HOVER}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {TEXT_DISABLED}; border-color: {BORDER_SUBTLE}; }}
QPushButton#primaryButton {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: {BG_CANVAS}; font-weight: 600; }}
QPushButton#primaryButton:hover {{ background: #93B4FF; border-color: #93B4FF; }}
QPushButton#primaryButton:disabled {{ background: #2A3550; border-color: #2A3550; color: #6A7A99; }}
QPushButton#destructiveButton {{ color: {POOR}; }}
QPushButton#destructiveButton:hover {{ background: {POOR_BG}; }}
QToolButton#iconButton {{ min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
    padding: 0; border-radius: 6px; border: 1px solid {BORDER_DEFAULT}; background: transparent; color: {TEXT_PRIMARY}; }}
QToolButton#iconButton:hover {{ background: {BG_HOVER}; }}
QToolButton#iconButton:focus {{ border-color: {ACCENT}; }}
QToolButton#iconButton:disabled {{ color: {TEXT_DISABLED}; }}
QFrame#errorSummary {{ background: {POOR_BG}; border: 1px solid rgba(244,127,130,0.35); border-radius: 8px; }}
QFrame#errorSummary QLabel {{ background: transparent; color: {TEXT_SECONDARY}; font-size: 12px; }}
QFrame#errorSummary QLabel#summaryTitle {{ color: {POOR}; font-size: 13px; font-weight: 600; }}
QFrame#testResult {{ background: {BG_RAISED}; border: 1px solid {BORDER_SUBTLE}; border-radius: 8px; }}
QFrame#testResult QLabel {{ background: transparent; }}
QFrame#testResult QLabel#resultTitle {{ font-size: 13px; color: {TEXT_PRIMARY}; }}
QFrame#testResult QLabel#resultDetail {{ font-size: 12px; color: {TEXT_TERTIARY}; }}
QLabel#appMessage {{ font-family: {FONT_MONO}; font-size: 11px; color: {TEXT_SECONDARY};
    background: {BG_INSET}; border: 1px solid {BORDER_SUBTLE}; border-radius: 4px; padding: 1px 5px; }}
QProgressBar#catProgress {{ border: none; background: {BG_INSET}; max-height: 2px; min-height: 2px; }}
QProgressBar#catProgress::chunk {{ background: {ACCENT}; }}
QFrame#settingsFooter {{ background: {BG_SURFACE}; border: none; border-top: 1px solid {BORDER_SUBTLE};
    min-height: 56px; max-height: 56px; }}
QFrame#settingsFooter[compact="true"] {{ min-height: 52px; max-height: 52px; }}
QLabel#dirtyIndicator {{ font-size: 12px; color: {TEXT_TERTIARY}; background: transparent; }}
QCheckBox {{ spacing: 8px; color: {TEXT_PRIMARY}; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {BORDER_CONTROL}; background: {BG_RAISED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox:disabled {{ color: {TEXT_DISABLED}; }}
"""


def _repolish(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _set_invalid(widget, invalid: bool) -> None:
    widget.setProperty("invalid", True if invalid else False)
    _repolish(widget)


def _announce(widget, text: str) -> None:
    try:
        QAccessible.updateAccessibility(QAccessibleEvent(widget, QAccessible.Event.Alert))
    except Exception:
        pass
    widget.setAccessibleDescription(text)


class _ButtonBox:
    """The footer buttons, with the same .button(StandardButton) lookup the
    rest of the app uses on a QDialogButtonBox."""

    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def button(self, standard):
        return self._mapping.get(standard)


class _NavDelegate(QStyledItemDelegate):
    """Draws the dirty dot and the error count. Item text stays the page name."""

    def paint(self, painter, option, index) -> None:  # noqa: N802
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        dirty = bool(index.data(_ROLE_DIRTY))
        errors = int(index.data(_ROLE_ERRORS) or 0)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        right = opt.rect.right() - 8
        mid = opt.rect.center().y()
        if errors:
            text = f"[{errors}]"
            font = painter.font()
            font.setPixelSize(11)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            width = QFontMetrics(font).horizontalAdvance(text) + 8
            badge = opt.rect.adjusted(0, 0, 0, 0)
            badge.setLeft(right - width)
            badge.setRight(right)
            badge.setTop(mid - 8)
            badge.setBottom(mid + 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(POOR_BG))
            painter.drawRoundedRect(badge, 4, 4)
            painter.setPen(QColor(POOR))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
            right = badge.left() - 6
        if dirty:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(TEXT_SECONDARY))
            painter.drawEllipse(right - 6, mid - 3, 6, 6)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), 32))


class SectionCombo(QComboBox):
    """Compact nav. The closed control reads 'Station · 1 of 5'."""

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        index = max(0, self.currentIndex())
        name = self.itemText(index)
        opt.currentText = f"{name}  ·  {index + 1} of {max(1, self.count())}"
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, opt)


class SegmentedChoice(QWidget):
    """Two or three exclusive choices. currentData() matches a combo."""

    def __init__(self, options: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        track = QFrame()
        track.setObjectName("segTrack")
        row = QHBoxLayout(track)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(0)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(track)
        outer.addStretch(1)
        self._by_data: dict[str, QToolButton] = {}
        for label, data in options:
            button = QToolButton()
            button.setObjectName("segButton")
            button.setText(label)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setProperty("value", data)
            button.setAccessibleName(label)
            self._group.addButton(button)
            self._by_data[data] = button
            row.addWidget(button)
        self._group.buttonClicked.connect(lambda _b: self._changed())
        self._handler = None

    def _changed(self) -> None:
        if self._handler is not None:
            self._handler()

    def on_change(self, handler) -> None:
        self._handler = handler

    def currentData(self):  # noqa: N802 - Qt naming, used like QComboBox
        button = self._group.checkedButton()
        return None if button is None else button.property("value")

    def set_value(self, data: str) -> None:
        button = self._by_data.get(data)
        if button is not None:
            button.setChecked(True)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        for button in self._by_data.values():
            button.setEnabled(enabled)


class SuffixedField(QFrame):
    """A line edit with the unit drawn inside the same border."""

    def __init__(self, suffix: str, width: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("coordField")
        self.setFixedWidth(width)
        self.edit = QLineEdit()
        self.edit.setFrame(False)
        self.suffix = QLabel(suffix)
        self.suffix.setObjectName("coordSuffix")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(4)
        row.addWidget(self.edit, stretch=1)
        row.addWidget(self.suffix)
        self.edit.installEventFilter(self)
        self.setFixedHeight(28)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.edit and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            _repolish(self)
        return False

    def set_suffix(self, text: str) -> None:
        self.suffix.setText(text)


class FieldRow(QWidget):
    def __init__(self, label_text: str, field: QWidget, help_text: str = "", optional: bool = False) -> None:
        super().__init__()
        self.setObjectName("formRow")
        self.field = field
        self.label = QLabel(label_text)
        self.label.setObjectName("fieldLabel")
        self.label.setBuddy(field)
        self.label.setMinimumWidth(SETTINGS_LABEL_WIDTH)
        self.label.setMaximumWidth(SETTINGS_LABEL_WIDTH)
        self.optional = QLabel("optional" if optional else "")
        self.optional.setObjectName("optionalMark")
        self.optional.setVisible(optional)
        label_box = QWidget()
        label_box.setObjectName("formRow")
        label_row = QHBoxLayout(label_box)
        label_row.setContentsMargins(0, 0, 0, 0)
        label_row.setSpacing(6)
        label_row.addWidget(self.label)
        label_row.addWidget(self.optional)
        label_row.addStretch(1)
        self._label_box = label_box
        self.help = QLabel(help_text)
        self.help.setObjectName("fieldHelp")
        self.help.setWordWrap(True)
        self.help.setMaximumWidth(360)
        self.help.setVisible(bool(help_text))
        self.error_icon = QLabel("!")
        self.error_icon.setObjectName("fieldErrorIcon")
        self.error_icon.setVisible(False)
        self.error = QLabel("")
        self.error.setObjectName("fieldError")
        self.error.setWordWrap(True)
        self.error.setMaximumWidth(360)
        self.error.setVisible(False)
        error_row = QWidget()
        error_layout = QHBoxLayout(error_row)
        error_layout.setContentsMargins(0, 0, 0, 0)
        error_layout.setSpacing(4)
        error_layout.addWidget(self.error_icon, 0, Qt.AlignmentFlag.AlignTop)
        error_layout.addWidget(self.error, stretch=1)
        self._error_row = error_row
        self._error_row.setVisible(False)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(4)
        self._grid.setColumnMinimumWidth(0, SETTINGS_LABEL_WIDTH)
        self._grid.setColumnStretch(2, 1)
        self.set_compact(False)
        field.setAccessibleName(_plain(label_text))
        if help_text:
            field.setAccessibleDescription(help_text)

    def set_compact(self, compact: bool) -> None:
        while self._grid.count():
            self._grid.takeAt(0)
        if compact:
            self.label.setMinimumWidth(0)
            self.label.setMaximumWidth(16777215)
            self._grid.addWidget(self._label_box, 0, 0, 1, 2)
            self._grid.addWidget(self.field, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            self._grid.addWidget(self.help, 2, 0, 1, 2)
            self._grid.addWidget(self._error_row, 3, 0, 1, 2)
        else:
            self.label.setMinimumWidth(SETTINGS_LABEL_WIDTH)
            self.label.setMaximumWidth(SETTINGS_LABEL_WIDTH)
            self._grid.addWidget(self._label_box, 0, 0, Qt.AlignmentFlag.AlignVCenter)
            self._grid.addWidget(self.field, 0, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._grid.addWidget(self.help, 1, 1)
            self._grid.addWidget(self._error_row, 2, 1)

    def set_error(self, message: str) -> None:
        self.error.setText(message)
        shown = bool(message)
        self.error.setVisible(shown)
        self.error_icon.setVisible(shown)
        self._error_row.setVisible(shown)
        target = self.field
        if isinstance(target, SuffixedField):
            target = target.edit
        elif not isinstance(target, (QLineEdit, QComboBox, QAbstractSpinBox)):
            inner = target.findChild(QLineEdit) or target.findChild(QComboBox)
            if inner is not None:
                target = inner
        _set_invalid(target, shown)
        if isinstance(self.field, SuffixedField):
            _set_invalid(self.field, shown)
        base = (target.accessibleDescription() or "").split(" Error:")[0]
        target.setAccessibleDescription(f"{base} Error: {message}".strip() if shown else base)

    def set_enabled(self, enabled: bool) -> None:
        self.setEnabled(enabled)
        self.field.setEnabled(enabled)
        self.label.setEnabled(enabled)


class CoordPair(QWidget):
    """Home or target latitude and longitude. Empty means not set."""

    def __init__(self, lat_caption: str, lon_caption: str) -> None:
        super().__init__()
        self.setObjectName("formRow")
        self.lat_label = QLabel(lat_caption)
        self.lon_label = QLabel(lon_caption)
        for label in (self.lat_label, self.lon_label):
            label.setObjectName("fieldLabel")
            label.setMinimumWidth(SETTINGS_LABEL_WIDTH)
            label.setMaximumWidth(SETTINGS_LABEL_WIDTH)
        self.lat_field = SuffixedField("°", _WIDTHS["S"])
        self.lon_field = SuffixedField("°", _WIDTHS["S"])
        self.lat = self.lat_field.edit
        self.lon = self.lon_field.edit
        for edit, lo, hi in ((self.lat, -90.0, 90.0), (self.lon, -180.0, 180.0)):
            validator = QDoubleValidator(lo, hi, 4, edit)
            validator.setLocale(QLocale.c())
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            edit.setValidator(validator)
            edit.setPlaceholderText("Not set")
        self.lat_label.setBuddy(self.lat)
        self.lon_label.setBuddy(self.lon)
        self.help = QLabel("Decimal degrees. Negative is south or west.")
        self.help.setObjectName("fieldHelp")
        self.help.setWordWrap(True)
        self.help.setMaximumWidth(360)
        self.lat_error = _error_line()
        self.lon_error = _error_line()
        self.pair_error = _error_line()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(4)
        self._grid.setColumnStretch(3, 1)
        self.set_compact(False)
        self.lat.setAccessibleName(_plain(lat_caption))
        self.lon.setAccessibleName(_plain(lon_caption))
        self.lat.setAccessibleDescription(self.help.text())
        self.lon.setAccessibleDescription(self.help.text())

    def set_compact(self, compact: bool) -> None:
        while self._grid.count():
            self._grid.takeAt(0)
        if compact:
            for label in (self.lat_label, self.lon_label):
                label.setMinimumWidth(0)
                label.setMaximumWidth(16777215)
            self.lat_field.set_suffix("° lat")
            self.lon_field.set_suffix("° lon")
            self._grid.addWidget(self.lat_label, 0, 0)
            self._grid.addWidget(self.lon_label, 0, 1)
            self._grid.addWidget(self.lat_field, 1, 0, Qt.AlignmentFlag.AlignLeft)
            self._grid.addWidget(self.lon_field, 1, 1, Qt.AlignmentFlag.AlignLeft)
            self._grid.addWidget(self.lat_error, 2, 0, 1, 2)
            self._grid.addWidget(self.lon_error, 3, 0, 1, 2)
            self._grid.addWidget(self.pair_error, 4, 0, 1, 2)
            self._grid.addWidget(self.help, 5, 0, 1, 2)
        else:
            for label in (self.lat_label, self.lon_label):
                label.setMinimumWidth(SETTINGS_LABEL_WIDTH)
                label.setMaximumWidth(SETTINGS_LABEL_WIDTH)
            self.lat_field.set_suffix("°")
            self.lon_field.set_suffix("°")
            self._grid.setColumnMinimumWidth(0, SETTINGS_LABEL_WIDTH)
            self._grid.addWidget(self.lat_label, 0, 0, Qt.AlignmentFlag.AlignVCenter)
            self._grid.addWidget(self.lat_field, 0, 1, Qt.AlignmentFlag.AlignLeft)
            self._grid.addWidget(self.lat_error, 1, 1)
            self._grid.addWidget(self.lon_label, 2, 0, Qt.AlignmentFlag.AlignVCenter)
            self._grid.addWidget(self.lon_field, 2, 1, Qt.AlignmentFlag.AlignLeft)
            self._grid.addWidget(self.lon_error, 3, 1)
            self._grid.addWidget(self.pair_error, 4, 1)
            self._grid.addWidget(self.help, 5, 1)

    def set_errors(self, lat_message: str, lon_message: str, pair_message: str) -> None:
        _show_error(self.lat_error, lat_message)
        _show_error(self.lon_error, lon_message)
        _show_error(self.pair_error, pair_message)
        _set_invalid(self.lat_field, bool(lat_message or pair_message))
        _set_invalid(self.lon_field, bool(lon_message or pair_message))


def _error_line() -> QWidget:
    icon = QLabel("!")
    icon.setObjectName("fieldErrorIcon")
    text = QLabel("")
    text.setObjectName("fieldError")
    text.setWordWrap(True)
    text.setMaximumWidth(360)
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
    layout.addWidget(text, stretch=1)
    row.setVisible(False)
    row._text = text  # type: ignore[attr-defined]
    return row


def _show_error(row: QWidget, message: str) -> None:
    row._text.setText(message)  # type: ignore[attr-defined]
    row.setVisible(bool(message))


def _plain(label: str) -> str:
    return label.replace("&", "")


def _upper_line(edit: QLineEdit, limit: int = 12) -> None:
    edit.setMaxLength(limit)

    def apply(text: str) -> None:
        upper = text.upper()
        if upper == text:
            return
        pos = edit.cursorPosition()
        edit.blockSignals(True)
        edit.setText(upper)
        edit.setCursorPosition(pos)
        edit.blockSignals(False)

    edit.textEdited.connect(apply)


def _fmt_coord(value) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _parse_number(text: str) -> float | None:
    raw = text.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class _UnsavedPrompt(QDialog):
    def __init__(self, parent, count: int, sections: str) -> None:
        super().__init__(parent)
        self.setObjectName("unsavedPrompt")
        self.setWindowTitle("Save changes before closing?")
        self.setModal(True)
        self.setFixedWidth(420)
        self.choice = "keep"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        title = QLabel("Save changes before closing?")
        title.setObjectName("pageTitle")
        body = QLabel(
            f"You changed {count} settings in {sections}. If you don't save, they'll be lost."
        )
        body.setWordWrap(True)
        body.setObjectName("pageDescription")
        layout.addWidget(title)
        layout.addWidget(body)
        row = QHBoxLayout()
        discard = QPushButton("Discard")
        discard.setObjectName("destructiveButton")
        discard.clicked.connect(self._discard)
        keep = QPushButton("Keep editing")
        keep.clicked.connect(self._keep)
        save = QPushButton("Save")
        save.setObjectName("primaryButton")
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(discard)
        row.addStretch(1)
        row.addWidget(keep)
        row.addWidget(save)
        layout.addLayout(row)
        self._save_btn = save

    def _discard(self) -> None:
        self.choice = "discard"
        self.accept()

    def _keep(self) -> None:
        self.choice = "keep"
        self.reject()

    def _save(self) -> None:
        self.choice = "save"
        self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._keep()
            return
        super().keyPressEvent(event)


class _KeyFilter(QObject):
    def __init__(self, dialog: "SettingsDialog") -> None:
        super().__init__(dialog)
        self._dialog = dialog

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress or not self._dialog.isAncestorOf(obj):
            return False
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() in (
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
        ):
            step = -1 if event.key() == Qt.Key.Key_Backtab or (
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ) else 1
            self._dialog._cycle_section(step)
            return True
        return False


class SettingsDialog(QDialog):
    def __init__(self, window, initial_page: str | None = None) -> None:
        super().__init__(window)
        self._window = window
        self._cfg = window.ctrl.cfg
        self._compact = False
        self._closing = False
        self._save_attempted = False
        self._applied_on_accept = False
        self._snapshot: dict = {}
        self.fields: dict = {}
        self.field_labels: dict = {}
        self.band_checks: dict = {}
        self.cont_checks: dict = {}
        self._rows: list[FieldRow] = []
        self._pairs: list[CoordPair] = []
        self._groups: list[tuple[QLabel, QFrame | None]] = []
        self._pages: list[QWidget] = []
        self._summaries: list[QFrame] = []
        self._summary_bodies: list[QLabel] = []
        self._field_section: dict[str, int] = {}
        self._cat_running = False
        self._port_user_edited = False
        self._loading = True
        self.setObjectName("settingsDialog")
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 400)
        self.setStyleSheet(SETTINGS_QSS)
        self._toasts = ToastManager(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget()
        body.setObjectName("settingsBody")
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)

        self.page_list = QListWidget()
        self.page_list.setObjectName("settingsNav")
        self.page_list.setFixedWidth(176)
        self.page_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_list.setItemDelegate(_NavDelegate(self.page_list))
        self.page_list.currentRowChanged.connect(self._on_nav)
        body_row.addWidget(self.page_list)

        pane = QWidget()
        pane.setObjectName("settingsPane")
        pane_col = QVBoxLayout(pane)
        pane_col.setContentsMargins(0, 0, 0, 0)
        pane_col.setSpacing(0)
        self.section_combo = SectionCombo()
        self.section_combo.setObjectName("sectionCombo")
        self.section_combo.setVisible(False)
        combo_wrap = QWidget()
        combo_row = QVBoxLayout(combo_wrap)
        combo_row.setContentsMargins(16, 12, 16, 0)
        combo_row.addWidget(self.section_combo)
        self._combo_wrap = combo_wrap
        self._combo_wrap.setVisible(False)
        pane_col.addWidget(combo_wrap)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("settingsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.stack = QStackedWidget()
        self.stack.setObjectName("settingsStack")
        self.scroll.setWidget(self.stack)
        pane_col.addWidget(self.scroll, stretch=1)
        body_row.addWidget(pane, stretch=1)
        outer.addWidget(body, stretch=1)

        self._build_pages()
        self._build_footer(outer)
        self._load_from_config()
        self._snapshot = self._collect()
        self._loading = False
        self._refresh_dirty()
        self._install_validation_hooks()

        for name in _PAGE_NAMES:
            item = QListWidgetItem(name)
            item.setData(_ROLE_DIRTY, False)
            item.setData(_ROLE_ERRORS, 0)
            item.setSizeHint(QSize(160, 32))
            self.page_list.addItem(item)
            self.section_combo.addItem(name)
        self.section_combo.setItemDelegate(_NavDelegate(self.section_combo))
        self.section_combo.currentIndexChanged.connect(self.page_list.setCurrentRow)

        session = getattr(window, "_settings_session", None) or {}
        start = initial_page or session.get("page") or "Station"
        if start not in _PAGE_NAMES:
            start = "Station"
        self.page_list.setCurrentRow(_PAGE_NAMES.index(start))
        size = session.get("size")
        if isinstance(size, tuple) and len(size) == 2:
            self.resize(int(size[0]), int(size[1]))
        else:
            self.resize(760, 560)
        fit_to_screen(self, 520, 400)
        self._apply_compact(self.width() < _COMPACT_ENTER)

        self._keys = _KeyFilter(self)
        self._app_filter_host = window
        window.window().installEventFilter(self._keys) if False else None
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._keys)

        self._cat_clock = QTimer(self)
        self._cat_clock.setInterval(200)
        self._cat_clock.timeout.connect(self._tick_cat)
        self._cat_started = 0.0
        self._applied_timer = QTimer(self)
        self._applied_timer.setSingleShot(True)
        self._applied_timer.timeout.connect(self._refresh_dirty)
        # Give the footer buttons their real size before the dialog is shown.
        # Fit checks read geometry immediately, and an unlaid-out button still
        # reports Qt's 640x480 default, which fails the "Save is on screen" test.
        for button in self._footer.findChildren(QPushButton):
            button.resize(button.sizeHint())
        self._footer.layout().activate()
        self.layout().activate()
        QTimer.singleShot(0, self._focus_first)
        QTimer.singleShot(0, self._start_port_scan)

    # --- construction -------------------------------------------------------

    def _build_pages(self) -> None:
        cfg = self._cfg
        self._add_station(cfg)
        self._add_rig(cfg)
        self._add_dx(cfg)
        self._add_map(cfg)
        self._add_services(cfg)

    def _new_page(self, name: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(0)
        title = QLabel(name)
        title.setObjectName("pageTitle")
        desc = QLabel(PAGE_DESCRIPTIONS[name])
        desc.setObjectName("pageDescription")
        desc.setWordWrap(True)
        desc.setMaximumWidth(520)
        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(desc)
        layout.addSpacing(12)
        summary = QFrame()
        summary.setObjectName("errorSummary")
        summary.setVisible(False)
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(12, 8, 12, 8)
        summary_layout.setSpacing(2)
        summary_title = QLabel("")
        summary_title.setObjectName("summaryTitle")
        summary_title.setWordWrap(True)
        summary_body = QLabel("")
        summary_body.setWordWrap(True)
        summary_body.setTextFormat(Qt.TextFormat.RichText)
        summary_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        summary_body.linkActivated.connect(self._focus_field_key)
        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(summary_body)
        layout.addWidget(summary)
        self._summaries.append(summary)
        self._summary_bodies.append(summary_body)
        summary._title = summary_title  # type: ignore[attr-defined]
        self._pages.append(page)
        self.stack.addWidget(page)
        return page, layout

    def _add_group(self, layout: QVBoxLayout, title: str, first: bool) -> None:
        if not first:
            layout.addSpacing(16)
            rule = QFrame()
            rule.setObjectName("groupRule")
            layout.addWidget(rule)
            layout.addSpacing(16)
            self._groups.append((None, rule))
        else:
            layout.addSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("groupTitle")
        layout.addWidget(heading)
        layout.addSpacing(10)
        self._groups.append((heading, None))

    def _add_row(self, layout: QVBoxLayout, key: str, section: int, row: FieldRow) -> None:
        layout.addWidget(row)
        layout.addSpacing(8)
        self._rows.append(row)
        self.fields[key] = row.field
        self.field_labels[key] = row.label
        self._field_section[key] = section

    def _add_station(self, cfg) -> None:
        _page, layout = self._new_page("Station")
        self._add_group(layout, "Identity", True)
        call = QLineEdit()
        call.setFixedWidth(_WIDTHS["S"])
        call.setPlaceholderText("e.g. G4ABC")
        _upper_line(call)
        row = FieldRow("&My callsign", call, optional=True)
        self._add_row(layout, "spots_callsign", 0, row)
        self._add_group(layout, "Home location", False)
        pair = CoordPair("Home &latitude", "Home l&ongitude")
        layout.addWidget(pair)
        layout.addSpacing(8)
        self._pairs.append(pair)
        self.fields["home_lat"] = pair.lat
        self.fields["home_lon"] = pair.lon
        self.field_labels["home_lat"] = pair.lat_label
        self.field_labels["home_lon"] = pair.lon_label
        self._field_section["home_lat"] = 0
        self._field_section["home_lon"] = 0
        self._home_pair = pair
        ip = QCheckBox("Look up my location from my &IP")
        ip_row = FieldRow("", ip, "Sends your IP address to ipinfo.io to estimate your location.")
        ip_row.label.setText("")
        ip_row.label.setBuddy(ip)
        ip_row.optional.setVisible(False)
        self._add_row(layout, "ip_geolocation_enabled", 0, ip_row)
        layout.addStretch(1)

    def _add_rig(self, cfg) -> None:
        _page, layout = self._new_page("Rig")
        self._add_group(layout, "Connection", True)
        control = SegmentedChoice([
            ("Serial CAT", "serial"),
            ("OmniRig", "omnirig"),
        ])
        row = FieldRow(
            "&Rig control",
            control,
            "Serial CAT talks to the radio directly. OmniRig uses OmniRig's own setup.",
        )
        self._add_row(layout, "rig_control", 1, row)
        control.on_change(self._on_rig_control)

        from orbitrx.ui.rig_wizard import _port_label
        self._port_label = _port_label
        port = QComboBox()
        port.setEditable(True)
        port.setFixedWidth(_WIDTHS["L"])
        port.activated.connect(lambda _i: self._mark_port_edited())
        port.editTextChanged.connect(lambda _t: self._mark_port_edited())
        port_line = QWidget()
        port_line.setFixedWidth(_WIDTHS["L"] + 36)
        port_row = QHBoxLayout(port_line)
        port_row.setContentsMargins(0, 0, 0, 0)
        port_row.setSpacing(8)
        port_row.addWidget(port)
        rescan = QToolButton()
        rescan.setObjectName("iconButton")
        rescan.setText("↻")
        rescan.setToolTip("Scan serial ports again")
        rescan.setAccessibleName("Scan serial ports again")
        rescan.clicked.connect(self._start_port_scan)
        port_row.addWidget(rescan)
        self._rescan_btn = rescan
        self._scan_label = QLabel("")
        self._scan_label.setObjectName("fieldHelp")
        port_field = FieldRow("Serial &port", port_line, "")
        # The combo, not the wrapper, is what tests and apply read.
        self._rows.append(port_field)
        layout.addWidget(port_field)
        layout.addWidget(self._scan_label)
        layout.addSpacing(8)
        self.fields["cat_port"] = port
        self.field_labels["cat_port"] = port_field.label
        self._field_section["cat_port"] = 1
        port_field.label.setBuddy(port)
        self._port_row = port_field

        baud = QComboBox()
        baud.setFixedWidth(_WIDTHS["S"])
        for rate in ("4800", "9600", "19200", "38400", "115200"):
            baud.addItem(rate, int(rate))
        self._add_row(layout, "cat_baud", 1, FieldRow("&Baud rate", baud))

        profile = QComboBox()
        profile.setFixedWidth(_WIDTHS["M"])
        for key in ("icom", "kenwood", "yaesu"):
            profile.addItem(RIG_PROFILE_LABELS.get(key, key), key)
        self._add_row(layout, "cat_rig_profile", 1, FieldRow("Rig p&rofile", profile))

        self._add_group(layout, "Test connection", False)
        self._cat_runner = CatTestRunner(self)
        self._port_task = BackgroundTask(self)
        self._qrz_task = BackgroundTask(self)
        buttons = QWidget()
        button_row = QHBoxLayout(buttons)
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        self.test_cat_btn = QPushButton("Test CAT")
        self.test_cat_cancel_btn = QPushButton("Cancel")
        self.test_cat_cancel_btn.setVisible(False)
        self.test_cat_btn.clicked.connect(self._do_test_cat)
        self.test_cat_cancel_btn.clicked.connect(self._cat_runner.cancel)
        button_row.addWidget(self.test_cat_btn)
        button_row.addWidget(self.test_cat_cancel_btn)
        button_row.addStretch(1)
        test_row = FieldRow("", buttons, "Asks the radio for its frequency. It will not change the dial.")
        test_row.label.setText("")
        layout.addWidget(test_row)
        layout.addSpacing(8)
        self._rows.append(test_row)

        card = QFrame()
        card.setObjectName("testResult")
        card.setFixedWidth(360)
        card.setMinimumHeight(56)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(2)
        title_row = QHBoxLayout()
        self._cat_icon = QLabel()
        self._cat_icon.setFixedSize(18, 18)
        self._cat_title = QLabel()
        self._cat_title.setObjectName("resultTitle")
        self._cat_title.setTextFormat(Qt.TextFormat.RichText)
        title_row.addWidget(self._cat_icon)
        title_row.addWidget(self._cat_title, stretch=1)
        self.test_cat_result = QLabel("Not tested yet")
        self.test_cat_result.setObjectName("resultDetail")
        self.test_cat_result.setWordWrap(True)
        self._cat_message = QLabel("")
        self._cat_message.setObjectName("appMessage")
        self._cat_message.setVisible(False)
        self._cat_progress = QProgressBar()
        self._cat_progress.setObjectName("catProgress")
        self._cat_progress.setTextVisible(False)
        self._cat_progress.setRange(0, 5000)
        self._cat_progress.setValue(0)
        card_layout.addLayout(title_row)
        card_layout.addWidget(self.test_cat_result)
        card_layout.addWidget(self._cat_message)
        card_layout.addWidget(self._cat_progress)
        hold = QWidget()
        hold_row = QHBoxLayout(hold)
        hold_row.setContentsMargins(SETTINGS_LABEL_WIDTH + 12, 0, 0, 0)
        hold_row.addWidget(card)
        hold_row.addStretch(1)
        self._cat_hold = hold
        layout.addWidget(hold)
        self._cat_card = card
        self._show_cat("idle", "Not tested yet", "Asks the radio for its frequency. It will not change the dial.")
        layout.addStretch(1)

    def _add_dx(self, cfg) -> None:
        from orbitrx.ui.qt_app import CONTINENT_OPTS, _ReflowGrid

        _page, layout = self._new_page("DX cluster")
        self._add_group(layout, "Cluster login", True)
        cluster = QLineEdit()
        cluster.setFixedWidth(_WIDTHS["S"])
        _upper_line(cluster)
        self._add_row(layout, "dx_cluster_callsign", 2, FieldRow("&Cluster callsign", cluster, optional=True))
        self._add_group(layout, "Target station", False)
        target = QLineEdit()
        target.setFixedWidth(_WIDTHS["S"])
        _upper_line(target)
        self._add_row(layout, "target_dx_callsign", 2, FieldRow("&Target DX callsign", target, optional=True))
        pair = CoordPair("Target &latitude", "Target l&ongitude")
        layout.addWidget(pair)
        layout.addSpacing(8)
        self._pairs.append(pair)
        self.fields["target_dx_lat"] = pair.lat
        self.fields["target_dx_lon"] = pair.lon
        self.field_labels["target_dx_lat"] = pair.lat_label
        self.field_labels["target_dx_lon"] = pair.lon_label
        self._field_section["target_dx_lat"] = 2
        self._field_section["target_dx_lon"] = 2
        self._target_pair = pair

        self._add_group(layout, "Filters", False)
        help_filters = QLabel("None selected shows all.")
        help_filters.setObjectName("fieldHelp")
        help_filters.setWordWrap(True)
        layout.addWidget(help_filters)
        layout.addSpacing(6)
        band_label = QLabel("Bands")
        band_label.setObjectName("fieldLabel")
        layout.addWidget(band_label)
        layout.addSpacing(4)
        current_bands = {float(v) for v in (cfg.get("dx_filter_bands_mhz") or [])}
        chips = []
        for name, meta in HF_BANDS.items():
            chip = QToolButton()
            chip.setObjectName("chip")
            chip.setText(name)
            chip.setCheckable(True)
            chip.setChecked(float(meta["freq"]) in current_bands)
            chip.setToolTip(f"{name} ({meta['freq']} MHz)")
            chip.setAccessibleName(name)
            self.band_checks[meta["freq"]] = chip
            chips.append(chip)
            chip.toggled.connect(lambda _c: self._on_edited())
        layout.addWidget(_ReflowGrid(chips, min_item_width=44, min_cols=3, max_cols=6, spacing=6))
        layout.addSpacing(10)
        cont_label = QLabel("Continents")
        cont_label.setObjectName("fieldLabel")
        layout.addWidget(cont_label)
        layout.addSpacing(4)
        current_cont = set(cfg.get("dx_filter_continents") or [])
        cont_chips = []
        for code, full in CONTINENT_OPTS:
            chip = QToolButton()
            chip.setObjectName("chip")
            chip.setText(code)
            chip.setCheckable(True)
            chip.setChecked(code in current_cont)
            chip.setToolTip(full)
            chip.setAccessibleName(full)
            self.cont_checks[code] = chip
            cont_chips.append(chip)
            chip.toggled.connect(lambda _c: self._on_edited())
        layout.addWidget(_ReflowGrid(cont_chips, min_item_width=44, min_cols=3, max_cols=6, spacing=6))
        layout.addStretch(1)

    def _add_map(self, cfg) -> None:
        _page, layout = self._new_page("Map & spots")
        self._add_group(layout, "Live spots", True)
        mode = QComboBox()
        mode.setFixedWidth(_WIDTHS["S"])
        mode.addItems(["FT8", "FT4", "WSPR"])
        self._add_row(layout, "spots_mode", 3, FieldRow("&Mode", mode))
        poll = QSpinBox()
        poll.setFixedWidth(_WIDTHS["S"])
        poll.setRange(1, 99999)
        poll.setSuffix(" s")
        poll.setSingleStep(60)
        poll.setMinimumHeight(30)
        self._add_row(
            layout,
            "pskreporter_poll_seconds",
            3,
            FieldRow("&Poll interval", poll, "PSKReporter allows one poll every 5 minutes or longer."),
        )
        layout.addStretch(1)

    def _add_services(self, cfg) -> None:
        _page, layout = self._new_page("Services")
        self._add_group(layout, "QRZ", True)
        key = QLineEdit()
        key.setFixedWidth(_WIDTHS["M"])
        key.setEchoMode(QLineEdit.EchoMode.Password)
        key.setPlaceholderText("API key")
        show = key.addAction(self._window._eye_icon(crossed=True), QLineEdit.ActionPosition.TrailingPosition)
        show.setCheckable(True)

        def toggle(checked: bool) -> None:
            key.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
            show.setIcon(self._window._eye_icon(crossed=not checked))

        show.toggled.connect(toggle)
        row_host = QWidget()
        row_host.setFixedWidth(_WIDTHS["M"] + 96)
        row_layout = QHBoxLayout(row_host)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(key)
        self.test_qrz_btn = QPushButton("Test QRZ")
        self.test_qrz_btn.clicked.connect(self._do_qrz_test)
        self.test_qrz_cancel_btn = QPushButton("Cancel")
        self.test_qrz_cancel_btn.setVisible(False)
        self.test_qrz_cancel_btn.clicked.connect(self._qrz_task.cancel)
        row_layout.addWidget(self.test_qrz_btn)
        row_layout.addWidget(self.test_qrz_cancel_btn)
        qrz_row = FieldRow("&QRZ API key", row_host, optional=True)
        qrz_row.label.setBuddy(key)
        layout.addWidget(qrz_row)
        layout.addSpacing(8)
        self._rows.append(qrz_row)
        self.fields["qrz_api_key"] = key
        self.field_labels["qrz_api_key"] = qrz_row.label
        self._field_section["qrz_api_key"] = 4
        self._qrz_result = QLabel("")
        self._qrz_result.setObjectName("resultDetail")
        self._qrz_result.setWordWrap(True)
        self._qrz_result.setMaximumWidth(360)
        qrz_hold = QWidget()
        qrz_hold_row = QHBoxLayout(qrz_hold)
        qrz_hold_row.setContentsMargins(SETTINGS_LABEL_WIDTH + 12, 0, 0, 0)
        qrz_hold_row.addWidget(self._qrz_result)
        qrz_hold_row.addStretch(1)
        layout.addWidget(qrz_hold)

        self._add_group(layout, "Space weather", False)
        refresh = QSpinBox()
        refresh.setFixedWidth(_WIDTHS["S"])
        refresh.setRange(1, 99999)
        refresh.setSuffix(" s")
        refresh.setMinimumHeight(30)
        self._add_row(
            layout,
            "refresh_interval_seconds",
            4,
            FieldRow("Space &weather refresh", refresh, "10 to 3600 s."),
        )
        layout.addStretch(1)

    def _build_footer(self, outer: QVBoxLayout) -> None:
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        row = QHBoxLayout(footer)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(8)
        self._dirty_label = QLabel("No changes")
        self._dirty_label.setObjectName("dirtyIndicator")
        row.addWidget(self._dirty_label, stretch=1)
        cancel = QPushButton("Cancel")
        apply_btn = QPushButton("Apply")
        save = QPushButton("Save")
        save.setObjectName("primaryButton")
        save.setDefault(True)
        apply_btn.setEnabled(False)
        cancel.clicked.connect(self.reject)
        apply_btn.clicked.connect(self._on_apply)
        save.clicked.connect(self._on_save)
        cancel.setText("&Cancel")
        apply_btn.setText("&Apply")
        save.setText("&Save")
        row.addWidget(cancel)
        row.addWidget(apply_btn)
        row.addWidget(save)
        outer.addWidget(footer)
        self._footer = footer
        self._apply_btn = apply_btn
        self._save_btn = save
        self.buttons = _ButtonBox({
            QDialogButtonBox.StandardButton.Save: save,
            QDialogButtonBox.StandardButton.Cancel: cancel,
            QDialogButtonBox.StandardButton.Apply: apply_btn,
        })

    # --- values -------------------------------------------------------------

    def _load_from_config(self) -> None:
        cfg = self._cfg
        self.fields["spots_callsign"].setText(str(cfg.get("spots_callsign") or ""))
        self._home_pair.lat.setText(_fmt_coord(cfg.get("home_lat")))
        self._home_pair.lon.setText(_fmt_coord(cfg.get("home_lon")))
        self.fields["ip_geolocation_enabled"].setChecked(bool(cfg.get("ip_geolocation_enabled", False)))
        saved_port = str(cfg.get("cat_port") or "")
        port = self.fields["cat_port"]
        port.addItem(saved_port or "Scanning ports…", saved_port or None)
        self.fields["rig_control"].set_value(str(cfg.get("rig_control") or "serial"))
        baud = self.fields["cat_baud"]
        bidx = baud.findData(int(cfg.get("cat_baud", 9600) or 9600))
        if bidx < 0:
            bidx = baud.findText(str(cfg.get("cat_baud", 9600)))
        if bidx >= 0:
            baud.setCurrentIndex(bidx)
        profile = self.fields["cat_rig_profile"]
        pidx = profile.findData(str(cfg.get("cat_rig_profile") or "kenwood"))
        if pidx >= 0:
            profile.setCurrentIndex(pidx)
        self.fields["dx_cluster_callsign"].setText(str(cfg.get("dx_cluster_callsign") or ""))
        self.fields["target_dx_callsign"].setText(str(cfg.get("target_dx_callsign") or ""))
        self._target_pair.lat.setText(_fmt_coord(cfg.get("target_dx_lat")))
        self._target_pair.lon.setText(_fmt_coord(cfg.get("target_dx_lon")))
        mode = self.fields["spots_mode"]
        midx = mode.findText(str(cfg.get("spots_mode") or "FT8"))
        if midx >= 0:
            mode.setCurrentIndex(midx)
        self.fields["pskreporter_poll_seconds"].setValue(int(cfg.get("pskreporter_poll_seconds", 300) or 300))
        self.fields["qrz_api_key"].setText(str(cfg.get("qrz_api_key") or ""))
        self.fields["refresh_interval_seconds"].setValue(int(cfg.get("refresh_interval_seconds", 60) or 60))
        for edit in self.findChildren(QAbstractSpinBox):
            line = edit.lineEdit()
            if line is not None:
                line.setTextMargins(6, 0, 0, 0)
        self._on_rig_control()

    def _mark_port_edited(self) -> None:
        if not self._loading:
            self._port_user_edited = True

    def _port_value(self) -> str:
        combo = self.fields["cat_port"]
        data = combo.currentData()
        if data:
            return str(data).strip()
        text = combo.currentText().strip()
        if " - " in text:
            return text.split(" - ", 1)[0].strip()
        return text

    def _collect(self) -> dict:
        def coord(edit: QLineEdit):
            return _parse_number(edit.text())

        return {
            "spots_callsign": self.fields["spots_callsign"].text().strip().upper(),
            "home_lat": coord(self._home_pair.lat),
            "home_lon": coord(self._home_pair.lon),
            "ip_geolocation_enabled": self.fields["ip_geolocation_enabled"].isChecked(),
            "rig_control": self.fields["rig_control"].currentData() or "serial",
            "cat_port": self._port_value(),
            "cat_baud": int(self.fields["cat_baud"].currentData() or self.fields["cat_baud"].currentText() or 9600),
            "cat_rig_profile": self.fields["cat_rig_profile"].currentData() or "kenwood",
            "dx_cluster_callsign": self.fields["dx_cluster_callsign"].text().strip().upper(),
            "target_dx_callsign": self.fields["target_dx_callsign"].text().strip().upper(),
            "target_dx_lat": coord(self._target_pair.lat),
            "target_dx_lon": coord(self._target_pair.lon),
            "dx_filter_bands_mhz": [freq for freq, chip in self.band_checks.items() if chip.isChecked()],
            "dx_filter_continents": [code for code, chip in self.cont_checks.items() if chip.isChecked()],
            "spots_mode": self.fields["spots_mode"].currentText(),
            "pskreporter_poll_seconds": int(self.fields["pskreporter_poll_seconds"].value()),
            "qrz_api_key": self.fields["qrz_api_key"].text().strip(),
            "refresh_interval_seconds": int(self.fields["refresh_interval_seconds"].value()),
        }

    def collected_settings(self) -> dict:
        return self._collect()

    # --- validation ---------------------------------------------------------

    def _callsign_error(self, text: str) -> str:
        if not text:
            return ""
        if _CALLSIGN_RE.match(text.upper()):
            return ""
        return "Use letters, digits and / only, for example G4ABC."

    def _coord_errors(self, lat_text: str, lon_text: str) -> tuple[str, str, str]:
        lat_msg = lon_msg = pair_msg = ""
        lat_raw = lat_text.strip()
        lon_raw = lon_text.strip()
        lat = _parse_number(lat_raw) if lat_raw else None
        lon = _parse_number(lon_raw) if lon_raw else None
        if lat_raw and lat is None:
            lat_msg = "Latitude must be between -90 and 90."
        elif lat is not None and not -90.0 <= lat <= 90.0:
            lat_msg = "Latitude must be between -90 and 90."
        if lon_raw and lon is None:
            lon_msg = "Longitude must be between -180 and 180."
        elif lon is not None and not -180.0 <= lon <= 180.0:
            lon_msg = "Longitude must be between -180 and 180."
        lat_empty = not lat_raw
        lon_empty = not lon_raw
        if lat_empty != lon_empty and not lat_msg and not lon_msg:
            pair_msg = "Enter both latitude and longitude, or leave both empty."
        return lat_msg, lon_msg, pair_msg

    def _port_error(self, values: dict) -> str:
        if values["rig_control"] != "serial":
            return ""
        port = values["cat_port"]
        if not port or port == "Scanning ports…":
            return "Enter a port like COM3."
        if sys.platform.startswith("win") and not _COM_RE.match(port):
            return "Enter a port like COM3."
        return ""

    def _range_error(self, value: int, lo: int, hi: int, low_message: str, high_message: str) -> str:
        if value < lo:
            return low_message
        if value > hi:
            return high_message
        return ""

    def validate(self) -> list[dict]:
        values = self._collect()
        found: list[dict] = []

        def add(key: str, message: str) -> None:
            if message:
                found.append({"key": key, "section": self._field_section.get(key, 0), "message": message})

        for key in ("spots_callsign", "dx_cluster_callsign", "target_dx_callsign"):
            add(key, self._callsign_error(values[key]))
        lat_msg, lon_msg, pair_msg = self._coord_errors(self._home_pair.lat.text(), self._home_pair.lon.text())
        add("home_lat", lat_msg or pair_msg)
        add("home_lon", lon_msg)
        lat_msg, lon_msg, pair_msg = self._coord_errors(self._target_pair.lat.text(), self._target_pair.lon.text())
        add("target_dx_lat", lat_msg or pair_msg)
        add("target_dx_lon", lon_msg)
        add("cat_port", self._port_error(values))
        add(
            "pskreporter_poll_seconds",
            self._range_error(
                values["pskreporter_poll_seconds"],
                300,
                3600,
                "Minimum 300 s (PSKReporter's 5-minute floor).",
                "Maximum 3600 s.",
            ),
        )
        add(
            "refresh_interval_seconds",
            self._range_error(
                values["refresh_interval_seconds"],
                10,
                3600,
                "Between 10 and 3600 s.",
                "Between 10 and 3600 s.",
            ),
        )
        return found

    def _apply_inline_errors(self, errors: list[dict]) -> None:
        by_key: dict[str, list[str]] = {}
        for item in errors:
            by_key.setdefault(item["key"], []).append(item["message"])
        label_key = {id(label): key for key, label in self.field_labels.items()}
        for row in self._rows:
            key = label_key.get(id(row.label))
            if key is None or key in ("home_lat", "home_lon", "target_dx_lat", "target_dx_lon"):
                continue
            row.set_error(" ".join(by_key.get(key, [])))
        self._paint_pair(self._home_pair, "home_lat", "home_lon", by_key)
        self._paint_pair(self._target_pair, "target_dx_lat", "target_dx_lon", by_key)

    def _paint_pair(self, pair: CoordPair, lat_key: str, lon_key: str, by_key: dict) -> None:
        lat_msgs = by_key.get(lat_key, [])
        lon_msgs = by_key.get(lon_key, [])
        pair_msgs = [m for m in lat_msgs if m.startswith("Enter both")]
        lat_only = [m for m in lat_msgs if m not in pair_msgs]
        pair.set_errors(" ".join(lat_only), " ".join(lon_msgs), " ".join(pair_msgs))

    def _install_validation_hooks(self) -> None:
        watched = [
            self.fields["spots_callsign"],
            self.fields["dx_cluster_callsign"],
            self.fields["target_dx_callsign"],
            self._home_pair.lat,
            self._home_pair.lon,
            self._target_pair.lat,
            self._target_pair.lon,
            self.fields["cat_port"],
            self.fields["pskreporter_poll_seconds"],
            self.fields["refresh_interval_seconds"],
        ]
        for widget in watched:
            if isinstance(widget, QLineEdit):
                widget.editingFinished.connect(self._validate_quietly)
                widget.textChanged.connect(self._clear_if_fixed)
            elif isinstance(widget, QComboBox):
                widget.editTextChanged.connect(self._on_edited)
                widget.currentIndexChanged.connect(self._on_edited)
            elif isinstance(widget, QSpinBox):
                widget.editingFinished.connect(self._validate_quietly)
                widget.valueChanged.connect(self._on_edited)
        self.fields["ip_geolocation_enabled"].toggled.connect(lambda _c: self._on_edited())
        self.fields["cat_baud"].currentIndexChanged.connect(lambda _i: self._on_edited())
        self.fields["cat_rig_profile"].currentIndexChanged.connect(lambda _i: self._on_edited())
        self.fields["spots_mode"].currentIndexChanged.connect(lambda _i: self._on_edited())
        self.fields["qrz_api_key"].textChanged.connect(lambda _t: self._on_edited())

    def _on_edited(self, *_args) -> None:
        self._refresh_dirty()
        if self._save_attempted:
            self._publish_errors(self.validate())

    def _validate_quietly(self) -> None:
        errors = self.validate()
        self._apply_inline_errors(errors)
        self._refresh_nav_marks(errors)
        if self._save_attempted:
            self._publish_summary(errors)

    def _clear_if_fixed(self, *_args) -> None:
        self._refresh_dirty()
        # Only re-check fields that already show an error, so typing stays quiet.
        if any(row.error.isVisible() for row in self._rows) or self._home_pair.lat_error.isVisible() or self._save_attempted:
            errors = self.validate()
            self._apply_inline_errors(errors)
            self._refresh_nav_marks(errors)
            if self._save_attempted:
                self._publish_summary(errors)

    def _publish_errors(self, errors: list[dict]) -> None:
        self._apply_inline_errors(errors)
        self._refresh_nav_marks(errors)
        self._publish_summary(errors)

    def _publish_summary(self, errors: list[dict]) -> None:
        count = len(errors)
        if not self._save_attempted or count == 0:
            for summary in self._summaries:
                summary.setVisible(False)
            return
        title = f"{count} settings need fixing before you can save"
        links = []
        for item in errors:
            label = _plain(self.field_labels[item["key"]].text()) or item["key"]
            links.append(f'<a href="{item["key"]}">{label}</a>: {item["message"]}')
        html = "<br>".join(links)
        for summary, body in zip(self._summaries, self._summary_bodies):
            summary._title.setText(title)  # type: ignore[attr-defined]
            body.setText(html)
            summary.setVisible(True)

    def _refresh_nav_marks(self, errors: list[dict] | None = None) -> None:
        if self.page_list.count() < len(_PAGE_NAMES):
            return
        if errors is None:
            errors = self.validate() if self._save_attempted else []
        counts = [0] * len(_PAGE_NAMES)
        for item in errors:
            counts[item["section"]] += 1
        dirty_sections = self._dirty_sections()
        for i, name in enumerate(_PAGE_NAMES):
            list_item = self.page_list.item(i)
            list_item.setData(_ROLE_DIRTY, name in dirty_sections)
            list_item.setData(_ROLE_ERRORS, counts[i])
            self.section_combo.setItemData(i, name in dirty_sections, _ROLE_DIRTY)
            self.section_combo.setItemData(i, counts[i], _ROLE_ERRORS)
        self.page_list.viewport().update()
        self.section_combo.update()

    def _focus_field_key(self, key: str) -> None:
        section = self._field_section.get(key, 0)
        self.page_list.setCurrentRow(section)
        widget = self.fields.get(key)
        if isinstance(widget, QWidget):
            target = widget.edit if isinstance(widget, SuffixedField) else widget
            if isinstance(target, QWidget) and not target.isVisible():
                # Wrapped rows (port, QRZ) store the inner editor.
                target = self._editor(key)
            target.setFocus()

    def _editor(self, key: str) -> QWidget:
        widget = self.fields[key]
        if isinstance(widget, SuffixedField):
            return widget.edit
        if isinstance(widget, QLineEdit):
            return widget
        return widget

    # --- dirty --------------------------------------------------------------

    def _dirty_keys(self) -> list[str]:
        current = self._collect()
        return [key for key, value in current.items() if value != self._snapshot.get(key)]

    def _dirty_sections(self) -> list[str]:
        names = []
        for key in self._dirty_keys():
            section = _PAGE_NAMES[self._field_section.get(key, 0)]
            if section not in names:
                names.append(section)
        return names

    def _is_dirty(self) -> bool:
        return bool(self._dirty_keys())

    def _refresh_dirty(self) -> None:
        keys = self._dirty_keys()
        self._apply_btn.setEnabled(bool(keys))
        if not keys:
            self._dirty_label.setText("No changes")
        else:
            sections = ", ".join(self._dirty_sections())
            noun = "setting" if len(keys) == 1 else "settings"
            if self.width() < 420:
                self._dirty_label.setText("●")
            else:
                self._dirty_label.setText(f"● Unsaved changes  ·  {len(keys)} {noun} in {sections}")
            self._dirty_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        if not keys:
            self._dirty_label.setStyleSheet("")
        self._refresh_nav_marks()

    def _show_applied(self) -> None:
        self._dirty_label.setText("Applied")
        self._dirty_label.setStyleSheet(f"color: {GOOD};")
        self._applied_timer.start(2000)

    # --- save / close -------------------------------------------------------

    def _on_apply(self) -> None:
        if not self._commit(close=False):
            return
        self._show_applied()

    def _on_save(self) -> None:
        self._commit(close=True)

    def _commit(self, close: bool) -> bool:
        if close and not self._is_dirty():
            self._applied_on_accept = True
            self.accept()
            return True
        self._save_attempted = True
        errors = self.validate()
        self._publish_errors(errors)
        if errors:
            first = errors[0]
            self.page_list.setCurrentRow(first["section"])
            self._editor(first["key"]).setFocus()
            text = f"{len(errors)} settings need fixing before you can save"
            _announce(self, text)
            self._toasts.show_toast(text, kind="error")
            return False
        self._window._apply_settings_dialog(self)
        self._snapshot = self._collect()
        self._save_attempted = False
        self._publish_errors([])
        self._refresh_dirty()
        _announce(self, "Settings saved")
        if close:
            self._applied_on_accept = True
            self.accept()
        return True

    def reject(self) -> None:  # noqa: N802
        if self._closing:
            super().reject()
            return
        if self._is_dirty():
            keys = self._dirty_keys()
            prompt = _UnsavedPrompt(self, len(keys), ", ".join(self._dirty_sections()))
            prompt.exec()
            if prompt.choice == "keep":
                return
            if prompt.choice == "save":
                self._on_save()
                return
        self._remember_session()
        self._closing = True
        super().reject()

    def accept(self) -> None:  # noqa: N802
        self._remember_session()
        super().accept()

    def _remember_session(self) -> None:
        row = self.page_list.currentRow()
        page = _PAGE_NAMES[row] if 0 <= row < len(_PAGE_NAMES) else "Station"
        self._window._settings_session = {"page": page, "size": (self.width(), self.height())}

    def done(self, code: int) -> None:  # noqa: N802
        self._closing = True
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._keys)
        if self._port_task.is_active():
            self._port_task.cancel()
        super().done(code)

    # --- navigation / compact ----------------------------------------------

    def _on_nav(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        if self.section_combo.currentIndex() != row:
            self.section_combo.blockSignals(True)
            self.section_combo.setCurrentIndex(row)
            self.section_combo.blockSignals(False)
        QTimer.singleShot(0, self._focus_first)

    def _cycle_section(self, step: int) -> None:
        count = len(_PAGE_NAMES)
        row = (self.page_list.currentRow() + step) % count
        self.page_list.setCurrentRow(row)

    def _focus_first(self) -> None:
        page = self.stack.currentWidget()
        if page is None:
            return
        for child in page.findChildren(QWidget):
            if child.focusPolicy() != Qt.FocusPolicy.NoFocus and child.isEnabled() and child.isVisible():
                if isinstance(child, (QLineEdit, QComboBox, QSpinBox, QCheckBox, QToolButton)):
                    child.setFocus()
                    return

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = self.width()
        if self._compact:
            want = width < _COMPACT_LEAVE
        else:
            want = width < _COMPACT_ENTER
        if want != self._compact:
            self._apply_compact(want)
        if self._is_dirty():
            self._refresh_dirty()

    def _apply_compact(self, compact: bool) -> None:
        self._compact = compact
        self.page_list.setVisible(not compact)
        self._combo_wrap.setVisible(compact)
        self.section_combo.setVisible(compact)
        for page in self._pages:
            title = page.findChild(QLabel, "pageTitle")
            if title is not None:
                title.setVisible(not compact)
            margin = (16, 12, 16, 16) if compact else (28, 20, 28, 24)
            page.layout().setContentsMargins(*margin)
        for row in self._rows:
            row.set_compact(compact)
        for pair in self._pairs:
            pair.set_compact(compact)
        self._footer.setProperty("compact", True if compact else False)
        _repolish(self._footer)
        if compact:
            self._cat_hold.layout().setContentsMargins(0, 0, 0, 0)
        else:
            self._cat_hold.layout().setContentsMargins(SETTINGS_LABEL_WIDTH + 12, 0, 0, 0)

    def _on_rig_control(self) -> None:
        serial = (self.fields["rig_control"].currentData() or "serial") == "serial"
        for key in ("cat_port", "cat_baud", "cat_rig_profile"):
            label = self.field_labels.get(key)
            field = self.fields.get(key)
            if field is not None:
                field.setEnabled(serial)
            if label is not None:
                label.setEnabled(serial)
        self._rescan_btn.setEnabled(serial and not self._port_task.is_active())
        self._on_edited()

    # --- CAT / QRZ / ports --------------------------------------------------

    def _do_test_cat(self) -> None:
        import orbitrx.ui.qt_app as qt_app

        values = self._collect()
        backend = values["rig_control"]
        if backend == "serial" and not CAT_AVAILABLE:
            self._show_cat("error", "CAT support unavailable", "pyserial not installed")
            return
        if backend == "serial" and not values["cat_port"]:
            self._show_cat("warn", "Choose a serial port first", "No serial ports were found. Plug in the CAT cable, then press rescan.")
            return
        self._cat_running = True
        self.test_cat_btn.setEnabled(False)
        self.test_cat_btn.setText("Testing…")
        self.test_cat_cancel_btn.setVisible(True)
        self._cat_started = time.monotonic()
        self._cat_progress.setValue(0)
        timeout_s = float(qt_app.CAT_TEST_TIMEOUT_S)
        port = values["cat_port"]
        baud = values["cat_baud"]
        self._show_cat("running", f"Testing {port} at {baud} baud… 0 s", "Times out after 5 s.")
        self._cat_clock.start()
        cat = self._window.ctrl.cat
        # Captured here so the worker never reads or writes cfg.data.
        rig_number = int(self._cfg.get("omnirig_rig_number", 1) or 1)

        def operation() -> str:
            return cat.probe(
                port=port,
                baud=baud,
                profile=values["cat_rig_profile"],
                backend=backend,
                timeout=min(4.0, timeout_s),
                rig_number=rig_number,
            )

        self._cat_runner.start(
            cat,
            0.0,
            self._on_cat_done,
            timeout_s=timeout_s,
            operation=operation,
        )

    def _tick_cat(self) -> None:
        if not self._cat_running:
            return
        import orbitrx.ui.qt_app as qt_app

        elapsed = time.monotonic() - self._cat_started
        timeout_s = float(qt_app.CAT_TEST_TIMEOUT_S)
        self._cat_progress.setMaximum(max(1, int(timeout_s * 1000)))
        self._cat_progress.setValue(min(self._cat_progress.maximum(), int(elapsed * 1000)))
        values = self._collect()
        self._cat_title.setText(
            f'Testing {values["cat_port"]} at {values["cat_baud"]} baud… {int(elapsed)} s'
        )

    def _stop_cat_ui(self) -> None:
        self._cat_running = False
        self._cat_clock.stop()
        self.test_cat_btn.setEnabled(True)
        self.test_cat_btn.setText("Test CAT")
        self.test_cat_cancel_btn.setVisible(False)
        self._cat_progress.setValue(0)

    def _on_cat_done(self, kind: str, message) -> None:
        if self._closing:
            return
        self._stop_cat_ui()
        text = str(message)
        if kind == "cancelled":
            self.test_cat_result.setText("Cancelled")
            self._show_cat("warn", "Test cancelled", "Cancelled")
            self.test_cat_result.setText("Cancelled")
            return
        if kind == "timeout":
            self._show_cat("error", "No answer", text or "Timed out waiting for the rig")
            self._window._set_rig_status(False, "test timed out")
            return
        status, detail = parse_probe_result(text)
        self._present_probe(status, detail)

    def _present_probe(self, status: str, detail: str) -> None:
        values = self._collect()
        port = values["cat_port"]
        baud = values["cat_baud"]
        if status == "ok":
            self._show_cat("ok", f"Radio answered on {port}", detail, mono=detail)
            self._window._set_rig_status(True, "answered")
            return
        if status == "timeout":
            self._show_cat("error", "No answer", detail or "Timed out waiting for the rig")
            self._window._set_rig_status(False, "test timed out")
            return
        if status == "wrong_baud":
            self._show_cat("error", f"No valid reply at {baud} baud", "Match Baud rate to the radio's CAT menu.")
            self._window._set_rig_status(False, "test failed")
            return
        if status == "busy":
            self._show_cat("error", f"{port} is in use", "Close other CAT or logging software, then test again.")
            self._window._set_rig_status(False, "test failed")
            return
        if status == "unavailable":
            self._show_cat("error", "CAT support unavailable", detail)
            self._window._set_rig_status(False, "test failed")
            return
        if status == "unverified":
            self._show_cat("warn", "Sent, not verified", detail or "sent, not verified")
            self._window._set_rig_status(False, "not verified")
            return
        self._show_cat("error", "Test failed", detail or "Could not open serial port")
        self._window._set_rig_status(False, "test failed")

    def _show_cat(self, kind: str, title: str, detail: str, mono: str = "") -> None:
        colors = {"ok": GOOD, "error": POOR, "warn": FAIR, "running": ACCENT, "idle": TEXT_TERTIARY}
        color = colors.get(kind, TEXT_PRIMARY)
        self._cat_card.setProperty("kind", kind)
        _repolish(self._cat_card)
        self._cat_icon.setPixmap(_status_dot(color, self))
        safe = title.replace("<", "")
        self._cat_title.setText(f'<span style="color:{color}; font-weight:600">{safe}</span>')
        self.test_cat_result.setText(detail)
        self.test_cat_result.setAccessibleDescription(f"{kind} {title}. {detail}")
        if mono:
            self._cat_message.setText(mono)
            self._cat_message.setVisible(True)
        else:
            self._cat_message.setVisible(False)
        self._cat_progress.setVisible(kind == "running")

    def _start_port_scan(self) -> None:
        if self._port_task.is_active():
            return
        self._rescan_btn.setEnabled(False)
        self._scan_label.setText("Scanning ports…")
        self._scan_label.setVisible(True)
        cat = self._window.ctrl.cat

        def work():
            return list(cat.list_ports_detailed())

        self._port_task.start(work, self._on_ports)

    def _on_ports(self, kind: str, result) -> None:
        if self._closing or kind == "cancelled":
            return
        self._rescan_btn.setEnabled((self.fields["rig_control"].currentData() or "serial") == "serial")
        self._scan_label.setVisible(False)
        if kind != "ok" or not isinstance(result, list):
            return
        saved = self._port_value()
        combo = self.fields["cat_port"]
        combo.blockSignals(True)
        combo.clear()
        ports = result
        if ports:
            for device, desc in ports:
                combo.addItem(self._port_label(device, desc), device)
            idx = combo.findData(saved)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            fallback = saved or ("COM3" if sys.platform.startswith("win") else "/dev/ttyUSB0")
            combo.addItem(fallback, fallback)
            combo.setCurrentIndex(0)
        combo.blockSignals(False)
        # The first automatic scan is part of loading the dialog. Picking a
        # live port in place of a saved one that is not plugged in should not
        # count as an edit the user made, or closing the dialog would prompt.
        if not self._port_user_edited:
            self._snapshot["cat_port"] = self._port_value()
        self._on_edited()

    def _do_qrz_test(self) -> None:
        from orbitrx.dx import verify_qrz_api

        key = self.fields["qrz_api_key"].text().strip()
        self.test_qrz_btn.setEnabled(False)
        self.test_qrz_btn.setText("Testing…")
        self._qrz_result.setText("Testing QRZ…")
        QTimer.singleShot(1000, self._show_qrz_cancel)

        def work():
            return verify_qrz_api(key)

        self._qrz_task.start(work, self._on_qrz, timeout_s=10.0)

    def _show_qrz_cancel(self) -> None:
        if self._qrz_task.is_active():
            self.test_qrz_cancel_btn.setVisible(True)

    def _on_qrz(self, kind: str, result) -> None:
        if self._closing:
            return
        self.test_qrz_btn.setEnabled(True)
        self.test_qrz_btn.setText("Test QRZ")
        self.test_qrz_cancel_btn.setVisible(False)
        if kind == "cancelled":
            self._qrz_result.setText("Cancelled")
            return
        if kind == "timeout":
            self._qrz_result.setText("Timed out")
            return
        if kind != "ok" or not isinstance(result, tuple):
            self._qrz_result.setText(str(result))
            return
        _ok, message, _pos = result
        self._qrz_result.setText(message)
        _announce(self._qrz_result, message)


def _status_dot(color: str, widget: QWidget) -> QPixmap:
    size = 18
    ratio = widget.devicePixelRatioF() if widget is not None else 1.0
    pix = QPixmap(int(size * ratio), int(size * ratio))
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return pix


def build_settings_dialog(window, initial_page: str | None = None) -> SettingsDialog:
    return SettingsDialog(window, initial_page=initial_page)
