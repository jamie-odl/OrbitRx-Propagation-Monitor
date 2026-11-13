"""F1: the Qt ship-set trim (tools/ship_set.py, OrbitRxMonitor.spec, ci.yml).

Policy is empirical (see the task notes / NOTICE): nothing in orbitrx/ or the
kept plugins imports Qt6Pdf, Qt6VirtualKeyboard, Qt6Quick, any Qt6Qml*, or
Qt6OpenGL (Qt6Quick's only importer), so none of them may reach the ship set.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A realistic TOC sample built from the shipped list in the task notes:
# everything that is actually in the 590f600 green build's _internal/PySide6,
# plus the banned modules that build still needlessly pulled in.
REALISTIC_TOC = [
    ("PySide6/Qt6Core.dll", "x", "BINARY"),
    ("PySide6/Qt6Gui.dll", "x", "BINARY"),
    ("PySide6/Qt6Widgets.dll", "x", "BINARY"),
    ("PySide6/Qt6Network.dll", "x", "BINARY"),
    ("PySide6/Qt6Svg.dll", "x", "BINARY"),
    ("PySide6/Qt6OpenGL.dll", "x", "BINARY"),
    ("PySide6/Qt6Pdf.dll", "x", "BINARY"),
    ("PySide6/Qt6Qml.dll", "x", "BINARY"),
    ("PySide6/Qt6QmlMeta.dll", "x", "BINARY"),
    ("PySide6/Qt6QmlModels.dll", "x", "BINARY"),
    ("PySide6/Qt6QmlWorkerScript.dll", "x", "BINARY"),
    ("PySide6/Qt6Quick.dll", "x", "BINARY"),
    ("PySide6/Qt6VirtualKeyboard.dll", "x", "BINARY"),
    ("opengl32sw.dll", "x", "BINARY"),
    ("pyside6.abi3.dll", "x", "BINARY"),
    ("PySide6/QtCore.pyd", "x", "EXTENSION"),
    ("PySide6/QtGui.pyd", "x", "EXTENSION"),
    ("PySide6/QtNetwork.pyd", "x", "EXTENSION"),
    ("PySide6/QtSvg.pyd", "x", "EXTENSION"),
    ("PySide6/QtWidgets.pyd", "x", "EXTENSION"),
    ("PySide6/plugins/platforms/qwindows.dll", "x", "BINARY"),
    ("PySide6/plugins/imageformats/qsvg.dll", "x", "BINARY"),
    ("PySide6/plugins/imageformats/qpdf.dll", "x", "BINARY"),
    ("PySide6/plugins/iconengines/qsvgicon.dll", "x", "BINARY"),
    ("PySide6/plugins/styles/qmodernwindowsstyle.dll", "x", "BINARY"),
    ("PySide6/plugins/tls/qschannelbackend.dll", "x", "BINARY"),
    ("PySide6/plugins/tls/qopensslbackend.dll", "x", "BINARY"),
    ("PySide6/plugins/tls/qcertonlybackend.dll", "x", "BINARY"),
    ("libcrypto-3.dll", "x", "BINARY"),
    ("libssl-3.dll", "x", "BINARY"),
    ("libcrypto-3-x64.dll", "x", "BINARY"),
    ("libssl-3-x64.dll", "x", "BINARY"),
    ("PySide6/plugins/networkinformation/qnetworklistmanager.dll", "x", "BINARY"),
    ("PySide6/plugins/generic/qtuiotouchplugin.dll", "x", "BINARY"),
    ("PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll", "x", "BINARY"),
    ("PySide6/translations/qtbase_en.qm", "x", "DATA"),
    ("PySide6/qml/QtQuick/qmldir", "x", "DATA"),
]

BANNED_SAMPLE_NAMES = {
    "PySide6/Qt6OpenGL.dll",
    "PySide6/Qt6Pdf.dll",
    "PySide6/Qt6Qml.dll",
    "PySide6/Qt6QmlMeta.dll",
    "PySide6/Qt6QmlModels.dll",
    "PySide6/Qt6QmlWorkerScript.dll",
    "PySide6/Qt6Quick.dll",
    "PySide6/Qt6VirtualKeyboard.dll",
    "PySide6/plugins/imageformats/qpdf.dll",
    "PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    "PySide6/qml/QtQuick/qmldir",
    "opengl32sw.dll",
    # P1: the runner-sourced OpenSSL 3.5.9 pair and Qt's OpenSSL TLS plugin.
    "PySide6/plugins/tls/qopensslbackend.dll",
    "libcrypto-3-x64.dll",
    "libssl-3-x64.dll",
}

KEPT_SAMPLE_NAMES = {
    "PySide6/Qt6Core.dll",
    "PySide6/Qt6Gui.dll",
    "PySide6/Qt6Widgets.dll",
    "PySide6/Qt6Network.dll",
    "PySide6/Qt6Svg.dll",
    "PySide6/plugins/imageformats/qsvg.dll",
    "PySide6/plugins/iconengines/qsvgicon.dll",
    "PySide6/plugins/tls/qschannelbackend.dll",
    "PySide6/plugins/tls/qcertonlybackend.dll",
    "libcrypto-3.dll",
    "libssl-3.dll",
    "PySide6/plugins/platforms/qwindows.dll",
    "PySide6/plugins/networkinformation/qnetworklistmanager.dll",
    "PySide6/plugins/generic/qtuiotouchplugin.dll",
}


def _clean_onedir(tmp_path):
    """A minimal onedir that passes the ship-set gate: the five Qt libraries,
    CPython's OpenSSL pair and the two allowed Qt TLS plugins."""
    root = tmp_path / "OrbitRxMonitor"
    internal = root / "_internal" / "PySide6"
    internal.mkdir(parents=True)
    for name in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll", "Qt6Svg.dll"):
        (internal / name).write_bytes(b"x")
    for name in ("libcrypto-3.dll", "libssl-3.dll"):
        (root / "_internal" / name).write_bytes(b"x")
    tls = internal / "plugins" / "tls"
    tls.mkdir(parents=True)
    for name in ("qschannelbackend.dll", "qcertonlybackend.dll"):
        (tls / name).write_bytes(b"x")
    return root


