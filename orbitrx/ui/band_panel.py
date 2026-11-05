from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from orbitrx.propagation import HF_BANDS, band_chip, suggested_dial_freq
from orbitrx.ui.theme import CARD_STYLE, CARD_TEXT, FONT_BODY

# M1: tile minimum width in logical px; a tile never shrinks below this, so the
# reflow below steps down to fewer columns instead of squeezing tiles unreadably
# thin.
TILE_MIN_WIDTH = 110


class BandPanelWidget(QWidget):
    """Per-band OPEN/FAIR/CLOSED cards with color chips and suggested dial freq."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bands = list(HF_BANDS)
        self._cards: dict[str, QLabel] = {}
        self._raw_lines: dict[str, list[str]] = {band: [] for band in self._bands}
        self._cols = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        for band in self._bands:
            card = QLabel()
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card.setStyleSheet(f"{CARD_STYLE} padding: 4px; color: {CARD_TEXT}; font-size: {FONT_BODY}px;")
            card.setMinimumWidth(TILE_MIN_WIDTH)
            card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self._cards[band] = card
        self._relayout(3)

    def _columns_for_width(self, width: int) -> int:
        # M1: cols = max(1, min(3, panel_width // 120)).
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
        """Elide each line to the tile's current width instead of ever clipping
        it mid-glyph (M1)."""
        cols = max(1, self._cols)
        tile_w = max(TILE_MIN_WIDTH, self.width() // cols)
        avail = max(1, tile_w - 16)  # minus the tile's own padding/border
        for band, card in self._cards.items():
            lines = self._raw_lines[band]
            if not lines:
                continue
            fm = QFontMetrics(card.font())
            elided = [fm.elidedText(line, Qt.TextElideMode.ElideRight, avail) for line in lines]
            card.setText("\n".join(elided))

    def update_grid(self, band_grid: dict[str, str]) -> None:
        for band in self._cards:
            cond = band_grid.get(band, "UNKNOWN")
            chip = band_chip(cond)
            dial = suggested_dial_freq(band)
            self._raw_lines[band] = [f"{chip} {band}", cond, f"{dial} MHz"]
        self._reflow_text()
