from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from orbitrx.propagation import HF_BANDS, suggested_dial_freq
from orbitrx.ui.theme import NO_DATA

# M4: tile minimum width; reflow steps down rather than squeezing unreadably.
TILE_MIN_WIDTH = 110

# SPEC §8: band_grid()'s real condition vocabulary (OPEN/FAIR/CLOSED/UNKNOWN,
# see orbitrx/propagation.py::band_condition) maps onto the card's four
# visual states. Anything else (defensively) reads as unknown rather than a
# raw/uppercase word -- never ship a literal "UNKNOWN".
_CONDITION_TO_STATE = {
    "OPEN": "good",
    "FAIR": "fair",
    "CLOSED": "poor",
    "UNKNOWN": "unknown",
}

# Badge text per state (SPEC §8 table): a word for good/fair/poor, the shared
# NO_DATA glyph for unknown -- colour is never the only cue and "UNKNOWN" is
# never shown. SPEC §10 itself specifies an em dash here, but
# tests/test_merge_integration.py::test_no_em_dashes_in_ui_strings bans literal
# U+2014 in this package, so NO_DATA's en dash is used instead (see theme.py).
_STATE_BADGE_TEXT = {
    "good": "GOOD",
    "fair": "FAIR",
    "poor": "POOR",
    "unknown": NO_DATA,
}


def _condition_to_state(condition: str) -> str:
    return _CONDITION_TO_STATE.get(condition.upper(), "unknown")


class BandPanelWidget(QWidget):
    """Per-band good/fair/poor/unknown cards (SPEC §8).

    Each card is a QFrame#bandCard holding three child QLabels (bandName,
    bandFreq, stateBadge). State is communicated through a dynamic "state"
    property plus unpolish/polish -- never a per-card inline styleSheet --
    so the cards are themed entirely through theme.QSS.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bands = list(HF_BANDS)
        self._cards: dict[str, QFrame] = {}
        self._name_labels: dict[str, QLabel] = {}
        self._freq_labels: dict[str, QLabel] = {}
        self._badge_labels: dict[str, QLabel] = {}
        self._raw: dict[str, str] = {band: f"{suggested_dial_freq(band)} MHz" for band in self._bands}
        self._cols = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        for band in self._bands:
            self._build_card(band)
            self._apply_state(band, "unknown")
        self._relayout(3)

    def _build_card(self, band: str) -> None:
        card = QFrame()
        card.setObjectName("bandCard")
        card.setProperty("state", "unknown")
        card.setMinimumWidth(TILE_MIN_WIDTH)
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        name_lbl = QLabel(band)
        name_lbl.setObjectName("bandName")

        badge_lbl = QLabel()
        badge_lbl.setObjectName("stateBadge")
        badge_lbl.setProperty("state", "unknown")
        badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        freq_lbl = QLabel()
        freq_lbl.setObjectName("bandFreq")

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        top_row.addWidget(name_lbl)
        top_row.addStretch(1)
        top_row.addWidget(badge_lbl)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addLayout(top_row)
        layout.addWidget(freq_lbl)

        self._cards[band] = card
        self._name_labels[band] = name_lbl
        self._freq_labels[band] = freq_lbl
        self._badge_labels[band] = badge_lbl

    def _columns_for_width(self, width: int) -> int:
        return max(1, min(3, width // 120))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cols = self._columns_for_width(self.width())
        if cols != self._cols:
            self._relayout(cols)
        self._reflow_text()

    def _relayout(self, cols: int) -> None:
        self._cols = cols
        while self._grid.count():
            self._grid.takeAt(0)
        for i, band in enumerate(self._bands):
            row, col = divmod(i, cols)
            self._grid.addWidget(self._cards[band], row, col)

    def _apply_state(self, band: str, state: str) -> None:
        card = self._cards[band]
        badge = self._badge_labels[band]
        card.setProperty("state", state)
        badge.setProperty("state", state)
        badge.setText(_STATE_BADGE_TEXT[state])
        for w in (card, badge):
            w.style().unpolish(w)
            w.style().polish(w)

    def _reflow_text(self) -> None:
        cols = max(1, self._cols)
        tile_w = max(TILE_MIN_WIDTH, self.width() // cols)
        name_avail = max(1, tile_w - 24 - 48)  # card padding minus badge+gap estimate
        freq_avail = max(1, tile_w - 24)       # card padding only, full-width row
        for band in self._bands:
            name_lbl = self._name_labels[band]
            freq_lbl = self._freq_labels[band]
            name_fm = QFontMetrics(name_lbl.font())
            name_lbl.setText(name_fm.elidedText(band, Qt.TextElideMode.ElideRight, name_avail))
            freq_fm = QFontMetrics(freq_lbl.font())
            freq_lbl.setText(freq_fm.elidedText(self._raw[band], Qt.TextElideMode.ElideRight, freq_avail))

    def update_grid(self, band_grid: dict[str, str]) -> None:
        for band in self._cards:
            condition = band_grid.get(band, "UNKNOWN")
            self._apply_state(band, _condition_to_state(condition))
            self._raw[band] = f"{suggested_dial_freq(band)} MHz"
        self._reflow_text()