def test_filter_binaries_drops_every_banned_item_and_keeps_the_rest():
    from tools.ship_set import filter_binaries

    kept = {entry[0] for entry in filter_binaries(REALISTIC_TOC)}
    for banned in BANNED_SAMPLE_NAMES:
        assert banned not in kept, banned
    for keep in KEPT_SAMPLE_NAMES:
        assert keep in kept, keep
    # Nothing was dropped that shouldn't have been, and nothing banned slipped through.
    assert kept == KEPT_SAMPLE_NAMES | {
        "pyside6.abi3.dll", "PySide6/QtCore.pyd", "PySide6/QtGui.pyd",
        "PySide6/QtNetwork.pyd", "PySide6/QtSvg.pyd", "PySide6/QtWidgets.pyd",
        "PySide6/plugins/styles/qmodernwindowsstyle.dll",
        "PySide6/translations/qtbase_en.qm",
    }


def test_filter_binaries_is_case_insensitive_and_preserves_tuple_shape():
    from tools.ship_set import filter_binaries

    toc = [("PySide6\\QT6PDF.DLL", "src", "BINARY"), ("PySide6\\Qt6Core.dll", "src", "BINARY")]
    kept = filter_binaries(toc)
    assert kept == [("PySide6\\Qt6Core.dll", "src", "BINARY")]


def test_check_ship_set_flags_banned_files_and_missing_required_dlls(tmp_path):
    from tools.ship_set import check_ship_set

    root = _clean_onedir(tmp_path)
    internal = root / "_internal" / "PySide6"
    assert check_ship_set(root) == []

    (internal / "Qt6Pdf.dll").write_bytes(b"x")
    problems = check_ship_set(root)
    assert any("Qt6Pdf.dll" in p for p in problems)

    (internal / "Qt6Pdf.dll").unlink()
    (internal / "Qt6Core.dll").unlink()
    problems = check_ship_set(root)
    assert any("Qt6Core.dll" in p for p in problems)


def test_check_ship_set_flags_opengl32sw_dll(tmp_path):
    from tools.ship_set import check_ship_set

    root = _clean_onedir(tmp_path)
    internal = root / "_internal" / "PySide6"
    assert check_ship_set(root) == []

    (root / "_internal" / "opengl32sw.dll").write_bytes(b"x")
    problems = check_ship_set(root)
    assert any("opengl32sw.dll" in p for p in problems)


