"""Ship-set policy: which Qt binaries this build packages (F1).

Standalone (no PyInstaller import) so it can be unit tested on any platform and
reused by the CI gate (``python tools/ship_set.py --check DIR``). The policy is
empirical: it matches the Windows PE import tables of the shipped onedir at the
590f600 green build (see the task notes). Only Qt6Pdf (via plugins/imageformats/
qpdf.dll), Qt6VirtualKeyboard (via plugins/platforminputcontexts/
qtvirtualkeyboardplugin.dll) and the Qt6Quick/Qml*/OpenGL stack that
Qt6VirtualKeyboard and Qt6Quick alone pulled in are importers of the banned
modules; nothing in orbitrx/ or the kept plugins depends on them.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

# Case-insensitive glob patterns, matched against the destination path of each
# collected binary/data entry (forward slashes). A match anywhere banns the
# file from the ship set.
BANNED_PATTERNS = (
    "*qt6pdf*.dll",
    "*plugins/imageformats/qpdf.dll",
    "*qt6virtualkeyboard*.dll",
    "*plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    "*qt6quick*.dll",
    "*qt6qml*.dll",
    "*qt6opengl*.dll",
    "*qt6webengine*.dll",
    "*qtwebengineprocess*",
    "*qt6webchannel*.dll",
    "*qt6positioning*.dll",
    "*qt6location*.dll",
    "*/qml/*",
    "*qml/*",
    "*qtwebengine_resources*",
    "*qtwebengine*locales*",
)

# Qt libraries this build must keep. Checked by name stem (case-insensitive),
# matched against the basename of each shipped file.
REQUIRED_QT_DLLS = (
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
    "Qt6Network.dll",
    "Qt6Svg.dll",
)


def _dest_name(entry) -> str:
    """PyInstaller TOC entries are (dest_name, src_name, typecode) tuples."""
    return str(entry[0]).replace("\\", "/")


def is_banned(dest_name: str) -> bool:
    name = dest_name.replace("\\", "/").lower()
    return any(fnmatch.fnmatch(name, pattern) for pattern in BANNED_PATTERNS)


def filter_binaries(toc):
    """Drop banned entries from a PyInstaller TOC-like list of tuples.

    ``toc`` is any iterable of ``(dest_name, src_name, typecode)`` tuples (the
    shape of ``Analysis.binaries`` / ``Analysis.datas``). Returns a list with
    the banned entries removed; order and remaining tuples are unchanged.
    """
    return [entry for entry in toc if not is_banned(_dest_name(entry))]


def shipped_qt_dlls(root: Path) -> list[str]:
    """Qt6*.dll basenames actually present under ``root`` (recursive)."""
    return sorted(p.name for p in root.rglob("Qt6*.dll"))


def check_ship_set(root: Path) -> list[str]:
    """Return a list of problems; empty means the ship set is clean."""
    problems: list[str] = []
    if not root.is_dir():
        return [f"not a directory: {root}"]
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if is_banned(rel):
                problems.append(f"banned file present: {rel}")
    present = {p.name for p in root.rglob("*.dll")}
    for required in REQUIRED_QT_DLLS:
        if required not in present:
            problems.append(f"required Qt library missing: {required}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", metavar="DIR", type=Path, required=True)
    parser.add_argument(
        "--write-qt-list", metavar="FILE", type=Path, default=None,
        help="Write the shipped Qt6*.dll basenames (one per line) to FILE.",
    )
    args = parser.parse_args(argv)
    problems = check_ship_set(args.check)
    if args.write_qt_list is not None:
        args.write_qt_list.write_text(
            "\n".join(shipped_qt_dlls(args.check)) + "\n", encoding="utf-8"
        )
    if problems:
        print("ship-set check failed:")
        for item in problems:
            print(f"  {item}")
        return 1
    print(f"ship-set check ok: {args.check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
