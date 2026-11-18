"""Shared off-UI-thread helpers (Phase 1 threading fixes): a queued-delivery
invoker and a CAT-test runner, used by both qt_app.py's Settings dialog and
rig_wizard.py so neither duplicates the busy/cancel/timeout lifecycle."""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Qt, Signal


class UiInvoker(QObject):
    """Runs callables on the Qt GUI thread (worker-thread results are posted
    here, same pattern as qt_app.py's _UiInvoker). Guarded against emitting
    once this invoker's own C++ object has already been torn down -- e.g. its
    parent dialog closed while a worker was still in flight -- which would
    otherwise crash on a QObject that is referenced from Python but already
    deleted on the C++ side."""

    call = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.call.connect(lambda fn: fn(), Qt.ConnectionType.QueuedConnection)

    def wrap(self, fn: Callable) -> Callable:
        def emit(*args):
            import shiboken6
            if not shiboken6.isValid(self):
                return
            self.call.emit(lambda: fn(*args))
        return emit


class CatTestRunner(QObject):
    """Runs CatController.tune() on a background thread so a Test CAT click
    never blocks the UI thread on serial I/O. Delivers exactly one
    on_done(kind, message) call per start(), on the GUI thread, with kind in
    {"ok", "timeout", "cancelled"}. A new start() implicitly cancels any test
    still in flight; cancel()/timeout mark the in-flight worker's eventual
    result stale so it is ignored when it arrives."""

    DEFAULT_TIMEOUT_S = 5.0

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._invoker = UiInvoker(self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._generation = 0
        self._on_done: Callable[[str, str], None] | None = None
        # Exposed so tests can join() the in-flight worker deterministically
        # instead of guessing a sleep duration is longer than tune()'s delay.
        self._thread: threading.Thread | None = None

    def is_active(self) -> bool:
        return self._on_done is not None

    def start(
        self,
        cat,
        freq: float,
        on_done: Callable[[str, str], None],
        timeout_s: float | None = None,
    ) -> None:
        self.cancel()
        self._generation += 1
        gen = self._generation
        self._on_done = on_done
        deliver = self._invoker.wrap(lambda result: self._finish(gen, result))

        def worker() -> None:
            try:
                result = cat.tune(freq, confirm=None)
            except Exception as e:
                result = str(e)
            deliver(result)

        self._thread = threading.Thread(target=worker, daemon=True, name="cat-test")
        self._thread.start()
        self._timer.start(max(1, int((timeout_s or self.DEFAULT_TIMEOUT_S) * 1000)))

    def cancel(self) -> None:
        if self._on_done is None:
            return
        self._generation += 1  # invalidates the in-flight worker's eventual result
        self._timer.stop()
        on_done, self._on_done = self._on_done, None
        on_done("cancelled", "Cancelled")

    def _on_timeout(self) -> None:
        if self._on_done is None:
            return
        self._generation += 1  # invalidates the in-flight worker's eventual result
        on_done, self._on_done = self._on_done, None
        on_done("timeout", "Timed out waiting for the rig")

    def _finish(self, gen: int, result: str) -> None:
        if gen != self._generation or self._on_done is None:
            return  # superseded by cancel(), a timeout, or a newer start()
        self._timer.stop()
        on_done, self._on_done = self._on_done, None
        on_done("ok", result)
