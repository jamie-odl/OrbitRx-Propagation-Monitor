from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from orbitrx.propagation import HF_BANDS, suggested_dial_freq
from orbitrx.ui.theme import (
    BAD, BORDER, FONT_CAPTION, MUTED, OK, RADIUS_S, SPACE_1, SPACE_2, SURFACE, TEXT, WARN,
)

# M4: tile minimum width; reflow steps down rather than squeezing unreadably.
TILE_MIN_WIDTH = 110

# P4: the band label's own font size, used both for the inline HTML style and
# for measuring how much of a long band name fits -- eliding against the
# card's default (smaller) font would under-truncate and let the larger
# rendered text overflow the card, since QLabel never clips rich text to its
# own rect.
NAME_FONT_SIZE = 18

_STATUS_COLOR = {
    "OPEN": OK,
    "GOOD": OK,
    "FAIR": WARN,
    "POOR": BAD,
    "CLOSED": BAD,
    "UNKNOWN": MUTED,
}


class BandPanelWidget(QWidget):
    """Per-band OPEN/FAIR/CLOSED cards with status disc + type hierarchy (M4)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bands = list(HF_BANDS)
        self._cards: dict[str, QLabel] = {}
        self._raw: dict[str, tuple[str, str, str]] = {band: ("", "UNKNOWN", "") for band in self._bands}
        self._cols = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        for band in self._bands:
            card = QLabel()
            card.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            card.setTextFormat(Qt.TextFormat.RichText)
            card.setProperty("state", "unknown")
            self._style_card(card, MUTED)
            card.setMinimumWidth(TILE_MIN_WIDTH)
            card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self._cards[band] = card
        self._relayout(3)

    def _style_card(self, card: QLabel, color: str) -> None:
        """P4: a coloured left edge (not just a small dot) is the primary
        state cue; tighter padding + a consistent radius than the old cards."""
        card.setStyleSheet(
            f"background: {SURFACE}; border: 1px solid {BORDER}; "
            f"border-left: 4px solid {color}; border-radius: {RADIUS_S}px; "
            f"padding: {SPACE_2}px {SPACE_2}px {SPACE_2}px {SPACE_1 + SPACE_2}px; color: {TEXT};"
        )

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

    def _reflow_text(self) -> None:
        cols = max(1, self._cols)
        tile_w = max(TILE_MIN_WIDTH, self.width() // cols)
        avail = max(1, tile_w - 28)
        for band, card in self._cards.items():
            name, cond, mhz = self._raw[band]
            if not name:
                continue
            state = cond.upper()
            color = _STATUS_COLOR.get(state, MUTED)
            card.setProperty("state", state.lower())
            self._style_card(card, color)
            fm = QFontMetrics(card.font())
            name_font = QFont(card.font())
            name_font.setPixelSize(NAME_FONT_SIZE)
            name_font.setWeight(QFont.Weight.Bold)
            name_fm = QFontMetrics(name_font)
            name_e = name_fm.elidedText(name, Qt.TextElideMode.ElideRight, avail)
            cond_e = fm.elidedText(cond, Qt.TextElideMode.ElideRight, avail)
            mhz_e = fm.elidedText(mhz, Qt.TextElideMode.ElideRight, avail)
            # P4: a large band label is the primary read; the condition badge
            # and frequency each get their own line below it (not inline next
            # to the band name) so neither ever overflows the card's width --
            # the state colour already reads via the left edge regardless.
            card.setText(
                f'<div style="line-height:1.25">'
                f'<span style="font-size:{NAME_FONT_SIZE}px;font-weight:700;color:{TEXT}">{name_e}</span><br/>'
                f'<span style="font-size:{FONT_CAPTION}px;font-weight:700;letter-spacing:0.06em;'
                f'color:{color}">{cond_e}</span><br/>'
                f'<span style="font-size:{FONT_CAPTION}px;font-weight:400;color:{MUTED}">'
                f'{mhz_e}</span></div>'
            )

    def update_grid(self, band_grid: dict[str, str]) -> None:
        for band in self._cards:
            cond = band_grid.get(band, "UNKNOWN")
            dial = suggested_dial_freq(band)
            self._raw[band] = (band, cond, f"{dial} MHz")
        self._reflow_text()
