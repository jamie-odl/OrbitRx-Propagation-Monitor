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
}

KEPT_SAMPLE_NAMES = {
    "PySide6/Qt6Core.dll",
    "PySide6/Qt6Gui.dll",
    "PySide6/Qt6Widgets.dll",
    "PySide6/Qt6Network.dll",
    "PySide6/Qt6Svg.dll",
    "opengl32sw.dll",
    "PySide6/plugins/imageformats/qsvg.dll",
    "PySide6/plugins/iconengines/qsvgicon.dll",
    "PySide6/plugins/tls/qschannelbackend.dll",
    "PySide6/plugins/tls/qopensslbackend.dll",
    "PySide6/plugins/tls/qcertonlybackend.dll",
    "PySide6/plugins/platforms/qwindows.dll",
    "PySide6/plugins/networkinformation/qnetworklistmanager.dll",
    "PySide6/plugins/generic/qtuiotouchplugin.dll",
}


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

    root = tmp_path / "OrbitRxMonitor"
    internal = root / "_internal" / "PySide6"
    internal.mkdir(parents=True)
    for name in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll", "Qt6Svg.dll"):
        (internal / name).write_bytes(b"x")
    assert check_ship_set(root) == []

    (internal / "Qt6Pdf.dll").write_bytes(b"x")
    problems = check_ship_set(root)
    assert any("Qt6Pdf.dll" in p for p in problems)

    (internal / "Qt6Pdf.dll").unlink()
    (internal / "Qt6Core.dll").unlink()
    problems = check_ship_set(root)
    assert any("Qt6Core.dll" in p for p in problems)


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
