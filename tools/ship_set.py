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
    # opengl32sw.dll (Mesa llvmpipe software OpenGL fallback, ~20 MB): nothing
    # in orbitrx/ or app.py uses OpenGL, QOpenGLWidget, Qt Quick or RHI
    # widgets, so a QOpenGLContext never falls back to software GL here.
    "*opengl32sw.dll",
    # P1 (Risk 161d6e5 screen): the second, runner-sourced OpenSSL build
    # (3.5.9, libcrypto-3-x64/libssl-3-x64) was collected only for Qt's TLS
    # plugin qopensslbackend.dll. OrbitRx makes no QtNetwork/QSsl calls; all
    # HTTPS goes through urllib/_ssl.pyd with CPython's own OpenSSL pair
    # (libcrypto-3.dll/libssl-3.dll). Qt keeps qschannelbackend and
    # qcertonlybackend.
    "*plugins/tls/qopensslbackend.dll",
    "*libcrypto-3-x64.dll",
    "*libssl-3-x64.dll",
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


# P1: the exact OpenSSL DLL set the ship set may contain (CPython 3.12's own
# pair, loaded by _ssl.pyd), and the exact Qt TLS plugin set. Any addition,
# removal or rename fails the CI ship-set gate, so a different OpenSSL build
# can never reach the package unnoticed. Basenames, case-insensitive.
EXPECTED_OPENSSL_DLLS = ("libcrypto-3.dll", "libssl-3.dll")
EXPECTED_TLS_PLUGINS = ("qcertonlybackend.dll", "qschannelbackend.dll")


def _is_openssl_dll(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".dll") and (
        lower.startswith("libcrypto") or lower.startswith("libssl")
        or lower.startswith("openssl") or lower.startswith("ssleay")
        or lower.startswith("libeay")
    )


def openssl_dlls(root: Path) -> list[str]:
    """Relative paths of every OpenSSL-looking DLL under ``root``."""
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*")
        if p.is_file() and _is_openssl_dll(p.name)
    )


def tls_plugins(root: Path) -> list[str]:
    """Basenames of the Qt TLS plugins shipped under ``root``."""
    return sorted(
        p.name for p in root.rglob("*.dll")
        if p.parent.name.lower() == "tls" and p.parent.parent.name.lower() == "plugins"
    )


def check_tls_set(root: Path) -> list[str]:
    """P1 gate: the OpenSSL DLLs and Qt TLS plugins are exactly the expected set."""
    problems: list[str] = []
    found = openssl_dlls(root)
    names = sorted(Path(rel).name.lower() for rel in found)
    expected = sorted(n.lower() for n in EXPECTED_OPENSSL_DLLS)
    if names != expected:
        problems.append(
            "OpenSSL DLL set changed: expected "
            f"{', '.join(EXPECTED_OPENSSL_DLLS)}; found {', '.join(found) or 'none'}"
        )
    plugins = sorted(n.lower() for n in tls_plugins(root))
    expected_plugins = sorted(n.lower() for n in EXPECTED_TLS_PLUGINS)
    if plugins != expected_plugins:
        problems.append(
            "Qt TLS plugin set changed: expected "
            f"{', '.join(EXPECTED_TLS_PLUGINS)}; found {', '.join(plugins) or 'none'}"
        )
    return problems


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
    problems.extend(check_tls_set(root))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", metavar="DIR", type=Path, required=True)
    parser.add_argument(
        "--write-qt-list", metavar="FILE", type=Path, default=None,
        help="Write the shipped Qt6*.dll basenames (one per line) to FILE.",
    )
    parser.add_argument(
        "--write-tls-list", metavar="FILE", type=Path, default=None,
        help="Write the shipped OpenSSL DLLs and Qt TLS plugins to FILE.",
    )
    args = parser.parse_args(argv)
    problems = check_ship_set(args.check)
    if args.write_tls_list is not None:
        lines = [f"openssl {rel}" for rel in openssl_dlls(args.check)]
        lines += [f"tls-plugin {name}" for name in tls_plugins(args.check)]
        args.write_tls_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
