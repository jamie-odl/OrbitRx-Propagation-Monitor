from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget,
)

from orbitrx.propagation import HF_BANDS, suggested_dial_freq
from orbitrx.ui.theme import BAND_CHIP_HEIGHT_COMPACT, FAIR, GOOD, NO_DATA, POOR, UNKNOWN

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

# SPEC §8 "Compact variant": the state word in title case (never "UNKNOWN"),
# and a filled dot in the state's semantic colour -- hollow (grey outline
# glyph) when unknown, since colour is never the only cue.
_STATE_WORD_TEXT = {"good": "Good", "fair": "Fair", "poor": "Poor", "unknown": NO_DATA}
_STATE_DOT_COLOR = {"good": GOOD, "fair": FAIR, "poor": POOR, "unknown": UNKNOWN}
_STATE_DOT_GLYPH = {"good": "●", "fair": "●", "poor": "●", "unknown": "○"}


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
        self._compact_name_labels: dict[str, QLabel] = {}
        self._dot_labels: dict[str, QLabel] = {}
        self._word_labels: dict[str, QLabel] = {}
        self._pages: dict[str, QStackedLayout] = {}
        self._raw: dict[str, str] = {band: f"{suggested_dial_freq(band)} MHz" for band in self._bands}
        self._cols = 0
        self._compact = False
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

        full_page = QWidget()
        full_layout = QVBoxLayout(full_page)
        full_layout.setContentsMargins(12, 10, 12, 10)
        full_layout.setSpacing(4)
        full_layout.addLayout(top_row)
        full_layout.addWidget(freq_lbl)

        # SPEC §8 "Compact variant (683, or a window height under 560)":
        # ~104x30, one row -- name, a state dot, the state word -- with the
        # frequency moved to the chip's tooltip instead of a second text row.
        compact_name_lbl = QLabel(band)
        compact_name_lbl.setObjectName("bandName")
        dot_lbl = QLabel()
        dot_lbl.setObjectName("bandChipDot")
        word_lbl = QLabel()
        word_lbl.setObjectName("bandChipWord")

        compact_page = QWidget()
        compact_layout = QHBoxLayout(compact_page)
        compact_layout.setContentsMargins(10, 0, 10, 0)
        compact_layout.setSpacing(6)
        compact_layout.addWidget(compact_name_lbl)
        compact_layout.addStretch(1)
        compact_layout.addWidget(dot_lbl)
        compact_layout.addWidget(word_lbl)

        pages = QStackedLayout(card)
        pages.setContentsMargins(0, 0, 0, 0)
        pages.addWidget(full_page)
        pages.addWidget(compact_page)
        pages.setCurrentIndex(0)

        self._cards[band] = card
        self._name_labels[band] = name_lbl
        self._freq_labels[band] = freq_lbl
        self._badge_labels[band] = badge_lbl
        self._compact_name_labels[band] = compact_name_lbl
        self._dot_labels[band] = dot_lbl
        self._word_labels[band] = word_lbl
        self._pages[band] = pages

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
        dot = self._dot_labels[band]
        word = self._word_labels[band]
        dot.setText(_STATE_DOT_GLYPH[state])
        dot.setStyleSheet(f"color: {_STATE_DOT_COLOR[state]};")
        word.setText(_STATE_WORD_TEXT[state])
        word.setStyleSheet(f"color: {_STATE_DOT_COLOR[state]};")

    def set_compact(self, compact: bool) -> None:
        """SPEC §8 "Compact variant (683, or a window height under 560)" --
        swaps every card's QStackedLayout page and fixes the card height to
        BAND_CHIP_HEIGHT_COMPACT (~30px); the frequency moves to the card's
        tooltip instead of a second text row."""
        if self._compact == compact:
            return
        self._compact = compact
        for band, card in self._cards.items():
            self._pages[band].setCurrentIndex(1 if compact else 0)
            if compact:
                card.setFixedHeight(BAND_CHIP_HEIGHT_COMPACT)
                card.setToolTip(self._raw[band])
            else:
                card.setMinimumHeight(0)
                card.setMaximumHeight(16777215)
                card.setToolTip("")
        self._reflow_text()

    def is_compact(self) -> bool:
        return self._compact

    def _reflow_text(self) -> None:
        cols = max(1, self._cols)
        tile_w = max(TILE_MIN_WIDTH, self.width() // cols)
        name_avail = max(1, tile_w - 24 - 48)  # card padding minus badge+gap estimate
        freq_avail = max(1, tile_w - 24)       # card padding only, full-width row
        compact_name_avail = max(1, tile_w - 20 - 48)  # compact padding minus dot+word estimate
        for band in self._bands:
            name_lbl = self._name_labels[band]
            freq_lbl = self._freq_labels[band]
            name_fm = QFontMetrics(name_lbl.font())
            name_lbl.setText(name_fm.elidedText(band, Qt.TextElideMode.ElideRight, name_avail))
            freq_fm = QFontMetrics(freq_lbl.font())
            freq_lbl.setText(freq_fm.elidedText(self._raw[band], Qt.TextElideMode.ElideRight, freq_avail))
            compact_name_lbl = self._compact_name_labels[band]
            compact_fm = QFontMetrics(compact_name_lbl.font())
            compact_name_lbl.setText(
                compact_fm.elidedText(band, Qt.TextElideMode.ElideRight, compact_name_avail)
            )

    def update_grid(self, band_grid: dict[str, str]) -> None:
        for band, card in self._cards.items():
            condition = band_grid.get(band, "UNKNOWN")
            self._apply_state(band, _condition_to_state(condition))
            self._raw[band] = f"{suggested_dial_freq(band)} MHz"
            if self._compact:
                card.setToolTip(self._raw[band])
        self._reflow_text()
