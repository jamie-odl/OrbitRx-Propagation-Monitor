from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QWidget

from orbitrx.propagation import HF_BANDS, band_chip, suggested_dial_freq
from orbitrx.ui.theme import CHECK_BORDER, FONT_BODY


class BandPanelWidget(QWidget):
    """Per-band OPEN/FAIR/CLOSED cards with color chips and suggested dial freq."""

    # M3: columns step down as the panel narrows (e.g. the side panel vs. the
    # Conditions tab in compact mode), instead of ever needing a horizontal
    # scrollbar to see every band.
    WIDE_COLS_MIN_WIDTH = 330
    MEDIUM_COLS_MIN_WIDTH = 220

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bands = list(HF_BANDS)
        self._cards: dict[str, QLabel] = {}
        self._cols = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        for band in self._bands:
            card = QLabel()
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card.setStyleSheet(
                f"background: #1A2332; border: 1px solid {CHECK_BORDER}; border-radius: 6px; "
                f"padding: 4px; color: #E3F2FD; font-size: {FONT_BODY}px;"
            )
            card.setMinimumWidth(0)
            card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self._cards[band] = card
        self._relayout(3)

    def _columns_for_width(self, width: int) -> int:
        if width >= self.WIDE_COLS_MIN_WIDTH:
            return 3
        if width >= self.MEDIUM_COLS_MIN_WIDTH:
            return 2
        return 1

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cols = self._columns_for_width(self.width())
        if cols != self._cols:
            self._relayout(cols)

    def _relayout(self, cols: int) -> None:
        self._cols = cols
        while self._grid.count():
            self._grid.takeAt(0)
        for i, band in enumerate(self._bands):
            row, col = divmod(i, cols)
            self._grid.addWidget(self._cards[band], row, col)

    def update_grid(self, band_grid: dict[str, str]) -> None:
        for band, lbl in self._cards.items():
            cond = band_grid.get(band, "UNKNOWN")
            chip = band_chip(cond)
            dial = suggested_dial_freq(band)
            lbl.setText(f"{chip} {band}\n{cond}\n{dial} MHz")