def test_spec_filters_binaries_and_datas_after_analysis_and_still_excludes_webengine():
    import ast

    text = (ROOT / "OrbitRxMonitor.spec").read_text(encoding="utf-8")
    assert "from tools.ship_set import filter_binaries" in text
    assert "a.binaries = filter_binaries(a.binaries)" in text
    assert "a.datas = filter_binaries(a.datas)" in text
    # The filter call must come after Analysis(...) built a.binaries/a.datas,
    # and before PYZ/COLLECT package them, or it has no effect.
    tree = ast.parse(text)
    analysis_line = next(
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "a"
    )
    filter_lines = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Attribute)
        and n.targets[0].attr in ("binaries", "datas")
    ]
    collect_line = next(
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "coll"
    )
    assert filter_lines, "no a.binaries/a.datas filter assignment found"
    assert all(analysis_line < ln < collect_line for ln in filter_lines)
    excludes_block = text.split("excludes = [")[1].split("]")[0]
    for excluded in ["QtPdf", "QtPdfWidgets", "QtVirtualKeyboard", "QtOpenGL", "QtOpenGLWidgets"]:
        assert f"'PySide6.{excluded}'" in excludes_block
    for excluded in ["QtWebEngineCore", "QtWebEngineWidgets", "QtWebChannel", "QtQml", "QtQuick"]:
        assert f"'PySide6.{excluded}'" in excludes_block


def test_requirements_and_pyproject_drop_the_pyside6_meta_and_addon_wheels():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PySide6_Essentials" in requirements
    assert "PySide6==" not in requirements
    for banned in ("PySide6_Addons", "PySide6-Addons", "PySide6_Pdf", "PySide6-Pdf",
                   "PySide6_WebEngine", "PySide6-WebEngine"):
        assert banned not in requirements
        assert banned not in pyproject
    assert "PySide6_Essentials" in pyproject
    assert "PySide6>=" not in pyproject
    assert 'map = [' not in pyproject
    assert "PySide6-Addons" not in pyproject


def test_ci_has_ship_set_gate_step_and_still_no_ship_set_upload():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Ship-set gate" in text
    assert "tools/ship_set.py --check" in text
    gate = text.split("name: Ship-set gate")[1].split("\n      - name:")[0]
    assert "upload-artifact" not in gate
    assert "dist\\" not in gate.split("--check")[0]  # sanity: the gate step exists at all
    assert "release-shots" in gate


# --- P1 (Risk screen of 161d6e5): OpenSSL / Qt TLS set -----------------------


def test_runner_openssl_pair_and_qopensslbackend_are_banned():
    from tools.ship_set import is_banned

    for name in (
        "libcrypto-3-x64.dll",
        "libssl-3-x64.dll",
        "_internal/libcrypto-3-x64.dll",
        "_internal\\LIBSSL-3-X64.DLL",
        "PySide6/plugins/tls/qopensslbackend.dll",
        "_internal/PySide6/plugins/tls/QOpenSSLBackend.dll",
    ):
        assert is_banned(name), name
    for name in (
        "libcrypto-3.dll",
        "libssl-3.dll",
        "_internal/libcrypto-3.dll",
        "PySide6/plugins/tls/qschannelbackend.dll",
        "PySide6/plugins/tls/qcertonlybackend.dll",
    ):
        assert not is_banned(name), name


def test_check_ship_set_fails_on_any_change_to_the_openssl_dll_set(tmp_path):
    from tools.ship_set import check_ship_set

    root = _clean_onedir(tmp_path)
    internal = root / "_internal"
    assert check_ship_set(root) == []

    # An extra OpenSSL build (banned by name *and* outside the exact set).
    (internal / "libcrypto-3-x64.dll").write_bytes(b"x")
    problems = check_ship_set(root)
    assert any("banned file present" in p and "libcrypto-3-x64.dll" in p for p in problems)
    assert any("OpenSSL DLL set changed" in p for p in problems)
    (internal / "libcrypto-3-x64.dll").unlink()

    # An OpenSSL DLL under a name no banned pattern knows still fails the gate.
    (internal / "PySide6" / "libssl-3-arm64.dll").write_bytes(b"x")
    problems = check_ship_set(root)
    assert problems and all("banned" not in p for p in problems)
    assert any("OpenSSL DLL set changed" in p for p in problems)
    (internal / "PySide6" / "libssl-3-arm64.dll").unlink()

    # CPython's pair missing also fails.
    (internal / "libssl-3.dll").unlink()
    problems = check_ship_set(root)
    assert any("OpenSSL DLL set changed" in p and "libssl-3.dll" in p for p in problems)


