from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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

    P5-r4/SPEC §8 "All unknown": when every band is unknown because a weather
    fetch failed with no usable data at all (never the merely-never-fetched
    case, which keeps showing the six unknown cards), the six cards are
    replaced by a single muted strip line of the *same reserved height* --
    see set_all_unknown() -- so the map never jumps.
    """

    retry_requested = Signal()

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
        self._all_unknown = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._stack = QStackedLayout()
        self._stack.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._stack)

        grid_page = QWidget()
        self._grid = QGridLayout(grid_page)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        self._stack.addWidget(grid_page)
        self._strip = self._build_all_unknown_strip()
        self._stack.addWidget(self._strip)
        self._stack.setCurrentIndex(0)

        for band in self._bands:
            self._build_card(band)
            self._apply_state(band, "unknown")
        self._relayout(3)

    def _build_all_unknown_strip(self) -> QWidget:
        # SPEC §8 "All unknown ... container of the *same reserved height*
        # (64px)" is specifically the full-size card height -- set_compact()
        # re-floors this to BAND_CHIP_HEIGHT_COMPACT to match instead, so the
        # strip never reserves more height than the six chips it replaces
        # would have at the current size (that extra height was silently
        # eating into the compact map's own share, see
        # qt_app._apply_map_min_height).
        strip = QFrame()
        strip.setObjectName("bandStrip")
        strip.setFixedHeight(64)
        layout = QHBoxLayout(strip)
        self._strip_layout = layout
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # Explicit setMinimumWidth(1), not the QLabel default of 0: Qt's
        # qSmartMinSize only honours an *explicitly set* QWidget.minimumSize
        # over the (long, uncompressible-text) minimumSizeHint when that
        # explicit size is non-zero -- a bare 0 is indistinguishable from
        # "never set". Without this, this strip's own minimum width (not
        # just its current, visible width) sets a floor on the whole
        # BandPanelWidget via QStackedLayout (which sizes for the largest of
        # all its pages, not just the current one) even while the six-card
        # grid page is the one actually showing -- harmless at this app's
        # normal fonts, but it ballooned past the map column's budget under
        # the wide-font CI metrics tests/test_map_dominant_layout.py and
        # tests/test_map_frame.py pin.
        self._strip_dot_lbl = QLabel("○")
        self._strip_dot_lbl.setStyleSheet(f"color: {UNKNOWN};")
        self._strip_dot_lbl.setMinimumWidth(1)
        layout.addWidget(self._strip_dot_lbl)

        self._strip_text_lbl = QLabel("Band conditions unavailable · last update never")
        self._strip_text_lbl.setObjectName("muted")
        self._strip_text_lbl.setMinimumWidth(1)
        layout.addWidget(self._strip_text_lbl)
        layout.addStretch(1)

        self._strip_retry_lbl = QLabel('<a href="#">Retry</a>')
        self._strip_retry_lbl.linkActivated.connect(lambda _: self.retry_requested.emit())
        self._strip_retry_lbl.setMinimumWidth(1)
        layout.addWidget(self._strip_retry_lbl)

        self._strip_bands_lbl = QLabel(" · ".join(self._bands))
        self._strip_bands_lbl.setObjectName("muted")
        self._strip_bands_lbl.setMinimumWidth(1)
        layout.addWidget(self._strip_bands_lbl)
        return strip

    def set_all_unknown(self, flag: bool, last_update_text: str = "never") -> None:
        """SPEC §10/§8 "All unknown": real driver is qt_app's own fetch-failed
        + never-loaded check (not "every band_grid value happens to be
        UNKNOWN"), so the ordinary never-fetched startup state keeps showing
        six unknown cards and only a genuine no-usable-data failure collapses
        to this strip."""
        self._strip_text_lbl.setText(f"Band conditions unavailable · last update {last_update_text}")
        if flag == self._all_unknown:
            return
        self._all_unknown = flag
        self._stack.setCurrentIndex(1 if flag else 0)

    def set_stale(self, flag: bool) -> None:
        """SPEC §8 "stale": same word, outline badge in its own semantic
        colour, no fill -- a second "stale" property alongside the existing
        good/fair/poor "state" one, so the colour/word themselves never
        change, only the fill."""
        for badge in self._badge_labels.values():
            if badge.property("stale") == flag:
                continue
            badge.setProperty("stale", flag)
            badge.style().unpolish(badge)
            badge.style().polish(badge)

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
        # SPEC §6.2/§8: one row of 6 under the full map column (~944px at
        # 1280x800) -- up from a 3-column cap inherited from when these
        # cards lived in the narrow (~300px) side panel. G10: the compact
        # variant's cards are far narrower (~104x30, SPEC §8 "Compact
        # variant") than the full cards' 120px floor, so the same divisor
        # would wrap 6 chips onto two rows under the ~635px map column a
        # 683-wide window leaves; using the compact card's own floor keeps
        # them on SPEC's single row down to that width.
        min_w = 104 if self._compact else 120
        return max(1, min(6, width // min_w))

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
        # P5-r4: self._grid now lives on grid_page (a child of self._stack),
        # not directly on self the way it did before the all-unknown strip
        # (G12) added a second QStackedLayout page. QGridLayout normally
        # self-invalidates on structural changes like this, which is enough
        # when it's the widget's own top-level layout -- but one level
        # removed behind QStackedLayout, that invalidation only reaches
        # self._stack via a *posted* LayoutRequest event, which needs an
        # actual event-loop turn to land. Explicitly invalidating the stack
        # here makes this synchronous instead, so a parent activate() racing
        # this call (e.g. qt_app._update_compact_mode, which toggles compact
        # mode and reads geometry back with no processEvents() in between)
        # sees the real, already-shrunk size instead of a stale, taller one.
        self._stack.invalidate()
        self.updateGeometry()

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
        self._strip.setFixedHeight(BAND_CHIP_HEIGHT_COMPACT if compact else 64)
        if compact:
            self._strip_layout.setContentsMargins(10, 2, 10, 2)
        else:
            self._strip_layout.setContentsMargins(12, 10, 12, 10)
        # G10: _columns_for_width()'s own floor depends on self._compact, so
        # a toggle here can change the right column count even when the
        # widget's width hasn't -- resizeEvent() alone wouldn't catch that.
        self._relayout(self._columns_for_width(self.width()))
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
