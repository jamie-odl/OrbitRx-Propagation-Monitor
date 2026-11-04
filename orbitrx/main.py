"""OrbitRx entry point."""

from __future__ import annotations

import logging
import sys


def main() -> int:
    from orbitrx import __version__
    from orbitrx.logger import setup_logging

    log = setup_logging()
    log.info("OrbitRx Propagation Monitor v%s starting (Python %s)", __version__, sys.version.split()[0])
    try:
        from orbitrx.ui.qt_app import run_qt_app
    except ImportError as exc:
        log.critical("PySide6 is required to run OrbitRx: %s", exc)
        sys.stderr.write("OrbitRx needs PySide6. Install it with: pip install -r requirements.txt\n")
        return 1
    try:
        run_qt_app()
    except Exception:  # last-resort guard so crashes are logged, not silent
        logging.getLogger("orbitrx").exception("Unhandled error in OrbitRx")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