def test_check_ship_set_fails_on_any_change_to_the_qt_tls_plugin_set(tmp_path):
    from tools.ship_set import check_ship_set

    root = _clean_onedir(tmp_path)
    tls = root / "_internal" / "PySide6" / "plugins" / "tls"
    (tls / "qopensslbackend.dll").write_bytes(b"x")
    problems = check_ship_set(root)
    assert any("qopensslbackend.dll" in p and "banned" in p for p in problems)
    assert any("Qt TLS plugin set changed" in p for p in problems)
    (tls / "qopensslbackend.dll").unlink()

    (tls / "qcertonlybackend.dll").unlink()
    problems = check_ship_set(root)
    assert any("Qt TLS plugin set changed" in p for p in problems)


def test_write_tls_list_records_the_shipped_openssl_and_tls_set(tmp_path):
    from tools.ship_set import main

    root = _clean_onedir(tmp_path)
    out = tmp_path / "tls.txt"
    assert main(["--check", str(root), "--write-tls-list", str(out)]) == 0
    assert out.read_text(encoding="utf-8").splitlines() == [
        "openssl _internal/libcrypto-3.dll",
        "openssl _internal/libssl-3.dll",
        "tls-plugin qcertonlybackend.dll",
        "tls-plugin qschannelbackend.dll",
    ]


def test_manifest_ship_set_matches_tools_ship_set():
    import json

    from tools.ship_set import (
        BANNED_PATTERNS,
        EXPECTED_OPENSSL_DLLS,
        EXPECTED_TLS_PLUGINS,
        REQUIRED_QT_DLLS,
    )

    manifest = json.loads(
        (ROOT / "packaging" / "distribution_manifest.json").read_text(encoding="utf-8")
    )
    ship = manifest["ship_set"]
    assert ship["banned_patterns"] == list(BANNED_PATTERNS)
    assert ship["also_shipped"] == list(EXPECTED_OPENSSL_DLLS)
    assert ship["shipped_qt_dlls"] == list(REQUIRED_QT_DLLS)
    pin = ship["openssl"]
    assert sorted(pin["dlls"]) == sorted(EXPECTED_OPENSSL_DLLS)
    assert pin["tls_plugins"] == list(EXPECTED_TLS_PLUGINS)
    assert pin["python"] == "3.12.10"
    for name, entry in pin["dlls"].items():
        assert entry["file_version"] == "3.0.16", name
        assert len(entry["sha256"]) == 64 and int(entry["sha256"], 16) >= 0, name
    for gone in ("libcrypto-3-x64.dll", "libssl-3-x64.dll"):
        assert gone not in ship["also_shipped"]


def test_ci_pins_build_python_and_fails_on_openssl_drift():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    build = text.split("  build-windows:")[1]
    assert 'python-version: "3.12.10"' in build.split("pip install")[0]
    step = build.split("name: OpenSSL pin")[1].split("\n      - name:")[0]
    for needle in (
        "file_version", "sha256", "OpenSSL DLL set changed", "qopensslbackend.dll",
        "throw", "OPENSSL-PIN: PASS", "pin.python",
    ):
        assert needle in step, needle
    assert "upload-artifact" not in step
    # The inventory no longer looks for the banned -x64 pair, and the ship-set
    # gate writes the OpenSSL/TLS list.
    assert "libcrypto-3-x64.dll" not in build.split("name: OpenSSL pin")[0]
    assert "--write-tls-list" in build
    # The pin runs before the ship-set gate and the self-capture.
    assert build.index("name: OpenSSL pin") < build.index("name: Ship-set gate")
    assert build.index("name: Ship-set gate") < build.index("name: Self-capture")


def test_app_makes_no_qt_network_or_qt_tls_calls():
    """P1 premise: banning qopensslbackend is safe because nothing in the app
    uses QtNetwork/QSsl; HTTPS goes through urllib (_ssl.pyd)."""
    offenders = []
    for path in [ROOT / "app.py", *sorted((ROOT / "orbitrx").rglob("*.py"))]:
        text = path.read_text(encoding="utf-8")
        for needle in ("QtNetwork", "QSsl", "QNetworkAccessManager", "QNetworkRequest"):
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {needle}")
    assert offenders == []
